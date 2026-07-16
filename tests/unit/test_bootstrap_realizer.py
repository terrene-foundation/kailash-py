# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the deterministic realizer in ``kailash.bootstrap``.

These tests exercise the structural plumbing of :mod:`kailash.bootstrap`
WITHOUT invoking the LLM:

- :class:`BootstrapConfig` — frozen dataclass contract.
- :data:`ALLOWED_PROFILES` / :data:`ALLOWED_RUNTIMES` /
  :data:`ALLOWED_DEPLOYMENT_TARGETS` — closed enum allowlists.
- :func:`_bootstrap_plan_cls` — lazy Pydantic model construction.
- :func:`_signature_cls` — lazy Kaizen Signature construction.
- :func:`_resolve_llm_model_from_env` — rules/env-models.md priority
  order (OPENAI_PROD_MODEL → DEFAULT_LLM_MODEL → None).
- :func:`_realize_config` — plan-to-BootstrapConfig assembly, including
  env-vs-LLM-suggestion model resolution.
- :func:`bootstrap` profile-allowlist gate — fires BEFORE the LLM call.
- :func:`bootstrap` enum-allowlist gates for ``resolved_runtime`` and
  ``resolved_deployment_target`` (exercised through the realizer
  branch; LLM call substituted via a deterministic stub-agent that
  satisfies the BaseAgent.run() contract).

The LLM-mediated end-to-end path lives in
:mod:`tests.integration.kailash.test_bootstrap` (Tier-2).

Per ``rules/testing.md`` § 3-Tier: Tier-1 covers the deterministic
realizer surface; Tier-2 covers the LLM-mediated pipeline; the two
tiers do NOT overlap (no LLM stubs leak past Tier-1 conftest scope).

Per ``rules/probe-driven-verification.md`` MUST Rule 3: every assertion
here is STRUCTURAL (typed exceptions, frozen dataclass attribute
shapes, enum-membership checks, identity comparisons) — no regex /
keyword / substring matching against semantic claims.

Origin: issue #1125 AC 4 + AC 9 — every NEW module should have direct
test coverage; this file is the structural coverage gate for the
S5 bootstrap realizer helpers (per ``rules/testing.md`` Audit Mode
rule 2).
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

import pytest

from kailash._from_brief.exceptions import BriefInterpretationError

# --------------------------------------------------------------------------- #
# BootstrapConfig dataclass contract                                          #
# --------------------------------------------------------------------------- #


def test_bootstrap_config_is_frozen_dataclass():
    """`BootstrapConfig` is a frozen dataclass — mutation raises."""
    from kailash.bootstrap import BootstrapConfig

    assert dataclasses.is_dataclass(BootstrapConfig)
    cfg = BootstrapConfig(
        db_url="sqlite:///:memory:",
        llm_model="gpt-4o-mini",
        runtime="local",
        deployment_target="dev",
    )
    # frozen=True surfaces as FrozenInstanceError on attribute assignment.
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.db_url = "postgresql://other"  # type: ignore[misc]


def test_bootstrap_config_has_required_fields():
    """`BootstrapConfig` exposes db_url + llm_model + runtime + deployment_target."""
    from kailash.bootstrap import BootstrapConfig

    fields = {f.name for f in dataclasses.fields(BootstrapConfig)}
    assert fields == {
        "db_url",
        "llm_model",
        "runtime",
        "deployment_target",
    }


def test_bootstrap_config_round_trips_field_values():
    """Field values are preserved verbatim through construction."""
    from kailash.bootstrap import BootstrapConfig

    cfg = BootstrapConfig(
        db_url="postgresql://user:pass@host:5432/app",
        llm_model="claude-haiku",
        runtime="async",
        deployment_target="containerized",
    )
    assert cfg.db_url == "postgresql://user:pass@host:5432/app"
    assert cfg.llm_model == "claude-haiku"
    assert cfg.runtime == "async"
    assert cfg.deployment_target == "containerized"


