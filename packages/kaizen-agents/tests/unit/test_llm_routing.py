# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for LLMBased routing strategy.

Mocks are permitted at Tier 1 per rules/testing.md.  The underlying
``llm_text_similarity`` and ``llm_capability_match`` functions are
mocked so the tests run without API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from kaizen_agents.patterns.llm_routing import LLMBased


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@dataclass
class _FakeCapability:
    """Minimal capability stub with name/description for routing tests."""

    name: str
    description: str


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class TestLLMBasedConstruction:
    """LLMBased can be constructed with or without config."""

    def test_construct_no_config(self):
        strategy = LLMBased()
        assert strategy._config is None

    def test_construct_with_config(self):
        from kaizen.core.base_agent import BaseAgentConfig

        cfg = BaseAgentConfig(llm_provider="mock", model="mock-model")
        strategy = LLMBased(config=cfg)
        assert strategy._config is cfg


class TestLLMBasedScore:
    """score() delegates to the correct reasoning helper and returns a float."""

    @pytest.mark.asyncio
    async def test_score_string_capability(self):
        strategy = LLMBased()
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            return_value=0.85,
        ):
            result = await strategy.score("translate a document", "translation service")
            assert isinstance(result, float)
            assert result == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_score_structured_capability(self):
        strategy = LLMBased()
        cap = _FakeCapability(name="translate", description="Translates documents")
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_capability_match",
            return_value=0.92,
        ):
            result = await strategy.score("translate a document", cap)
            assert isinstance(result, float)
            assert result == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_score_returns_zero_for_empty_task(self):
        """llm_text_similarity returns 0.0 for empty input."""
        strategy = LLMBased()
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            return_value=0.0,
        ):
            result = await strategy.score("", "anything")
            assert result == 0.0


class TestLLMBasedSelectBest:
    """select_best() scores all candidates and returns the highest."""

    @pytest.mark.asyncio
    async def test_select_best_returns_highest(self):
        strategy = LLMBased()
        candidates = ["translation", "summarization", "code review"]
        scores = {
            "translation": 0.9,
            "summarization": 0.3,
            "code review": 0.1,
        }
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            side_effect=lambda text_a, text_b, **kw: scores.get(text_b, 0.0),
        ):
            best = await strategy.select_best("translate this", candidates)
            assert best == "translation"

    @pytest.mark.asyncio
    async def test_select_best_empty_candidates(self):
        strategy = LLMBased()
        result = await strategy.select_best("translate", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_select_best_structured_capabilities(self):
        strategy = LLMBased()
        caps = [
            _FakeCapability(name="translate", description="Translates documents"),
            _FakeCapability(name="summarize", description="Summarizes text"),
        ]
        scores = {"translate": 0.95, "summarize": 0.4}
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_capability_match",
            side_effect=lambda capability_name, **kw: scores.get(capability_name, 0.0),
        ):
            best = await strategy.select_best("translate this document", caps)
            assert best is caps[0]
