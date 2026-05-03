# Draft GH issue — kaizen pyright cleanup (follow-up to T2)

**DO NOT FILE WITHOUT EXPLICIT USER APPROVAL** (per `rules/upstream-issue-hygiene.md` MUST Rule 1).

## Title

`fix(kaizen): resolve pre-existing pyright diagnostics in tools/native + research`

## Body

### Affected API

`kailash_kaizen.tools.native.*` (BaseTool subclass family) and `kailash_kaizen.research.*`.

### Symptoms

Pyright surfaces multiple pre-existing diagnostics in `packages/kailash-kaizen/src/`:

1. **BaseTool.execute signature drift** — 7 sites override `BaseTool.execute` with mismatched positional/keyword signatures:
   - `tools/native/skill_tool.py:96` — base has 2 params; override has 3 + `**kwargs`
   - `tools/native/process_tool.py:365`, `:478` — overrides have 3, 5 params
   - `tools/native/todo_tool.py:278` — override has 3
   - `tools/native/notebook_tool.py:105` — override has 7
   - `tools/native/task_tool.py:117` — signature mismatch
   - `tools/native/planning_tool.py` — `kwargs` not accessed (warning)

2. **Missing modules referenced by `__init__`** — `kaizen.research.__init__.py:26/35/39` imports `.advanced_patterns`, `.experimental`, `.intelligent_optimizer` — all unresolved per pyright.

3. **Possibly-unbound variables** — `tools/native/notebook_tool.py:229/230/242/245` — `result` reachable on a path where it's never assigned.

4. **Type argument mismatches** — `research/adapter.py:119` passes `dict[str, str]` where `List[str] | None` is expected (×2).

### Reproduction

```bash
cd packages/kailash-kaizen
uv run pyright src/kaizen/tools/native/skill_tool.py
uv run pyright src/kaizen/research/__init__.py
# Each command reports the diagnostics above.
```

### Expected vs actual

- **Expected:** `BaseTool` subclass methods type-check against the base contract; `__init__` imports resolve; `execute` paths assign before use.
- **Actual:** Pyright surfaces 20+ diagnostics across the listed files; pre-dates 2026-03-19 (`git log --oneline packages/kailash-kaizen/src/kaizen/tools/native/notebook_tool.py | head -1` → `b511f186 style(eatp,dataflow,kaizen): standardize code formatting...`).

### Severity

**MEDIUM** — diagnostics are static-analysis only; no runtime crash observed (the override-mismatch is type-system strictness, not Python ABC enforcement; missing imports surface only when those symbols are accessed). But the BaseTool contract drift is a maintenance hazard — future tool implementations inherit the inconsistency.

### Acceptance criteria

- [ ] `BaseTool.execute` contract clarified (decision: keep narrow signature + `**kwargs` on the base, OR widen base to accept all current call patterns).
- [ ] Every `BaseTool` subclass `execute` matches the ratified base signature.
- [ ] `kaizen/research/__init__.py` imports resolve — either by creating the missing modules (advanced_patterns, experimental, intelligent_optimizer) OR by removing the imports if those features are not on roadmap.
- [ ] `notebook_tool.py:229+` paths guarantee `result` is assigned before use (initialize at top OR raise on the missing-branch).
- [ ] `pyright packages/kailash-kaizen/src/` reports zero NEW diagnostics in the listed files.
- [ ] Regression test in `packages/kailash-kaizen/tests/regression/` calling each subclass's `execute` (per `rules/testing.md` "One Direct Test Per Variant").

### Discovery context (FOR HUMAN — strip before filing per upstream-issue-hygiene if filing publicly)

Surfaced during T2 of issue #781 TODO-NNN cleanup workstream — comment-only PR triggered pyright re-analysis on touched files. Diagnostics SHA-grounded as pre-existing in T2 PR body.
