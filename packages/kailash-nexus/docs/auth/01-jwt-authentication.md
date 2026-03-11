# JWT Authentication

The JWT middleware provides secure token-based authentication with multi-source extraction, multi-algorithm support, and algorithm confusion attack prevention.

## Quick Start

```python
from nexus import Nexus
from nexus.auth import JWTConfig, JWTMiddleware

app = Nexus()

# Option 1: Using JWTConfig
config = JWTConfig(
    secret="your-256-bit-secret-key-minimum-32-chars",
    algorithm="HS256",
)
app.add_middleware(JWTMiddleware, config=config)

# Option 2: Using NexusAuthPlugin (recommended)
from nexus.auth import NexusAuthPlugin

auth = NexusAuthPlugin(jwt=config)
app.add_plugin(auth)
```

## JWTConfig Reference

```python
from dataclasses import dataclass, field
from typing import List, Optional, Union

@dataclass
class JWTConfig:
    # Secret key for HS* algorithms (required for HS256/384/512)
    secret: Optional[str] = None

    # JWT algorithm (default: HS256)
    algorithm: str = "HS256"

    # Public key for RS*/ES* algorithms (required for asymmetric)
    public_key: Optional[str] = None

    # Private key for token signing (optional, for token creation)
    private_key: Optional[str] = None

    # Expected token issuer (optional validation)
    issuer: Optional[str] = None

    # Expected token audience (optional validation)
    audience: Optional[Union[str, List[str]]] = None

    # Header name for Bearer token (default: Authorization)
    token_header: str = "Authorization"

    # Cookie name for token (optional)
    token_cookie: Optional[str] = None

    # Query parameter for token (optional, for WebSocket)
    token_query_param: Optional[str] = None

    # Paths exempt from authentication
    exempt_paths: List[str] = field(default_factory=lambda: [
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/auth/login",
        "/auth/refresh",
        "/auth/sso/*",
    ])

    # URL for JWKS endpoint (for SSO providers)
    jwks_url: Optional[str] = None

    # JWKS cache TTL in seconds (default: 3600)
    jwks_cache_ttl: int = 3600

    # Verify token expiration (default: True)
    verify_exp: bool = True

    # Leeway in seconds for exp/nbf claims (default: 0)
    leeway: int = 0
```

## Configuration Examples

### Symmetric Algorithm (HS256)

The most common setup for single-service applications:

```python
config = JWTConfig(
    secret="your-256-bit-secret-key-minimum-32-characters-long",
    algorithm="HS256",
    issuer="https://myapp.com",
    audience="myapp-api",
    exempt_paths=["/health", "/auth/login", "/public/*"],
)
```

### Asymmetric Algorithm (RS256)

For microservices where the auth service signs tokens and other services verify:

```python
# Token verification service (public key only)
config = JWTConfig(
    algorithm="RS256",
    public_key="""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----""",
    issuer="https://auth.myapp.com",
)

# Auth service (needs private key for signing)
auth_service_config = JWTConfig(
    algorithm="RS256",
    public_key="...",
    private_key="""-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----""",
)
```

### JWKS Support (SSO Integration)

For integrating with external identity providers:

```python
# Azure AD
config = JWTConfig(
    algorithm="RS256",
    jwks_url="https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
    issuer="https://login.microsoftonline.com/{tenant}/v2.0",
    audience="your-client-id",
)

# Google
config = JWTConfig(
    algorithm="RS256",
    jwks_url="https://www.googleapis.com/oauth2/v3/certs",
    issuer=["https://accounts.google.com", "accounts.google.com"],
)
```

### Cookie-Based Authentication

For browser-based applications with HttpOnly cookies:

```python
config = JWTConfig(
    secret=os.environ["JWT_SECRET"],  # min 32 chars
    token_cookie="access_token",  # Read token from this cookie
    exempt_paths=["/auth/login", "/auth/refresh"],
)
```

### WebSocket Authentication

For WebSocket connections that pass tokens via query parameter:

```python
config = JWTConfig(
    secret=os.environ["JWT_SECRET"],  # min 32 chars
    token_query_param="token",  # ws://host/path?token=xyz
)
```

## Token Extraction Priority

The middleware extracts tokens in this order:

1. **Authorization Header** (Bearer token)

   ```
   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

2. **Cookie** (if `token_cookie` configured)

   ```
   Cookie: access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

