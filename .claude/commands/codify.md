---
name: codify
description: "Load phase 05 (codify) for the current workspace. Update existing agents and skills with new knowledge."
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context (this is the user's input surface)

## Phase Check

- Read `workspaces/<project>/04-validate/` to confirm validation passed
- Read `docs/` and `docs/00-authority/` for knowledge base
- Output: update existing agents and skills in their canonical locations (e.g., `agents/frameworks/`, `skills/01-core-sdk/`, `skills/02-dataflow/`, etc.)

## Execution Model

This phase executes under the **autonomous execution model** (see `rules/autonomous-execution.md`). Knowledge extraction and codification are autonomous — agents extract, structure, and validate knowledge without human intervention. The human reviews the codified output at the end (structural gate on what becomes institutional knowledge), but the extraction and synthesis process is fully autonomous.

## Workflow

### 0. Acquire codify lease (multi-operator concurrency gate)

Per `workspaces/multi-operator-coc/02-plans/01-architecture.md` §7.1: two concurrent `/codify` invocations clobber the rule corpus. Acquire the lease BEFORE any step below.

Call `acquireCodifyLease({ scopeFiles, displayId })` from `.claude/hooks/lib/codify-lease.js`. The helper unions `.claude/learning/learning-codified.json` + `.claude/.proposals/latest.yaml` into the scope automatically. `displayId` comes from `operator-id.js::resolveIdentity()`.

On `{ ok: false, reason: "conflict" }`: STOP, surface the conflicting `display_id` + acquired_at + scope overlap to the user verbatim. Silent proceed is BLOCKED (`rules/zero-tolerance.md` Rule 3).

On `{ ok: true, lease, branch }`: create/switch to `codify/<display_id>-<date>`; all edits this session lands there; end-of-session opens a PR + admin-merge per `coc-sync-landing.md` MUST-3; then `releaseCodifyLease({ repoDir, displayId })` (the helper derives the leasePath from `repoDir` internally per Sec-MED-3 — callers cannot misroute the release write). For MUST-clause rule changes the orchestrator additionally requires a signed `[ack: <rule-id>]` from the user before merge (consumed by `multi-operator-sessionstart.js`).

### 1. Consume learning digest

Before extracting new knowledge, integrate what the learning system has captured:

1. Read `.claude/learning/learning-digest.json` — the structured summary of recent observations
2. Read `.claude/learning/learning-codified.json` — what was previously codified (avoid re-processing)
3. Read recent journal entries referenced in the digest (`decisions` array) — DECISION and DISCOVERY entries contain semantic context
4. Read `.session-notes` — latest session accomplishments and outstanding items

Analyze the digest for actionable findings:

- **Corrections** → Do any rules or skills need updating to match user preferences? Each correction is a real signal where the user pushed back on an approach.
- **Error patterns** → Should any recurring rule violations become new rule sections (DO/DO NOT with examples)?
- **Decisions** → Should any architectural decisions from journals become agent or skill knowledge?
- **Accomplishments** → Do any completed features need documentation in skills?

For each finding, either:

- Update an existing rule (add DO/DO NOT with example and Why)
- Update a skill's SKILL.md or sub-files
- Update an agent's knowledge section
- Skip (not worth codifying — explain why)
- **Re-validate deferred items** (per `rules/value-prioritization.md` MUST-3): inherited items lacking a value-anchor MUST surface "lacks value-anchor — current value?" rather than re-list on faith. Items ≥2 sessions stale → "still wanted?" gate. Silent inheritance across `/clear` is BLOCKED.

After processing, write `.claude/learning/learning-codified.json` recording `last_codified` (ISO ts), `digest_hash` (sha256 of digest), and `actions_taken[]` (each entry: `{type, file, reason}` — types include `rule_update`, `skill_update`, `agent_update`, `team_memory_promote`).

This closes the feedback loop: observe → digest → **codify into real artifacts**.

### 2. Deep knowledge extraction

Using as many subagents as required, peruse `docs/`, especially `docs/00-authority/`, and `specs/` for domain specifications.

- Read beyond the docs into the intent of this project/product
- Read `specs/` to understand the detailed domain truth — specs contain the nuanced decisions, contracts, and constraints that should inform agent and skill updates
- Understand the roles and use of agents, skills, docs:
  - **Agents** — What to do, how to think about this, following procedural directives
  - **Skills** — Distilled knowledge for 100% situational awareness
  - **`docs/`** — Full knowledge base
  - **`specs/`** — Detailed domain specifications (authority on what the system does)

### 3. Update existing agents

Improve agents in their canonical locations.

- Reference `rules/cc-artifacts.md` for agent format (desc <120 chars, body <400 lines, frontmatter + trigger phrases); see `agents/frameworks/ml-specialist.md` as an example
- Identify which existing agent(s) should absorb the new knowledge
- If no existing agent covers the domain, create a new agent in the appropriate directory

### 4. Update existing skills

Improve skills in their canonical locations.

- Reference `.claude/guides/claude-code/06-the-skill-system.md` for skill format
- Update the directory's `SKILL.md` entry point to reference new files
- Skills must be detailed enough for agents to achieve situational awareness from them alone

### 4b. Promote team-memory facts (multi-operator repos)

If the digest surfaced a team-stable, non-secret fact ≥2 operators benefit from (shared convention, terminology binding, cross-repo path), draft a `.claude/team-memory/<topic-slug>.md` per `.claude/team-memory/README.md` (split rule: one file per fact). The frontmatter's signed-attribution fields (`promoted_by`, `signed`, `body_anchor`) are populated by `.claude/hooks/lib/coc-append.js` at merge time — leave them `pending`/`false` in the draft. The file lands on the codify lease branch alongside the other Step 3/4 edits and is validated by `integrity-guard.js` on every read.

### 5. Update README.md and documentation (MANDATORY)

Ensure user-facing documentation reflects new capabilities. Verify README.md, docstrings, and docs build.

### 6. Red team the agents and skills

Validate that generated agents and skills are correct, complete, and secure. **cc-architect** verifies cc-artifacts compliance (descriptions under 120 chars, agents under 400 lines, commands under 150 lines, rules path-scoped, SKILL.md progressive disclosure). **Self-referential gate (MANDATORY, posture-independent):** before drafting convergence, match every file the proposal touches against `rules/self-referential-codify.md` Rule 2's allowlist; ANY match → the multi-agent redteam-with-tests round (that rule's Rule 1: reviewer + security-reviewer + structural-validator, parallel) is MANDATORY regardless of trust posture. Run this check from here — `self-referential-codify.md` is `scope: path-scoped` and may not be in context at framing time; this always-loaded command body is the structural guarantee the gate is evaluated before convergence is decided.

