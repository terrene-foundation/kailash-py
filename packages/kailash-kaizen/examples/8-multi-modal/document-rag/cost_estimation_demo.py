"""
Document Extraction Cost Estimation Demo

Demonstrates:
1. Cost estimation before extraction
2. Provider comparison for cost-effectiveness
3. Budget-aware decision making
4. Free vs. paid provider selection

This example shows how to estimate costs and make informed provider choices.
"""

import os
import tempfile
from typing import List

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


def create_sample_documents() -> List[str]:
    """Create sample documents of varying sizes."""

    # Small document (1 page equivalent)
    small_doc = """# Summary Report

## Key Points
- Revenue: $1M
- Growth: 25%
- Outlook: Positive

## Conclusion
Strong quarterly performance.
"""

    # Medium document (3 page equivalent)
    medium_doc = """# Quarterly Business Report

## Executive Summary
This quarter showed exceptional growth across all business segments.

## Financial Performance
Total revenue reached $5 million, representing 45% year-over-year growth.
Operating expenses were well controlled at $3.5 million.
Net profit margin improved to 30%.

## Product Development
- Launched 2 major products
- Completed 5 feature updates
- Filed 3 patent applications

## Market Expansion
Entered 4 new geographic markets:
- Germany: 500 customers acquired
- France: 350 customers acquired
- UK: 800 customers acquired
- Japan: 250 customers acquired

## Customer Metrics
- Total customers: 15,000 (up from 10,000)
- Customer satisfaction: 4.8/5.0
- Retention rate: 94%
- Average contract value: $5,000

## Strategic Initiatives
1. AI/ML platform development
2. Mobile app launch
3. Enterprise tier introduction
4. Partner ecosystem expansion

## Future Outlook
Planning to double revenue in next 12 months through:
- Product innovation
- Market expansion
- Strategic partnerships
- Customer success programs
"""

    # Large document (10 page equivalent)
    large_doc = (
        medium_doc * 3
        + "\n\n"
        + "Additional detailed analysis:\n"
        + ("- Data point\n" * 100)
    )

    # Save to temp files
    docs = []
    for i, content in enumerate([small_doc, medium_doc, large_doc], 1):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(content)
            docs.append(tmp.name)

    return docs


def estimate_extraction_costs():
    """Demonstrate cost estimation across providers."""

    print("=" * 80)
    print("📊 DOCUMENT EXTRACTION COST ESTIMATION DEMO")
    print("=" * 80)

    # Create sample documents
    print("\n📄 Creating sample documents (small, medium, large)...")
    doc_paths = create_sample_documents()
    doc_sizes = ["Small (1 page)", "Medium (3 pages)", "Large (10 pages)"]

    # Initialize agent with all providers configured
    config = DocumentExtractionConfig(
        provider="auto",
        landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
        ollama_base_url="http://localhost:11434",
    )

    agent = DocumentExtractionAgent(config=config)

    print("\n" + "=" * 80)
    print("💰 COST ESTIMATION BY PROVIDER")
    print("=" * 80)

    # Estimate costs for each document
    for doc_path, size in zip(doc_paths, doc_sizes):
        print(f"\n📄 Document: {size}")
        print("-" * 80)

        # Get cost estimates for all providers
        cost_estimates = agent.estimate_cost(doc_path, provider="auto")

        # Display results
        print(
            f"   Landing AI:     ${cost_estimates['landing_ai']:.3f} (98% accuracy, bounding boxes)"
        )
        print(
            f"   OpenAI Vision:  ${cost_estimates['openai_vision']:.3f} (95% accuracy, fastest)"
        )
        print(
            f"   Ollama Vision:  ${cost_estimates['ollama_vision']:.3f} (85% accuracy, FREE)"
        )

        # Calculate potential savings
        highest_cost = max(
            cost_estimates["landing_ai"], cost_estimates["openai_vision"]
        )
        ollama_savings = highest_cost - cost_estimates["ollama_vision"]

        print(f"\n   💡 Savings with Ollama: ${ollama_savings:.3f} per document")
        print(
            f"   💡 Best accuracy/cost: Landing AI (98% accuracy, ${cost_estimates['landing_ai']:.3f})"
        )
        print(
            f"   💡 Best speed: OpenAI Vision (fastest, ${cost_estimates['openai_vision']:.3f})"
        )


