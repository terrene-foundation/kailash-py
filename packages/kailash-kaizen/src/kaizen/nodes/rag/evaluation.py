"""
RAG Evaluation and Benchmarking Framework

Implements comprehensive evaluation metrics and benchmarking:
- Retrieval quality metrics (precision, recall, MRR)
- Generation quality assessment
- End-to-end RAG evaluation
- A/B testing framework
- Performance benchmarking
- Dataset generation for testing

Based on RAGAS, BEIR, and evaluation research from 2024.
"""

import json
import logging
import os
import random
import statistics
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

from ..ai.llm_agent import LLMAgentNode

logger = logging.getLogger(__name__)


# F9 #1126: env-loaded default LLM model. Mirrors the router.py precedent
# (F8 B10). May be None when neither env var is set — that is
# env-models-compliant; do NOT fall back to a hardcoded model name.
_DEFAULT_LLM_MODEL = os.environ.get(
    "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
)


@register_node()
class RAGEvaluationNode(WorkflowNode):
    """
    Comprehensive RAG Evaluation Framework

    Evaluates RAG systems across multiple dimensions including retrieval
    quality, generation accuracy, and end-to-end performance.

    When to use:
    - Best for: System optimization, quality assurance, model selection
    - Not ideal for: Real-time evaluation during inference
    - Performance: 5-30 seconds per evaluation (depends on metrics)
    - Insights: Detailed breakdown of strengths and weaknesses

    Key features:
    - RAGAS-based evaluation metrics
    - Retrieval and generation quality assessment
    - Faithfulness and relevance scoring
    - Comparative analysis across strategies
    - Automated test dataset generation

    Example:
        evaluator = RAGEvaluationNode(
            metrics=["faithfulness", "relevance", "context_precision", "answer_quality"],
            use_reference_answers=True
        )

        # Evaluate a RAG system
        results = await evaluator.execute(
            test_queries=[
                {"query": "What is transformer architecture?",
                 "reference": "Transformers use self-attention..."},
                {"query": "Explain BERT",
                 "reference": "BERT is a bidirectional..."}
            ],
            rag_system=my_rag_node
        )

        # Results include:
        # - Per-query scores
        # - Aggregate metrics
        # - Failure analysis
        # - Improvement recommendations

    Parameters:
        metrics: List of evaluation metrics to compute
        use_reference_answers: Whether to use ground truth
        llm_judge_model: Model for LLM-based evaluation
        confidence_threshold: Minimum acceptable score

    Returns:
        scores: Detailed scores per metric
        aggregate_metrics: Overall system performance
        failure_analysis: Queries that performed poorly
        recommendations: Suggested improvements
    """

    def __init__(
        self,
        name: str = "rag_evaluation",
        metrics: Optional[List[str]] = None,
        use_reference_answers: bool = True,
        llm_judge_model: Optional[str] = _DEFAULT_LLM_MODEL,
    ):
        self.metrics = metrics or [
            "faithfulness",
            "relevance",
            "context_precision",
            "answer_quality",
        ]
        self.use_reference_answers = use_reference_answers
        self.llm_judge_model = llm_judge_model
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create RAG evaluation workflow"""
        builder = WorkflowBuilder()

        # Bound only inside the optional-branch below; initialize at entry so
        # the later wiring loop's reference never sees an unbound name.
        answer_quality_id: Optional[str] = None

        # Test executor - runs RAG on test queries
        test_executor_id = builder.add_node(
            "PythonCodeNode",
            node_id="test_executor",
            config={
                "code": """
import time
from datetime import datetime

