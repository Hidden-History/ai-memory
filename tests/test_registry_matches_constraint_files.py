"""The shipped Constraint registry and the shipped Constraint files name the same Constraints.

The comparison is a set of plain functions in this module. It starts from the
Constraint files (every ID-named file under the constraints directory, and
every Constraint a category index names as kept in another file) and from the
registry, and it has three outcomes: the two sides agree, they disagree, or it
could not check. Only agreement passes. ``require_agreement`` turns the other
two into a failed test, never a skip.

Every case except the shipped tree is built on ``tmp_path`` with synthetic
identifiers. The comparison is a test in the product's source and is not run
in an installed project.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from memory.degraded import POV_TREE

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parent.parent
_POV_ROOT = _REPO / POV_TREE
_DETECTORS_DIR = _POV_ROOT / "detectors"
_CONSTRAINTS_DIR = _POV_ROOT / "constraints"
_SHIPPED_REGISTRY = _DETECTORS_DIR / "constraint-registry.csv"
_README = _DETECTORS_DIR / "README.md"
_CHANGELOG = _REPO / "CHANGELOG.md"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _DETECTORS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry = _load("constraint_registry")

# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

AGREE = "agree"
DISAGREE = "disagree"
COULD_NOT_CHECK = "could-not-check"

_FILE_NAME = re.compile(r"^[A-Z]{2}-[0-9]{2}-.+\.md$")
_ID_TOKEN = re.compile(r"(?<![A-Za-z0-9-])[A-Z]{2}-[0-9]{2}(?![A-Za-z0-9])")
_INDEX_NAME = "constraints.md"
_NOTE_PREFIX = "**Note**:"


@dataclass(frozen=True)
class Holder:
    """A file that holds Constraints which have no file of their own."""

    words: str
    """What an index line says to name this holder."""

    path: str
    """The holding file, relative to the pov tree root."""

    heading: str
    """The heading its entries sit under."""


#: The one live holder. The live skill's name is written here and nowhere else
#: in this module; every ``tmp_path`` case passes its own synthetic holders.
SHIPPED_HOLDERS = (
    Holder(
        words="aim-agent-dispatch skill",
        path="skills/aim-agent-dispatch/SKILL.md",
        heading="## Embedded Constraints (Layer 3)",
    ),
)


@dataclass(frozen=True)
class Comparison:
    status: str
    differences: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Fileless:
    id: str
    index: str
    line: int
    holder: Holder


@dataclass(frozen=True)
class _ConstraintSide:
    files: dict[str, tuple[str, ...]]
    """id -> the ID-named files that carry it (relative to the constraints directory)."""

    fileless: tuple[_Fileless, ...]
    reasons: tuple[str, ...]

    @property
    def ids(self) -> set[str]:
        return set(self.files) | {item.id for item in self.fileless}


def _printable(text: str) -> str:
    """Text from a file, made safe to put in a message."""
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in str(text))


def _relative(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text(path: Path) -> tuple[str | None, str]:
    try:
        return path.read_text(encoding="utf-8"), ""
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {_printable(exc)}"


def read_constraint_side(
    constraints_dir: Path, pov_root: Path, holders: tuple[Holder, ...]
) -> _ConstraintSide:
    """The Constraints the files and the category indexes define."""
    reasons: list[str] = []
    files: dict[str, list[str]] = {}
    fileless: list[_Fileless] = []
    side = "Constraint side"

    if not constraints_dir.is_dir():
        reasons.append(
            f"{side}: the constraints directory {_printable(constraints_dir)} is"
            " absent or is not a directory"
        )
        return _ConstraintSide({}, (), tuple(reasons))
    try:
        found = sorted(p for p in constraints_dir.rglob("*") if p.is_file())
    except OSError as exc:
        reasons.append(
            f"{side}: the constraints directory could not be listed"
            f" ({type(exc).__name__}: {_printable(exc)})"
        )
        return _ConstraintSide({}, (), tuple(reasons))

    indexes = []
    for path in found:
        if _FILE_NAME.match(path.name):
            files.setdefault(path.name[:5], []).append(_relative(path, constraints_dir))
        elif path.name == _INDEX_NAME:
            indexes.append(path)

    for index in indexes:
        name = _relative(index, constraints_dir)
        text, error = _read_text(index)
        if text is None:
            reasons.append(f"{side}: the index {name} could not be read ({error})")
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.startswith(_NOTE_PREFIX):
                continue
            token = _ID_TOKEN.search(line)
            if token is None:
                continue
            named = [h for h in holders if h.words in line]
            if len(named) != 1:
                what = (
                    "the words of no holder"
                    if not named
                    else "the words of more than one holder"
                )
                reasons.append(
                    f"{side}: {name} line {number} names {token.group(0)} as kept"
                    f" elsewhere but carries {what}: {_printable(line)}"
                )
                continue
            fileless.append(_Fileless(token.group(0), name, number, named[0]))

    if not files and not fileless and not reasons:
        reasons.append(
            f"{side}: found empty - no ID-named Constraint file and no index line"
            f" naming a Constraint kept in another file under {_printable(constraints_dir)}"
        )
    return _ConstraintSide(
        {k: tuple(v) for k, v in files.items()}, tuple(fileless), tuple(reasons)
    )


def _holder_entries(text: str, heading: str) -> set[str] | None:
    """The ids with a list entry under *heading*, or None when it is absent."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return None
    entries: set[str] = set()
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        match = re.match(r"^- \*\*([A-Z]{2}-[0-9]{2})\*\*:", line)
        if match:
            entries.add(match.group(1))
    return entries


