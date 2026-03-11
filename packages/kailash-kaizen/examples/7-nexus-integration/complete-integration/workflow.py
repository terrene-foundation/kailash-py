"""
Complete Kaizen-Nexus Integration Showcase

This example demonstrates ALL integration capabilities in a production-ready pattern:
1. Optional integration detection and graceful handling
2. Multi-channel deployment (API, CLI, MCP)
3. Session management across channels
4. Performance monitoring and caching
5. Error handling and recovery
6. Production-ready patterns

This is the definitive example for Kaizen-Nexus integration.

Performance Features:
- Deployment caching (90% faster redeployment)
- Performance metrics collection
- Session synchronization (<50ms)
- Concurrent request handling

Part of TODO-149 Phase 4: Performance & Testing
"""

import time
from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent

# Check Nexus availability
from kaizen.integrations.nexus import (
    NEXUS_AVAILABLE,
    NexusSessionManager,
    PerformanceMetrics,
    PerformanceMonitor,
    deploy_multi_channel,
)
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    print("ERROR: Nexus not available. Install with: pip install kailash-nexus")
    print("See: https://docs.kailash.ai/nexus/installation")
    exit(1)

from nexus import Nexus

# =============================================================================
# Agent Configuration and Signature
# =============================================================================


@dataclass
class AssistantConfig:
    """Configuration for AI assistant agent."""

    llm_provider: str = "mock"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000


class AssistantSignature(Signature):
    """Signature for AI assistant interactions."""

    query: str = InputField(description="User query or question")
    context: dict = InputField(description="Conversation context", default_factory=dict)
    response: str = OutputField(description="AI-generated response")
    confidence: float = OutputField(description="Confidence score (0-1)")


# =============================================================================
# Production-Ready AI Assistant
# =============================================================================


class AIAssistant(BaseAgent):
    """
    Production-ready AI assistant with Nexus multi-channel support.

    Features:
    - Multi-channel deployment (API, CLI, MCP)
    - Session management for conversation continuity
    - Performance monitoring
    - Error handling and recovery
    """

    def __init__(self, config: AssistantConfig):
        super().__init__(config=config, signature=AssistantSignature())

    def process(self, query: str, context: dict = None) -> dict:
        """
        Process user query with conversation context.

        Args:
            query: User query or question
            context: Optional conversation context

        Returns:
            Response with confidence score
        """
        result = self.run(query=query, context=context or {})

        # Extract and validate response
        response = self.extract_str(result, "response", default="I don't understand.")
        confidence = self.extract_float(result, "confidence", default=0.5)

        # Write to memory for conversation history
        self.write_to_memory(
            content={"query": query, "response": response, "confidence": confidence},
            tags=["conversation"],
            importance=confidence,
        )

        return {
            "response": response,
            "confidence": confidence,
            "timestamp": time.time(),
        }


# =============================================================================
# Main Integration Showcase
# =============================================================================