### 6b. Trust Posture Wiring (MANDATORY for new rules — ENFORCED)

Per `rules/trust-posture.md` MUST 7 + `skills/32-trust-posture/codify-integration.md`:

For each NEW rule authored in this codify cycle (grandfathered rules pre-dating the trust-posture system are exempt):

1. **Read** `.claude/learning/violations.jsonl` (last 30 days). Find self-reported / detected violations whose `addressed_by` is null AND whose root cause matches the candidate rule.
2. **Link** the rule to those violations: update `addressed_by: "rules/<file>.md@<sha>"` for each.
3. **Author** a "Trust Posture Wiring" section per the canonical 8-field template at `rules/trust-posture.md` MUST Rule 8 (Severity, Grace period, Cumulative posture impact, Regression-within-grace, Receipt requirement, Detection mechanism, Violation scope, Origin). Fields MUST appear in that order; the literal token `**Violation scope:**` is the cc-architect mechanical-sweep anchor.
4. **Append** to `.claude/learning/posture.json::pending_verification` (via `state-io.js::writePosture`) — never via direct Edit/Write (denied by `permissions.deny`).
5. **Verify** via cc-architect: every new rule file ends with `## Trust Posture Wiring`. Missing → audit FAIL → /codify halts and reports.

**ENFORCEMENT**: this step is FAIL-on-missing for any rule authored after `rules/trust-posture.md` was committed. cc-architect MUST grep each new rule file for the literal `## Trust Posture Wiring` header AND verify all 8 canonical fields present in the section body in this order (Severity / Grace period / Cumulative posture impact / Regression-within-grace / Receipt requirement / Detection mechanism / Violation scope / Origin). Missing or incomplete → audit FAIL → /codify halts. The mechanical anchor is `grep -L 'Violation scope:'` per `rules/trust-posture.md` MUST Rule 8.

The trust-posture rule itself is the only grandfather exception. Every other rule authored from this point forward MUST include the wiring section.

### 7. Create upstream proposal (routed by repo class)

Detect repo class (four-row mutually-exclusive precedence per `rules/artifact-flow.md` § "Issue Routing By Change Type" — first matching signal wins). USE-template origination schema (Step 7b) is self-contained in the synced skill `skills/30-claude-code-patterns/sync-flow.md` § "USE-Template Proposal Schema (Step 7b)" — use that in USE-template context; `guides/co-setup/09-proposal-protocol.md` carries the same schema plus full rationale but is loom-only (`use_excluded`) and MUST NOT be relied on as the schema authority where it is absent. Manifests emit `origin: build | use-template | loom` explicitly; append-not-overwrite per `rules/artifact-flow.md`.

1. **loom** (`loom` in git remote AND `.claude/sync-manifest.yaml` exists) → Step 8 (loom→atelier; CC/CO-tier).
2. **USE-template** (`kailash-coc-*` in git remote OR `.claude/VERSION::type == "coc-template"`) → Step 7b (USE-template→loom; COC-artifact only; mechanical wrong-lane glob-check enforced per Step 7b).
3. **BUILD** (`kailash-py`/`kailash-rs`/`kailash-prism` in git remote OR `pyproject.toml`/`Cargo.toml::name` is exact `kailash` or sub-package) → Step 7a (BUILD→loom; SDK code; cross-SDK-FIRST).
4. **Downstream** (`.claude/VERSION::type == "coc-project"`, NOT `coc-template`) → SKIP; artifacts stay local.

## Agent Teams

**Knowledge extraction team:**

- **analyst** — Identify core patterns + distill requirements into reusable agent instructions
- `co-reference` skill — Ensure agents and skills follow COC five-layer architecture (codification IS Layer 5 evolution)

**Creation team:**

- **reviewer** — Validate skill examples are runnable + review agent/skill quality before finalizing

**Validation team (red team the agents and skills):**

- **cc-architect** — Verify cc-artifacts compliance: descriptions <120 chars, agents <400 lines, commands <150 lines, rules have `paths:` frontmatter, SKILL.md progressive disclosure, no CLAUDE.md duplication
- **gold-standards-validator** — Terrene naming, licensing accuracy, terminology standards
- **testing-specialist** — Verify code examples + probe-coverage on harness changes (`rules/probe-driven-verification.md` MUST-4)
- **security-reviewer** — Audit agents/skills for prompt injection, insecure patterns, secrets exposure

### Journal (MUST — phase-complete gate)

Before reporting `/codify` complete, create `/journal new <TYPE> <slug>` entries for: **DECISION** (which rules/skills/agents were updated and why), **DISCOVERY** (patterns extracted into institutional knowledge that the next session should inherit). Skip only if nothing is journal-worthy; do not batch.
