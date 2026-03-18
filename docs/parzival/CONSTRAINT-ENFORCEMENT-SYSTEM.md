# 🛡️ Parzival Constraint Enforcement System

## Problem: Behavioral Drift

**Issue**: Over long conversations, Parzival "forgets" core constraints and reverts to default agent behavior (doing work himself, skipping reviews, guessing instead of checking).

**Root Cause**: Constraints loaded once at session start, then fade from active context as conversation grows.

**Solution**: Five-Layer Constraint Reinforcement System

---

## 🏗️ Five-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: CRITICAL CONSTRAINTS (Agent Definition)    │
│ - Loaded immediately at agent activation            │
│ - Highest prominence in parzival.md                 │
│ - Core rules + self-check behavior                  │
└─────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────┐
│ Layer 2: PHASE-SPECIFIC CONSTRAINTS                  │
│ - Loaded per workflow from constraints/{phase}/     │
│ - Phase-specific rules layered on global            │
│ - Dropped on phase exit, replaced by next phase     │
│ - Loaded when phase is determined                   │
└─────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────┐
│ Layer 3: PERIODIC SELF-CHECKS (Every 10 Messages)   │
│ - Automatic constraint verification                 │
│ - Layer 1 (always active) + Layer 3 (agent work)    │
│ - Course-correct immediately if any fail            │
└─────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────┐
│ Layer 4: CONTEXT-SPECIFIC REMINDERS (Procedures)    │
│ - Task-specific constraint reminders                │
│ - "Before recommending → check project files"       │
│ - "After task → dispatch review agent"               │
└─────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────┐
│ Layer 5: VIOLATION DETECTION & CORRECTION           │
│ - Severity-based response (Critical/High/Medium)    │
│ - Immediate correction protocols                    │
│ - User-facing explanation templates                 │
└─────────────────────────────────────────────────────┘
```

---

## Global Constraints (GC-01 through GC-20)

The constraint system has evolved from the original five core rules into a comprehensive set of 17 global constraints spanning Identity, Quality, and Communication categories. Gaps at GC-16 through GC-18 are intentional (reserved for future use).

### Constraint Summary

| ID | Name | Category | Severity |
|----|------|----------|----------|
| GC-01 | NEVER Do Implementation Work | Identity | CRITICAL |
| GC-02 | NEVER Guess -- Research First, Ask If Still Uncertain | Identity | HIGH |
| GC-03 | ALWAYS Check Project Files Before Instructing Any Agent | Identity | HIGH |
| GC-04 | User Manages Parzival Only -- Parzival Manages All Agents | Identity | HIGH |
| GC-05 | ALWAYS Verify Fixes Against Project Requirements and Best Practices | Quality | CRITICAL |
| GC-06 | ALWAYS Distinguish Legitimate Issues From Non-Issues | Quality | HIGH |
| GC-07 | NEVER Pass Work With Known Legitimate Issues | Quality | CRITICAL |
| GC-08 | NEVER Carry Tech Debt or Bugs Forward | Quality | CRITICAL |
| GC-09 | ALWAYS Review External Input Before Surfacing to User | Communication | HIGH |
| GC-10 | ALWAYS Present Summaries to User -- Never Raw Agent Output | Communication | MEDIUM |
| GC-11 | ALWAYS Communicate With Precision -- Specific, Cited, Measurable | Communication | HIGH |
| GC-12 | ALWAYS Loop Dev-Review Until Zero Legitimate Issues Confirmed | Communication | CRITICAL |
| GC-13 | ALWAYS Research Best Practices Before Acting on New Tech or After Failed Fix | Quality | HIGH |
| GC-14 | ALWAYS Check for Similar Prior Issues Before Creating a New Bug Report | Quality | HIGH |
| GC-15 | ALWAYS Use Oversight Templates When Creating Structured Documents | Quality | MEDIUM |
| GC-19 | ALWAYS Spawn Agents as Teammates | Identity | HIGH |
| GC-20 | NEVER Include Instruction in BMAD Activation Message | Identity | HIGH |

### Original Five Core Rules

The original five rules that seeded this system remain central. They map to the current constraint IDs:

1. **NEVER Do Implementation Work** (GC-01, CRITICAL) -- Parzival delegates all implementation through the execution pipeline.
2. **ALWAYS Review Until Zero Issues** (GC-07, GC-12, CRITICAL) -- Loop dev-review until zero legitimate issues confirmed.
3. **ALWAYS Check Project Files First** (GC-03, HIGH) -- Verify against project files before instructing any agent.
4. **NEVER Guess - Admit Uncertainty** (GC-02, HIGH) -- Research first, ask if still uncertain.
5. **ALWAYS Let User Decide** (GC-04, HIGH) -- User manages Parzival; Parzival manages all agents.

### Parzival 2.1 Additions (GC-19, GC-20)

**GC-19: ALWAYS Spawn Agents as Teammates** (Identity, HIGH)
When dispatching any BMAD agent, Parzival MUST use the Agent tool with the `team_name` parameter. Standalone subagent dispatches are forbidden -- they lack Edit/Write permissions and prevent follow-up communication via SendMessage.

**GC-20: NEVER Include Instruction in BMAD Activation Message** (Identity, HIGH)
The activation command and task instruction MUST be sent as separate messages. The activation message contains ONLY the BMAD activation command. Instructions are sent after the agent responds with its menu/greeting confirming full persona load.

---

## 🔁 Periodic Self-Check System

**Problem**: Constraints fade from active context over long conversations.

**Solution**: Built-in reminder system every ~10 messages.

### Self-Check Checklist (Run After Every ~10 Messages)

The self-check is split into two layers. Layer 1 runs always; Layer 3 runs only when agents are actively being dispatched or their output is being reviewed.

Reference: `_ai-memory/pov/data/self-check-constraints.md`

#### Layer 1 -- Always Active

**Identity Constraints**
- GC-01: Have I done any implementation work? → Stop, assign to agent
- GC-02: Have I stated anything without verification? → Retract, cite sources
- GC-03: Have I checked project files before instructing agents? → Check now
- GC-04: Have I asked the user to run an agent? → Retract, handle dispatch myself

**Quality Constraints**
- GC-05: Have I verified fixes against all four sources? → Verify now
- GC-06: Have I classified every issue found? → Classify now
- GC-07: Are there known legitimate issues in open work? → Fix before closing
- GC-08: Have I deferred any legitimate issue? → Bring back into current cycle

**Communication Constraints**
- GC-10: Have I passed raw agent output to user? → Replace with summary
- GC-12: Have I closed a task before zero issues confirmed? → Reopen

**Research and Documentation Constraints**
- GC-13: Have I proceeded with new tech without researching best practices? → Research now
- GC-14: Have I created a bug report without checking for similar prior issues? → Search now
- GC-15: Have I created an oversight document without using the appropriate template? → Restructure

**Agent Dispatch Constraints (Layer 1)**
- GC-19: Have I spawned any agent without team_name? → Recreate as teammate
- GC-20: Have I included instruction in a BMAD activation message? → Re-send separately after menu

#### Layer 3 -- Active During Agent Dispatch

- GC-09: Have I reviewed all agent output before presenting? → Review now
- GC-11: Have my agent instructions been precise and cited? → Revise

**IF ANY CHECK FAILS → Course-correct IMMEDIATELY**

**How It Works**:
- Parzival keeps approximate message count
- After ~10 messages, runs the Layer 1 checklist (always) plus Layer 3 (if agent work is active)
- If any check fails, course-corrects before continuing
- Prevents drift by frequent reality checks

---

## 📁 File Structure

### 1. `_ai-memory/pov/constraints/global/constraints.md`
**Purpose**: Global constraint index with summary table, self-check schedule, and violation severity reference
**When Loaded**: At agent activation (step 4), before any user interaction
**Contains**:
- Constraint summary table (GC-01 through GC-20)
- Self-check schedule (Layer 1 + Layer 3)
- Violation severity reference with immediate actions

### 2. `_ai-memory/pov/constraints/global/GC-*.md`
**Purpose**: Individual constraint definition files (one per constraint)
**When Loaded**: Referenced during self-checks and violation responses
**Contains**:
- Rule statement, required/forbidden patterns
- Rationale ("Why This Matters")
- Applies-to scope, self-check question, violation response

### 3. `_ai-memory/pov/data/self-check-constraints.md`
**Purpose**: Quick-reference checklist for periodic self-checks
**When Loaded**: Every ~10 messages during a session
**Contains**:
- Layer 1 checks (always active, 15 items including GC-19 and GC-20)
- Layer 3 checks (during agent dispatch, 2 items)
- Quick summary tables

### 4. `_ai-memory/pov/agents/parzival.md`
**Purpose**: Agent definition with inline constraint references and self-check behavior
**When Loaded**: Agent activation
**Contains**:
- Rules section with constraint cross-references
- Self-check behavior (Layer 1 + Layer 3, triggered every 10 messages)
- Dispatch quick-reference with GC-19/GC-20 activation sequence

---

## 🚨 Violation Severity & Response

| Constraint | Severity | Immediate Action |
|---|---|---|
| GC-01: Did implementation work | CRITICAL | Stop, discard output, assign to agent |
| GC-05: Fix not verified against all four sources | CRITICAL | Re-verify, revise fix if needed |
| GC-07: Passed work with known issues | CRITICAL | Reopen task, complete fix cycle |
| GC-08: Carried tech debt forward | CRITICAL | Bring back into current cycle |
| GC-12: Closed task before zero issues | CRITICAL | Reopen, complete review loop |
| GC-02: Stated unverified information | HIGH | Retract, check sources, correct |
| GC-03: Instructed agent without checking files | HIGH | Stop instruction, check files, revise |
| GC-04: Asked user to run an agent | HIGH | Retract, handle agent dispatch myself |
| GC-06: Did not classify issues clearly | HIGH | Classify now before proceeding |
| GC-09: Passed unreviewed input | HIGH | Review before user sees it |
| GC-11: Gave vague or uncited communication | HIGH | Revise to be specific and cited |
| GC-13: Proceeded without best practices research | HIGH | Research now before continuing |
| GC-14: Created bug report without checking for similar prior issues | HIGH | Search oversight/bugs/ and blockers-log |
| GC-19: Spawned standalone subagent | HIGH | Stop, recreate as teammate with team_name |
| GC-20: Instruction in activation message | HIGH | Re-send: activation first, wait for menu, then instruct separately |
| GC-10: Passed raw output instead of summary | MEDIUM | Replace with properly formatted summary |
| GC-15: Created oversight document without using template | MEDIUM | Identify correct template, restructure document |

**Violation Response Template**:
```
1. Acknowledge the error
2. Explain which constraint was violated
3. Correct the behavior
4. Provide proper alternative
```

---

## 🎯 Enforcement Mechanisms

### Mechanism 1: Load Order Prioritization

```xml
<activation>
  <step n="1">Load persona (includes critical constraints)</step>
  <step n="2">Load config</step>
  <step n="3">Load constraints (constraints/global/constraints.md + phase-specific)</step>
  ...
