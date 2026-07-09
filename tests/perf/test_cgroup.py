"""Unit tests for scripts/perf/embedding_capacity/cgroup.py — cgroup-v2 access.

Fully mocked at the exec_fn / subprocess.run boundary (BP-179 §2/§3 logic under
test, never a live container).
"""

import time

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


def test_try_reset_peak_returns_true_on_success():
    reader = cgroup.DockerCgroupReader("c1", exec_fn=lambda *a: "")
    assert reader.try_reset_peak() is True


def test_try_reset_peak_returns_false_when_reset_unsupported():
    # BP-179 §2 corrected: kernel 6.6 / read-only cgroup -> reset raises.
    def exec_fn(container, *cmd):
        raise cgroup.CgroupAccessError("Read-only file system")

    reader = cgroup.DockerCgroupReader("c1", exec_fn=exec_fn)
    assert reader.try_reset_peak() is False


def test_peak_poller_tracks_max_current_over_time():
    # First 2 reads return a low baseline value, every read after that returns
    # a higher value forever — regardless of exact thread-scheduling timing,
    # any run long enough to poll more than twice must observe the higher max.
    call_count = {"n": 0}

    def exec_fn(container, *cmd):
        call_count["n"] += 1
        return "1000" if call_count["n"] <= 2 else "5000"

    reader = cgroup.DockerCgroupReader("c1", exec_fn=exec_fn)
    poller = cgroup.PeakPoller(reader, interval_seconds=0.01)
    poller.start()
    time.sleep(0.1)
    peak = poller.stop()

    assert peak == 5000


def test_peak_poller_stops_cleanly_when_never_started():
    reader = cgroup.DockerCgroupReader("c1", exec_fn=lambda *a: "1000")
    poller = cgroup.PeakPoller(reader)
    assert poller.stop() == 0


def test_peak_poller_surfaces_transient_read_failure(capsys):
    # A transient docker exec failure mid-poll must not be silently
    # swallowed: the loop stops, the last-seen max is kept as a floor, and
    # `degraded` plus a warning surface the failure (round-2 LOW fix).
    call_count = {"n": 0}

    def exec_fn(container, *cmd):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return "1000"
        raise cgroup.CgroupAccessError("docker exec: container not responding")

    reader = cgroup.DockerCgroupReader("c1", exec_fn=exec_fn)
    poller = cgroup.PeakPoller(reader, interval_seconds=0.01)
    poller.start()
    time.sleep(0.1)
    peak = poller.stop()

    assert peak == 1000
    assert poller.degraded is True
    assert "container not responding" in str(poller._poll_error)
    assert "WARNING" in capsys.readouterr().out


def test_peak_poller_not_degraded_on_clean_run():
    reader = cgroup.DockerCgroupReader("c1", exec_fn=lambda *a: "1000")
    poller = cgroup.PeakPoller(reader, interval_seconds=0.01)
    poller.start()
    time.sleep(0.05)
    poller.stop()

    assert poller.degraded is False


def test_dmesg_baseline_returns_latest_timestamp(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "[10.0] boot\n[55.5] some other line\n[30.0] middle\n"
        stderr = ""

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    assert cgroup.dmesg_baseline() == 55.5


def test_dmesg_baseline_returns_zero_when_no_timestamps(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "no timestamps here\n"
        stderr = ""

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    assert cgroup.dmesg_baseline() == 0.0


def test_dmesg_baseline_raises_on_permission_denied(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "dmesg: read kernel buffer failed: Operation not permitted"

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    with pytest.raises(cgroup.CgroupAccessError):
        cgroup.dmesg_baseline()


def test_scan_dmesg_oom_excludes_lines_at_or_before_baseline(monkeypatch):
    class _Result:
        returncode = 0
        stdout = (
            "[100.0] Out of memory: Killed process 1 (python) stale kill\n"
            "[200.0] Out of memory: Killed process 2 (python) fresh kill\n"
        )
        stderr = ""

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    lines = cgroup.scan_dmesg_oom(process_pattern="python", since_timestamp=100.0)

    assert len(lines) == 1
    assert "fresh kill" in lines[0]


def test_scan_dmesg_oom_keeps_lines_with_unparseable_timestamp(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "Out of memory: Killed process 1 (python) no bracket timestamp\n"
        stderr = ""

    monkeypatch.setattr(cgroup.subprocess, "run", lambda *a, **k: _Result())
    lines = cgroup.scan_dmesg_oom(process_pattern="python", since_timestamp=500.0)

    assert len(lines) == 1
