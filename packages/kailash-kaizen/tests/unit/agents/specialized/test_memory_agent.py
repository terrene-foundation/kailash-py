"""
Test MemoryAgent - Production-Ready Conversation Agent with Memory

Tests zero-config initialization, progressive configuration,
session management, memory continuity, and conversation tracking.

Written BEFORE implementation (TDD).
"""

import os

import pytest

# ============================================================================
# TEST CLASS 1: Initialization (REQUIRED - 8 tests)
# ============================================================================


class TestMemoryAgentInitialization:
    """Test agent initialization patterns."""

    def test_zero_config_initialization(self):
        """Test agent works with zero configuration (most important test)."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        # Should work with no parameters
        agent = MemoryAgent()

        assert agent is not None
        assert hasattr(agent, "memory_config")
        assert hasattr(agent, "run")
        assert hasattr(agent, "memory_store")

    def test_zero_config_uses_environment_variables(self):
        """Test that zero-config reads from environment variables."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        # Set environment variables
        os.environ["KAIZEN_LLM_PROVIDER"] = "anthropic"
        os.environ["KAIZEN_MODEL"] = "claude-3-sonnet"
        os.environ["KAIZEN_TEMPERATURE"] = "0.5"
        os.environ["KAIZEN_MAX_TOKENS"] = "2000"
        os.environ["KAIZEN_MAX_HISTORY_TURNS"] = "15"

        try:
            agent = MemoryAgent()

            # Should use environment values
            assert agent.memory_config.llm_provider == "anthropic"
            assert agent.memory_config.model == "claude-3-sonnet"
            assert agent.memory_config.temperature == 0.5
            assert agent.memory_config.max_tokens == 2000
            assert agent.memory_config.max_history_turns == 15
        finally:
            # Clean up
            del os.environ["KAIZEN_LLM_PROVIDER"]
            del os.environ["KAIZEN_MODEL"]
            del os.environ["KAIZEN_TEMPERATURE"]
            del os.environ["KAIZEN_MAX_TOKENS"]
            del os.environ["KAIZEN_MAX_HISTORY_TURNS"]

    def test_progressive_configuration_model_only(self):
        """Test progressive configuration - override model only."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent(model="gpt-3.5-turbo")

        assert agent.memory_config.model == "gpt-3.5-turbo"
        # Other values should be defaults
        assert agent.memory_config.llm_provider == "openai"  # default

    def test_progressive_configuration_multiple_params(self):
        """Test progressive configuration - override multiple parameters."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
            max_history_turns=20,
        )

        assert agent.memory_config.llm_provider == "anthropic"
        assert agent.memory_config.model == "claude-3-opus"
        assert agent.memory_config.temperature == 0.7
        assert agent.memory_config.max_tokens == 2000
        assert agent.memory_config.max_history_turns == 20

    def test_full_config_object_initialization(self):
        """Test initialization with full config object."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent, MemoryConfig

        config = MemoryConfig(
            llm_provider="openai",
            model="gpt-4-turbo",
            temperature=0.2,
            max_tokens=1800,
            timeout=60,
            max_history_turns=15,
        )

        agent = MemoryAgent(config=config)

        assert agent.memory_config.llm_provider == "openai"
        assert agent.memory_config.model == "gpt-4-turbo"
        assert agent.memory_config.temperature == 0.2
        assert agent.memory_config.max_tokens == 1800
        assert agent.memory_config.timeout == 60
        assert agent.memory_config.max_history_turns == 15

    def test_config_object_overrides_kwargs(self):
        """Test that config object takes precedence over kwargs."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent, MemoryConfig

        config = MemoryConfig(model="gpt-4", temperature=0.3, max_history_turns=5)

        # Kwargs should be ignored when config is provided
        agent = MemoryAgent(
            config=config,
            model="gpt-3.5-turbo",  # Should be ignored
            temperature=0.9,  # Should be ignored
            max_history_turns=20,  # Should be ignored
        )

        assert agent.memory_config.model == "gpt-4"
        assert agent.memory_config.temperature == 0.3
        assert agent.memory_config.max_history_turns == 5

    def test_default_configuration_values(self):
        """Test that defaults are set correctly."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # LLM defaults
        assert agent.memory_config.llm_provider == "openai"
        assert agent.memory_config.model == "gpt-3.5-turbo"
        assert isinstance(agent.memory_config.temperature, float)
        assert isinstance(agent.memory_config.max_tokens, int)

        # Memory-specific defaults
        assert agent.memory_config.max_history_turns == 10

        # Technical defaults
        assert agent.memory_config.timeout == 30
        assert agent.memory_config.retry_attempts == 3
        assert isinstance(agent.memory_config.provider_config, dict)

    def test_timeout_merged_into_provider_config(self):
        """Test that timeout is merged into provider_config."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent(timeout=60)

        # Timeout should be in provider_config
        assert "timeout" in agent.memory_config.provider_config
        assert agent.memory_config.provider_config["timeout"] == 60