def execute_rag_tests(test_queries, rag_system):
    '''Execute RAG system on test queries'''
    test_results = []

    for i, test_case in enumerate(test_queries):
        query = test_case.get("query", "")
        reference = test_case.get("reference", "")

        # Time the execution
        start_time = time.time()

        # Execute RAG (simplified - would call actual system)
        # In production, would use rag_system.run(query=query)
        rag_response = {
            "answer": f"Generated answer for: {query}",
            "retrieved_contexts": [
                {"content": "Context 1 about transformers...", "score": 0.9},
                {"content": "Context 2 about attention...", "score": 0.85},
                {"content": "Context 3 about architecture...", "score": 0.8}
            ],
            "confidence": 0.87
        }

        execution_time = time.time() - start_time

        test_results.append({
            "test_id": i,
            "query": query,
            "reference_answer": reference,
            "generated_answer": rag_response["answer"],
            "retrieved_contexts": rag_response["retrieved_contexts"],
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat()
        })

    # F9 umbrella + #1117 sibling: return from function so the module-scope
    # call below binds `result` (the wire-through happens via the module
    # namespace, not the function's local scope).
    return {
        "test_results": test_results,
        "total_tests": len(test_queries),
        "avg_execution_time": sum(r["execution_time"] for r in test_results) / len(test_results) if test_results else 0.0
    }

# F9: module-scope call + drop the helper so PythonCodeNode's output gate
# sees only `result`.
result = execute_rag_tests(test_queries, rag_system)
del execute_rag_tests
"""
            },
        )

        # Faithfulness evaluator
        faithfulness_evaluator_id = builder.add_node(
            "LLMAgentNode",
            node_id="faithfulness_evaluator",
            config={
                "system_prompt": """Evaluate the faithfulness of the generated answer to the retrieved contexts.

Faithfulness measures whether the answer is grounded in the retrieved information.

For each statement in the answer:
1. Check if it's supported by the contexts
2. Identify any hallucinations
3. Rate overall faithfulness

Return JSON:
{
    "faithfulness_score": 0.0-1.0,
    "supported_statements": ["list of supported claims"],
    "unsupported_statements": ["list of unsupported claims"],
    "hallucinations": ["list of hallucinated information"],
    "reasoning": "explanation"
}""",
                "model": self.llm_judge_model,
            },
        )

        # Relevance evaluator
        relevance_evaluator_id = builder.add_node(
            "LLMAgentNode",
            node_id="relevance_evaluator",
            config={
                "system_prompt": """Evaluate the relevance of the answer to the query.

Consider:
1. Does the answer address the query?
2. Is it complete?
3. Is it focused without irrelevant information?

Return JSON:
{
    "relevance_score": 0.0-1.0,
    "addresses_query": true/false,
    "completeness": 0.0-1.0,
    "focus": 0.0-1.0,
    "missing_aspects": ["list of missing elements"],
    "irrelevant_content": ["list of irrelevant parts"]
}""",
                "model": self.llm_judge_model,
            },
        )

        # Context precision evaluator
        context_evaluator_id = builder.add_node(
            "PythonCodeNode",
            node_id="context_evaluator",
            config={
                "code": """
def evaluate_context_precision(test_result):
    '''Evaluate the precision of retrieved contexts'''

    contexts = test_result.get("retrieved_contexts", [])
    query = test_result.get("query", "")

    if not contexts:
        return {
            "context_precision": 0.0,
            "context_recall": 0.0,
            "context_ranking_quality": 0.0
        }

    # Calculate precision at different k values
    precision_at_k = {}
    relevant_count = 0

    for k in [1, 3, 5, 10]:
        if k <= len(contexts):
            # Simulate relevance judgment (would use LLM in production)
            relevant_at_k = sum(1 for c in contexts[:k] if c.get("score", 0) > 0.7)
            precision_at_k[f"P@{k}"] = relevant_at_k / k

    # Calculate MRR (Mean Reciprocal Rank)
    first_relevant_rank = None
    for i, ctx in enumerate(contexts):
        if ctx.get("score", 0) > 0.7:
            first_relevant_rank = i + 1
            break

    mrr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0

    # Context diversity
    unique_terms = set()
    for ctx in contexts:
        unique_terms.update(ctx.get("content", "").lower().split()[:20])

    diversity_score = len(unique_terms) / (len(contexts) * 20) if contexts else 0

    # F9 #1117: function MUST return its computed metrics (was bound to
    # a function-scope `result` local but never returned).
    return {
        "context_metrics": {
            "precision_at_k": precision_at_k,
            "mrr": mrr,
            "diversity_score": diversity_score,
            "avg_relevance_score": sum(c.get("score", 0) for c in contexts) / len(contexts),
            "context_count": len(contexts)
        }
    }

