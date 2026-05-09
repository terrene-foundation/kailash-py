---
description: "Upgrade Claude-Code-only USE-template project to multi-CLI (Claude+Codex+Gemini). Modes: detect, --dry-run, --refresh, --rollback. Preserves project artifacts."
---

Migrate a project from `kailash-coc-claude-{py,rs,rb}` (CC-only) to `kailash-coc-{py,rs}` (multi-CLI), or refresh multi-CLI overlays on a project already migrated. Project source, workspaces, journals, briefs, todos, `.session-notes`, `.env`, and SDK pins are preserved.

Detailed protocol: `skills/30-claude-code-patterns/multi-cli-migration.md`. Manifest source-of-truth: `.claude/sync-manifest.yaml::multi_cli_overlays:`.

## Modes

| Invocation            | Behavior                                                                                |
| --------------------- | --------------------------------------------------------------------------------------- |
| `/migrate`            | Detect lineage from `.claude/.coc-sync-marker`, run full 12-step migration.             |
| `/migrate --dry-run`  | Detect + print every step's planned actions; apply nothing.                             |
| `/migrate --refresh`  | Multi-CLI consumer ONLY: re-pull top-level overlays per `multi_cli_overlays.paths`.     |
| `/migrate --rollback` | Inline porcelain guard, then `git reset --keep main` + restore from `.pre-migrate.bak`. |

## Step 0 — Pre-flight

1. Read `.claude/.coc-sync-marker`. Branch by `template_type`:
   - `cc-only-legacy` → full migration. Variant from `variant:` (`py`/`rs`/`rb`).
   - `multi-cli` → only `--refresh` is valid; `/migrate` exits "already migrated".
   - Missing/unrecognized → exit "not a recognized USE-template lineage".
2. Resolve sister template (full migration only):
   - py → `kailash-coc-py`, rs → `kailash-coc-rs`, rb → no multi-CLI sister exists.
   - **rb path**: do NOT migrate. Run `gh issue create --title "Multi-CLI sister template for kailash-coc-claude-rb" --body "Project at <repo> requests a multi-CLI Ruby USE template (Codex + Gemini parity)."` and exit.
3. Verify clean working tree inline: `[ -z "$(git status --porcelain)" ] || { echo "stash or commit first; recommend: git stash push -u -m pre-migrate"; exit 1; }`. Recommendation per `recommendation-quality.md` MUST-1 — stash beats commit because the migration commit will be atomic and stash restores cleanly post-merge.
4. Resolve sister template path via `node .claude/bin/resolve-template.js --template kailash-coc-<variant>` (else env `KAILASH_COC_TEMPLATE_PATH` → `~/.cache/kailash-coc/<sister>/` → offline-fallback). Same logic as `/sync` Downstream Sync step 1.
5. Branch-name collision: if `chore/coc-multi-cli-migrate-<YYYYMMDD>` exists locally, append `-<HHMMSS>` for same-day idempotency. Format: `chore/coc-multi-cli-migrate-<YYYYMMDD>-<HHMMSS>`.