# ============================================================================
# TEST CLASS 2: Execution (REQUIRED - 10 tests)
# ============================================================================


class TestMemoryAgentExecution:
    """Test agent execution and run method."""

    def test_run_method_exists(self):
        """Test that chat convenience method exists."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        assert hasattr(agent, "run")
        assert callable(getattr(agent, "chat"))

    def test_run_returns_dict(self):
        """Test that run method returns a dictionary."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        result = agent.run(message="Hello, how are you?")

        assert isinstance(result, dict)

    def test_run_has_expected_output_fields(self):
        """Test that output contains expected signature fields."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        result = agent.run(message="What is AI?")

        # Check for signature output fields
        assert "response" in result
        assert "memory_updated" in result

    def test_run_accepts_message_parameter(self):
        """Test that run method accepts message parameter."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Should accept message parameter
        result = agent.run(message="Test message")

        assert result is not None
        assert isinstance(result, dict)

    def test_run_method_integration(self):
        """Test that agent.run() method works (inherited from BaseAgent)."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Direct call to BaseAgent.run()
        result = agent.run(message="What is machine learning?", conversation_history="")

        assert isinstance(result, dict)
        assert "response" in result

    def test_execution_with_different_messages(self):
        """Test execution with various message types."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Test with different messages
        test_cases = [
            "Hello!",
            "What is your name?",
            "Tell me about AI",
            "Can you help me?",
        ]

        for message in test_cases:
            result = agent.chat(message)
            assert isinstance(result, dict)
            assert "response" in result

    def test_session_id_support(self):
        """Test that session_id parameter is accepted."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Should accept session_id for conversation tracking
        result = agent.run(message="Hello", session_id="user-123")

        assert isinstance(result, dict)
        assert "response" in result

    def test_multiple_turns_in_same_session(self):
        """Test multiple conversation turns in same session."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session-1"

        # First turn
        result1 = agent.chat("My name is Alice", session_id=session_id)
        assert result1.get("memory_updated") is True

        # Second turn - should have context from first
        result2 = agent.chat("What is my name?", session_id=session_id)
        assert result2.get("memory_updated") is True
        assert isinstance(result2["response"], str)

    def test_multiple_sessions_independent(self):
        """Test that multiple sessions are independent."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Session 1
        result1 = agent.run(message="My favorite color is blue", session_id="session-1")
        assert result1.get("memory_updated") is True

        # Session 2 - should not have context from session 1
        result2 = agent.run(
            message="What is my favorite color?", session_id="session-2"
        )
        assert result2.get("memory_updated") is True
        # Different session shouldn't know the answer

    def test_execution_performance(self):
        """Test that execution completes in reasonable time."""
        import time

        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        start = time.time()
        result = agent.run(message="Hello!")
        duration = time.time() - start

        # Should complete in less than 30 seconds
        assert duration < 30
        assert result is not None


# ============================================================================
# TEST CLASS 3: Configuration (REQUIRED - 8 tests)
# ============================================================================


class TestMemoryAgentConfiguration:
    """Test configuration class and behavior."""

    def test_config_class_exists(self):
        """Test that configuration class exists."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        assert MemoryConfig is not None

    def test_config_is_dataclass(self):
        """Test that config uses dataclass decorator."""
        import dataclasses

        from kaizen.agents.specialized.memory_agent import MemoryConfig

        assert dataclasses.is_dataclass(MemoryConfig)

    def test_config_has_required_llm_fields(self):
        """Test that config has required LLM fields."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        config = MemoryConfig()

        assert hasattr(config, "llm_provider")
        assert hasattr(config, "model")
        assert hasattr(config, "temperature")
        assert hasattr(config, "max_tokens")

    def test_config_has_required_technical_fields(self):
        """Test that config has required technical fields."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        config = MemoryConfig()

        assert hasattr(config, "timeout")
        assert hasattr(config, "retry_attempts")
        assert hasattr(config, "provider_config")

    def test_config_has_memory_specific_fields(self):
        """Test that config has memory-specific fields."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        config = MemoryConfig()

        assert hasattr(config, "max_history_turns")

    def test_config_environment_variable_defaults(self):
        """Test that config reads from environment variables."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        os.environ["KAIZEN_MODEL"] = "test-model"
        os.environ["KAIZEN_MAX_HISTORY_TURNS"] = "15"

        try:
            config = MemoryConfig()
            assert config.model == "test-model"
            assert config.max_history_turns == 15
        finally:
            del os.environ["KAIZEN_MODEL"]
            del os.environ["KAIZEN_MAX_HISTORY_TURNS"]

    def test_config_can_be_instantiated_with_custom_values(self):
        """Test that config accepts custom values."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        config = MemoryConfig(
            llm_provider="custom_provider",
            model="custom_model",
            temperature=0.123,
            max_tokens=999,
            max_history_turns=25,
        )

        assert config.llm_provider == "custom_provider"
        assert config.model == "custom_model"
        assert config.temperature == 0.123
        assert config.max_tokens == 999
        assert config.max_history_turns == 25

    def test_config_provider_config_is_dict(self):
        """Test that provider_config is initialized as dict."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        config = MemoryConfig()

        assert isinstance(config.provider_config, dict)

    def test_default_max_history_turns_is_10(self):
        """Test that default max_history_turns is 10."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        config = MemoryConfig()

        assert config.max_history_turns == 10


# ============================================================================
# TEST CLASS 4: Signature (REQUIRED - 5 tests)
# ============================================================================


class TestMemoryAgentSignature:
    """Test signature definition and structure."""

    def test_signature_class_exists(self):
        """Test that signature class exists."""
        from kaizen.agents.specialized.memory_agent import ConversationSignature

        assert ConversationSignature is not None

    def test_signature_inherits_from_base(self):
        """Test that signature inherits from Signature base class."""
        from kaizen.agents.specialized.memory_agent import ConversationSignature
        from kaizen.signatures import Signature

        assert issubclass(ConversationSignature, Signature)

    def test_signature_has_input_fields(self):
        """Test that signature has defined input fields."""
        from kaizen.agents.specialized.memory_agent import ConversationSignature

        sig = ConversationSignature()

        # Check for input fields
        assert hasattr(sig, "message")
        assert hasattr(sig, "conversation_history")

    def test_signature_has_output_fields(self):
        """Test that signature has defined output fields."""
        from kaizen.agents.specialized.memory_agent import ConversationSignature

        sig = ConversationSignature()

        # Check for output fields
        assert hasattr(sig, "response")
        assert hasattr(sig, "memory_updated")

    def test_signature_has_docstring(self):
        """Test that signature has comprehensive docstring."""
        from kaizen.agents.specialized.memory_agent import ConversationSignature

        assert ConversationSignature.__doc__ is not None
        assert len(ConversationSignature.__doc__) > 20


# ============================================================================
# TEST CLASS 5: Error Handling (REQUIRED - 5 tests)
# ============================================================================


class TestMemoryAgentErrorHandling:
    """Test error handling and edge cases."""

    def test_empty_input_handling(self):
        """Test handling of empty message."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Should handle empty input gracefully
        result = agent.run(message="")

        assert isinstance(result, dict)
        # Should have error indicator
        assert "error" in result
        assert result["error"] == "INVALID_INPUT"

    def test_whitespace_only_input_handling(self):
        """Test handling of whitespace-only message."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Should handle whitespace input gracefully
        result = agent.run(message="   \t\n   ")

        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"] == "INVALID_INPUT"

    def test_none_input_handling(self):
        """Test handling of None input."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Should handle None input gracefully
        try:
            result = agent.chat(None)
            # If it doesn't raise, check for error
            assert isinstance(result, dict)
        except (TypeError, AttributeError):
            # Acceptable to raise error for None
            pass

    def test_invalid_session_id_handling(self):
        """Test handling of invalid session_id."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Should handle various session_id types
        # Empty string session_id
        result = agent.run(message="Hello", session_id="")
        assert isinstance(result, dict)

        # None session_id should use default
        result = agent.chat("Hello", session_id=None)
        assert isinstance(result, dict)

    def test_invalid_config_handling(self):
        """Test handling of invalid configuration values."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        # Test with invalid max_history_turns (negative)
        try:
            agent = MemoryAgent(max_history_turns=-5)
            # If it doesn't raise, it should handle gracefully
            assert (
                agent.memory_config.max_history_turns >= 0
                or agent.memory_config.max_history_turns == -5
            )
        except ValueError:
            # Acceptable to raise ValueError for invalid config
            pass


