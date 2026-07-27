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
can.

The ratchet therefore gates on ``total_gated`` -- data-carrying connections plus
any the classifier could not decide. Unclassified ones are included on purpose:
see ``Tripwire._classify`` for why an undecided connection has to count as a
breach rather than as a probe.

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
import os
import socket
import subprocess
import sys
import threading

# This file runs in two contexts and the import has to work in both: CI invokes
# it as a script (`python3 tests/datastore_tripwire.py`, so sys.path[0] is
# tests/ and the repo root is absent), while tests/test_datastore_guard.py
# imports it as `tests.datastore_tripwire` (so the repo root is on sys.path and
# tests/ is not). One implementation of the floor, reachable from both.
try:
    from tests.ci_executed_floor import check_floor
except ImportError:  # pragma: no cover - exercised by the script entry point
    from ci_executed_floor import check_floor

# The operator's real services. 26351 is the live Qdrant gRPC port from
# docker/.env; 6334 is qdrant-client's own gRPC default, used whenever that
# variable is unset. 23100 is Langfuse, which the suite also reaches.
PRODUCTION_PORTS = (26350, 26351, 28080, 23100, 6334)

# How long the measurement path waits for a connection to declare itself. This
# is a throughput budget, not a correctness knob: a connection that misses it is
# recorded as `unclassified` and gated as though it carried data, so the number
# can be tuned for speed without weakening the oracle.
CLASSIFY_TIMEOUT = 0.4

# The self-test does not race this budget at all. Its control client sends its
# payload and only then closes, and TCP delivers those in order, so the server's
# recv returns the bytes before it can ever see EOF. The timeout below is a
# hang-guard for a control that never connects -- not the thing that decides the
# result.
SELF_TEST_CLASSIFY_TIMEOUT = 30.0

# The only wrapped exit codes that mean a suite actually ran.
#
# 0 is a clean run and 1 is a run with failing tests -- both executed the suite,
# so both produced a connection count worth comparing. Every other pytest exit
# code means the suite did not run: 2 interrupted (a collection error), 3
# internal error, 4 usage error, 5 nothing collected.
#
# That distinction is the whole point. A run that dies before executing anything
# connects to nothing, so it reports a count of zero -- which the ratchet, left
# to compare numbers alone, reads as the best result it has ever seen. A zero
# from a dead run is the absence of a measurement, not a clean bill of health,
# and it is the same "counter reading zero because it is broken" failure the
# self-test exists to catch, one layer further out.
HEALTHY_WRAPPED_EXIT_CODES = frozenset({0, 1})


