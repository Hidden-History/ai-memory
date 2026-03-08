---
name: 'step-03-build-ownership-map'
description: 'Build file ownership map, resolve conflicts, map cross-cutting concerns and contracts, present design for approval'
nextStepFile: './step-04-write-context-blocks.md'
---

# Step 3: Build Ownership Map

## STEP GOAL
Map every file and directory to exactly one owner at each level, resolve any conflicts, identify cross-cutting concerns, map contract chains (if applicable), and present the complete design for user approval.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Composition decisions from Step 2 (roster, pattern, models), project files
- Limits: Map ownership and get design approval — do not write context blocks yet

## MANDATORY SEQUENCE

### 1. Build Ownership Map

**For 3-tier — Manager-Level Ownership:**

| Manager Domain | Owns (May Modify) | Must Not Touch |
|----------------|-------------------|----------------|

**For 3-tier — Worker-Level Ownership Within Each Manager:**

| Worker | Owns (May Modify) | Must Not Touch |
|--------|-------------------|----------------|

**For 2-tier — Teammate Ownership:**

| Teammate | Owns (May Modify) | Must Not Touch |
|----------|-------------------|----------------|

### 2. Verify ZERO Overlap

Cross-check every file assignment at every level:
- No file appears under two managers
- No file appears under two workers within the same manager
- No file appears under workers in different managers
- For 2-tier: no file appears under two teammates

**If ANY overlap is found**: Do not proceed. Go to section 3.

### 3. Conflict Resolution

If overlap exists, resolve in this order:
1. Restructure tasks so one owner holds the shared file
2. If impossible within a domain, designate a single worker owner — other workers provide instructions via the manager
3. If overlap is cross-domain, restructure manager boundaries
4. If still unresolvable, STOP and present options to user

**Parallel Conflict Avoidance Strategies** (ranked by effectiveness):
1. **Git Worktree Isolation** (Highest) — Each worker gets independent filesystem copy
2. **Exclusive File Ownership** (High) — Enforced by the ownership map above
3. **Directory Partitioning** (High) — Workers own directories, not individual files
4. **Interface Contracts** (Medium) — For workers producing compatible code
5. **Merge-on-Green** (Medium) — Code merges to main only when all tests pass

**AVOID**: File locking — collapsed 20 agents to throughput of 2-3 in production testing.

### 4. Map Cross-Cutting Concerns

Identify which concerns span multiple domains and assign each to ONE owner:

| Concern | Applies? | Owner | Coordinates With | Specifics |
|---------|----------|-------|-----------------|-----------|
| URL/path conventions (trailing slashes, param style) | | | | |
| Response envelope format (flat vs nested wrappers) | | | | |
| Error response shape (status codes, error body format) | | | | |
| Streaming/SSE event format and storage semantics | | | | |
| Authentication token handling (header format, refresh) | | | | |
| Shared data types/enums (status values, role names) | | | | |
| Logging format and correlation IDs | | | | |
| UI accessibility (aria-labels for automated testing) | | | | |

**Assignment Rule**: Each concern gets ONE owner. That owner:
1. Defines the convention and includes it in every relevant context block
2. Communicates it to the lead for relay to other managers/teammates
3. Is responsible for verifying compliance during review

### 5. Map Contract Chain (Contract-First Build Only)

**Skip if not Contract-First Build pattern.**

Map which domains produce interfaces that others consume:

| Producer | Contract Type | Consumer(s) |
|----------|--------------|-------------|

### 6. Define Contract Spawn Order (Contract-First Build Only)

**Skip if not Contract-First Build pattern.**

Based on the chain, determine staggered spawn order:

| Phase | Agent(s) to Spawn | First Deliverable | Blocks |
|-------|-------------------|-------------------|--------|
| 1 | Most upstream | Publish contract to lead | Phase 2 |
| 2 | Middle | Receive verified contract, publish own | Phase 3 |
| 3 | Most downstream | Receive verified contract, implement | — |

**Rule**: Do NOT spawn a downstream agent until the lead has received AND verified the upstream contract.

**Contract Verification Checklist** (lead verifies before forwarding):
- URLs are exact, including trailing slashes
- Request body shapes are explicit with field names and types
- Response body shapes are explicit (exact JSON, not prose)
- All status codes documented (200, 201, 400, 404, 422, 500)
- Error response format specified (body shape for non-2xx)
- SSE/streaming event types listed with exact JSON (if applicable)
- Query parameter names and formats specified (if applicable)
- Authentication requirements stated (if applicable)
- No ambiguities remain — a developer could build to this without questions

### 7. Present Design for Approval

Present the complete design:
```
## Team Design

**Coordination Pattern**: [pattern]
**Structure**: [N] managers, [M] total workers (or [M] teammates for 2-tier)
**Models**: [model assignments]
**Plan Approval**: [Required/Not Required] — [reason]
**Delegate Mode**: [Recommended/Not Needed]

### Roster
[Table of managers/workers or teammates with domains and file sets]

### File Ownership Map
[Complete map with ZERO overlap verified]

### Cross-Cutting Concerns
[List or "None identified"]

### Contract Chain (if applicable)
[Chain + spawn order]

Approve this design?
```

Wait for user confirmation.

## CRITICAL STEP COMPLETION NOTE
ONLY when the team design is confirmed by the user and zero file overlap is verified, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every file is assigned to exactly one owner at each level
- Zero file overlap is verified and documented
- Cross-cutting concerns are identified and assigned
- Contract chain is mapped (if Contract-First)
- User approves the complete design

### FAILURE:
- Allowing file ownership overlap at any level
- Leaving files unassigned that will be modified
- Skipping the file ownership verification
- Not identifying cross-cutting concerns
- Proceeding without user approval of the design
