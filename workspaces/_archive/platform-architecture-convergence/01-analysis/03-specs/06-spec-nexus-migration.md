# SPEC-06: Nexus Auth/Audit Migration + PACTMiddleware

**Status**: DRAFT
**Implements**: Nexus audit recommendations (01-research/04-nexus-audit.md)
**Cross-SDK issues**: TBD
**Priority**: Phase 5 — independent from Kaizen work, can parallelize

## §1 Overview

Nexus currently implements its own auth/audit/rate-limiting/session/EATP-headers stack (~25KB JWT, custom RBAC, SSO for 4 providers, Memory+Redis rate limiting, custom audit logging, custom session trust). None of this consumes `kailash.trust`. This spec migrates Nexus to consume trust primitives and adds missing PACT integration.

**Key principle**: Nexus auth implementations may be BETTER than what exists in `kailash.trust` today (especially the 25KB JWT with SSO). The migration direction is:

- If `kailash.trust` already has the capability → Nexus consumes it
- If Nexus has a BETTER implementation → Extract it INTO `kailash.trust`, then Nexus consumes it
- If it's Nexus-specific (CSRF, security headers, Prometheus metrics) → Keep in Nexus

### Per-capability migration matrix

| Capability                             | Nexus file                             | kailash.trust has it?                 | Migration direction                                                 |
| -------------------------------------- | -------------------------------------- | ------------------------------------- | ------------------------------------------------------------------- |
| **JWT**                                | `nexus/auth/jwt.py` (25KB)             | Partial (`trust/interop/jwt.py`)      | Extract Nexus JWT → `kailash.trust.auth.jwt`, Nexus consumes        |
| **RBAC**                               | `nexus/auth/rbac.py`                   | No                                    | Extract → `kailash.trust.auth.rbac`, Nexus consumes                 |
| **API key**                            | `nexus/auth/api_key.py`                | Partial (MCP auth)                    | Extract → `kailash.trust.auth.api_key`                              |
| **SSO (Google, Azure, GitHub, Apple)** | `nexus/auth/sso/`                      | No                                    | Extract → `kailash.trust.auth.sso/`, Nexus consumes                 |
| **Rate limiting (Memory)**             | `nexus/auth/rate_limit/memory.py`      | No (BudgetTracker is different)       | Extract → `kailash.trust.rate_limit/`, Nexus consumes               |
| **Rate limiting (Redis)**              | `nexus/auth/rate_limit/redis.py`       | No                                    | Extract → `kailash.trust.rate_limit/redis.py`                       |
| **Audit logging**                      | `nexus/auth/audit/`                    | Partial (`trust/audit_store.py`)      | Nexus consumes `kailash.trust.AuditStore` + adds persistent backend |
| **Tenant resolver**                    | `nexus/auth/tenant/`                   | No                                    | Keep in Nexus (Nexus-specific)                                      |
| **EATP headers**                       | `nexus/trust/headers.py`               | Should be in trust                    | Extract → `kailash.trust.headers`                                   |
| **Trust middleware**                   | `nexus/trust/middleware.py`            | Should be in trust                    | Extract → `kailash.trust.middleware`                                |
| **Session trust**                      | `nexus/trust/session.py`               | Partial (`trust/trust/session.py`)    | Nexus consumes trust's session                                      |
| **MCP EATP handler**                   | `nexus/trust/mcp_handler.py`           | Nexus-specific                        | Keep in Nexus                                                       |
| **CSRF**                               | `nexus/middleware/csrf.py`             | No                                    | Keep in Nexus (web-specific)                                        |
| **Security headers**                   | `nexus/middleware/security_headers.py` | No                                    | Keep in Nexus (web-specific)                                        |
| **Prometheus metrics**                 | `nexus/middleware/metrics_mw.py`       | No                                    | Keep in Nexus (ecosystem-specific)                                  |
| **PACT governance**                    | **MISSING**                            | `kailash.trust.pact.GovernanceEngine` | **BUILD** `nexus/middleware/governance.py`                          |

