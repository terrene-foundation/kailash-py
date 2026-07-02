# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for disclosure-trace tokens (issue #1482).

Covers:
- Deterministic derivation: same (recipient, resource, session) -> same token.
- Different recipient / resource / session -> different token.
- One-way / keyed: token is HMAC, requires the server key.
- Reverse lookup returns the correct recipient (keyed store, not inversion).
- Token bound to the audit record (metadata participates in the Merkle hash).
- Server key must be injected; empty key fail-closes; from_env fail-closes.

Tier 1 (real HMAC, InMemory audit store — no mocking of crypto).
"""

from __future__ import annotations

import base64
import os

import pytest

from kailash.trust.audit_store import AuditEventType, InMemoryAuditStore
from kailash.trust.disclosure import (
    DisclosureError,
    DisclosureRecord,
    DisclosureTracer,
    InMemoryDisclosureStore,
)
from kailash.trust.signing import derive_trace_token
from kailash.trust.signing.derivation import derive_trace_token as derive_via_module

_KEY = b"server-held-32-byte-secret-key!!"
_KEY2 = b"a-completely-different-server-key"


# ---------------------------------------------------------------------------
# derive_trace_token — determinism / distinctness / keyed one-way
# ---------------------------------------------------------------------------


class TestDeriveTraceToken:
    def test_deterministic_same_inputs(self):
        t1 = derive_trace_token(_KEY, "user-42", "report-1", "sess-a")
        t2 = derive_trace_token(_KEY, "user-42", "report-1", "sess-a")
        assert t1 == t2
        assert len(t1) == 64  # SHA-256 hex

    def test_different_recipient_different_token(self):
        t1 = derive_trace_token(_KEY, "user-42", "report-1", "sess-a")
        t2 = derive_trace_token(_KEY, "user-99", "report-1", "sess-a")
        assert t1 != t2

    def test_different_resource_different_token(self):
        t1 = derive_trace_token(_KEY, "user-42", "report-1", "sess-a")
        t2 = derive_trace_token(_KEY, "user-42", "report-2", "sess-a")
        assert t1 != t2

    def test_different_session_different_token(self):
        t1 = derive_trace_token(_KEY, "user-42", "report-1", "sess-a")
        t2 = derive_trace_token(_KEY, "user-42", "report-1", "sess-b")
        assert t1 != t2

    def test_different_key_different_token(self):
        t1 = derive_trace_token(_KEY, "user-42", "report-1", "sess-a")
        t2 = derive_trace_token(_KEY2, "user-42", "report-1", "sess-a")
        assert t1 != t2

    def test_field_boundaries_unambiguous(self):
        # ("ab","c",..) must not collide with ("a","bc",..).
        assert derive_trace_token(_KEY, "ab", "c", "s") != derive_trace_token(
            _KEY, "a", "bc", "s"
        )

    def test_empty_key_fail_closed(self):
        with pytest.raises(ValueError):
            derive_trace_token(b"", "user-42", "report-1", "sess-a")

    def test_non_bytes_key_type_error(self):
        with pytest.raises(TypeError):
            derive_trace_token("not-bytes", "u", "r", "s")  # type: ignore[arg-type]

    def test_signing_reexport_is_same_function(self):
        assert derive_trace_token is derive_via_module


# ---------------------------------------------------------------------------
# InMemoryDisclosureStore — keyed reverse store
# ---------------------------------------------------------------------------


class TestInMemoryDisclosureStore:
    @pytest.mark.asyncio
    async def test_put_get_roundtrip(self):
        store = InMemoryDisclosureStore()
        rec = DisclosureRecord(
            trace_token="tok",
            recipient="user-42",
            resource="r",
            session="s",
            event_id="evt-1",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        await store.put(rec)
        assert (await store.get("tok")) == rec
        assert (await store.get("missing")) is None

    @pytest.mark.asyncio
    async def test_idempotent_overwrite_does_not_grow(self):
        store = InMemoryDisclosureStore()
        rec = DisclosureRecord(
            trace_token="tok",
            recipient="u",
            resource="r",
            session="s",
            event_id="e1",
            timestamp="t",
        )
        await store.put(rec)
        await store.put(rec)
        assert store.count == 1


# ---------------------------------------------------------------------------
# DisclosureTracer — record + reverse lookup + audit binding
# ---------------------------------------------------------------------------


class TestDisclosureTracer:
    @pytest.mark.asyncio
    async def test_record_returns_token_and_binds_audit_event(self):
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        event, token = await tracer.record_disclosure(
            recipient="user-42", resource="report-1", session="sess-a", actor="agent-x"
        )
        # Token bound to the audit record: it lives in metadata, which is part
        # of the Merkle hash, so verify_integrity confirms the binding.
        assert event.metadata["trace_token"] == token
        assert event.action == AuditEventType.DISCLOSURE.value
        assert event.resource == "report-1"
        assert event.actor == "agent-x"
        assert event.verify_integrity() is True
        # Tampering the token in metadata would break the hash (bound).
        assert token == derive_trace_token(_KEY, "user-42", "report-1", "sess-a")

    @pytest.mark.asyncio
    async def test_reverse_lookup_returns_recipient(self):
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        _, token = await tracer.record_disclosure(
            recipient="user-42", resource="report-1", session="sess-a"
        )
        assert (await tracer.lookup_recipient(token)) == "user-42"
        rec = await tracer.lookup(token)
        assert rec is not None
        assert rec.recipient == "user-42"
        assert rec.resource == "report-1"
        assert rec.session == "sess-a"

    @pytest.mark.asyncio
    async def test_reverse_lookup_unknown_token_none(self):
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        assert (await tracer.lookup_recipient("deadbeef")) is None
        assert (await tracer.lookup("deadbeef")) is None

    @pytest.mark.asyncio
    async def test_distinct_recipients_distinct_tokens_and_lookups(self):
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        _, tok_a = await tracer.record_disclosure(
            recipient="alice", resource="r", session="s"
        )
        _, tok_b = await tracer.record_disclosure(
            recipient="bob", resource="r", session="s"
        )
        assert tok_a != tok_b
        assert (await tracer.lookup_recipient(tok_a)) == "alice"
        assert (await tracer.lookup_recipient(tok_b)) == "bob"

    @pytest.mark.asyncio
    async def test_recipient_not_written_into_audit_event(self):
        # Attribution data (recipient) stays in the server-side keyed store,
        # NOT the audit event that could be co-located with the served artifact.
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        event, _ = await tracer.record_disclosure(
            recipient="secret-recipient", resource="r", session="s"
        )
        assert "secret-recipient" not in str(event.to_dict())

    @pytest.mark.asyncio
    async def test_reserved_metadata_key_rejected(self):
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        with pytest.raises(DisclosureError):
            await tracer.record_disclosure(
                recipient="u",
                resource="r",
                session="s",
                metadata={"trace_token": "forged"},
            )

    @pytest.mark.asyncio
    async def test_audit_chain_intact_after_records(self):
        audit = InMemoryAuditStore()
        tracer = DisclosureTracer(_KEY, audit)
        for i in range(3):
            await tracer.record_disclosure(recipient=f"u{i}", resource="r", session="s")
        assert await audit.verify_chain() is True

    @pytest.mark.asyncio
    async def test_unsupported_audit_store_fail_closed(self):
        class _Bogus:
            pass

        tracer = DisclosureTracer(_KEY, _Bogus())
        with pytest.raises(DisclosureError):
            await tracer.record_disclosure(recipient="u", resource="r", session="s")


# ---------------------------------------------------------------------------
# Server-key injection
# ---------------------------------------------------------------------------


class TestServerKeyInjection:
    def test_empty_key_fail_closed(self):
        with pytest.raises(DisclosureError):
            DisclosureTracer(b"", InMemoryAuditStore())

    def test_non_bytes_key_type_error(self):
        with pytest.raises(TypeError):
            DisclosureTracer("literal", InMemoryAuditStore())  # type: ignore[arg-type]

    def test_from_env_reads_base64_key(self, monkeypatch):
        monkeypatch.setenv(
            "KAILASH_DISCLOSURE_TRACE_KEY_TEST",
            base64.b64encode(_KEY).decode("ascii"),
        )
        tracer = DisclosureTracer.from_env(
            "KAILASH_DISCLOSURE_TRACE_KEY_TEST", InMemoryAuditStore()
        )
        # Uses the decoded key: token matches a direct derive.
        assert tracer.derive_token("u", "r", "s") == derive_trace_token(
            _KEY, "u", "r", "s"
        )

    def test_from_env_missing_fail_closed(self, monkeypatch):
        monkeypatch.delenv("KAILASH_DISCLOSURE_MISSING", raising=False)
        with pytest.raises(DisclosureError):
            DisclosureTracer.from_env(
                "KAILASH_DISCLOSURE_MISSING", InMemoryAuditStore()
            )

    def test_from_env_invalid_base64_fail_closed(self, monkeypatch):
        monkeypatch.setenv("KAILASH_DISCLOSURE_BAD", "!!!not-base64!!!")
        with pytest.raises(DisclosureError):
            DisclosureTracer.from_env("KAILASH_DISCLOSURE_BAD", InMemoryAuditStore())
