# DECISION — Cross-repo authorization: file kailash-rs audit-chain timestamp-lockstep issue

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (technical leader, this session), genuine user turn.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; Rust SDK sibling BUILD repo).
- **Timestamp:** 2026-06-20T18:30:00Z
- **Verbatim instruction:** "please file issue into kailash-rs and i will get the team to prioritize it"
- **Bounded action authorized (WRITE — ONE issue):**
  1. File EXACTLY ONE GitHub issue against `esperie-enterprise/kailash-rs` requesting
     the audit-chain canonical-timestamp lockstep: align the Rust audit-chain
     canonical timestamp to fixed six-digit microseconds (matching the
     already-6-digit trace-event fingerprint contract and the kailash-py
     conformance fix), regenerate the shared `test-vectors/audit-chain-canonical.json`
     to the 6-digit form, and add backward-compat recognition + a regression test.
  2. Labels: `cross-sdk` (+ `bug` if appropriate). Cross-reference per
     `cross-sdk-inspection.md` Rule 2 (this is a BUILD↔BUILD cross-SDK alignment,
     which mandates the cross-SDK note + link to kailash-rs#449, the audit-chain
     canonical contract this aligns).
  3. Issue body scrubbed per `upstream-issue-hygiene.md` MUST-2/3: SDK-API surface +
     public canonical-byte vectors + public kailash-py issue numbers ONLY. NO
     kailash-py session internals (no workspace paths, no journal refs, no redteam
     round details, no internal finding tags, no consumer/operator names).
  4. The exact issue body is restated to the user for a final confirm BEFORE
     `gh issue create` (the outward-facing, hard-to-reverse, public-record step) per
     `upstream-issue-hygiene.md` MUST-1.
- **Scope fence (condition 5):** ONLY the single issue filing against the named repo.
  NO PRs, NO comments elsewhere, NO code writes to kailash-rs, NO incidental edits.
  The rs CODE change itself is a SEPARATE future workstream (its own session +
  its own authorization); this entry authorizes the ISSUE filing only.
- **Context:** distinct from the read-only authorization in journal/0009 (which
  determined rs is on whole-second / variable-precision). The user chose the
  cross-SDK lockstep disposition and directed the issue filing as the formal
  hand-off to the rs team. kailash-py side: branch
  `fix/audit-chain-canonical-conformance`, public issues #1400/#1401/#1402/#1403/
  #1404/#1405/#1407, redteam-converged.

---

## OUTCOME (filed, 2026-06-20)

Filed ONE issue per the authorization: **esperie-enterprise/kailash-rs#1448** —
"fix(audit): align audit-chain canonical timestamp to fixed 6-digit microseconds
(cross-SDK lockstep)" (labels: `cross-sdk`, `bug`). Body shown to + approved by the
user before submission (upstream-issue-hygiene MUST-1). Scrubbed to SDK-API surface +
public canonical-byte vectors + public kailash-py issue numbers; no session internals.
Scope honored: exactly one issue, no other cross-repo writes. The user will route it to
the rs team for prioritization; the rs CODE change remains a separate future workstream.
