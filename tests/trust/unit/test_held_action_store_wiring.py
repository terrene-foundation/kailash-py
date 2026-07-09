# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 wiring test for the HITL held-action store (GitHub #1515, SAFR BH2).

Exercises the ``SqliteHeldActionStore`` THROUGH the ``StrictEnforcer`` facade
against a real on-disk SQLite database (no mocking, real infrastructure per
testing.md Tier 2 + facade-manager-detection.md Rule 1):

- A QUEUE hold with a timeout persists a row to the SQLite file.
- The row survives a "restart" (a fresh store on the same db_path).
- ``expire_holds()`` through the enforcer fires the disposition, records the
  expiry to the audit sink, and removes the row.
- The DB file is created 0o600 (trust-plane-security.md rule 6).
"""

from __future__ import annotations

import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.chain import VerificationResult
from kailash.trust.enforce.held import ExpiryDisposition, SqliteHeldActionStore
from kailash.trust.enforce.strict import (
    EATPHeldError,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)
from kailash.trust.governance.models import ApprovalPolicyModel

pytestmark = [pytest.mark.integration, pytest.mark.tier2]


def _held_result() -> VerificationResult:
    return VerificationResult(
        valid=True,
        reason="needs human review",
        violations=[{"field": "cost", "message": "near limit"}],
    )


def test_sqlite_store_persists_hold_through_enforcer_facade(tmp_path):
    """A QUEUE hold with a timeout lands a row in the real SQLite file."""
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-sql",
            action="deploy",
            result=_held_result(),
            timeout=300.0,
            on_expiry=ExpiryDisposition.DENY,
        )

    # External effect: the hold is persisted and readable back.
    pending = store.pending()
    assert len(pending) == 1
    assert pending[0].agent_id == "agent-sql"
    assert pending[0].timeout_seconds == 300.0
    assert pending[0].on_expiry is ExpiryDisposition.DENY
    store.close()


def test_hold_persists_across_store_restart(tmp_path):
    """The persisted hold survives a fresh store on the same db_path (restart)."""
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-restart",
            action="wire_funds",
            result=_held_result(),
            timeout=600.0,
        )
    store.close()

    # Simulate a process restart: a brand-new store on the same file.
    store2 = SqliteHeldActionStore(db_path)
    pending = store2.pending()
    assert len(pending) == 1
    assert pending[0].agent_id == "agent-restart"
    # Unset on_expiry defaulted to the fail-safe DENY at registration time.
    assert pending[0].on_expiry is ExpiryDisposition.DENY
    store2.close()


def test_expire_holds_fires_and_audits_through_sqlite(tmp_path):
    """expire_holds() through the enforcer fires DENY -> BLOCKED, audits, removes row."""
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    policy = ApprovalPolicyModel(
        external_agent_id="agent-exp", approval_timeout_seconds=300
    )
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-exp",
            action="invoke",
            result=_held_result(),
            approval_policy=policy,  # timeout window from the (formerly orphan) field
        )

    # Deadline is held_at + 300s; expire well past it.
    expired = enforcer.expire_holds(now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert len(expired) == 1
    assert expired[0].verdict is Verdict.BLOCKED  # fail-safe deny

    # Audited to the enforcer's records sink.
    assert expired[0] in enforcer.records
    assert expired[0].metadata["hold_expiry"] is True

    # The store row is gone (popped on expiry).
    assert store.pending() == []
    store.close()


def test_sqlite_db_file_permissions_are_owner_only(tmp_path):
    """trust-plane-security.md rule 6: the DB file is 0o600 on POSIX."""
    if os.name != "posix":
        pytest.skip("POSIX-only permission check")
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    mode = stat.S_IMODE(os.stat(db_path).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
    store.close()


def test_monotonic_expiry_never_less_restrictive_through_facade(tmp_path):
    """INV-5 through the real store: escalate -> HELD, deny -> BLOCKED; never relax."""
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-mono",
            action="escalate_me",
            result=_held_result(),
            timeout=10.0,
            on_expiry=ExpiryDisposition.ESCALATE_TO_SENIOR,
        )
    expired = enforcer.expire_holds(now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert len(expired) == 1
    # HELD is at least as restrictive as the original HELD; never AUTO_APPROVED.
    assert expired[0].verdict is Verdict.HELD
    assert expired[0].verdict not in (Verdict.AUTO_APPROVED, Verdict.FLAGGED)
    store.close()


def test_wal_shm_sidecars_are_owner_only(tmp_path):
    """HIGH: the WAL/SHM sidecars (created on first write) are also 0o600.

    WAL mode writes ``<db>-wal`` and ``<db>-shm`` holding the SAME governance
    data as the main DB; a world-readable sidecar leaks agent ids / actions /
    reasons to any local user (trust-plane-security.md rule 6).
    """
    if os.name != "posix":
        pytest.skip("POSIX-only permission check")
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    # A write forces the WAL/SHM sidecars into existence.
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-wal",
            action="deploy",
            result=_held_result(),
            timeout=300.0,
        )

    checked_any = False
    for suffix in ("-wal", "-shm"):
        sidecar = db_path + suffix
        if os.path.exists(sidecar):
            checked_any = True
            mode = stat.S_IMODE(os.stat(sidecar).st_mode)
            assert mode == 0o600, f"{suffix} expected 0o600, got {oct(mode)}"
    # WAL mode reliably creates -shm on the first write; assert we checked one.
    assert checked_any, "no WAL/SHM sidecar was created — cannot verify perms"
    store.close()


def test_corrupt_row_fails_closed_and_processes_siblings(tmp_path):
    """MEDIUM: a corrupt persisted row expires to a fail-closed BLOCKED record
    AND well-formed sibling rows in the same batch still process.

    user-flow-validation.md MUST-7 class (c): corrupt/partial persisted state
    on re-entry. Without per-row isolation, one tampered row aborts the whole
    pop_expired batch after the delete/commit — every expired hold is dropped
    with NO audit record. With it, the corrupt row yields a BLOCKED sentinel
    and the sibling is unaffected.
    """
    db_path = str(tmp_path / "held.db")
    store = SqliteHeldActionStore(db_path)
    enforcer = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store)

    # A well-formed sibling hold, already expired.
    with pytest.raises(EATPHeldError):
        enforcer.enforce(
            agent_id="agent-good",
            action="deploy",
            result=_held_result(),
            timeout=1.0,
            on_expiry=ExpiryDisposition.DENY,
        )
    store.close()

    # Tamper: insert a corrupt row directly (bad on_expiry string + a non-finite
    # timeout stored as text), already past its deadline.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO held_actions "
        "(hold_id, agent_id, action, held_at, timeout_seconds, expires_at, "
        "on_expiry, reason, violations_json, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "hold-corrupt-1",
            "agent-bad",
            "wire_funds",
            "2026-07-09T12:00:00+00:00",
            10.0,
            "2000-01-01T00:00:00+00:00",  # long past — expired
            "totally-not-a-valid-disposition",  # ExpiryDisposition() will raise
            "",
            "[]",
            "{}",
        ),
    )
    conn.commit()
    conn.close()

    # Re-open and expire both rows in one batch.
    store2 = SqliteHeldActionStore(db_path)
    enforcer2 = StrictEnforcer(on_held=HeldBehavior.QUEUE, held_store=store2)
    expired = enforcer2.expire_holds(
        now=datetime.now(timezone.utc) + timedelta(hours=1)
    )

    # BOTH rows processed — the corrupt one did NOT abort the batch.
    assert len(expired) == 2
    verdicts = [r.verdict for r in expired]
    # Every expiry verdict is at least as restrictive as HELD; both are BLOCKED
    # here (good row on_expiry=DENY; corrupt row fail-closed DENY).
    assert all(v is Verdict.BLOCKED for v in verdicts)

    # The corrupt row emitted a fail-closed BLOCKED audit record marked corrupt.
    corrupt_records = [r for r in expired if r.metadata.get("corrupt_row")]
    assert len(corrupt_records) == 1
    assert corrupt_records[0].verdict is Verdict.BLOCKED
    assert "corrupt held-action row" in (
        corrupt_records[0].verification_result.reason or ""
    )

    # Both are also in the enforcer's audit sink.
    assert store2.pending() == []
    store2.close()