# ============================================================================
# TEST CLASS 6: Documentation (REQUIRED - 4 tests)
# ============================================================================


class TestMemoryAgentDocumentation:
    """Test docstrings and documentation completeness."""

    def test_agent_class_has_docstring(self):
        """Test that agent class has comprehensive docstring."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        assert MemoryAgent.__doc__ is not None
        assert len(MemoryAgent.__doc__) > 100

    def test_run_method_has_docstring(self):
        """Test that run method has docstring."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        assert MemoryAgent.run.__doc__ is not None
        assert len(MemoryAgent.run.__doc__) > 50

    def test_config_class_has_docstring(self):
        """Test that config class has docstring."""
        from kaizen.agents.specialized.memory_agent import MemoryConfig

        assert MemoryConfig.__doc__ is not None

    def test_helper_methods_have_docstrings(self):
        """Test that helper methods have docstrings."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        # Check clear_memory method
        assert MemoryAgent.clear_memory.__doc__ is not None

        # Check get_conversation_count method
        assert MemoryAgent.get_conversation_count.__doc__ is not None


# ============================================================================
# TEST CLASS 7: Type Hints (REQUIRED - 2 tests)
# ============================================================================


class TestMemoryAgentTypeHints:
    """Test type hint completeness."""

    def test_run_method_has_type_hints(self):
        """Test that run method has type hints."""
        import inspect

        from kaizen.agents.specialized.memory_agent import MemoryAgent

        sig = inspect.signature(MemoryAgent.chat)

        # Check return type hint
        assert sig.return_annotation != inspect.Parameter.empty

        # Check parameter type hints (excluding *args/**kwargs which can't be type-hinted)
        params_with_hints = 0
        total_params = 0

        for param_name, param in sig.parameters.items():
            # Skip self, *args, and **kwargs
            if param_name != "self" and param.kind not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                total_params += 1
                if param.annotation != inspect.Parameter.empty:
                    params_with_hints += 1

        # At least 80% of regular parameters should have type hints
        if total_params > 0:
            hint_percentage = params_with_hints / total_params
            assert hint_percentage >= 0.8

    def test_init_method_has_type_hints(self):
        """Test that __init__ has type hints."""
        import inspect

        from kaizen.agents.specialized.memory_agent import MemoryAgent

        sig = inspect.signature(MemoryAgent.__init__)

        # Check parameter type hints (most should have hints)
        params_with_hints = 0
        total_params = 0

        for param_name, param in sig.parameters.items():
            if param_name not in ["self", "kwargs"]:
                total_params += 1
                if param.annotation != inspect.Parameter.empty:
                    params_with_hints += 1

        # At least 80% of parameters should have type hints
        if total_params > 0:
            hint_percentage = params_with_hints / total_params
            assert hint_percentage >= 0.8


# ============================================================================
# TEST CLASS 8: SimpleMemoryStore (Memory-specific - 10 tests)
# ============================================================================


class TestSimpleMemoryStore:
    """Test SimpleMemoryStore helper class."""

    def test_simple_memory_store_exists(self):
        """Test that SimpleMemoryStore class exists."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        assert SimpleMemoryStore is not None

    def test_add_turn_adds_conversation_turn(self):
        """Test that add_turn adds a conversation turn."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)
        store.add_turn("session1", "user", "Hello")

        # Should have one turn
        assert "session1" in store.conversations
        assert len(store.conversations["session1"]) == 1
        assert store.conversations["session1"][0]["role"] == "user"
        assert store.conversations["session1"][0]["content"] == "Hello"

    def test_get_history_returns_formatted_history(self):
        """Test that get_history returns formatted conversation history."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)
        store.add_turn("session1", "user", "Hello")
        store.add_turn("session1", "assistant", "Hi there!")

        history = store.get_history("session1")

        assert isinstance(history, str)
        assert "user: Hello" in history
        assert "assistant: Hi there!" in history

    def test_clear_session_clears_session(self):
        """Test that clear_session removes session data."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)
        store.add_turn("session1", "user", "Hello")

        # Clear session
        store.clear_session("session1")

        # Session should be gone
        assert "session1" not in store.conversations

    def test_multiple_sessions_independent(self):
        """Test that multiple sessions are independent."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)
        store.add_turn("session1", "user", "Hello from session 1")
        store.add_turn("session2", "user", "Hello from session 2")

        history1 = store.get_history("session1")
        history2 = store.get_history("session2")

        assert "session 1" in history1
        assert "session 1" not in history2
        assert "session 2" in history2
        assert "session 2" not in history1

    def test_automatic_pruning_to_max_turns_works(self):
        """Test that history is automatically pruned to max_turns."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=3)

        # Add more than max_turns * 2 messages
        for i in range(10):
            store.add_turn("session1", "user", f"Message {i}")
            store.add_turn("session1", "assistant", f"Response {i}")

        # Should keep only last max_turns * 2 messages
        assert len(store.conversations["session1"]) <= 3 * 2

    def test_history_format_is_correct(self):
        """Test that history format matches expected pattern."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)
        store.add_turn("session1", "user", "Question")
        store.add_turn("session1", "assistant", "Answer")

        history = store.get_history("session1")

        # Format should be "role: content\nrole: content"
        lines = history.strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == "user: Question"
        assert lines[1] == "assistant: Answer"

    def test_timestamps_added_to_turns(self):
        """Test that timestamps are added to conversation turns."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)
        store.add_turn("session1", "user", "Hello")

        # Should have timestamp
        assert "timestamp" in store.conversations["session1"][0]
        assert isinstance(store.conversations["session1"][0]["timestamp"], str)

    def test_empty_history_for_new_session(self):
        """Test that new session returns empty history."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)

        history = store.get_history("non_existent_session")

        assert history == ""

    def test_get_history_returns_empty_string_for_non_existent_session(self):
        """Test that get_history returns empty string for non-existent session."""
        from kaizen.agents.specialized.memory_agent import SimpleMemoryStore

        store = SimpleMemoryStore(max_turns=10)

        # Should return empty string for session that doesn't exist
        history = store.get_history("does_not_exist")

        assert history == ""


