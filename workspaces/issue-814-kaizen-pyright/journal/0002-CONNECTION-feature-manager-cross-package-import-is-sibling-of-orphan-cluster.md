# CONNECTION: `feature_manager.py:13` Cross-Package Import Is The Same Bug Class As The C1 Orphan Cluster

**Date:** 2026-05-04
**Phase:** /analyze (red-team-surfaced finding F-2)
**Severity:** HIGH — clean-install break that the original cluster reports missed

## Discovery

The /analyze cluster reports correctly identified:

- **C1**: `kaizen/research/__init__.py` re-exports 7 symbols whose backing modules were
  moved to `kaizen-agents` in PR #75 (commit `801de2bb`, 2026-03-25) without updating
  `__init__.py`.
- **C2**: 4 undeclared deps (`arxiv`, `pypdf`, `duckduckgo_search`, `bs4`) used via
  lazy-import sentinels.

The cluster reports **missed** a third instance of the same bug class:

```python
# packages/kailash-kaizen/src/kaizen/research/feature_manager.py:13
from kaizen_agents.research_patterns.experimental import ExperimentalFeature
```

This import is:

- **Module-scope** (executes on first `from kaizen.research import FeatureManager`)
- **Unconditional** (no `try/except ImportError` guard)
- **Cross-package** (depends on `kaizen-agents`)
- **Undeclared** (`kaizen-agents` is NOT in `kailash-kaizen/pyproject.toml::dependencies`
  and not in any `[project.optional-dependencies]` extra)

## Why This Is The Same Bug Class

The C1 orphan and the F-2 cross-package import share the structural failure mode:

> _Code shipped on main expects a sibling package that may or may not be installed; clean
> install raises `ModuleNotFoundError`._

Both mechanisms originate from the same parent commit (`801de2bb`, PR #75 "structural
split — move ~44K lines of L2 engine code to kaizen-agents"). When the source files
moved out of `kailash-kaizen`:

1. **C1 path**: `__init__.py:26-39` re-exports were left dangling — `from .advanced_patterns import ...`
   resolves through the package, hits the missing module, raises `ModuleNotFoundError`.
2. **F-2 path**: `feature_manager.py:13` uses `kaizen_agents.research_patterns.experimental`
   directly. If `kaizen-agents` is not installed (which is the default on a fresh
   `pip install kailash-kaizen[research]`), the import fails the same way.

The two paths are 80 lines apart in the same package. Both ship today. Both break the
same clean-install path. The C1 fix without the F-2 fix is half a fix.

## Why The Cluster Reports Missed It

Cluster C focused on:

- (a) Re-exports in `kaizen.research.__init__.py` (the 3 missing-module imports)
- (b) Lazy-import sentinels in `parser.py` and `search_tools.py` (the 4 undeclared deps)

The grep narrowly covered `kaizen.research/__init__.py` import lines + the `parser.py` /
`search_tools.py` `try: import X / except ImportError` patterns. It did NOT sweep ALL
module-scope imports under `kaizen/research/` for cross-package dependencies on
non-declared packages. The F-2 finding required a broader grep:

```bash
grep -rn "^from kaizen_agents" packages/kailash-kaizen/src/
```

Result:

```
packages/kailash-kaizen/src/kaizen/research/feature_manager.py:13:from kaizen_agents.research_patterns.experimental import ExperimentalFeature
```

## Resolution

Per `rules/autonomous-execution.md` Rule 4 ("Fix-Immediately when same-class gap fits
within shard budget"), F-2 is folded into Shard 2 of the architecture plan (already
amended). Disposition: **DELETE `feature_manager.py`** along with the orphan
`__init__.py` re-exports. `FeatureManager` was part of the same vestigial cluster PR #75
moved out — the only callers are the 5 dead-path tests we're already deleting.

## Cross-Reference

- `04-validate/01-redteam-analyze-gate.md` finding F-2 (full evidence)
- `02-plans/01-architecture.md` § Cluster C1 + Decisions Log entry #11
- `rules/dependencies.md` § "`__init__.py` Module-Scope Imports Honor The Manifest"
- `rules/autonomous-execution.md` MUST Rule 4

## Lesson For Future Sessions

When a "structural split" PR moves source files between packages, the audit MUST sweep
THREE call sites in the donor package, not just one:

1. The `__init__.py` re-export of the moved symbols (the obvious orphan)
2. **Module-scope imports of the moved symbols from sibling files in the donor package**
   ← THE F-2 CASE
3. Tests that import the moved symbols (orphan-detection Rule 4)

The orphan-detection skill's grep pattern should expand from
`grep "from kaizen.research import"` to `grep -rE "^from (kaizen|kaizen_agents)\\.\\S+"`
when auditing intra-monorepo splits.
