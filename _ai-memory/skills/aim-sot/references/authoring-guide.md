# aim-sot — Authoring Guide

Full decision procedure for capability C (categorize) and D (write + grade descriptions). Called from `SKILL.md → Authoring`.

## Contents

1. [Categorize the project](#1-categorize-the-project)
2. [Per-type canonical-parts checklists](#2-per-type-canonical-parts-checklists)
3. [Grade emit format](#3-grade-emit-format)
4. [Authoring loop and self-bias guard](#4-authoring-loop-and-self-bias-guard)
5. [Emit structure](#5-emit-structure)

---

## 1. Categorize the project

For EACH type below, check its signals against the repo. Record MATCH / NO-MATCH with the file(s) that triggered the match. Do not skip a type.

| # | Type | Primary signals (any-of) |
|---|------|--------------------------|
| 1 | **library** | `pyproject.toml` `[project]` w/ publish target; `package.json` `"exports"` + no app server; `Cargo.toml` `[lib]`; `go.mod` exported pkgs; `.nuspec`/`setup.py`; `CHANGELOG.md` + SemVer tags |
| 2 | **web app** | `next.config.*`, `vite.config.*`, `angular.json`, `astro.config.*`; route dir (`app/`, `pages/`, `routes/`); `public/` + `index.html`; build → static/SSR bundle |
| 3 | **service / API** | `openapi.yaml`/`.json`, `*.proto`, `schema.graphql`, `asyncapi.yaml`; server entrypoint; `Dockerfile` + deploy manifest; `service.datadog.yaml`/`catalog-info.yaml` |
| 4 | **monorepo** | `pnpm-workspace.yaml`, `nx.json`, `turbo.json`, `lerna.json`, Cargo/Go workspace, Bazel `WORKSPACE`; `packages/`/`apps/`/`libs/` with ≥2 child manifests; root `CODEOWNERS` with many path blocks |
| 5 | **CLI tool** | `package.json` `"bin"`, `[project.scripts]`, `cmd/` + cobra/clap/click; usage spec (`*.usage.kdl`, OpenCLI doc); `man/` pages; completion scripts |
| 6 | **data / ML pipeline** | `dags/`, `*.dbt`, `dbt_project.yml`, Airflow/Dagster/Prefect; `models/` + `MODEL_CARD.md`; `*.contract.yaml`; schema-registry refs; notebooks + training scripts |
| 7 | **infrastructure** | `*.tf` + backend/state config; `Pulumi.yaml`; `cdk.json`; `helm/Chart.yaml`; `kustomization.yaml`; `ansible/`; no application source as primary content |

**Resolution rule (apply mechanically):**
- 0 matches → ask the user; do not guess.
- 1 match → run that type's checklist.
- ≥2 matches → superset: run each matched type's checklist scoped to its detected sub-tree; also run the monorepo cross-cutting checklist for shared ownership/membership.

**Multi-label rule:** if ≥2 types match, the project is a superset. The monorepo checklist owns cross-cutting concerns (`CODEOWNERS` = ownership SOT; workspace manifest = membership SOT) that sub-type checklists do not own.

**Persistence + compute-tier prompt (superset / large stack):** for any superset or multi-service stack, enumerate each active backing datastore the system depends on (database, cache, vector store, object store, message broker) and each async worker / scheduler tier (even shared-image — it has its own scaling, queue, and schedule drift signals) as a first-class boundary. Use `kind: data` for logical data contracts and query surfaces; `kind: infrastructure` for the hosting layer (cluster, managed service). Use the selection contract (e.g., the env var that picks the live backend) as the `sot_location` pointer.

---

## 2. Per-type canonical-parts checklists

For each matched type, these are the parts whose SOT a developer should declare. Flag as a gap any expected part absent from the registry.

In each checklist's "kind / boundary" column, the first token is the `kind` field and the second is the `boundary_type` field; both must be drawn from the enums in §5. `owner` may be derived from a clearly-implied source (publish namespace, org/repo handle, or package manifest author field) when no literal `@handle` exists — cite the basis in `provenance_note`. D2 still requires a resolvable owner token on the row.

**Field-marker rows:** when the kind-column shows a parenthesised name (e.g. `(owner field)`) or a recognised bare field name (e.g. `links`), the canonical part is captured as a **field** on the relevant entry — not as a standalone `kind`-bearing entry. The "first token = `kind`, drawn from the enum" rule applies only to standalone-entry rows.

### 2.1 Library

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Public API surface** | `library` / component | export barrel / `__init__.py` / `lib.rs` / `index.ts` + API-baseline file if present | exports changed without a SemVer major/minor bump |
| **Version + release contract** | `decision` / concern | `CHANGELOG.md` + SemVer tag scheme | tag exists with no changelog entry; breaking change on a patch bump |
| **Build/publish config** | `library` / component | `pyproject.toml`/`package.json`/`Cargo.toml` packaging block | published artifact name/entrypoint differs from manifest |
| **Usage docs / examples** | `documentation` / concern | `README` "Usage" section, `examples/` | example imports a symbol no longer exported |

### 2.2 Web App

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Route/page map** | `application` / path | framework route dir (`app/`, `pages/`, `routes/`) | route file deleted but still linked/referenced |
| **Build & deploy target** | `application` / component | framework config + CI deploy workflow + host | deploy host/URL in docs ≠ actual deploy target |
| **Public env/config contract** | `decision` / concern | `.env.example` / config schema | new required env var not in `.env.example` |
| **Design-system / component source** | `library` / component | shared `components/`/design-token source | duplicated component diverges from canonical one |
| **API/backend dependency pointers** | `api` / concern | service(s) this app consumes (URL/spec) | consumed endpoint version bumped, client not updated |

### 2.3 Service / API

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Interface contract** | `api` / component | `openapi.yaml` / `.proto` / `schema.graphql` — contract-first SOT | implementation route/field diverges from spec |
| **Service implementation** | `service` / component | service dir + entrypoint | manifest/owner moved, entry stale |
| **Ownership + on-call** | (owner field) | `service.datadog.yaml`/`catalog-info.yaml` `owner`/contacts | owner group disbanded/renamed |
| **Runbook + dashboards** | links | `runbook_url`, `dashboard_url` | linked dashboard/runbook 404s |
| **Deploy + environments** | `infrastructure` / concern | deploy manifest + env URL table | env URL points to decommissioned host |

### 2.4 Monorepo (cross-cutting layer)

**Data/persistence note:** the persistence + compute-tier prompt in §1 applies to any multi-service superset, not only monorepos — declare active datastores as first-class boundaries regardless of topology.

**Inapplicable vs GAP (superset rule):** when a superset has no monorepo topology (no workspace manifest, no root `CODEOWNERS` with path blocks), the cross-cutting items below that have no declared artifact are **inapplicable (N/A)** — not GAPs. Flag a GAP only when the canonical part is expected for the detected topology but its SOT location is absent.

Run each sub-project's matched checklist, plus these cross-cutting parts:

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Workspace/package map** | `documentation` / concern | workspace manifest (`pnpm-workspace.yaml`, `nx.json`, `turbo.json`) | package added on disk, absent from workspace manifest |
| **Ownership map** | documentation / concern | `CODEOWNERS` / `OWNERS` | path block points at a renamed/empty team |
| **Shared/internal libs** | `library` / component | `libs/`/`packages/` internal packages | consumer imports a moved internal lib path |
| **Cross-package boundary rules** | `decision` / concern | Nx/`eslint` boundary config, ADR | import crosses a forbidden boundary |
| **Release/version strategy** | `decision` / concern | independent-vs-fixed versioning policy (lerna/changesets) | one package bumped, dependents not |

### 2.5 CLI Tool

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Command/flag surface** | `application` / component | usage spec (`*.usage.kdl`/OpenCLI) **or** arg-parser definition (cobra/clap/click) | help/docs list a flag the parser no longer defines |
| **Generated help / man / completions** | `documentation` / concern | generator output (man pages, completions) — derived from the spec | committed man page/completion out of sync with spec |
| **Config-file schema** | `decision` / concern | documented config schema (stable field names) | config key documented but unread by the tool |
| **Exit-code contract** | `decision` / concern | exit-code table in docs | exit code changed silently |

### 2.6 Data / ML Pipeline

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Source data contract** | `data` / concern | `*.contract.yaml`/schema-registry entry — schema + semantics + freshness SLA + PII flags + owner | upstream schema changed without contract bump |
| **Transformation logic** | `data` / component | dbt model / DAG task + its tests | transform changed, no test/contract update |
| **Output dataset + consumers** | `data` / concern | published dataset location + consumer list/dashboards | consumer reads a column the output dropped |
| **Model artifact + card** | `data` / component | model registry entry + `MODEL_CARD` (intended use, metrics, limitations, training data) | deployed model version ≠ card's documented version |
| **Lineage** | documentation / concern | lineage graph / pointers source→transform→output | lineage edge points at a deleted table |

### 2.7 Infrastructure

| Canonical part | kind / boundary | SOT-location signal | Drift signal |
|----------------|-----------------|---------------------|--------------|
| **Desired-state config** | `infrastructure` / component | IaC source (`*.tf`/Pulumi/CDK/Helm chart) — SOT for *intended* infra | resource created/changed outside IaC (config drift) |
| **State backend** | `infrastructure` / concern | remote state location (`backend` block / state bucket) — SOT for *current* infra | local/forked state diverges from remote |
| **Reusable modules + versions** | `library` / component | module registry entry + pinned version + README owner | consumer pins a yanked/old module version |
| **Environment topology** | `decision` / concern | env/workspace → account/region map | env points at a decommissioned account |
| **Secrets/policy references** | documentation / concern | secret-manager + policy (OPA/Sentinel) pointers | referenced secret/policy path removed |

---

## 3. Grade emit format

For each description under grade, answer in this exact order, one line each:

```
D1: yes/no — <the noun + role phrase found, or why absent>
D2: yes/no — <the owner token found, or "none on row">
D3: yes/no — <the authority basis phrase found, or "locates only">
D4: yes/no — <the drift signal found, or "none">
VERDICT: PASS | WEAK (name the one failing dim) | FAIL (name the failing dims)
```

Rationale-before-verdict is mandatory. The cited token must appear **verbatim** in the description or the named sibling field. Do not cite intent.

---

## 4. Authoring loop and self-bias guard

```
For each proposed entry:
1. Draft the description (or accept the user's).
2. GRADE: run D1–D4 per the rubric; emit the five lines above.
3. If FAIL: rewrite targeting the failed dimension(s) only — add the
   missing owner / authority-basis / drift-signal phrase; re-grade.
   Cap: 2 rewrite passes. If still FAIL: surface to the user with
   the failing dimensions named; do not loop further.
4. If WEAK: accept and flag the one missing dimension on the entry.
5. Never emit the registry while any entry is FAIL.
```

**Coverage check (after all entries graded):** re-scan every matched checklist and the discovered service/topology set. Flag any canonical part or running service with no covering entry as an explicit **GAP** — output the GAP list before the emit step. Do not silently under-cover.

**Schema-bind check (pre-emit):** verify every entry's `kind` ∈ {service, library, application, api, data, infrastructure, decision, documentation} and `boundary_type` ∈ {path, component, concern}. Any out-of-enum value → mark the entry **SCHEMA-INVALID**; it is NOT emittable. Surface SCHEMA-INVALID entries to the user; do not loop further.

**Self-bias guard:** the agent grades descriptions it drafted. Grade against the textual test only — the cited token must be literally present in the text or sibling field. Never award a dimension because you intended to include it. The "name the token you found" requirement is the anti-self-bias mechanism: if you cannot quote the owner/authority/drift token, the dimension is NO.

---

## 5. Emit structure

Categorizer emit (fixed shape):

```
matched_types: [<types>]
evidence: {<type>: [<triggering files>], ...}
resolution: single | superset
checklists_to_run: [<types>]
```

Per-entry grade block (fixed shape — emit one block per entry before emitting the registry):

```
entry: <id>
D1: yes/no — <cited token>
D2: yes/no — <cited token>
D3: yes/no — <cited token>
D4: yes/no — <cited token>
VERDICT: PASS | WEAK (<dim>) | FAIL (<dims>)
```

Never emit the registry until all entry VERDICT lines are PASS or WEAK. A single FAIL blocks the emit.

> **Bootstrap note:** a registry file requires a top-level `schema_version` field (e.g. `schema_version: "1.0"`). Always start from `templates/registry.yaml.template` — it supplies this field and the `entries` list skeleton.

### Registry-entry emit template (fixed shape)

```
# Required fields
id: <kebab-case-slug>
kind: <value>            # ∈ {service, library, application, api, data,
                         #     infrastructure, decision, documentation}
boundary_type: <value>   # ∈ {path, component, concern}
sot_location: <path, URL, or file#anchor>
owner: <@handle or team name>
description: <one-line: what it is · who owns it · why this location is SOT · how you'd know it went stale>

# Common optional fields (omit if not applicable)
provenance_note: <how/why this entry was added>
drift_check: <shell command or script path to verify currency>
last_verified: <YYYY-MM-DD>          # set to authoring date on first authoring
status: proposed | active | superseded
added_by: <@handle or 'aim-sot bootstrap'>
source_repo: <url>
docs_url: <url>
api_spec: <path or url>
ci_url: <url>
runbook_url: <url>
dashboard_url: <url>
adr_dir: <path>
links:                       # array of additional named pointers
  - {name: <label>, url: <url>, type: <optional classifier e.g. runbook|dashboard|ticket>}
```

**Enum glosses:**
- `kind`: `service` · `library` · `application` · `api` · `data` · `infrastructure` · `decision` · `documentation`
- `boundary_type`: `path` (directory or glob, CODEOWNERS-style) · `component` (named unit with a co-located manifest, Backstage-style) · `concern` (cross-cutting scope — an ADR, API contract, or shared platform concern)

**`sot_location` fragment syntax:** any entry whose SOT is a named section within a larger file may use `file#anchor` (e.g. `docker-compose.yaml#sandbox`); R1 resolves the file part.
