# Kailash Security -- Secrets, Credentials, Encryption, Framework, Nodes

Parent domain: Kailash Security. This sub-spec covers secrets management, credential handling, encryption (at rest and in transit), the security framework (`kailash.security`), security nodes, trust-plane security (`kailash.trust.security`), and DataFlow access controls. See `security-auth.md` for authentication, authorization, and sessions. See `security-threats.md` for audit logging, the exception hierarchy, threat model, and configuration defaults.

---

## 5. Secrets Management

### 5.1 SecretProvider Interface

`kailash.runtime.secret_provider` defines the pluggable secret provider architecture.

**Interface (`SecretProvider` ABC):**

```python
class SecretProvider(ABC):
    def get_secret(self, name: str, version: Optional[str] = None) -> str: ...
    def list_secrets(self) -> List[str]: ...
    def get_secrets(self, requirements: List[SecretRequirement]) -> Dict[str, str]: ...
```

**`SecretRequirement` fields:**

| Field            | Type            | Purpose                              |
| ---------------- | --------------- | ------------------------------------ |
| `name`           | `str`           | Secret name in the provider          |
| `parameter_name` | `str`           | Parameter name in the consuming node |
| `version`        | `Optional[str]` | Version identifier                   |
| `optional`       | `bool`          | Whether missing secret is fatal      |

### 5.2 Environment Provider

`EnvironmentSecretProvider` reads secrets from environment variables.

**Naming convention:** `{prefix}{NAME}` where prefix defaults to `KAILASH_SECRET_` and the name is uppercased with hyphens replaced by underscores.

**Fallback:** If the prefixed variable is not found, tries the unprefixed uppercased name for backward compatibility.

### 5.3 HashiCorp Vault Provider

`VaultSecretProvider` integrates with HashiCorp Vault.

| Parameter     | Default    | Purpose              |
| ------------- | ---------- | -------------------- |
| `vault_url`   | (required) | Vault server URL     |
| `vault_token` | (required) | Authentication token |
| `mount_path`  | `"secret"` | Vault mount path     |

- Tries KV v2 first, falls back to KV v1.
- Client is lazily initialized.
- Requires `hvac` library (optional extra).

### 5.4 AWS Secrets Manager Provider

`AWSSecretProvider` integrates with AWS Secrets Manager.

| Parameter     | Default       | Purpose    |
| ------------- | ------------- | ---------- |
| `region_name` | `"us-east-1"` | AWS region |

- Supports version-specific secret retrieval.
- Client is lazily initialized.
- Requires `boto3` library (optional extra).

### 5.5 Exception Types

| Exception             | Purpose                           |
| --------------------- | --------------------------------- |
| `SecretNotFoundError` | Secret does not exist in provider |
| `SecretProviderError` | Provider operation failed         |

---

## 6. Credential Handling

### 6.1 URL Credential Decode (`kailash.utils.url_credentials`)

Single shared helper module for all database credential parsing. Every code path that extracts credentials from a `DATABASE_URL`-style connection string MUST route through this module.

#### 6.1.1 `decode_userinfo_or_raise(parsed, *, default_user="root")`

Decodes percent-encoded username and password from a `urlparse` result. Raises `ValueError` if either decoded field contains a null byte (`\x00`).

**Null-byte threat model:**

- MySQL C client truncates credentials at the first null byte.
- A crafted `mysql://user:%00bypass@host/db` decodes to `\x00bypass`, which the driver truncates to an empty string.
- This succeeds against any MySQL user with an empty `authentication_string`, enabling auth bypass.
- PostgreSQL's libpq rejects null bytes outright, but uniform rejection at the parsing layer ensures identical behavior regardless of driver.

**Contract:**

- Returns `(user, password)` tuple with percent-encoding removed.
- Null bytes in either field -> `ValueError`.
- Missing username -> `default_user` parameter.
- Missing password -> empty string.

#### 6.1.2 `preencode_password_special_chars(connection_string)`

Pre-encodes raw `#$@?` characters in the password portion of a URL, for operators who paste raw connection strings without URL-encoding.

**Character handling:**

- Finds the LAST `@` in the URL (handles passwords containing literal `@`).
- Splits user and password on the FIRST `:` (handles passwords containing literal `:`).
- Percent-encodes `#` -> `%23`, `$` -> `%24`, `@` -> `%40`, `?` -> `%3F` in the password.

