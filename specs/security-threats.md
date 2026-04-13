# Kailash Security -- Audit, Exceptions, Threat Model, Configuration

Parent domain: Kailash Security. This sub-spec covers audit logging, the security exception hierarchy, the threat model summary, and the configuration reference with production defaults. See `security-auth.md` for authentication, authorization, and sessions. See `security-data.md` for secrets, credentials, encryption, the security framework, nodes, trust-plane security, and DataFlow access controls.

---

## 12. Audit Logging

### 12.1 Access Control Audit

Every access control decision is logged via `audit_logger` (named `kailash.access_control.audit`):

```python
extra={
    "user_id": user.user_id,
    "tenant_id": user.tenant_id,
    "resource_type": resource_type,
    "resource_id": resource_id,
    "permission": permission.value,
    "allowed": decision.allowed,
    "reason": decision.reason,
    "applied_rules": decision.applied_rules,
    "evaluator": type(self.rule_evaluator).__name__,
}
```

### 12.2 Auth Events

Auth events are logged per the observability rules:

- Login success/failure with user_id and method.
- Token creation with user_id (no token content).
- Token verification failures with error classification.
- Permission check results with user_id and permission.
- Security events (rate limit, injection attempt) via `SecurityEventNode`.

### 12.3 Trust-Plane Audit

`SecurityAuditLogger` maintains structured events for EATP operations. Each event captures: type, timestamp (UTC), authority_id, optional agent_id, details dict, and severity level.

### 12.4 Middleware Audit

When `enable_audit=True` in `MiddlewareAuthManager`, `AuditLogNode` records:

- Token creation (user_id, permissions)
- API key creation (user_id, key_name, permissions)
- Permission checks (user_id, permission, granted)

---

## 13. Exception Hierarchy

### 13.1 Core Security Exceptions (`kailash.security`)

```
SecurityError
  PathTraversalError
  CommandInjectionError
  ExecutionTimeoutError
  MemoryLimitError
```

### 13.2 Auth Exceptions (`kailash.middleware.auth.exceptions`)

```
AuthenticationError
  TokenExpiredError
  InvalidTokenError
  TokenBlacklistedError
  KeyRotationError
  RefreshTokenError
  PermissionDeniedError
  RateLimitError
  InvalidCredentialsError
  SessionExpiredError
```

### 13.3 Trust Auth Exceptions (`kailash.trust.auth.exceptions`)

```
AuthError (status_code=500)
  AuthenticationError (status_code=401)
    InvalidTokenError
    ExpiredTokenError
  AuthorizationError (status_code=403)
    InsufficientPermissionError  (generic detail for security)
    InsufficientRoleError        (generic detail for security)
    TenantAccessError
  RateLimitExceededError (status_code=429)
```

**Security note:** `InsufficientPermissionError` and `InsufficientRoleError` use a generic `"Forbidden"` detail in responses. The specific missing permission/role is logged server-side only, preventing information leakage to attackers probing for valid permissions.

### 13.4 Trust Security Exceptions (`kailash.trust.security`)

```
TrustError
  SecurityError
    ValidationError
    EncryptionError
    RateLimitExceededError (includes operation, authority_id, limit)
```

### 13.5 Encryption Exceptions

```
TrustDecryptionError  (wrong key, tampered data, truncated ciphertext)
```

---

## 14. Threat Model Summary

### 14.1 Authentication Threats

| Threat                             | Mitigation                                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| Algorithm confusion attack         | Token `alg` header verified against config before decode; `none` algorithm explicitly blocked |
| Refresh token misuse               | `token_type` claim enforced -- refresh tokens rejected for API auth                           |
| Brute-force on HS256 secret        | Minimum 32-character secret enforced at config time                                           |
| Stale tokens                       | `max_token_age_seconds` provides absolute age check independent of `exp`                      |
| Token replay                       | `jti` claim for unique identification; blacklist for revocation                               |
| JWT injection via extra_claims     | Reserved claims cannot be overridden                                                          |
| Null-byte auth bypass              | `decode_userinfo_or_raise()` rejects null bytes after URL-decoding                            |
| Special char credential truncation | `preencode_password_special_chars()` encodes `#$@?` before parsing                            |

### 14.2 Authorization Threats

| Threat                                    | Mitigation                                                                               |
| ----------------------------------------- | ---------------------------------------------------------------------------------------- |
| Privilege escalation via role inheritance | Cycle detection at load time; inheritance graph validated                                |
| Permission pattern bypass                 | Wildcard matching is exact on `:` split boundary                                         |
| Default-open access                       | Default DENY when no rules match; access control disabled by default for explicit opt-in |
| Expired rule bypass                       | Rule expiration checked at evaluation time                                               |

### 14.3 Data Protection Threats

| Threat                      | Mitigation                                                                         |
| --------------------------- | ---------------------------------------------------------------------------------- |
| SQL injection (values)      | Parameterized queries mandatory                                                    |
| SQL injection (identifiers) | `quote_identifier()` validates-then-quotes; rejects, does not escape               |
| Path traversal              | `validate_file_path()` blocks `..`, sensitive dirs, extension allowlist            |
| Command injection           | `validate_command_string()` blocks shell metacharacters                            |
| XSS in metadata             | `TrustSecurityValidator.sanitize_metadata()` strips script tags and event handlers |
| Key material in memory      | Encrypted at rest via Fernet/AES-256-GCM; immediate deletion after use             |
| Trust state downgrade       | Monotonic escalation enforced (AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED)        |

### 14.4 Denial of Service Threats

| Threat                         | Mitigation                                            |
| ------------------------------ | ----------------------------------------------------- |
| Rate limiting exhaustion       | Per-authority sliding window with configurable limits |
| Memory exhaustion via tracking | `MAX_TRACKED_AUTHORITIES = 10,000` with LRU eviction  |
| Unbounded collections          | `maxlen=10,000` on deque-backed stores                |
| NaN budget bypass              | `math.isfinite()` on all numeric constraint fields    |
| Large file attacks             | `max_file_size` check before read operations          |

---

## 15. Configuration Reference

### 15.1 Environment Variables

| Variable                           | Purpose                                                | Default                         |
| ---------------------------------- | ------------------------------------------------------ | ------------------------------- |
| `KAILASH_SECRET_*`                 | Prefix for `EnvironmentSecretProvider`                 | (none)                          |
| `KAIZEN_TRUST_ENCRYPTION_KEY`      | Master key for EATP key storage                        | (required for SecureKeyStorage) |
| `KAIZEN_TRUST_ENCRYPTION_KEY_SALT` | Salt for EATP key derivation                           | Random per-process              |
| `KAILASH_ALLOWED_DIRS`             | Colon-separated list of additional allowed directories | (none)                          |

### 15.2 Default Security Posture

| Setting                | Default     | Rationale                        |
| ---------------------- | ----------- | -------------------------------- |
| Access control enabled | `False`     | Backward compatibility -- opt-in |
| JWT algorithm          | HS256       | Simplest secure option           |
| Access token expiry    | 15 min (Middleware) / 30 min (Trust-Plane) | Layer-specific defaults |
| Refresh token expiry   | 7 days      | Reasonable session length        |
| Max refresh count      | 10          | Prevent indefinite refresh       |
| Token blacklist        | Enabled     | Revocation support               |
| Path validation        | Enabled     | Defense in depth                 |
| Command validation     | Enabled     | Defense in depth                 |
| Audit logging          | Enabled     | Compliance requirement           |
| File size limit        | 100 MB      | Prevent resource exhaustion      |
| Execution timeout      | 300 seconds | Prevent runaway processes        |
