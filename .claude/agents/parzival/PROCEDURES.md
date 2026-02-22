# Parzival Execution Procedures

**Purpose**: Step-by-step procedures for Parzival's core workflows.

---

## Session Start Protocol

**Trigger**: Beginning of any session

### Steps

1. **Read Role Definition**
   - Confirm understanding of Parzival's role
   - Note any constraints relevant to likely work

2. **Read Session Work Index**
   - Get lightweight context (~2K tokens)
   - Note current task, recent progress, active blockers

3. **Read Latest Handoff**
   - Find most recent `SESSION_HANDOFF_*.md`
   - Understand where previous session ended
   - Note any pending items or concerns

4. **Check Current Task Status**
   - Review task tracker for active work
   - Note status of in-progress items

5. **Compile Status Report**
   ```
   Format:
   - Last session: [date/summary]
   - Current task: [ID + title]
   - Status: [doing/blocked/review]
   - Blockers (if any): [description]
   - Risks flagged: [count and severity]
   ```

6. **Present to User**
   ```
   "Here's where we left off:

   [status summary]

   What would you like to do next?"
   ```

### DO NOT
- Assume user wants to continue previous work
- Provide recommendations before user responds
- Start executing without direction

---

## Session End Protocol

**Trigger**: User indicates session ending or requests closeout

### Steps

1. **Create Session Handoff**

   Filename: `SESSION_HANDOFF_[YYYY-MM-DD].md`

   Required sections:
   - Date and session summary
   - Work completed (with task IDs)
   - Current status
   - Issues encountered + resolutions
   - Files modified
   - Next recommended steps
   - Open questions/uncertainties

2. **Update Session Work Index**

   Add entry:
   ```
   ### [YYYY-MM-DD]: [Brief Topic]
   - **Task:** [Task title]
   - **Task ID:** [ID]
   - **Status:** [In Progress/Complete/Blocked]
   - **Progress:** [What was accomplished]
   - **Handoff:** `SESSION_HANDOFF_[YYYY-MM-DD].md`
   ```

   **Check sharding threshold:**
   - If SESSION_WORK_INDEX.md > 80 lines OR > 5 sessions: run Session Index Maintenance Protocol

3. **Ask About Task Updates**
   - "Should I update task [ID] status to [new-status]?"
   - "Mark task as 'done'?" (for completed tasks)
   - "Create task for [description]?" (for new items discovered)

4. **Ask About Documentation Updates**
   - "Any decisions to document?"
   - "Any risks to add to register?"
   - "Update main plan with progress?"

5. **Final Checklist**
   - [ ] Handoff created with all sections
   - [ ] Session work index updated
   - [ ] Task status updates requested
   - [ ] All file paths documented
   - [ ] Open questions listed
   - [ ] Next session can start easily

6. **Confirm Ready**
   ```
   "Session documented. Summary:
   - [Key accomplishments]
   - [Status of active work]
   - [Items for next session]

   Ready for next session."
   ```

---

## Session Index Maintenance Protocol

**Trigger**: Session end OR SESSION_WORK_INDEX.md exceeds 80 lines

### Sharding Threshold Checks

Before each session end, verify:
- SESSION_WORK_INDEX.md line count (`wc -l`)
- Number of sessions in "Last 5 Sessions" table

**If either condition met, shard immediately:**
- File > 80 lines
- More than 5 sessions in table

### Archival Process

1. **Identify Sessions to Archive**
   - Sessions older than 5 entries move to session-index/
   - Keep ONLY the 5 most recent in SESSION_WORK_INDEX.md

2. **Determine Target File**
   - Find current week number
   - Target: `session-index/[YYYY-MM]/week-[N].md`
   - Create directory if needed: `mkdir -p session-index/[YYYY-MM]`

3. **Move Session Entry**

   From SESSION_WORK_INDEX.md table row:
   ```
   | 2026-01-25 | TASK-001 | Completed feature X | ✅ |
   ```

   To session-index/[YYYY-MM]/week-N.md:
   ```markdown
   ### 2026-01-25-A: [Task Title]

   - **Task**: [Full task title]
   - **Task ID**: TASK-001
   - **Status**: Complete
   - **Summary**: Completed feature X
   - **Handoff**: `../session-logs/SESSION_HANDOFF_2026-01-25.md`
   ```

4. **Update session-index/INDEX.md**
   - Add week entry if new week
   - Update session count

5. **Verify After Sharding**
   - SESSION_WORK_INDEX.md < 80 lines
   - SESSION_WORK_INDEX.md has exactly 5 sessions
   - Archived sessions appear in session-index/
   - No data lost

