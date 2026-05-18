# Brief — Resurrect `kaizen.nodes.rag`

## Origin

User-gated 2026-05-19 during the issue #891 workstream. The #891 collision
census found `kaizen.nodes.rag` (17 modules, ~53 RAG node classes) is
**dead-on-arrival since the 2026-03-11 monorepo move** (`b553104c`): its
relative imports point at a non-existent `kaizen.nodes.{base,code,data,logic}`

- `kaizen.runtime` tree (the symbols actually live in `kailash.*`). Not a live
  collision (dead code never registers) → dropped from the #891 PR; user chose to
  resurrect as a separate PR this session. Lineage:
  `workspaces/issue-891-hybridsearch-collision/journal/0004`.

## Scope (de-risked by 01-analysis)

1. **Import repair** — repoint every broken `..X` / `...X` relative import in
   the 17 modules to `kailash.X`. All 9 distinct targets verified to exist:
   `kailash.nodes.{base,code.python,data.streaming,data.sql,logic,logic.workflow,api.rest}`,
   `kailash.runtime.async_local`, `kailash.workflow.graph`. `..data.cache` /
   `..data.readers` are already commented-out TODOs (CacheNode/ImageReaderNode
   genuinely absent) — leave commented.
2. **StreamingRAGNode rename** — `rag/realtime.StreamingRAGNode` →
   `RealtimeStreamingRAGNode`. It is the ONLY intra-rag duplicate-registered
   name (realtime vs optimized). MANDATORY: kailash 2.23.0's live cross-module
   guard (#891) raises `NodeConfigurationError` at import on this collision, so
   the package cannot import until it is resolved. `rag/__init__.py:177`
   already aliases `as RealtimeStreamingRAGNode`, anticipating this.
3. **Clean-import gate** — `import kaizen.nodes.rag` + each of the 17 modules
   MUST succeed under kailash 2.23.0. This is the definitive structural gate:
   Python runs every class body + `@register_node` decorator (incl. its
   constructor validation) at import; a clean import under the live guard
   proves imports resolve AND no residual cross-module collision exists.
4. **Import-smoke regression test** — `tests/regression/`, import all 17
   modules, assert representative RAG nodes register.
5. **kaizen version bump + CHANGELOG** — 2.22.0 → 2.23.0 (the package becoming
   functional is a feature; minor bump). Pin already `kailash>=2.23.0`.

## Out of scope (recommended follow-up, not a blocker)

Deep per-node behavioral test coverage of the ~53 RAG node classes. The
clean-import gate is the structural floor; exhaustive behavioral validation of
53 never-exercised nodes is a large incremental test workstream appropriately
filed as a follow-up, not gating the package becoming importable + collision-free.

## Success criteria

- All 17 `kaizen.nodes.rag.*` modules import clean under kailash 2.23.0.
- `kaizen.nodes.rag` package imports clean (no guard `NodeConfigurationError`).
- `RealtimeStreamingRAGNode` + `StreamingRAGNode` (optimized) both register
  distinctly; no `StreamingRAGNode` collision.
- Import-smoke regression test green.
- kaizen 2.23.0 released + clean-venv verified.