# --------------------------------------------------------------------------- #
# Closed allowlists (Q2 + Q6)                                                 #
# --------------------------------------------------------------------------- #


def test_allowed_profiles_is_closed_set_of_two():
    """`ALLOWED_PROFILES` is exactly {'dev', 'prod'} per Q2."""
    from kailash.bootstrap import ALLOWED_PROFILES

    assert ALLOWED_PROFILES == {"dev", "prod"}


def test_allowed_runtimes_is_closed_set_of_three():
    """`ALLOWED_RUNTIMES` is exactly {'local', 'async', 'nexus'} per Q6."""
    from kailash.bootstrap import ALLOWED_RUNTIMES

    assert ALLOWED_RUNTIMES == {"local", "async", "nexus"}


def test_allowed_deployment_targets_is_closed_set_of_three():
    """`ALLOWED_DEPLOYMENT_TARGETS` is {'dev', 'prod', 'containerized'} per Q6."""
    from kailash.bootstrap import ALLOWED_DEPLOYMENT_TARGETS

    assert ALLOWED_DEPLOYMENT_TARGETS == {"dev", "prod", "containerized"}


# --------------------------------------------------------------------------- #
# Lazy class resolution (PEP 562 __getattr__)                                  #
# --------------------------------------------------------------------------- #


def test_bootstrap_plan_cls_builds_pydantic_subclass():
    """`_bootstrap_plan_cls()` returns a Pydantic model with required fields."""
    from kailash._from_brief.validator import BriefPlan
    from kailash.bootstrap import _bootstrap_plan_cls

    cls = _bootstrap_plan_cls()

    assert issubclass(cls, BriefPlan)
    # Fields surfaced via Pydantic's `model_fields`.
    expected = {
        "interpretation_confidence",
        "resolved_db_url",
        "resolved_llm_model",
        "resolved_runtime",
        "resolved_deployment_target",
    }
    assert expected.issubset(set(cls.model_fields.keys()))


def test_bootstrap_plan_cls_caches_result():
    """`_bootstrap_plan_cls()` returns the same class on repeated calls."""
    from kailash.bootstrap import _bootstrap_plan_cls

    assert _bootstrap_plan_cls() is _bootstrap_plan_cls()


def test_signature_cls_builds_kaizen_signature():
    """`_signature_cls()` returns a Kaizen Signature subclass with fields."""
    # Class B (kaizen-dependent): `_signature_cls()` builds a real Kaizen
    # Signature, which `from kaizen.signatures import ...` requires. kaizen
    # is a downstream optional package absent in the core "Test"/"Base" CI
    # jobs. Per `rules/test-skip-discipline.md` this is an ACCEPTABLE skip
    # (cannot execute without the optional dep), NOT a masked failure — the
    # skip reason names kaizen.
    pytest.importorskip("kaizen")
    from kailash._from_brief.signatures import BriefPlanSignature
    from kailash.bootstrap import _signature_cls

    cls = _signature_cls()

    assert issubclass(cls, BriefPlanSignature)
    # Signature instances should be constructible without error.
    instance = cls()
    assert instance is not None


def test_signature_cls_caches_result():
    """`_signature_cls()` returns the same class on repeated calls."""
    # Class B (kaizen-dependent): `_signature_cls()` builds a real Kaizen
    # Signature. Skip without kaizen per `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    from kailash.bootstrap import _signature_cls

    assert _signature_cls() is _signature_cls()


def test_bootstrap_module_getattr_resolves_lazy_classes():
    """`from kailash.bootstrap import BootstrapPlanSignature` resolves at call-time."""
    # Class B (kaizen-dependent): resolving `BootstrapPlanSignature` calls
    # `_signature_cls()`, which builds a real Kaizen Signature. Skip without
    # kaizen per `rules/test-skip-discipline.md` (`BootstrapPlan` alone is
    # kaizen-free, but this test asserts the Signature resolution too).
    pytest.importorskip("kaizen")
    from kailash.bootstrap import (
        BootstrapPlan,
        BootstrapPlanSignature,
        _bootstrap_plan_cls,
        _signature_cls,
    )

    assert BootstrapPlanSignature is _signature_cls()
    assert BootstrapPlan is _bootstrap_plan_cls()


