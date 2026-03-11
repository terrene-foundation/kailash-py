#!/usr/bin/env python3
"""
Example 1: Simple Chain (QA → Memory)

Demonstrates chaining Kaizen agents as workflow nodes instead of using
pre-built agent methods.

Workflow:
    SimpleQAAgent → MemoryAgent

Flow:
    1. Ask question with SimpleQA
    2. Pass answer to MemoryAgent for summarization
    3. Memory persists the conversation

Benefits over direct agent usage:
    - Declarative workflow (JSON-serializable)
    - Visual composition in Studio
    - Reusable workflow template
    - Automatic data routing
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def main():
    """Execute simple agent chain workflow."""

    print("=" * 70)
    print("Workflow Chaining Example 1: QA → Memory")
    print("=" * 70)
    print()

    # ========================================
    # Build Workflow (Declarative)
    # ========================================

    print("🔨 Building workflow...")
    workflow = WorkflowBuilder()

    # Node 1: SimpleQA Agent
    print("   Adding SimpleQAAgent...")
    workflow.add_node(
        "SimpleQAAgent",
        "qa",
        {
            "question": "What is machine learning in simple terms?",
            "llm_provider": "ollama",
            "model": "llama2",
            "temperature": 0.7,
            "max_tokens": 300,
        },
    )

    # Node 2: Memory Agent (receives QA answer)
    print("   Adding MemoryAgent...")
    workflow.add_node(
        "MemoryAgent",
        "memory",
        {
            "question": "Summarize this in one sentence",  # Will receive qa.answer as context
            "session_id": "example_session_1",
            "llm_provider": "ollama",
            "model": "llama2",
            "temperature": 0.5,
            "max_tokens": 150,
        },
    )

    # Connect: qa.answer → memory (memory will receive answer as input)
    print("   Connecting qa → memory...")
    workflow.add_edge("qa", "memory")

    print("   ✅ Workflow built")
    print()

    # ========================================
    # Execute Workflow
    # ========================================

    print("🚀 Executing workflow...")
    print()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # ========================================
    # Display Results
    # ========================================

    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()

    print("📊 Run ID:", run_id)
    print()

    print("🤖 Node 1: SimpleQAAgent (qa)")
    print("-" * 70)
    if "qa" in results:
        qa_result = results["qa"]
        print("Question: What is machine learning in simple terms?")
        print(f"Answer: {qa_result.get('answer', 'N/A')[:300]}...")
        print(f"Confidence: {qa_result.get('confidence', 'N/A')}")
        print()

    print("🧠 Node 2: MemoryAgent (memory)")
    print("-" * 70)
    if "memory" in results:
        memory_result = results["memory"]
        print("Question: Summarize this in one sentence")
        print("Context: [QA answer from previous node]")
        print(f"Summary: {memory_result.get('answer', 'N/A')}")
        print(f"Session ID: {memory_result.get('session_id', 'N/A')}")
        print()

    # ========================================
    # Show Data Flow
    # ========================================

    print("=" * 70)
    print("DATA FLOW")
    print("=" * 70)
    print()

    print("1. SimpleQAAgent executed:")
    print("   Input: question='What is machine learning?'")
    print(f"   Output: answer='{results.get('qa', {}).get('answer', 'N/A')[:100]}...'")
    print()

    print("2. MemoryAgent executed:")
    print("   Input: answer from qa (auto-connected)")
    print("   Input: question='Summarize this in one sentence'")
    print(f"   Output: summary='{results.get('memory', {}).get('answer', 'N/A')}'")
    print()

    print("3. Memory persisted:")
    print("   Session ID: example_session_1")
    print("   Conversation history stored for future queries")
    print()

    # ========================================
    # Comparison with Direct Agent Usage
    # ========================================

    print("=" * 70)
    print("COMPARISON: Workflow vs Direct Agent Usage")
    print("=" * 70)
    print()

    print("❌ Direct Agent Usage (Old Way):")
    print(
        """
    from kaizen.agents import SimpleQAAgent, MemoryAgent

    qa = SimpleQAAgent(llm_provider="ollama", model="llama2")
    memory = MemoryAgent(llm_provider="ollama", model="llama2")

    # Manual chaining - hardcoded in Python
    answer = qa.ask("What is machine learning?")["answer"]
    summary = memory.ask(f"Summarize: {answer}", session_id="s1")

    # Problems:
    # - Chain logic in code (not declarative)
    # - Can't visualize in Studio
    # - Not reusable as template
    # - Manual data passing
    """
    )

    print("✅ Workflow (New Way):")
    print(
        """
    workflow = WorkflowBuilder()

    # Declarative node addition
    workflow.add_node("SimpleQAAgent", "qa", {...})
    workflow.add_node("MemoryAgent", "memory", {...})

    # Automatic data routing
    workflow.add_edge("qa", "memory")

    # Execute
    runtime.execute(workflow.build())

    # Benefits:
    # - Chain logic in data (JSON-serializable)
    # - Visualizable in Studio
    # - Reusable as template
    # - Automatic data passing
    """
    )

    print("=" * 70)
    print("✅ Example Complete!")
    print("=" * 70)
    print()

    print("📝 Studio JSON equivalent saved to:")
    print("   examples/workflow-chaining/01-simple-chain-qa-memory.json")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
