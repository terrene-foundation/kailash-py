#!/usr/bin/env python3
"""
RAG Toolkit Comprehensive Example

Demonstrates all RAG toolkit capabilities including:
- Strategy selection and swapping
- Conditional routing with LLM decision making
- WorkflowNode integration
- Performance monitoring and quality analysis
- Adaptive strategy selection

This example shows how users can seamlessly integrate RAG into their workflows
with flexible strategy switching and intelligent routing.
"""

import asyncio
import logging
from typing import Any, Dict, List

from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kaizen.nodes.rag import (
    AdaptiveRAGWorkflowNode,
    AdvancedRAGWorkflowNode,
    HierarchicalRAGNode,
    HybridRAGNode,
    RAGConfig,
    RAGPerformanceMonitorNode,
    RAGQualityAnalyzerNode,
    RAGStrategyRouterNode,
    RAGWorkflowRegistry,
    SemanticRAGNode,
    SimpleRAGWorkflowNode,
    StatisticalRAGNode,
)

from examples.utils.data_paths import get_input_data_path, get_output_data_path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sample_documents() -> List[Dict[str, Any]]:
    """Create sample documents for testing different RAG strategies"""

    documents = [
        {
            "id": "doc_1_narrative",
            "title": "Introduction to Machine Learning",
            "content": """Machine learning is a fascinating field that enables computers to learn patterns from data without being explicitly programmed. It combines concepts from statistics, computer science, and mathematics to create algorithms that can make predictions or decisions based on input data. The field has revolutionized industries from healthcare to finance, enabling applications like medical diagnosis, fraud detection, and recommendation systems. Understanding machine learning requires grasping fundamental concepts like supervised learning, unsupervised learning, and reinforcement learning.""",
            "type": "narrative",
            "source": "ml_guide.md",
        },
        {
            "id": "doc_2_technical",
            "title": "Python Machine Learning Implementation",
            "content": """
def train_model(X_train, y_train, algorithm="random_forest"):
    '''Train a machine learning model using the specified algorithm'''
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    if algorithm == "random_forest":
        model = RandomForestClassifier(n_estimators=100, random_state=42)
    elif algorithm == "logistic_regression":
        model = LogisticRegression(random_state=42, max_iter=1000)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    # Fit the model
    model.fit(X_train, y_train)
    return model

def evaluate_model(model, X_test, y_test):
    '''Evaluate model performance using accuracy score'''
    from sklearn.metrics import accuracy_score, classification_report
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    report = classification_report(y_test, predictions)
    return accuracy, report
""",
            "type": "technical",
            "source": "ml_code.py",
        },
        {
            "id": "doc_3_structured",
            "title": "Machine Learning Best Practices Guide",
            "content": """
# Machine Learning Best Practices

## 1. Data Preparation
### 1.1 Data Collection
- Ensure data quality and completeness
- Handle missing values appropriately
- Remove or correct outliers

### 1.2 Feature Engineering
- Create meaningful features from raw data
- Apply proper scaling and normalization
- Handle categorical variables

## 2. Model Selection
### 2.1 Algorithm Choice
- Consider problem type (classification vs regression)
- Evaluate computational requirements
- Assess interpretability needs

### 2.2 Hyperparameter Tuning
- Use cross-validation for parameter selection
- Apply grid search or random search
- Consider Bayesian optimization for complex spaces

## 3. Model Evaluation
### 3.1 Metrics Selection
- Choose appropriate evaluation metrics
- Consider business context in metric selection
- Use multiple metrics for comprehensive evaluation
""",
            "type": "structured",
            "source": "ml_practices.md",
        },
        {
            "id": "doc_4_mixed",
            "title": "Advanced Machine Learning Concepts",
            "content": """Deep learning represents a subset of machine learning that uses neural networks with multiple layers to model and understand complex patterns. The architecture typically consists of an input layer, multiple hidden layers, and an output layer.

```python
import tensorflow as tf

def create_neural_network(input_dim, hidden_layers, output_dim):
    model = tf.keras.Sequential()
    model.add(tf.keras.layers.Dense(hidden_layers[0], activation='relu', input_dim=input_dim))

    for units in hidden_layers[1:]:
        model.add(tf.keras.layers.Dense(units, activation='relu'))

    model.add(tf.keras.layers.Dense(output_dim, activation='softmax'))
    return model
```

The key advantage of deep learning is its ability to automatically learn hierarchical representations of data. Lower layers typically learn simple features like edges in images, while higher layers combine these to recognize complex patterns like objects or faces. This hierarchical feature learning eliminates the need for manual feature engineering in many applications.""",
            "type": "mixed",
            "source": "deep_learning.md",
        },
    ]

    return documents


