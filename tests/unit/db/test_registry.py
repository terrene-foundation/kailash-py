# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for URL resolution registry functions.

Tests cover:
- resolve_database_url() priority: KAILASH_DATABASE_URL > DATABASE_URL > None
- resolve_queue_url() priority: KAILASH_QUEUE_URL > None
- Environment variable isolation (tests do not leak state)
"""

from __future__ import annotations

import os

import pytest

from kailash.db.registry import resolve_database_url, resolve_queue_url


# ---------------------------------------------------------------------------
# resolve_database_url
# ---------------------------------------------------------------------------
class TestResolveDatabaseUrl:
    def test_kailash_database_url_takes_priority(self, monkeypatch):
        monkeypatch.setenv("KAILASH_DATABASE_URL", "postgresql://kailash")
        monkeypatch.setenv("DATABASE_URL", "postgresql://generic")
        assert resolve_database_url() == "postgresql://kailash"

    def test_falls_back_to_database_url(self, monkeypatch):
        monkeypatch.delenv("KAILASH_DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://generic")
        assert resolve_database_url() == "postgresql://generic"

    def test_returns_none_when_neither_set(self, monkeypatch):
        monkeypatch.delenv("KAILASH_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert resolve_database_url() is None

    def test_empty_kailash_url_falls_through(self, monkeypatch):
        """Empty string is falsy; should fall through to DATABASE_URL."""
        monkeypatch.setenv("KAILASH_DATABASE_URL", "")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///fallback.db")
        assert resolve_database_url() == "sqlite:///fallback.db"

    def test_both_empty_returns_none(self, monkeypatch):
        monkeypatch.setenv("KAILASH_DATABASE_URL", "")
        monkeypatch.setenv("DATABASE_URL", "")
        assert resolve_database_url() is None


# ---------------------------------------------------------------------------
# resolve_queue_url
# ---------------------------------------------------------------------------
class TestResolveQueueUrl:
    def test_returns_queue_url_when_set(self, monkeypatch):
        monkeypatch.setenv("KAILASH_QUEUE_URL", "postgresql://queue")
        assert resolve_queue_url() == "postgresql://queue"

    def test_returns_none_when_not_set(self, monkeypatch):
        monkeypatch.delenv("KAILASH_QUEUE_URL", raising=False)
        assert resolve_queue_url() is None

    def test_empty_returns_none(self, monkeypatch):
        monkeypatch.setenv("KAILASH_QUEUE_URL", "")
        assert resolve_queue_url() is None
