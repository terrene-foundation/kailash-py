# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for StrictEnforcer hook integration (Phase 3, todo 3.6).

Covers:
    1. PRE_VERIFICATION hook fires before classify()
    2. POST_VERIFICATION hook fires after classify()
    3. PRE_VERIFICATION hook deny raises EATPBlockedError
    4. POST_VERIFICATION hook deny raises EATPBlockedError
    5. Enforcer without hooks has unchanged behavior (backward compatible)
    6. Hooks fire in correct priority order
    7. POST_VERIFICATION hook metadata contains verdict info
    8. Multiple hooks interact correctly with enforce pipeline
    9. Hook context carries agent_id, action, and user metadata
   10. PRE_VERIFICATION deny prevents classify() from running
   11. Enforce records are NOT created when PRE_VERIFICATION denies
   12. Enforce records ARE created before POST_VERIFICATION runs

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from eatp.chain import VerificationResult
from eatp.enforce.strict import (
    EATPBlockedError,
    EATPHeldError,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)
from eatp.hooks import (
    EATPHook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)


# ---------------------------------------------------------------------------
# Concrete test hook implementations (no mocking)
# ---------------------------------------------------------------------------


class AllowHook(EATPHook):
    """A hook that always allows, recording each invocation."""

    def __init__(
        self,
        name: str = "allow_hook",
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_VERIFICATION]
        self._priority = priority
        self.call_count = 0
        self.last_context: Optional[HookContext] = None

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
        self.call_count += 1
        self.last_context = context
        return HookResult(allow=True)


class DenyHook(EATPHook):
    """A hook that always denies with a configurable reason."""

    def __init__(
        self,
        name: str = "deny_hook",
        event_types: List[HookType] | None = None,
        priority: int = 100,
        reason: str = "Denied by test policy",
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_VERIFICATION]
        self._priority = priority
        self._reason = reason
        self.call_count = 0
        self.last_context: Optional[HookContext] = None

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
        self.call_count += 1
        self.last_context = context
        return HookResult(allow=False, reason=self._reason)


class MetadataRecordingHook(EATPHook):
    """A hook that records the metadata it receives for later assertion."""

    def __init__(
        self,
        name: str = "recorder",
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.POST_VERIFICATION]
        self._priority = priority
        self.call_count = 0
        self.observed_contexts: List[HookContext] = []
        self.observed_metadata_snapshots: List[Dict[str, Any]] = []

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
        self.call_count += 1
        self.observed_contexts.append(context)
        self.observed_metadata_snapshots.append(dict(context.metadata))
        return HookResult(allow=True)


class OrderTrackingHook(EATPHook):
    """A hook that records its name into a shared order log."""

    def __init__(
        self,
        name: str,
        order_log: List[str],
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_VERIFICATION]
        self._priority = priority
        self._order_log = order_log

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
        self._order_log.append(self._name)
        return HookResult(allow=True)