## §2 PACTMiddleware (New)

```python
# packages/kailash-nexus/src/nexus/middleware/governance.py

from __future__ import annotations
from typing import Any, Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust import ConstraintEnvelope
from kailash.trust.posture import AgentPosture


class PACTMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces PACT governance at the request boundary.

    For every incoming request:
    1. Extract tenant ID from request (header, JWT claim, path parameter)
    2. Look up the tenant's operating envelope from GovernanceEngine
    3. Evaluate the request against the envelope
    4. Reject with 403 if BLOCKED, hold with 429 if HELD, log if FLAGGED

    This is the missing Nexus→PACT integration identified in the audit.

    Usage:
        from kailash.trust.pact.engine import GovernanceEngine

        governance = GovernanceEngine(org_definition=my_org)

        nexus = Nexus()
        nexus.add_middleware(PACTMiddleware, governance_engine=governance)
    """

    def __init__(
        self,
        app: Any,
        *,
        governance_engine: GovernanceEngine,
        tenant_header: str = "X-Tenant-ID",
        tenant_claim: str = "tenant_id",
        exempt_paths: set[str] = frozenset({"/health", "/metrics", "/docs"}),
    ):
        super().__init__(app)
        self._engine = governance_engine
        self._tenant_header = tenant_header
        self._tenant_claim = tenant_claim
        self._exempt_paths = exempt_paths

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        # Skip exempt paths
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # Extract tenant
        tenant_id = self._extract_tenant(request)
        if tenant_id is None:
            return await call_next(request)  # no tenant = no governance

        # Get envelope for this tenant's role
        envelope = self._engine.get_effective_envelope(tenant_id)
        if envelope is None:
            return await call_next(request)  # no envelope = unconstrained

        # Evaluate request against envelope
        verdict = self._evaluate(request, envelope)

        if verdict == "BLOCKED":
            return JSONResponse(
                status_code=403,
                content={"error": "governance_blocked", "message": "Request blocked by operating envelope"},
            )

        if verdict == "HELD":
            return JSONResponse(
                status_code=429,
                content={"error": "governance_held", "message": "Request held pending approval"},
            )

        # AUTO_APPROVED or FLAGGED: proceed
        response = await call_next(request)
        return response

    def _extract_tenant(self, request: Request) -> Optional[str]:
        # Try header first, then JWT claim
        tenant = request.headers.get(self._tenant_header)
        if tenant:
            return tenant
        # JWT extraction would go here (via auth middleware that ran earlier)
        return request.state.tenant_id if hasattr(request.state, 'tenant_id') else None

    def _evaluate(self, request: Request, envelope: ConstraintEnvelope) -> str:
        # Evaluate financial constraints (estimated cost of this request)
        # Evaluate operational constraints (allowed endpoints)
        # Evaluate temporal constraints (rate limiting via envelope)
        # Evaluate data access constraints (resource path matching)
        # Evaluate communication constraints (external host allowlist)
        # Return: AUTO_APPROVED | FLAGGED | HELD | BLOCKED
        return "AUTO_APPROVED"  # placeholder — full implementation per GovernanceEngine API
```

## §3 Migration Order

### Phase 5a: Extract auth primitives to kailash.trust

1. Create `src/kailash/trust/auth/` directory
2. Move/extract JWT module → `kailash.trust.auth.jwt`
3. Move/extract RBAC module → `kailash.trust.auth.rbac`
4. Move/extract API key module → `kailash.trust.auth.api_key`
5. Move/extract SSO providers → `kailash.trust.auth.sso/`
6. Move/extract rate limiting → `kailash.trust.rate_limit/`
7. Move/extract EATP headers → `kailash.trust.headers`
8. Move/extract trust middleware → `kailash.trust.middleware`
9. Add `SqliteAuditStore` to `kailash.trust.audit_store` (persistent backend, per trust audit)

### Phase 5b: Migrate Nexus to consume trust

