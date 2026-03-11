"""
Distributed Tracing with Hooks - Production Example

Demonstrates how to use the hooks system to implement distributed tracing
with OpenTelemetry integration for monitoring agent execution across services.

Use cases:
- Trace agent execution across microservices
- Debug performance issues in multi-agent systems
- Monitor agent behavior in production
- Track agent-to-agent communication latency

Run:
    python examples/autonomy/hooks/distributed_tracing_example.py
"""

import asyncio
from dataclasses import dataclass

from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# =============================================================================
# Tracing Hook Implementation
# =============================================================================


class DistributedTracingHook:
    """
    Production-ready distributed tracing hook.

    Integrates with OpenTelemetry (or any tracing backend) to track
    agent execution across services.

    Features:
    - Automatic span creation for agent loops
    - Propagate trace context across agents
    - Track tool execution latency
    - Export to Jaeger/Zipkin/etc.
    """

    def __init__(self, service_name: str = "kaizen-agent"):
        """
        Initialize tracing hook.

        Args:
            service_name: Service name for tracing backend
        """
        self.service_name = service_name
        self.active_spans = {}  # track_id -> span_info

    async def start_agent_span(self, context: HookContext) -> HookResult:
        """
        Start tracing span when agent loop begins.

        Creates a new span for the agent execution and stores it
        for completion in POST_AGENT_LOOP.
        """
        trace_id = context.trace_id

        # In production, create actual OpenTelemetry span:
        # from opentelemetry import trace
        # tracer = trace.get_tracer(self.service_name)
        # span = tracer.start_span(f"agent.{context.agent_id}.loop")

        # For demo, just track timing
        import time

        span_info = {
            "trace_id": trace_id,
            "agent_id": context.agent_id,
            "start_time": time.time(),
            "inputs": context.data.get("inputs", {}),
        }

        self.active_spans[trace_id] = span_info

        print(
            f"📍 [TRACE] Started span for agent={context.agent_id} trace_id={trace_id[:8]}..."
        )

        return HookResult(
            success=True, data={"span_started": True, "trace_id": trace_id}
        )

    async def end_agent_span(self, context: HookContext) -> HookResult:
        """
        End tracing span when agent loop completes.

        Finalizes the span with duration, status, and result metadata.
        """
        trace_id = context.trace_id

        if trace_id not in self.active_spans:
            return HookResult(success=False, error="No active span found")

        span_info = self.active_spans.pop(trace_id)

        import time

        duration_ms = (time.time() - span_info["start_time"]) * 1000

        # In production, end OpenTelemetry span:
        # span.set_attribute("agent.id", context.agent_id)
        # span.set_attribute("duration.ms", duration_ms)
        # span.set_status(Status(StatusCode.OK))
        # span.end()

        result = context.data.get("result", {})
        success = result.get("success", True)

        print(
            f"✅ [TRACE] Ended span for agent={context.agent_id} "
            f"duration={duration_ms:.1f}ms success={success}"
        )

        return HookResult(
            success=True,
            data={"span_ended": True, "duration_ms": duration_ms, "success": success},
        )


# =============================================================================
# Example Agent
# =============================================================================


class QuestionAnswerSignature(Signature):
    """Simple Q&A signature."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Agent answer")


@dataclass
class AgentConfig:
    """Agent configuration."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.7


# =============================================================================
# Main Demo
# =============================================================================


async def main():
    """
    Demonstrate distributed tracing with hooks.

    Shows:
    1. Hook registration for tracing
    2. Automatic span creation on agent execution
    3. Trace context propagation
    4. Performance monitoring
    """
    print("=" * 70)
    print("Distributed Tracing with Hooks - Production Example")
    print("=" * 70)

    # Step 1: Create tracing hook
    print("\n1️⃣  Creating distributed tracing hook...")
    tracing_hook = DistributedTracingHook(service_name="demo-agent")

    # Step 2: Register hook with manager
    print("2️⃣  Registering hooks for PRE/POST_AGENT_LOOP...")
    hook_manager = HookManager()
    hook_manager.register(
        HookEvent.PRE_AGENT_LOOP, tracing_hook.start_agent_span, HookPriority.HIGH
    )
    hook_manager.register(
        HookEvent.POST_AGENT_LOOP, tracing_hook.end_agent_span, HookPriority.HIGH
    )

    print("   ✅ Registered 2 tracing hooks")

    # Step 3: Create agent with hook manager
    print("\n3️⃣  Creating agent with tracing enabled...")
    agent = BaseAgent(
        config=AgentConfig(),
        signature=QuestionAnswerSignature(),
        hook_manager=hook_manager,
    )

    # Step 4: Run agent (hooks will automatically trace)
    print("\n4️⃣  Running agent (tracing happens automatically)...\n")
    result = agent.run(question="What is distributed tracing?")

    print(f"\n   📊 Agent result: {result}")

    # Step 5: Run multiple agents to show trace propagation
    print("\n5️⃣  Running multiple agents to demonstrate trace propagation...\n")

    questions = [
        "What is a span?",
        "What is a trace context?",
        "Why use distributed tracing?",
    ]

    for i, question in enumerate(questions, 1):
        print(f"   Question {i}/3:")
        agent.run(question=question)
        await asyncio.sleep(0.1)  # Small delay to show sequential traces

    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("=" * 70)
    print("\n💡 Key Takeaways:")
    print("   1. Hooks enable zero-code-change tracing integration")
    print("   2. Trace context automatically propagates across agents")
    print("   3. Performance metrics (duration) collected automatically")
    print("   4. Production-ready: swap to OpenTelemetry for real tracing")
    print("\n📚 Next Steps:")
    print("   - Install OpenTelemetry SDK: pip install opentelemetry-api")
    print("   - Configure Jaeger/Zipkin backend")
    print("   - Add custom span attributes (user_id, session_id, etc.)")
    print("   - Export to your monitoring platform")


if __name__ == "__main__":
    asyncio.run(main())