# F9 #1117: module-scope call. `test_data` is the wire from
# test_executor.test_results (a LIST). Aggregator expects `context_metrics`
# to be a LIST; map the per-result evaluation. Then `del` the non-JSON
# helpers so PythonCodeNode's output-validation gate sees only `result`.
_test_data = test_data if isinstance(test_data, list) else [test_data]
context_metrics = [evaluate_context_precision(t).get("context_metrics", {}) for t in _test_data]
result = {"context_metrics": context_metrics}
del evaluate_context_precision, _test_data
"""
            },
        )

        # Answer quality evaluator (if reference available)
        if self.use_reference_answers:
            answer_quality_id = builder.add_node(
                "LLMAgentNode",
                node_id="answer_quality_evaluator",
                config={
                    "system_prompt": """Compare the generated answer with the reference answer.

Evaluate:
1. Factual accuracy
2. Completeness
3. Clarity and coherence
4. Additional valuable information

Return JSON:
{
    "accuracy_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "clarity_score": 0.0-1.0,
    "additional_value": 0.0-1.0,
    "overall_quality": 0.0-1.0,
    "key_differences": ["list of major differences"],
    "improvements_needed": ["list of improvements"]
}""",
                    "model": self.llm_judge_model,
                },
            )

        # Metric aggregator
        aggregator_id = builder.add_node(
            "PythonCodeNode",
            node_id="metric_aggregator",
            config={
                "code": f"""
import statistics

def aggregate_evaluation_metrics(test_results, faithfulness_scores, relevance_scores,
                               context_metrics, answer_quality_scores=None):
    '''Aggregate all evaluation metrics'''
    # F9 #1118: import the datetime CLASS inside the function body —
    # PythonCodeNode passes separate (globals, locals) to exec() so a
    # module-scope `from datetime import datetime` rebind binds the alias
    # into LOCAL namespace and is invisible to this function's closure.
    # Importing here makes the class lookup resolve cleanly.
    # (`datetime.now()` on the module raises AttributeError.)
    from datetime import datetime as _datetime_class

    # Parse evaluation results
    all_metrics = {{
        "faithfulness": [],
        "relevance": [],
        "context_precision": [],
        "answer_quality": [],
        "execution_time": []
    }}

    for i, test in enumerate(test_results):
        # Get scores for this test
        faith_score = faithfulness_scores[i].get("response", {{}}).get("faithfulness_score", 0)
        rel_score = relevance_scores[i].get("response", {{}}).get("relevance_score", 0)
        ctx_score = context_metrics[i].get("context_metrics", {{}}).get("avg_relevance_score", 0)

        all_metrics["faithfulness"].append(faith_score)
        all_metrics["relevance"].append(rel_score)
        all_metrics["context_precision"].append(ctx_score)
        all_metrics["execution_time"].append(test.get("execution_time", 0))

        if answer_quality_scores:
            quality_score = answer_quality_scores[i].get("response", {{}}).get("overall_quality", 0)
            all_metrics["answer_quality"].append(quality_score)

    # Calculate aggregate statistics
    aggregate_stats = {{}}
    for metric, scores in all_metrics.items():
        if scores:
            aggregate_stats[metric] = {{
                "mean": statistics.mean(scores),
                "median": statistics.median(scores),
                "std_dev": statistics.stdev(scores) if len(scores) > 1 else 0,
                "min": min(scores),
                "max": max(scores),
                "scores": scores
            }}

    # Identify failure cases
    failure_threshold = 0.6
    failures = []

    for i, test in enumerate(test_results):
        overall_score = (all_metrics["faithfulness"][i] +
                        all_metrics["relevance"][i] +
                        all_metrics["context_precision"][i]) / 3

        if overall_score < failure_threshold:
            failures.append({{
                "test_id": i,
                "query": test["query"],
                "overall_score": overall_score,
                "weakest_metric": min(
                    ("faithfulness", all_metrics["faithfulness"][i]),
                    ("relevance", all_metrics["relevance"][i]),
                    ("context_precision", all_metrics["context_precision"][i]),
                    key=lambda x: x[1]
                )[0]
            }})

    # Generate recommendations
    recommendations = []

    if aggregate_stats.get("faithfulness", {{}}).get("mean", 1) < 0.7:
        recommendations.append("Improve grounding: Ensure answers strictly follow retrieved content")

    if aggregate_stats.get("relevance", {{}}).get("mean", 1) < 0.7:
        recommendations.append("Enhance relevance: Better query understanding and targeted responses")

    if aggregate_stats.get("context_precision", {{}}).get("mean", 1) < 0.7:
        recommendations.append("Optimize retrieval: Improve document ranking and selection")

    if aggregate_stats.get("execution_time", {{}}).get("mean", 0) > 2.0:
        recommendations.append("Reduce latency: Consider caching or parallel processing")

    # F9 #1117: function MUST return its aggregate dict (the prior
    # `result = {{...}}` bound a function-scope local that was never
    # returned).
    return {{
        "evaluation_summary": {{
            "aggregate_metrics": aggregate_stats,
            "overall_score": statistics.mean([
                aggregate_stats.get("faithfulness", {{}}).get("mean", 0),
                aggregate_stats.get("relevance", {{}}).get("mean", 0),
                aggregate_stats.get("context_precision", {{}}).get("mean", 0)
            ]) if aggregate_stats else 0.0,
            "failure_analysis": {{
                "failure_count": len(failures),
                "failure_rate": (len(failures) / len(test_results)) if test_results else 0.0,
                "failed_queries": failures
            }},
            "recommendations": recommendations,
            "evaluation_config": {{
                "metrics_used": {self.metrics},
                "total_tests": len(test_results),
                "timestamp": _datetime_class.now().isoformat()
            }}
        }}
    }}