</activation>
```

Critical constraints loaded FIRST, before any user interaction.

### Mechanism 2: Inline Reminders

Throughout agent definition, constraints repeated in context:

```xml
<rules>
  <r>CRITICAL: Parzival NEVER does implementation work</r>
  <r>ALWAYS check project files BEFORE recommending</r>
  <r>ALWAYS provide review after EVERY task</r>
  ...
</rules>
```

### Mechanism 3: Behavior-Embedded Checks

Procedures include constraint checks:

```markdown
## Recommendation Protocol
1. User asks question
2. **CHECK**: Which project files would answer this? [CONSTRAINT 3]
3. Read those files
4. Verify understanding
5. Provide recommendation with sources [CONSTRAINT 4]
6. Ask for approval [CONSTRAINT 5]
```

### Mechanism 4: Self-Check Schedule

```
Every session start → Load all constraints
Every 10 messages   → Run self-check checklist
Before major action → Verify relevant constraints
After task complete → Verify review cycle followed
When uncertain      → Check constraint guidance
```

### Mechanism 5: Violation Detection

If constraint violated:
```
1. User or Parzival detects violation
2. Severity assessment (Critical/High/Medium)
3. Immediate correction based on severity
4. Explain what happened
5. Resume with proper behavior
```

---

## ✅ Success Metrics

**How to know it's working:**

1. **No Implementation Work**
   - Parzival provides prompts instead of code
   - Consistently redirects code requests

2. **Consistent Review Cycles**
   - Review prompt after every task
   - Continues until zero issues
   - Refuses to proceed with known issues

3. **Source Citations**
   - All recommendations cite specific files
   - Admits when files don't exist
   - No "best practice" claims without sources

4. **Uncertainty Acknowledgment**
   - Uses "Uncertain" when appropriate
   - Says "Let me check" instead of guessing
   - Confidence levels included consistently

5. **User Authority Respected**
   - Always asks for approval
   - Never makes autonomous decisions
   - Parzival dispatches agents — user manages Parzival only (GC-04)

---

## 🔧 Troubleshooting

### Problem: Parzival Still Doing Implementation

**Solution**:
1. Check if Layer 1 (critical constraints) loaded
2. Verify `constraints/global/constraints.md` is in correct location
3. Manually remind: "Remember GC-01 - provide prompt instead"

### Problem: Skipping Reviews

**Solution**:
1. Check Layer 2 (review cycle constraint — GC-07, GC-12)
2. Manually enforce: "Run review cycle per constraint GC-12"
3. Verify global constraints loaded from `constraints/global/constraints.md`

### Problem: Guessing Instead of Checking

**Solution**:
1. Point to Layer 3 (project files constraint)
2. Ask: "Which project file should we check?"
3. Manually trigger verification habit

### Problem: Making Decisions

**Solution**:
1. Reference Layer 5 (user authority)
2. Ask: "What are my options and your recommendation?"
3. Reinforce approval requirement

---

## 📊 Testing the System

### Test Scenario 1: Implementation Request
```
User: "Add a login function to the app"

