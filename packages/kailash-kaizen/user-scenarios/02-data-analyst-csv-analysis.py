"""
Scenario 2: Data Analyst - CSV Data Analysis
============================================

User Profile:
- Data analyst working with datasets
- Needs AI to provide insights from data
- Wants to automate analysis reports

Use Case:
- Analyze sales data CSV
- Get AI-powered insights
- Generate summary reports

Developer Experience Goals:
- Easy data integration
- Multiple analysis tasks
- Structured output
- Repeatable workflow
"""

import pandas as pd
from dotenv import load_dotenv
from kaizen_agents.agents import SimpleQAAgent
from kaizen_agents.agents.specialized.simple_qa import SimpleQAConfig

# Load environment variables
load_dotenv()


def create_sample_data():
    """Create sample sales data for demonstration."""
    data = {
        "Product": ["Laptop", "Mouse", "Keyboard", "Monitor", "Laptop", "Mouse"],
        "Quantity": [2, 10, 5, 3, 1, 8],
        "Price": [1200, 25, 75, 350, 1200, 25],
        "Region": ["North", "North", "South", "East", "West", "South"],
    }
    df = pd.DataFrame(data)
    df["Total"] = df["Quantity"] * df["Price"]
    return df


def main():
    """Data analyst workflow - CSV analysis with AI insights."""

    print("=" * 60)
    print("Data Analyst - CSV Analysis with AI")
    print("=" * 60 + "\n")

    # Step 1: Load and prepare data
    print("📊 Loading sales data...")
    df = create_sample_data()
    print(df.to_string())
    print()

    # Calculate basic statistics
    total_sales = df["Total"].sum()
    avg_quantity = df["Quantity"].mean()
    top_product = df.groupby("Product")["Total"].sum().idxmax()

    stats_summary = f"""
    Sales Data Summary:
    - Total Sales: ${total_sales:,.2f}
    - Average Quantity per Order: {avg_quantity:.1f}
    - Top Product: {top_product}
    - Number of Transactions: {len(df)}
    - Regions: {df["Region"].nunique()} ({", ".join(df["Region"].unique())})

    Detailed Data:
    {df.to_string()}
    """

    # Step 2: Create AI agent for analysis
    print("🤖 Creating AI Analysis Agent...")
    config = SimpleQAConfig(
        llm_provider="ollama",
        model="llama2",
        temperature=0.3,  # Lower for more consistent analysis
        max_tokens=500,
    )
    agent = SimpleQAAgent(config=config)

    # Step 3: Get AI insights
    analysis_tasks = [
        {
            "task": "Overall Performance",
            "question": f"Based on this sales data, provide 3 key insights about overall performance:\n{stats_summary}",
        },
        {
            "task": "Regional Analysis",
            "question": f"Analyze the regional distribution and suggest which region needs more attention:\n{stats_summary}",
        },
        {
            "task": "Product Strategy",
            "question": f"Based on sales patterns, recommend which products to focus on:\n{stats_summary}",
        },
    ]

    results = {}

    for task_info in analysis_tasks:
        task = task_info["task"]
        question = task_info["question"]

        print(f"\n🔍 Analyzing: {task}")
        print("-" * 60)

        try:
            result = agent.ask(question)

            # Store result
            results[task] = {
                "answer": result["answer"],
                "confidence": result.get("confidence", 0.0),
            }

            # Display
            print(f"💡 Insights:\n{result['answer']}")
            print(f"📊 Confidence: {result.get('confidence', 'N/A')}")

        except Exception as e:
            print(f"❌ Error in {task}: {e}")
            results[task] = {"error": str(e)}

    # Step 4: Generate final report
    print("\n" + "=" * 60)
    print("📈 FINAL ANALYSIS REPORT")
    print("=" * 60)

    print("\n📊 Data Summary:")
    print(f"  - Total Revenue: ${total_sales:,.2f}")
    print(f"  - Transactions: {len(df)}")
    print(f"  - Top Product: {top_product}")

    print("\n🤖 AI Insights:")
    for task, result in results.items():
        if "error" not in result:
            print(f"\n{task}:")
            print(f"  {result['answer'][:200]}...")  # Truncate for display

    print("\n✅ Analysis complete!")


if __name__ == "__main__":
    main()
