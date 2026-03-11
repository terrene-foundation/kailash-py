"""
Kaizen Memory Systems Demonstration

This demo showcases all 4 memory types available in Kaizen:
1. BufferMemory - Full conversation history with FIFO limiting
2. SummaryMemory - LLM-generated summaries + recent verbatim
3. VectorMemory - Semantic search over conversations
4. KnowledgeGraphMemory - Entity extraction and relationships

Key Concepts Demonstrated:
- Same agent with different memory backends (comparison)
- Behavior with memory vs. without memory
- Multi-turn conversations showing memory benefits
- Session isolation (same agent, different sessions)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.buffer import BufferMemory
from kaizen.memory.knowledge_graph import KnowledgeGraphMemory
from kaizen.memory.summary import SummaryMemory
from kaizen.memory.vector import VectorMemory
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Configuration and Signature
# ============================================================================


@dataclass
class DemoConfig:
    """Configuration for demonstration agent."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    provider_config: Dict[str, Any] = field(default_factory=dict)


class QASignature(Signature):
    """Simple Q&A signature for demonstrations."""

    question: str = InputField(desc="User question")
    answer: str = OutputField(desc="Agent answer")


# ============================================================================
# Demo Agent
# ============================================================================


class DemoAgent(BaseAgent):
    """
    Simple demo agent for showcasing memory types.

    This agent uses BaseAgent architecture with optional memory support.
    It can be configured with any of the 4 memory types to demonstrate
    different memory behaviors.
    """

    def __init__(self, config: DemoConfig, memory=None):
        """
        Initialize demo agent with optional memory.

        Args:
            config: Agent configuration
            memory: Optional memory instance (BufferMemory, SummaryMemory, etc.)
        """
        # Create agent configuration
        agent_config = BaseAgentConfig(
            llm_provider=config.llm_provider,
            model=config.model,
            provider_config=config.provider_config,
            logging_enabled=False,  # Disable logging for cleaner demo output
            performance_enabled=False,
            error_handling_enabled=True,
        )

        # Initialize BaseAgent with signature and memory
        super().__init__(config=agent_config, signature=QASignature(), memory=memory)

    def ask(self, question: str, session_id: Optional[str] = None) -> str:
        """
        Ask a question and return the answer.

        Args:
            question: Question to ask
            session_id: Optional session identifier for memory persistence

        Returns:
            Answer string
        """
        # Execute via BaseAgent.run()
        result = self.run(question=question, session_id=session_id)

        # Extract answer (handle both dict and string responses)
        if isinstance(result, dict):
            return result.get("answer", result.get("response", str(result)))
        return str(result)


# ============================================================================
# Demonstration Functions
# ============================================================================


def demo_buffer_memory():
    """Demonstrate BufferMemory - full conversation history."""
    print("\n" + "=" * 80)
    print("DEMO 1: BufferMemory - Full Conversation History")
    print("=" * 80)
    print(
        "\nBufferMemory stores complete conversation history with optional FIFO limiting."
    )
    print("Perfect for: Short-term conversations, chat applications, debugging")

    # Create agent with BufferMemory (max 3 turns)
    memory = BufferMemory(max_turns=3)
    agent = DemoAgent(DemoConfig(), memory=memory)

    # Multi-turn conversation
    questions = [
        "What is Python?",
        "What did I just ask about?",
        "Tell me more about that topic",
        "What was my first question?",  # Should forget after 3 turns
    ]

    session_id = "buffer_demo"
    print("\nConversation (max_turns=3):")

    for i, question in enumerate(questions, 1):
        print(f"\n  Turn {i}: {question}")
        answer = agent.ask(question, session_id=session_id)
        print(f"  Answer: {answer}")

        # Show memory state
        context = memory.load_context(session_id)
        turn_count = context.get("turn_count", 0)
        print(f"  Memory: {turn_count} turns stored")

    print(
        "\n  Key Feature: FIFO limiting - oldest turns dropped when max_turns exceeded"
    )