async def example_1_basic_strategy_usage():
    """Example 1: Basic usage of individual RAG strategies"""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic RAG Strategy Usage")
    print("=" * 80)

    documents = create_sample_documents()
    config = RAGConfig(chunk_size=500, retrieval_k=3)

    # Test different strategies
    strategies = {
        "semantic": SemanticRAGNode("semantic_rag", config),
        "statistical": StatisticalRAGNode("statistical_rag", config),
        "hybrid": HybridRAGNode("hybrid_rag", config),
        "hierarchical": HierarchicalRAGNode("hierarchical_rag", config),
    }

    # Index documents with each strategy
    for strategy_name, strategy_node in strategies.items():
        print(f"\n--- Testing {strategy_name.upper()} Strategy ---")

        try:
            # Index documents
            index_result = await strategy_node.execute(
                documents=documents, operation="index"
            )
            print(f"✅ Indexing completed: {index_result.get('status', 'unknown')}")

            # Test retrieval
            retrieval_result = await strategy_node.execute(
                query="How to train a machine learning model?", operation="retrieve"
            )
            print(f"✅ Retrieved {len(retrieval_result.get('results', []))} documents")

            # Show top result
            results = retrieval_result.get("results", [])
            if results:
                top_result = results[0]
                print(f"   Top result: {top_result.get('title', 'N/A')}")
                print(f"   Score: {retrieval_result.get('scores', [0])[0]:.3f}")

        except Exception as e:
            print(f"❌ Error with {strategy_name}: {e}")


async def example_2_workflow_integration():
    """Example 2: Integrating RAG into custom workflows with conditional routing"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Workflow Integration with Conditional Routing")
    print("=" * 80)

    documents = create_sample_documents()

    # Create workflow with conditional RAG strategy selection
    builder = WorkflowBuilder()

    # Add document analyzer
    analyzer_id = builder.add_node(
        "PythonCodeNode",
        node_id="document_analyzer",
        config={
            "code": """
def analyze_documents(documents):
    technical_keywords = ["function", "class", "import", "def", "return", "code"]
    structure_indicators = ["# ", "## ", "### "]

    total_docs = len(documents)
    technical_count = 0
    structured_count = 0
    avg_length = 0

    for doc in documents:
        content = doc.get("content", "").lower()
        avg_length += len(content)

        # Check for technical content
        if any(keyword in content for keyword in technical_keywords):
            technical_count += 1

        # Check for structure
        if any(indicator in content for indicator in structure_indicators):
            structured_count += 1

    avg_length = avg_length / total_docs if total_docs > 0 else 0

    # Determine strategy
    if technical_count > total_docs * 0.5:
        strategy = "statistical"
        reasoning = "High technical content detected"
    elif structured_count > total_docs * 0.5 and avg_length > 1000:
        strategy = "hierarchical"
        reasoning = "Structured long documents detected"
    elif total_docs > 3:
        strategy = "hybrid"
        reasoning = "Multiple documents, using comprehensive approach"
    else:
        strategy = "semantic"
        reasoning = "General content, using semantic matching"

    return {
        "strategy": strategy,
        "reasoning": reasoning,
        "analysis": {
            "total_docs": total_docs,
            "technical_ratio": technical_count / total_docs,
            "structured_ratio": structured_count / total_docs,
            "avg_length": avg_length
        },
        "documents": documents
    }

result = {"analysis_result": analyze_documents(documents)}
"""
        },
    )

    # Add strategy router
    router_id = builder.add_node(
        "SwitchNode",
        node_id="strategy_router",
        config={
            "condition_field": "analysis_result.strategy",
            "routes": {
                "semantic": "semantic_rag",
                "statistical": "statistical_rag",
                "hybrid": "hybrid_rag",
                "hierarchical": "hierarchical_rag",
            },
        },
    )

    # Add RAG strategies
    config = RAGConfig(chunk_size=400, retrieval_k=2)

    semantic_id = builder.add_node(
        "SemanticRAGNode", node_id="semantic_rag", config={"config": config}
    )

    statistical_id = builder.add_node(
        "StatisticalRAGNode", node_id="statistical_rag", config={"config": config}
    )

    hybrid_id = builder.add_node(
        "HybridRAGNode", node_id="hybrid_rag", config={"config": config}
    )

    hierarchical_id = builder.add_node(
        "HierarchicalRAGNode", node_id="hierarchical_rag", config={"config": config}
    )

    # Add result aggregator
    aggregator_id = builder.add_node(
        "PythonCodeNode",
        node_id="result_aggregator",
        config={
            "code": """
