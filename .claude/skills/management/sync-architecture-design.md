# /sync Command Architecture Design

## Executive Summary

The current COC sync mechanism is an LLM-mediated agent (coc-sync) that lives in the BUILD repo and pushes transformed artifacts to sibling COC template repos. This design has three critical failure modes: (1) the scripts/ directory is routinely missed (the py COC template is currently missing it entirely), (2) there is no version tracking so drift is invisible, and (3) the entire process depends on an LLM session remembering to do ~7 steps with ~19 transform rules correctly every time. This document designs a deterministic, auditable /sync architecture that eliminates these failure modes.

**Complexity Score: 23 (Complex)** -- Governance: 7, Legal: 4, Strategic: 12

---

## Part 1: Answers to the Five Design Questions

### Question 1: Where does the canonical source live?

**Recommendation: The BUILD repo (kailash-py) remains the canonical source.**

Alternatives considered:

| Option                              | Pros                                                                                                                     | Cons                                                                                                                                                            | Verdict      |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **(a) BUILD repo (current)**        | Single source of truth; agents/skills evolve alongside code; /codify creates artifacts in the same repo where they apply | Requires transforms for USE repos; coc-sync agent complexity                                                                                                    | **Selected** |
| (b) Dedicated COC distribution repo | Clean separation; template repos are disposable consumers                                                                | Creates a third repo to maintain; splits institutional knowledge from the code it describes; two-hop sync (BUILD to distro to template) doubles failure surface | Rejected     |
| (c) COC template repos as source    | Template is the source and BUILD inherits                                                                                | Inverts the authority model; agents describing SDK internals would live outside the SDK; /codify would need to write to an external repo                        | Rejected     |

**Rationale**: CO Principle 1 (Institutional Knowledge Thesis) requires knowledge to live where it is generated. Agents and skills are generated during SDK development sessions. The BUILD repo is where that happens. The COC templates are distribution artifacts, not authoring environments.

### Question 2: How does the sync command discover the source?

**Recommendation: Config file (`.claude/sync.json`) with sibling directory default + override.**

```json
{
  "source": {
    "default": "../kailash-py",
    "override_env": "KAILASH_BUILD_REPO"
  }
}
```

Alternatives considered:

| Option                           | Pros                                                    | Cons                                                                                                               | Verdict                                     |
| -------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| (a) Hardcoded sibling path       | Simple                                                  | Breaks if repos are not siblings; breaks in CI; breaks on other developers' machines                               | Rejected                                    |
| (b) Git remote / URL             | Works in CI                                             | Requires clone/fetch; slow; version resolution is complex (which commit?)                                          | Rejected for primary; useful for CI variant |
| (c) Published package            | Clean distribution                                      | Massive overhead; COC artifacts are not a pip package; 30+ agents + 28 skills + hooks do not fit the package model | Rejected                                    |
| **(d) Config file with default** | Flexible; works locally and in CI; override via env var | Requires a config file                                                                                             | **Selected**                                |

**Design**: The `/sync` command in the COC template repo reads `.claude/sync.json` for the source path. The default (`../kailash-py`) works for the standard sibling layout. CI overrides via `KAILASH_BUILD_REPO` env var. A `/sync --source /path/to/build` flag is also supported for one-off use.

### Question 3: What triggers the sync?

**Recommendation: Manual `/sync` as primary. Session-start freshness check as advisory. CI as gatekeeper.**

| Trigger                | Behavior                                                                                | Phase                   |
| ---------------------- | --------------------------------------------------------------------------------------- | ----------------------- |
| **Manual `/sync`**     | Full sync with transforms, version update, contamination check                          | Primary                 |
| **Session start hook** | Read manifest, compare hash of BUILD .claude/ tree, warn if stale                       | Advisory (warning only) |
| **CI workflow**        | Run `/sync --check` in dry-run mode; fail PR if template is stale relative to BUILD tag | Gatekeeper (Phase 2)    |

The session-start hook adds approximately 200ms to check the manifest hash. If the BUILD repo has changed since last sync, it emits a single-line warning: `[COC] Template is N commits behind BUILD. Run /sync to update.`

### Question 4: How do version numbers get resolved?

**Recommendation: Read from BUILD repo's pyproject.toml files (option a) with PyPI fallback for validation.**

The sync command:

1. Reads `pyproject.toml` from the BUILD repo root and each `packages/*/pyproject.toml`
2. Extracts version strings for kailash, kailash-dataflow, kailash-nexus, kailash-kaizen, kailash-pact
3. Updates the COC template's `pyproject.toml` dependency pins atomically
4. Optionally queries PyPI to validate that the pinned version is actually published (avoids pinning to a version that only exists locally)

Version map stored in manifest:

