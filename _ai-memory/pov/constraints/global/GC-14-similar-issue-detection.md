---
id: GC-14
name: Similar Issue Detection
severity: HIGH
category: Quality
phase: global
---

# GC-14: ALWAYS Check for Similar Prior Issues Before Creating a New Bug Report

## Rule

Before logging any new bug, error, or issue, Parzival MUST search existing oversight records
for prior reports on the same component, file, or symptom.

## What to Check

- `{oversight_path}/bugs/` — existing BUG-XXX reports for same file/component
- `{oversight_path}/tracking/blockers-log.md` — prior blockers with similar symptoms
- Search criteria: same file path, same error message/exception type, same symptom description,
  same component (e.g., "hooks", "trace_buffer", "session_id propagation")

## Required Action

- If a matching prior report is found: reference it in the new report. Determine if this is
  the same root cause or a related but distinct issue. Do not open a duplicate if it is the same.
- If no matching report is found: proceed with creating the new bug report using
  `{oversight_path}/bugs/BUG_TEMPLATE.md`.

## Rationale

Prevents solving the same problem twice with different fixes. Enables root cause pattern
detection across sessions. Derived from V1 C2 lesson: Memory System V2 development produced
duplicate fixes for the same underlying issues because prior reports were not checked.

## Self-Check

- GC-14: Before logging a new bug, did I search oversight/bugs/ for prior similar reports?

## Violation Response

1. Stop — do not create the new bug report yet
2. Search oversight/bugs/ and blockers-log.md for matching symptoms
3. If match found: link to prior report, determine if same root cause
4. If no match: proceed with new report using BUG_TEMPLATE.md
