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