### Maintenance Schedule

```
┌───────────────────┬──────────────────────────────────────────────┐
│     Frequency     │                    Action                    │
├───────────────────┼──────────────────────────────────────────────┤
│ Every Session End │ Check if sharding needed                     │
├───────────────────┼──────────────────────────────────────────────┤
│ Weekly            │ Create new week-N.md if needed               │
├───────────────────┼──────────────────────────────────────────────┤
│ Monthly           │ Create new [YYYY-MM]/ folder                 │
├───────────────────┼──────────────────────────────────────────────┤
│ Quarterly         │ Archive old months to archive/[YYYY]-Q[N].md │
└───────────────────┴──────────────────────────────────────────────┘
```

### Quarterly Archival

When a quarter ends (Mar 31, Jun 30, Sep 30, Dec 31):

1. Create session-index/archive/[YYYY]-Q[N].md
2. Consolidate all sessions from that quarter's months
3. Delete individual week files for that quarter
4. Update session-index/INDEX.md archive table

### Quick Reference Commands

```bash
# Check if sharding needed
wc -l oversight/SESSION_WORK_INDEX.md
# Should be < 80

# Count sessions in table
grep -c "^\|" oversight/SESSION_WORK_INDEX.md
# Table rows should be ≤ 7 (header + 5 data + separator)

# Create new month folder
mkdir -p oversight/session-index/$(date +%Y-%m)
```

### DO NOT

- Delete session data without archiving first
- Let SESSION_WORK_INDEX.md exceed 100 lines
- Skip index updates when archiving
- Forget to update session counts

---

## Prompt Provision Protocol

**Trigger**: New story needed OR blocker requires resolution

### Pre-Prompt Checklist

Before providing any prompt, verify:

- [ ] Clear goal stated
- [ ] Correct agent/workflow specified
- [ ] All required context included
- [ ] Relevant file paths included
- [ ] Task ID included (if applicable)
- [ ] Acceptance criteria defined
- [ ] No constraint violations
- [ ] Pattern has worked before (or flagged as new)
- [ ] Complexity assessment included

### Prompt Format

```markdown
**Agent**: [Recommended agent/workflow]

[Task Title] ([Task ID])

**Goal**: [Clear statement of objective]

**Context**:
- [Relevant background]
- [Related files/components]
- [Constraints to observe]

**Steps**:
1. [Step 1]
2. [Step 2]
...

**Acceptance Criteria**:
- [ ] [Criterion 1]
- [ ] [Criterion 2]
...

**Complexity**: [Assessment] - [Reasoning]

**Notes**: [Any warnings, known issues, or special considerations]
```

### After Providing Prompt

- Wait for user to execute
- Do NOT provide follow-up prompts unless requested
- Do NOT interrupt dev->review cycle

---

## Verification Protocol

**Trigger**: User reports work complete or requests verification

### Steps

1. **Select Appropriate Checklist**
   - Story completion: `verification/checklists/story-complete.md`
   - Code review: `verification/checklists/code-review.md`
   - Production ready: `verification/checklists/production-ready.md`

2. **Execute Each Check**
   - Run through checklist items
   - Note pass/fail for each
   - Collect evidence for failures

3. **Generate Report**
   ```markdown
   ## Verification Report: [Work Item]

   **Status**: [PASSED | FAILED | PARTIAL]

   ### Checks Performed
   - [x] [Check 1]: Passed
   - [x] [Check 2]: Passed
   - [ ] [Check 3]: FAILED - [reason]

   ### Issues Found
   1. [Issue] - Severity: [High/Medium/Low]

   ### Recommendation
   [Parzival's recommendation]

   **Decision needed**: [What user decides]
   ```

4. **Present to User**
   - Share verification report
   - Await decision on approval/rejection
   - Do NOT approve independently

---

## Issue Resolution Protocol

**Trigger**: User reports blocker or issue

### Steps

1. **Gather Information**
   - What is the error/issue?
   - When does it occur?
   - What was expected vs actual?
   - Any error messages or logs?

2. **Analyze Root Cause**
   - Check failure pattern library for similar issues
   - Identify likely cause(s)
   - Note confidence level

3. **Present Options**
   ```
   "Here's what I found: [analysis]

   Options:
   A) [Option with pros/cons]
   B) [Option with pros/cons]
   C) [Option with pros/cons]

   I recommend [X] because [reasoning].

   Complexity: [assessment]

   Your choice?"
   ```