def compare(
    registry_path: Path,
    constraints_dir: Path,
    pov_root: Path,
    holders: tuple[Holder, ...] = SHIPPED_HOLDERS,
) -> Comparison:
    """Compare the registry with the Constraint files and the category indexes."""
    constraint = read_constraint_side(constraints_dir, pov_root, holders)
    reasons = list(constraint.reasons)

    read = registry.read_registry(registry_path)
    registry_ids: dict[str, int] = {}
    registry_empty = False
    if read.status == registry.UNCHECKED:
        reasons.append(
            f"registry side: {_printable(registry_path)} could not be read"
            f" ({_printable(read.detail)})"
        )
    elif read.status == registry.EMPTY:
        registry_empty = True
        reasons.append(
            f"registry side: found empty - {_printable(registry_path)} holds a"
            " header and no rows"
        )
    else:
        bad = False
        for row in read.rows:
            failed = row.failed(registry.COLUMN_ID)
            if failed is not None:
                bad = True
                reasons.append(
                    f"registry side: column {registry.COLUMN_ID} on line"
                    f" {row.line} cannot be read ({_printable(failed.reason)})"
                )
            else:
                registry_ids[row.values[registry.COLUMN_ID]] = row.line
        if bad:
            registry_ids = {}

    if reasons:
        if registry_empty and constraint.ids:
            reasons.extend(
                f"{cid}: has no row - missing from the registry"
                for cid in sorted(constraint.ids)
            )
        return Comparison(COULD_NOT_CHECK, reasons=tuple(reasons))

    differences: list[str] = []
    population = constraint.ids
    by_id: dict[str, list[_Fileless]] = {}
    for item in constraint.fileless:
        by_id.setdefault(item.id, []).append(item)

    for cid, paths in sorted(constraint.files.items()):
        if len(paths) > 1:
            differences.append(
                f"{cid}: carried by more than one Constraint file: " + ", ".join(paths)
            )
        if cid in by_id:
            for item in by_id[cid]:
                differences.append(
                    f"{cid}: has its own Constraint file ({paths[0]}) and is also"
                    f" named by the index line {item.index} line {item.line} as"
                    " kept in another file - one of the two places is wrong"
                )

    holder_cache: dict[str, set[str] | None] = {}
    for cid, items in sorted(by_id.items()):
        if cid in constraint.files:
            continue
        item = items[0]
        holder = item.holder
        if holder.path not in holder_cache:
            target = pov_root / holder.path
            text, error = _read_text(target)
            if text is None:
                return Comparison(
                    COULD_NOT_CHECK,
                    reasons=(
                        f"Constraint side: the holding file {holder.path} named by"
                        f" {item.index} line {item.line} could not be read ({error})",
                    ),
                )
            holder_cache[holder.path] = _holder_entries(text, holder.heading)
        entries = holder_cache[holder.path]
        if entries is None or cid not in entries:
            differences.append(
                f"{cid}: missing from the file that holds it ({holder.path}, under"
                f" the heading {_printable(holder.heading)}); named as kept there by"
                f" {item.index} line {item.line}"
            )

    for cid in sorted(population - set(registry_ids)):
        if cid in constraint.files:
            where = f"Constraint file {constraint.files[cid][0]}"
        else:
            item = by_id[cid][0]
            where = f"index line {item.index} line {item.line}"
        differences.append(f"{cid}: missing from the registry ({where})")

    for cid in sorted(set(registry_ids) - population):
        differences.append(
            f"{cid}: missing from the Constraint files and the index lines"
            f" (registry line {registry_ids[cid]} has a row for it)"
        )

    if differences:
        return Comparison(DISAGREE, differences=tuple(differences))
    return Comparison(AGREE)


