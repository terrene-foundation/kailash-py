# Kailash MCP Authentication, Protocol, and Error Handling Specification

Parent domain: MCP (Model Context Protocol). Companion files: `mcp-server.md`, `mcp-client.md`.

Package: `kailash-mcp` v0.2.3
Install: `pip install kailash-mcp` (base) | `pip install kailash-mcp[full]` (all features)
License: Apache-2.0 | Terrene Foundation

This file specifies the **authentication, protocol, error handling, and utilities** layers of Kailash MCP: API key / bearer / JWT / basic auth providers, permission and rate limiting, OAuth 2.1 authorization/resource server, protocol managers (progress/cancellation/completion/sampling/roots), error hierarchy and retry strategies, and shared utilities (cache, config, metrics, formatters).

---

## 1. Authentication

### 1.1 AuthProvider (Abstract Base)

```python
class AuthProvider(ABC):
    def authenticate(self, credentials: Union[str, Dict]) -> Dict[str, Any]: ...
    def get_client_config(self) -> Dict[str, Any]: ...
    def get_server_config(self) -> Dict[str, Any]: ...
```

All providers return an auth context dict: `{"user_id": str, "auth_type": str, "permissions": List[str], "metadata": Dict}`.

### 1.2 APIKeyAuth

```python
auth = APIKeyAuth(
    keys: Union[List[str], Dict[str, Dict[str, Any]]],
    header_name: str = "X-API-Key",
    permissions: Optional[List[str]] = None,    # Default: ["read"]
)
```

**Contract:**

- Accepts credentials as a string (the key) or dict with `api_key` field.
- Keys without explicit permissions inherit `default_permissions`.
- User ID is derived from SHA-256 hash of the key: `api_key_{hash[:8]}`.
- Constant-time comparison is NOT used (dict lookup). Use for non-timing-sensitive contexts.

### 1.3 BearerTokenAuth

```python
auth = BearerTokenAuth(
    tokens: Optional[Union[List[str], Dict[str, Dict]]] = None,
    validate_jwt: bool = False,
    jwt_secret: Optional[str] = None,
    jwt_algorithm: str = "HS256",
)
```

**Contract:**

- Accepts credentials as a string (the token) or dict with `token` field.
- When `validate_jwt=True`, decodes JWT using `pyjwt`. Extracts `sub` or `user` as user_id, `permissions` from payload.
- When `validate_jwt=False`, validates against the opaque token registry.
- JWT secret is required when `validate_jwt=True` (raises `ValueError`).
- Handles `ExpiredSignatureError` and `InvalidTokenError` from PyJWT.

### 1.4 JWTAuth

Extends `BearerTokenAuth` with token creation:

```python
auth = JWTAuth(
    secret: str,
    algorithm: str = "HS256",
    expiration: int = 3600,       # seconds
    issuer: str = "mcp-server",
)

token = auth.create_token(
    payload: Dict[str, Any],      # Must include "user" and "permissions"
    expiration: Optional[int],
) -> str
```

**Token payload structure:**

```python
{
    "iss": issuer,
    "iat": int(now),
    "exp": int(now + expiration),
    "jti": uuid4(),
    **payload,
}
```

### 1.5 BasicAuth

```python
auth = BasicAuth(
    users: Dict[str, Union[str, Dict[str, Any]]],
    hash_passwords: bool = False,
)
```

**Contract:**

- Accepts credentials as dict with `username` and `password` fields only. String credentials raise `AuthenticationError`.
- When `hash_passwords=True`, passwords are hashed with PBKDF2-HMAC-SHA256 (100,000 iterations, 32-byte salt).
- Password verification tries PBKDF2 first, falls back to `hmac.compare_digest` for plaintext comparison (timing-safe).
- Requires `cryptography` package for PBKDF2 hashing.

### 1.6 PermissionManager

```python
pm = PermissionManager(
    roles: Optional[Dict[str, List[str]]] = None,
    default_permissions: Optional[List[str]] = None,
)
```

Default roles: `admin` (read, write, delete, manage), `editor` (read, write), `viewer` (read).

`check_permission(user_info, permission)` -- Returns `True` or raises `PermissionError`. Permissions come from `user_info["permissions"]` plus role-based permissions from `user_info["roles"]`.

### 1.7 RateLimiter

```python
limiter = RateLimiter(
    default_limit: int = 60,              # requests per minute
    burst_limit: int = 10,
    per_user_limits: Optional[Dict[str, int]] = None,
)
```

Implements token bucket algorithm. `check_rate_limit(user_info)` returns `True` or raises `RateLimitError` with `retry_after` (seconds until next token).

