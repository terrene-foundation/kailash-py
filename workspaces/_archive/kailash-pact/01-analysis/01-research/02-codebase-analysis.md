# Codebase Analysis

## Package Structure

```
packages/kailash-pact/
  pyproject.toml              # hatchling, v0.2.0
  README.md
  src/pact/
    __init__.py               # Top-level re-exports (BROKEN — imports missing modules)
    governance/
      __init__.py             # 60+ exports (all self-contained, works)
      addressing.py           # D/T/R grammar engine
      access.py               # 5-step access enforcement
      agent.py                # PactGovernedAgent
      agent_mapping.py        # agent_id <-> D/T/R mapping
      audit.py                # PACT audit actions
      clearance.py            # 5-level knowledge clearance
      cli.py                  # kailash-pact CLI
      compilation.py          # OrgDefinition -> CompiledOrg
      context.py              # GovernanceContext (frozen snapshot)
      decorators.py           # @governed_tool
      engine.py               # GovernanceEngine (THE API) ~35K lines
      envelope_adapter.py     # Governance -> trust-layer bridge
      envelopes.py            # 3-layer envelope model ~33K lines
      explain.py              # Human-readable explanations
      knowledge.py            # KnowledgeItem
      middleware.py            # FastAPI middleware
      store.py                # Store protocols + memory impls
      testing.py              # MockGovernedAgent
      verdict.py              # GovernanceVerdict
      yaml_loader.py          # YAML org loader
      stores/
        __init__.py
        sqlite.py             # SQLite store backends
        backup.py             # Backup/restore
      api/
        __init__.py
        auth.py               # Bearer token auth
        endpoints.py          # 9 REST endpoints
        events.py             # WebSocket events
        router.py             # FastAPI router factory
        schemas.py            # Pydantic request/response
  tests/unit/governance/      # 37 test files, 824 tests
  examples/university/        # Reference implementation
  docs/                       # 6 documentation files
```

## Metrics

- **Source lines**: ~75K (engine.py ~35K, envelopes.py ~33K, rest ~7K)
- **Test lines**: ~18K (37 files, 824 test functions, 82 inline fixtures)
- **Test categories**: Unit (core), property-based (Hypothesis), thread safety, adversarial, security regression
- **Dependencies**: kailash>=1.0.0, eatp>=0.1.0, pydantic>=2.6

## Architecture

### Core Governance Pipeline

```
OrgDefinition  ->  compile_org()  ->  CompiledOrg
                                         |
                                    GovernanceEngine
                                    /     |     \
                           Clearance  Envelopes  Access
                               |         |         |
                         RoleClearance  3-layer   5-step
                         (5 levels)    model     algorithm
                               |         |         |
                               \    GovernanceVerdict   /
                                    (ALLOW/BLOCK/HOLD)
```

### Key Design Patterns

1. **Fail-closed**: All error paths return BLOCKED, never silently permit
2. **Thread-safe**: GovernanceEngine.\_lock on all public methods
3. **Monotonic tightening**: Child envelopes can only be MORE restrictive
4. **NaN-safe**: math.isfinite() on all numeric constraint fields
5. **Frozen returns**: All returned objects are frozen dataclasses

### Layered Envelope Model

```
RoleEnvelope (standing, attached to D/T/R position)
  ∩
TaskEnvelope (ephemeral, scoped to task)
  =
EffectiveEnvelope (computed intersection)
  →
GovernanceVerdict (ALLOWED/BLOCKED/HELD/FLAGGED)
```

## Current Dependencies

```toml
dependencies = [
    "kailash>=1.0.0,<2.0.0",   # BROKEN: needs >=2.0.0
    "eatp>=0.1.0,<1.0.0",      # REMOVED: merged into kailash.trust
    "pydantic>=2.6",             # KEEP: API schemas need it
]
```

## Import Dependency Graph

```
pact.__init__  ──→  pact.build.*     (MISSING: 6 imports)
                ──→  pact.trust.*     (MISSING: 7 imports)
                ──→  pact.use.*      (MISSING: 13 imports)

pact.governance.* ──→  pact.build.config.schema  (MISSING: used in 15 source + 37 test files)
                   ──→  pact.governance.*          (WORKS: self-contained)

pact.governance.envelope_adapter ──→  pact.trust.constraint.envelope  (MISSING: ConstraintEnvelope)
                                 ──→  pact.build.config.schema        (MISSING: ConstraintEnvelopeConfig)
```

## Critical Finding: Two-Tier Import Problem

**Tier 1 (Self-contained, WORKS)**:
`pact.governance.__init__` imports only from `pact.governance.*` — all defined locally. The 60+ public governance types are self-contained.

**Tier 2 (Broken, FAILS)**:
`pact.__init__` imports from `pact.build.*`, `pact.trust.*`, `pact.use.*` — none of these modules exist. This means `import pact` fails, but `from pact.governance import GovernanceEngine` works.

**Tier 3 (Conditionally broken)**:
15 source files and ALL 37 test files import from `pact.build.config.schema` — specifically the constraint config types (ConstraintEnvelopeConfig, ConfidentialityLevel, TrustPostureLevel, etc.). Until these types are defined somewhere importable, governance source and tests also fail.

## Convention Compliance

| Convention                             | Status  | Details                                                                 |
| -------------------------------------- | ------- | ----------------------------------------------------------------------- |
| Apache-2.0 license                     | PASS    | All files have correct header                                           |
| `from __future__ import annotations`   | PASS    | All modules                                                             |
| `@dataclass` not Pydantic              | MIXED   | Governance types are dataclasses; API schemas are Pydantic (acceptable) |
| `to_dict()`/`from_dict()`              | PASS    | All governance dataclasses                                              |
| Explicit `__all__`                     | PASS    | All modules                                                             |
| `str`-backed Enum                      | PASS    | All enums (VettingStatus, NodeType, etc.)                               |
| Error hierarchy from TrustError        | PARTIAL | GovernanceBlockedError doesn't inherit TrustError                       |
| `logger = logging.getLogger(__name__)` | PASS    | All modules                                                             |
| Bounded collections                    | PASS    | MAX_STORE_SIZE = 100_000 with eviction                                  |
| NaN/Inf validation                     | PASS    | All numeric constraints validated                                       |

## Security Posture

From pact repo: 40 adversarial tests, 32 NaN/Inf tests, 20 security tests, 17 thread safety tests. All passing in source repo.

Key security patterns:

- `math.isfinite()` on all constraint numerics
- Fail-closed default (DENY, not ALLOW)
- Thread-safe via `threading.Lock`
- Input validation on all public API entry points
- `hmac.compare_digest()` for hash comparisons
- SQL parameterized queries in SQLite stores