def test_bootstrap_module_getattr_raises_for_unknown_attr():
    """`kailash.bootstrap.<missing>` raises AttributeError loudly."""
    import kailash.bootstrap as bs

    with pytest.raises(AttributeError, match="no attribute 'NotARealSymbol'"):
        bs.NotARealSymbol  # noqa: B018


def test_kailash_top_level_binds_bootstrap_callable():
    """`kailash.bootstrap` resolves to the callable function (eager top-level binding).

    The submodule `kailash.bootstrap` (the file at src/kailash/bootstrap.py)
    is shadowed at the `kailash` package's namespace level by the eager
    `from kailash.bootstrap import bootstrap` at the bottom of
    `kailash/__init__.py`. The submodule object itself is still reachable
    via `sys.modules["kailash.bootstrap"]` and via the explicit
    `from kailash.bootstrap import <X>` path; only the bare attribute
    `kailash.bootstrap` resolves to the callable. This is the structural
    pattern that makes `kailash.bootstrap(brief, profile)` (issue #1125
    AC 4 verbatim) work as documented.
    """
    import sys

    import kailash
    from kailash.bootstrap import BootstrapConfig
    from kailash.bootstrap import bootstrap as module_bootstrap

    assert callable(kailash.bootstrap)
    assert kailash.bootstrap is module_bootstrap
    assert kailash.BootstrapConfig is BootstrapConfig
    # The submodule object remains in sys.modules so the
    # `from kailash.bootstrap import <X>` paths keep working.
    assert "kailash.bootstrap" in sys.modules


# --------------------------------------------------------------------------- #
# Env-grounded LLM model resolution (rules/env-models.md)                     #
# --------------------------------------------------------------------------- #


def test_resolve_llm_model_returns_none_when_env_unset(monkeypatch):
    """`_resolve_llm_model_from_env()` returns None when both env vars unset."""
    import dotenv

    from kailash.bootstrap import _resolve_llm_model_from_env

    # The resolver calls load_dotenv() internally (bootstrap.py), which would
    # re-read a developer's real .env and re-populate the vars we delete —
    # deleting the env vars alone cannot isolate the test. Neutralize
    # load_dotenv at the source module so the resolver's `from dotenv import
    # load_dotenv` binds the no-op; the delenv then genuinely simulates an
    # unset environment. (Passes in CI where no .env exists; this makes it
    # deterministic locally too, where .env sets OPENAI_PROD_MODEL.)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

    assert _resolve_llm_model_from_env() is None


def test_resolve_llm_model_prefers_openai_prod_model(monkeypatch):
    """`OPENAI_PROD_MODEL` wins over `DEFAULT_LLM_MODEL`."""
    from kailash.bootstrap import _resolve_llm_model_from_env

    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-4o-mini")

    assert _resolve_llm_model_from_env() == "gpt-4o"


def test_resolve_llm_model_falls_back_to_default_llm_model(monkeypatch):
    """When `OPENAI_PROD_MODEL` is unset, `DEFAULT_LLM_MODEL` is used."""
    import dotenv

    from kailash.bootstrap import _resolve_llm_model_from_env

    # Neutralize the resolver's internal load_dotenv so a developer's .env does
    # not re-populate OPENAI_PROD_MODEL after we delete it (see the env-unset
    # test above for the full rationale).
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "claude-haiku")

    assert _resolve_llm_model_from_env() == "claude-haiku"


