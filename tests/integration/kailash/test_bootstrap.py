# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for ``kailash.bootstrap()`` — issue #1125 AC 4 + AC 9.

These tests hit a real LLM endpoint via :func:`os.environ`-configured
``DEFAULT_LLM_MODEL`` (or ``OPENAI_PROD_MODEL``) per
``rules/env-models.md`` and ``rules/testing.md`` § "Tier 2 (Integration):
Real infrastructure recommended" — NO MOCKING.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression Above Unit +
Integration", every canonical pipeline the docs teach MUST have a Tier-2+
regression test executing DOCS-EXACT code against real infra; this file
is the regression surface for the issue #1125 AC 4 documented call
``kailash.bootstrap(brief, profile='dev')``.

## Probe shape

The tests assert STRUCTURAL properties (per
``rules/probe-driven-verification.md`` Rule 3 — structural probes when
LLM-judge is unavailable in CI):

- ``isinstance(result, BootstrapConfig)`` — return-type contract.
- ``result.runtime in ALLOWED_RUNTIMES`` — enum-allowlist membership.
- ``result.deployment_target in ALLOWED_DEPLOYMENT_TARGETS`` — same.
- ``result.db_url`` and ``result.llm_model`` are non-empty strings.
- When env is set, ``result.llm_model`` equals the env-resolved value
  (the AC 9 env-resolution invariant — env wins over LLM suggestion).
- For the invalid-profile path: :class:`BriefInterpretationError` raised
  with ``unknown_value="profile=<value>"`` — fires BEFORE the LLM call.

The tests intentionally do NOT regex-match the LLM's prose (per
``rules/probe-driven-verification.md`` MUST-1 — semantic verification
MUST be probe-driven, not regex/keyword); they assert SHAPE, not exact
LLM-emitted byte values. Two profile shapes cover AC 4 + AC 9: dev,
prod. The invalid-profile case is a Tier-2-flavored structural test
(no LLM consumed; the profile gate fires before any LLM call) but lives
here for parity with the sibling-shard error-path coverage.

## CI cost note

Each LLM-dependent test invokes one LLM completion against
``DEFAULT_LLM_MODEL``. Typical per-PR run cost across 2 LLM tests:
~2 LLM completions at the cheapest small-model tier (cents range).
Tests SKIP cleanly when DEFAULT_LLM_MODEL or the matched API key is
unset, per ``rules/test-skip-discipline.md`` § "acceptable skip with
explicit reason citing the missing env var".

## Env-var serialization

The two LLM tests both READ ``OPENAI_PROD_MODEL`` / ``DEFAULT_LLM_MODEL``
to assert the env-resolution invariant — they do NOT mutate env, so the
module-scope ``threading.Lock`` pattern from ``rules/testing.md`` §
"Serialize Env-Var-Mutating Tests" is not required here.

Origin: issue #1125 AC 4 + AC 9 — Tier-2 tests covering ≥2 profile
shapes against real LLM endpoint with env-driven model resolution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

# Marker pair per the shard plan: @pytest.mark.regression for tracking,
# @pytest.mark.integration for the no-mocking discipline gate.
pytestmark = [pytest.mark.regression, pytest.mark.integration]


FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "regression"
    / "from_brief"
    / "fixtures"
)


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a YAML fixture from the from_brief regression fixture dir.

    Args:
        name: Filename relative to :data:`FIXTURE_DIR` (e.g.
            ``"bootstrap_dev.yaml"``).

    Returns:
        The parsed YAML dict.
    """
    path = FIXTURE_DIR / name
    return yaml.safe_load(path.read_text())


def _has_llm_env() -> bool:
    """Return ``True`` when the required LLM env vars are set.

    Per ``rules/env-models.md``, the model name comes from
    ``DEFAULT_LLM_MODEL`` (or ``OPENAI_PROD_MODEL``) and the matching
    API key MUST be present for the model's provider prefix. The
    Tier-2 gate is "real LLM endpoint reachable" — when env is unset,
    the tests SKIP (per ``rules/test-skip-discipline.md`` — acceptable
    skip with explicit reason citing the missing env var).
    """
    model = os.environ.get("DEFAULT_LLM_MODEL") or os.environ.get("OPENAI_PROD_MODEL")
    if not model:
        return False
    lower = model.lower()
    if lower.startswith(("gpt", "o1", "o3", "o4")):
        return bool(os.environ.get("OPENAI_API_KEY"))
    if lower.startswith("claude"):
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if lower.startswith("gemini"):
        return bool(
            os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        )
    # Other providers: optimistic — assume key is present if model is set.
    return True


_LLM_AVAILABLE_REASON = (
    "Tier-2 LLM probe requires DEFAULT_LLM_MODEL (or OPENAI_PROD_MODEL) plus "
    "the matching API key per rules/env-models.md model-key pairing table."
)


# --------------------------------------------------------------------------- #
# Test 1 — dev profile: kailash.bootstrap(brief, profile='dev') round-trip   #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _has_llm_env(), reason=_LLM_AVAILABLE_REASON)
def test_bootstrap_dev_profile_returns_resolved_config():
    """AC 4: ``kailash.bootstrap(brief, profile='dev')`` returns a BootstrapConfig.

    Asserts the foundational contract the issue brief asserts in AC 4:
    the returned object is a :class:`BootstrapConfig` whose four
    fields are populated consistent with the dev profile. Asserts
    STRUCTURAL invariants only (per probe-driven-verification.md
    Rule 3) — enum membership, non-empty strings, and AC 9
    env-resolution invariant.
    """
    import kailash
    from kailash.bootstrap import (
        ALLOWED_DEPLOYMENT_TARGETS,
        ALLOWED_RUNTIMES,
        BootstrapConfig,
    )

    fixture = _load_fixture("bootstrap_dev.yaml")
    config = kailash.bootstrap(fixture["brief"], profile=fixture["profile"])

    # Probe 1 — return-type contract (structural, deterministic).
    assert isinstance(config, BootstrapConfig), (
        f"kailash.bootstrap MUST return BootstrapConfig, got "
        f"{type(config).__name__}"
    )

    # Probe 2 — closed-allowlist membership for the two enum fields.
    assert config.runtime in ALLOWED_RUNTIMES, (
        f"resolved runtime {config.runtime!r} not in allowlist "
        f"{sorted(ALLOWED_RUNTIMES)!r}"
    )
    assert config.deployment_target in ALLOWED_DEPLOYMENT_TARGETS, (
        f"resolved deployment_target {config.deployment_target!r} not in "
        f"allowlist {sorted(ALLOWED_DEPLOYMENT_TARGETS)!r}"
    )

    # Probe 3 — non-empty string fields.
    assert (
        isinstance(config.db_url, str) and config.db_url
    ), f"resolved db_url MUST be non-empty string; got {config.db_url!r}"
    assert (
        isinstance(config.llm_model, str) and config.llm_model
    ), f"resolved llm_model MUST be non-empty string; got {config.llm_model!r}"

    # Probe 4 — AC 9 env-resolution invariant: when env is set, the
    # env value MUST win over any LLM-emitted suggestion.
    env_model = os.environ.get("OPENAI_PROD_MODEL") or os.environ.get(
        "DEFAULT_LLM_MODEL"
    )
    if env_model:
        assert config.llm_model == env_model, (
            f"AC 9 violation: env-resolved llm_model is {env_model!r} but "
            f"config.llm_model is {config.llm_model!r}; env MUST win "
            f"per rules/env-models.md"
        )


# --------------------------------------------------------------------------- #
# Test 2 — prod profile: kailash.bootstrap(brief, profile='prod') round-trip #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _has_llm_env(), reason=_LLM_AVAILABLE_REASON)
def test_bootstrap_prod_profile_returns_resolved_config():
    """AC 4: ``kailash.bootstrap(brief, profile='prod')`` returns a BootstrapConfig.

    Mirrors Test 1 for the prod profile. The brief explicitly mentions
    Postgres + Kubernetes containerization, so the LLM is expected to
    pick a runtime and deployment_target reflecting that production
    shape — but the probe asserts ENUM MEMBERSHIP only, not exact
    values (the LLM may legitimately interpret the brief differently).
    """
    import kailash
    from kailash.bootstrap import (
        ALLOWED_DEPLOYMENT_TARGETS,
        ALLOWED_RUNTIMES,
        BootstrapConfig,
    )

    fixture = _load_fixture("bootstrap_prod.yaml")
    config = kailash.bootstrap(fixture["brief"], profile=fixture["profile"])

    # Probe 1 — return-type contract.
    assert isinstance(config, BootstrapConfig)

    # Probe 2 — enum-allowlist membership for both enum fields.
    assert config.runtime in ALLOWED_RUNTIMES, (
        f"resolved runtime {config.runtime!r} not in allowlist "
        f"{sorted(ALLOWED_RUNTIMES)!r}"
    )
    assert config.deployment_target in ALLOWED_DEPLOYMENT_TARGETS, (
        f"resolved deployment_target {config.deployment_target!r} not in "
        f"allowlist {sorted(ALLOWED_DEPLOYMENT_TARGETS)!r}"
    )

    # Probe 3 — non-empty string fields.
    assert isinstance(config.db_url, str) and config.db_url
    assert isinstance(config.llm_model, str) and config.llm_model

    # Probe 4 — AC 9 env-resolution invariant (env wins over LLM suggestion).
    env_model = os.environ.get("OPENAI_PROD_MODEL") or os.environ.get(
        "DEFAULT_LLM_MODEL"
    )
    if env_model:
        assert config.llm_model == env_model


# --------------------------------------------------------------------------- #
# Test 3 — error path: invalid profile raises typed exception (no LLM cost)  #
# --------------------------------------------------------------------------- #


def test_bootstrap_invalid_profile_raises_before_llm_call():
    """An invalid profile raises BriefInterpretationError BEFORE any LLM call.

    Lives in the Tier-2 test file for parity with the sibling-shard
    error-path coverage (S2 / S3 / S4 each have an error-path test
    next to their happy-path tests). The profile-allowlist gate is
    STRUCTURAL (input validation per agent-reasoning.md § "Permitted
    Deterministic Logic" exception 1), so this test runs without an
    LLM endpoint — no @pytest.mark.skipif gate.

    Verifies the typed-discriminator contract: the raised exception
    carries ``unknown_value="profile=<value>"`` so callers can branch
    on the failure mode without parsing the message string.
    """
    import kailash
    from kailash._from_brief.exceptions import BriefInterpretationError

    with pytest.raises(BriefInterpretationError) as exc_info:
        kailash.bootstrap("any brief", profile="staging")

    err = exc_info.value
    # The profile gate identifies the failure mode via unknown_value.
    assert err.unknown_value == "profile=staging", (
        f"profile-allowlist gate MUST set unknown_value='profile=<value>'; "
        f"got unknown_value={err.unknown_value!r}"
    )
    # And does NOT set the other two discriminators.
    assert not err.low_confidence
    assert not err.malformed