def demonstrate_budget_decisions():
    """Demonstrate budget-aware provider selection."""

    print("\n" + "=" * 80)
    print("🎯 BUDGET-AWARE PROVIDER SELECTION")
    print("=" * 80)

    # Create test document
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write("Sample document content for budget testing.")
        doc_path = tmp.name

    config = DocumentExtractionConfig(
        provider="auto",
        landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
        openai_key=os.getenv("OPENAI_API_KEY"),
    )

    agent = DocumentExtractionAgent(config=config)

    # Scenario 1: Generous budget
    print("\n📊 Scenario 1: Generous Budget ($0.10/document)")
    print("-" * 80)
    cost_estimates = agent.estimate_cost(doc_path)

    budget = 0.10
    print(f"   Budget: ${budget:.2f}")
    print(f"   Landing AI cost: ${cost_estimates['landing_ai']:.3f}")

    if cost_estimates["landing_ai"] <= budget:
        print("   ✅ Recommendation: Use Landing AI (highest accuracy)")
        print("   💡 Budget allows for best quality extraction")
    else:
        print("   ⚠️  Landing AI exceeds budget")

    # Scenario 2: Tight budget
    print("\n📊 Scenario 2: Tight Budget ($0.01/document)")
    print("-" * 80)

    budget = 0.01
    print(f"   Budget: ${budget:.2f}")
    print(f"   Landing AI cost: ${cost_estimates['landing_ai']:.3f}")
    print(f"   OpenAI cost: ${cost_estimates['openai_vision']:.3f}")

    if (
        cost_estimates["landing_ai"] > budget
        and cost_estimates["openai_vision"] > budget
    ):
        print("   ✅ Recommendation: Use Ollama (free, 85% accuracy)")
        print("   💡 Budget constraint requires free provider")
        print(f"   💰 Savings: ${max(cost_estimates.values()):.3f}/document")

    # Scenario 3: Zero budget (development)
    print("\n📊 Scenario 3: Zero Budget (Development/Testing)")
    print("-" * 80)

    budget = 0.00
    print(f"   Budget: ${budget:.2f}")
    print("   ✅ Recommendation: Use Ollama exclusively")
    print("   💡 Perfect for development, testing, and prototyping")
    print("   💡 85% accuracy is sufficient for most use cases")
    print("   💰 Unlimited free extractions")

    # Cleanup
    os.unlink(doc_path)


def demonstrate_cost_vs_quality():
    """Demonstrate cost vs. quality tradeoffs."""

    print("\n" + "=" * 80)
    print("⚖️  COST VS. QUALITY TRADEOFF ANALYSIS")
    print("=" * 80)

    # Provider comparison table
    providers = [
        {
            "name": "Landing AI",
            "accuracy": 98,
            "cost_per_page": 0.015,
            "features": ["Bounding boxes", "Tables", "High accuracy"],
            "speed": "1.2s/page",
            "best_for": "Production, legal documents, contracts",
        },
        {
            "name": "OpenAI Vision",
            "accuracy": 95,
            "cost_per_page": 0.068,
            "features": ["Tables", "Fast processing"],
            "speed": "0.8s/page (fastest)",
            "best_for": "Quick extraction, moderate accuracy needs",
        },
        {
            "name": "Ollama",
            "accuracy": 85,
            "cost_per_page": 0.000,
            "features": ["Local processing", "No API limits"],
            "speed": "2.5s/page",
            "best_for": "Development, testing, unlimited use",
        },
    ]

    print("\n📊 Provider Comparison:")
    print("-" * 80)

    for provider in providers:
        print(f"\n{provider['name']}:")
        print(f"   Accuracy: {provider['accuracy']}%")
        print(f"   Cost: ${provider['cost_per_page']:.3f}/page")
        print(f"   Speed: {provider['speed']}")
        print(f"   Features: {', '.join(provider['features'])}")
        print(f"   Best for: {provider['best_for']}")

    # Decision matrix
    print("\n" + "=" * 80)
    print("🎯 DECISION MATRIX")
    print("=" * 80)

    scenarios = [
        {
            "scenario": "Legal Documents",
            "priority": "Accuracy + Bounding boxes",
            "recommendation": "Landing AI",
            "reason": "98% accuracy with spatial coordinates for validation",
        },
        {
            "scenario": "Bulk Processing",
            "priority": "Cost efficiency",
            "recommendation": "Ollama",
            "reason": "Free unlimited processing, 85% accuracy acceptable",
        },
        {
            "scenario": "Quick Analysis",
            "priority": "Speed",
            "recommendation": "OpenAI Vision",
            "reason": "Fastest processing (0.8s/page), good accuracy",
        },
        {
            "scenario": "Development/Testing",
            "priority": "Zero cost",
            "recommendation": "Ollama",
            "reason": "Unlimited free use, no API costs during development",
        },
        {
            "scenario": "Financial Reports",
            "priority": "Table extraction + Accuracy",
            "recommendation": "Landing AI",
            "reason": "Best table handling with highest accuracy",
        },
    ]

    for scenario in scenarios:
        print(f"\n📋 {scenario['scenario']}:")
        print(f"   Priority: {scenario['priority']}")
        print(f"   ✅ Recommendation: {scenario['recommendation']}")
        print(f"   💡 Reason: {scenario['reason']}")


def main():
    """Run all cost estimation demonstrations."""

    # Part 1: Cost estimation
    estimate_extraction_costs()

    # Part 2: Budget decisions
    demonstrate_budget_decisions()

    # Part 3: Cost vs. quality
    demonstrate_cost_vs_quality()

    print("\n" + "=" * 80)
    print("✨ COST ESTIMATION DEMO COMPLETE")
    print("=" * 80)

    print("\n💡 Key Takeaways:")
    print("   1. Always estimate costs before processing large batches")
    print("   2. Ollama provides free unlimited extraction (85% accuracy)")
    print("   3. Landing AI offers highest accuracy (98%) with bounding boxes")
    print("   4. OpenAI Vision is fastest but more expensive ($0.068/page)")
    print("   5. Choose provider based on budget, accuracy needs, and features")

    print("\n📚 Related Examples:")
    print("   - basic_rag.py: Simple RAG with Ollama (free)")
    print("   - advanced_rag.py: Multi-document with cost optimization")
    print("   - workflow_integration.py: Core SDK integration patterns")


if __name__ == "__main__":
    main()
