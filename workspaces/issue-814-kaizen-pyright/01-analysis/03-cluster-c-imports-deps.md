# Cluster C — Missing imports + undeclared deps

**Scope:** 7 errors + 1 warning across 4 files in `packages/kailash-kaizen`. Two distinct subclasses:

- **C1 (orphan modules)**: 3 import lines in `research/__init__.py` resolve to files that DO NOT exist on disk.
- **C2 (undeclared deps)**: 4 third-party packages imported lazily but absent from `pyproject.toml`.

---

## C1 — Orphan modules in `research/__init__.py`

### 1. Disk verification (modules absent)

`ls packages/kailash-kaizen/src/kaizen/research/` shows only:

```
adapter.py  compatibility_checker.py  documentation_generator.py  feature_manager.py
feature_optimizer.py  integration_workflow.py  parser.py  registry.py  validator.py
__init__.py
```

No `advanced_patterns.py`, no `experimental.py`, no `intelligent_optimizer.py`. The orphan claims are confirmed.

### 2. Import shape in `research/__init__.py` (unconditional, top-level)

`packages/kailash-kaizen/src/kaizen/research/__init__.py:25-42`:

```python
from .adapter import ResearchAdapter, SignatureAdapter
from .advanced_patterns import (                       # line 26 — ORPHAN
    AdaptivePattern,
    AdvancedPatternBuilder,
    CompositionalPattern,
    HierarchicalPattern,
    MetaLearningPattern,
)
from .compatibility_checker import CompatibilityChecker
from .documentation_generator import DocumentationGenerator
from .experimental import ExperimentalFeature           # line 35 — ORPHAN
from .feature_manager import FeatureManager
from .feature_optimizer import FeatureOptimizer
from .integration_workflow import IntegrationWorkflow
from .intelligent_optimizer import IntelligentOptimizer # line 39 — ORPHAN
from .parser import ResearchPaper, ResearchParser
from .registry import RegistryEntry, ResearchRegistry
from .validator import ResearchValidator, ValidationResult
```

All three imports are **unconditional, module-scope, eager**. No `try/except ImportError` guard. `__all__` (lines 44-65) re-exports 8 symbols sourced from these orphan modules:

```
AdvancedPatternBuilder, CompositionalPattern, HierarchicalPattern, AdaptivePattern,
MetaLearningPattern, ExperimentalFeature, IntelligentOptimizer
```

Plus `FeatureManager` consumes `ExperimentalFeature` (per test imports). First user-`import kaizen.research` raises `ModuleNotFoundError: No module named 'kaizen.research.advanced_patterns'`. This is the canonical orphan-detection failure pattern from `rules/orphan-detection.md` MUST Rule 1 + `rules/dependencies.md` MUST Rule "`__init__.py` Module-Scope Imports Honor The Manifest".

### 3. Internal callers of orphan symbols

`grep -rn 'AdvancedPatternBuilder|CompositionalPattern|HierarchicalPattern|AdaptivePattern|MetaLearningPattern|ExperimentalFeature|IntelligentOptimizer' packages/kailash-kaizen/ tests/`:

**Production code** (in kailash-py): **ZERO production callers**. Not a single non-test src/ file references these symbols. The only production consumption is the `__init__.py` re-export itself.

**Test code** (orphaned, parallel failure):

- `packages/kailash-kaizen/tests/unit/research/test_advanced_patterns.py` (10,871 bytes, last touched 16 Apr 11:59)
- `packages/kailash-kaizen/tests/unit/research/test_experimental_feature.py` (14,192 bytes)
- `packages/kailash-kaizen/tests/unit/research/test_intelligent_optimizer.py` (5,196 bytes)
- `packages/kailash-kaizen/tests/unit/research/test_compatibility_checker.py` (uses `ExperimentalFeature`)
- `packages/kailash-kaizen/tests/unit/research/test_feature_manager.py` (likely; `FeatureManager` consumes ExperimentalFeature)

