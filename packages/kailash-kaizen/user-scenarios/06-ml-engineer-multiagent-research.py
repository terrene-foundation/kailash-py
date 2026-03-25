"""
Scenario 6: ML Engineer - Multi-Agent Research System
======================================================

User Profile:
- ML engineer researching new techniques
- Needs multiple specialized agents
- Wants systematic research workflow
- Requires coordinated analysis

Use Case:
- Research ML techniques (e.g., fine-tuning strategies)
- Multiple agents for different aspects:
  - Researcher: Find information
  - Analyst: Analyze findings
  - Reviewer: Quality check and summarize
- Coordinated workflow

Developer Experience Goals:
- Multiple specialized agents
- Clear coordination pattern
- Systematic workflow
- Comprehensive research output
"""

from typing import Dict

from dotenv import load_dotenv
from kaizen_agents.agents import ChainOfThoughtAgent, RAGResearchAgent, SimpleQAAgent
from kaizen_agents.agents.specialized.chain_of_thought import ChainOfThoughtConfig
from kaizen_agents.agents.specialized.rag_research import RAGConfig

# Load environment variables
load_dotenv()


class ResearchCoordinator:
    """Coordinates multiple agents for research workflow."""

    def __init__(self):
        # Agent 1: Researcher (finds information)
        self.researcher = RAGResearchAgent(
            RAGConfig(
                llm_provider="ollama", model="llama2", temperature=0.6, max_tokens=500
            )
        )

        # Agent 2: Analyst (deep analysis)
        self.analyst = ChainOfThoughtAgent(
            ChainOfThoughtConfig(
                llm_provider="ollama",
                model="llama2",
                temperature=0.4,  # Lower for structured analysis
                max_tokens=600,
            )
        )

        # Agent 3: Reviewer (quality check & summarize)
        self.reviewer = SimpleQAAgent(
            SimpleQAConfig(
                llm_provider="ollama", model="llama2", temperature=0.5, max_tokens=400
            )
        )

    def research_topic(self, topic: str, context: str = "") -> Dict:
        """Coordinate research on a topic using all agents."""

        print(f"\n🔬 RESEARCHING: {topic}")
        print("=" * 70)

        results = {"topic": topic, "research": None, "analysis": None, "review": None}

        # Phase 1: Research (gather information)
        print("\n📚 Phase 1: Research Agent")
        print("-" * 70)

        research_prompt = f"{topic}\n\nContext: {context}" if context else topic

        try:
            research_result = self.researcher.research(research_prompt)
            results["research"] = research_result.get("answer", "No research available")
            print("✅ Research completed")
            print(f"📝 Summary: {results['research'][:200]}...")
        except Exception as e:
            print(f"❌ Research error: {e}")
            results["research"] = f"Error: {str(e)}"

        # Phase 2: Analysis (deep dive)
        print("\n🧠 Phase 2: Analysis Agent (Chain-of-Thought)")
        print("-" * 70)

        if results["research"] and not results["research"].startswith("Error"):
            analysis_prompt = f"""
            Analyze this research finding:

            {results["research"]}

            Provide:
            1. Key insights
            2. Practical implications
            3. Potential challenges
            4. Recommendations
            """

            try:
                analysis_result = self.analyst.think(analysis_prompt)
                results["analysis"] = analysis_result.get(
                    "answer", "No analysis available"
                )
                print("✅ Analysis completed")
                print(f"💡 Key insight: {results['analysis'][:200]}...")

                # Show reasoning if available
                if "reasoning" in analysis_result:
                    print(f"🔍 Reasoning: {analysis_result['reasoning'][:150]}...")

            except Exception as e:
                print(f"❌ Analysis error: {e}")
                results["analysis"] = f"Error: {str(e)}"
        else:
            print("⚠️  Skipping analysis (research failed)")
            results["analysis"] = "Skipped due to research failure"

        # Phase 3: Review (quality check)
        print("\n✅ Phase 3: Review Agent (Quality Check)")
        print("-" * 70)

        if (
            results["research"]
            and results["analysis"]
            and not results["research"].startswith("Error")
            and not results["analysis"].startswith("Error")
        ):
            review_prompt = f"""
            Review this research output:

            Research Findings:
            {results["research"][:300]}

            Analysis:
            {results["analysis"][:300]}

            Provide:
            1. Quality assessment (1-10)
            2. Completeness check
            3. Action items (if any)
            4. Executive summary (2-3 sentences)
            """

            try:
                review_result = self.reviewer.ask(review_prompt)
                results["review"] = review_result.get("answer", "No review available")
                print("✅ Review completed")
                print(f"🎯 Summary: {results['review'][:200]}...")
            except Exception as e:
                print(f"❌ Review error: {e}")
                results["review"] = f"Error: {str(e)}"
        else:
            print("⚠️  Skipping review (previous phases failed)")
            results["review"] = "Skipped due to previous failures"

        return results