def demo_summary_memory():
    """Demonstrate SummaryMemory - LLM-generated summaries."""
    print("\n" + "=" * 80)
    print("DEMO 2: SummaryMemory - LLM-Generated Summaries")
    print("=" * 80)
    print("\nSummaryMemory maintains summaries of older turns + recent verbatim turns.")
    print(
        "Perfect for: Long conversations, context compression, efficient memory usage"
    )

    # Create agent with SummaryMemory (keep 2 recent, summarize rest)
    memory = SummaryMemory(keep_recent=2)
    agent = DemoAgent(DemoConfig(), memory=memory)

    # Multi-turn conversation on related topics
    questions = [
        "Tell me about machine learning",
        "What about neural networks?",
        "How do transformers work?",
        "What's the difference from RNNs?",
    ]

    session_id = "summary_demo"
    print("\nConversation (keep_recent=2):")

    for i, question in enumerate(questions, 1):
        print(f"\n  Turn {i}: {question}")
        answer = agent.ask(question, session_id=session_id)
        print(f"  Answer: {answer}")

        # Show memory state
        context = memory.load_context(session_id)
        summary = context.get("summary", "")
        recent_count = len(context.get("recent_turns", []))
        total_count = context.get("turn_count", 0)

        if summary:
            print(f"  Summary: {summary}")
        print(f"  Recent: {recent_count} turns verbatim | Total: {total_count} turns")

    print("\n  Key Feature: Automatic summarization - older turns compressed by LLM")


def demo_vector_memory():
    """Demonstrate VectorMemory - semantic search."""
    print("\n" + "=" * 80)
    print("DEMO 3: VectorMemory - Semantic Search")
    print("=" * 80)
    print(
        "\nVectorMemory uses semantic similarity to retrieve relevant past conversations."
    )
    print(
        "Perfect for: Large knowledge bases, RAG applications, finding related context"
    )

    # Create agent with VectorMemory
    memory = VectorMemory(top_k=2)
    agent = DemoAgent(DemoConfig(), memory=memory)

    # Conversation with semantically related and unrelated questions
    questions = [
        "What is deep learning?",
        "Tell me about Paris",
        "How does backpropagation work?",  # Related to Q1
        "What's the weather like?",
        "Explain gradient descent",  # Related to Q1, Q3
    ]

    session_id = "vector_demo"
    print("\nConversation (top_k=2 most similar):")

    for i, question in enumerate(questions, 1):
        print(f"\n  Turn {i}: {question}")
        answer = agent.ask(question, session_id=session_id)
        print(f"  Answer: {answer}")

        # Show memory state
        if i > 1:
            # Load context with query to show semantic search
            context = memory.load_context(session_id, query=question)
            relevant = context.get("relevant_turns", [])
            all_turns = context.get("all_turns", [])
            print(f"  Relevant past turns: {len(relevant)} of {len(all_turns)} total")

    print(
        "\n  Key Feature: Semantic search - finds related conversations, not just recent"
    )


def demo_knowledge_graph_memory():
    """Demonstrate KnowledgeGraphMemory - entity extraction."""
    print("\n" + "=" * 80)
    print("DEMO 4: KnowledgeGraphMemory - Entity Extraction")
    print("=" * 80)
    print(
        "\nKnowledgeGraphMemory extracts entities and relationships from conversations."
    )
    print(
        "Perfect for: Multi-entity conversations, relationship tracking, knowledge graphs"
    )

    # Create agent with KnowledgeGraphMemory
    memory = KnowledgeGraphMemory()
    agent = DemoAgent(DemoConfig(), memory=memory)

    # Conversation mentioning entities
    questions = [
        "Tell me about Albert Einstein",
        "What about Marie Curie?",
        "How did Einstein and Curie know each other?",
        "What did Einstein discover?",
    ]

    session_id = "kg_demo"
    print("\nConversation (automatic entity extraction):")

    for i, question in enumerate(questions, 1):
        print(f"\n  Turn {i}: {question}")
        answer = agent.ask(question, session_id=session_id)
        print(f"  Answer: {answer}")

        # Show entities
        context = memory.load_context(session_id)
        entities = context.get("entities", {})
        entity_names = list(entities.keys())
        print(f"  Entities: {entity_names if entity_names else '(none yet)'}")

    print(
        "\n  Key Feature: Entity extraction - builds knowledge graph from conversation"
    )


