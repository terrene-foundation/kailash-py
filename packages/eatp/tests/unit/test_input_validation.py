# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for input validation security fixes (H1-H6).

Tests are written BEFORE implementation (TDD). Each test class maps to
a specific HIGH security issue:

    H1: Hook modified_context allows unconstrained metadata mutation (hooks.py)
    H2: DualSignature.from_dict() lacks input validation (crypto.py)
    H3: TrustScore.from_dict() trusts all input (scoring.py)
    H4: CombinedTrustScore.from_dict() no weight consistency check (scoring.py)
    H5: HookResult.from_dict() allow field truthiness bug (hooks.py)
    H6: InMemoryRevocationBroadcaster history grows without bound (broadcaster.py)

Rules:
    - Fail-closed: unknown/error states deny, never silently permit
    - Bounded collections: maxlen=10000, trim oldest 10% at capacity
    - All validation raises clear errors with context
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from eatp.crypto import DualSignature
from eatp.hooks import (
    EATPHook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)
from eatp.revocation.broadcaster import (
    InMemoryRevocationBroadcaster,
    RevocationEvent,
    RevocationType,
)
from eatp.scoring import CombinedTrustScore, TrustScore


# ---------------------------------------------------------------------------
# Shared test hook implementations
# ---------------------------------------------------------------------------


