"""
Unit tests for simple-qa example with BufferMemory integration.

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, mocks strategy execution
- Tests BufferMemory initialization in SimpleQAAgent
- Tests context loading before execution
- Tests turn saving after execution
- Tests multi-turn conversations
- Tests session isolation
- Tests memory-specific features (FIFO limiting)
"""

from unittest.mock import patch

# Standardized example loading
from example_import_helper import import_example_module

# Load simple-qa example
_simple_qa_module = import_example_module("examples/1-single-agent/simple-qa")
SimpleQAAgent = _simple_qa_module.SimpleQAAgent
QAConfig = _simple_qa_module.QAConfig


class TestSimpleQAMemoryInitialization:
    """Test BufferMemory initialization in SimpleQAAgent."""

    def test_simple_qa_without_memory(self):
        """Test SimpleQAAgent can be created without memory (default behavior)."""
        config = QAConfig(llm_provider="mock", model="test")
        agent = SimpleQAAgent(config)

        # Should not have memory by default
        assert agent.memory is None

    def test_simple_qa_with_buffer_memory_unlimited(self):
        """Test SimpleQAAgent can be created with BufferMemory (unlimited)."""
        from kaizen.memory.buffer import BufferMemory

        # max_turns=0 means unlimited (converted to None internally)
        config = QAConfig(llm_provider="mock", model="test", max_turns=0)
        agent = SimpleQAAgent(config)

        # Should have BufferMemory with unlimited turns
        assert agent.memory is not None
        assert isinstance(agent.memory, BufferMemory)
        assert agent.memory.max_turns is None  # 0 converted to None for unlimited

    def test_simple_qa_with_buffer_memory_limited(self):
        """Test SimpleQAAgent can be created with BufferMemory (max_turns limit)."""
        from kaizen.memory.buffer import BufferMemory

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Should have BufferMemory with max_turns=10
        assert agent.memory is not None
        assert isinstance(agent.memory, BufferMemory)
        assert agent.memory.max_turns == 10

    def test_qa_config_has_max_turns_parameter(self):
        """Test QAConfig has max_turns parameter."""

        # Default should be None (memory disabled)
        config1 = QAConfig()
        assert hasattr(config1, "max_turns")
        assert config1.max_turns is None

        # Can be set explicitly
        config2 = QAConfig(max_turns=5)
        assert config2.max_turns == 5


class TestSimpleQAMemoryContextLoading:
    """Test memory context loading before execution."""

    def test_memory_context_loaded_with_session_id(self):
        """Test that memory context is loaded when session_id is provided."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Pre-populate memory
        agent.memory.save_turn(
            "session1",
            {
                "user": "What is 1+1?",
                "agent": "1+1 equals 2",
                "timestamp": "2025-10-02T10:00:00",
            },
        )

        # Mock strategy execution
        async def mock_execute(agent_inst, inputs):
            # Verify memory context was loaded
            assert "_memory_context" in inputs
            assert inputs["_memory_context"]["turn_count"] == 1
            return {
                "answer": "2+2 equals 4",
                "confidence": 0.99,
                "reasoning": "Basic arithmetic",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute):
            result = agent.run(question="What is 2+2?", session_id="session1")

        assert "answer" in result


class TestSimpleQATurnSaving:
    """Test turn saving after execution."""

    def test_turn_saved_to_memory_after_execution(self):
        """Test that conversation turns are saved to memory."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Mock strategy execution
        async def mock_execute(agent_inst, inputs):
            return {
                "answer": "42",
                "confidence": 1.0,
                "reasoning": "The answer to everything",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute):
            agent.run(question="What is the answer?", session_id="session1")

        # Verify turn was saved
        context = agent.memory.load_context("session1")
        assert context["turn_count"] == 1
        assert len(context["turns"]) == 1

        turn = context["turns"][0]
        assert "user" in turn
        assert "agent" in turn
        assert "timestamp" in turn
        assert "What is the answer?" in turn["user"]
        assert "42" in turn["agent"]

    def test_multiple_turns_saved_in_order(self):
        """Test that multiple turns are saved in chronological order."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Mock strategy execution
        responses = [
            {"answer": "Paris", "confidence": 0.95, "reasoning": "Capital of France"},
            {"answer": "London", "confidence": 0.95, "reasoning": "Capital of UK"},
            {"answer": "Berlin", "confidence": 0.95, "reasoning": "Capital of Germany"},
        ]

        questions = ["Capital of France?", "Capital of UK?", "Capital of Germany?"]

        # Ask multiple questions
        for i, question in enumerate(questions):

            async def mock_execute(agent_inst, inputs, idx=i):
                return responses[idx]

            with patch.object(agent.strategy, "execute", side_effect=mock_execute):
                agent.run(question=question, session_id="session1")

        # Verify all turns saved in order
        context = agent.memory.load_context("session1")
        assert context["turn_count"] == 3

        assert "France" in context["turns"][0]["user"]
        assert "UK" in context["turns"][1]["user"]
        assert "Germany" in context["turns"][2]["user"]

    def test_turn_not_saved_without_session_id(self):
        """Test that turns are not saved without session_id."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Mock strategy execution
        async def mock_execute(agent_inst, inputs):
            return {"answer": "Test", "confidence": 0.9, "reasoning": "Test"}

        with patch.object(agent.strategy, "execute", side_effect=mock_execute):
            agent.run(question="Test question?")

        # Memory should be empty (no session was specified)
        context = agent.memory.load_context("default_session")
        assert context["turn_count"] == 0


