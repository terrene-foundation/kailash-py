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

### Overlay Axes

The directory structure above shows the **language / stack** axis
(`py`, `rs`) for brevity, but `.claude/variants/` carries TWO orthogonal
overlay axes plus their composition. The authoritative axis set is
whatever `.claude/variants/*` holds on disk, declared in
`sync-manifest.yaml` (the top-level `variants:` map for the language
axis; `multi_cli_overlays` + `cli_variants` for the CLI axis). On disk
today `.claude/variants/` holds ten dirs: `base`, `py`, `rs`, `prism`,
`codex`, `gemini`, `py-codex`, `py-gemini`, `rs-codex`, `rs-gemini`
(plus a `README.md`). The three axes are:

- **Language / stack axis** — `base`, `py`, `rs`, `prism` (on disk) plus
  `rb` (a declared manifest axis with NO on-disk dir). Each selects the
  SDK-language overlay for a target (`/sync-to-use py` applies
  `variants/py/`). Status notes: `rb` (Ruby) has NO on-disk dir and no
  language overlay; in the manifest `variants:` map it is left UNDECLARED on
  most rules (and set `rb: null` on the few rules that carry an explicit
  per-axis list) — either way `resolveOverlay` treats an absent key and an
  explicit `null` identically (skip the axis), so `rb` resolves to the global
  and ships via the `rs` all-bindings template. The dedicated
  `kailash-coc-claude-rb` USE template was retired (`#423` Phase 1;
  `sync-manifest.yaml` header), so there is no `variants/rb/` dir. `prism`
  retains an on-disk `variants/prism/` dir reserved for the kailash-prism
  BUILD repo even though the `kailash-coc-claude-prism` USE template was
  retired in v2.9.4 (`sync-manifest.yaml` header); it is not an active
  USE-template target.
- **CLI axis** — `codex`, `gemini`. Selects the per-CLI overlay applied
  when emitting a multi-CLI artifact body (the Claude-Code baseline is
  the un-overlaid global; Codex/Gemini bodies overlay `variants/codex/`
  or `variants/gemini/`). Composed into the emitted body by
  `.claude/bin/emit.mjs::composeRule`.
- **Composed (ternary) axis** — `py-codex`, `py-gemini`, `rs-codex`,
  `rs-gemini`. A composed dir holds overlays needed ONLY when a specific
  language AND a specific CLI coincide — i.e. `py-codex` = the `py` ∩
  `codex` intersection, applied LAST so it can override both single-axis
  overlays (`rules/variant-authoring.md` § Composition precedence).

**Composition precedence** (per `rules/variant-authoring.md` Rule 4,
implemented at `.claude/bin/emit.mjs::composeRule`, lines 257-315): for a
target with language `<lang>` and CLI `<cli>`, overlays compose in order
**global → `variants/<lang>/` → `variants/<cli>/` → `variants/<lang>-<cli>/`**,
each present overlay applied additively (a slot-keyed overlay replaces the
matching global slot; a full-file overlay replaces the composed body — last
writer wins). Axis membership defers to `sync-manifest.yaml::variants` via
`resolveOverlay()` — a `null` declaration skips an axis even when a legacy
file exists on disk. So `py-codex` does NOT stand alone; it refines the
result of the `py` and `codex` overlays for the one target where both apply.

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

### loom Does Not Originate

loom is the central **splitter/distributor**. It never authors an artifact change itself — every change enters as an externally-originated proposal (BUILD repo for SDK code, USE-template repo for COC-artifact improvements). loom's job is Gate-1 split (global vs variant) + Gate-2 distribution. A loom-originated edit has no upstream provenance and is un-reviewable at Gate-1.

### Inbound: two typed proposal streams

Issues route by change TYPE, and each type originates a proposal on a different repo:

```
COC-artifact improvement (method/rules/skills/agents/COC-tooling)
  ↓ issue filed on the USE-template repo (kailash-coc-*)
  ↓ /codify originates .claude/.proposals/latest.yaml
  │   (authoritative target flow; see 09-proposal-protocol.md Step 7b)
  │
bug / code / feature / code-improvement (SDK code)
  ↓ issue filed on the BUILD repo (kailash-py or kailash-rs)
  ↓ BUILD repo considers CROSS-SDK FIRST
  ↓ /codify originates .claude/.proposals/latest.yaml
  │
  └──────────────┬──────────────┘
                 ↓
  loom/ receives proposal (PR, diff file, or interactive review)
  ↓ Gate-1 disclosure scrub on intake (scan-synced-disclosure.mjs --root
  │   on artifact files + HUMAN scrub of proposal body) — HALT on finding
  ↓ HUMAN classifies at loom/ (Gate-1):
    1. Is this global or language-specific?
    2. Does the other SDK need an equivalent? (BUILD stream: cross-SDK alignment note)
    3. Does this conflict with existing artifacts?
  ↓ HUMAN approves placement:
    - Global → merged into main artifacts
    - Language-specific → merged into variants/py/ or variants/rs/
    - Needs alignment → cross-SDK task created for other language
```

