---
name: "instruction"
description: "Standard agent instruction template used by WF-AGENT-DISPATCH to create precise, cited instructions for BMAD agents"
---

AGENT: {agent_name}
TASK: {task_description}
CONTEXT: {context_from_project_files}
REQUIREMENTS: {requirements_with_citations}
STANDARDS: {standards_with_citations}
SCOPE:
  IN: {in_scope}
  OUT: {out_of_scope}
OUTPUT EXPECTED: {expected_deliverable}
DONE WHEN: {measurable_completion_criteria}
