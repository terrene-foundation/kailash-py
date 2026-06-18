---
type: DECISION
slug: cross-repo-authorized-mint-errata-issue
created: 2026-06-13T14:09:29Z
---

# Cross-Repo Authorization — file EATP-08 §4 ed25519+sha256 transition erratum on mint

cross-repo-authorized: terrene-foundation/mint

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn (2026-06-13) — verbatim: "issue
   F-EATP-ERRATA to mint".
2. **Explicit + specific:** target `terrene-foundation/mint`; bounded action =
   file ONE new issue for F-EATP-ERRATA (the ed25519+sha256 transition provision,
   EATP-08 §4 open erratum question per specs/trust-crypto.md §32.5).
3. **Confirmed:** the directive is an explicit imperative naming target + item;
   restated here + in the session report. Matches the established eatp-gaps
   cross-repo pattern (journals 0001-0003, all executed).
4. **Journaled before acting:** this entry lands BEFORE the `gh issue create`.
5. **Scoped exactly:** ONLY a new issue on terrene-foundation/mint; no other
   write, no incidental edits. Existence verified: mint repo exists (private),
   mint#6 = EATP-08 parent spec, no existing mint issue covers the transition
   erratum (checked `gh issue list --search`).

## Disclosure scrub (upstream-issue-hygiene MUST-2)

Body references SDK/standards surfaces only — mint#6, kailash-py#1304, the
EATP-08 registry tokens (`eatp-v1`, `ed25519+sha256`). No consumer/downstream
identifiers, paths, finding tags, or workspace IDs.

## Filed

terrene-foundation/mint#26 — "[erratum] EATP-08 §4 — transition provision for
already-emitted ed25519+sha256 records" (filed 2026-06-13).
