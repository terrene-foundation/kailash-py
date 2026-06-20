---
type: DECISION
date: 2026-06-20
author: agent
project: cross-sdk-audit
topic: Post-rs#1448 fresh holistic redteam re-converges PR #1411 code surface; two residual human gates remain
phase: redteam
tags:
  [
    cross-sdk,
    canonical-encoder,
    redteam-convergence,
    kailash-rs-1448,
    kailash-rs-1451,
    pr-1411,
  ]
relates_to: 0011-DISCOVERY-canonical-encoder-family-sweep-broadens-cross-sdk-lockstep
---

# DECISION — Post-rs#1448 holistic redteam re-converges PR #1411 (code surface)

Continuation session after the user reported **kailash-rs#1448 has LANDED** and
**kailash-rs#1451 is IN PROGRESS**. A fresh multi-agent holistic `/redteam` was run
to convergence over the full canonical-encoder conformance surface on
`fix/audit-chain-canonical-conformance`.

## Verdict: code surface CONVERGED (2 consecutive clean passes)

- **Round 1** (5 lenses, serial, `ran`-evidence-gated): byte-conformance,
  security/tamper-evidence, spec-accuracy, coverage/orphan all CLEAN (zero
  CRIT/HIGH/MED). cross-SDK-lockstep lens surfaced 1 MED (human-gate, below),
  1 LOW (stale PR banner), and 1 fixable INFO (durable claim accuracy, fixed below).
  Receipt: workflow run `wf_3658232d-b13` (output `tasks/w7mkyvzsm.output`).
- **Round 2** (post-fix confirmation, 3 lenses — spec-accuracy + coverage +
  cross-SDK — serial): `code_surface_converged: true`, zero code-blocking findings.
  Receipt: workflow run `wf_1d89c1fc-d31` (output `tasks/wa7b1o03t.output`).
- The first parallel attempt (`wf_0f294242-601`) hit the synchronized server-side
  concurrency throttle (`not your usage limit · Rate limited`) — all 5 lenses + 5
  reruns nulled. The `ran`-evidence gate correctly returned `clean:false` (NOT false
  convergence). Remedy applied: **serial dispatch** (one agent at a time) per
  `worktree-isolation.md` Rule 4 + `agents.md` § Redteam Reviewer Dispatch — both
  re-runs then completed with zero throttle. (This is the recurring trap the prior
  session's notes flagged twice; serial dispatch is the durable fix.)

## Ground truth independently verified (this session, by hand)

- 68→79 conformance/genesis byte-pin tests pass; the pinned `envelope_hash`
  `698342bb…` reproduces byte-for-byte from the live `ConstraintEnvelope` path
  (not a copied literal); #1400 six-digit-microsecond rendering reproduces from the
  live `pact.audit._canonical_input` incl. the `microsecond==0` `.000000` case.
- The committed generator `test-vectors/regenerate_canonical_vectors.py` regenerates
  the vendored fixtures with an EMPTY git diff (reproducible).
- The two `default=str` hits in `pact/audit.py` are AST-confirmed to be
  `_compute_hash_legacy` / `_compute_hash_prefix_format` (forensic reproducers that
  MUST stay byte-verbatim) — NOT live signing/hash paths.

## #1451 confirmed NOT a blocker for THIS PR

`git diff main...HEAD -- src/kailash/trust/enforce/selective_disclosure.py
src/kailash/trust/envelope.py`: the witness family is a 0-line diff and
`to_canonical_json` is still `default=str` on HEAD. The byte-CHANGING family
members #1451 tracks are NOT switched in this PR (only the byte-NEUTRAL
`envelope_hash → canonical_scalars` switch landed). So #1451 (their FUTURE
migration) does not gate this PR's correctness; rs#1448 was the PR's sole stated
cross-SDK byte-contract gate.

## Fixed this session (working-tree only, uncommitted — BUILD repo, commit stays with user)

- **Inaccurate durable claim** corrected in `tests/regression/test_canonical_encoder_family_conformance.py`
  (module docstring) AND `specs/trust-canonical-encoders.md`: the over-broad "first
  tests for `selective_disclosure.py`" → "first BYTE-CONFORMANCE tests for the
  witness-encoder family (`_hash_value` / `_compute_chain_hash` / export+verify
  sign-payloads)". Evidence the prior claim was false: `_redact_record` has 16 call
  sites in `tests/trust/unit/test_enforce_reasoning.py` and `RedactedAuditRecord` is
  used in `tests/trust/unit/test_adversarial.py:1052` on `main` — `selective_disclosure.py`
  already had test coverage. (`verify-claims-before-write.md` MUST-1 + `spec-accuracy.md`.)
  journal/0011 makes the same claim but is immutable (left as-is per `journal.md`).

## Residual gates (human — NOT autonomously resolvable)

1. **[MED] Cross-SDK byte-match (the load-bearing pre-merge gate).** No in-repo evidence
   proves py's vendored `test-vectors/audit-chain-canonical.json` is byte-identical to
   rs#1448's regenerated golden. py's fixture is `cross_impl_status: python-self-consistent`
   (re-authored, reproducible from py's own generator) — internally consistent but NOT
   yet vendored-from-rs. Resolving requires a cross-repo read of kailash-rs (explicit user
   authorization + 5 repo-scope conditions + receipt-before-acting). Recommended optimal
   fix per `cross-sdk-inspection.md` Rule 4a: byte-diff rs#1448's golden against py's copy
   AND, if matching, vendor it + flip `cross_impl_status` to `vendored-from-kailash-rs` so a
   future rs-side divergence fails py CI too.
2. **[LOW] Stale PR #1411 banner.** Body still says "⛔ DO NOT MERGE until kailash-rs#1448
   lands." #1448 reportedly landed → reframe to a byte-match-confirmation gate. Outward-facing
   (PR body) — recommend, confirm before editing.

## For Discussion

1. Rule 4a says sibling-canonical fixtures MUST be vendored, not re-authored. py currently
   re-authors its fixture (`python-self-consistent`) and proves it via its own generator —
   which catches py-internal regressions but is BLIND to an rs-side divergence. Is the
   one-time byte-diff (gate 1 option a) acceptable, or should we always vendor rs's golden
   so the cross-SDK contract is enforced in py CI permanently?
2. Counterfactual: if rs#1448's regenerated 6-digit fixture does NOT match py's bytes
   (e.g. a different nested-metadata rendering), which SDK re-pins? py's bytes reproduce
   from py's generator and pass 79 tests, so a mismatch would mean an rs-side divergence
   from the shared `#449` contract — but only the byte-diff can tell.
3. The throttle nulled an entire 5-agent parallel wave; serial dispatch fixed it but cost
   wall-clock. Is the right default for redteam fan-out now serial-from-the-start on this
   machine, or parallel-with-evidence-gate-and-serial-fallback (what was used here)?
