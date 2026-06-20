---
type: DECISION
date: 2026-06-20
author: agent
project: cross-sdk-audit
topic: Fresh holistic /redteam caught two real gaps the prior "converged" rounds missed (red CI + cross-SDK NaN/Inf verify-break); both fixed, PR #1411 re-converged 2 clean rounds, CI green
phase: redteam
tags:
  [
    cross-sdk,
    canonical-encoder,
    redteam-convergence,
    pr-1411,
    integrity-manifest,
    allow-nan,
    ci-discipline,
  ]
relates_to: 0013-DECISION-post-1448-redteam-reconvergence-pr1411
---

# DECISION — Fresh /redteam caught two gaps prior "convergence" missed; PR #1411 re-converged

Continuation session (`/autonomize` + `/redteam` to convergence). The prior session
(journal/0013 + `.session-notes`) declared the PR #1411 code surface "converged (2 clean
passes)" and "ready-to-merge, CI running". Ground truth at this session's start CONTRADICTED
that: the remote `Cross-SDK Conformance / PACT N6 Conformance Vectors` check was **FAILING**,
and a fresh holistic redteam surfaced a second real defect. Both are now fixed and the PR is
genuinely converged + CI-green. This entry AMENDS the 0013 convergence claim.

## Two gaps the prior "converged" redteam missed

### Gap 1 — [HIGH/CI] PACT_VECTORS.sha256 not re-pinned (red Cross-SDK Conformance gate)

The PR's commit `9b9e01d3e` correctly changed `tests/trust/pact/conformance/vectors/audit_anchor.json`
(the #1400 six-digit-microsecond canonical fix: timestamp `…10:30:00+00:00` → `…10:30:00.000000+00:00`,
content_hash `ef25ab8a…` → `edfdf52b…`) but never re-pinned the repo-root integrity manifest
`PACT_VECTORS.sha256`. `cross-sdk-interop.yml` (step "Verify vector integrity", `shasum -a256 -c`)
therefore failed on the committed HEAD: `audit_anchor.json: FAILED`.

- **Root cause, not symptom:** the vector change is correct (verified: reproduces byte-for-byte
  from the live `AuditAnchor._canonical_input`/`compute_hash` path; a mutation test confirmed the
  empty-regenerate-diff proof is load-bearing, not vacuous). The manifest re-pin was simply omitted.
- **Fix — commit `b4929d924`:** re-pin `audit_anchor.json` `f7ba0381… → 3873da28…` + (LOW, same shard)
  register the PR's new `specs/trust-canonical-encoders.md` in `specs/_index.md` (`specs-authority` MUST-1).
- **Why the prior redteam missed it:** journal/0013's rounds never ran the conformance-vector
  integrity check (`shasum -c`). This session added a dedicated **integrity-manifest-sweep** lens that
  enumerates every `*.sha256` and verifies each — closing the class.

### Gap 2 — [MED/security] `to_canonical_json` HMAC pre-image emitted RFC-invalid NaN/Inf

`ConstraintEnvelope.to_canonical_json` (the LIVE HMAC sign/verify pre-image, consumed by
`sign_envelope`/`verify_envelope`) used `json.dumps(..., default=str)` WITHOUT `allow_nan=False`.
A NaN/Inf in free-form `metadata` (the sole un-isfinite-guarded ingress — financial fields ARE
guarded) emitted `Infinity`/`NaN` literals: Python's permissive json signs them, but a strict
cross-SDK parser (Rust `serde_json`) rejects them → a Python-signed envelope carrying NaN/Inf
metadata **cannot be HMAC-re-verified cross-SDK** — the exact parity hazard this PR exists to close.
The PR's sibling fix added `allow_nan=False` to `envelope_hash` (envelope.py:826) but missed this member.

