"""
Scenario 1: Beginner Developer - Simple Q&A Bot
================================================

User Profile:
- Just learning AI agents
- Wants to build a simple chatbot
- No prior experience with AI frameworks

Use Case:
- Personal knowledge assistant
- Answer general knowledge questions
- Learn the basics of Kaizen

Developer Experience Goals:
- Minimal code (< 20 lines)
- Zero configuration complexity
- Immediate results
- Clear error messages
"""

from dotenv import load_dotenv
from kaizen_agents.agents import SimpleQAAgent
from kaizen_agents.agents.specialized.simple_qa import SimpleQAConfig

# Load environment variables (API keys)
load_dotenv()


def main():
    """Simple Q&A bot - beginner friendly."""

    # Step 1: Create configuration (using Ollama - free, local)
    config = SimpleQAConfig(
        llm_provider="ollama",  # Free local inference
        model="llama2",  # Fast, good quality
        temperature=0.7,
    )

    # Step 2: Create agent
    print("🤖 Creating Q&A Agent...")
    agent = SimpleQAAgent(config=config)

    # Step 3: Ask questions
    questions = [
        "What is Python?",
        "Explain machine learning in simple terms",
        "What is the difference between AI and ML?",
    ]

    print("\n" + "=" * 60)
    print("Simple Q&A Bot - Beginner Example")
    print("=" * 60 + "\n")

    for question in questions:
        print(f"❓ Question: {question}")

        try:
            # Get answer
            result = agent.ask(question)

            # Display result
            print(f"💡 Answer: {result['answer']}")
            print(f"📊 Confidence: {result.get('confidence', 'N/A')}")
            print(f"🧠 Reasoning: {result.get('reasoning', 'N/A')}\n")

        except Exception as e:
            print(f"❌ Error: {e}\n")

    print("=" * 60)
    print("✅ Demo complete!")


if __name__ == "__main__":
    main()
