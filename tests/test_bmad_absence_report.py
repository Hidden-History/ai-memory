"""The BMAD absence report's data: the pin, the gate, and the stdout contract.

`scripts/bmad_absence_report.py` is what the installer runs when BMAD, or the
Module it needs, is not available to the target project. It prints one
tab-separated record per line. These tests assert on those records — the
machine-readable contract — never on the operator wording the installer builds
from them.

Every identifier below is synthetic except the two the detector itself checks,
the product root and its one Module, which are the namespace under test.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPT = _REPO / "scripts" / "bmad_absence_report.py"
_POV = "_ai-memory/pov"

ROOT_CAPABILITY = "cap:sample-needs-root"
MODULE_CAPABILITY = "cap:sample-needs-module"
UNCOVERED_CAPABILITY = "cap:sample-needs-uncovered-module"
SAMPLE_SOURCE = "https://example.invalid/sample-upstream"
SAMPLE_SCOPE = "sample-scope-one"

FIRING_STATES = ("bmad-absent", "bmm-absent", "bmad-indeterminate")


@pytest.fixture(scope="module")
def report():
    spec = importlib.util.spec_from_file_location("bmad_absence_report", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def _declaration(capability: str, depends_on: str) -> str:
    return (
        "<!-- ai-memory:degraded-declaration\n"
        f"capability: {capability}\n"
        f"depends_on: {depends_on}\n"
        "degraded_behaviour: reports itself unavailable\n"
        "degraded_test: not-yet-enforced\n"
        "ai-memory:end-degraded-declaration -->\n"
    )


def _skill(root: Path, name: str, body: str) -> None:
    site = root / _POV / "skills" / name / "SKILL.md"
    site.parent.mkdir(parents=True)
    site.write_text(body, encoding="utf-8")


def _pin(version_scope: str = SAMPLE_SCOPE, covers: str = "bmad.bmm") -> str:
    return (
        "<!-- ai-memory:pin-declaration\n"
        "dependency: bmad\n"
        f"version_scope: {version_scope}\n"
        f"covers: {covers}\n"
        "ai-memory:end-pin-declaration -->\n"
    )


@pytest.fixture
def product(tmp_path) -> Path:
    """A synthetic product tree: three capabilities, one remedy, one pin."""
    root = tmp_path / "product"
    _skill(root, "sample-one", _declaration(ROOT_CAPABILITY, "bmad"))
    _skill(root, "sample-two", _declaration(MODULE_CAPABILITY, "bmad.bmm"))
    _skill(
        root,
        "sample-three",
        _declaration(UNCOVERED_CAPABILITY, "bmad.sample-uncovered"),
    )
    (root / _POV / "DEPENDENCIES.md").write_text(
        "<!-- ai-memory:dependency-declaration\n"
        "dependency: bmad\n"
        f"upstream_source: {SAMPLE_SOURCE}\n"
        "ai-memory:end-dependency-declaration -->\n",
        encoding="utf-8",
    )
    (root / _POV / "BMAD-PIN.md").write_text(_pin(), encoding="utf-8")
    return root


def _capabilities(records) -> dict:
    return {r[1]: r[2] for r in records if r[0] == "capability"}


def _of(records, kind: str) -> list:
    return [r for r in records if r[0] == kind]


class TestPinReader:
    """Four returns, four tests: present, missing, empty, could not be read."""

    def test_present_returns_the_scope_and_the_modules_it_covers(self, report, product):
        pin = report.read_pin(product)
        assert pin.state == "present"
        assert pin.version_scope == SAMPLE_SCOPE
        assert pin.covers == ("bmad.bmm",)

    def test_missing_is_a_declared_state_with_no_scope(self, report, product):
        (product / _POV / "BMAD-PIN.md").unlink()
        pin = report.read_pin(product)
        assert pin.state == "missing"
        assert pin.version_scope is None
        assert pin.subject.endswith("BMAD-PIN.md")

    @pytest.mark.parametrize(
        "body", ["no declaration block in this file\n", _pin(version_scope="")]
    )
    def test_present_but_empty_is_not_missing(self, report, product, body):
        (product / _POV / "BMAD-PIN.md").write_text(body, encoding="utf-8")
        pin = report.read_pin(product)
        assert pin.state == "empty"
        assert pin.version_scope is None

    def test_could_not_be_read_is_not_missing_and_names_its_subject(
        self, report, product
    ):
        # A directory at the declaration's path: it exists, and reading it
        # fails. No permission bit is involved, so this holds as any user.
        site = product / _POV / "BMAD-PIN.md"
        site.unlink()
        site.mkdir()
        pin = report.read_pin(product)
        assert pin.state == "unreadable"
        assert pin.version_scope is None
        assert pin.subject.endswith("BMAD-PIN.md")

    def test_a_truncated_declaration_is_unreadable_not_a_short_valid_one(
        self, report, product
    ):
        (product / _POV / "BMAD-PIN.md").write_text(
            "<!-- ai-memory:pin-declaration\ndependency: bmad\n", encoding="utf-8"
        )
        assert report.read_pin(product).state == "unreadable"

    def test_the_four_states_are_distinct_tokens(self, report):
        assert len(set(report.PIN_STATES)) == 4


class TestGate:
    """A capability is listed only when its declared member is not satisfied."""

    def test_no_bmad_lists_every_capability(self, report, product):
        listed = _capabilities(report.build_report("bmad-absent", product))
        assert listed == {
            ROOT_CAPABILITY: "unsatisfied",
            MODULE_CAPABILITY: "unsatisfied",
            UNCOVERED_CAPABILITY: "unsatisfied",
        }

    def test_module_absent_lists_the_module_capability_and_not_the_root_one(
        self, report, product
    ):
        listed = _capabilities(report.build_report("bmm-absent", product))
        assert listed[MODULE_CAPABILITY] == "unsatisfied"
        assert ROOT_CAPABILITY not in listed

    def test_indeterminate_is_its_own_cause_never_folded_into_absent(
        self, report, product
    ):
        listed = _capabilities(report.build_report("bmad-indeterminate", product))
        assert listed[ROOT_CAPABILITY] == "indeterminate"
        assert listed[MODULE_CAPABILITY] == "indeterminate"

    def test_present_module_satisfies_both_levels(self, report):
        assert report.member_verdict("bmm-present", "bmad") == "satisfied"
        assert report.member_verdict("bmm-present", "bmad.bmm") == "satisfied"

    def test_a_module_the_detector_did_not_examine_is_never_called_present(
        self, report
    ):
        assert (
            report.member_verdict("bmm-absent", "bmad.sample-uncovered")
            == "indeterminate"
        )

    def test_one_record_per_capability_in_a_stable_order(self, report, product):
        first = report.build_report("bmad-absent", product)
        second = report.build_report("bmad-absent", product)
        assert first == second
        names = [r[1] for r in _of(first, "capability")]
        assert len(names) == len(set(names)) == 3

    def test_the_set_is_derived_from_the_declarations_at_run_time(
        self, report, product
    ):
        added = "cap:sample-added-later"
        _skill(product, "sample-four", _declaration(added, "bmad"))
        assert added in _capabilities(report.build_report("bmad-absent", product))


class TestEmptyResults:
    """Listed, declared-empty, did-not-run and failed are four different records."""

    def test_listed(self, report, product):
        assert _of(report.build_report("bmad-absent", product), "enumeration") == [
            ("enumeration", "listed")
        ]

    def test_nothing_dark_is_a_declared_empty_result(self, report, tmp_path):
        root = tmp_path / "product"
        _skill(root, "sample-one", _declaration(ROOT_CAPABILITY, "bmad"))
        records = report.build_report("bmm-absent", root)
        assert _of(records, "capability") == []
        assert _of(records, "enumeration") == [("enumeration", "empty")]

    def test_discovery_that_did_not_run_is_not_an_empty_result(self, report, tmp_path):
        records = report.build_report("bmad-absent", tmp_path / "no-product-here")
        assert _of(records, "enumeration")[0][:2] == ("enumeration", "did-not-run")

    def test_discovery_that_raised_is_not_an_empty_result(self, report, product):
        _skill(product, "sample-broken", "<!-- ai-memory:degraded-declaration\n")
        records = report.build_report("bmad-absent", product)
        assert _of(records, "enumeration")[0][:2] == ("enumeration", "failed")
        assert _of(records, "capability") == []
        # The pin does not depend on discovery, so it is still reported.
        assert _of(records, "pin")[0][1] == "present"


class TestRouteOut:
    def test_upstream_source_comes_from_the_dependency_declaration(
        self, report, product
    ):
        records = report.build_report("bmad-absent", product)
        assert ("upstream-source", "bmad", SAMPLE_SOURCE) in records

    def test_a_module_member_is_served_by_the_root_entry(self, report, product):
        records = report.build_report("bmm-absent", product)
        assert ("upstream-source", "bmad", SAMPLE_SOURCE) in records

    def test_route_out_is_given_even_when_nothing_is_listed(self, report, tmp_path):
        root = tmp_path / "product"
        _skill(root, "sample-one", _declaration(ROOT_CAPABILITY, "bmad"))
        (root / _POV / "DEPENDENCIES.md").write_text(
            "<!-- ai-memory:dependency-declaration\n"
            "dependency: bmad\n"
            f"upstream_source: {SAMPLE_SOURCE}\n"
            "ai-memory:end-dependency-declaration -->\n",
            encoding="utf-8",
        )
        records = report.build_report("bmm-absent", root)
        assert ("upstream-source", "bmad", SAMPLE_SOURCE) in records

    def test_a_dependency_with_no_declared_source_is_reported_not_defaulted(
        self, report, product
    ):
        (product / _POV / "DEPENDENCIES.md").unlink()
        records = report.build_report("bmad-absent", product)
        assert _of(records, "upstream-source") == []
        assert ("upstream-source-missing", "bmad") in records

    def test_version_scope_is_the_pin_files_value(self, report, product):
        other = "sample-scope-two"
        (product / _POV / "BMAD-PIN.md").write_text(_pin(other), encoding="utf-8")
        records = report.build_report("bmad-absent", product)
        assert ("pin", "present", other, "bmad.bmm") in records

    def test_missing_pin_is_reported_and_the_rest_is_still_rendered(
        self, report, product
    ):
        (product / _POV / "BMAD-PIN.md").unlink()
        records = report.build_report("bmad-absent", product)
        pin = _of(records, "pin")
        assert len(pin) == 1 and pin[0][1] == "missing"
        assert len(_of(records, "capability")) == 3
        assert ("upstream-source", "bmad", SAMPLE_SOURCE) in records

    def test_a_module_outside_the_pins_coverage_is_named_as_outside_it(
        self, report, product
    ):
        records = report.build_report("bmad-absent", product)
        assert _of(records, "outside-pin") == [("outside-pin", "bmad.sample-uncovered")]

    def test_a_covered_module_is_not_reported_as_outside(self, report, product):
        records = report.build_report("bmm-absent", product)
        assert ("outside-pin", "bmad.bmm") not in records

    def test_nothing_is_called_outside_coverage_when_there_is_no_pin(
        self, report, product
    ):
        (product / _POV / "BMAD-PIN.md").unlink()
        assert _of(report.build_report("bmad-absent", product), "outside-pin") == []


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args], capture_output=True, text=True
    )


class TestStdoutContract:
    @pytest.mark.parametrize("state", FIRING_STATES)
    def test_every_firing_state_ends_with_the_completion_record(self, product, state):
        result = _run("--state", state, "--product-root", str(product))
        assert result.returncode == 0
        lines = result.stdout.splitlines()
        assert lines[-1] == "report-complete"
        assert all("\t" in line for line in lines[:-1])

    def test_one_line_per_capability_not_a_joined_one(self, product):
        result = _run("--state", "bmad-absent", "--product-root", str(product))
        capability_lines = [
            line for line in result.stdout.splitlines() if line.startswith("capability")
        ]
        assert len(capability_lines) == 3
        assert all(line.count("cap:") == 1 for line in capability_lines)

    def test_two_runs_differ_by_exactly_the_capability_that_changed(self, product):
        before = _run("--state", "bmad-absent", "--product-root", str(product))
        _skill(product, "sample-four", _declaration("cap:sample-added-later", "bmad"))
        after = _run("--state", "bmad-absent", "--product-root", str(product))
        changed = set(after.stdout.splitlines()) ^ set(before.stdout.splitlines())
        assert changed == {"capability\tcap:sample-added-later\tunsatisfied"}

    @pytest.mark.parametrize("state", ["bmm-present", "sample-unrecognised", ""])
    def test_a_state_that_is_not_an_absence_produces_no_report(self, product, state):
        result = _run("--state", state, "--product-root", str(product))
        assert result.returncode != 0
        assert result.stdout == ""

    def test_nothing_is_written_into_the_product_tree(self, product):
        before = sorted(p for p in product.rglob("*"))
        _run("--state", "bmad-absent", "--product-root", str(product))
        assert sorted(p for p in product.rglob("*")) == before


class TestShippedDeclarations:
    """The shipped pin and the shipped declarations, read by the real reader."""

    def test_the_shipped_pin_is_present_and_names_the_modules_it_covers(self, report):
        pin = report.read_pin(_REPO)
        assert pin.state == "present"
        assert pin.version_scope
        assert pin.covers
        assert all(member.startswith("bmad.") for member in pin.covers)

    def test_the_shipped_pin_covers_the_module_the_detector_checks(self, report):
        assert "bmad.bmm" in report.read_pin(_REPO).covers

    def test_every_shipped_capability_is_listed_when_bmad_is_absent(self, report):
        records = report.build_report("bmad-absent", _REPO)
        assert _of(records, "enumeration") == [("enumeration", "listed")]
        assert all(name.startswith("cap:") for name in _capabilities(records))
        assert _of(records, "upstream-source")
        assert _of(records, "upstream-source-missing") == []

    def test_no_version_scope_is_written_outside_the_pin_declaration(self, report):
        scope = report.read_pin(_REPO).version_scope
        for path in (_SCRIPT, _REPO / _POV / "DEPENDENCIES.md"):
            assert scope not in path.read_text(encoding="utf-8")


def test_no_version_shaped_string_in_the_report_script():
    """The version scope is read from the pin, never restated in the code."""
    found = re.findall(r"\d+\.\d+", _SCRIPT.read_text(encoding="utf-8"))
    assert found == []
