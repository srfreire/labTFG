import pytest
from unittest.mock import AsyncMock

from decisionlab.tools.agents import LAUNCH_DEEP_RESEARCH_SCHEMA, create_launch_deep_research


def test_schema_has_required_fields():
    assert LAUNCH_DEEP_RESEARCH_SCHEMA["name"] == "launch_deep_research"
    assert "paradigm" in LAUNCH_DEEP_RESEARCH_SCHEMA["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_launch_deep_research_calls_sub_agent():
    sub_agent_factory = AsyncMock(return_value="# Homeostatic — Deep research\n\nContent here.")
    fn = create_launch_deep_research(sub_agent_factory)
    result = await fn({"paradigm": "Homeostatic regulation of food intake"})
    assert "Homeostatic" in result
    sub_agent_factory.assert_called_once_with("Homeostatic regulation of food intake")


@pytest.mark.asyncio
async def test_launch_deep_research_missing_paradigm_raises():
    sub_agent_factory = AsyncMock()
    fn = create_launch_deep_research(sub_agent_factory)
    with pytest.raises(ValueError, match="paradigm"):
        await fn({})
