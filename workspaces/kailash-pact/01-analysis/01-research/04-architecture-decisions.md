# Architecture Decisions

## ADR-001: Config Types as Dataclasses in pact.governance.config

### Context

kailash-pact uses config types (ConstraintEnvelopeConfig, FinancialConstraintConfig, etc.) that currently live in the standalone pact repo as Pydantic models. These types are used in 15 source files and all 37 test files.

### Decision

Convert config types from Pydantic to `@dataclass` with `to_dict()`/`from_dict()` and place them in `pact.governance.config`.

### Rationale

1. **Kailash SDK convention**: All data types use `@dataclass`, not Pydantic (see rules/eatp.md)
2. **Dependency reduction**: Pydantic is only needed for API schemas (`pact.governance.api.schemas`), not internal config
3. **Consistency**: `kailash.trust` types are all dataclasses; pact governance types should match
4. **Simplicity**: Config types are simple data containers — Pydantic validation is overkill

### Consequences

- Must add `math.isfinite()` validation in `__post_init__` (Pydantic validators did this)
- Must implement `to_dict()`/`from_dict()` on each config type
- Pydantic stays as a dependency for API schemas only

## ADR-002: TrustPostureLevel Alias Strategy

### Context

PACT uses `TrustPostureLevel` throughout (15+ source files, 37 test files). kailash.trust uses `TrustPosture`. Same enum values, different name.

### Decision

Define `TrustPostureLevel = TrustPosture` alias in `pact.governance.config` for backward compatibility. Source files use the alias; tests can be gradually migrated.

### Rationale

1. **Minimal disruption**: One line vs 50+ file changes
2. **Backward compat**: Existing code using `TrustPostureLevel.DELEGATED` continues to work
3. **Forward path**: New code should use `TrustPosture` directly

### Consequences

- Two names for the same type (acceptable during transition)
- Deprecation warning can be added later

## ADR-003: Defer pact.use.\* Execution Types

### Context

The top-level `pact/__init__.py` imports 16 types from `pact.use.*` (execution runtime, sessions, agents, approval). These modules don't exist in the monorepo — they're part of the standalone pact platform.

### Decision

Remove all `pact.use.*` imports from `pact/__init__.py`. The execution layer is not yet migrated.

### Rationale

1. **Governance is self-contained**: `pact.governance` works without execution types
2. **No source code depends on them**: Only `pact/__init__.py` re-exports them
3. **2 test files affected**: `test_redteam_rt21.py` and `test_deprecation.py` — can be handled individually
4. **Clean boundary**: Governance governs; execution executes. They compose, not couple.

### Consequences

- `import pact` will no longer export execution types
- Users must import from `pact.governance` directly (which already works)
- When execution layer is migrated, types will be added back to `pact/__init__.py`

## ADR-004: AuditChain Defined in kailash-pact

### Context

PACT uses `AuditChain` (a linked chain of `AuditAnchor` records). kailash.trust has `AuditAnchor` (individual records) and `LinkedHashChain` (generic chain), but no `AuditChain` that composes them for governance.

### Decision

Define `AuditChain` in `pact.governance.audit` that wraps `kailash.trust.AuditAnchor` records.

### Rationale

1. **PACT-specific concept**: The chain semantics (append, integrity verification) are governance concerns
2. **kailash.trust provides primitives**: `AuditAnchor` and `LinkedHashChain` are the building blocks
3. **Clean composition**: PACT builds on kailash.trust, doesn't duplicate it

## ADR-005: Namespace Stays as pact.governance

### Context

The brief discusses namespace options. The package installs as `kailash-pact` but the import path is `pact.governance`.

### Decision

Keep `pact.governance` as the import path (confirmed by decisions.yml — medium confidence).

### Rationale

1. **Existing code compatibility**: All source and test files use `pact.governance`
2. **PyPI name collision avoided**: Package is `kailash-pact`, not `pact`
3. **Namespace packages**: Python namespace packages allow `pact.governance` to coexist with other `pact.*` packages

### Risk

Medium — if another popular package claims the `pact` namespace on PyPI, there could be conflicts. Mitigated by the fact that `pact-python` (the existing PyPI package) uses `pact` namespace for contract testing, not governance.

## ADR-006: Keep Pydantic for API Schemas Only

### Context

`pact.governance.api.schemas` uses Pydantic for request/response validation. The Pydantic dependency is declared in pyproject.toml.

### Decision

Keep `pydantic>=2.6` as a dependency, but only for API schemas. All governance config types are dataclasses.

### Rationale

1. **FastAPI integration**: API schemas must be Pydantic for FastAPI request parsing
2. **Validation at boundaries**: Pydantic validation is valuable for HTTP API input
3. **Internal types**: Governance config types don't need Pydantic — they're validated in `__post_init__`
