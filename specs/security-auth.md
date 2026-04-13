# Kailash Security -- Authentication, Authorization, Sessions

Parent domain: Kailash Security. This sub-spec covers the architecture overview, authentication (JWT subsystems, API keys, SSO, MFA), authorization (RBAC, ABAC, hierarchical permissions, unified access control), and session management. See `security-data.md` for secrets management, credentials, encryption, the security framework, security nodes, trust-plane security, and DataFlow access controls. See `security-threats.md` for audit logging, the exception hierarchy, threat model, and configuration defaults.

---

## 1. Architecture Overview

Kailash security is layered across multiple subsystems, each with a distinct responsibility boundary.

```
                          +--------------------------+
                          |   Nexus (HTTP Gateway)   |
                          |  - CORS, rate limiting   |
                          |  - JWT middleware         |
                          |  - API key auth           |
                          +-----------+--------------+
                                      |
            +-------------------------+-------------------------+
            |                         |                         |
+-----------v---------+  +-----------v---------+  +------------v----------+
| Trust Plane Auth    |  | Access Control      |  | Security Framework    |
| - JWTValidator      |  | - RBAC (roles)      |  | - Path validation     |
| - RBACManager       |  | - ABAC (attributes) |  | - Input sanitization  |
| - SessionStore      |  | - Hybrid evaluator  |  | - Command injection   |
| - SSO providers     |  | - Matrix export     |  | - Execution sandboxing|
+---------------------+  | - Conflict detection|  +-----------------------+
                          +---------------------+
            |                         |                         |
+-----------v---------+  +-----------v---------+  +------------v----------+
| Secrets Management  |  | Credential Handling |  | Encryption            |
| - Env provider      |  | - URL decode helper |  | - AES-256-GCM (TrustPlane)|
| - Vault provider    |  | - Null-byte reject  |  | - Fernet (EATP keys) |
| - AWS provider      |  | - Pre-encoding      |  | - HKDF-SHA256 KDF    |
+---------------------+  +---------------------+  +-----------------------+
            |                         |                         |
+-----------v---------+  +-----------v---------+  +------------v----------+
| Security Nodes      |  | Auth Nodes          |  | Audit Logging         |
| - CredentialManager |  | - MFA               |  | - SecurityEvent       |
| - RotatingCredential|  | - SSO               |  | - SecurityAuditLogger |
| - ThreatDetection   |  | - Session mgmt      |  | - AuditLogNode        |
| - BehaviorAnalysis  |  | - Risk assessment   |  +-----------------------+
| - ABACEvaluator     |  | - Directory integ.  |
+---------------------+  | - Enterprise auth   |
                          +---------------------+
```

### Ownership Boundaries

| Concern                                        | Owner                         | Location                                              |
| ---------------------------------------------- | ----------------------------- | ----------------------------------------------------- |
| Authentication (login, JWT, sessions, cookies) | **Nexus** + **Trust Auth**    | `kailash.trust.auth.*`, `kailash.middleware.auth.*`   |
| Authorization (RBAC, ABAC, permissions)        | **PACT** + **Access Control** | `kailash.access_control.*`, `kailash.trust.auth.rbac` |
| Credential decode/encode                       | **Shared utils**              | `kailash.utils.url_credentials`                       |
| Secrets at rest                                | **Runtime**                   | `kailash.runtime.secret_provider`                     |
| Encryption (data at rest)                      | **TrustPlane**                | `kailash.trust.plane.encryption.*`                    |
| Input validation / sandboxing                  | **Core SDK**                  | `kailash.security`                                    |
| Security workflow nodes                        | **Nodes**                     | `kailash.nodes.security.*`, `kailash.nodes.auth.*`    |
| Trust-plane security (EATP)                    | **Trust**                     | `kailash.trust.security`                              |

---

## 2. Authentication

### 2.1 JWT (JSON Web Tokens)

The SDK contains two JWT subsystems serving different layers of the architecture.

#### 2.1.1 Trust-Plane JWTValidator (`kailash.trust.auth.jwt`)

Framework-agnostic JWT processor extracted from Nexus (SPEC-06). This is the canonical JWT implementation for production use.

**Supported algorithms:**