3. **Query Parameter** (if `token_query_param` configured)
   ```
   GET /ws?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

## Path Exemption

Exempt paths support exact matching and wildcards:

```python
exempt_paths=[
    "/health",           # Exact match: /health only
    "/auth/sso/*",       # Wildcard: /auth/sso/azure, /auth/sso/google, etc.
    "/public/*",         # Wildcard: /public/images, /public/docs/api, etc.
]
```

The wildcard `/*` matches any path segment including nested paths.

## Algorithm Confusion Prevention

The middleware includes built-in protection against algorithm confusion attacks:

1. **Rejects 'none' algorithm**: Tokens with `alg: none` are rejected
2. **Algorithm verification**: Token algorithm must match configured algorithm
3. **Strict key type enforcement**: Uses appropriate key type for algorithm

```python
# These attacks are automatically prevented:

# Attack 1: alg=none (no signature verification)
# Header: {"alg": "none", "typ": "JWT"}
# Result: InvalidTokenError("Algorithm 'none' is not permitted")

# Attack 2: Algorithm downgrade (RS256 -> HS256 using public key as secret)
# Config: algorithm="RS256", public_key="..."
# Token: {"alg": "HS256", ...}
# Result: InvalidTokenError("Token algorithm 'HS256' does not match configured algorithm 'RS256'")
```

## Token Creation

The middleware can also create tokens (useful for login endpoints):

### Access Tokens

```python
from nexus.auth import JWTMiddleware, JWTConfig

config = JWTConfig(secret=os.environ["JWT_SECRET"])  # min 32 chars
jwt = JWTMiddleware(app, config=config)

# Create access token
token = jwt.create_access_token(
    user_id="user-123",
    email="user@example.com",
    roles=["user", "editor"],
    permissions=["read:articles", "write:articles"],
    tenant_id="tenant-456",
    expires_minutes=30,
    # Additional custom claims
    department="engineering",
)
```

### Refresh Tokens

```python
refresh_token = jwt.create_refresh_token(
    user_id="user-123",
    tenant_id="tenant-456",
    expires_days=7,
)
```

## AuthenticatedUser

After successful authentication, `request.state.user` contains an `AuthenticatedUser` instance:

```python
from fastapi import Request, Depends
from nexus.auth import AuthenticatedUser
from nexus.auth.dependencies import get_current_user

@app.get("/profile")
async def get_profile(user: AuthenticatedUser = Depends(get_current_user)):
    return {
        "user_id": user.user_id,
        "email": user.email,
        "roles": user.roles,
        "permissions": user.permissions,
        "tenant_id": user.tenant_id,
        "provider": user.provider,  # "local", "azure", "google", etc.
        "is_admin": user.is_admin,
        "display_name": user.display_name,
    }
```

### AuthenticatedUser Methods

```python
# Role checks
user.has_role("admin")                    # True if user has "admin" role
user.has_any_role("admin", "moderator")   # True if user has any of these roles

# Permission checks (with wildcard support)
user.has_permission("read:articles")      # Exact match
user.has_permission("write:users")        # Also matches "write:*" or "*"
user.has_any_permission("read:*", "admin:*")  # Any of these

# Access raw JWT claims
user.get_claim("custom_field")            # Access custom claims
user.raw_claims                           # Full JWT payload

# Convenience properties
user.is_admin                             # True if "admin", "super_admin", or "administrator"
user.display_name                         # name, preferred_username, email, or user_id
```

## JWT Claim Normalization

The middleware normalizes different JWT claim formats into `AuthenticatedUser`:

| AuthenticatedUser | JWT Claims Checked                    |
| ----------------- | ------------------------------------- |
| `user_id`         | `sub`, `user_id`, `uid`               |
| `email`           | `email`, `preferred_username`         |
| `roles`           | `roles`, `role`                       |
| `permissions`     | `permissions`, `scope`                |
| `tenant_id`       | `tenant_id`, `tid`, `organization_id` |
| `provider`        | Determined from `iss` claim           |

## Provider Detection

The middleware automatically detects auth providers from the `iss` claim:

| Issuer Contains             | Provider |
| --------------------------- | -------- |
| `login.microsoftonline.com` | `azure`  |
| `accounts.google.com`       | `google` |
| `appleid.apple.com`         | `apple`  |
| `github.com`                | `github` |
| Other                       | `local`  |

## Error Responses

### Missing Token (401)

```json
{
  "detail": "Not authenticated",
  "error": "missing_token"
}
```

Headers: `WWW-Authenticate: Bearer realm="api"`

### Expired Token (401)

```json
{
  "detail": "Token has expired",
  "error": "token_expired"
}
```

Headers: `WWW-Authenticate: Bearer realm="api", error="invalid_token"`

### Invalid Token (401)

```json
{
  "detail": "Invalid token: Signature verification failed",
  "error": "invalid_token"
}
```

## Supported Algorithms

| Algorithm | Type       | Key Required                 |
| --------- | ---------- | ---------------------------- |
| HS256     | Symmetric  | `secret`                     |
| HS384     | Symmetric  | `secret`                     |
| HS512     | Symmetric  | `secret`                     |
| RS256     | Asymmetric | `public_key` (or `jwks_url`) |
| RS384     | Asymmetric | `public_key` (or `jwks_url`) |
| RS512     | Asymmetric | `public_key` (or `jwks_url`) |
| ES256     | Asymmetric | `public_key` (or `jwks_url`) |
| ES384     | Asymmetric | `public_key` (or `jwks_url`) |
| ES512     | Asymmetric | `public_key` (or `jwks_url`) |

## Best Practices

1. **Use strong secrets**: For HS256, use at least 256 bits (32 characters) of random data
2. **Prefer RS256 for microservices**: Allows verification without sharing signing key
3. **Set issuer and audience**: Prevents token reuse across applications
4. **Keep access tokens short-lived**: 15-30 minutes is recommended
5. **Use refresh tokens**: For seamless user experience with short access tokens
6. **Enable HTTPS only**: Never transmit tokens over HTTP in production
7. **Use HttpOnly cookies**: For browser apps, prevents XSS token theft
