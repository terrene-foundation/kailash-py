"""
Federated RAG Implementation

Implements RAG across distributed data sources without centralization:
- Federated learning for distributed embeddings
- Cross-silo and cross-device federation
- Secure aggregation protocols
- Heterogeneous data handling
- Communication-efficient protocols

Based on federated learning and distributed systems research.
"""

import hashlib
import json
import logging
import random
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.nodes.api.rest import (  # noqa: F401  (registers "RESTClientNode" for builder.add_node)
    RESTClientNode,
)
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.code.python import (  # noqa: F401  (registers "PythonCodeNode" for builder.add_node)
    PythonCodeNode,
)
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


@register_node()
class FederatedRAGNode(WorkflowNode):
    """
    Federated RAG Aggregation Pattern (in-process simulation)

    Demonstrates the federated-RAG aggregation pattern over in-process
    simulated nodes. It does NOT perform real distributed network queries —
    the per-node responses are generated in-process (no actual cross-host
    federation, no network calls). Use this node to demonstrate the
    aggregation + health-reporting shape of a federated-RAG pipeline.

    When to use:
    - Best for: prototyping the federated-RAG aggregation/health-reporting shape
    - Not ideal for: production federation requiring real cross-host queries

    Key features:
    - Aggregation of per-node responses (weighted/strategy-based)
    - Federation-health reporting over the simulated node set
    - Heterogeneous-source aggregation shape
    - Minimum-participating-nodes gating

    Example:
        federated_rag = FederatedRAGNode(
            federation_nodes=["hospital_a", "hospital_b", "research_lab"],
            aggregation_strategy="weighted_average",
            min_participating_nodes=2
        )

        # Query across all federated sources
        result = await federated_rag.execute(
            query="Latest treatment protocols for condition X",
            node_endpoints={
                "hospital_a": "https://hospitalA.api/rag",
                "hospital_b": "https://hospitalB.api/rag",
                "research_lab": "https://lab.api/rag"
            }
        )

        # Returns aggregated results without exposing individual data

    Parameters:
        federation_nodes: List of participating nodes
        aggregation_strategy: How to combine results
        min_participating_nodes: Minimum nodes for valid result
        timeout_per_node: Maximum wait time per node
        enable_caching: Cache results at edge nodes

    Returns:
        federated_results: Aggregated results from all nodes
        node_contributions: Which nodes participated
        aggregation_metadata: How results were combined
        federation_health: Status of federated network
    """

    def __init__(
        self,
        name: str = "federated_rag",
        federation_nodes: Optional[List[str]] = None,
        aggregation_strategy: str = "weighted_average",
        min_participating_nodes: int = 2,
        timeout_per_node: float = 5.0,
        enable_caching: bool = True,
    ):
        self.federation_nodes = federation_nodes or []
        self.aggregation_strategy = aggregation_strategy
        self.min_participating_nodes = min_participating_nodes
        self.timeout_per_node = timeout_per_node
        self.enable_caching = enable_caching
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create federated RAG workflow"""
        builder = WorkflowBuilder()
        # Assigned only when caching is enabled; pre-bind so the later
        # ``if self.enable_caching`` connection block has a defined name.
        cache_coordinator_id: Optional[str] = None

        # Query distributor
        query_distributor_id = builder.add_node(
            "PythonCodeNode",
            node_id="query_distributor",
            config={
                "code": f"""
import hashlib
from datetime import datetime

def distribute_query(query, node_endpoints, federation_config):
    '''Prepare query for distribution to federated nodes'''

    # Generate query ID for tracking
    query_id = hashlib.sha256(
        f"{{query}}_{{datetime.now().isoformat()}}".encode()
    ).hexdigest()[:16]

    # Prepare distribution plan
    distribution_plan = {{
        "query_id": query_id,
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "target_nodes": [],
        "federation_metadata": {{
            "total_nodes": len(node_endpoints),
            "min_required": {self.min_participating_nodes},
            "timeout_per_node": {self.timeout_per_node},
            "aggregation_strategy": "{self.aggregation_strategy}"
        }}
    }}

    # Create node-specific queries
    for node_id, endpoint in node_endpoints.items():
        node_query = {{
            "node_id": node_id,
            "endpoint": endpoint,
            "query_payload": {{
                "query": query,
                "query_id": query_id,
                "federation_context": {{
                    "requesting_node": "coordinator",
                    "protocol_version": "1.0",
                    "response_format": "standardized"
                }}
            }},
            "timeout": {self.timeout_per_node}
        }}

        distribution_plan["target_nodes"].append(node_query)

    result = {{
        "distribution_plan": distribution_plan,
        "ready_for_distribution": True
    }}
"""
            },
        )

        # Federated query executor (simulated - would use actual network calls)
        federated_executor_id = builder.add_node(
            "PythonCodeNode",
            node_id="federated_executor",
            config={
                "code": f"""
import asyncio
import random
import time

