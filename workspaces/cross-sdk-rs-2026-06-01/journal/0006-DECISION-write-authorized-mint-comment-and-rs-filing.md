---
type: DECISION
slug: write-authorized-mint-comment-and-rs-filing
created: 2026-06-02T03:05:00Z
---

# Cross-Repo WRITES authorized — mint#8 amendments + rs binding tracker

cross-repo-authorized: terrene-foundation/mint
cross-repo-authorized: esperie-enterprise/kailash-rs

Two per-action WRITE grants (repo-scope-discipline § User-Authorized Exception, all five conditions), approved together after the red-team REFUTED the original "split mint#8" plan and the user approved the corrected "strengthen-and-align" plan.

- **Requester:** repo co-owner (this session's user).
- **User directive (verbatim):** "approved." (in response to the corrected plan: "Approve the corrected cross-repo writes — A (comment amendments on mint#8) + B (file rs binding tracker)?" + "My pick: go on A+B+C as described. Want me to proceed?"). Prior turn the user also said "approved but please redteam your analysis first then split mint#8. Ensure you file the same works to kailash-rs to align" — the split was refuted by both red-teams; the corrected mechanic (contribute gap-closing amendments instead of splitting) was explicitly re-approved this turn.
- **Confirmed:** the corrected plan named A (mint#8 review comment with amendments) + B (rs binding tracker) explicitly; the user approved.

## Action A — `terrene-foundation/mint` (WRITE: issue comment)

- `gh issue comment 8 --repo terrene-foundation/mint` — ONE comment: a cross-SDK implementation red-team of the EATP-10 draft surfacing 3 MISSING + 2 PARTIAL CRITICAL gaps + 4 HIGH PARTIAL + 2 STRUCTURAL, each with a proposed normative clause. Body composed at `/tmp/mint-read/mint8-comment.md` from the workflow cross-check (wf_fb6bac61-ba6).
- **Scrub:** body is spec-clause content (N8-\* MUST clauses) + draft-section citations only. NO kailash-py internal source paths, NO secrets, NO workspace ids, NO session timestamps. Cites kailash-py#630/#596 as the legitimate cross-SDK implementation drivers. mint is the Foundation spec repo (not a downstream consumer); a structured spec review there is appropriate.
- **NOT splitting mint#8** — the split was refuted; this is a strengthen-in-place comment.

## Action B — `esperie-enterprise/kailash-rs` (WRITE: issue create)

- `gh issue create --repo esperie-enterprise/kailash-rs` — ONE issue: rs-side Trust Vault Shamir-backup binding (rs equivalent of kailash-py#630), gated on mint#8 (EATP-10), carrying the cross-SDK contract requirements (KEK-resolution + KMS/HSM non-exportability, memory-hygiene-via-process-boundary, passphrase provenance, restore-authz layer, refusal-semantics parity). Label `cross-sdk`. Cross-refs kailash-py#630 + mint#8.
- **Scrub (upstream-issue-hygiene Rule 2/3):** SDK API surface + cross-SDK contract only. NO kailash-py internal paths, NO workspace ids, NO finding tags tied to this session, NO timestamps tied to consumer work. rs-side gap framed as a parity INQUIRY (rs source NOT read — repo-scope-discipline: no incidental cross-repo reads).
- **Accuracy:** py-side facts verified this session (the #630 stub + the mint#8 draft delta); rs-side framed as "does rs have the equivalent + here is the corrected contract."

## Scope (condition 5)

Exactly these two writes (A: one mint#8 comment; B: one rs issue) + the in-repo kailash-py#630 comment (Action C, same-repo, no cross-repo grant needed). No mint writes beyond the one comment, no rs writes beyond the one issue, no rs source reads, without a new gate.

## Outcome receipts

- **A filed:** `terrene-foundation/mint#8` comment — https://github.com/terrene-foundation/mint/issues/8#issuecomment-4600372820 (10-finding cross-SDK red-team + proposed normative amendments). NOT a split.
- **B filed:** `esperie-enterprise/kailash-rs#1206` — rs-side Trust Vault Shamir-backup binding tracker, label cross-sdk, cross-ref kailash-py#630 + mint#8.
- **C posted:** `terrene-foundation/kailash-py#630` comment — corrected gate (mint#8 not "ISS-37"), CRIT-4 feasibility prerequisite, links to A + B; backup.py docstring fix deferred to implementation PR.
- Scope honored: exactly one mint comment, one rs issue, one in-repo #630 comment. No splits, no rs source reads, no further cross-repo writes.