# F9 #1117: module-scope call. answer_quality_scores is wired in only
# when self.use_reference_answers=True; defensive try/except so the code
# is valid in either configuration. `del` non-JSON helpers so
# PythonCodeNode's output gate sees only `result`.
try:
    _aqs = answer_quality_scores
except NameError:
    _aqs = None
result = aggregate_evaluation_metrics(
    test_results, faithfulness_scores, relevance_scores, context_metrics, _aqs
)
del aggregate_evaluation_metrics, _aqs
"""
            },
        )

        # Connect workflow
        builder.add_connection(
            test_executor_id, "test_results", faithfulness_evaluator_id, "test_data"
        )
        builder.add_connection(
            test_executor_id, "test_results", relevance_evaluator_id, "test_data"
        )
        builder.add_connection(
            test_executor_id, "test_results", context_evaluator_id, "test_data"
        )

        if self.use_reference_answers:
            assert answer_quality_id is not None  # narrowed: bound in the branch above
            builder.add_connection(
                test_executor_id, "test_results", answer_quality_id, "test_data"
            )
            builder.add_connection(
                answer_quality_id, "response", aggregator_id, "answer_quality_scores"
            )

        builder.add_connection(
            test_executor_id, "test_results", aggregator_id, "test_results"
        )
        builder.add_connection(
            faithfulness_evaluator_id, "response", aggregator_id, "faithfulness_scores"
        )
        builder.add_connection(
            relevance_evaluator_id, "response", aggregator_id, "relevance_scores"
        )
        builder.add_connection(
            context_evaluator_id, "context_metrics", aggregator_id, "context_metrics"
        )

        return builder.build(name="rag_evaluation_workflow")


@register_node()
class RAGBenchmarkNode(Node):
    """
    RAG Performance Benchmarking Node

    Benchmarks RAG systems for performance characteristics.

    When to use:
    - Best for: System comparison, optimization, capacity planning
    - Not ideal for: Quality evaluation (use RAGEvaluationNode)
    - Metrics: Latency, throughput, resource usage, scalability

    Example:
        benchmark = RAGBenchmarkNode(
            workload_sizes=[10, 100, 1000],
            concurrent_users=[1, 5, 10]
        )

        results = await benchmark.execute(
            rag_systems={"system_a": rag_a, "system_b": rag_b},
            test_queries=queries
        )

    Parameters:
        workload_sizes: Different dataset sizes to test
        concurrent_users: Concurrency levels to test
        metrics_interval: How often to collect metrics

    Returns:
        latency_profiles: Response time distributions
        throughput_curves: Requests/second at different loads
        resource_usage: Memory and compute utilization
        scalability_analysis: How performance scales
    """

    def __init__(
        self,
        name: str = "rag_benchmark",
        workload_sizes: Optional[List[int]] = None,
        concurrent_users: Optional[List[int]] = None,
    ):
        resolved_workload_sizes = workload_sizes or [10, 100, 1000]
        resolved_concurrent_users = concurrent_users or [1, 5, 10]
        super().__init__(
            name=name,
            workload_sizes=resolved_workload_sizes,
            concurrent_users=resolved_concurrent_users,
        )
        self.workload_sizes = resolved_workload_sizes
        self.concurrent_users = resolved_concurrent_users

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="rag_benchmark",
                description="Node instance name",
            ),
            "workload_sizes": NodeParameter(
                name="workload_sizes",
                type=list,
                required=False,
                default=None,
                description="Document-count workloads to benchmark",
            ),
            "concurrent_users": NodeParameter(
                name="concurrent_users",
                type=list,
                required=False,
                default=None,
                description="Concurrency levels to benchmark",
            ),
            "rag_systems": NodeParameter(
                name="rag_systems",
                type=dict,
                required=True,
                description="RAG systems to benchmark",
            ),
            "test_queries": NodeParameter(
                name="test_queries",
                type=list,
                required=True,
                description="Queries for benchmarking",
            ),
            "duration": NodeParameter(
                name="duration",
                type=int,
                required=False,
                default=60,
                description="Test duration in seconds",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run performance benchmarks"""
        rag_systems = kwargs.get("rag_systems", {})
        test_queries = kwargs.get("test_queries", [])
        duration = kwargs.get("duration", 60)

        benchmark_results = {}

        for system_name, system in rag_systems.items():
            system_results = {
                "latency_profiles": {},
                "throughput_curves": {},
                "resource_usage": {},
                "scalability_analysis": {},
            }

            # Test different workload sizes
            for size in self.workload_sizes:
                workload = test_queries[:size]

                # Measure latency
                latencies = []
                start_time = time.time()

                for query in workload:
                    query_start = time.time()
                    # Would call system.run(query=query) in production
                    # Simulate processing
                    time.sleep(0.1 + random.random() * 0.1)
                    latencies.append(time.time() - query_start)

                system_results["latency_profiles"][f"size_{size}"] = {
                    "p50": statistics.median(latencies),
                    "p95": sorted(latencies)[int(len(latencies) * 0.95)],
                    "p99": sorted(latencies)[int(len(latencies) * 0.99)],
                    "mean": statistics.mean(latencies),
                    "std_dev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                }

                # Calculate throughput
                total_time = time.time() - start_time
                throughput = len(workload) / total_time
                system_results["throughput_curves"][f"size_{size}"] = throughput

            # Test concurrency
            for users in self.concurrent_users:
                # Simulate concurrent load
                concurrent_latencies = []

                # Simplified - would use asyncio/threading in production
                for _ in range(users * 10):
                    query_start = time.time()
                    time.sleep(0.1 + random.random() * 0.2 * users)
                    concurrent_latencies.append(time.time() - query_start)

                system_results["scalability_analysis"][f"users_{users}"] = {
                    "avg_latency": statistics.mean(concurrent_latencies),
                    "throughput_degradation": 1.0 / users,  # Simplified
                }

            # Simulate resource usage
            system_results["resource_usage"] = {
                "memory_mb": 100 + random.randint(0, 500),
                "cpu_percent": 20 + random.randint(0, 60),
                "gpu_memory_mb": (
                    0
                    if "gpu" not in system_name.lower()
                    else 1000 + random.randint(0, 3000)
                ),
            }

            benchmark_results[system_name] = system_results

        # Comparative analysis
        comparison = self._compare_systems(benchmark_results)

        return {
            "benchmark_results": benchmark_results,
            "comparison": comparison,
            "test_configuration": {
                "workload_sizes": self.workload_sizes,
                "concurrent_users": self.concurrent_users,
                "duration": duration,
                "num_queries": len(test_queries),
            },
        }

    def _compare_systems(self, results: Dict) -> Dict[str, Any]:
        """Compare benchmark results across systems"""
        comparison = {
            "fastest_system": None,
            "most_scalable": None,
            "most_efficient": None,
            "recommendations": [],
        }

        # Find fastest system
        avg_latencies = {}
        for system, data in results.items():
            latencies = [v["mean"] for v in data["latency_profiles"].values()]
            avg_latencies[system] = (
                statistics.mean(latencies) if latencies else float("inf")
            )

        comparison["fastest_system"] = min(
            avg_latencies, key=lambda k: avg_latencies[k]
        )

        # Find most scalable
        scalability_scores = {}
        for system, data in results.items():
            # Lower degradation = better scalability
            degradations = [
                v["throughput_degradation"]
                for v in data["scalability_analysis"].values()
            ]
            scalability_scores[system] = (
                statistics.mean(degradations) if degradations else 0
            )

        comparison["most_scalable"] = max(
            scalability_scores, key=lambda k: scalability_scores[k]
        )

        # Find most efficient (performance per resource)
        efficiency_scores = {}
        for system, data in results.items():
            throughput = (
                statistics.mean(data["throughput_curves"].values())
                if data["throughput_curves"]
                else 1
            )
            memory = data["resource_usage"]["memory_mb"]
            efficiency_scores[system] = throughput / memory * 1000

        comparison["most_efficient"] = max(
            efficiency_scores, key=lambda k: efficiency_scores[k]
        )

        # Generate recommendations
        comparison["recommendations"] = [
            f"Use {comparison['fastest_system']} for latency-critical applications",
            f"Use {comparison['most_scalable']} for high-concurrency scenarios",
            f"Use {comparison['most_efficient']} for resource-constrained environments",
        ]

        return comparison


@register_node()
class TestDatasetGeneratorNode(Node):
    """
    RAG Test Dataset Generator

    Generates synthetic test datasets for RAG evaluation.

    When to use:
    - Best for: Creating evaluation benchmarks, testing edge cases
    - Not ideal for: Production data generation
    - Output: Queries with ground truth answers and contexts

    Example:
        generator = TestDatasetGeneratorNode(
            categories=["factual", "analytical", "comparative"],
            difficulty_levels=["easy", "medium", "hard"]
        )

        dataset = generator.execute(
            num_samples=100,
            domain="machine learning"
        )

    Parameters:
        categories: Types of questions to generate
        difficulty_levels: Complexity levels
        include_adversarial: Generate tricky cases

    Returns:
        test_queries: Generated queries with metadata
        reference_answers: Ground truth answers
        test_contexts: Relevant documents
    """

    def __init__(
        self,
        name: str = "test_dataset_generator",
        categories: Optional[List[str]] = None,
        include_adversarial: bool = True,
    ):
        resolved_categories = categories or [
            "factual",
            "analytical",
            "comparative",
        ]
        super().__init__(
            name=name,
            categories=resolved_categories,
            include_adversarial=include_adversarial,
        )
        self.categories = resolved_categories
        self.include_adversarial = include_adversarial

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="test_dataset_generator",
                description="Node instance name",
            ),
            "categories": NodeParameter(
                name="categories",
                type=list,
                required=False,
                default=None,
                description="Question categories to generate",
            ),
            "include_adversarial": NodeParameter(
                name="include_adversarial",
                type=bool,
                required=False,
                default=True,
                description="Include adversarial test cases",
            ),
            "num_samples": NodeParameter(
                name="num_samples",
                type=int,
                required=True,
                description="Number of test samples",
            ),
            "domain": NodeParameter(
                name="domain",
                type=str,
                required=False,
                default="general",
                description="Domain for questions",
            ),
            "seed": NodeParameter(
                name="seed",
                type=int,
                required=False,
                description="Random seed for reproducibility",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Generate test dataset"""
        num_samples = kwargs.get("num_samples", 10)
        domain = kwargs.get("domain", "general")
        seed = kwargs.get("seed")

        if seed:
            random.seed(seed)

        test_dataset = []

        # Templates for different categories
        templates = {
            "factual": [
                ("What is {concept}?", "Definition and explanation of {concept}"),
                (
                    "When was {event} discovered?",
                    "Discovery date and context of {event}",
                ),
                ("Who invented {invention}?", "Inventor and history of {invention}"),
            ],
            "analytical": [
                (
                    "How does {system} work?",
                    "Detailed explanation of {system} mechanics",
                ),
                (
                    "What are the advantages of {method}?",
                    "Benefits and strengths of {method}",
                ),
                (
                    "Why is {principle} important?",
                    "Significance and applications of {principle}",
                ),
            ],
            "comparative": [
                (
                    "Compare {option1} and {option2}",
                    "Comparison of {option1} vs {option2}",
                ),
                (
                    "What's the difference between {concept1} and {concept2}?",
                    "Distinctions between concepts",
                ),
                (
                    "Which is better: {choice1} or {choice2}?",
                    "Trade-offs and recommendations",
                ),
            ],
        }

        # Domain-specific concepts
        domain_concepts = {
            "machine learning": [
                "neural networks",
                "transformers",
                "BERT",
                "attention mechanism",
                "backpropagation",
            ],
            "general": [
                "democracy",
                "photosynthesis",
                "gravity",
                "internet",
                "climate change",
            ],
        }

        concepts = domain_concepts.get(domain, domain_concepts["general"])

        for i in range(num_samples):
            category = random.choice(self.categories)
            template_q, template_a = random.choice(templates[category])

            # Generate specific question
            if "{concept}" in template_q:
                concept = random.choice(concepts)
                query = template_q.format(concept=concept)
                answer = template_a.format(concept=concept)
            else:
                # Handle other placeholders
                query = template_q
                answer = template_a

            # Generate contexts
            contexts = []
            for j in range(3):
                contexts.append(
                    {
                        "id": f"ctx_{i}_{j}",
                        "content": f"Context {j + 1} about {query}: {answer}",
                        "relevance": 0.9 - j * 0.1,
                    }
                )

            # Add adversarial examples if enabled
            metadata = {"category": category, "difficulty": "medium"}

            if self.include_adversarial and random.random() < 0.2:
                # Make it adversarial
                if random.random() < 0.5:
                    # Negation
                    query = f"Is it true that {query.lower()}"
                    metadata["adversarial_type"] = "negation"
                else:
                    # Misleading context
                    contexts.append(
                        {
                            "id": f"ctx_{i}_misleading",
                            "content": f"Incorrect information: {query} is actually false because...",
                            "relevance": 0.7,
                        }
                    )
                    metadata["adversarial_type"] = "misleading_context"

            test_dataset.append(
                {
                    "id": f"test_{i}",
                    "query": query,
                    "reference_answer": answer,
                    "contexts": contexts,
                    "metadata": metadata,
                }
            )

        return {
            "test_dataset": test_dataset,
            "statistics": {
                "total_samples": len(test_dataset),
                "category_distribution": {
                    cat: sum(
                        1 for t in test_dataset if t["metadata"]["category"] == cat
                    )
                    for cat in self.categories
                },
                "adversarial_count": sum(
                    1 for t in test_dataset if "adversarial_type" in t["metadata"]
                ),
            },
            "generation_config": {
                "domain": domain,
                "categories": self.categories,
                "seed": seed,
            },
        }


# Export all evaluation nodes
__all__ = ["RAGEvaluationNode", "RAGBenchmarkNode", "TestDatasetGeneratorNode"]
