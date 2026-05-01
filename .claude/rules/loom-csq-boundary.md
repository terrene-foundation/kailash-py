---
priority: 10
scope: path-scoped
paths:
  - "**/.claude/test-harness/**"
  - "**/.claude/rules/loom-csq-boundary.md"
  - "**/test-harness/fixtures/**"
---

# loom ↔ csq Boundary Rule

This rule fixes the ownership split between loom and csq for COC artifact authoring vs multi-CLI evaluation. It is the loom-side half of a paired rule. The mirror lives at `csq/.claude/rules/csq-loom-boundary.md` (already shipped per csq H12).

Origin: csq journal `workspaces/coc-harness-unification/journal/0004-CONNECTION-csq-loom-symbiotic-boundary.md`; ADR-J in `csq/workspaces/coc-harness-unification/01-analysis/07-adrs.md`; pre-Phase-1 framing in `csq/workspaces/csq-v2/journal/0074-DECISION-csq-as-cli-phase-1-and-2-architecture.md`.

## The split

| Repo     | Owns                                                                                                                                                              | Does NOT own                                                                                                                                 |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **loom** | COC artifact authoring + per-CLI emission (slot composition, 60 KiB cap, parity contract for cc/codex/gemini variants, frontmatter shape).                        | Multi-CLI evaluation (csq is the canonical evaluator post-Phase-1). Loom may keep an authoring-side smoke-test only — never a parity matrix. |
| **csq**  | Multi-CLI evaluation harness at `coc-eval/` (4 suites × 3 CLIs); fixture content (RULE_ID grammar, prompt strings, scoring patterns); capability layer (Phase 2). | COC artifact authoring (loom retains). csq MUST NOT emit `.claude/` artifacts as a generator — only consume them as test inputs.             |

Schema authority disputes resolve **csq for content, loom for format**. Content = what the fixture asserts. Format = how the artifact serializes.

## MUST Rules

### 1. Loom's Test-Harness Stays Authoring-Side Only — Not A Parity Matrix

`loom/.claude/test-harness/` is loom's authoring-side smoke-test. It MUST NOT be expanded into a multi-CLI parity matrix that competes with `csq/coc-eval/`. Adding suite-runners, fixtures, or scoring infrastructure that duplicate csq's harness is BLOCKED.

```
# DO
loom/.claude/test-harness/run-all.sh   — small smoke-test the loom author
                                         runs locally before /sync
loom/.claude/test-harness/README.md    — points at csq/coc-eval/ as the
                                         canonical multi-CLI evaluator

# DO NOT
loom/.claude/test-harness/suites/parity-matrix.mjs  — reimplements csq's
                                                       4-suites-by-3-CLIs job
loom/.claude/test-harness/scoring/                  — duplicate scoring infra
```

**BLOCKED rationalizations:**

- "Loom needs end-to-end coverage; csq's CI can fail"
- "We can keep both in sync manually"
- "Just a temporary parallel matrix until csq stabilises"

**Why:** Two harnesses in two repos is the parallel-infrastructure failure mode csq journal 0074 names by name. Loom becomes a degraded copy of csq; csq downgrades to a deprecated copy of loom; CI maintainers cannot tell which is canonical and run both. The csq half of this paired rule (`csq-loom-boundary.md` Rule 1) blocks csq from owning the authoring side; this half blocks loom from owning the evaluation side. Both halves are required for the boundary to hold.

### 2. Loom's Release Path MUST NOT Depend On csq's CI

Loom's `/sync` and `/release` MUST run against loom-internal validators only. Coupling a loom release gate to a csq CI run (e.g., "block sync until csq's quarterly drift job passes") is BLOCKED. csq's quarterly cadence is csq's audit signal, not loom's pre-flight check.