## Step 1 — Branch + snapshot

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
BRANCH="chore/coc-multi-cli-migrate-${TS}"
git checkout -b "$BRANCH"
mkdir -p .pre-migrate.bak
cp .claude/.coc-sync-marker .pre-migrate.bak/.coc-sync-marker
[ -f CLAUDE.md ] && cp CLAUDE.md .pre-migrate.bak/CLAUDE.md
[ -f .claude/VERSION ] && cp .claude/VERSION .pre-migrate.bak/VERSION
echo "$BRANCH" > .pre-migrate.bak/.branch
```

## Step 2 — VERSION update FIRST

Update `.claude/VERSION` `upstream.template` → `kailash-coc-<variant>`, `upstream.template_repo` → `terrene-foundation/kailash-coc-<variant>`. This MUST precede Step 4 so the resolver targets the new template on subsequent calls.

## Step 3 — Top-level multi-CLI overlay copy

Per manifest `multi_cli_overlays.multi-cli.paths`. Cleanup stranded root `.coc-sync-marker` (legacy artifact at repo root from pre-v2.21 templates):

```bash
cp -R "$SISTER/.codex"           ./.codex
cp -R "$SISTER/.codex-mcp-guard" ./.codex-mcp-guard
cp -R "$SISTER/.gemini"          ./.gemini
cp    "$SISTER/AGENTS.md"        ./AGENTS.md
cp    "$SISTER/GEMINI.md"        ./GEMINI.md
[ -f .coc-sync-marker ] && rm .coc-sync-marker  # legacy root sentinel
```

## Step 4 — `.claude/` refresh

Run downstream-sync semantics against the sister (`skills/30-claude-code-patterns/sync-flow.md` § Downstream Sync). Diffs sister `.claude/` against project `.claude/`; overwrites template-owned files; preserves `.claude/settings.local.json`, `.claude/.proposals/`, `.claude/learning/`. Purges paths in sister's `.claude/.coc-obsoleted`. Picks up new binaries (`emit.mjs`, `emit-cli-artifacts.mjs`).

## Step 5 — CLAUDE.md 3-way reconciliation

Diff project `CLAUDE.md` against the CC-only template's `CLAUDE.md`. Three branches:

1. **Empty diff** (no local edits) → replace with multi-CLI sister's `CLAUDE.md`.
2. **Diff matches sister directly** (already multi-CLI-style) → keep as-is.
3. **Local edits present** → emit a 3-way merge plan (`base` = CC-only original, `theirs` = multi-CLI sister, `ours` = project) AND **recommend** the auto-merge if conflicts are non-overlapping; **recommend** human review if any load-bearing section conflicts. Per `recommendation-quality.md` MUST-1, never present an unannotated menu.

## Step 6 — Regenerate per-CLI emissions

Closes the variant-overlay-drift gap (Loom-A). Sister-installed binaries at `.claude/bin/` from Step 4:

```bash
node .claude/bin/emit-cli-artifacts.mjs --target <variant> --out .   # variant-aware per-CLI artifacts
node .claude/bin/emit.mjs --cli codex   # AGENTS.md baseline from project's .claude/rules/
node .claude/bin/emit.mjs --cli gemini  # GEMINI.md baseline from project's .claude/rules/
```

If `.codex-mcp-guard/policies.json` is missing or empty, `node .codex-mcp-guard/extract-policies.mjs` populates it from `.claude/hooks/`.

## Step 7 — Refresh `.github/`

Copy/refresh `.github/workflows/auto-merge.yml`, `.github/workflows/validate.yml`, and `.github/coc-sdk-refs-allowlist.txt` from the sister (multi-CLI templates carry the multi-CLI-aware schema). Preserve project-only workflows untouched.

## Step 8 — Update sync marker (full schema)

Write `.claude/.coc-sync-marker` per the canonical multi-CLI shape (`template`, `template_type: multi-cli`, `template_version`, `clis: [claude, codex, gemini]`, `variant`, `migrated_from`, `migrated_at`, `loom_version`, `loom_sha`, `stats.baselines_emitted.{cc,codex,gemini}`, `stats.cli_artifacts.{codex,gemini}`, `stats.mcp_guard.policies_populated`). Schema reference: `skills/30-claude-code-patterns/multi-cli-migration.md` § Marker Schema.

## Step 9 — Project-artifact lint

`node tools/lint-workspaces.js workspaces/ .session-notes 2>/dev/null || true` (advisory). Surfaces CC-native syntax leaks per `rules/cross-cli-artifact-hygiene.md`. Tool ships in the sister template; if absent, fall back to inline regex from `workspaces/multi-cli-coc/fixtures/slot-markers/emitter.mjs:279-301`.

## Step 10 — Verify cross-CLI surfaces

Emit the 15+ check verification table from `skills/30-claude-code-patterns/multi-cli-migration.md` § Verification Table. Any ✗ row halts; user adjudicates fix-in-place vs `/migrate --rollback`. Per `sync-completeness.md` Rule 2, single-row "✓ migrated" claims are BLOCKED.

## Step 11 — Trust-posture caveat banner

Emit: "Trust posture is per-CLI. `posture show` works on Claude Code today; Codex/Gemini posture surfaces are session-local until cross-CLI posture sync ships. See `rules/trust-posture.md` MUST Rule 1."

## Step 12 — Commit + PR

Stage explicit paths (per `coc-sync-landing.md` Rule 2 — `git add -A` BLOCKED):

```bash
git add .claude/ .codex/ .codex-mcp-guard/ .gemini/ AGENTS.md GEMINI.md CLAUDE.md \
        .github/workflows/auto-merge.yml .github/workflows/validate.yml \
        .github/coc-sdk-refs-allowlist.txt
