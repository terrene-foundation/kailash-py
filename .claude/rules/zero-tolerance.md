# Zero-Tolerance Rules

## Scope

ALL sessions, ALL agents, ALL code, ALL phases. ABSOLUTE and NON-NEGOTIABLE.

## Rule 1: Pre-Existing Failures, Warnings, and Notices MUST Be Resolved Immediately

If you found it, you own it. Fix it in THIS run — do not report, log, or defer.

**Applies to** — "found it" includes, with equal weight:

- Test failures, build errors, type errors
- Compiler warnings, linter warnings, deprecation notices
- WARN/ERROR entries in the workspace's logs since the previous gate
- Runtime warnings emitted during the session (`DeprecationWarning`, `ResourceWarning`, `RuntimeWarning`)
- Peer-dependency warnings, missing-module warnings, version-resolution warnings

A warning is not "less broken" than an error. It is an error that the framework chose to keep running through. Both are owed.

**Process:**

1. Diagnose root cause
2. Implement the fix
3. Write a regression test
4. Verify with `pytest` (or the project's test command)
5. Include in current or dedicated commit

**BLOCKED responses:**

- "Pre-existing issue, not introduced in this session"
- "Outside the scope of this change"
- "Known issue for future resolution"
- "Reporting this for future attention"
- "Warning, non-fatal — proceeding"
- "Deprecation warning, will address later"
- "Notice only, not blocking"
- ANY acknowledgement, logging, or documentation without an actual fix

**Why:** Deferring broken code creates a ratchet where every session inherits more failures, and the codebase degrades faster than any single session can fix. Warnings are the leading indicator: today's `DeprecationWarning` is next quarter's "it stopped working when we upgraded".

**Mechanism:** The log-triage protocol in `rules/observability.md` MUST Rule 5 provides the concrete commands for scanning test runner output, build tool output, and `*.log` files. If `observability.md` is not loaded (e.g., editing a config file), the agent MUST still scan the most recent test runner and build tool output for WARN+ entries before reporting any gate as complete.

**Exceptions:**

- User explicitly says "skip this issue."
- Upstream third-party deprecation that cannot be resolved by updating or configuring the dependency in this session. Required disposition: pinned version with documented reason OR upstream issue link OR todo with explicit owner. Silent dismissal is still BLOCKED.

### Rule 1a: Scanner-Surface Symmetry

Findings reported by a security scanner on a PR scan MUST be treated identically to findings reported on a main scan. The argument "this also exists on main, therefore not introduced here" is BLOCKED.

```python
# DO — fix the finding in this PR regardless of main's state
# CodeQL alert py/clear-text-logging-sensitive-data on log_redis_url() -> fix it here.
logger.info("redis.connect", url=mask_url(redis_url))

# DO NOT — rationalize based on main's scanner output
# "Same alert on main, out of scope for this PR"
logger.info("redis.connect", url=redis_url)  # still leaks, still my problem
```

**BLOCKED responses:**

- "Pre-existing on main, out of scope"
- "CodeQL only flags it on PR diffs"
- "Will be addressed when main re-scans"
- "Same alert ID exists upstream"
- "The main branch baseline suppresses it"

**Why:** "Same on main" is the institutional ratchet that defers fixes forever. Rule 1 already covers this in spirit; an explicit scanner-surface clause closes the rationalization gap.

**Second instance — CodeQL `py/modification-of-default-value` via lazy `__getattr__` in `__all__`:**

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

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12); extended 2026-04-19 with the `__all__` / `__getattr__` variant surfaced by PR #506.

## Rule 2: No Stubs, Placeholders, or Deferred Implementation

Production code MUST NOT contain:

- `TODO`, `FIXME`, `HACK`, `STUB`, `XXX` markers
- `raise NotImplementedError`
- `pass # placeholder`, empty function bodies
- `return None # not implemented`

**No simulated/fake data:**

- `simulated_data`, `fake_response`, `dummy_value`
- Hardcoded mock responses pretending to be real API calls
- `return {"status": "ok"}` as placeholder for real logic

**Frontend mock data is a stub:**

- `MOCK_*`, `FAKE_*`, `DUMMY_*`, `SAMPLE_*` constants
- `generate*()` / `mock*()` functions producing synthetic data
- `Math.random()` used for display data

**Why:** Frontend mock data is invisible to Python detection but has the same effect — users see fake data presented as real.

**Extended examples (DataFlow 2.0 Phase 5 audit):** these patterns passed prior audits but were caught by the Phase 5 wiring sweep. They are equally BLOCKED.

- **Fake encryption** — a class that takes an `encryption_key` parameter, stores it, and does nothing with it:

  ```python
  # BLOCKED — "encrypted" store that writes plaintext
  class EncryptedStore:
      def __init__(self, encryption_key: str):
          self._key = encryption_key
      def set(self, k, v):
          self._backend.set(k, v)  # no encryption applied
  ```

  **Why:** Operators pass a real key and assume data is encrypted at rest. The audit trail shows "encrypted store used"; the disk shows plaintext.

- **Fake transaction** — a context manager that looks like a transaction but commits after every statement:

  ```python
  # BLOCKED — misnamed context manager
  @contextmanager
  def transaction(self):
      yield  # no BEGIN, no COMMIT, no rollback on exception
  ```

  **Why:** Callers write `with db.transaction(): ...` expecting atomicity; partial failure leaves half-committed state.

