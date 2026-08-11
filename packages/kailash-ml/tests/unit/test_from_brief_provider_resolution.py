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
        """The misattribution itself is the defect — pin it directly.

        Asserted via ``pytest.raises(Exception)`` plus an explicit type check,
        NOT via ``pytest.raises(ConfigurationError)``: the latter would make the
        isinstance assertion vacuous, since ConfigurationError can never be a
        BriefInterpretationError by MRO. Written this way the test genuinely
        discriminates — it reddens if the swallow returns and the empty plan is
        rejected downstream as malformed model output, which is the exact
        pre-fix behaviour.
        """
        from kailash_ml.from_brief import from_brief

        from kailash._from_brief.exceptions import BriefInterpretationError

        with pytest.raises(Exception) as caught:
            from_brief("predict churn", frame, model="some-unregistered-local-model")

        assert not isinstance(
            caught.value, BriefInterpretationError
        ), "a configuration failure was reported as a malformed-plan failure"
        assert isinstance(caught.value, ConfigurationError)


class TestExplicitProviderPassthrough:
    """``llm_provider=`` is the escape hatch the error message names.

    Without this parameter the advice "pass llm_provider= explicitly" was
    un-followable from ``from_brief`` — the kwarg did not exist.
    """

    def test_explicit_provider_bypasses_resolution(self, keyless, frame):
        """An unregistered model + explicit provider must NOT raise at resolution."""
        from kailash_ml.from_brief import from_brief

        try:
            from_brief(
                "predict churn",
                frame,
                model="some-unregistered-local-model",
                llm_provider="ollama",
            )
        except ConfigurationError as exc:  # pragma: no cover - regression guard
            pytest.fail(f"explicit llm_provider should bypass resolution: {exc}")
        except Exception:
            # Any LATER failure (no Ollama running, plan validation, ...) is
            # fine and expected here — this test pins only that provider
            # resolution no longer rejects the call.
            pass


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
