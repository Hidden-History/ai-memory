"""Unit tests for BMAD agent definitions.

Tests TECH-DEBT-035 Phase 4 - Port BMAD Agents to AgentDefinition.
Validates that agent definitions are properly structured and importable.
"""

import pytest
from src.memory.agents import (
    DEV_AGENT,
    CODE_REVIEWER_AGENT,
    ARCHITECT_AGENT,
    PARZIVAL_AGENT,
    TEA_AGENT,
    PM_AGENT,
    SM_AGENT,
)


class TestDevAgent:
    """Test DEV_AGENT definition."""

    def test_dev_agent_name_and_description(self):
        """Verify DEV_AGENT has proper description."""
        assert DEV_AGENT.description is not None
        assert len(DEV_AGENT.description) > 0
        assert "Senior" in DEV_AGENT.description or "developer" in DEV_AGENT.description.lower()

    def test_dev_agent_prompt_exists(self):
        """Verify DEV_AGENT has a system prompt."""
        assert DEV_AGENT.prompt is not None
        assert len(DEV_AGENT.prompt) > 100  # Should be substantial
        assert "story" in DEV_AGENT.prompt.lower() or "Story" in DEV_AGENT.prompt

    def test_dev_agent_tools_configured(self):
        """Verify DEV_AGENT has appropriate tools for implementation work."""
        assert DEV_AGENT.tools is not None
        assert isinstance(DEV_AGENT.tools, list)

        # Implementation agent needs Read, Write, Edit at minimum
        assert "Read" in DEV_AGENT.tools
        assert "Write" in DEV_AGENT.tools
        assert "Edit" in DEV_AGENT.tools

        # Should also have Bash for running tests
        assert "Bash" in DEV_AGENT.tools

    def test_dev_agent_model_configured(self):
        """Verify DEV_AGENT has a model specified."""
        assert DEV_AGENT.model is not None
        assert DEV_AGENT.model in ["sonnet", "opus", "haiku", "inherit"]


class TestCodeReviewerAgent:
    """Test CODE_REVIEWER_AGENT definition."""

    def test_code_reviewer_agent_name_and_description(self):
        """Verify CODE_REVIEWER_AGENT has proper description."""
        assert CODE_REVIEWER_AGENT.description is not None
        assert len(CODE_REVIEWER_AGENT.description) > 0
        assert "review" in CODE_REVIEWER_AGENT.description.lower()

    def test_code_reviewer_agent_prompt_exists(self):
        """Verify CODE_REVIEWER_AGENT has a system prompt."""
        assert CODE_REVIEWER_AGENT.prompt is not None
        assert len(CODE_REVIEWER_AGENT.prompt) > 100
        # Adversarial reviewer should mention finding issues
        assert "review" in CODE_REVIEWER_AGENT.prompt.lower()

    def test_code_reviewer_agent_tools_configured(self):
        """Verify CODE_REVIEWER_AGENT has read-only tools for review work."""
        assert CODE_REVIEWER_AGENT.tools is not None
        assert isinstance(CODE_REVIEWER_AGENT.tools, list)

        # Review agent needs Read for examining code
        assert "Read" in CODE_REVIEWER_AGENT.tools

        # Should NOT have Write or Edit (read-only for reviews)
        assert "Write" not in CODE_REVIEWER_AGENT.tools
        assert "Edit" not in CODE_REVIEWER_AGENT.tools

    def test_code_reviewer_agent_model_configured(self):
        """Verify CODE_REVIEWER_AGENT has a model specified."""
        assert CODE_REVIEWER_AGENT.model is not None
        assert CODE_REVIEWER_AGENT.model in ["sonnet", "opus", "haiku", "inherit"]


