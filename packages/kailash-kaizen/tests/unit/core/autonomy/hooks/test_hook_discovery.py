"""
Unit tests for filesystem hook discovery.

Tests HookManager.discover_filesystem_hooks() functionality including:
- Hook discovery from .kaizen/hooks/*.py files
- Protocol validation (HookHandler interface)
- Error isolation (bad hooks don't break others)
- Auto-registration of discovered hooks
"""

from pathlib import Path

import pytest
from kaizen.core.autonomy.hooks import HookEvent, HookManager


class TestHookDiscovery:
    """Test filesystem hook discovery functionality"""

    @pytest.mark.asyncio
    async def test_discover_hooks_from_filesystem(self, tmp_path):
        """Test discovering .py files in .kaizen/hooks/ directory"""
        # Setup: Create hooks directory
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create a valid hook file
        hook_file = hooks_dir / "custom_hook.py"
        hook_file.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class CustomHook(BaseHook):
    def __init__(self):
        super().__init__(name="CustomHook")
        self.events = [HookEvent.PRE_TOOL_USE]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"custom": "data"})
"""
        )

        # Execute: Discover hooks
        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        # Assert: Hook was discovered and registered
        assert count == 1, "Should discover 1 hook"

        # Verify hook is registered for PRE_TOOL_USE event
        hooks = manager._hooks.get(HookEvent.PRE_TOOL_USE, [])
        assert len(hooks) == 1, "Hook should be registered for PRE_TOOL_USE"

        # Verify we can trigger the hook
        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE, agent_id="test", data={}
        )
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].data == {"custom": "data"}

    @pytest.mark.asyncio
    async def test_discover_validates_hook_protocol(self, tmp_path):
        """Test only loads classes implementing HookHandler protocol"""
        # Setup: Create hooks directory with both valid and invalid classes
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        hook_file = hooks_dir / "mixed_hooks.py"
        hook_file.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

# Valid hook
class ValidHook(BaseHook):
    def __init__(self):
        super().__init__(name="ValidHook")
        self.events = [HookEvent.PRE_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)

# Invalid: Not a BaseHook subclass
class NotAHook:
    def __init__(self):
        self.events = [HookEvent.PRE_TOOL_USE]

    async def handle(self, context):
        return {"success": True}

# Invalid: Regular function
def some_function():
    pass
"""
        )

        # Execute: Discover hooks
        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        # Assert: Only valid hook discovered
        assert count == 1, "Should discover only 1 valid hook (ValidHook)"

        # Verify ValidHook is registered
        hooks = manager._hooks.get(HookEvent.PRE_AGENT_LOOP, [])
        assert len(hooks) == 1

        # Verify NotAHook is NOT registered
        hooks = manager._hooks.get(HookEvent.PRE_TOOL_USE, [])
        assert len(hooks) == 0, "NotAHook should be skipped"

    @pytest.mark.asyncio
    async def test_discover_handles_invalid_hooks(self, tmp_path):
        """Test gracefully handles malformed hooks"""
        # Setup: Create hooks directory with syntax errors and invalid hooks
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Hook with syntax error
        bad_syntax = hooks_dir / "bad_syntax.py"
        bad_syntax.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook

class BadSyntax(BaseHook
    # Missing closing parenthesis and colon
"""
        )

        # Hook missing 'events' attribute
        missing_events = hooks_dir / "missing_events.py"
        missing_events.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult

class MissingEventsHook(BaseHook):
    def __init__(self):
        super().__init__(name="MissingEventsHook")
        # No 'events' attribute

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)
"""
        )

        # Hook that raises exception during instantiation
        instantiation_error = hooks_dir / "instantiation_error.py"
        instantiation_error.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class InstantiationErrorHook(BaseHook):
    def __init__(self):
        super().__init__(name="InstantiationErrorHook")
        self.events = [HookEvent.PRE_TOOL_USE]
        raise ValueError("Cannot instantiate this hook!")

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)
"""
        )

        # Execute: Discover hooks (should not raise exception)
        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        # Assert: Discovery completes without crashing
        assert count == 0, "No valid hooks should be discovered"
        assert len(manager._hooks) == 0, "No hooks should be registered"

    @pytest.mark.asyncio
    async def test_discover_isolates_errors(self, tmp_path):
        """Test one bad hook doesn't break others"""
        # Setup: Create hooks directory with both good and bad hooks
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Good hook 1
        good1 = hooks_dir / "good1.py"
        good1.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class GoodHook1(BaseHook):
    def __init__(self):
        super().__init__(name="GoodHook1")
        self.events = [HookEvent.PRE_TOOL_USE]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"hook": "good1"})
