---
type: DECISION
date: 2026-04-25
created_at: 2026-04-25T18:45:00Z
author: agent
project: kailash-ml-audit
topic: codify two new MUST rules from kaizen 2.13.1 hotfix cycle
phase: codify
tags:
  [
    codify,
    rules,
    dependencies,
    build-repo-release-discipline,
    clean-venv,
    kaizen-2-13-1,
  ]
---

# DECISION — Codify **init**.py import-guard rule + latent-failure clean-venv clause

## What

Two rule edits land this codify cycle, both Origin-tagged to the kaizen 2.13.0→2.13.1 hotfix (commit `9002c002`, 2026-04-25):

1. **`rules/dependencies.md`** — new MUST sub-rule `__init__.py` Module-Scope Imports Honor The Manifest, sitting inside `§ Declared = Imported`. Mandates `try/except ImportError` with `else`-branch side-effects for any module-scope import of a co-installed-but-NOT-declared sibling package. Distinct from the existing BLOCKED `redis = None` silent-fallback anti-pattern: the optional-proxy pattern has NO later use site that could break.
2. **`rules/build-repo-release-discipline.md`** — Rule 2 (PyPI Installability Is The Done Gate) extended with a "Latent failures count" clause. When the clean-venv check fails, the broken pattern is the scope of the hotfix, NOT just the most-recent PR's diff. Cross-references the dependencies.md sub-rule as the structural defense.

## Why

The 2.13.0→2.13.1 hotfix exposed two latent gaps in the existing rule set:

- **Gap A**: `dependencies.md` § Declared = Imported was silent on the `__init__.py` proxy-alias case. The existing BLOCKED list covered `redis = None` silent fallbacks but did not codify the legitimate `try/except ImportError: pass / else: sys.modules.setdefault(...)` pattern. Without the rule, future contributors had no structural defense against unconditional cross-package `__init__.py` imports.
- **Gap B**: `build-repo-release-discipline.md` Rule 2 mandated the clean-venv check but did not codify what to do when the check fails. The default agent behavior was "fix what THIS PR introduced" — which would have left 3 of 4 broken `kaizen_agents.*` imports in main (only #602 added the new one; the other 3 predated refactor #75).

Both rules are existing-rule extensions (not new files). Both are language-neutral at the principle level; the example anchor is Python-specific syntax. Both proposed for `global` classification at loom Gate 1.

## Alternatives considered

- **Single new rule file `rules/init-py-imports.md`**: rejected — `dependencies.md` already covers the broader "Declared = Imported" topic; a separate file would split the rationalizations across two locations.
- **Skill update only (no rule)**: rejected — the failure mode is structural (clean-install ImportError), not advisory. Skills suggest; rules forbid. Per `rules/rule-authoring.md` Rule 1, MUST-clauses are the right home.
- **Update `rules/zero-tolerance.md` § Rule 2 (No Stubs) with `__init__.py` import as a stub variant**: rejected — the kaizen pattern is not a stub; it's a misuse of import semantics. The rule belongs with dependency-declaration discipline.

## Consequences

- Future `__init__.py` PRs will be flagged at `/redteam` if they add unconditional cross-package imports of non-declared deps.
- Future hotfix sessions cued by clean-venv failure will know to widen the fix to the broken pattern, not the latest-PR diff.
- Cross-SDK: kailash-rs's `mod.rs` re-export pattern has the same latent failure mode (`use other_crate::*` in a workspace member without a Cargo.toml dep, only resolvable via path-dep). The proposal classification is `global` so loom Gate 1 routes the rule to all language variants.

## For Discussion

1. The new dependencies.md sub-rule explicitly PERMITS `try/except ImportError: pass` for optional proxies — but the BLOCKED list a few lines below still says `try: import redis except ImportError: redis = None` is BLOCKED. The discriminator is "alias side-effect with no later use site" vs "fallback to None with later use site". Is this distinction crisp enough that a future reader gets it right, or should we refactor both clauses into a unified taxonomy?
2. Counterfactual: if Rule 2 of `build-repo-release-discipline.md` had INCLUDED the latent-failure clause in 2026-04-04 when the rule was first authored, would 3 of the 4 kaizen_agents imports have been fixed at that time? `git log --grep "kaizen.orchestration"` shows the imports landed in refactor #75 (2026-03-12) — 23 days before the rule was authored. The rule didn't exist when the imports were merged; the rule when applied at the next clean-install verification IS what would have caught them. Lesson: rules are forward-looking defenses; the latent-failure clause is the structural mechanism that converts "rule didn't exist when this was merged" into "rule catches it now".
3. The Origin lines for both rules cite a single commit (`9002c002`) and a single hotfix. Per `rules/rule-authoring.md` Rule 6, that's sufficient — but both rules generalize a class of failure that we've seen analogues of (BP-049 multi-site kwarg plumbing, Phase 5.11 orphan trust executor, the 2026-04-19 `__all__` reconciliation). Should the Origin lines reference the broader pattern as well, or keep the single load-bearing incident?
