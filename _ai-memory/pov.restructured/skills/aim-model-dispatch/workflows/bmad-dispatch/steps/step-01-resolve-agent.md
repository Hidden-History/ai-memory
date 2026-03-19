---
name: 'step-01-resolve-agent'
description: 'Identify BMAD agent, present model options, determine backend, and prepare dispatch plan'
nextStepFile: './step-02-launch-and-activate.md'
---

# Step 1: Resolve Agent and Prepare Dispatch Plan

## STEP GOAL
Before opening any tmux pane, identify which BMAD agent to activate, determine the backend, present model options to the user, and prepare all values needed for dispatch.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User's task description, agent command list, backend preferences
- Limits: Do not open any tmux pane at this stage. This step is preparation only.
- **Backend skip:** If BACKEND was already set by route/step-01 (standard SKILL.md activation path),
  use that value directly and skip Section 2. Only run Section 2 if activating this workflow directly
  without the routing step.

## MANDATORY SEQUENCE

### 1. Identify the Target Agent

From the task description, determine which BMAD agent is needed.

**Agent command reference:**

| Agent Type | Activation Command |
|---|---|
| Developer | `/bmad-agent-bmm-dev` |
| PM (Product Manager) | `/bmad-agent-bmm-pm` |
| Analyst | `/bmad-agent-bmm-analyst` |
| Architect | `/bmad-agent-bmm-architect` |
| Scrum Master | `/bmad-agent-bmm-sm` |
| QA Engineer | `/bmad-agent-bmm-qa` |
| UX Designer | `/bmad-agent-bmm-ux-designer` |
| Tech Writer | `/bmad-agent-bmm-tech-writer` |
| Quick Flow Solo Dev | `/bmad-agent-bmm-quick-flow-solo-dev` |
| BMAD Master | `/bmad-agent-bmad-master` |
| Agent Builder | `/bmad-agent-bmb-agent-builder` |
| Module Builder | `/bmad-agent-bmb-module-builder` |
| Workflow Builder | `/bmad-agent-bmb-workflow-builder` |
| Brainstorming Coach | `/bmad-agent-cis-brainstorming-coach` |
| Creative Problem Solver | `/bmad-agent-cis-creative-problem-solver` |
| Design Thinking Coach | `/bmad-agent-cis-design-thinking-coach` |
| Innovation Strategist | `/bmad-agent-cis-innovation-strategist` |
| Presentation Master | `/bmad-agent-cis-presentation-master` |
| Storyteller | `/bmad-agent-cis-storyteller` |
| Test Architect (TEA) | `/bmad-agent-tea-tea` |

If the task description does not specify an agent, use this selection guide:

| Task Type | Agent | Menu Code |
|---|---|---|
| Research / analyze codebase | Analyst | Use menu |
| Create or update PRD | PM | `CP` |
| Validate a PRD | PM | `VP` |
| Break down features into stories | PM | `CE` |
| Design system architecture | Architect | Use menu |
| Sprint planning | SM | Use menu |
| Write code / implement a story | DEV | `DS` |
| Review implemented code | DEV | `CR` |
| Design user flows | UX Designer | Use menu |
| Write or review documentation | Tech Writer | `WD` |
| Validate documentation | Tech Writer | `VD` |
| Write and run tests | QA | Use menu |
| Build new BMAD agents | Agent Builder | Use menu |
| Build new BMAD modules | Module Builder | Use menu |
| Build new BMAD workflows | Workflow Builder | Use menu |

**IMPORTANT**: Even if the user specifies a direct workflow command like `/bmad-bmm-code-review` or `/bmad-bmm-dev-story`, you MUST still use two-phase activation. Map the direct command to its parent agent + menu code:

| Direct Command | Activate Agent | Menu Code |
|---|---|---|
| `/bmad-bmm-code-review` | `/bmad-agent-bmm-dev` | `CR` |
| `/bmad-bmm-dev-story` | `/bmad-agent-bmm-dev` | `DS` |
| `/bmad-bmm-create-prd` | `/bmad-agent-bmm-pm` | `CP` |
| `/bmad-bmm-validate-prd` | `/bmad-agent-bmm-pm` | `VP` |
| `/bmad-bmm-create-epics-and-stories` | `/bmad-agent-bmm-pm` | `CE` |
| `/bmad-bmm-create-architecture` | `/bmad-agent-bmm-architect` | Use menu |
| `/bmad-bmm-sprint-planning` | `/bmad-agent-bmm-sm` | Use menu |
| `/bmad-bmm-create-ux-design` | `/bmad-agent-bmm-ux-designer` | Use menu |

