---
type: DECISION
slug: 1532-cross-repo-read-grant
date: 2026-07-11
---

# DECISION — #1532 cross-repo read grant (RECORDED, not yet exercised)

## Context

#1532 (consolidate delegate connectors into `contrib/delegate-connectors/` as
independently-versioned packages) was DEFERRED to a dedicated fresh session. This session the
co-owner granted the cross-repo reads that session needs and gave the approach. No cross-repo
action was taken THIS session — this entry RECORDS the grant so the fresh #1532 session starts
with it; per `repo-scope-discipline.md` § User-Authorized Exception the fresh session MUST still
do the per-action restate+confirm+journal-before-acting for EACH read (a standing grant does not
satisfy the per-action gate — `handoff-completion.md` MUST-3).

## Verbatim directive (co-owner, 2026-07-11)

> "on 1532, approve dc read but dce is more advanced so you should take reference from that.
> I suggest that you check the implementation of dce in rs first. important to note that we
> align to specs and not to kailash-rs. i approve cross-rep read into dc and kailash-rs, as
> well as terrene and mint for specs as required."

## Grant (RECORDED — to be exercised by the #1532 session, per-action confirm+journal each read)

- cross-repo-authorized (RECORDED, not yet exercised): **dc** (delegate-connectors — exact
  repo path to resolve via `bin/lib/loom-links.mjs`, not positional-guess)
- cross-repo-authorized (RECORDED, not yet exercised): **kailash-rs** (`esperie-enterprise/kailash-rs`)
- cross-repo-authorized (RECORDED, not yet exercised): **terrene** — for specs, as required
- cross-repo-authorized (RECORDED, not yet exercised): **mint** — for specs, as required

## Approach (co-owner-directed)

1. **Check the implementation of `dce` (delegate-connectors-engine) in `rs` FIRST** — it is the
   more-advanced reference; take reference from it.
2. **Align to SPECS, not to kailash-rs.** kailash-rs `dce` is a reference implementation, NOT the
   authority — the specs (in terrene / mint, as required) are authoritative. Where dce and the
   specs disagree, the specs win.
3. Then do the #1532 `contrib/delegate-connectors/` consolidation (with-history migration;
   operator-local `dc` sources) aligned to the specs.

## Follow-ups for the fresh session

- Resolve exact repo locations for `dc` / `terrene` / `mint` via the loom-links resolver (or ask)
  BEFORE reading — do NOT positional-guess (`cross-repo.md` MUST-1).
- Per-action confirm+journal each cross-repo read (`repo-scope-discipline.md` conditions 3+4).
- This is a dedicated-session task (with-history migration) — run `/analyze` against the specs +
  the `dce` reference before `/todos`.
