# Upstream Proposal Protocol

How `/codify` creates proposals for upstream review. Proposals track artifact changes through a three-state lifecycle (`pending_review` → `reviewed` → `distributed`). See `rules/artifact-flow.md` for the full flow rules.

The protocol covers three originating directions, each with its own Step below. `/codify` detects the current repo class (loom / USE-template / BUILD / downstream-skip) and routes to the correct Step per the four-row precedence in `rules/artifact-flow.md` § "Issue Routing By Change Type". Branches are mutually exclusive; the first matching detection signal wins.

## Step 7a: BUILD Repo → loom/ Proposal

**Applies to BUILD repos only** (kailash-py, kailash-rs, kailash-prism). Detect by: git remote contains `kailash-py`, `kailash-rs`, or `kailash-prism`, OR `pyproject.toml`/`Cargo.toml::name` is exactly `kailash` OR matches `^kailash-(dataflow|nexus|kaizen|mcp|pact|ml|align)$` (the canonical kailash sub-package set).

**Scope**: SDK-code-originated proposals. The BUILD repo considers **cross-SDK FIRST** (per `rules/artifact-flow.md` § "Issue Routing By Change Type") before originating; Gate-1 sync-reviewer records/flags the cross-SDK alignment as an advisory note.

**DO NOT sync directly to COC template repos.** All distribution flows through loom/ via `/sync`.

### Proposal lifecycle

1. Create `.claude/.proposals/` directory if needed
2. Read SDK version from `pyproject.toml`/`Cargo.toml` and COC version from `.claude/VERSION`
3. Check for existing proposal at `.claude/.proposals/latest.yaml`:
   - **`pending_review`** → MUST NOT overwrite. **Append** new changes to existing `changes:` array.
   - **`reviewed`** → **Append** and reset status to `pending_review` (new unreviewed changes).
   - **`distributed`** → **Archive** to `.claude/.proposals/archive/{date}-{repo}.yaml`, then create fresh.
   - **Missing** → Create fresh.

**BLOCKED:** Overwriting a `pending_review` or `reviewed` proposal — destroys unprocessed changes.

### Fresh proposal format

```yaml
source_repo: kailash-py # or kailash-rs / kailash-prism
origin: build # explicit class discriminator
codify_date: YYYY-MM-DD
codify_session: "type(scope): description of work"
sdk_version: "2.2.1" # from pyproject.toml or Cargo.toml
coc_version: "1.0.0" # from .claude/VERSION

changes:
  - file: relative/path/to/artifact.md
    action: created | modified
    suggested_tier: cc | co | coc | coc-py | coc-rs
    reason: "Why this artifact was created/changed"
    diff_lines: "+N -N" # for modifications

status: pending_review
```

### Append format

Keep ALL existing fields and `changes:` entries. Add separator comment, append new entries, update dates/versions, reset status if was `reviewed`.

```yaml
# Existing entries preserved above...
# --- YYYY-MM-DD session: type(scope): description ---
  - file: relative/path/to/new-artifact.md
    action: created
    suggested_tier: coc
    reason: "Why this artifact was created"
    diff_lines: "+80"

status: pending_review  # reset if was reviewed
```

### Tier suggestions

- **cc**: Claude Code universal (guides, cc-audit)
- **co**: Methodology universal (CO principles, journal, communication)
- **coc**: Codegen, language-agnostic (workflow phases, analysis patterns)
- **coc-py** / **coc-rs**: Language-specific (code examples, SDK patterns)

### Reporting

**Fresh:** "Artifacts updated locally. Proposal created at `.claude/.proposals/latest.yaml` with {N} changes. Run `/sync {py|rs}` at loom/ to classify and distribute."

**Appended:** "Artifacts updated locally. Appended {N} new changes to existing proposal (now {total} changes, status reset to pending_review). Prior changes preserved."

## Step 7b: USE-Template Repo → loom/ Proposal

**Applies to USE-template repos only** (`kailash-coc-claude-py`, `kailash-coc-claude-rs`, `kailash-coc-claude-rb`, `kailash-coc-py`, `kailash-coc-rs`; canonical enumeration via `sync-manifest.yaml::sync_targets[].templates[].repo` per `rules/sync-completeness.md` MUST-1). Detect by: git remote matches a USE-template slug from that enumeration OR `.claude/VERSION::type == "coc-template"`.

**Scope**: COC-artifact improvements ONLY — method, rules, skills, agents, commands, guides, hooks, COC-tooling. SDK code routing is the BUILD lane (Step 7a); filing SDK code via this lane is BLOCKED — caught mechanically at origination time (see "Mechanical wrong-lane defense" below) and again at Gate-1 review by sync-reviewer Step 5 classification.