### 2. Determine Backend

Check for backend specification in the dispatch prompt:

**Explicit backend keywords:**
- "dispatch to claude" / "use claude" / "native claude" → `claude`
- "dispatch to openrouter" / "use openrouter" / "300 models" → `openrouter`
- "dispatch to ollama" / "use ollama" / "remote model" → `ollama`
- "gemini" or "google model" → `gemini`
- "deepseek" → `deepseek`
- "groq" → `groq`
- "cerebras" → `cerebras`
- "mistral" or "codestral" → `mistral`
- "openai" or "gpt-4o" → `openai`
- "vertex-ai" or "vertex ai" or "google vertex" → `vertex-ai`
- "siliconflow" or "silicon flow" → `siliconflow`
- No backend specified → `claude` (default)

### 3. Determine Wrapper Command

| Backend | Wrapper Command |
|---|---|
| claude | `claude-dispatch` |
| openrouter | `provider-dispatch openrouter` |
| ollama | `provider-dispatch ollama` |
| gemini | `provider-dispatch gemini` |
| deepseek | `provider-dispatch deepseek` |
| groq | `provider-dispatch groq` |
| cerebras | `provider-dispatch cerebras` |
| mistral | `provider-dispatch mistral` |
| openai | `provider-dispatch openai` |
| vertex-ai | `provider-dispatch vertex-ai` |
| siliconflow | `provider-dispatch siliconflow` |
| (any other provider) | `provider-dispatch <provider-name>` |

### 4. Check for Explicit Model

If the user already specified a model in their request (e.g., "use qwen3-coder-next:cloud", "with gpt-4o"), record that model and skip to section 7.

If no model was specified, proceed to section 5.

### 5. Present Model Options to User

Follow the model selection procedure in `references/model-selection-guide.md`:
- Detect task category using the category table
- Present backend-appropriate model options
- Run live query for openrouter (SKILL_DIR inline in every Bash call)

### 6. Wait for User Model Choice

Follow the confirmation gate in `references/model-selection-guide.md`. Halt and wait for
explicit user confirmation. Record confirmed choice as MODEL.

### 7. Determine Task Directions

After the agent menu appears, what should be sent?

**Pattern A — Menu Code:**
Each agent menu has items with codes like `[DS]`, `[CR]`, `[CH]`, `[VD]`. Send the code.

Examples:
- Dev agent: `DS` (Dev Story), `CR` (Code Review)
- Tech Writer: `VD` (Validate Documentation)
- PM: `CP` (Create PRD), `VP` (Validate PRD), `CE` (Create Epics)

**Pattern B — Direct Task Text:**
Send free-form task text. The agent will fuzzy-match it to a menu item.

Choose the pattern that best fits the task. Menu codes are more reliable.

### 8. Record the Dispatch Plan

Store these values:
- **AGENT_COMMAND**: The activation command (e.g., `/bmad-agent-bmm-dev`)
- **TASK_INPUT**: The text to send after menu appears (e.g., `DS`)
- **TASK_FOLLOW_UP**: Any additional input needed later (empty if not known)
- **AGENT_NAME**: Human-readable name (e.g., `bmad-dev`, `bmad-tech-writer`)
- **EXPECTED_BEHAVIOR**: What the agent should do (brief description)
- **BACKEND**: The backend (claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow)
- **WRAPPER_CMD**: `provider-dispatch ${BACKEND}` for all non-claude backends, or `claude-dispatch` for claude
- **MODEL**: The model ID confirmed by user (empty for claude if not specified)

### 9. Validate

Confirm:
- The activation command matches a known agent
- The task input is clear and unambiguous
- The expected behavior is specific enough
- The backend is valid
- Model is confirmed by user or was explicitly specified in request

## CRITICAL STEP COMPLETION NOTE
ONLY when model is confirmed by user (section 6) or was explicitly specified (section 4), AND the dispatch plan is fully prepared with all eight values recorded, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Correct agent identified for the task
- Activation command matches a valid agent
- Backend correctly determined
- Model options presented to user (when not pre-specified)
- User explicitly confirmed model choice
- Wrapper command resolved
- Task input is concrete
- All dispatch plan values recorded

### FAILURE:
- Choosing wrong agent for the task type
- Proceeding without user model confirmation when no model was specified
- Silently picking a default model without presenting options
- Proceeding without a concrete task input
- Missing or ambiguous expected behavior
- Ambiguous backend specification
- Opening a tmux pane during this step
