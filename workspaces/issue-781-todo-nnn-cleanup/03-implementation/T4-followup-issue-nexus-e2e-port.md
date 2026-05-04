# GH issue — nexus E2E test_ai_agent_discovery WebSocket port-mismatch (follow-up to T4)

**FILED 2026-05-04 as terrene-foundation/kailash-py#816** (per `rules/upstream-issue-hygiene.md` MUST Rule 1, with explicit user approval). Body promoted to file-ready state at `/tmp/issue-T4-nexus-e2e-port.md` before submission — workspace identifiers stripped, fixture line refs verified (lines 43-44, 51-52, 326), 8 sibling test sites enumerated.

This file retained as institutional history of the discovery context (T4 of issue #781 cleanup).

## Title

`fix(nexus): test_ai_agent_discovery_and_exploration WebSocket connect fails on production_nexus._mcp_port`

## Body

### Affected API

`packages/kailash-nexus/tests/e2e/test_ai_agent_workflows.py::TestAIAgentScenarios::test_ai_agent_discovery_and_exploration` (Tier 3 E2E test against the `production_nexus` fixture's MCP WebSocket transport).

### Symptoms

The test attempts a WebSocket connection at `ws://localhost:{production_nexus._mcp_port}` and fails — the test never converges past discovery (Step 1 `tools/list` request). Pre-dates the T4 cleanup; SHA-grounded to commit `b553104c` (2026-03-11) `refactor(monorepo): move published packages from apps/ to packages/`.

The fixture wires `mcp_port = find_free_port(api_port + 100)` at line 44 of the same file, but downstream calls in `production_nexus` may register the MCP transport against a different port (or never register the WebSocket transport when `enable_http_transport=False, enable_sse_transport=False` per lines 51–52).

### Reproduction

```bash
cd packages/kailash-nexus
uv run pytest tests/e2e/test_ai_agent_workflows.py::TestAIAgentScenarios::test_ai_agent_discovery_and_exploration -v
```

### Expected vs actual

- **Expected:** Test connects to the `production_nexus` MCP WebSocket transport, lists ≥3 tools (`document_processor`, `data_pipeline`, `api_integration`), reads the `workflow://document_processor` resource, asserts the workflow definition contains `nodes` + `schema`. Per `e2e-god-mode.md` Rule 4, "graceful failure" is BLOCKED — the test must converge.
- **Actual:** Connection / handshake fails or `tools/list` returns insufficient tools. Pre-dates issue #781 work; SHA `b553104c` is the most recent change to the surrounding test file structure.

### Severity

**MEDIUM** — single E2E test path; does NOT block other E2E tests. But it's a documented production scenario (multi-channel discovery via MCP WebSocket transport per `01-nexus-quickstart.md`), so silent failure here means the canonical AI-agent discovery path lacks E2E regression coverage.

### Acceptance criteria

- [ ] `production_nexus` fixture confirms which transport (HTTP / SSE / WebSocket / stdio) is bound to `_mcp_port` when `enable_http_transport=False, enable_sse_transport=False`. If WebSocket is the intended transport, fixture explicitly enables it; if not, test connects to the actually-bound transport.
- [ ] `test_ai_agent_discovery_and_exploration` exits 0 against the corrected fixture wiring.
- [ ] Test asserts the discovered tools list matches the `production_nexus` fixture's registered workflows (read fixture state, do not hardcode — per `e2e-god-mode.md` Rule 2).
- [ ] Tier-2 sibling test in `tests/integration/` covers the same MCP WebSocket discovery contract independently (so an E2E flake does not lose coverage).

### Discovery context (FOR HUMAN — strip before filing per upstream-issue-hygiene if filing publicly)

Surfaced during T4 of issue #781 TODO-NNN cleanup workstream when the touched `packages/kailash-nexus/src/nexus/auth/` files triggered E2E re-runs. Failure pre-dates the cleanup commits per `git log --oneline packages/kailash-nexus/tests/e2e/test_ai_agent_workflows.py | head -1` → `b553104c` 2026-03-11.
