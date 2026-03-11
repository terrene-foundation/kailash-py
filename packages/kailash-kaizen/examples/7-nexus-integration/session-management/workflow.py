"""
Kaizen-Nexus Session Management Example

Demonstrates cross-channel session consistency across API, CLI, and MCP channels.

Scenario:
1. User starts conversation via API
2. Continues conversation via CLI
3. Completes task via MCP
4. All channels share same session state

This shows how Nexus maintains conversation context across channels.

Features Demonstrated:
- Session creation and management
- Cross-channel state synchronization
- Channel activity tracking
- Session expiration and cleanup
- Memory pool integration
"""

from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent
from kaizen.integrations.nexus import (
    NEXUS_AVAILABLE,
    NexusSessionManager,
    deploy_with_sessions,
)
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    print("Nexus not available. Install with: pip install kailash-nexus")
    exit(1)

from nexus import Nexus


@dataclass
class ConversationConfig:
    """Configuration for conversation agent."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.8


class ConversationSignature(Signature):
    """Conversational agent signature."""

    message: str = InputField(description="User message")
    context: dict = InputField(description="Conversation context", default_factory=dict)
    response: str = OutputField(description="Agent response")


class ConversationAgent(BaseAgent):
    """Agent that maintains conversation context."""

    def __init__(self, config: ConversationConfig):
        super().__init__(config=config, signature=ConversationSignature())

    def chat(self, message: str, context: dict = None) -> dict:
        """Continue conversation with context."""
        return self.run(message=message, context=context or {})


def main():
    print("=" * 60)
    print("Cross-Channel Session Management Example")
    print("=" * 60)

    # Create Nexus platform
    print("\n1. Initializing Nexus with session management...")
    app = Nexus(auto_discovery=False)
    session_manager = NexusSessionManager(cleanup_interval=600)
    print("   ✓ Nexus platform initialized")
    print("   ✓ Session manager created (10min cleanup interval)")

    # Create conversation agent
    print("\n2. Creating conversation agent...")
    config = ConversationConfig()
    agent = ConversationAgent(config)
    print("   ✓ ConversationAgent created with mock provider")

    # Deploy with session support
    print("\n3. Deploying with session management...")
    channels = deploy_with_sessions(
        agent=agent, nexus_app=app, name="chat", session_manager=session_manager
    )

    print("   ✓ Deployed across channels:")
    for channel, identifier in channels.items():
        print(f"     - {channel}: {identifier}")

    # Simulate cross-channel conversation
    print("\n" + "=" * 60)
    print("Simulating Cross-Channel Conversation")
    print("=" * 60)

    # Create session
    session = session_manager.create_session(user_id="user-123")
    print(f"\n   Session created: {session.session_id}")
    print(f"   User ID: {session.user_id}")
    print(f"   Expires: {session.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")

    # API: Start conversation
    print("\n   [API Channel]")
    print("   User: What's the weather like?")
    session_manager.update_session_state(
        session.session_id,
        {
            "conversation_history": [
                {"role": "user", "content": "What's the weather like?"},
                {"role": "assistant", "content": "I'll check the weather for you."},
            ],
            "message_count": 2,
        },
        channel="api",
    )
    print("   ✓ State updated via API")
    print("   ✓ Conversation history: 2 messages")

    # CLI: Continue conversation (sees API state)
    print("\n   [CLI Channel]")
    print("   User checks conversation history...")
    cli_state = session_manager.get_session_state(session.session_id, channel="cli")
    print(f"   ✓ Retrieved {len(cli_state['conversation_history'])} messages from API")
    print(f"   ✓ Last message: \"{cli_state['conversation_history'][-1]['content']}\"")

    session_manager.update_session_state(
        session.session_id,
        {
            "conversation_history": cli_state["conversation_history"]
            + [{"role": "user", "content": "Thanks!"}],
            "message_count": cli_state["message_count"] + 1,
            "cli_accessed": True,
        },
        channel="cli",
    )
    print("   ✓ Added new message via CLI")
    print("   ✓ Total messages now: 3")

    # MCP: Complete task (sees both API and CLI state)
    print("\n   [MCP Channel]")
    print("   Tool retrieves full context...")
    mcp_state = session_manager.get_session_state(session.session_id, channel="mcp")
    print(f"   ✓ Retrieved {len(mcp_state['conversation_history'])} messages")
    print(f"   ✓ Message count: {mcp_state['message_count']}")
    print(f"   ✓ CLI accessed: {mcp_state.get('cli_accessed', False)}")

    # Verify cross-channel consistency
    print("\n" + "=" * 60)
    print("Verifying Cross-Channel Consistency")
    print("=" * 60)

    final_api = session_manager.get_session_state(session.session_id, channel="api")
    final_cli = session_manager.get_session_state(session.session_id, channel="cli")
    final_mcp = session_manager.get_session_state(session.session_id, channel="mcp")

    print(f"\n   API State:  {len(final_api['conversation_history'])} messages")
    print(f"   CLI State:  {len(final_cli['conversation_history'])} messages")
    print(f"   MCP State:  {len(final_mcp['conversation_history'])} messages")

    if final_api == final_cli == final_mcp:
        print("\n   ✓ All channels see identical state!")
    else:
        print("\n   ✗ State mismatch detected")

    # Display channel activity
    print("\n" + "=" * 60)
    print("Channel Activity Tracking")
    print("=" * 60)

    tracked_session = session_manager.get_session(session.session_id)
    print(f"\n   Session {tracked_session.session_id}:")
    print(f"   User: {tracked_session.user_id}")
    print(f"   Created: {tracked_session.created_at.strftime('%H:%M:%S')}")
    print(f"   Last accessed: {tracked_session.last_accessed.strftime('%H:%M:%S')}")
    print("\n   Channel Activity:")
    for channel_name, timestamp in sorted(tracked_session.channel_activity.items()):
        print(f"     - {channel_name}: {timestamp.strftime('%H:%M:%S')}")

    # Demonstrate memory pool binding
    print("\n" + "=" * 60)
    print("Memory Pool Integration")
    print("=" * 60)

    print("\n   Binding session to shared memory pool...")
    success = session_manager.bind_memory_pool(session.session_id, "shared-pool-xyz")

    if success:
        print("   ✓ Session bound to memory pool: shared-pool-xyz")
        print("   ✓ Agents can now share memory via this session")

        # Store agent memory in session
        session_manager.update_session_state(
            session.session_id,
            {
                "agent_memories": [
                    {
                        "timestamp": "2025-01-01",
                        "content": "User prefers concise responses",
                    },
                    {
                        "timestamp": "2025-01-02",
                        "content": "User is interested in weather",
                    },
                ]
            },
        )
        print("   ✓ Stored 2 agent memories in session")

        # Agents can access shared memory
        shared_state = session_manager.get_session_state(session.session_id)
        print(
            f"   ✓ Memories accessible to all agents: {len(shared_state['agent_memories'])}"
        )
    else:
        print("   ✗ Failed to bind memory pool")

    # Summary
    print("\n" + "=" * 60)
    print("Session Management Summary")
    print("=" * 60)

    print(f"\n   Total Sessions: {len(session_manager.sessions)}")
    print(f"   Active Session: {session.session_id}")
    print(f"   Channels Used: {list(tracked_session.channel_activity.keys())}")
    print(f"   State Keys: {list(final_api.keys())}")
    print(f"   Memory Pool: {tracked_session.memory_pool_id}")

    print("\n" + "=" * 60)
    print("Example Complete")
    print("=" * 60)

    print("\nKey Takeaways:")
    print("  1. Sessions maintain state across API, CLI, and MCP channels")
    print("  2. All channels see the same state in real-time")
    print("  3. Channel activity is tracked automatically")
    print("  4. Sessions can bind to memory pools for agent collaboration")
    print("  5. Session expiration and cleanup handled automatically")


if __name__ == "__main__":
    main()
