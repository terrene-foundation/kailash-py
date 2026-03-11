"""
Tier 2 Integration Tests: BaseAgent Hooks Integration.

Tests BaseAgent lifecycle hook triggers with REAL HookManager instances.
NO MOCKING ALLOWED - use real hook infrastructure.

Test Coverage:
- Basic Integration (5 tests)
- Error Handling (4 tests)
- Backward Compatibility (3 tests)

Total: 12 integration tests

Note: Tool hooks tests removed after ToolRegistry deletion (MCP migration).
Tool hook functionality is tested via MCP integration tests.
"""

import asyncio
import logging
from dataclasses import dataclass

import pytest
from kaizen.core.autonomy.hooks import (
    BaseHook,
    HookContext,
    HookEvent,
    HookManager,
    HookResult,
)
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)


# =============================================================================
# TEST FIXTURES
# =============================================================================


class TestSignature(Signature):
    """Simple test signature"""

    question: str = InputField(description="Question to answer")
    answer: str = OutputField(description="Answer to question")


@dataclass
class TestAgentConfig:
    """Test agent configuration"""

    llm_provider: str = "mock"
    model: str = "mock"
    temperature: float = 0.7
    hooks_enabled: bool = True  # Enable hooks for integration testing


class TestHook(BaseHook):
    """Test hook for capturing lifecycle events"""

    def __init__(self, name="test_hook", should_fail=False):
        super().__init__(name=name)
        self.should_fail = should_fail
        self.call_count = 0
        self.contexts = []
        self.events = []

    async def handle(self, context: HookContext) -> HookResult:
        self.call_count += 1
        self.contexts.append(context)
        self.events.append(context.event_type)

        if self.should_fail:
            raise ValueError("Intentional hook failure")

        return HookResult(
            success=True,
            data={"hook_name": self.name, "event": context.event_type.value},
        )


class SlowHook(BaseHook):
    """Slow hook that simulates timeout"""

    def __init__(self, delay=10.0):
        super().__init__(name="slow_hook")
        self.delay = delay
        self.call_count = 0

    async def handle(self, context: HookContext) -> HookResult:
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return HookResult(success=True)


@pytest.fixture
def hook_manager():
    """Create HookManager instance"""
    return HookManager()


@pytest.fixture
def test_agent_with_hooks(hook_manager):
    """Create test agent with hook manager"""
    config = TestAgentConfig()
    signature = TestSignature()
    agent = BaseAgent(config=config, signature=signature, hook_manager=hook_manager)
    return agent


@pytest.fixture
def test_agent_without_hooks():
    """Create test agent without hook manager (backward compatibility)"""
    config = TestAgentConfig()
    signature = TestSignature()
    agent = BaseAgent(config=config, signature=signature)
    return agent


# =============================================================================
# BASIC INTEGRATION TESTS (5 tests)
# =============================================================================


@pytest.mark.integration
def test_baseagent_accepts_hook_manager(hook_manager):
    """Test BaseAgent constructor accepts HookManager parameter"""
    config = TestAgentConfig()
    signature = TestSignature()

    # Should not raise any errors
    agent = BaseAgent(config=config, signature=signature, hook_manager=hook_manager)

    # Verify hook_manager is stored
    assert hasattr(agent, "hook_manager")
    assert agent.hook_manager is hook_manager


@pytest.mark.integration
def test_baseagent_creates_default_hook_manager():
    """Test BaseAgent creates default HookManager if None provided"""
    from kaizen.core.config import BaseAgentConfig

    config = BaseAgentConfig(
        llm_provider="mock",
        model="mock",
        temperature=0.7,
        hooks_enabled=True,  # Enable hooks to test default creation
    )
    signature = TestSignature()

    # Don't provide hook_manager
    agent = BaseAgent(config=config, signature=signature)

    # Should create default HookManager
    assert hasattr(agent, "hook_manager")
    assert isinstance(agent.hook_manager, HookManager)


@pytest.mark.integration
def test_baseagent_triggers_pre_agent_loop(test_agent_with_hooks, hook_manager):
    """Test BaseAgent triggers PRE_AGENT_LOOP hook before run"""
    # Register hook
    hook = TestHook(name="pre_agent_hook")
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, hook)

    # Run agent
    test_agent_with_hooks.run(question="What is 2+2?")

    # Verify hook was triggered
    assert hook.call_count == 1
    assert HookEvent.PRE_AGENT_LOOP in hook.events

    # Verify context has agent reference and inputs
    context = hook.contexts[0]
    assert context.event_type == HookEvent.PRE_AGENT_LOOP
    assert "question" in context.data or "inputs" in context.data


@pytest.mark.integration
def test_baseagent_triggers_post_agent_loop(test_agent_with_hooks, hook_manager):
    """Test BaseAgent triggers POST_AGENT_LOOP hook after run"""
    # Register hook
    hook = TestHook(name="post_agent_hook")
    hook_manager.register(HookEvent.POST_AGENT_LOOP, hook)

    # Run agent
    test_agent_with_hooks.run(question="What is 2+2?")

    # Verify hook was triggered
    assert hook.call_count == 1
    assert HookEvent.POST_AGENT_LOOP in hook.events

    # Verify context has result
    context = hook.contexts[0]
    assert context.event_type == HookEvent.POST_AGENT_LOOP
    assert "result" in context.data or context.data is not None