def execute_federated_queries(distribution_plan):
    '''Execute queries across federated nodes'''

    node_responses = []
    failed_nodes = []

    # Simulate parallel execution across nodes
    for node_info in distribution_plan["target_nodes"]:
        node_id = node_info["node_id"]

        # Simulate network call with varying latency
        start_time = time.time()

        # Simulate different node behaviors
        if random.random() > 0.9:  # 10% failure rate
            failed_nodes.append({{
                "node_id": node_id,
                "error": "Connection timeout",
                "timestamp": datetime.now().isoformat()
            }})
            continue

        # Simulate node processing
        latency = random.uniform(0.5, 3.0)

        # Generate simulated response based on node type
        if "hospital" in node_id:
            results = [
                {{
                    "content": f"Clinical protocol from {{node_id}}: Treatment approach...",
                    "score": 0.85 + random.random() * 0.1,
                    "metadata": {{"source": "clinical_database", "last_updated": "2024-01"}}
                }},
                {{
                    "content": f"Patient outcomes data from {{node_id}}...",
                    "score": 0.80 + random.random() * 0.1,
                    "metadata": {{"source": "patient_records", "anonymized": True}}
                }}
            ]
        elif "research" in node_id:
            results = [
                {{
                    "content": f"Research findings from {{node_id}}: Latest studies show...",
                    "score": 0.90 + random.random() * 0.05,
                    "metadata": {{"source": "research_papers", "peer_reviewed": True}}
                }},
                {{
                    "content": f"Experimental data from {{node_id}}...",
                    "score": 0.75 + random.random() * 0.15,
                    "metadata": {{"source": "lab_results", "trial_phase": "3"}}
                }}
            ]
        else:
            results = [
                {{
                    "content": f"General data from {{node_id}}...",
                    "score": 0.70 + random.random() * 0.2,
                    "metadata": {{"source": "general_database"}}
                }}
            ]

        # Add response
        response_time = time.time() - start_time

        node_responses.append({{
            "node_id": node_id,
            "status": "success",
            "results": results,
            "metadata": {{
                "response_time": response_time,
                "result_count": len(results),
                "node_load": random.uniform(0.3, 0.9),
                "cache_hit": random.random() > 0.7 if {self.enable_caching} else False
            }},
            "timestamp": datetime.now().isoformat()
        }})

    # Check if minimum nodes responded
    successful_nodes = len(node_responses)
    minimum_met = successful_nodes >= {self.min_participating_nodes}

    result = {{
        "federated_responses": {{
            "query_id": distribution_plan["query_id"],
            "node_responses": node_responses,
            "failed_nodes": failed_nodes,
            "statistics": {{
                "total_nodes": len(distribution_plan["target_nodes"]),
                "successful_nodes": successful_nodes,
                "failed_nodes": len(failed_nodes),
                "minimum_requirement_met": minimum_met,
                "avg_response_time": sum(r["metadata"]["response_time"] for r in node_responses) / len(node_responses) if node_responses else 0
            }}
        }}
    }}
"""
            },
        )

        # Result aggregator
        result_aggregator_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_aggregator",
            config={
                "code": f"""
from collections import defaultdict
import statistics

