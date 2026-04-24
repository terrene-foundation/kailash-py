# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 tests for ``nexus.context`` ContextVars.

Covers the standalone-vs-request-scope contract per spec
`specs/nexus-ml-integration.md` §§2.1, 2.3, 3. Mocking permitted; no real
HTTP or JWT infrastructure needed for these unit tests.
"""

from __future__ import annotations

import pytest

from nexus.context import (
    _current_actor_id,
    _current_tenant_id,
    get_current_actor_id,
    get_current_tenant_id,
    set_current_actor_id,
    set_current_tenant_id,
)


class TestContextVarDefaults:
    """Fallback-chain item 2: getters return None when no request scope active."""

    def test_get_current_tenant_id_defaults_to_none(self):
        assert get_current_tenant_id() is None

    def test_get_current_actor_id_defaults_to_none(self):
        assert get_current_actor_id() is None


class TestContextVarSetReset:
    """Scope-bound set/reset honours the reset-in-finally invariant of spec §2.2."""

    def test_set_current_tenant_id_then_reset(self):
        assert get_current_tenant_id() is None
        token = set_current_tenant_id("tenant-42")
        try:
            assert get_current_tenant_id() == "tenant-42"
        finally:
            _current_tenant_id.reset(token)
        assert get_current_tenant_id() is None

    def test_set_current_actor_id_then_reset(self):
        assert get_current_actor_id() is None
        token = set_current_actor_id("actor-007")
        try:
            assert get_current_actor_id() == "actor-007"
        finally:
            _current_actor_id.reset(token)
        assert get_current_actor_id() is None

    def test_independent_tenant_and_actor_contexts(self):
        """Tenant and actor are independent ContextVars — setting one
        does not touch the other."""
        t_tok = set_current_tenant_id("tenant-x")
        try:
            assert get_current_tenant_id() == "tenant-x"
            assert get_current_actor_id() is None
            a_tok = set_current_actor_id("actor-y")
            try:
                assert get_current_actor_id() == "actor-y"
                assert get_current_tenant_id() == "tenant-x"
            finally:
                _current_actor_id.reset(a_tok)
            assert get_current_actor_id() is None
            assert get_current_tenant_id() == "tenant-x"
        finally:
            _current_tenant_id.reset(t_tok)

    def test_explicit_none_is_preserved(self):
        """Setting to ``None`` is a valid assignment (JWT claim absent)."""
        t_tok = set_current_tenant_id(None)
        try:
            assert get_current_tenant_id() is None
        finally:
            _current_tenant_id.reset(t_tok)


class TestExceptionResetDiscipline:
    """Spec §2.2 invariant — raised exception inside the scope body MUST
    NOT leak tenant state to the next request on the same worker."""

    def test_exception_in_scope_with_finally_reset(self):
        assert get_current_tenant_id() is None
        with pytest.raises(RuntimeError, match="boom"):
            t = set_current_tenant_id("tenant-leaky")
            try:
                raise RuntimeError("boom")
            finally:
                _current_tenant_id.reset(t)
        # Post-exception: contextvar MUST be None (no cross-request leak)
        assert get_current_tenant_id() is None

    def test_exception_in_scope_with_finally_reset_actor(self):
        assert get_current_actor_id() is None
        with pytest.raises(ValueError, match="boom"):
            t = set_current_actor_id("actor-leaky")
            try:
                raise ValueError("boom")
            finally:
                _current_actor_id.reset(t)
        assert get_current_actor_id() is None