### Outbound: /sync-to-build + /sync-to-use

```
loom/ SPLITTER
  ├─ /sync-to-build ──→ kailash-py / kailash-rs (BUILD; canonical pushed back)
  └─ /sync-to-use py|rs|rb → kailash-coc-claude-{py,rs,rb}/ (USE templates)
                              ↓ downstream USE/project repos pull via own /sync-from-template
                              └──→ cycle repeats
```

USE templates are BOTH proposal originators (for COC-artifact improvements) AND distribution points (re-synced from loom) — never terminal-only. The `/sync-to-use` command reads `sync-manifest.yaml`, applies the correct variant overlay, and produces the target artifacts.

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
    - agents/cc-architect.md
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
    - variants/py/.claude/hooks/detect-package-manager.js
    - variants/py/.claude/hooks/validate-prod-deploy.js
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

## Standalone-Consumer Model — `client` is intentionally NOT a variant axis (yet)

Ratified 2026-05-16 (issue #243). Generalized pattern for any enterprise
consumer that runs its own downstream `/sync-from-template` against a USE template.

### The situation

An enterprise consumer repo (a Center-of-Excellence-style downstream
fork of a USE template) is synced from a loom release and adapted with
the consumer's own policy/directive set. The characteristic artifact
split observed:

- **~80% canonical base** — security, EATP, PACT, ISO / EU-AI-Act
  scaffolding. Stays loom-canonical; re-syncs via `/sync-from-template`.
- **~15%+5% consumer overlay** — consumer compliance rules, ITSM
  commands, enforcement hooks, project-scoped skills/agents. Authored
  in the consumer repo; MUST survive every `/sync-from-template`.

### The decision

`client` is **intentionally NOT a new first-class loom variant axis**
yet. An enterprise consumer repo is treated as a **standalone downstream
consumer with additive overlays**.

Rationale:

- `py`, `rs`, `rb`, `base`, `prism` are the **language / stack** axis —
  one of two overlay axes loom ships (see § Overlay Axes above for the
  full set, including the `codex` / `gemini` CLI axis and the composed
  `py-codex` / … ternary dirs). loom AUTHORS and SHIPS every variant's
  content on BOTH axes. A `client` axis would, by the same mechanic,
  require loom to author and ship client-specific content — which loom
  MUST NOT do. Consumer policy content is client-confidential and
  jurisdiction-specific; it has no place in the loom source of truth.
- There is exactly **one** enterprise consumer. A first-class axis is
  infrastructure built for N consumers; building it for N=1 is premature
  generalisation. The additive-overlay model (the consumer authors its
  own overlay in its own repo, the consumer's `/sync-from-template` preserves it) fully
  satisfies the N=1 requirement with zero loom-side client content.
- The ~80% canonical base already flows correctly through the existing
  tier-subscription `/sync-from-template` model. The only gap was preservation of the
  consumer's ~15%+5% — solved by the per-consumer boundary contract
  (below), not by a new axis.

### The revisit trigger

Re-evaluate the standalone-consumer model and consider promoting
`client` to a first-class axis **when (and only when) a 2nd enterprise
consumer appears**. Two consumers means a shared consumer-overlay
surface worth factoring; one consumer does not. Until then, each
enterprise consumer is a standalone downstream repo with its own
`consumer_overlays:` entry.

### Where the boundary contract lives

The canonical↔variant preservation + prohibition contract is in
`sync-manifest.yaml::consumer_overlays."<github-org>/<consumer-repo-slug>"`.
It is **consumer-targeted** (keyed by the consumer's GitHub slug),
NEVER applied to the kailash-coc-claude-{py,rs,rb} USE templates. It
declares three surfaces:

| Surface                | Purpose                                                                            |
| ---------------------- | ---------------------------------------------------------------------------------- |
| `preserved:`           | GLOB set of consumer-authored paths /sync-from-template never overwrites or purges |
| `canonical_protected:` | loom-owned paths the consumer must not edit; divergence is BLOCK-gated             |
| `codify_back:`         | exceptional upstreaming policy; consumer-confidential content never leaves         |

The downstream `/sync-from-template` enforcement is specified in
`skills/30-claude-code-patterns/sync-flow.md` § Downstream Sync (step 5
preservation extension + the new step 5a canonical-divergence gate).
