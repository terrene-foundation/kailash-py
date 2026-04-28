# Milestone 5: Convention Compliance

Dependencies: Milestone 1 (config types must exist first)
Can run in parallel with Milestone 3

---

## TODO-18: Define PactError base class

**Priority**: HIGH (COC finding — error hierarchy non-compliant)
**Files**: Create or update error definitions across governance source files

### Problem
EATP rules require all errors to inherit from `TrustError` with `.details: Dict[str, Any]`.
PACT errors inherit from bare `Exception` — non-compliant.

### Implementation
Define `PactError` in `pact.governance.exceptions` (or add to existing module):
```python
class PactError(Exception):
    """Base class for all PACT governance errors."""
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}
```

Update existing errors:
- `GovernanceBlockedError(PactError)` — with details (role, action, reason)
- `GovernanceHeldError(PactError)` — with details (role, action, hold_reason)
- `CompilationError(PactError)` — with details (node, error)
- `ConfigurationError(PactError)` — with details (field, value)
- `EnvelopeAdapterError(PactError)` — with details (role, envelope_type)
- `MonotonicTighteningError(PactError, ValueError)` — with details (parent, child, field)

### Decision
PactError is PARALLEL to TrustError, not inheriting from it. PACT is a peer to EATP, not a subpackage. But the `.details` pattern is shared.

### Acceptance criteria
- All governance errors inherit from `PactError`
- All errors include `.details: Dict[str, Any]`
- `isinstance(e, PactError)` catches any governance error
- No bare `Exception` subclasses remain

---

## TODO-19: Add ConfidentialityLevel round-trip tests

**Priority**: HIGH (FINDING-03 — serialization compatibility)
**Files**: Add to test suite (new file or extend existing)

### Tests
```python
def test_confidentiality_level_from_string():
    """Verify construction from stored string values works."""
    for level in ConfidentialityLevel:
        assert ConfidentialityLevel(level.value) == level

def test_confidentiality_level_serialization():
    """Verify .value gives the expected string, not str()."""
    assert ConfidentialityLevel.PUBLIC.value == "public"
    assert ConfidentialityLevel.TOP_SECRET.value == "top_secret"

def test_confidentiality_level_ordering():
    """Verify ordering matches CONFIDENTIALITY_ORDER."""
    from pact.governance.config import CONFIDENTIALITY_ORDER
    levels = sorted(ConfidentialityLevel, key=lambda l: CONFIDENTIALITY_ORDER[l])
    assert levels == [
        ConfidentialityLevel.PUBLIC,
        ConfidentialityLevel.RESTRICTED,
        ConfidentialityLevel.CONFIDENTIAL,
        ConfidentialityLevel.SECRET,
        ConfidentialityLevel.TOP_SECRET,
    ]

def test_sqlite_store_roundtrip():
    """Verify ConfidentialityLevel survives SQLite store/load cycle."""
    # Store a clearance with CONFIDENTIAL, load it back, verify level matches
```

### Also verify
- All `stores/sqlite.py` serialization uses `.value`, not `str()`
- All `stores/backup.py` serialization uses `.value`
- API endpoint construction uses `.value`

### Acceptance criteria
- All round-trip tests pass
- No `str(ConfidentialityLevel.X)` patterns in production code (only `.value`)
