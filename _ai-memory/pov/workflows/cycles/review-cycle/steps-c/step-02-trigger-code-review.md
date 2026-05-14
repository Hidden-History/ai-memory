---
name: 'step-02-trigger-code-review'
description: 'Instruct the DEV agent to run a thorough code review on the verified implementation'
nextStepFile: './step-03-process-review-report.md'
codeReviewTemplate: '{workflows_path}/cycles/review-cycle/templates/code-review-instruction.md'
---

# Step 2: Trigger DEV Code Review

**Progress: Step 2 of 7** — Next: Receive and Process Review Report

## STEP GOAL:

Once implementation is verified as complete, Parzival instructs the DEV agent to run a thorough code review covering correctness, security, architecture compliance, standards compliance, requirements compliance, edge cases, error handling, pre-existing issues, test coverage, and future risk.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The verified implementation output, task requirements (PRD, architecture, standards, story criteria), list of files changed or created
- Focus: Code review instruction building and dispatch — do not process results yet
- Limits: Parzival does not run the code review himself — DEV runs the review
- Dependencies: Verified complete implementation from step-01

- Build comprehensive code review instruction using {codeReviewTemplate}
**Behavioral Constraints:**
- FORBIDDEN to run the code review yourself — DEV runs the review
- Approach: Complete instruction in one send — no piecemeal delivery
- Wait for complete review report before loading next step

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Build Code Review Instruction

Using {codeReviewTemplate}, construct the code review instruction with:
- All files modified or created (IMPLEMENTATION SCOPE)
- Task/story reference
- Specific requirements to review against (PRD section, architecture section, standards section, story criteria)
- Full review checklist: correctness, security, architecture compliance, standards compliance, requirements compliance, edge cases, error handling, pre-existing issues, test coverage, future risk

---

### 2. Send Code Review Instruction to DEV

- Send the complete instruction to the DEV agent
- Do not add conversational preamble
- Do not abbreviate or summarize the instruction
- Send once and wait for DEV to complete

---

### 3. Wait for DEV Review Report

- Wait for DEV to return a complete review report
- The report must cover every area in the review checklist
- The report must contain either specific issues with location/description/severity or an explicit "Code review complete -- zero issues found" statement

## CRITICAL STEP COMPLETION NOTE

ONLY when DEV returns a complete code review report, load and read fully {nextStepFile}
