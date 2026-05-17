# Cluster B+D — Optional/None safety + type-argument mismatch

**Scope:** 5 errors + 7 warnings (12 issues) across 4 files. All warnings carry the same fix discipline as errors per `rules/zero-tolerance.md` Rule 1.

**Files involved:**

- `packages/kailash-kaizen/src/kaizen/tools/native/notebook_tool.py` (6 issues — 4 err + 2 warn)
- `packages/kailash-kaizen/src/kaizen/tools/native/interaction_tool.py` (1 warn)
- `packages/kailash-kaizen/src/kaizen/tools/native/task_tool.py` (1 warn)
- `packages/kailash-kaizen/src/kaizen/research/parser.py` (1 err + 1 warn)
- `packages/kailash-kaizen/src/kaizen/research/adapter.py` (2 warn — same line)

---

## Root-cause clustering

The 12 issues collapse to **5 distinct root causes**. Each cluster is a single bug expressed at multiple lines.

| #   | Root cause                                                   | Lines (file:line)                                                                                           | Fix shape                                                                         |
| --- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 1   | `result` may be unbound when `mode` matches none of 3 enums  | `notebook_tool.py:223`, `:227`, `:229`, `:230`, `:242`, `:245`                                              | unreachable-else `raise` OR pre-init                                              |
| 2   | `cell_id: Optional[str]` flows into helpers typed `str`      | `notebook_tool.py:223` (also 225, 227 — only 223/227 flagged because 225 takes new_source path differently) | typed guard: `assert cell_id is not None`                                         |
| 3   | Lazy `arxiv` sentinel is `None` when import failed           | `parser.py:83` (Search on None), `:138` (`PdfReader(None)` call) — TWO sentinels: `arxiv` AND `PdfReader`   | route through helper that raises ImportError already; type-narrow via local alias |
| 4   | `Signature.__init__` expects `List[str]`; caller passes dict | `adapter.py:119:41` (inputs), `:119:57` (outputs) — one call site, two args                                 | call-shape bug: pass list of names                                                |
| 5   | `_user_callback` union → `answers` not narrowed to `List`    | `interaction_tool.py:369`                                                                                   | `cast()` or split via local typed binding                                         |
| 6   | `task_tool.py:283` — `for_specialist` called on Optional     | `task_tool.py:283`                                                                                          | typed guard: `if self._adapter is None: raise` then call                          |

That's 6 clusters covering all 12 issues. (#3 is one root cause across 2 sentinel-objects.)

---

## Detailed analysis per cluster

### Cluster 1: `result` possibly unbound (notebook_tool.py:229/230/242/245)

**Citation:** `packages/kailash-kaizen/src/kaizen/tools/native/notebook_tool.py:222–245`

```python
# Perform edit
if mode == EditMode.REPLACE:
    result = self._replace_cell(notebook, cell_id, new_source, ctype)
elif mode == EditMode.INSERT:
    result = self._insert_cell(notebook, cell_id, new_source, ctype)
elif mode == EditMode.DELETE:
    result = self._delete_cell(notebook, cell_id)

if not result["success"]:                        # ← :229 unbound
    return NativeToolResult.from_error(result["error"])  # ← :230 unbound

# ...
return NativeToolResult.from_success(
    output=result["message"],                     # ← :242 unbound
    notebook_path=str(path),
    edit_mode=mode.value,
    cell_id=result.get("cell_id", cell_id),       # ← :245 unbound
    cell_count=len(notebook["cells"]),
)
```

**Root cause:** `EditMode` is a 3-value enum (REPLACE/INSERT/DELETE per the validator at line 172–177 — `EditMode(edit_mode)` raises if outside the set). Pyright cannot prove the `elif` chain is exhaustive because there is no `else` branch — even though at runtime it IS exhaustive thanks to the constructor validation upstream.

**Cleanest fix (recommended):** Add `else: raise RuntimeError(...)` after the third `elif`. This makes intent explicit ("validator should have caught this") AND satisfies pyright. Aligns with `rules/zero-tolerance.md` Rule 3a (typed guard with actionable message) — opaque `UnboundLocalError` is exactly what 3a blocks.

