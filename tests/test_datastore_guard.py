"""Regression gate for the production-datastore guard (TD-881, TD-876).

Every test here names a specific defect that was live in this repository and
fails if that defect returns. They are deliberately written against the
mechanism rather than the symptom: three separate live-write paths were closed,
and each had already survived one round of "fixed" because the fix was checked
by reasoning instead of by a test.

These assert *configuration* safety only. The load-bearing protection is the
network namespace the suite runs inside, whose oracle is the tripwire
accept-counter in .github/workflows/datastore-isolation.yml. Nothing in this
file can prove a connection was not made -- do not let it grow into something
that claims to.
"""

import ast
import inspect
import json
import os
import pathlib
import socket
import time
from typing import ClassVar

import pytest

from memory.config import MemoryConfig
from tests import conftest as root_conftest
from tests.datastore_guard import (
    CONFIG_FALLBACK_PORT,
    LIVE_OPT_IN_ENV,
    PRODUCTION_PORTS,
    SENTINEL_PORT,
    SENTINEL_URL,
    assert_not_production,
    install_safe_defaults,
    port_from_url,
    resolved_ports,
)
from tests.datastore_tripwire import Tripwire, check_run_happened

TESTS_DIR = pathlib.Path(__file__).parent
LIVE_QDRANT_PORT = 26350


class TestProductionPortSet:
    """The guard has to know which ports are production."""

    def test_config_defaults_are_all_protected(self):
        """A port default in config.py that the guard does not know is a hole.

        Catches the drift this set is exposed to: the values are written out in
        datastore_guard rather than derived at runtime, so this test is what
        keeps them honest.
        """
        fields = MemoryConfig.model_fields
        assert fields["qdrant_port"].default in PRODUCTION_PORTS
        assert fields["embedding_port"].default in PRODUCTION_PORTS
        langfuse_port = port_from_url(fields["langfuse_base_url"].default)
        assert langfuse_port in PRODUCTION_PORTS

    def test_grpc_port_is_protected(self):
        """26351 is the live gRPC port and is not represented in config.py.

        It comes from docker/.env (QDRANT_GRPC_PORT). A guard derived purely
        from config defaults would omit it -- which is exactly how an earlier
        design ended up protecting the wrong set while appearing to work.
        """
        assert 26351 in PRODUCTION_PORTS
        assert 6334 in PRODUCTION_PORTS  # qdrant-client's own gRPC default


class TestSentinel:
    """The sentinel has to be usable, and has to stay not-a-real-service."""

    def test_sentinel_satisfies_config_constraints(self):
        """A sentinel outside ge=1024/le=65535 breaks collection, not the run.

        Regression: an earlier sentinel of port 1 made MemoryConfig raise a
        pydantic ValidationError during collection, which fails the suite for a
        reason unrelated to the thing being guarded.
        """
        field = MemoryConfig.model_fields["qdrant_port"]
        bounds = {type(m).__name__: m for m in field.metadata}
        assert bounds["Ge"].ge <= SENTINEL_PORT <= bounds["Le"].le

    def test_sentinel_is_outside_the_ephemeral_range(self):
        """The kernel must never auto-assign the sentinel to a live process."""
        try:
            low, high = (
                pathlib.Path("/proc/sys/net/ipv4/ip_local_port_range")
                .read_text()
                .split()
            )
        except OSError:
            pytest.skip("ip_local_port_range unavailable on this platform")
        assert not int(low) <= SENTINEL_PORT <= int(high)

    def test_sentinel_is_not_a_production_port(self):
        assert SENTINEL_PORT not in PRODUCTION_PORTS


