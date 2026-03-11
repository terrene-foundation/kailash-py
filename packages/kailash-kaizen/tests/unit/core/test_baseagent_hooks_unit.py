"""
Tier 1 Unit Tests for BaseAgent Hooks Integration

Tests BaseAgent convenience methods for hooks integration in isolation.
Uses mocked HookManager for fast, isolated unit tests.

Coverage Target: 95%+ for BaseAgent hook methods
Test Strategy: TDD - Tests written BEFORE implementation
Infrastructure: Mocked HookManager (Tier 1 allows mocking)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookPriority, HookResult
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature

# ============================================
# Test Fixtures
# ============================================


class SimpleSignature(Signature):
    """Simple signature for testing"""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result of task")


@pytest.fixture
def mock_hook_manager():
    """Create mocked HookManager for unit tests"""
    manager = MagicMock()
    manager.register_hook = MagicMock()
    manager.trigger_hooks = AsyncMock(return_value=[])
    manager.get_stats = MagicMock(return_value={})
    return manager


# ============================================
# Test: Hook Registration
# ============================================


def test_register_hook():
    """
    Test hook registration via BaseAgent API.

    Expected to FAIL until implementation:
    - AttributeError: 'BaseAgent' object has no attribute 'register_hook'
    """
    # Arrange
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=True
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Mock hook function
    async def custom_hook(context: HookContext) -> HookResult:
        return HookResult(success=True)

    # Act - Register hook via BaseAgent convenience method
    agent.register_hook(HookEvent.PRE_TOOL_USE, custom_hook, HookPriority.HIGH)

    # Assert - Verify registration
    # (Should delegate to internal HookManager)
    assert hasattr(agent, "_hook_manager"), "BaseAgent should have _hook_manager"
    assert (
        len(agent._hook_manager._hooks[HookEvent.PRE_TOOL_USE]) > 0
    ), "Hook should be registered"


def test_register_hook_with_default_priority():
    """
    Test hook registration with default priority (NORMAL).

    Expected to FAIL until implementation:
    - AttributeError: 'BaseAgent' object has no attribute 'register_hook'
    """
    # Arrange
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=True
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Mock hook function
    async def custom_hook(context: HookContext) -> HookResult:
        return HookResult(success=True)

    # Act - Register hook without specifying priority
    agent.register_hook(HookEvent.PRE_AGENT_LOOP, custom_hook)

    # Assert - Should use HookPriority.NORMAL by default
    assert hasattr(agent, "_hook_manager"), "BaseAgent should have _hook_manager"


# ============================================
# Test: Hook Triggering
# ============================================


@pytest.mark.asyncio
async def test_trigger_hook():
    """
    Test hook triggering via BaseAgent API.

    Expected to FAIL until implementation:
    - AttributeError: 'BaseAgent' object has no attribute 'trigger_hook'
    """
    # Arrange
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=True
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Act - Trigger hook via BaseAgent convenience method
    results = await agent.trigger_hook(
        event_type=HookEvent.PRE_TOOL_USE,
        data={"tool_name": "test_tool", "args": {}},
    )

    # Assert - Verify trigger returns results
    assert isinstance(results, list), "trigger_hook should return list of HookResults"


# ============================================
# Test: Hook Stats
# ============================================


def test_get_hook_stats():
    """
    Test hook stats retrieval via BaseAgent API.

    Expected to FAIL until implementation:
    - AttributeError: 'BaseAgent' object has no attribute 'get_hook_stats'
    """
    # Arrange
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=True
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Act - Get hook stats via BaseAgent convenience method
    stats = agent.get_hook_stats()

    # Assert - Verify stats structure
    assert isinstance(stats, dict), "get_hook_stats should return dict"
    # Stats should contain hook execution counts, errors, etc.


# ============================================
# Test: Hooks Disabled by Default
# ============================================


def test_hooks_disabled_by_default():
    """
    Test that hooks are disabled by default (opt-in).

    Expected to FAIL until implementation:
    - AssertionError: hooks_enabled should default to False
    """
    # Arrange - Create config WITHOUT hooks_enabled
    config = BaseAgentConfig(llm_provider="ollama", model="llama3.1:8b-instruct-q8_0")

    # Act
    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Assert - Hooks should be disabled by default
    assert config.hooks_enabled is False, "Hooks should be disabled by default"
    assert (
        not hasattr(agent, "_hook_manager") or agent._hook_manager is None
    ), "HookManager should not be initialized when hooks disabled"


# ============================================
# Test: Hooks Config Validation
# ============================================


def test_hooks_config_validation():
    """
    Test hooks configuration validation.

    Expected to FAIL until implementation:
    - AttributeError: 'BaseAgentConfig' object has no attribute 'hooks_enabled'
    """
    # Arrange - Create config with hooks enabled
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        hooks_enabled=True,
        hook_timeout=5.0,
        builtin_hooks=["logging", "metrics"],
    )

    # Act
    BaseAgent(config=config, signature=SimpleSignature())

    # Assert - Config should be validated and stored
    assert config.hooks_enabled is True, "hooks_enabled should be True"
    assert config.hook_timeout == 5.0, "hook_timeout should be set"
    assert "logging" in config.builtin_hooks, "builtin_hooks should include 'logging'"
    assert "metrics" in config.builtin_hooks, "builtin_hooks should include 'metrics'"


# ============================================
# Test: Hook Registration with Disabled Hooks
# ============================================


def test_register_hook_when_disabled():
    """
    Test that registering hooks when disabled raises clear error.

    Expected to FAIL until implementation:
    - Should raise RuntimeError when hooks_enabled=False
    """
    # Arrange - Create config WITHOUT hooks enabled
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=False
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Mock hook function
    async def custom_hook(context: HookContext) -> HookResult:
        return HookResult(success=True)

    # Act & Assert - Should raise error when hooks disabled
    with pytest.raises(RuntimeError, match="Hooks are not enabled"):
        agent.register_hook(HookEvent.PRE_TOOL_USE, custom_hook)


# ============================================
# Test: Multiple Hook Registration
# ============================================


def test_register_multiple_hooks():
    """
    Test registering multiple hooks for same event.

    Expected to FAIL until implementation:
    - AttributeError: 'BaseAgent' object has no attribute 'register_hook'
    """
    # Arrange
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=True
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Mock hook functions
    async def hook1(context: HookContext) -> HookResult:
        return HookResult(success=True, data={"hook": "1"})

    async def hook2(context: HookContext) -> HookResult:
        return HookResult(success=True, data={"hook": "2"})

    # Act - Register multiple hooks for same event
    agent.register_hook(HookEvent.PRE_TOOL_USE, hook1, HookPriority.HIGH)
    agent.register_hook(HookEvent.PRE_TOOL_USE, hook2, HookPriority.NORMAL)

    # Assert - Both hooks should be registered
    assert hasattr(agent, "_hook_manager"), "BaseAgent should have _hook_manager"
    assert (
        len(agent._hook_manager._hooks[HookEvent.PRE_TOOL_USE]) >= 2
    ), "Multiple hooks should be registered"


# ============================================
# Test: Hook Error Isolation
# ============================================


@pytest.mark.asyncio
async def test_hook_error_isolation():
    """
    Test that hook errors don't crash agent execution.

    Expected to FAIL until implementation:
    - Hook errors should be isolated and logged
    """
    # Arrange
    config = BaseAgentConfig(
        llm_provider="ollama", model="llama3.1:8b-instruct-q8_0", hooks_enabled=True
    )

    agent = BaseAgent(config=config, signature=SimpleSignature())

    # Mock hook that raises error
    async def failing_hook(context: HookContext) -> HookResult:
        raise RuntimeError("Hook error")

    # Register failing hook
    agent.register_hook(HookEvent.PRE_TOOL_USE, failing_hook)

    # Act - Trigger hook (should not crash)
    results = await agent.trigger_hook(
        event_type=HookEvent.PRE_TOOL_USE, data={"tool_name": "test"}
    )

    # Assert - Should return error result, not crash
    assert len(results) > 0, "Should return results even if hook fails"
    assert not results[0].success, "Failing hook should return success=False"
    assert results[0].error is not None, "Failing hook should include error message"
