# Milestone 2: Import Rewiring

Dependencies: Milestone 1 (types must exist before imports can point to them)
Estimated: Same session as M1

---

## TODO-07: Rewrite pact/__init__.py

**Priority**: HIGH (package can't be imported until this is fixed)
**Files**: `packages/kailash-pact/src/pact/__init__.py`

### Steps
1. Remove ALL `pact.build.*` imports (lines 21-28)
2. Remove ALL `pact.trust.*` imports (lines 34-41)
3. Remove ALL `pact.use.*` imports (lines 44-53)
4. Replace with:
   - `from pact.governance import *` (self-contained governance types)
   - Selected imports from `kailash.trust` (TrustPosture, ConfidentialityLevel, AuditAnchor, CapabilityAttestation)
   - Config types from `pact.governance.config` (TrustPostureLevel alias, VerificationLevel, ConstraintEnvelopeConfig)
5. Update `__all__` to match new exports
6. **DO NOT** import `kailash.trust.VerificationLevel` (different concept — FINDING-02)

### Acceptance criteria
- `import pact` succeeds without ImportError
- `pact.GovernanceEngine` is accessible
- `pact.TrustPosture` is accessible (from kailash.trust)
- `pact.VerificationLevel.AUTO_APPROVED` exists (PACT's, not kailash.trust's)

---

## TODO-08: Update 15 source file imports

**Priority**: HIGH (source files can't be imported until this is done)
**Files**: All 15 source files importing from `pact.build.config.schema`

### Mechanical find-replace
```python
# OLD
from pact.build.config.schema import ...
# NEW
from pact.governance.config import ...
```

Files (from exploration):
1. `access.py` — ConfidentialityLevel, TrustPostureLevel
2. `agent.py` — config types
3. `clearance.py` — ConfidentialityLevel, TrustPostureLevel
4. `compilation.py` — DepartmentConfig, TeamConfig (+ OrgDefinition TYPE_CHECKING)
5. `engine.py` — ConstraintEnvelopeConfig, TrustPostureLevel, VerificationLevel
6. `envelope_adapter.py` — ConstraintEnvelopeConfig (+ trust import update in TODO-04)
7. `envelopes.py` — CONFIDENTIALITY_ORDER, all 5 dimension configs, ConfidentialityLevel, TrustPostureLevel
8. `explain.py` — ConfidentialityLevel, TrustPostureLevel
9. `knowledge.py` — ConfidentialityLevel
10. `store.py` — (if importing config types)
11. `stores/backup.py` — config types
12. `stores/sqlite.py` — ConfidentialityLevel
13. `testing.py` — config types
14. `yaml_loader.py` — OrgDefinition, config types
15. `api/endpoints.py` — ConfidentialityLevel
16. `api/schemas.py` — config types

### Also update
- `pact.build.org.builder.OrgDefinition` → `pact.governance.config.OrgDefinition`
- Used in: `compilation.py` (TYPE_CHECKING), `yaml_loader.py` (runtime), examples

### Acceptance criteria
- `grep -r "pact.build" packages/kailash-pact/src/` returns zero results
- `grep -r "from eatp" packages/kailash-pact/src/` returns zero results
- All governance source files importable

---

## TODO-09: Update pyproject.toml

**Priority**: HIGH (package can't install with broken deps)
**Files**: `packages/kailash-pact/pyproject.toml`

### Changes
```toml
# OLD
dependencies = [
    "kailash>=1.0.0,<2.0.0",
    "eatp>=0.1.0,<1.0.0",
    "pydantic>=2.6",
]

# NEW
dependencies = [
    "kailash>=2.0.0,<3.0.0",
    "pydantic>=2.6",
]
```

Also:
- Remove monorepo override for eatp (lines 67-70)
- Update kaizen optional dep: `kailash-kaizen>=2.0.0`
- Verify hatch wheel config includes `src/pact/examples/` (after TODO-02 move)

### Acceptance criteria
- `pip install -e packages/kailash-pact` succeeds with kailash 2.0.0
- No reference to `eatp` package remains
