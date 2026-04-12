# Upstream Proposal Protocol

How `/codify` creates proposals for upstream review. Proposals track artifact changes through a three-state lifecycle (`pending_review` → `reviewed` → `distributed`). See `rules/artifact-flow.md` for the full flow rules.

## Step 7: BUILD Repo → loom/ Proposal

**Applies to BUILD repos only** (kailash-py, kailash-rs). Detect by: git remote contains `kailash-py` or `kailash-rs`, OR `pyproject.toml`/`Cargo.toml` contains `name = "kailash"`.

**Downstream project repos**: SKIP. Artifact changes stay local. Report: "Artifacts updated locally. This is a downstream project repo — changes stay local."

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
source_repo: kailash-py # or kailash-rs
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

## Step 8: loom/ → atelier/ Proposal

**Applies ONLY at loom/.** Detect by: git remote contains `loom`, or `.claude/sync-manifest.yaml` exists.

Check whether updated artifacts are CC or CO tier (domain-agnostic methodology). If none qualify, report "No CC/CO changes to propose upstream."

Apply the **same append-not-overwrite logic** as Step 7 to `.claude/.proposals/latest.yaml`:

```yaml
source_repo: loom
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