# --------------------------------------------------------------------------- #
# _realize_config — assembly + env-vs-LLM-suggestion model resolution         #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class _PlanStub:
    """Plan-shaped stand-in for `_realize_config` tests.

    Per ``rules/testing.md`` § Protocol Adapters: this is NOT a mock —
    it is a deterministic adapter satisfying the duck-typed shape
    ``_realize_config`` reads (five attributes). It produces fixed
    output, lives in the test file, and has no external side effects.
    """

    interpretation_confidence: float
    resolved_db_url: str
    resolved_llm_model: str
    resolved_runtime: str
    resolved_deployment_target: str


def test_realize_config_uses_env_model_when_present():
    """When env_llm_model is non-None, env wins over the plan suggestion."""
    from kailash.bootstrap import _realize_config

    plan = _PlanStub(
        interpretation_confidence=0.9,
        resolved_db_url="sqlite:///:memory:",
        resolved_llm_model="claude-haiku",
        resolved_runtime="local",
        resolved_deployment_target="dev",
    )
    cfg = _realize_config(plan, env_llm_model="gpt-4o-mini-env-override")

    assert cfg.llm_model == "gpt-4o-mini-env-override"
    assert cfg.db_url == "sqlite:///:memory:"
    assert cfg.runtime == "local"
    assert cfg.deployment_target == "dev"


def test_realize_config_honors_plan_suggestion_when_env_absent():
    """When env_llm_model is None, the LLM-emitted suggestion is used."""
    from kailash.bootstrap import _realize_config

    plan = _PlanStub(
        interpretation_confidence=0.9,
        resolved_db_url="postgresql://localhost/app",
        resolved_llm_model="gpt-4o-mini-from-llm",
        resolved_runtime="async",
        resolved_deployment_target="prod",
    )
    cfg = _realize_config(plan, env_llm_model=None)

    assert cfg.llm_model == "gpt-4o-mini-from-llm"
    assert cfg.db_url == "postgresql://localhost/app"
    assert cfg.runtime == "async"
    assert cfg.deployment_target == "prod"


def test_realize_config_returns_frozen_instance():
    """The returned config is the frozen dataclass (no mutation possible)."""
    from kailash.bootstrap import BootstrapConfig, _realize_config

    plan = _PlanStub(
        interpretation_confidence=0.9,
        resolved_db_url="sqlite:///:memory:",
        resolved_llm_model="gpt-4o-mini",
        resolved_runtime="local",
        resolved_deployment_target="dev",
    )
    cfg = _realize_config(plan, env_llm_model=None)

    assert isinstance(cfg, BootstrapConfig)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.runtime = "nexus"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Profile-allowlist gate (fires BEFORE the LLM call)                          #
# --------------------------------------------------------------------------- #


def test_bootstrap_rejects_unknown_profile_before_llm_call():
    """An out-of-allowlist profile raises BriefInterpretationError pre-LLM.

    No LLM is invoked: the gate fires structurally before any
    network/LLM-provider call. The raised exception carries
    ``unknown_value="profile=<value>"`` per the typed-error contract.
    """
    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="staging")

    err = exc_info.value
    assert err.unknown_value == "profile=staging"
    assert not err.low_confidence
    assert not err.malformed


def test_bootstrap_rejects_empty_profile():
    """An empty-string profile fails the allowlist."""
    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="")

    assert exc_info.value.unknown_value == "profile="


def test_bootstrap_rejects_arbitrary_unknown_profile():
    """A unique invalid profile fails — `unknown_value` discriminator carries it."""
    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="qa")

    assert exc_info.value.unknown_value == "profile=qa"


# --------------------------------------------------------------------------- #
# Enum-allowlist gates (LLM-emitted values)                                   #
# --------------------------------------------------------------------------- #
#
# These gates run AFTER the LLM call but BEFORE realization. To exercise
# them without an LLM, we monkey-patch the agent factory + signature
# resolver so `bootstrap()` constructs a deterministic stub agent that
# returns the plan dict we want to test against. The stub satisfies the
# Protocol-adapter exception in `rules/testing.md` § 3-Tier (deterministic
# duck-typed adapter; not a mock).