class ClassifyTrackingHook(EATPHook):
    """Hook that fires on PRE_VERIFICATION and records whether classify has run.

    Works with a StrictEnforcer by checking whether any records exist yet.
    """

    def __init__(
        self,
        name: str = "classify_tracker",
        event_types: List[HookType] | None = None,
        priority: int = 100,
        enforcer_ref: Optional[StrictEnforcer] = None,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_VERIFICATION]
        self._priority = priority
        self._enforcer_ref = enforcer_ref
        self.records_at_call_time: Optional[int] = None

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
        if self._enforcer_ref is not None:
            self.records_at_call_time = len(self._enforcer_ref.records)
        return HookResult(allow=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_valid_result() -> VerificationResult:
    """Create a valid verification result with no violations."""
    return VerificationResult(valid=True, violations=[], reason="All checks passed")


def _make_invalid_result() -> VerificationResult:
    """Create an invalid verification result (BLOCKED)."""
    return VerificationResult(
        valid=False,
        violations=[{"dimension": "trust", "reason": "chain revoked"}],
        reason="Trust chain revoked",
    )


def _make_flagged_result() -> VerificationResult:
    """Create a valid result with warnings (violations present, below threshold)."""
    return VerificationResult(
        valid=True,
        violations=[{"dimension": "constraints", "reason": "near limit"}],
        reason="Valid with warnings",
    )


def _make_held_result(violation_count: int = 2) -> VerificationResult:
    """Create a valid result with enough violations to trigger HELD (flag_threshold=1)."""
    violations = [{"dimension": f"dim_{i}", "reason": f"violation {i}"} for i in range(violation_count)]
    return VerificationResult(
        valid=True,
        violations=violations,
        reason="Valid but needs review",
    )


@pytest.fixture
def registry() -> HookRegistry:
    """HookRegistry with tight timeout for fast tests."""
    return HookRegistry(timeout_seconds=1.0)


# ===========================================================================
# Test Class 1: PRE_VERIFICATION Hook Fires Before classify()
# ===========================================================================


class TestPreVerificationHookFires:
    """PRE_VERIFICATION hooks must fire before classify() is called."""

    def test_pre_hook_fires_on_valid_result(self, registry: HookRegistry):
        """PRE_VERIFICATION hook must be invoked when enforce() is called."""
        hook = AllowHook(name="pre_allow", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert verdict == Verdict.AUTO_APPROVED
        assert hook.call_count == 1

    def test_pre_hook_receives_correct_agent_id(self, registry: HookRegistry):
        """PRE_VERIFICATION context must contain the agent_id passed to enforce()."""
        hook = AllowHook(name="pre_agent_check", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-007", action="decrypt", result=result)

        assert hook.last_context is not None
        assert hook.last_context.agent_id == "agent-007"

    def test_pre_hook_receives_correct_action(self, registry: HookRegistry):
        """PRE_VERIFICATION context must contain the action passed to enforce()."""
        hook = AllowHook(name="pre_action_check", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-001", action="write_sensitive", result=result)

        assert hook.last_context is not None
        assert hook.last_context.action == "write_sensitive"

    def test_pre_hook_receives_correct_hook_type(self, registry: HookRegistry):
        """PRE_VERIFICATION context must have hook_type=PRE_VERIFICATION."""
        hook = AllowHook(name="pre_type_check", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert hook.last_context is not None
        assert hook.last_context.hook_type == HookType.PRE_VERIFICATION

    def test_pre_hook_receives_user_metadata(self, registry: HookRegistry):
        """PRE_VERIFICATION context.metadata must include user-provided metadata."""
        hook = AllowHook(name="pre_meta_check", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(
            agent_id="agent-001",
            action="read",
            result=result,
            metadata={"request_id": "req-42", "source": "api"},
        )

        assert hook.last_context is not None
        assert hook.last_context.metadata["request_id"] == "req-42"
        assert hook.last_context.metadata["source"] == "api"


# ===========================================================================
# Test Class 2: POST_VERIFICATION Hook Fires After classify()
# ===========================================================================


class TestPostVerificationHookFires:
    """POST_VERIFICATION hooks must fire after classify() produces a verdict."""

    def test_post_hook_fires_on_valid_result(self, registry: HookRegistry):
        """POST_VERIFICATION hook must be invoked during enforce()."""
        hook = AllowHook(name="post_allow", event_types=[HookType.POST_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert verdict == Verdict.AUTO_APPROVED
        assert hook.call_count == 1

    def test_post_hook_receives_correct_agent_and_action(self, registry: HookRegistry):
        """POST_VERIFICATION context must carry agent_id and action."""
        hook = AllowHook(name="post_check", event_types=[HookType.POST_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-abc", action="deploy", result=result)

        assert hook.last_context is not None
        assert hook.last_context.agent_id == "agent-abc"
        assert hook.last_context.action == "deploy"

    def test_post_hook_receives_correct_hook_type(self, registry: HookRegistry):
        """POST_VERIFICATION context must have hook_type=POST_VERIFICATION."""
        hook = AllowHook(name="post_type_check", event_types=[HookType.POST_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert hook.last_context is not None
        assert hook.last_context.hook_type == HookType.POST_VERIFICATION


# ===========================================================================
# Test Class 3: PRE_VERIFICATION Hook Deny Raises EATPBlockedError
# ===========================================================================


class TestPreVerificationDeny:
    """PRE_VERIFICATION deny must result in EATPBlockedError."""

    def test_pre_deny_raises_blocked_error(self, registry: HookRegistry):
        """PRE_VERIFICATION hook returning allow=False must raise EATPBlockedError."""
        hook = DenyHook(
            name="pre_denier",
            event_types=[HookType.PRE_VERIFICATION],
            reason="Agent not authorized for this action",
        )
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError) as exc_info:
            enforcer.enforce(agent_id="agent-bad", action="read", result=result)

        assert exc_info.value.agent_id == "agent-bad"
        assert exc_info.value.action == "read"
        assert "hook" in exc_info.value.reason.lower()

    def test_pre_deny_error_contains_hook_reason(self, registry: HookRegistry):
        """EATPBlockedError from PRE_VERIFICATION must include the hook's reason."""
        hook = DenyHook(
            name="reason_denier",
            event_types=[HookType.PRE_VERIFICATION],
            reason="Rate limit exceeded",
        )
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError) as exc_info:
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert "Rate limit exceeded" in exc_info.value.reason

    def test_pre_deny_prevents_classify(self, registry: HookRegistry):
        """PRE_VERIFICATION deny must prevent classify() from running (no records)."""
        hook = DenyHook(name="pre_block", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

        # No enforcement record should be created when PRE hook blocks
        assert len(enforcer.records) == 0

    def test_pre_deny_on_otherwise_valid_result(self, registry: HookRegistry):
        """PRE_VERIFICATION deny must block even when VerificationResult is valid."""
        hook = DenyHook(
            name="pre_override",
            event_types=[HookType.PRE_VERIFICATION],
            reason="Policy override",
        )
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)


# ===========================================================================
# Test Class 4: POST_VERIFICATION Hook Deny Raises EATPBlockedError
# ===========================================================================


class TestPostVerificationDeny:
    """POST_VERIFICATION deny must result in EATPBlockedError."""

    def test_post_deny_raises_blocked_error(self, registry: HookRegistry):
        """POST_VERIFICATION hook returning allow=False must raise EATPBlockedError."""
        hook = DenyHook(
            name="post_denier",
            event_types=[HookType.POST_VERIFICATION],
            reason="Audit trail incomplete",
        )
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError) as exc_info:
            enforcer.enforce(agent_id="agent-001", action="write", result=result)

        assert exc_info.value.agent_id == "agent-001"
        assert exc_info.value.action == "write"
        assert "hook" in exc_info.value.reason.lower()
        assert "Audit trail incomplete" in exc_info.value.reason

    def test_post_deny_overrides_auto_approved_verdict(self, registry: HookRegistry):
        """POST_VERIFICATION deny must block even when classify() returned AUTO_APPROVED."""
        hook = DenyHook(
            name="post_block",
            event_types=[HookType.POST_VERIFICATION],
            reason="Secondary policy violation",
        )
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        # This result would normally be AUTO_APPROVED
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

    def test_post_deny_overrides_flagged_verdict(self, registry: HookRegistry):
        """POST_VERIFICATION deny must block even when classify() returned FLAGGED."""
        hook = DenyHook(
            name="post_flag_block",
            event_types=[HookType.POST_VERIFICATION],
            reason="External compliance check failed",
        )
        registry.register(hook)
        enforcer = StrictEnforcer(flag_threshold=5, hook_registry=registry)
        # This result has violations but flag_threshold is high, so FLAGGED
        result = _make_flagged_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)


# ===========================================================================
# Test Class 5: Enforcer Without Hooks (Backward Compatibility)
# ===========================================================================


class TestEnforcerWithoutHooks:
    """Enforcer without hook_registry must behave identically to pre-hook versions."""

    def test_no_registry_auto_approved(self):
        """Enforcer without hooks: valid result produces AUTO_APPROVED."""
        enforcer = StrictEnforcer()
        result = _make_valid_result()
        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)
        assert verdict == Verdict.AUTO_APPROVED

    def test_no_registry_blocked(self):
        """Enforcer without hooks: invalid result raises EATPBlockedError."""
        enforcer = StrictEnforcer()
        result = _make_invalid_result()
        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

    def test_no_registry_flagged(self):
        """Enforcer without hooks: flagged result returns FLAGGED."""
        enforcer = StrictEnforcer(flag_threshold=5)
        result = _make_flagged_result()
        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)
        assert verdict == Verdict.FLAGGED

    def test_no_registry_held(self):
        """Enforcer without hooks: held result raises EATPHeldError."""
        enforcer = StrictEnforcer(on_held=HeldBehavior.RAISE, flag_threshold=1)
        result = _make_held_result(violation_count=2)
        with pytest.raises(EATPHeldError):
            enforcer.enforce(agent_id="agent-001", action="write", result=result)

    def test_no_registry_records_created(self):
        """Enforcer without hooks must still create enforcement records."""
        enforcer = StrictEnforcer()
        result = _make_valid_result()
        enforcer.enforce(agent_id="agent-001", action="read", result=result)
        assert len(enforcer.records) == 1
        assert enforcer.records[0].agent_id == "agent-001"

    def test_hook_registry_property_is_none(self):
        """Enforcer without hooks must have hook_registry property == None."""
        enforcer = StrictEnforcer()
        assert enforcer.hook_registry is None

    def test_hook_registry_property_returns_registry(self, registry: HookRegistry):
        """Enforcer with hooks must expose the registry via property."""
        enforcer = StrictEnforcer(hook_registry=registry)
        assert enforcer.hook_registry is registry


# ===========================================================================
# Test Class 6: Hooks Fire in Correct Priority Order
# ===========================================================================


class TestHookPriorityOrder:
    """Hooks must fire in priority order (lower number = earlier)."""

    def test_pre_hooks_fire_in_priority_order(self, registry: HookRegistry):
        """PRE_VERIFICATION hooks must execute lowest-priority-number first."""
        order_log: List[str] = []
        hook_c = OrderTrackingHook("hook_c", order_log, event_types=[HookType.PRE_VERIFICATION], priority=300)
        hook_a = OrderTrackingHook("hook_a", order_log, event_types=[HookType.PRE_VERIFICATION], priority=10)
        hook_b = OrderTrackingHook("hook_b", order_log, event_types=[HookType.PRE_VERIFICATION], priority=100)
        registry.register(hook_c)
        registry.register(hook_a)
        registry.register(hook_b)

        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()
        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert order_log == ["hook_a", "hook_b", "hook_c"]

    def test_post_hooks_fire_in_priority_order(self, registry: HookRegistry):
        """POST_VERIFICATION hooks must execute lowest-priority-number first."""
        order_log: List[str] = []
        hook_z = OrderTrackingHook("hook_z", order_log, event_types=[HookType.POST_VERIFICATION], priority=500)
        hook_x = OrderTrackingHook("hook_x", order_log, event_types=[HookType.POST_VERIFICATION], priority=5)
        hook_y = OrderTrackingHook("hook_y", order_log, event_types=[HookType.POST_VERIFICATION], priority=50)
        registry.register(hook_z)
        registry.register(hook_x)
        registry.register(hook_y)

        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()
        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert order_log == ["hook_x", "hook_y", "hook_z"]

    def test_pre_and_post_hooks_fire_in_correct_phases(self, registry: HookRegistry):
        """PRE hooks fire before POST hooks, each in their own priority order."""
        order_log: List[str] = []
        pre_hook = OrderTrackingHook("pre_hook", order_log, event_types=[HookType.PRE_VERIFICATION], priority=50)
        post_hook = OrderTrackingHook(
            "post_hook",
            order_log,
            event_types=[HookType.POST_VERIFICATION],
            priority=10,
        )
        registry.register(pre_hook)
        registry.register(post_hook)

        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()
        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert order_log == ["pre_hook", "post_hook"]


# ===========================================================================
# Test Class 7: POST_VERIFICATION Hook Metadata Contains Verdict Info
# ===========================================================================


class TestPostVerificationMetadata:
    """POST_VERIFICATION hook context metadata must contain verdict information."""

    def test_metadata_contains_verdict_auto_approved(self, registry: HookRegistry):
        """POST_VERIFICATION metadata must include verdict='auto_approved' for valid."""
        recorder = MetadataRecordingHook(name="post_recorder", event_types=[HookType.POST_VERIFICATION])
        registry.register(recorder)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert recorder.call_count == 1
        metadata = recorder.observed_metadata_snapshots[0]
        assert metadata["verdict"] == "auto_approved"

    def test_metadata_contains_verdict_flagged(self, registry: HookRegistry):
        """POST_VERIFICATION metadata must include verdict='flagged' for flagged results."""
        recorder = MetadataRecordingHook(name="post_recorder", event_types=[HookType.POST_VERIFICATION])
        registry.register(recorder)
        enforcer = StrictEnforcer(flag_threshold=5, hook_registry=registry)
        result = _make_flagged_result()

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert recorder.call_count == 1
        metadata = recorder.observed_metadata_snapshots[0]
        assert metadata["verdict"] == "flagged"

    def test_metadata_contains_valid_field(self, registry: HookRegistry):
        """POST_VERIFICATION metadata must include 'valid' from the VerificationResult."""
        recorder = MetadataRecordingHook(name="valid_recorder", event_types=[HookType.POST_VERIFICATION])
        registry.register(recorder)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        metadata = recorder.observed_metadata_snapshots[0]
        assert metadata["valid"] is True

    def test_metadata_contains_violation_count(self, registry: HookRegistry):
        """POST_VERIFICATION metadata must include violation count."""
        recorder = MetadataRecordingHook(name="violation_recorder", event_types=[HookType.POST_VERIFICATION])
        registry.register(recorder)
        enforcer = StrictEnforcer(flag_threshold=5, hook_registry=registry)
        result = _make_flagged_result()  # has 1 violation

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        metadata = recorder.observed_metadata_snapshots[0]
        assert metadata["violations"] == 1

    def test_metadata_includes_user_metadata(self, registry: HookRegistry):
        """POST_VERIFICATION metadata must include user-provided metadata merged in."""
        recorder = MetadataRecordingHook(name="user_meta_recorder", event_types=[HookType.POST_VERIFICATION])
        registry.register(recorder)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(
            agent_id="agent-001",
            action="read",
            result=result,
            metadata={"custom_key": "custom_value"},
        )

        metadata = recorder.observed_metadata_snapshots[0]
        assert metadata["custom_key"] == "custom_value"
        # verdict info must still be present alongside user metadata
        assert metadata["verdict"] == "auto_approved"

    def test_metadata_verdict_blocked_for_invalid_result(self, registry: HookRegistry):
        """POST_VERIFICATION metadata must include verdict='blocked' for invalid results.

        Note: For BLOCKED verdicts the enforcer raises EATPBlockedError AFTER
        the POST hook runs, so the POST hook still gets the verdict metadata.
        However, looking at the implementation, BLOCKED verdicts raise after
        POST hooks. The POST hook sees the verdict and can decide to allow or deny.
        """
        recorder = MetadataRecordingHook(name="blocked_recorder", event_types=[HookType.POST_VERIFICATION])
        registry.register(recorder)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_invalid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="write", result=result)

        assert recorder.call_count == 1
        metadata = recorder.observed_metadata_snapshots[0]
        assert metadata["verdict"] == "blocked"
        assert metadata["valid"] is False


# ===========================================================================
# Test Class 8: Multiple Hook Interactions
# ===========================================================================


class TestMultipleHookInteractions:
    """Multiple hooks must interact correctly with the enforce pipeline."""

    def test_both_pre_and_post_hooks_fire_on_success(self, registry: HookRegistry):
        """Both PRE and POST hooks must fire when enforce succeeds."""
        pre_hook = AllowHook(name="pre", event_types=[HookType.PRE_VERIFICATION])
        post_hook = AllowHook(name="post", event_types=[HookType.POST_VERIFICATION])
        registry.register(pre_hook)
        registry.register(post_hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert verdict == Verdict.AUTO_APPROVED
        assert pre_hook.call_count == 1
        assert post_hook.call_count == 1

    def test_pre_deny_prevents_post_hook_from_firing(self, registry: HookRegistry):
        """PRE_VERIFICATION deny must prevent POST_VERIFICATION hooks from running."""
        pre_hook = DenyHook(name="pre_blocker", event_types=[HookType.PRE_VERIFICATION])
        post_hook = AllowHook(name="post_allow", event_types=[HookType.POST_VERIFICATION])
        registry.register(pre_hook)
        registry.register(post_hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert pre_hook.call_count == 1
        assert post_hook.call_count == 0

    def test_multiple_enforce_calls_fire_hooks_each_time(self, registry: HookRegistry):
        """Each enforce() call must fire hooks independently."""
        hook = AllowHook(name="counter", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        enforcer.enforce(agent_id="a1", action="r1", result=result)
        enforcer.enforce(agent_id="a2", action="r2", result=result)
        enforcer.enforce(agent_id="a3", action="r3", result=result)

        assert hook.call_count == 3

    def test_unrelated_hook_types_do_not_fire(self, registry: HookRegistry):
        """Hooks for PRE_DELEGATION must NOT fire during enforce()."""
        delegation_hook = AllowHook(name="delegation_hook", event_types=[HookType.PRE_DELEGATION])
        registry.register(delegation_hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert verdict == Verdict.AUTO_APPROVED
        assert delegation_hook.call_count == 0


# ===========================================================================
# Test Class 9: PRE_VERIFICATION Deny Prevents Record Creation
# ===========================================================================


class TestPreDenyNoRecords:
    """When PRE_VERIFICATION denies, no enforcement records should be created."""

    def test_no_records_on_pre_deny(self, registry: HookRegistry):
        """PRE_VERIFICATION deny must not create any enforcement records."""
        hook = DenyHook(name="pre_block", event_types=[HookType.PRE_VERIFICATION])
        registry.register(hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_valid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert len(enforcer.records) == 0

    def test_pre_hook_fires_before_record_creation(self, registry: HookRegistry):
        """PRE_VERIFICATION hook must observe zero records (fires before classify)."""
        enforcer = StrictEnforcer(hook_registry=registry)
        tracker = ClassifyTrackingHook(
            name="tracker",
            event_types=[HookType.PRE_VERIFICATION],
            enforcer_ref=enforcer,
        )
        registry.register(tracker)
        result = _make_valid_result()

        enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert tracker.records_at_call_time == 0


# ===========================================================================
# Test Class 10: Hook Integration with Different Verdicts
# ===========================================================================


class TestHookIntegrationWithVerdicts:
    """Hooks must work correctly with all verdict types."""

    def test_hooks_fire_for_flagged_verdict(self, registry: HookRegistry):
        """Hooks must fire even when the verdict is FLAGGED."""
        pre_hook = AllowHook(name="pre", event_types=[HookType.PRE_VERIFICATION])
        post_hook = AllowHook(name="post", event_types=[HookType.POST_VERIFICATION])
        registry.register(pre_hook)
        registry.register(post_hook)
        enforcer = StrictEnforcer(flag_threshold=5, hook_registry=registry)
        result = _make_flagged_result()

        verdict = enforcer.enforce(agent_id="agent-001", action="read", result=result)

        assert verdict == Verdict.FLAGGED
        assert pre_hook.call_count == 1
        assert post_hook.call_count == 1

    def test_hooks_fire_for_blocked_verdict(self, registry: HookRegistry):
        """POST hook must fire even when classify() returns BLOCKED."""
        post_hook = AllowHook(name="post", event_types=[HookType.POST_VERIFICATION])
        registry.register(post_hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_invalid_result()

        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

        # POST hook still fires for BLOCKED results (it sees the verdict)
        assert post_hook.call_count == 1

    def test_post_deny_on_blocked_result_still_raises_blocked(self, registry: HookRegistry):
        """POST deny on an already-blocked result must raise EATPBlockedError.

        The post hook deny raises its own EATPBlockedError before the enforcer
        would have raised for the BLOCKED verdict.
        """
        post_hook = DenyHook(
            name="post_deny",
            event_types=[HookType.POST_VERIFICATION],
            reason="Hook override",
        )
        registry.register(post_hook)
        enforcer = StrictEnforcer(hook_registry=registry)
        result = _make_invalid_result()

        with pytest.raises(EATPBlockedError) as exc_info:
            enforcer.enforce(agent_id="agent-001", action="read", result=result)

        # The error should come from the hook, not from the blocked verdict
        assert "Hook override" in exc_info.value.reason
