---
priority: 10
scope: path-scoped
paths:
  - "**/.claude/variants/**"
  - "**/.claude/rules/**"
---

# Variant Authoring Meta-Rule

<!-- slot:neutral-body -->

Loom's variant system has two axes: **language** (`py`/`rs`/`rb`/`prism`) and **CLI** (`cc`/`codex`/`gemini`). Variant files overlay global artifacts at sync time. This rule defines how overlays MUST be authored so the composed output stays correct across all target matrix cells.

Authoring a variant wrong doesn't fail at author time — it fails at emit time across every downstream USE template. One bad overlay desynchronises N × M targets.

Origin: `workspaces/multi-cli-coc/02-plans/04-loom-multi-cli-spec-v3.md` §3, authored after round-2 convergence flagged a missing contract.

## MUST Rules

### 1. Variants Are Slot Replacements, Not Whole-File Replacements

A variant file MUST contain ONLY slot-keyed replacement bodies, never a full alternate copy of the global source. Slot markers (`<!-- slot:examples -->` … `<!-- /slot:examples -->`) anchor at column 0, outside fenced code blocks.

````markdown
# DO — variant file contains ONLY divergent slots

<!-- slot:examples -->

```rust
// Rust-specific example
let db = DataFlow::new(...);
```

<!-- /slot:examples -->

# DO NOT — variant file is a full copy with 5% diff

# Variant Authoring Meta-Rule

Loom's variant system has two axes...
[entire file re-emitted]
````

**Why:** Full-file variants silently drift from global as the global evolves; composed output diverges and nobody notices until a rule stops matching reality. Slot overlays keep divergence localized and diff-able.

### 2. Ternary Overlay Applies Only To Content-Divergent Primitives

Three-axis (language × CLI) overlay is reserved for rules whose examples reference a CLI-native delegation primitive AND differ across languages simultaneously. The current classification:

- **CLI + language divergent (ternary — `variants/<lang>-<cli>/rules/`)**: `agents.md`, `worktree-isolation.md`. Both files contain `Agent(...)` delegation calls AND language-specific paths (`packages/<pkg>/src/*.py` vs `packages/<pkg>/src/*.rs`) or tooling (`pytest`/`pip` vs `cargo check`/`cargo tree`).
- **CLI-only divergent (binary — `variants/<cli>/rules/`)**: `specs-authority.md`. Contains `Agent(...)` delegation syntax but no language-specific content; one overlay per CLI serves all languages.
- **Language-only divergent (binary — `variants/<lang>/rules/`)**: `agent-reasoning.md`, `framework-first.md`. Examples use Kaizen framework classes (`BaseAgent`, `ReActAgent`) whose identifiers differ by language but not by CLI runtime.

Adding a new `variants/<lang>-<cli>/` tree for a rule not in the ternary classification above is BLOCKED without an updated spec + classification.

```markdown
# DO — ternary when both axes diverge

variants/py-codex/rules/agents.md # Codex-native delegation syntax, Python paths
variants/py-gemini/rules/agents.md # Gemini-native delegation syntax, Python paths

# DO — CLI-only when only CLI axis diverges

variants/codex/rules/specs-authority.md # delegation syntax only; paths are generic

# DO NOT — invent a ternary tree for a rule whose examples have no CLI-native primitive

variants/py-codex/rules/zero-tolerance.md # zero-tolerance has a neutral body; it emits globally
```

**BLOCKED rationalizations:**

- "The rule has a CC-style example, just ternary-overlay it"
- "We'll classify it later"
- "It'll be faster than rewriting the example block neutrally"

**Why:** Each new ternary rule multiplies sync complexity and drift surface. A neutral body + per-CLI `examples` slot overlay satisfies 95% of divergence cases at 1/3 the maintenance cost. Empirical audit on 2026-04-22 of the five rules previously blanket-classified as RED found only 2 are truly ternary; 1 is CLI-only; 2 are language-only. Mis-classification would have produced 10 redundant overlay files across the codex and gemini axes.

### 3. Frontmatter Merges Per Declared Strategy, Not Per Author Guess