| Family             | Algorithms          | Key type      |
| ------------------ | ------------------- | ------------- |
| HMAC (symmetric)   | HS256, HS384, HS512 | Shared secret |
| RSA (asymmetric)   | RS256, RS384, RS512 | RSA key pair  |
| ECDSA (asymmetric) | ES256, ES384, ES512 | EC key pair   |

**Configuration (`JWTConfig`):**

| Field                   | Type                              | Default                              | Purpose                                         |
| ----------------------- | --------------------------------- | ------------------------------------ | ----------------------------------------------- |
| `secret`                | `Optional[str]`                   | `None`                               | Shared secret for HS\* algorithms               |
| `algorithm`             | `str`                             | `"HS256"`                            | Signing/verification algorithm                  |
| `public_key`            | `Optional[str]`                   | `None`                               | PEM-encoded public key for RS*/ES*              |
| `private_key`           | `Optional[str]`                   | `None`                               | PEM-encoded private key for signing             |
| `issuer`                | `Optional[str]`                   | `None`                               | Expected `iss` claim                            |
| `audience`              | `Optional[Union[str, List[str]]]` | `None`                               | Expected `aud` claim                            |
| `token_header`          | `str`                             | `"Authorization"`                    | HTTP header for Bearer token                    |
| `token_cookie`          | `Optional[str]`                   | `None`                               | Cookie name for token                           |
| `token_query_param`     | `Optional[str]`                   | `None`                               | Query param for token                           |
| `exempt_paths`          | `List[str]`                       | `/health`, `/metrics`, `/docs`, etc. | Paths that skip auth                            |
| `jwks_url`              | `Optional[str]`                   | `None`                               | JWKS endpoint for SSO providers                 |
| `jwks_cache_ttl`        | `int`                             | `3600`                               | JWKS cache TTL in seconds                       |
| `verify_exp`            | `bool`                            | `True`                               | Verify expiration claim                         |
| `leeway`                | `int`                             | `0`                                  | Clock skew tolerance in seconds                 |
| `api_key_header`        | `str`                             | `"X-API-Key"`                        | Header for API key auth                         |
| `api_key_enabled`       | `bool`                            | `False`                              | Enable API key authentication                   |
| `max_token_age_seconds` | `Optional[int]`                   | `None`                               | Absolute token age limit (independent of `exp`) |
| `MIN_SECRET_LENGTH`     | `int`                             | `32`                                 | Minimum key length for symmetric algorithms     |

**Validation invariants:**

- `__post_init__` enforces minimum secret length of 32 characters for HS\* algorithms (NIST SP 800-117 guidance).
- Asymmetric algorithms require either `public_key` or `jwks_url`.
- These checks run at construction time -- misconfigured JWTConfig fails fast.

**Security hardening in `verify_token()`:**

1. **Algorithm confusion prevention:** The token's `alg` header is compared against the configured algorithm _before_ verification. Mismatches are rejected. The `none` algorithm is explicitly blocked.
2. **Refresh token rejection:** Tokens with `token_type: "refresh"` are rejected when used for API authentication, preventing token-type confusion.
3. **JWKS support:** For SSO providers, the `PyJWKClient` fetches signing keys from a JWKS endpoint with configurable cache TTL.
4. **Algorithm not revealed in errors:** When algorithm mismatch is detected, the error message does not disclose the configured algorithm to potential attackers.

**Token creation:**

- `create_access_token()` produces short-lived tokens (default 30 minutes in the Trust-Plane `JWTValidator`; the Middleware `JWTAuthManager` defaults to 15 minutes -- these are separate subsystems with independent defaults). Reserved claims (`sub`, `iat`, `exp`, `iss`, `aud`, `token_type`, `roles`, `permissions`, `tenant_id`) cannot be overridden via `extra_claims` -- attempts are silently dropped with a warning log.
- `create_refresh_token()` produces long-lived tokens (default 7 days) with a unique `jti` claim. Refresh tokens carry `token_type: "refresh"` which is enforced during verification.

**Absolute token age check:**

- When `max_token_age_seconds` is configured, `check_token_age()` validates that `iat` is a finite number, is not in the future, and that the token age does not exceed the limit. This is independent of the `exp` claim and catches long-lived tokens created with excessively large expiration values.

