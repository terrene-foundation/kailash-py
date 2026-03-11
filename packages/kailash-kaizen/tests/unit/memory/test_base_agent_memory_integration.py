"""
Unit tests for BaseAgent memory integration.

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, mock LLM
- Tests memory integration with BaseAgent
- Tests all 4 memory types (Buffer, Summary, Vector, KG)
- Tests session_id parameter handling
- Tests backward compatibility (agents without memory)
"""

from unittest.mock import Mock


class TestBaseAgentMemoryConfigIntegration:
    """Test BaseAgent memory configuration integration."""

    def test_base_agent_accepts_memory_parameter(self):
        """Test that BaseAgent can be instantiated with memory parameter."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", memory_enabled=True
        )

        memory = BufferMemory()

        # BaseAgent should accept memory parameter
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        assert agent.memory is not None
        assert isinstance(agent.memory, BufferMemory)

    def test_base_agent_without_memory_parameter(self):
        """Test that BaseAgent works without memory (backward compatibility)."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", memory_enabled=False
        )

        agent = BaseAgent(config=config, signature=TestSignature())

        # Should work without memory
        assert hasattr(agent, "memory")
        assert agent.memory is None


class TestBaseAgentBufferMemoryIntegration:
    """Test BaseAgent with BufferMemory."""

    def test_agent_loads_buffer_memory_context(self):
        """Test that agent loads memory context before execution."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = BufferMemory()

        # Pre-populate memory with turns
        memory.save_turn(
            "session1", {"user": "Previous question", "agent": "Previous answer"}
        )

        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy to capture inputs
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Test output"})
        agent.strategy = mock_strategy

        # Run with session_id
        agent.run(prompt="Current question", session_id="session1")

        # Verify strategy was called with memory context
        call_args = mock_strategy.execute.call_args
        inputs = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("inputs", {})
        )

        # Memory context should be in inputs
        assert "_memory_context" in inputs
        assert inputs["_memory_context"]["turn_count"] == 1

    def test_agent_saves_turn_to_buffer_memory_after_execution(self):
        """Test that agent saves turn to memory after execution."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = BufferMemory()
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Test output"})
        agent.strategy = mock_strategy

        # Run with session_id
        agent.run(prompt="Test question", session_id="session1")

        # Verify memory was updated
        context = memory.load_context("session1")
        assert context["turn_count"] == 1
        assert context["turns"][0]["user"] == "Test question"
        assert context["turns"][0]["agent"] == "Test output"


class TestBaseAgentSummaryMemoryIntegration:
    """Test BaseAgent with SummaryMemory."""

    def test_agent_with_summary_memory(self):
        """Test agent with SummaryMemory integration."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.summary import SummaryMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = SummaryMemory(keep_recent=2)
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Test"})
        agent.strategy = mock_strategy

        # Run multiple times to trigger summarization
        for i in range(4):
            agent.run(prompt=f"Question {i}", session_id="session1")

        # Verify summary memory behavior
        context = memory.load_context("session1")
        assert context["turn_count"] == 4
        assert len(context["recent_turns"]) == 2  # keep_recent=2
        assert context["summary"] != ""  # Summary generated


class TestBaseAgentVectorMemoryIntegration:
    """Test BaseAgent with VectorMemory."""

    def test_agent_with_vector_memory(self):
        """Test agent with VectorMemory integration."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.vector import VectorMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = VectorMemory(top_k=2)
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Answer"})
        agent.strategy = mock_strategy

        # Add some turns
        agent.run(prompt="Python programming", session_id="session1")
        agent.run(prompt="What's for dinner?", session_id="session1")

        # Verify vector memory behavior
        context = memory.load_context("session1", query="coding")
        assert len(context["all_turns"]) == 2
        # relevant_turns would be populated if query matches


class TestBaseAgentKnowledgeGraphMemoryIntegration:
    """Test BaseAgent with KnowledgeGraphMemory."""

    def test_agent_with_knowledge_graph_memory(self):
        """Test agent with KnowledgeGraphMemory integration."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.knowledge_graph import KnowledgeGraphMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = KnowledgeGraphMemory()
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Ok"})
        agent.strategy = mock_strategy

        # Add turn with entities
        agent.run(prompt="Alice met Bob in Paris", session_id="session1")

        # Verify knowledge graph behavior
        context = memory.load_context("session1")
        assert "Alice" in context["entities"]
        assert "Bob" in context["entities"]
        assert "Paris" in context["entities"]


class TestBaseAgentSessionIsolation:
    """Test session isolation in memory."""

    def test_different_sessions_isolated(self):
        """Test that different sessions maintain separate memory."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = BufferMemory()
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Ok"})
        agent.strategy = mock_strategy

        # Run with different sessions
        agent.run(prompt="Session 1 question", session_id="session1")
        agent.run(prompt="Session 2 question", session_id="session2")

        # Verify isolation
        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        assert context1["turn_count"] == 1
        assert context2["turn_count"] == 1
        assert context1["turns"][0]["user"] == "Session 1 question"
        assert context2["turns"][0]["user"] == "Session 2 question"

    def test_no_session_id_no_memory_persistence(self):
        """Test that without session_id, memory is not persisted."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=True
        )

        memory = BufferMemory()
        agent = BaseAgent(config=config, signature=TestSignature(), memory=memory)

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Ok"})
        agent.strategy = mock_strategy

        # Run without session_id
        agent.run(prompt="Question without session")

        # Verify no memory persistence (no sessions created)
        # Since no session_id, memory should not have any sessions
        assert len(memory._sessions) == 0


class TestBaseAgentBackwardCompatibility:
    """Test backward compatibility - agents without memory."""

    def test_agent_without_memory_still_works(self):
        """Test that agent without memory works normally."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            prompt: str = InputField(desc="Test input")
            response: str = OutputField(desc="Test output")

        config = BaseAgentConfig(
            llm_provider="mock", model="mock-model", memory_enabled=False
        )

        agent = BaseAgent(config=config, signature=TestSignature())

        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.execute = Mock(return_value={"response": "Ok"})
        agent.strategy = mock_strategy

        # Run without memory
        result = agent.run(prompt="Test question")

        # Should work fine
        assert result["response"] == "Ok"
        assert agent.memory is None