10. Refactor `nexus/auth/jwt.py` → re-export from `kailash.trust.auth.jwt`
11. Refactor `nexus/auth/rbac.py` → re-export from `kailash.trust.auth.rbac`
12. Refactor `nexus/auth/rate_limit/` → re-export from `kailash.trust.rate_limit`
13. Refactor `nexus/auth/audit/` → use `kailash.trust.AuditStore` (with new SQLite backend)
14. Refactor `nexus/trust/headers.py` → import from `kailash.trust.headers`
15. Refactor `nexus/trust/session.py` → import from `kailash.trust.session`
16. Delete `nexus/trust/middleware.py` → replaced by `kailash.trust.middleware`
17. Add backward-compat shims at old Nexus import paths

### Phase 5c: Add PACT integration

18. Create `nexus/middleware/governance.py` (PACTMiddleware)
19. Wire PACTMiddleware into NexusEngine's enterprise middleware stack
20. Add integration tests for PACT + Nexus

## §4 Backward Compatibility

```python
# packages/kailash-nexus/src/nexus/auth/__init__.py (v2.x shim)
import warnings
warnings.warn(
    "nexus.auth submodules are deprecated since v2.next. "
    "Use `from kailash.trust.auth import ...` instead.",
    DeprecationWarning, stacklevel=2,
)
from kailash.trust.auth.jwt import JWTAuth, JWTConfig
from kailash.trust.auth.rbac import RBACManager, Permission
from kailash.trust.auth.api_key import APIKeyAuth
```

## §5 Test Plan

- All existing Nexus auth tests must pass against new import paths
- New integration test: PACTMiddleware + NexusEngine with tenant envelope enforcement
- New test: `SqliteAuditStore` persistence across restarts

## §6 Related Specs

- **SPEC-01**: kailash-mcp (Nexus MCP already consolidated)
- **SPEC-07**: ConstraintEnvelope (PACTMiddleware consumes canonical type)
- **SPEC-08**: Core SDK audit consolidation (trust.AuditStore is the canonical store)

## §7 Rust Parallel

Rust Nexus has the same duplication (per `02-rs-research/03-rs-dataflow-nexus-audit.md`). The same migration pattern applies: extract Nexus auth into a shared auth crate (or into eatp), then Nexus consumes it. PACT middleware at request boundary is also missing in Rust.

## §8 Security Considerations

Nexus is the multi-channel entry point (API + CLI + MCP). Any auth or audit vulnerability at this layer is directly internet-exposed. The migration from Nexus-native auth to `kailash.trust` is itself a security-critical operation — the transition window has its own threat surface beyond the normal migration risks.

### §8.1 Credential Isolation During Migration

**Threat**: Nexus currently holds per-tenant JWT secrets in its own auth module. `kailash.trust` has a single shared `AuthConfig`. A naive migration would copy Nexus's secrets into `kailash.trust`, but if the trust module's configuration is process-global and Nexus is multi-tenant, one tenant's JWT secret becomes readable by code running on behalf of another tenant. The result: an attacker with access to tenant A's context could forge JWTs for tenant B.

**Mitigations**:

1. `kailash.trust.auth` MUST support a `TenantContext` abstraction: secrets are stored per-tenant, not globally. The context is keyed by a tenant identifier derived from the request (not user-provided).
2. Migration order in §3 is amended: step 1 is "introduce `TenantContext` into `kailash.trust.auth`." No Nexus code moves until tenant isolation exists in trust.
3. Integration tests MUST verify that a request arriving on tenant A's channel cannot access tenant B's JWT secret even if the code path references the global trust module.
4. PACT envelope tightening (write-time) MUST include the tenant identifier; envelopes cannot be loosened to allow cross-tenant secret access.

### §8.2 Auth Middleware Ordering

**Threat**: Nexus currently runs auth middleware in a specific order: rate limiting → JWT validation → RBAC → session trust → audit. Moving components to `kailash.trust` risks reordering. If rate limiting moves behind JWT validation, a flood of invalid tokens exhausts the JWT verification budget before rate limiting kicks in (CPU DoS). If audit moves in front of JWT validation, unauthenticated requests flood the audit store (storage DoS).

