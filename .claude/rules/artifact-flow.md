# Artifact Flow Rules

## Scope

These rules apply to ALL artifact creation, modification, and distribution operations across the Kailash ecosystem.

## MUST Rules

### 1. Authority Chain

Two sources of truth exist, each authoritative for their tier:

- **atelier/** (`~/repos/atelier/`) — CC (Claude Code) and CO (Cognitive Orchestration) authority. Methodology, base rules, base commands, Claude Code guides.
- **loom/** — COC (Codegen) authority. SDK agents, framework specialists, variant system, codegen-specific rules.

CC+CO artifacts flow: `atelier/ → loom/` (via `/sync-to-coc`) → then loom/ distributes to USE templates.
COC artifacts flow: `BUILD repos → loom/` (via proposals) → then loom/ distributes to USE templates.

```
# DO:
atelier/ edits CC/CO → /sync-to-coc → loom/ → /sync → USE templates
BUILD repos /codify → proposal → loom/ → /sync → USE templates

# DO NOT:
loom/ edits CC/CO independently (drifts from atelier/)
BUILD repos sync directly to templates (bypasses loom/)
```

**Why**: CC and CO are domain-agnostic — they serve research, finance, compliance, AND codegen. atelier/ ensures all domains share the same methodology. COC is codegen-specific — loom/ is the authority for SDK patterns.

**How to apply**: For CC/CO changes, edit at atelier/ first. For COC changes, edit at loom/ (via BUILD repo proposals).

### 2. BUILD Repos Write Locally, Propose Upstream

When `/codify` creates or modifies artifacts in a BUILD repo (kailash-py, kailash-rs):

1. Artifacts are written to the BUILD repo's `.claude/` for **immediate local use**
2. A proposal manifest is created at `.claude/.proposals/latest.yaml`
3. The BUILD repo does NOT sync to any other repo

```
# DO:
/codify → writes to kailash-py/.claude/ + creates proposal
/sync py (at loom/) → reviews, classifies, distributes

# DO NOT:
/codify → writes to kailash-py/.claude/ → syncs to kailash-coc-claude-py/
```

**Why**: Direct BUILD-to-template sync bypasses classification (global vs variant) and cross-SDK alignment.

### 2a. Downstream Repos Do NOT Propose Upstream

Downstream project repos (everything except kailash-py, kailash-rs) consume COC artifacts from USE templates. When `/codify` runs in a downstream repo, artifact changes stay **local to that project** — no proposal manifest is created.

```
# Downstream repo /codify:
/codify → writes to project/.claude/ (local only, no proposal)

# NOT this:
/codify → creates .proposals/latest.yaml (wrong — no upstream path exists)
```

**Why**: Downstream repos have no authority over COC artifacts. Their `.claude/` is template-managed. Project-specific artifacts (local rules, learned instincts) are project knowledge, not COC-level insights.

### 3. /sync Is the Only Outbound Path

Only `/sync` executed at `loom/` may write to COC template repos. No other command, agent, or manual process may modify template repo artifacts.

**Why**: The /sync command reads `sync-manifest.yaml` and applies the variant overlay correctly. Manual copies produce inconsistent results.

### 4. Human Classifies Every Inbound Change

When artifact changes from a BUILD repo are reviewed at loom/, a human must classify each change as:

- **Global** → `.claude/{type}/{file}` (synced to all targets)
- **Variant** → `.claude/variants/{lang}/{type}/{file}` (synced to one target)
- **Skip** → not upstreamed (BUILD repo keeps it locally)

Automated classification suggestions are permitted; automated placement is not.

**Why**: Only a human can judge whether a pattern is truly language-universal or language-specific. Agent suggestions inform the decision; they don't make it.

### 5. Cross-SDK Alignment on Global Changes

When a change is classified as **global**, the reviewer must consider whether the other SDK needs adaptation. If yes, an alignment task is created.

**Why**: A global rule change (e.g., updated agent-reasoning patterns) affects both SDKs. The other SDK may need a variant adaptation.

### 6. Variant Overlay Semantics

During `/sync`, variants work as follows:

- **Replacement**: If `variants/{lang}/rules/foo.md` exists and `rules/foo.md` exists, the variant replaces the global
- **Addition**: If `variants/{lang}/skills/01-core-sdk/bar.md` exists with no global equivalent, it is added
- **Global only**: If no variant exists, the global file is used as-is

**Why**: Clear overlay semantics prevent confusion about which version wins.

## MUST NOT Rules

### 1. No Direct Cross-Repo Artifact Sync

MUST NOT sync artifacts directly between BUILD repos (kailash-py ↔ kailash-rs) or between BUILD repos and templates (kailash-py → kailash-coc-claude-py). All paths go through loom/.

### 2. No Template Repo Editing

MUST NOT edit artifacts directly in COC template repos (kailash-coc-claude-py, kailash-coc-claude-rs). Templates are distribution artifacts, rebuilt entirely by `/sync`.

### 3. No Automated Tier Classification

MUST NOT automatically place artifacts into global vs variant without human approval. Agents may suggest; humans decide.

## Cross-References

- `rules/cross-sdk-inspection.md` — Cross-SDK alignment (integrated into /sync review gate)
- `rules/agents.md` — Agent orchestration rules

Note: The variant architecture design docs (`guides/co-setup/05-variant-architecture.md`, `guides/co-setup/06-artifact-lifecycle.md`) and `sync-manifest.yaml` exist at loom/ (source of truth) only — not in downstream repos.
