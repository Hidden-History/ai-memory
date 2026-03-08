---
name: 'step-03-layer2-documentation'
description: 'Layer 2 research: Consult official documentation and established best practices for the specific technology'
nextStepFile: './step-04-layer3-analyst-research.md'
---

# Step 3: Layer 2 -- Official Documentation and Established Best Practices

## STEP GOAL
When project files do not answer the question, consult the authoritative external sources for the specific technology in use. Always verify the exact version and confirm the answer fits the project's specific context.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The research question, Layer 1 results, the project's technology stack and versions from project-context.md
- Limits: Only consult sources at Tier 1-4 authority levels. Do not accept unverified sources.

## MANDATORY SEQUENCE

### 1. Identify the Exact Technology
Not just "React" -- "React 18.2 with TypeScript 5.0" (or whatever the exact version is from project-context.md).

### 2. Consult Sources in Priority Order

**TIER 1 -- Official documentation:**
- The official docs for the exact library/framework/language version in use
- Release notes for the specific version
- Official migration guides if applicable

**TIER 2 -- Language/platform specification:**
- Language specification (e.g., ECMAScript spec, Python docs)
- Platform documentation (e.g., Node.js docs, browser APIs)

**TIER 3 -- Established community standards:**
- Style guides maintained by the language/framework core team
- Security guidelines from recognized authorities (OWASP, NIST, etc.)
- Performance benchmarks with methodology disclosed

**TIER 4 -- Widely adopted community practice:**
- Patterns with broad adoption in the specific ecosystem
- Must be specific to the technology -- not generic programming advice

### 3. Invalid Sources (Do NOT Use)
- Generic "best practices" without a named source
- Stack Overflow answers without verification against official docs
- Blog posts without author credentials and source citations
- "Everyone does it this way" without evidence
- AI-generated recommendations without a cited source
- What Parzival remembers from training without verification
- What worked in a different project with a different stack

### 4. Research Process
1. Go to the official documentation for the exact version
2. Search for the specific question -- not the topic area
3. Read the relevant section in full -- do not skim
4. Verify the answer applies to the project's specific context:
   - Does the project use this version?
   - Are there project-specific configurations that change this guidance?
   - Does architecture.md override or modify this guidance?
5. Record the finding with full citation:
   Source: [official doc name, version, URL if applicable, section]
   Answer: [specific answer in Parzival's own words]
   Applies to this project: [yes/no + reasoning]

### 5. Evaluate Layer 2 Results

**FOUND -- verified answer from authoritative source:**
- Record citation (source, version, section)
- Verify it fits the project's specific context
- Check it does not conflict with any project file decision
- Proceed with confidence level: VERIFIED (Tier 1-2) or INFORMED (Tier 3-4)
- Skip to step-06 (document answer) or return to calling workflow

**FOUND -- conflicting guidance across sources:**
- Document the conflict precisely
- Determine which source has higher authority for this project
- If conflict cannot be resolved clearly: escalate to user via step-05
- Never pick one arbitrarily

**NOT FOUND or not applicable to this project's context:**
- Document what was searched
- Continue to Layer 3

## CRITICAL STEP COMPLETION NOTE
ONLY when Layer 2 research is complete and results evaluated, either return to calling workflow (if answer found) or load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Exact technology version identified before searching
- Sources consulted in priority order
- Findings include full citations with source, version, section
- Answer verified against project-specific context
- Conflicts documented when found

### FAILURE:
- Using sources from a different version
- Accepting blog posts or forum answers as authoritative
- Not verifying answer fits project context
- Picking arbitrarily between conflicting sources
- Stopping when an answer "sounds right" instead of when it is verified
