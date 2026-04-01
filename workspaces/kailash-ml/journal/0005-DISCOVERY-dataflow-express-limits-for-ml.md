---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T11:00:00Z
author: agent
session_turn: 1
project: kailash-ml
topic: DataFlow Express API limitations for ML use cases
phase: analyze
tags: [ml, dataflow, express, point-in-time, bulk]
---

# Discovery: DataFlow Express API Has Limitations for ML-Specific Queries

## Context

Researched how kailash-ml engines (FeatureStore, ModelRegistry, DriftMonitor) will use DataFlow for persistent storage. DataFlow's Express API is the recommended interface for single-record CRUD operations.

## Findings

### 1. Point-in-time queries not supported by Express

FeatureStore's `get_features(entity_ids, feature_names, as_of=datetime)` requires:

```sql
SELECT * FROM features
WHERE entity_id = ? AND created_at <= ?
ORDER BY created_at DESC
LIMIT 1
```

DataFlow Express supports `list()` with simple filters (`{"entity_id": "x"}`) and `limit`, but does NOT support:

- Inequality filters (`created_at <= ?`)
- ORDER BY with direction
- Subqueries

**Impact**: FeatureStore MUST use DataFlow's `ConnectionManager` directly (raw parameterized SQL) for point-in-time retrieval. This drops from Engine-layer (Express) to Primitives-layer, which is acceptable per `rules/framework-first.md` ("Complex multi-step workflows requiring explicit node wiring").

### 2. Bulk write performance

Express `bulk_create()` processes records individually (wrapped in a transaction). For 100K+ feature rows, this will be slow. The architecture specifies an "Arrow-native path for >10K rows" which requires ConnectionManager-level batch inserts.

### 3. Express works well for metadata CRUD

ModelRegistry (register, promote, list versions, compare) and DriftMonitor (write reports, read history) are simple CRUD patterns that Express handles perfectly. No need to drop to ConnectionManager for these.

## Implications

- FeatureStore will be a mixed-layer engine: Express for metadata, ConnectionManager for feature data
- The `rules/infrastructure-sql.md` rules apply to FeatureStore's raw SQL (validate identifiers, use transactions, canonical `?` placeholders)
- ModelRegistry and DriftMonitor can use Express exclusively, simplifying their implementation

## For Discussion

1. Should DataFlow Express be extended with inequality filters and ORDER BY support? This would benefit kailash-ml and potentially other consumers. Or is this Express scope creep?
2. The Arrow-native bulk insert path does not exist in DataFlow today (Express uses dict records). Should kailash-ml implement this as a DataFlow contribution, or keep it internal to kailash-ml?
3. The mixed-layer pattern (Express + ConnectionManager in one engine) is unusual in the Kailash ecosystem. Should it be documented as a pattern for other frameworks that have similar needs?