def require_agreement(result: Comparison) -> None:
    """Pass on agreement. Fail on disagreement, and fail on could not check."""
    if result.status == AGREE:
        return
    if result.status == DISAGREE:
        pytest.fail(
            "the registry and the Constraint files disagree:\n  "
            + "\n  ".join(result.differences),
            pytrace=False,
        )
    pytest.fail(
        "could not check whether the registry and the Constraint files agree:\n  "
        + "\n  ".join(result.reasons),
        pytrace=False,
    )


def _shipped() -> Comparison:
    return compare(_SHIPPED_REGISTRY, _CONSTRAINTS_DIR, _POV_ROOT)


# ---------------------------------------------------------------------------
# Builders for tmp_path trees (synthetic identifiers only)
# ---------------------------------------------------------------------------

HEADER = "id,detector,enforcement_state\n"
ZZ_HEADING = "## Zz Embedded Constraints"
ZZ_HOLDERS = (
    Holder(
        words="zz-holder skill", path="skills/zz-holder/SKILL.md", heading=ZZ_HEADING
    ),
)
ZY_HOLDERS = (
    Holder(words="zy-other skill", path="skills/zy-other/SKILL.md", heading="## Zy"),
)


def _rows(*ids: str) -> str:
    return HEADER + "".join(f"{cid},,not-yet-enforced\n" for cid in ids)


def _tree(
    tmp_path: Path,
    *,
    files: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    held: tuple[str, ...] = (),
    rows: str | None = None,
    holder_text: str | None = None,
    index_prose: str = "",
) -> tuple[Path, Path, Path]:
    """A registry, a constraints directory and a pov root, all synthetic."""
    pov = tmp_path / "pov"
    cdir = pov / "constraints"
    category = cdir / "zy"
    category.mkdir(parents=True)
    for cid in files:
        (category / f"{cid}-name.md").write_text(f"# {cid}\n", encoding="utf-8")
    index = ["# Zy constraints", "", "| Id | Name |", "|---|---|"]
    index += [f"| {cid} | name |" for cid in files]
    index += ["", index_prose]
    index += [
        f"{_NOTE_PREFIX} {cid} (Some Name) is kept in the zz-holder skill as a"
        " Layer 3 constraint."
        for cid in notes
    ]
    (category / _INDEX_NAME).write_text("\n".join(index) + "\n", encoding="utf-8")
    holder = pov / "skills" / "zz-holder" / "SKILL.md"
    holder.parent.mkdir(parents=True)
    if holder_text is None:
        holder_text = (
            "# Holder\n\n"
            + ZZ_HEADING
            + "\n\n"
            + "".join(f"- **{cid}**: text\n" for cid in held)
            + "\n## Later\n\n- **ZX-99**: not under the heading\n"
        )
    holder.write_text(holder_text, encoding="utf-8")
    reg = tmp_path / "constraint-registry.csv"
    if rows is None:
        rows = _rows(*sorted(set(files) | set(notes)))
    reg.write_bytes(rows.encode("utf-8"))
    return reg, cdir, pov


def _check(
    tmp_path: Path, holders: tuple[Holder, ...] = ZZ_HOLDERS, **kw
) -> Comparison:
    reg, cdir, pov = _tree(tmp_path, **kw)
    return compare(reg, cdir, pov, holders)


def _failure_message(result: Comparison) -> str:
    with pytest.raises(pytest.fail.Exception) as info:
        require_agreement(result)
    return str(info.value)


