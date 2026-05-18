# Wave 5 — Portfolio-Wide Spec Audit

## Why

Wave 3 audited only the 6-PR bundle (#622–#629). The full `specs/` directory has 72 files / ~40k LOC across 17 domains. Many of these specs predate or post-date Wave 3 in-flight edits and have never been mechanically verified against `src/` + `packages/`. Recent Wave 4 + Wave 3 work touched only `trust-crypto.md`, `mcp-auth.md`, `dataflow-models.md` — the other 69 specs are untouched-but-unverified.

`rules/specs-authority.md` § 4 says phases MUST read specs before acting. Specs are the contract. Drift between spec and code = silent broken contract = production bug class on the next downstream feature that consumes the wrong contract.

## Goal

Produce a portfolio-wide audit per `skills/spec-compliance/SKILL.md`. For every § N.M acceptance assertion across all 72 specs, AST/grep verify the symbol/contract/threat exists in code. Findings filed by domain under `workspaces/portfolio-spec-audit/04-validate/<domain>-findings.md` with severity (CRIT/HIGH/MED/LOW) and remediation pointer.

## Sharding

17 domains → ~6 shards (≤3 parallel per `rules/worktree-isolation.md` Rule 4). Each shard one specialist agent with Edit + Bash. Wave size 3, run sequentially in 2 waves.

| Shard | Domain                                                                                                                            | Specs | Owner specialist                               |
| ----- | --------------------------------------------------------------------------------------------------------------------------------- | ----- | ---------------------------------------------- |
| W5-A  | core (4) + infra (2) + node-catalog (1)                                                                                           | 7     | pattern-expert                                 |
| W5-B  | dataflow (5) + dataflow-cache, models, ml-integration                                                                             | 5     | dataflow-specialist                            |
| W5-C  | nexus (5) + middleware + nexus-ml-integration                                                                                     | 5     | nexus-specialist                               |
| W5-D  | kaizen (13) + kaizen-ml-integration                                                                                               | 13    | kaizen-specialist                              |
| W5-E  | ml (16) + align (4) + align-ml-integration + diagnostics-catalog                                                                  | 22    | ml-specialist + align-specialist (split E1/E2) |
| W5-F  | trust (3) + pact (5) + pact-ml-integration + security (3) + mcp (3) + scheduling + task-tracking + edge-computing + visualization | 18    | pact-specialist + mcp-specialist (split F1/F2) |

## Per-shard contract

Every shard agent MUST:

1. Read spec `_index.md` + every spec in its assigned domain
2. For every § N.M subsection, enumerate the acceptance assertions (symbols claimed to exist, BLOCKED patterns, security threats, contract signatures)
3. AST/grep `src/` + `packages/` for each assertion
4. Classify each finding:
   - **CRIT** — security/governance contract claimed but absent (orphan facade per `rules/orphan-detection.md` §1)
   - **HIGH** — public API claimed but absent or signature-divergent
   - **MED** — internal helper or utility claimed but absent
   - **LOW** — naming/terminology drift, doc-only assertions
5. Write findings to `workspaces/portfolio-spec-audit/04-validate/W5-<shard>-findings.md` with:
   - Spec file + § reference
   - Expected symbol/contract
   - Actual code state (or absent)
   - Severity + remediation hint
6. Commit incrementally (per `rules/agents.md` § "MUST: Worktree Agents Commit Incremental Progress")

## Worktree + isolation

Each shard runs with `isolation: "worktree"` per `rules/worktree-isolation.md`. Branch naming: `audit/w5-<shard>-spec-audit`. Pre-flight merge-base check against `main` HEAD before launch.

## Output

Aggregated report: `workspaces/portfolio-spec-audit/04-validate/00-portfolio-summary.md` listing all CRIT + HIGH findings cross-domain, ranked by blast radius. Becomes input to Wave 6 (remediation).

## What is NOT in scope

- Implementation of fixes (Wave 6's job)
- Test additions (Wave 6's job)
- Spec rewrites (only update specs if §6 deviation is found)
- Cross-SDK kailash-rs parity audit (separate workstream — already deferred to next /sync cycle)

## Convergence criteria

- All 6 shards push branches with findings files
- 00-portfolio-summary.md aggregates cross-shard
- Reviewer + analyst + gold-standards-validator review summary (background, parallel)
- Human approves Wave 6 remediation scope from summary

## Origin

Session note 2026-04-26 — `/codify` complete on Wave 3+4 bundle. Portfolio boundary doc flagged this as deferred Wave 5 work. Loom is currently running `/sync` on the 2 new MUST rules (specialist tool inventory + sub-package version-bump sweep), so kailash-py work proceeds in parallel.