class TestArchitectAgent:
    """Test ARCHITECT_AGENT definition."""

    def test_architect_agent_name_and_description(self):
        """Verify ARCHITECT_AGENT has proper description."""
        assert ARCHITECT_AGENT.description is not None
        assert len(ARCHITECT_AGENT.description) > 0
        assert "architect" in ARCHITECT_AGENT.description.lower() or "design" in ARCHITECT_AGENT.description.lower()

    def test_architect_agent_prompt_exists(self):
        """Verify ARCHITECT_AGENT has a system prompt."""
        assert ARCHITECT_AGENT.prompt is not None
        assert len(ARCHITECT_AGENT.prompt) > 100
        assert "architect" in ARCHITECT_AGENT.prompt.lower() or "design" in ARCHITECT_AGENT.prompt.lower()

    def test_architect_agent_tools_configured(self):
        """Verify ARCHITECT_AGENT has appropriate tools for design work."""
        assert ARCHITECT_AGENT.tools is not None
        assert isinstance(ARCHITECT_AGENT.tools, list)

        # Architect needs Read for understanding existing architecture
        assert "Read" in ARCHITECT_AGENT.tools

        # Should have Write for creating architecture docs
        assert "Write" in ARCHITECT_AGENT.tools

        # Should have WebSearch for researching technologies
        assert "WebSearch" in ARCHITECT_AGENT.tools

    def test_architect_agent_model_configured(self):
        """Verify ARCHITECT_AGENT has a model specified."""
        assert ARCHITECT_AGENT.model is not None
        assert ARCHITECT_AGENT.model in ["sonnet", "opus", "haiku", "inherit"]


class TestParzivalAgent:
    """Test PARZIVAL_AGENT definition."""

    def test_parzival_agent_name_and_description(self):
        """Verify PARZIVAL_AGENT has proper description."""
        assert PARZIVAL_AGENT.description is not None
        assert len(PARZIVAL_AGENT.description) > 0
        assert "oversight" in PARZIVAL_AGENT.description.lower() or "quality" in PARZIVAL_AGENT.description.lower()

    def test_parzival_agent_prompt_exists(self):
        """Verify PARZIVAL_AGENT has a system prompt."""
        assert PARZIVAL_AGENT.prompt is not None
        assert len(PARZIVAL_AGENT.prompt) > 100
        assert "Parzival" in PARZIVAL_AGENT.prompt

    def test_parzival_agent_tools_configured(self):
        """Verify PARZIVAL_AGENT has read-only tools (oversight only, no implementation)."""
        assert PARZIVAL_AGENT.tools is not None
        assert isinstance(PARZIVAL_AGENT.tools, list)

        # Oversight agent needs Read for examining code
        assert "Read" in PARZIVAL_AGENT.tools

        # Should NOT have Write or Edit (oversight only, never implements)
        assert "Write" not in PARZIVAL_AGENT.tools
        assert "Edit" not in PARZIVAL_AGENT.tools

        # Should have Grep and Glob for searching
        assert "Grep" in PARZIVAL_AGENT.tools
        assert "Glob" in PARZIVAL_AGENT.tools

        # Should have WebSearch for research
        assert "WebSearch" in PARZIVAL_AGENT.tools

    def test_parzival_agent_model_configured(self):
        """Verify PARZIVAL_AGENT uses opus (requires strategic thinking)."""
        assert PARZIVAL_AGENT.model == "opus"


class TestTEAAgent:
    """Test TEA_AGENT definition."""

    def test_tea_agent_name_and_description(self):
        """Verify TEA_AGENT has proper description."""
        assert TEA_AGENT.description is not None
        assert len(TEA_AGENT.description) > 0
        assert "test" in TEA_AGENT.description.lower()

    def test_tea_agent_prompt_exists(self):
        """Verify TEA_AGENT has a system prompt."""
        assert TEA_AGENT.prompt is not None
        assert len(TEA_AGENT.prompt) > 100
        assert "test" in TEA_AGENT.prompt.lower()

    def test_tea_agent_tools_configured(self):
        """Verify TEA_AGENT has appropriate tools for test architecture work."""
        assert TEA_AGENT.tools is not None
        assert isinstance(TEA_AGENT.tools, list)

        # Test architect needs Read, Write, Edit for creating tests
        assert "Read" in TEA_AGENT.tools
        assert "Write" in TEA_AGENT.tools
        assert "Edit" in TEA_AGENT.tools

        # Should have Bash for running tests
        assert "Bash" in TEA_AGENT.tools

    def test_tea_agent_model_configured(self):
        """Verify TEA_AGENT uses sonnet (technical but not strategic)."""
        assert TEA_AGENT.model == "sonnet"