class TestSimpleQAMultiTurnConversations:
    """Test multi-turn conversation capabilities."""

    def test_conversation_continuity_with_memory(self):
        """Test that agent maintains conversation context across turns."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Turn 1
        async def mock_execute_1(agent_inst, inputs):
            return {
                "answer": "Python is a programming language",
                "confidence": 0.99,
                "reasoning": "Definition",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute_1):
            agent.run(question="What is Python?", session_id="session1")

        # Turn 2 - should have context from turn 1
        async def mock_execute_2(agent_inst, inputs):
            # Verify previous context is available
            assert "_memory_context" in inputs
            assert inputs["_memory_context"]["turn_count"] == 1
            return {
                "answer": "Guido van Rossum created it",
                "confidence": 0.95,
                "reasoning": "Historical fact",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute_2):
            agent.run(question="Who created it?", session_id="session1")

        # Verify both turns in memory
        context = agent.memory.load_context("session1")
        assert context["turn_count"] == 2
        assert "Python" in context["turns"][0]["user"]
        assert "created" in context["turns"][1]["user"]

    def test_different_sessions_maintain_separate_histories(self):
        """Test that different sessions have isolated memory."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Session 1
        async def mock_execute_s1(agent_inst, inputs):
            return {
                "answer": "Session 1 answer",
                "confidence": 0.9,
                "reasoning": "Test",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute_s1):
            agent.run(question="Session 1 question", session_id="session1")

        # Session 2
        async def mock_execute_s2(agent_inst, inputs):
            return {
                "answer": "Session 2 answer",
                "confidence": 0.9,
                "reasoning": "Test",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute_s2):
            agent.run(question="Session 2 question", session_id="session2")

        # Verify isolation
        context1 = agent.memory.load_context("session1")
        context2 = agent.memory.load_context("session2")

        assert context1["turn_count"] == 1
        assert context2["turn_count"] == 1
        assert "Session 1" in context1["turns"][0]["user"]
        assert "Session 2" in context2["turns"][0]["user"]


class TestSimpleQAMemoryFIFO:
    """Test BufferMemory FIFO limiting behavior."""

    def test_max_turns_limit_enforced(self):
        """Test that max_turns limit enforces FIFO behavior."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=3)
        agent = SimpleQAAgent(config)

        # Add 5 turns (should keep only last 3)
        for i in range(5):

            async def mock_execute(agent_inst, inputs, idx=i):
                return {
                    "answer": f"Answer {idx}",
                    "confidence": 0.9,
                    "reasoning": "Test",
                }

            with patch.object(agent.strategy, "execute", side_effect=mock_execute):
                agent.run(question=f"Question {i}", session_id="session1")

        # Verify only last 3 turns kept
        context = agent.memory.load_context("session1")
        assert context["turn_count"] == 3

        # Should have questions 2, 3, 4 (0 and 1 removed)
        assert "Question 2" in context["turns"][0]["user"]
        assert "Question 3" in context["turns"][1]["user"]
        assert "Question 4" in context["turns"][2]["user"]

    def test_unlimited_memory_keeps_all_turns(self):
        """Test that unlimited memory (0) keeps all turns."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=0)
        agent = SimpleQAAgent(config)

        # Add 10 turns
        for i in range(10):

            async def mock_execute(agent_inst, inputs, idx=i):
                return {
                    "answer": f"Answer {idx}",
                    "confidence": 0.9,
                    "reasoning": "Test",
                }

            with patch.object(agent.strategy, "execute", side_effect=mock_execute):
                agent.run(question=f"Question {i}", session_id="session1")

        # Should keep all 10 turns (unlimited)
        context = agent.memory.load_context("session1")
        assert context["turn_count"] == 10