### 1.8 AuthManager

Combines provider, permissions, and rate limiting:

```python
manager = AuthManager(
    provider: AuthProvider,
    permission_manager: Optional[PermissionManager] = None,
    rate_limiter: Optional[RateLimiter] = None,
    enable_audit: bool = True,
)

user_info = manager.authenticate_and_authorize(
    credentials: Dict,
    required_permission: Optional[str] = None,
)
```

**Pipeline:** authenticate -> rate limit check -> permission check -> audit log.

Audit log retains last 1000 events. Each event: `{timestamp, event_type, user_id, auth_type, permission}`.

### 1.9 OAuth 2.1

Requires `pip install kailash-mcp[auth-oauth]`.

#### Grant Types

- `AUTHORIZATION_CODE` -- Standard authorization code flow with PKCE support.
- `CLIENT_CREDENTIALS` -- Machine-to-machine authentication.
- `REFRESH_TOKEN` -- Token renewal.

#### OAuthClient

```python
@dataclass
class OAuthClient:
    client_id: str
    client_name: str
    client_type: ClientType           # CONFIDENTIAL or PUBLIC
    redirect_uris: List[str]
    grant_types: List[GrantType]
    scopes: List[str]
    client_secret: Optional[str]
    response_types: List[str]         # Default: ["code"]
    token_endpoint_auth_method: str   # Default: "client_secret_basic"
```

#### AuthorizationCode

```python
@dataclass
class AuthorizationCode:
    code: str
    client_id: str
    redirect_uri: str
    scope: Optional[str]
    code_challenge: Optional[str]     # PKCE
    code_challenge_method: Optional[str]  # "S256" or "plain"
    expires_at: float                 # Default: 10 minutes from creation
```

**PKCE validation:** `validate_pkce(code_verifier)` computes SHA-256 of the verifier, base64url-encodes it, and compares against the stored challenge.

#### AccessToken / RefreshToken

Access tokens have `expires_in` (default 3600s), scope (string or list), and audience. `is_expired()` checks against `expires_at`. `has_scope(scope)` checks scope membership.

Refresh tokens support revocation via `revoke()`. Expiration is optional (non-expiring by default).

#### ClientStore / TokenStore

Abstract interfaces for persistence. `InMemoryClientStore` and `InMemoryTokenStore` provide in-memory implementations. Token store manages access tokens, refresh tokens, and authorization codes. Expired tokens are cleaned on access.

#### JWTManager

Handles JWT signing/verification for OAuth tokens using RSA or HMAC algorithms. Supports PEM-encoded keys. Auto-generates RSA-2048 key pair if no keys are provided.

#### AuthorizationServer

Full OAuth 2.1 authorization server with:

- Dynamic client registration
- Authorization endpoint (generates authorization codes)
- Token endpoint (exchanges codes for tokens, handles client credentials, refresh)
- Token introspection
- Token revocation
- Well-known metadata endpoint (`.well-known/oauth-authorization-server`)

#### ResourceServer

OAuth 2.1 resource server middleware. Implements `AuthProvider` interface so it can be passed to `MCPServer(auth_provider=...)`. Validates JWT access tokens against the authorization server's public key.

#### OAuth2Client

Client-side OAuth 2.1 implementation:

```python
client = OAuth2Client(
    client_id="...",
    client_secret="...",
    token_endpoint="https://auth.example.com/token",
)
token = await client.get_client_credentials_token(scopes=["mcp.tools"])
```

---

## 2. Protocol Implementation

### 2.1 Message Types

`MessageType` enum covers the full MCP specification:

- Core: `INITIALIZE`, `INITIALIZED`
- Tools: `TOOLS_LIST`, `TOOLS_CALL`
- Resources: `RESOURCES_LIST`, `RESOURCES_READ`, `RESOURCES_SUBSCRIBE`, `RESOURCES_UNSUBSCRIBE`, `RESOURCES_UPDATED`
- Prompts: `PROMPTS_LIST`, `PROMPTS_GET`
- Progress: `PROGRESS`
- Cancellation: `CANCELLED`
- Completion: `COMPLETION_COMPLETE`
- Sampling: `SAMPLING_CREATE_MESSAGE`
- Roots: `ROOTS_LIST`
- Logging: `LOGGING_SET_LEVEL`
- Extensions: `PING`, `PONG`, `REQUEST`, `NOTIFICATION`

### 2.2 ProgressManager

```python
progress = ProgressManager()
token = progress.start_progress("operation_name", total=100)
await progress.update_progress(token, progress=50, status="Halfway done")
await progress.complete_progress(token, "completed")
```

