"""Tests for the executed-test floor (GR-01, BUG-535, BUG-536).

The fail-closed cases carry most of the weight here. A floor is only worth
having if it fails on the runs where something already went wrong -- a missing
report, an empty one, a truncated one. Those are exactly the paths a safety
predicate tends to get wrong, because the happy path is the one people test.
"""

import pytest

from tests.ci_executed_floor import FloorError, check_floor, executed_tests, main


def _write(tmp_path, body, name="pytest-report.xml"):
    path = tmp_path / name
    path.write_text(body)
    return str(path)


class TestExecutedTests:
    """executed = tests - skipped, and anything unreadable raises."""

    def test_skipped_tests_do_not_count_as_executed(self, tmp_path):
        """The defect this module was built to remove, stated as a test."""
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="100" skipped="40"/></testsuites>'
        )
        assert executed_tests(junit) == (60, 100, 40)

    def test_a_fully_skipped_run_executes_nothing(self, tmp_path):
        """BUG-536: 4 collected, 4 skipped, exit 0, job green."""
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="4" skipped="4"/></testsuites>'
        )
        assert executed_tests(junit) == (0, 4, 4)

    def test_errored_tests_count_as_executed(self, tmp_path):
        """An errored test ran far enough to fail, so it carries signal."""
        junit = _write(
            tmp_path,
            '<testsuites><testsuite tests="10" skipped="0" errors="3" '
            'failures="2"/></testsuites>',
        )
        assert executed_tests(junit) == (10, 10, 0)

    def test_multiple_suites_are_summed(self, tmp_path):
        junit = _write(
            tmp_path,
            '<testsuites><testsuite tests="10" skipped="2"/>'
            '<testsuite tests="5" skipped="1"/></testsuites>',
        )
        assert executed_tests(junit) == (12, 15, 3)

    def test_a_bare_testsuite_root_is_read(self, tmp_path):
        """pytest emits a bare <testsuite> root in some configurations."""
        junit = _write(tmp_path, '<testsuite tests="8" skipped="3"/>')
        assert executed_tests(junit) == (5, 8, 3)

    def test_absent_skipped_attribute_defaults_to_zero(self, tmp_path):
        junit = _write(tmp_path, '<testsuites><testsuite tests="7"/></testsuites>')
        assert executed_tests(junit) == (7, 7, 0)


class TestFailsClosed:
    """Every unreadable outcome raises rather than returning a passing zero."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(FloorError, match="could not read"):
            executed_tests(str(tmp_path / "never-written.xml"))

    def test_no_path_at_all(self):
        with pytest.raises(FloorError, match="not a floor"):
            executed_tests("")

    def test_empty_file(self, tmp_path):
        with pytest.raises(FloorError, match="is empty"):
            executed_tests(_write(tmp_path, ""))

    def test_whitespace_only_file(self, tmp_path):
        """Distinct from empty on disk, identical in meaning: nothing was written."""
        with pytest.raises(FloorError, match="is empty"):
            executed_tests(_write(tmp_path, "   \n\t  \n"))

    def test_malformed_xml(self, tmp_path):
        with pytest.raises(FloorError, match="not valid XML"):
            executed_tests(_write(tmp_path, "<testsuites><testsuite tests="))

    def test_well_formed_xml_with_no_testsuite(self, tmp_path):
        with pytest.raises(FloorError, match="no <testsuite>"):
            executed_tests(_write(tmp_path, "<something-else/>"))

    def test_non_integer_attribute(self, tmp_path):
        """Treating an unparseable count as zero would pass an unreadable report."""
        with pytest.raises(FloorError, match="non-integer"):
            executed_tests(
                _write(tmp_path, '<testsuites><testsuite tests="lots"/></testsuites>')
            )

    def test_more_skipped_than_total_is_incoherent(self, tmp_path):
        with pytest.raises(FloorError, match="impossible"):
            executed_tests(
                _write(
                    tmp_path,
                    '<testsuites><testsuite tests="3" skipped="9"/></testsuites>',
                )
            )


class TestCheckFloor:
    """The gate decision itself."""

    def test_a_run_clearing_the_floor_passes(self, tmp_path):
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="500" skipped="10"/></testsuites>'
        )
        assert check_floor(junit, 400) is None

    def test_a_run_exactly_on_the_floor_passes(self, tmp_path):
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="400" skipped="0"/></testsuites>'
        )
        assert check_floor(junit, 400) is None

    def test_zero_executed_is_rejected(self, tmp_path):
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="4" skipped="4"/></testsuites>'
        )
        problem = check_floor(junit, 1, "the nightly regression suite")
        assert problem is not None
        assert "executed 0 tests" in problem
        assert "the nightly regression suite" in problem

    def test_an_under_run_is_rejected(self, tmp_path):
        """BUG-535: collected in full, a third skipped away, exit 0."""
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="498" skipped="159"/></testsuites>'
        )
        problem = check_floor(junit, 450)
        assert problem is not None
        assert "below the floor" in problem
        assert "339" in problem

    def test_a_collected_count_that_would_have_passed_the_old_gate_fails(
        self, tmp_path
    ):
        """The regression guard for the migration itself.

        6,000 collected against a floor of 5,000 passed the old collected-basis
        gate. Every one of them skipped. It must fail now.
        """
        junit = _write(
            tmp_path,
            '<testsuites><testsuite tests="6000" skipped="6000"/></testsuites>',
        )
        assert check_floor(junit, 5000) is not None

    @pytest.mark.parametrize("floor", [0, -1])
    def test_a_floor_below_one_is_refused(self, tmp_path, floor):
        """A floor of zero is satisfied by a run that did nothing."""
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="10" skipped="0"/></testsuites>'
        )
        problem = check_floor(junit, floor)
        assert problem is not None
        assert "floor below 1" in problem

    def test_a_missing_report_is_rejected(self, tmp_path):
        problem = check_floor(str(tmp_path / "absent.xml"), 1)
        assert problem is not None
        assert "could not read" in problem


class TestCli:
    """The entry point CI actually calls."""

    def test_exit_zero_when_the_floor_is_cleared(self, tmp_path, capsys):
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="50" skipped="5"/></testsuites>'
        )
        assert main(["--junit", junit, "--min-executed", "40"]) == 0
        assert "45 executed" in capsys.readouterr().out

    def test_exit_one_when_the_suite_under_ran(self, tmp_path, capsys):
        junit = _write(
            tmp_path, '<testsuites><testsuite tests="50" skipped="50"/></testsuites>'
        )
        assert main(["--junit", junit, "--min-executed", "40"]) == 1
        assert "::error::" in capsys.readouterr().out

    def test_exit_one_when_the_report_is_missing(self, tmp_path):
        assert main(["--junit", str(tmp_path / "gone.xml"), "--min-executed", "1"]) == 1