**User extraction (`create_user_from_payload()`):**

Normalizes different JWT claim formats into `AuthenticatedUser`:

- `sub` / `user_id` / `uid` -> `user_id`
- `email` / `preferred_username` -> `email`
- `roles` (list or string) + `role` (string) -> `roles[]`
- `permissions` (list or space-delimited string) + `scope` -> `permissions[]`
- `tenant_id` / `tid` / `organization_id` -> `tenant_id`
- `iss` -> provider detection (azure, google, apple, github, local)

#### 2.1.2 Middleware JWTAuthManager (`kailash.middleware.auth.jwt_auth`)

Middleware-specific JWT manager for the Nexus middleware layer. Provides additional features on top of the core validator:

- **RSA key pair generation and rotation:** Auto-generates 2048-bit RSA keys with configurable rotation interval (`key_rotation_days`, default 30).
- **Refresh token tracking:** In-memory store of refresh tokens with per-token metadata (user_id, tenant_id, created_at, refresh_count, last_used).
- **Max refresh count:** Limits how many times a refresh token can be used (default 10) before automatic revocation.
- **Token blacklisting:** Optional in-memory blacklist for revoked tokens (`enable_blacklist`, default True).
- **JWKS export:** `get_public_key_jwks()` exports the public key in JWKS format for external verifiers.
- **Token pair creation:** `create_token_pair()` returns both access and refresh tokens as a `TokenPair` dataclass.
- **Cleanup:** `cleanup_expired_tokens()` removes expired refresh tokens and old failed attempt records.

**Token payload structure (`TokenPayload`):**

| Claim           | Type            | Purpose                                 |
| --------------- | --------------- | --------------------------------------- |
| `sub`           | `str`           | User ID                                 |
| `iss`           | `str`           | Issuer (default `"kailash-middleware"`) |
| `aud`           | `str`           | Audience (default `"kailash-api"`)      |
| `exp`           | `int`           | Expiration timestamp                    |
| `iat`           | `int`           | Issued-at timestamp                     |
| `jti`           | `str`           | Unique token ID (UUID4)                 |
| `tenant_id`     | `Optional[str]` | Tenant identifier                       |
| `session_id`    | `Optional[str]` | Session identifier                      |
| `token_type`    | `str`           | `"access"` or `"refresh"`               |
| `permissions`   | `List[str]`     | Permission strings                      |
| `roles`         | `List[str]`     | Role strings                            |
| `refresh_count` | `int`           | Refresh usage count                     |

**Token expiration defaults:**

| Token type | Default expiration |
| ---------- | ------------------ |
| Access     | 15 minutes         |
| Refresh    | 7 days             |

### 2.2 API Key Authentication

API keys are generated and managed through the `MiddlewareAuthManager` (`kailash.middleware.auth.auth_manager`).

**Key format:** `sk_` prefix followed by 32 bytes of URL-safe base64 (`secrets.token_urlsafe(32)`).

**Verification flow:**

1. Client sends `X-API-Key` header.
2. `verify_api_key()` queries `CredentialManagerNode` for the key's metadata.
3. If valid, returns metadata dict containing `user_id`, `key_name`, `permissions`, and `created_at`.
4. If invalid, logs security event via `SecurityEventNode` and returns 401.

**Permission checking:** API keys carry their own permission list. When `required_permissions` is specified on a route, each permission is checked first against the key's embedded permissions, then via `PermissionCheckNode` for dynamic permission resolution.

**Edge cases:**

- API keys are disabled when `enable_api_keys=False` in the auth manager -- calls to `create_api_key()` or `verify_api_key()` return HTTP 400.
- API key rotation is handled by `RotatingCredentialNode` which supports configurable rotation intervals.

### 2.3 SSO Integration

The trust-plane SSO layer (`kailash.trust.auth.sso`) provides pluggable OAuth2/OIDC integration.

**Supported providers (`kailash.trust.auth.sso/`):**

| Provider | Module      | Protocol           |
| -------- | ----------- | ------------------ |
| Google   | `google.py` | OAuth2 / OIDC      |
| Azure AD | `azure.py`  | OAuth2 / OIDC      |
| Apple    | `apple.py`  | Sign in with Apple |
| GitHub   | `github.py` | OAuth2             |

