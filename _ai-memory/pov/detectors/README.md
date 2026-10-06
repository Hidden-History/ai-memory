# Detectors

This directory holds the product's Constraint registry, the reader for it, and
the orphan check. Not every file here is a detector: `constraint-registry.csv`,
`constraint_registry.py`, `orphan_check.py` and this README are not.

## Read this first: the shipped registry belongs to the installer

1. `constraint-registry.csv` in this directory is the **product's base
   registry**. The installer owns it and replaces it on every install.
2. A row added to it in an installed project **does not survive the next
   install**. After that install the file is back to what the product ships,
   and the check reports `empty:constraint-registry` and exits `0`.
3. **There is no place here for a project's own Constraints.** `--registry PATH`
   makes the check read a different file instead; nothing merges two files.

The shipped registry holds a header row and no Constraints. Until it holds
rows, the check proves that the mechanism works and enforces nothing.

## The registry

A CSV file, UTF-8, with one header row and then one row per Constraint. It is
read with a CSV parser, so a quoted field may contain commas.

| Column | Required in header | A value is valid when |
|---|---|---|
| `id` | yes | it is not empty after trimming spaces, and no other row has the same `id` |
| `detector` | yes | always. A cell that is empty after trimming spaces means no Detector is declared |
| `enforcement_state` | yes | it is empty, or it is exactly one of the four tokens below |
| any other column | no | it is not validated and not read by the check |

The four Enforcement states, in order:

1. `unenforceable`
2. `not-yet-enforced`
3. `enforced-but-non-blocking`
4. `enforced-and-blocking`

The tokens are case-sensitive and `enforcement_state` is not trimmed. `true`,
`false`, `yes`, `no`, `1`, `0` and `unenforced` are not markings: a marking
says which of the four states applies, or it is refused.

Validation is per column. A field that fails is excluded and reported, and its
row is kept. A row that is too short has **absent** fields, which is a
failure of those fields; an empty cell is a value. A row with more fields than
the header declares keeps its disposition, and the extra fields are reported
as one excluded field.

## What the check decides

Each row gets exactly one disposition.

| Disposition | When | Makes the check exit `1` |
|---|---|---|
| `orphan` | `detector` and `enforcement_state` are both empty | yes |
| `refused:<column>` | `id`, `detector` or `enforcement_state` failed validation. The first failing column in that order is named | yes |
| `refused:enforcement_state` | the state is `enforced-but-non-blocking` or `enforced-and-blocking` and no Detector is declared | yes |
| `marked:<state>` | no Detector is declared and the state is `unenforceable` or `not-yet-enforced` | no |
| `bound` | a Detector is declared and no field the check reads failed | no |

The check does **not** verify that a declared Detector exists or can fail, and
it does **not** compare the registry against the constraint files on disk. It
reads the rows of one registry file and nothing else.

## Running it

From this directory:

```text
python3 orphan_check.py [--registry PATH]
```

With no `--registry`, the check reads `constraint-registry.csv` beside itself.

Output is text on standard output. Each orphan or refused row prints one line
starting `finding:`, with the row's line number in the file, its `id` where
one is readable, the disposition and the reason. Each excluded field prints
one line starting `exclusion:`. The last line is the outcome.

| Outcome | When | Exit status |
|---|---|---|
| finding lines, then a `checked ...` line | at least one row is `orphan` or `refused:*` | `1` |
| `clean:constraint-registry` | the registry holds at least one row and none is `orphan` or `refused:*` | `0` |
| `empty:constraint-registry` | the registry was read and holds no Constraint rows | `0` |
| `unchecked:constraint-registry` | the registry could not be checked: no file at the path, the file could not be read or parsed, it has no header, or the header is missing a required column or declares one twice | `2` |

Exit status `2` is also what a wrong command line returns. The check returns
`0`, `1` or `2` and no other value.

An excluded field in a column the check does not read is reported and counted
and does not change the exit status by itself.

Other code that needs these facts imports `read_registry` from
`constraint_registry.py` and `row_disposition` from `orphan_check.py`; the
printed text has no machine-readable form.

## Fixture pairs and the binding check

### Read this first: the fixture location belongs to the installer

1. This directory and `fixtures/` inside it hold **the product's own**
   Detectors and fixture pairs. The installer owns both and replaces them on
   every install.
2. A Detector or a fixture pair added here in an installed project **does not
   survive the next install**. Nothing reports the loss; the binding check
   no longer sees them.
3. **There is no place here for a project's own fixture pairs.** `--root DIR`
   makes the binding check read a different directory instead; nothing merges
   two.

### What "Detector" means for the binding check

The top of this README says `orphan_check.py` is not a detector. For the
binding check it is one. The binding check uses the word for **a program in
this directory that can refuse, and so owes a fixture pair**: a `.py` file
directly in the directory with a top-level `if __name__ == "__main__":` block.
By that rule `orphan_check.py` is the one Detector here.
`constraint_registry.py` has no such block and is not one. Nothing inside
`fixtures/` or any other sub-directory is looked at.

A `.py` file that cannot be read or parsed is treated as a Detector, because
it cannot be shown not to be one.

The binding check does not check itself. The last line it prints names the
files in its own directory that it left out.