result = {
    "strategy_used": analysis_result["strategy"],
    "reasoning": analysis_result["reasoning"],
    "document_analysis": analysis_result["analysis"],
    "rag_results": rag_results,
    "success": len(rag_results.get("results", [])) > 0
}
"""
        },
    )

    # Connect workflow
    builder.add_connection(analyzer_id, "result", router_id, "input")
    builder.add_connection(router_id, semantic_id, route="semantic")
    builder.add_connection(router_id, statistical_id, route="statistical")
    builder.add_connection(router_id, hybrid_id, route="hybrid")
    builder.add_connection(router_id, hierarchical_id, route="hierarchical")

    # Connect all strategies to aggregator
    builder.add_connection(semantic_id, "output", aggregator_id, "rag_results")
    builder.add_connection(statistical_id, "output", aggregator_id, "rag_results")
    builder.add_connection(hybrid_id, "output", aggregator_id, "rag_results")
    builder.add_connection(hierarchical_id, "output", aggregator_id, "rag_results")
    builder.add_connection(analyzer_id, "result", aggregator_id, "analysis_result")

    # Build and run workflow
    workflow = builder.build(name="conditional_rag_workflow")
    runtime = LocalRuntime(enable_async=True)

    print("🚀 Running conditional RAG workflow...")

    try:
        result = await runtime.run_workflow(
            workflow, input_data={"documents": documents}
        )

        print("✅ Workflow completed successfully!")
        print(f"   Strategy selected: {result.get('strategy_used')}")
        print(f"   Reasoning: {result.get('reasoning')}")
        print(
            f"   Documents analyzed: {result.get('document_analysis', {}).get('total_docs')}"
        )
        print(f"   Success: {result.get('success')}")

    except Exception as e:
        print(f"❌ Workflow failed: {e}")


async def example_3_llm_driven_routing():
    """Example 3: LLM-driven intelligent RAG strategy routing"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: LLM-Driven Intelligent Routing")
    print("=" * 80)

    documents = create_sample_documents()

    # Create LLM-powered RAG router
    rag_router = RAGStrategyRouterNode("smart_rag_router")

    print("🤖 Using LLM to analyze documents and select optimal RAG strategy...")

    try:
        # Get strategy recommendation
        routing_result = await rag_router.execute(
            documents=documents,
            query="How do I implement and evaluate machine learning models?",
            user_preferences={"priority": "accuracy", "domain": "machine_learning"},
        )

        recommended_strategy = routing_result.get("strategy")
        reasoning = routing_result.get("reasoning")
        confidence = routing_result.get("confidence")

        print("✅ LLM Analysis Complete!")
        print(f"   Recommended strategy: {recommended_strategy}")
        print(f"   Reasoning: {reasoning}")
        print(f"   Confidence: {confidence:.2f}")
        print(
            f"   Documents analyzed: {routing_result.get('routing_metadata', {}).get('documents_count')}"
        )

        # Create and use recommended strategy
        registry = RAGWorkflowRegistry()
        strategy_node = registry.create_strategy(recommended_strategy)

        print(f"\n🎯 Executing {recommended_strategy} strategy...")

        # Index and retrieve
        index_result = await strategy_node.execute(
            documents=documents, operation="index"
        )
        retrieval_result = await strategy_node.execute(
            query="How do I implement and evaluate machine learning models?",
            operation="retrieve",
        )

        print("✅ Strategy execution completed!")
        print(f"   Indexed: {index_result.get('status')}")
        print(f"   Retrieved: {len(retrieval_result.get('results', []))} results")

        # Show results
        results = retrieval_result.get("results", [])
        scores = retrieval_result.get("scores", [])

        for i, (result, score) in enumerate(zip(results[:2], scores[:2])):
            print(f"   Result {i+1}: {result.get('title')} (score: {score:.3f})")

    except Exception as e:
        print(f"❌ LLM routing failed: {e}")


