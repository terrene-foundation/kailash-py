#!/usr/bin/env python3
"""
Advanced RAG Techniques Example

Demonstrates cutting-edge RAG implementations including:
- Self-Correcting RAG with verification and iterative refinement
- RAG-Fusion with multi-query approach and result fusion
- HyDE (Hypothetical Document Embeddings) for improved matching
- Step-Back prompting for abstract reasoning and background context

These techniques represent the state-of-the-art in RAG research (2024).
"""

import asyncio
import logging
from typing import Any, Dict, List

from kailash.runtime.local import LocalRuntime
from kaizen.nodes.rag import (
    HyDENode,
    RAGConfig,
    RAGFusionNode,
    RAGQualityAnalyzerNode,
    SelfCorrectingRAGNode,
    StepBackRAGNode,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_comprehensive_test_documents() -> List[Dict[str, Any]]:
    """Create diverse documents for testing advanced RAG techniques"""

    documents = [
        {
            "id": "doc_1_ml_intro",
            "title": "Introduction to Machine Learning",
            "content": """Machine learning is a powerful subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed for every task. The fundamental principle behind machine learning is pattern recognition - algorithms analyze data to identify patterns, relationships, and trends that can be used to make predictions or decisions about new, unseen data.

There are three main types of machine learning: supervised learning, where algorithms learn from labeled training data; unsupervised learning, where patterns are discovered in data without labels; and reinforcement learning, where agents learn through interaction with an environment via rewards and penalties.

The machine learning process typically involves several key steps: data collection and preprocessing, feature selection and engineering, model selection and training, evaluation and validation, and finally deployment and monitoring. Each step is crucial for building effective machine learning systems.

Common applications include image recognition, natural language processing, recommendation systems, fraud detection, autonomous vehicles, and medical diagnosis. The field has experienced explosive growth due to advances in computing power, the availability of large datasets, and improvements in algorithms, particularly deep learning techniques.""",
            "type": "educational",
            "domain": "machine_learning",
            "complexity": "intermediate",
        },
        {
            "id": "doc_2_neural_networks",
            "title": "Neural Network Architecture and Training",
            "content": """Neural networks are computational models inspired by the biological neural networks in animal brains. They consist of interconnected nodes (neurons) organized in layers: an input layer that receives data, one or more hidden layers that process information, and an output layer that produces results.

The training process involves forward propagation, where data flows through the network to generate predictions, and backpropagation, where errors are calculated and used to adjust the network's weights through gradient descent optimization. The goal is to minimize a loss function that measures the difference between predicted and actual outputs.

Key architectural components include activation functions (ReLU, sigmoid, tanh) that introduce non-linearity, weight initialization strategies that affect convergence, and regularization techniques (dropout, batch normalization) that prevent overfitting. Modern architectures include convolutional neural networks (CNNs) for image processing, recurrent neural networks (RNNs) for sequence data, and transformers for natural language processing.

Training considerations include choosing appropriate learning rates, batch sizes, and optimization algorithms (Adam, SGD, RMSprop). Hyperparameter tuning through techniques like grid search, random search, or Bayesian optimization is essential for achieving optimal performance.""",
            "type": "technical",
            "domain": "deep_learning",
            "complexity": "advanced",
        },
        {
            "id": "doc_3_python_implementation",
            "title": "Python Machine Learning Implementation Guide",
            "content": """
# Complete Python Implementation for Machine Learning

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns

class MLPipeline:
    def __init__(self, algorithm='random_forest'):
        self.algorithm = algorithm
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()

    def load_and_preprocess_data(self, file_path, target_column):
        '''Load data and perform preprocessing'''
        # Load dataset
        self.data = pd.read_csv(file_path)

        # Handle missing values
        self.data = self.data.fillna(self.data.mean(numeric_only=True))

        # Separate features and target
        X = self.data.drop(columns=[target_column])
        y = self.data[target_column]

        # Encode categorical variables
        for col in X.select_dtypes(include=['object']).columns:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42, stratify=y
        )

        return X_train, X_test, y_train, y_test

    def train_model(self, X_train, y_train):
        '''Train the selected model'''
        if self.algorithm == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
        elif self.algorithm == 'logistic_regression':
            self.model = LogisticRegression(
                random_state=42,
                max_iter=1000,
                solver='liblinear'
            )

        # Train model
        self.model.fit(X_train, y_train)

        return self.model

    def evaluate_model(self, X_test, y_test):
        '''Evaluate model performance'''
        predictions = self.model.predict(X_test)

        # Calculate metrics
        accuracy = accuracy_score(y_test, predictions)
        report = classification_report(y_test, predictions)
        cm = confusion_matrix(y_test, predictions)

        # Feature importance (for tree-based models)
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
        else:
            importances = None

        return {
            'accuracy': accuracy,
            'classification_report': report,
            'confusion_matrix': cm,
            'feature_importances': importances
        }

# Usage example
def main():
    # Initialize pipeline
    ml_pipeline = MLPipeline(algorithm='random_forest')

    # Load and preprocess data
    X_train, X_test, y_train, y_test = ml_pipeline.load_and_preprocess_data(
        'dataset.csv', 'target'
    )

    # Train model
    model = ml_pipeline.train_model(X_train, y_train)

    # Evaluate performance
    results = ml_pipeline.evaluate_model(X_test, y_test)

    print(f"Model Accuracy: {results['accuracy']:.4f}")
    print(f"Classification Report:\\n{results['classification_report']}")

if __name__ == "__main__":
    main()
""",
            "type": "code",
            "domain": "implementation",
            "complexity": "intermediate",
        },
        {
            "id": "doc_4_optimization",
            "title": "Optimization Algorithms in Machine Learning",
            "content": """Optimization algorithms are the backbone of machine learning, responsible for finding the best parameters that minimize loss functions. The choice of optimization algorithm significantly impacts model convergence speed, final performance, and training stability.

Gradient Descent is the fundamental optimization technique where parameters are updated in the direction opposite to the gradient of the loss function. The basic update rule is: θ = θ - α∇θJ(θ), where α is the learning rate and ∇θJ(θ) is the gradient of the loss function with respect to parameters θ.

Stochastic Gradient Descent (SGD) processes one sample at a time, providing faster updates but with higher variance. Mini-batch gradient descent balances computational efficiency and gradient estimate quality by processing small batches of data.

Advanced optimizers include Momentum, which accumulates gradients to accelerate convergence and reduce oscillations; Adam (Adaptive Moment Estimation), which adapts learning rates for each parameter using first and second moment estimates; RMSprop, which normalizes gradients by their recent magnitude; and AdaGrad, which adapts learning rates based on historical gradients.

Learning rate scheduling is crucial for optimal convergence. Techniques include step decay, exponential decay, cosine annealing, and adaptive scheduling based on validation performance. Proper initialization, regularization, and hyperparameter tuning are essential complementary strategies for effective optimization.""",
            "type": "technical",
            "domain": "optimization",
            "complexity": "advanced",
        },
        {
            "id": "doc_5_evaluation",
            "title": "Model Evaluation and Validation Strategies",
            "content": """Model evaluation is critical for assessing machine learning performance and ensuring generalization to unseen data. The evaluation strategy depends on the problem type, dataset characteristics, and business requirements.

For classification problems, key metrics include accuracy (correct predictions / total predictions), precision (true positives / (true positives + false positives)), recall (true positives / (true positives + false negatives)), and F1-score (harmonic mean of precision and recall). The confusion matrix provides detailed insight into classification performance across different classes.

Cross-validation techniques provide robust performance estimates by training and testing on different data subsets. K-fold cross-validation divides data into k folds, training on k-1 folds and testing on the remaining fold, repeating k times. Stratified k-fold maintains class distribution in each fold, while time series cross-validation respects temporal ordering.

For regression problems, common metrics include Mean Squared Error (MSE), Root Mean Squared Error (RMSE), Mean Absolute Error (MAE), and R-squared (coefficient of determination). Each metric emphasizes different aspects of prediction quality.

Validation strategies include holdout validation (simple train/test split), cross-validation for small datasets, and separate validation sets for hyperparameter tuning. Early stopping prevents overfitting by monitoring validation performance during training. Bootstrap sampling provides confidence intervals for performance estimates.""",
            "type": "technical",
            "domain": "evaluation",
            "complexity": "intermediate",
        },
        {
            "id": "doc_6_applications",
            "title": "Real-World Machine Learning Applications",
            "content": """Machine learning has transformed numerous industries and aspects of daily life through practical applications that solve real-world problems. Understanding these applications helps contextualize theoretical concepts and demonstrates the field's impact.

In healthcare, machine learning enables medical image analysis for detecting tumors, fractures, and diseases with accuracy often exceeding human radiologists. Drug discovery processes are accelerated through molecular property prediction and compound optimization. Electronic health records analysis supports personalized treatment recommendations and early disease detection.

Financial services leverage machine learning for fraud detection, algorithmic trading, credit scoring, and risk assessment. Real-time transaction monitoring identifies suspicious patterns, while robo-advisors provide automated investment management based on individual risk profiles and market conditions.

Technology companies use recommendation systems to personalize user experiences on platforms like Netflix, Amazon, and Spotify. These systems analyze user behavior, preferences, and item characteristics to suggest relevant content or products, significantly improving user engagement and satisfaction.

Transportation has been revolutionized by autonomous vehicles that use computer vision, sensor fusion, and decision-making algorithms to navigate complex environments. Route optimization algorithms minimize travel time and fuel consumption for logistics companies.

Natural language processing applications include machine translation, chatbots, sentiment analysis, and content generation. These systems power virtual assistants, automate customer service, and enable cross-language communication.

Manufacturing benefits from predictive maintenance that prevents equipment failures, quality control systems that detect defects, and supply chain optimization that reduces costs and improves efficiency.""",
            "type": "application",
            "domain": "real_world",
            "complexity": "beginner",
        },
    ]

    return documents


async def example_1_self_correcting_rag():
    """Example 1: Self-Correcting RAG with verification and refinement"""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Self-Correcting RAG with Verification")
    print("=" * 80)

    documents = create_comprehensive_test_documents()

    # Create self-correcting RAG node
    self_correcting_rag = SelfCorrectingRAGNode(
        name="self_correcting_rag",
        max_corrections=2,
        confidence_threshold=0.8,
        verification_model="gpt-4",
    )

    # Test with different query types
    test_queries = [
        "How do neural networks learn and what is backpropagation?",  # Well-covered topic
        "What are the latest quantum machine learning algorithms?",  # Poorly covered topic
        "Explain gradient descent optimization with mathematical details",  # Mixed coverage
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n--- Test Query {i}: {query} ---")

        try:
            result = await self_correcting_rag.execute(documents=documents, query=query)

            quality = result.get("quality_assessment", {})
            metadata = result.get("self_correction_metadata", {})

            print("✅ Self-correction completed!")
            print(f"   Final confidence: {quality.get('confidence', 0):.3f}")
            print(f"   Total attempts: {metadata.get('total_attempts', 1)}")
            print(f"   Status: {result.get('status', 'unknown')}")
            print(f"   Threshold met: {metadata.get('threshold_met', False)}")

            if quality.get("issues_found"):
                print(f"   Issues found: {len(quality.get('issues_found', []))}")

            if metadata.get("correction_history"):
                print("   Correction history:")
                for attempt in metadata["correction_history"]:
                    print(
                        f"     Attempt {attempt['attempt']}: confidence {attempt['confidence']:.3f}"
                    )

        except Exception as e:
            print(f"❌ Self-correcting RAG failed: {e}")

    print("\n🎯 Self-Correcting RAG demonstrates:")
    print("   - Automatic quality verification using LLM")
    print("   - Iterative refinement when confidence is low")
    print("   - Detailed tracking of correction attempts")
    print("   - Fallback to best attempt when threshold not met")


async def example_2_rag_fusion():
    """Example 2: RAG-Fusion with multi-query approach"""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: RAG-Fusion with Multi-Query Approach")
    print("=" * 80)

    documents = create_comprehensive_test_documents()

    # Create RAG-Fusion node
    rag_fusion = RAGFusionNode(
        name="rag_fusion",
        num_query_variations=3,
        fusion_method="rrf",
        query_generator_model="gpt-4",
    )

    # Test with queries that benefit from multiple perspectives
    test_queries = [
        "How to implement machine learning models?",
        "What are the best practices for neural network training?",
        "Explain optimization in machine learning",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n--- Fusion Test {i}: {query} ---")

        try:
            result = await rag_fusion.execute(documents=documents, query=query)

            metadata = result.get("fusion_metadata", {})
            variations = result.get("query_variations", [])

            print("✅ RAG-Fusion completed!")
            print(f"   Original query: {result.get('original_query')}")
            print("   Generated variations:")
            for j, variation in enumerate(variations, 1):
                print(f"     {j}. {variation}")

            print(f"   Fusion method: {metadata.get('fusion_method')}")
            print(f"   Queries processed: {metadata.get('queries_processed')}")
            print(f"   Unique documents: {metadata.get('total_unique_documents')}")
            print(
                f"   Score improvement: {metadata.get('fusion_score_improvement', 0):.1%}"
            )

            # Show query performance
            query_perfs = metadata.get("query_performances", [])
            if query_perfs:
                print("   Query performances:")
                for perf in query_perfs:
                    query_type = "Original" if perf.get("is_original") else "Variation"
                    results_count = perf.get("results_count", 0)
                    avg_score = perf.get("avg_score", 0)
                    print(
                        f"     {query_type}: {results_count} results, avg score {avg_score:.3f}"
                    )

        except Exception as e:
            print(f"❌ RAG-Fusion failed: {e}")

    print("\n🎯 RAG-Fusion demonstrates:")
    print("   - Automatic query variation generation")
    print("   - Reciprocal Rank Fusion for result combination")
    print("   - Improved recall and robustness to query phrasing")
    print("   - Detailed performance tracking per query")


async def example_3_hyde():
    """Example 3: HyDE (Hypothetical Document Embeddings)"""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: HyDE (Hypothetical Document Embeddings)")
    print("=" * 80)

    documents = create_comprehensive_test_documents()

    # Create HyDE node
    hyde = HyDENode(
        name="hyde_rag",
        hypothesis_model="gpt-4",
        use_multiple_hypotheses=True,
        num_hypotheses=2,
    )

    # Test with complex analytical queries where query-document gap is large
    test_queries = [
        "What are the theoretical foundations behind machine learning optimization?",
        "How do different neural network architectures compare in terms of computational efficiency?",
        "What are the trade-offs between different evaluation metrics in machine learning?",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n--- HyDE Test {i}: {query} ---")

        try:
            result = await hyde.execute(documents=documents, query=query)

            hypotheses = result.get("hypotheses_generated", [])
            metadata = result.get("hyde_metadata", {})

            print("✅ HyDE completed!")
            print(f"   Original query: {result.get('original_query')}")
            print("   Generated hypotheses:")
            for j, hypothesis in enumerate(hypotheses, 1):
                truncated = (
                    hypothesis[:150] + "..." if len(hypothesis) > 150 else hypothesis
                )
                print(f"     {j}. {truncated}")

            print(f"   Hypotheses generated: {metadata.get('num_hypotheses')}")
            print(f"   Successful retrievals: {metadata.get('successful_retrievals')}")
            print(f"   Total unique docs: {metadata.get('total_unique_docs')}")

            # Show hypothesis performance
            hypothesis_results = result.get("hypothesis_results", [])
            print("   Hypothesis performances:")
            for h_result in hypothesis_results:
                if "error" not in h_result:
                    retrieval = h_result.get("retrieval_result", {})
                    results_count = len(retrieval.get("results", []))
                    print(
                        f"     Hypothesis {h_result.get('hypothesis_index', 0) + 1}: {results_count} documents"
                    )
                else:
                    print(
                        f"     Hypothesis {h_result.get('hypothesis_index', 0) + 1}: Error occurred"
                    )

        except Exception as e:
            print(f"❌ HyDE failed: {e}")

    print("\n🎯 HyDE demonstrates:")
    print("   - Hypothetical answer generation for better matching")
    print("   - Answer-to-document similarity vs query-to-document")
    print("   - Effective for complex analytical questions")
    print("   - Multiple hypotheses for comprehensive coverage")


async def example_4_step_back_rag():
    """Example 4: Step-Back RAG with abstract reasoning"""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Step-Back RAG with Abstract Reasoning")
    print("=" * 80)

    documents = create_comprehensive_test_documents()

    # Create Step-Back RAG node
    step_back_rag = StepBackRAGNode(name="step_back_rag", abstraction_model="gpt-4")

    # Test with specific queries that benefit from background context
    test_queries = [
        "How does the Adam optimizer compare to SGD in neural network training?",
        "What makes convolutional neural networks effective for image recognition?",
        "Why is cross-validation important in machine learning model evaluation?",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n--- Step-Back Test {i}: {query} ---")

        try:
            result = await step_back_rag.execute(documents=documents, query=query)

            specific_query = result.get("specific_query")
            abstract_query = result.get("abstract_query")
            metadata = result.get("step_back_metadata", {})

            print("✅ Step-Back RAG completed!")
            print(f"   Specific query: {specific_query}")
            print(f"   Abstract query: {abstract_query}")
            print(
                f"   Abstraction successful: {metadata.get('abstraction_successful')}"
            )

            # Show retrieval breakdown
            print("   Retrieval breakdown:")
            print(f"     Specific docs: {metadata.get('specific_docs_count')}")
            print(f"     Abstract docs: {metadata.get('abstract_docs_count')}")
            print(f"     Combined total: {metadata.get('combined_docs_count')}")

            # Show combined results structure
            combined = result.get("combined_results", {})
            source_breakdown = combined.get("source_breakdown", {})
            if source_breakdown:
                print("   Source breakdown:")
                print(
                    f"     Specific sources: {source_breakdown.get('specific_count')}"
                )
                print(
                    f"     Abstract sources: {source_breakdown.get('abstract_count')}"
                )
                print(f"     Total unique: {source_breakdown.get('total_unique')}")

                weights = source_breakdown.get("weights_used", {})
                print(
                    f"     Weights - specific: {weights.get('specific', 0):.1f}, abstract: {weights.get('abstract', 0):.1f}"
                )

        except Exception as e:
            print(f"❌ Step-Back RAG failed: {e}")

    print("\n🎯 Step-Back RAG demonstrates:")
    print("   - Abstract query generation for background context")
    print("   - Weighted combination of specific and abstract results")
    print("   - Better reasoning through foundational knowledge")
    print("   - Comprehensive answers with context and specifics")


async def example_5_comparative_analysis():
    """Example 5: Comparative analysis of all advanced techniques"""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Comparative Analysis of Advanced RAG Techniques")
    print("=" * 80)

    documents = create_comprehensive_test_documents()

    # Create all advanced RAG nodes
    techniques = {
        "Self-Correcting": SelfCorrectingRAGNode(
            max_corrections=1, confidence_threshold=0.7
        ),
        "RAG-Fusion": RAGFusionNode(num_query_variations=2, fusion_method="rrf"),
        "HyDE": HyDENode(use_multiple_hypotheses=False, num_hypotheses=1),
        "Step-Back": StepBackRAGNode(),
    }

    # Quality analyzer for comparison
    quality_analyzer = RAGQualityAnalyzerNode()

    # Test query that challenges different aspects
    test_query = "How can I optimize neural network training for better performance?"

    print(f"📊 Comparing techniques with query: '{test_query}'")

    results_comparison = {}

    for technique_name, rag_node in techniques.items():
        print(f"\n--- Testing {technique_name} ---")

        try:
            import time

            start_time = time.time()

            # Execute technique
            result = await rag_node.execute(documents=documents, query=test_query)

            execution_time = time.time() - start_time

            # Analyze quality
            quality_result = await quality_analyzer.execute(
                rag_results=result, query=test_query
            )

            # Extract key metrics
            results_comparison[technique_name] = {
                "execution_time": execution_time,
                "quality_score": quality_result.get("quality_score", 0),
                "passed_quality": quality_result.get("passed_quality_check", False),
                "recommendations": quality_result.get("recommendations", []),
                "unique_features": get_technique_features(technique_name, result),
            }

            print(f"   ✅ Completed in {execution_time:.2f}s")
            print(f"   Quality score: {quality_result.get('quality_score', 0):.3f}")
            print(
                f"   Passed quality check: {quality_result.get('passed_quality_check', False)}"
            )

        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results_comparison[technique_name] = {
                "execution_time": 0,
                "quality_score": 0,
                "passed_quality": False,
                "error": str(e),
            }

    # Summary comparison
    print("\n📈 TECHNIQUE COMPARISON SUMMARY:")
    print(
        f"{'Technique':<15} {'Time (s)':<10} {'Quality':<10} {'Passed':<8} {'Key Features'}"
    )
    print("-" * 80)

    for technique, metrics in results_comparison.items():
        if "error" not in metrics:
            time_str = f"{metrics['execution_time']:.2f}"
            quality_str = f"{metrics['quality_score']:.3f}"
            passed_str = "✅" if metrics["passed_quality"] else "❌"
            features = ", ".join(metrics.get("unique_features", [])[:2])

            print(
                f"{technique:<15} {time_str:<10} {quality_str:<10} {passed_str:<8} {features}"
            )
        else:
            print(
                f"{technique:<15} {'ERROR':<10} {'0.000':<10} {'❌':<8} Error occurred"
            )

    # Best technique recommendation
    successful_techniques = {
        k: v for k, v in results_comparison.items() if "error" not in v
    }
    if successful_techniques:
        best_technique = max(
            successful_techniques.items(), key=lambda x: x[1]["quality_score"]
        )
        print(f"\n🏆 Best performing technique: {best_technique[0]}")
        print(f"   Quality score: {best_technique[1]['quality_score']:.3f}")
        print(f"   Execution time: {best_technique[1]['execution_time']:.2f}s")


def get_technique_features(technique_name: str, result: Dict[str, Any]) -> List[str]:
    """Extract unique features for each technique"""
    if technique_name == "Self-Correcting":
        metadata = result.get("self_correction_metadata", {})
        features = [f"{metadata.get('total_attempts', 1)} attempts"]
        if metadata.get("threshold_met"):
            features.append("threshold met")
        return features

    elif technique_name == "RAG-Fusion":
        metadata = result.get("fusion_metadata", {})
        features = [f"{metadata.get('queries_processed', 0)} queries"]
        improvement = metadata.get("fusion_score_improvement", 0)
        if improvement > 0:
            features.append(f"+{improvement:.1%} improvement")
        return features

    elif technique_name == "HyDE":
        metadata = result.get("hyde_metadata", {})
        features = [f"{metadata.get('num_hypotheses', 0)} hypotheses"]
        if metadata.get("successful_retrievals", 0) > 0:
            features.append("hypothesis-based")
        return features

    elif technique_name == "Step-Back":
        metadata = result.get("step_back_metadata", {})
        features = ["abstract reasoning"]
        if metadata.get("abstraction_successful"):
            features.append("background context")
        return features

    return ["advanced technique"]


async def main():
    """Run all advanced RAG technique examples"""
    print("🚀 Advanced RAG Techniques Demonstration")
    print("=" * 80)
    print("Showcasing cutting-edge RAG implementations from 2024 research:")
    print("- Self-Correcting RAG with iterative refinement")
    print("- RAG-Fusion with multi-query approach")
    print("- HyDE for hypothetical document embeddings")
    print("- Step-Back prompting for abstract reasoning")

    # Run all examples
    examples = [
        example_1_self_correcting_rag,
        example_2_rag_fusion,
        example_3_hyde,
        example_4_step_back_rag,
        example_5_comparative_analysis,
    ]

    for i, example in enumerate(examples, 1):
        try:
            await example()
        except Exception as e:
            print(f"\n❌ Example {i} failed: {e}")
            logger.exception(f"Example {i} failed")

    print("\n" + "=" * 80)
    print("🎉 Advanced RAG Techniques Demonstration Complete!")
    print("=" * 80)
    print("\nKey Innovations Demonstrated:")
    print("1. ✅ Self-verification and iterative correction")
    print("2. ✅ Multi-query fusion for improved recall")
    print("3. ✅ Hypothetical answer-based retrieval")
    print("4. ✅ Abstract reasoning with background context")
    print("5. ✅ Comprehensive quality analysis and comparison")
    print("\nThese techniques represent the state-of-the-art in RAG research,")
    print(
        "providing significant improvements in accuracy, robustness, and reasoning capability."
    )


if __name__ == "__main__":
    asyncio.run(main())
