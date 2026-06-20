# DECISION — Cross-repo authorization: file kailash-rs canonical-encoder family lockstep issue

cross-repo-authorized: esperie-enterprise/kailash-rs

- **Requester:** the user (technical leader, this session), genuine user turn.
- **Target repo:** `esperie-enterprise/kailash-rs` (private; Rust SDK sibling BUILD repo).
- **Timestamp:** 2026-06-20T20:00:00Z
- **Verbatim instruction:** "approved decision please file" — approving the
  recommendation in this session's message + `journal/0011` (expand the cross-SDK
  canonical-conformance lockstep to the two additional surfaces, or file a sibling
  `cross-sdk` issue against kailash-rs).
- **Bounded action authorized (WRITE — ONE issue):**
  1. File EXACTLY ONE GitHub issue against `esperie-enterprise/kailash-rs`
     recording that the canonical-encoder conformance lockstep (tracked at
     `kailash-rs#1448` for the audit chain) has a BROADER scope: two additional
     Family-B signing/hash surfaces — the selective-disclosure witness
     export/verify family and the constraint-envelope HMAC sign/verify pre-image
     (`to_canonical_json` equivalent) — use the non-conformant `default=str`-class
     encoder, claim `kailash-rs#449` byte parity, and are byte-CHANGING under the
     shared `canonical_scalars` whitelist. The issue ASKS rs to (a) confirm its
     current byte output for these two surfaces matches the `#449` contract, and
     (b) include them in the `#1448` canonical-migration lockstep planning so any
     future migration lands in BOTH SDKs in lockstep with shared fixtures re-pinned
     together. It is a coordination/conformance item, NOT a bug (no current
     divergence — both SDKs are on the current encoding today).
  2. Decision (per `/autonomize`): ONE combined issue (both surfaces share one
     root cause + one lockstep mechanism; keeps the canonical lockstep a single
     coordinated item alongside `#1448`), `cross-sdk` label, cross-referencing
     `#1448` / `#449` / py PR #1411 / py commit `ae0118b64`.
- **Scope fence (condition 5):** ONLY the single issue filing described above
  against the named repo. NO writes beyond that one issue, NO PRs, NO comments on
  other issues, and NO reads of kailash-rs source in this authorization (the
  issue is informed entirely by the py-side analysis + the `kailash-rs#449`
  contract that py's own code already references). Any subsequent cross-repo
  action requires its own explicit user authorization + a new receipt.
- **Context:** Follows `journal/0011` (the canonical-encoder family sweep that
  found the broadened lockstep scope) and `journal/0009`/`0010` (the audit-chain
  read + the `#1448` filing). `cross-sdk-inspection.md` Rule 1 mandates the
  sibling-SDK inspection; the user converted the surfaced recommendation into an
  explicit filing authorization.

---

## FILING RECEIPT

- **Filed:** `esperie-enterprise/kailash-rs#1451` —
  https://github.com/esperie-enterprise/kailash-rs/issues/1451
- **Label:** `cross-sdk`
- **Filed at:** 2026-06-20 (this session), per the authorization above.
- **Content disposition:** scrubbed per `upstream-issue-hygiene.md` — no operator/
  client/third-party tokens, no local paths, minimal-repro shape; cross-references
  `#1448` / `#449` / py PR #1411 / py commit `ae0118b64`. Framed as a
  coordination/conformance item (no current divergence), not a bug.
- **Scope honored:** exactly one issue filed; no kailash-rs source read; no other
  cross-repo action taken.