**Required callers (all five dialect parse sites):**

1. `src/kailash/db/connection.py`
2. `src/kailash/trust/esa/database.py`
3. `src/kailash/nodes/data/async_sql.py`
4. `packages/kailash-dataflow/src/dataflow/core/pool_utils.py`
5. `packages/kaizen-agents/src/kaizen_agents/patterns/state_manager.py`

---

## 7. Encryption

### 7.1 TrustPlane Encryption at Rest (`kailash.trust.plane.encryption.crypto_utils`)

AES-256-GCM encryption for trust plane records.

**Constants:**

| Constant      | Value                         | Purpose            |
| ------------- | ----------------------------- | ------------------ |
| `_NONCE_SIZE` | 12 bytes                      | GCM nonce length   |
| `_KEY_SIZE`   | 32 bytes                      | AES-256 key length |
| `_HKDF_INFO`  | `b"trustplane-encryption-v1"` | HKDF context       |

**Key derivation (`derive_encryption_key()`):**

- Algorithm: HKDF-SHA256
- Input: Arbitrary-length key material (must be non-empty)
- Output: 32-byte AES-256 key
- Salt: None (stateless derivation)

**Encryption (`encrypt_record()`):**

- Fresh 12-byte random nonce per call (`os.urandom(12)`)
- AES-256-GCM with 16-byte authentication tag
- Output format: `nonce (12 bytes) || ciphertext (includes tag)`
- Strict type/length validation on inputs

**Decryption (`decrypt_record()`):**

- Validates minimum ciphertext length (nonce + GCM tag = 28 bytes)
- Raises `TrustDecryptionError` on:
  - Truncated ciphertext
  - Wrong key (invalid authentication tag)
  - Tampered ciphertext

### 7.2 EATP Key Storage (`kailash.trust.security.SecureKeyStorage`)

Fernet-based encryption for EATP cryptographic keys at rest.

**Key derivation:**

- Algorithm: PBKDF2-HMAC-SHA256 with 100,000 iterations
- Master key source: Environment variable (default `KAIZEN_TRUST_ENCRYPTION_KEY`)
- Salt: Per-instance (CARE-001 fix). Priority: explicit `__init__` salt > env var `{master_key_source}_SALT` > random `os.urandom(32)`.
- Random salt generates a warning -- keys will not be recoverable across restarts.

**Operations:**

- `store_key(key_id, private_key)`: Encrypts and stores key bytes in memory.
- `retrieve_key(key_id)`: Decrypts and returns key bytes.
- `delete_key(key_id)`: Removes encrypted key from memory.

**Threat model:**

- Keys are encrypted in-memory using Fernet (AES-128-CBC + HMAC-SHA256).
- Master key never stored in memory in plaintext -- derived once during init.
- Random salt without env var means keys are ephemeral per process.

### 7.3 Signing Algorithms

**EATP trust plane:**

- Ed25519 is the mandatory signing algorithm for trust records.
- HMAC is an optional overlay (HMAC alone is NEVER sufficient for external verification).
- AWS KMS uses ECDSA P-256 (Ed25519 not available in KMS).
- Constant-time comparison via `hmac.compare_digest()` -- NEVER use `==` for signature comparison.

**JWT:**

- See Section 2.1 for supported algorithms.

---

## 8. Security Framework (`kailash.security`)

Core input validation and execution sandboxing layer.

### 8.1 SecurityConfig

| Parameter                   | Default                                                                       | Purpose                               |
| --------------------------- | ----------------------------------------------------------------------------- | ------------------------------------- |
| `allowed_directories`       | `~/.kailash`, temp dirs, cwd, `/tmp`, `/var/tmp` + `KAILASH_ALLOWED_DIRS` env | Permitted file system paths           |
| `max_file_size`             | 100 MB                                                                        | Maximum file size for read operations |
| `execution_timeout`         | 300 seconds                                                                   | Maximum execution time                |
| `memory_limit`              | 512 MB                                                                        | Maximum memory usage                  |
| `allowed_file_extensions`   | `.txt`, `.csv`, `.json`, `.yaml`, `.py`, etc. (18 extensions)                 | Permitted file extensions             |
| `enable_audit_logging`      | `True`                                                                        | Log security events                   |
| `enable_path_validation`    | `True`                                                                        | Validate file paths                   |
| `enable_command_validation` | `True`                                                                        | Validate command strings              |

### 8.2 Path Validation (`validate_file_path()`)

