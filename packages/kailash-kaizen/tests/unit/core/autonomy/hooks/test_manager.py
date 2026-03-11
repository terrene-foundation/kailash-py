"""
Unit tests for HookManager.

Tests registration, triggering, error handling, stats, and filesystem discovery.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
from kaizen.core.autonomy.hooks import (
    BaseHook,
    HookContext,
    HookEvent,
    HookManager,
    HookPriority,
    HookResult,
)


class TestHook(BaseHook):
    """Test hook for unit tests"""

    def __init__(self, name="test_hook", should_fail=False, delay=0.0):
        super().__init__(name=name)
        self.should_fail = should_fail
        self.delay = delay
        self.call_count = 0
        self.contexts = []

    async def handle(self, context: HookContext) -> HookResult:
        self.call_count += 1
        self.contexts.append(context)

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.should_fail:
            raise ValueError("Intentional failure")

        return HookResult(success=True, data={"test": "data"})


class TestHookManager:
    """Test HookManager class"""

    def test_create_manager(self):
        """Test creating a HookManager"""
        manager = HookManager()
        assert manager is not None
        assert len(manager._hooks) == 0

    def test_register_hook(self):
        """Test registering a hook"""
        manager = HookManager()
        hook = TestHook()

        manager.register(HookEvent.PRE_TOOL_USE, hook)

        assert HookEvent.PRE_TOOL_USE in manager._hooks
        assert len(manager._hooks[HookEvent.PRE_TOOL_USE]) == 1

    def test_register_with_priority(self):
        """Test registering hooks with priorities"""
        manager = HookManager()
        hook1 = TestHook(name="high_priority")
        hook2 = TestHook(name="normal_priority")
        hook3 = TestHook(name="critical_priority")

        manager.register(HookEvent.PRE_TOOL_USE, hook1, priority=HookPriority.HIGH)
        manager.register(HookEvent.PRE_TOOL_USE, hook2, priority=HookPriority.NORMAL)
        manager.register(HookEvent.PRE_TOOL_USE, hook3, priority=HookPriority.CRITICAL)

        # Check hooks are sorted by priority (CRITICAL, HIGH, NORMAL)
        hooks = manager._hooks[HookEvent.PRE_TOOL_USE]
        assert hooks[0][1].name == "critical_priority"
        assert hooks[1][1].name == "high_priority"
        assert hooks[2][1].name == "normal_priority"

    def test_register_function_hook(self):
        """Test registering a plain async function as hook"""
        manager = HookManager()

        async def my_hook(context: HookContext) -> HookResult:
            return HookResult(success=True)

        manager.register(HookEvent.PRE_TOOL_USE, my_hook)

        assert len(manager._hooks[HookEvent.PRE_TOOL_USE]) == 1

    def test_register_with_string_event(self):
        """Test registering with string event type"""
        manager = HookManager()
        hook = TestHook()

        manager.register("pre_tool_use", hook)

        assert HookEvent.PRE_TOOL_USE in manager._hooks

    def test_register_invalid_event(self):
        """Test registering with invalid event type"""
        manager = HookManager()
        hook = TestHook()

        with pytest.raises(ValueError, match="Invalid event type"):
            manager.register("invalid_event", hook)

    def test_unregister_all_hooks(self):
        """Test unregistering all hooks for an event"""
        manager = HookManager()
        hook1 = TestHook(name="hook1")
        hook2 = TestHook(name="hook2")

        manager.register(HookEvent.PRE_TOOL_USE, hook1)
        manager.register(HookEvent.PRE_TOOL_USE, hook2)

        removed = manager.unregister(HookEvent.PRE_TOOL_USE)

        assert removed == 2
        assert HookEvent.PRE_TOOL_USE not in manager._hooks

    def test_unregister_specific_hook(self):
        """Test unregistering a specific hook"""
        manager = HookManager()
        hook1 = TestHook(name="hook1")
        hook2 = TestHook(name="hook2")

        manager.register(HookEvent.PRE_TOOL_USE, hook1)
        manager.register(HookEvent.PRE_TOOL_USE, hook2)

        removed = manager.unregister(HookEvent.PRE_TOOL_USE, hook1)

        assert removed == 1
        assert len(manager._hooks[HookEvent.PRE_TOOL_USE]) == 1
        assert manager._hooks[HookEvent.PRE_TOOL_USE][0][1] == hook2

    @pytest.mark.asyncio
    async def test_trigger_hook(self):
        """Test triggering a hook"""
        manager = HookManager()
        hook = TestHook()

        manager.register(HookEvent.PRE_TOOL_USE, hook)

        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={"tool_name": "search"},
        )

        assert len(results) == 1
        assert results[0].success is True
        assert hook.call_count == 1
        assert hook.contexts[0].agent_id == "test_agent"
        assert hook.contexts[0].data == {"tool_name": "search"}

    @pytest.mark.asyncio
    async def test_trigger_multiple_hooks(self):
        """Test triggering multiple hooks"""
        manager = HookManager()
        hook1 = TestHook(name="hook1")
        hook2 = TestHook(name="hook2")

        manager.register(HookEvent.PRE_TOOL_USE, hook1)
        manager.register(HookEvent.PRE_TOOL_USE, hook2)

        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE, agent_id="test_agent", data={}
        )

        assert len(results) == 2
        assert hook1.call_count == 1
        assert hook2.call_count == 1

    @pytest.mark.asyncio
    async def test_trigger_with_string_event(self):
        """Test triggering with string event type"""
        manager = HookManager()
        hook = TestHook()

        manager.register(HookEvent.PRE_TOOL_USE, hook)

        results = await manager.trigger("pre_tool_use", agent_id="test_agent", data={})

        assert len(results) == 1
        assert hook.call_count == 1

    @pytest.mark.asyncio
    async def test_trigger_no_hooks(self):
        """Test triggering when no hooks registered"""
        manager = HookManager()

        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE, agent_id="test_agent", data={}
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_hook_error_isolation(self):
        """Test hook failures don't crash execution"""
        manager = HookManager()
        failing_hook = TestHook(name="failing", should_fail=True)
        success_hook = TestHook(name="success")

        manager.register(HookEvent.PRE_TOOL_USE, failing_hook)
        manager.register(HookEvent.PRE_TOOL_USE, success_hook)

        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE, agent_id="test_agent", data={}
        )

        # Both hooks executed despite first one failing
        assert len(results) == 2
        assert results[0].success is False
        assert "Intentional failure" in results[0].error
        assert results[1].success is True

    @pytest.mark.asyncio
    async def test_hook_timeout(self):
        """Test hook timeout enforcement"""
        manager = HookManager()
        slow_hook = TestHook(name="slow", delay=2.0)

        manager.register(HookEvent.PRE_TOOL_USE, slow_hook)

        # Trigger with 0.5s timeout (hook takes 2s)
        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE, agent_id="test_agent", data={}, timeout=0.5
        )

        assert len(results) == 1
        assert results[0].success is False
        assert "timeout" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_trigger_with_metadata(self):
        """Test triggering with metadata"""
        manager = HookManager()
        hook = TestHook()

        manager.register(HookEvent.PRE_TOOL_USE, hook)

        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={},
            metadata={"session_id": "abc123"},
        )

        assert len(results) == 1
        assert hook.contexts[0].metadata == {"session_id": "abc123"}

    def test_get_stats(self):
        """Test getting hook statistics"""
        manager = HookManager()
        assert manager.get_stats() == {}

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Test hook statistics are tracked"""
        manager = HookManager()
        hook = TestHook(name="tracked_hook")

        manager.register(HookEvent.PRE_TOOL_USE, hook)

        # Trigger multiple times
        await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="test", data={})
        await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="test", data={})

        stats = manager.get_stats()
        assert "tracked_hook" in stats
        assert stats["tracked_hook"]["call_count"] == 2
        assert stats["tracked_hook"]["success_count"] == 2
        assert stats["tracked_hook"]["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_failures(self):
        """Test stats track failures"""
        manager = HookManager()
        failing_hook = TestHook(name="failing", should_fail=True)

        manager.register(HookEvent.PRE_TOOL_USE, failing_hook)

        await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="test", data={})

        stats = manager.get_stats()
        assert stats["failing"]["call_count"] == 1
        assert stats["failing"]["success_count"] == 0
        assert stats["failing"]["failure_count"] == 1


class TestFilesystemDiscovery:
    """Test filesystem hook discovery"""

    @pytest.mark.asyncio
    async def test_discover_hooks_nonexistent_dir(self):
        """Test discovery with nonexistent directory"""
        manager = HookManager()

        with pytest.raises(OSError, match="not found"):
            await manager.discover_filesystem_hooks(Path("/nonexistent"))

    @pytest.mark.asyncio
    async def test_discover_hooks_not_a_directory(self):
        """Test discovery with file instead of directory"""
        manager = HookManager()

        with tempfile.NamedTemporaryFile() as tf:
            with pytest.raises(OSError, match="Not a directory"):
                await manager.discover_filesystem_hooks(Path(tf.name))

    @pytest.mark.asyncio
    async def test_discover_hooks_empty_directory(self):
        """Test discovery in empty directory"""
        manager = HookManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            count = await manager.discover_filesystem_hooks(Path(tmpdir))
            assert count == 0

    @pytest.mark.asyncio
    async def test_discover_hooks_with_files(self):
        """Test discovery loads .py files"""
        manager = HookManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple hook file
            hook_file = Path(tmpdir) / "my_hook.py"
            hook_file.write_text(
                """
from kaizen.core.autonomy.hooks import BaseHook, HookEvent, HookContext, HookResult

class MyCustomHook(BaseHook):
    events = [HookEvent.PRE_TOOL_USE]

    def __init__(self):
        super().__init__(name="my_custom_hook")

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)
"""
            )

            count = await manager.discover_filesystem_hooks(Path(tmpdir))

            # Should have discovered 1 hook
            assert count == 1
            assert len(manager._hooks[HookEvent.PRE_TOOL_USE]) == 1
