# Nexus × kailash-ml Integration — Tenant/Actor Propagation + Dashboard Auth

Version: 1.0.0 (draft)
Package: `kailash-nexus`
Target release: **kailash-nexus 2.2.0** (shipping in the kailash-ml 1.0.0 wave)
Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/nexus-ml-integration-draft.md`. Promotes to `specs/nexus-ml-integration.md` after round-3 convergence.
Supersedes: none — this is net-new Nexus surface that kailash-ml 1.0.0 consumes.
Parent domain: Kailash Nexus (multi-channel platform: API + CLI + MCP).
Sibling specs: `specs/nexus-auth.md` (JWT middleware), `specs/nexus-core.md` (core), `specs/nexus-channels.md` (channels), `specs/nexus-services.md` (services).

Origin: round-1 theme T3 (tenant isolation absent from 13/13 ML engines). Every kailash-ml engine mandates `tenant_id` + `actor_id` on every mutation; when the engine runs inside a Nexus-served request, the ambient tenant/actor MUST reach the engine without the engine caller having to extract JWT claims manually. Also: `ml-dashboard-draft.md` §5 mandates `MLDashboard(auth="nexus")` — Nexus MUST expose the validator surface the dashboard needs.

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Four capabilities Nexus 2.2.0 ships to support kailash-ml 1.0.0:

1. **Tenant-id contextvar** — `kailash_nexus.context._current_tenant_id: ContextVar[Optional[str]]` set by the JWT middleware from a documented JWT claim; read by kailash-ml engines via `kailash_nexus.context.get_current_tenant_id() -> Optional[str]`.
2. **Actor-id contextvar** — `kailash_nexus.context._current_actor_id: ContextVar[Optional[str]]` set from the JWT `sub` claim; read via `kailash_nexus.context.get_current_actor_id() -> Optional[str]`.
3. **Dashboard auth adapter** — `MLDashboard(auth="nexus")` accepts a Nexus-issued JWT and validates it via Nexus's public-key registry; the dashboard HTTP/SSE/WebSocket surface reuses Nexus auth without importing Nexus modules into kailash-ml's core.
4. **Inference-endpoint tenant propagation** — when kailash-ml's `InferenceServer` runs behind Nexus, Nexus forwards ambient tenant+actor context into the predictor's request-scoped execution.

### 1.2 Out of Scope (Owned By Sibling Specs)

- JWT middleware internals → `specs/nexus-auth.md` §9.1.
- RBAC → `specs/nexus-auth.md` §9.2 (`rbac_manager` usage stays unchanged).
- Channel registration → `specs/nexus-channels.md`.
- Service registry → `specs/nexus-services.md`.
- Dashboard HTTP/SSE implementation details → `ml-dashboard-draft.md`.
- Inference server algorithm → `ml-serving-draft.md`.

### 1.3 Non-Goals

- **No breaking changes** to `nexus-auth.md` §9.1 JWT middleware signature.
- **No new JWT claim requirements** — `tenant_id` claim support is OPTIONAL at the JWT level; if the claim is absent the contextvar is set to `None` and kailash-ml engines handle the multi-tenant-strict-mode error per `rules/tenant-isolation.md` §2.
- **No Nexus dependency inside kailash-ml's core** — kailash-ml reads contextvars by name from `kailash_nexus.context` WHEN Nexus is installed, else falls back to its own `kailash_ml.tracking.context` contextvars (same names, same types). This preserves kailash-ml as a standalone package.

---

## 2. Tenant-ID ContextVar

### 2.1 Definition

```python
# packages/kailash-nexus/src/kailash_nexus/context.py
from contextvars import ContextVar
from typing import Optional

_current_tenant_id: ContextVar[Optional[str]] = ContextVar(
    "kailash_nexus.current_tenant_id",
    default=None,
)