**Checks (in order):**

1. Resolve to absolute path.
2. Reject `..` in original input (path traversal).
3. Block sensitive system directories: `/etc`, `/var`, `/usr`, `/root`, `/boot`, `/sys`, `/proc`.
4. Validate file extension against allowlist.
5. Verify path is within an allowed directory (using `Path.relative_to()` with fallback to string prefix).

**Returns:** Normalized `Path` object.

**Raises:** `PathTraversalError` (traversal attempt), `SecurityError` (extension or directory violation).

### 8.3 Input Sanitization (`sanitize_input()`)

**Type validation:** Checks input against a cached allowlist of types (built once, cached for performance -- P0D-002 optimization). Includes core Python types plus optional data science types (pandas, numpy, torch, tensorflow, scipy, sklearn, xgboost, lightgbm, matplotlib, plotly, statsmodels, PIL, spacy, networkx, prophet).

**String sanitization (context-aware):**

| Context       | Removes                                                  | Preserves                                              |
| ------------- | -------------------------------------------------------- | ------------------------------------------------------ |
| `generic`     | `<script>` tags, `javascript:` URLs, angle brackets      | Most characters                                        |
| `python_exec` | `<script>` tags, `javascript:` URLs, HTML injection tags | Shell metacharacters (`$;& \|`) -- safe in Python exec |
| `shell_exec`  | All shell metacharacters (`<>;&\|$()`) plus script tags  | Nothing dangerous                                      |

**Length validation:** Rejects strings exceeding `max_length` (default 10,000).

**Recursive:** Sanitizes dicts and lists recursively.

### 8.4 Command Injection Prevention (`validate_command_string()`)

Blocks patterns including:

- Command chaining: `;`, `&&`, `||`
- Pipe operations: `|`
- Command substitution: `$(...)`, backticks
- Device redirection: `> /dev/`
- Dangerous commands: `eval`, `exec`, `rm ... /`, `cat /etc/`

### 8.5 Execution Timeout (`execution_timeout()`)

Context manager that tracks elapsed time and raises `ExecutionTimeoutError` if execution exceeds the configured timeout.

### 8.6 Secure Temporary Directories (`create_secure_temp_dir()`)

Creates temp directories with `0o700` permissions (owner-only access).

---

## 9. Security Nodes

### 9.1 Credential Nodes (`kailash.nodes.security`)

| Node                          | Purpose                                                 |
| ----------------------------- | ------------------------------------------------------- |
| `CredentialManagerNode`       | Stores, retrieves, and validates credentials            |
| `RotatingCredentialNode`      | Manages credential rotation with configurable intervals |
| `AuditLogNode`                | Records security events for audit trails                |
| `SecurityEventNode`           | Generates and dispatches security event notifications   |
| `ThreatDetectionNode`         | Detects anomalous patterns in authentication and access |
| `BehaviorAnalysisNode`        | Analyzes user behavior for security anomalies           |
| `ABACPermissionEvaluatorNode` | Evaluates ABAC policies within workflow pipelines       |

### 9.2 Auth Nodes (`kailash.nodes.auth`)

| Node                         | Purpose                                   |
| ---------------------------- | ----------------------------------------- |
| `MultiFactorAuthNode`        | TOTP/SMS/email MFA verification           |
| `SessionManagementNode`      | Session create/validate/renew/destroy     |
| `SSOAuthenticationNode`      | OAuth2/OIDC SSO flow orchestration        |
| `DirectoryIntegrationNode`   | LDAP/Active Directory user lookup         |
| `EnterpriseAuthProviderNode` | Enterprise IdP integration (SAML, OIDC)   |
| `RiskAssessmentNode`         | Context-based authentication risk scoring |

---

## 10. Trust-Plane Security (`kailash.trust.security`)

Security hardening for the Enterprise Agent Trust Protocol (EATP).

### 10.1 Input Validation (`TrustSecurityValidator`)

**Agent ID validation:** UUID format only (`^[0-9a-f]{8}-[0-9a-f]{4}-...`).

**Authority ID validation:** Alphanumeric with hyphens/underscores, starts with alphanumeric, 1-64 characters (`^[a-zA-Z0-9][a-zA-Z0-9\-_]{0,63}$`).

**Capability URI validation:**

- Must have a scheme.
- Blocks dangerous schemes: `javascript`, `data`, `vbscript`.
- HTTP/HTTPS must have a netloc.

