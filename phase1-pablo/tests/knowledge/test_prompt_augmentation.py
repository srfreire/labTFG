"""Tests for P4-002: system prompt augmentation with Knowledge Backbone sections."""

from __future__ import annotations

from decisionlab.agents.builder_sub import (
    BUILDER_SUB_SYSTEM_PROMPT,
    _KNOWLEDGE_PROMPT_SECTION as BUILDER_KNOWLEDGE,
)
from decisionlab.agents.deep_researcher import (
    DEEP_RESEARCHER_SYSTEM_PROMPT,
    _KNOWLEDGE_PROMPT_SECTION as DEEP_RESEARCHER_KNOWLEDGE,
)
from decisionlab.agents.formalizer_sub import (
    FORMALIZER_SUB_SYSTEM_PROMPT,
    _KNOWLEDGE_PROMPT_SECTION as FORMALIZER_KNOWLEDGE,
)
from decisionlab.agents.reasoner_sub import (
    REASONER_SUB_SYSTEM_PROMPT,
    _KNOWLEDGE_PROMPT_SECTION as REASONER_KNOWLEDGE,
)
from decisionlab.agents.researcher import (
    RESEARCHER_SYSTEM_PROMPT,
    _KNOWLEDGE_PROMPT_SECTION as RESEARCHER_KNOWLEDGE,
)


# ── AC1: Knowledge Backbone section present when infra available ──


class TestKnowledgeBackbonePresent:
    """AC1: When knowledge infrastructure is available, each agent's system
    prompt contains the 'Knowledge Backbone' section."""

    def test_researcher_prompt_contains_knowledge_backbone(self):
        section = RESEARCHER_KNOWLEDGE
        assert "## Knowledge Backbone" in section
        assert "retrieve_knowledge" in section

    def test_deep_researcher_prompt_contains_knowledge_backbone(self):
        section = DEEP_RESEARCHER_KNOWLEDGE
        assert "## Knowledge Backbone" in section
        assert "retrieve_knowledge" in section

    def test_formalizer_prompt_contains_knowledge_backbone(self):
        section = FORMALIZER_KNOWLEDGE
        assert "## Knowledge Backbone" in section
        assert "retrieve_knowledge" in section

    def test_reasoner_prompt_contains_knowledge_backbone(self):
        section = REASONER_KNOWLEDGE
        assert "## Knowledge Backbone" in section
        assert "retrieve_knowledge" in section

    def test_builder_prompt_contains_knowledge_backbone(self):
        section = BUILDER_KNOWLEDGE
        assert "## Knowledge Backbone" in section
        assert "retrieve_knowledge" in section


# ── AC2: Prompts unchanged when knowledge infra unavailable ──


class TestPromptsUnchangedWithoutKnowledge:
    """AC2: When knowledge infrastructure is unavailable, system prompts
    are unchanged from current behavior (no Knowledge Backbone section)."""

    def test_researcher_base_prompt_has_no_knowledge_section(self):
        assert "Knowledge Backbone" not in RESEARCHER_SYSTEM_PROMPT

    def test_deep_researcher_base_prompt_has_no_knowledge_section(self):
        assert "Knowledge Backbone" not in DEEP_RESEARCHER_SYSTEM_PROMPT

    def test_formalizer_base_prompt_has_no_knowledge_section(self):
        assert "Knowledge Backbone" not in FORMALIZER_SUB_SYSTEM_PROMPT

    def test_reasoner_base_prompt_has_no_knowledge_section(self):
        assert "Knowledge Backbone" not in REASONER_SUB_SYSTEM_PROMPT

    def test_builder_base_prompt_has_no_knowledge_section(self):
        assert "Knowledge Backbone" not in BUILDER_SUB_SYSTEM_PROMPT


# ── AC3: Researcher prompt instructs early retrieval (before web_search) ──


class TestResearcherEarlyRetrieval:
    """AC3: Researcher prompt mentions calling retrieve_knowledge before
    web searches, encouraging early use."""

    def test_researcher_prompt_mentions_before_searches(self):
        assert "before" in RESEARCHER_KNOWLEDGE.lower()
        assert "web search" in RESEARCHER_KNOWLEDGE.lower()


# ── AC4: Formalizer prompt references formulation patterns ──


class TestFormalizerPatternReferences:
    """AC4: Formalizer prompt instructs referencing retrieved formulation
    patterns when available."""

    def test_formalizer_prompt_mentions_formulation_patterns(self):
        text = FORMALIZER_KNOWLEDGE.lower()
        assert "formulation pattern" in text

    def test_formalizer_prompt_mentions_equations(self):
        text = FORMALIZER_KNOWLEDGE.lower()
        assert "equation" in text


# ── AC5: Prompt additions under 80 words each ──


def _word_count(text: str) -> int:
    """Count words in text, stripping markdown headers and backticks."""
    lines = text.strip().splitlines()
    body_lines = [line for line in lines if not line.startswith("#")]
    return len(" ".join(body_lines).split())


class TestPromptConciseness:
    """AC5: Prompt additions are concise — under 80 words each."""

    def test_researcher_prompt_under_80_words(self):
        wc = _word_count(RESEARCHER_KNOWLEDGE)
        assert wc <= 80, f"Researcher prompt is {wc} words (max 80)"

    def test_deep_researcher_prompt_under_80_words(self):
        wc = _word_count(DEEP_RESEARCHER_KNOWLEDGE)
        assert wc <= 80, f"DeepResearcher prompt is {wc} words (max 80)"

    def test_formalizer_prompt_under_80_words(self):
        wc = _word_count(FORMALIZER_KNOWLEDGE)
        assert wc <= 80, f"Formalizer prompt is {wc} words (max 80)"

    def test_reasoner_prompt_under_80_words(self):
        wc = _word_count(REASONER_KNOWLEDGE)
        assert wc <= 80, f"Reasoner prompt is {wc} words (max 80)"

    def test_builder_prompt_under_80_words(self):
        wc = _word_count(BUILDER_KNOWLEDGE)
        assert wc <= 80, f"Builder prompt is {wc} words (max 80)"


# ── Agent-specific content checks ──


class TestAgentSpecificContent:
    """Each agent's Knowledge Backbone section contains stage-appropriate
    guidance, not generic boilerplate."""

    def test_researcher_mentions_paradigms(self):
        text = RESEARCHER_KNOWLEDGE.lower()
        assert "paradigm" in text

    def test_deep_researcher_mentions_postulates_or_variables(self):
        text = DEEP_RESEARCHER_KNOWLEDGE.lower()
        assert "postulate" in text or "variable" in text

    def test_formalizer_mentions_mathematical(self):
        text = FORMALIZER_KNOWLEDGE.lower()
        assert "mathematical" in text or "equation" in text

    def test_reasoner_mentions_parameter_ranges(self):
        text = REASONER_KNOWLEDGE.lower()
        assert "parameter" in text

    def test_builder_mentions_code_patterns(self):
        text = BUILDER_KNOWLEDGE.lower()
        assert "code pattern" in text
