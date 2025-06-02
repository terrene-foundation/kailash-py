"""
Simple Hierarchical RAG Workflow Example

This example demonstrates the basic usage of the hierarchical RAG template
without the full complexity of the comprehensive example.

Quick start guide for using OpenAI's hierarchical document processing method.
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from kailash.workflow.templates.hierarchical_rag import create_hierarchical_rag_template


def main():
    """Simple example of using hierarchical RAG template."""

    print("🚀 Simple Hierarchical RAG Example")
    print("=" * 40)

    # Sample document
    document = """
    Climate Change and Its Global Impact

    Climate change represents one of the most pressing challenges facing humanity today.
    The Earth's climate is warming at an unprecedented rate, primarily due to human
    activities that release greenhouse gases into the atmosphere.

    The primary causes of climate change include burning fossil fuels, deforestation,
    and industrial processes. These activities increase concentrations of carbon dioxide,
    methane, and other greenhouse gases, creating a "blanket" effect that traps heat.

    The impacts of climate change are already visible worldwide. Rising sea levels
    threaten coastal communities, extreme weather events are becoming more frequent,
    and ecosystems are shifting. Arctic ice is melting at alarming rates, affecting
    global weather patterns and wildlife habitats.

    Solutions to climate change require both mitigation and adaptation strategies.
    Mitigation involves reducing greenhouse gas emissions through renewable energy,
    energy efficiency, and carbon capture technologies. Adaptation means preparing
    for climate impacts through resilient infrastructure and sustainable practices.

    International cooperation is essential. The Paris Agreement represents a global
    commitment to limit warming to 1.5°C above pre-industrial levels. Achieving this
    goal requires immediate action from governments, businesses, and individuals.
    """

    # Create and use the template
    print("\n1️⃣ Creating Hierarchical RAG Template")
    template = create_hierarchical_rag_template()
    print(f"✓ Template created: {template.name}")
    print(f"  Parameters: {len(template.parameters)}")

    # Show available parameters
    print("\n2️⃣ Available Parameters:")
    for name, param in template.parameters.items():
        print(f"  • {name}: {param.description}")
        if param.default is not None:
            print(f"    Default: {param.default}")

    # Example queries
    queries = [
        "What are the main causes of climate change?",
        "What solutions are proposed for climate change?",
        "How is climate change affecting the Arctic?",
    ]

    print("\n3️⃣ Processing Queries:")

    for i, query in enumerate(queries, 1):
        print(f"\n📝 Query {i}: {query}")

        # Create workflow with minimal configuration
        workflow = template.instantiate(
            document_content=document,
            query=query,
            # Use defaults for most parameters
            max_iterations=3,  # Fewer iterations for demo
            output_format="bullet_points",  # Concise output
        )

        print(f"✓ Workflow created with {len(workflow.nodes)} nodes")

        # In a real implementation, you would execute:
        # runtime = LocalRuntime()
        # results = runtime.execute_workflow(workflow)
        # print(results["response"])

        # For demo, show the workflow structure
        print(f"  Workflow nodes: {', '.join(workflow.nodes.keys())}")

    # Show different configurations
    print("\n4️⃣ Configuration Examples:")

    # Fast configuration
    print("\n⚡ Fast Processing:")
    fast_workflow = template.instantiate(
        document_content=document,
        query="Summarize the document",
        max_iterations=2,
        min_iterations=1,
        relevance_threshold=0.6,
        validation_enabled=False,
    )
    print("  - Minimal iterations, no validation")
    print("  - Good for quick summaries")

    # Thorough configuration
    print("\n🔍 Thorough Analysis:")
    thorough_workflow = template.instantiate(
        document_content=document,
        query="Analyze all climate impacts mentioned",
        max_iterations=5,
        min_iterations=3,
        relevance_threshold=0.8,
        validation_enabled=True,
        output_format="structured",
    )
    print("  - Maximum iterations with validation")
    print("  - Best for detailed analysis")

    # Custom model configuration
    print("\n🤖 Custom Models:")
    custom_workflow = template.instantiate(
        document_content=document,
        query="What are the solutions?",
        splitting_model={"provider": "ollama", "model": "llama2", "temperature": 0.1},
        generation_model={"provider": "openai", "model": "gpt-4o", "temperature": 0.3},
    )
    print("  - Use local Ollama for splitting (cost savings)")
    print("  - Use GPT-4 for generation (quality)")

    print("\n✅ Example completed!")
    print("\n💡 Next Steps:")
    print("  1. Implement LLM integration in nodes")
    print("  2. Add actual execution with LocalRuntime")
    print("  3. Connect to your preferred LLM providers")
    print("  4. Experiment with different configurations")


if __name__ == "__main__":
    main()