def aggregate_federated_results(federated_responses):
    '''Aggregate results from multiple federated nodes'''

    if not federated_responses["statistics"]["minimum_requirement_met"]:
        return {{
            "aggregated_results": {{
                "error": "Insufficient nodes responded",
                "required": {self.min_participating_nodes},
                "received": federated_responses["statistics"]["successful_nodes"]
            }}
        }}

    # Collect all results
    all_results = []
    node_weights = {{}}

    for node_response in federated_responses["node_responses"]:
        node_id = node_response["node_id"]

        # Calculate node weight based on various factors
        weight = 1.0

        # Adjust weight based on response time (faster = higher weight)
        avg_response_time = federated_responses["statistics"]["avg_response_time"]
        if avg_response_time > 0:
            weight *= avg_response_time / node_response["metadata"]["response_time"]

        # Adjust weight based on result count
        weight *= min(2.0, 1 + node_response["metadata"]["result_count"] / 10)

        # Boost weight for cache hits
        if node_response["metadata"].get("cache_hit"):
            weight *= 1.2

        node_weights[node_id] = weight

        # Add results with node information
        for result in node_response["results"]:
            # A node's results list is data from a federated peer — a non-dict
            # element has no .copy(); a present-but-None content reaches a
            # [:50] slice and a str-keyed group. Guard once at intake so every
            # downstream aggregation strategy sees only well-formed dicts.
            if not isinstance(result, dict):
                continue
            result_with_node = result.copy()
            if result_with_node.get("content") is None:
                result_with_node["content"] = ""
            result_with_node["source_node"] = node_id
            result_with_node["node_weight"] = weight
            all_results.append(result_with_node)

    # Aggregate based on strategy
    if "{self.aggregation_strategy}" == "weighted_average":
        # Group similar results and weight scores
        grouped_results = defaultdict(list)

        for result in all_results:
            # Simple content hashing for grouping
            content_key = result["content"][:50]  # First 50 chars as key
            grouped_results[content_key].append(result)

        aggregated = []
        for content_key, group in grouped_results.items():
            # Calculate weighted average score
            total_weight = sum(r["node_weight"] for r in group)
            weighted_score = sum(r["score"] * r["node_weight"] for r in group) / total_weight

            # Merge metadata
            merged_metadata = {{
                "source_nodes": list(set(r["source_node"] for r in group)),
                "aggregation_method": "weighted_average",
                "individual_scores": {{r["source_node"]: r["score"] for r in group}},
                "confidence": statistics.stdev([r["score"] for r in group]) if len(group) > 1 else 1.0
            }}

            aggregated.append({{
                "content": group[0]["content"],  # Use full content from first
                "score": weighted_score,
                "metadata": merged_metadata,
                "node_agreement": len(group) / len(federated_responses["node_responses"])
            }})

    elif "{self.aggregation_strategy}" == "voting":
        # Majority voting on top results
        node_top_results = {{}}

        for node_response in federated_responses["node_responses"]:
            node_id = node_response["node_id"]
            # Get top 3 results from each node
            top_results = sorted(node_response["results"], key=lambda x: x["score"], reverse=True)[:3]
            node_top_results[node_id] = [r["content"] for r in top_results]

        # Count votes
        content_votes = defaultdict(int)
        for node_id, results in node_top_results.items():
            for i, content in enumerate(results):
                # Higher rank = more votes
                content_votes[content] += (3 - i)

        # Sort by votes
        aggregated = []
        for content, votes in sorted(content_votes.items(), key=lambda x: x[1], reverse=True)[:10]:
            # Find original result data
            for result in all_results:
                if result["content"] == content:
                    aggregated.append({{
                        "content": content,
                        "score": votes / (3 * len(federated_responses["node_responses"])),
                        "metadata": {{
                            "aggregation_method": "voting",
                            "vote_count": votes,
                            "max_possible_votes": 3 * len(federated_responses["node_responses"])
                        }}
                    }})
                    break

    else:  # Simple merge
        # Just combine and sort by score
        aggregated = sorted(all_results, key=lambda x: x["score"], reverse=True)[:10]
        for result in aggregated:
            result["metadata"]["aggregation_method"] = "simple_merge"

    # Sort final results by score
    aggregated.sort(key=lambda x: x["score"], reverse=True)

    # Calculate federation health metrics
    federation_health = {{
        "overall_health": "healthy" if federated_responses["statistics"]["successful_nodes"] >= len(federated_responses["node_responses"]) * 0.8 else "degraded",
        "node_participation_rate": federated_responses["statistics"]["successful_nodes"] / federated_responses["statistics"]["total_nodes"],
        "avg_node_latency": federated_responses["statistics"]["avg_response_time"],
        "result_diversity": len(set(r["content"][:30] for r in all_results)) / len(all_results) if all_results else 0
    }}

    result = {{
        "aggregated_results": {{
            "results": aggregated[:10],  # Top 10 aggregated results
            "total_raw_results": len(all_results),
            "aggregation_metadata": {{
                "strategy": "{self.aggregation_strategy}",
                "node_weights": node_weights,
                "participating_nodes": list(node_weights.keys())
            }},
            "federation_health": federation_health
        }}
    }}
"""
            },
        )

        # Cache coordinator (if enabled)
        if self.enable_caching:
            cache_coordinator_id = builder.add_node(
                "PythonCodeNode",
                node_id="cache_coordinator",
                config={
                    "code": """
def coordinate_caching(aggregated_results, distribution_plan):
    '''Coordinate caching across federated nodes'''

    # Identify high-value results to cache
    cache_candidates = []

    for result in aggregated_results["results"][:5]:  # Top 5 results
        if result["score"] > 0.8 and result.get("node_agreement", 0) > 0.5:
            # A present-but-None content bypasses an upstream "" default and
            # reaches .encode() — coerce before hashing.
            content_hash = hashlib.sha256(
                (result.get("content") or "").encode()
            ).hexdigest()[:16]
            cache_candidates.append({
                "content_hash": content_hash,
                "result": result,
                "cache_priority": result["score"] * result.get("node_agreement", 1),
                "ttl": 3600  # 1 hour
            })

    # Create cache distribution plan
    cache_distribution = {
        "cache_candidates": cache_candidates,
        "distribution_strategy": "broadcast",  # Send to all nodes
        "cache_metadata": {
            "query_id": distribution_plan["query_id"],
            "cached_at": datetime.now().isoformat(),
            "cache_version": "1.0"
        }
    }

    result = {
        "cache_coordination": {
            "candidates_identified": len(cache_candidates),
            "cache_distribution": cache_distribution,
            "estimated_hit_rate_improvement": min(0.3, len(cache_candidates) * 0.05)
        }
    }
"""
                },
            )

        # Result formatter
        result_formatter_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_formatter",
            config={
                "code": f"""
