---
name: 'step-03-process-review-report'
description: 'Read the DEV review report in full, run WF-LEGITIMACY-CHECK on every issue, and determine next action'
nextStepFile: './step-04-build-correction-instruction.md'
exitStepFile: './step-07-exit-cycle.md'
---

# Step 3: Receive and Process Review Report

## STEP GOAL
When DEV returns the code review report, Parzival processes it systematically: read the full report, count and list every issue separately, run WF-LEGITIMACY-CHECK on each, and determine whether to proceed to corrections or exit the cycle.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: DEV's code review report, task requirements, implementation scope, all prior pass records if this is not the first pass
- Limits: Do not rely on DEV's severity assessments — Parzival classifies independently via WF-LEGITIMACY-CHECK

## MANDATORY SEQUENCE

### 1. Read the Full Report
- Read the entire review report — do not skim
- Count total issues reported
- List every issue separately — do not combine
- Note the location of each issue (file, function, line)
- Note DEV's severity assessment (but classify independently)

### 2. Handle Zero Issues Reported
If DEV review returns zero issues:
1. Verify this is plausible given the implementation scope
   - Simple task with clean implementation: accept
   - Complex task with no issues: question this
2. If the complexity warrants skepticism:
   - Request a second review pass with specific areas to re-examine
   - "Please re-examine [specific area] more closely — this level of complexity typically surfaces issues"
   - Wait for second pass and re-process from sequence item 1
3. If zero issues is accepted: proceed to {exitStepFile}

### 3. Run WF-LEGITIMACY-CHECK on Every Issue
For EACH issue in the review report:
- Trigger WF-LEGITIMACY-CHECK
- Classify: LEGITIMATE / NON-ISSUE / UNCERTAIN
- Record classification with basis and citation
- Assign priority if LEGITIMATE: CRITICAL / HIGH / MEDIUM / LOW
- Do NOT classify multiple issues together — each gets its own pass

### 4. Handle Uncertain Issues
When WF-LEGITIMACY-CHECK returns UNCERTAIN on an issue:
1. Trigger WF-RESEARCH-PROTOCOL immediately
2. Hold the uncertain issue — do not send DEV a fix instruction for it yet
3. Continue with all LEGITIMATE issues in parallel (DEV fixes known legitimate issues while research runs)
4. Once research resolves the uncertainty:
   - LEGITIMATE: add to next correction instruction
   - NON-ISSUE: document and exclude
5. If user escalation is needed: pause cycle, escalate, resume after decision
6. The cycle does not exit until all uncertain issues are resolved

### 5. Handle Pre-Existing Issues
When DEV surfaces pre-existing issues during a review pass:
1. Run WF-LEGITIMACY-CHECK on each pre-existing issue
2. If LEGITIMATE:
   - Add to current correction instruction with appropriate priority
   - Notify user immediately with: location, issue description, legitimacy basis, origin (pre-existing), priority, and action being taken
3. Pre-existing issues are fixed in the current cycle — not deferred
4. Count them in the cycle tracking record

### 6. Determine Next Action
- If zero legitimate issues after classification: proceed to {exitStepFile}
- If legitimate issues exist: proceed to {nextStepFile} to build correction instruction

## CRITICAL STEP COMPLETION NOTE
ONLY when all issues have been classified and a clear determination is made (corrections needed OR zero legitimate issues), load and read fully the appropriate next step file.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every issue in the report was read and classified individually
- WF-LEGITIMACY-CHECK ran for every single issue
- Uncertain issues triggered WF-RESEARCH-PROTOCOL
- Pre-existing issues were classified and included, not deferred
- Zero-issue reports on complex tasks were questioned

### FAILURE:
- Skipping classification for any issue
- Classifying multiple issues together in batch
- Relying on DEV's severity instead of independent classification
- Ignoring uncertain issues or guessing their classification
- Deferring pre-existing legitimate issues
- Accepting implausible zero-issue reports without scrutiny