# ---------------------------------------------------------------------------
# The shipped tree
# ---------------------------------------------------------------------------


@pytest.mark.process
def test_the_shipped_registry_and_the_shipped_constraint_files_agree() -> None:
    require_agreement(_shipped())


@pytest.mark.process
def test_every_shipped_holder_exists_and_carries_the_heading_the_map_gives() -> None:
    for holder in SHIPPED_HOLDERS:
        path = _POV_ROOT / holder.path
        assert path.is_file(), holder.path
        headings = [line.strip() for line in path.read_text("utf-8").splitlines()]
        assert holder.heading in headings, holder.path


@pytest.mark.process
def test_the_shipped_registry_enters_each_shipped_constraint_once_as_not_yet_enforced() -> (
    None
):
    side = read_constraint_side(_CONSTRAINTS_DIR, _POV_ROOT, SHIPPED_HOLDERS)
    assert side.reasons == ()
    read = registry.read_registry(_SHIPPED_REGISTRY)
    assert read.status == registry.READ
    assert read.excluded == ()
    ids = []
    for row in read.rows:
        assert row.excluded == (), row.line
        assert set(row.values) == set(registry.REQUIRED_COLUMNS), row.line
        assert row.values[registry.COLUMN_DETECTOR] == ""
        assert row.values[registry.COLUMN_STATE] == "not-yet-enforced"
        ids.append(row.values[registry.COLUMN_ID])
    assert len(ids) == len(set(ids)), "an id is entered more than once"
    assert set(ids) == side.ids


# ---------------------------------------------------------------------------
# Disagreement (AC-3)
# ---------------------------------------------------------------------------


def test_agreement_on_a_small_tree_passes(tmp_path: Path) -> None:
    result = _check(tmp_path, files=("ZY-01", "ZY-02"))
    assert result.status == AGREE
    require_agreement(result)


def test_a_constraint_file_with_no_row_fails_naming_the_id_and_the_registry(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=("ZY-01", "ZY-02"), rows=_rows("ZY-01"))
    assert result.status == DISAGREE
    message = _failure_message(result)
    assert "ZY-02: missing from the registry" in message
    assert "ZY-01" not in message


def test_a_row_with_no_constraint_file_and_no_index_line_fails_naming_the_id(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=("ZY-01",), rows=_rows("ZY-01", "ZY-07"))
    assert result.status == DISAGREE
    assert "ZY-07: missing from the Constraint files and the index lines" in (
        _failure_message(result)
    )


def test_several_differences_at_once_are_all_named(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        files=("ZY-01", "ZY-02", "ZY-03"),
        rows=_rows("ZY-01", "ZY-07", "ZY-08"),
    )
    message = _failure_message(result)
    for text in (
        "ZY-02: missing from the registry",
        "ZY-03: missing from the registry",
        "ZY-07: missing from the Constraint files",
        "ZY-08: missing from the Constraint files",
    ):
        assert text in message


def test_a_constraint_kept_in_another_file_in_all_three_places_agrees(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=("ZY-01",), notes=("ZY-05",), held=("ZY-05",))
    assert result.status == AGREE


def test_a_constraint_kept_elsewhere_removed_from_the_registry_fails_naming_it(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        files=("ZY-01",),
        notes=("ZY-05",),
        held=("ZY-05",),
        rows=_rows("ZY-01"),
    )
    message = _failure_message(result)
    assert "ZY-05: missing from the registry" in message
    assert "missing from the file that holds it" not in message


def test_a_constraint_kept_elsewhere_removed_from_its_index_fails_naming_it(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        files=("ZY-01",),
        notes=(),
        held=("ZY-05",),
        rows=_rows("ZY-01", "ZY-05"),
    )
    assert "ZY-05: missing from the Constraint files and the index lines" in (
        _failure_message(result)
    )


def test_a_constraint_kept_elsewhere_removed_from_its_holder_fails_naming_it_and_the_file(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=("ZY-01",), notes=("ZY-05",), held=())
    message = _failure_message(result)
    assert "ZY-05: missing from the file that holds it" in message
    assert "skills/zz-holder/SKILL.md" in message
    assert ZZ_HEADING in message
    assert "missing from the registry" not in message


