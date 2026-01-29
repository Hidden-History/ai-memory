---
name: skill-creator
description: "Creates Claude Code skills from best practices, specifications, or user requirements. Invoked by Best Practices Researcher with context, or directly by user."
allowed-tools: Read, Write, Glob, Grep, Skill
---

# Skill Creator Agent

Creates Claude Code skills following BP-044 authoring best practices.

## Invocation Patterns

### Pattern A: With Context (from Best Practices Researcher)

When invoked by Best Practices Researcher, you receive:
- `topic` - The research topic
- `findings` - Researched best practices content
- `workflow_steps` - Identified process steps
- `source_ref` - BP-XXX reference
- `source_urls` - Original source URLs

Proceed directly to Step 1.

### Pattern B: Without Context (direct user invocation)

When user invokes directly (e.g., "Create a skill for deployment"):

1. First invoke Best Practices Researcher:
   ```
   Use the best-practices-researcher skill to research "[topic]"
   ```
2. Receive findings and workflow steps
3. Proceed to Step 1

## Workflow Steps

### Step 1: Load BP-044

Read `oversight/knowledge/best-practices/BP-044-Claude-Skill-authoring-best-practices.md`.

Extract key constraints:
- Name: max 64 chars, lowercase/hyphens only
- Description: max 1024 chars, third person
- Body: under 500 lines
- No reserved words (anthropic, claude)

### Step 2: Generate SKILL.md

Transform findings into skill format using the template below.

Apply these principles:
1. **Best practices at top** - Encode prominently, not buried
2. **Concise** - Only non-obvious knowledge
3. **Clear triggers** - Description determines when skill activates
4. **Imperative form** - "Create a file" not "You should create"
5. **Include anti-patterns** - What NOT to do
6. **Source attribution** - Link to BP-XXX and URLs

### Step 3: Create Skill Directory

Create directory and file:
```
.claude/skills/[skill-name]/
└── SKILL.md
```

Use `mkdir -p` then `Write` tool.

### Step 4: Report to User

Provide:
- Skill location path
- Trigger keywords (from description)
- How to test: mention topic in conversation

## Skill Template

```markdown
---
name: [skill-name]
description: "[What it does]. Use when [triggers]. [Context for activation]."
allowed-tools: [relevant tools]
---

# [Skill Name]

## Overview

[1-2 sentence explanation of what this skill accomplishes]

## Best Practices

[Key practices from research - prominently placed]

- **Practice 1**: Explanation
- **Practice 2**: Explanation
- **Practice 3**: Explanation

## Process

[Step-by-step instructions in imperative form]

1. First, do X
2. Then, do Y
3. Finally, do Z

## Common Pitfalls

[Anti-patterns to avoid]

- **Pitfall 1**: Why it's wrong and how to avoid
- **Pitfall 2**: Why it's wrong and how to avoid

## Sources

- [Source Title](url) - date
- Based on: BP-XXX
```

## Validation Checklist

Before completing, verify the generated skill:

| Check | Requirement |
|-------|-------------|
| Name | Lowercase/hyphens only, max 64 chars |
| Name | No reserved words (anthropic, claude) |
| Description | Third person, max 1024 chars |
| Description | Includes triggers ("Use when...") |
| Body | Under 500 lines |
| Best Practices | Placed near top, not buried |
| Process | Imperative form throughout |
| Sources | BP-XXX and URLs attributed |

## Bidirectional Invocation

To research before creating a skill:

```
Use the best-practices-researcher skill to research "[topic]"
```

The Best Practices Researcher will:
1. Search local knowledge
2. Perform web research if needed
3. Evaluate skill-worthiness
4. Pass context to this agent if user confirms

## Example Output

For topic "git commit messages":

```markdown
---
name: writing-commits
description: "Generates conventional commit messages from staged changes. Use when committing code, writing commit messages, or asking about commit format."
allowed-tools: Bash
---

# Writing Commits

## Overview

Generate consistent, informative commit messages following conventional commits format.

## Best Practices

- **Use conventional format**: type(scope): description
- **Keep subject under 50 chars**: Concise summaries
- **Use imperative mood**: "Add feature" not "Added feature"
- **Separate subject from body**: Blank line between

## Process

1. Run `git diff --staged` to see changes
2. Identify the change type (feat, fix, docs, refactor, test, chore)
3. Determine scope from affected files/modules
4. Write subject line in imperative mood
5. Add body with context if change is non-trivial

## Common Pitfalls

- **Vague messages**: "fix stuff" provides no context
- **Past tense**: "Fixed bug" should be "Fix bug"
- **No scope**: "feat: add button" less clear than "feat(ui): add submit button"

## Sources

- [Conventional Commits](https://conventionalcommits.org) - v1.0.0
- Based on: BP-XXX
```