List fields use explicit merge strategies declared in `sync-manifest.yaml`: `tools` and `paths` = **union**; `mcp_servers` = **deep-merge**; `priority`, `scope`, `tier` = **replace** (variant wins). Scalars default to replace. Authors MUST NOT rely on implicit merge behavior.

```yaml
# DO — global
tools: [Read, Write]
# DO — variant (merged result: [Read, Write, Edit])
tools: [Edit]

# DO NOT — variant attempts to "remove" a global tool
tools: [Read]  # merge is union; Write is still present
```

**Why:** Implicit merge guesses diverge across authors; a global-tools list that grows in main silently breaks variants that relied on "last-wins." Explicit strategy per field makes the composed output deterministic.

### 4. Three Overlay Axes — Use The Narrowest That Covers Your Divergence

Variant overlay files live under one of three tree shapes. Pick the narrowest tree that covers your actual divergence — broader placement wastes sync cost and invites drift.

| Tree                           | Axis           | When to use                                                                                                                        |
| ------------------------------ | -------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `variants/<lang>/rules/`       | language-only  | Rule body differs by language (py vs rs vs rb). Examples: Python/Rust-specific Why lines, FFI semantics, runtime lifecycle quirks. |
| `variants/<cli>/rules/`        | CLI-only       | Rule body is language-invariant but the CLI native primitive differs (Agent vs codex_agent vs @specialist). Examples slot only.    |
| `variants/<lang>-<cli>/rules/` | ternary (both) | Divergence is both language AND CLI (e.g., rs-codex worktree-isolation that couples Rust paths with Codex delegation syntax).      |

Composition precedence per `.claude/bin/emit.mjs::composeRule` — applied in this order, each overlay stacked on the previous:

1. `global` (`.claude/rules/<rule>.md`)
2. `variants/<lang>/rules/<rule>.md` (language-axis)
3. `variants/<cli>/rules/<rule>.md` (CLI-axis)
4. `variants/<lang>-<cli>/rules/<rule>.md` (ternary)

```markdown
# DO — language-only (rs licensing semantics)

variants/rs/rules/independence.md

# DO — CLI-only (Codex syntax in examples slot)

variants/codex/rules/specs-authority.md

# DO — ternary (Rust paths + Codex delegation syntax)

variants/rs-codex/rules/worktree-isolation.md

# DO — wrappers are CLI-only (language-invariant tooling)

variants/codex/wrappers/coc-analyze.sh.template

# DO NOT — duplicate a CLI-only overlay across languages

variants/py-codex/wrappers/coc-analyze.sh.template
variants/rs-codex/wrappers/coc-analyze.sh.template # same content — should be variants/codex/

# DO NOT — use a ternary tree when only one axis actually differs

variants/py-codex/rules/zero-tolerance.md # zero-tolerance's neutral body is CLI-invariant and language-invariant → stays global
```

**Why:** Duplicate overlays become drift surface the moment one is touched without the other. The three-axis system lets `emit.mjs` compose each axis independently — a CLI-only wrapper inherits across languages, a language-only rule inherits across CLIs, and the ternary tree is reserved for truly dual-axis divergence. Collapsing all divergence into ternary (historical pre-F4 pattern) multiplies maintenance cost and silently desynchronises the N × M target matrix.

**Reference implementation:** `.claude/bin/emit.mjs::composeRule` (v6.1, Phase I2 2026-04-22) — previous versions lacked the language-axis step, which shipped the global rule body into e.g. `kailash-coc-rs/AGENTS.md` instead of the rs-specific override (affected `independence.md`, `agents.md`). The language-axis step closes that semantic drift.

## MUST NOT

- Edit the global file to add a CLI-specific example

**Why:** Global files are the neutral-body source; adding CLI-specific content there breaks the parity contract and triggers cross-CLI drift audit.

- Use `variants/<cli>/` as a dumping ground for "will resolve later"

**Why:** Unresolved variants accumulate; /sync distributes them unchanged; downstream repos inherit the mess.

Origin: `workspaces/multi-cli-coc/02-plans/04-loom-multi-cli-spec-v3.md` §3 + round-2 aggregate `04-validate/10-round-2-aggregate.md`.

<!-- /slot:neutral-body -->
