# DECISION — NaN/Inf signing-pre-image bug class CLOSED + convergence receipt + 2.43.1 release

relates_to: 0015 (PR #1411 convergence), 0016 (rs#1448 release-state verify)

## What closed

The trust-plane-WIDE **NaN/Inf-in-signing-pre-image** bug class is fully closed and
on `main`. A `json.dumps` over a signing / integrity-hash pre-image that omitted
`allow_nan=False` emitted RFC-8259-invalid `NaN` / `Infinity` literals — Python
signs/hashes them, a strict cross-SDK parser (Rust `serde_json`) rejects them, so a
Python-signed artifact whose pre-image carried a non-finite float could not be
re-verified cross-SDK. The sweep added `allow_nan=False` at EVERY signing/hash/
cross-SDK pre-image (byte-neutral on all finite input).

- **PR #1412** (`fix/witness-family-nan-inf-allow-nan`, 6 commits f888ee65e..ece16e9dd
  - pin test 5c9abdf51) — MERGED 2026-06-21, merge commit **`b2f265ce8`**. Extends the
    PR #1411 envelope/audit-chain NaN/Inf start to the full trust plane + PACT + the
    cross-SDK delegate-conformance digest.
- **Durable guard:** `tests/regression/test_trust_signing_preimage_rejects_nan_inf.py`
  — a module-granularity AST invariant (`test_trust_plane_signing_preimages_all_carry_allow_nan`)
  over roots `src/kailash/trust`, `packages/kailash-pact/src`, `src/kailash/delegate/conformance`,
  plus behavioral tests. EXCLUDED-by-design (encoded in the guard): `pact/audit.py`
  legacy/prefix forensic byte-reproducers + `enforce/decorators.py` `_hash_*` local
  memoization caches.

## Convergence receipt (the gate before merge)

A final convergence `/redteam` ran on current HEAD (post-delegate-fix) as a Workflow —
**run `wf_157fb9c6-3e8`**, output `tasks/w75gk4ivy.output`. Three independent lenses per
round (exhaustive multi-site sweep / fix-adversarial / byte-neutral full-suite), evidence-
gated with serial fallback on this machine's rate-limit throttle.

- **Result: CONVERGED — 2 consecutive clean rounds**, all 6 lens-agents ran with verbatim
  command evidence, 0 CRIT/HIGH/MED.
- Independent AST sweep (149 `json.dumps` across trust + pact + delegate + diagnostics)
  found EXACTLY the 4 documented EXCLUDED sites — **no missed sibling**. The guard's
  cross-file blind spot was manually traced: every central canonical helper
  (`_json.canonical_json_dumps`, `pact.conformance.vectors.canonical_json_dumps`,
  `diagnostics._canonical_json`, `crypto.serialize_for_signing`) carries `allow_nan=False`.
- The prior-round blocking **MED** (`delegate/conformance/schema.py:448 _canonical_json_bytes`)
  verified CLOSED (allow_nan added + guard root extended + behavioral test).

## LOW disposition (the only residual)

`verify_witness_export` raises an uncaught `ValueError` (rather than returning `valid=False`)
on a **hand-forged** NaN-bearing `ExportPackage`. This is **fail-closed** (verify can never
return `valid=True` for it) and unreachable via any legitimate or cross-SDK flow (the
producer + Rust `serde_json` both reject NaN). Disposition: **pinned the intended fail-closed
contract with a behavioral regression test** (`test_verify_witness_export_rejects_nan_inf_fail_closed`,
commit `5c9abdf51`) — NOT wrapped to return a verdict (a forged adversarial input deserves a
loud raise). This also filled the witness-family behavioral coverage gap (the family the
sweep originated from, f888ee65e).

## Release — 2.43.1 (core kailash)

- **Lockstep gate CLEARED** (journal/0016): rs#1448 RELEASED in kailash-rs **v4.12.0**
  (2026-06-20). py 2.43.1 FOLLOWS rs; the #1412 NaN/Inf surfaces are additionally
  out-of-Family-B / byte-neutral / need no rs lockstep.
- **Version:** 2.43.0 → **2.43.1** (patch; per project convention behavior/conformance
  fixes ship as patch, minor reserved for API-signature breaks). Combined release ships
  PR #1411 (audit-chain canonical 6-digit conformance — byte-CHANGING, see CHANGELOG
  migration note) + PR #1412 (NaN/Inf sweep — byte-neutral).
- **Scope:** core kailash only. Sibling-drift enumeration clean (all other packages
  main == PyPI). Residual: a 1-line byte-neutral `allow_nan` hardening to
  `packages/kailash-pact/src/pact/conformance/vectors.py` is stranded (pact main == PyPI
  0.14.0) — a Rule-5 gap from #1412; surfaced for a separate kailash-pact 0.14.1 decision.

Human gates honored: convergence + CI-green preceded merge (approval ≠ convergence bypass);
the merge and the 2.43.1 publish were each explicitly user-authorized this session.
