"""The executed-test floor: a job must fail when its suite ran too few tests.

GR-01. A green is a claim about what RAN, so absence of execution has to be an
error rather than a pass. Two confirmed defects, one disease:

  * BUG-535 -- the integration job skipped 159 of 498 selected tests and
    reported green. Thirty genuinely broken tests were hiding behind it.
  * BUG-536 -- the nightly regression job executed **zero** tests
    (``4 skipped ... in 2.06s``) and reported success, every night.

Neither is visible in an exit code: pytest exits 0 for a suite that skipped
everything exactly as it does for a suite that passed everything.

Why executed, and not collected
-------------------------------
``executed = tests - skipped``, and the distinction is the whole point of this
module rather than a detail of it.

JUnit's ``tests`` attribute counts every test case the run *reported*, and a
skipped test is reported. A floor built on that number is satisfied by a run in
which nothing at all executed -- which is precisely BUG-536's shape, and is how
the floor this module replaces came to be satisfiable without the property it
stood for. ``tests/datastore_tripwire.py`` gated on ``sum(tests)`` and would
have passed a run where all ~6,500 tests collected and every one skipped.

An errored test counts as executed on purpose. It ran far enough to fail, so it
carries signal; a skipped test carries none.

Why it fails closed
-------------------
Every unreadable outcome -- missing file, empty file, malformed XML, no
``testsuite`` element, a non-integer attribute -- raises rather than returning
zero or being treated as "no floor to check". A floor that cannot be evaluated
is not a floor, and the failure direction has to be toward *failing the job*:
the alternative is a gate that silently disables itself on exactly the runs
where something already went wrong enough to lose the report.

Usage::

    python3 tests/ci_executed_floor.py --junit report.xml --min-executed 400 \
        --label "integration tests"
"""

import argparse
import sys
from xml.etree import ElementTree


class FloorError(Exception):
    """The report could not be read, so no floor can be evaluated."""


def _int_attr(suite, name, junit_path):
    """Read an integer JUnit attribute, refusing to guess when it is not one."""
    raw = suite.get(name, "0")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise FloorError(
            f"the JUnit report at {junit_path} has a non-integer {name!r} "
            f"attribute ({raw!r}), so the number of tests that ran cannot be "
            "determined. Treating it as zero would turn an unreadable report "
            "into a passing floor."
        ) from exc


def _parse_suites(junit_path):
    """Return the report's testsuite elements, or raise FloorError."""
    if not junit_path:
        raise FloorError(
            "no JUnit report path was given, so the number of tests that ran "
            "is unknown. A floor that cannot be evaluated is not a floor."
        )

    try:
        with open(junit_path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise FloorError(
            f"could not read the JUnit report at {junit_path}: {exc}. The run "
            "was supposed to write one, so its absence means the run did not "
            "get as far as it claims."
        ) from exc

    # An empty or whitespace-only file is what a run that died mid-write leaves
    # behind. ElementTree reports it as a parse error, but it is worth its own
    # message because the cause is different and so is the fix.
    if not raw.strip():
        raise FloorError(
            f"the JUnit report at {junit_path} is empty. pytest writes this "
            "file at the end of a run, so an empty one means the run did not "
            "reach the end."
        )

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise FloorError(
            f"the JUnit report at {junit_path} is not valid XML: {exc}. A "
            "report that cannot be parsed cannot be graded."
        ) from exc

    # A bare <testsuite> root is its own only suite; iter() would also return
    # self, so the two cases are separated rather than merged.
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    if not suites:
        raise FloorError(
            f"the JUnit report at {junit_path} contains no <testsuite> "
            f"element (root tag {root.tag!r}), so it records no run at all."
        )
    return suites


def executed_tests(junit_path):
    """Return ``(executed, reported, skipped)`` for a pytest JUnit report.

    ``executed`` is ``reported - skipped``: the tests that actually ran. Read
    from the XML rather than from console output, because the console format is
    presentation and changes between versions while the attributes are a
    contract.
    """
    suites = _parse_suites(junit_path)
    reported = sum(_int_attr(s, "tests", junit_path) for s in suites)
    skipped = sum(_int_attr(s, "skipped", junit_path) for s in suites)
    executed = reported - skipped

    if executed < 0:
        raise FloorError(
            f"the JUnit report at {junit_path} reports {skipped} skipped tests "
            f"out of {reported} total, which is impossible. The report is "
            "inconsistent and cannot be graded."
        )
    return executed, reported, skipped


def check_floor(junit_path, min_executed, label=""):
    """Return an error message, or None when the run cleared the floor."""
    where = f" for {label}" if label else ""

    # A floor of zero is satisfied by a run that did nothing, which is the
    # defect this module exists to catch. Refuse it rather than honour it.
    if min_executed < 1:
        return (
            f"the configured floor{where} is {min_executed}, but a floor below "
            "1 is satisfied by a run that executed nothing -- which is the "
            "defect this check exists to catch. Set a real expected minimum."
        )

    try:
        executed, reported, skipped = executed_tests(junit_path)
    except FloorError as exc:
        return f"{exc}"

    if executed == 0:
        return (
            f"the suite{where} executed 0 tests ({reported} reported, "
            f"{skipped} skipped), so this job proves nothing.\n"
            "pytest exits 0 when every test skips, which is why the exit code "
            "did not catch this. Establish why the tests skip -- run with -rs "
            "-- before changing anything."
        )

    if executed < min_executed:
        return (
            f"the suite{where} executed {executed} tests, below the floor of "
            f"{min_executed} ({reported} reported, {skipped} skipped).\n"
            "Most of the suite did not run, so its green says nothing about "
            "the tests that did not. Check the paths, the -m expression, and "
            "the skip reasons (-rs) before trusting this result."
        )

    print(
        f"executed-test floor{where}: {executed} executed "
        f"(floor {min_executed}; {reported} reported, {skipped} skipped) -- OK"
    )
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--junit", required=True, help="pytest JUnit XML written by the run"
    )
    parser.add_argument(
        "--min-executed",
        type=int,
        required=True,
        help="the fewest tests this job may execute and still be believed",
    )
    parser.add_argument("--label", default="", help="what this suite is, for messages")
    args = parser.parse_args(argv)

    problem = check_floor(args.junit, args.min_executed, args.label)
    if problem:
        # ::error:: surfaces it in the GitHub Actions annotation panel, where a
        # reader looking at a red job sees the reason without opening the log.
        print(f"::error::executed-test floor failed: {problem}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
