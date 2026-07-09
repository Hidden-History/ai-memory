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
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"

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
        """Reset memory.peak to the current value (Linux >= 5.19, BP-179 §2)."""
        self.exec_fn(
            self.container, "sh", "-c", f"echo 0 > {self._path('memory.peak')}"
        )

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


_DMESG_OOM_PATTERN = re.compile(r"Out of memory|Killed process", re.IGNORECASE)


def scan_dmesg_oom(process_pattern: str = "embed|onnx|python") -> list[str]:
    """Return dmesg lines showing an OOM-kill matching `process_pattern`.

    Per BP-179 §3, dmesg is one of the two authoritative OOM signals (the other
    is cgroup memory.events:oom_kill). Raises CgroupAccessError if dmesg cannot
    be read (e.g. permission denied) — callers must surface this per the
    BLOCKER PROTOCOL rather than silently treating it as zero kills.
    """
    result = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise CgroupAccessError(f"dmesg failed: {result.stderr.strip()}")
    proc_re = re.compile(process_pattern, re.IGNORECASE)
    return [
        line
        for line in result.stdout.splitlines()
        if _DMESG_OOM_PATTERN.search(line) and proc_re.search(line)
    ]