class TestRefusal:
    """assert_not_production must refuse, and must not be bypassable by luck."""

    @pytest.mark.parametrize("port", sorted(PRODUCTION_PORTS))
    def test_every_production_port_is_refused(self, port):
        with pytest.raises(pytest.UsageError, match="Refusing to run"):
            assert_not_production({"QDRANT_PORT": str(port)})

    def test_production_url_is_refused(self):
        """The port can arrive inside a URL rather than as a bare port var."""
        with pytest.raises(pytest.UsageError, match="Refusing to run"):
            assert_not_production({"QDRANT_URL": "http://localhost:26350"})

    def test_auxiliary_production_vars_do_not_block_the_run(self):
        """The refusal is scoped to the Qdrant target, on purpose.

        src/memory/classifier/config.py loads the operator's real
        ~/.ai-memory/docker/.env into os.environ during collection, and does not
        honour AI_MEMORY_INSTALL_DIR, so EMBEDDING_PORT / QDRANT_GRPC_PORT /
        LANGFUSE_BASE_URL sit at their production values in every run. Refusing
        on those produced 5889 setup errors and no actionable signal. They are
        still counted by the tripwire, which is where that exposure is tracked.

        The Qdrant target here is an ephemeral port so that this asserts what it
        says it does. Without one the environment names no target at all, which
        is its own refusal -- see TestEmptyEnvironmentIsNotSafety.
        """
        assert_not_production(
            {
                "QDRANT_PORT": "46731",
                "LANGFUSE_BASE_URL": "http://localhost:23100",
                "EMBEDDING_PORT": "28080",
                "QDRANT_GRPC_PORT": "26351",
            }
        )

    def test_sentinel_target_is_permitted(self):
        assert_not_production({"QDRANT_URL": SENTINEL_URL})

    def test_ephemeral_target_is_permitted(self):
        """A throwaway instance on an arbitrary port must not be refused."""
        assert_not_production({"QDRANT_PORT": "46731"})

    def test_opt_in_permits_a_deliberate_live_run(self):
        assert_not_production(
            {"QDRANT_PORT": str(LIVE_QDRANT_PORT), LIVE_OPT_IN_ENV: "1"}
        )

    def test_opt_in_is_not_triggered_by_an_arbitrary_value(self):
        """`AI_MEMORY_ALLOW_LIVE_DATASTORE=0` must not count as opting in."""
        with pytest.raises(pytest.UsageError):
            assert_not_production(
                {"QDRANT_PORT": str(LIVE_QDRANT_PORT), LIVE_OPT_IN_ENV: "0"}
            )


class TestSafeDefaults:
    """install_safe_defaults is the replacement for the autouse override."""

    def test_untargeted_run_gets_the_sentinel(self):
        env = {}
        install_safe_defaults(env)
        assert env["QDRANT_URL"] == SENTINEL_URL
        assert env["QDRANT_PORT"] == str(SENTINEL_PORT)
        assert LIVE_QDRANT_PORT not in resolved_ports(env)

    def test_an_explicit_caller_target_is_never_overwritten(self):
        """The defect that made every earlier mitigation useless.

        A session-scoped autouse fixture rewrote QDRANT_URL/QDRANT_PORT to the
        live instance from inside the pytest process, after any pre-launch check
        had passed. Honouring the caller is the whole fix.
        """
        env = {"QDRANT_URL": "http://localhost:46731", "QDRANT_PORT": "46731"}
        install_safe_defaults(env)
        assert env["QDRANT_URL"] == "http://localhost:46731"
        assert env["QDRANT_PORT"] == "46731"


