# DECISION — Cross-repo authorization: verify kailash-rs canonical lockstep (#1448 + #1451 landed) + vendor

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (technical leader, manages both SDK teams), genuine user turns.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; Rust SDK sibling BUILD repo).
- **Timestamp:** 2026-06-20T13:06:25Z
- **Verbatim instructions (two turns):**
  1. "approved" — approving the recommendation in the prior message: read-only access
     of `esperie-enterprise/kailash-rs`'s `test-vectors/audit-chain-canonical.json`,
     byte-diff against py's vendored copy, and vendor-if-identical (+ flip
     `cross_impl_status` to `vendored-from-kailash-rs`) per `cross-sdk-inspection.md` Rule 4a.
  2. "1451 on rs side has landed but the pr has not been updated. please check" — the user
     reports BOTH rs#1448 AND rs#1451 have now landed and PR #1411's body is stale; directs
     a check of the #1451 landed state + the PR.
- **Bounded action authorized (READ-ONLY against kailash-rs; py-side writes are in-repo):**
  1. READ kailash-rs `test-vectors/audit-chain-canonical.json` (the #1448 shared audit-chain
     fixture) and any sibling canonical fixtures in rs `test-vectors/` covering the
     witness-family / envelope `to_canonical_json` surfaces (the #1451 scope). Byte-diff
     against py's vendored copies.
  2. READ the resolution state of rs#1448 + rs#1451 (`gh issue view`) to determine whether
     #1451 landed as a CONFIRM-no-divergence (rs stays on `default=str` for witness/envelope —
     py's pins remain correct) or a MIGRATION (rs switched those encoders — py would be
     DIVERGENT and must migrate in lockstep). This is the load-bearing distinction.
  3. If the audit-chain fixture is byte-identical: vendor rs's golden into py's
     `test-vectors/` + record provenance (`vendored-from-kailash-rs`). If #1451 shows a
     migration that diverges py's pinned bytes, do NOT switch py-only — surface as a finding
     for a lockstep decision.
- **Scope fence (condition 5):** ONLY the reads above against the named repo — the
  `test-vectors/` canonical fixtures + the #1448/#1451 issue state. NO broad rs source
  spidering, NO writes/PRs/comments against kailash-rs. py-side edits (vendoring, PR #1411
  body update — the PR the user flagged as not-updated) are in-repo and remain uncommitted
  (BUILD repo; commits stay with the user). Any rs read beyond the named fixtures + issue
  state requires its own authorization + receipt.
