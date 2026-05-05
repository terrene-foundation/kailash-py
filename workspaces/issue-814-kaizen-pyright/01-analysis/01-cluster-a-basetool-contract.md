# Cluster A — BaseTool Contract & 17 Override Sites

**Mission:** Ratify the `BaseTool.execute` contract for issue #814 (kaizen pyright cleanup), eliminating 17 `reportIncompatibleMethodOverride` diagnostics without breaking the production dispatch path.

**Sources:** read-only research, no edits, no `pyright` re-run.

---

## 1. BaseTool Contract (canonical)

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/tools/native/base.py`

| Item                | Value                                                                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Class               | `BaseTool(ABC)`                                                                                                                                  |
| Define site         | `base.py:91`                                                                                                                                     |
| `execute` signature | `async def execute(self, **kwargs) -> NativeToolResult:`                                                                                         |
| Define site         | `base.py:149-165` (decorated `@abstractmethod`)                                                                                                  |
| Async               | yes                                                                                                                                              |
| Return type         | `NativeToolResult`                                                                                                                               |
| Helper wrapper      | `execute_with_timing(self, **kwargs) -> NativeToolResult` at `base.py:236-246` — calls `self.execute(**kwargs)` then injects `execution_time_ms` |

**Docstring contract** (`base.py:151-164`, condensed):

- "Execute the tool with the given parameters."
- `Args: **kwargs: Tool-specific parameters`
- `Returns: NativeToolResult with success/failure and output`
- "Implementations should NOT raise exceptions for normal failures. Instead, return `NativeToolResult.from_error()` or `NativeToolResult.from_exception()`."

**Class-attribute contract** (`base.py:135-138`): subclasses MUST set `name`, `description`, `danger_level`, `category`. `__init__` (`base.py:140-147`) raises `ValueError` if `name` or `description` is empty.

**Schema contract** (`base.py:167-185`, parallel abstract method): every tool also implements `get_schema() -> Dict[str, Any]` returning a JSON Schema with `type`, `properties`, `required` — used by `get_full_schema()` for OpenAI function-calling format.

> **Implication:** every tool already declares its parameter set twice — once in the `execute` signature, once in `get_schema()`. The signature is for static analysis; the schema is for the LLM. Pyright is complaining about the first; the LLM only sees the second.

---

## 2. Override-Site Inventory (17 sites)

| #   | File:Line                 | Tool class            | Positional param count<sup>†</sup> | `**kwargs`? | Param shape                                                                                                                                                                           |
| --- | ------------------------- | --------------------- | ---------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `bash_tools.py:125`       | `BashTool`            | 4                                  | no          | `command: str, timeout: int = 120, cwd: Optional[str] = None`                                                                                                                         |
| 2   | `file_tools.py:60`        | `ReadFileTool`        | 4                                  | no          | `path: str, offset: int = 0, limit: int = 2000`                                                                                                                                       |
| 3   | `file_tools.py:155`       | `WriteFileTool`       | 3                                  | no          | `path: str, content: str`                                                                                                                                                             |
| 4   | `file_tools.py:225`       | `EditFileTool`        | 5                                  | no          | `path: str, old_string: str, new_string: str, replace_all: bool = False`                                                                                                              |
| 5   | `file_tools.py:326`       | `GlobTool`            | 3                                  | no          | `pattern: str, path: str = "."`                                                                                                                                                       |
| 6   | `file_tools.py:399`       | `GrepTool`            | 5                                  | no          | `pattern: str, path: str = ".", file_glob: str = "*", case_insensitive: bool = False`                                                                                                 |
| 7   | `file_tools.py:569`       | `ListDirectoryTool`   | 2                                  | no          | `path: str`                                                                                                                                                                           |
| 8   | `file_tools.py:643`       | `FileExistsTool`      | 2                                  | no          | `path: str`                                                                                                                                                                           |
| 9   | `interaction_tool.py:246` | `AskUserQuestionTool` | 4                                  | **yes**     | `questions: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None, **kwargs`                                                                                                |
| 10  | `notebook_tool.py:105`    | `NotebookEditTool`    | 7                                  | **yes**     | `notebook_path: str, new_source: str, cell_id: Optional[str] = None, cell_type: str = "code", edit_mode: str = "replace", **kwargs`                                                   |
| 11  | `process_tool.py:365`     | `KillShellTool`       | 3                                  | **yes**     | `shell_id: str, **kwargs`                                                                                                                                                             |
| 12  | `process_tool.py:478`     | `TaskOutputTool`      | 5                                  | **yes**     | `task_id: str, block: bool = True, timeout: float = 30000, **kwargs`                                                                                                                  |
| 13  | `search_tools.py:64`      | `WebSearchTool`       | 3                                  | no          | `query: str, num_results: int = 5`                                                                                                                                                    |
| 14  | `search_tools.py:227`     | `WebFetchTool`        | 3                                  | no          | `url: str, extract_text: bool = True`                                                                                                                                                 |
| 15  | `skill_tool.py:96`        | `SkillTool`           | 3                                  | no          | `skill_name: str, load_additional_files: bool = True`                                                                                                                                 |
| 16  | `task_tool.py:117`        | `TaskTool`            | 8                                  | no          | `subagent_type: str, prompt: str, description: str = "", model: Optional[str] = None, max_turns: Optional[int] = None, run_in_background: bool = False, resume: Optional[str] = None` |
| 17  | `todo_tool.py:278`        | `TodoWriteTool`       | 3                                  | **yes**     | `todos: List[Dict[str, Any]], **kwargs`                                                                                                                                               |

<sup>†</sup> Counts as pyright reports them — includes `self`. Base method count is 2 (`self` + `**kwargs`). All overrides are `async def` and return `NativeToolResult`.

**Sanity reference (NOT in the 17):** `planning_tool.py` exports two tools (`EnterPlanModeTool` at line 170, `ExitPlanModeTool` at line 282). Both already use `(self, ..., **kwargs) -> NativeToolResult` pattern with all params keyword-only-style, and neither errors on pyright. They are the closest existing exemplar of a "compatible" override.

---

## 3. Override Patterns — Natural Clusters

| Cluster                                                 | Members                                         | Trait                                                                                                                                              |
| ------------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Bare typed positional** (no `**kwargs`) — 12 sites | bash, file_tools×7, search_tools×2, skill, task | One or more required typed args; no kwargs sink. **Pyright: 2 errors each** ("positional mismatch" + "no corresponding `**kwargs`").               |
| **B. Typed positional + `**kwargs` sink\*\* — 5 sites   | interaction, notebook, process×2, todo          | Typed args plus a trailing `**kwargs` (mostly ignored). **Pyright: 1 error each** ("positional mismatch" only — already accepts arbitrary kwargs). |

**Observation.** Cluster B is what Cluster A WOULD look like if a `**kwargs` sink were added. The fix shape is mechanical and uniform.

---

## 4. Caller Patterns — `BaseTool.execute` Is Always Called via Kwargs Spread

Every production caller funnels through `NativeToolRegistry.execute(tool_name, params)`, which spreads a `Dict[str, Any]` as kwargs.

**The single dispatch site:** `tools/native/registry.py:325-354`

```python
async def execute(self, tool_name: str, params: Dict[str, Any]) -> NativeToolResult:
    tool = self._tools.get(tool_name)
    if not tool:
        return NativeToolResult.from_error(f"Unknown tool: {tool_name}. ...")
    try:
        result = await tool.execute_with_timing(**params)   # ← kwargs spread
        ...