class ContextModifyingHook(EATPHook):
    """A hook that injects arbitrary keys via modified_context."""

    def __init__(
        self,
        name: str = "modifier",
        event_types: List[HookType] | None = None,
        priority: int = 100,
        inject: dict | None = None,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
        self._priority = priority
        self._inject = inject or {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def event_types(self) -> List[HookType]:
        return self._event_types

    @property
    def priority(self) -> int:
        return self._priority

    async def __call__(self, context: HookContext) -> HookResult:
        return HookResult(allow=True, modified_context=self._inject)


class ContextReaderHook(EATPHook):
    """A hook that records the metadata it received."""

    def __init__(
        self,
        name: str = "reader",
        event_types: List[HookType] | None = None,
        priority: int = 200,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
        self._priority = priority
        self.observed_metadata: dict | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def event_types(self) -> List[HookType]:
        return self._event_types

    @property
    def priority(self) -> int:
        return self._priority

    async def __call__(self, context: HookContext) -> HookResult:
        self.observed_metadata = dict(context.metadata)
        return HookResult(allow=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def registry() -> HookRegistry:
    """HookRegistry with tight timeout for fast test execution."""
    return HookRegistry(timeout_seconds=0.5)


@pytest.fixture
def pre_delegation_context() -> HookContext:
    """Standard PRE_DELEGATION context."""
    return HookContext(
        agent_id="agent-001",
        action="delegate_to_subagent",
        hook_type=HookType.PRE_DELEGATION,
    )


def _make_trust_score_dict(
    score: Any = 85,
    grade: Any = "B",
    computed_at: str = "2026-03-14T12:00:00+00:00",
    agent_id: str = "agent-001",
    breakdown: Any = None,
) -> Dict[str, Any]:
    """Build a TrustScore dict for from_dict testing."""
    if breakdown is None:
        breakdown = {
            "chain_completeness": 28.5,
            "delegation_depth": 14.25,
            "constraint_coverage": 20.0,
            "posture_level": 16.0,
            "chain_recency": 6.25,
        }
    return {
        "score": score,
        "breakdown": breakdown,
        "grade": grade,
        "computed_at": computed_at,
        "agent_id": agent_id,
    }


def _make_revocation_event(event_id: str) -> RevocationEvent:
    """Create a minimal RevocationEvent."""
    return RevocationEvent(
        event_id=event_id,
        revocation_type=RevocationType.AGENT_REVOKED,
        target_id="agent-target",
        revoked_by="admin",
        reason="Test reason",
    )


# ===========================================================================
# H1: Hook modified_context allows unconstrained metadata mutation
# ===========================================================================


class TestH1ModifiedContextConstraints:
    """H1: modified_context must be size-capped and must not overwrite reserved keys."""

    async def test_modified_context_over_100_keys_is_truncated(
        self, registry, pre_delegation_context
    ):
        """modified_context with >100 keys must be truncated to 100."""
        large_inject = {f"key_{i}": f"value_{i}" for i in range(150)}
        modifier = ContextModifyingHook(
            name="large_modifier", priority=10, inject=large_inject
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True
        assert reader.observed_metadata is not None
        # Only first 100 keys from modified_context should have been merged
        injected_keys = [k for k in reader.observed_metadata if k.startswith("key_")]
        assert len(injected_keys) == 100

    async def test_modified_context_exactly_100_keys_is_allowed(
        self, registry, pre_delegation_context
    ):
        """modified_context with exactly 100 keys must be fully applied."""
        inject = {f"key_{i}": f"value_{i}" for i in range(100)}
        modifier = ContextModifyingHook(
            name="exact_modifier", priority=10, inject=inject
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True
        injected_keys = [k for k in reader.observed_metadata if k.startswith("key_")]
        assert len(injected_keys) == 100

    async def test_reserved_key_agent_id_is_skipped(
        self, registry, pre_delegation_context
    ):
        """Attempting to overwrite 'agent_id' via modified_context must be skipped."""
        modifier = ContextModifyingHook(
            name="agent_overwriter",
            priority=10,
            inject={"agent_id": "evil-agent", "safe_key": "ok"},
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True
        assert reader.observed_metadata is not None
        # agent_id should NOT have been overwritten in metadata
        assert reader.observed_metadata.get("agent_id") != "evil-agent"
        # safe_key should still be applied
        assert reader.observed_metadata["safe_key"] == "ok"

    async def test_reserved_key_authority_id_is_skipped(
        self, registry, pre_delegation_context
    ):
        """Attempting to overwrite 'authority_id' via modified_context must be skipped."""
        modifier = ContextModifyingHook(
            name="auth_overwriter",
            priority=10,
            inject={"authority_id": "malicious-authority"},
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert reader.observed_metadata is not None
        assert reader.observed_metadata.get("authority_id") != "malicious-authority"

    async def test_reserved_key_action_is_skipped(
        self, registry, pre_delegation_context
    ):
        """Attempting to overwrite 'action' via modified_context must be skipped."""
        modifier = ContextModifyingHook(
            name="action_overwriter",
            priority=10,
            inject={"action": "delete_all", "benign": "data"},
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert reader.observed_metadata is not None
        assert reader.observed_metadata.get("action") != "delete_all"
        assert reader.observed_metadata["benign"] == "data"

    async def test_all_six_reserved_keys_are_protected(
        self, registry, pre_delegation_context
    ):
        """All 6 reserved keys must be protected from overwrite."""
        reserved = {
            "agent_id": "evil",
            "authority_id": "evil",
            "action": "evil",
            "resource": "evil",
            "hook_type": "evil",
            "trace_id": "evil",
        }
        modifier = ContextModifyingHook(
            name="all_reserved",
            priority=10,
            inject={**reserved, "allowed_key": "value"},
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert reader.observed_metadata is not None
        # None of the reserved keys should have been set to "evil"
        for key in reserved:
            assert (
                reader.observed_metadata.get(key) != "evil"
            ), f"Reserved key '{key}' was overwritten"
        # The non-reserved key should be applied
        assert reader.observed_metadata["allowed_key"] == "value"

    async def test_non_reserved_key_overwrite_is_allowed(
        self, registry, pre_delegation_context
    ):
        """Non-reserved keys in metadata CAN be overwritten by modified_context."""
        pre_delegation_context.metadata["custom_key"] = "original"
        modifier = ContextModifyingHook(
            name="custom_overwriter",
            priority=10,
            inject={"custom_key": "updated"},
        )
        reader = ContextReaderHook(name="reader", priority=200)

        registry.register(modifier)
        registry.register(reader)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert reader.observed_metadata is not None
        assert reader.observed_metadata["custom_key"] == "updated"

    async def test_truncation_logs_warning(
        self, registry, pre_delegation_context, caplog
    ):
        """Truncating modified_context must log a warning."""
        large_inject = {f"key_{i}": f"value_{i}" for i in range(101)}
        modifier = ContextModifyingHook(
            name="warn_modifier", priority=10, inject=large_inject
        )
        registry.register(modifier)

        with caplog.at_level(logging.WARNING, logger="eatp.hooks"):
            await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)

        assert any("exceeds 100 keys" in msg for msg in caplog.messages)

    async def test_reserved_key_skip_logs_warning(
        self, registry, pre_delegation_context, caplog
    ):
        """Skipping a reserved key must log a warning."""
        modifier = ContextModifyingHook(
            name="reserved_warner",
            priority=10,
            inject={"agent_id": "evil"},
        )
        registry.register(modifier)

        with caplog.at_level(logging.WARNING, logger="eatp.hooks"):
            await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)

        assert any("reserved key" in msg for msg in caplog.messages)


# ===========================================================================
# H2: DualSignature.from_dict() lacks input validation
# ===========================================================================


class TestH2DualSignatureFromDictValidation:
    """H2: DualSignature.from_dict() must validate ed25519_signature and hmac_algorithm."""

    def test_valid_data_round_trip(self):
        """Valid data must round-trip correctly (regression)."""
        data = {
            "ed25519_signature": "valid_sig==",
            "hmac_algorithm": "sha256",
        }
        ds = DualSignature.from_dict(data)
        assert ds.ed25519_signature == "valid_sig=="
        assert ds.hmac_algorithm == "sha256"

    def test_empty_string_ed25519_signature_raises(self):
        """Empty string ed25519_signature must raise ValueError."""
        data = {"ed25519_signature": ""}
        with pytest.raises(ValueError, match="non-empty string"):
            DualSignature.from_dict(data)

    def test_none_ed25519_signature_raises(self):
        """None ed25519_signature (via dict value) must raise ValueError."""
        data = {"ed25519_signature": None}
        with pytest.raises(ValueError, match="non-empty string"):
            DualSignature.from_dict(data)

    def test_integer_ed25519_signature_raises(self):
        """Integer ed25519_signature must raise ValueError."""
        data = {"ed25519_signature": 12345}
        with pytest.raises(ValueError, match="non-empty string"):
            DualSignature.from_dict(data)

    def test_list_ed25519_signature_raises(self):
        """List ed25519_signature must raise ValueError."""
        data = {"ed25519_signature": ["a", "b"]}
        with pytest.raises(ValueError, match="non-empty string"):
            DualSignature.from_dict(data)

    def test_valid_hmac_algorithms(self):
        """sha256, sha384, sha512 must all be accepted."""
        for algo in ("sha256", "sha384", "sha512"):
            data = {"ed25519_signature": "sig==", "hmac_algorithm": algo}
            ds = DualSignature.from_dict(data)
            assert ds.hmac_algorithm == algo

    def test_invalid_hmac_algorithm_raises(self):
        """Unsupported hmac_algorithm must raise ValueError."""
        data = {"ed25519_signature": "sig==", "hmac_algorithm": "md5"}
        with pytest.raises(ValueError, match="Unsupported hmac_algorithm"):
            DualSignature.from_dict(data)

    def test_hmac_algorithm_sha1_rejected(self):
        """sha1 is not in the allowed set and must be rejected."""
        data = {"ed25519_signature": "sig==", "hmac_algorithm": "sha1"}
        with pytest.raises(ValueError, match="Unsupported hmac_algorithm"):
            DualSignature.from_dict(data)

    def test_hmac_algorithm_empty_string_rejected(self):
        """Empty string hmac_algorithm must raise ValueError."""
        data = {"ed25519_signature": "sig==", "hmac_algorithm": ""}
        with pytest.raises(ValueError, match="Unsupported hmac_algorithm"):
            DualSignature.from_dict(data)

    def test_default_hmac_algorithm_still_sha256(self):
        """When hmac_algorithm is not in the dict, it must default to sha256."""
        data = {"ed25519_signature": "sig=="}
        ds = DualSignature.from_dict(data)
        assert ds.hmac_algorithm == "sha256"

    def test_missing_ed25519_key_raises_key_error(self):
        """Missing ed25519_signature key must raise KeyError (existing behavior)."""
        with pytest.raises(KeyError):
            DualSignature.from_dict({"hmac_signature": "hmac=="})

    def test_with_valid_hmac_signature(self):
        """Valid full data with hmac_signature must work."""
        data = {
            "ed25519_signature": "ed_sig==",
            "hmac_signature": "hmac_sig==",
            "hmac_algorithm": "sha384",
        }
        ds = DualSignature.from_dict(data)
        assert ds.ed25519_signature == "ed_sig=="
        assert ds.hmac_signature == "hmac_sig=="
        assert ds.hmac_algorithm == "sha384"


# ===========================================================================
# H3: TrustScore.from_dict() trusts all input
# ===========================================================================


class TestH3TrustScoreFromDictValidation:
    """H3: TrustScore.from_dict() must validate score range and grade values."""

    def test_valid_data_round_trip(self):
        """Valid data must round-trip correctly (regression)."""
        data = _make_trust_score_dict(score=85, grade="B")
        ts = TrustScore.from_dict(data)
        assert ts.score == 85
        assert ts.grade == "B"

    def test_score_negative_raises(self):
        """Negative score must raise ValueError."""
        data = _make_trust_score_dict(score=-1)
        with pytest.raises(ValueError, match="score must be integer 0-100"):
            TrustScore.from_dict(data)

    def test_score_over_100_raises(self):
        """Score > 100 must raise ValueError."""
        data = _make_trust_score_dict(score=101)
        with pytest.raises(ValueError, match="score must be integer 0-100"):
            TrustScore.from_dict(data)

    def test_score_zero_is_valid(self):
        """Score 0 is a valid boundary value."""
        data = _make_trust_score_dict(score=0, grade="F")
        ts = TrustScore.from_dict(data)
        assert ts.score == 0

    def test_score_100_is_valid(self):
        """Score 100 is a valid boundary value."""
        data = _make_trust_score_dict(score=100, grade="A")
        ts = TrustScore.from_dict(data)
        assert ts.score == 100

    def test_score_float_raises(self):
        """Float score must raise ValueError."""
        data = _make_trust_score_dict(score=85.5)
        with pytest.raises(ValueError, match="score must be integer 0-100"):
            TrustScore.from_dict(data)

    def test_score_string_raises(self):
        """String score must raise ValueError."""
        data = _make_trust_score_dict(score="85")
        with pytest.raises(ValueError, match="score must be integer 0-100"):
            TrustScore.from_dict(data)

    def test_grade_invalid_raises(self):
        """Invalid grade string must raise ValueError."""
        data = _make_trust_score_dict(grade="X")
        with pytest.raises(ValueError, match="grade must be A/B/C/D/F"):
            TrustScore.from_dict(data)

    def test_grade_lowercase_rejected(self):
        """Lowercase grade must be rejected (grades are uppercase only)."""
        data = _make_trust_score_dict(grade="a")
        with pytest.raises(ValueError, match="grade must be A/B/C/D/F"):
            TrustScore.from_dict(data)

    def test_grade_empty_string_rejected(self):
        """Empty string grade must be rejected."""
        data = _make_trust_score_dict(grade="")
        with pytest.raises(ValueError, match="grade must be A/B/C/D/F"):
            TrustScore.from_dict(data)

    def test_all_valid_grades_accepted(self):
        """All valid grades A, B, C, D, F must be accepted."""
        for grade in ("A", "B", "C", "D", "F"):
            data = _make_trust_score_dict(grade=grade)
            ts = TrustScore.from_dict(data)
            assert ts.grade == grade


# ===========================================================================
# H4: CombinedTrustScore.from_dict() no combined_score validation
# ===========================================================================


class TestH4CombinedTrustScoreFromDictValidation:
    """H4: CombinedTrustScore.from_dict() must validate combined_score range."""

    def _make_combined_dict(
        self,
        combined_score: Any = 79,
    ) -> Dict[str, Any]:
        """Build a CombinedTrustScore dict for testing."""
        return {
            "structural_score": _make_trust_score_dict(score=85, grade="B"),
            "behavioral_score": None,
            "combined_score": combined_score,
            "breakdown": {
                "structural_weight": 1.0,
                "behavioral_weight": 0.0,
                "structural_contribution": 85,
                "behavioral_contribution": 0,
            },
        }

    def test_valid_data_round_trip(self):
        """Valid data must deserialize correctly."""
        data = self._make_combined_dict(combined_score=79)
        cts = CombinedTrustScore.from_dict(data)
        assert cts.combined_score == 79

    def test_combined_score_negative_raises(self):
        """Negative combined_score must raise ValueError."""
        data = self._make_combined_dict(combined_score=-5)
        with pytest.raises(ValueError, match="combined_score must be integer 0-100"):
            CombinedTrustScore.from_dict(data)

    def test_combined_score_over_100_raises(self):
        """combined_score > 100 must raise ValueError."""
        data = self._make_combined_dict(combined_score=150)
        with pytest.raises(ValueError, match="combined_score must be integer 0-100"):
            CombinedTrustScore.from_dict(data)

    def test_combined_score_zero_is_valid(self):
        """combined_score 0 is a valid boundary value."""
        data = self._make_combined_dict(combined_score=0)
        cts = CombinedTrustScore.from_dict(data)
        assert cts.combined_score == 0

    def test_combined_score_100_is_valid(self):
        """combined_score 100 is a valid boundary value."""
        data = self._make_combined_dict(combined_score=100)
        cts = CombinedTrustScore.from_dict(data)
        assert cts.combined_score == 100

    def test_combined_score_float_raises(self):
        """Float combined_score must raise ValueError."""
        data = self._make_combined_dict(combined_score=79.5)
        with pytest.raises(ValueError, match="combined_score must be integer 0-100"):
            CombinedTrustScore.from_dict(data)

    def test_combined_score_string_raises(self):
        """String combined_score must raise ValueError."""
        data = self._make_combined_dict(combined_score="79")
        with pytest.raises(ValueError, match="combined_score must be integer 0-100"):
            CombinedTrustScore.from_dict(data)


# ===========================================================================
# H5: HookResult.from_dict() allow field truthiness bug
# ===========================================================================


class TestH5HookResultAllowValidation:
    """H5: HookResult.from_dict() must enforce strict bool type for allow."""

    def test_allow_true_accepted(self):
        """allow=True (bool) must be accepted."""
        data = {"allow": True, "reason": None, "modified_context": None}
        result = HookResult.from_dict(data)
        assert result.allow is True

    def test_allow_false_accepted(self):
        """allow=False (bool) must be accepted."""
        data = {"allow": False, "reason": "blocked"}
        result = HookResult.from_dict(data)
        assert result.allow is False

    def test_allow_integer_1_rejected(self):
        """allow=1 (truthy int) must be rejected."""
        data = {"allow": 1}
        with pytest.raises(TypeError, match="must be bool"):
            HookResult.from_dict(data)

    def test_allow_integer_0_rejected(self):
        """allow=0 (falsy int) must be rejected."""
        data = {"allow": 0}
        with pytest.raises(TypeError, match="must be bool"):
            HookResult.from_dict(data)

    def test_allow_string_yes_rejected(self):
        """allow='yes' (truthy string) must be rejected."""
        data = {"allow": "yes"}
        with pytest.raises(TypeError, match="must be bool"):
            HookResult.from_dict(data)

    def test_allow_string_empty_rejected(self):
        """allow='' (falsy string) must be rejected."""
        data = {"allow": ""}
        with pytest.raises(TypeError, match="must be bool"):
            HookResult.from_dict(data)

    def test_allow_none_rejected(self):
        """allow=None must be rejected."""
        data = {"allow": None}
        with pytest.raises(TypeError, match="must be bool"):
            HookResult.from_dict(data)

    def test_allow_list_rejected(self):
        """allow=[] (falsy list) must be rejected."""
        data = {"allow": []}
        with pytest.raises(TypeError, match="must be bool"):
            HookResult.from_dict(data)

    def test_round_trip_preserves_bool_type(self):
        """to_dict -> from_dict must preserve bool type for allow."""
        for allow_val in (True, False):
            original = HookResult(allow=allow_val, reason="test")
            restored = HookResult.from_dict(original.to_dict())
            assert restored.allow is allow_val
            assert type(restored.allow) is bool


# ===========================================================================
# H6: InMemoryRevocationBroadcaster history grows without bound
# ===========================================================================


class TestH6BroadcasterBoundedHistory:
    """H6: InMemoryRevocationBroadcaster must bound history and dead_letters."""

    def test_history_under_limit_is_not_trimmed(self):
        """History with fewer than 10000 events must retain all events."""
        broadcaster = InMemoryRevocationBroadcaster()
        for i in range(100):
            broadcaster.broadcast(_make_revocation_event(f"rev-{i:06d}"))
        assert len(broadcaster.get_history()) == 100

    def test_history_at_limit_triggers_trim(self):
        """History at 10000 events must trim oldest 10% on next broadcast."""
        broadcaster = InMemoryRevocationBroadcaster()
        # Fill to capacity
        for i in range(10000):
            broadcaster.broadcast(_make_revocation_event(f"rev-{i:06d}"))
        assert len(broadcaster.get_history()) == 10000

        # Adding one more must trigger trim
        broadcaster.broadcast(_make_revocation_event("rev-trigger"))
        history = broadcaster.get_history()
        # After trim: 10000 - 1000 (oldest 10%) + 1 (new) = 9001
        assert len(history) == 9001

    def test_history_trim_removes_oldest(self):
        """Trim must remove the OLDEST entries, not the newest."""
        broadcaster = InMemoryRevocationBroadcaster()
        for i in range(10000):
            broadcaster.broadcast(_make_revocation_event(f"rev-{i:06d}"))

        # Trigger trim
        broadcaster.broadcast(_make_revocation_event("rev-new"))
        history = broadcaster.get_history()

        # The oldest 1000 events (rev-000000 through rev-000999) must be gone
        event_ids = {e.event_id for e in history}
        assert "rev-000000" not in event_ids
        assert "rev-000999" not in event_ids
        # The 1001st event should be the first remaining
        assert "rev-001000" in event_ids
        # The new event should be present
        assert "rev-new" in event_ids

    def test_dead_letters_under_limit_is_not_trimmed(self):
        """Dead letters with fewer than 1000 entries must retain all."""
        broadcaster = InMemoryRevocationBroadcaster()

        # Create a subscriber that always raises
        def failing_callback(event: RevocationEvent) -> None:
            raise RuntimeError("callback failure")

        broadcaster.subscribe(failing_callback)

        for i in range(50):
            broadcaster.broadcast(_make_revocation_event(f"rev-{i:06d}"))

        assert len(broadcaster.get_dead_letters()) == 50

    def test_dead_letters_at_limit_triggers_trim(self):
        """Dead letters at 1000 entries must trim oldest 10% on next failure."""
        broadcaster = InMemoryRevocationBroadcaster()

        def failing_callback(event: RevocationEvent) -> None:
            raise RuntimeError("callback failure")

        broadcaster.subscribe(failing_callback)

        # Fill to capacity
        for i in range(1000):
            broadcaster.broadcast(_make_revocation_event(f"rev-{i:06d}"))

        assert len(broadcaster.get_dead_letters()) == 1000

        # Trigger trim with one more
        broadcaster.broadcast(_make_revocation_event("rev-trigger"))
        dead_letters = broadcaster.get_dead_letters()
        # After trim: 1000 - 100 (oldest 10%) + 1 (new) = 901
        assert len(dead_letters) == 901

    def test_history_bounded_after_many_broadcasts(self):
        """After many broadcasts, history must never exceed 10000."""
        broadcaster = InMemoryRevocationBroadcaster()
        for i in range(15000):
            broadcaster.broadcast(_make_revocation_event(f"rev-{i:06d}"))
        assert len(broadcaster.get_history()) <= 10000

    def test_history_constant_defined(self):
        """Module must define _MAX_HISTORY = 10000."""
        from eatp.revocation import broadcaster as mod

        assert hasattr(mod, "_MAX_HISTORY")
        assert mod._MAX_HISTORY == 10000

    def test_dead_letters_constant_defined(self):
        """Module must define _MAX_DEAD_LETTERS = 1000."""
        from eatp.revocation import broadcaster as mod

        assert hasattr(mod, "_MAX_DEAD_LETTERS")
        assert mod._MAX_DEAD_LETTERS == 1000
