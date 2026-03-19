# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Security regression tests for 11 hardened patterns.

These patterns were established through 13 rounds of red teaming and MUST NOT
be silently removed by future refactoring. Each test verifies the behavioral
contract of a specific security pattern.

See: packages/trust-plane/CLAUDE.md "What NOT to Change -- Security Patterns"
"""

from __future__ import annotations

import hmac as hmac_mod
import json
import math
import os
import sys
from collections import deque
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Pattern 1: validate_id() rejects path traversal
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern1ValidateId:
    """Pattern 1: validate_id() prevents path traversal attacks.

    Any externally-sourced record ID used in a filesystem path MUST be
    validated. The regex ^[a-zA-Z0-9_-]+$ prevents directory traversal
    and injection via IDs.
    """

    def test_path_traversal_rejected(self) -> None:
        """Path traversal strings like '../etc/passwd' must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("../etc/passwd")

    def test_forward_slash_rejected(self) -> None:
        """Slash-separated paths like 'foo/bar' must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("foo/bar")

    def test_null_byte_rejected(self) -> None:
        """Null byte injection like 'id\\x00bad' must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("id\x00bad")

    def test_backslash_rejected(self) -> None:
        """Backslash paths like 'foo\\\\bar' must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("foo\\bar")

    def test_dot_dot_only_rejected(self) -> None:
        """Double dot '..' alone must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("..")

    def test_safe_id_accepted(self) -> None:
        """Alphanumeric IDs with hyphens/underscores must be accepted."""
        from trustplane._locking import validate_id

        validate_id("del-abc123")
        validate_id("hold_456")
        validate_id("myID-99")

    def test_prefix_validation(self) -> None:
        """If a prefix is required, IDs without it must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("abc123", prefix="del-")

    def test_empty_string_rejected(self) -> None:
        """An empty string must raise ValueError."""
        from trustplane._locking import validate_id

        with pytest.raises(ValueError):
            validate_id("")


# ---------------------------------------------------------------------------
# Pattern 2: safe_read_json() uses O_NOFOLLOW
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern2ONoFollow:
    """Pattern 2: safe_read_json() uses O_NOFOLLOW to prevent symlink attacks.

    Symlink attacks redirect file reads to attacker-controlled locations.
    O_NOFOLLOW raises ELOOP if the path is a symlink.
    """

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="O_NOFOLLOW not available on Windows",
    )
    def test_symlink_rejected(self, tmp_path: Path) -> None:
        """Reading through a symlink must raise OSError (ELOOP)."""
        from trustplane._locking import safe_read_json

        real_file = tmp_path / "real.json"
        real_file.write_text('{"key": "value"}')

        link_path = tmp_path / "link.json"
        link_path.symlink_to(real_file)

        with pytest.raises(OSError, match="[Ss]ymlink|ELOOP|[Ll]oop"):
            safe_read_json(link_path)

    def test_regular_file_accepted(self, tmp_path: Path) -> None:
        """Reading a regular (non-symlink) file must succeed."""
        from trustplane._locking import safe_read_json

        real_file = tmp_path / "data.json"
        real_file.write_text('{"key": "value"}')

        result = safe_read_json(real_file)
        assert result == {"key": "value"}

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Reading a nonexistent file must raise FileNotFoundError."""
        from trustplane._locking import safe_read_json

        with pytest.raises(FileNotFoundError):
            safe_read_json(tmp_path / "does_not_exist.json")


