---
type: DECISION
slug: cross-repo-authorized-rs
created: 2026-06-01T06:34:42Z
---

# Cross-Repo Authorization — esperie-enterprise/kailash-rs

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn this session (2026-06-01) — the user
   selected "Authorize cross-SDK rs work" at the AskUserQuestion prioritization gate.
2. **Explicit + specific:** target repo `esperie-enterprise/kailash-rs`; bounded
   actions: (a) READ for #760 Check 1 (verify rs#723 SHA-256 fingerprint pin landed
   + cross-SDK fixture-byte parity); (b) DRAFT scrubbed issue bodies for F25 (#937
   scheduler-admin cross-SDK follow-up) + F26 (Multipart/SSE/WS parity gap).
3. **Confirmed:** agent restated target + actions in the AskUserQuestion option
   description; user confirmed by selecting it ("all of the above in parallel").
4. **Journaled before acting:** THIS receipt lands before any substantive rs access.
5. **Scoped exactly:** READ-only for #760 Check 1; DRAFT-only for F25/F26.
   **Actual `gh issue create` / `gh pr create` against kailash-rs is NOT covered** —
   per upstream-issue-hygiene Rule 1, each filing needs its own per-issue human gate
   with the scrubbed body shown. "User said yes once" is NOT standing filing approval.

## Verbatim user grant

> "all of the above in parallel with workflow"
> (selecting option: "Authorize cross-SDK rs work — Grant me explicit auth to
>  read/write esperie-enterprise/kailash-rs for #760 Check 1 + F25/F26 parity
>  filings. I'll journal the cross-repo-authorized marker first, then proceed.")