def demo_no_memory():
    """Demonstrate agent WITHOUT memory (baseline)."""
    print("\n" + "=" * 80)
    print("DEMO 5: No Memory - Baseline Comparison")
    print("=" * 80)
    print("\nAgent without memory cannot reference previous conversation turns.")
    print(
        "Useful for: Stateless APIs, independent queries, privacy-focused applications"
    )

    # Create agent without memory
    agent = DemoAgent(DemoConfig(), memory=None)

    questions = ["What is Python?", "What did I just ask about?"]  # Should not remember

    print("\nConversation (no memory):")

    for i, question in enumerate(questions, 1):
        print(f"\n  Turn {i}: {question}")
        answer = agent.ask(question)  # No session_id
        print(f"  Answer: {answer}")

    print("\n  Warning: Without memory, agent cannot reference previous turns")
    print("  Key Feature: Stateless execution - each query is independent")


def demo_session_isolation():
    """Demonstrate session isolation."""
    print("\n" + "=" * 80)
    print("DEMO 6: Session Isolation")
    print("=" * 80)
    print("\nMultiple sessions maintain separate memory contexts.")
    print("Perfect for: Multi-user applications, parallel conversations, testing")

    # Create agent with BufferMemory
    memory = BufferMemory(max_turns=None)
    agent = DemoAgent(DemoConfig(), memory=memory)

    print("\nTwo parallel sessions with the same agent:")

    # Session 1
    print("\n  Session 1:")
    agent.ask("My name is Alice", session_id="session1")
    answer1 = agent.ask("What's my name?", session_id="session1")
    print("    Q: What's my name?")
    print(f"    A: {answer1}")

    # Session 2
    print("\n  Session 2:")
    agent.ask("My name is Bob", session_id="session2")
    answer2 = agent.ask("What's my name?", session_id="session2")
    print("    Q: What's my name?")
    print(f"    A: {answer2}")

    # Verify isolation
    context1 = memory.load_context("session1")
    context2 = memory.load_context("session2")
    print(f"\n  Session 1 turns: {context1['turn_count']}")
    print(f"  Session 2 turns: {context2['turn_count']}")
    print("\n  Key Feature: Sessions are completely isolated - no cross-contamination")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Kaizen Memory Systems Showcase")
    print("=" * 80)
    print("\nDemonstrating all 4 memory types:")
    print("  1. BufferMemory - Full conversation history")
    print("  2. SummaryMemory - LLM-generated summaries")
    print("  3. VectorMemory - Semantic search")
    print("  4. KnowledgeGraphMemory - Entity extraction")

    demo_buffer_memory()
    demo_summary_memory()
    demo_vector_memory()
    demo_knowledge_graph_memory()
    demo_no_memory()
    demo_session_isolation()

    print("\n" + "=" * 80)
    print("All demonstrations complete!")
    print("=" * 80)
    print("\nKey Takeaways:")
    print("  - Choose memory type based on use case")
    print("  - BufferMemory: Simple, fast, full history")
    print("  - SummaryMemory: Long conversations, efficient")
    print("  - VectorMemory: Semantic search, RAG applications")
    print("  - KnowledgeGraphMemory: Entity tracking, relationships")
    print("  - No Memory: Stateless, privacy-focused")
    print("\nSession isolation enables multi-user and parallel conversations.")
    print("=" * 80 + "\n")