```python
elif mode == EditMode.DELETE:
    result = self._delete_cell(notebook, cell_id)
else:
    raise RuntimeError(f"unreachable: EditMode {mode!r} not handled — validator drift")
```

**Alternative:** Convert the chain to `match mode: case ... case _: raise`. Same shape, more idiomatic in Python 3.10+.

**LOC:** 2 (one `else:` + raise).
**Public API impact:** None — internal control flow.
**Issue count collapsed:** 4 errors → 1 fix.

---

### Cluster 2: `cell_id: Optional[str]` passed where `str` expected (notebook_tool.py:223, :227)

**Citation:** `notebook_tool.py:188–191, :222–227`

```python
# Validator at 188–191
if mode in (EditMode.REPLACE, EditMode.DELETE) and not cell_id:
    return NativeToolResult.from_error(
        f"cell_id is required for edit_mode='{mode.value}'"
    )
# ...
# Perform edit
if mode == EditMode.REPLACE:
    result = self._replace_cell(notebook, cell_id, new_source, ctype)  # ← :223 cell_id may be None
elif mode == EditMode.INSERT:
    result = self._insert_cell(notebook, cell_id, new_source, ctype)   # (insert allows None — OK)
elif mode == EditMode.DELETE:
    result = self._delete_cell(notebook, cell_id)                       # ← :227 cell_id may be None
```

**Root cause:** Validator at :188 returns early when `cell_id` is falsy and mode is REPLACE/DELETE — so by line 222–227, when `mode == REPLACE`, `cell_id` is guaranteed non-None. Pyright cannot follow this control-flow correlation across `mode` and `cell_id`. The `_replace_cell` and `_delete_cell` signatures accept `cell_id: str` (non-Optional). For INSERT, `cell_id` is allowed None (insert appends). Only :223 and :227 are flagged; :225 (INSERT) is fine because `_insert_cell` declares `Optional[str]`.

**Cleanest fix:** Restructure so the guard's narrowing is local. Two options:

**Option A (preferred — local assert in REPLACE/DELETE branches):**

```python
if mode == EditMode.REPLACE:
    assert cell_id is not None  # validator at :188 guarantees this
    result = self._replace_cell(notebook, cell_id, new_source, ctype)
elif mode == EditMode.INSERT:
    result = self._insert_cell(notebook, cell_id, new_source, ctype)
elif mode == EditMode.DELETE:
    assert cell_id is not None  # validator at :188 guarantees this
    result = self._delete_cell(notebook, cell_id)
```

**Option B (folds into Cluster 1 if using match):** Use one early-narrow before the dispatch:

```python
if mode in (EditMode.REPLACE, EditMode.DELETE):
    assert cell_id is not None  # already validated at :188
```

**LOC:** 2 lines (Option A) or 1 line (Option B).
**Public API impact:** None.
**Issue count collapsed:** 2 warnings → 1 fix.

---

### Cluster 3: Lazy import sentinels return None (parser.py:83, :138)

**Citation:** `packages/kailash-kaizen/src/kaizen/research/parser.py:18–33, :76–83, :126–138`

```python
# At top of file, lines 18-33:
try:
    import arxiv
    ARXIV_AVAILABLE = True
except ImportError:
    arxiv = None  # type: ignore[assignment]
    ARXIV_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None  # type: ignore[assignment, misc]
    PYPDF_AVAILABLE = False
```

```python
# Lines 76-83 (parse_from_arxiv)
if not ARXIV_AVAILABLE:
    raise ImportError(...)
# Search arXiv for paper
search = arxiv.Search(id_list=[arxiv_id])  # ← :83 "Search" on None
```

```python
# Lines 126-138 (parse_from_pdf)
if not PYPDF_AVAILABLE:
    raise ImportError(...)
# ...
reader = PdfReader(pdf_path)                # ← :138 "None" not callable
```

**Root cause:** The optional-dep pattern uses a module-level `arxiv = None` / `PdfReader = None` fallback. The runtime guards (`if not ARXIV_AVAILABLE: raise ImportError`) prove safety, but pyright cannot correlate `ARXIV_AVAILABLE is True` with `arxiv is not None` across module-scope sentinels.

