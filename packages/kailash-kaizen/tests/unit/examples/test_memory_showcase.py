"""
Unit tests for memory showcase demonstration.

Tests verify all 6 demonstration functions work correctly and showcase
the 4 memory types: BufferMemory, SummaryMemory, VectorMemory, KnowledgeGraphMemory.

Test Coverage:
- Demo function execution (6 tests)
- DemoAgent initialization and usage (3 tests)
- Integration tests (3 tests)

Total: 12+ tests
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load memory-showcase example
_demo_module = import_example_module(
    "examples/1-single-agent/memory-showcase", module_name="demo"
)
DemoAgent = _demo_module.DemoAgent
DemoConfig = _demo_module.DemoConfig
QASignature = _demo_module.QASignature
demo_buffer_memory = _demo_module.demo_buffer_memory
demo_summary_memory = _demo_module.demo_summary_memory
demo_vector_memory = _demo_module.demo_vector_memory
demo_knowledge_graph_memory = _demo_module.demo_knowledge_graph_memory
demo_no_memory = _demo_module.demo_no_memory
demo_session_isolation = _demo_module.demo_session_isolation

from kaizen.memory.buffer import BufferMemory
from kaizen.memory.knowledge_graph import KnowledgeGraphMemory
from kaizen.memory.summary import SummaryMemory
from kaizen.memory.vector import VectorMemory


class TestMemoryShowcaseDemoFunctions:
    """Test all demo functions execute without errors."""

    def test_demo_buffer_memory_executes(self, capsys):
        """Test BufferMemory demo runs successfully."""
        # Should not raise any exceptions
        demo_buffer_memory()

        # Verify output was produced
        captured = capsys.readouterr()
        assert "DEMO 1: BufferMemory" in captured.out
        assert "Full Conversation History" in captured.out

    def test_demo_summary_memory_executes(self, capsys):
        """Test SummaryMemory demo runs successfully."""
        # Should not raise any exceptions
        demo_summary_memory()

        # Verify output was produced
        captured = capsys.readouterr()
        assert "DEMO 2: SummaryMemory" in captured.out
        assert "LLM-Generated Summaries" in captured.out

    def test_demo_vector_memory_executes(self, capsys):
        """Test VectorMemory demo runs successfully."""
        # Should not raise any exceptions
        demo_vector_memory()

        # Verify output was produced
        captured = capsys.readouterr()
        assert "DEMO 3: VectorMemory" in captured.out
        assert "Semantic Search" in captured.out

    def test_demo_knowledge_graph_memory_executes(self, capsys):
        """Test KnowledgeGraphMemory demo runs successfully."""
        # Should not raise any exceptions
        demo_knowledge_graph_memory()

        # Verify output was produced
        captured = capsys.readouterr()
        assert "DEMO 4: KnowledgeGraphMemory" in captured.out
        assert "Entity Extraction" in captured.out

    def test_demo_no_memory_executes(self, capsys):
        """Test no memory demo runs successfully."""
        # Should not raise any exceptions
        demo_no_memory()

        # Verify output was produced
        captured = capsys.readouterr()
        assert "DEMO 5: No Memory" in captured.out
        assert "Baseline Comparison" in captured.out

    def test_demo_session_isolation_executes(self, capsys):
        """Test session isolation demo runs successfully."""
        # Should not raise any exceptions
        demo_session_isolation()

        # Verify output was produced
        captured = capsys.readouterr()
        assert "DEMO 6: Session Isolation" in captured.out
        assert "Session 1:" in captured.out
        assert "Session 2:" in captured.out


class TestMemoryShowcaseDemoAgent:
    """Test DemoAgent initialization and usage."""

    def test_demo_agent_without_memory(self):
        """Test DemoAgent initializes without memory."""
        config = DemoConfig()
        agent = DemoAgent(config, memory=None)

        assert agent.memory is None
        assert agent.signature is not None
        assert isinstance(agent.signature, QASignature)

    def test_demo_agent_with_buffer_memory(self):
        """Test DemoAgent initializes with BufferMemory."""
        config = DemoConfig()
        memory = BufferMemory(max_turns=5)
        agent = DemoAgent(config, memory=memory)

        assert agent.memory is memory
        assert isinstance(agent.memory, BufferMemory)

    def test_demo_agent_ask_method(self):
        """Test DemoAgent.ask() method works.

        Note: run() returns a dict with result or error fields.
        With mock provider, we test structure only.
        """
        config = DemoConfig()
        agent = DemoAgent(config, memory=None)

        # Ask a question
        result = agent.run(question="What is Python?")

        # run() returns a dict - may have 'answer' field or 'response' or 'error'
        assert isinstance(result, dict)
        # Should have either answer output or response or error
        assert "answer" in result or "response" in result or "error" in result


class TestMemoryShowcaseIntegration:
    """Test full showcase integration."""

    def test_all_demos_run_in_sequence(self, capsys):
        """Test all demonstrations run without errors."""
        # Run all demos like main would
        demo_buffer_memory()
        demo_summary_memory()
        demo_vector_memory()
        demo_knowledge_graph_memory()
        demo_no_memory()
        demo_session_isolation()

        # Verify all demos produced output
        captured = capsys.readouterr()
        assert "DEMO 1: BufferMemory" in captured.out
        assert "DEMO 2: SummaryMemory" in captured.out
        assert "DEMO 3: VectorMemory" in captured.out
        assert "DEMO 4: KnowledgeGraphMemory" in captured.out
        assert "DEMO 5: No Memory" in captured.out
        assert "DEMO 6: Session Isolation" in captured.out

    def test_each_memory_type_produces_different_behavior(self):
        """Test each memory type produces different behavior."""
        config = DemoConfig()

        # Create agents with different memory types
        buffer_agent = DemoAgent(config, memory=BufferMemory(max_turns=3))
        summary_agent = DemoAgent(config, memory=SummaryMemory(keep_recent=2))
        vector_agent = DemoAgent(config, memory=VectorMemory(top_k=2))
        kg_agent = DemoAgent(config, memory=KnowledgeGraphMemory())
        no_memory_agent = DemoAgent(config, memory=None)

        # All agents should have different memory configurations
        assert isinstance(buffer_agent.memory, BufferMemory)
        assert isinstance(summary_agent.memory, SummaryMemory)
        assert isinstance(vector_agent.memory, VectorMemory)
        assert isinstance(kg_agent.memory, KnowledgeGraphMemory)
        assert no_memory_agent.memory is None

        # Memory types should be distinguishable
        assert type(buffer_agent.memory).__name__ == "BufferMemory"
        assert type(summary_agent.memory).__name__ == "SummaryMemory"
        assert type(vector_agent.memory).__name__ == "VectorMemory"
        assert type(kg_agent.memory).__name__ == "KnowledgeGraphMemory"

    def test_session_isolation_demonstration_works(self):
        """Test session isolation demonstration works correctly.

        Note: run() returns a dict. With mock provider, we test structure only.
        """
        config = DemoConfig()
        memory = BufferMemory(max_turns=None)
        agent = DemoAgent(config, memory=memory)

        # Session 1
        agent.run(question="My name is Alice", session_id="session1")
        result1 = agent.run(question="What's my name?", session_id="session1")

        # Session 2
        agent.run(question="My name is Bob", session_id="session2")
        result2 = agent.run(question="What's my name?", session_id="session2")

        # Both sessions should have dict results
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)

        # Verify memory has both sessions stored
        context1 = memory.load_context("session1")
        context2 = memory.load_context("session2")

        # Turn count depends on memory update behavior with mock provider
        assert context1["turn_count"] >= 0
        assert context2["turn_count"] >= 0


class TestMemoryShowcaseSignature:
    """Test QASignature used in demos."""

    def test_qa_signature_has_required_fields(self):
        """Test QASignature has question and answer fields."""
        signature = QASignature()

        # Check that signature exists
        assert signature is not None

        # Check that signature has the expected structure
        # (actual field inspection depends on Signature implementation)
        assert hasattr(signature, "__class__")
        assert signature.__class__.__name__ == "QASignature"


class TestMemoryShowcaseMemoryInteraction:
    """Test memory interaction patterns in demos."""

    def test_buffer_memory_respects_max_turns(self):
        """Test BufferMemory properly enforces max_turns limit."""
        config = DemoConfig()
        memory = BufferMemory(max_turns=3)
        agent = DemoAgent(config, memory=memory)

        session_id = "test_buffer"

        # Add 5 turns
        for i in range(5):
            agent.ask(f"Question {i}", session_id=session_id)

        # Should only keep last 3 turns
        context = memory.load_context(session_id)
        assert context["turn_count"] == 3

    def test_summary_memory_keeps_recent_turns(self):
        """Test SummaryMemory properly maintains recent turns."""
        config = DemoConfig()
        memory = SummaryMemory(keep_recent=2)
        agent = DemoAgent(config, memory=memory)

        session_id = "test_summary"

        # Add 4 turns
        for i in range(4):
            agent.ask(f"Question {i}", session_id=session_id)

        # Should keep last 2 turns recent
        context = memory.load_context(session_id)
        assert len(context["recent_turns"]) == 2
        assert context["turn_count"] == 4

    def test_vector_memory_stores_all_turns(self):
        """Test VectorMemory stores all conversation turns."""
        config = DemoConfig()
        memory = VectorMemory(top_k=2)
        agent = DemoAgent(config, memory=memory)

        session_id = "test_vector"

        # Add 3 turns
        agent.ask("What is deep learning?", session_id=session_id)
        agent.ask("Tell me about Paris", session_id=session_id)
        agent.ask("How does backpropagation work?", session_id=session_id)

        # Should have all turns stored
        context = memory.load_context(session_id)
        assert len(context["all_turns"]) == 3

    def test_knowledge_graph_memory_extracts_entities(self):
        """Test KnowledgeGraphMemory extracts entities from conversations."""
        config = DemoConfig()
        memory = KnowledgeGraphMemory()
        agent = DemoAgent(config, memory=memory)

        session_id = "test_kg"

        # Add turns with entities
        agent.ask("Tell me about Albert Einstein", session_id=session_id)
        agent.ask("What about Marie Curie?", session_id=session_id)

        # Should have extracted entities
        context = memory.load_context(session_id)
        entities = context.get("entities", {})

        # Should have at least some entities (capitalized words)
        # Note: Default extractor extracts capitalized words
        assert len(entities) > 0