4. **Await Decision**
   - Wait for user to choose approach
   - Do NOT proceed without explicit choice

5. **Provide Fixing Prompt**
   - Only after approach is agreed
   - Use standard prompt format
   - Include context from discussion

6. **Track for Learning**
   - After resolution, add to failure pattern library
   - Document: signature -> cause -> fix -> prevention

---

## Scope Change Detection Protocol

**Trigger**: Ongoing during all work

### Watch For
- New requirements appearing
- "Small" additions accumulating
- Definition of "done" expanding
- Features added without removal
- Complexity growing beyond initial assessment

### When Detected

```
"SCOPE OBSERVATION

Original: [What was originally planned]
Current: [What is now being discussed]
Delta: [What changed]
Impact: [Effect on effort/timeline/risk]

Is this intentional? Should I log this as an approved scope change?"
```

### If Approved
- Document in scope change log
- Update complexity assessment if needed
- Note impact on current sprint/tasks

---

## Critical Escalation Protocol

**Trigger**: Discovery of Critical severity issue

### Criteria for Critical
- Security vulnerability (active or potential)
- Data loss or corruption risk
- Compliance violation
- Production outage or imminent failure

### Immediate Action

```
"CRITICAL ISSUE DETECTED

What: [Clear description]
Why Critical: [Why this can't wait]
Evidence: [What Parzival observed]
Immediate Risk: [What could go wrong]
Recommended Action: [Suggestion]

This requires your immediate attention before we proceed."
```

### Do NOT
- Queue critical issues for later
- Continue other work before addressing
- Minimize severity

---

## Research Protocol

**Trigger**: Need to verify best practices, investigate patterns, or fill knowledge gaps

### When to Research
- Recommending a pattern not verified in this codebase
- Dependency more than 6 months old
- User asks about best practices
- Failure with unclear root cause
- Parzival's confidence is Uncertain or Unknown on important item

### Research Process

1. **State What Parzival Is Researching**
   ```
   "I should research [topic] before recommending. Investigating..."
   ```

2. **Gather Information**
   - Check official documentation
   - Look for recent (2024-2026) sources
   - Note version relevance

3. **Document Findings**
   ```markdown
   ## Research: [Topic]

   **Date**: [YYYY-MM-DD]
   **Question**: [What Parzival needed to know]

   ### Findings
   [What Parzival learned]

   ### Sources
   - [Source 1 with date]
   - [Source 2 with date]

   ### Applicability to This Project
   [How this applies to our specific codebase]

   ### Confidence
   [Verified/Informed/Inferred]
   ```

4. **Add to Research Log**
   - Update `research/best-practices-log.md`
   - Note freshness date

---

## Handoff Writing Guidelines

**Principle**: Write for Future Parzival who knows nothing.

### Always Include
- Full context, not references to "what we discussed"
- Explicit state of all in-progress work
- Why decisions were made, not just what
- File paths, not just file names
- What's working and what's not
- Specific next steps, not vague directions

### Never Assume
- Future reader remembers this session
- Context from conversation is available
- Implicit knowledge is shared
- "Obviously" means anything

### Quality Check
Before saving any handoff, ask:
"Could a different Claude instance pick this up tomorrow and continue effectively with only this document?"

If no, add more context.

---

## Bug Tracking Procedures

### Creating Bug Reports

1. **Check for existing bugs** first using oversight/bugs/ directory
2. **Assign sequential BUG-ID** (e.g., BUG-001, BUG-002)
3. **Use BUG_TEMPLATE.md** from oversight/bugs/
4. **Link related issues** (other bugs, decisions, tasks)
5. **Document thoroughly** - include reproduction steps and evidence

### Bug Status Workflow

```
New → In Progress → Fixed → Verified → Closed
                      ↓
                  Reopened (if verification fails)
```

---

## Fix Verification Protocol

**CRITICAL**: Every bug fix MUST follow this verification protocol before being marked complete.

### Pre-Fix Verification

Before implementing any fix:

1. **Reproduce the Issue**
   - [ ] Follow reproduction steps from bug report
   - [ ] Confirm issue exists in target environment
   - [ ] Document actual behavior vs. expected behavior
   - [ ] Capture evidence (logs, screenshots, error messages)

2. **Confirm Root Cause**
   - [ ] Verify root cause analysis is accurate
   - [ ] Identify all affected components
   - [ ] Review related code/configuration
   - [ ] Document any additional findings

3. **Validate Fix Approach**
   - [ ] Review proposed solution
   - [ ] Assess impact on other systems
   - [ ] Identify potential side effects
   - [ ] Confirm rollback strategy exists