```json
{
  "versions": {
    "kailash": "2.2.0",
    "kailash-dataflow": "1.2.1",
    "kailash-nexus": "1.6.0",
    "kailash-kaizen": "2.3.1",
    "kailash-pact": "0.4.1"
  }
}
```

### Question 5: What is the conflict resolution strategy?

**Recommendation: Layer isolation (option c) as the primary model, with force overwrite (option a) as the fallback for synced layers.**

Design:

- **Layers A-D** (synced content): Force overwrite. The BUILD repo is authoritative. Any local edits to synced files are destroyed on sync. This is by design -- the COC template is a distribution artifact, not an authoring environment.
- **Layer E** (project-local): Never touched. The sync command has a hardcoded exclusion list for Layer E paths. It physically cannot overwrite `CLAUDE.md`, `pyproject.toml`, `.env`, `agents/project/`, `skills/project/`, or `learning/`.
- **Conflict detection**: The manifest records SHA-256 hashes of every synced file. If a synced file has been locally modified since last sync, the sync command warns but proceeds with overwrite. The warning is informational: "File X was locally modified since last sync. Overwriting with BUILD version."

This eliminates three-way merge complexity entirely. The invariant is: if a file came from sync, sync owns it. If a file was created locally, sync ignores it.

---

## Part 2: Architecture

### 2.1 Artifact Layer Classification

Each file in the COC template belongs to exactly one layer. The sync command must know the layer of every file to apply correct behavior.

```
Layer A: CC Platform (Claude Code configuration)
  .claude/settings.json          -- Synced (with hook path transforms)
  scripts/hooks/*.js             -- Synced (with possible softening)
  scripts/hooks/lib/*.js         -- Synced as-is
  scripts/learning/*.js          -- Synced as-is
  scripts/ci/*.js                -- Synced as-is
  scripts/plugin/*.js            -- Synced as-is

Layer B: CO Methodology (domain-agnostic)
  .claude/rules/communication.md         -- Synced as-is
  .claude/rules/autonomous-execution.md  -- Synced as-is
  .claude/rules/journal.md               -- Synced as-is (if exists in BUILD)
  .claude/rules/terrene-naming.md        -- Synced as-is
  .claude/rules/independence.md          -- Synced as-is
  .claude/agents/standards/co-expert.md  -- Synced as-is
  .claude/agents/standards/care-expert.md-- Synced as-is
  .claude/agents/standards/eatp-expert.md-- Synced as-is
  .claude/agents/standards/coc-expert.md -- Synced as-is
  .claude/skills/co-reference/           -- Synced as-is
  .claude/skills/27-care-reference/      -- Synced as-is
  .claude/skills/26-eatp-reference/      -- Synced as-is
  .claude/skills/28-coc-reference/       -- Synced as-is

Layer C: COC Artifacts (codegen-specific, shared across SDKs)
  .claude/agents/deep-analyst.md         -- Synced (strip builder paths)
  .claude/agents/intermediate-reviewer.md-- Synced (strip builder paths)
  .claude/agents/security-reviewer.md    -- Synced as-is
  .claude/agents/frameworks/*.md         -- Synced (strip builder paths)
  .claude/agents/frontend/*.md           -- Synced as-is
  .claude/agents/management/*.md         -- Synced (minus coc-sync.md)
  .claude/rules/agents.md               -- Synced (rule softening)
  .claude/rules/no-stubs.md             -- Synced (rule softening)
  .claude/rules/testing.md              -- Synced (rule softening)
  .claude/rules/git.md                  -- Synced (rule softening)
  .claude/rules/security.md             -- Synced as-is
  .claude/rules/branch-protection.md    -- Synced as-is
  .claude/rules/e2e-god-mode.md         -- Synced as-is
  .claude/rules/env-models.md           -- Synced as-is
  .claude/rules/patterns.md             -- Synced (strip builder paths)
  .claude/rules/zero-tolerance.md       -- Synced (rule softening)
  .claude/commands/*.md                  -- Synced as-is (except codify.md)
  .claude/guides/**                      -- Synced as-is
  .claude/skills/01-core-sdk/            -- Synced (strip builder paths)
  .claude/skills/02-dataflow/            -- Synced (strip builder paths)
  .claude/skills/03-nexus/               -- Synced (strip builder paths)
  .claude/skills/04-kaizen/              -- Synced (strip builder paths + rule softening)
  .claude/skills/05-kailash-mcp/         -- Synced (strip builder paths)
  .claude/skills/06-cheatsheets/ thru 28 -- Mostly synced as-is
  .claude/skills/30-claude-code-patterns/-- Synced as-is

Layer D: SDK-Specific (different per py vs rs)
  .claude/rules/dataflow-pool.md         -- Synced as-is (py-specific)
  .claude/rules/infrastructure-sql.md    -- Synced as-is (py-specific)
  .claude/rules/eatp.md                  -- Synced as-is (py-specific)
  .claude/rules/trust-plane-security.md  -- Synced as-is (py-specific)
  .claude/rules/pact-governance.md       -- Synced as-is (py-specific)
  .claude/rules/deployment.md            -- Synced as-is (py-specific)
  .claude/rules/agent-reasoning.md       -- Synced as-is
  .claude/rules/cc-artifacts.md          -- Synced as-is
  .claude/rules/connection-pool.md       -- Synced as-is (py-specific)
  .claude/skills/15-enterprise-infrastructure/ -- Synced (strip builder paths)

Layer E: Project-Local (NEVER synced)
  CLAUDE.md                              -- Project root context file
  pyproject.toml                         -- Project dependencies (version pins updated, structure preserved)
  .env / .env.example                    -- Project configuration
  .claude/learning/                      -- Per-repo learning data
  .claude/agents/project/                -- DOWNSTREAM USE REPOS ONLY (project-specific /codify output).
                                         -- BUILD repos (kailash-py/rs/prism) MUST NOT have this directory —
                                         -- /codify writes to canonical locations in BUILD for upstream flow.
  .claude/skills/project/                -- DOWNSTREAM USE REPOS ONLY (same as above)
  workspaces/                            -- Project workspace state
  journal/                               -- Project journal entries
  conftest.py                            -- Project test configuration
  scripts/hooks/detect-package-manager.js-- Potentially customized per project
```