**ProgressToken** is a `@dataclass` with `value` (string UUID), `operation_name`, `total`, `progress`, and `status`. It is hashable (by value).

**ProgressNotification** wraps progress updates for JSON-RPC transport: `{"method": "notifications/progress", "params": {"progressToken": ..., "progress": N, "total": N, "status": "..."}}`.

### 2.3 CancellationManager

```python
cancellation = CancellationManager()

# Cancel a request
await cancellation.cancel_request(request_id, reason="User cancelled")

# Check cancellation status
if await cancellation.is_cancelled(request_id):
    raise CancelledError("Operation cancelled")
```

**CancelledNotification:** `{"method": "notifications/cancelled", "params": {"requestId": "...", "reason": "..."}}`.

### 2.4 CompletionManager

```python
completion = CompletionManager()
results = await completion.get_completions(
    ref_type="prompts/analyze",
    argument_name="data_source",
    partial_value="fil",
)
```

Provides auto-complete suggestions for prompt arguments and resource URIs.

### 2.5 SamplingManager

Server-to-client sampling requests for LLM interactions:

```python
sampling = SamplingManager()
request = SamplingRequest(
    messages=[{"role": "user", "content": "..."}],
    model_preferences={"hints": [{"name": "claude-3-sonnet"}]},
    max_tokens=1000,
)
```

### 2.6 RootsManager

File system root management for MCP servers that need to declare which directories they can access.

### 2.7 ProtocolManager

Singleton that aggregates all protocol managers:

```python
protocol = get_protocol_manager()
protocol.progress      # ProgressManager
protocol.cancellation  # CancellationManager
protocol.completion    # CompletionManager
protocol.sampling      # SamplingManager
protocol.roots         # RootsManager
```

### 2.8 MetaData

Protocol-level metadata attached to messages:

```python
@dataclass
class MetaData:
    progress_token: Optional[ProgressToken]
    request_id: Optional[str]
    timestamp: Optional[float]        # Auto-set to current time
    operation_id: Optional[str]
    user_id: Optional[str]
    additional_data: Optional[Dict]
```

### 2.9 Convenience Functions

```python
start_progress(operation_name, total=None) -> ProgressToken
update_progress(token, progress=None, status=None)
complete_progress(token, final_status=None)
is_cancelled(request_id) -> bool
cancel_request(request_id, reason=None)
```

---

## 3. Error Handling

### 3.1 Error Hierarchy

```
MCPError (base)
  TransportError          -- Transport failures (retryable by default)
  AuthenticationError     -- Auth failures (not retryable)
  AuthorizationError      -- Permission failures (not retryable)
  RateLimitError          -- Rate limit exceeded (retryable, retry_after=60s)
  ToolError               -- Tool execution failures (retryable)
  ResourceError           -- Resource access failures (retryable)
  ServiceDiscoveryError   -- Discovery failures (retryable)
  ValidationError         -- Validation failures (not retryable)
```

### 3.2 MCPError

```python
MCPError(
    message: str,
    error_code: Union[MCPErrorCode, int] = MCPErrorCode.INTERNAL_ERROR,
    data: Optional[Dict] = None,
    retryable: bool = False,
    retry_after: Optional[float] = None,
    cause: Optional[Exception] = None,
)
```

**Methods:**

- `to_dict()` -- JSON-RPC error format: `{"code": int, "message": str, "data": dict}`.
- `is_retryable()` -- Whether the error should be retried.
- `get_retry_delay()` -- Suggested delay. Uses `retry_after` if set, otherwise default per error code: RATE_LIMITED=60s, SERVER_UNAVAILABLE=30s, TRANSPORT_ERROR=5s, TOOL_EXECUTION_FAILED=2s, EXTERNAL_SERVICE_ERROR=10s, default=1s.
- `get_severity()` -- "high" (auth, data integrity, protocol mismatch), "medium" (not found, validation, business logic), "low" (everything else).

### 3.3 MCPErrorCode

JSON-RPC standard codes:

- `PARSE_ERROR` (-32700), `INVALID_REQUEST` (-32600), `METHOD_NOT_FOUND` (-32601), `INVALID_PARAMS` (-32602), `INTERNAL_ERROR` (-32603)

MCP-specific codes (-32099 to -32000):