```
# DO — loom uses its own pre-flight
loom/.claude/test-harness/run-all.sh   — author runs locally pre-/sync
loom CI                                 — emit-validators only
                                          (validator-12 slot round-trip,
                                          validator-13 codex-mcp-guard,
                                          validator-14 rule-frontmatter)

# DO NOT — block loom on csq
loom CI step: ssh csq-runner -- coc-eval/scripts/check-loom-drift.sh
loom CI step: gh workflow run loom-csq-drift.yml --repo csq && wait
```

**BLOCKED rationalizations:**

- "csq's harness covers more than loom's, of course we should run it pre-sync"
- "If csq fails, the loom release would have broken downstream anyway"
- "It's the same author maintaining both, the coupling is virtual not real"

**Why:** Coupling loom's release path to csq's CI is the centralization failure csq journal 0004 §"For Discussion #2" calls out. A vendor outage at csq CI (GitHub Actions, csq runner, network partition) would stall loom releases unrelated to csq's evaluation gradient. Loom's authoring-side smoke-test is sufficient to ship; csq's quarterly drift cadence catches downstream regressions out-of-band.

### 3. test-harness/README.md MUST Cite csq As The Canonical Multi-CLI Evaluator

`loom/.claude/test-harness/README.md` MUST include a top-section pointer at `csq/coc-eval/` as the canonical multi-CLI evaluator. The pointer MUST name csq's harness, link to its repo path, and state explicitly that loom's harness is authoring-side smoke-test only. Pretending the boundary doesn't exist (or burying the pointer beneath the loom harness's quick-start) is BLOCKED.

```markdown
# DO — top-of-README pointer

# COC Multi-CLI Test Harness

> **Canonical multi-CLI evaluator: `csq/coc-eval/`** (not this directory).
> Loom retains this harness as an authoring-side smoke-test only — runs
> against the fixture set the loom author edits. csq's harness runs the
> full 4-suites × 3-CLIs parity matrix and is what downstream contributors
> should consult for empirical claims. See `rules/loom-csq-boundary.md`.

## Quick start

…

# DO NOT — bury the pointer or omit it

# COC Multi-CLI Test Harness

Empirical validation of … [no pointer; reads as if loom's harness IS canonical]
```

**Why:** The boundary is invisible to a contributor who lands at `loom/.claude/test-harness/` first and assumes it's the parity-matrix authority. The README pointer is the single structural defense that makes the split discoverable from the wrong-entry-point side. Without it, csq's H12 work — the entire reason the boundary exists — gets quietly re-confused on every onboarding cycle.

### 4. Loom-Originated Fixture Edits Carry A csq-Side Provenance Marker

When a loom session edits files under `loom/.claude/test-harness/fixtures/` (e.g., updates a fixture to cover a new compliance scenario), the commit message OR PR body MUST include a `# csq-mirror:` line if the fixture has a sibling at `csq/coc-eval/fixtures/`. The line lists the csq path that should adopt the same change in the next csq cycle.

```
# DO (commit body)
fix(test-harness): add `open-source counterpart of X` phrasing class to
CM5-refuse-commercial-reference fixture.

# csq-mirror: csq/coc-eval/fixtures/compliance/CLAUDE.md L42-L51 — adopt
# in csq's next quarterly drift cycle. Loom is the format authority; csq
# is the content authority — this edit is content, so csq leads adoption.

# DO NOT (commit body)
fix(test-harness): tweak compliance fixture for new phrasing class.
```

**BLOCKED rationalizations:**

- "csq will catch the divergence in the quarterly drift job, no need to flag"
- "The csq-side maintainer will see the loom commit"
- "Adding mirror lines to every fixture commit is ceremony"

**Why:** csq's drift-detection allowlist (`csq/coc-eval/loom-diff-allowlist.txt`) requires a `# REASON:` per accepted divergence (`csq-loom-boundary.md` Rule 4). Without a `# csq-mirror:` line in the loom commit, the csq maintainer triaging the next quarterly drift report cannot tell whether a divergence was intentional content evolution or accidental edit; the allowlist entry's reason becomes a guess. The marker is the structural pre-write to that allowlist's audit trail.

### 5. Format Changes At loom MUST Tag The Commit For csq Adoption

