"""
Kaizen-Nexus CLI Deployment Example

Deploy a Kaizen AI agent as a CLI command using Nexus platform.

This example shows:
1. Creating a code generation agent
2. Deploying it as CLI command
3. Using the deployed command

Usage:
    python workflow.py

    Then use with:
    nexus run codegen --task "Create a Python function to calculate fibonacci"
"""

from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent

# Check Nexus availability
from kaizen.integrations.nexus import NEXUS_AVAILABLE, deploy_as_cli
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    print("Nexus not available. Install with: pip install kailash-nexus")
    exit(1)

from nexus import Nexus


@dataclass
class CodeGenConfig:
    """Configuration for code generation agent."""

    llm_provider: str = "mock"  # Use mock for example
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.2


class CodeGenSignature(Signature):
    """Code generation agent signature."""

    task: str = InputField(description="Code generation task")
    code: str = OutputField(description="Generated code")
    explanation: str = OutputField(description="Code explanation")


class CodeGenAgent(BaseAgent):
    """Simple code generation agent."""

    def __init__(self, config: CodeGenConfig):
        super().__init__(config=config, signature=CodeGenSignature())

    def generate(self, task: str) -> dict:
        """Generate code for a task."""
        return self.run(task=task)


def main():
    print("=== Kaizen-Nexus CLI Deployment Example ===\n")

    # Create Nexus platform
    print("1. Initializing Nexus platform...")
    app = Nexus(auto_discovery=False)

    # Create code generation agent
    print("2. Creating code generation agent...")
    config = CodeGenConfig()
    agent = CodeGenAgent(config)

    # Deploy as CLI
    print("3. Deploying agent as CLI...")
    command = deploy_as_cli(agent=agent, nexus_app=app, command_name="codegen")

    print("✅ Agent deployed successfully!")
    print(f"   Command: {command}")
    print("\n4. Using the deployed CLI command:")
    print(f'   {command} --task "Create a Python function to calculate fibonacci"')

    # Check health
    health = app.health_check()
    print("\n5. Platform Status:")
    print(f"   Status: {health['status']}")
    print(f"   Workflows: {health['workflows']}")
    print("\nCLI deployment complete! The command is ready for use.")
    print("Note: Call app.start() to start the Nexus platform (enables CLI execution).")


if __name__ == "__main__":
    main()