def get_current_tenant_id() -> Optional[str]:
    """Return the ambient tenant_id set by the JWT middleware, or None."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: Optional[str]) -> object:
    """Set the ambient tenant_id. Returns the token for `reset()` use.
    PUBLIC for test code; production callers use the middleware-managed form."""
    return _current_tenant_id.set(tenant_id)
```

### 2.2 Middleware extraction

`JWTMiddleware` (per `specs/nexus-auth.md` §9.1) MUST set the contextvar on every successful token validation:

```python
# nexus.auth.jwt.JWTMiddleware.dispatch (conceptual)
async def dispatch(self, request, call_next):
    # ... existing token extraction + validation ...
    payload = self._verify_token(token)
    user = self._create_user_from_payload(payload)

    tenant_id = payload.get("tenant_id")  # OPTIONAL claim
    actor_id = payload.get("sub")         # MANDATORY per JWT spec

    tenant_token = _current_tenant_id.set(tenant_id)
    actor_token = _current_actor_id.set(actor_id)
    try:
        response = await call_next(request)
    finally:
        _current_actor_id.reset(actor_token)
        _current_tenant_id.reset(tenant_token)
    return response
```

**Invariants:**

- Reset in `finally` — if `call_next` raises, the contextvar MUST be restored. Otherwise the next request on the same worker sees the prior tenant.
- `tenant_id` claim is OPTIONAL; `sub` claim is MANDATORY (per RFC 7519 §4.1.2). If `sub` is missing, the middleware returns 401 `invalid_token` BEFORE setting contextvars.
- No default-to-"default-tenant" fallback — per `rules/tenant-isolation.md` §2 ("multi-tenant strict mode").

### 2.3 Read API for kailash-ml

```python
# kailash-ml engines call this helper (via the compat layer):
from kailash_ml._compat.nexus_context import get_current_tenant_id
tid = get_current_tenant_id()  # None if Nexus not installed OR no ambient request
```

The `kailash_ml._compat.nexus_context` module:

```python
# packages/kailash-ml/src/kailash_ml/_compat/nexus_context.py
try:
    from kailash_nexus.context import get_current_tenant_id, get_current_actor_id
except ImportError:
    # Nexus not installed; fall back to ml-local contextvars (same names)
    from kailash_ml.tracking.context import (
        get_current_tenant_id,
        get_current_actor_id,
    )
```

**Why:** Keeps kailash-ml installable without Nexus. When Nexus IS present, the middleware-managed contextvars win; when absent, the engine-local contextvars (set by `km.track(tenant_id=...)`) are the source.

---

## 3. Actor-ID ContextVar

Symmetric to §2, keyed on JWT `sub` claim. Same extraction, same reset-in-`finally`, same read helper.

```python
# packages/kailash-nexus/src/kailash_nexus/context.py
_current_actor_id: ContextVar[Optional[str]] = ContextVar(
    "kailash_nexus.current_actor_id",
    default=None,
)


def get_current_actor_id() -> Optional[str]:
    return _current_actor_id.get()


def set_current_actor_id(actor_id: Optional[str]) -> object:
    return _current_actor_id.set(actor_id)
```

---

## 4. Dashboard Auth Adapter

### 4.1 MLDashboard contract

Per `ml-dashboard-draft.md` §5, `MLDashboard(auth="nexus")` is supported. The implementation:

```python
# packages/kailash-ml/src/kailash_ml/dashboard/auth.py (ml-side)
from kailash_ml.dashboard.auth_base import DashboardAuth

class NexusDashboardAuth(DashboardAuth):
    def __init__(self, *, issuer: str, audience: str, jwks_url: Optional[str] = None):
        from kailash_nexus.auth.jwt import JWTValidator, JWTConfig
        self._validator = JWTValidator(JWTConfig(
            issuer=issuer,
            audience=audience,
            jwks_url=jwks_url,
        ))

    async def authenticate(self, token: str) -> DashboardPrincipal:
        payload = self._validator.verify_token(token)  # raises on invalid
        return DashboardPrincipal(
            actor_id=payload["sub"],
            tenant_id=payload.get("tenant_id"),
            scopes=payload.get("scopes", []),
        )
```

### 4.2 Nexus public-key registry

Nexus 2.2.0 ships the dashboard auth adapter at `nexus.ml.MLDashboard` (`packages/kailash-nexus/src/nexus/ml/__init__.py`). The adapter exposes `MLDashboard.from_nexus(nexus)` — a classmethod that walks the live Nexus instance's ASGI middleware stack, locates the registered `JWTMiddleware`, extracts its `JWTConfig` (issuer / audience / jwks_url / public_key / secret / algorithm), and constructs the dashboard auth adapter from those fields:

```python
# packages/kailash-nexus/src/nexus/ml/__init__.py
class MLDashboard:
    @classmethod
    def from_nexus(cls, nexus: Any) -> "MLDashboard":
        """Construct an MLDashboard auth adapter from a live Nexus instance.

        Reuses the Nexus instance's JWT config (issuer / audience / JWKS URL /
        public key) so the dashboard does NOT store key material independently.
        Raises RuntimeError when the Nexus instance has no fastapi_app or no
        JWTMiddleware is registered.
        """
        cfg = cls._extract_jwt_config(nexus)
        return cls(**cfg)
```

**Invariant:** `MLDashboard(auth="nexus")` resolves to `MLDashboard.from_nexus(nexus)` on the ml side; the dashboard does NOT store key material independently — it always reads the live JWTMiddleware config off the Nexus instance.

**Canonical JWTValidator construction:** `JWTValidator` is constructed directly from a `JWTConfig` populated via environment variables per `rules/env-models.md` (`os.environ["NEXUS_JWT_SECRET"]`, etc.) — there is NO `JWTValidator.from_nexus_config()` classmethod. The Nexus-side reuse path runs through `MLDashboard.from_nexus(nexus)` which walks the middleware stack to extract the already-configured JWTConfig:

```python
# Direct construction (canonical):
import os
from kailash.trust.auth.jwt import JWTValidator, JWTConfig

validator = JWTValidator(JWTConfig(
    issuer=os.environ["NEXUS_JWT_ISSUER"],
    audience=os.environ["NEXUS_JWT_AUDIENCE"],
    jwks_url=os.environ.get("NEXUS_JWKS_URL"),
    secret=os.environ.get("NEXUS_JWT_SECRET"),
))

# Nexus-reuse path (canonical for dashboard):
from nexus.ml import MLDashboard
dash_auth = MLDashboard.from_nexus(nexus)  # reads JWTMiddleware config off live instance
```

### 4.3 Dashboard principal dataclass

```python
@dataclass(frozen=True)
class DashboardPrincipal:
    actor_id: str
    tenant_id: Optional[str]
    scopes: tuple[str, ...]
```

Frozen (per PACT MUST Rule 1 discipline) + the scopes tuple is immutable.

---

## 5. Inference-Endpoint Tenant Propagation

### 5.1 Contract

When a kailash-ml `ServeHandle` (returned by `km.serve(...)` or constructed directly from an `InferenceServer`) is mounted behind Nexus:

```python
from nexus import Nexus
from nexus.ml import mount_ml_endpoints
import kailash_ml as km

nexus = Nexus(...)
serve_handle = await km.serve(model_name="churn_v3")
mount_ml_endpoints(nexus, serve_handle, prefix="/ml")
```

Every request hitting `POST /ml/predict` (or the optional MCP / WebSocket variants — see §5.2) MUST:

1. Pass through `JWTMiddleware` (sets `_current_tenant_id`, `_current_actor_id`).
2. `mount_ml_endpoints` wraps the registered `ServeHandle.predict` so the handler reads `get_current_tenant_id()` / `get_current_actor_id()` at the request boundary and forwards them as keyword arguments into `predict(inputs, *, tenant_id=..., actor_id=...)` when the predictor's signature accepts them. Predictors that do NOT accept the kwargs still see the propagated tenant via `get_current_tenant_id()` directly through the kailash-ml compat layer (`§2.3`).
3. The predictor appends the tenant/actor to the inference audit row.

### 5.2 `mount_ml_endpoints` API (canonical)

```python
# packages/kailash-nexus/src/nexus/ml/__init__.py
def mount_ml_endpoints(
    nexus: Any,
    serve_handle: Any,
    *,
    prefix: str = "/ml",
) -> None:
    """Mount REST + MCP + WebSocket routes for a kailash-ml ``ServeHandle``.

    Routes registered (relative to ``prefix``, default ``/ml``):
        - ``POST {prefix}/predict``       — REST prediction endpoint
        - ``GET  {prefix}/describe``      — model metadata (signature, version)
        - ``GET  {prefix}/healthz``       — liveness probe (no auth)
        - ``POST {prefix}/mcp/predict``   — MCP-compatible prediction endpoint
        - WebSocket ``{prefix}/ws``       — streaming predictions (when the
          underlying Nexus exposes ``register_websocket``)
    """
```

**Canonical contract** (verified at `packages/kailash-nexus/src/nexus/ml/__init__.py:222`):

- `serve_handle` MUST expose a `predict(inputs, *, tenant_id=None, actor_id=None) -> dict` callable. Predictors whose signatures lack the kwargs are still supported — `mount_ml_endpoints` introspects `inspect.signature(predict)` and only forwards kwargs the callable accepts.
- `serve_handle` MAY expose `describe() -> dict` for model metadata; absent, `GET {prefix}/describe` returns `{"prefix": prefix}`.
- The `[ml]` extra is required (`pip install kailash-nexus[ml]`); `mount_ml_endpoints` raises `ImportError` at call time when `kailash_ml` is not installed.
- WebSocket registration is best-effort: when the Nexus instance exposes `register_websocket`, a class-based `MessageHandler` is registered at `{prefix}/ws` per `skills/03-nexus/nexus-multi-channel.md`. Errors during streaming send a generic `{"error": "prediction failed"}` body without leaking exception details (per `rules/security.md` § Output Encoding).

The mount function is a thin wrapper — kailash-ml does NOT take a hard dependency on Nexus. The Nexus-side import of `kailash_ml` is deferred to call time inside `_require_ml_extra(...)` per `rules/dependencies.md` § "Exception: Optional Extras with Loud Failure".

### 5.3 Auto-audit

Every forwarded call MUST:

- Emit a `km.track()` metric `inference.requests_total{tenant_id=..., actor_id=...}` (bounded cardinality per `rules/tenant-isolation.md` §4 — the label set uses `top-N-or-_other` bucketing).
- Append an audit row to the inference audit table with `tenant_id`, `actor_id`, `model_name`, `model_version`, `request_fingerprint` (`sha256:<8hex>` of the serialized input per `rules/event-payload-classification.md` §2), `status_code`, `latency_ms`.

---

## 6. Error Taxonomy

All errors inherit from `kailash_nexus.exceptions.NexusError`:

```python
class NexusError(Exception):
    """Base for every Nexus exception."""

class NexusAuthError(NexusError):
    """Base for auth-related errors. Existing."""

class NexusContextError(NexusError):
    """New. Raised when a caller tries to reset a contextvar with a token
    that doesn't belong to them, or when contextvar state is corrupt."""

