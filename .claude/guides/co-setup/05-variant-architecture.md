# Variant Architecture — Single Source with Language Overlays

## Problem

loom/ is the canonical source of CO/COC artifacts, but has no mechanism to distinguish:

- **Global** artifacts (same everywhere) from
- **Language-specific** artifacts (Python patterns vs Rust patterns)

Result: 85% of artifacts have drifted across py and rs templates, with no way to tell which drift is intentional (language-specific) vs accidental (sync failure).

Additionally, ~/repos/.claude/ holds management artifacts (sync agent, commands) that should live in loom/ as the single source of truth.

## Architecture

### Tier Model

All artifacts belong to exactly one tier:

| Tier       | Scope                                           | Example                                    | Sync behavior                |
| ---------- | ----------------------------------------------- | ------------------------------------------ | ---------------------------- |
| **CC**     | Claude Code — universal                         | guides/claude-code/, cc-audit command      | Sync to ALL repos            |
| **CO**     | Cognitive Orchestration — universal methodology | `co-reference` skill agent, journal rules  | Sync to ALL CO-managed repos |
| **COC**    | Codegen — language-agnostic                     | analyze command, analyst agent             | Sync to ALL COC repos        |
| **COC-py** | Python SDK-specific                             | Python async patterns, DataFlow enterprise | Sync to PY targets only      |
| **COC-rs** | Rust SDK-specific                               | Rust benchmarks, Ruby examples             | Sync to RS targets only      |

**Key principle**: CC, CO, and COC artifacts are NEVER language-specific. If a file needs language-specific content, the global version contains the shared concepts and the variant contains the language-specific implementation.

### Directory Structure

```
loom/.claude/
  agents/              # Global agents (CC + CO + COC)
  commands/            # Global commands (CC + CO + COC)
  rules/               # Global rules (CC + CO + COC)
  skills/              # Global skills (CC + CO + COC)
  guides/              # Global guides (CC + CO)

  variants/
    py/
      agents/          # Python-specific agents (additions or replacements)
      commands/        # Python-specific commands (additions or replacements)
      rules/           # Python-specific rules (additions or replacements)
      skills/          # Python-specific skills (additions or replacements)
    rs/
      agents/          # Rust-specific agents (additions or replacements)
      commands/        # Rust-specific commands (additions or replacements)
      rules/           # Rust-specific rules (additions or replacements)
      skills/          # Rust-specific skills (additions or replacements)

  sync-manifest.yaml   # Declares tier membership and variant mappings
```

### Sync Logic

When syncing to a **py** target:

1. Copy ALL global files (agents/, commands/, rules/, skills/, guides/)
2. Apply `variants/py/` as overlay:
   - If a file exists in BOTH global and variant → **variant wins** (replacement)
   - If a file exists ONLY in variant → **added** (language-specific addition)
   - If a file exists ONLY in global → **copied as-is** (shared)
3. Copy scripts (hooks follow same overlay logic)
4. Exclude: learning/, .env, .git

When syncing to an **rs** target: same logic with `variants/rs/`.

### What Goes Where

#### Global (agents/, commands/, rules/, skills/)

Files that are conceptually the same regardless of language:

- Agent definitions with the same role (analyst, security-reviewer)
- Rules about methodology (zero-tolerance, journal, communication)
- Commands about workflow phases (analyze, todos, implement)
- Skills about concepts (architecture decisions, design principles, CARE/EATP/CO references)

#### Variants (variants/py/, variants/rs/)

Files that MUST differ because of implementation language:

**Replacements** (same filename as global, different content):

- `rules/patterns.md` — Python SDK patterns vs Rust SDK patterns
- `commands/sdk.md` — Python code examples vs Python+Ruby code examples
- `commands/ai.md` — Python Kaizen examples vs Rust Kaizen examples
- `skills/01-core-sdk/SKILL.md` — Python-specific trigger phrases vs Rust-specific

**Additions** (files that only exist for one language):

- `variants/py/skills/01-core-sdk/async-pythoncode-patterns.md` — Python async patterns
- `variants/py/skills/04-kaizen/kaizen-l3-*.md` — Python-only Kaizen L3 autonomy
- `variants/rs/skills/01-core-sdk/run-benchmarks.md` — Rust-specific benchmarking
- `variants/rs/agents/frameworks/trust-plane-specialist.md` — Rust-specific agent
- `variants/py/rules/infrastructure-sql.md` — Full Python infrastructure SQL rules (RS gets gutted version in global)

## Controlled Flow

### Outbound: loom/ → BUILD repos

