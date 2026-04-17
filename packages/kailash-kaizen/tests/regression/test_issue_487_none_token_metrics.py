"""Regression tests for issue #487: None token counts crash _calculate_usage_metrics.

The bug: Custom providers (e.g. WebSocket bridges to browser-side Ollama) cannot
obtain tokenizer state and return ``usage={'prompt_tokens': None, ...}``. Kaizen
then computes ``prompt_tokens + completion_tokens`` which raises
``TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'``.

The crash happens AFTER the provider successfully returned content, so the
entire ``self.run()`` call fails even though the LLM response was fine.

The fix: coerce ``None`` to ``0`` before arithmetic in every token-sum site:
- ``_calculate_usage_metrics`` (primary report site)
- ``_call_native_llm`` post-dispatch total_tokens back-fill
- ``_extract_token_usage`` TokenUsage population

Also guards ``efficiency_score = completion / total_tokens`` against
``ZeroDivisionError`` when all counts are zero.

Reported by @vflores-io (MediScribe) against kailash-kaizen.
"""

from unittest.mock import MagicMock

import pytest

from kaizen.nodes.ai.llm_agent import LLMAgentNode


def _make_node() -> LLMAgentNode:
    """Construct a minimal LLMAgentNode without running a workflow.

    ``_calculate_usage_metrics`` / ``_extract_token_usage`` are pure methods
    that depend only on the response dict. A MagicMock-backed node is
    sufficient; we don't need a provider, runtime, or network.
    """
    node = LLMAgentNode.__new__(LLMAgentNode)
    # logger is referenced on some provider paths; a MagicMock is fine.
    node.logger = MagicMock()
    return node


# ===================================================================
# Primary reproduction — exact scenario from the issue body
# ===================================================================


class TestIssue487PrimaryReproduction:
    """Reproduce the exact crash reported in issue #487."""

    @pytest.mark.regression
    def test_prompt_tokens_none_does_not_crash(self):
        """Regression #487: usage={'prompt_tokens': None, ...} must not raise.

        This is the minimal reproduction from the issue body. Without the fix,
        ``prompt_tokens + completion_tokens`` raises
        ``TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'``.
        """
        node = _make_node()
        response = {
            "content": "ok",
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": 42,
                "total_tokens": 42,
            },
        }

        # Must not raise.
        metrics = node._calculate_usage_metrics(
            messages=[{"role": "user", "content": "hi"}],
            response=response,
            model="browser-ollama-bridge",
            provider="custom",
        )

        # Missing counts coerced to 0; present counts preserved.
        assert metrics["prompt_tokens"] == 0
        assert metrics["completion_tokens"] == 42
        # total_tokens trusts the explicit value from the provider if present.
        assert metrics["total_tokens"] == 42
        # efficiency_score must not raise ZeroDivisionError.
        assert 0.0 <= metrics["efficiency_score"] <= 1.0


# ===================================================================
# Edge cases — all-None, all-zero, partial-None, missing keys
# ===================================================================


class TestIssue487EdgeCases:
    """Boundary conditions around None / 0 / missing usage fields."""

    @pytest.mark.regression
    def test_all_token_fields_none(self):
        """All three counters None — producer has zero tokenizer visibility."""
        node = _make_node()
        response = {
            "content": "ok",
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            },
        }

        metrics = node._calculate_usage_metrics(
            messages=[], response=response, model="x", provider="y"
        )

        assert metrics["prompt_tokens"] == 0
        assert metrics["completion_tokens"] == 0
        assert metrics["total_tokens"] == 0
        assert metrics["estimated_cost_usd"] == 0.0
        # efficiency_score is undefined on zero usage; must return a finite
        # number (not raise ZeroDivisionError, not return NaN).
        assert metrics["efficiency_score"] == 0.0

    @pytest.mark.regression
    def test_all_token_fields_zero(self):
        """All three counters explicitly 0 — legitimate empty response."""
        node = _make_node()
        response = {
            "content": "",
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

        metrics = node._calculate_usage_metrics(
            messages=[], response=response, model="x", provider="y"
        )

        assert metrics["prompt_tokens"] == 0
        assert metrics["completion_tokens"] == 0
        assert metrics["total_tokens"] == 0
        assert metrics["efficiency_score"] == 0.0

    @pytest.mark.regression
    def test_completion_tokens_none_prompt_known(self):
        """Inverse of the reported case: completion_tokens is None."""
        node = _make_node()
        response = {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": None,
                "total_tokens": None,
            }
        }

        metrics = node._calculate_usage_metrics(
            messages=[], response=response, model="x", provider="y"
        )

        assert metrics["prompt_tokens"] == 100
        assert metrics["completion_tokens"] == 0
        # total_tokens missing → computed from the coerced parts.
        assert metrics["total_tokens"] == 100

    @pytest.mark.regression
    def test_usage_key_absent_entirely(self):
        """Response has no 'usage' key — handled before the reported fix too,
        but asserted here so a future refactor can't regress the contract."""
        node = _make_node()
        response = {"content": "ok"}  # no usage key

        metrics = node._calculate_usage_metrics(
            messages=[], response=response, model="x", provider="y"
        )

        assert metrics["prompt_tokens"] == 0
        assert metrics["completion_tokens"] == 0
        assert metrics["total_tokens"] == 0

    @pytest.mark.regression
    def test_usage_key_explicit_none(self):
        """Response has ``usage=None`` (some providers emit this instead of {})."""
        node = _make_node()
        response = {"content": "ok", "usage": None}

        metrics = node._calculate_usage_metrics(
            messages=[], response=response, model="x", provider="y"
        )

        assert metrics["prompt_tokens"] == 0
        assert metrics["completion_tokens"] == 0
        assert metrics["total_tokens"] == 0

    @pytest.mark.regression
    def test_total_tokens_none_derived_from_parts(self):
        """Only total_tokens is None; prompt + completion known."""
        node = _make_node()
        response = {
            "usage": {
                "prompt_tokens": 30,
                "completion_tokens": 20,
                "total_tokens": None,
            }
        }

        metrics = node._calculate_usage_metrics(
            messages=[], response=response, model="x", provider="y"
        )

        assert metrics["prompt_tokens"] == 30
        assert metrics["completion_tokens"] == 20
        assert metrics["total_tokens"] == 50


# ===================================================================
# Sibling sites — same None bug exists in _extract_token_usage
# ===================================================================


class TestIssue487SiblingSites:
    """Same None-arithmetic bug exists in _extract_token_usage; guard both."""

    @pytest.mark.regression
    def test_extract_token_usage_none_prompt(self):
        """``_extract_token_usage`` must coerce None to 0 on the OpenAI path."""
        node = _make_node()
        response = {
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": 42,
                "total_tokens": 42,
            }
        }

        usage = node._extract_token_usage(response)

        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 42
        assert usage.total_tokens == 42

    @pytest.mark.regression
    def test_extract_token_usage_anthropic_none(self):
        """Anthropic metadata path sums input + output; None must not crash."""
        node = _make_node()
        response = {
            "metadata": {
                "usage": {
                    "input_tokens": None,
                    "output_tokens": 10,
                }
            }
        }

        usage = node._extract_token_usage(response)

        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 10
        assert usage.total_tokens == 10
