---
type: DECISION
slug: 1532-cross-repo-read-grant-EXERCISED
date: 2026-07-13
supersedes-context: 0014 (grant RECORDED; this entry EXERCISES it per-action)
---

# DECISION — #1532 cross-repo reads EXERCISED (per-action confirm+journal-before-acting)

## Context

#1532 (consolidate `delegate-connectors` → `contrib/delegate-connectors/` as independently-versioned
packages) is the sole unblocked forest item (F13). Its mandated first step — "check `dce` in `rs`
first, align to specs" (grant journal `0014`) — requires cross-repo reads. Per
`repo-scope-discipline.md` § User-Authorized Exception the standing `0014` grant does NOT satisfy the
per-action gate; this entry is the per-action **restate + confirm + journal-BEFORE-acting** receipt.
This repo has no `bin/lib/loom-links.mjs` resolver, so repo locations were obtained by asking the
co-owner directly (grant `0014` follow-up permits "or ask").

## Verbatim directive (co-owner, 2026-07-13)

> "confirm cross-repo reads (~/repos/terrene, ~/repos/terrene/mint,
> ~/repos/terrene/contrib/delegate-connectors but please check the kailash-rs that have integrated
> delegate-connectors-enterprise as that is the anchor while you must align to the specs not copy
> blindly, kailash-rs is correct)"

Preceded by (this session) the co-owner authorizing the reads in response to my restatement naming
the exact targets + the exact action (read-only, for the #1532 /analyze step).

## Requester / target / action / timestamp

- **Requester:** co-owner (jack@integrum.global), user-initiated turn, 2026-07-13T01:17:47Z
- **Action:** READ-ONLY. Characterize the delegate-connectors surface (OSS `dc` to migrate), the
  enterprise `dce` anchor, how `kailash-rs` integrates `dce`, and the authoritative specs. NO writes,
  NO edits, NO commits in any target repo. Align the eventual `contrib/` migration to the SPECS —
  `dce`/`rs` are reference implementations, the specs win where they disagree (grant `0014` approach §2).
- **Scope:** exactly the paths marked below; no incidental reads outside them.

## Authorized targets (greppable markers)

- cross-repo-authorized: terrene — /Users/esperie/repos/terrene (delegate-connector SPECS, authority)
- cross-repo-authorized: terrene/mint — /Users/esperie/repos/terrene/mint (SPECS, authority)
- cross-repo-authorized: terrene/contrib/delegate-connectors — /Users/esperie/repos/terrene/contrib/delegate-connectors (OSS `dc` source to consolidate)
- cross-repo-authorized: terrene/contrib/delegate-connectors-enterprise — /Users/esperie/repos/terrene/contrib/delegate-connectors-enterprise (`dce` enterprise anchor, more-advanced reference)
- cross-repo-authorized: esperie-enterprise/kailash-rs — /Users/esperie/repos/kailash/build/kailash-rs (rs integration of `dce`, the anchor to check per directive)

## Disposition

Reads dispatched AFTER this entry lands. Alignment authority = specs (terrene/mint); `dce` + `rs` are
references, not copy targets. Output feeds `/analyze` → `/todos` for the in-repo `contrib/` consolidation.
No cross-repo WRITE is authorized by this entry (a migration-with-history write, if reached, needs its
own confirm+journal). kailash-py is a BUILD repo — commits stay with the co-owner.
