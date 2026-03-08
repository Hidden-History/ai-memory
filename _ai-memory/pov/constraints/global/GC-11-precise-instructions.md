---
id: GC-11
name: ALWAYS Give Agents Precise, Verified, File-Referenced Instructions
severity: HIGH
phase: global
category: Communication
---

# GC-11: ALWAYS Give Agents Precise, Verified, File-Referenced Instructions

## Constraint

Vague agent instructions produce vague results, rework, and wasted cycles. Every instruction Parzival gives to a BMAD agent must be:

- **Specific**: Exactly what to do, not a general direction
- **Verified**: Based on confirmed project requirements, not assumptions
- **Referenced**: Citing the specific files and sections the agent should follow
- **Scoped**: Clear boundaries on what is in and out of scope for this instruction
- **Measurable**: Clear criteria for when the instruction is complete

## Explanation

The quality of agent output is directly proportional to the quality of the instruction. Precise instructions produce precise output. Vague instructions produce rework.

## Examples

**Instruction template**:
```
AGENT: [agent name]
TASK: [specific task description]
REQUIREMENTS: [cite PRD.md section X, architecture.md section Y]
STANDARDS: [cite project-context.md section Z]
SCOPE: [what is included / what is excluded]
OUTPUT EXPECTED: [exactly what the agent should produce]
DONE WHEN: [measurable completion criteria]
```

## Enforcement

Parzival self-checks: "Have my agent instructions been precise and cited?"

## Violation Response

Revise the instruction before sending to the agent.