```
loom/  ──/sync py──→  kailash-coc-claude-py/  ──/sync──→  target project repos
loom/  ──/sync rs──→  kailash-coc-claude-rs/  ──/sync──→  target project repos
```

The `/sync` command reads `sync-manifest.yaml`, applies the correct variant overlay, and produces the target artifacts.

### Inbound: BUILD repo → loom/ (proposal flow)

```
BUILD repo (py or rs)
  ↓
  Developer creates/modifies artifact in BUILD repo
  ↓
  /codify step 7 creates .claude/.proposals/latest.yaml
  ↓
  PROPOSAL contains:
    - Which files changed
    - Suggested tier (global vs language-specific)
    - Reason for each change
  ↓
  loom/ receives proposal (PR, diff file, or interactive review)
  ↓
  HUMAN reviews at loom/:
    1. Is this global or language-specific?
    2. Does the other SDK need an equivalent?
    3. Does this conflict with existing artifacts?
  ↓
  HUMAN approves placement:
    - Global → merged into main artifacts
    - Language-specific → merged into variants/py/ or variants/rs/
    - Needs alignment → cross-SDK task created for other language
  ↓
  /sync out to update both COC template repos
```

### Control Gates

| Gate                    | Who            | When                                      |
| ----------------------- | -------------- | ----------------------------------------- |
| **Proposal review**     | Human at loom/ | When BUILD repo proposes upstream changes |
| **Tier classification** | Human at loom/ | Deciding if artifact is global or variant |
| **Cross-SDK alignment** | Human at loom/ | Deciding if other SDK needs equivalent    |
| **Sync authorization**  | Human at loom/ | Before pushing changes to COC templates   |

### Never Allowed

- BUILD repo directly modifying another BUILD repo's artifacts
- py COC directly syncing to rs COC (or vice versa)
- Any sync that bypasses loom/ as the source of truth
- Automated tier classification without human review

## sync-manifest.yaml

The manifest declares every artifact's tier and variant status:

```yaml
# Tier membership for each file/pattern
# Files not listed default to COC (codegen, language-agnostic)

tiers:
  cc:
    - guides/claude-code/**
    - agents/claude-code-architect.md
    - skills/30-claude-code-patterns/**
    - rules/cc-artifacts.md
    - commands/cc-audit.md

  co:
    - agents/standards/`co-reference` skill.md
    - agents/standards/`co-reference` skill.md
    - agents/standards/`co-reference` skill.md
    - skills/co-reference/**
    - skills/26-eatp-reference/**
    - skills/co-reference/**
    - skills/29-pact/**
    - guides/co-setup/**
    - guides/model-optimization/**
    - rules/autonomous-execution.md
    - rules/communication.md
    - rules/journal.md
    - rules/zero-tolerance.md
    - rules/terrene-naming.md
    - rules/independence.md
    - rules/git.md
    - rules/git.md
    - rules/security.md
    - rules/agents.md
    - rules/zero-tolerance.md
    - commands/learn.md
    - commands/journal.md
    - commands/ws.md
    - commands/wrapup.md
    - commands/start.md

  # Everything not listed in cc or co defaults to coc (language-agnostic codegen)

# Variant declarations
# Format: path → { py: variant-path, rs: variant-path }
# If a file has a variant, the variant REPLACES the global during sync

variants:
  # Rules with language-specific content
  rules/patterns.md:
    py: variants/py/rules/patterns.md
    rs: variants/rs/rules/patterns.md
  rules/agent-reasoning.md:
    py: variants/py/rules/agent-reasoning.md
    rs: variants/rs/rules/agent-reasoning.md
  rules/deployment.md:
    py: variants/py/rules/deployment.md
    rs: variants/rs/rules/deployment.md
  rules/eatp.md:
    py: variants/py/rules/eatp.md
    rs: variants/rs/rules/eatp.md
  rules/infrastructure-sql.md:
    py: variants/py/rules/infrastructure-sql.md
    rs: variants/rs/rules/infrastructure-sql.md
  rules/pact-governance.md:
    py: variants/py/rules/pact-governance.md
    rs: variants/rs/rules/pact-governance.md
  rules/trust-plane-security.md:
    py: variants/py/rules/trust-plane-security.md
    rs: variants/rs/rules/trust-plane-security.md
  rules/connection-pool.md:
    py: variants/py/rules/connection-pool.md
    rs: variants/rs/rules/connection-pool.md
  rules/dataflow-pool.md:
    py: variants/py/rules/dataflow-pool.md
    rs: variants/rs/rules/dataflow-pool.md
  rules/testing.md:
    py: variants/py/rules/testing.md
    rs: variants/rs/rules/testing.md
  rules/e2e-god-mode.md:
    py: variants/py/rules/e2e-god-mode.md
    rs: variants/rs/rules/e2e-god-mode.md

  # Commands with language-specific examples
  commands/sdk.md:
    py: variants/py/commands/sdk.md
    rs: variants/rs/commands/sdk.md
  commands/db.md:
    py: variants/py/commands/db.md
    rs: variants/rs/commands/db.md
  commands/ai.md:
    py: variants/py/commands/ai.md
    rs: variants/rs/commands/ai.md
  commands/api.md:
    py: variants/py/commands/api.md
    rs: variants/rs/commands/api.md
  commands/test.md:
    py: variants/py/commands/test.md
    rs: variants/rs/commands/test.md
  commands/release.md:
    py: variants/py/commands/release.md
    rs: variants/rs/commands/release.md

  # Agents with language-specific content
  agents/frameworks/infrastructure-specialist.md:
    py: variants/py/agents/frameworks/infrastructure-specialist.md
    # rs: no infrastructure-specialist (uses trust-plane-specialist instead)

# Variant-only files (exist ONLY for one language, no global equivalent)
variant_only:
  py:
    - variants/py/agents/frameworks/infrastructure-specialist.md
    - variants/py/scripts/hooks/detect-package-manager.js
    - variants/py/scripts/hooks/validate-prod-deploy.js
    - variants/py/scripts/deployment/**
    - variants/py/scripts/development/**
    - variants/py/scripts/maintenance/**
    - variants/py/scripts/metrics/**
    # Python-specific skills (no global equivalent)
    - variants/py/skills/01-core-sdk/async-pythoncode-patterns.md
    - variants/py/skills/01-core-sdk/otel-tracing.md
    - variants/py/skills/01-core-sdk/runtime-lifecycle.md
    # ... (all Python-only skill files)
  rs:
    - variants/rs/agents/frameworks/trust-plane-specialist.md
    # Rust-specific skills (no global equivalent)
    - variants/rs/skills/01-core-sdk/add-node.md
    - variants/rs/skills/01-core-sdk/configure-alerts.md
    - variants/rs/skills/01-core-sdk/run-benchmarks.md
    # ... (all Rust-only skill files)

# Exclusions (never synced, per-repo)
exclude:
  - learning/**
  - .coc-sync-marker
  - settings.local.json
```

