# EATP SDK Gaps -- Risk & Failure Analysis

**Date**: 2026-03-14
**Analyst**: deep-analyst
**Package**: `packages/eatp/src/eatp/` (v0.1.0)

---

## Executive Summary

The 11 gaps span active production hazards (unbounded memory, deprecated Python APIs), missing trust-critical capabilities (no behavioral scoring, no proximity warnings), and architectural gaps (no lifecycle hooks). Three CRITICAL gaps (G1, G2, G3) collectively mean the SDK can assess structural trust but cannot detect behavioral decay, cannot warn before constraint violations, and cannot be integrated without manual boilerplate.

**Hidden risks discovered**: 4 additional issues not in the original brief.

---

## Risk Register

| ID  | Risk                                                                             | Likelihood | Impact   | Severity | Complexity |
| --- | -------------------------------------------------------------------------------- | ---------- | -------- | -------- | ---------- |
| G1  | Agents with degrading behavior retain high trust scores                          | HIGH       | CRITICAL | CRITICAL | L          |
| G2  | Agents at 95% budget get AUTO_APPROVED, next action BLOCKED with no warning      | HIGH       | CRITICAL | CRITICAL | M          |
| G3  | Every integration requires manual decorator wiring; sub-agent spawning unguarded | HIGH       | CRITICAL | CRITICAL | XL         |
| G4  | No fleet-level circuit breaker management or enumeration                         | MEDIUM     | HIGH     | HIGH     | S          |
| G5  | ShadowEnforcer.\_records grows unbounded (memory leak)                           | HIGH       | HIGH     | HIGH     | S          |
| G5+ | **StrictEnforcer.\_records ALSO unbounded** (not in brief)                       | HIGH       | HIGH     | HIGH     | S          |
| G6  | All verification uses Ed25519; no HMAC fast-path for internal checks             | LOW        | MEDIUM   | MEDIUM   | L          |
| G7  | AWSKMSKeyManager raises NotImplementedError on all 7 methods                     | MEDIUM     | HIGH     | HIGH     | L          |
| G8  | asyncio.get_event_loop() deprecated in Python 3.12+                              | HIGH       | MEDIUM   | HIGH     | S          |
| G8+ | **5 additional deprecated call sites** beyond decorators.py (messaging, MCP)     | HIGH       | MEDIUM   | HIGH     | S          |
| G9  | asyncio.Lock not safe for multi-threaded access                                  | MEDIUM     | MEDIUM   | MEDIUM   | S          |
| G9+ | **asyncio.Lock pattern is systemic** across 10+ modules                          | MEDIUM     | MEDIUM   | MEDIUM   | M          |
| G10 | No canonical CARE-to-EATP vocabulary mapping                                     | MEDIUM     | MEDIUM   | MEDIUM   | M          |
| G11 | BUILTIN_DIMENSIONS set mismatches actual registered dimensions                   | LOW        | LOW      | LOW      | S          |

---

## Hidden Risks Not in Brief

### HR1: StrictEnforcer.\_records Unbounded (G5+)

`strict.py:120` — identical pattern to ShadowEnforcer. The `_review_queue` (line 121) is also unbounded. Must be fixed alongside G5.

### HR2: get_event_loop() in Messaging and MCP (G8+)

8 total call sites across 3 files (not 3 as the brief states):

- `enforce/decorators.py`: lines 94, 182, 262
- `messaging/channel.py`: line 331
- `mcp/server.py`: lines 1531, 1538, 1542

### HR3: asyncio.Lock Systemic Pattern (G9+)

10+ modules use async-only locking: `cache.py`, `rotation.py`, `security.py`, `replay_protection.py`, `channel.py`, `esa/api.py`, `revocation/broadcaster.py`, orchestration modules. `security.py` line 750 already has a comment acknowledging the problem.

### HR4: BUILTIN_DIMENSIONS Bidirectional Mismatch (G11 detail)

Not just naming — two implemented dimensions (`data_access`, `communication`) are MISSING from the auto-approve set, and four entries in the auto-approve set have NO implementations (`geo_restrictions`, `budget_limit`, `max_delegation_depth`, `allowed_actions`).

---

## Dependency Graph

```
G3 (Lifecycle Hooks) -----> G1 (Behavioral Scoring)
                      \---> G2 (Proximity Thresholds, can be a hook)
                       \--> G4 (Circuit Breaker, can subscribe to hooks)

G4 (CB Registry) ----------> G1 (needs error rates from breakers)
G5 (Bounded Records) -------> G1 (needs clean data for rate computation)

G10 (Adapters) <-----------> G11 (Naming Alignment)
G6 (Dual Signature) <------> G7 (KMS Implementation)

G8 (Deprecated API) --------  Independent
G9 (Threading Model) -------  Independent
```

---

## Cross-Cutting Concerns

1. **Unbounded Collection Pattern**: G5, G5+, and circuit breaker `_failures` dict share append-only lists with no bound. Apply `PostureStateMachine`'s bounded pattern systematically.

2. **asyncio.Lock-Only Threading Model**: Systemic architectural decision. Document as async-only or add threading.Lock SDK-wide.

3. **Deprecated get_event_loop()**: 8 call sites across 3 files. Fix in a single sweep.

4. **Enforcement Lacks Utilization Awareness**: `ConstraintCheckResult` already carries `remaining`, `used`, `limit` — data is computed but never consumed by enforcement.

5. **Hooks as Foundation**: G3 is the architectural enabler for G1, G2, and G4 via event-based composition.

---

## Decision Points Requiring Stakeholder Input

| Decision              | Options                                         | Impact                                                  |
| --------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| G1 Weight Balance     | 50/50 vs 60/40 vs 70/30 structural/behavioral   | Whether behavioral scoring is advisory or authoritative |
| G2 Threshold Defaults | 70/90/100 vs 80/95/100 (kailash-rs alignment)   | Sensitivity of proximity warnings                       |
| G3 Hook Error Policy  | Fail-closed (block) vs fail-open (warn)         | Fundamental security posture decision                   |
| G7 Algorithm          | ECDSA P-256 (AWS KMS supported) vs Ed25519 only | Algorithm mismatch across SDK                           |
| G9 Threading Model    | Document async-only vs add threading.Lock       | Target audience scope                                   |
| G10 Ownership         | EATP SDK vs CARE Platform vs bridge package     | Who maintains the canonical mapping                     |

---

## Success Criteria

| Gap    | Metric                                                                    |
| ------ | ------------------------------------------------------------------------- |
| G1     | Trust score changes within 5 min of behavioral degradation (10+ failures) |
| G2     | Agent at 90%+ utilization receives FLAGGED or HELD, never AUTO_APPROVED   |
| G3     | New framework integration requires zero decorator boilerplate             |
| G4     | Enumerate all tripped circuit breakers across 100+ agents in O(1)         |
| G5/G5+ | Memory usage constant after 100,000+ enforcement checks                   |
| G6     | Internal HMAC verification <0.1ms (vs ~1ms for Ed25519)                   |
| G7     | End-to-end: generate KMS key, sign, verify, rotate, revoke                |
| G8/G8+ | Zero DeprecationWarnings on Python 3.12+; sync works in running loops     |
| G9     | 10 threads concurrently recording failures without data corruption        |
| G10    | Round-trip: CARE -> EATP -> CARE produces identical output                |
| G11    | BUILTIN_DIMENSIONS matches registered dimension names exactly             |
