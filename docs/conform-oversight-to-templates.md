# Conforming oversight files to their templates

This is an interim, manual procedure for bringing your project's oversight files into
conformance with their shipped templates, using the template-parity oracle as the source of
truth. Use it until automated conform and auto-surfacing of conformance findings land in a
future release.

Give Parzival the prompt below in your own project. It walks through detecting
non-conformant files, letting you choose which ones to fix, then conforming them
automatically — backing up first, preserving all content, and looping each fix to zero
findings.

A few things worth knowing before you run it:

- **Default the scope to your live files, not the whole project.** On most projects, the
  bulk of non-conformance sits in historical or archived content. The oracle is report-only,
  so forcing template structure onto history produces placeholder noise for no functional
  gain. Start with live registers and singletons — the files you actually read and update
  every session — and treat historical/archive content as opt-in.
- **Live files get real values, never placeholders.** When a file is one you read regularly,
  add the missing structure and then fill it with real values. Never ship `[TODO]` or empty
  placeholder text into a live register.
- **Watch for synonym gaps.** Sometimes a file already expresses a template's required
  section under a different heading name (for example, a file has `## Findings` where the
  template expects `## Root Cause`). In that case, don't force-add an empty duplicate
  heading — flag the mismatch instead so it can be resolved deliberately.

Copy the block below as-is:

```
Parzival — bring my project's oversight files into conformance with their shipped templates,
using the template-parity oracle as the source of truth. Detect, let me choose the scope, then
conform the chosen files automatically to zero oracle findings — backing up, preserving all
content, and reviewing each fix to zero — and report when done. Follow exactly.

SETUP. Determine my project root as an ABSOLUTE path (the directory containing oversight/).
Substitute it literally wherever you see <ROOT>. Never use "." as the root.

STEP 1 — DETECT (read-only, FULL capture).
Capture the COMPLETE oracle output with a plain redirect — never pipe through head/tail/tee/grep
(a truncated read produces a false result):
  python3 "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/template_parity/template_parity_oracle.py" \
    --registry "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/template_parity/oversight-templates.yaml" \
    --project-root "<ROOT>" --format text > /tmp/oracle_report.txt
Before summarizing: read N from the first line ("N finding(s)"); count STRUCT_NONCONFORMANT,
UNMANAGED, OVER_CAP; confirm STRUCT + UNMANAGED + OVER_CAP = N. If they don't match, STOP,
re-capture and recount. Report N and the three counts to me.

STEP 2 — CLASSIFY, RECOMMEND & LET ME CHOOSE (conform nothing yet).
  - IGNORE UNMANAGED (no template).
  - Separate OVER_CAP → needs rotation (aim-tracking-rotate), not section work. List, don't touch.
  - Sort each STRUCT_NONCONFORMANT file into a fix KIND; show me counts by kind + directory:
      A (missing sections) — file is missing template sections. Fix = add them (add-only).
      B (front-matter)     — e.g. unrecognized/absent plan_role. Fix = set the correct key,
                             then re-check (may then reveal a Kind-A gap).
      C (restructure)      — file uses a different heading/numbering scheme than the template.
                             Fix = remap existing content to the template's sections + renumber.
  - Recommend LIVE core files first (tracking registers, project-status, SESSION_WORK_INDEX,
    INDEX files); historical/archive content is opt-in. Ask which files/areas to conform.
    Conform nothing until I choose.

STEP 3 — CONFORM AUTOMATICALLY, to zero (no per-file stop). For each approved file:
  - Back it up first (copy to <file>.bak) — the rollback net.
  - Apply the fix for its kind, PRESERVING every existing line (never delete or drop content):
      A: add the missing sections.
      B: set the correct front-matter key (state which value you chose and why).
      C: remap existing content under the template's sections and renumber — move content, never drop it.
  - LOOP TO ZERO — all gates must pass before a file is "done":
      (1) oracle reports 0 STRUCT_NONCONFORMANT findings for the file (full capture). (An OVER_CAP
          finding may remain — that is rotation's job, not this loop's; do NOT loop on OVER_CAP.)
      (2) NO CONTENT LOST — every original non-empty line still present somewhere in the file;
      (3) KIND C ONLY — SEMANTIC PLACEMENT: confirm each remapped section's content genuinely
          belongs under its new heading (independent review pass where available; else your own
          careful check). If you cannot confirm a clean mapping, do NOT ship it — restore the
          backup and flag that file for my judgment.
  Run file-disjoint conforms in parallel with teammates + a second review pass where supported;
  else sequentially with the same gates. Don't stop for me between files.

STEP 4 — RECORD. For each conformed file that also shows in the content-drift pending-updates list,
record it "resolved". NEVER record "resolved" on a file the oracle still flags.

STEP 5 — REPORT WHEN COMPLETE. One report: per file — fix kind, what changed (sections added /
front-matter set / sections remapped), before/after oracle; any Kind-C files flagged for my judgment;
the OVER_CAP item; where the .bak backups are; and any friction in these directions.

HARD RULES: Full-capture the oracle output; never summarize from a truncated read. Absolute root,
never ".". Preserve all content — move, never delete or drop. A file is "done" only when the oracle
reports 0 STRUCT_NONCONFORMANT findings AND no content was lost AND (Kind C) content sits under the
right headings. OVER_CAP is rotation, not conforming. Never stamp a file the oracle still flags.
Back up every file first.
```