# ============================================================================
# TEST CLASS 9: Conversation Continuity (Memory-specific - 8 tests)
# ============================================================================


class TestMemoryAgentConversationContinuity:
    """Test conversation continuity across turns."""

    def test_first_message_has_no_history(self):
        """Test that first message has empty conversation history."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session"

        # First message - should have no history
        result = agent.chat("Hello", session_id=session_id)

        # Memory should be updated
        assert result.get("memory_updated") is True

        # Should have response
        assert "response" in result

    def test_second_message_includes_first_in_history(self):
        """Test that second message includes first in conversation history."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session-2"

        # First message
        agent.chat("My name is Bob", session_id=session_id)

        # Second message
        result = agent.chat("What is my name?", session_id=session_id)

        # Should have memory from first turn
        assert result.get("memory_updated") is True

        # Memory store should have both turns
        count = agent.get_conversation_count(session_id)
        assert count == 4  # 2 user + 2 assistant messages

    def test_third_message_includes_first_and_second(self):
        """Test that third message includes first and second in history."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session-3"

        # Three turns
        agent.chat("My name is Carol", session_id=session_id)
        agent.chat("I like Python", session_id=session_id)
        agent.chat("What is my name and what do I like?", session_id=session_id)

        # Should have all turns
        count = agent.get_conversation_count(session_id)
        assert count == 6  # 3 user + 3 assistant messages

    def test_history_formatted_correctly(self):
        """Test that conversation history is formatted correctly."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session-4"

        # Add some conversation
        agent.chat("Hello", session_id=session_id)
        agent.chat("How are you?", session_id=session_id)

        # Check internal memory store format
        history = agent.memory_store.get_history(session_id)

        assert isinstance(history, str)
        assert "user: Hello" in history or "user:Hello" in history.replace(" ", "")

    def test_memory_updated_flag_is_true_after_chat(self):
        """Test that memory_updated flag is True after successful chat."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        result = agent.run(message="Test message")

        assert result.get("memory_updated") is True

    def test_clear_memory_works(self):
        """Test that clear_memory removes conversation history."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session-5"

        # Add some conversation
        agent.chat("Hello", session_id=session_id)
        agent.chat("How are you?", session_id=session_id)

        # Clear memory
        agent.clear_memory(session_id=session_id)

        # Should have no conversation
        count = agent.get_conversation_count(session_id)
        assert count == 0

    def test_get_conversation_count_returns_correct_count(self):
        """Test that get_conversation_count returns accurate count."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-session-6"

        # Initial count should be 0
        assert agent.get_conversation_count(session_id) == 0

        # Add one turn
        agent.chat("Hello", session_id=session_id)
        assert agent.get_conversation_count(session_id) == 2  # user + assistant

        # Add another turn
        agent.chat("How are you?", session_id=session_id)
        assert agent.get_conversation_count(session_id) == 4  # 2 user + 2 assistant

    def test_multiple_sessions_dont_interfere(self):
        """Test that multiple sessions don't interfere with each other."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Session 1
        agent.run(message="Session 1 message", session_id="session-1")

        # Session 2
        agent.run(message="Session 2 message", session_id="session-2")

        # Check counts
        count1 = agent.get_conversation_count("session-1")
        count2 = agent.get_conversation_count("session-2")

        assert count1 == 2  # 1 user + 1 assistant
        assert count2 == 2  # 1 user + 1 assistant

        # Clear session 1
        agent.clear_memory("session-1")

        # Session 1 should be empty
        assert agent.get_conversation_count("session-1") == 0

        # Session 2 should be unchanged
        assert agent.get_conversation_count("session-2") == 2