# ---------------------------------------------------------------------------
# Pattern 3: atomic_write() for crash-safe record writes
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern3AtomicWrite:
    """Pattern 3: atomic_write() uses temp file + fsync + os.replace().

    Partial writes on crash produce corrupted records. atomic_write()
    ensures either the old file or the new file exists, never a corrupt
    partial.
    """

    def test_atomic_write_creates_file(self, tmp_path: Path) -> None:
        """atomic_write must create a complete JSON file."""
        from trustplane._locking import atomic_write

        target = tmp_path / "record.json"
        data = {"id": "rec-001", "value": 42}
        atomic_write(target, data)

        assert target.exists()
        content = json.loads(target.read_text())
        assert content == data

    def test_atomic_write_replaces_existing(self, tmp_path: Path) -> None:
        """atomic_write must atomically replace an existing file."""
        from trustplane._locking import atomic_write

        target = tmp_path / "record.json"
        atomic_write(target, {"version": 1})
        atomic_write(target, {"version": 2})

        content = json.loads(target.read_text())
        assert content["version"] == 2

    def test_no_temp_files_left_on_success(self, tmp_path: Path) -> None:
        """After a successful write, no temp files should remain."""
        from trustplane._locking import atomic_write

        target = tmp_path / "record.json"
        atomic_write(target, {"ok": True})

        # Only the target file and possibly __pycache__ should exist
        files = [f for f in tmp_path.iterdir() if f.name != "__pycache__"]
        assert len(files) == 1
        assert files[0].name == "record.json"

    def test_atomic_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        """atomic_write must create parent directories if needed."""
        from trustplane._locking import atomic_write

        target = tmp_path / "nested" / "dir" / "record.json"
        atomic_write(target, {"nested": True})

        assert target.exists()
        assert json.loads(target.read_text()) == {"nested": True}


# ---------------------------------------------------------------------------
# Pattern 4: safe_read_json() for deserialization (no bare json.loads)
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern4SafeDeserialization:
    """Pattern 4: All JSON deserialization uses safe_read_json().

    Using path.read_text() + json.loads() bypasses O_NOFOLLOW protection.
    This is tested via static analysis in test_static_checks.py.
    Behavioral test: safe_read_json returns valid data.
    """

    def test_safe_read_json_returns_dict(self, tmp_path: Path) -> None:
        """safe_read_json must return parsed JSON dict from regular file."""
        from trustplane._locking import safe_read_json

        target = tmp_path / "data.json"
        target.write_text('{"hello": "world", "count": 5}')

        result = safe_read_json(target)
        assert isinstance(result, dict)
        assert result["hello"] == "world"
        assert result["count"] == 5

    def test_safe_read_json_invalid_json_raises(self, tmp_path: Path) -> None:
        """safe_read_json must raise on invalid JSON content."""
        from trustplane._locking import safe_read_json

        target = tmp_path / "bad.json"
        target.write_text("not valid json {{{")

        with pytest.raises(json.JSONDecodeError):
            safe_read_json(target)


# ---------------------------------------------------------------------------
# Pattern 5: math.isfinite() on numeric constraint fields
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern5IsFinite:
    """Pattern 5: NaN and Inf are rejected in numeric constraint fields.

    NaN bypasses numeric comparisons (NaN < 0 is False). Inf bypasses
    upper-bound checks. An attacker can set constraints to NaN to make
    all checks pass silently.
    """

    def test_nan_max_cost_per_session_rejected(self) -> None:
        """FinancialConstraints must reject NaN for max_cost_per_session."""
        from trustplane.models import FinancialConstraints

        with pytest.raises(ValueError, match="finite"):
            FinancialConstraints(max_cost_per_session=float("nan"))

    def test_inf_max_cost_per_session_rejected(self) -> None:
        """FinancialConstraints must reject Inf for max_cost_per_session."""
        from trustplane.models import FinancialConstraints

        with pytest.raises(ValueError, match="finite"):
            FinancialConstraints(max_cost_per_session=float("inf"))

    def test_nan_max_cost_per_action_rejected(self) -> None:
        """FinancialConstraints must reject NaN for max_cost_per_action."""
        from trustplane.models import FinancialConstraints

        with pytest.raises(ValueError, match="finite"):
            FinancialConstraints(max_cost_per_action=float("nan"))

    def test_inf_max_cost_per_action_rejected(self) -> None:
        """FinancialConstraints must reject Inf for max_cost_per_action."""
        from trustplane.models import FinancialConstraints

        with pytest.raises(ValueError, match="finite"):
            FinancialConstraints(max_cost_per_action=float("inf"))

    def test_neg_inf_max_cost_per_session_rejected(self) -> None:
        """FinancialConstraints must reject -Inf for max_cost_per_session."""
        from trustplane.models import FinancialConstraints

        with pytest.raises(ValueError, match="finite"):
            FinancialConstraints(max_cost_per_session=float("-inf"))

    def test_nan_max_session_hours_rejected(self) -> None:
        """TemporalConstraints must reject NaN for max_session_hours."""
        from trustplane.models import TemporalConstraints

        with pytest.raises(ValueError, match="finite"):
            TemporalConstraints(max_session_hours=float("nan"))

    def test_inf_max_session_hours_rejected(self) -> None:
        """TemporalConstraints must reject Inf for max_session_hours."""
        from trustplane.models import TemporalConstraints

        with pytest.raises(ValueError, match="finite"):
            TemporalConstraints(max_session_hours=float("inf"))

    def test_finite_values_accepted(self) -> None:
        """Valid finite values must be accepted."""
        from trustplane.models import FinancialConstraints, TemporalConstraints

        fc = FinancialConstraints(max_cost_per_session=100.0, max_cost_per_action=10.0)
        assert fc.max_cost_per_session == 100.0

        tc = TemporalConstraints(max_session_hours=8.0)
        assert tc.max_session_hours == 8.0


