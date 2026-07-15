"""Regression: issue #1755 — SelfCorrectingRAGNode verification-parse hardening.

Post-#1736, ``_parse_verification_response`` consumes real LLM output on a LIVE
path (the pre-#1736 buggy envelope-read always fell back to the rule-based
path). The /redteam adversarial pass over #1736 surfaced two robustness gaps
(both rated LOW / non-security) now reachable by an ill-behaved LLM response:

  1. The parser validated field PRESENCE only, not TYPE. A ``confidence``
     returned as a STRING passed the presence check, then raised an uncaught
     ``TypeError`` at the numeric gate (``confidence >= threshold``) inside
     ``SelfCorrectingRAGNode.run()``.
  2. ``json.loads`` accepts the ``NaN`` literal. A ``confidence`` of NaN is
     ``math.isfinite``-false, so it never met the gate and the self-correction
     loop ran to ``max_corrections`` every time.

Fix: coerce every score field to a finite float at the single parse chokepoint
(``_parse_verification_response``); an ill-formed (non-numeric / non-finite)
score routes the whole response to the heuristic fallback, which already emits
finite floats. Every downstream ``confidence`` read (the run-loop gate, the
best-attempt selection, the final-result formatter) flows through that
chokepoint.

Tests are behavioral — call the method / run(), assert return/raise — never
source-grep. They fail against the pre-#1755 advanced.py and pass against the
fix.
"""

from __future__ import annotations

import math

import pytest

from kaizen.nodes.rag.advanced import SelfCorrectingRAGNode

pytestmark = pytest.mark.regression


def _envelope(content: str) -> dict:
    """The ``LLMAgentNode.execute()`` envelope shape the parser unwraps."""
    return {"success": True, "response": {"content": content}}


def _parse(content: str) -> dict:
    return SelfCorrectingRAGNode(max_corrections=0)._parse_verification_response(
        _envelope(content)
    )


class _StubVerifier:
    """Deterministic stand-in for the verifier LLMAgentNode.

    Not a mock of the parser under test — a Protocol-satisfying deterministic
    adapter returning a fixed envelope so the real ``_parse_verification_response``
    + run-loop gate execute against controlled LLM output offline. ``run()``
    re-enters ``_initialize_components`` but that method only builds a verifier
    when ``self.verifier_agent`` is falsy, so a pre-set stub survives.
    """

    def __init__(self, content: str) -> None:
        self._content = content

    def execute(self, **kwargs) -> dict:
        return _envelope(self._content)


class TestCoerceScore:
    """The coercion primitive: finite float or None (ill-formed sentinel)."""

    def test_numeric_string_coerces_to_float(self):
        assert SelfCorrectingRAGNode._coerce_score("0.9") == pytest.approx(0.9)

    def test_real_float_passes_through(self):
        assert SelfCorrectingRAGNode._coerce_score(0.85) == pytest.approx(0.85)

    def test_int_coerces_to_float(self):
        value = SelfCorrectingRAGNode._coerce_score(1)
        assert isinstance(value, float) and value == pytest.approx(1.0)

    def test_non_numeric_string_returns_none(self):
        assert SelfCorrectingRAGNode._coerce_score("high") is None

    def test_nan_returns_none(self):
        assert SelfCorrectingRAGNode._coerce_score(float("nan")) is None

    def test_positive_infinity_returns_none(self):
        assert SelfCorrectingRAGNode._coerce_score(float("inf")) is None

    def test_negative_infinity_returns_none(self):
        assert SelfCorrectingRAGNode._coerce_score(float("-inf")) is None

    def test_none_returns_none(self):
        assert SelfCorrectingRAGNode._coerce_score(None) is None


class TestParseVerificationHardening:
    """Gap 1 (string → coerce) + Gap 2 (NaN → fallback) at the parse chokepoint."""

    def test_string_confidence_is_coerced_not_crashed(self):
        v = _parse(
            '{"confidence": "0.9", "retrieval_quality": "0.8", '
            '"generation_quality": 0.7}'
        )
        assert isinstance(v["confidence"], float)
        assert v["confidence"] == pytest.approx(0.9)
        # sibling score fields are coerced too
        assert isinstance(v["retrieval_quality"], float)
        assert v["retrieval_quality"] == pytest.approx(0.8)

    def test_wellformed_float_confidence_returned_unchanged(self):
        v = _parse(
            '{"confidence": 0.85, "retrieval_quality": 0.9, '
            '"generation_quality": 0.8}'
        )
        assert v["confidence"] == pytest.approx(0.85)
        assert v["retrieval_quality"] == pytest.approx(0.9)

    def test_nan_confidence_routes_to_finite_fallback(self):
        # json.loads accepts the bare NaN literal; the fix must neutralize it.
        v = _parse(
            '{"confidence": NaN, "retrieval_quality": 0.8, '
            '"generation_quality": 0.7}'
        )
        assert isinstance(v["confidence"], float)
        assert math.isfinite(v["confidence"])

    def test_infinity_confidence_routes_to_finite_fallback(self):
        v = _parse(
            '{"confidence": Infinity, "retrieval_quality": 0.8, '
            '"generation_quality": 0.7}'
        )
        assert isinstance(v["confidence"], float)
        assert math.isfinite(v["confidence"])

    def test_non_numeric_confidence_routes_to_finite_fallback(self):
        v = _parse(
            '{"confidence": "very good", "retrieval_quality": 0.8, '
            '"generation_quality": 0.7}'
        )
        assert isinstance(v["confidence"], float)
        assert math.isfinite(v["confidence"])

    def test_string_confidence_survives_numeric_gate_without_typeerror(self):
        # the originating crash: a string confidence reaching `>= threshold`.
        v = _parse(
            '{"confidence": "0.5", "retrieval_quality": 0.5, '
            '"generation_quality": 0.5}'
        )
        # Must not raise TypeError — the comparison is now float >= float.
        assert (v["confidence"] >= 0.8) is False


class TestRunLoopWithIllFormedConfidence:
    """The live path: run() must not crash / hang on ill-formed LLM confidence."""

    def test_string_confidence_does_not_crash_run(self):
        node = SelfCorrectingRAGNode(max_corrections=1)
        node.verifier_agent = _StubVerifier(  # type: ignore[assignment]
            '{"confidence": "0.95", "retrieval_quality": "0.9", '
            '"generation_quality": "0.9"}'
        )
        result = node.run(
            documents=[{"id": "d1", "content": "neural network optimization"}],
            query="how are neural networks optimized?",
        )
        conf = result["quality_assessment"]["confidence"]
        assert isinstance(conf, float)
        assert math.isfinite(conf)
        assert conf == pytest.approx(0.95)

    def test_nan_confidence_run_terminates_with_finite_confidence(self):
        node = SelfCorrectingRAGNode(max_corrections=1)
        node.verifier_agent = _StubVerifier(  # type: ignore[assignment]
            '{"confidence": NaN, "retrieval_quality": 0.8, '
            '"generation_quality": 0.7}'
        )
        result = node.run(
            documents=[{"id": "d1", "content": "gradient descent"}],
            query="explain gradient descent",
        )
        conf = result["quality_assessment"]["confidence"]
        assert isinstance(conf, float)
        assert math.isfinite(conf)