### 2.2 The Sync Manifest

The key missing piece in the current design is a **sync manifest** -- a machine-readable record of what was synced, when, from where, and with what content hash.

**File**: `.claude/sync-manifest.json` (lives in the COC template, committed to git)

```json
{
  "schema_version": 1,
  "last_sync": {
    "timestamp": "2026-03-28T14:30:00Z",
    "build_repo": "../kailash-py",
    "build_commit": "ae41e2cb",
    "build_branch": "main",
    "sync_agent_version": "1.0.0"
  },
  "versions": {
    "kailash": "2.2.0",
    "kailash-dataflow": "1.2.1",
    "kailash-nexus": "1.6.0",
    "kailash-kaizen": "2.3.1",
    "kailash-pact": "0.4.1"
  },
  "files": {
    ".claude/agents/deep-analyst.md": {
      "source": ".claude/agents/deep-analyst.md",
      "layer": "C",
      "transform": "strip_builder_paths",
      "source_hash": "sha256:abc123...",
      "synced_hash": "sha256:def456...",
      "synced_at": "2026-03-28T14:30:00Z"
    },
    ".claude/rules/agents.md": {
      "source": ".claude/rules/agents.md",
      "layer": "C",
      "transform": "rule_softening",
      "source_hash": "sha256:...",
      "synced_hash": "sha256:...",
      "synced_at": "2026-03-28T14:30:00Z"
    },
    "scripts/hooks/validate-workflow.js": {
      "source": "scripts/hooks/validate-workflow.js",
      "layer": "A",
      "transform": "as_is",
      "source_hash": "sha256:...",
      "synced_hash": "sha256:...",
      "synced_at": "2026-03-28T14:30:00Z"
    }
  },
  "exclusions": [
    ".claude/agents/management/coc-sync.md",
    ".claude/skills/management/coc-sync-mapping.md",
    ".claude/skills/management/coc-sync-agent-reference.md",
    ".claude/learning/",
    ".claude/rules/cross-sdk-inspection.md"
  ],
  "contamination_check": {
    "passed": true,
    "checked_at": "2026-03-28T14:30:05Z",
    "counts": {
      "src_kailash_refs": 0,
      "packages_internal_refs": 0,
      "absolute_paths": 0,
      "sync_infra_leaked": 0,
      "internal_class_names": 0
    }
  }
}
```

**Why a manifest matters**:

1. **Drift detection**: Session-start hook compares BUILD commit hash against `last_sync.build_commit`. If they differ, it warns.
2. **Selective sync**: On subsequent syncs, only files whose `source_hash` changed need processing. This turns a 200-file full sync into a 3-file delta sync.
3. **Audit trail**: The manifest is committed to git. `git log sync-manifest.json` shows every sync event, who triggered it, and what BUILD commit it corresponds to.
4. **Local modification detection**: Compare current file hash against `synced_hash`. If they differ, the file was locally modified since last sync.
5. **Version consistency**: The `versions` section makes it trivial to check if `pyproject.toml` pins match without re-reading the BUILD repo.

### 2.3 The /sync Command

**File**: `.claude/commands/sync.md` (lives in the COC template repo, NOT the BUILD repo)

This is the critical architectural decision: the /sync command lives in the CONSUMER (the COC template), not the PRODUCER (the BUILD repo). The BUILD repo's coc-sync agent is the producer-side mechanism. The /sync command in the template is the consumer-side pull mechanism.