These three test files import `from kaizen.research import ExperimentalFeature / IntelligentOptimizer / AdvancedPatternBuilder` — they fail at `pytest --collect-only` with `ModuleNotFoundError`, blocking the entire research/ test directory per `rules/orphan-detection.md` MUST Rule 4 ("API Removal MUST Sweep Tests In The Same PR") + Rule 5 ("Collect-Only Is A Merge Gate").

### 4. Git history — commit `801de2bb` is the smoking gun

Commit `801de2bb` (2026-03-25), "refactor(kaizen): structural split — move ~44K lines of L2 engine code to kaizen-agents (#75)", explicitly MOVED these files:

```
- kaizen/research/ patterns → kaizen_agents/research_patterns/ (1K)
.../kaizen_agents/research_patterns}/advanced_patterns.py        |   0
.../kaizen_agents/research_patterns}/experimental.py             |   0
.../kaizen_agents/research_patterns}/intelligent_optimizer.py    |   0
```

Destination on disk (verified):
`packages/kaizen-agents/src/kaizen_agents/research_patterns/__init__.py` exists with the docstring `"""Advanced research patterns — LLM-based optimization and meta-learning."""`. All three files are present at:

- `packages/kaizen-agents/src/kaizen_agents/research_patterns/advanced_patterns.py`
- `packages/kaizen-agents/src/kaizen_agents/research_patterns/experimental.py`
- `packages/kaizen-agents/src/kaizen_agents/research_patterns/intelligent_optimizer.py`

**The structural-split refactor moved the source files but did NOT update `kaizen/research/__init__.py` to remove the dangling imports OR to use a `try/except ImportError` guard against the now-cross-package source.** The orphan has lived on main since `801de2bb` (~6 weeks).

`git log --oneline -10 -- packages/kailash-kaizen/src/kaizen/research/__init__.py`:

```
ee277cfc fix(kaizen): strip TODO-NNN refs in research/ module (11 hits)
b553104c refactor(monorepo): move published packages from apps/ to packages/
```

The structural-split commit (`801de2bb`) does NOT appear in the `__init__.py` history, confirming the file was never updated to reflect the move.

Note: `packages/kailash-kaizen/build/lib/kaizen/research/__init__.py` ALSO contains the dangling imports (a stale build artifact from before the split — not git-tracked, .gitignored).

### 5. Recommendation for C1 — **Option A: Delete the imports**

The 3 dangling imports + 7 orphaned `__all__` entries MUST be **deleted** from `kaizen/research/__init__.py`, AND the parallel orphan tests deleted in the SAME commit (per `rules/orphan-detection.md` MUST Rule 4).

**Justification:**

- **No production callers in kaizen.** Zero references outside the `__init__.py` re-export — nothing in kaizen's hot path uses these symbols.
- **The files moved, they were not deleted.** The destination is `kaizen-agents.research_patterns` (a sibling package, not a kailash-kaizen orphan); rules/dependencies.md "`__init__.py` Module-Scope Imports Honor The Manifest" requires that any cross-package import to a non-declared sibling MUST be `try/except ImportError`-guarded. `kaizen-agents` is NOT in `kailash-kaizen/pyproject.toml::dependencies` (verified — `grep -n 'kaizen-agents\|kaizen_agents' packages/kailash-kaizen/pyproject.toml` returns only one comment match in line 101 about `kaizen_agents.Delegate`).
- **Re-importing from the sibling is the wrong fix.** Adding `try/except ImportError` re-exports of `kaizen_agents.research_patterns.*` would be a cross-package re-export with no production consumer in kaizen — kailash-kaizen would advertise a public API it doesn't own, while every kailash-kaizen install on a clean venv (without kaizen-agents) would silently degrade to half the symbols missing. Per `rules/orphan-detection.md` MUST Rule 3 ("Removed = Deleted, Not Deprecated"), the kaizen-side surface MUST be deleted; consumers who want these symbols import from `kaizen_agents.research_patterns` directly.
- **Tests are deferral-orphans.** Per `rules/orphan-detection.md` Rule 4, the SAME PR that deletes the imports MUST delete `tests/unit/research/test_advanced_patterns.py`, `test_experimental_feature.py`, `test_intelligent_optimizer.py`, AND port `test_compatibility_checker.py` + `test_feature_manager.py` to drop their `ExperimentalFeature` references — otherwise `pytest --collect-only` blocks merge.