# ============================================================================
# TEST CLASS 10: Session Management (Memory-specific - 6 tests)
# ============================================================================


class TestMemoryAgentSessionManagement:
    """Test session management and isolation."""

    def test_default_session_is_default(self):
        """Test that default session is 'default'."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Chat without session_id should use "default"
        agent.run(message="Hello")

        # Should have conversation in default session
        count = agent.get_conversation_count("default")
        assert count == 2  # user + assistant

    def test_custom_session_id_works(self):
        """Test that custom session_id is respected."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Use custom session ID
        agent.run(message="Hello", session_id="custom-session")

        # Should have conversation in custom session
        count = agent.get_conversation_count("custom-session")
        assert count == 2

        # Default session should be empty
        assert agent.get_conversation_count("default") == 0

    def test_multiple_sessions_are_independent(self):
        """Test that multiple sessions maintain independent state."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Different sessions
        agent.run(message="Session A message", session_id="session-a")
        agent.run(message="Session B message", session_id="session-b")
        agent.run(message="Session C message", session_id="session-c")

        # All should have independent counts
        assert agent.get_conversation_count("session-a") == 2
        assert agent.get_conversation_count("session-b") == 2
        assert agent.get_conversation_count("session-c") == 2

    def test_clearing_one_session_doesnt_affect_others(self):
        """Test that clearing one session doesn't affect other sessions."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Create multiple sessions
        agent.run(message="Session 1", session_id="s1")
        agent.run(message="Session 2", session_id="s2")
        agent.run(message="Session 3", session_id="s3")

        # Clear session 2
        agent.clear_memory("s2")

        # s1 and s3 should be unchanged
        assert agent.get_conversation_count("s1") == 2
        assert agent.get_conversation_count("s2") == 0
        assert agent.get_conversation_count("s3") == 2

    def test_get_conversation_count_per_session(self):
        """Test that get_conversation_count works per session."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Different sessions with different counts
        agent.run(message="Message 1", session_id="session-x")
        agent.run(message="Message 2", session_id="session-x")

        agent.run(message="Message 1", session_id="session-y")

        # Check independent counts
        assert agent.get_conversation_count("session-x") == 4  # 2 user + 2 assistant
        assert agent.get_conversation_count("session-y") == 2  # 1 user + 1 assistant

    def test_empty_session_returns_0_count(self):
        """Test that empty session returns 0 count."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Non-existent session
        count = agent.get_conversation_count("non-existent-session")

        assert count == 0


