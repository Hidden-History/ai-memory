---
name: 'step-01-gather-project-info'
description: 'Gather all required project information from the user in a single structured request'
nextStepFile: './step-02-validate-and-clarify.md'
---

# Step 1: Gather Project Information

## STEP GOAL
Ask the user for all required project information upfront in a single structured request. Do not ask piecemeal across multiple exchanges. Collect everything needed to create the project baseline.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: No project files exist. This is a brand new project.
- Limits: Do not assume any answers. Do not pre-fill any fields. Do not begin creating files yet.

## MANDATORY SEQUENCE

### 1. Check for Existing Information
Before asking questions, check if the user has already provided a spec, design doc, or feature list in their initial message.

**IF existing document is provided:**
- Read it fully before asking any questions
- Extract what is already decided from the document
- Ask only about what is genuinely missing
- Do not ask for information the document already contains
- Note in the gathering output where information came from

### 2. Present Information Gathering Request
Present the following structured request to the user:

**REQUIRED -- Cannot proceed without these:**
1. **Project name** -- What is this project called?
2. **Project type** -- What are we building? (web app / mobile app / API / CLI tool / library / other)
3. **Primary goal** -- In one or two sentences, what does this project accomplish? What problem does it solve?
4. **Tech stack preferences** -- Does the user have existing preferences for language/runtime, framework, database, hosting/deployment target, or any tools/libraries already decided? (or "not decided yet")
5. **Project scale** -- Which track fits this project?
   - Quick Flow: bug fix, simple feature, clear scope (1-15 stories)
   - Standard Method: product, platform, complex feature (10-50+ stories)
   - Enterprise: compliance, multi-tenant, large team (30+ stories)
6. **Known constraints** -- Any hard constraints? Deadlines, budget, team size, regulatory/compliance requirements, integration requirements with existing systems

**OPTIONAL -- Helpful but not required to start:**
7. **Existing references** -- Any existing designs, specs, or inspiration?
8. **Definition of done** -- How will we know when the project is complete? What does "shipped" look like?

### 3. Wait for User Response
Halt and wait for the user to respond with their information. Do not proceed until information is received.

### 4. Record Raw Responses
Record all responses exactly as provided. Do not interpret, rephrase, or fill gaps at this stage.

## CRITICAL STEP COMPLETION NOTE
ONLY when the user has responded with project information, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All required fields were requested in a single structured message
- User responses are recorded verbatim without interpretation
- Existing documents (if provided) were read before asking questions
- Only genuinely missing information was asked for

### FAILURE:
- Asking questions piecemeal across multiple exchanges
- Pre-filling any fields with assumptions
- Asking for information already provided in an existing document
- Proceeding without receiving user response