- **Fix — commit `9dfb1d968`:** add `allow_nan=False` (+ explicit `ensure_ascii=True`, matching the
  Family-B wire-format common config the spec already mandated + the 3 sibling encoders already carry).
  **Byte-neutral on every finite envelope** (proven: identical bytes with/without the kwarg on valid
  input; the existing `default=str` datetime pin is unchanged). NOT the deferred `default=str` →
  `canonical_scalars` migration — `default=str` is PRESERVED (that byte-changing switch stays #1451).
  Regression test `test_to_canonical_json_rejects_nan_inf_metadata` asserts NaN/Inf metadata raises.
- **In-shard, not deferred:** same bug class as the PR (cross-SDK canonical conformance), ≤1 LOC + 1
  test, surfaced at gate review → `autonomous-execution` Rule 4 / `/autonomize` MUST-6 MANDATE fixing
  in-shard (filing a follow-up would be BLOCKED).

## Convergence — 2 consecutive clean rounds (durable receipts)

Per `verify-resource-existence` MUST-4 (convergence claims cite external receipts):

- **Round 1** — `wf_f746f707-f30`: 5 lenses (byte-conformance, integrity-manifest-sweep,
  security-tamper-evidence, spec-accuracy, coverage-ci), waves of ≤3, all ran, **findings: []**.
- **Round 2** — `wf_7775fe4c-ef2`: 3 independent re-derivation lenses dispatched **SERIALLY**, all ran,
  **findings: []**. → `converged: true, rounds_clean: 2`.

The earlier parallel Round 2 (`wf_b92e53d3`/`wf_f746f707` tails) nulled all 3 lenses to the
**synchronized concurrency throttle** (`"Server is temporarily limiting requests (not your usage
limit) · Rate limited"` — distinct from account-quota exhaustion, which a prior run hit and was
remedied by `csq swap`). The `ran`-evidence gate held correctly: throttled = did-not-run = NOT a clean
round (no false convergence). **Serial dispatch** (one agent at a time, fresh rate budget each) is the
durable remedy per `agents.md` § Redteam Reviewer Dispatch + `worktree-isolation` Rule 4 — the recurring
trap the prior session-notes flagged twice.

## CI + merge state

- HEAD `9dfb1d968`: **23 checks pass, 0 fail, 0 pending**. The previously-red `PACT N6 Conformance
Vectors` now passes (28s).
- `mergeable: MERGEABLE`; `mergeStateStatus: BLOCKED` is **REVIEW_REQUIRED only** (branch protection
  requires 1 approval; `failing: 0`) — the owner admin-merge bypasses it. Merge + release stay with the
  user (BUILD repo).

## Outstanding (unchanged from 0013/0014 — human-gated, cross-SDK)

- **F-XSDK-1451** (witness-family + `to_canonical_json` `default=str` → `canonical_scalars`): still the
  deferred byte-CHANGING lockstep with rs's `canonicalize`. This session's `allow_nan=False` fix is
  orthogonal (byte-neutral) and does NOT pre-empt the #1451 decision.
- **F-XSDK-4A**: unify the drifted `audit-chain-canonical.json` shared fixture across both repos.
- **F-AUDIT-XSDK** release lockstep: RELEASE must coordinate with rs#1448's release (not just merge).

## For Discussion

1. Both gaps shipped through a redteam that journal/0013 recorded as "converged (2 clean passes)".
   The miss was scope: 0013's lenses never ran `shasum -c` (integrity manifest) and never probed the
   NaN/Inf metadata ingress. Should the canonical-encoder redteam lens-set (integrity-manifest-sweep +
   the allow_nan/ingress probe) be promoted into a reusable conformance-audit checklist so the next
   canonical-vector PR cannot converge without them?
2. Counterfactual: had CI not gated on `PACT_VECTORS.sha256`, Gap 1 would have shipped a manifest that
   silently no-ops the integrity check for `audit_anchor.json` — invisible until a future tamper. Is the
   per-vector integrity manifest the right mechanism, or should the generator itself emit/refresh the
   manifest so re-pin can never be omitted?
3. The synchronized throttle nulled an entire parallel confirmation wave on THIS machine for the third
   recorded time. Is parallel-with-evidence-gate-and-serial-fallback still the right default for redteam
   fan-out here, or should the confirmation round be serial-from-the-start?