class Tripwire:
    """Binds ports and counts accepts until stopped."""

    def __init__(self, ports, classify_timeout=CLASSIFY_TIMEOUT):
        self.ports = list(ports)
        self.counts = dict.fromkeys(self.ports, 0)
        # A bare liveness probe (connect + close, no payload) cannot read or
        # write anything. A real client sends bytes immediately -- an HTTP
        # request line, or the HTTP/2 preface. Counting them apart keeps a
        # harmless probe from reading as a data breach.
        self.data_counts = dict.fromkeys(self.ports, 0)
        self.probe_counts = dict.fromkeys(self.ports, 0)
        # Connections that produced neither definite outcome inside the budget.
        # See _classify: these are counted as breaches, not as probes.
        self.unclassified_counts = dict.fromkeys(self.ports, 0)
        self._classify_timeout = classify_timeout
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
                self._classify(port, conn)
            finally:
                conn.close()

    def _classify(self, port, conn):
        """Decide whether a connection carried data, and fail toward "it did".

        Exactly two outcomes are definite, and both are events rather than
        elapsed time:

          * bytes arrive              -> a real client; it spoke a protocol
          * recv returns b"" (EOF)    -> the peer closed having sent nothing,
                                         which is precisely a liveness probe

        Anything else -- a timeout, a reset -- is *not* evidence of a probe. It
        is absence of evidence, and it is counted as `unclassified` and gated
        alongside data-carrying connections.

        That direction is the whole point. The previous version treated "no
        bytes within 0.4s" as a probe, so a real payload connection on a loaded
        runner was recorded as harmless. The ratchet gates on this number, so
        the error direction was toward *under*-reporting: a genuine regression
        could slip in under the ceiling. A guard may cost a false alarm; it may
        not quietly miss a breach.

        Note also that a timeout cannot be made safe by enlarging it. A larger
        timeout is still a bet on the machine being fast enough, which is the
        "works on my machine" property this plan exists to remove. The
        self-test's determinism comes from TCP ordering instead -- see
        _payload_control.
        """
        try:
            conn.settimeout(self._classify_timeout)
            payload = conn.recv(65536)
        except (TimeoutError, OSError):
            with self._lock:
                self.unclassified_counts[port] += 1
            return
        with self._lock:
            if payload:
                self.data_counts[port] += 1
            else:
                self.probe_counts[port] += 1

    def disarm(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        for srv in self._listeners.values():
            with contextlib.suppress(OSError):
                srv.close()

    def report(self, wrapped_exit_code=None):
        data = sum(self.data_counts.values())
        unclassified = sum(self.unclassified_counts.values())
        return {
            "accepts": {str(p): self.counts[p] for p in self.ports},
            "data_carrying": {str(p): self.data_counts[p] for p in self.ports},
            "probes": {str(p): self.probe_counts[p] for p in self.ports},
            "unclassified": {str(p): self.unclassified_counts[p] for p in self.ports},
            "total_accepts": sum(self.counts.values()),
            "total_data_carrying": data,
            "total_probes": sum(self.probe_counts.values()),
            "total_unclassified": unclassified,
            # What the ratchet gates on. Unclassified connections are included
            # because they might have carried data; excluding them would let a
            # regression hide behind a slow runner.
            "total_gated": data + unclassified,
            "wrapped_exit_code": wrapped_exit_code,
        }


def _connect(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def _payload_control(port):
    """Connect, send, then close -- in that order, deliberately.

    TCP delivers the payload before the FIN, so the server's recv returns the
    bytes and can never observe EOF first. The classification is therefore
    settled by protocol ordering, not by whether the machine was fast enough.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)
    try:
        sock.connect(("127.0.0.1", port))
        sock.sendall(b"GET / HTTP/1.1\r\nHost: tripwire-self-test\r\n\r\n")
    finally:
        sock.close()


def self_test():
    """Prove the counter stays silent, rises, and classifies. Returns exit code."""
    probe_port, grpc_port = PRODUCTION_PORTS[0], PRODUCTION_PORTS[1]

    quiet = Tripwire(PRODUCTION_PORTS, classify_timeout=SELF_TEST_CLASSIFY_TIMEOUT)
    quiet.arm()
    quiet.disarm()
    if quiet.report()["total_accepts"] != 0:
        print("SELF-TEST FAIL: counter registered an accept with no client")
        return 1
    print("  negative control: 0 accepts with nothing connecting -- OK")

    live = Tripwire(PRODUCTION_PORTS, classify_timeout=SELF_TEST_CLASSIFY_TIMEOUT)
    live.arm()
    grpc_ran = False
    try:
        if not _connect(probe_port):
            print(f"SELF-TEST FAIL: could not reach the tripwire on {probe_port}")
            return 1
        _payload_control(probe_port)
        grpc_ran = _grpc_probe(grpc_port)
    finally:
        live.disarm()

    result = live.report()
    port, gport = str(probe_port), str(grpc_port)

    if result["accepts"][port] < 2:
        print("SELF-TEST FAIL: counter did not rise on deliberate connections")
        return 1
    print(f"  positive control: accepts counted -- {result['accepts']}")

    if result["probes"][port] < 1:
        print(
            "SELF-TEST FAIL: a connect-then-close carried no bytes but was not "
            "classified as a probe, so the two cases are not being told apart"
        )
        return 1
    print(f"  positive control: bare probe classified -- {result['probes']}")

    if result["data_carrying"][port] < 1:
        print(
            "SELF-TEST FAIL: a payload-carrying connection was not classified "
            "as data-carrying, so the oracle cannot tell a probe from a breach"
        )
        return 1
    print(f"  positive control: payload classified -- {result['data_carrying']}")

    if result["total_unclassified"]:
        print(
            "SELF-TEST FAIL: "
            f"{result['total_unclassified']} connection(s) could not be "
            f"classified ({result['unclassified']}). Every control here has a "
            "definite outcome, so this means the classifier is racing the "
            "machine rather than reading the protocol."
        )
        return 1
    print("  no unclassified connections -- classification is deterministic")

    if grpc_ran:
        if result["accepts"][gport] < 1:
            print(
                "SELF-TEST FAIL: a real gRPC connection was made but the "
                f"counter on {grpc_port} did not rise. This is the exact case a "
                "socket-layer guard is blind to; the tripwire must see it."
            )
            return 1
        print(f"  positive control: gRPC counted on {grpc_port} -- OK")
    elif os.environ.get("TRIPWIRE_REQUIRE_GRPC", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        print(
            "SELF-TEST FAIL: grpcio is not importable, so the gRPC leg of the "
            "positive control did not run, and TRIPWIRE_REQUIRE_GRPC is set.\n"
            "That leg is not optional here: gRPC is what an earlier "
            "socket-layer guard could not see, and it is why this tripwire "
            "counts at the accept layer. A positive control that silently omits "
            "its most important case is the defect that guard had.\n"
            "grpcio ships with the pinned qdrant-client[grpc] extra -- if it is "
            "missing, the interpreter running this is probably not the one the "
            "dependencies were installed into."
        )
        return 1
    else:
        print(
            "  DEGRADED CONTROL: grpcio not importable, gRPC leg SKIPPED. "
            "This control is weaker than it looks; set TRIPWIRE_REQUIRE_GRPC=1 "
            "to make this a failure."
        )

    print("SELF-TEST PASS: the counter can stay silent, rise, and classify.")
    return 0


def _grpc_probe(port):
    """Drive a real gRPC connection; return whether the leg actually ran.

    This is the leg that matters most. grpcio's C-core never enters Python's
    ``socket`` module, so a guard patching ``socket`` sees nothing here while
    real connections reach the protected port. The caller decides how loudly to
    complain when grpcio is missing -- what it must not do is report OK.
    """
    try:
        import grpc
    except ImportError:
        return False
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    try:
        with contextlib.suppress(Exception):
            # Expected to fail: the tripwire accepts and drops the connection.
            # The accept is the signal, not the RPC outcome.
            grpc.channel_ready_future(channel).result(timeout=5)
    finally:
        channel.close()
    return True


def check_run_happened(report, baseline, junit_path):
    """Fail unless the wrapped run executed the suite it claims to have.

    A ratchet compares a measurement to a ceiling, so it has to establish there
    *was* a measurement before the comparison means anything. Two ways a run can
    produce a passing number without proving anything, both observed here:

      * it died before executing -- collection error, usage error, no tests
        collected. Nothing connects, so the count is zero and the ceiling is
        trivially satisfied.
      * it executed a fraction of the suite -- a mis-typed path, a marker
        expression that silently selected forty tests instead of thousands, or
        a service outage that turned every test into a skip. The exit code is a
        clean 0 and the count is honestly low, because most of the suite never
        ran.

    The exit code catches the first and cannot catch the second; the executed
    floor catches the second. Both are needed.

    The floor is on tests that EXECUTED, not tests that were collected. It used
    to be the latter, and that was an instance of the very defect this file
    exists to catch: JUnit's ``tests`` attribute counts skips, so the old gate
    passed a run in which all ~6,500 tests collected and every one skipped --
    satisfied without the property it stood for. See tests/ci_executed_floor.py.

    Returns an error message, or None when the run is trustworthy.
    """
    exit_code = report.get("wrapped_exit_code")
    if exit_code not in HEALTHY_WRAPPED_EXIT_CODES:
        return (
            f"the wrapped run exited {exit_code!r}, so the suite did not "
            "execute and this report measures nothing.\n"
            f"Only {sorted(HEALTHY_WRAPPED_EXIT_CODES)} mean a suite ran (clean, "
            "or with failing tests). Anything else is a collection error, a "
            "usage error, an internal error, or an empty selection -- and a run "
            "that never executed connects to nothing, so its count of zero is "
            "the absence of a measurement rather than a clean result.\n"
            "Fix the run itself; do not read this number."
        )

    # The old collected-basis key. A baseline still carrying it would otherwise
    # be read as "no floor configured" and the gate would silently vanish --
    # the same class of quiet disablement this module exists to prevent.
    if "min_tests" in baseline:
        return (
            "this baseline still sets 'min_tests', which counted COLLECTED "
            "tests. That number includes skips, so it was satisfied by a run "
            "in which every test skipped and nothing executed. Rename the key "
            "to 'min_executed' and set it against tests that actually ran -- "
            "see tests/ci_executed_floor.py."
        )

    floor = baseline.get("min_executed")
    if floor is None:
        return None

    problem = check_floor(junit_path, floor, "the tripwire-wrapped suite")
    if problem:
        return problem
    print(f"run health: exit={exit_code}")
    return None


def check_ratchet(report_path, baseline_path, junit_path=None):
    """Fail when data-carrying accepts rise above a port's recorded ceiling.

    A ratchet rather than a fixed threshold: the count varies run to run because
    gRPC retries a variable number of times, so a hard number would flake. What
    matters is the direction -- a new test that reaches production pushes the
    count up, and that is the regression worth failing on.

    The gate is per-port. The whole-suite total is printed but nothing fails on
    it, because a total over these ports cannot detect what a total was for. The
    tripwire binds only PRODUCTION_PORTS, so the total is by construction the sum
    of the per-port counts: a port nobody thought to watch is never bound, never
    contributes, and cannot move it. The total therefore caught nothing the
    per-port ceilings do not already catch, while carrying all of the jitter --
    it read 25, 38 and 37 against a ceiling of 40 across three green runs, all of
    that spread coming from one retry-prone port. A gate that cannot catch its
    own quarry but can fail on noise gets raised, raised again, then ignored.
    What replaces it is the coverage assertion in tests/test_datastore_guard.py:
    every bound port must carry a ceiling, which answers "did we forget to gate
    something" directly instead of by proxy.

    The comparison is only reached once the run has been shown to have happened
    -- see check_run_happened for why a number alone cannot be trusted.
    """
    with open(report_path) as handle:
        report = json.load(handle)
    with open(baseline_path) as handle:
        baseline = json.load(handle)

    broken = check_run_happened(report, baseline, junit_path)
    if broken:
        print(f"\nFAIL: {broken}")
        return 1

    # Gated number includes unclassified connections -- see Tripwire._classify.
    # Printed as a trend line only; the gate below is per-port.
    observed = report["total_gated"]

    print(f"gated connections: {observed} total (informational -- gate is per-port)")
    print(f"  data-carrying: {report['data_carrying']}")
    print(f"  unclassified (counted as breaches): {report['unclassified']}")
    print(f"  bare probes (not gated): {report['probes']}")
    print(f"  total accepts: {report['total_accepts']}")

    failed = False

    # The gate. Each port carries its own ceiling, sized to what that port
    # actually does: 26350 is pinned exactly because it is the REST write path
    # and does not move, while a retry-prone client default is given room. A
    # ceiling is the maximum across every environment the gate runs in -- see the
    # baseline's own notes.
    for port, ceiling in sorted(baseline.get("max_per_port", {}).items()):
        seen = report["data_carrying"].get(port, 0) + report["unclassified"].get(
            port, 0
        )
        if seen > ceiling:
            print(
                f"\nFAIL: port {port} saw {seen} gated connections, above its "
                f"ceiling of {ceiling}.\n"
                "Something new in the suite reaches that service. Point it at a "
                "throwaway instance, or gate it as an integration test."
            )
            failed = True

    if failed:
        return 1

    print("\nPASS: no increase in connections to production ports.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", help="write the accept report here")
    parser.add_argument("--check", help="ratchet-check a report written earlier")
    parser.add_argument("--baseline", help="baseline file for --check")
    parser.add_argument(
        "--junit",
        help="pytest JUnit XML from the wrapped run, for the collected-tests floor",
    )
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.check:
        if not args.baseline:
            parser.error("--check requires --baseline")
        return check_ratchet(args.check, args.baseline, args.junit)

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
