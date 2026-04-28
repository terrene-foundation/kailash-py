# COC Artifact Improvements

**Date**: 2026-03-20
**Goal**: Ensure USE template users can never do the wrong thing with connection pools

---

## Problem

Users of the Kailash COC template repos (USE repos) struggle with connection pool configuration because:

1. The SDK defaults are wrong (DEFECT-A: five competing defaults, the loudest one produces unsafe values)
2. There's no guidance in the COC artifacts about pool configuration
3. There's no enforcement preventing unsafe pool configurations
4. The MonitoringConfig flags suggest protection that doesn't exist

Fixing the codebase (Phase 0 through PY-5) solves problem #1. This document addresses #2, #3, and #4 — the COC artifact changes that make the guidance persistent across sessions and projects.

---

## Layer 1: New Rule — `rules/dataflow-pool.md`

**Scope**: `packages/kailash-dataflow/**`

```markdown
# DataFlow Pool Configuration Rules

## Scope

These rules apply when editing `packages/kailash-dataflow/**` files.

## MUST Rules

### 1. Single Source of Truth for Pool Size

Pool size MUST be resolved through exactly one code path:
`DatabaseConfig.get_pool_size(environment)`.

No hardcoded pool size defaults outside this method. Any code that needs
a pool size MUST call the config object. If the config doesn't have a
value, that is a config bug — not a reason to invent a local default.

### 2. No Hardcoded Numeric Pool Defaults

MUST NOT add `pool_size=N` as a default in constructors, env var
fallbacks, or adapter base classes. All defaults flow through
`get_pool_size()`.

### 3. Validate Pool Config at Startup

When connecting to PostgreSQL, MUST call `validate_pool_config()`
to log whether the configured pool will exhaust `max_connections`.

### 4. No Deceptive Configuration

Config fields that suggest a feature exists MUST have a backing
implementation. A config flag set to `True` by default with no
consumer is functionally a stub and violates `no-stubs.md` Rule 4.

## MUST NOT Rules

### 1. No `pool_size * 2` for max_overflow

MUST NOT compute `max_overflow = pool_size * 2`. This doubles the
connection footprint. Use `max(2, pool_size // 2)` instead.
```

**Sync target**: `kailash-coc-claude-py` via coc-sync

---

## Layer 2: Skill Update — `skills/02-dataflow`

Add a "Connection Pool Configuration" section to the DataFlow skill:

```markdown
## Connection Pool Configuration

DataFlow auto-detects safe pool sizes by querying the database server's
`max_connections` and dividing by the detected worker count. Users should
NOT manually set `pool_size` unless they know their exact deployment
topology.

### When to override

- Behind PgBouncer: Set `DATAFLOW_POOL_SIZE=N` where N matches your
  PgBouncer `default_pool_size`
- Known worker count: Set `DATAFLOW_WORKER_COUNT=N` if env vars like
  `UVICORN_WORKERS` are not set
- Development: No override needed — auto-scaling uses conservative
  fallback for SQLite

### Diagnostic flow

1. Check startup logs for "Connection pool validated" / "WILL EXHAUST"
2. Call `dataflow.pool_stats()` for real-time utilization
3. Check logs for "[POOL] WARNING: Connection held for Xs" (leak detection)

### Common mistakes

- Setting `pool_size=50` without checking `max_connections` — NEVER do this
- Using `pool_size * 2` for `max_overflow` — use `pool_size // 2` instead
- Ignoring "WILL EXHAUST" startup warning — this WILL cause production outages
```

**Sync target**: `kailash-coc-claude-py` via coc-sync

---

## Layer 3: Learned Instinct

Add to `rules/learned-instincts.md`:

```
## Configuration Patterns
- When adding a new config parameter, search for existing parameters with
  similar names or purposes. Consolidate before adding. (CRITICAL, pool
  default drift incident — five competing defaults in DataFlow config)
```

---

## Layer 4: Hook Enhancement — `validate-workflow.js`

Extend the existing validate-workflow hook to detect unsafe pool patterns in user code:

**Detection patterns**:

```javascript
// Detect hardcoded pool_size > 20 without comment explaining why
/pool_size\s*=\s*(\d+)/ where $1 > 20

// Detect max_overflow = pool_size * 2 (the old dangerous default)
/max_overflow\s*=\s*.*pool_size\s*\*\s*2/

// Detect MonitoringConfig flags being set without PY-2 being present
// (once PY-2 ships, this check becomes: warn if alert flags are set to False)
```

**Action**: WARNING (not BLOCK) — user may have a valid reason for large pool sizes. Message:

```
WARNING: pool_size=50 may exhaust database connections in multi-worker
deployments. DataFlow auto-detects safe pool sizes by default.
Consider removing the explicit pool_size override.
```

---

## Layer 5: Session-Start Enhancement

Add to the session-start hook: if the project uses DataFlow with PostgreSQL (detected via `DATABASE_URL` or `DATAFLOW_DATABASE_URL` in `.env`), show:

```
[DataFlow] Pool auto-scaling active. Override with DATAFLOW_POOL_SIZE=N
if needed. Run `dataflow.pool_stats()` for real-time utilization.
```

This ensures every session starts with pool awareness.

---

## Sync Plan

After implementation, these COC artifacts must be synced to the USE template repo:

| Artifact                     | Source (BUILD)                           | Target (USE)                                        |
| ---------------------------- | ---------------------------------------- | --------------------------------------------------- |
| `rules/dataflow-pool.md`     | `kailash-py/.claude/rules/`              | `kailash-coc-claude-py/.claude/rules/`              |
| `skills/02-dataflow` update  | `kailash-py/.claude/skills/02-dataflow/` | `kailash-coc-claude-py/.claude/skills/02-dataflow/` |
| `rules/learned-instincts.md` | `kailash-py/.claude/rules/`              | `kailash-coc-claude-py/.claude/rules/`              |
| Hook updates                 | `kailash-py/scripts/hooks/`              | `kailash-coc-claude-py/scripts/hooks/`              |

Use `/codify` (phase 05) after implementation to trigger the sync.

---

## Expected Outcome

After these COC changes, a user of the USE template repo who:

1. **Creates a DataFlow project** → gets safe defaults automatically (codebase fix)
2. **Tries to set pool_size=50** → gets a WARNING from the validate-workflow hook
3. **Deploys to production** → sees startup validation log confirming pool safety
4. **Hits pool pressure** → sees utilization monitor logs with exact stats
5. **Has a connection leak** → sees WARNING with the checkout traceback pointing to the leaking code
6. **Asks Claude for help** → Claude knows the pool configuration rules and guides them correctly (skill + rule)
7. **Starts a new session** → sees pool status reminder (session-start hook)

The goal is that at no point in this chain can the user silently end up with an unsafe pool configuration.
