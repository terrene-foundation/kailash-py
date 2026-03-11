"""
Kaizen-Nexus API Deployment Example

Deploy a Kaizen AI agent as a REST API endpoint using Nexus platform.

This example shows:
1. Creating a simple Q&A agent
2. Deploying it as REST API
3. Testing the deployed endpoint

Usage:
    python workflow.py

    Then test with:
    curl -X POST http://localhost:8000/api/workflows/qa/execute \
         -H "Content-Type: application/json" \
         -d '{"question": "What is AI?"}'
"""

from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent

# Check Nexus availability
from kaizen.integrations.nexus import NEXUS_AVAILABLE, deploy_as_api
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    print("Nexus not available. Install with: pip install kailash-nexus")
    exit(1)

from nexus import Nexus


@dataclass
class QAConfig:
    """Configuration for Q&A agent."""

    llm_provider: str = "mock"  # Use mock for example
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7


class QASignature(Signature):
    """Q&A agent signature."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer to question")


class QAAgent(BaseAgent):
    """Simple Q&A agent."""

    def __init__(self, config: QAConfig):
        super().__init__(config=config, signature=QASignature())

    def ask(self, question: str) -> dict:
        """Ask a question and get an answer."""
        return self.run(question=question)


def main():
    print("=== Kaizen-Nexus API Deployment Example ===\n")

    # Create Nexus platform
    print("1. Initializing Nexus platform...")
    app = Nexus(auto_discovery=False)

    # Create Q&A agent
    print("2. Creating Q&A agent...")
    config = QAConfig()
    agent = QAAgent(config)

    # Deploy as API
    print("3. Deploying agent as API...")
    endpoint = deploy_as_api(agent=agent, nexus_app=app, endpoint_name="qa")

    print("✅ Agent deployed successfully!")
    print(f"   Endpoint: {endpoint}")
    print("\n4. Testing deployed API...")
    print(f"   curl -X POST http://localhost:8000{endpoint} \\")
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"question": "What is AI?"}\'')

    # Check health
    health = app.health_check()
    print("\n5. Platform Status:")
    print(f"   Status: {health['status']}")
    print(f"   Workflows: {health['workflows']}")
    print("\nAPI deployment complete! The endpoint is ready for use.")
    print("Note: Call app.start() to start the API server (blocks until stopped).")


if __name__ == "__main__":
    main()
