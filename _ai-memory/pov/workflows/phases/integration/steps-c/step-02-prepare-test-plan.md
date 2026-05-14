---
name: 'step-02-prepare-test-plan'
description: 'Build the integration test plan from PRD requirements and architecture integration points'
nextStepFile: './step-03-dev-full-review.md'
---

# Step 2: Prepare Integration Test Plan

**Progress: Step 2 of 8** — Next: DEV Full Review Pass

## STEP GOAL:

Build the test plan that defines what must pass before integration is approved. Parzival builds this from PRD requirements and architecture integration points -- not delegated to an agent.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Integration scope document, PRD.md, architecture.md
- Focus: Test plan creation only — do not begin agent dispatch or reviews
- Limits: Parzival builds the test plan. Tests must be specific (not generic).
- Dependencies: Integration scope document from Step 1 is required

- Build a complete four-section test plan — Parzival builds it, not an agent
**Behavioral Constraints:**
- FORBIDDEN to use generic test descriptions or delegate test plan creation
- Approach: Systematic coverage of all PRD features and integration points
- Every Must Have feature must have specific test coverage with defined thresholds

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Section 1: Functional Integration Tests

For each Must Have PRD feature in this milestone:
- Test primary user flow (happy path) with specific input and expected outcome
- Test edge case or error path
- Test integration with another feature in this milestone

---

### 2. Section 2: Integration Point Tests

For each internal integration point:
- Test data/call flow between components
- Test correct behavior at boundaries
- Test error case (what happens when a component fails)

For each external integration point:
- Test API call or service interaction
- Test handling of success and failure responses

---

### 3. Section 3: Non-Functional Tests

- Performance criteria from PRD with specific thresholds
- Security: authentication flow end-to-end, authorization boundaries, data protection
- Scale requirements if applicable

---

### 4. Section 4: Regression Tests

Existing functionality that must still work:
- Each existing feature with a specific test confirming it still works

---

### 5. Define Pass Criteria

All tests in Sections 1-4 must pass. Zero legitimate issues from DEV review. Architect cohesion check: CONFIRMED.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the test plan is complete with specific tests in all four sections, will you then read fully and follow: `{nextStepFile}` to begin the DEV full review pass.
