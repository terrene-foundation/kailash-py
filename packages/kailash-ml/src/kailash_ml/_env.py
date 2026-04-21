# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Store-path resolver for kailash-ml engines.

Single-point authority for every engine's backing-store URL. Consolidates
the priority chain:

1. Explicit kwarg (if non-empty)
2. ``KAILASH_ML_STORE_URL`` env var
3. ``KAILASH_ML_TRACKER_DB`` env var (legacy bridge — one DEBUG log per
   process; raises :class:`EnvVarDeprecatedError` when
   ``KAILASH_ML_STRICT_ENV=1``)
4. Default: ``sqlite:///~/.kailash_ml/ml.db``

Every engine / tracker / registry / feature-store / server in kailash-ml
1.0 MUST call :func:`resolve_store_url` instead of reading env vars
directly. The grep gate at ``rg 'os.environ.get.*KAILASH_ML' src/ | grep
-v '_env.py'`` should return empty.

See ``specs/ml-engines-v2.md §2.1 MUST 1b``.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

from kailash_ml.errors import EnvVarDeprecatedError

__all__ = [
    "resolve_store_url",
    "DEFAULT_STORE_URL",
    "LEGACY_TRACKER_DB_ENV",
    "CANONICAL_STORE_URL_ENV",
    "STRICT_ENV_FLAG",
]


logger = logging.getLogger(__name__)

# Canonical environment variable read by all engines in 1.0+.
CANONICAL_STORE_URL_ENV: str = "KAILASH_ML_STORE_URL"

# Legacy bridge — kailash-ml 0.x tracker stored its DB path under this
# variable. 1.0 still honours it but emits a DEBUG deprecation line on
# first use in the process. Set ``KAILASH_ML_STRICT_ENV=1`` (see
# :data:`STRICT_ENV_FLAG`) to flip the bridge from DEBUG-log to
# :class:`EnvVarDeprecatedError`. The bridge is scheduled for removal in
# kailash-ml 2.0.
LEGACY_TRACKER_DB_ENV: str = "KAILASH_ML_TRACKER_DB"

# Strict-mode flag that promotes legacy env var reads from DEBUG log to
# an ``EnvVarDeprecatedError`` raise. Used in 1.0 by operators who want
# to preemptively fail on 0.x configs before the 2.0 cut.
STRICT_ENV_FLAG: str = "KAILASH_ML_STRICT_ENV"

# 1.0 default store path. ``~`` is expanded by the caller at connection
# time; we return the literal with the tilde so callers can see the
# placeholder in logs without leaking the home directory unintentionally.
DEFAULT_STORE_URL: str = "sqlite:///~/.kailash_ml/ml.db"


# Guard for the "emit DEBUG log exactly once per process" invariant.
# Threading lock is defensive — the debug log is idempotent but the flag
# read-and-set must be atomic to avoid double-emission under concurrent
# ExperimentTracker constructions at import time.
_legacy_log_lock = threading.Lock()
_legacy_log_emitted = False


def _strict_mode_enabled() -> bool:
    return os.environ.get(STRICT_ENV_FLAG, "").strip().lower() in {"1", "true", "yes"}


def _expand_sqlite_tilde(url: str) -> str:
    """Expand ``~`` in sqlite URLs. Non-sqlite URLs pass through unchanged."""
    if not url.startswith("sqlite:///"):
        return url
    path_part = url[len("sqlite:///") :]
    if not path_part.startswith("~"):
        return url
    expanded = str(Path(path_part).expanduser())
    return f"sqlite:///{expanded}"


def resolve_store_url(
    explicit: Optional[str] = None,
    *,
    expand: bool = True,
) -> str:
    """Resolve the backing-store URL for any kailash-ml engine.

    Priority chain (first non-empty wins):

    1. ``explicit`` kwarg (if non-empty)
    2. ``KAILASH_ML_STORE_URL`` env var
    3. ``KAILASH_ML_TRACKER_DB`` env var (legacy — DEBUG log once per
       process; raises :class:`EnvVarDeprecatedError` when
       ``KAILASH_ML_STRICT_ENV=1``)
    4. :data:`DEFAULT_STORE_URL` (``sqlite:///~/.kailash_ml/ml.db``)

    Args:
        explicit: Caller-supplied override. An empty string is treated
            the same as ``None``.
        expand: When ``True`` (default), expand ``~`` in sqlite URLs
            against the caller's home directory. Set ``False`` when the
            caller intends to log the raw URL (e.g. a ``km doctor`` dump
            that should not reveal the home directory).

    Returns:
        The resolved URL string. SQLite URLs with ``~`` are expanded by
        default so downstream DB drivers see an absolute path.

    Raises:
        EnvVarDeprecatedError: When ``KAILASH_ML_STRICT_ENV=1`` is set
            AND the legacy ``KAILASH_ML_TRACKER_DB`` variable is the
            resolved source.
    """
    if explicit:
        return _expand_sqlite_tilde(explicit) if expand else explicit

    canonical = os.environ.get(CANONICAL_STORE_URL_ENV)
    if canonical:
        return _expand_sqlite_tilde(canonical) if expand else canonical

    legacy = os.environ.get(LEGACY_TRACKER_DB_ENV)
    if legacy:
        if _strict_mode_enabled():
            raise EnvVarDeprecatedError(
                reason=(
                    f"{LEGACY_TRACKER_DB_ENV} is deprecated and removed in "
                    f"kailash-ml 2.0; migrate to {CANONICAL_STORE_URL_ENV}. "
                    f"Strict mode ({STRICT_ENV_FLAG}=1) is rejecting this read."
                ),
            )
        global _legacy_log_emitted
        with _legacy_log_lock:
            if not _legacy_log_emitted:
                logger.debug(
                    "kailash_ml.env.tracker_db_legacy",
                    extra={
                        "legacy_var": LEGACY_TRACKER_DB_ENV,
                        "canonical_var": CANONICAL_STORE_URL_ENV,
                        "sunset_version": "2.0",
                    },
                )
                _legacy_log_emitted = True
        return _expand_sqlite_tilde(legacy) if expand else legacy

    return _expand_sqlite_tilde(DEFAULT_STORE_URL) if expand else DEFAULT_STORE_URL


def _reset_legacy_log_state_for_tests() -> None:
    """Reset the once-per-process legacy-log guard.

    Testing-only helper so the precedence matrix can assert the DEBUG
    log fires on a fresh process-equivalent run. Not part of the public
    API — import only from tests.
    """
    global _legacy_log_emitted
    with _legacy_log_lock:
        _legacy_log_emitted = False
