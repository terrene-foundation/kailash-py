# AUTHORIZATION — cross-repo GH issue to loom (sweep forest-ledger gap)

cross-repo-authorized: esperie-enterprise/loom

- **Date:** 2026-06-25
- **Requester:** user (co-owner, this session)
- **Target repo:** `esperie-enterprise/loom` (verified: exists, private, issues enabled)
- **Action (scoped exactly):** file ONE GitHub issue titled
  `feat(sweep): /sweep + /wrapup blind to workspace forest ledgers (two coupled gaps)`,
  body as restated to + approved by the user this session. No other cross-repo
  action authorized.
- **Why:** `/sweep` (canonical `commands/sweep.md`, loom-owned + synced) has no step
  reading the `## Outstanding ledger (forest)` section of any `.session-notes`; +
  `/wrapup` reconciliation never aggregates per-workspace ledgers to root. Surfaced
  this session when 4 dormant kailash-py workspaces (issues all CLOSED) held open
  forest items invisible to `/sweep`. loom owns the fix + distributes it.

## Verbatim instructions

> "update the artifacts and also file gh issue to loom so that it will know. then /codify"

> "i approve" (to the agent's restated target repo + title + scrubbed body)

## Disclosure scrub (upstream-issue-hygiene MUST-2)

Body carries NO client/operator/3rd-party identifiers. Workspaces described
generically; only public kailash-py issue numbers referenced as evidence. The
COC-artifact paths named (`commands/sweep.md`, `validate-forest-ledger.mjs`,
`.session-notes`) are the subject of the issue, not downstream-context leaks.
