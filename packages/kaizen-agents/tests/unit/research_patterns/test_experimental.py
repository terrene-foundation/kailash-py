"""Unit tests for kaizen_agents.research_patterns.experimental.

Tier 1 — pure logic, no infrastructure.
Re-establishes coverage for the modules moved by PR #75 (closes #821).
"""

from __future__ import annotations

import pytest

from kaizen.research.parser import ResearchPaper
from kaizen.research.validator import ValidationResult
from kaizen.signatures import Signature
from kaizen_agents.research_patterns.experimental import ExperimentalFeature


class _MockExecuteSignatureStub(Signature):
    """Minimal Signature subclass that records execute() invocations.

    Suffix `Stub` per `rules/testing.md` — pytest will not collect this
    helper as a test class.
    """

    def __init__(self) -> None:
        super().__init__(inputs=["query"], outputs=["result"])

    def execute(self, **kwargs: object) -> dict:  # type: ignore[override]
        return {"called_with": kwargs}


def _make_paper(arxiv_id: str = "2106.00001") -> ResearchPaper:
    return ResearchPaper(
        arxiv_id=arxiv_id,
        title="Flash Attention",
        authors=["Tri Dao", "Daniel Y. Fu"],
        abstract="abstract text",
        methodology="methodology text",
    )


def _make_validation() -> ValidationResult:
    return ValidationResult(
        validation_passed=True,
        reproducibility_score=0.96,
    )


@pytest.fixture
def feature() -> ExperimentalFeature:
    return ExperimentalFeature(
        feature_id="flash-attention-v1",
        paper=_make_paper(),
        validation=_make_validation(),
        signature_class=_MockExecuteSignatureStub,
        version="1.0.0",
        status="experimental",
        compatibility={"kaizen": ">=0.1.0"},
        performance={"speedup": 2.7},
        metadata={"tags": ["attention", "optimization"], "description": "Fast attn"},
    )


# ---------------------------------------------------------------------------
# Construction + enable / disable
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_is_enabled_defaults_to_false(self, feature: ExperimentalFeature) -> None:
        assert feature.is_enabled() is False

    def test_enable_sets_state(self, feature: ExperimentalFeature) -> None:
        feature.enable()
        assert feature.is_enabled() is True

    def test_disable_clears_state(self, feature: ExperimentalFeature) -> None:
        feature.enable()
        feature.disable()
        assert feature.is_enabled() is False

    def test_enable_is_idempotent(self, feature: ExperimentalFeature) -> None:
        feature.enable()
        feature.enable()
        assert feature.is_enabled() is True


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_when_disabled_raises(self, feature: ExperimentalFeature) -> None:
        with pytest.raises(RuntimeError, match="flash-attention-v1"):
            feature.execute(query="test")

    def test_execute_when_enabled_calls_signature(
        self, feature: ExperimentalFeature
    ) -> None:
        feature.enable()
        result = feature.execute(query="hello", key="k")
        assert result == {"called_with": {"query": "hello", "key": "k"}}

    def test_execute_after_disable_raises(self, feature: ExperimentalFeature) -> None:
        feature.enable()
        feature.disable()
        with pytest.raises(RuntimeError, match="not enabled"):
            feature.execute(query="x")


# ---------------------------------------------------------------------------
# Lifecycle: update_status()
# ---------------------------------------------------------------------------


class TestUpdateStatusValidTransitions:
    @pytest.mark.parametrize(
        "start_status, end_status",
        [
            ("experimental", "beta"),
            ("experimental", "deprecated"),
            ("beta", "stable"),
            ("beta", "deprecated"),
            ("stable", "deprecated"),
        ],
    )
    def test_valid_transitions(self, start_status: str, end_status: str) -> None:
        feature = ExperimentalFeature(
            feature_id="f",
            paper=_make_paper(),
            validation=_make_validation(),
            signature_class=_MockExecuteSignatureStub,
            version="1.0.0",
            status=start_status,
            compatibility={},
            performance={},
            metadata={},
        )
        feature.update_status(end_status)
        assert feature.status == end_status


class TestUpdateStatusInvalidTransitions:
    @pytest.mark.parametrize(
        "start_status, end_status",
        [
            ("experimental", "stable"),  # must go through beta
            ("stable", "experimental"),  # cannot downgrade
            ("stable", "beta"),  # cannot downgrade
            ("beta", "experimental"),  # cannot downgrade
            ("deprecated", "experimental"),  # terminal
            ("deprecated", "beta"),  # terminal
            ("deprecated", "stable"),  # terminal
        ],
    )
    def test_invalid_transitions_raise(
        self, start_status: str, end_status: str
    ) -> None:
        feature = ExperimentalFeature(
            feature_id="f",
            paper=_make_paper(),
            validation=_make_validation(),
            signature_class=_MockExecuteSignatureStub,
            version="1.0.0",
            status=start_status,
            compatibility={},
            performance={},
            metadata={},
        )
        with pytest.raises(ValueError, match="Invalid status transition"):
            feature.update_status(end_status)
        # Status MUST be unchanged after a refused transition.
        assert feature.status == start_status


# ---------------------------------------------------------------------------
# get_documentation()
# ---------------------------------------------------------------------------


class TestGetDocumentation:
    def test_documentation_contains_metadata_description_as_title(
        self, feature: ExperimentalFeature
    ) -> None:
        docs = feature.get_documentation()
        # When metadata.description is set, it wins over paper.title for the H1.
        assert docs.startswith("# Fast attn")

    def test_documentation_contains_feature_metadata(
        self, feature: ExperimentalFeature
    ) -> None:
        docs = feature.get_documentation()
        assert "**Feature ID**: flash-attention-v1" in docs
        assert "**Version**: 1.0.0" in docs
        assert "**Status**: experimental" in docs

    def test_documentation_contains_paper_section(
        self, feature: ExperimentalFeature
    ) -> None:
        docs = feature.get_documentation()
        assert "## Source Research" in docs
        assert "**Paper**: Flash Attention" in docs
        assert "Tri Dao" in docs and "Daniel Y. Fu" in docs
        assert "**arXiv**: 2106.00001" in docs

    def test_documentation_contains_validation_section(
        self, feature: ExperimentalFeature
    ) -> None:
        docs = feature.get_documentation()
        assert "## Validation" in docs
        assert "**Reproducibility Score**: 96.00%" in docs
        assert "**Validation Passed**: True" in docs

    def test_documentation_contains_performance_section(
        self, feature: ExperimentalFeature
    ) -> None:
        docs = feature.get_documentation()
        assert "## Performance" in docs
        assert "**speedup**: 2.7" in docs

    def test_documentation_contains_compatibility_section(
        self, feature: ExperimentalFeature
    ) -> None:
        docs = feature.get_documentation()
        assert "## Compatibility" in docs
        assert "**kaizen**: >=0.1.0" in docs

    def test_documentation_contains_tags(self, feature: ExperimentalFeature) -> None:
        docs = feature.get_documentation()
        assert "## Tags" in docs
        assert "attention, optimization" in docs

    def test_documentation_falls_back_to_paper_title(self) -> None:
        feature = ExperimentalFeature(
            feature_id="bare",
            paper=_make_paper(),
            validation=_make_validation(),
            signature_class=_MockExecuteSignatureStub,
            version="0.1.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},  # no description, no tags
        )
        docs = feature.get_documentation()
        # When metadata.description is absent, paper.title is the H1.
        assert docs.startswith("# Flash Attention")
        assert "## Tags" not in docs
        assert "## Performance" not in docs
        assert "## Compatibility" not in docs
