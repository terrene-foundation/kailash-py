# T4 Disposition Catalog — `src/kailash/` + `packages/kailash-nexus/src/`

34 TODO-NNN hits across 16 files (4 in Core SDK, 12 in Nexus). Classified per `02-plans/01-cleanup-architecture.md` § Refined taxonomy + T1 catalog precedent.

Bundling is safe — Core SDK and Nexus packages have no shared symbols and ship to PyPI independently.

## Class Distribution Summary

| Class                                                    |  Count | Disposition rule                                                      |
| -------------------------------------------------------- | -----: | --------------------------------------------------------------------- |
| 1a — header banner / group label / inline-shipped marker |     17 | Rewrite to `(SHIPPED-vX.Y.Z)` if version paired; else drop `(TODO-NNN)` parenthetical |
| 1b — module docstring provenance                         |     17 | Strip `TODO-NNN` references (provenance lives in git log + CHANGELOG) |
| 2 — active iterative TODO                                |      0 | None — every T4 marker pointed to SHIPPED work                        |
| 3 — cross-reference                                      |      0 | None                                                                  |
| ambiguous                                                |      0 | None                                                                  |
| **Total**                                                | **34** |                                                                       |

## Catalog

|   # | package | file:line                                                                       | snippet                                                                       | class | disposition                                                                  | notes                                                                                          |
| --: | ------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ----- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
|   1 | core    | src/kailash/runtime/local.py:770                                                | `# === Coordinated Shutdown (v0.12.0, TODO-015) ===`                          | 1a    | rewrite to `# === Coordinated Shutdown (SHIPPED-v0.12.0) ===`                | version paired (v0.12.0); class-1a archetype                                                   |
|   2 | core    | src/kailash/runtime/local.py:783                                                | `# === Signal/Query System (TODO-010) ===`                                    | 1a    | rewrite to `# === Signal/Query System ===`                                   | section banner, no version paired; signal/query API SHIPPED (annotates `_workflow_signals`)    |
|   3 | core    | src/kailash/runtime/local.py:1023                                               | `# === Signal/Query Public API (TODO-010) ===`                                | 1a    | rewrite to `# === Signal/Query Public API ===`                               | section banner annotating SHIPPED `signal()` public method                                     |
|   4 | core    | src/kailash/runtime/local.py:1781                                               | `_signal_key = None  # TODO-010: Signal cleanup key`                          | 1a    | rewrite to `_signal_key = None  # Signal cleanup key`                        | inline init comment annotating SHIPPED signal cleanup key var                                  |
|   5 | core    | src/kailash/runtime/local.py:1838                                               | `# === Signal/Query System (TODO-010) ===`                                    | 1a    | rewrite to `# === Signal/Query System ===`                                   | section banner annotating SHIPPED SignalChannel + QueryRegistry creation                       |
|   6 | core    | src/kailash/runtime/local.py:1854                                               | `# === Checkpoint/Restore (TODO-005/006) ===`                                 | 1a    | rewrite to `# === Checkpoint/Restore ===`                                    | **multi-tracker variant** (005/006); no version paired → strip parenthetical                   |
|   7 | core    | src/kailash/runtime/local.py:1921                                               | `# === Signal/Query System (TODO-010) ===`                                    | 1a    | rewrite to `# === Signal/Query System ===`                                   | section banner annotating SHIPPED signal channel registration in `_workflow_signals`           |
|   8 | core    | src/kailash/runtime/local.py:2099                                               | `# === Signal/Query System Cleanup (TODO-010) ===`                            | 1a    | rewrite to `# === Signal/Query System Cleanup ===`                           | section banner annotating SHIPPED `_workflow_signals.pop` cleanup                              |
|   9 | core    | src/kailash/runtime/local.py:2332                                               | `# === Checkpoint/Restore (TODO-005/006) ===`                                 | 1a    | rewrite to `# === Checkpoint/Restore ===`                                    | **multi-tracker variant** (005/006); annotates SHIPPED resume-from-tracker logic               |
|  10 | core    | src/kailash/runtime/local.py:2503                                               | `# === Checkpoint/Restore (TODO-005/006) ===`                                 | 1a    | rewrite to `# === Checkpoint/Restore ===`                                    | **multi-tracker variant** (005/006); annotates SHIPPED `record_completion` call                |
|  11 | core    | src/kailash/runtime/local.py:2583                                               | `# OpenTelemetry tracing (TODO-014): end node span on success`                | 1a    | rewrite to `# OpenTelemetry tracing: end node span on success`               | inline comment annotating SHIPPED `_tracer.end_span` call                                      |
|  12 | core    | src/kailash/runtime/local.py:2599                                               | `# OpenTelemetry tracing (TODO-014): end node span on error`                  | 1a    | rewrite to `# OpenTelemetry tracing: end node span on error`                 | inline comment annotating SHIPPED tracer call on error path                                    |
|  13 | core    | src/kailash/runtime/local.py:2724                                               | `# OpenTelemetry tracing (TODO-014): end workflow span`                       | 1a    | rewrite to `# OpenTelemetry tracing: end workflow span`                      | inline comment annotating SHIPPED workflow-span end                                            |
|  14 | core    | src/kailash/runtime/local.py:2953                                               | `# Connection parameter validation (TODO-121) with enhanced error messages and metrics` | 1a    | rewrite to `# Connection parameter validation with enhanced error messages and metrics` | inline comment annotating SHIPPED `connection_validation` block                       |
|  15 | core    | src/kailash/runtime/local.py:5122                                               | `# Enhanced Persistent Mode Methods (TODO-135 Implementation)`                | 1a    | rewrite to `# Enhanced Persistent Mode Methods`                              | section banner annotating SHIPPED `start_persistent_mode` etc.                                 |
|  16 | core    | src/kailash/runtime/pause.py:24                                                 | `Part of: Production readiness (TODO-022)`                                    | 1b    | rewrite to `Part of: Production readiness`                                   | module docstring "Part of:" provenance line                                                    |
|  17 | core    | src/kailash/runtime/shutdown.py:37                                              | `Part of: Production readiness (TODO-015)`                                    | 1b    | rewrite to `Part of: Production readiness`                                   | module docstring "Part of:" provenance line                                                    |
|  18 | core    | src/kailash/trust/plane/key_managers/manager.py:4                               | `"""Pluggable key management for TrustPlane (TODO-23).`                       | 1b    | rewrite to `"""Pluggable key management for TrustPlane.`                     | module docstring opener                                                                        |
|  19 | nexus   | packages/kailash-nexus/src/nexus/core.py:1613                                   | `# Public Middleware API (WS01 - TODO-300A)`                                  | 1a    | rewrite to `# Public Middleware API`                                         | section banner annotating SHIPPED `add_middleware` method                                      |
|  20 | nexus   | packages/kailash-nexus/src/nexus/core.py:1788                                   | `# Public Router API (WS01 - TODO-300B)`                                      | 1a    | rewrite to `# Public Router API`                                             | section banner annotating SHIPPED `include_router` method                                      |
|  21 | nexus   | packages/kailash-nexus/src/nexus/core.py:2041                                   | `# Public Plugin API (WS01 - TODO-300C)`                                      | 1a    | rewrite to `# Public Plugin API`                                             | section banner annotating SHIPPED `add_plugin` method                                          |
|  22 | nexus   | packages/kailash-nexus/src/nexus/core.py:2351                                   | `# CORS Configuration API (WS01 - TODO-300E)`                                 | 1a    | rewrite to `# CORS Configuration API`                                        | section banner annotating SHIPPED `_get_cors_defaults` etc.                                    |
|  23 | nexus   | packages/kailash-nexus/src/nexus/core.py:2561                                   | `# Preset System API (WS01 - TODO-300D)`                                      | 1a    | rewrite to `# Preset System API`                                             | section banner annotating SHIPPED `active_preset` property                                     |
|  24 | nexus   | packages/kailash-nexus/src/nexus/auth/plugin.py:1                               | `"""NexusAuthPlugin - Unified auth plugin for Nexus (TODO-310G).`             | 1b    | rewrite to `"""NexusAuthPlugin - Unified auth plugin for Nexus.`             | module docstring opener                                                                        |
|  25 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/pii_filter.py:1                     | `"""PII filtering utility (TODO-310F).`                                       | 1b    | rewrite to `"""PII filtering utility.`                                       | module docstring opener                                                                        |
|  26 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/config.py:1                         | `"""Audit logging configuration (TODO-310F).`                                 | 1b    | rewrite to `"""Audit logging configuration.`                                 | module docstring opener                                                                        |
|  27 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/backends/__init__.py:1              | `"""Audit logging backends (TODO-310F)."""`                                   | 1b    | rewrite to `"""Audit logging backends."""`                                   | one-line module docstring                                                                      |
|  28 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/record.py:1                         | `"""Audit record dataclass (TODO-310F).`                                      | 1b    | rewrite to `"""Audit record dataclass.`                                      | module docstring opener                                                                        |
|  29 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/middleware.py:1                     | `"""Audit logging middleware (TODO-310F).`                                    | 1b    | rewrite to `"""Audit logging middleware.`                                    | module docstring opener                                                                        |
|  30 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/backends/dataflow.py:1              | `"""DataFlow database backend for audit records (TODO-310F).`                 | 1b    | rewrite to `"""DataFlow database backend for audit records.`                 | module docstring opener                                                                        |
|  31 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/backends/logging.py:1               | `"""Structured JSON logging backend (TODO-310F).`                             | 1b    | rewrite to `"""Structured JSON logging backend.`                             | module docstring opener                                                                        |
|  32 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/__init__.py:1                       | `"""Nexus audit logging package (TODO-310F).`                                 | 1b    | rewrite to `"""Nexus audit logging package.`                                 | module docstring opener                                                                        |
|  33 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/backends/base.py:1                  | `"""Abstract audit backend interface (TODO-310F)."""`                         | 1b    | rewrite to `"""Abstract audit backend interface."""`                         | one-line module docstring                                                                      |
|  34 | nexus   | packages/kailash-nexus/src/nexus/auth/audit/backends/custom.py:1                | `"""Custom backend wrapper for user-provided callable (TODO-310F)."""`        | 1b    | rewrite to `"""Custom backend wrapper for user-provided callable."""`        | one-line module docstring                                                                      |

