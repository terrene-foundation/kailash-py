---
description: "Ingest the BUILD proposal stream at loom (Gate-1 review + scrub + classify); one half of loom's inbound sync"
---

Ingest the **BUILD proposal stream** INBOUND at loom (Gate-1). `/sync-from-build` brings SDK-code-originated proposals (kailash-py / kailash-rs) into loom for classification. Its sibling `/sync-from-use` ingests the USE-template proposal stream; together they are loom's full inbound surface, mirroring the outbound `/sync-to-build` + `/sync-to-use`.

Detailed protocol: `skills/30-claude-code-patterns/sync-flow.md` § Gate 1 (loaded by the sync-reviewer agent).

**Usage**: `/sync-from-build [target]` — `target` = `py`, `rs`, `rb`, `base`, or `all`. If omitted, ask.

## Step 0: Verify Repo Class (this verb is loom-only)

Read `.claude/VERSION` → `type`. `/sync-from-build` is valid ONLY at loom (`type: coc-source`).

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

## Gate 1: Review + Scrub — the BUILD stream

**loom is the central splitter, not an author.** loom does NOT originate artifact changes — it ingests proposals, splits global vs variant at Gate 1, then dual-distributes: `/sync-to-build` pushes canonical back to BUILD repos; `/sync-to-use` distributes to USE templates.

The **BUILD stream** (kailash-py / kailash-rs) carries SDK-code-originated proposals. Gate 1 records/flags whether the proposal considered cross-SDK (advisory alignment note — see step 8; NOT a hard block).

**Disclosure-scrub on intake (MUST, runs first):** before classifying any change, run `node .claude/bin/scan-synced-disclosure.mjs --root <build-repo-path>` against the candidate artifact files AND have a human scrub the `.proposals/latest.yaml` body per `upstream-issue-hygiene.md` Rule 2 (`.proposals/` is `isNeverSynced`, so `--root` won't reach it — the human gate covers the body). Non-zero exit or any finding = HALT until genericized + relocated (#255/#260 pattern). Symmetric with the Gate-2 synced-disclosure preflight in `/sync-to-use`.

**Trigger**: Runs automatically when `/sync-from-build` detects unreviewed BUILD-stream changes. Also runs if the user explicitly says "review" (e.g., `/sync-from-build py review`).

**Process summary** (full protocol in skill § Gate 1):

1. Read `sync-manifest.yaml` for tier membership + variant mappings; `repos.{target}.build` gives the BUILD logical NAME — resolve its on-disk path via `bin/lib/loom-links.mjs::resolveRepo("build.{target}")` (canonical NAME→location binding, `cross-repo.md` MUST-1), never a positional `../{build}` guess.
2. Read SDK version from BUILD repo's `pyproject.toml` (py) / `Cargo.toml` (rs) — report in review header.
3. Compute expected state (loom + variant overlay), diff BUILD repo's `.claude/` against it.
4. Check `.claude/.proposals/latest.yaml` status (`pending_review` / `reviewed` / `distributed`); for `reviewed`, re-review only entries appended after `reviewed_date`.
5. For each NEW or MODIFIED file, classify (sync-reviewer agent: global vs variant vs skip).
6. Place files: global → `.claude/{type}/{file}`, variant → `.claude/variants/{lang}/{type}/{file}`, skip → leave in BUILD only. New-rule discipline applies at placement: every new rule landed at loom MUST also land a corresponding `validate-emit.mjs` check OR a `no-check: <reason>` annotation in the same PR.
7. Mark proposal as reviewed.

**Skip when**: No diff between BUILD and expected state, or user says "skip review".

**Completion output MUST name the follow-on**: `Gate 1 (BUILD stream) complete — <N> reviewed (<G> global, <V> variant, <S> skipped). The USE-template stream is a separate verb: run /sync-from-use <target>. Distribution is separate: run /sync-to-use <target> + /sync-to-build.`

## Delegate

- **Gate 1** → **sync-reviewer** agent

## Examples

- `/sync-from-build py` — review kailash-py's BUILD proposal stream (ingest only; then `/sync-from-use py`, then `/sync-to-use py`)
- `/sync-from-build rs` — review kailash-rs's BUILD proposal stream
- `/sync-from-build all` — review every lane's BUILD stream