**Metadata sanitization:** Removes:

- `<script>` tags
- `javascript:` URLs
- `on*=` event handler attributes
- `data:text/html` URIs

Applies recursively to nested dicts and lists.

### 10.2 Rate Limiting (`TrustRateLimiter`)

Per-authority sliding-window rate limiting for trust operations.

**Default limits:**

| Operation   | Limit                          |
| ----------- | ------------------------------ |
| `establish` | 100 per minute per authority   |
| `verify`    | 1,000 per minute per authority |
| Other       | 100 per minute per authority   |

**Memory protection (ROUND5-007):** Limits tracked authorities to `MAX_TRACKED_AUTHORITIES = 10,000`. When capacity is reached, the authority with the oldest most-recent timestamp is evicted. This prevents memory exhaustion via unique authority ID flooding.

**Concurrency:** Uses `asyncio.Lock` for thread-safe operation.

### 10.3 Security Audit Logger (`SecurityAuditLogger`)

In-memory audit log with configurable capacity.

**Event types (`SecurityEventType`):**

| Category            | Events                                                                                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Authentication      | SUCCESS, FAILURE                                                                                                                                            |
| Authorization       | SUCCESS, FAILURE                                                                                                                                            |
| Trust operations    | ESTABLISH_TRUST, VERIFY_TRUST, DELEGATE_CAPABILITY, REVOKE_DELEGATION                                                                                       |
| Validation          | SUCCESS, FAILURE                                                                                                                                            |
| Key management      | KEY_STORED, KEY_RETRIEVED, KEY_DELETED                                                                                                                      |
| Rate limiting       | RATE_LIMIT_EXCEEDED, RATE_LIMIT_WARNING                                                                                                                     |
| Attack detection    | INJECTION_ATTEMPT, REPLAY_ATTACK, SUSPICIOUS_ACTIVITY                                                                                                       |
| Credential rotation | ROTATION_STARTED, ROTATION_COMPLETED, ROTATION_FAILED, ROTATION_SCHEDULED, ROTATION_KEY_REVOKED, SCHEDULED_ROTATION_FAILED, CHAIN_RESIGN_INCONSISTENT_STATE |

**Severity levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL.

**Capacity management:** When `max_events` (default 10,000) is exceeded, oldest events are trimmed. Uses `threading.Lock` for thread safety (ROUND5-005 fix).

**Filtering:** `get_recent_events()` supports filtering by event_type, authority_id, and severity.

---

## 11. DataFlow Access Controls

DataFlow security is enforced at multiple levels:

### 11.1 Model-Level Security

- `@db.model` definitions declare the schema as code -- no raw DDL.
- DataFlow auto-migration creates tables from model definitions.
- `quote_identifier()` is mandatory for all dynamic DDL identifiers (see `rules/dataflow-identifier-safety.md`).

### 11.2 Express API Security

- `db.express.create/read/update/delete/list` operations go through the DataFlow framework.
- When access control is enabled (`AccessControlledRuntime`), RBAC/ABAC rules are evaluated before each operation.
- DataFlow validates all input at the model level before database interaction.

### 11.3 SQL Injection Prevention

- All VALUES-path queries use parameterized SQL (see `rules/infrastructure-sql.md`).
- All identifier-path DDL uses `dialect.quote_identifier()` which validates against `^[a-zA-Z_][a-zA-Z0-9_]*$`, checks dialect-specific length limits, and quotes with dialect-appropriate characters.
- The "reject, don't escape" rule eliminates bypass attempts -- invalid identifiers are refused, not sanitized.
- `BulkUpsertNode._build_upsert_query` returns `(sql, params)` with dialect-appropriate placeholders (`$N` PostgreSQL, `?` SQLite, `%s` MySQL); VALUES are bound by the driver, never string-escaped (issue #492 regression).
- DataFlow's `validate_inputs` sanitizer applies the contract pinned in `rules/security.md` § Sanitizer Contract: token-replace for display-path safety (`STATEMENT_BLOCKED`, `DROP_TABLE`, `UNION_SELECT` sentinels), and `ValueError` raise on type-confusion when a `dict`/`list`/`set`/`tuple` value is passed to a declared-`str` field (issue #493).

### 11.4 DROP Protection

- All DROP operations require explicit `force_drop=True` flag.
- Default is to refuse with a descriptive error naming the data loss risk.

---
