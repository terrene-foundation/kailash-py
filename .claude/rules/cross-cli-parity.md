---
priority: 10
scope: path-scoped
paths:
  - "**/.claude/rules/**"
  - "**/.claude/variants/**"
---

# Cross-CLI Parity Meta-Rule

<!-- slot:neutral-body -->

Loom emits the same underlying artifact (rule / agent / skill / command) to three CLI targets (CC, Codex, Gemini). Parity means: the semantic content users depend on is identical across all three; only the delegation syntax and surface format differ. This rule defines what MUST match and what MAY diverge so the cross-CLI drift audit has a deterministic contract.

Parity violations don't fail at emit time — they fail at user time, when a rule shipped to Codex is quietly weaker than the same rule shipped to CC.

Origin: (loom-internal reference) §4.5 + §6.2 `cli-orchestrator.sees` verb, authored after round-2 portability reviewer flagged missing contract.

## MUST Rules

### 1. Neutral-Body Slot Content Is Invariant Across CLI Emissions

The `neutral-body` slot MUST be byte-identical (modulo whitespace normalization) across every CLI emission of the same rule. Drift in this slot HARD BLOCKS sync.

```markdown
# DO — neutral-body is identical; only examples slot diverges

<!-- slot:neutral-body -->

Every bulk operation MUST log per-row failures at WARN level.

<!-- /slot:neutral-body -->

<!-- slot:examples -->

(CC variant) (Codex variant) (Gemini variant)
`python                      `python `python
Agent(                         codex_agent(                   {{ @specialist }}
  subagent_type="dataflow"     agent="dataflow"               (dataflow-specialist)
)                              )                              `

# DO NOT — CLI-specific carve-outs in neutral-body

<!-- slot:neutral-body -->

Every bulk op MUST log at WARN. On Codex, this applies only to mutating tools.

<!-- /slot:neutral-body -->
```

**BLOCKED rationalizations:**

- "Codex doesn't support that, just weaken the rule there"
- "The neutral body is close enough, one-word delta is fine"
- "We'll harmonise on the next sync"

**Why:** Asymmetric rule strength across CLIs means a user who tests compliance on CC sees a green check, ships to Codex, and finds the rule silently relaxed. Users cannot audit across CLIs; the emitter is the audit. Drift in neutral-body is the failure mode this rule exists to prevent.

### 2. Examples Slot May Diverge; Drift Emits SOFT WARN

The `examples` slot is explicitly divergent across CLIs (CC uses `Agent(...)`, Codex uses native delegation, Gemini uses `@specialist`). Drift here produces a warning, not a block. Drift in ANY other slot is a hard block.

```yaml
# DO — parity_enforcement declares which slots may diverge
parity_enforcement:
  cross_cli_drift_audit:
    fail_on_drift_in_slots:
      ["neutral-body", "frontmatter.priority", "frontmatter.scope"]
    warn_on_drift_in_slots: ["examples"]
    scrub_tokens: ["Agent(", "subagent_type", "codex_agent(", "@specialist"]

# DO NOT — accept drift silently in non-examples slots
# (no warn_on_drift entry for "origin-extended" — drift there SILENTLY merges)
```

**Why:** Examples diverge by design; the drift audit must distinguish expected divergence from regression. Without the slot allowlist, every `/sync` produces noise that operators learn to ignore — and the real drift hides in the noise.

### 3. Frontmatter Priority + Scope Are Identical Across CLIs

A rule's `priority:` and `scope:` frontmatter values MUST match on every CLI emission. A rule cannot be CRIT baseline on CC and path-scoped on Codex for the same underlying file. Drift here is a hard block.

```yaml
# DO — rule ships at priority:0, scope:baseline everywhere
priority: 0
scope: baseline
# → AGENTS.md baseline, CLAUDE.md always-on, GEMINI.md always-on

# DO NOT — different scope per CLI
# variants/codex/rules/foo.md frontmatter: { scope: path-scoped }
# global rules/foo.md frontmatter: { scope: baseline }
```

**Why:** Different scopes across CLIs produce different always-on surfaces; a rule the user relies on everywhere becomes present-sometimes on Codex. Scope is a compositional invariant; variants MUST NOT override it.

### 4. Scrub Tokens Cover Delegation Syntax, Not Semantic Content

The `scrub_tokens` list in `parity_enforcement.cross_cli_drift_audit` exists to eliminate false-positive drift from delegation syntax (CC: `Agent(`, Codex: `codex_agent(`, Gemini: `@specialist`). It MUST NOT be extended to semantic phrases.

```yaml
# DO — scrub syntactic tokens only
scrub_tokens: ["Agent(", "subagent_type", "run_in_background", "codex_agent(", "@specialist"]

# DO NOT — scrub semantic content to silence a drift finding
scrub_tokens: ["MUST", "never", "always", "WARN"]  # hides real drift
```

**BLOCKED rationalizations:**

- "Adding MUST to scrub_tokens silences the noisy finding"
- "The semantic difference is intentional; scrubbing is the clean fix"
- "We can tune this later"

**Why:** Scrubbing semantic tokens turns the drift audit into a null check. The finding it silences is exactly the finding it exists to produce. Extend `warn_on_drift_in_slots` if a whole slot is expected to diverge — never the token list.

## MUST NOT

- Ship a CLI-specific weakening of a rule under the guise of "equivalent"

**Why:** "Equivalent" is the excuse that turns parity into drift; the audit treats byte-identity + scrub as the contract.

- Disable the drift audit to unblock a sync

**Why:** A disabled audit produces no findings; the drift ships silently and is unrecoverable once downstream repos pull it.

Origin: (loom-internal reference) §4.5 + §6.2 + round-2 aggregate `04-validate/10-round-2-aggregate.md`.

<!-- /slot:neutral-body -->
