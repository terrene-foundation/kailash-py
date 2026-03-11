"""
Production Multi-Cycle Autonomous Research Agent

This example demonstrates TRUE autonomous execution with multi-cycle reasoning:
- Agent decides what to do each cycle (LLM-driven)
- Tools are executed based on agent decisions
- Results feed back to agent for next cycle
- Continues until task is complete (autonomous convergence)

Use Case: Research a topic and create a comprehensive report
- Cycle 1: Plan research strategy
- Cycle 2: Search for information
- Cycle 3: Extract relevant content
- Cycle 4: Analyze findings
- Cycle 5: Create summary
- Cycle 6: Write report
- Cycle N: Finish when complete

This is the Kaizen autonomous loop in action - just like Claude Code!

Usage:
    OPENAI_API_KEY=your-key python examples/workflows/05_autonomous_research_agent.py
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kaizen.agents.specialized.react import ReActAgent


@dataclass
class ResearchConfig:
    """Configuration for autonomous research agent."""

    llm_provider: str = "openai"
    model: str = "gpt-5-nano-2025-08-07"
    temperature: float = 1.0  # gpt-5-nano only supports temperature=1
    max_cycles: int = 15
    confidence_threshold: float = 0.85
    output_dir: str = "/tmp/kaizen_research"


class AutonomousResearchAgent:
    """
    Production autonomous research agent.

    Demonstrates multi-cycle autonomous execution where the agent:
    1. Reasons about what to do (Think)
    2. Takes action using tools (Act)
    3. Observes results (Observe)
    4. Repeats until task complete (Converge)
    """

    def __init__(self, config: ResearchConfig):
        self.config = config

        # Setup tools

        # Create autonomous ReAct agent with tool registry
        self.agent = ReActAgent(
            llm_provider=config.llm_provider,
            model=config.model,
            temperature=config.temperature,
            max_cycles=config.max_cycles,
            confidence_threshold=config.confidence_threshold,
        )

        # Populate available_tools so LLM knows what tools it can use
        self.agent.available_tools = [
            {
                "name": tool_name,
                "description": self.registry.get(tool_name).description,
                "danger_level": self.registry.get(tool_name).danger_level.value,
            }
            for tool_name in self.registry.get_tool_names()
        ]

        # Setup output directory
        os.makedirs(config.output_dir, exist_ok=True)

    def print_banner(self):
        """Print agent banner."""
        print("\n" + "=" * 80)
        print("🤖 AUTONOMOUS RESEARCH AGENT")
        print("=" * 80)
        print("\nThis agent will autonomously:")
        print("  1. Plan research strategy")
        print("  2. Search for information")
        print("  3. Extract relevant content")
        print("  4. Analyze findings")
        print("  5. Create comprehensive report")
        print("  6. Save results to file")
        print("\nThe agent decides what to do each cycle - just like Claude Code!")
        print("=" * 80)

    def print_available_tools(self):
        """Print available tools for transparency."""
        print(f"\n🔧 Available Tools: {self.registry.count()} tools")

        # Group by category
        from collections import defaultdict

        by_category = defaultdict(list)
        for tool_name in self.registry.get_tool_names():
            tool = self.registry.get(tool_name)
            by_category[tool.category.value].append(tool_name)

        for category, tools in sorted(by_category.items()):
            print(f"\n  {category.upper()}:")
            for tool_name in sorted(tools):
                tool = self.registry.get(tool_name)
                print(
                    f"    - {tool_name:20s} [{tool.danger_level.value:8s}] {tool.description}"
                )

    async def research(self, topic: str) -> dict:
        """
        Execute autonomous research on a topic.

        The agent will autonomously:
        - Decide what information to search for
        - Execute tools to gather data
        - Analyze and synthesize findings
        - Create comprehensive report
        - Decide when task is complete

        Args:
            topic: Research topic

        Returns:
            Dictionary with research results
        """
        print(f"\n📋 Research Topic: {topic}\n")

        # Build research task prompt
        task = f"""
Research the following topic and create a comprehensive report:

TOPIC: {topic}

Your task:
1. Plan your research strategy
2. Gather information from multiple sources
3. Extract key insights and findings
4. Synthesize information into coherent analysis
5. Create well-structured report with:
   - Executive summary
   - Key findings (3-5 points)
   - Detailed analysis
   - Recommendations
6. Save report to {self.config.output_dir}/research_report.md

Use available tools to:
- Search and fetch information
- Read and analyze content
- Write the final report

Take your time and be thorough. Use multiple cycles to gather comprehensive information.
When you're confident the research is complete and report is written, finish.
"""

        # Execute autonomously!
        print("🚀 Starting autonomous research execution...\n")
        result = self.agent.solve_task(task, context="")

        return result

    def print_results(self, result: dict):
        """Print research results."""
        print("\n" + "=" * 80)
        print("✅ RESEARCH COMPLETE")
        print("=" * 80)

        if "thought" in result:
            print("\n💭 Final Thought:")
            print(f"   {result['thought']}")

        if "action" in result:
            print(f"\n🎯 Final Action: {result['action']}")

        if "action_input" in result and result.get("action") == "finish":
            action_input = result["action_input"]
            if isinstance(action_input, dict) and "answer" in action_input:
                print("\n📊 Research Summary:")
                print(f"   {action_input['answer']}")

        cycles_used = result.get("cycles_used", 0)
        total_cycles = result.get("total_cycles", 0)
        confidence = result.get("confidence", 0)

        print("\n📈 Execution Metrics:")
        print(f"   Cycles Used: {cycles_used}/{total_cycles}")
        print(f"   Confidence: {confidence:.2f}")

        if cycles_used >= total_cycles:
            print("   ⚠️  Reached max cycles - research may be incomplete")
        elif confidence >= self.config.confidence_threshold:
            print("   ✅ High confidence - research is thorough")

        # Check if report was created
        report_path = Path(self.config.output_dir) / "research_report.md"
        if report_path.exists():
            print(f"\n📄 Report saved to: {report_path}")
            print(f"   File size: {report_path.stat().st_size} bytes")
        else:
            print(f"\n⚠️  Report not found at: {report_path}")
            print("   Agent may have used different filename")

        print("\n" + "=" * 80 + "\n")


async def main():
    """Run autonomous research agent demo."""

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable is required")
        print("\nUsage:")
        print(
            "  OPENAI_API_KEY=your-key python examples/workflows/05_autonomous_research_agent.py"
        )
        return

    # Create agent
    config = ResearchConfig(
        llm_provider="openai",
        model="gpt-5-nano-2025-08-07",
        temperature=1.0,  # gpt-5-nano only supports temperature=1
        max_cycles=15,
        confidence_threshold=0.85,
        output_dir="/tmp/kaizen_research",
    )

    agent = AutonomousResearchAgent(config)

    # Print setup info
    agent.print_banner()
    agent.print_available_tools()

    # Research topic (realistic use case)
    topic = """
Python Async/Await Best Practices for Production Applications

Focus on:
- Common pitfalls and how to avoid them
- Performance optimization patterns
- Error handling strategies
- Testing async code
- Production deployment considerations
"""

    # Execute autonomous research
    result = await agent.research(topic.strip())

    # Print results
    agent.print_results(result)

    # Show sample of report if it exists
    report_path = Path(config.output_dir) / "research_report.md"
    if report_path.exists():
        print("📖 Report Preview (first 500 characters):")
        print("-" * 80)
        content = report_path.read_text()
        print(content[:500])
        if len(content) > 500:
            print(f"\n... ({len(content) - 500} more characters)")
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())