def format_federated_results(aggregated_results, federated_responses, cache_coordination=None):
    '''Format final federated RAG results'''

    # Extract key information
    results = aggregated_results.get("results", [])
    aggregation_metadata = aggregated_results.get("aggregation_metadata", {{}})
    federation_health = aggregated_results.get("federation_health", {{}})

    # Build node contribution summary
    node_contributions = {{}}
    for node_response in federated_responses["node_responses"]:
        node_id = node_response["node_id"]
        node_contributions[node_id] = {{
            "status": node_response["status"],
            "results_contributed": node_response["metadata"]["result_count"],
            "response_time": node_response["metadata"]["response_time"],
            "weight": aggregation_metadata["node_weights"].get(node_id, 0)
        }}

    # Add failed nodes
    for failed_node in federated_responses["failed_nodes"]:
        node_contributions[failed_node["node_id"]] = {{
            "status": "failed",
            "error": failed_node["error"]
        }}

    # Build final output
    formatted_output = {{
        "federated_results": results,
        "node_contributions": node_contributions,
        "aggregation_metadata": {{
            "strategy_used": aggregation_metadata.get("strategy", "{self.aggregation_strategy}"),
            "nodes_participated": len(aggregation_metadata.get("participating_nodes", [])),
            "total_results_aggregated": aggregated_results.get("total_raw_results", 0),
            "minimum_nodes_required": {self.min_participating_nodes},
            "minimum_requirement_met": federated_responses["statistics"]["minimum_requirement_met"]
        }},
        "federation_health": federation_health,
        "performance_metrics": {{
            "total_query_time": federated_responses["statistics"]["avg_response_time"],
            "successful_node_rate": federated_responses["statistics"]["successful_nodes"] / federated_responses["statistics"]["total_nodes"],
            "result_diversity_score": federation_health.get("result_diversity", 0)
        }}
    }}

    # Add caching information if available
    if cache_coordination and {self.enable_caching}:
        formatted_output["cache_optimization"] = {{
            "cache_candidates": cache_coordination["cache_coordination"]["candidates_identified"],
            "expected_hit_rate_improvement": cache_coordination["cache_coordination"]["estimated_hit_rate_improvement"]
        }}

    result = {{"federated_rag_output": formatted_output}}