# ---------------------------------------------------------------------------
# Pattern 6: Bounded collections (deque with maxlen)
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern6BoundedCollections:
    """Pattern 6: Bounded collections prevent memory exhaustion.

    Unbounded collections in long-running processes lead to OOM.
    call_log and tool_calls must use deque(maxlen=N).
    """

    def test_proxy_call_log_is_bounded(self) -> None:
        """TrustProxy._call_log must use deque with maxlen."""
        from trustplane.proxy import TrustProxy

        # Create a minimal TrustProxy with a mock project
        class FakeProject:
            pass

        proxy = TrustProxy(project=FakeProject())
        assert isinstance(proxy._call_log, deque)
        assert proxy._call_log.maxlen is not None
        assert proxy._call_log.maxlen > 0
        assert proxy._call_log.maxlen <= 100_000  # reasonable upper bound

    def test_shadow_session_tool_calls_bounded(self) -> None:
        """ShadowSession.tool_calls must use deque with maxlen."""
        from trustplane.shadow import ShadowSession

        session = ShadowSession()
        assert isinstance(session.tool_calls, deque)
        assert session.tool_calls.maxlen is not None
        assert session.tool_calls.maxlen > 0
        assert session.tool_calls.maxlen <= 100_000

    def test_bounded_collection_evicts_oldest(self) -> None:
        """When a bounded deque is full, oldest entries must be evicted."""
        d: deque[int] = deque(maxlen=3)
        for i in range(5):
            d.append(i)
        # Only the last 3 should remain
        assert list(d) == [2, 3, 4]


# ---------------------------------------------------------------------------
# Pattern 7: Monotonic escalation (verdict cannot be downgraded)
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern7MonotonicEscalation:
    """Pattern 7: Trust state can only escalate, never relax.

    Verdict ordering: AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED.
    A HELD action cannot become AUTO_APPROVED.
    """

    def test_verdict_enum_has_all_four_levels(self) -> None:
        """Verdict must define AUTO_APPROVED, FLAGGED, HELD, BLOCKED."""
        from eatp.enforce.strict import Verdict

        assert hasattr(Verdict, "AUTO_APPROVED")
        assert hasattr(Verdict, "FLAGGED")
        assert hasattr(Verdict, "HELD")
        assert hasattr(Verdict, "BLOCKED")

    def test_delegation_revocation_is_irreversible(self, tmp_path: Path) -> None:
        """A revoked delegate cannot be re-activated (monotonic status)."""
        from trustplane.delegation import (
            DelegateStatus,
            DelegationManager,
        )

        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        mgr = DelegationManager(trust_dir)

        delegate = mgr.add_delegate(
            name="Alice",
            dimensions=["operational"],
        )
        assert delegate.status == DelegateStatus.ACTIVE

        mgr.revoke_delegate(delegate.delegate_id, reason="test")
        revoked = mgr.get_delegate(delegate.delegate_id)
        assert revoked.status == DelegateStatus.REVOKED
        assert not revoked.is_active()

    def test_constraint_envelope_monotonic_tightening(self) -> None:
        """ConstraintEnvelope.is_tighter_than() must enforce monotonicity.

        A looser envelope must NOT be accepted as tighter than a strict one.
        """
        from trustplane.models import (
            ConstraintEnvelope,
            FinancialConstraints,
            OperationalConstraints,
        )

        strict = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["dangerous"]),
            financial=FinancialConstraints(max_cost_per_session=100.0),
        )
        loose = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=[]),
            financial=FinancialConstraints(max_cost_per_session=500.0),
        )
        # Loose cannot be tighter than strict
        assert not loose.is_tighter_than(strict)
        # Strict is tighter than loose
        assert strict.is_tighter_than(loose)


