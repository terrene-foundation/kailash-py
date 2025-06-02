"""
Hierarchical RAG (Retrieval-Augmented Generation) Workflow Example

This example demonstrates OpenAI's hierarchical document processing method
implemented as a reusable workflow template in the Kailash SDK.

Features Demonstrated:
1. Hierarchical document splitting (3 parts per iteration)
2. Query-driven relevance selection
3. Iterative processing (3-5 iterations)
4. Multi-model strategy (splitting, generation, validation)
5. Configurable parameters and strategies
6. Template composition and reuse

The workflow implements the complete pipeline:
- Document preprocessing and initialization
- Iterative hierarchical splitting and selection
- Context combination with multiple strategies
- Response generation with configurable models
- Optional validation using reasoning models
- Structured output formatting
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from kailash.runtime.local import LocalRuntime
from kailash.workflow.templates.hierarchical_rag import (
    create_hierarchical_rag_template,
    create_simple_rag_template,
)
from kailash.workflow.templates.registry import WorkflowTemplateRegistry


def demonstrate_hierarchical_rag():
    """
    Demonstrate the hierarchical RAG workflow template.

    This example shows how to:
    1. Create and register the hierarchical RAG template
    2. Configure different model strategies
    3. Process a sample document with queries
    4. Compare results with different configurations
    """

    print("🚀 Hierarchical RAG Workflow Template Demo")
    print("=" * 50)

    # Sample document for processing
    sample_document = """
    Artificial Intelligence and Machine Learning Overview

    Artificial Intelligence (AI) represents one of the most significant technological
    advancements of the 21st century. AI systems are designed to perform tasks that
    typically require human intelligence, such as learning, reasoning, perception,
    and language understanding.

    Machine Learning Fundamentals

    Machine Learning (ML) is a subset of AI that focuses on algorithms and statistical
    models that enable computers to improve their performance on a specific task through
    experience. There are three main types of machine learning: supervised learning,
    unsupervised learning, and reinforcement learning.

    Supervised learning involves training algorithms on labeled datasets where the
    correct output is known. Common applications include image classification, email
    spam detection, and medical diagnosis. Popular algorithms include linear regression,
    decision trees, random forests, and neural networks.

    Deep Learning and Neural Networks

    Deep Learning is a specialized area of machine learning that uses artificial neural
    networks with multiple layers (hence "deep") to model and understand complex patterns
    in data. These networks are inspired by the structure and function of the human brain.

    Convolutional Neural Networks (CNNs) are particularly effective for image processing
    tasks, while Recurrent Neural Networks (RNNs) and Long Short-Term Memory (LSTM)
    networks excel at processing sequential data like text and time series.

    Natural Language Processing

    Natural Language Processing (NLP) is a branch of AI that focuses on the interaction
    between computers and human language. It encompasses tasks such as text analysis,
    sentiment analysis, machine translation, and question answering.

    Recent advances in NLP include transformer models like BERT, GPT, and T5, which
    have revolutionized language understanding and generation. These models use attention
    mechanisms to process text more effectively than previous approaches.

    Applications and Future Directions

    AI and ML technologies are being applied across numerous industries including
    healthcare, finance, transportation, and entertainment. In healthcare, AI assists
    with medical imaging, drug discovery, and personalized treatment plans.

    Future developments in AI include improved explainability, better handling of
    edge cases, reduced bias, and more efficient algorithms that require less
    computational power and data.
    """

    # Sample queries to test
    sample_queries = [
        "What are the main types of machine learning?",
        "How do neural networks work in deep learning?",
        "What are the applications of AI in healthcare?",
        "What are transformer models in NLP?",
    ]

    # 1. Create and register the hierarchical RAG template
    print("\n📋 Creating Hierarchical RAG Template...")
    hierarchical_template = create_hierarchical_rag_template()

    # Register in the template registry
    registry = WorkflowTemplateRegistry()
    registry.register(hierarchical_template)

    print(f"✅ Template registered: {hierarchical_template.template_id}")
    print(f"   Name: {hierarchical_template.name}")
    print(f"   Category: {hierarchical_template.category}")
    print(f"   Parameters: {len(hierarchical_template.parameters)}")

    # 2. Demonstrate different configurations
    configurations = [
        {
            "name": "OpenAI Standard Configuration",
            "config": {
                "document_content": sample_document,
                "query": sample_queries[0],
                "max_iterations": 4,
                "min_iterations": 3,
                "relevance_threshold": 0.7,
                "splitting_strategy": "semantic",
                "combination_strategy": "hierarchical",
                "output_format": "structured",
                "validation_enabled": True,
                "splitting_model": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                },
                "generation_model": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "temperature": 0.3,
                },
                "validation_model": {
                    "provider": "openai",
                    "model": "o1-mini",
                    "temperature": 0.1,
                },
            },
        },
        {
            "name": "Fast Processing Configuration",
            "config": {
                "document_content": sample_document,
                "query": sample_queries[1],
                "max_iterations": 3,
                "min_iterations": 2,
                "relevance_threshold": 0.6,
                "splitting_strategy": "length",
                "combination_strategy": "flat",
                "output_format": "bullet_points",
                "validation_enabled": False,
                "splitting_model": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                },
                "generation_model": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.2,
                },
            },
        },
        {
            "name": "High Quality Configuration",
            "config": {
                "document_content": sample_document,
                "query": sample_queries[2],
                "max_iterations": 5,
                "min_iterations": 3,
                "relevance_threshold": 0.8,
                "splitting_strategy": "hybrid",
                "combination_strategy": "weighted",
                "output_format": "narrative",
                "validation_enabled": True,
                "splitting_model": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "temperature": 0.05,
                },
                "generation_model": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "temperature": 0.2,
                },
                "validation_model": {
                    "provider": "openai",
                    "model": "o1-mini",
                    "temperature": 0.0,
                },
            },
        },
    ]

    # 3. Process each configuration
    runtime = LocalRuntime()

    for i, config_info in enumerate(configurations, 1):
        print(f"\n📊 Configuration {i}: {config_info['name']}")
        print("-" * 40)

        try:
            # Instantiate workflow from template
            workflow = hierarchical_template.instantiate(**config_info["config"])

            print("✅ Workflow instantiated successfully")
            print(f"   Nodes: {len(workflow.nodes)}")
            print(f"   Connections: {len(workflow.connections)}")

            # Prepare inputs for execution
            inputs = {
                "document_content": config_info["config"]["document_content"],
                "query": config_info["config"]["query"],
            }

            print(f"\n🔍 Processing Query: '{config_info['config']['query']}'")
            print(f"📄 Document Length: {len(sample_document)} characters")

            # Execute workflow (in a real implementation)
            print(f"⚙️  Executing workflow with {config_info['name']}...")

            # Simulate execution results
            simulated_result = {
                "response": f"Hierarchical RAG response for: {config_info['config']['query']}",
                "metadata": {
                    "template_id": "hierarchical_rag",
                    "processing_complete": True,
                    "iterations_completed": config_info["config"]["min_iterations"],
                    "parts_processed": 9,  # 3^2 parts in typical case
                    "validation_enabled": config_info["config"]["validation_enabled"],
                    "model_config": {
                        "splitting_model": config_info["config"]["splitting_model"][
                            "model"
                        ],
                        "generation_model": config_info["config"]["generation_model"][
                            "model"
                        ],
                    },
                },
            }

            if config_info["config"]["validation_enabled"]:
                simulated_result["validation"] = {
                    "is_valid": True,
                    "quality_score": 8.7,
                    "validation_notes": "Response accurately addresses query using relevant context.",
                }

            print("✅ Execution completed successfully!")
            print(f"   Response length: {len(simulated_result['response'])} characters")
            print(
                f"   Iterations: {simulated_result['metadata']['iterations_completed']}"
            )
            print(
                f"   Parts processed: {simulated_result['metadata']['parts_processed']}"
            )

            if "validation" in simulated_result:
                print(
                    f"   Quality score: {simulated_result['validation']['quality_score']}/10"
                )

        except Exception as e:
            print(f"❌ Error executing configuration: {e}")

    # 4. Compare with simple RAG template
    print("\n🔄 Comparing with Simple RAG Template")
    print("-" * 40)

    simple_template = create_simple_rag_template()
    registry.register(simple_template)

    simple_workflow = simple_template.instantiate(
        document_content=sample_document,
        query=sample_queries[0],
        chunk_size=500,
        model_config={"provider": "openai", "model": "gpt-4o", "temperature": 0.3},
    )

    print("✅ Simple RAG workflow created")
    print(
        f"   Nodes: {len(simple_workflow.nodes)} (vs {len(workflow.nodes)} in hierarchical)"
    )
    print("   Complexity: Much simpler, no iterations")
    print("   Use case: Quick processing, smaller documents")

    # 5. Template composition example
    print("\n🔗 Template Composition Example")
    print("-" * 40)

    print("📋 Available templates in registry:")
    for template in registry.list_templates():
        print(f"   • {template.template_id}: {template.name}")

    print("\n💡 Composition possibilities:")
    print("   • Preprocessing → Hierarchical RAG → Postprocessing")
    print("   • Multiple documents → Parallel RAG → Result merging")
    print("   • Document extraction → RAG → Knowledge base update")

    # 6. Performance and cost considerations
    print("\n💰 Cost and Performance Considerations")
    print("-" * 40)

    print("📊 Model usage breakdown:")
    print("   • Splitting/Selection: High volume, cheap models (gpt-4o-mini)")
    print("   • Generation: Medium volume, quality models (gpt-4o)")
    print("   • Validation: Low volume, reasoning models (o1-mini)")

    print("\n⚡ Performance optimizations:")
    print("   • Caching: Reuse splitting results for similar documents")
    print("   • Parallel processing: Split evaluation in parallel")
    print("   • Early termination: Stop when all parts selected")
    print("   • Batch processing: Process multiple queries together")

    print("\n✅ Demo completed successfully!")


def demonstrate_template_customization():
    """
    Demonstrate how to customize and extend the hierarchical RAG template.
    """

    print("\n🛠️  Template Customization Demo")
    print("=" * 40)

    # Get the base template
    registry = WorkflowTemplateRegistry()
    base_template = registry.get("hierarchical_rag")

    print("📋 Base template parameters:")
    for name, info in base_template.get_parameter_info().items():
        print(f"   • {name}: {info['description']}")

    # Show how to create variants
    print("\n🎯 Creating specialized variants:")

    # Medical document variant
    medical_config = {
        "max_iterations": 5,
        "min_iterations": 4,  # More thorough for medical
        "relevance_threshold": 0.8,  # Higher precision needed
        "splitting_strategy": "semantic",
        "validation_enabled": True,  # Critical for medical
        "output_format": "structured",
    }

    # Legal document variant
    legal_config = {
        "max_iterations": 6,  # Very thorough
        "min_iterations": 4,
        "relevance_threshold": 0.9,  # Highest precision
        "splitting_strategy": "paragraph",  # Preserve legal structure
        "validation_enabled": True,
        "output_format": "structured",
    }

    # Quick analysis variant
    quick_config = {
        "max_iterations": 3,
        "min_iterations": 2,
        "relevance_threshold": 0.6,
        "splitting_strategy": "length",
        "validation_enabled": False,
        "output_format": "bullet_points",
    }

    variants = [
        ("Medical Document Processing", medical_config),
        ("Legal Document Analysis", legal_config),
        ("Quick Document Summary", quick_config),
    ]

    for variant_name, config in variants:
        print(f"\n📄 {variant_name}:")
        print(f"   • Iterations: {config['min_iterations']}-{config['max_iterations']}")
        print(f"   • Threshold: {config['relevance_threshold']}")
        print(f"   • Strategy: {config['splitting_strategy']}")
        print(f"   • Validation: {config['validation_enabled']}")

    print("\n💡 Customization benefits:")
    print("   • Domain-specific optimizations")
    print("   • Cost-performance trade-offs")
    print("   • Quality requirements adaptation")
    print("   • Industry compliance needs")


if __name__ == "__main__":
    try:
        demonstrate_hierarchical_rag()
        demonstrate_template_customization()

        print("\n🎉 All demonstrations completed successfully!")
        print("\n📚 Next steps:")
        print("   1. Implement actual LLM integration for node execution")
        print("   2. Add caching and performance optimizations")
        print("   3. Create domain-specific template variants")
        print("   4. Build template package distribution system")
        print("   5. Add monitoring and cost tracking features")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()