**Note on `rules/dependencies.md` § BLOCKED Anti-Patterns:** That rule blocks `redis = None  # silent fallback`. The exception in this file: there IS a loud failure at the call site (the `if not ARXIV_AVAILABLE: raise ImportError(...)` block at :76 and :126). Per the rules guide, the optional-extras pattern with loud failure at call site is permitted — this code already complies with the spirit of the rule. The pyright finding is purely a static-analysis-visibility issue, NOT a rule violation.

**Cleanest fix:** Use `typing.TYPE_CHECKING` + module-level type-narrowed accessor. The shape that satisfies pyright AND keeps the runtime lazy:

**Option A (preferred — assert after guard):**

```python
def parse_from_arxiv(self, arxiv_id: str) -> ResearchPaper:
    if not ARXIV_AVAILABLE:
        raise ImportError(...)
    assert arxiv is not None  # narrowed by ARXIV_AVAILABLE
    search = arxiv.Search(id_list=[arxiv_id])
    ...

def parse_from_pdf(self, pdf_path: str) -> ResearchPaper:
    if not PYPDF_AVAILABLE:
        raise ImportError(...)
    assert PdfReader is not None  # narrowed by PYPDF_AVAILABLE
    ...
    reader = PdfReader(pdf_path)
```

**Option B (more involved — replace boolean flag with object presence check):**
Replace `if not ARXIV_AVAILABLE` with `if arxiv is None: raise ImportError(...)`. Pyright DOES narrow `arxiv` to non-None after that check. This eliminates the redundancy of `ARXIV_AVAILABLE` flag + `arxiv = None` parallel state. Drops the boolean flags entirely.

**Recommendation:** Option B is cleaner long-term but Option A is the minimal fix. For this issue's scope, prefer Option A (less surface to test).

**LOC:** 2 lines (one `assert` in each function).
**Public API impact:** None — `ImportError` still raised first.
**Issue count collapsed:** 1 error + 1 warning → 1 fix (applied at 2 sites).

---

### Cluster 4: `Signature(inputs=dict, outputs=dict)` — type mismatch (adapter.py:119)

**Citation:** `packages/kailash-kaizen/src/kaizen/research/adapter.py:103–119` plus `kaizen/signatures/core.py:306–321`

**Caller (adapter.py:103–119):**

```python
class ResearchSignature(Signature):
    def __init__(self):
        inputs = (
            {name: f"Input {name}" for name in param_names}  # dict[str, str]
            if param_names
            else {"input": "Input data"}
        )
        outputs = {"result": "Research result"}              # dict[str, str]
        super().__init__(inputs=inputs, outputs=outputs)     # ← :119 BOTH args wrong
```

**Callee (`kaizen/signatures/core.py:306–321`):**

```python
def __init__(
    self,
    inputs: Optional[List[str]] = None,
    outputs: Optional[List[Union[str, List[str]]]] = None,
    ...
    input_types: Optional[Dict[str, Any]] = None,    # ← THIS is the dict-typed kwarg
    output_types: Optional[Dict[str, Any]] = None,
    ...
):
```

**Root cause:** **The caller is wrong.** `Signature.__init__` expects `inputs: List[str]` (parameter NAMES) and a separate `input_types: Dict[str, Any]` for type annotations. The adapter is passing `{name: "Input description"}` dicts as `inputs=`/`outputs=`, conflating "names" with "descriptions". This is a real bug, not just a type mismatch — at runtime, internal consumers of `_inputs_list` (declared `List[str]` per `core.py:297`) will see dict objects and produce confusing errors downstream.

