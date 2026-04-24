# Zero-Tolerance Rules — Extended Evidence and Examples

Companion reference for `.claude/rules/zero-tolerance.md`. Full code examples + audit post-mortems.

## Rule 1a — Second Instance: `__all__` / `__getattr__` (PR #506, 2026-04-19)

```python
# DO — eager-import new `__all__` entries so CodeQL resolves them
# __init__.py
from .client import TypedServiceClient  # eager import
from .decoder import DecoderRegistry
__all__ = ["TypedServiceClient", "DecoderRegistry", ...]

# DO NOT — add to __all__ but resolve only via __getattr__
# __init__.py
__all__ = ["TypedServiceClient", "DecoderRegistry", ...]
def __getattr__(name):
    if name == "TypedServiceClient":
        from .client import TypedServiceClient
        return TypedServiceClient
    # CodeQL: "name in __all__ has no definition at module scope"
    # → rationalization-blocked: "the existing 8 entries do this too"
```

**Why:** PR #506 added 8 new `__all__` entries that CodeQL flagged because they were only resolvable via lazy `__getattr__`; existing grandfathered entries used the same pattern. The fix is to eager-import the NEW entries (closing the flag for this PR), not to argue "main does this too." The grandfathered entries remain a separate workstream and are NOT justification for adding more of the same.

## Rule 2 — Full BLOCKED Pattern Code Examples

### Fake Encryption

```python
# BLOCKED — "encrypted" store that writes plaintext
class EncryptedStore:
    def __init__(self, encryption_key: str):
        self._key = encryption_key
    def set(self, k, v):
        self._backend.set(k, v)  # no encryption applied
```

**Why:** Operators pass a real key and assume data is encrypted at rest. The audit trail shows "encrypted store used"; the disk shows plaintext.

### Fake Transaction

```python
# BLOCKED — misnamed context manager
@contextmanager
def transaction(self):
    yield  # no BEGIN, no COMMIT, no rollback on exception
```

**Why:** Callers write `with db.transaction(): ...` expecting atomicity; partial failure leaves half-committed state.

### Fake Health

```python
# BLOCKED — always-green health endpoint
@router.get("/health")
async def health():
    return {"status": "healthy"}  # no DB probe, no Redis ping, no nothing
```

**Why:** Load balancers and orchestrators use the health endpoint to decide routing and restart decisions. A fake-healthy endpoint masks real outages.

### Fake Classification / Redaction

```python
# BLOCKED — classify promises redaction but read path ignores it
@db.model
class User:
    @classify("email", PII, REDACT)
    email: str
# user = db.express.read("User", uid)
# user.email  ← still returns the raw PII
```

**Why:** Documented as a security control; ships as a no-op. The Phase 5.10 audit found this had been non-functional for an unknown period.

### Fake Tenant Isolation

```python
# BLOCKED — multi_tenant flag with no tenant dimension in key
@db.model(multi_tenant=True)
class Document: ...
# cache_key = f"dataflow:v1:Document:{id}"  ← tenant_id missing
```

**Why:** See `rules/tenant-isolation.md`. This is the Phase 5.7 orphan pattern surfaced at the cache key layer.

### Fake Integration Via Missing Handoff Field

```python
# BLOCKED — TrainingResult is frozen, has no `trainable` or `.model` field
@dataclass(frozen=True)
class TrainingResult:
    run_id: str
    metrics: dict
    duration_s: float
    # ... no `trainable`, no `model` → register cannot locate fitted model
    # ... so km.register(result, ...) raises ValueError at ONNX export time

# km.train returns TrainingResult(run_id="...", metrics={...}, duration_s=1.5)
# km.register(result, name="demo") → ValueError: could not locate trained model
# Every unit test of fit() passes ✓ (returns TrainingResult)
# Every unit test of register() passes ✓ (accepts TrainingResult with mocked .trainable)
# End-to-end Quick Start in the README is broken on every fresh install.
```

**Why:** A pipeline's canonical 3-line chain (`train → register → serve`) is the public API surface the README advertises. When the frozen-dataclass handoff between two primitives omits the field the consumer primitive needs, both primitives pass their own unit+integration tests (each constructs its own `TrainingResult` with exactly the fields IT needs) while the advertised pipeline breaks on every real install. The dataclass IS structurally a stub — `register` receives a "result" object the framework's own `train` produced, but the object cannot support `register`'s contract.

Fix: add the missing handoff field (`trainable: Trainable | None = None`), ensure every `fit()` return site populates it, AND add an end-to-end regression test (see `rules/testing.md` § End-to-End Pipeline Regression Tests).

Evidence: kailash-ml-audit 2026-04-23 W33b — `TrainingResult(frozen=True)` without `trainable` shipped in W31 + W33; `km.register` landed in W33c with no way to resolve `.model`; canonical Quick Start raised `ValueError` on every fresh install until W33b added `trainable=self` at every `Trainable.fit()` return site and landed `packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py`.

### Fake Metrics

```python
# BLOCKED — silent no-op metrics
try:
    from prometheus_client import Counter
except ImportError:
    Counter = lambda *a, **k: _NoOp()
# User thinks /fabric/metrics is reporting; it's empty
```

**Why:** Operators rely on dashboards. A silent no-op metrics layer removes the observability contract without any signal. The Phase 5.12 fix emits a loud startup WARN AND an explanatory body from the `/fabric/metrics` endpoint.

## Audit Origins

- DataFlow 2.0 Phase 5 wiring audit (2026-04) surfaced: fake encryption, fake transaction, fake health, fake classification, fake tenant isolation, fake metrics.
- kailash-ml-audit session 2026-04-23 W33b surfaced: fake integration via missing handoff field.
- `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12) — Rule 1a origin + Rule 3a typed-delegate guard origin.
- PR #506 (2026-04-19) — Rule 1a second instance (`__all__` + lazy `__getattr__`).
