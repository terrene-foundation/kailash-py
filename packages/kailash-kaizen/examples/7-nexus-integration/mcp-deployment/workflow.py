"""
Kaizen-Nexus MCP Deployment Example

Deploy a Kaizen AI agent as an MCP tool using Nexus platform.

This example shows:
1. Creating a research agent
2. Deploying it as MCP tool
3. Making it available for AI integrations (Claude Code, etc.)

Usage:
    python workflow.py

    Then the tool becomes available to MCP clients like Claude Code
"""

from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent

# Check Nexus availability
from kaizen.integrations.nexus import NEXUS_AVAILABLE, deploy_as_mcp
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    print("Nexus not available. Install with: pip install kailash-nexus")
    exit(1)

from nexus import Nexus


@dataclass
class ResearchConfig:
    """Configuration for research agent."""

    llm_provider: str = "mock"  # Use mock for example
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.5


class ResearchSignature(Signature):
    """Research agent signature."""

    topic: str = InputField(description="Research topic")
    summary: str = OutputField(description="Research summary")
    key_points: str = OutputField(description="Key findings")


class ResearchAgent(BaseAgent):
    """Simple research agent."""

    def __init__(self, config: ResearchConfig):
        super().__init__(config=config, signature=ResearchSignature())

    def research(self, topic: str) -> dict:
        """Research a topic."""
        return self.run(topic=topic)


def main():
    print("=== Kaizen-Nexus MCP Deployment Example ===\n")

    # Create Nexus platform
    print("1. Initializing Nexus platform...")
    app = Nexus(auto_discovery=False, mcp_port=3001)

    # Create research agent
    print("2. Creating research agent...")
    config = ResearchConfig()
    agent = ResearchAgent(config)

    # Deploy as MCP tool
    print("3. Deploying agent as MCP tool...")
    tool_name = deploy_as_mcp(
        agent=agent,
        nexus_app=app,
        tool_name="research",
        tool_description="Research any topic and provide a summary with key findings",
    )

    print("✅ Agent deployed successfully!")
    print(f"   MCP Tool Name: {tool_name}")
    print("   MCP Server Port: 3001")
    print("\n4. Tool is now available for MCP clients:")
    print("   - Claude Code can discover and use this tool")
    print("   - Other MCP clients can call: research(topic='AI Ethics')")

    # Check health
    health = app.health_check()
    print("\n5. Platform Status:")
    print(f"   Status: {health['status']}")
    print(f"   Workflows: {health['workflows']}")
    print("\nMCP deployment complete! The tool is ready for AI integration.")
    print("Note: Call app.start() to start the MCP server (blocks until stopped).")


if __name__ == "__main__":
    main()
