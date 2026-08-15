# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2069 — ``AgentConfig`` provider resolution must fail CLOSED.

``_detect_provider_from_model`` ended in a terminal ``else: return "openai"``,
so a model no substring matched was dispatched to OpenAI under whatever
credential happened to be configured, and the caller was never told
(``rules/zero-tolerance.md`` Rule 3).

Two defects, not one. The fail-open default is the visible half. The other is
an ORDERING defect: the allowlist gate ran only when ``llm_provider`` was
non-None on entry, i.e. strictly BEFORE the auto-detect assignment, so an
auto-detected provider was structurally un-validatable. It never bit only
because the four literals the substring table could return all happened to sit
in ``VALID_PROVIDERS``.

Both polarities are pinned here: the unresolvable case must RAISE, and the
resolvable cases must keep resolving exactly as before.

A note on the keyless case, because it decides whether these tests can observe
anything at all: the kaizen harness sets ``KAIZEN_ALLOW_KEYLESS_MOCK=1``
(``tests/conftest.py:34``), under which ``detect_provider_from_env`` answers
``"mock"`` rather than ``None``. A fail-closed test that did not clear it would
resolve to ``"mock"`` and pass while proving nothing, so the tests below clear
it AND the provider keys explicitly.
"""

from __future__ import annotations

import pytest

from kaizen.agent_config import AgentConfig

pytestmark = pytest.mark.regression


@pytest.fixture
def keyless_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No provider credential and no keyless-mock opt-in.

    This is the only state in which an unresolvable model can be OBSERVED to
    fail closed; with any of these set, resolution succeeds for an unrelated
    reason and the assertion below would be vacuous.
    """
    monkeypatch.delenv("KAIZEN_ALLOW_KEYLESS_MOCK", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_unknown_model_fails_closed_instead_of_defaulting_to_openai(keyless_env):
    """An unresolvable model must raise, not silently become ``"openai"``.

    This is the #2069 defect proper. Before the fix this returned an
    ``AgentConfig`` whose ``llm_provider`` was ``"openai"``, so a typo'd or
    non-OpenAI model name sent the request — and its prompt content — to the
    wrong vendor.
    """
    with pytest.raises(Exception) as excinfo:
        AgentConfig(model="totally-unregistered-model-xyz")

    # The error must name the model; an error that does not is not actionable.
    assert "totally-unregistered-model-xyz" in str(excinfo.value)


def test_unknown_model_does_not_resolve_to_openai(keyless_env):
    """Stated as its own assertion because it is the exact silent behaviour.

    Kept separate from the raise above: if a future change swaps the exception
    for some other non-raising disposition, this still fails rather than
    quietly accepting a wrong-vendor default.
    """
    try:
        config = AgentConfig(model="totally-unregistered-model-xyz")
    except Exception:
        return  # failing closed is the required behaviour
    pytest.fail(
        f"Unresolvable model silently resolved to {config.llm_provider!r} "
        f"instead of failing closed (#2069)."
    )


def test_explicit_invalid_provider_still_raises():
    """No-false-positive polarity: the explicit path must keep rejecting."""
    with pytest.raises(ValueError, match="Invalid llm_provider"):
        AgentConfig(model="gpt-4", llm_provider="not_a_real_provider")


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4", "openai"),
        ("claude-3-opus-20240229", "anthropic"),
    ],
)
def test_registry_recognised_models_still_resolve(model, expected):
    """No-false-positive polarity: fail-closed must not break what worked.

    These two are resolved by the registry-derived prefix table, so they must
    keep resolving with no credential present and no env fallback consulted.
    """
    assert AgentConfig(model=model).llm_provider == expected


def test_auto_detected_provider_is_validated_by_the_same_gate(monkeypatch):
    """The ORDERING half of #2069.

    The allowlist gate must sit BELOW the auto-detect assignment so both the
    explicit and the auto-detected path pass through it. Before the fix this
    was impossible to express: the gate ran only for a provider supplied on
    entry, so an auto-detected value could never reach it whatever it was.

    Driving it requires a resolver that returns something outside the
    allowlist, which the real one does not do today — that is precisely why
    the hole was invisible.
    """
    import kaizen.core._provider_env as provider_env

    monkeypatch.setattr(
        provider_env,
        "resolve_agent_provider",
        lambda model, component="": "a_provider_not_in_the_allowlist",
    )

    with pytest.raises(ValueError, match="a_provider_not_in_the_allowlist"):
        AgentConfig(model="gpt-4")


def test_valid_providers_covers_every_emittable_provider():
    """``VALID_PROVIDERS`` must never be NARROWER than what resolvers emit.

    Containment, deliberately one-directional. The reverse is left
    unconstrained on purpose: ``mock``, ``ollama``, ``azure`` and friends are
    legitimately dispatchable without owning a model-prefix row, so requiring
    equality would reject them.

    Not DERIVED from the registry, which was measured and rejected: the
    registry is a model-PREFIX table (4 entries) and deriving would drop nine
    dispatchable providers including ``mock`` — which the harness depends on
    — and ``ollama``.
    """
    from kaizen.llm.provider import LlmProvider

    emittable = {p.name for p in LlmProvider.all()} | {  # model-keyed
        "openai",
        "anthropic",
        "mock",
    }  # env-keyed (_provider_env.detect_provider_from_env)

    missing = sorted(emittable - set(AgentConfig.VALID_PROVIDERS))
    assert not missing, (
        f"VALID_PROVIDERS is narrower than what the resolvers can emit: "
        f"{missing}. A provider that can be resolved but not validated makes "
        f"AgentConfig reject its own auto-detected output."
    )