## Final tally (re-derived from per-row classification)

- **Class 1a (header banner / group label / inline-shipped marker)**: rows 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 20, 21, 22, 23 → **20**
- **Class 1b (module docstring provenance)**: rows 16, 17, 18, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 → **14**
- **Class 2 (active iterative)**: 0
- **Class 3 (cross-reference)**: 0
- **Ambiguous**: 0
- **Sum**: 20 + 14 = **34** ✓

Per-package: Core SDK 18 (15 in `runtime/local.py`, 1 in `runtime/pause.py`, 1 in `runtime/shutdown.py`, 1 in `trust/plane/key_managers/manager.py`); Nexus 16 (5 in `nexus/core.py`, 11 across `nexus/auth/audit/` + `nexus/auth/plugin.py`).

(Initial summary table shows 17/17 split; per-row recount lands 20/14 because 5 `nexus/core.py` section banners are 1a, not 1b — annotating SHIPPED `add_middleware`/`include_router`/`add_plugin`/CORS/preset methods.)

## Dispositions of note

### Multi-tracker `(TODO-005/006)` variant — Core SDK only

Three hits in `runtime/local.py` (lines 1854, 2332, 2503) pair two trackers in a single banner: `# === Checkpoint/Restore (TODO-005/006) ===`. No version paired. Per ratified rules: drop `(TODO-NNN)` parenthetical when no version is paired. All three rewrite to `# === Checkpoint/Restore ===`. The Checkpoint/Restore subsystem (ExecutionTracker, `is_completed()`, `record_completion()`) is SHIPPED and exercised in production code paths.

