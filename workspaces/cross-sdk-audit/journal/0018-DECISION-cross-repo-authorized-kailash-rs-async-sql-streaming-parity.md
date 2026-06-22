# 0018 — DECISION: cross-repo authorized — kailash-rs async-SQL streaming parity issue

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Timestamp:** 2026-06-22T05:31:45Z
- **Requester:** jack.hong (co-owner; in-session)
- **Target repo:** `esperie-enterprise/kailash-rs` (private Rust SDK)
- **Action (bounded, exact):** file ONE scrubbed cross-SDK parity issue via
  `gh issue create --repo esperie-enterprise/kailash-rs`, labels `cross-sdk` +
  `enhancement`, with the verbatim title + body reviewed and approved in-session.
  The issue requests the rs maintainer check for (a) an equivalent non-functional
  `FetchMode::Iterator`-class dead enum + silent-fallback in the Rust async-SQL
  surface and (b) a memory-bounded server-side-cursor `stream()` parity API —
  cross-referencing the Python work (terrene-foundation/kailash-py#1416 + #1417,
  shipped in kailash 2.44.0).
- **NO incidental reads** of kailash-rs source/specs/tests; the issue is authored
  from the known py-side finding only (cross-sdk-inspection pattern), letting the rs
  maintainer scope it with their own repro. Body scrubbed per
  `upstream-issue-hygiene.md` MUST-2/3 (no session/workspace/downstream context, no
  finding tags, minimal SDK-API-only repro shape).

## Verbatim authorization

1. Decision-packet selection: **"File a scrubbed rs issue now"** (Rust SDK parity
   question, this session).
2. On the presented verbatim issue title + body + target + labels: **"yes"** (file
   it verbatim against `esperie-enterprise/kailash-rs`).

## Conditions (repo-scope-discipline.md User-Authorized Exception — all five hold)

1. User-initiated — genuine user turns (the selection + the "yes"). ✓
2. Explicit + specific — names `esperie-enterprise/kailash-rs` + the exact bounded
   filing action + the verbatim body. ✓
3. Confirmed — agent restated action + target + verbatim body; user confirmed "yes"
   before execution. ✓
4. Journaled before acting — THIS entry, written before `gh issue create` runs. ✓
5. Scoped exactly — only this one issue against only this repo; no incidental reads,
   no scope creep. ✓