**Q3 answer (call-shape bug vs contract bug):** **Call-shape bug.** Callee is right (its `inputs` param has been `List[str]` since the class was authored — see `core.py:264–267` docstring example: `Signature(inputs=["question"], outputs=["answer"])`). Caller is wrong: it should pass list-of-names AND optionally pass descriptions via a different mechanism (no `input_descriptions` param exists; the adapter's "description" dict is being misused as the names list).

**Cleanest fix:**

```python
inputs = list(param_names) if param_names else ["input"]
outputs = ["result"]
super().__init__(inputs=inputs, outputs=outputs)
```

The descriptions (`f"Input {name}"`, `"Research result"`) are dropped — but they were never being consumed anyway. If preservation of descriptions is desired, add `input_types=` map separately (though `input_types` is for type annotations, not human descriptions).

**LOC:** 3 lines.
**Public API impact:** Runtime behavior change — the adapter will now correctly populate `_inputs_list`. Likely fixes a latent runtime bug (consumers relying on `_inputs_list` being `List[str]`). NOT a backwards-incompatible change — the dict form was never working as intended.
**Issue count collapsed:** 2 warnings on one line → 1 fix.
**Tier 2 regression test recommended** (this is a behavior fix, not pure typing hygiene).

---

### Cluster 5: `Awaitable[List[QuestionAnswer]]` cannot assign to `List[QuestionAnswer]` (interaction_tool.py:369)

**Citation:** `packages/kailash-kaizen/src/kaizen/tools/native/interaction_tool.py:163–168, :230, :346–369`

**`UserCallback` type alias (line 165–168):**

```python
UserCallback = Union[
    Callable[[List[Question]], List[QuestionAnswer]],
    Callable[[List[Question]], Awaitable[List[QuestionAnswer]]],
]
```

**`_answers` attribute declaration (line 230):**

```python
self._answers: List[QuestionAnswer] = []
```

**Body (line 346–369):**

```python
try:
    if asyncio.iscoroutinefunction(self._user_callback):
        answers = await asyncio.wait_for(
            self._user_callback(parsed_questions),
            timeout=self._timeout_seconds,
        )
    else:
        answers = await asyncio.wait_for(
            asyncio.to_thread(self._user_callback, parsed_questions),  # noqa
            timeout=self._timeout_seconds,
        )
except asyncio.TimeoutError:
    ...
except Exception as e:
    ...

# Store answers
self._answers = answers if answers else []   # ← :369
```

**Root cause:** `_user_callback` is `Optional[UserCallback]`. The union has TWO callable shapes — one returning `List[QuestionAnswer]` (sync), one returning `Awaitable[List[QuestionAnswer]]`. Calling `self._user_callback(parsed_questions)` returns the union `List[QuestionAnswer] | Awaitable[List[QuestionAnswer]]`. `asyncio.wait_for(awaitable, timeout)` is typed to accept any awaitable; pyright cannot prove the sync path's `asyncio.to_thread(...)` produces the right shape (it does at runtime — `to_thread` wraps the sync callable's return in an awaitable). The result is `answers` being inferred as `List[QuestionAnswer] | Awaitable[List[QuestionAnswer]]`.

**Q4 answer (await missing somewhere?):** No. The `await` is correctly on `asyncio.wait_for(...)` at line 350 and 355. The issue is that `asyncio.iscoroutinefunction` is a runtime check that pyright cannot use for type narrowing on an attribute (it CAN narrow on a local variable, but `self._user_callback` is an attribute — pyright invalidates narrowing on attributes across `await` boundaries).

**Cleanest fix:** Capture the callback into a local variable before the dispatch, then narrow on the local:

```python
callback = self._user_callback
assert callback is not None  # checked at line 336
try:
    if asyncio.iscoroutinefunction(callback):
        # callback is now Callable[[List[Question]], Awaitable[List[QuestionAnswer]]]
        answers = await asyncio.wait_for(
            callback(parsed_questions),
            timeout=self._timeout_seconds,
        )
    else:
        # callback is the sync variant
        answers = await asyncio.wait_for(
            asyncio.to_thread(callback, parsed_questions),
            timeout=self._timeout_seconds,
        )
```

If pyright still does not narrow (`iscoroutinefunction` returns `TypeGuard[CoroutineFunction]` which is sometimes flaky on Union of two Callable), fall back to:

```python
from typing import cast
answers_raw = await asyncio.wait_for(...)
answers = cast(List[QuestionAnswer], answers_raw)
```

**LOC:** 3 lines (local capture + minor restructure).
**Public API impact:** None.
**Issue count collapsed:** 1 warning → 1 fix.

---

### Cluster 6: `for_specialist` on Optional adapter (task_tool.py:283)

**Citation:** `packages/kailash-kaizen/src/kaizen/tools/native/task_tool.py:283`

```python
async def _execute_subagent(self, ...):
    # ...
    specialist_adapter = self._adapter.for_specialist(subagent_type)  # ← :283
```

The brief enumerates this as a `reportOptionalMemberAccess` warning, meaning `self._adapter` is `Optional`. Need to read the class declaration to confirm.