class TestPMAgent:
    """Test PM_AGENT definition."""

    def test_pm_agent_name_and_description(self):
        """Verify PM_AGENT has proper description."""
        assert PM_AGENT.description is not None
        assert len(PM_AGENT.description) > 0
        assert "product" in PM_AGENT.description.lower() or "prd" in PM_AGENT.description.lower()

    def test_pm_agent_prompt_exists(self):
        """Verify PM_AGENT has a system prompt."""
        assert PM_AGENT.prompt is not None
        assert len(PM_AGENT.prompt) > 100
        assert "product" in PM_AGENT.prompt.lower() or "WHY" in PM_AGENT.prompt

    def test_pm_agent_tools_configured(self):
        """Verify PM_AGENT has appropriate tools for product work."""
        assert PM_AGENT.tools is not None
        assert isinstance(PM_AGENT.tools, list)

        # PM needs Read for understanding requirements
        assert "Read" in PM_AGENT.tools

        # Should have Write for creating PRDs
        assert "Write" in PM_AGENT.tools

        # Should have WebSearch for research
        assert "WebSearch" in PM_AGENT.tools

    def test_pm_agent_model_configured(self):
        """Verify PM_AGENT uses sonnet."""
        assert PM_AGENT.model == "sonnet"


class TestSMAgent:
    """Test SM_AGENT definition."""

    def test_sm_agent_name_and_description(self):
        """Verify SM_AGENT has proper description."""
        assert SM_AGENT.description is not None
        assert len(SM_AGENT.description) > 0
        assert "scrum" in SM_AGENT.description.lower() or "story" in SM_AGENT.description.lower()

    def test_sm_agent_prompt_exists(self):
        """Verify SM_AGENT has a system prompt."""
        assert SM_AGENT.prompt is not None
        assert len(SM_AGENT.prompt) > 100
        assert "story" in SM_AGENT.prompt.lower() or "scrum" in SM_AGENT.prompt.lower()

    def test_sm_agent_tools_configured(self):
        """Verify SM_AGENT has appropriate tools for story preparation."""
        assert SM_AGENT.tools is not None
        assert isinstance(SM_AGENT.tools, list)

        # SM needs Read, Write, Edit for story preparation
        assert "Read" in SM_AGENT.tools
        assert "Write" in SM_AGENT.tools
        assert "Edit" in SM_AGENT.tools

    def test_sm_agent_model_configured(self):
        """Verify SM_AGENT uses sonnet."""
        assert SM_AGENT.model == "sonnet"


class TestAgentImportability:
    """Test that agents can be imported from src.memory.agents."""

    def test_all_agents_importable(self):
        """Verify all agents can be imported from the package."""
        from src.memory.agents import (
            DEV_AGENT,
            CODE_REVIEWER_AGENT,
            ARCHITECT_AGENT,
            PARZIVAL_AGENT,
            TEA_AGENT,
            PM_AGENT,
            SM_AGENT,
        )

        assert DEV_AGENT is not None
        assert CODE_REVIEWER_AGENT is not None
        assert ARCHITECT_AGENT is not None
        assert PARZIVAL_AGENT is not None
        assert TEA_AGENT is not None
        assert PM_AGENT is not None
        assert SM_AGENT is not None

    def test_agents_have_required_attributes(self):
        """Verify all agents have the required AgentDefinition attributes."""
        agents = [
            DEV_AGENT,
            CODE_REVIEWER_AGENT,
            ARCHITECT_AGENT,
            PARZIVAL_AGENT,
            TEA_AGENT,
            PM_AGENT,
            SM_AGENT,
        ]

        for agent in agents:
            # All agents must have these attributes
            assert hasattr(agent, "description")
            assert hasattr(agent, "prompt")
            assert hasattr(agent, "tools")
            assert hasattr(agent, "model")

            # Verify types
            assert isinstance(agent.description, str)
            assert isinstance(agent.prompt, str)
            assert agent.tools is None or isinstance(agent.tools, list)
            assert agent.model is None or agent.model in ["sonnet", "opus", "haiku", "inherit"]
