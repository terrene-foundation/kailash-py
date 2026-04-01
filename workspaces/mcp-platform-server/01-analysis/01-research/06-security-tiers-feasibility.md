# Security Tiers Feasibility Analysis

## The 4-Tier Model

| Tier | Category      | Risk   | Default      | Gate               |
| ---- | ------------- | ------ | ------------ | ------------------ |
| 1    | Introspection | None   | Enabled      | None               |
| 2    | Scaffold      | Low    | Enabled      | None               |
| 3    | Validation    | Medium | Enabled      | Env var to disable |
| 4    | Execution     | High   | **Disabled** | Env var to enable  |

## Tier 1: Introspection (Read-Only)

**Tools**: `list_models`, `describe_model`, `query_schema`, `list_handlers`, `list_agents`, `platform_map`, `trust_status`, `org_tree`

**Feasibility**: Fully feasible. No execution, no side effects.

**Security concerns**:

- Schema information leakage: in a shared environment, model schemas could reveal business logic. Low risk for local dev (primary use case).
- No authorization needed for local Claude Code usage.

**Verdict**: Green. No issues.

## Tier 2: Scaffold (Code Generation)

**Tools**: `scaffold_model`, `scaffold_handler`, `scaffold_agent`, `generate_tests`

**Feasibility**: Fully feasible. Tools return code as strings; they do not write to disk.

**Security concerns**:

- Path traversal in suggested `file_path`: scaffold tools suggest where to write the file. Must validate paths don't escape `project_root`.
- Code injection: generated code could contain malicious imports. Mitigation: `ast.parse()` validation confirms syntactic validity, but does not guarantee safety.

**Implementation note**: Input validation for scaffold parameters:

- `name` must match `^[a-zA-Z_][a-zA-Z0-9_]*$` (valid Python identifier)
- `method` must be in `{"GET", "POST", "PUT", "PATCH", "DELETE"}`
- `path` must start with `/`

**Verdict**: Green. Standard input validation sufficient.

## Tier 3: Validation (Subprocess Isolation)

**Tools**: `validate_model`, `validate_handler`, `validate_workflow`

**Feasibility**: Feasible with subprocess isolation.

**How it works**: Validation tools import the project's code to analyze it. Importing Python modules triggers module-level side effects (database connections, file I/O, network requests).

**Mitigation strategy**:

1. Run validation in a subprocess (`subprocess.run()` or `ProcessPoolExecutor`)
2. 10-second timeout per call
3. Capture stdout/stderr; translate to structured result
4. Default: enabled (disable with `KAILASH_MCP_ENABLE_VALIDATION=false`)

**Security concerns**:

- Module-level side effects during import (mitigated by subprocess isolation)
- Subprocess inherits environment variables (including secrets). Consider environment scrubbing for sensitive vars.
- Validation subprocess has full filesystem access. Not a concern for local dev; matters for multi-tenant deployments.

**Verdict**: Yellow. Feasible for local dev. Multi-tenant requires additional sandboxing (not in scope).

## Tier 4: Execution (Trust Plane + PACT Integration)

**Tools**: `test_handler` (HTTP requests), `test_agent` (LLM calls)

**Feasibility**: Feasible but requires careful integration.

### Trust Plane Integration

If `kailash[trust]` is installed (it is -- trust is in the base package):

```python
from kailash.trust.plane.project import TrustProject

project = await TrustProject.load(trust_dir)
verdict = project.check("test_handler", {"handler": handler_name})
if verdict == "BLOCKED":
    return {"error": "Trust Plane blocked this action", "verdict": "BLOCKED"}
```

This works because:

- `TrustProject.load()` is already proven (TrustPlane MCP server uses it)
- The `check()` method evaluates against the constraint envelope
- The trust directory must exist in the project

**Gap**: The trust directory path discovery. The platform server knows `project_root` but needs to find `trust-plane/` within it. Convention: `project_root / "trust-plane"`.

### PACT Integration

If `kailash-pact` is installed:

```python
from kailash.trust.pact.engine import GovernanceEngine

engine = GovernanceEngine(...)
decision = engine.verify_action(action)
if decision == "BLOCKED":
    return {"error": "PACT governance blocked this action"}
```

**Gap**: PACT requires a compiled org tree. The platform server would need to:

1. Discover PACT configuration in `project_root`
2. Compile the org tree
3. Resolve the caller's address (who is the MCP client?)

**Major question**: Who is the caller in MCP context? Claude Code has no identity in PACT's D/T/R grammar. Options:

- Default to a "tool-user" role with restricted envelope
- Use a `KAILASH_MCP_PACT_ROLE` environment variable
- Skip PACT if no role can be resolved

### Cost Implications

`test_agent` invokes LLM calls. This costs money and could be accidentally triggered in bulk. Mitigations:

- Default disabled (`KAILASH_MCP_ENABLE_EXECUTION=true` required)
- Tool description explicitly states cost implication
- Trust Plane budget check (if configured) limits spend
- Response includes `tokens_used` for visibility

### Is the Env Var Approach Sufficient?

**For local dev**: Yes. Claude Code users set env vars in their config. The env var acts as a conscious opt-in.

**For production/shared environments**: No. Env vars are not a security boundary — any process on the same machine can read them. Production deployments would need:

- Authentication (JWT/mTLS) on the MCP transport
- Per-tool access control via PACT envelopes
- These are future A2A concerns, not initial scope

**Verdict**: Yellow-Green. Feasible for initial implementation. PACT caller identity is the main design question. Recommend deferring PACT integration for Tier 4 to a follow-up milestone after the A2A identity model is clarified.

## Summary

| Tier | Feasibility  | Blockers                     | Recommendation                                            |
| ---- | ------------ | ---------------------------- | --------------------------------------------------------- |
| 1    | Green        | None                         | Ship as designed                                          |
| 2    | Green        | None                         | Ship with input validation                                |
| 3    | Yellow       | Subprocess isolation needed  | Ship with subprocess + timeout                            |
| 4    | Yellow-Green | PACT caller identity unclear | Ship Trust Plane integration; defer PACT to A2A milestone |