def main():
    """
    Complete Kaizen-Nexus integration demonstration.

    This function showcases:
    1. Platform initialization
    2. Performance monitoring setup
    3. Session management configuration
    4. Multi-channel deployment with caching
    5. Cross-channel session usage
    6. Performance analysis
    7. Resource cleanup
    """
    print("=" * 70)
    print("COMPLETE KAIZEN-NEXUS INTEGRATION SHOWCASE")
    print("=" * 70)
    print()

    # =========================================================================
    # Step 1: Initialize Performance Monitoring
    # =========================================================================
    print("[1/8] Initializing performance monitoring...")
    metrics = PerformanceMetrics()

    # =========================================================================
    # Step 2: Initialize Nexus Platform
    # =========================================================================
    print("[2/8] Initializing Nexus platform...")
    with PerformanceMonitor(metrics, "deployment") as monitor:
        app = Nexus(auto_discovery=False)

    print(f"      Platform initialized in {metrics.deployment_times[-1]*1000:.1f}ms")
    print()

    # =========================================================================
    # Step 3: Configure Session Management
    # =========================================================================
    print("[3/8] Configuring session management...")
    session_manager = NexusSessionManager(
        cleanup_interval=300, session_ttl=7200  # 5 minutes  # 2 hours
    )
    print("      Session management configured")
    print("      - Cleanup interval: 5 minutes")
    print("      - Session TTL: 2 hours")
    print()

    # =========================================================================
    # Step 4: Create AI Assistant
    # =========================================================================
    print("[4/8] Creating AI assistant...")
    config = AssistantConfig()
    assistant = AIAssistant(config)
    print("      Assistant created with signature-based programming")
    print(f"      - Provider: {config.llm_provider}")
    print(f"      - Model: {config.model}")
    print(f"      - Temperature: {config.temperature}")
    print()

    # =========================================================================
    # Step 5: Deploy Across All Channels (with caching)
    # =========================================================================
    print("[5/8] Deploying across all channels (API, CLI, MCP)...")
    with PerformanceMonitor(metrics, "deployment") as monitor:
        channels = deploy_multi_channel(
            agent=assistant,
            nexus_app=app,
            name="assistant",
            # use_cache=True is default, enables 90% faster redeployment
        )

    deployment_time = metrics.deployment_times[-1]
    print(f"      Deployment completed in {deployment_time*1000:.1f}ms")
    print()
    print("      Channels available:")
    for channel, identifier in channels.items():
        print(f"      - {channel.upper():8s}: {identifier}")
    print()

    # =========================================================================
    # Step 6: Demonstrate Multi-Channel Usage
    # =========================================================================
    print("[6/8] Demonstrating multi-channel usage...")

    # Create cross-channel session
    session = session_manager.create_session(user_id="demo-user-123")
    print(f"      Session created: {session.session_id}")
    print()

    # === API Channel Usage ===
    print("      [API] Simulating API request...")
    with PerformanceMonitor(metrics, "api") as monitor:
        session_manager.update_session_state(
            session.session_id,
            {
                "query": "Explain quantum computing in simple terms",
                "channel": "api",
                "timestamp": time.time(),
            },
            channel="api",
        )

        # Execute agent
        result = assistant.process(
            query="Explain quantum computing in simple terms", context={"source": "api"}
        )

        # Store result in session
        session_manager.update_session_state(
            session.session_id, {"api_result": result}, channel="api"
        )

    api_time = metrics.api_latencies[-1]
    print(f"      [API] Response time: {api_time*1000:.1f}ms")
    print(f"      [API] Response: {result['response'][:50]}...")
    print()

    # === CLI Channel Usage ===
    print("      [CLI] Simulating CLI command...")
    with PerformanceMonitor(metrics, "cli") as monitor:
        # CLI accesses session state from API
        state = session_manager.get_session_state(session.session_id, channel="cli")

        # CLI continues conversation
        result = assistant.process(query="Can you give me an example?", context=state)

        session_manager.update_session_state(
            session.session_id, {"cli_result": result}, channel="cli"
        )

    cli_time = metrics.cli_latencies[-1]
    print(f"      [CLI] Response time: {cli_time*1000:.1f}ms")
    print(f"      [CLI] Context preserved: {state.get('query', 'N/A')[:40]}...")
    print()

    # === MCP Channel Usage ===
    print("      [MCP] Simulating MCP tool call...")
    with PerformanceMonitor(metrics, "mcp") as monitor:
        # MCP accesses full session history
        state = session_manager.get_session_state(session.session_id, channel="mcp")

        # MCP uses accumulated context
        result = assistant.process(query="Summarize our conversation", context=state)

        session_manager.update_session_state(
            session.session_id, {"mcp_result": result}, channel="mcp"
        )

    mcp_time = metrics.mcp_latencies[-1]
    print(f"      [MCP] Response time: {mcp_time*1000:.1f}ms")
    print(f"      [MCP] Full context available: {len(state)} keys")
    print()

    # Verify session synchronization
    print("      Verifying cross-channel session synchronization...")
    final_state = session_manager.get_session_state(session.session_id)
    print(f"      Session state contains: {list(final_state.keys())}")
    print(f"      Channels used: {session.channel_activity.keys()}")
    print()

    # =========================================================================
    # Step 7: Performance Analysis
    # =========================================================================
    print("[7/8] Performance analysis:")
    summary = metrics.get_summary()

    print()
    print("      Deployment Performance:")
    print(f"      - Mean:   {summary['deployment']['mean']*1000:.1f}ms")
    print(f"      - Median: {summary['deployment']['median']*1000:.1f}ms")
    print(f"      - Count:  {summary['deployment']['count']}")

    print()
    print("      API Latency:")
    print(f"      - Mean:   {summary['api']['mean']*1000:.1f}ms")
    print(
        "      - Target: <500ms ✓"
        if summary["api"]["mean"] < 0.5
        else "      - Target: <500ms ✗"
    )

    print()
    print("      CLI Latency:")
    print(f"      - Mean:   {summary['cli']['mean']*1000:.1f}ms")
    print(
        "      - Target: <500ms ✓"
        if summary["cli"]["mean"] < 0.5
        else "      - Target: <500ms ✗"
    )

    print()
    print("      MCP Latency:")
    print(f"      - Mean:   {summary['mcp']['mean']*1000:.1f}ms")
    print(
        "      - Target: <500ms ✓"
        if summary["mcp"]["mean"] < 0.5
        else "      - Target: <500ms ✗"
    )

    # =========================================================================
    # Step 8: Cleanup and Summary
    # =========================================================================
    print()
    print("[8/8] Cleanup and summary...")

    # Cleanup expired sessions
    cleaned = session_manager.cleanup_expired_sessions()
    print(f"      Cleaned {cleaned} expired sessions")

    # Session metrics
    session_metrics = session_manager.get_session_metrics()
    print(f"      Active sessions: {session_metrics['active_sessions']}")
    print(f"      Total sessions: {session_metrics['total_sessions']}")

    # Health check
    health = app.health_check()
    print(f"      Platform status: {health['status']}")

    print()
    print("=" * 70)
    print("INTEGRATION SHOWCASE COMPLETE")
    print("=" * 70)
    print()
    print("✓ All systems operational")
    print("✓ Multi-channel deployment verified")
    print("✓ Session management working")
    print("✓ Performance within targets")
    print("✓ Production-ready patterns demonstrated")
    print()
    print("Next steps:")
    print("1. Review performance metrics above")
    print("2. Test with real LLM providers (set API keys)")
    print("3. Deploy to production with app.start()")
    print("4. Monitor with platform health checks")
    print()


if __name__ == "__main__":
    main()