```

`execute_with_timing` (`base.py:243`) forwards: `result = await self.execute(**kwargs)`.

**The single production caller of `registry.execute`:** `packages/kaizen-agents/src/kaizen_agents/runtime_adapters/kaizen_local.py:971`

```python
result = await self._tool_registry.execute(tool_name, tool_args)
```

`tool_args` originates from LLM tool-calling JSON (a dict), so by construction it is always a kwargs-shaped `Dict[str, Any]`.

**Test callers** (`tests/unit/tools/native/`) all use the same pattern:

- `test_registry.py:430`: `registry.execute("exec_tool", {"text": "hello"})`
- `test_registry.py:440`: `registry.execute("unknown_tool", {})`
- `test_registry.py:465`: `registry.execute("failing_tool", {})`
- `test_task_tool.py:744`: `await registry.execute(...)`
- `test_skill_tool.py:559`: `await registry.execute(...)`

**Conclusion: zero callers pass positional args to `tool.execute(...)` directly.** Every call is either `registry.execute(name, dict)` (which becomes `execute_with_timing(**dict)` → `execute(**dict)`) or, in tests, the same shape. Adding a `**kwargs` sink to every override is **runtime-safe and backwards-compatible** because no caller relies on a fixed positional ordering.

> **Cross-check vs `agent-reasoning.md`:** The LLM does NOT see the Python `execute` signature; it sees `get_schema()` (`base.py:167-185`). The Python signature is purely a static-analysis artifact. This means the contract decision is purely a typing concern, not an LLM-reasoning concern.

---

## 5. Existing Tool Registry / Dispatcher

Yes — `NativeToolRegistry` at `tools/native/registry.py:51` is the single dispatcher. Key surface:

| Method                       | Signature         | Use                                                |
| ---------------------------- | ----------------- | -------------------------------------------------- |
| `register(tool: BaseTool)`   | `registry.py:58`  | Adds tool to `_tools` dict by `tool.name`.         |
| `register_defaults(...)`     | `registry.py:99`  | Bulk-registers built-ins.                          |
| `execute(tool_name, params)` | `registry.py:325` | The dispatcher. Always spreads `params` as kwargs. |
| `get_tool_schemas(...)`      | `registry.py:248` | Returns the JSON-schema list the LLM consumes.     |

The dispatcher's contract is firmly **kwargs-spread**. There is no positional-args path anywhere.

---

## 6. Recommendation: **Option 1 — Widen `BaseTool.execute` to `(self, **kwargs)`and add`**kwargs` to every override**

> Pyright's complaint is mechanical, not architectural: every override declares typed required params that are not nameable through the base's bare `**kwargs`. Per LSP (Liskov), an override may relax requirements but not tighten them — declaring extra required positional params tightens. The fix is to keep the base permissive and make every override _accept_ extra kwargs without consuming them.

### What lands

1. **No change to `BaseTool.execute` signature** — it already is `async def execute(self, **kwargs) -> NativeToolResult` (`base.py:149`). The base is already permissive; the overrides are too strict.
2. **Add `**kwargs: Any` to the 12 Cluster A overrides\*\* that lack it. (Cluster B already has it; pyright's residual "positional mismatch" on those 5 is the same mechanical issue and is also resolved by the keyword-only convention below.)
3. **Make every typed param keyword-only.** Insert a `*,` before the first typed param so the override formally accepts no positional args. This satisfies pyright's "positional parameter count mismatch" arm.

Per-tool change shape (illustrative — `BashTool` example):

```python
# Before (bash_tools.py:125)
async def execute(
    self,
    command: str,
    timeout: int = 120,
    cwd: Optional[str] = None,
) -> NativeToolResult:

# After
async def execute(
    self,
    *,
    command: str,
    timeout: int = 120,
    cwd: Optional[str] = None,
    **kwargs: Any,
) -> NativeToolResult:
```

### Why this option

| Criterion                                    | Verdict                                                                                                                                                                                                                                                                                                                                                  |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Caller pattern fit**                       | Perfect. Every caller already passes kwargs (§4). The `*,` makes the keyword-only convention explicit and the `**kwargs` accepts spurious LLM-emitted fields without `TypeError`.                                                                                                                                                                        |
| **Runtime breakage risk**                    | Effectively zero. No caller passes positional args (§4 grep). The keyword-only marker makes the existing call shape — `execute(**dict)` — the only valid one.                                                                                                                                                                                            |
| **Regression-test feasibility**              | High. Each tool's existing unit test already calls `tool.execute(...)` via kwargs (verified in `tests/unit/tools/native/`). One regression test per tool: `await tool.execute(**{...})` before AND after the change to lock the contract. Optional structural-invariant test: `inspect.signature(tool.execute).parameters[<each>].kind == KEYWORD_ONLY`. |
| **Alignment with MCP/Kailash tool surfaces** | MCP tool calling is JSON-object → kwargs by definition (LLM emits `{"tool": "x", "arguments": {...}}`). OpenAI function-calling is identical. Keyword-only matches the wire shape. The schema contract in `get_schema()` is unchanged.                                                                                                                   |
| **Defensive vs LLM hallucinated kwargs**     | `**kwargs: Any` silently absorbs unknown fields the LLM hallucinates (e.g. an extra `language` field on `bash`); without it, `TypeError: unexpected keyword argument 'language'` would crash the dispatcher and propagate out via `from_exception`. The current Cluster B tools already do this; the fix extends the convention.                         |
| **Foundation independence**                  | Unaffected. No commercial-product references; pure typing housekeeping.                                                                                                                                                                                                                                                                                  |
| **`agent-reasoning.md` compliance**          | Unaffected. The LLM still calls `get_schema()`; the Python signature change is invisible to it.                                                                                                                                                                                                                                                          |
| **Spec churn**                               | None. There is no `specs/` entry that pins the signature shape (per workspace `briefs/`); this is implementation detail.                                                                                                                                                                                                                                 |

### Why NOT Option 2 (single `params: dict` arg)

- Forces a refactor of every Cluster B test that passes individual kwargs (e.g. `await tool.execute(shell_id="123")` → `await tool.execute({"shell_id": "123"})`).
- Forces `execute_with_timing` (`base.py:236`) to change shape, propagating the dict to every caller of `execute_with_timing` directly.
- Loses inline parameter type hints — the typed signature is the cheapest static-analysis surface available; collapsing to a `dict` defeats every per-arg pyright narrowing the file currently enjoys.
- Diverges from the Cluster B exemplar (`planning_tool.py`) which has been clean since landing.

### Why NOT Option 3 (Pydantic input schemas per tool)

- Heaviest churn: introduces 17 new model classes, a new validation hop, and a registry-side `model_validate(params)` call before dispatch.
- Adds runtime cost on every tool call (validation), where the current path is a direct kwargs spread.
- The schema layer already exists at `get_schema()`; duplicating it as Pydantic introduces a third source of truth (signature, JSON-schema, Pydantic model) that can drift.
- Worth reconsidering as a separate workstream IF the kaizen team wants runtime input validation; out of scope for a pyright cleanup.

### Edge case worth calling out

`AskUserQuestionTool.execute` (interaction_tool.py:246) has a side effect: `pyright` separately warns on line 369 that `_answers` may be assigned an `Awaitable`. Cluster A fix won't address that — it's an unrelated `reportAttributeAccessIssue` and belongs to a different cluster.

---

## 7. Shard-Size Estimate

### Option 1 (recommended)

| Item                                               | Count   | LOC                                             |
| -------------------------------------------------- | ------- | ----------------------------------------------- |
| Files touched                                      | 9       | —                                               |
| `def execute(...)` headers rewritten               | 17      | ~80 (avg ~5 lines each, mostly the param block) |
| `Any` import added if missing                      | up to 9 | up to 9                                         |
| Optional structural-invariant tests (one per tool) | 17      | ~50                                             |
| **Total load-bearing logic LOC**                   | —       | **0**                                           |
| **Total mechanical / boilerplate LOC**             | —       | **~140**                                        |

The change is pure boilerplate per `rules/autonomous-execution.md` MUST Rule 2: "Boilerplate scales ~5× further than logic before sharding triggers, because the model holds a single pattern and stamps it out." The single pattern here is `def execute(self, *, <named params>, **kwargs: Any)`.

**Single shard, well within the ≤500 LOC load-bearing logic budget.** No invariants beyond LSP compliance. Zero call-graph hops.

### Option 2 (single `params` arg)

| Item                                   | Count                                       | LOC                                                    |
| -------------------------------------- | ------------------------------------------- | ------------------------------------------------------ |
| Override sites rewritten               | 17                                          | ~120 (must extract dict-to-locals at top of each body) |
| `execute_with_timing` signature change | 1                                           | 5                                                      |
| Test-call refactor                     | ~25 sites across `tests/unit/tools/native/` | ~80                                                    |
| **Total**                              | —                                           | **~205**                                               |

Larger blast radius, more invariants (test-call sites must all migrate atomically), and changes both production and test surfaces.

### Option 3 (Pydantic schemas)

| Item                                               | Count | LOC      |
| -------------------------------------------------- | ----- | -------- |
| New `<Tool>Input` Pydantic models                  | 17    | ~250     |
| Registry validation hop                            | 1     | ~15      |
| Override bodies adapted to consume validated model | 17    | ~80      |
| Test-call additions for validation errors          | 17    | ~100     |
| **Total**                                          | —     | **~445** |

Touches the dispatcher, runtime validation, AND every override; large invariant count. Closest to the budget ceiling.

---

## 8. Decision

**Pick Option 1.** It is the smallest mechanical change that converts every `reportIncompatibleMethodOverride` from red to green, leaves the dispatch path untouched, costs ~140 LOC of pure boilerplate in one shard, and matches the existing Cluster B exemplar (`planning_tool.py`). Under `rules/autonomous-execution.md` MUST Rule 2 this is one shard; under MUST Rule 4 (fix-immediately) the same shard can also fix the residual `reportPossiblyUnbound` in `notebook_tool.py:229-245` and the `reportOptionalMemberAccess` in `task_tool.py:283` if they sit in the same edit window — though those are technically Cluster B/C concerns (not in scope of this brief).

**Confidence:** High. Caller-pattern grep is exhaustive; the dispatch funnel through `registry.execute`+`execute_with_timing` provably forces kwargs spread.

---

## Appendix — Key file:line citations

- `BaseTool` class: `packages/kailash-kaizen/src/kaizen/tools/native/base.py:91`
- Abstract `execute`: `packages/kailash-kaizen/src/kaizen/tools/native/base.py:149-165`
- `execute_with_timing` wrapper: `packages/kailash-kaizen/src/kaizen/tools/native/base.py:236-246`
- Registry dispatcher: `packages/kailash-kaizen/src/kaizen/tools/native/registry.py:325-354`
- Production caller: `packages/kaizen-agents/src/kaizen_agents/runtime_adapters/kaizen_local.py:971`
- Cluster B exemplar: `packages/kailash-kaizen/src/kaizen/tools/native/planning_tool.py:170, 282`
- Pyright baseline reference: `workspaces/issue-814-kaizen-pyright/01-analysis/00-pyright-baseline.txt:1-72`