class TestMechanismsStayClosed:
    """Static checks on the three live-write paths TD-881 enumerated."""

    def test_qdrant_base_url_does_not_default_to_production(self):
        """Mechanism 1: the fixture's own default was the live port."""
        source = inspect.getsource(root_conftest.qdrant_base_url)
        assert str(LIVE_QDRANT_PORT) not in source

    def test_integration_test_env_assigns_no_target_directly(self):
        """Mechanism 2: the autouse fixture hard-set QDRANT_URL/QDRANT_PORT.

        It must delegate to the shared helper, never assign a target itself --
        a direct assignment here is what no caller could defend against.
        """
        source = inspect.getsource(root_conftest.integration_test_env)
        assert 'os.environ["QDRANT_URL"] =' not in source
        assert 'os.environ["QDRANT_PORT"] =' not in source
        assert "install_safe_defaults()" in source

    def test_no_test_hardcodes_a_production_port_in_a_subprocess_env(self):
        """Mechanism 3: a literal production target in a subprocess `env=`.

        Parsed rather than string-matched. The substring version of this check
        required QDRANT_URL to be the *first* key of a double-quoted dict
        literal written on one physical line, and matched only port 26350 --
        so a non-first key, a multi-line dict, single quotes, or any other
        production port slipped past while the docstring claimed "a new
        occurrence anywhere under tests/ fails this".

        Walking the AST instead: every dict literal passed as `env=` to any
        call, every string value in it, matched against the whole production
        port set.
        """
        offenders = []
        for path in sorted(TESTS_DIR.rglob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "env" or not isinstance(keyword.value, ast.Dict):
                        continue
                    for value in keyword.value.values:
                        if not isinstance(value, ast.Constant) or not isinstance(
                            value.value, str
                        ):
                            continue
                        port = port_from_url(value.value) or (
                            int(value.value) if value.value.isdigit() else None
                        )
                        if port in PRODUCTION_PORTS:
                            offenders.append(
                                f"{path.relative_to(TESTS_DIR)}:{value.lineno} -> {port}"
                            )
        assert not offenders, (
            "subprocess env= must derive its Qdrant target, not hardcode the "
            f"operator's live install: {offenders}"
        )


class TestSharedGuard:
    """TD-876: one implementation, applied at both conftest levels."""

    @pytest.mark.parametrize(
        "conftest_path", ["conftest.py", "integration/conftest.py"]
    )
    def test_conftest_uses_the_shared_guard(self, conftest_path):
        source = (TESTS_DIR / conftest_path).read_text(encoding="utf-8")
        assert "datastore_guard" in source
        assert "assert_not_production()" in source
        assert "install_safe_defaults()" in source

    def test_neither_conftest_defaults_to_the_live_port(self):
        for conftest_path in ("conftest.py", "integration/conftest.py"):
            source = (TESTS_DIR / conftest_path).read_text(encoding="utf-8")
            for lineno, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or "=" not in stripped:
                    continue
                assert (
                    f"localhost:{LIVE_QDRANT_PORT}" not in stripped
                ), f"{conftest_path}:{lineno} assigns the live datastore"


class TestUngatedTestsStayGated:
    """The 16 root-level tests that ran against live data on a plain pytest."""

    # Fixtures that hand a test a real connection to a live service.
    LIVE_FIXTURES: ClassVar[frozenset] = frozenset(
        {"qdrant_client", "qdrant_base_url", "async_qdrant_client"}
    )
    # Only markers that deselect a test *unconditionally*, on the plain
    # `pytest tests/` this class is about.
    #
    #   integration / e2e  -- deselected by the skip gate in conftest, which
    #                         keys on the keyword or the path segment
    #   regression         -- excluded by addopts: -m 'not regression'
    #   skip               -- never runs, by construction
    #
    # `requires_qdrant`, `requires_embedding` and `requires_docker_stack` were
    # counted here and are not gates at all. conftest's skip_if_service_available
    # path skips them only when the service is *unavailable*, so on the operator
    # machine TD-881 is about -- where Qdrant is up -- they permit the test to
    # run rather than hold it back. A root test taking `qdrant_client` and
    # marked only `@pytest.mark.requires_qdrant` satisfied this oracle while
    # doing precisely what TD-881 forbids.
    #
    # `quarantine` was counted too and has no skip hook anywhere. The
    # CI-scope command passes -m 'not quarantine' explicitly, but addopts does
    # not, and a bare `pytest tests/` is the case being checked here.
    GATING_MARKERS: ClassVar[frozenset] = frozenset(
        {"integration", "e2e", "regression", "skip"}
    )

    @classmethod
    def _marker_name(cls, node):
        node = node.func if isinstance(node, ast.Call) else node
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        parts.reverse()
        if len(parts) >= 3 and parts[:2] == ["pytest", "mark"]:
            return parts[2]
        return None

    @classmethod
    def _module_markers(cls, tree):
        markers = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
            ):
                values = (
                    node.value.elts
                    if isinstance(node.value, (ast.List, ast.Tuple))
                    else [node.value]
                )
                markers.update(filter(None, (cls._marker_name(v) for v in values)))
        return markers

    @classmethod
    def _collect_ungated(cls, node, markers, path, ungated):
        """Walk a module or class body, recording un-gated live-fixture tests."""
        for child in node.body:
            own = markers | {
                m
                for m in map(cls._marker_name, getattr(child, "decorator_list", []))
                if m
            }
            if isinstance(child, ast.ClassDef):
                cls._collect_ungated(child, own, path, ungated)
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                if not child.name.startswith("test_"):
                    continue
                takes_live = {a.arg for a in child.args.args} & cls.LIVE_FIXTURES
                if takes_live and not (own & cls.GATING_MARKERS):
                    ungated.append(f"{path.name}::{child.name}")

    def test_no_root_level_test_takes_a_live_fixture_ungated(self):
        """Root-level unmarked tests match neither branch of the skip gate.

        That gate keys only on the integration/e2e keyword or an /integration/
        or /e2e/ path segment, so a test sitting directly under tests/ with no
        marker is never deselected -- not by the gate, and not by
        `-m "not quarantine"` either, because it carries no markers at all.
        """
        ungated = []
        for path in sorted(TESTS_DIR.glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            self._collect_ungated(tree, self._module_markers(tree), path, ungated)

        assert not ungated, (
            "root-level tests take a live-service fixture with no gating "
            f"marker, so a plain `pytest tests/` runs them: {ungated}"
        )


class TestEmptyEnvironmentIsNotSafety:
    """Clearing the target does not point the suite nowhere -- it points it home.

    BP-197's rule is that a guard reading configuration can be defeated by
    anything that writes configuration. This is the removal-side twin: MemoryConfig
    has no QDRANT_URL field and its qdrant_port default is the operator's live
    REST port, so an empty environment resolves to production rather than to
    nothing. A guard that reported "no target" for an empty environment would
    wave through exactly the case it exists to catch.
    """

    def test_fallback_matches_the_config_field_default(self):
        """Pinned, so a change in config.py fails here instead of drifting."""
        assert MemoryConfig.model_fields["qdrant_port"].default == CONFIG_FALLBACK_PORT

    def test_empty_environment_resolves_to_the_live_port(self):
        assert CONFIG_FALLBACK_PORT in resolved_ports({})

    def test_empty_environment_is_refused(self):
        with pytest.raises(pytest.UsageError, match="Refusing to run"):
            assert_not_production({})

    def test_config_really_does_resolve_there(self):
        """The claim above, checked against MemoryConfig rather than asserted."""
        assert MemoryConfig.model_fields["qdrant_port"].default == LIVE_QDRANT_PORT


class TestRunHealthGatesTheRatchet:
    """A count is only evidence if the run that produced it actually happened.

    Both holes here are fail-open: a run that dies or that executes a fraction of
    the suite connects to almost nothing, so its low count reads as the best
    result ever recorded. The ratchet has to establish there was a measurement
    before comparing it to anything.
    """

    @staticmethod
    def _report(exit_code):
        return {"total_gated": 0, "wrapped_exit_code": exit_code}

    @staticmethod
    def _junit(tmp_path, tests):
        path = tmp_path / "pytest-report.xml"
        path.write_text(f'<testsuites><testsuite tests="{tests}"/></testsuites>')
        return str(path)

    @pytest.mark.parametrize("exit_code", [2, 3, 4, 5, 127, None])
    def test_a_run_that_did_not_execute_is_rejected(self, exit_code, tmp_path):
        """Exit 2 is a collection error, 4 a usage error, 5 nothing selected.

        Observed for real: a malformed wrapper made pytest run without its flags
        and the leftovers exited 127. Had a report been written, it would have
        carried a near-zero count straight past the ceiling.
        """
        problem = check_run_happened(
            self._report(exit_code), {}, self._junit(tmp_path, 6000)
        )
        assert problem is not None
        assert "did not execute" in problem

    @pytest.mark.parametrize("exit_code", [0, 1])
    def test_a_run_that_executed_is_accepted(self, exit_code, tmp_path):
        """1 means tests failed, which is still a run that connected or did not."""
        assert (
            check_run_happened(
                self._report(exit_code),
                {"min_tests": 5000},
                self._junit(tmp_path, 6000),
            )
            is None
        )

    def test_a_partial_run_is_rejected(self, tmp_path):
        """Exit 0 with a fraction of the suite: honest count, meaningless one."""
        problem = check_run_happened(
            self._report(0), {"min_tests": 5000}, self._junit(tmp_path, 40)
        )
        assert problem is not None
        assert "below the floor" in problem

    def test_a_floor_with_no_junit_report_is_rejected(self):
        """A floor that cannot be evaluated must not silently pass."""
        problem = check_run_happened(self._report(0), {"min_tests": 5000}, None)
        assert problem is not None
        assert "not a floor" in problem

    def test_an_unreadable_junit_report_is_rejected(self, tmp_path):
        bad = tmp_path / "truncated.xml"
        bad.write_text("<testsuites><testsuite tests=")
        problem = check_run_happened(self._report(0), {"min_tests": 5000}, str(bad))
        assert problem is not None

    def test_the_shipped_baseline_sets_a_floor(self):
        """Without min_tests the partial-run hole is open in the real config."""
        baseline = json.loads(
            (TESTS_DIR / "datastore_isolation_baseline.json").read_text()
        )
        assert baseline.get("min_tests", 0) > 0


class TestTripwireClassification:
    """The oracle must fail toward "breach", never toward "harmless probe".

    CI caught the original version doing the opposite: it treated "no bytes
    within 0.4s" as a probe, so on a loaded runner a real payload connection was
    recorded as harmless. Because the ratchet gates on that number, the error
    direction was toward under-reporting -- a genuine regression could pass under
    the ceiling. These tests pin the corrected direction.
    """

    @staticmethod
    def _free_port():
        """A port nothing is using, so these never touch a production port."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _observe(self, client, classify_timeout=1.0):
        port = self._free_port()
        tripwire = Tripwire([port], classify_timeout=classify_timeout)
        tripwire.arm()
        try:
            client(port)
        finally:
            tripwire.disarm()
        return tripwire.report(), str(port)

    def test_payload_connection_counts_as_data_carrying(self):
        def client(port):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.sendall(b"GET / HTTP/1.1\r\n\r\n")

        report, key = self._observe(client)
        assert report["data_carrying"][key] == 1
        assert report["probes"][key] == 0
        assert report["total_gated"] == 1

    def test_bare_probe_is_not_gated(self):
        """connect-then-close carries nothing and must not read as a breach."""

        def client(port):
            socket.create_connection(("127.0.0.1", port), timeout=5).close()

        report, key = self._observe(client)
        assert report["probes"][key] == 1
        assert report["data_carrying"][key] == 0
        assert report["total_gated"] == 0

    def test_slow_payload_is_gated_not_written_off_as_a_probe(self):
        """The exact CI failure: a real client too slow for the budget.

        With a deliberately tiny budget the classifier cannot see the payload in
        time. It must record the connection as undecided and gate it -- the old
        behaviour scored this as a probe and lost a real connection from the
        count.
        """

        def client(port):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                time.sleep(0.5)
                sock.sendall(b"slow but entirely real")

        report, key = self._observe(client, classify_timeout=0.05)
        assert report["unclassified"][key] == 1
        assert report["probes"][key] == 0, "an undecided connection is not a probe"
        assert report["total_gated"] == 1, "an undecided connection must be gated"

    def test_gated_total_is_data_plus_unclassified(self):
        report, _ = self._observe(lambda port: None)
        assert report["total_gated"] == (
            report["total_data_carrying"] + report["total_unclassified"]
        )


def test_guard_is_active_in_this_very_session():
    """The suite running right now must not be pointed at production."""
    assert not resolved_ports(os.environ) & PRODUCTION_PORTS