**Concrete diff (illustrative, not for implementation in this analysis):**

- Delete `kaizen/research/__init__.py:26-32` (advanced_patterns block)
- Delete `kaizen/research/__init__.py:35` (experimental)
- Delete `kaizen/research/__init__.py:39` (intelligent_optimizer)
- Drop 7 entries from `__all__`: `ExperimentalFeature`, `AdvancedPatternBuilder`, `CompositionalPattern`, `HierarchicalPattern`, `AdaptivePattern`, `MetaLearningPattern`, `IntelligentOptimizer`
- Delete the 3 orphan test files; port the 2 dependent tests
- Update CHANGELOG with "removed (moved to kaizen-agents in 2.3.0)" migration note per `rules/zero-tolerance.md` Rule 6a (Public-API Removal Requires Deprecation Cycle) — though arguably the symbols never resolved post-2.3.0 so they were never functionally public

---

## C2 — Undeclared deps in lazy-import sentinels

### 6. Per-file:line shape

#### 6a. `arxiv` — `packages/kailash-kaizen/src/kaizen/research/parser.py:18-25`

```python
# Optional dependencies for research parsing
try:
    import arxiv
    ARXIV_AVAILABLE = True
except ImportError:
    arxiv = None  # type: ignore[assignment]
    ARXIV_AVAILABLE = False
```

**Pattern:** `try/except ImportError` with `arxiv = None` sentinel + boolean flag. Use site at line 76-80:

```python
if not ARXIV_AVAILABLE:
    raise ImportError(
        "arxiv library is required for parsing arXiv papers. "
        "Install with: pip install arxiv"
    )
```

**Hygiene:** Loud failure at call site with actionable install message. Matches the permitted optional-extras exception in `rules/dependencies.md` (the pattern is permitted IF the failure is loud at the call site, NOT silent degradation). **HYGIENE: PASS.**

#### 6b. `pypdf` — `packages/kailash-kaizen/src/kaizen/research/parser.py:27-33`

```python
try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None  # type: ignore[assignment, misc]
    PYPDF_AVAILABLE = False
```

**Pattern:** Same shape as arxiv — sentinel + boolean. Loud-failure at call site (`if not PYPDF_AVAILABLE: raise ImportError(...)`). **HYGIENE: PASS.**

#### 6c. `duckduckgo_search` — `packages/kailash-kaizen/src/kaizen/tools/native/search_tools.py:50-62, 100-101`

```python
def _check_ddg_available(self) -> bool:
    """Check if duckduckgo-search is available."""
    if self._ddg_available is None:
        try:
            from duckduckgo_search import DDGS
            self._ddg_available = True
        except ImportError:
            self._ddg_available = False
            logger.warning(
                "duckduckgo-search not installed. Install with: pip install duckduckgo-search"
            )
    return self._ddg_available
```

Use site at `_search_duckduckgo` (line 91-101):

```python
if not self._check_ddg_available():
    return NativeToolResult.from_error(
        "DuckDuckGo search not available. Install duckduckgo-search: pip install duckduckgo-search"
    )
try:
    from duckduckgo_search import DDGS
    ...
```

**Pattern:** Lazy availability-probe, returns a typed error result instead of raising. **HYGIENE: PASS** (loud at call site via `NativeToolResult.from_error` + a one-time WARN log on first probe).

#### 6d. `bs4` (beautifulsoup4) — `packages/kailash-kaizen/src/kaizen/tools/native/search_tools.py:295-321`

