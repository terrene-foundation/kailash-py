"""Provider resolution in ``km.from_brief`` — runnable on CI, no live LLM (#2022).

Why this file exists at all. The three tests that would have caught #2022 are
Tier-3 real-LLM tests that SKIP whenever no model env var is configured, so
they never ran on CI and the defect shipped. It was only visible where a
``.env`` is present — i.e. to the developer or user following the README, which
is the worst possible place to discover it.

These tests exercise the provider-resolution path structurally: they assert on
what ``from_brief`` resolves and on how it fails, without ever reaching a
provider. They run everywhere.
"""

from __future__ import annotations

import polars as pl
import pytest

from kaizen.config.providers import ConfigurationError
from kaizen.core import resolve_agent_provider

KEYLESS_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "KAIZEN_ALLOW_KEYLESS_MOCK",
)


@pytest.fixture
def keyless(monkeypatch):
    for var in KEYLESS_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def frame() -> pl.DataFrame:
    return pl.DataFrame({"age": [31, 44], "spend": [12.5, 88.0], "churned": [0, 1]})


class TestFromBriefResolvesProviderBeforeDispatch:
    """The failure a user hits must name the CONFIGURATION, not the model."""

    def test_unresolvable_provider_raises_configuration_error(self, keyless, frame):
        """Previously: an empty plan, reported as "the LLM emitted a malformed plan"."""
        from kailash_ml.from_brief import from_brief

        with pytest.raises(ConfigurationError) as caught:
            from_brief(
                "predict which customers churn",
                frame,
                model="some-unregistered-local-model",
            )

        message = str(caught.value)
        assert "llm_provider" in message, "must name the kwarg that fixes it"
        assert "kailash_ml.from_brief" in message, "must name the calling component"

    def test_error_is_not_a_brief_interpretation_error(self, keyless, frame):
        """The misattribution itself is the defect — pin it directly."""
        from kailash_ml.from_brief import from_brief

        from kailash._from_brief.exceptions import BriefInterpretationError

        with pytest.raises(ConfigurationError) as caught:
            from_brief("predict churn", frame, model="some-unregistered-local-model")

        assert not isinstance(caught.value, BriefInterpretationError)


class TestResolutionContractUsedByFromBrief:
    """The resolver from_brief depends on, pinned at the ml boundary.

    ``kailash-ml`` reaches kaizen's provider resolution through the PUBLIC
    ``kaizen.core`` surface. A regression that moved or unpublished it would
    fail here rather than at a user's first README run.
    """

    def test_public_surface_is_importable(self):
        from kaizen.core import resolve_agent_provider as public

        assert callable(public)

    def test_model_keyed_resolution_ignores_mismatched_credential(self, keyless):
        keyless.setenv("OPENAI_API_KEY", "sk-test-not-used")
        assert resolve_agent_provider("claude-3-5-haiku") == "anthropic"