**CSRF protection:**

SSO flows use a `SessionStore` protocol for CSRF nonce validation:

```python
class SessionStore(Protocol):
    def store(self, state: str) -> None: ...
    def validate_and_consume(self, state: str) -> bool: ...
    def cleanup(self) -> None: ...
```

- `InMemorySessionStore`: Development only. State is lost on restart and not shared across workers.
- For production: Implement `SessionStore` with Redis. Example pattern provided in the module docstring.

**State token lifecycle:**

1. `store(state)` saves the nonce with a timestamp.
2. `validate_and_consume(state)` atomically validates and removes the nonce (single-use).
3. Nonces expire after `ttl_seconds` (default 600 seconds / 10 minutes).
4. `cleanup()` removes expired entries.

**Provider detection from JWT issuer:**

| Issuer pattern              | Provider |
| --------------------------- | -------- |
| `login.microsoftonline.com` | azure    |
| `accounts.google.com`       | google   |
| `appleid.apple.com`         | apple    |
| `github.com`                | github   |
| Anything else               | local    |

### 2.4 Multi-Factor Authentication

`MultiFactorAuthNode` (`kailash.nodes.auth.mfa`) provides MFA capabilities as a workflow node. Supports TOTP-based verification flows that can be wired into authentication workflows.

### 2.5 Risk-Based Authentication

`RiskAssessmentNode` (`kailash.nodes.auth.risk_assessment`) performs contextual risk scoring during authentication. Evaluates factors like:

- Login location anomalies
- Device fingerprint changes
- Time-of-day patterns
- Failed attempt history

### 2.6 Enterprise Authentication

`EnterpriseAuthProviderNode` (`kailash.nodes.auth.enterprise_auth_provider`) integrates with enterprise identity providers. `DirectoryIntegrationNode` (`kailash.nodes.auth.directory_integration`) provides LDAP/Active Directory connectivity.

---

## 3. Authorization

### 3.1 RBAC (Role-Based Access Control)

Two RBAC implementations exist at different layers.

#### 3.1.1 Trust-Plane RBACManager (`kailash.trust.auth.rbac`)

Framework-agnostic RBAC extracted from Nexus (SPEC-06).

**Role definitions:**

```python
@dataclass
class RoleDefinition:
    name: str
    permissions: List[str]       # Permissions granted to this role
    description: str = ""
    inherits: List[str] = []     # Role inheritance chain
```

**Permission syntax:**

| Pattern      | Matches                             |
| ------------ | ----------------------------------- |
| `read:users` | Exactly `read:users`                |
| `read:*`     | `read:users`, `read:articles`, etc. |
| `*:users`    | `read:users`, `write:users`, etc.   |
| `*`          | Everything (superadmin)             |

**Matching algorithm (`matches_permission()`):**

1. Pattern `*` matches everything.
2. Exact match.
3. Split both pattern and permission on `:` into action and resource.
4. If pattern action is `*`, check resource match (or resource is also `*`).
5. If pattern resource is `*`, check action match.

**Role inheritance:**

- Roles can inherit from other roles via the `inherits` field.
- Inheritance graph is validated at load time -- cycles and references to undefined roles raise `ValueError`.
- Cycle detection uses DFS with path tracking.
- Resolved permissions are cached per role in `_permission_cache` (cleared on any role add/remove).

**Key methods:**

| Method                                     | Purpose                                                    |
| ------------------------------------------ | ---------------------------------------------------------- |
| `has_permission(role_or_user, permission)` | Check if role/user has permission (with wildcard matching) |
| `has_role(user, *roles)`                   | Check if user has any of the specified roles               |
| `require_permission(user, permission)`     | Raises `InsufficientPermissionError` if lacking            |
| `require_role(user, *roles)`               | Raises `InsufficientRoleError` if lacking                  |
| `get_role_permissions(role_name)`          | Resolve all permissions including inherited (cached)       |
| `get_user_permissions(user)`               | Resolve all permissions across all user roles + direct     |

**Default role:** When a user has no roles and `default_role` is configured, the default role's permissions are applied.

#### 3.1.2 Workflow Access Control (`kailash.access_control`)

