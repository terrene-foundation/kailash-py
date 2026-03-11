#!/usr/bin/env python3
"""
BaseAgent with Real Ollama LLM + Control Protocol

Demonstrates BaseAgent using REAL Ollama inference combined with Control Protocol.

This example shows:
1. BaseAgent makes real LLM inferences (Ollama)
2. During inference, agent can ask user questions
3. Agent can request user approval before actions
4. Complete workflow with real AI decision-making

Usage:
    # Start Ollama first
    ollama serve

    # Run example
    python examples/autonomy/baseagent_with_ollama.py

Prerequisites:
    - Ollama installed and running
    - llama3.1:8b-instruct-q8_0 model downloaded (ollama pull llama3.1:8b-instruct-q8_0)

See Also:
    - baseagent_interactive.py - Mock LLM version
    - docs/reference/multi-modal-api-reference.md - Ollama configuration
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import anyio
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# ============================================
# Agent Configuration - REAL OLLAMA
# ============================================


@dataclass
class ResearchAgentConfig:
    """Config using real Ollama LLM."""

    llm_provider: str = "ollama"
    model: str = "llama3.1:8b-instruct-q8_0"  # Fast, lightweight model
    temperature: float = 0.7


class ResearchSignature(Signature):
    """Signature for research tasks."""

    topic: str = InputField(description="Research topic")
    focus_area: str = InputField(description="Specific area to focus on", default="")
    approved: str = InputField(description="User approval status", default="")
    research_summary: str = OutputField(description="Research findings")


# ============================================
# Research Agent with Interactive Capabilities
# ============================================


class InteractiveResearchAgent(BaseAgent):
    """Research agent that consults user during execution."""

    def __init__(self, config: ResearchAgentConfig, control_protocol: ControlProtocol):
        super().__init__(
            config=config,
            signature=ResearchSignature(),
            control_protocol=control_protocol,
        )

    async def research(self, topic: str) -> dict:
        """
        Conduct research with user interaction.

        Steps:
        1. Ask user for specific focus area
        2. Request approval before conducting research
        3. Run LLM inference (real Ollama)
        4. Return results
        """
        print(f"\n🔍 Starting research on: {topic}")
        print("=" * 70)

        try:
            # Step 1: Ask user for focus area
            print("\n📋 Step 1: Asking user for focus area...")
            focus_area = await self.ask_user_question(
                question=f"What aspect of '{topic}' should I focus on?",
                options=["overview", "technical details", "practical applications"],
                timeout=30.0,
            )
            print(f"✅ User selected: {focus_area}")

            # Step 2: Request approval
            print("\n📋 Step 2: Requesting approval...")
            approved = await self.request_approval(
                action=f"Conduct research on '{topic}' focusing on '{focus_area}'",
                details={
                    "topic": topic,
                    "focus_area": focus_area,
                    "will_use_llm": True,
                    "estimated_tokens": 500,
                },
                timeout=30.0,
            )

            if not approved:
                print("❌ Research cancelled by user")
                return {"status": "cancelled", "reason": "user denied approval"}

            print("✅ Research approved by user")

            # Step 3: Run REAL LLM inference
            print(f"\n📋 Step 3: Running Ollama inference ({self.config.model})...")
            print("⏳ This will make a real LLM call...")

            result = self.run(topic=topic, focus_area=focus_area, approved="yes")

            print("\n✅ Research complete!")

            # Extract result
            summary = self.extract_str(
                result, "research_summary", default="No summary generated"
            )

            print("\n" + "=" * 70)
            print("📊 Research Summary:")
            print("=" * 70)
            print(summary)
            print("=" * 70)

            return result

        except TimeoutError as e:
            print(f"\n⏱️  Timeout: {e}")
            return {"status": "timeout", "error": str(e)}
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback

            traceback.print_exc()
            return {"status": "error", "error": str(e)}


# ============================================
# Main Workflow
# ============================================


async def main():
    """
    Demonstrate BaseAgent with real Ollama + Control Protocol.

    This example shows:
    1. Real LLM inference (not mocked)
    2. Interactive user questions during workflow
    3. Approval requests before actions
    4. Complete AI-powered decision making
    """
    print("\n" + "=" * 70)
    print("BaseAgent with Real Ollama LLM + Control Protocol")
    print("=" * 70)
    print()
    print("This example demonstrates:")
    print("1. 🤖 Real Ollama LLM inference (llama3.1:8b-instruct-q8_0)")
    print("2. 💬 Interactive questions during execution")
    print("3. ✅ Approval requests before actions")
    print("4. 🧠 AI-powered decision making")
    print()
    print("Note: You'll interact via terminal (stdin/stdout)")
    print("=" * 70)
    print()

    # Setup Control Protocol with CLI transport
    transport = CLITransport()
    await transport.connect()

    protocol = ControlProtocol(transport)

    # Create research agent with REAL Ollama
    config = ResearchAgentConfig()
    agent = InteractiveResearchAgent(config=config, control_protocol=protocol)

    print(f"✅ Agent created with Ollama ({config.model})")
    print(f"📋 Agent ID: {agent.agent_id}")
    print()

    async with anyio.create_task_group() as tg:
        # Start protocol
        await protocol.start(tg)

        # Run research workflow
        topic = "Artificial Intelligence in Healthcare"

        result = await agent.research(topic)

        print()
        print("🎉 Workflow complete!")
        print()
        print("Result summary:")
        print(f"  Status: {result.get('status', 'success')}")
        print(f"  Keys: {list(result.keys())}")

        # Stop protocol
        await protocol.stop()

    # Close transport
    await transport.close()

    print()
    print("✅ All done!")


if __name__ == "__main__":
    print()
    print("⚠️  PREREQUISITES:")
    print("   1. Ollama must be running: ollama serve")
    print("   2. Model must be available: ollama pull llama3.1:8b-instruct-q8_0")
    print()
    input("Press Enter to continue...")
    print()

    # Run with async
    asyncio.run(main())