## Migration from ~/repos

The management commands currently at ~/repos/.claude/ move to loom/:

| Current (~/repos)                    | New (loom/)                                     | Notes                                       |
| ------------------------------------ | ----------------------------------------------- | ------------------------------------------- |
| `.claude/agents/coc-sync.md`         | `.claude/agents/management/coc-sync.md`         | Rewritten for variant system                |
| `.claude/agents/repo-ops.md`         | `.claude/agents/management/repo-ops.md`         | Absorbed                                    |
| `.claude/agents/repo-ops.md`         | `.claude/agents/management/repo-ops.md`         | Absorbed                                    |
| `.claude/agents/settings-manager.md` | `.claude/agents/management/settings-manager.md` | Absorbed                                    |
| `.claude/commands/sync.md`           | `.claude/commands/sync.md`                      | Exists, update for variants                 |
| `.claude/commands/repos.md`          | `.claude/commands/repos.md`                     | New in loom/                                |
| `.claude/commands/inspect.md`        | `.claude/commands/inspect.md`                   | New in loom/                                |
| `.claude/commands/settings.md`       | `.claude/commands/settings.md`                  | New in loom/                                |
| `.claude/rules/cross-repo.md`        | `.claude/rules/cross-repo.md`                   | Absorbed into existing cross-sdk-inspection |
| `.claude/skills/coc-sync-mapping.md` | Replaced by sync-manifest.yaml                  | Structured data replaces prose              |
| `CLAUDE.md`                          | Already exists                                  | Update for new architecture                 |

After migration, ~/repos/.claude/ can be reduced to a thin settings.json (for basic hooks when working at root level) and a CLAUDE.md that says "for COC management, work in loom/".

## Implementation Order

1. Create `variants/` directory structure in loom/
2. Create `sync-manifest.yaml` with full tier and variant declarations
3. Move language-specific content from current locations into variants/
4. Normalize global files to be truly language-agnostic
5. Absorb ~/repos management artifacts into loom/
6. Rewrite coc-sync agent to read manifest and apply overlays
7. Update /codify to create proposals (replaces direct sync)
8. Update CLAUDE.md for new architecture
9. Test: sync to py template, verify output matches expected
10. Test: sync to rs template, verify output matches expected
