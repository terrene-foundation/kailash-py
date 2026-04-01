---
type: GAP
date: 2026-04-01
created_at: 2026-04-01T15:00:00+08:00
author: agent
session_turn: 3
project: kailash-align
topic: No defined extension contract for ModelRegistry that AdapterRegistry needs to implement
phase: analyze
tags:
  [kailash-ml, model-registry, adapter-registry, interface, gap, architecture]
---

# Missing ModelRegistry Extension Contract

## The Gap

AdapterRegistry is designed to extend kailash-ml's ModelRegistry. The overview brief states this clearly: "kailash-align depends on kailash-ml (for ModelRegistry, which AdapterRegistry extends)." However, no document in the kailash-align analysis or the kailash-ml workspace defines the specific interface contract that AdapterRegistry needs from ModelRegistry.

The following questions are unanswered:

1. **What methods does ModelRegistry expose that AdapterRegistry will call?** (register, get, list, delete, version management)
2. **What DataFlow models does ModelRegistry define that AdapterRegistry will extend?** (MLModel, MLModelVersion -- what are their fields?)
3. **How does ModelRegistry support subclass extension?** (Does AdapterRegistry inherit from a base class? Compose with a protocol? Extend DataFlow models via table inheritance?)
4. **What storage backend does ModelRegistry use?** (DataFlow with SQLite/PostgreSQL? If so, AdapterRegistry can use the same database connection. If a separate storage mechanism, integration is harder.)
5. **Does ModelRegistry expose async or sync APIs?** (kailash-align's pipeline is async; if ModelRegistry is sync-only, bridge code is needed.)

## Why This Matters

AdapterRegistry is the highest-value component in kailash-align (rated HIGH in value proposition analysis). It is also the first component to be implemented in the plan (WS-A1). Without a defined extension contract, Phase 1 of kailash-align cannot begin with confidence.

The risk is not that the contract is wrong -- it is that it does not exist at all. Journal entry 0003 identifies the ordering risk (kailash-ml must ship first). This entry identifies the more fundamental problem: even if kailash-ml ships, if its ModelRegistry was not designed with external extension in mind, AdapterRegistry may require invasive changes to kailash-ml rather than clean extension.

## What the Contract Must Define

At minimum, the ModelRegistry extension contract must specify:

### 1. Base Model Schema (DataFlow)

```python
# What fields does MLModel have?
@db.model
class MLModel:
    id: str        # Primary key
    name: str      # Human-readable name
    model_type: str  # "classification", "regression", "alignment" -- is this extensible?
    # ... what other fields? metadata? tags? creation date?

# What fields does MLModelVersion have?
@db.model
class MLModelVersion:
    id: str
    model_id: str    # FK to MLModel
    version: str     # Semantic version or sequential number?
    # ... artifact path? metrics? status?
```

### 2. Extension Points

```python
# Can AdapterRegistry add fields to MLModel/MLModelVersion?
# Or does it need separate tables with FK relationships?

# Option A: Table inheritance (DataFlow-level)
@db.model
class AlignAdapter(MLModel):  # Inherits all MLModel fields
    base_model_id: str
    lora_config_json: str
    # ...

# Option B: Composition (separate table with FK)
@db.model
class AlignAdapter:
    id: str
    ml_model_id: str  # FK to MLModel
    base_model_id: str
    lora_config_json: str
    # ...
```

### 3. Registry API

```python
# Is the registry API generic enough for extension?
class ModelRegistry:
    async def register(self, model: MLModel) -> None: ...
    async def get(self, name: str, version: str = None) -> MLModel: ...
    async def list(self, filter: dict = None) -> list[MLModel]: ...
    async def delete(self, name: str, version: str = None) -> None: ...

# Does AdapterRegistry:
# (a) Call these methods on a composed ModelRegistry instance?
# (b) Override these methods in a subclass?
# (c) Implement a separate interface with the same shape?
```

## Action Required

Before kailash-align moves to /todos:

1. The kailash-ml workspace must produce a ModelRegistry interface specification (even if kailash-ml implementation has not started).
2. This specification must include the DataFlow model schemas, the extension pattern (inheritance vs. composition), and the registry API surface.
3. The specification should be reviewed by the kailash-align analysis to confirm AdapterRegistry can cleanly extend it.

If this gap is not filled before /todos, the implementation plan for kailash-align will be building on an undefined foundation. Phase 1 estimates become unreliable because the integration approach is unknown.

## Composition vs. Inheritance Decision

The existing DataFlow ModelRegistry in `packages/kailash-dataflow/src/dataflow/core/model_registry.py` uses a specific pattern (threading, lazy registration, in-memory + DataFlow storage). Journal entry 0003 question 3 already asks: "Would it be safer to make AdapterRegistry a standalone registry that USES kailash-ml's ModelRegistry for storage (composition) rather than EXTENDS it (inheritance)?"

This question remains unanswered and is load-bearing for the implementation approach.

## For Discussion

1. The kailash-ml workspace is currently in its own /analyze phase. Can the ModelRegistry extension contract be extracted and frozen as a standalone deliverable without waiting for kailash-ml to complete its full analysis? This would be a 0.5-session task that unblocks kailash-align's /todos phase.
2. If DataFlow does not support table inheritance (extending a @db.model in a different package), AdapterRegistry must use composition (separate table with FK). Has anyone verified whether DataFlow supports cross-package model inheritance?
3. The brief says AdapterRegistry "extends" ModelRegistry. But the simplest implementation might be a standalone registry that imports and calls ModelRegistry as a dependency. If the "extends" language is relaxed to "integrates with," does the contract become simpler?
