# kailash-pact

**PACT governance framework** — D/T/R accountability grammar, operating envelopes, knowledge clearance, and verification gradient for AI agent organizations.

Part of the [Kailash](https://github.com/terrene-foundation/kailash-py) enterprise AI platform.

## Quick Start

```python
from pact.governance import GovernanceEngine

engine = GovernanceEngine.from_yaml("my-org.yaml")
verdict = engine.verify_action("D1-R1-T1-R1", "write_report", {"cost": 50.0})

if verdict.allowed:
    print("Approved:", verdict.reason)
else:
    print("Blocked:", verdict.reason)
```

## Installation

```bash
pip install kailash-pact
```

With Kaizen agent integration:

```bash
pip install kailash-pact[kaizen]
```

## Features

- **D/T/R Grammar Engine** — Accountability grammar (Department/Team/Role) with positional addressing
- **Three-Layer Envelopes** — Role (standing) + Task (ephemeral) = Effective (computed intersection)
- **Knowledge Clearance** — Five-level classification independent of authority/seniority
- **5-Step Access Enforcement** — Clearance → Classification → Compartment → Containment → Deny
- **GovernanceEngine** — Single facade composing all primitives
- **PactGovernedAgent** — Wrap any Kaizen agent with governance enforcement
- **SQLite/PostgreSQL Stores** — Persistent governance state
- **REST API** — 9 governance endpoints with auth and rate limiting
- **CLI** — `kailash-pact validate org.yaml`

## MCP Governance — Tenant Isolation (Pre-Pledge v0)

`pact.mcp` adds deterministic governance to MCP (Model Context Protocol) tool
calls and resource reads, including first-class multi-tenant isolation
(issue #1843, shipped in 0.16.0). Because `kailash-pact` is still pre-1.0,
this section is an explicit pledge of what the tenant-isolation surface
enforces **today** versus what remains open — read it before relying on
`McpGovernanceConfig.tenant_grants` in a multi-tenant deployment.

- **Enforced today:** `McpGovernanceConfig.tenant_grants` (a
  `dict[str, McpTenantGrant]`) scopes both `tools/call` and `resources/read`
  to the caller's tenant through one shared, fail-closed restrictiveness
  function, evaluated before tool registration (so it applies even under
  `DefaultPolicy.ALLOW`). The effective tenant is resolved from the
  server-verified `tenant` field (populated server-side at the network
  boundary, #1878) or a trusted `McpCallerIdentity.tenant` (resolved by your
  transport/auth layer and passed to `check_tool_call`/`check_resource_read`);
  the self-asserted `metadata["tenant_id"]` channel is deprecated and no
  longer consulted for tenant resolution in any mode (#1919), defeating
  impersonation. `require_caller_identity` defaults to `True`: with no
  verified/trusted tenant the call fails closed.
- **Deferred:** `resources/read` has ONLY the tenant-isolation check today —
  no cost, argument, clearance, or rate-limit governance layer exists yet
  for that surface (that richer contract exists only for `tools/call` via
  `McpToolPolicy`). The server-verified `tenant` field (#1878) is populated
  server-side and deliberately excluded from the wire envelope
  (`to_dict`/`from_dict` never emit it — byte-neutral with the Rust SDK's
  frozen envelope); it is NOT a client-serialized field, and the self-asserted
  `metadata["tenant_id"]` channel is no longer consulted for tenant
  resolution (#1919).
- **Non-promises:** `tenant_grants` being empty is NOT "tenant isolation
  enabled with an empty allowlist" — it is isolation OFF entirely (every
  call auto-approved on that axis, byte-identical to pre-0.16.0 behavior).
  Passing `require_caller_identity=False` is NOT a recommended production
  setting — it exists only for the documented #1843 weaker-mode surface. As
  of #1919 it NO LONGER re-enables a trusted metadata fallback: a caller that
  relied on the self-asserted `metadata["tenant_id"]` now receives a
  `DeprecationWarning` and the decision fails closed.
- **Verify:** `pytest packages/kailash-pact/tests/regression/test_issue_1843_mcp_tenant_isolation.py -v`
  exercises the fail-closed defaults, the impersonation-defeat contract, and
  the `resources/read` isolation-only surface end-to-end.
- **Status:** v0 within a pre-1.0 package (`kailash-pact` 0.18.0) — the
  isolation contract above is stable for this release; the deferred items
  may change shape (not just grow) before a 1.0 cut.

## Documentation

- [Quickstart](docs/quickstart.md) — Zero to governance in 10 minutes
- [Architecture](docs/architecture.md) — How it all fits together
- [Vertical Guide](docs/vertical-guide.md) — Build your own governed platform
- [API Reference](docs/api.md) — REST endpoints
- [Cookbook](docs/cookbook.md) — Common patterns
- [YAML Schema](docs/yaml-schema.md) — Org definition format

## Cross-SDK Conformance (PACT N4/N5)

The PACT N6 cross-SDK conformance contract pins byte-for-byte canonical JSON
across language SDKs. The Python implementation lives in `pact.conformance`
and drives the same vector files the Rust SDK does.

### Run the runner programmatically

```python
from pact.conformance import ConformanceRunner, load_vectors_from_dir

vectors = load_vectors_from_dir(
    "/path/to/kailash-rs/crates/kailash-pact/tests/conformance/vectors"
)
report = ConformanceRunner().run(vectors)
if not report.all_passed:
    raise SystemExit(report.render_failure_report())
print(f"PACT conformance: {report.passed}/{report.total} passed")
```

### Run via pytest

The Tier 1 unit tests at
`tests/unit/conformance/test_runner.py::test_runner_passes_against_real_cross_sdk_vectors`
auto-discover the `kailash-rs` sibling checkout and exercise every vector.
The test SKIPS gracefully when the sibling repo is absent, so unit-only CI
hosts do not fail.

```bash
pytest packages/kailash-pact/tests/unit/conformance/ -v
```

### Vector schema

Each vector is a JSON document at `crates/kailash-pact/tests/conformance/vectors/`
with:

- `id`: unique identifier (sort key)
- `contract`: `"N4"` (TieredAuditEvent canonicalisation) or `"N5"` (Evidence canonicalisation)
- `input.verdict`: `{zone, reason, action, role_address, details}`
- `input.posture`: required for N4 (`PseudoAgent`, `Supervised`, `SharedPlanning`, `ContinuousInsight`, `Delegated`)
- `input.fixed_event_id` / `input.fixed_timestamp`: required for determinism
- `expected.canonical_json`: the byte-for-byte JSON the SDK MUST emit
- `expected.tier` / `durable` / `requires_signature` / `requires_replication`: optional N4 invariants

The runner compares actual vs expected via byte equality (NOT JSON-equal); a
single-byte drift surfaces as a `FAILED` outcome with both SHA-256
fingerprints populated for forensic correlation.

## License

Apache 2.0 — Terrene Foundation
