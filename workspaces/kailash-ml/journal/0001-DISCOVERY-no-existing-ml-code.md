---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T10:00:00Z
author: agent
session_turn: 1
project: kailash-ml
topic: No existing ML code in kailash-py codebase
phase: analyze
tags: [ml, codebase-audit, greenfield]
---

# Discovery: kailash-py Contains Zero ML Code

## Context

Audited the entire kailash-py codebase for existing ML-related code during the kailash-ml analysis phase. Searched `src/kailash/`, `packages/`, and all node categories.

## Findings

1. **No ML packages exist**: No `packages/kailash-ml/` or `src/kailash/ml/` directory. kailash-ml is genuinely greenfield.
2. **DataFlow ModelRegistry naming conflict**: `dataflow.core.model_registry.ModelRegistry` tracks Python class definitions (DataFlow models), NOT trained ML models. Import paths are unambiguous but documentation must clarify.
3. **LLMAgentNode exists in Kaizen**: AI-related nodes (`LLMAgentNode`, `A2AAgentNode`, `MCPAgentNode`) are in the Kaizen package for text processing, not ML training.
4. **Vector/embedding nodes exist**: `EmbeddingNode`, `VectorDatabaseNode`, `AsyncPostgreSQLVectorNode` serve RAG (retrieval-augmented generation), not ML feature engineering.
5. **Zero polars adoption**: No file in the entire `src/` or `packages/` tree references polars, `pl.DataFrame`, or `pl.LazyFrame`. kailash-ml will be the first polars consumer.

## Implications

- kailash-ml has no legacy code to work around or integrate with
- The DataFlow ModelRegistry naming overlap requires clear documentation
- The interop module between polars and the dict-based ecosystem is uniquely critical because there are no existing polars patterns to follow
- kailash-ml agents should use Kaizen's Delegate pattern (consumer), not create new LLM node types (reimplementation)

## For Discussion

1. Given that polars has zero adoption in the existing codebase, should the interop module include DataFlow-specific conversions (polars <-> dict records) in addition to ML-specific ones (polars <-> numpy/LightGBM)?
2. If the DataFlow ModelRegistry had been named differently (e.g., `SchemaRegistry`), would it change the kailash-ml naming decision? What would the cost of renaming DataFlow's class be vs. accepting the ambiguity?
3. The zero-polars finding suggests kailash-ml will pioneer polars integration patterns for the entire Kailash ecosystem. Should these patterns be extracted into a shared utility (e.g., `kailash-polars-bridge`) or remain kailash-ml-internal?
