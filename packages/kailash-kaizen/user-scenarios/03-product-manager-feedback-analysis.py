"""
Scenario 3: Product Manager - Customer Feedback Analysis
=========================================================

User Profile:
- Product manager collecting user feedback
- Needs to identify patterns and sentiment
- Wants to track insights over multiple sessions
- Requires structured analysis reports

Use Case:
- Analyze customer feedback/reviews
- Track sentiment trends
- Generate actionable insights
- Maintain context across analysis sessions

Developer Experience Goals:
- Memory persistence across sessions
- Batch processing of feedback
- Sentiment analysis
- Clear, structured insights
"""

from datetime import datetime

from dotenv import load_dotenv
from kaizen_agents.agents import MemoryAgent
from kaizen_agents.agents.specialized.memory_agent import MemoryConfig

# Load environment variables
load_dotenv()

# Sample customer feedback data
CUSTOMER_FEEDBACK = [
    {
        "id": 1,
        "customer": "Alice",
        "feedback": "The new feature is amazing! Love the improved UI. Makes my workflow 10x faster.",
        "date": "2025-01-15",
    },
    {
        "id": 2,
        "customer": "Bob",
        "feedback": "App keeps crashing on mobile. Very frustrating experience. Please fix ASAP.",
        "date": "2025-01-15",
    },
    {
        "id": 3,
        "customer": "Carol",
        "feedback": "Great product but pricing is too high for small teams. Consider a starter plan.",
        "date": "2025-01-16",
    },
    {
        "id": 4,
        "customer": "David",
        "feedback": "Customer support was excellent! Quick response and solved my issue in minutes.",
        "date": "2025-01-16",
    },
    {
        "id": 5,
        "customer": "Eve",
        "feedback": "Missing integration with Slack. This is a deal-breaker for our team.",
        "date": "2025-01-17",
    },
]


def main():
    """Product manager workflow - feedback analysis with memory."""

    print("=" * 70)
    print("Product Manager - Customer Feedback Analysis with Memory")
    print("=" * 70 + "\n")

    # Step 1: Create memory-enabled agent
    print("🧠 Creating Memory-Enabled Analysis Agent...")
    session_id = f"feedback_analysis_{datetime.now().strftime('%Y%m%d')}"

    config = MemoryConfig(
        llm_provider="ollama",
        model="llama2",
        temperature=0.3,  # Lower for more consistent analysis
        session_id=session_id,  # Track patterns across interactions
        max_tokens=500,
    )
    agent = MemoryAgent(config=config)
    print(f"✅ Session ID: {session_id}\n")

    # Step 2: Process feedback in batches
    print("📊 Processing Customer Feedback...")
    print("-" * 70)

    results = []

    for feedback_item in CUSTOMER_FEEDBACK:
        customer = feedback_item["customer"]
        feedback = feedback_item["feedback"]
        date = feedback_item["date"]

        print(f"\n📝 [{date}] Feedback from {customer}:")
        print(f'   "{feedback}"')

        # Analyze with context from previous feedback
        analysis_prompt = f"""
        Analyze this customer feedback:
        Customer: {customer}
        Date: {date}
        Feedback: "{feedback}"

        Provide:
        1. Sentiment (Positive/Negative/Neutral)
        2. Key themes/topics
        3. Action items (if any)
        4. Priority (High/Medium/Low)
        """

        try:
            result = agent.ask(analysis_prompt)

            # Store analysis
            analysis = {
                "customer": customer,
                "date": date,
                "sentiment": "Extracted from AI",  # Would parse from result
                "analysis": result["answer"],
                "reasoning": result.get("reasoning", "N/A"),
            }
            results.append(analysis)

            # Display
            print(f"   💡 Analysis: {result['answer'][:150]}...")  # Truncate

        except Exception as e:
            print(f"   ❌ Error analyzing feedback: {e}")
            results.append({"customer": customer, "error": str(e)})

    # Step 3: Generate summary insights with memory
    print("\n" + "=" * 70)
    print("📈 GENERATING SUMMARY INSIGHTS (Using Memory)")
    print("=" * 70 + "\n")

    summary_prompt = """
    Based on all the customer feedback you've just analyzed in this session:

    1. What are the TOP 3 most important themes?
    2. What is the overall sentiment trend?
    3. What are the TOP 2 priority action items for the product team?
    4. Are there any patterns in the feedback?

    Provide a concise executive summary.
    """

    try:
        summary_result = agent.ask(summary_prompt)

        print("🎯 Executive Summary:")
        print("-" * 70)
        print(summary_result["answer"])
        print()

        if "reasoning" in summary_result:
            print(f"🧠 Reasoning: {summary_result['reasoning'][:200]}...")
            print()

    except Exception as e:
        print(f"❌ Error generating summary: {e}\n")

    # Step 4: Test memory persistence
    print("=" * 70)
    print("🔍 TESTING MEMORY PERSISTENCE")
    print("=" * 70 + "\n")

    memory_test_prompt = "What feedback did Alice provide?"

    try:
        memory_result = agent.ask(memory_test_prompt)
        print(f"❓ Question: {memory_test_prompt}")
        print(f"💭 Answer: {memory_result['answer']}\n")

        # Verify agent remembers context
        context_test = (
            "Based on all feedback, should we prioritize mobile fixes or new features?"
        )
        context_result = agent.ask(context_test)
        print(f"❓ Question: {context_test}")
        print(f"💭 Answer: {context_result['answer']}\n")

    except Exception as e:
        print(f"❌ Memory test error: {e}\n")

    # Step 5: Display statistics
    print("=" * 70)
    print("📊 ANALYSIS STATISTICS")
    print("=" * 70)
    print(f"\n✅ Feedback Processed: {len(CUSTOMER_FEEDBACK)}")
    print(f"✅ Successful Analyses: {len([r for r in results if 'error' not in r])}")
    print(f"✅ Session ID: {session_id}")
    print("✅ Memory Enabled: Yes")
    print("\n💡 Note: This session's context is preserved for future analysis.")
    print("   You can continue this analysis by using the same session_id.")


if __name__ == "__main__":
    main()