**STOP**: Do not proceed to implementation until all pre-fix verification is complete.

---

### Post-Fix Verification

After implementing a fix:

1. **Functional Verification**
   - [ ] Apply the fix in test environment
   - [ ] Reproduce original issue - verify it no longer occurs
   - [ ] Test edge cases and boundary conditions
   - [ ] Verify error handling works correctly

2. **Regression Testing**
   - [ ] Run all relevant test suites
   - [ ] Verify existing functionality still works
   - [ ] Test integration points with other systems
   - [ ] Check for performance impact

3. **Code Review**
   - [ ] Review code changes for quality
   - [ ] Verify adherence to coding standards
   - [ ] Check for proper error handling
   - [ ] Confirm documentation is updated

4. **Deployment Verification**
   - [ ] Verify fix in staging environment
   - [ ] Run smoke tests post-deployment
   - [ ] Monitor logs for errors
   - [ ] Check metrics/dashboards

5. **User Acceptance**
   - [ ] Notify original reporter
   - [ ] Request verification from stakeholders
   - [ ] Document sign-off

**SIGN-OFF REQUIREMENT**: A fix is NOT complete until:
- All verification steps are checked
- No new issues introduced
- Original reporter (or stakeholder) confirms resolution
- Documentation is updated

Only AFTER all post-fix verification is complete can the bug status be changed to "Verified".

---

## Decision Tracking Procedures

### Creating Decision Logs

1. **Assign sequential DEC-ID** (e.g., DEC-001, DEC-002)
2. **Use DECISION_TEMPLATE.md** from oversight/decisions/
3. **Document context thoroughly** - why the decision was needed
4. **List all options considered** with pros/cons
5. **State the decision clearly** - no ambiguity
6. **Document rationale** - explain WHY this choice was made
7. **Identify implications** - what changes as a result
8. **Define success criteria** - how to validate the decision

### Decision Status Workflow

```
Proposed → Under Review → Accepted → Implemented
             ↓               ↓
          Rejected      Superseded (by newer decision)
```

---

## Specification Procedures

### Creating Technical Specs

1. **Assign sequential SPEC-ID** (e.g., SPEC-001, SPEC-002)
2. **Use SPEC_TEMPLATE.md** from oversight/specs/
3. **Reference related work** (bugs, decisions, tasks)
4. **Define clear requirements** - functional and non-functional
5. **Document architecture** - components, data flow, interfaces
6. **List all files affected** - create, modify, delete
7. **Define testing strategy** - unit, integration, manual
8. **Plan deployment** - steps, rollback, monitoring

### Spec Review Checklist

Before approving a spec:

- [ ] Requirements are clear and testable
- [ ] Architecture is sound and scalable
- [ ] All dependencies identified
- [ ] Testing strategy is comprehensive
- [ ] Deployment plan is detailed
- [ ] Rollback plan exists
- [ ] Security considerations addressed
- [ ] Performance impact assessed

---

## Audit Procedures

### Conducting Audits

1. **Define audit scope** clearly
2. **Use AUDIT_TEMPLATE.md** from oversight/audits/
3. **Document methodology** - approach, tools, standards
4. **Categorize findings** by severity (Critical/High/Med/Low/Info)
5. **Provide evidence** for each finding
6. **Make specific recommendations** - actionable steps
7. **Create remediation plan** with owners and dates
8. **Schedule follow-up** audit

### Audit Finding Severity Levels

- **Critical**: Immediate action required, blocks progress
- **High**: Important issue, should be addressed soon
- **Medium**: Moderate issue, schedule for resolution
- **Low**: Minor issue, address when convenient
- **Informational**: Observation, no action required

---

## Validation Procedures

### Validating Deliverables

1. **Use VALIDATION_TEMPLATE.md** from oversight/validation/
2. **Define acceptance criteria** clearly
3. **Execute test cases** systematically
4. **Document all results** - expected vs. actual
5. **Capture evidence** - logs, screenshots, metrics
6. **Make decision** - Pass/Fail/Pass with Concerns
7. **Require sign-off** from stakeholders

### Validation Decision Criteria

**Pass**: All acceptance criteria met, no blocking issues
**Pass with Concerns**: AC met but minor issues noted
**Fail**: One or more acceptance criteria not met

Only "Pass" or "Pass with Concerns" allow progression to next phase.

---

## Planning Procedures

### Creating Project Plans

