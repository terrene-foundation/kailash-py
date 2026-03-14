# EATP SDK Gaps -- COC Methodology Assessment

**Date**: 2026-03-14
**Assessor**: coc-expert
**Framework**: Cognitive Orchestration for Codegen (COC) Five-Layer Analysis

---

## 1. Three Fault Lines Assessment

### 1.1 Amnesia — Institutional Knowledge at Risk

**Severity: CRITICAL.** The SDK encodes dense design decisions that exist only as code patterns.

**Critical knowledge at risk:**

| Knowledge                            | Pattern                                                       | Source                | At-Risk Gaps    |
| ------------------------------------ | ------------------------------------------------------------- | --------------------- | --------------- |
| Fail-safe principle                  | Zero-data scores 0 (pessimistic)                              | `scoring.py`          | G1              |
| Bounded memory                       | `_max_history_size = 10000`, oldest-10% trim                  | `postures.py:209-232` | G5              |
| `__all__` export discipline          | Every module ends with explicit `__all__`                     | All modules           | G3, G10         |
| SPDX header                          | `# Copyright 2026 Terrene Foundation` + Apache-2.0            | All files             | G3, G10         |
| `from __future__ import annotations` | Used in modules with complex type annotations                 | scoring, strict, CB   | All new modules |
| Defense-in-depth layering            | Decorators = DX, Enforcers = policy, Hooks = interception     | `enforce/`            | G3              |
| Reasoning trace 3-state              | `None` (legacy), `True`, `False` — check `is True`/`is False` | `shadow.py:152-159`   | G2, G3          |

### 1.2 Convention Drift — Highest Risk Gaps

**Tier 1 (Will drift without constraints):**

- **G1**: AI will default to sklearn-style APIs, Pydantic, numpy. SDK uses `@dataclass`, pure Python math, module-level async functions.
- **G3**: AI will default to Django signals or event-emitter patterns. SDK uses ABCs for extension, enums for types, dataclasses for DTOs.
- **G7**: AI will make boto3 a hard dependency. SDK uses ABC pattern with optional backends.

**Tier 2 (May drift subtly):**

- **G2**: AI might create a new `ProximityEnforcer` class instead of extending `StrictEnforcer.classify()`.
- **G4**: AI might create elaborate DI registry instead of simple `Dict[str, T]` with lazy init.
- **G6**: AI might import `hmac` directly instead of going through `eatp.crypto` abstraction.

**Tier 3 (Straightforward, low drift):** G5, G8, G9, G10, G11

### 1.3 Security Blindness — Highest Sensitivity

**Critical (exploitable if wrong):**

- **G2**: Without proximity, agents drain budgets in a burst with no warning. Threshold bypass = trust circumvention.
- **G6**: HMAC accidentally becoming default degrades non-repudiation guarantee.
- **G3**: Hooks that can abort operations introduce DoS surface. Malicious hook blocks all actions.

**High (weakens trust guarantees):**

- **G1**: Gameable behavioral scoring (agent attempts only safe actions) = unearned trust escalation.
- **G7**: KMS unreachable → must NOT fall back to in-memory signing.
- **G4**: Registry allowing cross-agent state observation = operational metadata leak.

---

## 2. Anti-Amnesia Pattern Reference Card

Must be injected into every implementation session:

```
EATP SDK Conventions:
- Data classes: @dataclass (NOT Pydantic BaseModel)
- Extension points: ABC with @abstractmethod
- Type enums: str-backed Enum (class X(str, Enum))
- Public API: async functions at module level, not class methods
- Fail-safe: zero/pessimistic defaults when data missing
- Score range: integer 0-100, clamped via max(0, min(100, int(round(total))))
- File header: Copyright + SPDX + module docstring
- Exports: explicit __all__ at end of every module
- Bounded collections: maxlen cap with oldest-10% trimming
- Logging: logger = logging.getLogger(__name__)
- Error hierarchy: inherit from TrustError, carry structured .details dict
- IDs: string parameters (agent_id: str, key_id: str)
- Serialization: to_dict() method on dataclasses
```

---

## 3. Quality Gates per Phase

### Gate 1: After Phase 1 (G5 + G8 + G9 + G11) — Pattern Conformance

- [ ] Bounded memory matches PostureStateMachine pattern exactly
- [ ] Sync wrapper uses `asyncio.run()` or `asyncio.new_event_loop()`, not deprecated `get_event_loop()`
- [ ] Threading model documented
- [ ] All changes carry SPDX header, `__all__`, `from __future__ import annotations`
- [ ] Tests follow existing class organization pattern
- [ ] No new dependencies

### Gate 2: After Phase 2 (G2 + G4) — Security Invariant

- [ ] Proximity thresholds escalate monotonically: AUTO_APPROVED → FLAGGED → HELD → BLOCKED
- [ ] All utilization dimensions covered (financial, token, rate, tool)
- [ ] No bypass paths around proximity escalation
- [ ] Circuit breaker registry creates isolated breakers per agent
- [ ] Edge cases: exactly at threshold, float comparison, multi-dimension proximity

### Gate 3: After Phase 3 (G3 + G1) — Architecture Conformance

- [ ] Hooks complement decorators (not replace)
- [ ] Hook abort = fail-closed (crash = block action)
- [ ] Hook timeout prevents DoS
- [ ] Behavioral scoring uses @dataclass, returns int 0-100
- [ ] Zero behavioral data = score 0 (fail-safe)
- [ ] Behavioral cannot override structural (complementary only)
- [ ] `__init__.py` updated with new public exports

### Gate 4: Before Merge — Integration

- [ ] All gaps implemented with consistent patterns
- [ ] No `NotImplementedError` stubs remain
- [ ] No `TODO`/`FIXME` markers
- [ ] All new modules have `__all__` exports
- [ ] Full test suite passes
- [ ] Backward compatibility preserved

---

## 4. COC-Optimal Implementation Order

Optimized for **knowledge dependency** (each session builds context for the next):

| Session | Gaps            | Rationale                                                                      |
| ------- | --------------- | ------------------------------------------------------------------------------ |
| 1       | G5, G8, G9, G11 | Low-risk fixes that force reading core modules. Internalizes SDK patterns.     |
| 2       | G4, G2          | Extends existing systems using patterns learned in Session 1.                  |
| 3-4     | G3              | New module (hooks). Requires deep enforcement understanding from Sessions 1-2. |
| 4-5     | G1              | New scoring capability. Requires G4, G5 patterns + scoring.py conventions.     |
| 5       | G6, G7          | Cryptographic extensions. Focused security attention.                          |
| 6       | G10             | Vocabulary alignment. Safest when all implementations stable.                  |

---

## 5. Risk Matrix Summary

| Gap | Amnesia | Convention Drift | Security | Session |
| --- | ------- | ---------------- | -------- | ------- |
| G1  | HIGH    | HIGH             | HIGH     | 4-5     |
| G2  | MEDIUM  | MEDIUM           | CRITICAL | 2       |
| G3  | HIGH    | HIGH             | HIGH     | 3-4     |
| G4  | LOW     | MEDIUM           | MEDIUM   | 2       |
| G5  | LOW     | LOW              | LOW      | 1       |
| G6  | MEDIUM  | MEDIUM           | HIGH     | 5       |
| G7  | LOW     | HIGH             | MEDIUM   | 5       |
| G8  | LOW     | LOW              | LOW      | 1       |
| G9  | LOW     | LOW              | LOW      | 1       |
| G10 | MEDIUM  | LOW              | MEDIUM   | 6       |
| G11 | LOW     | LOW              | LOW      | 1       |