- `TRANSPORT_ERROR` (-32001), `AUTHENTICATION_FAILED` (-32002), `AUTHORIZATION_FAILED` (-32003), `RATE_LIMITED` (-32004), `TOOL_NOT_FOUND` (-32005), `TOOL_EXECUTION_FAILED` (-32006), `RESOURCE_NOT_FOUND` (-32007), `RESOURCE_ACCESS_FAILED` (-32008), `SERVER_UNAVAILABLE` (-32009), `PROTOCOL_VERSION_MISMATCH` (-32010), `CAPABILITY_NOT_SUPPORTED` (-32011), `SESSION_EXPIRED` (-32012), `CIRCUIT_BREAKER_OPEN` (-32013)

Application-specific codes (positive):

- `VALIDATION_ERROR` (1001), `BUSINESS_LOGIC_ERROR` (1002), `EXTERNAL_SERVICE_ERROR` (1003), `DATA_INTEGRITY_ERROR` (1004), `QUOTA_EXCEEDED` (1005), `REQUEST_TIMEOUT` (1006), `REQUEST_CANCELLED` (1007)

### 3.4 ExponentialBackoffRetry

```python
retry = ExponentialBackoffRetry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
)
```

**Contract:**

- `should_retry(error, attempt)` returns `True` if: attempt < max_attempts AND error is retryable AND severity is not "high".
- `get_delay(error, attempt)` computes `base_delay * (backoff_factor ^ (attempt-1))`, capped at `max_delay`. Uses error's `retry_after` if set. Jitter multiplies by random factor in [0.5, 1.0].

### 3.5 CircuitBreakerRetry

```python
cb = CircuitBreakerRetry(
    failure_threshold: int = 5,
    timeout: float = 60.0,
    success_threshold: int = 3,
)
```

Three states: `closed` (normal), `open` (rejecting), `half-open` (testing).

**State transitions:**

- `closed` -> `open`: When `failure_count >= failure_threshold`.
- `open` -> `half-open`: When `timeout` seconds pass since last failure.
- `half-open` -> `closed`: When `success_count >= success_threshold`.
- `half-open` -> `open`: On any failure.

**Methods:** `on_success()`, `on_failure(error)`.

### 3.6 RetryableOperation

```python
retry_op = RetryableOperation(strategy)
result = await retry_op.execute(func, *args, **kwargs)
```

Wraps any sync or async function with retry logic. Non-MCPError exceptions are converted to `MCPError(INTERNAL_ERROR, retryable=False)`.

### 3.7 ErrorAggregator

```python
aggregator = ErrorAggregator(max_errors=1000)
aggregator.record_error(error)
stats = aggregator.get_error_stats(time_window=3600)
trends = aggregator.get_error_trends(bucket_size=300)
```

**Stats output:** `{total_errors, error_rate, error_codes, severity_levels, most_common_error, retryable_errors, time_window}`.

**Trends output:** List of time buckets, each with `{start_time, end_time, error_count, error_codes}`.

---

## 4. Utilities

### 4.1 CacheManager

Manages named caches with configurable backends:

```python
cache_mgr = CacheManager(
    enabled=True,
    default_ttl=300,
    backend="memory",       # or "redis"
    config={"redis_url": "redis://localhost:6379", "prefix": "mcp:"},
)
cache = cache_mgr.get_cache("search_results", ttl=600)
```

Features:

- Memory-backed `LRUCache` with TTL and max size.
- Redis-backed cache (optional, requires Redis).
- Stampede prevention via `get_or_compute()` for async tools.
- Per-cache statistics: hit rate, miss rate, evictions.

### 4.2 ConfigManager

Hierarchical configuration with dot-notation access:

```python
config = ConfigManager("config.json")
config.get("cache.default_ttl", default=300)
config.update({"server": {"name": "my-server"}})
config.to_dict()
```

### 4.3 MetricsCollector

```python
metrics = MetricsCollector(
    enabled=True,
    collect_performance=True,
    collect_usage=True,
)
metrics.track_tool_call(tool_name, latency, success, error_type=None)
wrapped_fn = metrics.track_tool("tool_name")(fn)
metrics.export_metrics()
```

### 4.4 Response Formatters

```python
formatted = format_response(data, format="markdown")
```

Formats: `json` (pretty-printed), `markdown` (tables, headers), `table` (ASCII), `search` (search-result format).

---

## 5. OAuth Edge Cases

- **PKCE:** Supports `S256` (SHA-256) and `plain` challenge methods. Unknown methods return `False` from `validate_pkce()`.
- **Authorization code expiry:** Default 10 minutes.
- **Access token expiry:** Default 1 hour.
- **In-memory stores:** Not suitable for production multi-process deployments. Use external stores (implement `ClientStore`/`TokenStore` abstract classes).
