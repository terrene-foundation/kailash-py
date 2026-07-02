---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T10:30:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: kailash-ml dependency creates critical path ordering risk
phase: analyze
tags: [kailash-ml, dependency, model-registry, ordering, risk]
---

# kailash-ml Dependency Ordering Risk

## Risk Description

kailash-align's AdapterRegistry extends kailash-ml's ModelRegistry. kailash-ml is being designed in parallel but has not been implemented. This creates a hard sequential dependency:

```
kailash-ml Phase 2 (ModelRegistry shipped) → kailash-align Phase 1 (AdapterRegistry starts)
```

Any delay in kailash-ml directly delays kailash-align. The 6-10 session estimate for kailash-align does NOT include waiting time for kailash-ml.

## Specific Risks

1. **API instability**: ModelRegistry's API is being designed now. If its methods, DataFlow models, or extension patterns change during kailash-ml implementation, AdapterRegistry must adapt after the fact.

2. **DataFlow model dependency**: AdapterRegistry extends `MLModel` and `MLModelVersion` DataFlow models. If kailash-ml renames fields, changes types, or restructures the model hierarchy, all kailash-align DataFlow models break.

3. **Interface-first not guaranteed**: kailash-ml-protocols exists as a concept but the ModelRegistry extension points that AdapterRegistry needs may not be explicitly defined there yet.

## Mitigation: Interface-First Development (P0)

The critical action is: **define the ModelRegistry interface in kailash-ml-protocols BEFORE either package starts implementation.**

Specifically, kailash-ml-protocols must include:

- `ModelRegistry` abstract base class or protocol with methods that AdapterRegistry will call/override
- `MLModel` and `MLModelVersion` DataFlow model definitions (or their field contracts)
- Extension patterns: how subclasses add fields to the DataFlow models

This allows:

- kailash-align to code against the interface (with mock implementations for testing)
- kailash-ml to implement the interface independently
- Both packages to develop in parallel without blocking

## Timeline Impact

If the interface is NOT frozen first:

- kailash-align Phase 1 is blocked until kailash-ml Phase 2 ships (~3-5 sessions into kailash-ml)
- Total elapsed time: kailash-ml (7-14 sessions) + kailash-align (6-10 sessions) = **13-24 sessions sequential**

If the interface IS frozen first:

- kailash-align Phase 1 starts immediately after interface freeze (~0.5 session cost)
- Phases overlap significantly
- Total elapsed time: max(kailash-ml, kailash-align) + 0.5 = **~8-14 sessions parallel**

The difference is 5-10 sessions of calendar time.

## For Discussion

1. The existing `ModelRegistry` in DataFlow (`packages/kailash-dataflow/src/dataflow/core/model_registry.py`) is 100+ lines with threading, lazy registration, and transaction management. How much of this complexity does AdapterRegistry actually need to inherit vs. compose?
2. If kailash-ml decides to build a NEW ModelRegistry (separate from DataFlow's existing one), does that invalidate the entire AdapterRegistry extension strategy?
3. Would it be safer to make AdapterRegistry a standalone registry that USES kailash-ml's ModelRegistry for storage (composition) rather than EXTENDS it (inheritance)?