def test_a_constraint_kept_elsewhere_removed_from_registry_and_holder_is_named_twice(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        files=("ZY-01",),
        notes=("ZY-05",),
        held=(),
        rows=_rows("ZY-01"),
    )
    lines = [x for x in _failure_message(result).splitlines() if "ZY-05" in x]
    assert len(lines) == 2
    assert any("missing from the registry" in x for x in lines)
    assert any("missing from the file that holds it" in x for x in lines)


def test_an_entry_written_with_a_suffix_or_mentioned_elsewhere_is_not_the_entry(
    tmp_path: Path,
) -> None:
    text = (
        f"# Holder\n\n{ZZ_HEADING}\n\n- **ZY-05 L3**: a second wording\n"
        "A mention of ZY-05 in prose.\n\n## Later\n\n- **ZY-05**: wrong section\n"
    )
    result = _check(
        tmp_path,
        files=("ZY-01",),
        notes=("ZY-05",),
        holder_text=text,
    )
    assert result.status == DISAGREE
    assert "ZY-05: missing from the file that holds it" in _failure_message(result)


def test_an_id_with_its_own_file_that_an_index_also_names_as_kept_elsewhere_fails(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path, files=("ZY-01", "ZY-02"), notes=("ZY-02",), held=("ZY-02",)
    )
    assert result.status == DISAGREE
    message = _failure_message(result)
    line = next(x for x in message.splitlines() if "ZY-02" in x)
    assert "own Constraint file" in line
    assert "ZY-02-name.md" in line
    assert "zy/constraints.md line " in line
    assert "ZY-01" not in message


def test_an_id_on_two_constraint_files_fails_naming_both(tmp_path: Path) -> None:
    reg, cdir, pov = _tree(tmp_path, files=("ZY-01",))
    other = cdir / "zx"
    other.mkdir()
    (other / "ZY-01-again.md").write_text("# again\n", encoding="utf-8")
    result = compare(reg, cdir, pov, ZZ_HOLDERS)
    assert result.status == DISAGREE
    message = _failure_message(result)
    assert "ZY-01: carried by more than one Constraint file" in message
    assert "zy/ZY-01-name.md" in message
    assert "zx/ZY-01-again.md" in message


def test_prose_naming_a_range_of_ids_outside_a_note_line_adds_nothing(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        files=("ZY-01",),
        index_prose="Global constraints (ZG-01 through ZG-22) are always active.",
    )
    assert result.status == AGREE


def test_a_file_that_is_not_an_id_named_constraint_is_not_a_constraint(
    tmp_path: Path,
) -> None:
    reg, cdir, pov = _tree(tmp_path, files=("ZY-01",))
    (cdir / "zy" / ".audit" / "logs").mkdir(parents=True)
    (cdir / "zy" / ".audit" / "logs" / "ZY-77.log").write_text("x", encoding="utf-8")
    (cdir / "zy" / "notes.md").write_text("ZY-88 is mentioned\n", encoding="utf-8")
    assert compare(reg, cdir, pov, ZZ_HOLDERS).status == AGREE


def test_a_note_line_with_no_id_names_no_constraint_and_is_ignored(
    tmp_path: Path,
) -> None:
    reg, cdir, pov = _tree(tmp_path, files=("ZY-01",))
    index = cdir / "zy" / _INDEX_NAME
    index.write_text(
        index.read_text("utf-8") + f"{_NOTE_PREFIX} nothing here is a Constraint.\n",
        encoding="utf-8",
    )
    assert compare(reg, cdir, pov, ZZ_HOLDERS).status == AGREE


# ---------------------------------------------------------------------------
# Could not check (AC-4): never a pass, never a skip
# ---------------------------------------------------------------------------


def _assert_could_not_check(result: Comparison, *words: str) -> str:
    assert result.status == COULD_NOT_CHECK
    message = _failure_message(result)
    assert message.startswith("could not check")
    for word in words:
        assert word in message, word
    return message


def test_a_registry_with_a_header_and_no_rows_beside_constraint_files_could_not_check(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        files=("ZY-01", "ZY-02"),
        notes=("ZY-05",),
        held=("ZY-05",),
        rows=HEADER,
    )
    message = _assert_could_not_check(result, "registry side: found empty")
    for cid in ("ZY-01", "ZY-02", "ZY-05"):
        assert f"{cid}: has no row" in message
    assert "Constraint side" not in message


