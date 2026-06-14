# aim-sot — Grading Exemplars

Contrastive calibration set for the D1–D4 rubric. Read before grading. Covers FAIL, the WEAK-trap (looks WEAK, grades FAIL), WEAK, and PASS. Reuses BP-033 worked examples verbatim; library pair derived from the flask golden-set.

---

## 1. Service entry (source: BP-033 §3)

**BAD — Grade: FAIL**

```
description: "auth service"
```

- D1 ✗ — restates `id`, no role phrase.
- D2 ✗ — no owner anywhere on the row.
- D3 ✗ — no authority basis.
- D4 ✗ — no drift signal.
- **VERDICT: FAIL** (D1 fails; ≥2 dims fail).

---

**BAD — the WEAK trap — Grade: FAIL (not WEAK)**

```
description: "JWT auth and session service"
owner: "@platform"
```

- D1 ✓ — "JWT auth and session service" names artifact + role phrase.
- D2 ✓ — `@platform` present in `owner` field.
- D3 ✗ — no why-authoritative basis stated.
- D4 ✗ — no `drift_check`, no staleness clause.
- **VERDICT: FAIL** (D1 passes, but D3 AND D4 fail = ≥2 dims fail).

This is the "looks fine but ungradeable" trap: a present owner does not rescue absent provenance and drift. Two dims fail → FAIL, not WEAK.

---

**GOOD — Grade: PASS**

```
description: "JWT authentication & session service. Contract-first: services/auth/openapi.yaml is the SOT for its HTTP behavior; implementation must conform."
owner: "@platform-team"
drift_check: "spectral lint services/auth/openapi.yaml"
```

- D1 ✓ — "JWT authentication & session service" (concrete noun + role phrase).
- D2 ✓ — `@platform-team` in `owner` field.
- D3 ✓ — "Contract-first … openapi.yaml is the SOT" (why-authoritative basis present).
- D4 ✓ — `drift_check` populated with a lint command.
- **VERDICT: PASS**.

---

## 2. Library entry (derived from flask golden-set)

**WEAK — D3 missing — Grade: WEAK**

```
description: "Flask's public API surface — every name importable from `flask`; SemVer-governed, breaking changes gated by a major version."
owner: "@pallets"
drift_check: "diff the __init__ re-export set against CHANGES.rst; a removed/renamed export without a major bump is drift."
```

- D1 ✓ — "Flask's public API surface" + role phrase ("SemVer-governed…").
- D2 ✓ — `@pallets` in `owner` field.
- D3 ✗ — names the artifact but does not state why `src/flask/__init__.py` is authoritative (the "re-exports ARE the public contract" basis is absent).
- D4 ✓ — `drift_check` populated.
- **VERDICT: WEAK** (D1 passes; exactly one dim fails: D3). Accept + flag D3 for improvement.

---

**GOOD — Grade: PASS**

```
description: "Flask's public API surface — every name importable from `flask` (Flask, Blueprint, request, jsonify, url_for, the signals); SemVer-governed, breaking changes gated by a major version. The re-exports in src/flask/__init__.py ARE the public contract; anything not re-exported is internal."
owner: "@pallets"
drift_check: "diff the __init__ re-export set against the documented API + CHANGES.rst; a removed/renamed export without a major bump is drift."
```

- D1 ✓ — "Flask's public API surface" + role phrase.
- D2 ✓ — `@pallets` in `owner` field.
- D3 ✓ — "re-exports in src/flask/__init__.py ARE the public contract" (single-source authority basis present).
- D4 ✓ — `drift_check` populated.
- **VERDICT: PASS**.

---

## Verdict band summary

| Example | D1 | D2 | D3 | D4 | VERDICT |
|---------|----|----|----|----|---------|
| Service — `"auth service"` | ✗ | ✗ | ✗ | ✗ | FAIL |
| Service — `"JWT auth…"` + owner | ✓ | ✓ | ✗ | ✗ | FAIL (WEAK-trap) |
| Service — full PASS | ✓ | ✓ | ✓ | ✓ | PASS |
| Library — no D3 basis | ✓ | ✓ | ✗ | ✓ | WEAK |
| Library — full PASS | ✓ | ✓ | ✓ | ✓ | PASS |