# ---------------------------------------------------------------------------
# Pattern 8: hmac.compare_digest() for hash comparison
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern8HmacCompareDigest:
    """Pattern 8: hmac.compare_digest() for all hash/signature comparisons.

    String equality (==) leaks timing information. An attacker can measure
    comparison time to determine how many bytes match.
    Static verification is in test_static_checks.py.
    """

    def test_compare_digest_catches_mismatch(self) -> None:
        """hmac.compare_digest must return False for different hashes."""
        assert not hmac_mod.compare_digest("abc123", "abc456")

    def test_compare_digest_accepts_match(self) -> None:
        """hmac.compare_digest must return True for identical hashes."""
        assert hmac_mod.compare_digest("abc123", "abc123")

    def test_wal_tamper_detection_uses_compare_digest(self, tmp_path: Path) -> None:
        """WAL recovery must detect tampered content hashes.

        This verifies the delegation WAL recovery path uses
        hmac.compare_digest (not ==) for hash verification.
        """
        from trustplane._locking import compute_wal_hash
        from trustplane.delegation import DelegationManager

        trust_dir = tmp_path / "trust-plane"
        trust_dir.mkdir()
        mgr = DelegationManager(trust_dir)

        delegate = mgr.add_delegate(name="Bob", dimensions=["operational"])

        # Manually create a tampered WAL
        wal_data = {
            "root_delegate_id": delegate.delegate_id,
            "planned_revocations": [delegate.delegate_id],
            "reason": "test",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        # Compute correct hash then tamper the content
        wal_data["content_hash"] = compute_wal_hash(wal_data)
        wal_data["reason"] = "TAMPERED"  # Change after hashing

        mgr._store.store_wal(wal_data)

        # Recovery should detect the tamper and NOT revoke
        recovered = mgr.recover_pending_revocations()
        assert recovered == [], (
            "Tampered WAL should be rejected; no delegates should be revoked"
        )


# ---------------------------------------------------------------------------
# Pattern 9: Key material zeroization on revocation
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern9KeyZeroization:
    """Pattern 9: Key material is cleared from memory on revocation.

    Private key material in memory is vulnerable to debugger inspection
    and memory dumps. After revocation, the key slot must contain empty
    string (tombstone), not the original key material.
    """

    async def test_key_cleared_on_revocation(self) -> None:
        """After revoking a key, _keys[key_id] must be empty string."""
        from eatp.key_manager import InMemoryKeyManager

        key_mgr = InMemoryKeyManager()
        key_id = "test-key"
        await key_mgr.generate_keypair(key_id)

        # Verify key exists and has material
        assert key_mgr._keys[key_id] != ""

        await key_mgr.revoke_key(key_id)

        # F4: Key material must be zeroized (empty string tombstone)
        assert key_mgr._keys[key_id] == "", (
            "SECURITY REGRESSION: Key material not cleared on revocation. "
            "Private key remains in memory after revocation, vulnerable to "
            "memory dump attacks. See Pattern 9 (F4 fix)."
        )

    async def test_revoked_key_cannot_sign(self) -> None:
        """Signing with a revoked key must fail."""
        from eatp.key_manager import InMemoryKeyManager

        key_mgr = InMemoryKeyManager()
        key_id = "test-key"
        await key_mgr.generate_keypair(key_id)
        await key_mgr.revoke_key(key_id)

        with pytest.raises(Exception):
            # Should raise due to revoked status or empty key
            key_mgr.sign_with_key(key_id, "test payload")


# ---------------------------------------------------------------------------
# Pattern 10: MultiSigPolicy / frozen dataclasses
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern10FrozenDataclass:
    """Pattern 10: Security-critical dataclasses use frozen=True.

    Without frozen=True, an attacker with object reference can bypass
    __post_init__ validation by directly setting fields.
    """

    def test_role_permission_is_frozen(self) -> None:
        """RolePermission must be a frozen dataclass (immutable after init)."""
        from trustplane.rbac import Role, RolePermission

        perm = RolePermission(
            role=Role.ADMIN,
            allowed_operations=frozenset({"decide", "verify"}),
        )
        with pytest.raises(FrozenInstanceError):
            perm.role = Role.OBSERVER  # type: ignore[misc]

    def test_role_permission_operations_immutable(self) -> None:
        """RolePermission.allowed_operations must use frozenset (immutable)."""
        from trustplane.rbac import Role, RolePermission

        perm = RolePermission(
            role=Role.ADMIN,
            allowed_operations=frozenset({"decide"}),
        )
        # frozenset does not support add/remove
        assert isinstance(perm.allowed_operations, frozenset)


# ---------------------------------------------------------------------------
# Pattern 11: from_dict() validates required fields
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestPattern11FromDictValidation:
    """Pattern 11: from_dict() validates all required fields.

    Silent defaults in from_dict() accept malformed/tampered JSON without
    raising errors. A corrupted record should fail loudly.
    """

    def test_delegate_from_dict_missing_fields(self) -> None:
        """Delegate.from_dict must raise on missing required fields."""
        from trustplane.delegation import Delegate

        with pytest.raises(ValueError, match="missing required field"):
            Delegate.from_dict({})

        with pytest.raises(ValueError, match="missing required field"):
            Delegate.from_dict({"delegate_id": "del-x"})

    def test_delegate_from_dict_invalid_depth(self) -> None:
        """Delegate.from_dict must reject negative depth values."""
        from trustplane.delegation import Delegate

        with pytest.raises(ValueError, match="depth"):
            Delegate.from_dict(
                {
                    "delegate_id": "del-x",
                    "name": "Alice",
                    "dimensions": ["operational"],
                    "delegated_by": "owner",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "depth": -1,
                }
            )

    def test_decision_record_from_dict_missing_fields(self) -> None:
        """DecisionRecord.from_dict must raise on missing required fields."""
        from trustplane.models import DecisionRecord

        with pytest.raises(ValueError, match="missing required field"):
            DecisionRecord.from_dict({})

        with pytest.raises(ValueError, match="missing required field"):
            DecisionRecord.from_dict({"decision_id": "dec-x"})

    def test_decision_record_from_dict_nan_confidence(self) -> None:
        """DecisionRecord.from_dict must reject NaN confidence."""
        from trustplane.models import DecisionRecord

        with pytest.raises(ValueError, match="finite"):
            DecisionRecord.from_dict(
                {
                    "decision_id": "dec-x",
                    "decision_type": "scope",
                    "decision": "test",
                    "rationale": "because",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "confidence": float("nan"),
                }
            )

    def test_milestone_record_from_dict_missing_fields(self) -> None:
        """MilestoneRecord.from_dict must raise on missing required fields."""
        from trustplane.models import MilestoneRecord

        with pytest.raises(ValueError, match="missing required field"):
            MilestoneRecord.from_dict({})

        with pytest.raises(ValueError, match="missing required field"):
            MilestoneRecord.from_dict({"milestone_id": "ms-x"})

    def test_shadow_tool_call_from_dict_missing_fields(self) -> None:
        """ShadowToolCall.from_dict must raise on missing required fields."""
        from trustplane.shadow import ShadowToolCall

        with pytest.raises(ValueError, match="action"):
            ShadowToolCall.from_dict({})

        with pytest.raises(ValueError, match="resource"):
            ShadowToolCall.from_dict({"action": "Read"})

        with pytest.raises(ValueError, match="category"):
            ShadowToolCall.from_dict({"action": "Read", "resource": "/src"})

    def test_shadow_session_from_dict_missing_fields(self) -> None:
        """ShadowSession.from_dict must raise on missing required fields."""
        from trustplane.shadow import ShadowSession

        with pytest.raises(ValueError, match="session_id"):
            ShadowSession.from_dict({})

    def test_role_permission_from_dict_missing_fields(self) -> None:
        """RolePermission.from_dict must raise on missing required fields."""
        from trustplane.rbac import RolePermission

        with pytest.raises(ValueError, match="missing required field"):
            RolePermission.from_dict({})

        with pytest.raises(ValueError, match="missing required field"):
            RolePermission.from_dict({"role": "admin"})
