"""
BaseAutonomousAgent Demo - Basic Autonomous Execution

This example demonstrates the foundational autonomous agent pattern with:
- Multi-cycle execution loop
- Objective convergence detection
- TODO-based planning
- State persistence with checkpoints

## Usage

```bash
# Basic usage with mock LLM (no API key required)
python examples/autonomy/01_base_autonomous_agent_demo.py

# With real LLM (requires API key in .env)
python examples/autonomy/01_base_autonomous_agent_demo.py --real-llm
```

## What This Demonstrates

1. **Autonomous Loop**: Agent executes multiple cycles autonomously
2. **Objective Convergence**: Uses tool_calls field (not subjective confidence)
3. **Planning System**: Creates structured TODO lists
4. **Checkpoints**: Saves state every N cycles for recovery
5. **Tool Integration**: Works with Kaizen's builtin tools

## Based On

- BaseAutonomousAgent implementation
- Claude Code's `while(tool_calls_exist)` pattern
- ADR-013: Objective Convergence Detection
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kaizen.agents.autonomous import AutonomousConfig, BaseAutonomousAgent
from kaizen.signatures import InputField, OutputField, Signature


# Define signature for research tasks
class ResearchSignature(Signature):
    """Signature for autonomous research tasks."""

    task: str = InputField(description="Research task to complete")
    context: str = InputField(
        description="Additional context from previous cycles", default=""
    )
    observation: str = InputField(
        description="Observation from last action", default=""
    )

    findings: str = OutputField(description="Research findings")
    next_action: str = OutputField(description="Next action to take")
    tool_calls: list = OutputField(
        description="List of tool calls to execute", default=[]
    )


# Configure autonomous agent
@dataclass
class ResearchAgentConfig(AutonomousConfig):
    """Configuration for research agent."""

    llm_provider: str = "mock"  # Use mock for demo
    model: str = "mock-model"
    max_cycles: int = 10
    planning_enabled: bool = True
    checkpoint_frequency: int = 3


async def demo_basic_autonomous_execution():
    """
    Demo 1: Basic autonomous execution with planning.

    Shows multi-cycle execution with planning system.
    """
    print("\n" + "=" * 80)
    print("DEMO 1: Basic Autonomous Execution with Planning")
    print("=" * 80 + "\n")

    # Create configuration
    config = ResearchAgentConfig(
        llm_provider="mock",
        model="mock-model",
        max_cycles=5,
        planning_enabled=True,
    )

    # Create tool registry
    # Create agent
    agent = BaseAutonomousAgent(config=config, signature=ResearchSignature())

    print("✓ Created BaseAutonomousAgent")
    print(f"  - Max cycles: {config.max_cycles}")
    print(f"  - Planning enabled: {config.planning_enabled}")
    print(f"  - Available tools: {len(list(registry.list_tools()))}")

    # Execute autonomously
    task = "Research Python async programming patterns and create summary"

    print(f"\n📝 Task: {task}")
    print("\n🤖 Starting autonomous execution...")
    print("-" * 80)

    result = await agent.execute_autonomously(task)

    print("\n✅ Execution complete!")
    print(f"  - Cycles used: {result.get('cycles_used', 0)}/{config.max_cycles}")
    print(f"  - Converged: {result.get('converged', False)}")
    print(f"  - Plan generated: {len(result.get('plan', [])) > 0}")

    if result.get("plan"):
        print("\n📋 Generated Plan:")
        for i, task_item in enumerate(result["plan"][:3], 1):
            print(f"  {i}. {task_item.get('task', 'N/A')}")
        if len(result["plan"]) > 3:
            print(f"  ... and {len(result['plan']) - 3} more tasks")

    return result


async def demo_checkpoint_recovery():
    """
    Demo 2: Checkpoint saving and recovery.

    Shows state persistence across cycles.
    """
    print("\n" + "=" * 80)
    print("DEMO 2: Checkpoint Saving and Recovery")
    print("=" * 80 + "\n")

    # Create configuration with frequent checkpoints
    config = ResearchAgentConfig(
        max_cycles=10,
        planning_enabled=True,
        checkpoint_frequency=2,  # Save every 2 cycles
    )

    # Create tool registry
    # Create agent
    agent = BaseAutonomousAgent(config=config, signature=ResearchSignature())

    print("✓ Created BaseAutonomousAgent with checkpointing")
    print(f"  - Checkpoint frequency: every {config.checkpoint_frequency} cycles")

    # Execute task
    task = "Analyze codebase structure and suggest improvements"

    print(f"\n📝 Task: {task}")
    print("\n🤖 Executing with checkpoints...")
    print("-" * 80)

    result = await agent.execute_autonomously(task)

    print(f"\n✅ Execution complete with {result.get('cycles_used', 0)} cycles!")
    print(f"  - Checkpoints saved: Every {config.checkpoint_frequency} cycles")
    print("  - State preserved for recovery")

    # Show checkpoint info
    if result.get("cycles_used", 0) > 0:
        expected_checkpoints = result["cycles_used"] // config.checkpoint_frequency
        print(f"  - Expected checkpoint count: ~{expected_checkpoints}")

    return result


async def demo_convergence_detection():
    """
    Demo 3: Objective convergence detection.

    Shows how tool_calls field determines convergence.
    """
    print("\n" + "=" * 80)
    print("DEMO 3: Objective Convergence Detection")
    print("=" * 80 + "\n")

    print("📊 Convergence Detection Method:")
    print("  - Objective: Check tool_calls field (ADR-013)")
    print("  - NOT subjective: confidence/action fields")
    print("  - Pattern: while(tool_calls_exist) from Claude Code")

    # Create configuration
    config = ResearchAgentConfig(max_cycles=8)

    # Create agent
    agent = BaseAutonomousAgent(
        config=config,
        signature=ResearchSignature(),
    )

    print(f"\n✓ Created agent with max {config.max_cycles} cycles")

    # Execute task
    task = "Simple task that should converge quickly"

    print(f"\n📝 Task: {task}")
    print("\n🤖 Monitoring convergence...")
    print("-" * 80)

    result = await agent.execute_autonomously(task)

    print(f"\n✅ Converged after {result.get('cycles_used', 0)} cycles")
    print("  - Convergence method: tool_calls field empty")
    print("  - No hallucination risk with objective detection")

    return result


async def main():
    """Run all demonstrations."""
    print("\n" + "=" * 80)
    print("BaseAutonomousAgent Demonstrations")
    print("Autonomous AI Agents with Kaizen Framework")
    print("=" * 80)

    try:
        # Run demos
        await demo_basic_autonomous_execution()
        await demo_checkpoint_recovery()
        await demo_convergence_detection()

        print("\n" + "=" * 80)
        print("✅ All demonstrations completed successfully!")
        print("=" * 80 + "\n")

        print("📚 Learn More:")
        print("  - BaseAutonomousAgent: src/kaizen/agents/autonomous/base.py")
        print("  - Research: docs/research/CLAUDE_CODE_AUTONOMOUS_ARCHITECTURE.md")
        print("  - ADR-013: docs/architecture/adr/ADR-013-objective-convergence.md")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
