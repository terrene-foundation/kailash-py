---
name: cc-audit
description: "Audit project artifacts for quality, completeness, effectiveness, and template alignment"
---

# CC Artifact Audit

Reviews artifacts for quality and template alignment.

## BUILD vs USE Repo Distinction (what gets audited?)

Audit scope depends on repo type:

- **BUILD repos** (kailash-py, kailash-rs, kailash-prism — source of truth): Audit **canonical locations** — `agents/frameworks/`, `agents/analysis/`, `skills/01-core-sdk/`, `skills/NN-name/`, `rules/*.md`, `commands/*.md`. BUILD repos MUST NOT have `agents/project/` or `skills/project/` — those are a USE-repo convention.
- **USE/downstream project repos** (consumer projects): Audit `agents/project/`, `skills/project/` — project-specific local artifacts. Shared artifacts from the template are checked for drift (template wins on next `/sync`).

This repo is a BUILD repo. Audit canonical locations.

## Your Role

Specify scope: `all`, `fidelity` (quality only), `sync` (template alignment only), or a specific file/type.

## Phase 1: Fidelity Audit

1. **Inventory**: List canonical artifacts (`agents/**/*.md`, `skills/**/*.md`, `rules/*.md`, `commands/*.md`) with line counts.

2. **Four-dimension audit** per artifact:
   - **Competency**: Precise instructions? Knows its domain?
   - **Completeness**: Edge cases? Missing handoffs?
   - **Effectiveness**: Reliable behavior? Output format specified?
   - **Token Efficiency**: Lean? No redundancy?

3. **Hard limits** (cc-artifacts rules):
   - Agent descriptions under 120 chars with trigger phrases
   - Agents under 400 lines, commands under 150 lines
   - CLAUDE.md under 200 lines
   - Rules have DO/DO NOT examples and Why rationale

4. **Cross-reference check**: Every referenced artifact exists on disk.

## Phase 2: Template Alignment

5. **Freshness**: Check `.coc-sync-marker` — when was the last sync from the upstream template? If stale, recommend running `/sync`.

6. **Shared artifact integrity**: Are shared artifacts (from template) still intact, or have they been locally modified? Local modifications to shared files will be overwritten on next `/sync`.

7. **Hook integrity**: Every hook in settings.json has a script on disk.

## Phase 3: Report + Convergence

Report findings as CRITICAL/HIGH/NOTE. Run iteratively until zero CRITICAL and zero HIGH.