async def example_4_adaptive_workflow():
    """Example 4: Using AdaptiveRAGWorkflowNode for fully automated optimization"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Adaptive RAG Workflow with Full Automation")
    print("=" * 80)

    documents = create_sample_documents()

    # Create adaptive RAG workflow
    adaptive_rag = AdaptiveRAGWorkflowNode(
        name="adaptive_rag_system", llm_model="gpt-4"
    )

    print("🧠 Running adaptive RAG workflow with AI-driven optimization...")

    try:
        # Let the adaptive system handle everything
        result = await adaptive_rag.execute(
            documents=documents,
            query="Explain machine learning implementation best practices",
        )

        print("✅ Adaptive RAG completed!")
        print(f"   Strategy used: {result.get('strategy_used')}")
        print(f"   LLM reasoning: {result.get('llm_reasoning')}")
        print(f"   Confidence: {result.get('confidence'):.2f}")
        print(f"   Results count: {len(result.get('results', {}).get('results', []))}")

        # Show document analysis
        doc_analysis = result.get("document_analysis", {})
        print("   Document analysis:")
        print(f"     - Count: {doc_analysis.get('count')}")
        print(f"     - Avg length: {doc_analysis.get('avg_length')}")
        print(f"     - Content types: {doc_analysis.get('content_types')}")

        # Show adaptive metadata
        metadata = result.get("adaptive_metadata", {})
        print("   Adaptive metadata:")
        print(f"     - LLM model: {metadata.get('llm_model_used')}")
        print(f"     - Selection method: {metadata.get('strategy_selection_method')}")
        print(f"     - Fallback available: {metadata.get('fallback_available')}")

    except Exception as e:
        print(f"❌ Adaptive workflow failed: {e}")


async def example_5_performance_monitoring():
    """Example 5: Performance monitoring and quality analysis"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Performance Monitoring and Quality Analysis")
    print("=" * 80)

    documents = create_sample_documents()

    # Create monitoring components
    quality_analyzer = RAGQualityAnalyzerNode("quality_analyzer")
    performance_monitor = RAGPerformanceMonitorNode("performance_monitor")

    # Create different strategies for comparison
    strategies = {
        "semantic": SemanticRAGNode("semantic", RAGConfig(retrieval_k=3)),
        "hybrid": HybridRAGNode("hybrid", RAGConfig(retrieval_k=3)),
    }

    queries = [
        "How to train machine learning models?",
        "What are the best practices for data preparation?",
        "Show me Python code for model evaluation",
    ]

    print("📊 Running performance comparison across strategies...")

    strategy_results = {}

    for strategy_name, strategy_node in strategies.items():
        print(f"\n--- Testing {strategy_name.upper()} Strategy ---")

        try:
            # Index documents
            await strategy_node.execute(documents=documents, operation="index")

            strategy_performance = []

            for query in queries:
                import time

                start_time = time.time()

                # Retrieve results
                rag_result = await strategy_node.execute(
                    query=query, operation="retrieve"
                )

                execution_time = time.time() - start_time

                # Analyze quality
                quality_result = await quality_analyzer.execute(
                    rag_results=rag_result, query=query
                )

                # Monitor performance
                performance_result = await performance_monitor.execute(
                    rag_results=rag_result,
                    execution_time=execution_time,
                    strategy_used=strategy_name,
                    query_type="technical" if "code" in query.lower() else "general",
                )

                strategy_performance.append(
                    {
                        "query": query,
                        "quality_score": quality_result.get("quality_score"),
                        "execution_time": execution_time,
                        "result_count": len(rag_result.get("results", [])),
                        "passed_quality": quality_result.get("passed_quality_check"),
                        "recommendations": quality_result.get("recommendations", []),
                    }
                )

                print(f"   Query: {query[:40]}...")
                print(f"   Quality score: {quality_result.get('quality_score'):.3f}")
                print(f"   Execution time: {execution_time:.3f}s")
                print(
                    f"   Passed quality: {quality_result.get('passed_quality_check')}"
                )

            strategy_results[strategy_name] = strategy_performance

        except Exception as e:
            print(f"❌ Error testing {strategy_name}: {e}")

    # Performance comparison
    print("\n📈 PERFORMANCE COMPARISON:")
    for strategy_name, performance_data in strategy_results.items():
        avg_quality = sum(p["quality_score"] for p in performance_data) / len(
            performance_data
        )
        avg_time = sum(p["execution_time"] for p in performance_data) / len(
            performance_data
        )
        pass_rate = sum(1 for p in performance_data if p["passed_quality"]) / len(
            performance_data
        )

        print(f"   {strategy_name.upper()}:")
        print(f"     - Avg Quality Score: {avg_quality:.3f}")
        print(f"     - Avg Execution Time: {avg_time:.3f}s")
        print(f"     - Quality Pass Rate: {pass_rate:.1%}")