### Where a pair lives

`fixtures/` in this directory is the one declared fixture location. The pair
for the Detector `<name>.py` is the directory `fixtures/<name>/`. The name is
the binding: no file points from a Detector to its pair.

A pair directory holds one manifest, `fixture-pair.json`, and the fixtures the
manifest names. A fixture is the file or directory a manifest path names. The
path may reach into a sub-directory of the pair directory and may not leave
it. A file in the fixture location that no manifest names is not a fixture and
is not reported.

### The manifest

`fixture-pair.json` is one JSON object, UTF-8.

| Key | Required | Valid when |
|---|---|---|
| `fixture_marker` | yes | it is exactly `synthetic-fixture` |
| `args` | yes | it is a list of strings, and at least one contains `{fixture}` |
| `positive` | yes | it is a relative path to an existing fixture inside the pair directory: the example the Detector must flag |
| `negative` | yes | the same: the example the Detector must not flag |
| `exemptions` | yes | it is an object mapping an exemption id to a fixture path inside the pair directory. It may be empty |

A path that is absolute, contains `..`, or resolves outside the pair directory
is not valid.

`fixture_marker` is the fixture marker. It is carried once, in the manifest,
and covers every fixture the manifest names. Fixtures use synthetic
identifiers only, never the name of a real skill, module or agent.

An exemption is something the Detector must **not** fire on. Two are standing,
and every Detector the product ships declares both:

- `labelled-evidentiary-quotation` — a quotation of the defect, kept as
  evidence and labelled as one.
- `historical-record-not-to-inherit` — a historical record marked
  not-to-inherit.

A test in the product's test suite requires the standing two of shipped
Detectors. The binding check itself requires the `exemptions` key and proves
every exemption that is declared.

### How a fixture is run

For each fixture the check runs the Detector with the Python interpreter and
the manifest's `args`, with `{fixture}` replaced by the fixture's absolute
path.

| The Detector exits | The binding check reads it as |
|---|---|
| `0` | pass: the Detector did not flag |
| `1` | fail: the Detector flagged |
| anything else, runs past the time limit, cannot be started, or ends on an uncaught exception | could not be run: neither pass nor fail |

An uncaught exception also exits `1`. The check tells it from a finding by one
rule: an exit of `1` is read as "could not be run" when the Detector's standard
error holds the interpreter's line `Traceback (most recent call last):`.

The rule has one known limit. A Detector that writes that line to standard
error itself while exiting `1` for a real finding is read as a crash. It is
then `unchecked:<name>` and the check exits `2`, so the error is never read as
a pass.

### What the binding check decides

Each Detector gets exactly one verdict. The table is read top to bottom and
the first row that applies is the verdict.

| Verdict | When | Makes the check exit `1` |
|---|---|---|
| `unbound` | there is no `fixtures/<name>/` directory, or no manifest in it, or the manifest names no `positive` or no `negative`, or a file either names does not exist | yes |
| `refused:<key>` | the manifest is not a JSON object or cannot be read (`refused:manifest`), or the named key is missing or not valid, or a declared exemption's fixture does not exist (`refused:exemptions`) | yes |
| `unchecked:<name>` | the Detector could not be parsed, or could not be run on a fixture | no; see exit `2` below |
| `non-functional` | the positive fixture did not make the Detector fail | yes |
| `false-positive:<fixture>` | the positive fixture made it fail, and so did `negative` or the named exemption | yes |
| `functional` | the positive fixture makes it fail, and the negative and every declared exemption make it pass | no |

`functional` is not the orphan check's `bound`. `bound` says a registry row
names a Detector. `functional` says a Detector file's pair was run and behaved.
Nothing joins the two: the binding check does not read the registry.

### Running it

From this directory:

```text
python3 binding_check.py [--root DIR]
```

With no `--root`, the check reads the directory it is in.

Output is text on standard output. Each Detector prints one line: it starts
`finding:` when the verdict makes the check exit `1`, and `detector:`
otherwise. The last line is the outcome.

| Outcome | When | Exit status |
|---|---|---|
| finding lines, then a `checked ...` line | at least one Detector is `unbound`, `refused:*`, `non-functional` or `false-positive:*` | `1` |
| `clean:fixture-binding` | there is at least one Detector and all are `functional` | `0` |
| `empty:fixture-binding` | the directory was read and holds no Detectors | `0` |
| `unchecked:fixture-binding` | there is no directory at the path read, or it could not be listed; or there is no finding and at least one Detector is `unchecked:<name>`; or the check itself failed | `2` |

Exit status `2` is also what a wrong command line returns. The check returns
`0`, `1` or `2` and no other value.

Any total the check prints counts the Detector files present in that one
directory, not counting its own file. The check does **not** read the
Constraint registry, does **not** check that any Constraint names a Detector,
and does **not** inspect fixture content.

Other code that needs these facts imports `check_bindings` and
`detector_files` from `binding_check.py`; the printed text has no
machine-readable form. `check_bindings(root)` returns the run's outcome and
one entry per Detector with its name, its file name and its verdict.
`detector_files(root)` returns the sorted Detector file names, or `None` when
the directory is absent or cannot be listed.
