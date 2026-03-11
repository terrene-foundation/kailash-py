"""
Basic Q&A Agent - Your First Kaizen Agent

This example shows:
- How to create a configuration dataclass
- How to define a signature for inputs/outputs
- How to extend BaseAgent
- How to run the agent and extract results

Prerequisites:
- OPENAI_API_KEY in .env file
- pip install kailash-kaizen python-dotenv
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Step 1: Load environment variables (ALWAYS FIRST!)
load_dotenv()

# Step 2: Import Kaizen components
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


# Step 3: Define the signature (input/output contract)
class QASignature(Signature):
    """
    Signature defines what data flows in and out of the agent.

    Think of this as the agent's API contract:
    - InputField: What the user provides
    - OutputField: What the agent returns
    """

    # Input: User's question
    question: str = InputField(description="The question to answer")

    # Outputs: Agent's response
    answer: str = OutputField(description="The answer to the question")
    confidence: float = OutputField(description="Confidence score between 0.0 and 1.0")


# Step 4: Define configuration (LLM settings)
@dataclass
class QAConfig:
    """
    Configuration for the Q&A agent.

    BaseAgent automatically extracts these fields:
    - llm_provider: Which LLM service to use
    - model: Which model to use
    - temperature: Randomness (0.0 = deterministic, 1.0 = creative)
    - max_tokens: Maximum response length
    """

    llm_provider: str = "openai"  # Options: openai, anthropic, ollama
    model: str = "gpt-3.5-turbo"  # Cheaper model for simple tasks
    temperature: float = 0.7  # Balanced creativity
    max_tokens: int = 500  # Reasonable answer length


# Step 5: Create the agent class
class SimpleQAAgent(BaseAgent):
    """
    A simple question-answering agent.

    Extends BaseAgent to inherit:
    - Workflow execution engine
    - LLM provider integration
    - Signature validation
    - Result extraction helpers
    """

    def __init__(self, config: QAConfig):
        """
        Initialize the agent.

        Args:
            config: QAConfig instance with LLM settings

        Note: BaseAgent automatically converts QAConfig to BaseAgentConfig
        """
        super().__init__(
            config=config,  # Domain-specific config
            signature=QASignature(),  # Input/output contract
        )

    def ask(self, question: str) -> dict:
        """
        Ask the agent a question.

        Args:
            question: The question to answer

        Returns:
            dict with keys: question, answer, confidence

        Example:
            >>> agent = SimpleQAAgent(QAConfig())
            >>> result = agent.ask("What is quantum computing?")
            >>> print(result["answer"])
        """
        # Run the agent's underlying workflow
        # BaseAgent.run() executes the workflow and returns results
        result = self.run(question=question)

        # Optional: Extract fields with defaults (UX improvement)
        # This handles cases where LLM doesn't return expected fields
        answer = self.extract_str(result, "answer", default="No answer generated")
        confidence = self.extract_float(result, "confidence", default=0.5)

        return {
            "question": question,
            "answer": answer,
            "confidence": confidence,
            "raw_result": result,  # Full result for debugging
        }


# Step 6: Usage example
def main():
    """
    Main function demonstrating agent usage.
    """
    print("=" * 80)
    print("KAIZEN BASIC Q&A AGENT - Example 1")
    print("=" * 80)
    print()

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found in environment variables")
        print("Please create a .env file with your API key")
        return

    # Create configuration
    config = QAConfig(llm_provider="openai", model="gpt-3.5-turbo", temperature=0.7)

    # Initialize agent
    print("Initializing Q&A agent...")
    agent = SimpleQAAgent(config)
    print(f"✓ Agent initialized with {config.model}")
    print()

    # Ask questions
    questions = [
        "What is the capital of France?",
        "Explain machine learning in one sentence.",
        "What is 2 + 2?",
    ]

    for i, question in enumerate(questions, 1):
        print(f"Question {i}: {question}")

        # Execute agent
        result = agent.ask(question)

        # Display results
        print(f"Answer: {result['answer']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print()

    print("=" * 80)
    print("✓ All questions answered successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