"""
        )

        # Bad hook (instantiation error)
        bad = hooks_dir / "bad.py"
        bad.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class BadHook(BaseHook):
    def __init__(self):
        super().__init__(name="BadHook")
        self.events = [HookEvent.POST_TOOL_USE]
        raise RuntimeError("I'm broken!")

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)
"""
        )

        # Good hook 2
        good2 = hooks_dir / "good2.py"
        good2.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class GoodHook2(BaseHook):
    def __init__(self):
        super().__init__(name="GoodHook2")
        self.events = [HookEvent.PRE_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"hook": "good2"})
"""
        )

        # Execute: Discover hooks
        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        # Assert: Good hooks discovered despite bad hook
        assert count == 2, "Should discover 2 good hooks (error isolation)"

        # Verify GoodHook1 is registered
        hooks = manager._hooks.get(HookEvent.PRE_TOOL_USE, [])
        assert len(hooks) == 1
        results = await manager.trigger(HookEvent.PRE_TOOL_USE, "test", {})
        assert results[0].data == {"hook": "good1"}

        # Verify GoodHook2 is registered
        hooks = manager._hooks.get(HookEvent.PRE_AGENT_LOOP, [])
        assert len(hooks) == 1
        results = await manager.trigger(HookEvent.PRE_AGENT_LOOP, "test", {})
        assert results[0].data == {"hook": "good2"}

        # Verify BadHook is NOT registered
        hooks = manager._hooks.get(HookEvent.POST_TOOL_USE, [])
        assert len(hooks) == 0, "BadHook should be skipped"

    @pytest.mark.asyncio
    async def test_discover_returns_hook_instances(self, tmp_path):
        """Test returns instantiated hook objects (not classes)"""
        # Setup: Create hooks directory with multiple hooks
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        hook_file = hooks_dir / "multi_event_hook.py"
        hook_file.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class MultiEventHook(BaseHook):
    def __init__(self):
        super().__init__(name="MultiEventHook")
        # Register for multiple events
        self.events = [
            HookEvent.PRE_TOOL_USE,
            HookEvent.POST_TOOL_USE,
            HookEvent.PRE_AGENT_LOOP
        ]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"event": context.event_type.value})
"""
        )

        # Execute: Discover hooks
        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        # Assert: Hook registered for all 3 events
        assert count == 3, "Should register hook for 3 events"

        # Verify hook works for all events
        for event in [
            HookEvent.PRE_TOOL_USE,
            HookEvent.POST_TOOL_USE,
            HookEvent.PRE_AGENT_LOOP,
        ]:
            hooks = manager._hooks.get(event, [])
            assert len(hooks) == 1, f"Hook should be registered for {event.value}"

            results = await manager.trigger(event, "test", {})
            assert len(results) == 1
            assert results[0].success is True
            assert results[0].data == {"event": event.value}

    @pytest.mark.asyncio
    async def test_discover_nonexistent_directory(self):
        """Test raises OSError if hooks directory doesn't exist"""
        manager = HookManager()

        with pytest.raises(OSError, match="Hooks directory not found"):
            await manager.discover_filesystem_hooks(Path("/nonexistent/path"))

    @pytest.mark.asyncio
    async def test_discover_file_instead_of_directory(self, tmp_path):
        """Test raises OSError if hooks_dir is a file, not directory"""
        # Create a file instead of directory
        hooks_file = tmp_path / "hooks.txt"
        hooks_file.write_text("I'm a file, not a directory")

        manager = HookManager()

        with pytest.raises(OSError, match="Not a directory"):
            await manager.discover_filesystem_hooks(hooks_file)

    @pytest.mark.asyncio
    async def test_discover_empty_directory(self, tmp_path):
        """Test handles empty directory gracefully"""
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        assert count == 0, "Should discover 0 hooks from empty directory"
        assert len(manager._hooks) == 0

    @pytest.mark.asyncio
    async def test_discover_ignores_init_py(self, tmp_path):
        """Test ignores __init__.py files"""
        hooks_dir = tmp_path / ".kaizen" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create __init__.py (should be ignored)
        init_file = hooks_dir / "__init__.py"
        init_file.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class InitHook(BaseHook):
    def __init__(self):
        super().__init__(name="InitHook")
        self.events = [HookEvent.PRE_TOOL_USE]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)
"""
        )

        # Create regular hook file (should be discovered)
        hook_file = hooks_dir / "real_hook.py"
        hook_file.write_text(
            """
from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class RealHook(BaseHook):
    def __init__(self):
        super().__init__(name="RealHook")
        self.events = [HookEvent.PRE_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True)
"""
        )

        manager = HookManager()
        count = await manager.discover_filesystem_hooks(hooks_dir)

        assert count == 1, "Should discover only RealHook, not InitHook"

        # Verify __init__.py was ignored
        hooks = manager._hooks.get(HookEvent.PRE_TOOL_USE, [])
        assert len(hooks) == 0

        # Verify real hook was discovered
        hooks = manager._hooks.get(HookEvent.PRE_AGENT_LOOP, [])
        assert len(hooks) == 1
