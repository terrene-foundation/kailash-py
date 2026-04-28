---
name: cc-audit
description: "Audit project artifacts for quality, completeness, effectiveness, and template alignment"
---

# CC Artifact Audit (Project)

Reviews your repo's artifacts for quality and template alignment. Scope depends on repo type.

## BUILD vs USE Repo Distinction

- **BUILD repos** (kailash-py, kailash-rs, kailash-prism): no `agents/project/` or `skills/project/` directories. Every artifact lives in a canonical location (`agents/frameworks/`, `skills/01-core-sdk/`, etc.) and is subject to the same fidelity checks as loom/. The Phase 1 inventory in a BUILD repo walks ALL artifact directories, not just `project/`.
- **Downstream USE repos** (consumer projects): project-specific artifacts live in `agents/project/` and `skills/project/`. The Phase 1 inventory focuses on these, since shared artifacts are owned by the upstream template and audited at loom/.

If this repo is a BUILD repo, skip the `project/`-only inventory below and audit all canonical artifact directories.

## Your Role

Specify scope: `all`, `fidelity` (quality only), `sync` (template alignment only), or a specific file/type.

## Phase 1: Fidelity Audit

1. **Inventory**:
   - **USE repos**: list project-specific artifacts (`agents/project/`, `skills/project/`) with line counts.
   - **BUILD repos**: list all canonical artifacts (`agents/**/*.md`, `skills/**/*`, `rules/*.md`, `commands/*.md`) with line counts; `agents/project/` and `skills/project/` should not exist.

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