**Why consumer-side**: The current model requires someone to be in the BUILD repo to push. The new model allows someone working in any project that uses the COC template to pull updates. This is analogous to `apt update` -- the consumer initiates the update, not the upstream.

**Command signature**: `/sync [--check] [--source PATH] [--force] [--layer A|B|C|D|all]`

| Flag            | Behavior                                                                 |
| --------------- | ------------------------------------------------------------------------ |
| (none)          | Full sync: detect changes, transform, write, validate, update manifest   |
| `--check`       | Dry run: report what would change, exit 0 if up-to-date, exit 1 if stale |
| `--source PATH` | Override source repo path (default: from sync.json or ../kailash-py)     |
| `--force`       | Skip local modification warnings, overwrite everything                   |
| `--layer X`     | Sync only the specified layer (for debugging or partial updates)         |

### 2.4 Sync Process (7 Phases)

```
Phase 1: DISCOVER
  - Read .claude/sync.json for source path
  - Verify source repo exists and is a git repo
  - Read source repo's HEAD commit hash and branch
  - Read source repo's pyproject.toml versions
  - Compare against manifest's last_sync.build_commit
  - If identical and not --force: "Already up to date." Exit.

Phase 2: PLAN
  - Walk source .claude/ directory tree
  - Walk source scripts/ directory tree
  - For each file:
    - Check exclusion list (skip if excluded)
    - Classify into layer (A/B/C/D)
    - Determine transform type (as_is, strip_builder_paths, rule_softening, etc.)
    - Compute source file hash
    - Compare against manifest's source_hash for that file
    - If hash unchanged: mark SKIP (unless --force)
    - If hash changed or new file: mark SYNC
  - For each file in manifest but NOT in source:
    - Mark ORPHAN (warn but do not delete -- additive model)
  - Present plan to user:
    "Sync plan: 12 files to sync (3 new, 9 updated), 185 unchanged, 2 orphaned"
    If --check: print plan and exit

Phase 3: TRANSFORM
  - For each file marked SYNC:
    - Read source file content
    - Apply transforms in order:
      1. Strip absolute paths (any path starting with /Users/ or /home/)
      2. Strip internal source paths (src/kailash/, packages/kailash-*/src/)
      3. Strip internal class names (SyncDDLExecutor, TypeAwareFieldProcessor, etc.)
      4. Strip builder-only references (contrib, tests/utils/test-env)
      5. Apply rule softening (if applicable per transform type)
      6. Apply CLAUDE.md special handling (if file is CLAUDE.md)
      7. Apply command-specific transforms (codify.md -> project/ output paths — USE template only; source BUILD repo keeps canonical /codify routing)
    - Compute synced file hash (post-transform)
    - Stage in memory (do not write yet)

Phase 4: WRITE
  - For each transformed file:
    - Check if target file exists and differs from staged content
    - If target exists and was locally modified (hash differs from manifest's synced_hash):
      - Warn: "File X was locally modified since last sync. Overwriting."
    - Write file to target path
    - Record in manifest: source_hash, synced_hash, transform, timestamp

Phase 5: VERSION
  - Read versions from BUILD repo's pyproject.toml files
  - Read COC template's pyproject.toml
  - For each dependency pin (kailash, kailash-dataflow, etc.):
    - If version differs from BUILD: update pin
    - Log change: "kailash: 2.1.0 -> 2.2.0"
  - Grep synced .claude/ files for stale version references
  - Update inline version references where found

Phase 6: VALIDATE
  - Run contamination check (grep for builder-specific patterns)
  - Verify all hooks in settings.json have corresponding scripts in scripts/hooks/
  - Verify all cross-references in synced files point to files that exist
  - Report any issues found
  - If contamination detected: BLOCK (exit 1, do not commit manifest)

Phase 7: MANIFEST
  - Write updated sync-manifest.json
  - Generate human-readable sync report
  - Print summary:
    "Sync complete: 12 files synced, 185 unchanged, 0 contamination issues"
    "SDK versions: kailash 2.2.0, dataflow 1.2.1, nexus 1.6.0, kaizen 2.3.1"
    "Build: ae41e2cb (main)"
```

### 2.5 Transform Pipeline

Transforms are applied as a deterministic pipeline, not LLM-mediated reasoning. Each transform is a pure function: `(content: string, metadata: FileMetadata) -> string`.