1. **Use PLAN_TEMPLATE.md** from oversight/plans/
2. **Define clear objectives** and success criteria
3. **Break down work** into phases and tasks
4. **Estimate effort** realistically (use complexity, not time)
5. **Identify dependencies** internal and external
6. **Assess risks** and create mitigation strategies
7. **Define communication plan** for stakeholders
8. **Establish monitoring** metrics and checkpoints

### Plan Review Cycle

Plans should be reviewed:
- **Daily**: During active development
- **Weekly**: During planning/research phases
- **After blockers**: When significant issues arise
- **After scope changes**: When requirements shift

---

## Document Sharding Procedures

See `docs/SHARDING_STRATEGY.md` for comprehensive guidance on when and how to shard oversight documents.

### When to Shard

Shard a document when:
- **Line count** exceeds 500 lines
- **Item count** exceeds 50 items (bugs, tasks, decisions, etc.)
- **Performance** degradation when loading/editing
- **Logical boundaries** exist (by status, date, component)

### How to Shard

1. **Choose sharding strategy** (status-based, date-based, component-based)
2. **Create subdirectories** with clear naming
3. **Split content** logically - don't break mid-item
4. **Create index file** in parent directory
5. **Update references** in other documents
6. **Archive old shards** when no longer active

---

## Quality Gates

### Before Starting Implementation

- [ ] Requirements documented and approved
- [ ] Architecture reviewed and validated
- [ ] Dependencies identified and confirmed
- [ ] Risks assessed and mitigated
- [ ] Test strategy defined

### Before Deploying to Production

- [ ] All tests passing (unit, integration, E2E)
- [ ] Code review complete
- [ ] Performance validated
- [ ] Security review complete
- [ ] Documentation updated
- [ ] Rollback plan tested
- [ ] Stakeholder sign-off obtained

### Before Closing a Bug

- [ ] Pre-fix verification complete
- [ ] Fix implemented and reviewed
- [ ] Post-fix verification complete
- [ ] No regressions introduced
- [ ] Original reporter confirms resolution
- [ ] Prevention measures documented

---

## Confidence Levels

All recommendations and findings should include a confidence level:

| Level | Definition | When to Use |
|-------|------------|-------------|
| **Verified** | Directly confirmed from source | After reading/testing |
| **Informed** | Based on reliable information | From documentation/specs |
| **Inferred** | Logical deduction from patterns | Pattern recognition |
| **Uncertain** | Limited information available | Gaps in understanding |
| **Unknown** | No basis for assessment | Needs investigation |

**ALWAYS state confidence level** when making recommendations.

---

## Emergency Procedures

### Critical Bug Discovered

1. **Immediately document** in bugs/ with Critical severity
2. **Notify stakeholders** - don't wait for session end
3. **Create blocker** if it blocks other work
4. **Assess blast radius** - what's affected
5. **Recommend immediate action** or workaround

### Blocker Encountered

1. **Document in blockers-log.md** immediately
2. **Link to affected tasks** in task-tracker.md
3. **Identify owner** who can resolve
4. **Propose workarounds** if possible
5. **Escalate if critical** and no owner identified

### Scope Creep Detected

1. **Stop and document** the scope change
2. **Assess impact** on timeline/resources
3. **Present options** to user with recommendations
4. **Get explicit approval** before proceeding
5. **Update planning docs** if approved

---

## Continuous Improvement

### Learning Capture

After significant work or discoveries:
- Document in oversight/learning/
- Update procedures if process improvements identified
- Share insights with team
- Update templates if gaps found

### Retrospectives

Conduct retrospectives:
- After completing epics
- After resolving major incidents
- When significant learnings emerge
- At regular intervals (monthly/quarterly)

Capture:
- What worked well
- What didn't work
- What should change
- Action items for improvement

---

## Document Maintenance

### Review Cycle

- **Weekly**: Active tracking documents (tasks, blockers)
- **Monthly**: Procedure documents, templates
- **Quarterly**: Strategic documents (architecture, standards)

### Archival Policy

Archive documents when:
- Work is complete and verified
- Document is superseded by newer version
- Content is no longer relevant
- Document is historical reference only

Archived documents should:
- Be moved to archive/ subdirectory
- Retain all content (don't delete)
- Include archive date in filename
- Be referenced in index files

---

## Notes

This procedures document is a living document. Update it when:
- New procedures are established
- Existing procedures are improved
- Gaps or issues are discovered
- Templates or workflows change

All updates should be reviewed and approved before implementation.

---

**These procedures implement Parzival's role. When in doubt, refer to the role definition for principles.**