def main():
    """ML Engineer workflow - multi-agent research coordination."""

    print("=" * 70)
    print("ML Engineer - Multi-Agent Research System")
    print("=" * 70 + "\n")

    print("🤖 Initializing Research System...")
    print("-" * 70)
    print("Creating 3 specialized agents:")
    print("  1. 📚 Research Agent (RAG-based information gathering)")
    print("  2. 🧠 Analysis Agent (Chain-of-thought reasoning)")
    print("  3. ✅ Review Agent (Quality assurance)")
    print()

    coordinator = ResearchCoordinator()
    print("✅ Multi-agent system ready!\n")

    # Research topics for ML engineer
    research_topics = [
        {
            "topic": "What are the best practices for fine-tuning large language models?",
            "context": "Focus on efficiency and cost-effectiveness",
        },
        {
            "topic": "How does LoRA (Low-Rank Adaptation) work for model fine-tuning?",
            "context": "Explain the mathematical principles and practical benefits",
        },
        {
            "topic": "What are the trade-offs between full fine-tuning and parameter-efficient methods?",
            "context": "Consider computational cost, performance, and use cases",
        },
    ]

    all_results = []

    # Execute research workflow
    for idx, research_item in enumerate(research_topics, 1):
        topic = research_item["topic"]
        context = research_item.get("context", "")

        print(f"\n{'=' * 70}")
        print(f"RESEARCH TASK {idx}/{len(research_topics)}")
        print("=" * 70)

        results = coordinator.research_topic(topic, context)
        all_results.append(results)

        print()

    # Generate final synthesis
    print("\n" + "=" * 70)
    print("📊 RESEARCH SYNTHESIS")
    print("=" * 70 + "\n")

    print("🎯 Research Completed:")
    print("-" * 70)
    for idx, result in enumerate(all_results, 1):
        status = (
            "✅"
            if (result["research"] and not result["research"].startswith("Error"))
            else "❌"
        )
        print(f"{idx}. {status} {result['topic'][:60]}...")

    # Summary statistics
    print("\n📈 Statistics:")
    print("-" * 70)
    print(f"  Total Topics: {len(all_results)}")
    print(
        f"  Research Success: {len([r for r in all_results if r['research'] and not r['research'].startswith('Error')])}/{len(all_results)}"
    )
    print(
        f"  Analysis Success: {len([r for r in all_results if r['analysis'] and not r['analysis'].startswith('Error')])}/{len(all_results)}"
    )
    print(
        f"  Review Success: {len([r for r in all_results if r['review'] and not r['review'].startswith('Error')])}/{len(all_results)}"
    )

    print("\n🤖 Agent Coordination:")
    print("-" * 70)
    print("  • RAGResearchAgent: Information gathering")
    print("  • ChainOfThoughtAgent: Deep analysis with reasoning")
    print("  • SimpleQAAgent: Quality review and synthesis")
    print("  • Coordinator: Workflow orchestration")

    print("\n💡 Multi-Agent Benefits:")
    print("-" * 70)
    print("  ✅ Specialization: Each agent optimized for specific task")
    print("  ✅ Quality: Multi-stage validation (research → analyze → review)")
    print("  ✅ Comprehensive: Different perspectives on same topic")
    print("  ✅ Scalable: Easy to add more agents or topics")

    print("\n🚀 Production Enhancements:")
    print("-" * 70)
    print("  • Add parallel processing for multiple topics")
    print("  • Implement caching for repeated research")
    print("  • Use memory agents for cross-topic insights")
    print("  • Add citation tracking and source verification")
    print("  • Integrate with document databases (RAG)")

    print("\n" + "=" * 70)
    print("✅ Multi-Agent Research System Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