class NexusMLMountError(NexusError):
    """New. Raised when ``nexus.ml.mount_ml_endpoints`` cannot register
    routes (missing ``[ml]`` extra, ``serve_handle`` lacks ``predict``,
    or the underlying Nexus HTTP transport is uninitialised)."""
```

Missing `sub` claim → 401 `invalid_token` (existing behavior in `specs/nexus-auth.md` §9.1).

---

## 7. Test Contract

### 7.1 Tier 1 (unit)

- `test_get_current_tenant_id_default_none.py` — no ambient request → `None`.
- `test_set_tenant_id_reset_on_raise.py` — `set → raise inside call_next → contextvar reset`.
- `test_actor_id_from_jwt_sub.py` — mock JWT payload → `get_current_actor_id()` returns `sub`.
- `test_ml_compat_falls_back_when_nexus_missing.py` — simulate Nexus absent → compat import uses `kailash_ml.tracking.context`.

### 7.2 Tier 2 (integration wiring, per `rules/facade-manager-detection.md` §2)

File naming:

- `tests/integration/test_jwt_middleware_tenant_propagation_wiring.py` — real FastAPI app + real JWTMiddleware + ML engine reads `get_current_tenant_id()` → matches JWT `tenant_id` claim.
- `tests/integration/test_dashboard_nexus_auth_wiring.py` — real Nexus instance issues JWT → `MLDashboard(auth="nexus")` validates it → principal carries `actor_id` + `tenant_id`.
- `tests/integration/test_nexus_ml_endpoints_wiring.py` — Nexus instance + `mount_ml_endpoints` + Protocol-satisfying `ServeHandle` (per `rules/testing.md` § Tier 2 "Protocol-Satisfying Deterministic Adapters") + JWT-authenticated request → assertions: (a) `POST {prefix}/predict` returns 200; (b) the predictor saw the propagated `tenant_id` + `actor_id`; (c) `GET {prefix}/healthz` is reachable without auth; (d) `POST {prefix}/mcp/predict` unwraps the MCP tool envelope; (e) two sequential requests with different JWTs do NOT bleed tenant context.
- `tests/integration/test_mount_ml_endpoints.py` — Canonical-entry regression locking the shipped public-API shape: (1) `mount_ml_endpoints` signature is exactly `(nexus, serve_handle, *, prefix="/ml") -> None` (structural invariant test per `rules/cross-sdk-inspection.md` §3a); (2) the absent legacy names `Nexus.register_service` and `InferenceServer.as_nexus_service` are NOT present on the Nexus or kailash-ml public surfaces — if a future refactor reintroduces them, the test fails loudly and forces re-audit per `rules/orphan-detection.md` §3.

Each test asserts state persistence per `rules/testing.md` § "State Persistence Verification" — every write is read back.

### 7.3 Regression tests

- `tests/regression/test_contextvar_leak_across_requests.py` — two sequential requests on the same worker, each with different JWTs → the second request MUST NOT see the first's tenant_id.

---

## 8. Cross-SDK Parity Requirements

Nexus exists in kailash-rs at `crates/kailash-nexus/`. Rust's `tokio::task_local!` serves the same role as Python's `ContextVar`. The contract:

- Same claim names (`tenant_id`, `sub`).
- Same audit row shape on inference requests.
- Same `sha256:<8hex>` fingerprint for request payloads.

Cross-SDK follow-up is deferred until kailash-rs scopes a Rust-side Nexus ML inference surface. The parity contract above (JWT claims + audit row shape + fingerprint format) is the baseline. No tracking issue required until Rust-side scoping begins.

---

## 9. Industry Comparison

| Capability                                  | kailash-nexus 2.2.0 | FastAPI + python-jose | Kong + OPA | AWS API Gateway + Lambda Authorizer |
| ------------------------------------------- | ------------------- | --------------------- | ---------- | ----------------------------------- |
| JWT claim → contextvar                      | Y (built-in)        | Manual                | Manual     | Manual (event context)              |
| Tenant_id propagation to downstream engines | Y (built-in)        | Manual                | Manual     | Manual                              |
| Dashboard auth reuses server's key registry | Y                   | Manual                | N          | N                                   |
| Inference-endpoint tenant/actor auto-audit  | Y                   | Manual                | N          | Manual                              |
| Reset-in-`finally` for contextvars          | Y (enforced)        | Opt-in                | N/A        | N/A                                 |

**Position:** Nexus is the only multi-channel platform that auto-propagates JWT tenant/actor claims through a contextvar surface that downstream engines (kailash-ml, kailash-dataflow, kailash-kaizen) read without additional wiring. This closes the round-1 T3 gap structurally — every ML engine gets tenant context for free when served via Nexus.

---

## 10. Migration Path (kailash-nexus 2.1.x → 2.2.0)

2.1.x users get the contextvar surface as ADDITIONS. No existing middleware signature changes:

- `JWTMiddleware.__init__` — unchanged.
- `JWTValidator` — unchanged; constructed directly via `JWTValidator(JWTConfig(...))`. Dashboard reuse runs through `nexus.ml.MLDashboard.from_nexus(nexus)` which extracts the already-configured JWTConfig from the live JWTMiddleware on the Nexus instance.
- `nexus.ml` — new module: `MLDashboard` auth adapter + `mount_ml_endpoints` helper.
- `Nexus` — UNCHANGED. The ML serving surface mounts via the standalone helper `nexus.ml.mount_ml_endpoints(nexus, serve_handle)` rather than a method on the `Nexus` class itself. No `register_service()` overload and no `NexusServiceAdapter` class are introduced; the prior draft's mention of those names is RETRACTED in favor of the canonical `mount_ml_endpoints` entry per §5.2.

Users relying on `specs/nexus-auth.md` §9.1 behavior are unaffected. Optional migration: switch from manual `request.state.user.tenant_id` extraction to `get_current_tenant_id()` (simpler, same value, but NOT required).

**No deprecations.** No shims.

---

## 11. Release Coordination Notes

Part of the kailash-ml 1.0.0 wave release (see `pact-ml-integration-draft.md` §10 for the full wave list).

**Release order position:** after kailash 2.9.0 (which ships the expanded `src/kailash/diagnostics/protocols.py` that the Dashboard auth adapter depends on for `DashboardAuth` Protocol — see `kailash-core-ml-integration-draft.md` §2). Parallel with kailash-pact 0.10.0, kailash-kaizen 2.12.0, kailash-dataflow 2.1.0.

**Parallel-worktree ownership** (`rules/agents.md`): nexus-specialist agent owns `packages/kailash-nexus/pyproject.toml`, `packages/kailash-nexus/src/kailash_nexus/__init__.py::__version__`, and `packages/kailash-nexus/CHANGELOG.md`. Every other agent's prompt MUST exclude these files.

---

## 12. Cross-References

- kailash-ml specs consuming this surface:
  - `ml-tracking-draft.md` §10 — `get_current_run()` contextvar (ml-side mirror).
  - `ml-dashboard-draft.md` §5 — `MLDashboard(auth="nexus")`.
  - `ml-serving.md` — `InferenceServer` runtime that produces the `ServeHandle` instance fed to `mount_ml_endpoints` (the bridge module is owned by `nexus-ml-integration.md` §5; ml-serving owns only the runtime).
  - `ml-engines-v2-draft.md` §3 — every engine reads `get_current_tenant_id()` via the compat layer.
- Nexus companion specs:
  - `specs/nexus-auth.md` §9.1 — JWTMiddleware (unchanged).
  - `specs/nexus-core.md` — Nexus config + service registry.
- Rule references:
  - `rules/tenant-isolation.md` §1, §2 — multi-tenant strict mode, no silent fallback.
  - `rules/event-payload-classification.md` §2 — request fingerprint format.
  - `rules/facade-manager-detection.md` §2 — Tier 2 wiring tests.
  - `rules/terrene-naming.md` § "Canonical Terminology" — CARE Trust Plane / Execution Plane labeling preserved.
