# Artifact Flow Rules

## Scope

These rules apply to ALL artifact creation, modification, and distribution operations across the Kailash ecosystem.

## MUST Rules

### 1. Authority Chain

Two sources of truth exist, each authoritative for their tier:

- **co/** (`~/repos/co/`) — CC (Claude Code) and CO (Cognitive Orchestration) authority. Methodology, base rules, base commands, Claude Code guides.
- **kailash/** — COC (Codegen) authority. SDK agents, framework specialists, variant system, codegen-specific rules.

CC+CO artifacts flow: `co/ → kailash/` (via `/sync-to-coc`) → then kailash/ distributes to USE templates.
COC artifacts flow: `BUILD repos → kailash/` (via proposals) → then kailash/ distributes to USE templates.

```
# DO:
co/ edits CC/CO → /sync-to-coc → kailash/ → /sync → USE templates
BUILD repos /codify → proposal → kailash/ → /sync → USE templates

# DO NOT:
kailash/ edits CC/CO independently (drifts from co/)
BUILD repos sync directly to templates (bypasses kailash/)
```

**Why**: CC and CO are domain-agnostic — they serve research, finance, compliance, AND codegen. co/ ensures all domains share the same methodology. COC is codegen-specific — kailash/ is the authority for SDK patterns.

**How to apply**: For CC/CO changes, edit at co/ first. For COC changes, edit at kailash/ (via BUILD repo proposals).

### 2. BUILD Repos Write Locally, Propose Upstream

When `/codify` creates or modifies artifacts in a BUILD repo (kailash-py, kailash-rs):

1. Artifacts are written to the BUILD repo's `.claude/` for **immediate local use**
2. A proposal manifest is created at `.claude/.proposals/latest.yaml`
3. The BUILD repo does NOT sync to any other repo

```
# DO:
/codify → writes to kailash-py/.claude/ + creates proposal
/sync py (at kailash/) → reviews, classifies, distributes

# DO NOT:
/codify → writes to kailash-py/.claude/ → syncs to kailash-coc-claude-py/
```

**Why**: Direct BUILD-to-template sync bypasses classification (global vs variant) and cross-SDK alignment.

### 3. /sync Is the Only Outbound Path

Only `/sync` executed at `kailash/` may write to COC template repos. No other command, agent, or manual process may modify template repo artifacts.

**Why**: The /sync command reads `sync-manifest.yaml` and applies the variant overlay correctly. Manual copies produce inconsistent results.

### 4. Human Classifies Every Inbound Change

When artifact changes from a BUILD repo are reviewed at kailash/, a human must classify each change as:

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

MUST NOT sync artifacts directly between BUILD repos (kailash-py ↔ kailash-rs) or between BUILD repos and templates (kailash-py → kailash-coc-claude-py). All paths go through kailash/.

### 2. No Template Repo Editing

MUST NOT edit artifacts directly in COC template repos (kailash-coc-claude-py, kailash-coc-claude-rs). Templates are distribution artifacts, rebuilt entirely by `/sync`.

### 3. No Automated Tier Classification

MUST NOT automatically place artifacts into global vs variant without human approval. Agents may suggest; humans decide.

## Cross-References

- `rules/cross-sdk-inspection.md` — Cross-SDK alignment (integrated into /sync review gate)
- `rules/agents.md` — Agent orchestration rules

Note: The variant architecture design docs (`guides/co-setup/05-variant-architecture.md`, `guides/co-setup/06-artifact-lifecycle.md`) and `sync-manifest.yaml` exist at kailash/ (source of truth) only — not in downstream repos.