git commit -F /tmp/migrate-msg.txt
gh pr create --title "chore(coc): migrate to multi-CLI" --body-file /tmp/migrate-pr-body.md
```

Commit body MUST cite source template, target template, files added, files replaced, verification-table summary, link to `skills/30-claude-code-patterns/multi-cli-migration.md`. PR body MUST embed Step 10 verification table.

## `--refresh` (multi-CLI consumer re-pull)

Detected when `template_type: multi-cli`. Skips Steps 0.2 sister-resolution mismatch, Step 5 (CLAUDE.md owned-by-project), Step 7 GitHub workflow refresh (already aligned), Step 8 marker rewrite (only timestamp + stats update). Runs Step 3 per `multi_cli_overlays.multi-cli.paths`, respecting `multi_cli_overlays.multi-cli.preserved` (`.codex/local-config.toml`, `.gemini/local-settings.json`). Step 6 regenerates emissions. Commit: `chore(coc): refresh multi-CLI overlays`.

## `--rollback`

Inline porcelain guard (do NOT cite `rules/git.md` only — verify here):

```bash
[ -z "$(git status --porcelain)" ] || { echo "uncommitted work — recommend: git stash push -u -m pre-rollback; abort"; exit 1; }
git reset --keep main      # --keep aborts on local changes; --hard would silently discard
[ -d .pre-migrate.bak ] && {
  [ -f .pre-migrate.bak/.coc-sync-marker ] && cp .pre-migrate.bak/.coc-sync-marker .claude/.coc-sync-marker
  [ -f .pre-migrate.bak/CLAUDE.md ]        && cp .pre-migrate.bak/CLAUDE.md        ./CLAUDE.md
  [ -f .pre-migrate.bak/VERSION ]          && cp .pre-migrate.bak/VERSION          .claude/VERSION
}
BRANCH=$(cat .pre-migrate.bak/.branch 2>/dev/null)
git checkout main && [ -n "$BRANCH" ] && git branch -D "$BRANCH"
```

`--keep` is the recommendation over `--hard` per `rules/git.md` § "git reset --hard MUST verify clean working tree" — `--keep` aborts loudly when working tree has changes; `--hard` would silently wipe them.

## Hook env-var portability + `.pre-migrate.bak` lifecycle

Hooks MUST handle three env vars (`$CLAUDE_PROJECT_DIR`/`$CODEX_PROJECT_DIR`/`$GEMINI_PROJECT_DIR`); pattern: `PROJECT_DIR="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${GEMINI_PROJECT_DIR:-$PWD}}}"`. Sister-template hooks already conformant. `.pre-migrate.bak/` is preserved one cycle for inspection; recommend `rm -rf .pre-migrate.bak` after user verifies.

## When NOT to run

- `template_type: multi-cli` AND no `--refresh` flag → "already migrated; use `--refresh` to re-pull overlays".
- `variant: rb` (no multi-CLI rb sister exists) → file tracking issue (Step 0.2).
- Uncommitted work → stash first (Step 0.3 recommendation).
