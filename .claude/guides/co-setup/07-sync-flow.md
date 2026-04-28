# Sync Flow — Merge Semantics and Adaptation

How artifacts actually move between repos. This is the operational companion to [06 - Artifact Lifecycle](06-artifact-lifecycle.md) which covers the _when_ and _why_. This guide covers the _how_.

## The Distribution Chain

```
BUILD repo ──/codify──> proposal ──> loom/ ──/sync──> USE template ──> downstream projects
 (kailash-py)          (.proposals/)  (source)   (Gate 2)  (coc-claude-py)   (user projects)
 (kailash-rs)                         of truth              (coc-claude-rs)
```

Every arrow is a **merge**, not a copy. Each step reads, compares, adapts, and writes.

## Step 1: BUILD Repo Creates Artifacts (/codify)

BUILD repos (kailash-py, kailash-rs) are where features, bugs, and issues land first. When `/codify` runs:

1. Artifacts are written to BUILD repo's `.claude/` for immediate local use
2. A proposal manifest is created at `.claude/.proposals/latest.yaml`
3. The BUILD repo does NOT sync anywhere

The proposal includes tier suggestions (cc/co/coc/coc-py/coc-rs) for each changed artifact. These are agent suggestions — the human decides during review.

## Step 2: Review at loom/ (/sync Gate 1)

When the developer runs `/sync py` (or rs) at loom/, Gate 1 activates:

### What it computes

The **expected state** — what the BUILD repo SHOULD have if freshly synced from loom/:

- Start with all global files from loom/.claude/
- Apply the correct variant overlay (py or rs)
- This produces the "expected" BUILD repo content

### What it diffs

Compare BUILD repo's actual `.claude/` against expected state:

- **NEW in BUILD**: artifact created by /codify (or ad-hoc)
- **MODIFIED in BUILD**: artifact changed from what loom/ would produce
- **MATCHING**: BUILD has exactly what loom/ would produce (no action)
- **BUILD-ONLY**: artifact in BUILD that has no source equivalent (preserved)

### Human classification

For each NEW or MODIFIED artifact, the human decides:

| Classification | Placement                                    | Effect                                |
| -------------- | -------------------------------------------- | ------------------------------------- |
| **Global**     | `loom/.claude/{type}/{file}`                 | Synced to ALL targets (py + rs)       |
| **Variant**    | `loom/.claude/variants/{lang}/{type}/{file}` | Synced to ONE target, overlays global |
| **Skip**       | Not upstreamed                               | BUILD repo keeps it locally           |

For global changes, the agent asks: "Does the other SDK need an adaptation?" This catches cross-SDK alignment issues before they propagate.

## Step 3: Distribute to USE Templates (/sync Gate 2)

Gate 2 rebuilds USE template repos from loom/ source. This is NOT a file copy — it is a computed merge:

### Overlay computation

For each syncable file in loom/.claude/:

```
if file is in exclude list → skip
if variants/{lang}/{path} exists → use variant (REPLACES global)
if variants/{lang}/{path} is variant_only → ADD (no global equivalent)
else → use global as-is
```

### Merge semantics (critical)

The sync to USE templates follows these rules:

**Additive**: Files in the template that don't exist in source are PRESERVED. These are template-only artifacts (per-repo learning, local skills, management docs).

**Replace**: Files that exist in both source and template are REPLACED with the source version (after variant overlay). The source is authoritative.

**Never delete**: No file is ever deleted from the template. If an artifact is removed from loom/ source, it becomes template-only in the template until manually cleaned up.

**CLAUDE.md exempt**: The template's CLAUDE.md is NEVER overwritten. Each repo maintains its own identity.

**settings.json verified**: Copied from source, then every hook path is verified to resolve on disk. If a hook path is broken, the sync reports it.

### Adaptation context

USE templates serve downstream projects that DON'T own the SDK source. This means:

- `zero-tolerance.md` Rule 4 says "file a GitHub issue" (not "fix it directly")
- `release.md` describes publishing workflows appropriate to the variant (PyPI vs cargo)
- `testing.md` uses language-appropriate examples and tooling
- BUILD-specific paths (`src/kailash/`, `packages/kailash-dataflow/`) appear in path-scoped rules only (they guide developers working WITH the SDK, even though they don't own it)

These adaptations are handled by the **variant overlay system** — not by runtime transformation. If a file needs different content in BUILD vs USE context, a variant is created.

## Step 4: Downstream Propagation

Downstream projects (user applications built on the SDK) receive artifacts from USE templates:

### How downstream gets updates

1. **Session-start hook** checks `.coc-sync-marker` timestamp
2. If >7 days old, warns: "COC artifacts may be outdated. Run `/sync`."
3. Developer runs `/sync` — the command detects `coc-project` type from `.claude/VERSION`
4. **Template resolver** (`scripts/resolve-template.js`) locates the USE template:
   - Checks local sibling directory (e.g., `../kailash-coc-claude-py/`)
   - Checks cache at `~/.cache/kailash-coc/<template>/`
   - If not found: shallow clones (`git clone --depth 1`) from GitHub to cache
   - GitHub slug comes from `upstream.template_repo` in VERSION, or auto-resolved for known templates
5. Downstream `/sync` diffs template against local, applies additive merge

**No local clone required.** Users who don't have the USE template repo cloned locally get a shallow clone cached automatically. Subsequent `/sync` runs fetch the latest from origin.

### Downstream merge rules

Same additive semantics as template sync:

- Source (USE template) files overwrite matching downstream files
- Downstream-only files are preserved
- CLAUDE.md is never overwritten
- settings.json is verified after copy
- `.claude/VERSION` updated: `upstream.template_version`, `upstream.template_repo`, `upstream.synced_at`

### What downstream NEVER gets

- `sync-manifest.yaml` (loom/-only)
- `variants/` directory (loom/-only, applied during sync)
- Management agents (sync-reviewer, coc-sync, repo-ops, repo-ops, settings-manager)
- Meta files (\_README.md, \_subagent-guide.md)
- Per-repo data (learning/, .proposals/)

## Sync Is Not rsync

The distinction matters:

| rsync behavior            | /sync behavior                            |
| ------------------------- | ----------------------------------------- |
| Copies files              | Computes expected state, then merges      |
| Optionally deletes extras | Never deletes (additive only)             |
| No content awareness      | Applies variant overlays                  |
| No validation             | Verifies hook paths, checks contamination |
| No human gate             | Gate 1 requires human classification      |
| No adaptation             | Variant system adapts content per target  |

The `/sync` command delegates to specialized agents (sync-reviewer for Gate 1, coc-sync for Gate 2) because the merge requires understanding file semantics — not just copying bytes.

## When Conflicts Arise

### Same file changed in both py and rs BUILD repos

Run `/sync py` and `/sync rs` separately. If both propose changes to the same global file, the second review sees the first's changes and the human resolves.

### Global change that needs variant adaptation

The reviewer marks it global AND creates a variant for the SDK that needs adaptation. Both are placed in loom/ — the global and the variant.

### Template has content that source doesn't

Template-only files are preserved. If a template file should be removed, it must be deleted manually (sync never deletes).

### BUILD repo has stale artifacts

`/sync-to-build` pushes latest loom/ content to BUILD repos. After sync, any remaining BUILD-only artifacts are either:

- Legitimate local content (preserved)
- Stale content from before the variant system (cleanup candidate)

## Cross-References

- [05 - Variant Architecture](05-variant-architecture.md) — How overlays work
- [06 - Artifact Lifecycle](06-artifact-lifecycle.md) — When each step happens
- [08 - Versioning](08-versioning.md) — How version tracking triggers updates
- `rules/artifact-flow.md` — Authority chain rules
- `commands/sync.md` — The /sync command spec
- `commands/sync-to-build.md` — The /sync-to-build command spec