"""
            },
        )

        # Connect workflow
        builder.add_connection(
            query_distributor_id,
            "distribution_plan",
            federated_executor_id,
            "distribution_plan",
        )
        builder.add_connection(
            federated_executor_id,
            "federated_responses",
            result_aggregator_id,
            "federated_responses",
        )

        if self.enable_caching:
            # cache_coordinator_id is assigned in the matching enable_caching
            # block above; narrow it from Optional[str] for the connections.
            assert cache_coordinator_id is not None
            builder.add_connection(
                result_aggregator_id,
                "aggregated_results",
                cache_coordinator_id,
                "aggregated_results",
            )
            builder.add_connection(
                query_distributor_id,
                "distribution_plan",
                cache_coordinator_id,
                "distribution_plan",
            )
            builder.add_connection(
                cache_coordinator_id,
                "cache_coordination",
                result_formatter_id,
                "cache_coordination",
            )

        builder.add_connection(
            result_aggregator_id,
            "aggregated_results",
            result_formatter_id,
            "aggregated_results",
        )
        builder.add_connection(
            federated_executor_id,
            "federated_responses",
            result_formatter_id,
            "federated_responses",
        )

        return builder.build(name="federated_rag_workflow")


@register_node()
class EdgeRAGNode(Node):
    """
    Edge Computing RAG Node

    Optimized RAG for edge devices with limited resources.

    When to use:
    - Best for: IoT devices, mobile apps, offline scenarios
    - Constraints: Limited memory, CPU, storage
    - Features: Model quantization, selective caching, incremental updates

    Example:
        edge_rag = EdgeRAGNode(
            model_size="tiny",  # 50MB model
            max_cache_size_mb=100,
            update_strategy="incremental"
        )

        result = await edge_rag.execute(
            query="Local sensor anomaly detection",
            local_data=sensor_readings,
            sync_with_cloud=False
        )

    Parameters:
        model_size: Size constraints (tiny, small, medium)
        max_cache_size_mb: Maximum cache size
        update_strategy: How to update the edge model
        power_mode: Optimization for battery life

    Returns:
        results: Local RAG results
        resource_usage: Memory and CPU consumption
        sync_recommendations: When to sync with cloud
    """

    def __init__(
        self,
        name: str = "edge_rag",
        model_size: str = "small",
        max_cache_size_mb: int = 100,
        update_strategy: str = "incremental",
        power_mode: str = "balanced",
    ):
        super().__init__(
            name=name,
            model_size=model_size,
            max_cache_size_mb=max_cache_size_mb,
            update_strategy=update_strategy,
            power_mode=power_mode,
        )
        self.model_size = model_size
        self.max_cache_size_mb = max_cache_size_mb
        self.update_strategy = update_strategy
        self.power_mode = power_mode
        self.cache = {}
        self.cache_size_bytes = 0

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="edge_rag",
                description="Node instance name",
            ),
            "model_size": NodeParameter(
                name="model_size",
                type=str,
                required=False,
                default="small",
                description="Edge model size profile",
            ),
            "max_cache_size_mb": NodeParameter(
                name="max_cache_size_mb",
                type=int,
                required=False,
                default=100,
                description="Maximum local cache size in MB",
            ),
            "update_strategy": NodeParameter(
                name="update_strategy",
                type=str,
                required=False,
                default="incremental",
                description="Edge index update strategy",
            ),
            "power_mode": NodeParameter(
                name="power_mode",
                type=str,
                required=False,
                default="balanced",
                description="Edge power/performance profile",
            ),
            "query": NodeParameter(
                name="query", type=str, required=True, description="Query to process"
            ),
            "local_data": NodeParameter(
                name="local_data",
                type=list,
                required=True,
                description="Local data available on edge",
            ),
            "sync_with_cloud": NodeParameter(
                name="sync_with_cloud",
                type=bool,
                required=False,
                default=False,
                description="Whether to sync with cloud",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute edge-optimized RAG"""
        # ``.get(key, default)`` only applies the default to a MISSING key; an
        # explicit ``query=None`` returns ``None`` and ``None.encode()`` raises.
        query = kwargs.get("query") or ""
        local_data = kwargs.get("local_data") or []
        sync_with_cloud = kwargs.get("sync_with_cloud", False)

        # Check cache first
        cache_key = hashlib.sha256(query.encode()).hexdigest()[:8]
        if cache_key in self.cache and self.power_mode != "performance":
            logger.info(f"Cache hit for query: {cache_key}")
            return self.cache[cache_key]

        # Resource tracking
        start_memory = self._estimate_memory_usage()

        # Lightweight retrieval optimized for edge
        results = self._edge_optimized_retrieval(query, local_data)

        # Generate response with constrained model
        response = self._generate_edge_response(query, results)

        # Calculate resource usage
        end_memory = self._estimate_memory_usage()
        resource_usage = {
            "memory_mb": (end_memory - start_memory) / 1024 / 1024,
            "estimated_cpu_ms": 50 if self.model_size == "tiny" else 200,
            "model_size": self.model_size,
            "cache_size_mb": self.cache_size_bytes / 1024 / 1024,
        }

        # Determine sync recommendations
        sync_recommendations = self._calculate_sync_recommendations(
            len(local_data), self.cache_size_bytes, sync_with_cloud
        )

        # Cache result if space available
        result = {
            "results": response["results"],
            "resource_usage": resource_usage,
            "sync_recommendations": sync_recommendations,
            "edge_metadata": {
                "model_size": self.model_size,
                "power_mode": self.power_mode,
                "cache_hit": False,
                "local_data_size": len(local_data),
            },
        }

        # Update cache
        self._update_cache(cache_key, result)

        return result

    def _edge_optimized_retrieval(
        self, query: str, local_data: List[Dict]
    ) -> List[Dict]:
        """Perform retrieval optimized for edge constraints"""
        # Simple keyword matching for efficiency
        query_words = set(query.lower().split())
        scored_results = []

        # Limit processing based on power mode
        max_docs = 50 if self.power_mode == "low_power" else 200

        for doc in local_data[:max_docs]:
            # local_data is arbitrary user input — a non-dict element has no
            # ``.get``; a present-but-None ``content`` bypasses the "" default.
            if not isinstance(doc, dict):
                continue
            content = (doc.get("content") or "").lower()
            doc_words = set(content.split())

            # Quick scoring
            if query_words:
                score = len(query_words & doc_words) / len(query_words)
                if score > 0:
                    scored_results.append({"document": doc, "score": score})

        # Sort and limit results
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:5]  # Keep only top 5 for edge

    def _generate_edge_response(
        self, query: str, results: List[Dict]
    ) -> Dict[str, Any]:
        """Generate response with edge-constrained model"""
        # Simulate different model sizes
        if self.model_size == "tiny":
            # Very basic response
            if results:
                response = f"Found {len(results)} relevant results for: {query}"
            else:
                response = f"No local results for: {query}"
        elif self.model_size == "small":
            # Slightly better response
            if results:
                # A present-but-None ``content`` bypasses the "" default and
                # ``None[:100]`` raises — coerce before slicing.
                top_content = (results[0]["document"].get("content") or "")[:100]
                response = f"Based on local data: {top_content}..."
            else:
                response = "No relevant local data found. Consider syncing with cloud."
        else:  # medium
            # Best edge response
            if results:
                contents = [
                    (r["document"].get("content") or "")[:200] for r in results[:2]
                ]
                response = f"Local analysis for '{query}': " + " ".join(contents)
            else:
                response = f"No local matches for '{query}'. Cloud sync recommended."

        return {
            "results": [
                {
                    "content": response,
                    "score": results[0]["score"] if results else 0,
                    "source": "edge_processing",
                }
            ]
        }

    def _estimate_memory_usage(self) -> int:
        """Estimate current memory usage in bytes"""
        # Simplified estimation
        base_memory = {
            "tiny": 50 * 1024 * 1024,  # 50MB
            "small": 200 * 1024 * 1024,  # 200MB
            "medium": 500 * 1024 * 1024,  # 500MB
        }
        return (
            base_memory.get(self.model_size, 200 * 1024 * 1024) + self.cache_size_bytes
        )

    def _calculate_sync_recommendations(
        self, local_data_size: int, cache_size: int, sync_requested: bool
    ) -> Dict[str, Any]:
        """Calculate when to sync with cloud"""
        recommendations = {"should_sync": False, "sync_priority": "low", "reasons": []}

        # Check various conditions
        if local_data_size < 10:
            recommendations["should_sync"] = True
            recommendations["reasons"].append("Insufficient local data")
            recommendations["sync_priority"] = "high"

        if cache_size > self.max_cache_size_mb * 1024 * 1024 * 0.9:
            recommendations["should_sync"] = True
            recommendations["reasons"].append("Cache near capacity")
            recommendations["sync_priority"] = "medium"

        if sync_requested:
            recommendations["should_sync"] = True
            recommendations["reasons"].append("User requested sync")
            recommendations["sync_priority"] = "high"

        # Add sync strategy
        if self.update_strategy == "incremental":
            recommendations["sync_type"] = "differential"
        else:
            recommendations["sync_type"] = "full"

        return recommendations

    def _update_cache(self, key: str, result: Dict):
        """Update cache with size management"""
        result_size = len(json.dumps(result))

        # Check if we need to evict
        while (
            self.cache_size_bytes + result_size > self.max_cache_size_mb * 1024 * 1024
            and self.cache
        ):
            # Evict oldest (simple FIFO)
            oldest_key = next(iter(self.cache))
            evicted_size = len(json.dumps(self.cache[oldest_key]))
            del self.cache[oldest_key]
            self.cache_size_bytes -= evicted_size
            logger.debug(f"Evicted cache entry: {oldest_key}")

        # Add to cache
        self.cache[key] = result
        self.cache_size_bytes += result_size


