---
description: "Pull and merge latest COC artifacts from upstream template into this repo"
---

Pull the latest CO/COC artifacts from the upstream template and merge them into this repo, preserving project-specific artifacts.

**Usage**: `/sync`

## Context

This repo inherits its `.claude/` directory from a USE template (`kailash-coc-claude-py`). The template is updated when the loom/ source runs `/sync`. This command pulls those updates into your repo.

```
loom/ (source) → kailash-coc-claude-py/ (USE template) → THIS REPO
                                                              ↑ you are here
```

## Merge Semantics

This is a **merge**, not an overwrite. Three categories of files:

| Category             | Examples                                        | Behavior                      |
| -------------------- | ----------------------------------------------- | ----------------------------- |
| **Shared artifacts** | agents/deep-analyst.md, rules/security.md       | **Updated** from template     |
| **Project-specific** | agents/project/_, skills/project/_, workspaces/ | **Preserved** — never touched |
| **Per-repo data**    | learning/\*, learned-instincts.md, .proposals/  | **Preserved** — never touched |

**Rule**: If a file exists in BOTH the template and this repo, the template version wins (it's the upstream source). If a file exists ONLY in this repo, it's preserved. If a file exists ONLY in the template, it's added.

## Process

### 1. Detect upstream template

Check `.claude/.coc-sync-marker` for the template. If missing, auto-detect:

- `pyproject.toml` has `kailash` dependency → `kailash-coc-claude-py`
- `pyproject.toml` has `kailash-enterprise` → `kailash-coc-claude-rs`

### 2. Locate template

Search paths (in order):

1. `../{template}/` (sibling directory)
2. `../../loom/{template}/` (loom parent)
3. Ask user for path

### 3. Check SDK version compatibility

Read this project's SDK version from `pyproject.toml` (look for `kailash` or `kailash-enterprise` in `[project.dependencies]` or `[tool.poetry.dependencies]`). Read the template's VERSION file for the `build_version` (the loom/ source version the template was synced from).

Report both in the sync header:
```
Project SDK: kailash==2.0.0 (from pyproject.toml)
Template COC: 1.0.0 (from template .claude/VERSION)
```

If the template artifacts were codified from a newer SDK version than the project uses, warn:
```
⚠ Template artifacts may reference SDK features newer than your installed version.
  Consider upgrading: pip install --upgrade kailash
```

This is informational — sync proceeds regardless. The warning helps developers understand why some skill content may reference unfamiliar APIs.

### 4. Compare freshness

Compare `.coc-sync-marker` timestamps. If already fresh: "Already up to date."

### 5. Pull and merge

**Updated from template** (shared artifacts):

- `agents/**/*.md` (except `agents/project/`)
- `commands/*.md`
- `rules/*.md` (except `rules/learned-instincts.md`)
- `skills/**/*` (except `skills/project/`)
- `guides/**/*`

**Added from template** (new files not yet in this repo):

- Any file in the template not present locally

**Preserved** (never modified by sync):

- `agents/project/**` — project-specific agents
- `skills/project/**` — project-specific skills
- `learning/**` — per-repo learning data
- `rules/learned-instincts.md` — auto-generated
- `.proposals/**` — review artifacts
- `settings.local.json` — per-repo settings
- `workspaces/**` — project workspaces
- `CLAUDE.md` (at repo root) — project-specific directives
- Any file/directory not present in the template

**Scripts** (updated from template):

- `scripts/hooks/*.js` — updated
- `scripts/hooks/lib/*.js` — updated

### 6. Verify integrity

- Every hook in `settings.json` has a corresponding script
- Every `require("./lib/...")` has a matching lib file

### 7. Update tracking

- Write `.claude/.coc-sync-marker` with timestamp and template source
- If `.claude/VERSION` exists, update `upstream.version` to match the template's VERSION version (so future session-start checks report correctly)

### 8. Report

```
## Sync Complete: kailash-coc-claude-py → this repo

Updated: {N} shared artifacts
Added: {N} new artifacts from template
Preserved: {N} project-specific files untouched
Scripts: {N} hooks updated

Your artifacts are current with the template.
```

## Pushing Changes Upstream

If you created knowledge worth sharing (via `/codify`):

1. `/codify` creates `.claude/.proposals/latest.yaml`
2. Open loom/ and run `/sync py`
3. Human classifies each change (global vs variant)
4. `/sync` distributes to USE templates
5. Other projects pull via their `/sync`

**Never** edit the template directly. All changes flow through loom/.

## When to Run

- Session-start reports "COC artifacts are stale"
- After upstream releases new patterns
- Before starting a new feature (ensure latest)
