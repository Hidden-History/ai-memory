---
name: 'step-01-structure-decision'
description: 'Frame the decision with context, constraints, and generate options with tradeoffs'
nextStepFile: './step-02-present-decision.md'
---

# Step 1: Structure the Decision

## STEP GOAL
Frame the decision clearly: what needs to be decided, why now, what constraints apply, and what the viable options are with their tradeoffs.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User's decision topic, project constraints at `{constraints_path}/`, architecture decisions, relevant project files
- Limits: Structure the decision objectively -- do not pre-decide

## MANDATORY SEQUENCE

### 1. Frame the Decision
Document:
- **What needs to be decided**: Clear, specific statement
- **Why now**: What triggered this decision point
- **Impact of not deciding**: What happens if this is deferred
- **Decision scope**: What is and is not included in this decision

### 2. Identify Applicable Constraints
Check relevant constraint files at `{constraints_path}/` and document:
- Which constraints apply to this decision
- Any architectural decisions that are relevant
- Best practices with sources

### 3. Generate Options
Produce at least 2 viable options (3 preferred). Include "do nothing" if it is a viable option.

For each option, document:
- **Name**: Short descriptive label
- **Description**: What this option means concretely
- **Complexity**: Straightforward / Moderate / Significant / Complex
- **Risk**: Low / Medium / High
- **Reversibility**: Easy / Moderate / Difficult / Irreversible
- **Pros**: Benefits of this option
- **Cons**: Drawbacks of this option
- **Constraint compliance**: Which constraints it respects or violates

### 4. Build Comparison Matrix
Create a comparison across all options on these dimensions:
- Complexity
- Risk
- Reversibility
- Alignment with project goals
- Constraint compliance

### 5. Formulate Recommendation
Select the option Parzival recommends:
- Primary reasoning
- Secondary reasoning
- Confidence level: Verified / Informed / Inferred
- What Parzival does NOT know that might affect this decision

## CRITICAL STEP COMPLETION NOTE
ONLY when the decision is fully structured with all options and recommendation, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Decision is framed with clear context and trigger
- At least 2 options are generated with full tradeoff analysis
- Applicable constraints are identified and referenced
- Comparison matrix enables side-by-side evaluation
- Recommendation includes confidence level and unknowns

### FAILURE:
- Presenting only one option
- Omitting tradeoffs or constraint analysis
- Not stating confidence level
- Hiding unknowns that could affect the decision
- Pre-deciding by presenting options with obvious bias