```python
def _extract_text(self, html: str) -> str:
    """Extract text content from HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        ...
        return "\n".join(lines)
    except ImportError:
        logger.warning(
            "beautifulsoup4 not installed, returning raw HTML. "
            "Install with: pip install beautifulsoup4"
        )
        return html
    except Exception as e:
        logger.warning(f"Text extraction failed: {e}, returning raw content")
        return html
```

**Pattern:** `try/except ImportError` with a **silent degradation fallback** — returns raw HTML instead of extracted text. This is a `BLOCKED` form per `rules/dependencies.md` ("BLOCKED: silent fallback to None / silent fallback to degraded path"). The user requested text extraction; the tool silently returns HTML. **HYGIENE: BORDERLINE FAIL** — the degradation is noted in the docstring and warns at the log layer, but the caller cannot distinguish "extracted text" from "raw HTML" at the API surface; this is the soft form of "fake feature". The pyright warning (`reportMissingModuleSource`) at line 298 is what surfaced it.

The pyright report flags this at line 298 as warning level (`reportMissingModuleSource`), suggesting beautifulsoup4 type stubs may be present in the venv via a transitive dep but the module itself isn't declared; in a clean install the import fails silently.

### 7. User-facing surface and feature gating

| Dep                 | Surface                                                              | Hot-path?                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `arxiv`             | `ResearchParser.parse_from_arxiv(arxiv_id)`                          | NO — opt-in (call-site gated, raises if missing)                                                                                                                                                                                                                                                                                                                                                                                              |
| `pypdf`             | `ResearchParser.parse_from_pdf(pdf_path)`                            | NO — opt-in (call-site gated, raises if missing)                                                                                                                                                                                                                                                                                                                                                                                              |
| `duckduckgo_search` | `WebSearchTool` (registered as kaizen native tool category "search") | YES — registered in `tools/native/registry.py:171` under `"search"` category, exposed via `tools/native/__init__.py:69, 94-95` `__all__`. Default-import path of `kaizen.tools.native` triggers `WebSearchTool` class definition (no module-scope `from duckduckgo_search import` — lazy via `_check_ddg_available`), so default install of kaizen does NOT crash, but instantiation + execute returns a typed error result. Call-site gated. |
| `bs4`               | `WebFetchTool._extract_text(html)`                                   | YES — `WebFetchTool` is in the same default registry category. The fallback silently returns raw HTML if bs4 is missing — a degradation, not a hard fail.                                                                                                                                                                                                                                                                                     |

**None are on the hot path of `import kailash_kaizen` itself** — all four are lazy at call site. The default `pip install kailash-kaizen` runs cleanly without any of these four deps (verified: lazy try/except blocks).

### 8. Cross-check against existing `pyproject.toml` extras

`pyproject.toml` extras: `bedrock`, `vertex`, `interpretability`, `judges`, `evaluation`, `dev`. None cover the four C2 deps.

**Recommended extras names (consistent with naming convention):**

- `research = ["arxiv>=2.0", "pypdf>=4.0"]` — backs `kaizen.research.parser.ResearchParser` (file location + naming aligns)
- `web-search = ["duckduckgo-search>=6.0", "beautifulsoup4>=4.12"]` — backs `kaizen.tools.native.WebSearchTool` + `WebFetchTool`

Single-extra alternative: fold all four into `research` (parser.py + WebSearchTool both serve research workflows). The two-extra split is cleaner since `WebSearchTool` is a generic tool category, not research-specific.

### 9. Lazy-sentinel hygiene per dep (re-cap)

| Dep                 | Sentinel pattern                                                   | Loud at call site?                         | Hygiene verdict                             |
| ------------------- | ------------------------------------------------------------------ | ------------------------------------------ | ------------------------------------------- |
| `arxiv`             | `arxiv = None` + bool flag                                         | YES (raises ImportError with install hint) | PASS                                        |
| `pypdf`             | `PdfReader = None` + bool flag                                     | YES (raises ImportError with install hint) | PASS                                        |
| `duckduckgo_search` | Lazy probe + WARN log                                              | YES (returns NativeToolResult.from_error)  | PASS                                        |
| `bs4`               | `try/except ImportError` with degraded fallback (returns raw HTML) | NO (silent degradation, only a WARN log)   | BORDERLINE FAIL — fix as part of resolution |