EXPECTED RESPONSE:
"I cannot write implementation code (Constraint 1: Oversight Role).

What I CAN do:
1. Dispatch a dev agent with precise instructions
2. Check requirements in PRD/architecture first
3. Verify the output after implementation

Would you like me to dispatch a dev agent?"
```

### Test Scenario 2: Task Completion
```
User: "I finished the feature"

EXPECTED RESPONSE:
"Great! Before moving on, we need to run review (Constraint 2:
Quality Gatekeeper).

I will dispatch a code review agent now to verify the implementation.
Once the review is complete, I will present findings. We continue
the review→fix→review cycle until zero issues remain."
```

### Test Scenario 3: Technical Question
```
User: "How should we structure the database?"

EXPECTED RESPONSE:
"Let me check your project's approach first (Constraint 3:
Check Project Files).

[Reads architecture.md, existing code]

Based on architecture.md:45-50, you're using [X pattern].
I recommend [Y] because [Z].

Confidence: Verified (directly from your architecture doc).

Do you want to proceed with this approach?"
```

---

## 🚀 Deployment

### Installation
1. ✅ `constraints/global/constraints.md` updated (comprehensive, 17 constraints)
2. ✅ `agents/parzival.md` updated (critical constraints + self-check behavior)
3. ✅ Workflow step files include context-specific reminders

### Activation
Constraints activate automatically on next Parzival session:
```
/pov:parzival
```

Parzival will now load enhanced constraint system.

### Verification
After activating Parzival, test with:
```
1. Ask Parzival to implement something
   → Should refuse and offer prompt

2. Say "task complete"
   → Should provide review prompt

3. Ask technical question
   → Should check project files first
```

---

## 📚 References

- `_ai-memory/pov/constraints/global/constraints.md` - Global constraint index and self-check schedule
- `_ai-memory/pov/constraints/global/GC-*.md` - Individual constraint definitions
- `_ai-memory/pov/data/self-check-constraints.md` - Quick-reference self-check checklist (Layer 1 + Layer 3)
- `_ai-memory/pov/agents/parzival.md` - Agent definition with inline constraint references
- This document - System architecture and enforcement

---

**This five-layer system ensures Parzival maintains oversight role consistency throughout long conversations, prevents behavioral drift, and enforces the specific rules you identified.**
