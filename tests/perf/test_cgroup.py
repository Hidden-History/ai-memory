"""Unit tests for scripts/perf/embedding_capacity/cgroup.py — cgroup-v2 access.

Fully mocked at the exec_fn / subprocess.run boundary (BP-179 §2/§3 logic under
test, never a live container).
"""

import pytest
from embedding_capacity import cgroup


def _stub_exec(responses):
    def exec_fn(container, *cmd):
        key = " ".join(cmd)
        if key not in responses:
            raise AssertionError(f"unexpected exec command: {key!r}")
        return responses[key]

    return exec_fn


def test_read_current_parses_int():
    reader = cgroup.DockerCgroupReader(
        "c1", exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.current": "123456\n"})
    )
    assert reader.read_current() == 123456


def test_read_peak_parses_int():
    reader = cgroup.DockerCgroupReader(
        "c1", exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.peak": "6710886400\n"})
    )
    assert reader.read_peak() == 6710886400


def test_read_max_handles_literal_max():
    reader = cgroup.DockerCgroupReader(
        "c1", exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.max": "max\n"})
    )
    assert reader.read_max() is None


def test_read_max_parses_int():
    reader = cgroup.DockerCgroupReader(
        "c1", exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.max": "6442450944\n"})
    )
    assert reader.read_max() == 6442450944


def test_read_events_parses_multiple_keys():
    raw = "low 0\nhigh 3\nmax 92979\noom 0\noom_kill 0\noom_group_kill 0\n"
    reader = cgroup.DockerCgroupReader(
        "c1", exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.events": raw})
    )
    assert reader.read_events() == {
        "low": 0,
        "high": 3,
        "max": 92979,
        "oom": 0,
        "oom_kill": 0,
        "oom_group_kill": 0,
    }


def test_oom_kill_count_reads_from_events():
    reader = cgroup.DockerCgroupReader(
        "c1",
        exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.events": "oom_kill 45\n"}),
    )
    assert reader.oom_kill_count() == 45


def test_oom_kill_count_defaults_to_zero_when_absent():
    reader = cgroup.DockerCgroupReader(
        "c1", exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.events": "low 0\n"})
    )
    assert reader.oom_kill_count() == 0


def test_reset_peak_writes_zero_to_the_peak_file():
    calls = []

    def exec_fn(container, *cmd):
        calls.append(cmd)
        return ""

    reader = cgroup.DockerCgroupReader("c1", exec_fn=exec_fn)
    reader.reset_peak()
    assert calls == [("sh", "-c", "echo 0 > /sys/fs/cgroup/memory.peak")]


def test_custom_cgroup_root_is_used_in_paths():
    calls = []

    def exec_fn(container, *cmd):
        calls.append(cmd)
        return "0\n"

    reader = cgroup.DockerCgroupReader(
        "c1", cgroup_root="/custom/root", exec_fn=exec_fn
    )
    reader.read_current()
    assert calls == [("cat", "/custom/root/memory.current")]


def test_read_int_raises_on_garbage():
    reader = cgroup.DockerCgroupReader(
        "c1",
        exec_fn=_stub_exec({"cat /sys/fs/cgroup/memory.current": "not-a-number\n"}),
    )
    with pytest.raises(cgroup.CgroupAccessError):
        reader.read_current()


def test_docker_exec_raises_cgroup_access_error_on_nonzero_exit(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "Error: No such container: missing"

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    with pytest.raises(cgroup.CgroupAccessError):
        cgroup._docker_exec("missing", "cat", "/x")


def test_scan_dmesg_oom_filters_by_pattern(monkeypatch):
    class _Result:
        returncode = 0
        stdout = (
            "[100.0] some unrelated line\n"
            "[101.0] Out of memory: Killed process 123 (python) total-vm:...\n"
            "[102.0] Killed process 456 (other-proc)\n"
        )
        stderr = ""

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    lines = cgroup.scan_dmesg_oom(process_pattern="python")
    assert len(lines) == 1
    assert "python" in lines[0]


def test_scan_dmesg_oom_returns_empty_when_no_kills(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "[100.0] unrelated boot message\n"
        stderr = ""

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    assert cgroup.scan_dmesg_oom() == []


def test_scan_dmesg_oom_raises_on_permission_denied(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "dmesg: read kernel buffer failed: Operation not permitted"

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    with pytest.raises(cgroup.CgroupAccessError):
        cgroup.scan_dmesg_oom()