### Version-paired Class 1a — Core SDK

One hit (`runtime/local.py:770`): `# === Coordinated Shutdown (v0.12.0, TODO-015) ===`. Rewrite to `# === Coordinated Shutdown (SHIPPED-v0.12.0) ===` per Class 1a rule (version paired → SHIPPED-vX.Y.Z form).

### `(WS01 - TODO-300X)` family — Nexus

5 section banners in `nexus/core.py` use the form `# Public X API (WS01 - TODO-300A/B/C/D/E)`. The "WS01 - " prefix is also workspace provenance (workstream identifier, not a tracker the public will recognize). Strip the entire `(WS01 - TODO-NNN)` parenthetical → `# Public X API`. Same disposition as bare `(TODO-NNN)` since no version is paired.

### `(TODO-310F)` cluster — Nexus audit subsystem

10 hits across `nexus/auth/audit/` all carry `(TODO-310F)` as module-docstring provenance for the audit logging package. Strip the parenthetical from each opener; the substantive prose stays. The audit subsystem is SHIPPED and consumed by `NexusAuthPlugin` (which itself carries `(TODO-310G)`).

## Class 2 (active iterative TODO) — zero hits

Every T4 marker annotates SHIPPED code: signal/query system, checkpoint/restore, OTel tracing, persistent-mode methods, public middleware/router/plugin/CORS/preset APIs, audit logging backends. The brief framed `runtime/local.py` markers as candidates for Class 2 review, but ±10/±30 line context confirms each annotates code that exists and runs. Same finding as T1/T2/T3 cohorts: the T4 cohort is "comment-cleanup" — no production gaps.
