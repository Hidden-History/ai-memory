"""cgroup-v2 memory signal access for the embedding capacity harness (BP-179 §2/§3).

Reads memory.current / memory.peak / memory.events / memory.max from inside the
running embedding container via `docker exec`, and scans dmesg for OOM-kill lines.
Per BP-179 §3, `memory.events:oom_kill` + dmesg are the ONLY authoritative OOM
signals for the soak gate — the Docker OOMKilled flag and the app's own
embedding_oom_events_total gauge are blind to worker-level kills and must never
be used to certify an envelope safe.
"""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"
DEFAULT_POLL_INTERVAL_SECONDS = 0.05

ExecFn = Callable[..., str]


class CgroupAccessError(RuntimeError):
    """Raised when a cgroup file or dmesg cannot be read from the harness context."""


def _docker_exec(container: str, *cmd: str) -> str:
    """Run a command inside `container` via `docker exec` and return stdout."""
    result = subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise CgroupAccessError(
            f"docker exec {container} {' '.join(cmd)} failed "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _parse_events(raw: str) -> dict[str, int]:
    events: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                events[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return events


@dataclass
class DockerCgroupReader:
    """Reads cgroup-v2 memory files from inside a container.

    `exec_fn` defaults to a real `docker exec` call; tests inject a stub that
    returns canned output for a given command, so this class is fully
    unit-testable without a live container (BLOCKER PROTOCOL: if the real
    `exec_fn` raises CgroupAccessError against the live container, the harness
    must stop and report — never guess a value).
    """

    container: str
    cgroup_root: str = DEFAULT_CGROUP_ROOT
    exec_fn: ExecFn = _docker_exec

    def _path(self, name: str) -> str:
        return f"{self.cgroup_root}/{name}"

    def read_current(self) -> int:
        return self._read_int("memory.current")

    def read_peak(self) -> int:
        return self._read_int("memory.peak")

    def read_max(self) -> int | None:
        return self._read_maybe_int("memory.max")

    def reset_peak(self) -> None:
        """Reset memory.peak to the current value.

        Requires Linux >= 6.8 AND a writable cgroup mount (BP-179 §2, corrected
        PM #387) — reading memory.peak alone only needs >= 5.19. Raises
        CgroupAccessError if the reset is unsupported (e.g. a read-only cgroup
        FS, as verified on the WSL2 6.6 target); callers needing a fallback
        should use `try_reset_peak()` instead of calling this directly.
        """
        self.exec_fn(
            self.container, "sh", "-c", f"echo 0 > {self._path('memory.peak')}"
        )

    def try_reset_peak(self) -> bool:
        """Attempt `reset_peak()`, returning False instead of raising if unsupported.

        Use this to decide between the memory.peak-reset burst measurement and
        the dense-poll `memory.current` fallback (BP-179 §2 corrected). A True
        return means memory.peak has already been reset as a side effect.
        """
        try:
            self.reset_peak()
        except CgroupAccessError:
            return False
        return True

    def read_events(self) -> dict[str, int]:
        raw = self.exec_fn(self.container, "cat", self._path("memory.events"))
        return _parse_events(raw)

    def oom_kill_count(self) -> int:
        return self.read_events().get("oom_kill", 0)

    def _read_int(self, name: str) -> int:
        raw = self.exec_fn(self.container, "cat", self._path(name)).strip()
        try:
            return int(raw)
        except ValueError as e:
            raise CgroupAccessError(f"non-integer {name}: {raw!r}") from e

    def _read_maybe_int(self, name: str) -> int | None:
        raw = self.exec_fn(self.container, "cat", self._path(name)).strip()
        if raw == "max":
            return None
        try:
            return int(raw)
        except ValueError as e:
            raise CgroupAccessError(f"unparseable {name}: {raw!r}") from e


@dataclass
class PeakPoller:
    """Background dense-poll of memory.current — the burst-peak fallback when
    memory.peak reset is unsupported (BP-179 §2 corrected: kernel < 6.8 or a
    read-only cgroup mount, verified true on the WSL2 6.6.114 target).

    Runs `reader.read_current()` on a poll thread (docker exec is blocking)
    every `interval_seconds` and tracks the max observed, so it can run
    alongside an async burst without blocking the event loop. Call `start()`
    before driving load, `stop()` after — `stop()` returns the observed max.
    """

    reader: DockerCgroupReader
    interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    _max_seen: int = field(default=0, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _poll_error: Exception | None = field(default=None, init=False)

    def start(self) -> None:
        self._max_seen = self.reader.read_current()
        self._stop_event.clear()
        self._poll_error = None
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                current = self.reader.read_current()
            except CgroupAccessError as e:
                # Non-fatal (a long soak shouldn't abort on one transient
                # docker exec hiccup) but must not be silent — the peak from
                # this point on is a floor, not a true max, so callers need
                # to see it (BLOCKER PROTOCOL: never guess a value quietly).
                self._poll_error = e
                print(
                    f"WARNING: PeakPoller lost its docker exec read mid-poll "
                    f"({e}) — peak reporting is degraded from here on (last "
                    f"observed: {self._max_seen} bytes)"
                )
                break
            self._max_seen = max(self._max_seen, current)
            self._stop_event.wait(self.interval_seconds)

    def stop(self) -> int:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 5)
        return self._max_seen

    @property
    def degraded(self) -> bool:
        """True if the poll loop exited early on a docker exec read failure."""
        return self._poll_error is not None


_DMESG_OOM_PATTERN = re.compile(r"Out of memory|Killed process", re.IGNORECASE)
_DMESG_TIMESTAMP_PATTERN = re.compile(r"^\[\s*(\d+\.\d+)\]")


def _parse_dmesg_timestamp(line: str) -> float | None:
    match = _DMESG_TIMESTAMP_PATTERN.match(line)
    return float(match.group(1)) if match else None


def dmesg_baseline() -> float:
    """Pre-flight dmesg readability check + baseline kernel timestamp.

    Call this at the START of a soak (not hours in) so a permission problem
    surfaces immediately, and pass the returned timestamp to `scan_dmesg_oom`
    as `since_timestamp` so stale prior-run kills in the ring buffer aren't
    re-reported as this run's failures (BP-179 §3 corrected). Raises
    CgroupAccessError if dmesg cannot be read.
    """
    result = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise CgroupAccessError(f"dmesg failed: {result.stderr.strip()}")
    timestamps = [
        ts
        for line in result.stdout.splitlines()
        if (ts := _parse_dmesg_timestamp(line)) is not None
    ]
    return max(timestamps) if timestamps else 0.0


def scan_dmesg_oom(
    process_pattern: str = "embed|onnx|python", since_timestamp: float = 0.0
) -> list[str]:
    """Return dmesg lines showing an OOM-kill matching `process_pattern`.

    Per BP-179 §3, dmesg is one of the two authoritative OOM signals (the other
    is cgroup memory.events:oom_kill). `since_timestamp` (from `dmesg_baseline()`
    taken before the run) excludes stale prior-run kills — the ring buffer
    holds everything since boot, not just this run. A line whose timestamp
    can't be parsed is kept (fail toward reporting, not silently dropping a
    possible kill). Raises CgroupAccessError if dmesg cannot be read (e.g.
    permission denied) — callers must surface this per the BLOCKER PROTOCOL
    rather than silently treating it as zero kills.
    """
    result = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise CgroupAccessError(f"dmesg failed: {result.stderr.strip()}")
    proc_re = re.compile(process_pattern, re.IGNORECASE)
    lines = []
    for line in result.stdout.splitlines():
        if not (_DMESG_OOM_PATTERN.search(line) and proc_re.search(line)):
            continue
        ts = _parse_dmesg_timestamp(line)
        if ts is not None and ts <= since_timestamp:
            continue
        lines.append(line)
    return lines