### Proposal lifecycle

Identical three-state lifecycle as Step 7a (`pending_review` → `reviewed` → `distributed`). Append-not-overwrite per `rules/artifact-flow.md` § "Proposal Lifecycle" MUST clauses.

### Mechanical wrong-lane defense (MUST)

Before writing the manifest, `/codify` MUST glob-check every candidate change-file path against the disallowed-glob set: `src/**`, `packages/**`, `pyproject.toml`, `Cargo.toml`. Disposition:

- **All change-paths disallowed** → HALT. Print: "wrong-lane — refile against BUILD repo issue queue (kailash-py / kailash-rs / kailash-prism)." Do NOT write the manifest.
- **Mixed (some in-scope, some disallowed)** → skip-with-warning. In-scope entries proceed into the manifest; disallowed entries excluded; warning printed listing the excluded paths.
- **All in-scope** → proceed.

The mechanical check is the first-line defense; sync-reviewer Step 5 classification at Gate-1 is the second-line defense.

### Fresh proposal format

```yaml
source_repo: kailash-coc-claude-py # or kailash-coc-claude-rs / kailash-coc-claude-rb / kailash-coc-py / kailash-coc-rs
origin: use-template # explicit class discriminator
codify_date: YYYY-MM-DD
codify_session: "type(scope): description of work"
template_version: "X.Y.Z" # from .claude/VERSION::upstream.template_version
coc_version: "X.Y.Z" # from .claude/VERSION::upstream.version (canonical per sync-completeness.md Rule 3)

changes:
  - file: .claude/rules/some-rule.md
    action: created | modified
    suggested_tier: cc | co | coc | coc-py | coc-rs
    reason: "Why this artifact was created/changed"
    diff_lines: "+N -N"

status: pending_review
```

**Schema asymmetry vs BUILD (intentional)**: USE-template manifests OMIT `sdk_version` / `sdk_packages` — the originator is artifact-only, not SDK code. BUILD manifests carry `sdk_version` per Step 7a; loom→atelier manifests carry `loom_version` per Step 8. Each originator's pin field reflects the artifact source it authoritatively bumps.

### Append format

Identical to Step 7a (separator comment + new entries + status reset).

### Tier suggestions

USE-template-origin proposals usually suggest `cc` or `coc` tier. The originating template's slug already implies the language axis (`kailash-coc-claude-py` → py) AND, for CC-only legacy templates (`kailash-coc-claude-*`), the CLI axis (cc). Sync-reviewer Step 5 applies these biases as defaults when the `suggested_tier` does not name a specific axis (per spec §4.4 of `workspaces/codify-use-template-origination/`).

### Reporting

**Fresh**: "Artifacts updated locally. Proposal created at `.claude/.proposals/latest.yaml` with {N} changes for USE-template origination. Run `/sync` at loom/ to classify and distribute."

**Appended**: same shape as Step 7a.

## Step 8: loom/ → atelier/ Proposal

**Applies ONLY at loom/.** Detect by: git remote contains `loom`, or `.claude/sync-manifest.yaml` exists.

Check whether updated artifacts are CC or CO tier (domain-agnostic methodology). If none qualify, report "No CC/CO changes to propose upstream."

Apply the **same append-not-overwrite logic** as Step 7a to `.claude/.proposals/latest.yaml`:

```yaml
source_repo: loom
origin: loom # explicit class discriminator
upstream_target: atelier
codify_date: YYYY-MM-DD
codify_session: "type(scope): description"
loom_version: "X.Y.Z"
coc_version: "X.Y.Z"

changes:
  - file: rules/rule-authoring.md
    action: created
    suggested_tier: cc
    canonical_path: .claude/rules/rule-authoring.md
    reason: "..."
    adaptation_notes: "Notes on what atelier needs to adjust"

status: pending_review
```

Report: "{N} CC/CO artifacts proposed for upstream to atelier/. When ready, the atelier maintainer reviews and adapts."

## Back-compat: legacy manifests missing `origin:`

When a manifest predates this protocol revision and lacks the `origin:` field, sync-reviewer at loom Gate-1 infers from `source_repo:`:

- `source_repo == "loom"` → infer `origin: loom`
- `source_repo == "kailash-py"` / `"kailash-rs"` / `"kailash-prism"` → infer `origin: build`
- `source_repo` matches `kailash-coc-*` → infer `origin: use-template`
- otherwise → BLOCK with "unparseable proposal origin"

Regardless of inferred or explicit origin, any manifest with `status: distributed` is skipped on ingest (the lifecycle gate is authoritative — no re-ingest of already-processed manifests). New proposals MUST emit `origin:` explicitly; inference is for archived manifests only.