Workflow-level RBAC/ABAC system for controlling access to workflows and individual nodes.

**Permission types:**

| Type                 | Values                                               | Scope          |
| -------------------- | ---------------------------------------------------- | -------------- |
| `WorkflowPermission` | VIEW, EXECUTE, MODIFY, DELETE, SHARE, ADMIN          | Workflow-level |
| `NodePermission`     | EXECUTE, READ_OUTPUT, WRITE_INPUT, SKIP, MASK_OUTPUT | Node-level     |

**Permission effects:**

| Effect        | Behavior                                    |
| ------------- | ------------------------------------------- |
| `ALLOW`       | Grant access                                |
| `DENY`        | Deny access (takes precedence)              |
| `CONDITIONAL` | Evaluate runtime conditions before deciding |

**`PermissionRule` fields:**

| Field           | Type                                     | Purpose                           |
| --------------- | ---------------------------------------- | --------------------------------- |
| `id`            | `str`                                    | Unique rule identifier            |
| `resource_type` | `str`                                    | `"workflow"` or `"node"`          |
| `resource_id`   | `str`                                    | Workflow ID or node ID            |
| `permission`    | `WorkflowPermission` or `NodePermission` | Permission being granted/denied   |
| `effect`        | `PermissionEffect`                       | ALLOW, DENY, or CONDITIONAL       |
| `user_id`       | `Optional[str]`                          | Specific user (None = any)        |
| `role`          | `Optional[str]`                          | Role match (None = any)           |
| `tenant_id`     | `Optional[str]`                          | Tenant match (None = any)         |
| `conditions`    | `Dict[str, Any]`                         | Conditions for CONDITIONAL effect |
| `priority`      | `int`                                    | Higher = evaluated first          |
| `expires_at`    | `Optional[datetime]`                     | Rule expiration                   |

**Rule evaluation order:**

1. Rules are sorted by priority (descending).
2. For each applicable rule, check if it matches the user (user_id, role, tenant_id, or unrestricted).
3. Expired rules are skipped.
4. CONDITIONAL rules evaluate all conditions; if all pass, the effect is ALLOW.
5. Explicit DENY breaks evaluation immediately.
6. If no rules match, default is DENY.

**Caching:**

- Access decisions are cached with key format: `{resource_type}:{resource_id}:{user_id}:{permission_value}`.
- Cache is invalidated when rules are added or removed.
- Runtime-context-dependent decisions bypass the cache.

**Data masking:**

- `mask_node_output()` applies field-level masking to node outputs.
- Masked fields are replaced with `"***MASKED***"`.
- Masking rules are specified in the `masked_fields` condition of CONDITIONAL permission rules.

**Global instance:**

- `get_access_control_manager()` returns the global singleton.
- `set_access_control_manager()` replaces it.
- The global manager is disabled by default (`enabled=False`) for backward compatibility.

### 3.2 ABAC (Attribute-Based Access Control)

`kailash.access_control_abac` extends RBAC with attribute-based policies.

**Attribute operators (`AttributeOperator`):**

| Operator                             | Behavior                                                                         |
| ------------------------------------ | -------------------------------------------------------------------------------- |
| `EQUALS` / `NOT_EQUALS`              | Value comparison (case-sensitive toggle)                                         |
| `CONTAINS` / `NOT_CONTAINS`          | Membership/substring check                                                       |
| `CONTAINS_ANY`                       | Any of the expected items in value                                               |
| `IN` / `NOT_IN`                      | Value in expected collection                                                     |
| `GREATER_THAN` / `LESS_THAN`         | Numeric comparison                                                               |
| `GREATER_OR_EQUAL` / `LESS_OR_EQUAL` | Numeric comparison                                                               |
| `MATCHES`                            | Regex match                                                                      |
| `BETWEEN`                            | Range check (inclusive)                                                          |
| `HIERARCHICAL_MATCH`                 | Department tree matching (e.g., `engineering.backend.api` matches `engineering`) |
| `SECURITY_LEVEL_MEETS`               | Security clearance level comparison                                              |
| `SECURITY_LEVEL_BELOW`               | Below clearance level                                                            |
| `MATCHES_DATA_REGION`                | Region matching with family grouping                                             |