- **Fake health** — a health endpoint that returns 200 without checking anything:

  ```python
  # BLOCKED — always-green health endpoint
  @router.get("/health")
  async def health():
      return {"status": "healthy"}  # no DB probe, no Redis ping, no nothing
  ```

  **Why:** Load balancers and orchestrators use the health endpoint to decide routing and restart decisions. A fake-healthy endpoint masks real outages.

- **Fake classification / redaction** — a `@classify("email", REDACT)` decorator that stores the classification but never enforces it on read:

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

- **Fake tenant isolation** — a `multi_tenant=True` flag that silently uses a shared cache key:

  ```python
  # BLOCKED — multi_tenant flag with no tenant dimension in key
  @db.model(multi_tenant=True)
  class Document: ...
  # cache_key = f"dataflow:v1:Document:{id}"  ← tenant_id missing
  ```

  **Why:** See `rules/tenant-isolation.md`. This is the Phase 5.7 orphan pattern surfaced at the cache key layer.

- **Fake integration via missing handoff field** — a frozen dataclass on a pipeline's critical path that omits the field the NEXT primitive needs to consume it:

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

  **Why:** A pipeline's canonical 3-line chain (`train → register → serve`) is the public API surface the README advertises. When the frozen-dataclass handoff between two primitives omits the field the consumer primitive needs, both primitives pass their own unit+integration tests (each constructs its own `TrainingResult` with exactly the fields IT needs) while the advertised pipeline breaks on every real install. The dataclass IS structurally a stub — `register` receives a "result" object the framework's own `train` produced, but the object cannot support `register`'s contract. The fix is to add the missing handoff field (`trainable: Trainable | None = None`), ensure every `fit()` return site populates it, AND add an end-to-end regression test (see `rules/testing.md` § End-to-End Pipeline Regression Tests). Evidence: kailash-ml-audit 2026-04-23 W33b — `TrainingResult(frozen=True)` without `trainable` shipped in W31 + W33; `km.register` landed in W33c with no way to resolve `.model`; canonical Quick Start raised `ValueError` on every fresh install until W33b added `trainable=self` at every `Trainable.fit()` return site and landed `packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py`.

- **Fake metrics** — a metrics class where every counter is a no-op because `prometheus_client` isn't installed but there's no warning:
  ```python
  # BLOCKED — silent no-op metrics
  try:
      from prometheus_client import Counter
  except ImportError:
      Counter = lambda *a, **k: _NoOp()
  # User thinks /fabric/metrics is reporting; it's empty
  ```
  **Why:** Operators rely on dashboards. A silent no-op metrics layer removes the observability contract without any signal. The Phase 5.12 fix emits a loud startup WARN AND an explanatory body from the `/fabric/metrics` endpoint.

## Rule 3: No Silent Fallbacks or Error Hiding

- `except: pass` (bare except with pass) — BLOCKED
- `catch(e) {}` (empty catch) — BLOCKED
- `except Exception: return None` without logging — BLOCKED

**Why:** Silent error swallowing hides bugs until they cascade into data corruption or production outages with no stack trace to diagnose.

**Acceptable:** `except: pass` in hooks/cleanup where failure is expected.

### Rule 3a: Typed Delegate Guards For None Backing Objects

Any delegate method that forwards to a lazily-assigned backing object MUST guard with a typed error before access. Allowing `AttributeError` to propagate from `None.method()` is BLOCKED.

```python
# DO — typed guard with actionable message
class JWTMiddleware:
    def _require_validator(self) -> JWTValidator:
        if self._validator is None:
            raise RuntimeError(
                "JWTMiddleware._validator is None — construct via __init__ or "
                "assign mw._validator = JWTValidator(mw.config) in test setup"
            )
        return self._validator

    def create_access_token(self, *args, **kwargs):
        return self._require_validator().create_access_token(*args, **kwargs)

# DO NOT — raw delegation, opaque AttributeError
class JWTMiddleware:
    def create_access_token(self, *args, **kwargs):
        return self._validator.create_access_token(*args, **kwargs)
        # AttributeError: 'NoneType' object has no attribute 'create_access_token'
```

**Why:** Opaque `AttributeError` blocks N tests at once with no actionable message; a typed guard turns the failure into a one-line fix instruction.

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12)

## Rule 4: No Workarounds for Core SDK Issues

This is a BUILD repo. You have the source. Fix bugs directly.

**Why:** Workarounds create a parallel implementation that diverges from the SDK, doubling maintenance cost and masking the root bug from being fixed.

**BLOCKED:** Naive re-implementations, post-processing, downgrading.

## Rule 5: Version Consistency on Release

ALL version locations updated atomically:

1. `pyproject.toml` → `version = "X.Y.Z"`
2. `src/{package}/__init__.py` → `__version__ = "X.Y.Z"`

**Why:** Split version states cause `pip install kailash==X.Y.Z` to install a package whose `__version__` reports a different number, breaking version-gated logic.

## Rule 6: Implement Fully

- ALL methods, not just the happy path
- If an endpoint exists, it returns real data
- If a service is referenced, it is functional
- Never leave "will implement later" comments
- If you cannot implement: ask the user what it should do, then do it. If user says "remove it," delete the function.

**Test files excluded:** `test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, `__tests__/`

**Why:** Half-implemented features present working UI with broken backend, causing users to trust outputs that are silently incomplete or wrong.

**Iterative TODOs:** Permitted when actively tracked.