```
Transform Registry:

  as_is
    No content transformation. File copied verbatim.
    Applied to: Layer B files, most Layer A files, many Layer C files

  strip_builder_paths
    Remove lines containing: src/kailash/, packages/kailash-*/src/,
    tests/utils/test-env, contrib references.
    Remove references to internal class names.
    Remove absolute paths matching /Users/* or /home/*.
    Applied to: Agents and skills that reference SDK internals

  rule_softening
    Pattern replacements:
      "MUST delegate" -> "SHOULD delegate" / "RECOMMENDED"
      "MANDATORY" (in delegation context) -> "RECOMMENDED"
      "NO exceptions" (in review context) -> "Users may skip"
      "PROHIBITED" (in review context) -> "RECOMMENDED"
      "NO MOCKING" -> "Real infrastructure recommended"
      "MUST NOT contain TODO" -> "SHOULD NOT contain TODO"
      "Non-negotiable" (in review context) -> "strongly recommended"
    Applied to: rules/agents.md, rules/no-stubs.md, rules/testing.md,
                rules/git.md, rules/zero-tolerance.md, CLAUDE.md

  rule_softening_downstream
    Same patterns as rule_softening applied to files that echo rule language.
    Applied to: guides/claude-code/CLAUDE.md, skills/04-kaizen/SKILL.md

  context_file_rewrite
    Full CLAUDE.md transformation:
      - "COC setup for Claude Code" -> "COC setup for building with the Kailash SDK"
      - "Mandatory Reviews" -> "Recommended Reviews"
      - Strip builder-internal references
    Applied to: Root CLAUDE.md only

  codify_command_rewrite
    Rewrite /codify output paths for USE-template delivery:
      agents/ -> agents/project/
      skills/ -> skills/project/
    Applied to: commands/codify.md only, and ONLY during loom/→USE-template sync.
    Scope: USE-template side ONLY. The BUILD repo (kailash-py/rs/prism) keeps its
    own codify.md with canonical routing ("write to canonical locations + create
    proposal") so BUILD-side /codify output flows UPSTREAM via .proposals/latest.yaml.
    Do NOT apply this transform to a BUILD repo's own codify.md.

  exclusion_filter
    Entire files excluded from sync.
    Applied to: coc-sync.md, coc-sync-mapping.md, coc-sync-agent-reference.md,
```

### 2.6 The Missing scripts/ Problem

The current kailash-coc-claude-py is MISSING the entire `scripts/` directory despite `settings.json` referencing 7 hook scripts in `scripts/hooks/`. This means every Claude Code session in a project using this template starts with hook execution failures.

**Fix in the /sync architecture**: scripts/ is a first-class sync target, same as .claude/.

```
scripts/ sync rules:
  scripts/hooks/*.js           -> Synced from BUILD, with transforms if needed
  scripts/hooks/lib/*.js       -> Synced as-is
  scripts/learning/*.js        -> Synced as-is
  scripts/ci/*.js              -> Synced as-is
  scripts/plugin/*.js          -> Synced as-is
```

The sync manifest tracks scripts/ files with the same hash-based change detection as .claude/ files. The validation phase (Phase 6) checks that every hook command in `settings.json` has a corresponding file in `scripts/hooks/`.

**Hook softening**: Some hooks enforce BUILD-repo-strict policies. For USE repos, these hooks may need softer behavior. The `/sync` architecture supports hook-level transforms:

| Hook                            | BUILD behavior                     | USE behavior (softened)      |
| ------------------------------- | ---------------------------------- | ---------------------------- |
| `validate-workflow.js`          | EXIT 2 (BLOCK) on stubs            | EXIT 0 (WARN) on stubs       |
| `user-prompt-rules-reminder.js` | Inject zero-tolerance reminder     | Inject softer reminder       |
| `session-start.js`              | Check package freshness + COC sync | Check package freshness only |

Hook softening is implemented via environment variable detection. The hook scripts already run in the target project's context. A `.claude/sync.json` field `"repo_type": "use"` signals USE mode. Hooks read this and adjust severity.

**Alternative**: Instead of environment-based softening, maintain separate hook variants. The BUILD hooks are the master; the USE hooks are derived with softer thresholds. This is more explicit but doubles the hook maintenance surface. Recommendation: environment-based softening, because hooks are already parameterized by `$CLAUDE_PROJECT_DIR`.

### 2.7 Exclusion Lists

Two exclusion categories:

**BUILD-only files** (exist in BUILD, never synced to USE):

```
.claude/agents/management/coc-sync.md          # Sync infrastructure
.claude/skills/management/coc-sync-mapping.md   # Sync infrastructure
.claude/skills/management/coc-sync-agent-reference.md  # Sync infrastructure
.claude/rules/cross-sdk-inspection.md           # BUILD-only process rule
.claude/learning/                               # Per-repo learning data
```

**USE-only files** (exist in USE, never overwritten by sync):

```
CLAUDE.md                    # Project-specific directives
pyproject.toml               # Project dependencies (version pins updated separately)
.env / .env.example          # Project configuration
conftest.py                  # Project test configuration
.claude/agents/project/      # Project-specific agents (USE repos only; BUILD repos do NOT have this)
.claude/skills/project/      # Project-specific skills (USE repos only; BUILD repos do NOT have this)
.claude/learning/            # Per-repo learning data
workspaces/                  # Project workspace state
journal/                     # Project journal entries
```

