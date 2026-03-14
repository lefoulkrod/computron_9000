"""Unit tests for skill models."""

from __future__ import annotations

import pytest

from tools.skills._models import SkillDefinition, SkillParameter, SkillStep


@pytest.mark.unit
class TestSkillParameter:
    """Tests for SkillParameter model."""

    def test_defaults(self) -> None:
        """Verify default values."""
        param = SkillParameter(name="url", description="Target URL")
        assert param.type == "string"
        assert param.required is True
        assert param.example == ""


@pytest.mark.unit
class TestSkillStep:
    """Tests for SkillStep model."""

    def test_construction(self) -> None:
        """Verify step with all fields."""
        step = SkillStep(
            description="Open the page",
            tool="open_url",
            argument_template={"url": "{target_url}"},
            expected_outcome="Page loaded",
            notes="May need to handle cookie popup",
        )
        assert step.tool == "open_url"
        assert "{target_url}" in step.argument_template["url"]


@pytest.mark.unit
class TestSkillDefinition:
    """Tests for SkillDefinition model."""

    def test_defaults(self) -> None:
        """Verify sensible defaults."""
        skill = SkillDefinition(id="s1", name="test_skill", description="A test")
        assert skill.agent_scope == "ANY"
        assert skill.confidence == 0.5
        assert skill.usage_count == 0
        assert skill.active is True
        assert skill.version == 1

    def test_serialization_roundtrip(self) -> None:
        """Verify model_dump and model_validate roundtrip."""
        skill = SkillDefinition(
            id="s2",
            name="scrape_prices",
            description="Scrape product prices",
            agent_scope="COMPUTRON_9000",
            category="web_scraping",
            parameters=[
                SkillParameter(name="url", description="Target URL", type="url"),
            ],
            steps=[
                SkillStep(
                    description="Open page",
                    tool="browser_agent_tool",
                    argument_template={"instructions": "Open {url}"},
                ),
            ],
            confidence=0.85,
            usage_count=12,
            success_count=10,
        )
        data = skill.model_dump()
        restored = SkillDefinition.model_validate(data)
        assert restored.name == "scrape_prices"
        assert len(restored.parameters) == 1
        assert len(restored.steps) == 1
        assert restored.confidence == 0.85
