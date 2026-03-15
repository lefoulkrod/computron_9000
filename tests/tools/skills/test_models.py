"""Unit tests for skill models."""

from __future__ import annotations

import pytest

from skills._models import SkillDefinition, SkillStep


@pytest.mark.unit
class TestSkillStep:
    """Tests for SkillStep model."""

    def test_construction(self) -> None:
        """Verify step with all fields."""
        step = SkillStep(
            description="Open the page",
            tool="open_url",
            notes="May need to handle cookie popup",
        )
        assert step.tool == "open_url"
        assert step.notes == "May need to handle cookie popup"


@pytest.mark.unit
class TestSkillDefinition:
    """Tests for SkillDefinition model."""

    def test_defaults(self) -> None:
        """Verify sensible defaults."""
        skill = SkillDefinition(id="s1", name="test_skill", description="A test")
        assert skill.agent_scope == "ANY"
        assert skill.usage_count == 0
        assert skill.version == 1

    def test_serialization_roundtrip(self) -> None:
        """Verify model_dump and model_validate roundtrip."""
        skill = SkillDefinition(
            id="s2",
            name="scrape_prices",
            description="Scrape product prices",
            agent_scope="COMPUTRON_9000",
            steps=[
                SkillStep(
                    description="Open page",
                    tool="browser_agent_tool",
                ),
            ],
            usage_count=12,
        )
        data = skill.model_dump()
        restored = SkillDefinition.model_validate(data)
        assert restored.name == "scrape_prices"
        assert len(restored.steps) == 1
        assert restored.usage_count == 12
