"""Tripwire accept-counter: the acceptance oracle for datastore isolation.

TD-881. Binds the production ports *inside* a network namespace and counts every
TCP connection the suite makes to them. Each count is a connection that would
have reached the operator's live services on an unwrapped run.

Why the count and not the exit code
-----------------------------------
qdrant-client wraps a failed connection into ResponseHandlingException, and this
repository has many broad ``except Exception`` graceful-degradation handlers, so
a run that touched production repeatedly still exits 0. Measured on this suite:
147 accepts while pytest's failures were ten unrelated tests. The exit code
carries no signal about isolation and must never be used as the oracle.

An armed run is not the same suite as an unarmed one
----------------------------------------------------
Arming the tripwire changes the behaviour of the thing it measures, and the
number has to be read with that in mind. ``_check_service_available`` in
tests/conftest.py probes a port with ``connect_ex``. In a bare namespace that
probe is refused, so tests carrying a ``requires_*`` marker skip cleanly. With
the tripwire listening the same probe *succeeds*, so those tests do not skip --
they run, and each probe registers an accept of its own.

Two consequences. The accept total includes connections that would not have
happened without the tripwire, so it can never be expected to reach zero by
arithmetic alone. And a bare probe is counted separately from a connection that
carried bytes, because a probe cannot read or write anything while a real client
can: that is what ``data_carrying`` is for, and why the ratchet gates on it.

Why the self-test is not optional
---------------------------------
A counter reading zero because it is broken is indistinguishable from a counter
reading zero because nothing connected. A previous guard design passed its own
self-test while leaving the production path wide open. ``--self-test`` therefore
asserts the counter *rises* on a deliberate connection, over the raw socket path
and the gRPC path both, because gRPC is what defeated that earlier design:
grpcio's C-core never enters Python's ``socket`` module, so anything patching
``socket`` sees nothing. This tripwire sits at the TCP accept layer instead,
which no client library can bypass.
"""

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import threading

# The operator's real services. 26351 is the live Qdrant gRPC port from
# docker/.env; 6334 is qdrant-client's own gRPC default, used whenever that
# variable is unset. 23100 is Langfuse, which the suite also reaches.
PRODUCTION_PORTS = (26350, 26351, 28080, 23100, 6334)