When a loom commit changes the COC artifact shape (RULE_ID grammar, slot composition, frontmatter shape, file-layout convention), the commit message MUST include a `# coc-shape:` line naming the change. This is the inverse of csq's Rule 3 (csq adopts within one cycle): the loom-side marker is the signal csq's regression-test author greps for.

```
# DO (commit body)
feat(rules): introduce `scope: skill-embedded` frontmatter value for
rules inlined into a skill's SKILL.md (per v6 §A.1).

# coc-shape: rule-frontmatter scope-enum extended (baseline | path-scoped
# | skill-embedded | excluded). csq MUST land a regression test within
# one cycle per csq-loom-boundary.md Rule 3.

# DO NOT (commit body)
feat(rules): support skill-embedded scope.
# (no coc-shape: line; csq has to discover the change empirically when
# the next emission breaks an existing assertion)
```

**Why:** The shape-change protocol (csq's ADR-J §R1-1) only works if csq can grep `git log --grep="coc-shape:"` to find the commits that need a regression test. Without the marker, csq's regression-test author has to read every loom commit body to find the shape change — an O(N) read where O(1) is available. Same structural-confirmation principle as `git.md` § "Commit-message claim accuracy": the commit body is the cheapest institutional-knowledge surface; it must carry the load-bearing tag.

## MUST NOT Rules

### 1. Loom MUST NOT Add A Multi-CLI Authoring Generator To csq

A loom commit that proposes csq grow an artifact generator — `csq/coc-eval/lib/emit_artifacts.py`, `csq/coc-eval/scripts/regenerate-fixtures.sh`, anything that produces `.claude/`-shape artifacts from coc-eval inputs — is BLOCKED. Generators belong in loom; csq is consume-only.

**BLOCKED rationalizations:** "It would be more convenient if csq could regenerate fixtures" / "Just a one-shot tool" / "csq's harness needs to know the format anyway".

**Why:** Generators in csq become a second emit path; the kailash-coc-claude-{py,rs,rb,prism} family pulls from loom's emit, csq pulls from its own — and the two diverge silently the first time a slot composition changes. Same anti-pattern csq's Rule 1 blocks from the other side; both halves required.

### 2. Loom MUST NOT Mirror csq's Drift-Detection Job

Loom CI MUST NOT add a quarterly job that diffs `loom/.claude/test-harness/fixtures/` against `csq/coc-eval/fixtures/`. csq's `.github/workflows/loom-csq-drift.yml` is the single drift detector; mirroring it on loom's side creates two reports for one signal.

**Why:** Two drift jobs running on different schedules produce two report streams the maintainer reconciles by hand. csq runs the detector; loom is the detected; both halves of a one-direction audit. Adding a loom-side detector inverts the directionality csq journal 0004 selected and burns CI minutes for zero novel signal.

## Cross-References

- `csq/.claude/rules/csq-loom-boundary.md` — paired-rule mirror (csq side)
- `csq/workspaces/coc-harness-unification/journal/0004-CONNECTION-csq-loom-symbiotic-boundary.md` — analysis that motivated the paired rule
- `csq/workspaces/coc-harness-unification/journal/0028-DECISION-h12-loom-csq-boundary-shipped.md` — H12 ship decision (csq side)
- `csq/workspaces/coc-harness-unification/01-analysis/07-adrs.md` ADR-J — original boundary decision + R1 amendments
- `csq/coc-eval/loom-diff-allowlist.txt` — accepted divergences (Rule 4 in csq's mirror)
- `csq/coc-eval/scripts/check-loom-drift.sh` — drift detection script (Rule 4 in csq's mirror)
- `csq/.github/workflows/loom-csq-drift.yml` — quarterly CI cadence (Rule 4 in csq's mirror)
- `loom/.claude/test-harness/README.md` — points at csq/coc-eval/ per Rule 3 above
- Tracking issue: `esperie-enterprise/loom#21` (loom-side mirror; closed by this rule's landing)