### 2.8 Version Pin Update Strategy

The `pyproject.toml` in the COC template is a USE-only file (Layer E) -- it belongs to the project. However, the Kailash SDK dependency pins within it are Layer D content. The sync command updates ONLY the dependency pins, preserving all other content.

Strategy:

1. Parse the COC template's `pyproject.toml` using a TOML parser (not regex)
2. Find the `[project] dependencies` list
3. For each Kailash package pin (kailash, kailash-dataflow, kailash-nexus, kailash-kaizen, kailash-pact):
   - Read the BUILD repo's version for that package
   - Update the pin to `>=BUILD_VERSION`
4. Write back the TOML, preserving all other content, comments, and formatting
5. Report changes: `"kailash: >=2.1.0 -> >=2.2.0"`

**Edge case**: The template's `pyproject.toml` has a `# TODO: Replace with your project name` template. The sync command MUST NOT replace this. It only touches lines matching `kailash*>=`.

**Edge case**: All standard extras (`trust`, `pact`, `postgres`, `database`, `mysql`, `server`, `http`, `monitoring`, `trust-encryption`, `trust-sso`) are now included in the base `pip install kailash`. The sync should normalize any extras-bracket dependency using only standard extras (e.g., `kailash[trust,pact]>=2.1.0`) to `kailash>=2.1.0`. The extras-bracket handling is still needed for vendor-specific backends (`kailash[vault]`, `kailash[aws-secrets]`, `kailash[azure-secrets]`, `kailash[trust-windows]`) which remain genuine optional extras.

---

## Part 3: Risk Register

| ID  | Risk                                                                                                                     | Likelihood     | Impact                                                             | Mitigation                                                                                                                                                                       |
| --- | ------------------------------------------------------------------------------------------------------------------------ | -------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | scripts/ directory missing from sync (current state)                                                                     | CERTAIN        | CRITICAL -- hooks fail silently, enforcement layer non-functional  | Phase 6 validation: verify every settings.json hook has a matching script file. Block sync if missing.                                                                           |
| R2  | Rule softening inconsistency -- agents.md softened but git.md not, or downstream echoes not updated                      | HIGH           | MAJOR -- contradictory instructions confuse the LLM                | Transform pipeline applies rule_softening to all mapped files atomically. Contamination check greps for residual strict language patterns.                                       |
| R3  | Transform corrupts file content -- regex over-matches or destroys code examples                                          | MEDIUM         | MAJOR -- invalid agents or skills deployed to users                | Transforms operate on line-level patterns with context guards (do not strip lines inside code fences). Integration tests verify transform output against golden files.           |
| R4  | Stale manifest after manual edits -- someone edits a synced file in the COC template and the manifest becomes inaccurate | MEDIUM         | MINOR -- next sync warns and overwrites, which is correct behavior | Manifest records synced_hash. If current hash differs from synced_hash, warn on next sync. No action needed -- overwrite is the design.                                          |
| R5  | Version pin mismatch -- BUILD has 2.2.0 but PyPI only has 2.1.0 published                                                | LOW            | MAJOR -- users cannot install                                      | Phase 5 optionally queries PyPI to validate. If version is not published, warn but proceed (BUILD may be pre-release).                                                           |
| R6  | New file in BUILD not classified into a layer                                                                            | MEDIUM         | SIGNIFICANT -- file synced without appropriate transform           | Default behavior: sync as-is with strip_builder_paths transform. Log a warning: "Unclassified file X synced with default transform." The manifest marks it `"layer": "unknown"`. |
| R7  | LLM-mediated transforms fail silently -- the LLM does not apply all 19 transform rules consistently                      | HIGH (current) | CRITICAL                                                           | Eliminate LLM-mediated transforms. Replace with deterministic transform pipeline. The coc-sync agent orchestrates but transforms are pure functions.                             |
| R8  | Sync from wrong BUILD branch                                                                                             | LOW            | MAJOR -- unstable artifacts deployed                               | Phase 1 records build_branch in manifest. If not `main`, warn: "Syncing from non-main branch: feat/X. Proceed?"                                                                  |
| R9  | Orphaned files accumulate in COC template                                                                                | LOW            | MINOR -- dead files waste context                                  | Phase 2 detects orphans (in manifest but not in BUILD). Reports but does not delete (additive model). Periodic manual cleanup.                                                   |
| R10 | Hook scripts diverge from settings.json references                                                                       | MEDIUM         | CRITICAL -- hooks configured but scripts missing = silent failures | Phase 6 cross-references settings.json hook commands against scripts/ directory. Blocks if any referenced script is missing.                                                     |

---

## Part 4: Cross-Reference Audit

### Documents Affected by This Design