**Mitigations**:

1. SPEC-06 §3 Migration Order MUST be atomic per-component — no partial states where half of auth is in Nexus and half is in trust.
2. An `AuthMiddlewareChain` object defined in `kailash.trust.auth.chain` enforces the canonical ordering: rate limit → JWT → RBAC → session → audit. The chain MUST raise `MiddlewareOrderError` on any attempt to deviate.
3. Regression tests verify chain ordering using a synthetic "order tracer" middleware that records call sequence.
4. Chain is frozen at module load — no runtime modification.

### §8.3 `PACTMiddleware._evaluate()` Stub Hides Real Decisions

**Threat** (related to R2-005): The SPEC-06 `PACTMiddleware._evaluate()` placeholder returns `AUTO_APPROVED` with a comment "full implementation per GovernanceEngine API." If the implementation keeps this stub in production code (even temporarily), every request bypasses governance evaluation but the middleware LOOKS like it enforces something. This is worse than no middleware — it creates false security confidence.

**Mitigations**:

1. `_evaluate()` MUST NOT return `AUTO_APPROVED` unconditionally in any production code path. The stub is permitted only in test fixtures marked `@pytest.mark.fixture_only`.
2. Production `PACTMiddleware` MUST delegate to `GovernanceEngine.evaluate()` with an explicit import and no fallback. If `kailash.trust.pact.GovernanceEngine` is unavailable at import time, the middleware raises `ImportError` rather than degrading to a no-op.
3. The constraint check order MUST be documented explicitly in §2 of this spec before implementation begins (R2-005 fix): financial → temporal → operational → data_access → communication. Each check returns a verdict and the first non-AUTO_APPROVED wins.
4. Integration tests use a mock `GovernanceEngine` that returns `BLOCKED` and verify the middleware actually blocks the request (not just logs it).

### §8.4 JWT Secret Rotation Across Trust and Nexus Boundaries

**Threat**: During the migration, JWT secrets exist in both Nexus auth and `kailash.trust.auth` for some window. If secrets are rotated (a routine security operation), one side may update and the other may not — leaving stale secrets that still validate tokens. A token issued under the old secret continues to work through the un-updated side.

**Mitigations**:

1. JWT secret rotation MUST use `kailash.trust.auth.SecretRotationHandle` — a single authoritative rotation primitive. Nexus does not rotate directly.
2. During migration, Nexus's auth module MUST proxy every secret read through `kailash.trust.auth.get_jwt_secret(tenant_id)`. Nexus does not cache secrets.
3. A `jti` (JWT ID) blocklist shared between Nexus and trust allows immediate revocation of specific tokens during rotation.
4. Observability: `kailash.trust.audit` emits `JWTSecretRotated` events with tenant_id, old key fingerprint, new key fingerprint, and time delta between the rotation call and the last successful verification under the old secret.

### §8.5 SSO Token Exchange During Extraction

**Threat**: Nexus's SSO integration (SAML / OAuth2) exchanges external tokens for internal JWTs. During the migration, this code path moves into `kailash.trust.auth`. If the extraction keeps the SSO callback URL registered at Nexus while the handler moves into trust, an attacker could intercept the redirect and claim the session.

**Mitigations**:

1. SSO callback URLs MUST be updated atomically with handler location — the DNS/reverse-proxy config change and the code move are one deployment, not two.
2. SSO token exchange MUST validate the `state` parameter against a per-session nonce stored in `kailash.trust.session.SessionStore`. Validation happens in trust, not at the Nexus boundary.
3. During the window, Nexus's old SSO handler MUST be a hard redirect to the trust handler (HTTP 308) — not a proxy. Proxies open a TLS-termination window.
4. Integration tests verify the full SSO flow: IdP → trust callback → session creation → authorized request. Red-team variant: tamper with the state parameter and verify rejection.