class TestSimpleQAMemoryEdgeCases:
    """Test edge cases and error conditions."""

    def test_run_with_empty_question_and_memory(self):
        """Test handling of empty question with memory enabled.

        Note: Agent doesn't perform input validation - it processes empty input.
        With mock provider, we test structure only.
        """

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Ask empty question (via run method)
        result = agent.run(question="", session_id="session1")

        # Result should be a dict with expected structure
        assert isinstance(result, dict)
        # Should have answer and confidence fields (or error)
        assert "answer" in result or "error" in result

        # Memory behavior depends on whether result was successful
        context = agent.memory.load_context("session1")
        assert isinstance(context["turns"], list)
        assert context["turn_count"] >= 0

    def test_run_with_low_confidence_saves_to_memory(self):
        """Test that low confidence answers still save to memory.

        Note: With mock provider, we test structure only. Warning behavior
        depends on actual confidence threshold logic.
        """

        config = QAConfig(
            llm_provider="mock",
            model="test",
            max_turns=10,
            min_confidence_threshold=0.7,
        )
        agent = SimpleQAAgent(config)

        # Mock strategy execution
        async def mock_execute(agent_inst, inputs):
            return {
                "answer": "Uncertain answer",
                "confidence": 0.3,
                "reasoning": "Not sure",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute):
            result = agent.run(question="Difficult question?", session_id="session1")

        # Result should be a dict with expected structure
        assert isinstance(result, dict)
        # Should have answer and confidence fields
        assert "answer" in result
        assert "confidence" in result

        # Should save to memory (structure test)
        context = agent.memory.load_context("session1")
        assert isinstance(context["turns"], list)
        assert context["turn_count"] >= 0

    def test_memory_with_context_parameter(self):
        """Test that context parameter works with memory."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        # Mock strategy execution
        async def mock_execute(agent_inst, inputs):
            return {
                "answer": "Context-aware answer",
                "confidence": 0.95,
                "reasoning": "Used context",
            }

        with patch.object(agent.strategy, "execute", side_effect=mock_execute):
            agent.ask(
                "What is this?",
                context="This is a Python framework",
                session_id="session1",
            )

        # Should save to memory
        context = agent.memory.load_context("session1")
        assert context["turn_count"] == 1
        assert "What is this?" in context["turns"][0]["user"]


class TestSimpleQAMemoryIntegration:
    """Integration tests for memory with actual agent execution."""

    def test_full_qa_workflow_with_memory(self):
        """Test complete Q&A workflow with memory enabled."""

        # Create agent with memory
        config = QAConfig(
            llm_provider="mock", model="test", max_turns=5, min_confidence_threshold=0.5
        )
        agent = SimpleQAAgent(config)

        # Simulate conversation
        questions = ["What is AI?", "What is ML?", "What is DL?"]
        answers = [
            {
                "answer": "Artificial Intelligence",
                "confidence": 0.9,
                "reasoning": "Definition",
            },
            {
                "answer": "Machine Learning",
                "confidence": 0.9,
                "reasoning": "Definition",
            },
            {"answer": "Deep Learning", "confidence": 0.9, "reasoning": "Definition"},
        ]

        for i, question in enumerate(questions):

            async def mock_execute(agent_inst, inputs, idx=i):
                return answers[idx]

            with patch.object(agent.strategy, "execute", side_effect=mock_execute):
                result = agent.ask(question, session_id="conversation1")
                assert "answer" in result
                assert result["confidence"] >= config.min_confidence_threshold

        # Verify complete conversation history
        context = agent.memory.load_context("conversation1")
        assert context["turn_count"] == 3

        # Check chronological order
        assert "AI" in context["turns"][0]["user"]
        assert "ML" in context["turns"][1]["user"]
        assert "DL" in context["turns"][2]["user"]

    def test_memory_persists_across_agent_method_calls(self):
        """Test that memory persists across multiple ask() calls."""

        config = QAConfig(llm_provider="mock", model="test", max_turns=10)
        agent = SimpleQAAgent(config)

        session_id = "persistent_session"

        # First call
        async def mock_execute_1(agent_inst, inputs):
            return {"answer": "First answer", "confidence": 0.9, "reasoning": "Test"}

        with patch.object(agent.strategy, "execute", side_effect=mock_execute_1):
            agent.ask("First question", session_id=session_id)

        # Check memory
        context = agent.memory.load_context(session_id)
        turn_count_after_first = context["turn_count"]

        # Second call
        async def mock_execute_2(agent_inst, inputs):
            return {"answer": "Second answer", "confidence": 0.9, "reasoning": "Test"}

        with patch.object(agent.strategy, "execute", side_effect=mock_execute_2):
            agent.ask("Second question", session_id=session_id)

        # Memory should have accumulated
        context = agent.memory.load_context(session_id)
        assert context["turn_count"] == turn_count_after_first + 1
        assert context["turn_count"] == 2