### 10. Recommendation for C2 — **Option B: Add as optional extras + fix bs4 fallback**

**For arxiv + pypdf + duckduckgo_search**: Add as `[project.optional-dependencies]` extras `research` and `web-search`. The lazy-sentinel hygiene is correct for an extras-gated feature — all three raise/error loudly at the call site when the extra isn't installed. The fix is purely the manifest entry; no source-code change.

**For bs4**: Two-part fix:

1. Add to `web-search` extra (manifest entry).
2. **Convert the silent-degradation fallback to loud failure** at the API surface: change `WebFetchTool._extract_text` to either (a) return an `NativeToolResult.from_error` if `extract_text=True` was requested AND bs4 is missing, OR (b) raise `ImportError` with the actionable install hint. The current "WARN log + return raw HTML" form silently delivers a different output type than the user requested, which trips `rules/dependencies.md` § BLOCKED Anti-Patterns.

**Why Option B over Option A or C:**

- **Not Option A (mandatory)**: None of the four are on the import-time hot path. Forcing all four into base `dependencies = [...]` would penalize every kaizen consumer with a ~40MB transitive install (bs4 + lxml + duckduckgo's deps + arxiv's HTTP stack + pypdf) for a feature most installs don't use.
- **Not Option C (delete)**: `WebSearchTool` and `WebFetchTool` ARE consumed in the default `kaizen.tools.native` `__all__` and registered in `tools/native/registry.py:171` under the `"search"` category — they have production wiring inside kaizen. `ResearchParser` is wired into `kaizen.research.integration_workflow.IntegrationWorkflow` (line 16 imports it). All four are real features, not orphan deferrals.

---

## Summary — recommended dispositions

| Cluster                   | Disposition                                                                                                                   | Reasoning ground                                                                                                                                                                                |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C1 (3 errors)             | **Delete** dangling imports + drop 7 `__all__` entries + sweep 3 orphan test files + port 2 dependent tests + CHANGELOG entry | Source files moved to `kaizen-agents` in commit `801de2bb` (2026-03-25); zero production callers in kaizen; per `rules/orphan-detection.md` MUST Rules 1, 3, 4                                  |
| C2 (3 errors + 1 warning) | **Add `[research]` and `[web-search]` extras** + fix bs4 silent-degradation fallback to loud failure                          | Lazy-sentinel hygiene is mostly correct (3/4 PASS); manifest gap is the structural defense per `rules/dependencies.md` "Declared = Imported"; bs4 case violates BLOCKED silent-fallback pattern |

**Files changed if both dispositions implemented (FYI — not for this analysis):**

- `packages/kailash-kaizen/src/kaizen/research/__init__.py` (delete 3 imports + 7 `__all__` entries)
- `packages/kailash-kaizen/tests/unit/research/test_advanced_patterns.py` (delete)
- `packages/kailash-kaizen/tests/unit/research/test_experimental_feature.py` (delete)
- `packages/kailash-kaizen/tests/unit/research/test_intelligent_optimizer.py` (delete)
- `packages/kailash-kaizen/tests/unit/research/test_compatibility_checker.py` (port — drop ExperimentalFeature refs)
- `packages/kailash-kaizen/tests/unit/research/test_feature_manager.py` (port — drop ExperimentalFeature refs if present)
- `packages/kailash-kaizen/pyproject.toml` (add `research` + `web-search` extras)
- `packages/kailash-kaizen/src/kaizen/tools/native/search_tools.py` (convert bs4 silent-degradation to loud failure)
- `packages/kailash-kaizen/CHANGELOG.md` (entry: removed orphan re-exports + new optional extras)

All changes per zero-tolerance Rule 6a: same-PR delivery, with shim/CHANGELOG migration note covering the orphan-removal half.
