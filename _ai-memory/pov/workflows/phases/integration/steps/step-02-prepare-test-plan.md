---
name: 'step-02-prepare-test-plan'
description: 'Build the integration test plan from PRD requirements and architecture integration points'
nextStepFile: './step-03-dev-full-review.md'
---

# Step 2: Prepare Integration Test Plan

## STEP GOAL
Build the test plan that defines what must pass before integration is approved. Parzival builds this from PRD requirements and architecture integration points -- not delegated to an agent.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Integration scope document, PRD.md, architecture.md
- Limits: Parzival builds the test plan. Tests must be specific (not generic).

## MANDATORY SEQUENCE

### 1. Section 1: Functional Integration Tests
For each Must Have PRD feature in this milestone:
- Test primary user flow (happy path) with specific input and expected outcome
- Test edge case or error path
- Test integration with another feature in this milestone

### 2. Section 2: Integration Point Tests
For each internal integration point:
- Test data/call flow between components
- Test correct behavior at boundaries
- Test error case (what happens when a component fails)

For each external integration point:
- Test API call or service interaction
- Test handling of success and failure responses

### 3. Section 3: Non-Functional Tests
- Performance criteria from PRD with specific thresholds
- Security: authentication flow end-to-end, authorization boundaries, data protection
- Scale requirements if applicable

### 4. Section 4: Regression Tests
Existing functionality that must still work:
- Each existing feature with a specific test confirming it still works

### 5. Define Pass Criteria
All tests in Sections 1-4 must pass. Zero legitimate issues from DEV review. Architect cohesion check: CONFIRMED.

## CRITICAL STEP COMPLETION NOTE
ONLY when the test plan is complete with specific tests in all four sections, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All four test plan sections are populated
- Tests are specific (not generic)
- Every Must Have feature has test coverage
- Integration points have explicit boundary tests
- Pass criteria are defined

### FAILURE:
- Generic test descriptions ("verify it works")
- Missing test plan sections
- Must Have features without test coverage
- No pass criteria defined
