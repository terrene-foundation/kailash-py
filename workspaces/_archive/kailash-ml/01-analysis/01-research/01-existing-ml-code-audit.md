# Existing ML Code Audit

## Purpose

Audit the entire kailash-py codebase for existing ML-related code, model management, inference patterns, and AI node types that kailash-ml must integrate with or avoid colliding with.

## Findings

### 1. No Existing ML Package

There is no `packages/kailash-ml/` directory. No `src/kailash/ml/` module. No existing ML training, inference, or model management code in the SDK proper. kailash-ml is genuinely greenfield.

### 2. DataFlow ModelRegistry (NAMING CONFLICT)

**Critical finding**: `packages/kailash-dataflow/src/dataflow/core/model_registry.py` contains a class called `ModelRegistry`. This is a **DataFlow model definition registry** -- it tracks which Python class definitions are registered as DataFlow models (e.g., User, Product). It has nothing to do with ML model lifecycle management.

**Impact on kailash-ml**: The kailash-ml `ModelRegistry` (ML model lifecycle: staging, shadow, production, archived) is a completely different concept. However, the name collision means:

- Import paths must be unambiguous: `from kailash_ml.engines.model_registry import ModelRegistry` vs `from dataflow.core.model_registry import ModelRegistry`
- Documentation must clarify: "DataFlow ModelRegistry" = Python class definitions; "kailash-ml ModelRegistry" = trained ML model lifecycle
- In code that uses both (e.g., FeatureStore creating DataFlow models AND registering ML models), variable names must disambiguate (e.g., `df_registry` vs `ml_registry`)

**Recommendation**: Accept the naming overlap. Different packages, different import paths, well-documented distinction. Renaming either would break established APIs.

### 3. LLMAgentNode (Kaizen AI Node)

`LLMAgentNode` exists in `kaizen.nodes.ai` and is referenced from:

- `src/kailash/nodes/validation.py` (in the `llm_tasks` category alongside `A2AAgentNode`, `MCPAgentNode`)
- `src/kailash/workflow/templates.py` (document processing template uses it with model name and prompt template)
- `src/kailash/runtime/validation/suggestion_engine.py` (node suggestion patterns)

**How it works**: `LLMAgentNode` is a workflow node that wraps an LLM call. It accepts a model name and prompt template. It is NOT an ML training node -- it is a Kaizen agent node for text processing.

**Impact on kailash-ml**: kailash-ml does not need to create its own LLM nodes. When agent-augmented engines need LLM calls, they use the Kaizen `Delegate` pattern (which internally may use `LLMAgentNode`). kailash-ml's agents are consumers of Kaizen, not reimplementors.

### 4. Vector/Embedding Nodes (Core SDK)

`src/kailash/nodes/data/` contains:

- `vector_db.py`: `EmbeddingNode`, `VectorDatabaseNode`
- `async_vector.py`: `AsyncPostgreSQLVectorNode`
- `retrieval.py`: `ChunkRelevanceScorerNode` with similarity methods (cosine, BM25, TF-IDF)

These are RAG (retrieval-augmented generation) infrastructure nodes. They compute and store embeddings for document retrieval.

**Impact on kailash-ml**: These overlap with potential kailash-ml embedding features but serve a different purpose (document retrieval vs. ML feature engineering). kailash-ml's FeatureStore does NOT need to duplicate these. If kailash-ml needs embedding features, it should use these existing nodes via WorkflowBuilder, not reimplement cosine similarity.

### 5. Node Categories (140+ Nodes)

The `src/kailash/nodes/` directory contains categories: admin, alerts, api, auth, cache, code, compliance, data, edge, enterprise, governance, logic, mixins, monitoring, security, system, testing, transform, transaction, validation.

There is **no** `ai/` or `ml/` node category. The AI/ML nodes live in the Kaizen package (`kaizen.nodes.ai`), not in the core SDK node tree.

**Impact on kailash-ml**: kailash-ml engines do not need to create core SDK nodes. The engines themselves ARE the abstraction layer above nodes. However, if kailash-ml needs workflow orchestration for training pipelines, it can use `WorkflowBuilder` + existing nodes (data loading, transformation) and add its own training step as a high-level engine method.

### 6. No polars Usage in Existing Codebase

Searched the entire `src/` and `packages/` directories. **Zero** files reference `polars`, `pl.DataFrame`, or `pl.LazyFrame`. The entire Kailash ecosystem currently uses Python dicts, lists, and occasionally pandas (via LightGBM in the DataFlow model registry tests, if any). kailash-ml will be the first framework to introduce polars as a core data type.

**Impact on kailash-ml**: This is both a clean slate (no existing polars patterns to conflict with) and a friction point (no existing interop utilities). The `kailash_ml.interop` module must be robust because it is the sole bridge between the polars-native ML layer and the dict-based ecosystem.

### 7. Existing Model/Prediction Terminology

The following files use "model" or "predict" in ML-adjacent contexts:

- `src/kailash/nodes/security/behavior_analysis.py`: Behavioral anomaly detection (not ML model training)
- `src/kailash/workflow/type_inference.py`: Type inference for workflow parameters (not ML inference)
- `src/kailash/nodes/monitoring/performance_benchmark.py`: Performance benchmarking (not ML performance)

None of these represent actual ML functionality. The terms are used in their general computing sense.

## Summary

| Area                   | Finding                            | Impact                                                |
| ---------------------- | ---------------------------------- | ----------------------------------------------------- |
| ML packages            | None exist                         | Clean greenfield                                      |
| DataFlow ModelRegistry | Name collision (different concept) | Disambiguate in docs + code                           |
| LLMAgentNode           | Exists in Kaizen                   | kailash-ml agents use Delegate, not raw nodes         |
| Vector/Embedding nodes | Exist for RAG                      | kailash-ml reuses via WorkflowBuilder if needed       |
| polars                 | Zero adoption                      | kailash-ml is the pioneer; interop module is critical |
| AI/ML node category    | Does not exist                     | Engines are the abstraction, not nodes                |
