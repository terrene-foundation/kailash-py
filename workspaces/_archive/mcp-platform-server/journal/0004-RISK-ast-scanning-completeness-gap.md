---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T12:00:00Z
author: agent
session_turn: 1
project: mcp-platform-server
topic: AST-based scanning cannot guarantee complete introspection results
phase: analyze
tags:
  [
    ast-scanning,
    introspection,
    completeness,
    platform-map,
    detection-heuristics,
  ]
---

# RISK: AST Scanning Completeness Gap

## Background

The MCP platform server's Tier 1 introspection tools (GAP-2 resolution) use AST-based source scanning instead of runtime registry queries. This was a necessary architectural pivot because the MCP server runs as a separate process without access to framework registries (DataFlow, Nexus, Kaizen).

During Red Team Round 2, systematic analysis of AST scanning reliability across all three framework contributors revealed that static analysis produces incomplete results in several real-world scenarios.

## The Risk

AST scanning cannot detect:

1. **Dynamic model registration** -- DataFlow models registered via `ModelRegistry.register_model()` or `DataFlowEngine.register_model()` rather than `@db.model` decorator
2. **Models in external packages** -- `@db.model` classes defined in installed packages outside `project_root` (e.g., `pip install company-models`)
3. **Indirect agent inheritance** -- Kaizen agents that subclass an intermediate class (not `BaseAgent` directly) defined in a different file
4. **Imperative handler registration** -- Nexus handlers added via `app.add_handler()` calls with variable names that are not statically resolvable

The combined detection rate is estimated at >90% for typical projects but can drop to ~60% for enterprise projects with extensive dynamic registration, shared model packages, or deep agent inheritance hierarchies.

## Impact

If the platform server returns 8 of 10 models to Claude Code, the LLM trusts these as complete and generates code that does not account for the 2 missing models. This is more dangerous than returning 0 models (which signals failure) because partial results create false confidence.

The `platform_map()` cross-framework connection graph is especially affected -- missing models mean missing connections, which means Claude Code does not understand the full architecture.

## Mitigation

The R2 report (04-red-team-r2.md) recommends:

1. **Completeness indicator**: Every introspection tool response includes `scan_info` with detection method, files scanned, and known limitations
2. **`platform_map()` metadata**: Top-level `scan_metadata` field in the response schema so consumers can assess result quality
3. **Future escape hatch**: Optional `kailash-models.json` manifest for projects to declare models/agents/handlers that AST cannot detect
4. **Detection heuristics**: Broad matching (`@anything.model` for DataFlow, class name containing "Agent" for Kaizen) trades false positive risk for better false negative coverage

## Consequences

- Implementation must add `scan_info` to all Tier 1 tool responses (TSG-501, TSG-502, TSG-503)
- `platform_map()` response schema must include `scan_metadata` (TSG-504)
- Documentation must clearly state detection boundaries
- Future enhancement: runtime scanning as an opt-in Tier 3 behavior for projects needing 100% accuracy

## For Discussion

1. The detection heuristic for `@db.model` matches any `@anything.model` class decorator. In the Kailash ecosystem this is unique to DataFlow, but if a project uses a third-party library with a `.model` decorator pattern (e.g., some ORM frameworks), false positives would contaminate the model list. Should the scanner verify the import path resolves to `dataflow` before accepting a match?

2. If the `scan_info.limitations` field lists "Dynamic model registration not detected" and the user has only dynamic models, the tool returns an empty list with a limitation note. Would Claude Code understand this limitation and ask the user, or would it proceed assuming there are genuinely no models? Should the response include a `"confidence": "partial"` flag that triggers more cautious behavior in LLM consumers?

3. If external package scanning (R2-09) were implemented via `KAILASH_MCP_SCAN_PACKAGES` env var, what would be the security implications of scanning arbitrary installed packages? A malicious package could contain code that, while only parsed by `ast.parse` (not executed), could be crafted to confuse the scanner into reporting false models or agents.