def test_both_sides_empty_is_not_agreement(tmp_path: Path) -> None:
    result = _check(tmp_path, files=(), rows=HEADER)
    _assert_could_not_check(
        result, "registry side: found empty", "Constraint side: found empty"
    )


def test_an_empty_constraint_side_beside_registry_rows_could_not_check(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=(), rows=_rows("ZY-01"))
    _assert_could_not_check(result, "Constraint side: found empty")


def test_an_absent_constraints_directory_could_not_check(tmp_path: Path) -> None:
    reg, _, pov = _tree(tmp_path, files=("ZY-01",))
    result = compare(reg, tmp_path / "nowhere", pov, ZZ_HOLDERS)
    _assert_could_not_check(result, "Constraint side", "absent or is not a directory")


def test_a_constraints_path_that_is_a_file_could_not_check(tmp_path: Path) -> None:
    reg, _, pov = _tree(tmp_path, files=("ZY-01",))
    result = compare(reg, reg, pov, ZZ_HOLDERS)
    _assert_could_not_check(result, "Constraint side")


def test_an_absent_registry_could_not_check_naming_the_registry(tmp_path: Path) -> None:
    _, cdir, pov = _tree(tmp_path, files=("ZY-01",))
    result = compare(tmp_path / "missing.csv", cdir, pov, ZZ_HOLDERS)
    _assert_could_not_check(result, "registry side")


def test_an_unreadable_index_could_not_check_naming_the_index(tmp_path: Path) -> None:
    reg, cdir, pov = _tree(tmp_path, files=("ZY-01",))
    (cdir / "zy" / _INDEX_NAME).write_bytes(b"\xff\xfe\x00bad\n")
    result = compare(reg, cdir, pov, ZZ_HOLDERS)
    _assert_could_not_check(result, "Constraint side", "zy/constraints.md")


def test_an_absent_holding_file_could_not_check_naming_it(tmp_path: Path) -> None:
    reg, cdir, pov = _tree(
        tmp_path, files=("ZY-01",), notes=("ZY-05",), held=("ZY-05",)
    )
    (pov / "skills" / "zz-holder" / "SKILL.md").unlink()
    result = compare(reg, cdir, pov, ZZ_HOLDERS)
    _assert_could_not_check(
        result,
        "Constraint side",
        "skills/zz-holder/SKILL.md",
        "zy/constraints.md line ",
    )


def test_a_note_line_with_an_id_and_no_holder_in_the_map_could_not_check(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        holders=ZY_HOLDERS,
        files=("ZY-01",),
        notes=("ZY-05",),
        held=("ZY-05",),
    )
    message = _assert_could_not_check(
        result, "Constraint side", "zy/constraints.md line ", "ZY-05", "no holder"
    )
    assert "more than one" not in message


def test_a_note_line_carrying_the_words_of_two_holders_could_not_check(
    tmp_path: Path,
) -> None:
    both = (
        *ZZ_HOLDERS,
        Holder(
            words="zz-holder skill as", path="skills/zz-holder/SKILL.md", heading="## X"
        ),
    )
    result = _check(
        tmp_path, holders=both, files=("ZY-01",), notes=("ZY-05",), held=("ZY-05",)
    )
    _assert_could_not_check(result, "Constraint side", "more than one holder", "ZY-05")


def test_a_registry_with_a_line_break_in_a_cell_could_not_check(tmp_path: Path) -> None:
    rows = HEADER + 'ZY-01,"a\nb",not-yet-enforced\n'
    result = _check(tmp_path, files=("ZY-01",), rows=rows)
    _assert_could_not_check(result, "registry side")


def test_a_repeated_registry_id_could_not_check_naming_the_column_and_line(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=("ZY-01",), rows=_rows("ZY-01", "ZY-01"))
    _assert_could_not_check(result, "registry side", "column id on line ")


def test_an_empty_registry_id_could_not_check_naming_the_column_and_line(
    tmp_path: Path,
) -> None:
    rows = HEADER + ",,not-yet-enforced\n" + "ZY-01,,not-yet-enforced\n"
    result = _check(tmp_path, files=("ZY-01",), rows=rows)
    _assert_could_not_check(result, "registry side", "column id on line 2")


