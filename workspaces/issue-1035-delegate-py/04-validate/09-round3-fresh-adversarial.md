# Round 3 — Fresh Adversarial Sweep (issue-1035-delegate-py)

Branch: `feat/1035-redteam-integration` @ 8b7e68a4b · Posture L5_DELEGATED · 2026-05-25
Mission: hunt NEW CRIT/HIGH the 3-shard fix-wave introduced (NOT closure re-verify).

## VERDICT: CONVERGED (0 new CRIT / 0 new HIGH)

Round 2 clean + Round 3 clean = two consecutive clean rounds = formal convergence.

## Crypto correctness (verifier.py) — SOUND

- Imports clean: `.venv/bin/python -c "from kailash.delegate.verifier import Ed25519Verifier, Verifier, NullVerifier"` → `verifier OK`.
- Pyright Round-1 flags RESOLVED: `verifier.py:262` `InvalidSignature` is imported INSIDE the `try` (line 254) and caught at 262 in the same scope — not possibly-unbound. `public_key_for` is a real method (`_directory.public_key_for(delegate_uuid)` @ verifier.py:228; impl confirmed in audit.py path). No unknown-attribute.
- Fail-closed verified: `verify()` catches `InvalidSignature → False` (262) AND bare `Exception → False` (264); NEVER raises. Length guard (32-byte) @238, type guards @242/247, UUID-parse guard @220.
- `Ed25519PublicKey.from_public_bytes` + `.verify(sig, msg)` is the canonical cryptography-lib path; byte handling correct (raw bytes, not hex at the lib boundary; hex decode happens caller-side in dispatch.py:2006).
- Dispatch-path verify (dispatch.py:2004-2039): verifier-raises → `DispatchSignatureError` (fail-closed); signer_id sha256-hashed in error (observability Rule 8 compliant).
- Verifier-coherence check (runtime.py:1012, `type(audit) is not type(cascade)`) is a class-equality gate — no bypass; tested (test_runtime.py + test_signature_verification_wiring.py).

## verifier=None gap — PRIOR-KNOWN ADVISORY (not new)

`DispatchSurface.__init__` defaults `verifier=None` → verification skipped (dispatch.py:2004). Already tracked in `08-convergence.md` as the explicit Round-3 question ("flip default to fail-closed once existing tests inject Verifier"). NOT a new finding. C1 is closed for the wired path; the None default is the documented 418-test backward-compat opt-in. No production composer constructs an unverified runtime today (no `Delegate.compose()` factory exists).

## Integration-seam — CLEAN

- Seam OK: `from kailash.delegate.dispatch import DispatchSurface; from kailash.delegate.verifier import Verifier` → `seam OK`. Shard X's `Verifier` import resolves to Shard Y's real `verifier.py`.
- Stub-leak grep `grep -rn "_verifier_stub\|_verifier_helpers" src/` → EMPTY. The helpers live only under `tests/unit/delegate/` (test-only, correct).

## Lifecycle auto-advance — MEDIUM orphan (acceptable-with-tracking), NOT HIGH

`grep -rn "advance_lifecycle" src/ tests/` → only the definition + docstrings; ZERO production callers, ZERO tests on the runtime wrapper. The 23 "VERIFIED-CLOSED" H1 tests (`test_lifecycle_state_machine.py`) exercise the `LifecycleState.advance_to` ENUM method, NOT `DelegateRuntime.advance_lifecycle` (the wrapper @ runtime.py:1097).

Classified MEDIUM not HIGH: `advance_lifecycle` is a public lifecycle-management API awaiting its (not-yet-built) composer, NOT a security gate silently bypassed on the data path. The dispatch hot path uses the SEPARATE, fully-wired TAOD `state` axis (`state.advance_to("thinking"/"acting"/...)` @ runtime.py:1367-1591). Unlike the Phase-5.11 trust-executor orphan, nothing on the hot path depends on `advance_lifecycle`, so it cannot be "bypassed" — it simply isn't reachable until a composer calls it. Recommend (non-blocking) one direct wrapper test locking the `self._lifecycle_state` mutation contract; file as tracked todo.

## Standard sweeps — ALL CLEAN

- DDL outside migrations: `grep -RInE "CREATE (TABLE|INDEX)|ALTER TABLE|DROP TABLE" src/kailash/delegate/` → EMPTY (in-memory only). ✓
- Stub/fake: `grep -rnE "TODO|FIXME|NotImplementedError|..."` → only ABC abstract methods in dispatch.py (`raise NotImplementedError  # pragma: no cover (abstract)` @694-772) — legitimate ABC contract, not stubs. `pass # accept int as float` @1877 = benign coercion. Zero `fake_/dummy_/mock_response/simulated_`. ✓
- Collection: `pytest --collect-only` → 498 tests collected, exit 0. ✓
- Full run: `pytest tests/unit/delegate/ tests/integration/delegate/ -q` → 487 passed, 1 skipped, 0 failed. ✓

## New findings vs prior-known

NEW CRIT/HIGH introduced by fix-wave: **NONE.**
Prior-known (NOT re-reported as new): verifier=None advisory, M1/M3/M4, L1/L2/L3 (all in 08-convergence.md).
New MEDIUM (advisory): `advance_lifecycle` runtime-wrapper untested — file tracking todo, non-blocking.
