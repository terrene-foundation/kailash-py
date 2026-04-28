# Milestone 3: Test Suite

Dependencies: Milestone 1 + 2 (types extracted, imports rewired)
Estimated: 1 autonomous session

---

## TODO-10: Update all 37 test file imports

**Priority**: HIGH (no tests run until this is done)
**Files**: All 37 files in `packages/kailash-pact/tests/unit/governance/`

### Mechanical find-replace
```python
# OLD
from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel, ...
# NEW
from pact.governance.config import ConfidentialityLevel, TrustPostureLevel, ...

# OLD
from pact.build.org.builder import OrgDefinition
# NEW
from pact.governance.config import OrgDefinition
```

### Verify
- Every test file compiles after import update
- No remaining `pact.build` imports in test directory

### Acceptance criteria
- `grep -r "pact.build" packages/kailash-pact/tests/` returns zero results

---

## TODO-11: Update trust imports in 3 test files

**Priority**: HIGH (FINDING-08)
**Files**: `test_envelope_adapter.py`, `test_envelope_unification.py`, `test_deprecation.py`

### Changes
```python
# OLD
from pact.trust.audit.anchor import AuditChain
from pact.trust.constraint.envelope import ConstraintEnvelope
from pact.trust.constraint.gradient import GradientEngine

# NEW
from pact.governance.audit import AuditChain
from pact.governance.gradient import GradientEngine, EvaluationResult
# ConstraintEnvelope: use kailash.trust.plane.models or governance wrapper per TODO-04
```

### Acceptance criteria
- `grep -r "pact.trust" packages/kailash-pact/tests/` returns zero results
- All 3 test files compile after update

---

## TODO-12: Handle 3 test files importing pact.use.*

**Priority**: MEDIUM (FINDING-08 — 3 files, not 2)
**Files**:
- `test_redteam_rt21.py` — imports `ExecutionRuntime`, `TaskStatus`
- `test_envelope_unification.py` — imports `ApprovalQueue`, `AgentRegistry`, `ExecutionRuntime`
- `test_deprecation.py` — imports trust types (handled in TODO-11)

### Strategy
For tests that depend on `pact.use.*` execution layer types:
1. Identify which specific test functions use execution types
2. Add `@pytest.mark.skip(reason="pact.use execution layer not yet migrated")` to those functions
3. Keep governance-only tests in the same files running
4. Track skipped test count for future migration

### Acceptance criteria
- No `pact.use` imports remain at module level (move to function level or skip)
- Skipped tests are documented with clear skip reason
- Non-skipped tests in same files still pass

---

## TODO-13: Add conftest.py with shared fixtures

**Priority**: MEDIUM (reduces duplication, improves maintainability)
**Files**: Create `packages/kailash-pact/tests/conftest.py`

### Shared fixtures to extract
1. `compiled_org` → pre-compiled university org (used in ~19 files)
2. `clearances` → standard clearance assignments (used in ~21 files)
3. `engine` → GovernanceEngine with all memory stores (used in ~25 files)
4. `bridges` / `ksps` → access policy fixtures (used in ~15 files)

### Steps
1. Create conftest.py importing from `pact.examples.university.*`
2. Define module-scoped fixtures for expensive objects (compiled_org)
3. Define function-scoped fixtures for mutable state (engine, stores)
4. Update test files to remove inline duplicates and use shared fixtures
5. Run full test suite to verify no regressions

### Acceptance criteria
- conftest.py provides at least `compiled_org`, `clearances`, `engine`
- No test behavior changes from fixture refactor

---

## TODO-14: Run full test suite and fix failures

**Priority**: CRITICAL (validation gate)
**Files**: All test files + any source files needing fixes

### Steps
1. `cd packages/kailash-pact && pip install -e ".[dev]" && pip install -e ../..`
2. `pytest tests/ -v --timeout=120 2>&1 | tee test-results.txt`
3. Categorize failures:
   - Import errors → fix remaining import issues
   - Type errors → fix type compatibility (FINDING-03: ConfidentialityLevel serialization)
   - Behavioral changes → investigate and fix
4. Add round-trip serialization tests for ConfidentialityLevel:
   ```python
   def test_confidentiality_level_roundtrip():
       for level in ConfidentialityLevel:
           assert ConfidentialityLevel(level.value) == level
           assert level.value == level.value  # not str(level)
   ```
5. Fix any `str(level)` → `level.value` issues in stores/backup
6. Re-run until all tests pass (excluding pact.use.* skips)

### Acceptance criteria
- All tests pass except explicitly skipped pact.use.* tests
- `pytest --tb=short` shows 0 failures
- Count of skipped tests documented
