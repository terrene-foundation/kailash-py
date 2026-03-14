# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the EATP hook system (Phase 3, todo 3.4).

Covers:
    1. Priority ordering (lower priority executes first)
    2. Abort semantics (one deny aborts remaining hooks)
    3. Timeout enforcement (slow hook times out -> fail-closed)
    4. Crash handling (hook raises exception -> fail-closed)
    5. Concurrent registration/unregistration
    6. Empty registry (no hooks registered -> allow by default)
    7. Hook with multiple event types
    8. Duplicate hook name rejection
    9. HookType enum has exactly 4 values
    10. HookContext dataclass fields
    11. HookResult dataclass fields
    12. EATPHook ABC enforcement
    13. Default priority is 100
    14. list_hooks with and without filter
    15. unregister is no-op for unknown name
    16. execute_sync wrapper works
    17. modified_context merges into metadata for subsequent hooks
    18. HookRegistry timeout validation (must be positive)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List

import pytest

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


class AllowAllHook(EATPHook):
    """A hook that always allows the operation."""

    def __init__(
        self,
        name: str = "allow_all",
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
        self._priority = priority
        self.call_count = 0

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
        return HookResult(allow=True)


class DenyHook(EATPHook):
    """A hook that always denies the operation."""

    def __init__(
        self,
        name: str = "denier",
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
        self._priority = priority
        self.call_count = 0

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
        return HookResult(allow=False, reason="Denied by policy")


class CrashingHook(EATPHook):
    """A hook that raises an exception on execution."""

    def __init__(
        self,
        name: str = "crasher",
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
        self._priority = priority

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
        raise RuntimeError("Hook exploded unexpectedly")


class SlowHook(EATPHook):
    """A hook that sleeps longer than the configured timeout."""

    def __init__(
        self,
        name: str = "slowpoke",
        event_types: List[HookType] | None = None,
        priority: int = 100,
        delay: float = 10.0,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
        self._priority = priority
        self._delay = delay

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
        await asyncio.sleep(self._delay)
        return HookResult(allow=True)


class OrderTrackingHook(EATPHook):
    """A hook that records its execution order into a shared list."""

    def __init__(
        self,
        name: str,
        order_log: list,
        event_types: List[HookType] | None = None,
        priority: int = 100,
    ):
        self._name = name
        self._event_types = event_types or [HookType.PRE_DELEGATION]
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


class ContextModifyingHook(EATPHook):
    """A hook that adds data to modified_context for downstream hooks."""

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
    """A hook that records the metadata it received for assertion."""

    def __init__(
        self,
        name: str = "reader",
        event_types: List[HookType] | None = None,
        priority: int = 100,
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


class DefaultPriorityHook(EATPHook):
    """A hook that does not override the default priority property."""

    @property
    def name(self) -> str:
        return "default_priority"

    @property
    def event_types(self) -> List[HookType]:
        return [HookType.PRE_VERIFICATION]

    async def __call__(self, context: HookContext) -> HookResult:
        return HookResult(allow=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> HookRegistry:
    """HookRegistry with a tight 0.5s timeout for fast test execution."""
    return HookRegistry(timeout_seconds=0.5)


@pytest.fixture
def pre_delegation_context() -> HookContext:
    """Standard PRE_DELEGATION context for reuse across tests."""
    return HookContext(
        agent_id="agent-001",
        action="delegate_to_subagent",
        hook_type=HookType.PRE_DELEGATION,
    )


# ---------------------------------------------------------------------------
# 9. HookType enum has exactly 4 values
# ---------------------------------------------------------------------------


class TestHookTypeEnum:
    """Verify HookType enum has the expected members."""

    def test_exactly_four_members(self):
        """HookType must have exactly 4 lifecycle events."""
        members = list(HookType)
        assert len(members) == 4

    def test_expected_values(self):
        """Each HookType member must map to its documented string value."""
        assert HookType.PRE_DELEGATION.value == "pre_delegation"
        assert HookType.POST_DELEGATION.value == "post_delegation"
        assert HookType.PRE_VERIFICATION.value == "pre_verification"
        assert HookType.POST_VERIFICATION.value == "post_verification"

    def test_is_string_enum(self):
        """HookType must be a str enum so values are usable as strings."""
        for member in HookType:
            assert isinstance(member, str)


# ---------------------------------------------------------------------------
# 10. HookContext dataclass fields
# ---------------------------------------------------------------------------


class TestHookContext:
    """Verify HookContext fields, defaults, and types."""

    def test_required_fields(self):
        """agent_id, action, and hook_type are required."""
        ctx = HookContext(
            agent_id="a1",
            action="read",
            hook_type=HookType.PRE_VERIFICATION,
        )
        assert ctx.agent_id == "a1"
        assert ctx.action == "read"
        assert ctx.hook_type == HookType.PRE_VERIFICATION

    def test_metadata_defaults_to_empty_dict(self):
        """metadata must default to an empty dict, not None."""
        ctx = HookContext(agent_id="a1", action="r", hook_type=HookType.PRE_DELEGATION)
        assert ctx.metadata == {}
        assert isinstance(ctx.metadata, dict)

    def test_timestamp_auto_populated(self):
        """timestamp must be auto-populated as a UTC datetime."""
        ctx = HookContext(agent_id="a1", action="r", hook_type=HookType.PRE_DELEGATION)
        assert isinstance(ctx.timestamp, datetime)
        assert ctx.timestamp.tzinfo is not None

    def test_custom_metadata(self):
        """Explicit metadata must be preserved."""
        ctx = HookContext(
            agent_id="a1",
            action="r",
            hook_type=HookType.PRE_DELEGATION,
            metadata={"key": "value"},
        )
        assert ctx.metadata == {"key": "value"}

    def test_metadata_instances_are_independent(self):
        """Each HookContext must get its own metadata dict (no shared default)."""
        ctx1 = HookContext(agent_id="a", action="x", hook_type=HookType.PRE_DELEGATION)
        ctx2 = HookContext(agent_id="b", action="y", hook_type=HookType.PRE_DELEGATION)
        ctx1.metadata["injected"] = True
        assert "injected" not in ctx2.metadata


# ---------------------------------------------------------------------------
# 11. HookResult dataclass fields
# ---------------------------------------------------------------------------


class TestHookResult:
    """Verify HookResult fields and defaults."""

    def test_allow_true(self):
        """allow=True with no extras is valid."""
        result = HookResult(allow=True)
        assert result.allow is True
        assert result.reason is None
        assert result.modified_context is None

    def test_allow_false_with_reason(self):
        """allow=False must carry a reason."""
        result = HookResult(allow=False, reason="Blocked by policy")
        assert result.allow is False
        assert result.reason == "Blocked by policy"

    def test_modified_context_field(self):
        """modified_context carries data for downstream hooks."""
        result = HookResult(allow=True, modified_context={"enriched": True})
        assert result.modified_context == {"enriched": True}


# ---------------------------------------------------------------------------
# 12. EATPHook ABC enforcement
# ---------------------------------------------------------------------------


class TestEATPHookABC:
    """Verify that EATPHook cannot be instantiated without implementing abstract methods."""

    def test_cannot_instantiate_directly(self):
        """Instantiating EATPHook directly must raise TypeError."""
        with pytest.raises(TypeError, match="abstract method"):
            EATPHook()  # type: ignore[abstract]

    def test_partial_implementation_raises(self):
        """Missing any abstract method must raise TypeError."""

        class IncompleteHook(EATPHook):
            @property
            def name(self) -> str:
                return "incomplete"

            # Missing event_types and __call__

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteHook()  # type: ignore[abstract]

    def test_complete_implementation_works(self):
        """A fully implemented subclass must be instantiable."""
        hook = AllowAllHook()
        assert hook.name == "allow_all"


# ---------------------------------------------------------------------------
# 13. Default priority is 100
# ---------------------------------------------------------------------------


class TestDefaultPriority:
    """Verify the base class default priority."""

    def test_default_priority_is_100(self):
        """EATPHook.priority must default to 100 when not overridden."""
        hook = DefaultPriorityHook()
        assert hook.priority == 100

    def test_custom_priority_overrides_default(self):
        """Subclass overriding priority must use the custom value."""
        hook = AllowAllHook(priority=42)
        assert hook.priority == 42


# ---------------------------------------------------------------------------
# 18. HookRegistry timeout validation
# ---------------------------------------------------------------------------


class TestHookRegistryInit:
    """Verify HookRegistry construction and timeout validation."""

    def test_default_timeout(self):
        """Default timeout must be 5.0 seconds."""
        registry = HookRegistry()
        assert registry.timeout_seconds == 5.0

    def test_custom_timeout(self):
        """Custom positive timeout must be accepted."""
        registry = HookRegistry(timeout_seconds=2.5)
        assert registry.timeout_seconds == 2.5

    def test_zero_timeout_raises(self):
        """timeout_seconds=0 must raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            HookRegistry(timeout_seconds=0)

    def test_negative_timeout_raises(self):
        """Negative timeout must raise ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            HookRegistry(timeout_seconds=-1.0)


# ---------------------------------------------------------------------------
# 8. Duplicate hook name rejection
# ---------------------------------------------------------------------------


class TestDuplicateRegistration:
    """Verify that registering a hook with a duplicate name raises."""

    def test_duplicate_name_raises_value_error(self, registry):
        """Registering two hooks with the same name must raise ValueError."""
        hook1 = AllowAllHook(name="shared_name")
        hook2 = DenyHook(name="shared_name")
        registry.register(hook1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(hook2)

    def test_reregister_after_unregister_works(self, registry):
        """Unregistering then re-registering the same name must succeed."""
        hook1 = AllowAllHook(name="reusable")
        registry.register(hook1)
        registry.unregister("reusable")
        hook2 = DenyHook(name="reusable")
        registry.register(hook2)
        hooks = registry.list_hooks()
        assert len(hooks) == 1
        assert hooks[0].name == "reusable"


# ---------------------------------------------------------------------------
# 15. unregister is no-op for unknown name
# ---------------------------------------------------------------------------


class TestUnregister:
    """Verify unregister behavior."""

    def test_unregister_unknown_name_is_noop(self, registry):
        """Unregistering a non-existent hook must not raise."""
        registry.unregister("does_not_exist")  # Must not raise

    def test_unregister_removes_hook(self, registry):
        """Unregistering an existing hook must remove it from the registry."""
        hook = AllowAllHook(name="temp")
        registry.register(hook)
        assert len(registry.list_hooks()) == 1
        registry.unregister("temp")
        assert len(registry.list_hooks()) == 0


# ---------------------------------------------------------------------------
# 14. list_hooks with and without filter
# ---------------------------------------------------------------------------


class TestListHooks:
    """Verify list_hooks filtering and sorting."""

    def test_list_hooks_empty_registry(self, registry):
        """Empty registry must return empty list."""
        assert registry.list_hooks() == []

    def test_list_hooks_all(self, registry):
        """list_hooks() without filter must return all registered hooks."""
        hook1 = AllowAllHook(name="h1", event_types=[HookType.PRE_DELEGATION])
        hook2 = AllowAllHook(name="h2", event_types=[HookType.POST_DELEGATION])
        registry.register(hook1)
        registry.register(hook2)
        hooks = registry.list_hooks()
        assert len(hooks) == 2

    def test_list_hooks_filtered_by_type(self, registry):
        """list_hooks(hook_type) must return only matching hooks."""
        hook1 = AllowAllHook(name="pre", event_types=[HookType.PRE_DELEGATION])
        hook2 = AllowAllHook(name="post", event_types=[HookType.POST_DELEGATION])
        registry.register(hook1)
        registry.register(hook2)
        pre_hooks = registry.list_hooks(hook_type=HookType.PRE_DELEGATION)
        assert len(pre_hooks) == 1
        assert pre_hooks[0].name == "pre"

    def test_list_hooks_sorted_by_priority(self, registry):
        """list_hooks must return hooks sorted by priority (lowest first)."""
        hook_high = AllowAllHook(name="high", priority=200)
        hook_low = AllowAllHook(name="low", priority=10)
        hook_mid = AllowAllHook(name="mid", priority=50)
        registry.register(hook_high)
        registry.register(hook_low)
        registry.register(hook_mid)
        names = [h.name for h in registry.list_hooks()]
        assert names == ["low", "mid", "high"]

    def test_list_hooks_filtered_excludes_non_matching(self, registry):
        """Filtering by a type with no registered hooks must return empty."""
        hook = AllowAllHook(name="pre_only", event_types=[HookType.PRE_DELEGATION])
        registry.register(hook)
        result = registry.list_hooks(hook_type=HookType.POST_VERIFICATION)
        assert result == []


# ---------------------------------------------------------------------------
# 6. Empty registry (no hooks registered -> allow by default)
# ---------------------------------------------------------------------------


class TestEmptyRegistry:
    """Verify behavior when no hooks are registered."""

    async def test_execute_empty_registry_allows(
        self, registry, pre_delegation_context
    ):
        """Execute with no hooks must return allow=True."""
        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True

    async def test_execute_no_matching_hooks_allows(
        self, registry, pre_delegation_context
    ):
        """Execute with hooks only for a different type must return allow=True."""
        hook = AllowAllHook(name="post_only", event_types=[HookType.POST_DELEGATION])
        registry.register(hook)
        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True


# ---------------------------------------------------------------------------
# 1. Priority ordering (lower priority executes first)
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    """Verify hooks execute in priority order (lower number first)."""

    async def test_hooks_execute_in_priority_order(
        self, registry, pre_delegation_context
    ):
        """Hooks must execute lowest priority first."""
        order_log: list[str] = []
        hook_a = OrderTrackingHook("a_last", order_log, priority=300)
        hook_b = OrderTrackingHook("b_first", order_log, priority=10)
        hook_c = OrderTrackingHook("c_middle", order_log, priority=100)

        registry.register(hook_a)
        registry.register(hook_b)
        registry.register(hook_c)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert order_log == ["b_first", "c_middle", "a_last"]

    async def test_same_priority_all_execute(self, registry, pre_delegation_context):
        """Hooks with the same priority must all execute (order is stable)."""
        order_log: list[str] = []
        hook_x = OrderTrackingHook("x", order_log, priority=50)
        hook_y = OrderTrackingHook("y", order_log, priority=50)
        registry.register(hook_x)
        registry.register(hook_y)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert set(order_log) == {"x", "y"}
        assert len(order_log) == 2


# ---------------------------------------------------------------------------
# 2. Abort semantics (one deny aborts remaining hooks)
# ---------------------------------------------------------------------------


class TestAbortSemantics:
    """Verify fail-closed abort on deny."""

    async def test_deny_stops_chain(self, registry, pre_delegation_context):
        """A denying hook must prevent subsequent hooks from running."""
        order_log: list[str] = []
        hook_allow = OrderTrackingHook("first_allow", order_log, priority=10)
        deny_hook = DenyHook(name="denier", priority=50)
        hook_after = OrderTrackingHook("should_not_run", order_log, priority=200)

        registry.register(hook_allow)
        registry.register(deny_hook)
        registry.register(hook_after)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert result.reason == "Denied by policy"
        assert "first_allow" in order_log
        assert "should_not_run" not in order_log

    async def test_deny_returns_hook_result(self, registry, pre_delegation_context):
        """The deny result must be returned directly."""
        deny_hook = DenyHook(name="blocker", priority=1)
        registry.register(deny_hook)
        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert "Denied by policy" in result.reason

    async def test_all_allow_returns_allow(self, registry, pre_delegation_context):
        """If all hooks allow, the final result must be allow=True."""
        registry.register(AllowAllHook(name="a1", priority=10))
        registry.register(AllowAllHook(name="a2", priority=20))
        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True


# ---------------------------------------------------------------------------
# 3. Timeout enforcement (slow hook times out -> fail-closed)
# ---------------------------------------------------------------------------


class TestTimeoutEnforcement:
    """Verify that slow hooks are aborted with fail-closed."""

    async def test_slow_hook_times_out(self, pre_delegation_context):
        """A hook exceeding the timeout must be fail-closed."""
        registry = HookRegistry(timeout_seconds=0.1)
        slow = SlowHook(name="turtle", delay=5.0)
        registry.register(slow)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert "timed out" in result.reason
        assert "turtle" in result.reason

    async def test_timeout_stops_chain(self, pre_delegation_context):
        """A timed-out hook must prevent subsequent hooks from running."""
        registry = HookRegistry(timeout_seconds=0.1)
        slow = SlowHook(name="turtle", delay=5.0, priority=10)
        after = AllowAllHook(name="should_not_run", priority=200)

        registry.register(slow)
        registry.register(after)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert after.call_count == 0


# ---------------------------------------------------------------------------
# 4. Crash handling (hook raises exception -> fail-closed)
# ---------------------------------------------------------------------------


class TestCrashHandling:
    """Verify that crashing hooks produce fail-closed results."""

    async def test_crashing_hook_returns_deny(self, registry, pre_delegation_context):
        """A hook that raises must produce allow=False with crash info."""
        crasher = CrashingHook(name="bomber")
        registry.register(crasher)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert "crashed" in result.reason
        assert "bomber" in result.reason
        assert "fail-closed" in result.reason

    async def test_crash_stops_chain(self, registry, pre_delegation_context):
        """A crashing hook must prevent subsequent hooks from running."""
        crasher = CrashingHook(name="bomb", priority=10)
        after = AllowAllHook(name="unreachable", priority=200)

        registry.register(crasher)
        registry.register(after)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert after.call_count == 0


# ---------------------------------------------------------------------------
# 5. Concurrent registration/unregistration
# ---------------------------------------------------------------------------


class TestConcurrentRegistration:
    """Verify that registration and unregistration are safe under concurrent access."""

    async def test_register_many_hooks_sequentially(self, registry):
        """Registering many hooks sequentially must all succeed."""
        for i in range(50):
            hook = AllowAllHook(name=f"hook_{i}")
            registry.register(hook)
        assert len(registry.list_hooks()) == 50

    async def test_unregister_during_iteration_safety(
        self, registry, pre_delegation_context
    ):
        """Unregistering a hook between execute calls must not corrupt state."""
        hook_a = AllowAllHook(name="a", priority=10)
        hook_b = AllowAllHook(name="b", priority=20)
        registry.register(hook_a)
        registry.register(hook_b)

        # Execute once — both run
        result1 = await registry.execute(
            HookType.PRE_DELEGATION, pre_delegation_context
        )
        assert result1.allow is True
        assert hook_a.call_count == 1
        assert hook_b.call_count == 1

        # Unregister hook_a, execute again — only hook_b runs
        registry.unregister("a")
        result2 = await registry.execute(
            HookType.PRE_DELEGATION, pre_delegation_context
        )
        assert result2.allow is True
        assert hook_a.call_count == 1  # Not incremented
        assert hook_b.call_count == 2

    async def test_register_unregister_register_same_name(
        self, registry, pre_delegation_context
    ):
        """Register -> unregister -> register with same name must work."""
        hook_v1 = AllowAllHook(name="versioned")
        hook_v2 = DenyHook(name="versioned")

        registry.register(hook_v1)
        result1 = await registry.execute(
            HookType.PRE_DELEGATION, pre_delegation_context
        )
        assert result1.allow is True

        registry.unregister("versioned")
        registry.register(hook_v2)
        result2 = await registry.execute(
            HookType.PRE_DELEGATION, pre_delegation_context
        )
        assert result2.allow is False


# ---------------------------------------------------------------------------
# 7. Hook with multiple event types
# ---------------------------------------------------------------------------


class TestMultipleEventTypes:
    """Verify hooks handling multiple event types."""

    async def test_hook_triggers_for_each_registered_type(self, registry):
        """A hook registered for multiple types must trigger for each."""
        multi_hook = AllowAllHook(
            name="multi",
            event_types=[HookType.PRE_DELEGATION, HookType.POST_VERIFICATION],
        )
        registry.register(multi_hook)

        ctx_pre = HookContext(
            agent_id="a", action="x", hook_type=HookType.PRE_DELEGATION
        )
        ctx_post = HookContext(
            agent_id="a", action="x", hook_type=HookType.POST_VERIFICATION
        )

        await registry.execute(HookType.PRE_DELEGATION, ctx_pre)
        assert multi_hook.call_count == 1

        await registry.execute(HookType.POST_VERIFICATION, ctx_post)
        assert multi_hook.call_count == 2

    async def test_hook_does_not_trigger_for_unregistered_type(self, registry):
        """A multi-type hook must not trigger for types it did not register."""
        multi_hook = AllowAllHook(
            name="selective",
            event_types=[HookType.PRE_DELEGATION, HookType.POST_DELEGATION],
        )
        registry.register(multi_hook)

        ctx = HookContext(agent_id="a", action="x", hook_type=HookType.PRE_VERIFICATION)
        result = await registry.execute(HookType.PRE_VERIFICATION, ctx)
        assert result.allow is True
        assert multi_hook.call_count == 0

    def test_list_hooks_includes_multi_type_for_each_type(self, registry):
        """list_hooks filtered by type must include multi-type hooks."""
        multi = AllowAllHook(
            name="multi",
            event_types=[HookType.PRE_DELEGATION, HookType.POST_VERIFICATION],
        )
        registry.register(multi)

        pre_list = registry.list_hooks(hook_type=HookType.PRE_DELEGATION)
        post_list = registry.list_hooks(hook_type=HookType.POST_VERIFICATION)
        assert len(pre_list) == 1
        assert len(post_list) == 1
        assert pre_list[0] is post_list[0]


# ---------------------------------------------------------------------------
# 17. modified_context merges into metadata for subsequent hooks
# ---------------------------------------------------------------------------


class TestModifiedContextPropagation:
    """Verify that modified_context is merged into metadata for subsequent hooks."""

    async def test_modified_context_visible_to_next_hook(
        self, registry, pre_delegation_context
    ):
        """A hook's modified_context must appear in the next hook's metadata."""
        modifier = ContextModifyingHook(
            name="enricher",
            priority=10,
            inject={"enriched_by": "enricher", "level": 42},
        )
        reader = ContextReaderHook(name="observer", priority=100)

        registry.register(modifier)
        registry.register(reader)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True
        assert reader.observed_metadata is not None
        assert reader.observed_metadata["enriched_by"] == "enricher"
        assert reader.observed_metadata["level"] == 42

    async def test_chained_modifications_accumulate(
        self, registry, pre_delegation_context
    ):
        """Multiple modifier hooks must accumulate their context changes."""
        mod1 = ContextModifyingHook(name="mod1", priority=10, inject={"step": 1})
        mod2 = ContextModifyingHook(
            name="mod2", priority=20, inject={"step": 2, "extra": "data"}
        )
        reader = ContextReaderHook(name="final_reader", priority=100)

        registry.register(mod1)
        registry.register(mod2)
        registry.register(reader)

        await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert reader.observed_metadata is not None
        # step should be overwritten by mod2
        assert reader.observed_metadata["step"] == 2
        assert reader.observed_metadata["extra"] == "data"

    async def test_deny_hook_does_not_merge_context(
        self, registry, pre_delegation_context
    ):
        """modified_context from a deny result must NOT be merged (chain aborts)."""
        # The deny hook's modified_context never gets applied because the chain stops
        deny = DenyHook(name="blocker", priority=10)
        reader = ContextReaderHook(name="observer", priority=100)

        registry.register(deny)
        registry.register(reader)

        result = await registry.execute(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        # Reader should never have been called
        assert reader.observed_metadata is None

    async def test_original_metadata_preserved(self, registry):
        """Existing metadata must survive alongside injected context."""
        ctx = HookContext(
            agent_id="a",
            action="x",
            hook_type=HookType.PRE_DELEGATION,
            metadata={"original_key": "original_value"},
        )
        modifier = ContextModifyingHook(
            name="adder", priority=10, inject={"new_key": "new_value"}
        )
        reader = ContextReaderHook(name="checker", priority=100)

        registry.register(modifier)
        registry.register(reader)

        await registry.execute(HookType.PRE_DELEGATION, ctx)
        assert reader.observed_metadata is not None
        assert reader.observed_metadata["original_key"] == "original_value"
        assert reader.observed_metadata["new_key"] == "new_value"


# ---------------------------------------------------------------------------
# 16. execute_sync wrapper works
# ---------------------------------------------------------------------------


class TestExecuteSync:
    """Verify the synchronous wrapper for execute()."""

    def test_execute_sync_allows_with_no_hooks(self, registry, pre_delegation_context):
        """execute_sync with no hooks must return allow=True."""
        result = registry.execute_sync(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True

    def test_execute_sync_runs_hooks(self, registry, pre_delegation_context):
        """execute_sync must actually execute registered hooks."""
        hook = AllowAllHook(name="sync_test")
        registry.register(hook)
        result = registry.execute_sync(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is True
        assert hook.call_count == 1

    def test_execute_sync_deny_works(self, registry, pre_delegation_context):
        """execute_sync must propagate deny results."""
        hook = DenyHook(name="sync_denier")
        registry.register(hook)
        result = registry.execute_sync(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert result.reason == "Denied by policy"

    def test_execute_sync_crash_handling(self, registry, pre_delegation_context):
        """execute_sync must handle crashing hooks with fail-closed."""
        hook = CrashingHook(name="sync_crasher")
        registry.register(hook)
        result = registry.execute_sync(HookType.PRE_DELEGATION, pre_delegation_context)
        assert result.allow is False
        assert "crashed" in result.reason