def test_could_not_check_is_a_failure_that_is_neither_a_skip_nor_a_pass(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, files=("ZY-01",), rows=HEADER)
    with pytest.raises(pytest.fail.Exception):
        require_agreement(result)


def test_a_message_prints_no_count_and_makes_text_from_files_safe(
    tmp_path: Path,
) -> None:
    reg, cdir, pov = _tree(tmp_path, files=("ZY-01",), notes=("ZY-05",))
    index = cdir / "zy" / _INDEX_NAME
    index.write_text(
        index.read_text("utf-8")
        + f"{_NOTE_PREFIX} ZY-06 kept in the qq-other skill \x1b[31mred\n",
        encoding="utf-8",
    )
    message = _failure_message(compare(reg, cdir, pov, ZZ_HOLDERS))
    assert "\x1b" not in message
    assert "\\u001b" in message
    assert not re.search(r"\b\d+ (Constraint|row|file)", message)


# ---------------------------------------------------------------------------
# The written descriptions of the shipped registry (AC-5)
# ---------------------------------------------------------------------------

_STALE = (
    "the check reports `empty:constraint-registry`",
    "holds a header row and no Constraints",
    "Until it holds rows",
    "on the shipped product every count is zero",
    "The shipped registry has no rows",
    "the shipped product there is nothing to resolve",
    "still holds no rows",
    "while the registry has no rows",
    "registry is empty and belongs to the installer",
)


def _unreleased() -> str:
    text = _CHANGELOG.read_text(encoding="utf-8")
    start = text.index("## [Unreleased]")
    end = text.find("\n## [", start + 1)
    return text[start : end if end != -1 else len(text)]


def _row_count_sentence(text: str, count: int) -> re.Match | None:
    pattern = (
        rf"(?<![0-9]){count}(?![0-9])[^.!?\n]*?\b(rows?|Constraints?)\b"
        rf"(?![^.!?\n]*\n\n)"
    )
    return re.search(pattern, text, flags=re.IGNORECASE)


def _shipped_row_count() -> int:
    return len(registry.read_registry(_SHIPPED_REGISTRY).rows)


@pytest.mark.process
@pytest.mark.parametrize("which", ["readme", "changelog"])
def test_no_description_of_the_shipped_registry_still_says_it_is_empty(
    which: str,
) -> None:
    text = _README.read_text("utf-8") if which == "readme" else _unreleased()
    flat = " ".join(text.split())
    found = [phrase for phrase in _STALE if phrase in flat]
    assert found == []


@pytest.mark.process
def test_the_readme_says_every_shipped_constraint_is_entered_and_none_is_enforced() -> (
    None
):
    flat = " ".join(_README.read_text("utf-8").split())
    for required in (
        "Every Constraint the product ships is entered in the shipped registry as `not-yet-enforced`",
        "None is yet enforced by a Detector",
        '-m "not regression and not quarantine"',
        "is a test in the product's source and is not run in an installed project",
    ):
        assert required in flat, required


@pytest.mark.process
def test_the_changelog_line_for_the_comparison_carries_its_three_statements() -> None:
    flat = " ".join(_unreleased().split()).lower()
    for required in (
        "every constraint the product ships is entered in the shipped registry as `not-yet-enforced`",
        "none is yet enforced by a detector",
        "tests/test_registry_matches_constraint_files.py",
    ):
        assert required in flat, required


@pytest.mark.process
@pytest.mark.parametrize("which", ["readme", "changelog"])
def test_neither_description_states_the_number_of_rows(which: str) -> None:
    count = _shipped_row_count()
    assert count > 0
    text = _README.read_text("utf-8") if which == "readme" else _unreleased()
    assert _row_count_sentence(text, count) is None


@pytest.mark.parametrize(
    "sentence",
    ["The registry ships {n} rows.", "It holds {n} Constraint entries, all alike."],
)
def test_the_row_count_pattern_catches_a_stated_count_and_ignores_other_numbers(
    sentence: str,
) -> None:
    assert _row_count_sentence("Intro. " + sentence.format(n=85), 85)
    assert _row_count_sentence("Intro. " + sentence.format(n=185), 85) is None
    assert _row_count_sentence("85 things. The rows are listed.", 85) is None
