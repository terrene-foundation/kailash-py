# Architecture Plan — Issue #814 (kaizen pyright cleanup)

**Workspace:** `workspaces/issue-814-kaizen-pyright/`
**Issue:** [#814](https://github.com/terrene-foundation/kailash-py/issues/814) `fix(kaizen): resolve pre-existing pyright diagnostics in tools/native + research`
**Status:** /analyze complete; awaiting human gate at /todos.

## TL;DR

Issue #814 enumerates 29 pyright errors + 8 warnings across `kailash-kaizen`. Mechanical
verification confirmed the totals but **substantially undercounted Category A** (brief: 7
sites; pyright: **17 sites**). The undercount is journaled at
`journal/0001-DISCOVERY-brief-undercounts-baseTool-override-sites.md`.

Three parallel verification agents reduced the work to **two clean shards**:

- **Shard 1**: Type-safety sweep — BaseTool contract ratification (17 sites) + Optional/None
  safety (12 issues → 6 root-cause clusters) + 1 real runtime bug at `adapter.py:119` + 1
  Tier 2 regression test. **~170 LOC load-bearing logic, single shard.**
- **Shard 2**: Orphan + dependency cleanup — delete 3 vestigial imports + 7 `__all__`
  entries from `research/__init__.py`, delete `feature_manager.py` (carries unguarded
  cross-package import per red-team finding F-2), delete 5 dead-path test files, add 2
  optional-extras groups (`research`, `web-search`), fix bs4 silent-degradation.
  **~100 LOC, single shard.**

Both shards comfortably fit `rules/autonomous-execution.md` Rule 1 budget (≤500 LOC,
≤5–10 invariants, ≤3–4 call-graph hops, describable in 3 sentences). Pyright provides a
live feedback loop for both shards (Rule 3 multiplier applies). Recommended ship order:
**Shard 1 → Shard 2** (Shard 1 is the high-leverage contract decision; Shard 2 is mechanical).

The release surface is **kailash-kaizen v<next>** — version bump + CHANGELOG entry land
with Shard 2 (BUILD-repo discipline per `feedback_build_repo_release.md`).

## Brief Corrections

Mechanical verification surfaced three brief inaccuracies. All MUST be reflected in /todos
per `rules/agents.md` MUST: Parallel Brief-Claim Verification:

| Brief claim                              | Pyright ground truth                        | Delta    |
| ---------------------------------------- | ------------------------------------------- | -------- |
| Category A: 7 BaseTool override sites    | **17 sites** across 9 files                 | +10      |
| Category B: 4 Optional/None safety sites | 9 issues (5 errors + 4 warnings)            | +5       |
| Category C: ~7 missing-import sites      | 7 errors + 1 warning (one is `Source` warn) | match    |
| Category D: described as "errors"        | Both are `reportArgumentType` warnings      | severity |

Files entirely missed by the brief in Category A: `bash_tools.py`, `file_tools.py` (8
sites!), `interaction_tool.py`, `notebook_tool.py`. Files entirely missed in Category B:
`interaction_tool.py:369`, `notebook_tool.py:223/227/229/230/242` (the brief listed only
`:245` as the unbound-`result` site).

## Cluster Findings (Detailed Reports)

- **`01-analysis/01-cluster-a-basetool-contract.md`** — BaseTool contract ratification
- **`01-analysis/02-cluster-bd-optional-safety.md`** — Optional/None + type-arg
- **`01-analysis/03-cluster-c-imports-deps.md`** — Imports + dependency declaration

Headline conclusions consolidated below.

### Cluster A: BaseTool Contract (17 sites, 9 files)

**Base contract** (`packages/kailash-kaizen/src/kaizen/tools/native/base.py:149-165`):

```python
class BaseTool:
    async def execute(self, **kwargs) -> NativeToolResult: ...
```

The base is already permissive (`**kwargs`-only). Pyright is complaining that overrides
declare typed positional params **without a `**kwargs` sink\*\* — making the override less
permissive than the base, which is an LSP violation.

**Caller pattern is uniform — kwargs-spread, always:**

- Single dispatcher: `tools/native/registry.py:325` calls `tool.execute_with_timing(**params)`.
- Single production caller: `kaizen_agents/runtime_adapters/kaizen_local.py:971` calls
  `registry.execute(tool_name, tool_args)` with LLM-emitted JSON args.
- **Zero callers** pass positional args directly to `tool.execute(...)`.

**LLM never sees Python signatures** — it consumes `BaseTool.get_schema()` (`base.py:167-185`).
Signature change is invisible to LLM tool-calling, so this is pure-typing housekeeping with
no agent-reasoning impact.

**Decision: Option 1 — Add `*, ` keyword-only marker + `**kwargs: Any` sink to every override.\*\*

```python
# Before — pyright error: incompatible override
async def execute(self, action: str, name: str = "") -> NativeToolResult:
    ...

# After — keyword-only + **kwargs sink
async def execute(self, *, action: str, name: str = "", **kwargs: Any) -> NativeToolResult:
    ...
```

**Why this option (vs widen-base or Pydantic-schemas):**

- Caller pattern is uniform — kwargs-spread is already the runtime contract.
- Signature change is invisible to LLM (uses `get_schema()`, not signature introspection).
- ~140 LOC of mechanical edits across 9 files; zero load-bearing logic moves.
- Existing `planning_tool.py` already follows this pattern — works as the canonical exemplar.
- Pydantic schemas (Option 3) introduce a 3rd source of truth (signature, `get_schema()`,
  Pydantic model) and ~445 LOC; defer to a future workstream if runtime validation becomes a
  requirement.

**Spec consequence**: Document this contract in `specs/kaizen-tools.md` (new file — see § Specs below).

### Cluster B+D: Optional/None Safety + Type-Arg Mismatch (12 issues, 6 root causes)

| Cluster | Sites                              | Root cause                                                                                                    | Fix                                                                                    | LOC       |
| ------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------- |
| B1      | `notebook_tool.py:229,230,242,245` | `if/elif/elif` over `EditMode` enum, no exhaustive `else`                                                     | Add `else: raise ValueError(f"unhandled: {mode!r}")`                                   | ~3        |
| B2      | `notebook_tool.py:223,227`         | Validator narrows `cell_id` at L188 but pyright can't follow across function boundary                         | Local variable `cell_id_str: str = cell_id  # validated above`                         | ~2        |
| B3      | `parser.py:83,138`                 | Lazy-import sentinels (`arxiv = None`, `PdfReader = None`) — pyright loses type info                          | Typed guard: `if arxiv is None: raise ImportError("install kailash-kaizen[research]")` | ~4        |
| B4      | `task_tool.py:283`                 | `_adapter` is `Optional[Adapter]` accessed without guard                                                      | Typed guard per `rules/zero-tolerance.md` Rule 3a                                      | ~3        |
| B5      | `interaction_tool.py:369`          | `_user_callback` is `Union[sync, async]`; `iscoroutinefunction` narrowing fails on attribute                  | Local-variable capture before dispatch                                                 | ~2        |
| D       | `adapter.py:119:41,57`             | **Real runtime bug** — caller passes `dict[str,str]` where `Signature(inputs=, outputs=)` expects `List[str]` | `inputs = list(param_names)` + Tier 2 regression                                       | ~2 + test |

**Total:** ~16 LOC of fixes + 1 Tier 2 regression test. All 12 issues collapse to 6 root-cause
clusters. Combinable with Cluster A in one shard.

**Cluster D severity escalation:** The brief classifies this as a static-typing warning, but
the report identifies it as a real silent runtime corruption. `Signature._inputs_list` has
been silently broken since the adapter was written. Tier 2 regression is MANDATORY per
`rules/testing.md` § "End-to-End Pipeline Regression".

### Cluster C: Imports + Deps (3+5 issues, 2 root causes)

#### C1: Orphan imports in `research/__init__.py`

**Smoking gun:** Commit `801de2bb` (2026-03-25, PR #75 "structural split — move ~44K lines
of L2 engine code to kaizen-agents") **moved** `advanced_patterns.py`, `experimental.py`,
`intelligent_optimizer.py` to `packages/kaizen-agents/src/kaizen_agents/research_patterns/`
**but forgot to update `kaizen/research/__init__.py`**. Vestigial imports have lived on main
~6 weeks.

**Verification of safety to delete:**

- ✅ Source files exist at `kaizen-agents/src/kaizen_agents/research_patterns/{advanced_patterns,experimental,intelligent_optimizer}.py`
- ✅ Zero non-test callers of `kaizen.research.*_patterns` exist in `kailash-kaizen/src/`
- ⚠️ 5 test files at `kailash-kaizen/tests/unit/research/test_*.py` reference symbols
  removed by PR #75 via dead-path imports. **Only `test_advanced_patterns.py` has the
  `pytest.mark.skipif(not arxiv-importable)` guard (line 23).** The other 4 files
  (`test_experimental_feature.py`, `test_intelligent_optimizer.py`,
  `test_compatibility_checker.py`, `test_feature_manager.py`) have NO skip guard and
  import directly via `from kaizen.research import …`. They pass today only because
  `kaizen.research.__init__.py` still re-exports the symbols (the orphan re-exports
  themselves are the symbol-resolution path). Once we delete those re-exports per
  Shard 2, ALL 5 test files MUST be removed in the SAME commit per
  `rules/orphan-detection.md` Rule 4 — otherwise `pytest --collect-only` blocks every
  subsequent suite run.
- ⚠️ kaizen-agents has **zero test coverage** for `research_patterns/` — file follow-up.
- 🔴 **Cross-package import without dep declaration (red-team finding F-2):**
  `packages/kailash-kaizen/src/kaizen/research/feature_manager.py:13` contains
  `from kaizen_agents.research_patterns.experimental import ExperimentalFeature`.
  `kaizen-agents` is NOT in `kailash-kaizen/pyproject.toml::dependencies` and is not
  in any optional extra. This is the same bug class as C1 — clean install of
  `kailash-kaizen` raises `ModuleNotFoundError` on first
  `from kaizen.research import FeatureManager`. Per `rules/autonomous-execution.md`
  Rule 4 ("Fix-Immediately when same-class gap fits within shard budget"), this MUST
  land in Shard 2. **Disposition: DELETE `feature_manager.py`** along with the orphan
  `__init__.py` re-exports — `FeatureManager` was part of the same vestigial cluster
  PR #75 moved out, and the only callers are the orphan tests we're already deleting.

**Decision: Delete the orphan imports, delete `feature_manager.py`, sweep the 5 dead-path
tests, file kaizen-agents test coverage as a follow-up issue.**

```python
# packages/kailash-kaizen/src/kaizen/research/__init__.py
# DELETE lines 26, 35, 39 imports + 7 corresponding __all__ entries
- from .advanced_patterns import ...
- from .experimental import ...
- from .intelligent_optimizer import ...
# Also DELETE the FeatureManager re-export (carries the unguarded
# kaizen_agents import per F-2)
```

```bash
# Sweep dead-path tests + the cross-package-import source file
rm packages/kailash-kaizen/src/kaizen/research/feature_manager.py
rm packages/kailash-kaizen/tests/unit/research/test_{advanced_patterns,experimental_feature,intelligent_optimizer,compatibility_checker,feature_manager}.py
```

**Follow-up (file at /implement, not in this PR):** GitHub issue against `terrene-foundation/kailash-py` titled `test(kaizen-agents): add coverage for research_patterns/ moved in PR #75`.

#### C2: Undeclared deps (`arxiv`, `pypdf`, `duckduckgo_search`, `bs4`)

**Lazy-import sentinel hygiene:**

| Dep                 | File:line                                     | Pattern                                                                 | Hygiene  |
| ------------------- | --------------------------------------------- | ----------------------------------------------------------------------- | -------- |
| `arxiv`             | `research/parser.py:18-25`                    | `arxiv = None` sentinel + bool flag, raises at call site                | PASS     |
| `pypdf`             | `research/parser.py:27-33`                    | Same shape, raises at call site                                         | PASS     |
| `duckduckgo_search` | `tools/native/search_tools.py:50-62, 100-101` | Lazy probe + WARN, returns `NativeToolResult.from_error`                | PASS     |
| `bs4`               | `tools/native/search_tools.py:295-321`        | `try/except ImportError` with **silent degradation** (returns raw HTML) | **FAIL** |

**bs4 silent-degradation violates `rules/dependencies.md`:** when user requests
`extract_text=True` and bs4 is missing, the tool silently returns raw HTML — user thinks
they got extracted text. Convert to loud failure.

**Decision: Option B — Add as optional-extras + fix bs4 silent-degradation.**

```toml
# packages/kailash-kaizen/pyproject.toml
[project.optional-dependencies]
# Research surface — arxiv paper search + PDF parsing for ResearchParser
research = ["arxiv>=2.0", "pypdf>=4.0"]
# Web-search surface — DuckDuckGo search + HTML extraction for WebSearchTool/WebFetchTool
web-search = ["duckduckgo-search>=6.0", "beautifulsoup4>=4.12"]
```

```python
# tools/native/search_tools.py:295-321 — replace silent fallback with loud failure
- try:
-     from bs4 import BeautifulSoup
-     ...
- except ImportError:
-     return raw_html  # silent — user can't tell extraction failed
+ if BeautifulSoup is None:  # set via lazy-import sentinel at module top
+     return NativeToolResult.from_error(
+         "extract_text=True requires kailash-kaizen[web-search] (beautifulsoup4)"
+     )
```

## Sharding

Per `rules/autonomous-execution.md` Rule 1 budget (≤500 LOC load-bearing, ≤5–10 invariants,
≤3–4 call-graph hops, describable in 3 sentences):

### Shard 1 — Type-safety sweep (single shard, ~170 LOC)

**One sentence**: Ratify BaseTool contract as `**kwargs`-permissive, sweep 17 override sites
to add `*, ` + `**kwargs: Any` sinks, fix 6 Optional/None root causes (12 pyright issues),
fix the real `adapter.py:119` runtime bug with Tier 2 regression test.

**Files touched:** 11 (9 tool subclasses + adapter.py + parser.py + task_tool.py + 1 new test)
**Invariants:** LSP compliance + adapter.py call shape + 4 None guards = 6 invariants
**Call-graph hops:** 2 (adapter.py → Signature.**init**; tool dispatcher → tool.execute)
**Feedback loop:** Live (`uv run pyright src/kaizen/tools/native/ src/kaizen/research/` after each edit)

**Acceptance gates:**

- `uv run pyright src/kaizen/tools/native/ src/kaizen/research/` reports 0 errors, 0 warnings
- `uv run pytest packages/kailash-kaizen/tests/regression/` passes including the new
  **`tests/regression/test_issue_814_research_adapter_inputs_list.py`** (canonical name per
  `rules/testing.md` "Regression Testing"). Test asserts behavior: call `Signature(inputs=...)`
  with the corrected `list(param_names)` shape, assert `_inputs_list == [name1, name2, ...]`
  and NOT a dict-stringified blob. Source-grep is BLOCKED as the sole assertion.
- Existing kaizen unit + integration suites green
- **Per-subclass direct test sweep** per `rules/testing.md` § "One Direct Test Per Variant In
  Every Delegating Pair": for each of the 18 `BaseTool` subclasses (17 fixed + planning*tool.py
  exemplar), grep `tests/unit/tools/native/` for a `def test*_<subclass>_` matching:
  ```bash
  for tool in bash file interaction notebook process search skill task todo planning; do
    grep -rln "${tool}_tool" packages/kailash-kaizen/tests/unit/tools/native/ \
      || echo "MISSING: tests/unit/tools/native/test_${tool}_tool.py"
  done
  ```
  Any subclass without a direct unit test calling its `execute()` MUST get one added in this shard.

### Shard 2 — Orphan + dependency cleanup (single shard, ~100 LOC)

**One sentence**: Delete 3 vestigial imports + 7 `__all__` entries from
`research/__init__.py`, delete `feature_manager.py` (carries unguarded cross-package import),
sweep 5 dead-path test files, add `research` + `web-search` optional extras to
`pyproject.toml`, convert bs4 silent-degradation to loud failure.

**Files touched:** 5 (`research/__init__.py`, `feature_manager.py` deletion,
`pyproject.toml`, `search_tools.py`, 5 test deletions)
**Invariants:** `pytest --collect-only` clean + extras install works + bs4 failure is loud +
no-`kaizen_agents` clean install of kailash-kaizen does not raise = 4 invariants
**Call-graph hops:** 0 (deletions + config edits + one branch flip)
**Feedback loop:** Live (`pytest --collect-only` + `uv pip install '.[web-search]'` smoke)

**Acceptance gates:**

- `pytest --collect-only -q` exit 0 across all kaizen test dirs
- `uv pip install --no-deps -e packages/kailash-kaizen` then `uv pip install '.[research]'` succeeds
- `uv pip install '.[web-search]'` succeeds
- **Clean-install probe** (F-2 amendment): `python -c "from kaizen.research import *"` in a
  venv where `kaizen-agents` is NOT installed does NOT raise `ModuleNotFoundError`. Confirms
  `feature_manager.py` deletion eliminated the unguarded cross-package import.
- `WebFetchTool(extract_text=True)` invocation without bs4 returns loud error (regression test)
- Version bump `kaizen` → next-patch, CHANGELOG migration entry per `rules/zero-tolerance.md` Rule 6a
- Follow-up issue filed against `terrene-foundation/kailash-py` for kaizen-agents test parity (research_patterns)

### Why Two Shards Not One

Combined LOC (~250) and combined invariants (~9) sit at the upper edge of the budget.
Splitting:

- Lets Shard 1 ship the contract decision + runtime bug fix as the high-leverage PR
- Lets Shard 2 carry the version bump + CHANGELOG (release-track work)
- Reduces blast radius of a Shard-1-rollback (e.g. if the BaseTool ratification surfaces an
  unforeseen LLM-tooling regression)
- Aligns with `feedback_build_repo_release.md`: Shard 2 is the release-prep PR; per
  `rules/git.md` § "Release-Prep PRs MUST Use `release/v*` Branch Convention", Shard 2 SHOULD
  open from `release/v<next>` to skip the PR-gate matrix

### Why Not Three Shards

Splitting Cluster A from Cluster B+D would orphan the `adapter.py:119` runtime bug fix from
the BaseTool sweep — breaking the "fix-immediately when same-class gap fits the budget" rule
(`rules/autonomous-execution.md` Rule 4). They share the file (`adapter.py`) and the
context-window of pyright fixes; combining them is correct.

## Specs

**Deferred to post-merge per `rules/spec-accuracy.md` Rule 5** ("Incremental Spec
Extension Is The Workflow" — spec content describes only behavior already shipped on
`main`).

A spec gap was discovered: `specs/_index.md` has no entry for the BaseTool surface
(`packages/kailash-kaizen/src/kaizen/tools/native/base.py`), and the pre-existing 17-site
override drift was never caught because no spec ratified the contract. The architecture
plan in `02-plans/01-architecture.md` IS the design artifact for this workstream — it
documents the contract decision, override pattern, dispatcher behavior, and error contract.

Spec creation is deferred to a follow-up PR after Shard 1 lands:

1. **`specs/kaizen-tools.md`** (new file, post-Shard-1) — describes the BaseTool family
   contract as it ships AFTER the override sweep:
   - `async def execute(self, **kwargs) -> NativeToolResult` base contract
   - Override pattern (`*, <named params>, **kwargs: Any` sink)
   - Dispatcher: `ToolRegistry.execute(name, params: Dict)` → `tool.execute_with_timing(**params)`
   - LLM-facing surface: `BaseTool.get_schema()` (signature is invisible to the LLM)
   - Error contract: `NativeToolResult.from_error(...)` for declared failure modes

2. **`specs/_index.md`** update (post-Shard-1) — add the new entry under § Kaizen.

3. **`specs/kaizen-research.md`** — NOT pursued. After Shard 2, the remaining
   `kaizen.research.*` surface is small (`ResearchParser`, `ResearchPersistence`,
   `Signature`); the existing `specs/kaizen-core.md` can be extended with a § Research
   subsection rather than splitting a new file.

**Why defer:** Writing `specs/kaizen-tools.md` now would document a contract that 17 of
18 subclasses violate today. Per spec-accuracy Rule 5 BLOCKED rationalizations: "the
spec describes intent, code describes reality" is exactly the divergence the rule
prohibits. The design lives in `02-plans/`; the spec lands when the contract is
universally enforced.

## Red Team Verification (planned for /redteam)

The /redteam phase MUST verify (every step is a mechanical command, not a judgment call):

1. **Cluster A — pyright clean**: `cd packages/kailash-kaizen && uv run pyright src/kaizen/tools/native/ src/kaizen/research/` reports `0 errors, 0 warnings`. Note: bs4 is `reportMissingModuleSource` (warning), so `0 warnings` requires `kailash-kaizen[web-search]` to be installed in the pyright venv (or equivalent type-stub fallback).
2. **Cluster B — every named site fixed**: `grep -E "(reportPossiblyUnbound|reportOptional|reportArgumentType|reportAttributeAccessIssue)" /tmp/pyright-post-fix.txt | wc -l` → `0`.
3. **Cluster D — behavioral regression demonstrates pre-fix bug**: `git stash && uv run pytest tests/regression/test_issue_814_research_adapter_inputs_list.py -v` FAILS on the pre-fix code; `git stash pop && uv run pytest tests/regression/test_issue_814_research_adapter_inputs_list.py -v` PASSES post-fix. (Per `rules/testing.md` § "Behavioral Regression Tests Over Source-Grep" — the test calls `Signature(inputs=...)` and asserts the resulting `_inputs_list`; source-grep BLOCKED.)
4. **Cluster C1 — orphan elimination**: `python -c "from kaizen.research import *"` succeeds; `python -c "from kaizen.research import FeatureManager"` raises `ImportError` (proves deletion); `pytest --collect-only -q packages/kailash-kaizen/tests/` exits 0.
5. **Cluster C2 — extras install**: `uv pip install '.[research]'` and `uv pip install '.[web-search]'` succeed in clean venvs; `WebFetchTool(extract_text=True)` invocation without bs4 returns `NativeToolResult.from_error("...beautifulsoup4...")` (verified via Tier 2 regression test).
6. **Cross-package import elimination (F-2)**: in a venv WITHOUT `kaizen-agents` installed, `python -c "from kailash_kaizen.research import *"` does NOT raise `ModuleNotFoundError`.
7. **Mechanical orphan sweep**: `grep -rn "from kaizen.research import \\(AdvancedPattern\\|CompositionalPattern\\|HierarchicalPattern\\|AdaptivePattern\\|MetaLearningPattern\\|ExperimentalFeature\\|IntelligentOptimizer\\|FeatureManager\\)" packages/ tests/` returns 0 hits.
8. **No test/source colocation regression**: kaizen-agents test parity follow-up filed and labeled `area/quality, test-coverage`.
9. **Per-subclass test coverage**: each of the 18 BaseTool subclasses has a direct `execute()` test in `tests/unit/tools/native/` per `rules/testing.md` § "One Direct Test Per Variant In Every Delegating Pair".

## Decisions Log

| #   | Decision                                            | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Ratify `BaseTool.execute(self, **kwargs)` as base   | Already the runtime contract; LLM uses `get_schema()`; minimal change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2   | Override pattern: `*, <named>, **kwargs: Any`       | Keyword-only marker + sink; matches `planning_tool.py` exemplar                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 3   | Tier 2 regression for adapter.py:119                | Real runtime bug; `rules/testing.md` "Regression Testing" mandates same-PR test                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 4   | Delete orphan imports vs restore-from-git           | PR #75 (commit `801de2bb`, 2026-03-25) moved files intentionally; `__init__.py` was never updated → defect                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 5   | Delete 5 dead-path tests in kailash-kaizen          | Tests import from dead path. ONLY `test_advanced_patterns.py` has `pytest.mark.skipif`; the other 4 pass today only because the orphan re-exports still resolve. Once Shard 2 deletes the re-exports, the tests would block `pytest --collect-only` → MUST be removed in same commit per `rules/orphan-detection.md` Rule 4.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 6   | File kaizen-agents test parity as follow-up         | Out of #814 scope; tests should colocate with source                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 7   | Add `research` + `web-search` extras                | Matches existing `bedrock`/`vertex`/`judges` pattern                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 8   | bs4 silent-degradation → loud failure               | `rules/dependencies.md` BLOCKED anti-pattern (silent-fallback)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 9   | Two shards (type-safety / orphan-cleanup)           | Capacity budget + release-track separation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 10  | **No deprecation shim for the 7 removed `__all__`** | Per `rules/zero-tolerance.md` Rule 6a, public-API removal normally requires a `DeprecationWarning` shim covering one minor cycle. Justification for **no shim owed here**: PR #75 (commit `801de2bb`, 2026-03-25) moved the source files out of `kaizen.research/`. From that commit forward, `from kaizen.research import AdvancedPatternBuilder` raised `ModuleNotFoundError` on FIRST USE — the `__all__` re-export resolved the name but the underlying module load failed. **No consumer could have ever successfully imported these symbols on main since 2026-03-25** (verified: `git log --oneline --since=2026-03-25 packages/kailash-kaizen/src/kaizen/research/{advanced_patterns,experimental,intelligent_optimizer}.py` returns zero results). There is no working public surface to deprecate; Rule 6a's deprecation cycle is owed only when removal breaks a previously working callsite. CHANGELOG migration note still required per Rule 6a (documents that the symbols moved to `kaizen_agents.research_patterns`). |
| 11  | Add `feature_manager.py` deletion to Shard 2        | F-2 finding: `feature_manager.py:13` imports unguarded from `kaizen_agents` (not a kailash-kaizen dep). Same bug class as C1 orphan; per `rules/autonomous-execution.md` Rule 4 must land in same shard since gap fits budget.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
