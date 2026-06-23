---
description: "Ingest the USE-template proposal stream at loom (Gate-1 review + scrub + classify); one half of loom's inbound sync"
---

Ingest the **USE-template proposal stream** INBOUND at loom (Gate-1). `/sync-from-use` brings COC-artifact-improvement proposals (originated by USE-template `/codify` per `guides/co-setup/09-proposal-protocol.md` Step 7b, including downstream-relayed proposals) into loom for classification. Its sibling `/sync-from-build` ingests the BUILD proposal stream; together they are loom's full inbound surface, mirroring the outbound `/sync-to-use` + `/sync-to-build`.

Detailed protocol: `skills/30-claude-code-patterns/sync-flow.md` § Gate 1 (loaded by the sync-reviewer agent).

**Usage**: `/sync-from-use [target]` — `target` = `py`, `rs`, `rb`, `base`, or `all`. If omitted, ask.

## Step 0: Verify Repo Class (this verb is loom-only)

Read `.claude/VERSION` → `type`. `/sync-from-use` is valid ONLY at loom (`type: coc-source`).

- `coc-source` → proceed below.
- `coc-use-template` → STOP: "this is a USE template — ingest the downstream inbox with `/sync-from-downstream`."
- `coc-project` → STOP: "this is a downstream consumer — pull from your template with `/sync-from-template`."
- `coc-build` → STOP: "BUILD repos receive artifacts via `/sync-to-build` run at loom; they do not ingest."
- Missing → ask the user what class this repo is.

## Step 0b: Loom-Main Freshness Check (loom only)

Before Gate 1, verify loom's local `main` matches `origin/main` — Gate-1 classification onto a stale local main places artifacts against outdated state (F62, journal/0163 / 0164).

```bash
node .claude/bin/check-sync-freshness.mjs --loom
```

Exit 1 → HALT; the helper emits the verbatim local-vs-remote SHA pair AND remediation (`git fetch origin main && git reset --keep origin/main` per `git.md` — `--keep` over `--hard` to refuse on dirty tree). Read-only check — no fetch side-effects.

## Gate 1: Review + Scrub — the USE-template stream

**loom is the central splitter, not an author.** loom does NOT originate artifact changes — it ingests proposals, splits global vs variant at Gate 1, then dual-distributes: `/sync-to-use` distributes to USE templates (which downstream repos pull via their own `/sync-from-template`); `/sync-to-build` pushes canonical back to BUILD repos.

The **USE-template stream** (`kailash-coc-*`) carries COC-artifact-improvement proposals from USE-template `/codify` origination per `guides/co-setup/09-proposal-protocol.md` Step 7b. Downstream-relayed proposals (a `coc-project` consumer's Step-7c upflow relayed by its template, hop-provenance `origin: downstream, via: <template-slug>`, never consumer-identifying) ride this same stream.

**Disclosure-scrub on intake (MUST, runs first):** before classifying any change, run `node .claude/bin/scan-synced-disclosure.mjs --root <use-template-path>` against the candidate artifact files AND have a human scrub the `.proposals/latest.yaml` body per `upstream-issue-hygiene.md` Rule 2 (`.proposals/` is `isNeverSynced`, so `--root` won't reach it — the human gate covers the body). Non-zero exit or any finding = HALT until genericized + relocated (#255/#260 pattern). Symmetric with the Gate-2 synced-disclosure preflight in `/sync-to-use`.

**Trigger**: Runs automatically when `/sync-from-use` detects unreviewed USE-template-stream changes. Also runs if the user explicitly says "review" (e.g., `/sync-from-use py review`).

**Process summary** (full protocol in skill § Gate 1):

1. Read `sync-manifest.yaml` for tier membership + variant mappings; `repos.{target}.templates[]` gives the USE-template logical NAMEs — resolve each on-disk path via `bin/lib/loom-links.mjs::resolveRepo("use-template.{slug}")` (canonical NAME→location binding, `cross-repo.md` MUST-1), never a positional guess.
2. Read the template's `.claude/VERSION` upstream block — report current template version in the review header.
3. Compute expected state (loom + variant overlay), diff the template's proposal against it.
4. Check `.claude/.proposals/latest.yaml` status (`pending_review` / `reviewed` / `distributed`); for `reviewed`, re-review only entries appended after `reviewed_date`.
5. For each NEW or MODIFIED file, classify (sync-reviewer agent: global vs variant vs skip).
6. Place files: global → `.claude/{type}/{file}`, variant → `.claude/variants/{lang}/{type}/{file}`, skip → leave in the template only. New-rule discipline applies at placement: every new rule landed at loom MUST also land a corresponding `validate-emit.mjs` check OR a `no-check: <reason>` annotation in the same PR.
7. Mark proposal as reviewed.

**Skip when**: No diff between the template proposal and expected state, or user says "skip review".

**Completion output MUST name the follow-on**: `Gate 1 (USE-template stream) complete — <N> reviewed (<G> global, <V> variant, <S> skipped). The BUILD stream is a separate verb: run /sync-from-build <target>. Distribution is separate: run /sync-to-use <target>.`

## Delegate

- **Gate 1** → **sync-reviewer** agent

## Examples

- `/sync-from-use py` — review the py-lane USE-template proposal stream (ingest only; then `/sync-to-use py`)
- `/sync-from-use rs` — review the rs-lane USE-template proposal stream
- `/sync-from-use all` — review every lane's USE-template stream