class _StubAgent:
    """Deterministic agent satisfying BaseAgent.run() shape.

    Returns the raw dict it was constructed with. NOT a mock —
    deterministic adapter per ``rules/testing.md`` § Protocol Adapters
    exception. Lives in the test file; no external side effects.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    def run(self, *, brief: str, profile: str) -> dict[str, Any]:
        return self._raw


def _install_stub_agent(monkeypatch, raw: dict[str, Any]) -> None:
    """Wire `_build_agent` to return a stub agent emitting `raw`.

    Also stubs `get_default_llm_model` so the profile-allowlist gate is
    the only structural input the bootstrap pipeline needs from env.

    Uses `sys.modules["kailash.bootstrap"]` (the module object) rather
    than `from kailash import bootstrap` (which now resolves to the
    callable function per the eager top-level binding in
    kailash/__init__.py). The submodule object is what carries
    `_build_agent` as a module-level attribute monkey-patching can
    target.
    """
    import sys

    from kailash._from_brief import signatures as sig_module

    bs_module = sys.modules["kailash.bootstrap"]

    monkeypatch.setattr(
        bs_module, "_build_agent", lambda model, signature: _StubAgent(raw)
    )
    monkeypatch.setattr(
        sig_module, "get_default_llm_model", lambda: "stub-model-for-tier1"
    )


def test_bootstrap_rejects_unknown_runtime_value(monkeypatch):
    """An LLM-emitted `resolved_runtime` outside the allowlist raises."""
    # Class B (kaizen-dependent): the enum gate runs AFTER the LLM call, so
    # `bootstrap()` reaches `_signature_cls()` (builds a real Kaizen
    # Signature) and `_install_stub_agent` imports `kailash._from_brief.
    # signatures` (which `from kaizen.signatures import ...` requires)
    # BEFORE the gate fires. kaizen is a downstream optional package absent
    # in the core CI jobs. Skip without it per `rules/test-skip-discipline.md`
    # (acceptable skip — the enum gate cannot be exercised through the full
    # pipeline without the LLM-mediation surface kaizen provides).
    pytest.importorskip("kaizen")
    _install_stub_agent(
        monkeypatch,
        {
            "interpretation_confidence": 0.9,
            "resolved_db_url": "sqlite:///:memory:",
            "resolved_llm_model": "gpt-4o-mini",
            "resolved_runtime": "spark",  # not in {local, async, nexus}
            "resolved_deployment_target": "dev",
        },
    )
    # Also clear env so the env-resolution branch doesn't accidentally
    # populate the model field with a real .env value.
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="dev")

    err = exc_info.value
    assert err.unknown_value == "runtime=spark"
    assert not err.low_confidence
    assert not err.malformed


def test_bootstrap_rejects_unknown_deployment_target_value(monkeypatch):
    """An LLM-emitted `resolved_deployment_target` outside the allowlist raises."""
    # Class B (kaizen-dependent): same as the runtime-enum test — the gate
    # runs after `_signature_cls()`/`_install_stub_agent` reach kaizen.
    # Skip without kaizen per `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    _install_stub_agent(
        monkeypatch,
        {
            "interpretation_confidence": 0.9,
            "resolved_db_url": "sqlite:///:memory:",
            "resolved_llm_model": "gpt-4o-mini",
            "resolved_runtime": "local",
            "resolved_deployment_target": "edge",  # not in {dev, prod, containerized}
        },
    )
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="dev")

    assert exc_info.value.unknown_value == "deployment_target=edge"


def test_bootstrap_rejects_low_confidence(monkeypatch):
    """A confidence below the threshold raises low_confidence=True."""
    # Class B (kaizen-dependent): this exercises the LLM-PRODUCED plan
    # through the full `bootstrap()` pipeline via the stub agent — it does
    # NOT construct a plan object and call the validator directly. The
    # pipeline reaches `_signature_cls()` (real Kaizen Signature) and
    # `_install_stub_agent` imports `kailash._from_brief.signatures` before
    # the confidence gate fires. Skip without kaizen per
    # `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    _install_stub_agent(
        monkeypatch,
        {
            "interpretation_confidence": 0.3,  # below 0.6 floor
            "resolved_db_url": "sqlite:///:memory:",
            "resolved_llm_model": "gpt-4o-mini",
            "resolved_runtime": "local",
            "resolved_deployment_target": "dev",
        },
    )
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="dev")

    assert exc_info.value.low_confidence is True


def test_bootstrap_rejects_malformed_plan(monkeypatch):
    """A plan missing required fields raises malformed=True."""
    # Class B (kaizen-dependent): exercises the LLM-PRODUCED plan through
    # the full `bootstrap()` pipeline via the stub agent (not a direct
    # validator call). Reaches `_signature_cls()` + the `signatures` import
    # before the malformed-plan gate fires. Skip without kaizen per
    # `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    _install_stub_agent(
        monkeypatch,
        {
            "interpretation_confidence": 0.9,
            "resolved_db_url": "sqlite:///:memory:",
            # resolved_llm_model intentionally absent
            "resolved_runtime": "local",
            "resolved_deployment_target": "dev",
        },
    )
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

    from kailash.bootstrap import bootstrap

    with pytest.raises(BriefInterpretationError) as exc_info:
        bootstrap(brief="any brief", profile="dev")

    assert exc_info.value.malformed is True


# --------------------------------------------------------------------------- #
# Happy path through the stub (full pipeline minus LLM)                       #
# --------------------------------------------------------------------------- #


def test_bootstrap_returns_config_with_env_model_override(monkeypatch):
    """End-to-end through stub: env-resolved model wins over LLM suggestion."""
    # Class B (kaizen-dependent): full `bootstrap()` happy path through the
    # stub agent reaches `_signature_cls()` (real Kaizen Signature) +
    # `_install_stub_agent`'s `signatures` import. Skip without kaizen per
    # `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    _install_stub_agent(
        monkeypatch,
        {
            "interpretation_confidence": 0.9,
            "resolved_db_url": "sqlite:///:memory:",
            "resolved_llm_model": "claude-haiku-from-llm",
            "resolved_runtime": "local",
            "resolved_deployment_target": "dev",
        },
    )
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-env-pick")

    from kailash.bootstrap import BootstrapConfig, bootstrap

    cfg = bootstrap(brief="a dev workflow that reads CSV", profile="dev")

    assert isinstance(cfg, BootstrapConfig)
    assert cfg.db_url == "sqlite:///:memory:"
    assert cfg.llm_model == "gpt-4o-env-pick"  # env wins per env-models.md
    assert cfg.runtime == "local"
    assert cfg.deployment_target == "dev"


def test_bootstrap_returns_config_honoring_llm_suggestion_when_env_clear(monkeypatch):
    """When env is clear, the LLM-emitted model suggestion populates llm_model."""
    # Class B (kaizen-dependent): full `bootstrap()` happy path through the
    # stub agent reaches `_signature_cls()` + the `signatures` import. Skip
    # without kaizen per `rules/test-skip-discipline.md`.
    pytest.importorskip("kaizen")
    _install_stub_agent(
        monkeypatch,
        {
            "interpretation_confidence": 0.95,
            "resolved_db_url": "postgresql://localhost/app",
            "resolved_llm_model": "claude-haiku-suggestion",
            "resolved_runtime": "async",
            "resolved_deployment_target": "prod",
        },
    )
    # Neutralize the resolver's internal load_dotenv so a developer's .env does
    # not re-populate the model vars after we clear them (see the env-unset
    # test above for the full rationale).
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

    from kailash.bootstrap import bootstrap

    cfg = bootstrap(brief="a prod API", profile="prod")

    assert cfg.llm_model == "claude-haiku-suggestion"
    assert cfg.db_url == "postgresql://localhost/app"
    assert cfg.runtime == "async"
    assert cfg.deployment_target == "prod"