@register_node()
class CrossSiloRAGNode(Node):
    """
    Cross-Silo Federated RAG

    RAG across organizational boundaries with strict data governance.

    When to use:
    - Best for: Multi-organization collaborations, consortiums
    - Features: Data sovereignty, audit trails, access control
    - Compliance: GDPR, HIPAA compatible

    Example:
        cross_silo_rag = CrossSiloRAGNode(
            silos=["org_a", "org_b", "org_c"],
            data_sharing_agreement="minimal",
            audit_mode="comprehensive"
        )

        result = await cross_silo_rag.execute(
            query="Industry-wide trend analysis",
            requester_org="org_a",
            access_permissions=["read_aggregated", "no_raw_data"]
        )

    Parameters:
        silos: Participating organizations
        data_sharing_agreement: Level of data sharing allowed
        audit_mode: Audit trail comprehensiveness
        governance_rules: Data governance policies

    Returns:
        silo_results: Results respecting data boundaries
        audit_trail: Complete audit of data access
        compliance_report: Governance compliance status
    """

    def __init__(
        self,
        name: str = "cross_silo_rag",
        silos: Optional[List[str]] = None,
        data_sharing_agreement: str = "minimal",
        audit_mode: str = "standard",
        governance_rules: Optional[Dict[str, Any]] = None,
    ):
        resolved_silos = silos or []
        resolved_governance_rules = governance_rules or {}
        super().__init__(
            name=name,
            silos=resolved_silos,
            data_sharing_agreement=data_sharing_agreement,
            audit_mode=audit_mode,
            governance_rules=resolved_governance_rules,
        )
        self.silos = resolved_silos
        self.data_sharing_agreement = data_sharing_agreement
        self.audit_mode = audit_mode
        self.governance_rules = resolved_governance_rules

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="cross_silo_rag",
                description="Node instance name",
            ),
            "silos": NodeParameter(
                name="silos",
                type=list,
                required=False,
                default=None,
                description="Participating data silos",
            ),
            "data_sharing_agreement": NodeParameter(
                name="data_sharing_agreement",
                type=str,
                required=False,
                default="minimal",
                description="Cross-silo data sharing agreement level",
            ),
            "audit_mode": NodeParameter(
                name="audit_mode",
                type=str,
                required=False,
                default="standard",
                description="Audit logging mode",
            ),
            "governance_rules": NodeParameter(
                name="governance_rules",
                type=dict,
                required=False,
                default=None,
                description="Cross-silo governance ruleset",
            ),
            "query": NodeParameter(
                name="query", type=str, required=True, description="Cross-silo query"
            ),
            "requester_org": NodeParameter(
                name="requester_org",
                type=str,
                required=True,
                description="Organization making request",
            ),
            "access_permissions": NodeParameter(
                name="access_permissions",
                type=list,
                required=True,
                description="Granted permissions",
            ),
            "purpose": NodeParameter(
                name="purpose", type=str, required=False, description="Purpose of query"
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute cross-silo federated RAG"""
        # ``.get(key, default)`` only applies the default to a MISSING key; an
        # explicit ``query=None`` reaches ``query.encode()`` in the audit-trail
        # hash, and ``access_permissions=None`` reaches ``perm in None``.
        query = kwargs.get("query") or ""
        requester_org = kwargs.get("requester_org") or ""
        access_permissions = kwargs.get("access_permissions") or []
        purpose = kwargs.get("purpose") or "analysis"

        # Validate access
        access_valid = self._validate_cross_silo_access(
            requester_org, access_permissions, purpose
        )

        if not access_valid["granted"]:
            return {
                "error": "Access denied",
                "reason": access_valid["reason"],
                "required_permissions": access_valid["required"],
            }

        # Execute query across silos
        silo_results = self._execute_cross_silo_query(query, requester_org)

        # Apply data governance rules
        governed_results = self._apply_governance(
            silo_results, requester_org, self.data_sharing_agreement
        )

        # Generate audit trail
        audit_trail = self._generate_audit_trail(
            query, requester_org, silo_results, governed_results
        )

        # Create compliance report
        compliance_report = self._generate_compliance_report(
            requester_org, access_permissions, governed_results
        )

        return {
            "silo_results": governed_results,
            "audit_trail": (
                audit_trail
                if self.audit_mode != "minimal"
                else "Audit available on request"
            ),
            "compliance_report": compliance_report,
            "federation_metadata": {
                "participating_silos": len(
                    [r for r in silo_results if r["participated"]]
                ),
                "data_sharing_level": self.data_sharing_agreement,
                "governance_applied": True,
            },
        }

    def _validate_cross_silo_access(
        self, requester: str, permissions: List[str], purpose: str
    ) -> Dict[str, Any]:
        """Validate cross-silo access request"""
        # Check if requester is part of federation
        if requester not in self.silos:
            return {
                "granted": False,
                "reason": "Organization not part of federation",
                "required": ["federation_membership"],
            }

        # Check required permissions
        required_permissions = {
            "minimal": ["read_aggregated"],
            "standard": ["read_aggregated", "read_anonymized"],
            "full": ["read_aggregated", "read_anonymized", "read_samples"],
        }

        required = required_permissions.get(
            self.data_sharing_agreement, ["read_aggregated"]
        )

        if not all(perm in permissions for perm in required):
            return {
                "granted": False,
                "reason": "Insufficient permissions",
                "required": required,
            }

        # Purpose-based validation
        allowed_purposes = self.governance_rules.get(
            "allowed_purposes", ["analysis", "research", "compliance", "improvement"]
        )

        if purpose not in allowed_purposes:
            return {
                "granted": False,
                "reason": f"Purpose '{purpose}' not allowed",
                "required": allowed_purposes,
            }

        return {"granted": True, "reason": "Access approved"}

    def _execute_cross_silo_query(
        self, query: str, requester: str
    ) -> List[Dict[str, Any]]:
        """Execute query across organizational silos.

        The caller's permission list is validated upstream by
        ``_validate_cross_silo_access`` before this runs; per-silo
        ``access_level`` here is an organization-relationship decision
        (own silo → full, peer silo → the data-sharing agreement), not a
        re-check of the already-gated permission list.
        """
        silo_results = []

        for silo in self.silos:
            if silo == requester:
                # Full access to own data
                access_level = "full"
            else:
                # Restricted access based on agreement
                access_level = self.data_sharing_agreement

            # Simulate silo response
            if random.random() > 0.1:  # 90% success rate
                results = []

                # Generate results based on access level
                if access_level == "full":
                    results = [
                        {
                            "content": f"Detailed data from {silo}: {query} analysis...",
                            "score": 0.9,
                            "raw_data_included": True,
                        }
                    ]
                elif access_level == "standard":
                    results = [
                        {
                            "content": f"Anonymized data from {silo}: aggregated {query} insights...",
                            "score": 0.8,
                            "raw_data_included": False,
                        }
                    ]
                else:  # minimal
                    results = [
                        {
                            "content": f"Summary from {silo}: high-level {query} trends...",
                            "score": 0.7,
                            "raw_data_included": False,
                        }
                    ]

                silo_results.append(
                    {
                        "silo": silo,
                        "participated": True,
                        "results": results,
                        "access_level": access_level,
                        "response_time": random.uniform(1, 3),
                    }
                )
            else:
                silo_results.append(
                    {
                        "silo": silo,
                        "participated": False,
                        "reason": "Silo temporarily unavailable",
                    }
                )

        return silo_results

    def _apply_governance(
        self, silo_results: List[Dict], requester: str, agreement: str
    ) -> List[Dict[str, Any]]:
        """Apply data governance rules to results"""
        governed_results = []

        for silo_result in silo_results:
            if not silo_result["participated"]:
                governed_results.append(silo_result)
                continue

            # Apply governance based on agreement. ``dict.copy()`` is shallow —
            # the nested ``results`` list would stay shared with silo_result,
            # so the in-place content mutation below would silently govern the
            # pre-governance record too. Rebuild ``results`` with independent
            # per-result dicts so silo_results stays a true pre-governance
            # record and governed_results is the only mutated structure.
            governed_silo_result = silo_result.copy()
            governed_silo_result["results"] = [
                dict(r) if isinstance(r, dict) else r
                for r in silo_result.get("results", [])
            ]

            if silo_result["silo"] != requester:
                # Apply restrictions for other silos
                if agreement == "minimal":
                    # Remove any detailed information
                    for result in governed_silo_result["results"]:
                        result["content"] = self._minimize_content(result["content"])
                        result["governance_applied"] = "minimal_sharing"

                elif agreement == "standard":
                    # Ensure anonymization
                    for result in governed_silo_result["results"]:
                        result["content"] = self._anonymize_content(result["content"])
                        result["governance_applied"] = "anonymized"

            governed_results.append(governed_silo_result)

        return governed_results

    def _minimize_content(self, content: str) -> str:
        """Minimize content to high-level summary"""
        # In production, would use NLP summarization
        words = content.split()[:20]
        return " ".join(words) + "... [Details restricted by data sharing agreement]"

    def _anonymize_content(self, content: str) -> str:
        """Anonymize content while preserving insights"""
        # Simple anonymization (would be more sophisticated in production)
        anonymized = content

        # Remove organization names
        for silo in self.silos:
            anonymized = anonymized.replace(silo, "[Organization]")

        # Remove potential identifiers
        anonymized = re.sub(r"\b\d{3,}\b", "[Number]", anonymized)
        anonymized = re.sub(r"\b[A-Z]{2,}\b", "[Identifier]", anonymized)

        return anonymized

    def _generate_audit_trail(
        self,
        query: str,
        requester: str,
        silo_results: List[Dict],
        governed_results: List[Dict],
    ) -> Dict[str, Any]:
        """Generate comprehensive audit trail"""
        audit = {
            "timestamp": datetime.now().isoformat(),
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16],
            "requester": requester,
            "federation_activity": {
                "silos_queried": len(self.silos),
                "silos_responded": len([r for r in silo_results if r["participated"]]),
                "data_governance_applied": True,
            },
            "data_flow": [],
        }

        # Track data flow. The governance markers are read from
        # governed_results (the actual post-governance output returned to the
        # requester) so the audit records what governance produced, not the
        # pre-governance silo response.
        governed_by_silo = {gr["silo"]: gr for gr in governed_results}
        for silo_result in silo_results:
            governed = governed_by_silo.get(silo_result["silo"], silo_result)
            flow = {
                "silo": silo_result["silo"],
                "data_shared": silo_result["participated"],
                "access_level": silo_result.get("access_level", "none"),
                "governance_applied": any(
                    r.get("governance_applied") for r in governed.get("results", [])
                ),
            }
            audit["data_flow"].append(flow)

        if self.audit_mode == "comprehensive":
            # Add detailed audit information
            audit["detailed_access"] = {
                "permissions_used": ["read_aggregated"],
                "data_categories_accessed": ["aggregated_insights"],
                "purpose_stated": "analysis",
                "retention_period": "0 days",  # No retention
            }

        return audit

    def _generate_compliance_report(
        self, requester: str, permissions: List[str], results: List[Dict]
    ) -> Dict[str, Any]:
        """Generate a compliance report derived from the actual request.

        The verdict reflects the real ``requester``, the ``permissions`` that
        were granted, and the governed ``results`` that crossed the boundary —
        it is NOT a fixed "compliant" stamp. ``data_minimization`` is True only
        when every peer silo's result actually carries a governance marker;
        ``compliance_status`` degrades to "non_compliant" when a peer silo's
        data crossed without governance applied.
        """
        # A peer silo is any participating silo other than the requester's own.
        peer_results = [
            r for r in results if r.get("participated") and r.get("silo") != requester
        ]
        # Every peer silo's content must carry a governance marker.
        ungoverned_peers = [
            r
            for r in peer_results
            if not all(item.get("governance_applied") for item in r.get("results", []))
        ]
        data_minimization = len(ungoverned_peers) == 0

        return {
            "compliance_status": (
                "compliant" if data_minimization else "non_compliant"
            ),
            "regulations_checked": ["GDPR", "CCPA", "Industry Standards"],
            "requester": requester,
            "permissions_granted": list(permissions),
            "peer_silos_governed": len(peer_results) - len(ungoverned_peers),
            "peer_silos_total": len(peer_results),
            "data_minimization": data_minimization,
            "purpose_limitation": True,
            "access_controls": "enforced",
            "audit_trail": "maintained",
            "data_retention": "none",
            "cross_border_transfer": "not_applicable",
            "user_rights": {
                "access": "supported",
                "rectification": "supported",
                "erasure": "supported",
                "portability": "limited",
            },
        }


# Export all federated nodes
__all__ = ["FederatedRAGNode", "EdgeRAGNode", "CrossSiloRAGNode"]
