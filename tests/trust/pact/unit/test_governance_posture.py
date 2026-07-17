# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""#1779 governance_required posture — core reader/setter/env-resolution +
typed error shape (EATP D6 parity).

Tier-1 unit: pure stdlib, no infra. Covers design-doc acceptance (a) reader/
setter round-trip + env precedence and the invariant that an unrecognized env
value resolves OFF (byte-identical to today).

Env-mutating tests serialize via a module lock per rules/testing.md § "Serialize
Env-Var-Mutating Tests Via Module Lock" — the posture reads a process-global
override AND the KAILASH_GOVERNANCE_REQUIRED env var, both shared surfaces.
"""

from __future__ import annotations

import threading

import pytest

import kailash
from kailash.trust.pact import (
    GOVERNANCE_REQUIRED_ENV_VAR,
    PactError,
    UngovernedEgressRefused,
    is_governance_required,
    set_governance_required,
)

# One lock domain for every test in this file mutating the posture override or
# the env var (rules/testing.md § "One Lock Domain Per Env Surface").
_POSTURE_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=True)
def _serialized_posture(monkeypatch: pytest.MonkeyPatch):
    """Serialize + reset the posture surface around every test."""
    with _POSTURE_ENV_LOCK:
        monkeypatch.delenv(GOVERNANCE_REQUIRED_ENV_VAR, raising=False)
        set_governance_required(None)
        try:
            yield
        finally:
            set_governance_required(None)


def test_default_off() -> None:
    assert is_governance_required() is False
    # Top-level re-export resolves to the same function.
    assert kailash.is_governance_required() is False


def test_programmatic_override_true_then_false_then_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_governance_required(True)
    assert is_governance_required() is True
    set_governance_required(False)
    assert is_governance_required() is False
    # An explicit False override MASKS a truthy env var (most-specific wins).
    monkeypatch.setenv(GOVERNANCE_REQUIRED_ENV_VAR, "1")
    assert is_governance_required() is False
    # Clearing the override falls back to the env var.
    set_governance_required(None)
    assert is_governance_required() is True


@pytest.mark.parametrize("token", ["1", "true", "TRUE", "Yes", "on", " on "])
def test_env_truthy_tokens(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv(GOVERNANCE_REQUIRED_ENV_VAR, token)
    assert is_governance_required() is True


@pytest.mark.parametrize("token", ["0", "false", "no", "off", "", "garbage", "2"])
def test_env_unrecognized_resolves_off(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    # Invariant 2: unrecognized env value => OFF (byte-identical to today).
    monkeypatch.setenv(GOVERNANCE_REQUIRED_ENV_VAR, token)
    assert is_governance_required() is False


def test_override_precedence_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GOVERNANCE_REQUIRED_ENV_VAR, "false")
    set_governance_required(True)  # override beats env
    assert is_governance_required() is True


def test_set_governance_required_rejects_non_bool() -> None:
    with pytest.raises(TypeError):
        set_governance_required("yes")  # type: ignore[arg-type]


def test_ungoverned_egress_refused_shape() -> None:
    err = UngovernedEgressRefused("LlmClient")
    assert isinstance(err, PactError)
    msg = str(err)
    # Names BOTH remedies verbatim (invariant 7: no secret interpolated).
    assert "ungoverned=True" in msg
    assert "GovernedProvider" in msg
    assert "LlmClient" in msg
    # Redteam CRITICAL: must NOT promise install_interceptor governs the
    # four-axis client (it does not); the message discloses the non-coverage.
    assert "install_interceptor(" not in msg
    assert "does NOT govern" in msg
    # Surface name is the only interpolation.
    assert UngovernedEgressRefused("Agent").args[0].count("Agent") >= 1


def test_top_level_exception_reexport_is_same_object() -> None:
    assert kailash.UngovernedEgressRefused is UngovernedEgressRefused