async def example_6_registry_usage():
    """Example 6: Using RAG Registry for discovery and recommendations"""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: RAG Registry for Discovery and Recommendations")
    print("=" * 80)

    registry = RAGWorkflowRegistry()

    # List available components
    print("📚 Available RAG Strategies:")
    strategies = registry.list_strategies()
    for name, info in strategies.items():
        print(f"   {name}: {info['description']}")
        print(f"     Use cases: {', '.join(info['use_cases'])}")
        print(
            f"     Performance: Speed={info['performance']['speed']}, "
            f"Accuracy={info['performance']['accuracy']}"
        )

    print("\n🔧 Available RAG Workflows:")
    workflows = registry.list_workflows()
    for name, info in workflows.items():
        print(f"   {name}: {info['description']}")
        print(f"     Complexity: {info['complexity']}")
        print(f"     Features: {', '.join(info['features'])}")

    # Get recommendations
    print("\n🎯 Getting Recommendations:")

    # Scenario 1: Technical documentation
    tech_recommendation = registry.recommend_strategy(
        document_count=50,
        avg_document_length=1200,
        is_technical=True,
        has_structure=True,
        query_type="technical",
        performance_priority="accuracy",
    )

    print("   Technical Documentation Scenario:")
    print(f"     Recommended: {tech_recommendation['recommended_strategy']}")
    print(f"     Reasoning: {tech_recommendation['reasoning']}")
    print(f"     Confidence: {tech_recommendation['confidence']:.2f}")

    # Scenario 2: General content
    general_recommendation = registry.recommend_strategy(
        document_count=20,
        avg_document_length=800,
        is_technical=False,
        has_structure=False,
        query_type="conceptual",
        performance_priority="speed",
    )

    print("   General Content Scenario:")
    print(f"     Recommended: {general_recommendation['recommended_strategy']}")
    print(f"     Reasoning: {general_recommendation['reasoning']}")
    print(f"     Confidence: {general_recommendation['confidence']:.2f}")

    # Workflow recommendations
    workflow_rec = registry.recommend_workflow(
        user_level="intermediate",
        use_case="production",
        needs_customization=True,
        needs_monitoring=True,
    )

    print("   Production Workflow Scenario:")
    print(f"     Recommended: {workflow_rec['recommended_workflow']}")
    print(f"     Reasoning: {workflow_rec['reasoning']}")
    print(f"     Suggested utilities: {', '.join(workflow_rec['suggested_utilities'])}")

    # Create recommended components
    print("\n🏗️ Creating Recommended Components:")

    try:
        # Create strategy
        strategy = registry.create_strategy(tech_recommendation["recommended_strategy"])
        print(f"   ✅ Created {tech_recommendation['recommended_strategy']} strategy")

        # Create workflow
        workflow = registry.create_workflow(workflow_rec["recommended_workflow"])
        print(f"   ✅ Created {workflow_rec['recommended_workflow']} workflow")

        # Create utilities
        for utility in workflow_rec["suggested_utilities"]:
            utility_instance = registry.create_utility(utility)
            print(f"   ✅ Created {utility} utility")

    except Exception as e:
        print(f"   ❌ Error creating components: {e}")


async def main():
    """Run all RAG toolkit examples"""
    print("🚀 RAG Toolkit Comprehensive Examples")
    print("=" * 80)
    print("This example demonstrates the complete RAG toolkit capabilities:")
    print("- Individual strategy usage")
    print("- Workflow integration with conditional routing")
    print("- LLM-driven intelligent strategy selection")
    print("- Adaptive workflows with full automation")
    print("- Performance monitoring and quality analysis")
    print("- Registry-based discovery and recommendations")

    # Run all examples
    examples = [
        example_1_basic_strategy_usage,
        example_2_workflow_integration,
        example_3_llm_driven_routing,
        example_4_adaptive_workflow,
        example_5_performance_monitoring,
        example_6_registry_usage,
    ]

    for i, example in enumerate(examples, 1):
        try:
            await example()
        except Exception as e:
            print(f"\n❌ Example {i} failed: {e}")

    print("\n" + "=" * 80)
    print("🎉 RAG Toolkit Examples Complete!")
    print("=" * 80)
    print("\nKey Takeaways:")
    print("1. ✅ Multiple RAG strategies available for different use cases")
    print("2. ✅ Seamless integration into workflows with conditional routing")
    print("3. ✅ LLM-powered intelligent strategy selection")
    print("4. ✅ Fully automated adaptive workflows")
    print("5. ✅ Comprehensive monitoring and quality analysis")
    print("6. ✅ Easy discovery and recommendations via registry")
    print("\nNext Steps:")
    print("- Explore individual strategy parameters for fine-tuning")
    print("- Integrate RAG into your specific workflows")
    print("- Use adaptive workflows for optimal performance")
    print("- Monitor and optimize based on quality metrics")


if __name__ == "__main__":
    asyncio.run(main())
