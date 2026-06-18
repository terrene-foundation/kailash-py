# R2 Redteam — Connector ABC option (c) — CONVERGENCE RECEIPT (2026-05-25)

**Verdict: CONVERGED at Round 1 — APPROVE, 0 CRIT / 0 HIGH.** Three independent
agents reviewed the uncommitted option-(c) refactor in parallel; all reached
APPROVE / VERIFIED with no CRIT/HIGH findings.

## Scope reviewed

`feat/delegate-connector-abc-concrete-defaults` (based `7ee8ed53f`; origin/main
advanced to `b0568adc` mid-session — see § Multi-operator note). Working-tree
diff, 3 files:

- `src/kailash/delegate/dispatch.py` (Connector ABC; net −88 LOC)
- `tests/unit/delegate/test_connector_abc_shape.py` (contract tests → new shape)
- `tests/unit/delegate/test_dispatch.py` (3 BadConnector `invoke` return-type fixes)

## The change (option c)

`Connector` ABC: 7 `@abstractmethod`s + `__init_subclass__` proxy-install +
`__abstractmethods__` mutation → **concrete defaults**. `invoke` is the sole
`@abstractmethod`; the 6 newer members (3 accessors + 3 primitives) are concrete
defaults (accessors raise the typed `_legacy_unsupported` guard; primitives carry
the legacy-adapter behavior inlined). Dead `_LegacyAccessor` / `_LEGACY_*` /
`_legacy_authenticate|write|read` deleted. Goal: eliminate the 42 pyright
`reportAbstractUsage` errors shipped in v2.26.0 (legacy `invoke()`-only
subclasses were concrete at runtime via the magic but abstract to pyright).

## Round-history / receipts

| Agent (task ID)     | Role                                       | Verdict                                                                                                                                                                                                                                                                     |
| ------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `a0dc2ff350a4862da` | reviewer (correctness/parity)              | APPROVE — exact behavioral parity, all 5 invariants confirmed at runtime, contract tests strengthened, zero orphan refs. 1 LOW (`repr()` non-determinism in `read` default — byte-identical to origin/main, out of scope).                                                  |
| `a673dfc9d5b1d5288` | security-reviewer (audit/sig/tenant)       | APPROVE — delta security-neutral. 2 MEDIUM (empty-crypto primitive defaults are unconsumed orphans; `authenticate` `tenant_id=None` footgun) flagged **pre-existing, non-blocking**. 1 LOW assumption (silent-inheritance parity) → closed by orchestrator git-check below. |
| `a6a8b73fbde07e5e3` | general-purpose closure-parity (Bash+Read) | VERIFIED 7/8 claims; PARTIAL on baseline anchor (39 vs 42 — swap artifact, see below). No CRIT/HIGH.                                                                                                                                                                        |

## Mechanical verification (closure-parity, reproduced by orchestrator)

- pyright delegate scope: **42 → 0 errors** (6 warnings, all pre-existing).
- byte-parity of inlined `authenticate`/`write`/`read` vs old `_legacy_*`:
  **logic-identical** (Principal `tenant_id=None`; empty-signature envelope;
  empty-attestation receipt; same `canonical_json_dumps` + branches).
- orphan sweep: zero references to the 7 deleted symbols across `src/ tests/ packages/`.
- delegate unit tests: **439 passed, 1 skipped**.
- collect-only gate: **498 collected, exit 0**.
- `__all__`: byte-identical to origin/main (17 entries); `LegacyInvokeConnector` intact.

## LOW-1 (security) closed — PARITY

Orchestrator ran `git show origin/main:.../dispatch.py`: the OLD `__init_subclass__`
(lines 559-569) installed proxies for **all 6** members (`cls.authenticate =
_legacy_authenticate`, `.write`, `.read` + 3 accessors) on legacy subclasses and
stripped them from `__abstractmethods__` (line 577). A legacy `invoke()`-only
connector inherited the identical empty-crypto defaults BEFORE option (c). The
silent-inheritance surface is **unchanged** → no HIGH escalation; delta neutral.

## "42 vs 39" anchor reconciled

The clean v2.26.0 baseline (origin files at `7ee8ed53f`) is **42** (39
`reportAbstractUsage` + 3 incompatible-`invoke`-override), measured directly by
the orchestrator at session start. The closure-parity agent measured **39**
because its swap kept the orchestrator's already-fixed test files (origin
dispatch.py + fixed test_dispatch.py → 39 abstract + 0 override). Both reduce to
**0**. No real discrepancy.

## Pre-existing / orthogonal items (NOT introduced by option c — surfaced for disposition)

1. **6 e2e failures** (`tests/e2e/delegate/test_delegate_e2e_flows.py`,
   `phase=='failed'`): `AuditChainSignatureError` at THINKING — the v2.26.0
   signature-verification feature rejects the e2e fake `_test_signer`. Reproduces
   identically on origin/main `dispatch.py` (baseline swap). Signature-verification
   subsystem (verifier.py line), never reaches the Connector. **Pre-existing.**
2. **6 pyright warnings** (delegate tests): 3× `"Never" is not iterable`
   (`audit_engine.entries` test-helper inference), 1× `_grantees` (intentional
   negative test), 1× `invocations`, 1× `to_dict on None` (test_trust_cascade.py).
   All in the v2.26.0 baseline; orthogonal to the ABC.
3. **MEDIUM-1/2 (security)**: empty-crypto `write`/`read`/`authenticate` defaults
   are unconsumed orphans; "treat-as-unverifiable" is docstring-only (unenforced);
   `authenticate` default `tenant_id=None`. **Pre-existing** (byte-parity with
   origin/main). Recommended follow-up in the #1035 substrate (verifier.py line),
   NOT folded into the type-debt refactor (would break the behavioral parity that
   makes option (c) safe).

## Multi-operator note

origin/main advanced `7ee8ed53f` → `b0568adc` during this session: PR #1167
(lazy-crypto) merged, **v2.26.1 released** (slim-core delegate import corrective
patch), #1035 sweep/wrapup (journal/0008). The advance touched **only
`verifier.py`** — zero overlap with option (c)'s `dispatch.py` + delegate tests.
Branch rebases cleanly onto `b0568adc`.