**Cleanest fix (predicted):** Typed guard at `_execute_subagent` entry:

```python
if self._adapter is None:
    raise RuntimeError(
        "TaskTool._adapter is None — construct via __init__ with adapter= kwarg"
    )
```

This matches `rules/zero-tolerance.md` Rule 3a (typed delegate guards for None backing objects).

**LOC:** 4 lines.
**Public API impact:** None — converts opaque AttributeError into typed RuntimeError.
**Issue count collapsed:** 1 warning → 1 fix.

---

## Sharding recommendation

Per `rules/autonomous-execution.md` MUST Rule 1 (≤500 LOC load-bearing logic, ≤5–10 invariants, ≤3–4 call-graph hops):

**Verdict:** **All 12 issues fit in ONE shard combined with Cluster A (BaseTool contract).** Total estimate:

| Cluster                                 | LOC     | Invariants                | Call-graph hops            |
| --------------------------------------- | ------- | ------------------------- | -------------------------- |
| 1 (notebook unbound `result`)           | ~2      | 1 (3-enum exhaustiveness) | 0 (local control flow)     |
| 2 (notebook cell_id Optional)           | ~2      | 1 (validator-narrowing)   | 1 (helper signatures)      |
| 3 (parser.py lazy sentinels)            | ~2      | 1 (optional-extras guard) | 0                          |
| 4 (adapter.py Signature call-shape)     | ~3      | 1 (caller correctness)    | 1 (Signature.**init**)     |
| 5 (interaction_tool callback narrowing) | ~3      | 1 (Union-of-Callable)     | 1 (asyncio APIs)           |
| 6 (task_tool adapter guard)             | ~4      | 1 (typed delegate guard)  | 1 (adapter.for_specialist) |
| **Total**                               | **~16** | **6**                     | **≤2 hops max**            |

This is well under the budget. A reasonable sizing for Cluster B+D as a SHARD is **B+D in one shard** (16 LOC, 6 invariants, 2 hops max) OR **merge with Cluster A** if A is similarly small. Each cluster is independent — no inter-cluster dependencies — so they can also be split into 2 commits inside one shard for cleaner `git log --grep`.

**Recommended commit boundary inside the shard:**

1. `fix(kaizen): notebook_tool result + cell_id type safety (clusters 1+2)` — 4 LOC
2. `fix(kaizen): research parser/adapter type safety (clusters 3+4)` — 5 LOC
3. `fix(kaizen): interaction_tool + task_tool optional guards (clusters 5+6)` — 7 LOC

Three small commits in one shard. Or one commit if granular history is not desired.

**Feedback-loop multiplier (Rule 3):** Pyright is the live feedback loop. Each cluster fix can be verified locally via `uv run pyright packages/kailash-kaizen/src/kaizen/` against the baseline at `workspaces/issue-814-kaizen-pyright/01-analysis/00-pyright-baseline.txt`. This justifies up to 3-5× the base budget; the actual work is far below even the base.

---

## Cross-cutting observations

- **Cluster 4 is a real bug**, not just typing hygiene. The `adapter.py:119` call has been passing `dict` where `List[str]` is required — `_inputs_list: List[str]` (`core.py:297`) is being silently corrupted. A Tier 2 test exercising `ResearchAdapter.create_signature_adapter` end-to-end MUST be added per `rules/orphan-detection.md` Rule 2 if no such test exists.
- **Clusters 3 and 5 are both `Optional`/`Union` narrowing failures** — pyright cannot correlate runtime guards (`if not FLAG`, `iscoroutinefunction`) with attribute types. The fix pattern (assert / local capture) is the same idiom; the cluster could be co-located in commit history for searchability.
- **Cluster 6 (task_tool) needs verification** — the brief lists the warning but the read-around-line was cut at 50 lines. The `_adapter` attribute declaration needs to be confirmed `Optional` to fully validate the proposed fix shape, but the fix shape is robust either way (typed guard works for any nullable case).

---

## File index (absolute paths)

- `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/tools/native/notebook_tool.py`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/tools/native/interaction_tool.py`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/tools/native/task_tool.py`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/research/parser.py`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/research/adapter.py`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/signatures/core.py` (Signature.**init** contract — read-only reference)
