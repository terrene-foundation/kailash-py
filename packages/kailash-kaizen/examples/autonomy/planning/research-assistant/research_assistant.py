"""
Research Assistant - Automated research agent with PlanningAgent pattern.

This example demonstrates:
1. Multi-step research plan generation
2. Plan validation before execution
3. Web search with HTTP tools
4. Memory persistence (hot/warm tiers)
5. Interrupt handling for long tasks
6. Hooks integration for audit trail

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+

Usage:
    python research_assistant.py "quantum computing applications"

    The agent will:
    - Generate research plan with 5-10 steps
    - Validate plan feasibility
    - Execute research using web search
    - Generate comprehensive report
    - Track progress and cost ($0.00 with Ollama)
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List

from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookManager, HookResult
from kaizen.memory.tiers import HotMemoryTier


class ResearchAuditHook:
    """Custom hook for research audit trail."""

    def __init__(self, audit_log_path: Path):
        self.audit_log_path = audit_log_path
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    async def pre_agent_loop(self, context: HookContext) -> HookResult:
        """Log research task start."""
        import json
        from datetime import datetime

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "research_start",
            "agent_id": context.agent_id,
            "trace_id": context.trace_id,
            "task": context.data.get("task", ""),
        }

        with open(self.audit_log_path, "a") as f:
            json.dump(entry, f)
            f.write("\n")

        print(f"📝 Audit: Research started - {context.data.get('task', '')[:50]}...")
        return HookResult(success=True)

    async def post_agent_loop(self, context: HookContext) -> HookResult:
        """Log research completion."""
        import json
        from datetime import datetime

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "research_complete",
            "agent_id": context.agent_id,
            "trace_id": context.trace_id,
            "success": True,
        }

        with open(self.audit_log_path, "a") as f:
            json.dump(entry, f)
            f.write("\n")

        print("✅ Audit: Research completed successfully")
        return HookResult(success=True)


class ResearchAssistant:
    """Research assistant with planning, memory, and audit trail."""

    def __init__(
        self,
        config: PlanningConfig,
        control_protocol: ControlProtocol = None,
        enable_audit: bool = True,
    ):
        """
        Initialize research assistant.

        Args:
            config: Planning configuration
            control_protocol: Optional control protocol for progress reporting
            enable_audit: Enable audit trail logging
        """
        self.config = config
        self.control_protocol = control_protocol

        # Setup hooks for audit trail
        self.hook_manager = None
        if enable_audit:
            self.hook_manager = HookManager()
            audit_hook = ResearchAuditHook(Path("./research_audit.jsonl"))
            self.hook_manager.register(
                HookEvent.PRE_AGENT_LOOP, audit_hook.pre_agent_loop
            )
            self.hook_manager.register(
                HookEvent.POST_AGENT_LOOP, audit_hook.post_agent_loop
            )

        # Setup hot memory tier for caching
        self.memory = HotMemoryTier(max_size=100, eviction_policy="lru")

        # Create planning agent
        self.agent = PlanningAgent(
            llm_provider=config.llm_provider,
            model=config.model,
            temperature=config.temperature,
            max_plan_steps=config.max_plan_steps,
            validation_mode=config.validation_mode,
            enable_replanning=config.enable_replanning,
        )

        print("\n" + "=" * 60)
        print("🤖 RESEARCH ASSISTANT INITIALIZED")
        print("=" * 60)
        print(f"🔧 LLM: {config.llm_provider}/{config.model}")
        print(f"📊 Max Plan Steps: {config.max_plan_steps}")
        print(f"✅ Validation Mode: {config.validation_mode}")
        print(f"🔄 Replanning: {config.enable_replanning}")
        print(f"📝 Audit Trail: {enable_audit}")
        print("=" * 60 + "\n")

    async def research(self, topic: str, context: Dict = None) -> Dict:
        """
        Execute research on topic with planning pattern.

        Args:
            topic: Research topic/question
            context: Optional research context (sources, constraints)

        Returns:
            Dict with plan, validation, execution results, and final report
        """
        print(f"\n🔍 Starting research on: {topic}\n")

        # Check memory cache
        cache_key = f"research_{hash(topic)}"
        cached = await self.memory.get(cache_key)
        if cached:
            print("💾 Using cached research result\n")
            return cached

        # Report progress
        if self.control_protocol:
            await self.control_protocol.report_progress(
                message="Generating research plan", percentage=10
            )

        # Build research context
        research_context = context or {}
        research_context["topic"] = topic
        research_context["max_sources"] = research_context.get("max_sources", 5)
        research_context["report_length"] = research_context.get(
            "report_length", "2000 words"
        )

        try:
            # Execute planning agent (plan → validate → execute)
            result = self.agent.run(
                task=f"Research and report on: {topic}", context=research_context
            )

            # Display plan
            print("\n" + "=" * 60)
            print("📋 RESEARCH PLAN")
            print("=" * 60)
            if isinstance(result.get("plan"), list):
                for i, step in enumerate(result["plan"], 1):
                    if isinstance(step, dict):
                        print(
                            f"{i}. {step.get('description', step.get('step', str(step)))}"
                        )
                    else:
                        print(f"{i}. {step}")
            else:
                print(result.get("plan", "No plan generated"))
            print("=" * 60 + "\n")

            # Display validation
            validation = result.get("validation_result", {})
            print("=" * 60)
            print("✅ PLAN VALIDATION")
            print("=" * 60)
            print(f"Status: {validation.get('status', 'unknown')}")
            if validation.get("issues"):
                print("Issues found:")
                for issue in validation["issues"]:
                    print(f"  - {issue}")
            else:
                print("✅ Plan is feasible and complete")
            print("=" * 60 + "\n")

            # Report progress
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message="Executing research plan", percentage=50
                )

            # Display execution results
            print("=" * 60)
            print("🔬 EXECUTION RESULTS")
            print("=" * 60)
            execution_results = result.get("execution_results", [])
            if isinstance(execution_results, list):
                for i, exec_result in enumerate(execution_results, 1):
                    if isinstance(exec_result, dict):
                        print(f"\nStep {i}: {exec_result.get('status', 'completed')}")
                        if exec_result.get("result"):
                            result_text = str(exec_result["result"])
                            print(
                                f"  {result_text[:100]}..."
                                if len(result_text) > 100
                                else f"  {result_text}"
                            )
                    else:
                        print(f"\nStep {i}: {exec_result}")
            else:
                print(execution_results)
            print("=" * 60 + "\n")

            # Display final report
            print("=" * 60)
            print("📊 RESEARCH REPORT")
            print("=" * 60)
            final_result = result.get("final_result", "No report generated")
            print(final_result)
            print("=" * 60 + "\n")

            # Report progress
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message="Research complete", percentage=100
                )

            # Cache result
            await self.memory.put(cache_key, result, ttl=3600)  # 1 hour cache

            return result

        except Exception as e:
            print(f"\n❌ Error during research: {e}\n")
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message=f"Research failed: {e}", percentage=0
                )
            raise


async def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python research_assistant.py 'research topic'")
        print("\nExample:")
        print("  python research_assistant.py 'quantum computing applications'")
        sys.exit(1)

    topic = sys.argv[1]

    # Optional: Parse additional context
    context = {}
    if len(sys.argv) >= 3:
        # Parse key=value pairs: max_sources=5 report_length="3000 words"
        for arg in sys.argv[2:]:
            if "=" in arg:
                key, value = arg.split("=", 1)
                # Try to parse as int, otherwise string
                try:
                    context[key] = int(value)
                except ValueError:
                    context[key] = value.strip('"')

    # Create control protocol for progress reporting
    transport = MemoryTransport()
    await transport.connect()
    control_protocol = ControlProtocol(transport)

    # Create research assistant with Ollama (FREE)
    config = PlanningConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.3,  # Low temperature for factual research
        max_plan_steps=10,
        validation_mode="strict",
        enable_replanning=True,
    )

    assistant = ResearchAssistant(
        config=config,
        control_protocol=control_protocol,
        enable_audit=True,
    )

    try:
        # Execute research
        result = await assistant.research(topic, context=context)

        # Show statistics
        print("\n" + "=" * 60)
        print("📈 RESEARCH STATISTICS")
        print("=" * 60)
        print(f"Plan Steps: {len(result.get('plan', []))}")
        print(
            f"Validation: {result.get('validation_result', {}).get('status', 'unknown')}"
        )
        print(f"Execution Steps: {len(result.get('execution_results', []))}")
        print("💰 Cost: $0.00 (using Ollama local inference)")
        print("=" * 60 + "\n")

    except KeyboardInterrupt:
        print("\n⚠️  Research interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during research: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
