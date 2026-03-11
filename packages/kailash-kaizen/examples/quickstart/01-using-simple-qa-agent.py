"""
Quickstart: Using SimpleQAAgent (2 minutes)

This example demonstrates how to use Kaizen's pre-built SimpleQAAgent.
No configuration needed - just import and use!

Learning Path:
1. This example - USE existing specialized agents ← START HERE
2. Creating custom agents - CREATE your own from BaseAgent
"""

from kaizen.agents import SimpleQAAgent


def main():
    print("=== Kaizen SimpleQAAgent Quickstart ===\n")

    # ===================================================================
    # OPTION 1: Zero-Config (Easiest - Uses sensible defaults)
    # ===================================================================
    print("Option 1: Zero-config usage")
    print("-" * 50)

    agent = SimpleQAAgent()  # That's it! Defaults to OpenAI GPT-4
    result = agent.ask("What is artificial intelligence?")

    print("Question: What is artificial intelligence?")
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Reasoning: {result['reasoning']}\n")

    # ===================================================================
    # OPTION 2: Progressive Configuration (Override specific params)
    # ===================================================================
    print("\nOption 2: Progressive configuration")
    print("-" * 50)

    agent = SimpleQAAgent(
        model="gpt-3.5-turbo",  # Override just the model
        temperature=0.7,  # And temperature
        # All other params use defaults
    )

    result = agent.ask("What are the main branches of AI?")
    print(f"Answer: {result['answer']}\n")

    # ===================================================================
    # OPTION 3: With Memory (For conversational Q&A)
    # ===================================================================
    print("\nOption 3: With memory for context")
    print("-" * 50)

    agent = SimpleQAAgent(max_turns=10)  # Enable 10-turn memory

    # First question
    result1 = agent.ask("What is machine learning?", session_id="conversation_1")
    print("Q1: What is machine learning?")
    print(f"A1: {result1['answer']}\n")

    # Follow-up (agent remembers previous context)
    result2 = agent.ask(
        "Can you give an example?",
        session_id="conversation_1",  # Same session = memory enabled
    )
    print("Q2: Can you give an example?")
    print(f"A2: {result2['answer']}\n")

    # ===================================================================
    # OPTION 4: One-liner convenience function
    # ===================================================================
    print("\nOption 4: One-liner for quick use")
    print("-" * 50)

    from kaizen.agents.specialized.simple_qa import ask

    answer = ask("What is deep learning?")
    print(f"Answer: {answer}\n")

    # ===================================================================
    # OPTION 5: Full configuration (All parameters)
    # ===================================================================
    print("\nOption 5: Full configuration")
    print("-" * 50)

    agent = SimpleQAAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.1,
        max_tokens=300,
        timeout=30,
        retry_attempts=3,
        min_confidence_threshold=0.5,
        max_turns=None,  # No memory
        provider_config={"api_key": "your-key-here"},
    )

    result = agent.ask("What is natural language processing?")
    print(f"Answer: {result['answer']}\n")

    print("\n✅ Quickstart Complete!")
    print("\nNext steps:")
    print("1. Try other specialized agents: ReActAgent, RAGAgent, etc.")
    print("2. Learn to create custom agents: examples/guides/creating-custom-agents/")


if __name__ == "__main__":
    main()
