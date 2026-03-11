"""
Kaizen-Nexus Multi-Channel Deployment Example

Deploy a Kaizen AI agent across API, CLI, and MCP simultaneously using Nexus platform.

This example shows:
1. Creating a data analysis agent
2. Deploying it across all channels at once
3. Accessing the same functionality via API, CLI, and MCP

Usage:
    python workflow.py

    Then access via:
    - API: curl -X POST http://localhost:8000/api/workflows/analyze/execute ...
    - CLI: nexus run analyze --data "[1,2,3,4,5]"
    - MCP: Claude Code can discover and use the "analyze" tool
"""

from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent

# Check Nexus availability
from kaizen.integrations.nexus import NEXUS_AVAILABLE, deploy_multi_channel
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    print("Nexus not available. Install with: pip install kailash-nexus")
    exit(1)

from nexus import Nexus


@dataclass
class AnalysisConfig:
    """Configuration for data analysis agent."""

    llm_provider: str = "mock"  # Use mock for example
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.3


class AnalysisSignature(Signature):
    """Data analysis agent signature."""

    data: str = InputField(description="Data to analyze (JSON format)")
    insights: str = OutputField(description="Analysis insights")
    statistics: str = OutputField(description="Statistical summary")


class AnalysisAgent(BaseAgent):
    """Simple data analysis agent."""

    def __init__(self, config: AnalysisConfig):
        super().__init__(config=config, signature=AnalysisSignature())

    def analyze(self, data: str) -> dict:
        """Analyze data and provide insights."""
        return self.run(data=data)


def main():
    print("=== Kaizen-Nexus Multi-Channel Deployment Example ===\n")

    # Create Nexus platform with both ports
    print("1. Initializing Nexus platform...")
    app = Nexus(auto_discovery=False, api_port=8000, mcp_port=3001)

    # Create data analysis agent
    print("2. Creating data analysis agent...")
    config = AnalysisConfig()
    agent = AnalysisAgent(config)

    # Deploy across all channels
    print("3. Deploying agent across all channels...")
    channels = deploy_multi_channel(agent=agent, nexus_app=app, name="analyze")

    print("✅ Agent deployed successfully across all channels!")
    print("\n4. Channel Access Information:")
    print(f"   API Endpoint: {channels['api']}")
    print(f"   CLI Command: {channels['cli']}")
    print(f"   MCP Tool: {channels['mcp']}")

    print("\n5. Usage Examples:")
    print("\n   API:")
    print(f"   curl -X POST http://localhost:8000{channels['api']} \\")
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"data": "[1, 2, 3, 4, 5]"}\'')

    print("\n   CLI:")
    print(f'   {channels["cli"]} --data "[1, 2, 3, 4, 5]"')

    print("\n   MCP (for Claude Code):")
    print(f'   Tool "{channels["mcp"]}" is automatically available')

    # Check health
    health = app.health_check()
    print("\n6. Platform Status:")
    print(f"   Status: {health['status']}")
    print(f"   Workflows: {health['workflows']}")
    print(f"   API Port: {health['api_port']}")

    print("\nMulti-channel deployment complete!")
    print(
        "Same agent, three access methods - choose what works best for your use case."
    )
    print("\nNote: Call app.start() to start all services (blocks until stopped).")


if __name__ == "__main__":
    main()
