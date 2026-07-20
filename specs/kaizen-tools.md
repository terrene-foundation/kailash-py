# Kaizen Native Tools — `kaizen.tools.native`

Domain truth for the BaseTool family that backs Kaizen agents' native tool calls
(`Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `WebSearch`, `WebFetch`,
`Task`, `TodoWrite`, `Skill`, `NotebookEdit`, `EnterPlanMode`, `ExitPlanMode`).

This spec describes the contract as it ships on `main` after issue #814 closed
the override-conformance gap (Shard 1, PR #818) and the orphan-cluster cleanup
(Shard 2). Every citation is grep-resolvable per `rules/spec-accuracy.md` Rule 1.

## Base Contract

`packages/kailash-kaizen/src/kaizen/tools/native/base.py`:

```python
class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    danger_level: ClassVar[DangerLevel]
    category: ClassVar[ToolCategory]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> NativeToolResult: ...

    def get_schema(self) -> Dict[str, Any]: ...

    async def execute_with_timing(self, **kwargs: Any) -> NativeToolResult:
        start = time.perf_counter()
        result = await self.execute(**kwargs)
        result.execution_ms = (time.perf_counter() - start) * 1000
        return result
```

The base method is declared `async def execute(self, **kwargs) -> NativeToolResult`.
The signature is intentionally permissive — the parameter dispatch contract is
"the registry passes all caller-provided keys via `**`-spread; the subclass
declares the keys it consumes as keyword-only and accepts the rest into a sink".

## Override Pattern (MUST)

Every concrete subclass MUST declare `execute` as:

```python
async def execute(
    self,
    *,                        # keyword-only marker
    <named_param_1>: <type>,
    <named_param_2>: <type> = <default>,
    ...
    **_kwargs: Any,           # sink for unknown keys
) -> NativeToolResult: ...
```

Three structural invariants:

1. **Keyword-only marker (`*,`) before named params.** `ToolRegistry` dispatches
   via `tool.execute_with_timing(**params)` (`registry.py:328`); positional args
   never reach the override. Declaring named params keyword-only matches the
   runtime contract and prevents a future positional caller from binding to
   the wrong parameter.
2. **`**_kwargs: Any`sink.** LLM-emitted JSON arguments may contain keys the
tool does not recognize (model hallucination, schema drift, extra context).
The sink prevents a`TypeError: unexpected keyword argument`from killing
the agent loop. The leading underscore documents the parameter as
intentionally not consumed in the body — pyright LSP advisory hints`_<name> is not accessed` are advisory only and MUST NOT trigger removal of
   the sink (removal breaks LSP override conformance across the family).
3. **Return type `NativeToolResult`.** Success constructed via
   `NativeToolResult.from_success(<content>, **metadata)`; failure via
   `NativeToolResult.from_error(<message>)`. Raising exceptions out of `execute`
   is BLOCKED — uncaught exceptions kill the agent loop instead of surfacing
   typed errors to the LLM.

## Subclass Inventory

19 concrete subclasses ship under `packages/kailash-kaizen/src/kaizen/tools/native/`
(AST-verified count). Grouped by file:

| File                  | Subclasses                                                                                                     |
| --------------------- | -------------------------------------------------------------------------------------------------------------- |
| `bash_tools.py`       | `BashTool`                                                                                                     |
| `file_tools.py`       | `ReadFileTool`, `WriteFileTool`, `EditFileTool`, `GlobTool`, `GrepTool`, `ListDirectoryTool`, `FileExistsTool` |
| `interaction_tool.py` | `AskUserQuestionTool`                                                                                          |
| `notebook_tool.py`    | `NotebookEditTool`                                                                                             |
| `planning_tool.py`    | `EnterPlanModeTool`, `ExitPlanModeTool`                                                                        |
| `process_tool.py`     | `KillShellTool`, `TaskOutputTool`                                                                              |
| `search_tools.py`     | `WebSearchTool`, `WebFetchTool`                                                                                |
| `skill_tool.py`       | `SkillTool`                                                                                                    |
| `task_tool.py`        | `TaskTool`                                                                                                     |
| `todo_tool.py`        | `TodoWriteTool`                                                                                                |

Production caller: `packages/kaizen-agents/src/kaizen_agents/runtime_adapters/kaizen_local.py`
calls `registry.execute(tool_name, tool_args)` with LLM-emitted JSON args.

## Dispatcher

`packages/kailash-kaizen/src/kaizen/tools/native/registry.py:325` —
`ToolRegistry.execute(name: str, params: Dict[str, Any])` looks up the tool by
`name`, validates `danger_level` against the registry's allow-list, and calls
`tool.execute_with_timing(**params)` at `registry.py:347`. The dispatcher is the single hot path —
no other production callsite invokes `tool.execute(...)` directly.

## LLM-Facing Surface

The LLM consumes `BaseTool.get_schema()` (`base.py:168`), NOT the Python
signature. `get_schema()` returns the JSON-schema shape the LLM uses to
construct tool calls:

```python
{
    "type": "object",
    "properties": {
        "<param_name>": {"type": "string", "description": "..."},
        ...
    },
    "required": ["<required_param>", ...],
}
```

Signature-level changes (widening kwargs, adding sinks, reordering params) are
invisible to the LLM. Schema-level changes (adding/removing/renaming keys in
`get_schema()`) ARE visible and require explicit migration of agent prompts.

## Error Contract

Every documented failure mode in a subclass MUST return `NativeToolResult.from_error(...)`
with an actionable message. Examples:

- `BashTool.execute(command="git push --force")` → `from_error("Command blocked
by sandbox: matches BLOCKED_PATTERNS regex")`
- `WebFetchTool.execute(url="...", extract_text=True)` when beautifulsoup4 is
  missing → `from_error("extract_text=True requires beautifulsoup4 — install
via pip install 'kailash-kaizen[web-search]' or pass extract_text=False to
receive raw HTML.")`
- `NotebookEditTool.execute(mode=<unknown>)` → `from_error("Invalid edit mode
'<value>'; valid: insert, replace, delete")`. `if/elif` over `EditMode` ends
  with explicit `else: raise RuntimeError("unreachable: ...")` per
  `rules/zero-tolerance.md` Rule 2 (no fall-through default that masks new modes).

## Optional Dependencies

Two optional-extras groups declared in
`packages/kailash-kaizen/pyproject.toml::[project.optional-dependencies]`:

| Extra        | Packages                                         | Used by                                                                |
| ------------ | ------------------------------------------------ | ---------------------------------------------------------------------- |
| `research`   | `arxiv>=2.0`, `pypdf>=4.0`                       | `kaizen.research.parser` (`ResearchParser` arXiv search + PDF parsing) |
| `web-search` | `duckduckgo-search>=6.0`, `beautifulsoup4>=4.12` | `kaizen.tools.native.search_tools` (`WebSearchTool`, `WebFetchTool`)   |

Install via:

```bash
pip install 'kailash-kaizen[research]'
pip install 'kailash-kaizen[web-search]'
pip install 'kailash-kaizen[research,web-search]'
```

### Lazy-Import Sentinel Pattern

Each optional dep follows the canonical lazy-import sentinel pattern per
`rules/dependencies.md` § "Declared = Imported":

```python
# Module top — sentinel captures import outcome
try:
    from <package> import <Symbol> as _<Symbol>
except ImportError:
    _<Symbol> = None  # type: ignore[assignment]

# Call site — raise typed ImportError when sentinel is None
def some_method(self, ...):
    if _<Symbol> is None:
        raise ImportError(
            "<feature> requires <package> — install via "
            "`pip install 'kailash-kaizen[<extra>]'` or pass "
            "<fallback_kwarg> to <fallback_behavior>."
        )
    ...
```

Silent degradation (returning a default value when the dep is missing) is
BLOCKED per `rules/dependencies.md` BLOCKED anti-patterns. Loud failure at
the call site lets the LLM caller surface the install hint to the user.

## Sandbox Guards

Tools that access OS resources MUST validate inputs before execution. Examples:

- `BashTool` — `BLOCKED_PATTERNS` regex sweep (defined at `bash_tools.py:44`,
  compiled at `bash_tools.py:91`), `allowed_commands` / `blocked_commands`
  allowlist, `sandbox_mode` toggle, timeout cap.
- `ReadFileTool`, `WriteFileTool`, `EditFileTool` — `validate_safe_path` +
  absolute-path check (`file_tools.py:69`, `:165`, `:243`).
- `WebFetchTool` — URL validation: scheme allowlist (`http`, `https`),
  `BLOCKED_URL_PATTERNS` regex sweep (defined at `search_tools.py:183`,
  enforced at `search_tools.py:235`), redirect cap (`max_redirects=5` at
  `search_tools.py:271`), content-length cap (`max_content_length`).

The sandbox layer is enforced before `**_kwargs: Any` widening. Adding `**_kwargs`
to an override never bypasses input validation — validation runs on the
named params declared in the same override.

## Testing Contract

Per `rules/testing.md` § "One Direct Test Per Variant In Every Delegating Pair":

1. **Direct unit test per subclass.** Each of the 19 subclasses has a unit test
   under `packages/kailash-kaizen/tests/unit/tools/native/test_<lowercase_tool>.py`
   that calls `await tool.execute(**args)` directly and asserts both success
   and known-failure paths.
2. **Behavioral regression for runtime bugs.** `tests/regression/test_issue_814_*`
   files exercise the corrected behavior (per `rules/testing.md` "Behavioral
   Regression Tests Over Source-Grep").
3. **`get_schema()` shape test.** Each subclass has a Tier 1 test asserting
   `get_schema()` returns the documented JSON shape and required-keys list
   matches the override's keyword-only params.

Tier 2 / Tier 3 coverage is via the production caller path (`kaizen_local.py`
→ `ToolRegistry.execute` → tool subclass) under
`packages/kailash-kaizen/tests/integration/`.

## See Also

- `kaizen-core.md` — `BaseAgent`, agent lifecycle, tool registry initialization
- `kaizen-providers-provider-system.md` — Provider system, tool routing
- `kaizen-providers-tool-integration.md` — MCP integration
- `kaizen-llm-deployments.md` — LLM deployment surface that consumes
  `get_schema()` for tool-call construction
- `rules/dependencies.md` — Lazy-import sentinel + optional-extras patterns
- `rules/zero-tolerance.md` Rule 6a — Public-API removal + deprecation cycle

## Change Log

- 2026-05-04 (#814): created. Documents the BaseTool contract as it ships
  after PR #818 (Cluster A: 17 BaseTool override sites widened to keyword-only
  - `**_kwargs: Any` sink) + Shard 2 (orphan cleanup of vestigial
    `kaizen.research` integration subsystem; addition of `research` + `web-search`
    optional extras; bs4 silent-degradation → loud failure in `WebFetchTool`).