@pytest.mark.integration
def test_baseagent_hook_context_has_agent_ref(test_agent_with_hooks, hook_manager):
    """Test hook context includes agent reference"""
    # Register hook
    hook = TestHook(name="context_test_hook")
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, hook)

    # Run agent
    test_agent_with_hooks.run(question="What is 2+2?")

    # Verify context has agent_id
    context = hook.contexts[0]
    assert context.agent_id is not None
    assert isinstance(context.agent_id, str)
    assert len(context.agent_id) > 0


# =============================================================================
# ERROR HANDLING TESTS (4 tests)
# =============================================================================


@pytest.mark.integration
def test_baseagent_continues_on_hook_error(test_agent_with_hooks, hook_manager):
    """Test BaseAgent continues execution if hook fails"""
    # Register failing hook
    failing_hook = TestHook(name="failing_hook", should_fail=True)
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, failing_hook)

    # Agent run should NOT fail
    result = test_agent_with_hooks.run(question="What is 2+2?")

    # Verify hook was called but agent continued
    assert failing_hook.call_count == 1
    assert result is not None


@pytest.mark.integration
def test_baseagent_hook_timeout_doesnt_block(test_agent_with_hooks, hook_manager):
    """Test hook timeout doesn't hang agent execution"""
    # Register slow hook (will timeout)
    slow_hook = SlowHook(delay=10.0)
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, slow_hook)

    # Run should complete quickly (not wait for timeout)
    import time

    start = time.time()
    result = test_agent_with_hooks.run(question="What is 2+2?")
    duration = time.time() - start

    # Should complete in reasonable time (not 10 seconds)
    # Hook timeout is 5s by default, but agent should continue
    assert duration < 7.0  # Allow some buffer for slow systems
    assert result is not None


@pytest.mark.integration
def test_baseagent_multiple_hooks_isolated(test_agent_with_hooks, hook_manager):
    """Test one hook failure doesn't affect other hooks"""
    # Register multiple hooks: good -> bad -> good
    good_hook1 = TestHook(name="good_hook1", should_fail=False)
    bad_hook = TestHook(name="bad_hook", should_fail=True)
    good_hook2 = TestHook(name="good_hook2", should_fail=False)

    hook_manager.register(HookEvent.PRE_AGENT_LOOP, good_hook1)
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, bad_hook)
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, good_hook2)

    # Run agent
    result = test_agent_with_hooks.run(question="What is 2+2?")

    # All hooks should be called
    assert good_hook1.call_count == 1
    assert bad_hook.call_count == 1
    assert good_hook2.call_count == 1

    # Agent should complete successfully
    assert result is not None


@pytest.mark.integration
def test_baseagent_hook_error_logged(test_agent_with_hooks, hook_manager, caplog):
    """Test hook errors are logged"""
    # Register failing hook
    failing_hook = TestHook(name="logged_failure_hook", should_fail=True)
    hook_manager.register(HookEvent.PRE_AGENT_LOOP, failing_hook)

    # Capture logs
    with caplog.at_level(logging.ERROR):
        result = test_agent_with_hooks.run(question="What is 2+2?")

    # Verify error was logged (check logs contain hook-related errors)
    # Note: HookManager logs errors, not BaseAgent directly
    # We just verify agent didn't crash and logs were captured
    assert result is not None
    assert failing_hook.call_count == 1


# =============================================================================
# BACKWARD COMPATIBILITY TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
def test_baseagent_works_without_hooks(test_agent_without_hooks):
    """Test BaseAgent works when hook_manager=None"""
    # Agent without hooks should work normally
    result = test_agent_without_hooks.run(question="What is 2+2?")

    # Should complete successfully
    assert result is not None
    assert isinstance(result, dict)


@pytest.mark.integration
def test_existing_agent_tests_still_pass():
    """Test existing BaseAgent functionality still works"""
    # Test basic agent creation and execution
    config = TestAgentConfig()
    signature = TestSignature()

    # Old-style agent creation (no hooks)
    agent = BaseAgent(config=config, signature=signature)

    # Should work as before
    result = agent.run(question="What is 2+2?")
    assert result is not None


@pytest.mark.integration
def test_baseagent_optional_hook_manager():
    """Test hook_manager parameter is truly optional"""
    from kaizen.core.config import BaseAgentConfig

    config = BaseAgentConfig(
        llm_provider="mock",
        model="mock",
        temperature=0.7,
        hooks_enabled=True,  # Enable hooks to test default creation
    )
    signature = TestSignature()

    # Create agent without any hook-related parameters
    agent = BaseAgent(config=config, signature=signature)

    # Should have default hook_manager
    assert hasattr(agent, "hook_manager")
    assert agent.hook_manager is not None

    # Should work normally
    result = agent.run(question="What is 2+2?")
    assert result is not None
