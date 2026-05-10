# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: default-queue Redis-list-key byte-compat (#911 Shard 1).

Pins the legacy ``_QUEUE_KEY = "kailash:tasks:pending"`` constant and
the helper-derived default key. If a future refactor changes either
side, this test fails LOUDLY before any production user is affected.

Same failure-mode class as ``zero-tolerance.md`` Rule 6a public-API
removal without deprecation cycle: a byte-shape change to the default
Redis list key orphans every in-flight task on first deploy.
"""

from __future__ import annotations

import pytest

from kailash.runtime._queue_keys import DEFAULT_QUEUE_NAME, make_queue_key
from kailash.runtime.distributed import _QUEUE_KEY


@pytest.mark.regression
def test_default_queue_key_is_legacy_byte_string() -> None:
    """The legacy single-queue Redis list key MUST stay byte-identical."""
    assert _QUEUE_KEY == "kailash:tasks:pending"


@pytest.mark.regression
def test_make_queue_key_default_matches_legacy_constant() -> None:
    """``make_queue_key("default")`` MUST equal the legacy ``_QUEUE_KEY``."""
    assert make_queue_key(DEFAULT_QUEUE_NAME) == _QUEUE_KEY
    assert make_queue_key("default") == "kailash:tasks:pending"


@pytest.mark.regression
def test_make_queue_key_default_no_suffix() -> None:
    """The default queue MUST NOT get the ``:default`` suffix.

    The asymmetry (default → no suffix; non-default → suffix) is the
    load-bearing back-compat invariant for #911 Shard 1. If a refactor
    makes the default-queue key ``"kailash:tasks:pending:default"``,
    every existing single-queue deployment orphans on upgrade.
    """
    key = make_queue_key("default")
    assert not key.endswith(":default")
    assert key == "kailash:tasks:pending"


@pytest.mark.regression
def test_non_default_queue_gets_suffix() -> None:
    """Non-default queues MUST get ``:<name>`` to namespace cleanly."""
    assert make_queue_key("fast") == "kailash:tasks:pending:fast"
    assert make_queue_key("slow") == "kailash:tasks:pending:slow"
