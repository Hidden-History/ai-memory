# Skill Evaluation

Phase 5 criteria for evaluating whether best practices warrant a reusable skill.

---

## Skill-Worthiness Criteria

### Decision Rule

```
Recommend skill if:
  (Process-oriented AND Reusable)
  OR
  (Stack Pain Point: Agent Failed Before OR Many Config Options)
```

### Criteria Table

| Criterion | Question | Weight |
|-----------|----------|--------|
| **Process-oriented** | Has 3+ distinct steps? | Required* |
| **Reusable** | Applies to common/recurring tasks? | Required* |
| **Complex** | Non-trivial to remember correctly? | Nice-to-have |
| **Consistency-critical** | Should be done the same way each time? | Nice-to-have |
| **Stack Pain Point** | Agents have failed at this before OR many config options? | Alternate trigger |

*Required unless Stack Pain Point applies

### Stack Pain Point Trigger

Skills should be created for **core stack technologies** when:

1. **Agent Failure History**: Agents have previously made mistakes with this technology
2. **Many Configuration Options**: Technology has numerous valid choices requiring guidance
3. **Decision Tree Required**: Choosing correctly requires evaluating multiple factors

### Stack Pain Point Examples

| Technology | Skill? | Reason |
|------------|--------|--------|
| Prometheus metrics | **Yes** | 4 metric types, naming rules, cardinality traps |
| Grafana panels | **Yes** | 20+ viz types, agents pick wrong ones |
| Docker Compose | Maybe | If agents misconfigure services |
| Python logging | No | Simple, well-known patterns |
| Git commands | No | Claude already knows git well |

### Scoring

**Recommend skill if:**
- (Process-oriented = Yes AND Reusable = Yes) OR Stack Pain Point = Yes

**Skip skill creation if:**
- No criteria met AND no pain point identified

---

## Documentation Override Rule

**When comprehensive documentation already exists**, apply this override:

```
IF existing_bp_files >= 3 AND newest_file < 6_months_old:
  THEN recommend "documentation sufficient"
  UNLESS user explicitly requests skill creation
```

### Override Criteria

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Multiple BP files on topic | >= 3 files | Triggers override consideration |
| Documentation is fresh | < 6 months old | Override applies |
| Documentation is stale | > 6 months old | Override does NOT apply |
| User requests skill | Explicit request | Override is bypassed |

### When Override Applies

Report to user:
```
Existing documentation found:
- BP-XXX: [title] (YYYY-MM-DD)
- BP-YYY: [title] (YYYY-MM-DD)
- BP-ZZZ: [title] (YYYY-MM-DD)

These [N] best practice documents provide comprehensive coverage.
Recommendation: Documentation sufficient - no skill needed.

Override available: Say "create skill anyway" if you want a skill despite existing docs.
```

### When Override Does NOT Apply

- Fewer than 3 BP files exist
- Existing files are > 6 months old
- User explicitly requests skill creation
- Topic has significant Stack Pain Point AND no decision tree in existing docs

---

## When NOT to Create a Skill

| Situation | Example | Why Skip |
|-----------|---------|----------|
| **Single fact** | "Use port 6333 for Qdrant" | Just a convention |
| **One-off task** | "Migrate this specific schema" | Won't repeat |
| **Simple rule** | "Use snake_case for Python" | Trivial, 1 step |
| **Well-known tool** | Git, curl, basic Linux | Claude knows these |

---

## Evaluation Workflow

### Step 1: Analyze Findings

- How many distinct steps?
- Is this recurring?
- **Is this a stack technology with many options?**
- **Have agents failed at this before?**

### Step 2: Score Against Criteria

```
Skill-Worthiness Assessment:
Process-oriented: Yes/No
Reusable: Yes/No
Stack Pain Point: Yes/No ([reason])
Decision: RECOMMEND / SKIP
```

### Step 3: User Prompt (if skill-worthy)

```
This best practice defines a reusable [N]-step workflow for [topic].

**Why this warrants a skill:**
- Process-oriented: [N] distinct steps
- Stack Pain Point: [many options / agents fail at this]

Would you like me to create a skill?
[Yes - Create skill] [No - Keep as documentation only]
```

---

## Context Handoff Format

```yaml
topic: "The research topic"
findings: |
  [The researched best practices]
workflow_steps:
  - "Step 1"
  - "Step 2"
source_ref: "BP-XXX"
skill_worthiness:
  process_oriented: true
  reusable: true
  stack_pain_point: true
  pain_point_reason: "reason"
```

---

## User Override

User can request skill creation even when criteria not met.