| Document                                                   | Impact                                                                                                                                                                      |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kailash-py/.claude/agents/management/coc-sync.md`         | Retains role as BUILD-side push mechanism. The /sync command in COC template is the complementary pull mechanism. Both can coexist.                                         |
| `kailash-py/.claude/skills/management/coc-sync-mapping.md` | Transform rules encoded here become the transform pipeline specification. This file remains the canonical source for transform definitions.                                 |
| `kailash-coc-claude-py/CLAUDE.md`                          | Not modified by sync (Layer E). Template CLAUDE.md is generated during initial setup, then owned by the project.                                                            |
| `kailash-coc-claude-py/.claude/settings.json`              | Currently references scripts/hooks/ that do not exist. Sync will fix this by syncing scripts/ alongside .claude/.                                                           |
| `~/repos/.claude/commands/sync.md`                         | The root-level /sync command pushes FROM template TO project. The new /sync command in the template pulls FROM BUILD TO template. Different direction, complementary roles. |
| `~/repos/CLAUDE.md`                                        | Documents COC templates and sync. Update to reference the manifest-based sync model.                                                                                        |
| `kailash-py/.claude/rules/cc-artifacts.md`                 | Rule 5 ("No BUILD Artifacts in USE Repos") is now enforced by the exclusion list in the sync manifest.                                                                      |

### Inconsistencies Found

1. **scripts/ missing from py COC template**: `settings.json` references 7 hook scripts that do not exist. The rs COC template HAS scripts/. This is the documented #1 sync failure mode, and it is currently active.

2. **Root /sync direction mismatch**: The root-level `/sync` command (in `~/repos/.claude/commands/sync.md`) syncs FROM template TO project. The coc-sync agent syncs FROM BUILD TO template. There is no command that syncs FROM BUILD TO template from the template side. The new /sync command fills this gap.

3. **No version tracking**: Neither the BUILD repo nor either COC template has any mechanism to record what was last synced. The sync manifest addresses this.

4. **Rule softening applied inconsistently**: The py COC template's `rules/agents.md` has already been softened (RECOMMENDED instead of MUST), but the BUILD repo's `cc-artifacts.md` rule 5 references files that should be excluded (`agents/frontend/`) -- and those files ARE present in the py COC template. The exclusion list needs reconciliation.

5. **`kailash-coc-claude-py` has `connection-pool.md` in rules**: This file exists in the COC template but NOT in the BUILD repo's rules. It is COC-only content. The sync must preserve it (additive model).

---

## Part 5: Decision Points

These require stakeholder input before implementation:

1. **Should the /sync command be a Claude Code command (.claude/commands/sync.md) or a shell script (scripts/sync.sh)?**
   - Command: Leverages LLM for error recovery, reporting, and edge case handling. Higher token cost per sync.
   - Shell script: Deterministic, zero LLM cost, can run in CI. Lower flexibility for complex transforms.
   - Recommendation: **Both**. A shell script (`scripts/sync.sh`) handles the deterministic parts (file copying, hashing, manifest update). The `/sync` command delegates to the script and adds LLM-mediated reporting, error explanation, and transform validation.

2. **Should hook scripts be softened via environment variable or maintained as separate variants?**
   - Env-based: One set of hooks, behavior varies by `repo_type` in sync.json. Less duplication.
   - Separate variants: Two sets of hooks (build/ and use/). More explicit, easier to audit.
   - Recommendation: **Env-based** for Phase 1. If hook divergence grows beyond 3 hooks, reconsider separate variants.

3. **Should the session-start freshness check be opt-in or default-on?**
   - Default-on: Every session warns if stale. Prevents drift.
   - Opt-in: Users who do not care about sync are not bothered. Reduces noise.
   - Recommendation: **Default-on** with a one-line warning. The warning is informational, not blocking.

4. **Should the manifest be committed to git or gitignored?**
   - Committed: Audit trail, reproducibility, team coordination.
   - Gitignored: Less noise in commits, simpler workflow.
   - Recommendation: **Committed**. The manifest IS the audit trail. It should be part of the project's git history.

5. **What is the BUILD-only exclusion policy for `agents/frontend/`?**
   - The `cc-artifacts.md` rule says "agents/frontend/ -- BUILD repos don't do frontend work" should be excluded from USE repos. But the current coc-sync-mapping.md lists `agents/frontend/*` as Category 1 (synced as-is). These are contradictory.
   - Recommendation: **Sync frontend agents**. USE repos DO build frontends. The cc-artifacts rule is written from the perspective of the BUILD repo (which does not do frontend work). COC templates serve users who build applications, and applications have frontends.

6. **Should the Gemini sync target be supported by the same /sync command?**
   - Yes: One command, two targets. Complexity in the command, simplicity for the user.
   - No: Separate /sync commands per platform. The Gemini template gets its own /sync.
   - Recommendation: **Yes, same command with target flag**. `/sync --target claude` (default) or `/sync --target gemini`. The transform pipeline is modular -- Gemini adds path remapping, tool name mapping, and TOML conversion as additional transform stages.

---

## Part 6: Implementation Roadmap

### Phase 1: Foundation (1 autonomous session)

1. Create `.claude/sync.json` in kailash-coc-claude-py with source path config
2. Create `.claude/commands/sync.md` in kailash-coc-claude-py
3. Create `scripts/sync.sh` -- deterministic sync engine (file walk, hash, copy, manifest)
4. Run initial sync to populate scripts/ directory (fixing the missing hooks crisis)
5. Generate initial sync-manifest.json
6. Commit and verify all hooks work

### Phase 2: Transforms (1 autonomous session)

1. Encode transform pipeline as deterministic functions in `scripts/sync-transforms.js`
2. Create golden file tests for each transform type
3. Verify rule softening, builder path stripping, and CLAUDE.md rewrite
4. Validate contamination check as part of sync pipeline

### Phase 3: Version Management (0.5 autonomous session)

1. Implement version extraction from BUILD repo pyproject.toml files
2. Implement version pin update in COC template pyproject.toml
3. Implement stale version reference scanning in synced .claude/ content
4. Optional: PyPI validation for published versions

### Phase 4: Session Integration (0.5 autonomous session)

1. Add freshness check to session-start.js hook
2. Read manifest, compare BUILD commit hash
3. Emit single-line warning if stale
4. Test end-to-end flow: BUILD changes -> session-start warns -> /sync updates

### Phase 5: CI Integration (future, not in initial scope)

1. GitHub Action that runs `/sync --check` on PRs to the COC template
2. Fails if template is stale relative to the latest BUILD release tag
3. Optionally auto-creates a PR with updated artifacts

---

## Part 7: Success Criteria

| Criterion                  | Measurement                                                                                     | Target      |
| -------------------------- | ----------------------------------------------------------------------------------------------- | ----------- |
| scripts/ always synced     | Phase 6 validation passes: every settings.json hook has a matching script                       | 100%        |
| Contamination-free sync    | All 5 contamination counts = 0 after every sync                                                 | 100%        |
| Version consistency        | COC template pyproject.toml pins match BUILD versions after sync                                | 100%        |
| Selective sync performance | Delta sync (no BUILD changes) completes in < 5 seconds                                          | < 5s        |
| Full sync performance      | Full sync (all files changed) completes in < 60 seconds                                         | < 60s       |
| Rule softening consistency | No residual strict language patterns (MUST delegate, NO exceptions, NO MOCKING) in synced files | 0 residual  |
| Manifest accuracy          | Manifest file count matches actual synced file count                                            | Exact match |
| Session-start freshness    | Hook detects stale state within 500ms                                                           | < 500ms     |
| Additive guarantee         | Zero files deleted from COC template during sync                                                | 0 deletions |

---

## Appendix A: File Count Estimates

Based on current BUILD repo inventory:

| Category               | Count                           |
| ---------------------- | ------------------------------- |
| Agents (synced)        | ~32 (37 total minus 5 excluded) |
| Rules (synced)         | ~18 (22 total minus 4 excluded) |
| Skills directories     | ~28                             |
| Skill files (total)    | ~120                            |
| Commands               | ~24                             |
| Guides                 | ~20                             |
| Hook scripts           | ~12                             |
| Hook lib files         | ~4                              |
| Learning scripts       | ~4                              |
| CI scripts             | ~6                              |
| Plugin scripts         | ~3                              |
| **Total synced files** | **~270**                        |

## Appendix B: Relationship Between Push and Pull Sync

```
                         BUILD REPO
                        (kailash-py)
                             |
                     coc-sync agent
                     (push, /codify)
                             |
                    +--------+--------+
                    |                 |
              COC Template       COC Template
            (claude-py)          (gemini-py)
                    |                 |
              /sync command      /sync command
              (pull, on-demand)  (pull, on-demand)
                    |                 |
             +------+------+    +------+------+
             |      |      |    |      |      |
           Proj1  Proj2  Proj3  Proj4  Proj5  Proj6
             ^                    ^
             |                    |
         /sync (root-level)   /sync (root-level)
         pushes FROM template  pushes FROM template
         TO project            TO project
```

Three sync operations exist:

1. **BUILD -> Template** (coc-sync agent, push): Runs in BUILD repo during /codify. Transforms and pushes artifacts to COC template repos.
2. **Template -> Template** (/sync command in template, pull): Runs in COC template repo. Pulls latest from BUILD, applies transforms, updates manifest. THIS IS WHAT THIS DESIGN ADDS.
3. **Template -> Project** (/sync command at root level, push): Runs at ~/repos level. Pushes artifacts from COC template to target project repos. Already exists.

Operation 2 is the missing link. Without it, the COC template can only be updated by someone with a session open in the BUILD repo. With it, anyone maintaining the COC template can pull updates independently.
