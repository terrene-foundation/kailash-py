# EATP SDK Gaps — Discovered from CARE Platform Upstream Analysis

**Date**: 2026-03-14
**Source**: Deep-dive audit of `packages/eatp/` against CARE/EATP specifications and Aegis foundational strengths
**Priority**: These gaps affect any downstream consumer of the EATP SDK (CARE Platform, Aegis, future implementations)

---

## Context

During analysis of upstreaming Aegis foundational strengths to the CARE Platform, we discovered that several core trust capabilities belong in the EATP SDK — not in downstream consumers. The CARE Platform already consumes `eatp>=0.1.0` via 6 trust modules. These gaps, if filled here, benefit the entire ecosystem.

---

## Gaps Summary

### CRITICAL (3)

| ID | Gap | Impact | Location |
|----|-----|--------|----------|
| G1 | **No behavioral trust scoring** | The EATP spec defines trust scoring with 5 structural factors (chain completeness, delegation depth, constraint coverage, posture level, chain recency). There is no behavioral scoring component — interaction history, approval rate, error rate, posture stability, time-at-posture. Behavioral scoring is complementary to structural scoring and essential for dynamic trust evolution. | `packages/eatp/src/eatp/scoring.py` |
| G2 | **No constraint proximity thresholds in verification gradient** | Actions near budget/rate boundaries pass as AUTO_APPROVED instead of FLAGGED. The verification gradient should escalate when usage approaches limits (e.g., FLAG at 70%, HELD at 90%, BLOCKED at 100%) across utilization dimensions. Without this, the early-warning signal central to the EATP verification gradient spec is missing. | `packages/eatp/src/eatp/enforce/` |
| G3 | **No EATP lifecycle hooks** | No way to intercept agent tool calls or sub-agent spawning for trust verification without manual decorator wiring. Need hook types: PRE_TOOL_USE, POST_TOOL_USE, SUBAGENT_SPAWN, PRE_DELEGATION, POST_DELEGATION with priority ordering and a hook registry. This is the extensibility mechanism that makes the enforcement system composable. | New module needed |

### HIGH (3)

| ID | Gap | Impact | Location |
|----|-----|--------|----------|
| G4 | **No per-agent circuit breaker registry** | `PostureCircuitBreaker` tracks state per-agent internally but there is no registry that lazily creates/manages isolated breakers per agent. One failing agent should not trip the circuit for all agents. Production wiring is cumbersome without a registry pattern. | `packages/eatp/src/eatp/circuit_breaker.py` |
| G5 | **ShadowEnforcer lacks bounded memory** | `_records` list grows unbounded. In long-running production shadow deployments this is a memory leak. Need a maxlen cap (e.g., 10,000) with oldest-10% trimming, similar to PostureStateMachine's bounded history. Also needs `change_rate` metric. | `packages/eatp/src/eatp/enforce/shadow.py` |
| G6 | **No dual-signature pattern on audit anchors** | EATP architecture describes dual signing for internal speed (HMAC-SHA256) + external non-repudiation (Ed25519). Current implementation only has Ed25519. Need optional HMAC fast-path for internal verification. | `packages/eatp/src/eatp/` |

### MEDIUM (4)

| ID | Gap | Impact | Location |
|----|-----|--------|----------|
| G7 | **AWSKMSKeyManager is a stub** | `raise NotImplementedError` — production environments cannot use KMS. Need at least one production backend (AWS KMS or HashiCorp Vault). Violates no-stubs principle. | `packages/eatp/src/eatp/key_manager.py` |
| G8 | **Sync decorator uses deprecated `get_event_loop()`** | `asyncio.get_event_loop()` is deprecated in Python 3.12+. Will warn/fail in running event loops. Use `asyncio.run()` or create new loop for sync wrappers. | `packages/eatp/src/eatp/enforce/decorators.py` |
| G9 | **PostureCircuitBreaker uses asyncio.Lock (not threading.Lock)** | Thread-safe for coroutine-based code but not safe for multi-threaded access. Aegis uses `threading.Lock` + `time.monotonic()`. Document as async-only or add `threading.Lock` option. | `packages/eatp/src/eatp/circuit_breaker.py` |
| G10 | **No posture/constraint dimension adapter modules** | No canonical bidirectional mapping between CARE labels and EATP SDK vocabulary. Increases drift risk as multiple implementations emerge. Need `to_eatp()`/`from_eatp()` with safe-conversion defaults. | New modules needed |

### LOW (1)

| ID | Gap | Impact | Location |
|----|-----|--------|----------|
| G11 | **Built-in dimension registry mismatch** | `BUILTIN_DIMENSIONS` in `constraints/dimensions.py` has 14 built-in dimensions but uses EATP SDK field names, not CARE canonical dimension names. Need alignment or explicit mapping. | `packages/eatp/src/eatp/constraints/dimensions.py` |

---

## Recommended Priority Order

1. **G2 (Proximity thresholds)** — Straightforward extension of existing verification gradient. High safety impact.
2. **G3 (Lifecycle hooks)** — Enables composable enforcement. Unblocks CARE Platform and Kaizen agent integration.
3. **G4 (Per-agent circuit breaker registry)** — Thin wrapper over existing PostureCircuitBreaker. High production value.
4. **G1 (Behavioral scoring)** — New scoring module complementing structural scoring. Requires CARE spec alignment.
5. **G5 (ShadowEnforcer bounded memory)** — Simple fix with high production impact.
6. **G6 (Dual-signature)** — Performance optimization for internal verification paths.
7. **G8 (Deprecated sync path)** — Python 3.12+ compatibility fix.
8. **G7 (KMS stub)** — Production readiness for cloud deployments.
9. **G10 (Adapters)** — Vocabulary alignment for multi-implementation ecosystems.
10. **G9 (Threading)** — Document or extend threading model.
11. **G11 (Dimension registry)** — Terminology alignment.