- **Context:** Follows journal/0009 (rs audit-chain read), 0010 (#1448 filing), 0011
  (family sweep), 0012 (#1451 filing), 0013 (post-#1448 redteam re-convergence). The redteam
  already proved py-side internal consistency + that PR #1411 does not touch the
  #1451 byte-CHANGING sites; this authorization closes the one residual cross-SDK byte-match
  gate against the now-landed rs state.

---

## OUTCOME (read + verify, 2026-06-20)

Read scope honored: only rs `test-vectors/audit-chain-canonical.json`, the rs `test-vectors/`
listing, rs#1448/#1451 issue state, and rs PR #1450/#1452 (the #1448/#1451 PRs the user's
"please check" directed). No broad rs source spidering; no writes against kailash-rs.

### 1. Audit chain (#1448) — LANDED + in lockstep (zero divergence)

- rs#1448 CLOSED/COMPLETED; closing PR **rs#1450** MERGED 2026-06-20T11:40:42Z
  ("align audit-chain canonical timestamp to fixed 6-digit microseconds").
- rs's `audit-chain-canonical.json` is on the 6-digit form (V1 ends `…10:00:00.000000+00:00`).
- **Definitive divergence check by canonical INPUT:** the 2 inputs both fixtures share
  (`anc-u1-001`, `anc-u2-001`) produce IDENTICAL `expected_sha256` in rs and py
  (`f1c755c8…`, `efd824a2…`). **0 same-input-different-SHA divergences.** The audit-chain
  6-digit + `canonical_scalars` contract is genuinely in cross-SDK lockstep on shared inputs.
  → PR #1411's SOLE stated cross-SDK gate (rs#1448) is CLEARED.

### 2. Rule 4a fixture DRIFT (real, but not a #1411 blocker)

The two `audit-chain-canonical.json` fixtures have drifted in SHAPE and COVERAGE (the exact
`cross-sdk-inspection.md` Rule 4a "re-authored, not vendored" failure):

- rs: `version:1` / `id`+`input` shape / vectors `V1–V4, N4, U1, U2` (genesis, sorted-keys,
  multi-anchor sequence).
- py: `spec_version:1.1` / `name`+`input_repr`+`provenance` shape / vectors `U1–U6`
  (incl. nonzero-microsecond, whole-second-explicit, typed-scalar-metadata, whole-second
  metadata-datetime — the edge cases that EXERCISE the #1400/#1405 fix).
- 5 rs-only inputs + 4 py-only inputs; neither is a superset. They AGREE where they overlap.
- **"Vendor if identical" (the authorized action) does NOT apply — they are NOT identical.**
  The correct fix is a UNIFIED shared fixture (union of vectors, one shape) vendored to BOTH
  repos — a cross-SDK reconciliation that touches rs (out of this session's write scope).

### 3. #1451 (witness-family + envelope) — rs landed TRIPWIRES, not a migration; rs is on `canonicalize`

- rs#1451 issue is **OPEN** (the user's "1451 landed" = the rs PR merged, not the issue closed).
- Closing-the-rs-side PR **rs#1452** MERGED 2026-06-20T12:56:17Z — `test(eatp)`, **no production
  code modified**: it adds loud-tripwire byte-pins for the redaction-value-hash family (the
  rs-side mirror of py's `test_canonical_encoder_family_conformance.py` pins).
- **KEY CROSS-SDK FINDING (rs#1452 body, citing rs source `types.rs:762/830/951`,
  `signed_artifact.rs:161`, `chain.rs:12`):** rs is the **INVERSE of py** — rs is ALREADY
  fully on the #449-conformant `canonicalize` encoder for EVERY Family-B surface; **rs has no
  `default=str`-class encoder** (serde_json has no such fallback; rich types pre-convert via
  the `canonicalize` type-whitelist). The ConstraintEnvelope HMAC pre-image has **no rs
  equivalent** (rs envelope external verification is Ed25519, not HMAC).

### 4. SPEC-ACCURACY DEFECT surfaced (NOT auto-fixed — entangled with the #1451 decision)

py's `specs/trust-canonical-encoders.md` + `test_canonical_encoder_family_conformance.py`
justify keeping the witness-family/`to_canonical_json` on `default=str` with: _"the kailash-rs
counterpart that mirrors the current `default=str` output."_ rs#1452 CONTRADICTS this — rs is
on `canonicalize`, not `default=str`. The pin itself is SAFE either way (defensive tripwire),
but the RATIONALE is inverted: the open #1451 direction is likely **py → `canonical_scalars`
to MATCH rs's `canonicalize`**, not "keep py on `default=str`." This is a cross-SDK
architecture decision the user (both-SDK lead) owns — surfaced for direction, not auto-decided.

### Disposition

- **PR #1411 is merge-ready on its own (audit-chain) scope** — #1448 lockstep confirmed,
  0 divergence; the witness/envelope pins are correct defensive tripwires regardless of #1451.
- **No vendoring performed** (fixtures not identical — the authorized precondition failed).
- **PR #1411 body updated** to reflect the verified state (stale banner reframed).
- Two cross-SDK follow-ups surfaced for the user's direction: (4a) unify the audit-chain
  shared fixture across both repos; (#1451) decide the witness/envelope encoder alignment
  (py→canonical_scalars to match rs) + correct the spec rationale accordingly.
