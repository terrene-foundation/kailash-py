---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T15:30:00+08:00
author: agent
session_id: s14
session_turn: 15
project: kailash
topic: Nexus creates 3 independent AsyncLocalRuntime instances
phase: implement
tags: [nexus, dataflow, connection-pool, docker-desktop, runtime]
---

## Discovery

Nexus startup creates **three independent `AsyncLocalRuntime` instances**, each with its own database connection pool:

1. `core.py:324` — Nexus's own runtime
2. `enterprise_workflow_server.py:183` — Enterprise gateway's runtime (via `create_gateway()`)
3. `transports/mcp.py:169` — MCP transport's lazy runtime

`_initialize_gateway()` at `core.py:451` never passed `runtime=self.runtime` to the gateway, and the MCP transport had no runtime injection mechanism at all. Combined with DataFlow's per-statement DDL connections (63+ for 21 models), a simple `DataFlow(auto_migrate=True) + Nexus()` opened 108-118 connections in <2 seconds — killing Docker Desktop PostgreSQL (max_connections=100).

kailash-rs is NOT affected: defaults to `Preset::None`, uses shared pool for DDL, already has `CREATE INDEX IF NOT EXISTS`.

## Resolution

PR #213 + #214 (merged, released as nexus v1.7.1, dataflow v1.5.1):

- Share single runtime: Nexus → gateway → MCP transport
- Batch DDL into single connection (was 63+, now 1)
- Configurable `server_type`/`max_workers` (env: `NEXUS_SERVER_TYPE`/`NEXUS_MAX_WORKERS`)
- Added `IF NOT EXISTS` to all `CREATE INDEX`

## For Discussion

1. The orphan runtime pattern violated `rules/dataflow-pool.md` Rule 6 which was written after issue #71 — why wasn't the Nexus gateway caught by that rule? Was it because the gateway is in `kailash.servers` (core SDK) while the rule was enforced only in `kailash-dataflow`?
2. If kailash-rs had used the same architecture (separate runtime per gateway), would Rust's tokio runtime pooling have masked the issue? (tokio shares a single connection pool by default)
3. The `SyncDDLExecutor.execute_ddl_batch()` method existed since v1.0 but was never called by the auto_migrate path — should we add a lint rule that flags `execute_ddl()` calls inside loops?
