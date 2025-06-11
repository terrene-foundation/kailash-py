"""Node-specific cycle tests for Data processing nodes.

Tests data processing nodes in cyclic workflows to ensure proper data
transformation, embedding generation, and progressive data improvement.

Covers:
- DataTransformer: Progressive data improvement
- EmbeddingGeneratorNode: RAG cycle refinement
- Data readers/writers: Iterative data processing
"""

import json
import os
import tempfile
from typing import Any

from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime


class MockDataTransformerNode(CycleAwareNode):
    """Mock data transformer for testing cycles."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "transformation_type": NodeParameter(
                name="transformation_type", type=str, required=False, default="clean"
            ),
            "quality_threshold": NodeParameter(
                name="quality_threshold", type=float, required=False, default=0.8
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        data = kwargs.get("data", [])
        transformation_type = kwargs.get("transformation_type", "clean")
        quality_threshold = kwargs.get("quality_threshold", 0.8)
        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        if not data:
            return {
                "transformed_data": [],
                "quality_score": 0.0,
                "transformation_count": 0,
                "converged": True,
            }

        # Apply different transformations based on type
        if transformation_type == "clean":
            # Remove invalid entries progressively
            transformed_data = []
            for item in data:
                if isinstance(item, (int, float)) and item >= 0:
                    transformed_data.append(item)
                elif isinstance(item, str) and len(item.strip()) > 0:
                    transformed_data.append(item.strip())

        elif transformation_type == "normalize":
            # Normalize numeric data
            numeric_data = [x for x in data if isinstance(x, (int, float))]
            if numeric_data:
                min_val = min(numeric_data)
                max_val = max(numeric_data)
                if max_val > min_val:
                    transformed_data = [
                        (x - min_val) / (max_val - min_val) for x in numeric_data
                    ]
                else:
                    transformed_data = [0.5] * len(numeric_data)
            else:
                transformed_data = data

        elif transformation_type == "aggregate":
            # Group similar items
            if all(isinstance(x, (int, float)) for x in data):
                # Group by ranges
                ranges = {"low": [], "medium": [], "high": []}
                for x in data:
                    if x < 0.33:
                        ranges["low"].append(x)
                    elif x < 0.67:
                        ranges["medium"].append(x)
                    else:
                        ranges["high"].append(x)
                transformed_data = [
                    {"range": k, "values": v, "count": len(v)}
                    for k, v in ranges.items()
                    if v
                ]
            else:
                transformed_data = data
        else:
            transformed_data = data

        # Calculate quality score
        if isinstance(transformed_data, list) and len(data) > 0:
            quality_score = len(transformed_data) / len(data)
        else:
            quality_score = 1.0 if transformed_data else 0.0

        # Track transformation history
        transformation_history = prev_state.get("transformation_history", [])
        transformation_history.append(
            {
                "iteration": iteration + 1,
                "type": transformation_type,
                "input_size": len(data),
                "output_size": (
                    len(transformed_data) if isinstance(transformed_data, list) else 1
                ),
                "quality": quality_score,
            }
        )

        self.set_cycle_state({"transformation_history": transformation_history})

        converged = quality_score >= quality_threshold or iteration >= 10

        return {
            "transformed_data": transformed_data,
            "quality_score": quality_score,
            "transformation_count": len(transformation_history),
            "transformation_type": transformation_type,
            "converged": converged,
        }


class MockEmbeddingGeneratorNode(CycleAwareNode):
    """Mock embedding generator for testing cycles."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "texts": NodeParameter(name="texts", type=list, required=False, default=[]),
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                required=False,
                default="mock-embedding-model",
            ),
            "refinement_iterations": NodeParameter(
                name="refinement_iterations", type=int, required=False, default=3
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        texts = kwargs.get("texts", [])
        model_name = kwargs.get("model_name", "mock-embedding-model")
        refinement_iterations = kwargs.get("refinement_iterations", 3)
        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        if not texts:
            return {
                "embeddings": [],
                "refined_texts": [],
                "embedding_quality": 0.0,
                "converged": True,
            }

        # Simulate text refinement for better embeddings
        refined_texts = []
        for text in texts:
            if isinstance(text, str):
                # Progressive text refinement
                if iteration == 0:
                    refined_text = text.strip().lower()
                elif iteration == 1:
                    refined_text = " ".join(
                        text.strip().lower().split()
                    )  # Remove extra spaces
                else:
                    # Add context or expand abbreviations (simplified)
                    refined_text = text.strip().lower().replace("&", "and")
            else:
                refined_text = str(text)
            refined_texts.append(refined_text)

        # Generate mock embeddings (simulate improving quality)
        embeddings = []
        base_quality = 0.5 + (iteration * 0.15)  # Quality improves with refinement

        for i, text in enumerate(refined_texts):
            # Mock embedding as list of floats
            embedding_dim = 384  # Typical embedding dimension
            # Use text hash for deterministic "embedding"
            text_hash = hash(text + str(iteration))
            embedding = [(text_hash + j) / 1000000.0 for j in range(embedding_dim)]
            embeddings.append(embedding)

        embedding_quality = min(base_quality, 0.95)

        # Track refinement history
        refinement_history = prev_state.get("refinement_history", [])
        refinement_history.append(
            {
                "iteration": iteration + 1,
                "text_count": len(texts),
                "quality": embedding_quality,
                "avg_text_length": sum(len(str(t)) for t in refined_texts)
                / len(refined_texts),
            }
        )

        self.set_cycle_state({"refinement_history": refinement_history})

        converged = (
            embedding_quality >= 0.8
            or iteration >= refinement_iterations
            or iteration >= 5
        )

        return {
            "embeddings": embeddings,
            "refined_texts": refined_texts,
            "embedding_quality": embedding_quality,
            "model_name": model_name,
            "refinement_count": len(refinement_history),
            "converged": converged,
        }


class TestDataTransformerCycles:
    """Test data transformer nodes in cyclic workflows."""

    def test_data_transformer_progressive_cleaning(self):
        """Test data transformer for progressive data cleaning."""
        workflow = Workflow("data-cleaning-cycle", "Data Cleaning Cycle")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "data": NodeParameter(name="data", type=list, required=False),
                    "transformation_type": NodeParameter(
                        name="transformation_type", type=str, required=False
                    ),
                    "quality_threshold": NodeParameter(
                        name="quality_threshold", type=float, required=False
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                return {
                    "data": kwargs.get("data", []),
                    "transformation_type": kwargs.get("transformation_type", "clean"),
                    "quality_threshold": kwargs.get("quality_threshold", 0.7),
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("transformer", MockDataTransformerNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "transformer",
            mapping={
                "data": "data",
                "transformation_type": "transformation_type",
                "quality_threshold": "quality_threshold",
            },
        )

        # Create cleaning cycle with specific field mapping
        workflow.connect(
            "transformer",
            "transformer",
            mapping={
                "transformed_data": "data",
                "transformation_type": "transformation_type",
                "quality_threshold": "quality_threshold",
            },
            cycle=True,
            max_iterations=8,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "data": [1, -2, 3, "", 4, None, 5, "  ", 6, -1, 7],
                    "transformation_type": "clean",
                    "quality_threshold": 0.7,
                }
            },
        )

        assert run_id is not None
        final_output = results["transformer"]
        assert final_output["converged"] is True
        assert final_output["quality_score"] >= 0.7

        # Should have removed invalid entries
        transformed_data = final_output["transformed_data"]
        assert all(isinstance(x, (int, float, str)) for x in transformed_data)
        assert all(
            x >= 0 if isinstance(x, (int, float)) else len(x.strip()) > 0
            for x in transformed_data
        )

    def test_data_transformer_multi_stage_processing(self):
        """Test data transformer with multiple transformation stages."""
        workflow = Workflow("multi-stage-transform", "Multi Stage Transform")

        class MultiStageTransformerNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "data": NodeParameter(
                        name="data", type=list, required=False, default=[]
                    ),
                    "stage": NodeParameter(
                        name="stage", type=str, required=False, default="clean"
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                data = kwargs.get("data", [])
                kwargs.get("stage", "clean")
                iteration = self.get_iteration(context)

                # Define processing stages
                stages = ["clean", "normalize", "aggregate", "finalize"]
                stage_index = min(iteration, len(stages) - 1)
                next_stage = stages[stage_index]

                # Apply transformation based on current stage
                if next_stage == "clean":
                    # Remove negative numbers and empty strings
                    transformed_data = [
                        x
                        for x in data
                        if (isinstance(x, (int, float)) and x >= 0)
                        or (isinstance(x, str) and x.strip())
                    ]
                elif next_stage == "normalize":
                    # Normalize numeric values to 0-1 range
                    numeric_data = [x for x in data if isinstance(x, (int, float))]
                    if numeric_data:
                        min_val = min(numeric_data)
                        max_val = max(numeric_data)
                        if max_val > min_val:
                            transformed_data = [
                                (x - min_val) / (max_val - min_val)
                                for x in numeric_data
                            ]
                        else:
                            transformed_data = [0.5] * len(numeric_data)
                    else:
                        transformed_data = data
                elif next_stage == "aggregate":
                    # Group into statistical summary
                    if data and all(isinstance(x, (int, float)) for x in data):
                        transformed_data = {
                            "count": len(data),
                            "mean": sum(data) / len(data),
                            "min": min(data),
                            "max": max(data),
                            "sum": sum(data),
                        }
                    else:
                        transformed_data = {"count": len(data), "items": data}
                else:  # finalize
                    # Final stage - return summary
                    if isinstance(data, dict):
                        transformed_data = data
                    else:
                        transformed_data = {"final_result": data, "processed": True}

                converged = next_stage == "finalize" or iteration >= len(stages)

                return {
                    "transformed_data": transformed_data,
                    "current_stage": next_stage,
                    "stage_index": stage_index,
                    "converged": converged,
                }

        workflow.add_node("multi_stage", MultiStageTransformerNode())

        workflow.connect(
            "multi_stage",
            "multi_stage",
            mapping={"transformed_data": "data", "current_stage": "stage"},
            cycle=True,
            max_iterations=6,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"data": [1, 2, -3, 4, 5, "", 6, 7, 8, -9, 10]}
        )

        assert run_id is not None
        final_output = results["multi_stage"]
        assert final_output["converged"] is True
        assert final_output["current_stage"] == "finalize"

        # Final result should be a processed summary
        transformed_data = final_output["transformed_data"]
        assert isinstance(transformed_data, dict)

    def test_data_transformer_quality_convergence(self):
        """Test data transformer converging on quality metrics."""
        workflow = Workflow(
            "quality-convergence-transform", "Quality Convergence Transform"
        )

        class QualityConvergenceNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "dataset": NodeParameter(
                        name="dataset", type=list, required=False, default=[]
                    ),
                    "target_quality": NodeParameter(
                        name="target_quality", type=float, required=False, default=0.9
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                dataset = kwargs.get("dataset", [])
                target_quality = kwargs.get("target_quality", 0.9)
                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Track quality improvements over iterations
                quality_history = prev_state.get("quality_history", [])

                # Simulate progressive quality improvement
                if not dataset:
                    quality_score = 0.0
                    cleaned_dataset = []
                else:
                    # Progressive cleaning - remove more outliers each iteration
                    numeric_data = [x for x in dataset if isinstance(x, (int, float))]

                    if numeric_data:
                        mean_val = sum(numeric_data) / len(numeric_data)
                        variance = sum((x - mean_val) ** 2 for x in numeric_data) / len(
                            numeric_data
                        )
                        std_dev = variance**0.5

                        # Progressive outlier removal - tighten threshold each iteration
                        threshold_factor = 3.0 - (
                            iteration * 0.5
                        )  # Start with 3σ, tighten to 0.5σ
                        threshold_factor = max(threshold_factor, 0.5)

                        if std_dev > 0:
                            cleaned_dataset = [
                                x
                                for x in numeric_data
                                if abs(x - mean_val) <= threshold_factor * std_dev
                            ]
                        else:
                            cleaned_dataset = numeric_data

                        quality_score = len(cleaned_dataset) / len(dataset)
                    else:
                        cleaned_dataset = dataset
                        quality_score = 1.0

                quality_history.append(quality_score)
                self.set_cycle_state({"quality_history": quality_history})

                # Check for quality convergence
                converged = (
                    quality_score >= target_quality
                    or iteration >= 10
                    or (
                        len(quality_history) >= 3
                        and all(
                            abs(quality_history[-1] - q) < 0.01
                            for q in quality_history[-3:]
                        )
                    )
                )

                return {
                    "cleaned_dataset": cleaned_dataset,
                    "quality_score": quality_score,
                    "quality_history": quality_history,
                    "target_quality": target_quality,
                    "converged": converged,
                }

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "dataset": NodeParameter(name="dataset", type=list, required=False),
                    "target_quality": NodeParameter(
                        name="target_quality", type=float, required=False
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                return {
                    "dataset": kwargs.get("dataset", []),
                    "target_quality": kwargs.get("target_quality", 0.85),
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("quality_transformer", QualityConvergenceNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "quality_transformer",
            mapping={"dataset": "dataset", "target_quality": "target_quality"},
        )

        # Cycle with specific field mapping
        workflow.connect(
            "quality_transformer",
            "quality_transformer",
            mapping={"cleaned_dataset": "dataset", "target_quality": "target_quality"},
            cycle=True,
            max_iterations=12,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "dataset": [
                        1,
                        2,
                        3,
                        100,
                        4,
                        5,
                        6,
                        200,
                        7,
                        8,
                        9,
                        300,
                        10,
                    ],  # Has outliers
                    "target_quality": 0.85,
                }
            },
        )

        assert run_id is not None
        final_output = results["quality_transformer"]
        assert final_output["converged"] is True
        assert (
            final_output["quality_score"] >= 0.85
            or len(final_output["quality_history"]) >= 3
        )


class TestEmbeddingGeneratorCycles:
    """Test embedding generator nodes in cyclic workflows."""

    def test_embedding_generator_iterative_refinement(self):
        """Test embedding generator with iterative text refinement."""
        workflow = Workflow("embedding-refinement-cycle", "Embedding Refinement Cycle")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "texts": NodeParameter(name="texts", type=list, required=False),
                    "model_name": NodeParameter(
                        name="model_name", type=str, required=False
                    ),
                    "refinement_iterations": NodeParameter(
                        name="refinement_iterations", type=int, required=False
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                return {
                    "texts": kwargs.get("texts", []),
                    "model_name": kwargs.get("model_name", "text-embedding-ada-002"),
                    "refinement_iterations": kwargs.get("refinement_iterations", 3),
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("embedding_gen", MockEmbeddingGeneratorNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "embedding_gen",
            mapping={
                "texts": "texts",
                "model_name": "model_name",
                "refinement_iterations": "refinement_iterations",
            },
        )

        # Create refinement cycle with specific field mapping
        workflow.connect(
            "embedding_gen",
            "embedding_gen",
            mapping={
                "refined_texts": "texts",
                "model_name": "model_name",
                "refinement_iterations": "refinement_iterations",
            },
            cycle=True,
            max_iterations=6,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "texts": [
                        "The quick brown fox",
                        "Machine learning & AI",
                        "  Data   processing  ",
                        "NLP & embeddings",
                    ],
                    "model_name": "text-embedding-ada-002",
                    "refinement_iterations": 3,
                }
            },
        )

        assert run_id is not None
        final_output = results["embedding_gen"]
        assert final_output["converged"] is True
        assert final_output["embedding_quality"] >= 0.8
        assert len(final_output["embeddings"]) == 4
        assert len(final_output["embeddings"][0]) == 384  # Mock embedding dimension

        # Text should be refined
        refined_texts = final_output["refined_texts"]
        assert all(isinstance(text, str) for text in refined_texts)
        assert "and" in " ".join(refined_texts)  # & should be replaced with "and"

    def test_embedding_rag_cycle_pattern(self):
        """Test embedding generator in RAG-style iterative cycles."""
        workflow = Workflow("rag-embedding-cycle", "RAG Embedding Cycle")

        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "query": NodeParameter(name="query", type=str, required=False),
                    "documents": NodeParameter(
                        name="documents", type=list, required=False
                    ),
                    "top_k": NodeParameter(name="top_k", type=int, required=False),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                return {
                    "query": kwargs.get("query", ""),
                    "documents": kwargs.get("documents", []),
                    "top_k": kwargs.get("top_k", 3),
                }

        class RAGEmbeddingNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "query": NodeParameter(
                        name="query", type=str, required=False, default=""
                    ),
                    "documents": NodeParameter(
                        name="documents", type=list, required=False, default=[]
                    ),
                    "top_k": NodeParameter(
                        name="top_k", type=int, required=False, default=3
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                query = kwargs.get("query", "")
                documents = kwargs.get("documents", [])
                top_k = kwargs.get("top_k", 3)
                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Simulate query expansion based on previous results
                if iteration == 0:
                    expanded_query = query
                else:
                    # Add context from previous iterations
                    previous_context = prev_state.get("context", [])
                    context_terms = (
                        " ".join(previous_context[-2:]) if previous_context else ""
                    )
                    expanded_query = f"{query} {context_terms}".strip()

                # Generate mock embeddings
                query_embedding = [
                    hash(expanded_query + str(i)) / 1000000.0 for i in range(384)
                ]

                # Simulate document similarity search
                doc_similarities = []
                for i, doc in enumerate(documents):
                    # Mock similarity calculation
                    doc_hash = hash(str(doc) + expanded_query)
                    similarity = (doc_hash % 100) / 100.0  # 0-1 similarity
                    doc_similarities.append((i, doc, similarity))

                # Sort by similarity and get top-k
                doc_similarities.sort(key=lambda x: x[2], reverse=True)
                top_documents = doc_similarities[:top_k]

                # Extract context for next iteration
                context_terms = []
                for _, doc, _ in top_documents:
                    if isinstance(doc, str):
                        # Extract key terms (simplified)
                        words = doc.lower().split()
                        context_terms.extend(words[:2])  # Take first 2 words

                # Update state
                all_context = prev_state.get("context", [])
                all_context.extend(context_terms)
                self.set_cycle_state({"context": all_context})

                # Calculate relevance score (improves with iterations)
                base_relevance = 0.4 + (iteration * 0.2)
                relevance_score = min(base_relevance, 0.9)

                converged = relevance_score >= 0.8 or iteration >= 4

                return {
                    "expanded_query": expanded_query,
                    "query": query,
                    "documents": documents,
                    "top_k": top_k,
                    "query_embedding": query_embedding,
                    "top_documents": [
                        {"doc": doc, "similarity": sim} for _, doc, sim in top_documents
                    ],
                    "relevance_score": relevance_score,
                    "context_count": len(all_context),
                    "converged": converged,
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("rag_embedder", RAGEmbeddingNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "rag_embedder",
            mapping={"query": "query", "documents": "documents", "top_k": "top_k"},
        )

        # Create cycle with specific field mapping
        workflow.connect(
            "rag_embedder",
            "rag_embedder",
            mapping={
                "expanded_query": "query",
                "documents": "documents",
                "top_k": "top_k",
            },
            cycle=True,
            max_iterations=6,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "data_source": {
                    "query": "machine learning algorithms",
                    "documents": [
                        "Neural networks are powerful machine learning models",
                        "Decision trees provide interpretable predictions",
                        "Support vector machines work well for classification",
                        "Random forests combine multiple decision trees",
                        "Deep learning uses neural networks with many layers",
                    ],
                    "top_k": 3,
                }
            },
        )

        assert run_id is not None
        final_output = results["rag_embedder"]
        assert final_output["converged"] is True
        assert final_output["relevance_score"] >= 0.8
        assert len(final_output["top_documents"]) == 3
        assert final_output["context_count"] > 0


class TestDataIOCycles:
    """Test data I/O nodes in cyclic workflows."""

    def test_csv_reader_writer_cycle(self):
        """Test CSV reader/writer in iterative processing cycle."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create initial CSV file
            input_file = os.path.join(temp_dir, "input.csv")
            output_file = os.path.join(temp_dir, "output.csv")

            with open(input_file, "w") as f:
                f.write("id,value,status\n")
                f.write("1,10,pending\n")
                f.write("2,20,pending\n")
                f.write("3,30,pending\n")
                f.write("4,40,pending\n")

            workflow = Workflow("csv-processing-cycle", "CSV Processing Cycle")

            class CSVProcessorNode(CycleAwareNode):
                def get_parameters(self) -> dict[str, NodeParameter]:
                    return {
                        "data": NodeParameter(
                            name="data", type=list, required=False, default=[]
                        ),
                        "batch_size": NodeParameter(
                            name="batch_size", type=int, required=False, default=2
                        ),
                    }

                def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                    data = kwargs.get("data", [])
                    batch_size = kwargs.get("batch_size", 2)
                    iteration = self.get_iteration(context)
                    prev_state = self.get_previous_state(context)

                    processed_count = prev_state.get("processed_count", 0)

                    # Process data in batches
                    processed_data = []
                    current_batch = 0

                    for row in data:
                        if current_batch < batch_size:
                            # Mark as processed
                            processed_row = row.copy() if isinstance(row, dict) else row
                            if (
                                isinstance(processed_row, dict)
                                and "status" in processed_row
                            ):
                                processed_row["status"] = "processed"
                            processed_data.append(processed_row)
                            current_batch += 1
                        else:
                            # Leave for next iteration
                            processed_data.append(row)

                    new_processed_count = processed_count + current_batch
                    self.set_cycle_state({"processed_count": new_processed_count})

                    # Check if all data is processed
                    total_items = len(data)
                    all_processed = (
                        all(
                            (isinstance(row, dict) and row.get("status") == "processed")
                            for row in processed_data
                        )
                        if data
                        else True
                    )

                    converged = all_processed or iteration >= 5

                    return {
                        "processed_data": processed_data,
                        "processed_count": new_processed_count,
                        "total_items": total_items,
                        "converged": converged,
                    }

            workflow.add_node("csv_reader", CSVReaderNode(file_path=input_file))
            workflow.add_node("processor", CSVProcessorNode())
            workflow.add_node("csv_writer", CSVWriterNode(file_path=output_file))

            # Initial flow
            # Add a data source node for batch_size parameter
            class DataSourceNode(CycleAwareNode):
                def get_parameters(self) -> dict[str, NodeParameter]:
                    return {
                        "batch_size": NodeParameter(
                            name="batch_size", type=int, required=False
                        )
                    }

                def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                    return {"batch_size": kwargs.get("batch_size", 2)}

            workflow.add_node("data_source", DataSourceNode())

            # Initial flow
            workflow.connect("csv_reader", "processor", mapping={"data": "data"})
            workflow.connect(
                "data_source", "processor", mapping={"batch_size": "batch_size"}
            )
            workflow.connect(
                "processor", "csv_writer", mapping={"processed_data": "data"}
            )

            # Cycle back to processor with specific field mapping
            workflow.connect(
                "processor",
                "processor",
                mapping={"processed_data": "data", "batch_size": "batch_size"},
                cycle=True,
                max_iterations=6,
                convergence_check="converged == True",
            )

            runtime = LocalRuntime()
            results, run_id = runtime.execute(
                workflow, parameters={"data_source": {"batch_size": 2}}
            )

            assert run_id is not None
            final_output = results["processor"]
            assert final_output["converged"] is True

    def test_json_incremental_processing(self):
        """Test JSON processing with incremental updates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create initial JSON file
            input_file = os.path.join(temp_dir, "data.json")
            initial_data = {
                "items": [
                    {"id": 1, "value": 10, "processed": False},
                    {"id": 2, "value": 20, "processed": False},
                    {"id": 3, "value": 30, "processed": False},
                    {"id": 4, "value": 40, "processed": False},
                ],
                "metadata": {"total": 4, "processed_count": 0},
            }

            with open(input_file, "w") as f:
                json.dump(initial_data, f)

            workflow = Workflow("json-incremental-cycle", "JSON Incremental Cycle")

            class JSONIncrementalProcessor(CycleAwareNode):
                def get_parameters(self) -> dict[str, NodeParameter]:
                    return {
                        "json_data": NodeParameter(
                            name="json_data", type=dict, required=False, default={}
                        ),
                        "items_per_iteration": NodeParameter(
                            name="items_per_iteration",
                            type=int,
                            required=False,
                            default=2,
                        ),
                    }

                def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                    json_data = kwargs.get("json_data", {})
                    items_per_iteration = kwargs.get("items_per_iteration", 2)
                    iteration = self.get_iteration(context)

                    items = json_data.get("items", [])
                    metadata = json_data.get("metadata", {})

                    # Process unprocessed items in batches
                    processed_count = 0
                    for item in items:
                        if (
                            not item.get("processed", False)
                            and processed_count < items_per_iteration
                        ):
                            item["processed"] = True
                            item["processed_iteration"] = iteration + 1
                            item["processed_value"] = (
                                item.get("value", 0) * 2
                            )  # Double the value
                            processed_count += 1

                    # Update metadata
                    total_processed = sum(
                        1 for item in items if item.get("processed", False)
                    )
                    metadata["processed_count"] = total_processed
                    metadata["completion_rate"] = (
                        total_processed / len(items) if items else 0
                    )

                    updated_data = {"items": items, "metadata": metadata}

                    converged = total_processed >= len(items) or iteration >= 6

                    return {
                        "updated_json": updated_data,
                        "items_processed_this_round": processed_count,
                        "total_processed": total_processed,
                        "completion_rate": metadata["completion_rate"],
                        "converged": converged,
                    }

            workflow.add_node("json_reader", JSONReaderNode(file_path=input_file))
            workflow.add_node("json_processor", JSONIncrementalProcessor())

            # Add a data source node for items_per_iteration parameter
            class DataSourceNode(CycleAwareNode):
                def get_parameters(self) -> dict[str, NodeParameter]:
                    return {
                        "items_per_iteration": NodeParameter(
                            name="items_per_iteration", type=int, required=False
                        )
                    }

                def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                    return {"items_per_iteration": kwargs.get("items_per_iteration", 2)}

            workflow.add_node("data_source", DataSourceNode())

            # Initial connections
            workflow.connect(
                "json_reader", "json_processor", mapping={"data": "json_data"}
            )
            workflow.connect(
                "data_source",
                "json_processor",
                mapping={"items_per_iteration": "items_per_iteration"},
            )

            # Cycle with specific field mapping
            workflow.connect(
                "json_processor",
                "json_processor",
                mapping={
                    "updated_json": "json_data",
                    "items_per_iteration": "items_per_iteration",
                },
                cycle=True,
                max_iterations=8,
                convergence_check="converged == True",
            )

            runtime = LocalRuntime()
            results, run_id = runtime.execute(
                workflow, parameters={"data_source": {"items_per_iteration": 1}}
            )

            assert run_id is not None
            final_output = results["json_processor"]
            assert final_output["converged"] is True
            assert final_output["completion_rate"] == 1.0

            # All items should be processed
            updated_data = final_output["updated_json"]
            assert all(item["processed"] for item in updated_data["items"])


class TestDataNodePerformance:
    """Test performance characteristics of data nodes in cycles."""

    def test_large_dataset_cycle_performance(self):
        """Test data processing cycles with large datasets."""
        workflow = Workflow("large-dataset-cycle", "Large Dataset Cycle")

        class LargeDataProcessorNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "dataset": NodeParameter(
                        name="dataset", type=list, required=False, default=[]
                    ),
                    "chunk_size": NodeParameter(
                        name="chunk_size", type=int, required=False, default=1000
                    ),
                    "processed_items": NodeParameter(
                        name="processed_items", type=int, required=False, default=0
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                dataset = kwargs.get("dataset", [])
                chunk_size = kwargs.get("chunk_size", 1000)
                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # On subsequent iterations, use the passed processed_items count
                if iteration > 0:
                    processed_items = kwargs.get("processed_items", 0)
                else:
                    processed_items = prev_state.get("processed_items", 0)

                # Process chunk of data
                start_idx = processed_items
                end_idx = min(start_idx + chunk_size, len(dataset))

                if start_idx >= len(dataset):
                    # All data processed
                    chunk_result = []
                    new_processed = processed_items
                else:
                    # Process chunk (simple transformation)
                    chunk = dataset[start_idx:end_idx]
                    chunk_result = [
                        x * 2 if isinstance(x, (int, float)) else str(x).upper()
                        for x in chunk
                    ]
                    new_processed = end_idx

                self.set_cycle_state({"processed_items": new_processed})

                progress = new_processed / len(dataset) if dataset else 1.0
                converged = progress >= 1.0 or iteration >= 20

                return {
                    "chunk_result": chunk_result,
                    "processed_items": new_processed,
                    "total_items": len(dataset),
                    "progress": progress,
                    "chunk_size": len(chunk_result),
                    "converged": converged,
                }

        # Add a data source node for parameters
        class DataSourceNode(CycleAwareNode):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "dataset": NodeParameter(name="dataset", type=list, required=False),
                    "chunk_size": NodeParameter(
                        name="chunk_size", type=int, required=False
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                return {
                    "dataset": kwargs.get("dataset", []),
                    "chunk_size": kwargs.get("chunk_size", 1000),
                }

        workflow.add_node("data_source", DataSourceNode())
        workflow.add_node("large_processor", LargeDataProcessorNode())

        # Initial data flow
        workflow.connect(
            "data_source",
            "large_processor",
            mapping={"dataset": "dataset", "chunk_size": "chunk_size"},
        )

        # Cycle with specific field mapping to preserve all necessary data
        workflow.connect(
            "large_processor",
            "large_processor",
            mapping={
                "dataset": "dataset",
                "chunk_size": "chunk_size",
                "processed_items": "processed_items",
            },
            cycle=True,
            max_iterations=25,
            convergence_check="converged == True",
        )

        # Create large dataset
        large_dataset = list(range(10000))  # 10K items

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={"data_source": {"dataset": large_dataset, "chunk_size": 1500}},
        )

        assert run_id is not None
        final_output = results["large_processor"]
        assert final_output["converged"] is True
        assert final_output["progress"] == 1.0
        assert final_output["processed_items"] == 10000
