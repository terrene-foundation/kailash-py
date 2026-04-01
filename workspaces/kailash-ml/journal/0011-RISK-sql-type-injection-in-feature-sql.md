---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T13:30:00+08:00
author: agent
session_id: session-16
session_turn: 45
project: kailash-ml
topic: SQL type injection via unvalidated sql_type parameter
phase: redteam
tags: [security, sql-injection, feature-store, red-team]
---

# SQL Type Injection in \_feature_sql.py

## Finding

`create_feature_table()` in `_feature_sql.py:71` interpolated `sql_type` values directly into DDL without validation. While column names were validated via `_validate_identifier()`, the SQL type strings had zero validation. A crafted `sql_type` like `"TEXT); DROP TABLE users; --"` would create a SQL injection in the CREATE TABLE statement.

## Fix Applied

Added `_ALLOWED_SQL_TYPES = frozenset({"INTEGER", "REAL", "TEXT", "BLOB", "NUMERIC"})` and `_validate_sql_type()` function. Called before any type interpolation.

## Impact

The immediate caller (`FeatureStore`) uses `dtype_to_sql()` which maps safe values, but the public API of `create_feature_table()` accepted arbitrary strings. Defense-in-depth requires validating at the interpolation point, not relying on callers.

## For Discussion

1. Should `_validate_sql_type()` also accept database-specific types like `BYTEA` (PostgreSQL) or `VARCHAR(N)`, given that ConnectionManager supports multiple dialects?
2. If the FeatureStore had been the only caller, would this still warrant a CRITICAL severity? The vulnerability requires a crafted caller — is call-chain analysis sufficient mitigation?
3. What other SQL interpolation points in the kailash-ml codebase could have similar type-injection vulnerabilities?
