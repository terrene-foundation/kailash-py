---
type: CONVERGENCE
status: converged
session: 2026-05-25 (/autonomize cycle 2 — M1/M3/M4 hardening + R1 MED follow-ups)
branch: feat/1035-m1-m3-m4-hardening
head: 6bb3e67b7
base: origin/main b0568adc0
commit_count: 17
---

# /redteam Convergence Receipt — issue-1035-delegate-py (cycle 2)

**Status: CONVERGED — 0 CRITICAL / 0 HIGH / 0 MED, 2 consecutive clean rounds (R2 + R3).**

## Round history (6 agent verdicts)

| Round | Agent | Verdict | New findings |
|-------|-------|---------|--------------|
| R1 | reviewer | CONVERGED | 0 C / 0 H / 0 M |
| R1 | security-reviewer | CONVERGED (CRIT/HIGH axis) | 0 C / 0 H / 4 MED (defense-in-depth) |
| R1 | pact-specialist (closure-parity) | CONVERGED | 0 (all 3 M-rows VERIFIED-CLOSED) |
| R1.5 fix-wave | Shard E | 5 commits | 4 R1-MED closed |
| R2 | security-reviewer | CONVERGED | 0 C / 0 H / 0 M / 2 LOW docstring follow-ups |
| R2 | pact-specialist (closure-parity) | All 4 R1-MED VERIFIED-CLOSED | 0 new |
| R2.5 polish | inline | 1 commit | 2 R2-LOW docstrings inlined |
| R3 | security-reviewer | CONVERGED | 0 (all 10 fresh-adversarial probes cleared) |
| R3 | reviewer | CONVERGED — 2nd consecutive clean | 0 C / 0 I / 0 M (11/11 mechanical sweeps green) |

## Delivered (4 shards + 1 fix-wave + 1 polish + 1 codify proposal)

### M1 — `_consumed` TOCTOU
- `src/kailash/delegate/runtime.py` — wrapped `_consumed` check-and-set in `async with self._consume_lock: asyncio.Lock()`. Per-runtime instance; `with_posture()` returns fresh runtime with fresh lock.
- `tests/regression/test_issue_1035_delegate_m1_consumed_toctou.py` — N=10 concurrent execute() under asyncio.gather; revert-test confirmed bug class caught.

### M3 — payload-depth subclass bypass
- `src/kailash/delegate/dispatch.py::_check_payload_depth` — replaced concrete dict/list/tuple isinstance with `collections.abc.Mapping` + `Sequence` (excluding str/bytes/bytearray) + `Set` (R1.5 followup).
- `tests/regression/test_issue_1035_delegate_m3_payload_depth_subclass.py` — 14 tests covering UserDict, UserList, abstract Mapping, frozenset/set/MappingView, memoryview exclusion, plain-dict/list regression guards. Revert-probe verified.

### M4 — salted per-process tenant hash
- `src/kailash/delegate/trust.py::_tenant_id_hash` — replaced unsalted SHA-256 with HMAC-SHA-256 keyed by `_TENANT_HASH_SALT = secrets.token_bytes(32)` (eager module-init per R1.5 thread-safety fix; lazy helper `_get_tenant_hash_salt` fully removed per orphan-detection Rule 4a).
- Docstring covers fork() inheritance, importlib.reload() rotation, chroot/jail entropy-starved edge case.
- `tests/regression/test_issue_1035_delegate_m4_tenant_hash_salt.py` — 7 tests including subprocess cross-process unpredictability + ThreadPoolExecutor-10 concurrent first-call test.
- `tests/unit/delegate/test_trust_cascade.py` — rewrote 1 sibling test to shape+inequality assertions (no specific bytes).

### Codify proposal (Gate-1-ready for loom)
- `workspaces/issue-1035-delegate-py/05-codify/01-PROPOSAL-slim-core-eager-import.md` — 271 lines, two MUST clauses for loom `deployment.md` § Eagerly-Imported Transitive Dependencies:
  1. Pyright unbound-name fix MUST NOT move extras-only import to module scope in slim-core closure
  2. New module-scope side-effect in slim-core closure requires TestPyPI rehearsal

## Test counts

- Baseline (origin/main): 487 passed + 1 skipped
- Final (HEAD 6bb3e67b7): **512 passed + 1 skipped** (+25 new regression tests: 9 M3 + 7 M4 + 1 M1 from shards + 5 M3 + 2 M4 + 1 M1 from R1.5)
- `pytest -W error`: clean (no DeprecationWarning / ResourceWarning / RuntimeWarning)
- `pytest --collect-only`: 1161 tests, exit 0
- `pyright src/kailash/delegate/ --level error`: 0 errors

## Mechanical-sweep results (R3 reviewer + R2 closure-parity)

- `except: pass` / bare-except: CLEAN
- `eval/exec/shell=True`: CLEAN
- Secrets-in-log (`password|token|secret`): CLEAN
- TODO/FIXME/HACK/STUB/XXX: only typed-delegate-guard markers (Rule 3a compliant)
- Inline DDL outside migrations: CLEAN
- Module-scope import check (orphan-detection Rule 6): all eager imports in `__all__`
- DataFlow framework usage: N/A (delegate substrate)

## Outstanding follow-ups (NON-blocking, all DEFER-OK)

- R3-INFO-1: `with_posture()` shares `_signer` / `_envelope` / `_cascade` / `_dispatch_surface` / `_audit_engine`. Documented via the R2.5 docstring; the Verifier Protocol stateless contract is the structural defense.
- R3-INFO-2: Eager `secrets.token_bytes(32)` at module import is documented as the chroot/jail entropy-starved edge case (failure surface narrow per Python's multi-platform entropy fallback chain).
- F-18/F-19 conformance vectors: STILL DEFERRED per journal/0003 (rs Ed25519 library unconfirmed).
- M5 `DelegateRuntime.advance_lifecycle` orphan: still awaiting `Delegate.compose()` composer (per prior session ledger).
- L1 rotation_id UUID variant bits / L2 genesis shallow-replace snapshot / L3 CapabilitySet.intersect order-stability: untouched, low-priority.

## Critical institutional flag for next release

**TestPyPI MUST be used for the next release that ships this PR.** M4 adds a NEW eager module-scope side-effect (`_TENANT_HASH_SALT = secrets.token_bytes(32)`) inside the slim-core closure (`kailash.delegate.trust` is eagerly-imported by `kailash.delegate.__init__`). This is exactly the v2.26.0 lesson class (per the codify-proposal Clause 2 authored in this cycle). Skipping TestPyPI on this release risks repeating the slim-core regression.

Release-specialist invocation MUST treat this PR as a "new module-scope import-shape change" and run the TestPyPI clean-venv probe before tagging.

## Receipts

- R1 reviewer:           `tasks/a340ba48b12ec79fa.output`
- R1 security-reviewer:  `tasks/a021dce40322fb334.output`
- R1 closure-parity:     `tasks/abbe2fc6d4aa22241.output`
- R1.5 Shard E:          `tasks/ab08cb915c449f3a7.output`
- R2 security-reviewer:  `tasks/a2f1e21fe2f92005f.output`
- R2 closure-parity:     `tasks/a5cde5070ff29e232.output`
- R3 security-reviewer:  `tasks/a4305f2716acf7cdf.output`
- R3 reviewer:           `tasks/acd63026d3ff9bab0.output`

## Gate

Integration branch ready for merge. Merge to main + /release remain the user's gate (BUILD-repo Prudence). #1035 remains open pending maintainer close.