**Security clearance hierarchy:**

| Level          | Numeric value |
| -------------- | ------------- |
| `public`       | 0             |
| `internal`     | 1             |
| `confidential` | 2             |
| `secret`       | 3             |
| `top_secret`   | 4             |

**Logical operators:** `AND`, `OR`, `NOT` for combining conditions. `NOT` requires exactly one sub-condition.

**Data masking types:**

| Mask type | Behavior                                          |
| --------- | ------------------------------------------------- |
| `redact`  | Replaces with `[REDACTED]`                        |
| `partial` | Shows first 2 and last 2 characters, masks middle |
| `hash`    | SHA-256 hash (first 16 hex chars)                 |
| `replace` | Replaces with specified value                     |

**Enhanced condition evaluators (`EnhancedConditionEvaluator`):**

Extends the base `ConditionEvaluator` with:

- `attribute_expression`: Complex attribute conditions with nested AND/OR/NOT logic.
- `department_hierarchy`: Department tree matching with optional child inclusion.
- `security_clearance`: Minimum clearance level check.
- `geographic_region`: Region-based access control.
- `time_of_day`: Time range conditions (handles overnight ranges).
- `day_of_week`: Allowed weekday conditions.

### 3.3 Composition-Based Manager

`kailash.access_control.managers.AccessControlManager` uses the composition pattern with pluggable evaluation strategies.

**Strategies:**

| Strategy | Evaluator             | Capabilities                                      |
| -------- | --------------------- | ------------------------------------------------- |
| `rbac`   | `RBACRuleEvaluator`   | Role/user/tenant matching, no conditions          |
| `abac`   | `ABACRuleEvaluator`   | Full attribute conditions, complex expressions    |
| `hybrid` | `HybridRuleEvaluator` | ABAC for conditional rules, RBAC for simple rules |

Default strategy is `hybrid`.

**Factory:** `create_rule_evaluator(strategy)` returns the appropriate evaluator.

### 3.4 RBAC Matrix Export and Conflict Detection

`kailash.access_control.matrix_exporter.RBACMatrixExporter` provides:

**Matrix export** (`export_matrix()` -> `RBACMatrix`):

- Builds a roles x resources x permissions matrix.
- Cells contain effect summaries: `"allow"`, `"deny"`, `"allow (conditional)"`, or `"allow,deny"` for conflicts.
- Export formats: CSV (`to_csv()`), JSON (`to_json()`), Markdown (`to_markdown()`).

**Conflict detection** (`detect_conflicts()` -> `List[PolicyConflict]`):

- Identifies rules targeting the same resource and permission with overlapping scope but different effects.
- Severity: `"high"` when conflicting rules have equal priority (ambiguous outcome), `"medium"` when priority resolves the conflict.
- Scope overlap detection considers: same role, same user, same tenant, or unrestricted rules (apply to everyone).

### 3.5 AccessControlledRuntime

`kailash.runtime.access_controlled.AccessControlledRuntime` wraps `LocalRuntime` with access control enforcement.

**Behavior:**

- When `acm.enabled` is False (default), all operations pass through unchanged.
- When enabled, checks `WorkflowPermission.EXECUTE` before workflow execution.
- Wraps each node with `AccessControlledNodeWrapper` that:
  1. Checks `NodePermission.EXECUTE` before running.
  2. If denied, optionally redirects to an alternative node.
  3. After execution, checks `NodePermission.READ_OUTPUT` to control output visibility.
  4. Applies field masking on masked fields.

**Convenience function:** `execute_with_access_control(workflow, user_context, ...)` handles runtime lifecycle.

---

## 4. Session Management

### 4.1 Session Nodes

`SessionManagementNode` (`kailash.nodes.auth.session_management`) provides session lifecycle operations as workflow nodes: creation, validation, renewal, and destruction.

### 4.2 Nexus Sessions

`kailash.channels.session` provides the unified session model for Nexus multi-channel deployment:

- Sessions span API, CLI, and MCP channels.
- Session ID ties together state across channels.
- Session ID is included as a JWT claim (`session_id`) for correlation.

### 4.3 SSO State Store

`kailash.trust.auth.session` provides the SSO CSRF state store. See Section 2.3 for details.

---