class Tripwire:
    """Binds ports and counts accepts until stopped."""

    def __init__(self, ports):
        self.ports = list(ports)
        self.counts = dict.fromkeys(self.ports, 0)
        # A bare liveness probe (connect + close, no payload) cannot read or
        # write anything. A real client sends bytes immediately -- an HTTP
        # request line, or the HTTP/2 preface. Counting them apart keeps a
        # harmless probe from reading as a data breach.
        self.data_counts = dict.fromkeys(self.ports, 0)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listeners = {}
        self._threads = []

    def arm(self):
        for port in self.ports:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                srv.bind(("127.0.0.1", port))
            except OSError as exc:
                srv.close()
                self.disarm()
                raise RuntimeError(
                    f"tripwire could not bind port {port}: {exc}. Inside a "
                    "network namespace this should always succeed, even while "
                    "the host holds the same port."
                ) from exc
            srv.listen(128)
            srv.settimeout(0.5)
            self._listeners[port] = srv

        for port, srv in self._listeners.items():
            thread = threading.Thread(target=self._serve, args=(port, srv), daemon=True)
            thread.start()
            self._threads.append(thread)

    def _serve(self, port, srv):
        while not self._stop.is_set():
            try:
                conn, _ = srv.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with self._lock:
                self.counts[port] += 1
            try:
                conn.settimeout(0.4)
                try:
                    payload = conn.recv(65536)
                except OSError:
                    payload = b""
                if payload:
                    with self._lock:
                        self.data_counts[port] += 1
            finally:
                conn.close()

    def disarm(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        for srv in self._listeners.values():
            with contextlib.suppress(OSError):
                srv.close()

    def report(self, wrapped_exit_code=None):
        return {
            "accepts": {str(p): self.counts[p] for p in self.ports},
            "data_carrying": {str(p): self.data_counts[p] for p in self.ports},
            "total_accepts": sum(self.counts.values()),
            "total_data_carrying": sum(self.data_counts.values()),
            "wrapped_exit_code": wrapped_exit_code,
        }


def _connect(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def self_test():
    """Prove the counter can both stay silent and rise. Returns an exit code."""
    probe_port = PRODUCTION_PORTS[0]

    quiet = Tripwire(PRODUCTION_PORTS)
    quiet.arm()
    quiet.disarm()
    if quiet.report()["total_accepts"] != 0:
        print("SELF-TEST FAIL: counter registered an accept with no client")
        return 1
    print("  negative control: 0 accepts with nothing connecting -- OK")

    live = Tripwire(PRODUCTION_PORTS)
    live.arm()
    try:
        if not _connect(probe_port):
            print(f"SELF-TEST FAIL: could not reach the tripwire on {probe_port}")
            return 1
        _grpc_probe(probe_port)
    finally:
        live.disarm()

    result = live.report()
    if result["accepts"][str(probe_port)] < 1:
        print("SELF-TEST FAIL: counter did not rise on a deliberate connection")
        return 1
    print(f"  positive control: raw socket counted -- {result['accepts']}")

    if result["data_carrying"][str(probe_port)] < 1:
        print(
            "SELF-TEST FAIL: a payload-carrying connection was not classified "
            "as data-carrying, so the oracle cannot tell a probe from a breach"
        )
        return 1
    print(f"  positive control: payload classified -- {result['data_carrying']}")
    print("SELF-TEST PASS: the counter can stay silent and can rise.")
    return 0


def _grpc_probe(port):
    """Drive a real gRPC connection, the path a socket-layer guard cannot see."""
    try:
        import grpc
    except ImportError:
        print("  (grpcio unavailable; skipped the gRPC leg of the positive control)")
        return
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    try:
        grpc.channel_ready_future(channel).result(timeout=3)
    except Exception:
        # Expected: the tripwire accepts and drops. The accept is the signal.
        pass
    finally:
        channel.close()


def check_ratchet(report_path, baseline_path):
    """Fail when data-carrying accepts rise above the recorded baseline.

    A ratchet rather than a fixed threshold: the count varies run to run because
    gRPC retries a variable number of times, so a hard number would flake. What
    matters is the direction -- a new test that reaches production pushes the
    count up, and that is the regression worth failing on.
    """
    with open(report_path) as handle:
        report = json.load(handle)
    with open(baseline_path) as handle:
        baseline = json.load(handle)

    observed = report["total_data_carrying"]
    allowed = baseline["max_data_carrying"]
    # Headroom for run-to-run gRPC retry jitter. Only a drop clearly outside it
    # is worth tightening the ceiling for; nagging about jitter trains people to
    # ignore the message.
    jitter = baseline.get("jitter_allowance", 0)

    print(f"data-carrying accepts: observed={observed} baseline={allowed}")
    print(f"  per port observed: {report['data_carrying']}")
    print(f"  total accepts (incl. bare probes): {report['total_accepts']}")

    if observed > allowed:
        print(
            f"\nFAIL: {observed} data-carrying connections to production ports, "
            f"above the baseline of {allowed}.\n"
            "Something new in the suite reaches the operator's datastore. Point "
            "it at a throwaway instance, or gate it as an integration test."
        )
        return 1

    if observed < allowed - jitter:
        print(
            f"\nThe count fell to {observed}. Lower max_data_carrying in "
            f"{baseline_path} so the ground gained cannot be given back."
        )
    print("\nPASS: no increase in connections to production ports.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", help="write the accept report here")
    parser.add_argument("--check", help="ratchet-check a report written earlier")
    parser.add_argument("--baseline", help="baseline file for --check")
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.check:
        if not args.baseline:
            parser.error("--check requires --baseline")
        return check_ratchet(args.check, args.baseline)

    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        parser.error("nothing to run: pass a command after --")

    tripwire = Tripwire(PRODUCTION_PORTS)
    tripwire.arm()
    print(f"tripwire armed on {list(PRODUCTION_PORTS)}", file=sys.stderr)
    try:
        exit_code = subprocess.call(cmd)
    finally:
        tripwire.disarm()

    result = tripwire.report(exit_code)
    if args.report:
        with open(args.report, "w") as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2), file=sys.stderr)

    # Deliberately 0: the wrapped command's failures are not this tool's verdict.
    # The verdict is --check against the baseline.
    return 0


if __name__ == "__main__":
    sys.exit(main())
