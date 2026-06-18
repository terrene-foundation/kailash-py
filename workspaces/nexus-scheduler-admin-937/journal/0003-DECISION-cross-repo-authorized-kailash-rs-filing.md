---
type: DECISION
date: 2026-05-29
author: human
project: nexus-scheduler-admin-937
topic: cross-repo authorization to file 2 cross-SDK inspection issues on kailash-rs
phase: implement
tags: [cross-sdk, repo-scope-discipline, user-authorized-exception]
---

cross-repo-authorized: terrene-foundation/kailash-rs

# DECISION — User authorized cross-SDK filing on kailash-rs (#937 follow-up)

Per `repo-scope-discipline.md` § User-Authorized Exception, all five conditions met:

1. **User-initiated** — genuine user turn (this session).
2. **Explicit + specific** — target repo `terrene-foundation/kailash-rs`; exact
   action: file 2 cross-SDK inspection issues.
3. **Confirmed** — agent restated the action ("the kailash-rs cross-SDK filing —
   2 issues: missing NexusError handler + GET-dedup staleness — yes/no?"); user
   confirmed: **"approved both"**.
4. **Journaled before acting** — this entry + the marker line above land BEFORE
   any `gh issue create --repo terrene-foundation/kailash-rs` runs.
5. **Scoped exactly** — only the 2 named issues against only kailash-rs; no
   incidental reads of rs source, no scope creep.

## Bounded action

File 2 issues on `terrene-foundation/kailash-rs`, `cross-sdk` label, framed as
INSPECTION requests (I have not read kailash-rs source — per repo-scope-discipline
I do NOT inspect the sibling; the issues ask the rs maintainers to verify the
equivalent). Bodies scrubbed per `upstream-issue-hygiene.md` MUST-2/3: SDK-API
surface only, cross-ref to public kailash-py#937, no workspace paths / finding
tags / consumer context.

- **Issue A** — verify whether the Rust Nexus durable gateway deduplicates safe
  HTTP methods (GET/HEAD/OPTIONS) and could serve stale reads (kailash-py #937).
- **Issue B** — verify the Rust `NexusError → HTTP` mapping is actually wired at
  the transport (kailash-py had a documented-but-absent handler; Rust likely
  already has `into_response`, so this may be a no-op confirm).

## For Discussion

- Should Issue B be filed at all if the Rust SDK's `into_response`/`status_code`
  is the canonical source the convention rule cites (i.e., Rust likely already
  correct)? Filed as a verify-only issue to honor the explicit user authorization;
  rs maintainers can close as already-correct.
- Is "verify whether" the right framing when I cannot inspect rs source from a
  kailash-py session? (Yes — cross-sdk-inspection.md prescribes filing the
  inspection handoff; asserting the bug without reading rs would be unfounded.)
