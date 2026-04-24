# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for kailash_ml._env.resolve_store_url.

Exercises the precedence matrix (explicit / canonical / legacy / default),
the once-per-process DEBUG log for the legacy bridge, and the strict-mode
flag that raises :class:`EnvVarDeprecatedError`.

Env-var isolation follows ``rules/testing.md § Env-Var Test Isolation``:
module-scope :class:`threading.Lock` + function-scope
:func:`monkeypatch.setenv` (pytest-xdist-safe).
"""
from __future__ import annotations

import logging
import threading

import pytest
from kailash_ml._env import (
    CANONICAL_STORE_URL_ENV,
    DEFAULT_STORE_URL,
    LEGACY_TRACKER_DB_ENV,
    STRICT_ENV_FLAG,
    _reset_legacy_log_state_for_tests,
    resolve_store_url,
)
from kailash_ml.errors import EnvVarDeprecatedError

_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=True)
def _serialize_env_tests(monkeypatch):
    """Module-scoped lock + clean env for every test."""
    with _ENV_LOCK:
        monkeypatch.delenv(CANONICAL_STORE_URL_ENV, raising=False)
        monkeypatch.delenv(LEGACY_TRACKER_DB_ENV, raising=False)
        monkeypatch.delenv(STRICT_ENV_FLAG, raising=False)
        _reset_legacy_log_state_for_tests()
        yield
        _reset_legacy_log_state_for_tests()


# --- Precedence matrix (4 cases × present/absent) --------------------


def test_explicit_wins_over_canonical_env(monkeypatch):
    monkeypatch.setenv(CANONICAL_STORE_URL_ENV, "postgresql://db/store")
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    assert resolve_store_url("sqlite:///explicit.db") == "sqlite:///explicit.db"


def test_canonical_env_wins_over_legacy(monkeypatch):
    monkeypatch.setenv(CANONICAL_STORE_URL_ENV, "postgresql://db/canonical")
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    assert resolve_store_url() == "postgresql://db/canonical"


def test_legacy_env_wins_over_default(monkeypatch):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    assert resolve_store_url() == "sqlite:///legacy.db"


def test_default_when_nothing_set():
    # DEFAULT_STORE_URL carries a ``~`` which is expanded by default.
    resolved = resolve_store_url()
    assert resolved.startswith("sqlite:///")
    assert "~" not in resolved  # expanded


def test_default_expansion_can_be_disabled():
    resolved = resolve_store_url(expand=False)
    assert resolved == DEFAULT_STORE_URL
    assert "~" in resolved


# --- Empty / None explicit kwarg treated as absent ------------------


def test_empty_explicit_falls_through_to_canonical(monkeypatch):
    monkeypatch.setenv(CANONICAL_STORE_URL_ENV, "postgresql://db/canonical")
    assert resolve_store_url("") == "postgresql://db/canonical"


def test_none_explicit_falls_through_to_canonical(monkeypatch):
    monkeypatch.setenv(CANONICAL_STORE_URL_ENV, "postgresql://db/canonical")
    assert resolve_store_url(None) == "postgresql://db/canonical"


# --- Legacy bridge DEBUG log (once per process) ---------------------


def test_legacy_emits_debug_log_once(monkeypatch, caplog):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    with caplog.at_level(logging.DEBUG, logger="kailash_ml._env"):
        resolve_store_url()
        resolve_store_url()
        resolve_store_url()
    matches = [
        r for r in caplog.records if r.message == "kailash_ml.env.tracker_db_legacy"
    ]
    assert len(matches) == 1, (
        f"expected exactly 1 legacy DEBUG line, got {len(matches)}. "
        "The once-per-process guard is broken."
    )


def test_legacy_debug_log_carries_sunset_version(monkeypatch, caplog):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    with caplog.at_level(logging.DEBUG, logger="kailash_ml._env"):
        resolve_store_url()
    record = next(
        r for r in caplog.records if r.message == "kailash_ml.env.tracker_db_legacy"
    )
    assert record.sunset_version == "2.0"
    assert record.legacy_var == LEGACY_TRACKER_DB_ENV
    assert record.canonical_var == CANONICAL_STORE_URL_ENV


# --- Strict-mode flag raises typed error ----------------------------


def test_strict_mode_raises_on_legacy_env(monkeypatch):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    monkeypatch.setenv(STRICT_ENV_FLAG, "1")
    with pytest.raises(EnvVarDeprecatedError) as exc:
        resolve_store_url()
    assert LEGACY_TRACKER_DB_ENV in exc.value.reason
    assert CANONICAL_STORE_URL_ENV in exc.value.reason


def test_strict_mode_does_not_fire_on_canonical_env(monkeypatch):
    monkeypatch.setenv(CANONICAL_STORE_URL_ENV, "postgresql://db/canonical")
    monkeypatch.setenv(STRICT_ENV_FLAG, "1")
    # Should NOT raise — canonical env is the 1.0+ path.
    assert resolve_store_url() == "postgresql://db/canonical"


def test_strict_mode_does_not_fire_on_explicit(monkeypatch):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    monkeypatch.setenv(STRICT_ENV_FLAG, "1")
    # Explicit wins over legacy — no legacy read, no strict-mode error.
    assert resolve_store_url("sqlite:///explicit.db") == "sqlite:///explicit.db"


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
def test_strict_mode_flag_truthy_values(monkeypatch, value):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    monkeypatch.setenv(STRICT_ENV_FLAG, value)
    with pytest.raises(EnvVarDeprecatedError):
        resolve_store_url()


@pytest.mark.parametrize("value", ["0", "false", "no", "", "off", "random"])
def test_strict_mode_flag_falsy_values(monkeypatch, value):
    monkeypatch.setenv(LEGACY_TRACKER_DB_ENV, "sqlite:///legacy.db")
    monkeypatch.setenv(STRICT_ENV_FLAG, value)
    # Falsy strict-mode = DEBUG log path, no error.
    resolve_store_url()


# --- SQLite tilde expansion -----------------------------------------


def test_explicit_sqlite_tilde_expands_by_default():
    resolved = resolve_store_url("sqlite:///~/custom/ml.db")
    assert "~" not in resolved
    assert resolved.endswith("/custom/ml.db")


def test_non_sqlite_urls_unchanged():
    assert resolve_store_url("postgresql://db/store") == "postgresql://db/store"
    assert resolve_store_url("mysql://db/store") == "mysql://db/store"


def test_expand_false_preserves_tilde():
    assert resolve_store_url("sqlite:///~/custom/ml.db", expand=False) == (
        "sqlite:///~/custom/ml.db"
    )