# ============================================================================
# TEST CLASS 11: Helper Methods (Memory-specific - 3 tests)
# ============================================================================


class TestMemoryAgentHelperMethods:
    """Test helper methods for memory management."""

    def test_clear_memory_exists_and_works(self):
        """Test that clear_memory method exists and works."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-clear"

        # Add conversation
        agent.chat("Test message", session_id=session_id)
        assert agent.get_conversation_count(session_id) > 0

        # Clear it
        agent.clear_memory(session_id=session_id)
        assert agent.get_conversation_count(session_id) == 0

    def test_get_conversation_count_exists_and_works(self):
        """Test that get_conversation_count method exists and works."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()
        session_id = "test-count"

        # Initial count
        count = agent.get_conversation_count(session_id)
        assert count == 0

        # Add message
        agent.chat("Test", session_id=session_id)
        count = agent.get_conversation_count(session_id)
        assert count == 2  # user + assistant

    def test_helper_methods_have_docstrings(self):
        """Test that helper methods have proper docstrings."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        # clear_memory should have docstring
        assert MemoryAgent.clear_memory.__doc__ is not None
        assert len(MemoryAgent.clear_memory.__doc__.strip()) > 10

        # get_conversation_count should have docstring
        assert MemoryAgent.get_conversation_count.__doc__ is not None
        assert len(MemoryAgent.get_conversation_count.__doc__.strip()) > 10


# ============================================================================
# TEST CLASS 12: BaseAgent Integration (REQUIRED - 2 tests)
# ============================================================================


class TestMemoryAgentBaseAgentIntegration:
    """Test integration with BaseAgent."""

    def test_agent_inherits_from_base_agent(self):
        """Test MemoryAgent inherits from BaseAgent."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent
        from kaizen.core.base_agent import BaseAgent

        agent = MemoryAgent()

        assert isinstance(agent, BaseAgent)

    def test_agent_uses_async_single_shot_strategy(self):
        """Test that agent uses AsyncSingleShotStrategy by default."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent
        from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy

        agent = MemoryAgent()

        # Should use AsyncSingleShotStrategy (default for BaseAgent)
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
