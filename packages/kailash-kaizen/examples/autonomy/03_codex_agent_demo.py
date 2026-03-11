"""
CodexAgent Demo - Codex Autonomous PR Generation Pattern

Demonstrates Codex's proven autonomous architecture:
- Container-based execution (isolated environment)
- AGENTS.md configuration for project conventions
- Test-driven iteration (run → parse → fix → repeat)
- Professional PR generation with commit messages
- Logging and evidence system

## Usage

```bash
python examples/autonomy/03_codex_agent_demo.py
```

## Based On

- Codex's production autonomous architecture (OpenAI)
- Research: docs/research/CODEX_AUTONOMOUS_ARCHITECTURE.md
- Agent-model separation for long-running tasks
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kaizen.agents.autonomous import CodexAgent, CodexConfig
from kaizen.signatures import InputField, OutputField, Signature


class PRSignature(Signature):
    """Signature for autonomous PR generation tasks."""

    task: str = InputField(description="PR task (bug fix, feature, refactor)")
    context: str = InputField(description="Repository context", default="")
    observation: str = InputField(description="Test/lint results", default="")

    changes: str = OutputField(description="Code changes made")
    pr_description: str = OutputField(description="PR description")
    tool_calls: list = OutputField(description="Tool calls", default=[])


async def demo_container_execution():
    """Demo 1: Container-based execution model."""
    print("\n" + "=" * 80)
    print("DEMO 1: CodexAgent - Container Execution")
    print("=" * 80 + "\n")

    config = CodexConfig(
        llm_provider="mock",
        model="mock-model",
        container_image="python:3.11",
        enable_internet=False,  # Disabled after startup
        timeout_minutes=30,
    )

    agent = CodexAgent(config=config, signature=PRSignature())

    print("✓ CodexAgent created with container config")
    print(f"  - Container image: {config.container_image}")
    print(f"  - Internet access: {config.enable_internet}")
    print(f"  - Timeout: {config.timeout_minutes} minutes")
    print("  - Isolated filesystem + terminal")

    print("\n✅ Container execution model configured!")
    return agent


async def demo_agents_md_configuration():
    """Demo 2: AGENTS.md configuration loading."""
    print("\n" + "=" * 80)
    print("DEMO 2: AGENTS.md Configuration")
    print("=" * 80 + "\n")

    config = CodexConfig(
        agents_md_path="AGENTS.md",
        test_command="pytest tests/",
        lint_command="ruff check src/",
    )

    agent = CodexAgent(
        config=config,
        signature=PRSignature(),
    )

    print("✓ AGENTS.md configuration loaded")
    print(f"  - Test command: {config.test_command}")
    print(f"  - Lint command: {config.lint_command}")
    print("  - Project conventions from AGENTS.md")

    print("\n✅ Project-specific configuration ready!")
    return agent


async def demo_test_driven_iteration():
    """Demo 3: Test-driven iteration workflow."""
    print("\n" + "=" * 80)
    print("DEMO 3: Test-Driven Iteration")
    print("=" * 80 + "\n")

    config = CodexConfig(test_command="pytest", max_cycles=10)

    agent = CodexAgent(
        config=config,
        signature=PRSignature(),
    )

    print("✓ Test-driven iteration workflow")
    print("  - 1. Run tests")
    print("  - 2. Parse failures")
    print("  - 3. Generate fixes")
    print("  - 4. Repeat until pass")

    task = "Fix authentication bug in login module"
    result = await agent.execute_autonomously(task)

    print("\n✅ Iterative fixes applied!")
    print(f"  - Cycles: {result.get('cycles_used', 0)}")
    return result


async def demo_pr_generation():
    """Demo 4: Professional PR generation."""
    print("\n" + "=" * 80)
    print("DEMO 4: PR Generation")
    print("=" * 80 + "\n")

    config = CodexConfig(timeout_minutes=30, max_cycles=30)

    agent = CodexAgent(
        config=config,
        signature=PRSignature(),
    )

    print("✓ PR generation configured")
    print("  - Professional commit messages")
    print("  - Comprehensive PR descriptions")
    print("  - Citations to action logs")
    print("  - 1-30 minute one-shot workflow")

    task = "Add user authentication with JWT"
    result = await agent.execute_autonomously(task)

    print("\n✅ PR generated!")
    print(f"  - Task: {task}")
    print(f"  - Cycles: {result.get('cycles_used', 0)}")
    if result.get("pr_description"):
        print("  - PR description ready")
    return result


async def demo_logging_system():
    """Demo 5: Logging and evidence system."""
    print("\n" + "=" * 80)
    print("DEMO 5: Logging and Evidence")
    print("=" * 80 + "\n")

    config = CodexConfig(max_cycles=5)

    agent = CodexAgent(
        config=config,
        signature=PRSignature(),
    )

    print("✓ Logging system active")
    print("  - Step-by-step action recording")
    print("  - Timestamp tracking")
    print("  - Command output capture")
    print("  - Complete audit trail")

    task = "Refactor API endpoints"
    result = await agent.execute_autonomously(task)

    print("\n✅ Full execution log available!")
    print("  - All actions recorded")
    print("  - Citations in PR description")
    return result


async def main():
    """Run all demonstrations."""
    print("\n" + "=" * 80)
    print("CodexAgent Demonstrations")
    print("Codex Autonomous Architecture in Kaizen")
    print("=" * 80)

    try:
        await demo_container_execution()
        await demo_agents_md_configuration()
        await demo_test_driven_iteration()
        await demo_pr_generation()
        await demo_logging_system()

        print("\n" + "=" * 80)
        print("✅ All Codex patterns demonstrated!")
        print("=" * 80 + "\n")

        print("📚 Learn More:")
        print("  - CodexAgent: src/kaizen/agents/autonomous/codex.py")
        print("  - Research: docs/research/CODEX_AUTONOMOUS_ARCHITECTURE.md")
        print("  - Tests: tests/unit/agents/autonomous/test_codex.py")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
