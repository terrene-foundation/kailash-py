# Red Team Findings

## CRITICAL

### FINDING-01: ConstraintEnvelope `config=` Constructor Mismatch

`envelope_adapter.py` line 139 constructs `ConstraintEnvelope(config=config)`. NEITHER `kailash.trust.chain.ConstraintEnvelope` nor `kailash.trust.plane.models.ConstraintEnvelope` accepts a `config` parameter. The adapter was written against the standalone pact repo's OWN `ConstraintEnvelope` class, which is a different type entirely.

**Resolution**: The `GovernanceEnvelopeAdapter` must be rewritten to:

- Map `ConstraintEnvelopeConfig` fields to `kailash.trust.plane.models.ConstraintEnvelope` constructor args (FinancialConstraintConfig -> FinancialConstraints, etc.)
- OR define a PACT-specific `ConstraintEnvelope` in `pact.governance.envelope_adapter` that wraps `ConstraintEnvelopeConfig` with `evaluate_action()` capability

### FINDING-02: VerificationLevel Enum Value Mismatch

kailash.trust `VerificationLevel` has values: `QUICK`, `STANDARD`, `FULL` (verification thoroughness).
PACT uses `VerificationLevel` with values: `AUTO_APPROVED`, `HELD`, `BLOCKED` (action disposition).

These are COMPLETELY DIFFERENT CONCEPTS. Cannot be aliased.

**Resolution**: PACT's `VerificationLevel` must be defined in `pact.governance.config` as a separate enum. It represents action disposition, not verification depth. Consider renaming to `ActionDisposition` or `GovernanceDisposition` to avoid confusion.

## HIGH

### FINDING-03: ConfidentialityLevel Base Class Incompatibility

kailash.trust `ConfidentialityLevel(Enum)` — plain Enum, not str-backed.
PACT code does `ConfidentialityLevel("confidential")` to reconstruct from stored strings.

Values are lowercase strings in both ("public", "restricted", etc.) so `ConfidentialityLevel("confidential")` DOES work with plain Enum. However, `str(ConfidentialityLevel.PUBLIC)` returns `"ConfidentialityLevel.PUBLIC"`, not `"public"`. Any code using `str()` instead of `.value` will break.

**Resolution**: Verify all serialization paths use `.value`, not `str()`. Add round-trip tests.

### FINDING-04: GradientRuleConfig Missing from Extraction List

`GradientRuleConfig` is imported by test files and is a field type within `VerificationGradientConfig`. Must be extracted alongside it.

**Resolution**: Add to TODO-01 extraction list.

### FINDING-05: `pact.examples.university.*` Import Path Not In Wheel

14 test files import `from pact.examples.university.org import create_university_org`. The `examples/` directory is at `packages/kailash-pact/examples/`, OUTSIDE `src/pact/`. This means the import path `pact.examples.university` doesn't resolve.

**Resolution**: Move `examples/university/` to `src/pact/examples/university/` with proper `__init__.py` files so it becomes part of the `pact` package.

### FINDING-07: `pact.governance.api.events` Imports from `pact.use.api.events` at Runtime

The analysis incorrectly categorized ALL `pact.use.*` imports as "only in `pact/__init__.py`". The events module has a RUNTIME import from `pact.use.api.events`, making the entire `pact.governance.api` subpackage potentially broken.

**Resolution**: Define `EventType`, `PlatformEvent`, and `event_bus` locally in `pact.governance.api.events` or make the import conditional.

### FINDING-09: OrgDefinition Runtime Scope Underestimated

`OrgDefinition` is used at runtime in `yaml_loader.py`, `compilation.py`, and all test fixtures — not just TYPE_CHECKING. Its fields depend on `DepartmentConfig`, `TeamConfig`, and `RoleDefinition`, creating potential circular imports.

**Resolution**: Define `OrgDefinition` in `pact.governance.config` alongside `DepartmentConfig`/`TeamConfig` to avoid circular imports.

## MEDIUM

### FINDING-06: Test Count Discrepancy

Brief says 968, analysis says 824, actual `def test_` count is ~849. The brief's 968 may include parameterized test cases from the source repo.

**Resolution**: Run `pytest --collect-only` for ground truth count after integration.

### FINDING-08: 3 Test Files Import pact.use.\* (Not 2)

`test_envelope_unification.py` also imports from `pact.use.*`. Plan TODO-12 lists only 2 files.

**Resolution**: Update TODO-12 to handle 3 files.

### FINDING-10: Pydantic Validation Loss

Converting config types from Pydantic to dataclasses may break tests that use `model_dump()`, `model_validate()`, or rely on Pydantic type coercion.

**Resolution**: Grep the pact source repo for Pydantic-specific API calls on config types before converting. If extensive, keep Pydantic for config types too.

### FINDING-11: CI Workflow Structure

The unified CI runs root-level tests only, not sub-package tests. No matrix strategy for packages exists. TODO-13 needs a separate job, not just a matrix entry.

**Resolution**: Add a dedicated CI job for sub-package testing.

## LOW

### FINDING-12: pact Namespace Collision with pact-python

The `pact` import namespace conflicts with `pact-python` (contract testing library, 2.2M+ downloads on PyPI).

**Resolution**: Monitor. Consider `kailash_pact.governance` rename if collision becomes real. Add CI test with `pact-python` co-installed.
