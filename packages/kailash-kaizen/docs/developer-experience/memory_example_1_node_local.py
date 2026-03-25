#!/usr/bin/env python3
"""
Example 1: Node-Local Memory
Shows how session_id isolates conversations per user.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kaizen_agents.agents.specialized.memory_agent import MemoryAgent


def demo_node_local_memory():
    """Node-local memory: Each session_id has independent history."""

    print("=" * 70)
    print("Example 1: Node-Local Memory (session_id)")
    print("=" * 70)
    print()

    # Create single agent instance
    agent = MemoryAgent(llm_provider="ollama", model="llama2")

    # Session 1: User Alice
    print("📍 Session: user_alice")
    result1 = agent.chat("My name is Alice", session_id="user_alice")
    print("   User: My name is Alice")
    print(f"   Agent: {result1['response']}")

    result2 = agent.chat("What is my name?", session_id="user_alice")
    print("   User: What is my name?")
    print(f"   Agent: {result2['response']}")  # → "Alice"
    print()

    # Session 2: User Bob (DIFFERENT session)
    print("📍 Session: user_bob")
    result3 = agent.chat("My name is Bob", session_id="user_bob")
    print("   User: My name is Bob")
    print(f"   Agent: {result3['response']}")

    result4 = agent.chat("What is my name?", session_id="user_bob")
    print("   User: What is my name?")
    print(f"   Agent: {result4['response']}")  # → "Bob" (NOT Alice!)
    print()

    # Verify isolation
    print("✅ Memory Isolation Verified:")
    print(
        f"   Session 'user_alice' has {agent.get_conversation_count('user_alice')} messages"
    )
    print(
        f"   Session 'user_bob' has {agent.get_conversation_count('user_bob')} messages"
    )
    print()

    print("🔍 Studio Visual Builder Mapping:")
    print("   This is a NODE PARAMETER - configured per node:")
    print()
    print("   Node 1 Config:")
    print("   ┌─────────────────────────────────────┐")
    print("   │ MemoryAgent Configuration           │")
    print("   ├─────────────────────────────────────┤")
    print("   │ Message: [My name is Alice______]  │")
    print("   │ Session ID: [user_alice_________]  │ ← Per-node config")
    print("   └─────────────────────────────────────┘")
    print()


if __name__ == "__main__":
    demo_node_local_memory()
