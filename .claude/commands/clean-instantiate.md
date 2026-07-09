---
description: Clean a freshly-cloned client repo of canon operator/trust identity BEFORE /ecosystem-init (clear-then-bootstrap). Destructive; dry-run by default; human-gated.
---

# /clean-instantiate — Strip Canon Identity From A Client Clone (once, before /ecosystem-init)

When a client clones, copies, or templates canon (loom + builds + use-templates) from GitHub to
instantiate **their own** ecosystem, the clone inherits canon's committed **coordination-substrate
identity** — the genesis trust-root, the operator roster (signing keys, owner identity), the journal,
the team-memory facts, the ecosystem registry, the tenant denylist. `/ecosystem-init` does NOT clear
these — it presumes the client owner is already enrolled. **This command is the clear-then-bootstrap
step that runs FIRST**, on the client clone (canon is never touched).

It is the fourth onboarding surface, strictly BEFORE the other three: **`/clean-instantiate`** (once,
on a fresh client clone) → `/ecosystem-init` (once per fork — re-anchors genesis to YOUR owner) →
`/enroll` (once per operator) → `/onboard` (read-only, every session).

**Usage**: `/clean-instantiate` — runs in the current clone's checkout.

Procedure depth (the contamination-surface map, the assert-zero gate semantics, troubleshooting a
fail-closed residual) lives in `.claude/skills/46-clean-instantiate/SKILL.md` per `cc-artifacts.md`
Rule 3; this command is the entry point. The engine is `.claude/bin/clean-instantiate.mjs`; the
"what counts as canon identity" judgement is the SHARED `.claude/bin/lib/identity-scrub.mjs` lib —
the exact gate the public-fork publish fence uses, so the two fences cannot drift.

## What it clears (plain language)

- **Operator roster** → reset to a placeholder. Canon's owner identity, signing keys, and trust-root
  are removed; YOUR `/ecosystem-init` + `/enroll` re-establish them.
- **Decision journal** (`journal/`) → deleted. Canon's recorded decisions are canon's, not yours.
- **Team-memory facts** → cleared (the index README is kept).
- **Ecosystem registry** (`ecosystem.json`) → reset to a placeholder, with `upstream_canon` pointed at
  the canon you cloned from (so your fork is recognised as a fork; the cross-ecosystem write-fence's
  operative activation stays gated on #576 — the entry-point hook is registered at F3 Level-1).
- **Tenant denylist** → emptied.
- **Per-clone coordination state** (logs, posture, lease, init markers) → cleared if a copy carried them.

Until you run this, a freshly-cloned client stays **coordination-OFF** (non-disruptive) — the
multi-operator substrate turns ON only by your explicit `/ecosystem-init` (a placeholder genesis reads
as not-yet-anchored).

## The two-step human gate (destructive — confirm before applying)

This command **deletes** `journal/` and **overwrites** the roster, so it follows the destructive-op
discipline (`commands/autonomize.md` § Prudence + the destructive-op confirm MUST in `cross-repo.md`
root MUST-2 / `git.md`): dry-run first, confirm, then apply.

1. **Preview (writes nothing):**

   ```
   node .claude/bin/clean-instantiate.mjs
   ```

   Reports how many canon-identity tokens the clone carries, what would be cleared, and the
   `upstream_canon` URL that would be set. STOP and show this to the operator.

2. **Confirm**: ask the operator, in plain language: "This permanently deletes this clone's `journal/`
   and resets the operator roster + ecosystem config to placeholders. Canon is untouched. Proceed?"
   Wait for an explicit yes.

3. **Apply** (only after yes):

   ```
   node .claude/bin/clean-instantiate.mjs --apply [--reset-history] [--upstream-canon-url <git-url>] [--ecosystem-id <label>]
   ```

   If `--upstream-canon-url` is omitted, the engine captures `git remote get-url origin` (the URL you
   cloned canon from). Re-running `--apply` on an already-cleared clone is **refused** (the canon
   snapshot can no longer be re-derived) — re-clone if you must run it again.

## The `.git` history caveat (canon history is NOT in the working tree)

A `git clone` of canon carries canon's **entire commit history** in `.git/` — commit authorship, the
pre-clear journal blobs, the real root_commit. The working-tree clear (and its assert-zero gate) cannot
reach that history; on `git push` it would ship. The engine therefore **never claims the clone is
clean** while that history exists: it scopes its pass to "working tree" and loudly directs you to either
re-run with **`--reset-history`** (re-anchors a fresh root commit, discarding canon history) or strip
history yourself before pushing. Pass `--reset-history` once you have confirmed the working-tree clear.

## The fail-closed assert-zero gate

After `--apply`, the engine runs a **fail-closed** gate: it greps the whole tree for every canon
trust-identity token snapshotted before the clear (fingerprints, PGP names/emails, principals,
person-ids, tenant tokens) **and** runs the framework's structural disclosure scanner. **ANY residual →
exit 1** (the ceremony never silently claims clean). On a non-zero exit, surface the residual hits to
the operator: it means canon identity survives in a file the clear does not own (e.g. prose), which the
operator must address (or clone the already-scrubbed public distribution instead). Do not proceed to
`/ecosystem-init` until the gate exits 0.

## On success

Exit 0 prints the next step: **`/ecosystem-init`** to re-anchor genesis to YOUR owner, then `/enroll`.
