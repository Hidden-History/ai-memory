---
name: help
description: 'Analyzes what is done and the users query and offers advice on what to do next. Use if user says what should I do next or what do I do now'
---

# Task: AI Memory Help

## ROUTING RULES

- **Empty `phase` = anytime** — Universal tools work regardless of workflow state
- **Numbered phases indicate sequence** — Phases flow in order: init -> discovery -> architecture -> planning -> execution -> integration -> release -> maintenance
- **Phase with no Required Steps** - If an entire phase has no required items, it is optional. Always be clear about the next required item.
- **Stay in module** — Guide through the active module's workflow based on phase+sequence ordering
- **Descriptions contain routing** — Read for alternate paths (e.g., "back to previous if fixes needed")
- **`required=true` blocks progress** — Required workflows must complete before proceeding to later phases
- **Artifacts reveal completion** — Search resolved output paths for `outputs` patterns

## DISPLAY RULES

### Command-Based Workflows
When `command` field has a value:
- Show the command prefixed with `/` (e.g., `/parzival-start`)

### Menu-Based Workflows
When `command` field is empty:
- User invokes via the Parzival agent menu code
- Show the code value and menu reference

## MODULE DETECTION

- **Empty `module` column** → universal tools (work across all modules)
- **Named `module`** → module-specific workflows

Detect the active module from conversation context.

## INPUT ANALYSIS

Determine what was just completed:
- Explicit completion stated by user
- Workflow completed in current conversation
- Artifacts found matching `outputs` patterns
- If unclear, ask: "What workflow did you most recently complete?"

## EXECUTION

1. **Load catalog** — Load `{project-root}/_ai-memory/_config/aim-help.csv`

2. **Resolve output locations and config** — Scan `{project-root}/_ai-memory/` module configs. For each workflow row, resolve its `output-location` variables. Also extract `communication_language` from config.

3. **Ground in project knowledge** — Read available project documentation for context. Never fabricate project-specific details.

4. **Detect active module** — Use MODULE DETECTION above

5. **Analyze input** — Infer what was just completed using INPUT ANALYSIS above.

6. **Present recommendations** — Show next steps based on:
   - Completed workflows detected
   - Phase/sequence ordering (ROUTING RULES)
   - Artifact presence

   **Optional items first** — List optional workflows until a required step is reached
   **Required items next** — List the next required workflow

   For each item, include:
   - Workflow **name**
   - **Command** or **Menu code**
   - Brief **description**

7. **Additional guidance**:
   - Present all output in `{communication_language}`
   - For conversational requests: match the user's tone while presenting clearly

8. Return to the calling process after presenting recommendations.
