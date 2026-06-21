# DECISION — Cross-repo authorization: verify kailash-rs #1448 RELEASE state (py 2.43.1 lockstep gate)

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (technical leader, manages both SDK teams), genuine user turn.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; Rust SDK sibling BUILD repo —
  NOT `terrene-foundation/kailash-rs`, per the standing reference correction).
- **Timestamp:** 2026-06-21T10:47:28Z
- **Verbatim instruction:** "approved" — approving the prior message's two-part request:
  (a) explicit authorization to verify rs#1448's release state on `esperie-enterprise/kailash-rs`,
  and (b) confirmation to proceed with the py 2.43.1 PyPI publish of the NaN/Inf sweep.
- **Bounded action authorized (READ-ONLY against kailash-rs; ALL py-side writes are in-repo):**
  1. READ rs#1448 issue + its closing PR state
     (`gh issue view 1448 --repo esperie-enterprise/kailash-rs`; the closing PR rs#1450 per 0014).
  2. READ kailash-rs RELEASE state (`gh release list/view --repo esperie-enterprise/kailash-rs`)
     to determine whether the #1448 audit-chain-canonical content has been cut into a released
     crate version — the py 2.43.1 lockstep gate (does py ship the cross-SDK-conformance content
     ahead of rs, or is rs already released?).
- **Scope fence (condition 5):** ONLY the reads above against the named repo — rs#1448 issue/PR
  state + rs release-list/version state. NO broad rs source spidering, NO writes/PRs/comments
  against kailash-rs. py-side edits (version bump, CHANGELOG, journal amendment) are in-repo and
  ride the `release/v2.43.1` PR. Any rs read beyond #1448 + release state requires its own
  authorization + receipt.
- **Context:** Follows journal/0014 (rs#1448 audit-chain LANDED + 0-divergence verified;
  closing PR rs#1450 MERGED 2026-06-20T11:40:42Z) + 0015 (PR #1411 converged). PR #1412
  (trust-plane-wide NaN/Inf sweep) MERGED 2026-06-21 (py merge `b2f265ce8`); its surfaces are
  OUTSIDE Family-B (byte-neutral, no pinned cross-SDK vector changed — needs no rs lockstep per
  the convergence redteam). This authorization confirms the rs RELEASE state (not merely landed)
  before the irreversible py 2.43.1 PyPI publish.

---

## OUTCOME (verify, 2026-06-21)

Read scope honored: only rs#1448 issue state, the rs release list, and rs release `v4.12.0`
notes (to confirm #1448 inclusion). No broad rs source spidering; no writes against kailash-rs.

### rs#1448 — RELEASED (lockstep gate CLEARED)

- rs#1448 **CLOSED/COMPLETED** 2026-06-20T11:40:43Z (closing PR rs#1450, per journal/0014).
- kailash-rs releases since: **v4.12.0** (2026-06-20T17:43:51Z), v4.12.1 (2026-06-21T08:53:00Z).
  v4.11.0 (06-20T10:08Z) predates the #1448 close, so the first release CARRYING #1448 is v4.12.0.
- rs **v4.12.0** release notes confirm it verbatim: _"fix(audit): align audit-chain canonical
  timestamp to fixed 6-digit microseconds (#1448, cross-SDK lockstep) … PR #1450"_.
- **Disposition:** rs has already RELEASED the #1448 audit-chain-canonical content (v4.12.0+).
  py 2.43.1 (audit-chain re-pin from #1411 + the trust-plane-wide NaN/Inf sweep from #1412)
  therefore FOLLOWS rs — it does not ship cross-SDK-conformance content ahead of the Rust SDK.
  The #1412 NaN/Inf surfaces are additionally out-of-Family-B / byte-neutral / need no rs
  lockstep at all (per the convergence redteam, run `wf_157fb9c6-3e8`). **py 2.43.1 is clear
  to release.**
