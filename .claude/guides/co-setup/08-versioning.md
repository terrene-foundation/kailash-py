# Versioning — Tracking Artifact Currency Across the Chain

How repos know whether their COC artifacts are current, and how updates propagate.

## The Version Chain

```
loom/.claude/VERSION          ← Source of truth (BUILD COC version)
       │
       ├── kailash-coc-claude-py/.claude/VERSION   (upstream.build_version)
       │          │
       │          └── downstream-project/.claude/VERSION   (upstream.template_version)
       │
       └── kailash-coc-claude-rs/.claude/VERSION   (upstream.build_version)
                  │
                  └── downstream-project/.claude/VERSION   (upstream.template_version)
```

Each repo in the chain tracks the version of its upstream. The session-start hook compares versions and prompts for updates.

## VERSION File Format

Every repo with COC artifacts MUST have `.claude/VERSION`:

### Source (loom/)

```json
{
  "version": "1.1.0",
  "type": "coc-source",
  "updated": "2026-03-29",
  "description": "Kailash COC artifact source of truth"
}
```

The source version is bumped by the human after `/sync` distributes changes.

### USE Template (coc-claude-py, coc-claude-rs)

```json
{
  "version": "1.1.0",
  "type": "coc-use-template",
  "variant": "py",
  "updated": "2026-03-29",
  "description": "COC USE template for Python SDK projects",
  "upstream": {
    "source": "kailash",
    "build_version": "1.1.0",
    "synced_at": "2026-03-29T14:30:00Z"
  }
}
```

`upstream.build_version` tracks which loom/ version this template was last synced from.

### BUILD Repo (kailash-py, kailash-rs)

```json
{
  "version": "1.1.0",
  "type": "coc-build",
  "variant": "py",
  "updated": "2026-03-29",
  "description": "Kailash Python SDK BUILD repo",
  "upstream": {
    "source": "kailash",
    "build_version": "1.1.0",
    "synced_at": "2026-03-29T14:30:00Z"
  }
}
```

BUILD repos track the same `upstream.build_version` as templates — they receive from the same source.

### Downstream Project

```json
{
  "version": "1.0.0",
  "type": "coc-project",
  "variant": "py",
  "updated": "2026-03-15",
  "description": "My application built on Kailash SDK",
  "upstream": {
    "template": "kailash-coc-claude-py",
    "template_version": "1.0.0",
    "synced_at": "2026-03-15T10:00:00Z"
  }
}
```

Downstream projects track the USE template version, not the source directly.

## Version Checking (session-start hook)

The `session-start.js` hook checks version currency on every session:

### For BUILD repos

1. Read local `.claude/VERSION` → get `upstream.build_version`
2. Read `loom/.claude/VERSION` → get current source `version`
3. If local < source → warn: "COC artifacts are outdated (local: 1.0.0, source: 1.1.0). Run `/sync-to-build` at loom/ to update."

### For USE templates

Same check as BUILD repos — compare `upstream.build_version` against loom/ source version.

### For downstream projects

1. Read local `.claude/VERSION` → get `upstream.template_version`
2. Read the USE template's `.claude/VERSION` (via git or local path) → get template `version`
3. If local < template → warn: "COC artifacts are outdated (local: 1.0.0, template: 1.1.0). Run `/sync` to pull latest from template."

### If VERSION file doesn't exist

Many downstream projects already exist without VERSION files. The hook handles this gracefully:

1. If `.claude/` exists but no `.claude/VERSION` → create one automatically:
   - Set `type` to `"coc-project"` (assume downstream project)
   - Set `version` to `"0.0.0"` (unknown — will be updated on next sync)
   - Set `upstream.template_version` to `"0.0.0"`
   - Warn: "Created initial VERSION file. Run `/sync` to pull latest template artifacts."
2. If `.claude/` doesn't exist → no COC setup, skip version check

This ensures existing repos get version tracking on their next session without manual intervention.

## When Versions Bump

### Source version (loom/)

Bumped AFTER `/sync` distributes changes. The human decides the bump level:

| Change type                                                         | Bump          | Example       |
| ------------------------------------------------------------------- | ------------- | ------------- |
| New agents, skills, guides added                                    | Minor (x.Y.0) | 1.0.0 → 1.1.0 |
| Breaking changes (renamed/removed artifacts, changed hook behavior) | Major (X.0.0) | 1.1.0 → 2.0.0 |
| Fixes, wording updates, description tweaks                          | Patch (x.y.Z) | 1.1.0 → 1.1.1 |

The `/sync` command prompts for version bump after Gate 2 completes:

```
Gate 2 complete. 12 files updated, 2 added.
Current source version: 1.0.0
Bump to: [1.0.1] patch  [1.1.0] minor  [2.0.0] major  [S]kip?
```

### USE template version

Set automatically by `/sync` Gate 2:

- `version` matches the source version it was synced from
- `upstream.build_version` set to source version
- `upstream.synced_at` set to current timestamp

### BUILD repo version

Set automatically by `/sync-to-build`:

- Same logic as USE template — tracks source version

### Downstream project version

Set automatically by downstream `/sync`:

- `upstream.template_version` set to template version
- `upstream.synced_at` set to current timestamp

## The Update Flow

```
Human bumps loom/ VERSION to 1.1.0
    │
    ├── /sync py → coc-claude-py VERSION: upstream.build_version = 1.1.0
    │                    │
    │         developer opens downstream project
    │         session-start: "template 1.1.0 > local 1.0.0, run /sync"
    │         /sync → project VERSION: upstream.template_version = 1.1.0
    │
    ├── /sync-to-build py → kailash-py VERSION: upstream.build_version = 1.1.0
    │
    └── (same for rs)
```

## Bootstrap: Existing Repos Without VERSION

For repos that already have `.claude/` but no VERSION file:

1. **session-start.js** auto-creates VERSION with `version: "0.0.0"` on next session
2. **Next `/sync` run** (at any level) updates the VERSION to track its upstream
3. After one sync cycle, the repo is fully version-tracked

No manual intervention required. The version chain self-heals on first contact.

## What VERSION Is NOT

- NOT a code version (that's `pyproject.toml` / `Cargo.toml`)
- NOT a release version (that's the SDK publish version)
- NOT tracked in git history for semantic purposes (it's operational metadata)

VERSION tracks **COC artifact currency** — whether your agents, skills, rules, and hooks are up to date with the source.

## Cross-References

- [07 - Sync Flow](07-sync-flow.md) — How artifacts actually move
- [06 - Artifact Lifecycle](06-artifact-lifecycle.md) — When each step happens
- `commands/sync.md` — /sync command (updates VERSION in Gate 2)
- `commands/sync-to-build.md` — /sync-to-build command (updates VERSION)
- `scripts/hooks/session-start.js` — Version check implementation
