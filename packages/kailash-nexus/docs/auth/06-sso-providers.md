# SSO Providers

OAuth2/OIDC integration with Azure AD, Google, Apple, and GitHub for enterprise single sign-on.

## Overview

The SSO module provides:

- Pre-built providers for major identity platforms
- Standardized user info extraction
- CSRF protection with state parameter
- JWKS-based token validation
- Helper functions for OAuth2 flows

## Available Providers

| Provider | Protocol      | ID Token | Algorithms |
| -------- | ------------- | -------- | ---------- |
| Azure AD | OAuth2 + OIDC | Yes      | RS256      |
| Google   | OAuth2 + OIDC | Yes      | RS256      |
| Apple    | OAuth2 + OIDC | Yes      | ES256      |
| GitHub   | OAuth2 only   | No       | N/A        |

## Quick Start

```python
from nexus.auth.sso import (
    AzureADProvider,
    GoogleProvider,
    AppleProvider,
    GitHubProvider,
    initiate_sso_login,
    handle_sso_callback,
)

# Create provider instances
azure = AzureADProvider(
    tenant_id="your-tenant-id",
    client_id="your-client-id",
    client_secret="your-client-secret",
)

google = GoogleProvider(
    client_id="your-client-id.apps.googleusercontent.com",
    client_secret="your-client-secret",
)

# Routes for SSO flow
@app.get("/auth/sso/azure/login")
async def azure_login():
    return await initiate_sso_login(
        provider=azure,
        callback_base_url="https://myapp.com",
    )

@app.get("/auth/sso/azure/callback")
async def azure_callback(code: str, state: str):
    result = await handle_sso_callback(
        provider=azure,
        code=code,
        state=state,
        auth_plugin=auth,
        callback_base_url="https://myapp.com",
    )
    return result  # Contains access_token, refresh_token, user info
```

## Azure AD Provider

For Microsoft Entra ID (formerly Azure Active Directory).

### Configuration

```python
from nexus.auth.sso import AzureADProvider

# Single-tenant app
azure = AzureADProvider(
    tenant_id="your-tenant-id",
    client_id="your-client-id",
    client_secret="your-client-secret",
    scopes=["openid", "profile", "email", "User.Read"],
)

# Multi-tenant app
azure = AzureADProvider(
    tenant_id="common",  # or "organizations" or "consumers"
    client_id="your-client-id",
    client_secret="your-client-secret",
    allowed_tenants=["tenant-id-1", "tenant-id-2"],  # Optional restriction
)
```

### Parameters

| Parameter         | Required | Description                                                |
| ----------------- | -------- | ---------------------------------------------------------- |
| `tenant_id`       | Yes      | Azure AD tenant ID or "common"/"organizations"/"consumers" |
| `client_id`       | Yes      | Application (client) ID from Azure portal                  |
| `client_secret`   | Yes      | Client secret from Azure portal                            |
| `scopes`          | No       | OAuth2 scopes (default: openid, profile, email, User.Read) |
| `allowed_tenants` | No       | For multi-tenant: list of allowed tenant IDs               |
| `timeout`         | No       | HTTP request timeout in seconds (default: 30)              |

### Endpoints Used

- Authorization: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize`
- Token: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
- JWKS: `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`
- User Info: `https://graph.microsoft.com/v1.0/me`

### Authorization URL Options

```python
auth_url = azure.get_authorization_url(
    state="csrf-state",
    redirect_uri="https://myapp.com/auth/sso/azure/callback",
    prompt="select_account",  # none, login, consent, select_account
    login_hint="user@example.com",  # Pre-fill email
    domain_hint="contoso.com",  # Force specific domain
)
```

### Logout

```python
logout_url = azure.get_logout_url(
    post_logout_redirect_uri="https://myapp.com/logged-out",
)
```

## Google Provider

For Google Workspace and consumer accounts.

### Configuration

```python
from nexus.auth.sso import GoogleProvider

google = GoogleProvider(
    client_id="your-client-id.apps.googleusercontent.com",
    client_secret="your-client-secret",
    scopes=["openid", "profile", "email"],
)
```

### Parameters

| Parameter       | Required | Description                                     |
| --------------- | -------- | ----------------------------------------------- |
| `client_id`     | Yes      | OAuth client ID from Google Cloud Console       |
| `client_secret` | Yes      | OAuth client secret                             |
| `scopes`        | No       | OAuth2 scopes (default: openid, profile, email) |
| `timeout`       | No       | HTTP request timeout in seconds (default: 30)   |

### Endpoints Used

- Authorization: `https://accounts.google.com/o/oauth2/v2/auth`
- Token: `https://oauth2.googleapis.com/token`
- JWKS: `https://www.googleapis.com/oauth2/v3/certs`
- User Info: `https://www.googleapis.com/oauth2/v3/userinfo`

### Authorization URL Options

```python
auth_url = google.get_authorization_url(
    state="csrf-state",
    redirect_uri="https://myapp.com/auth/sso/google/callback",
    access_type="offline",  # "online" or "offline" (for refresh token)
    prompt="consent",  # "none", "consent", "select_account"
    hd="example.com",  # Restrict to Google Workspace domain
    login_hint="user@example.com",
)
```

## Apple Provider

For Sign in with Apple.

### Configuration

```python
from nexus.auth.sso import AppleProvider

apple = AppleProvider(
    team_id="YOUR_TEAM_ID",
    client_id="com.yourapp.service",
    key_id="YOUR_KEY_ID",
    private_key_path="/path/to/AuthKey.p8",  # OR use private_key=
)
```

### Parameters

| Parameter          | Required | Description                                   |
| ------------------ | -------- | --------------------------------------------- |
| `team_id`          | Yes      | Apple Developer Team ID                       |
| `client_id`        | Yes      | Service ID (e.g., "com.yourapp.service")      |
| `key_id`           | Yes      | Key ID from Apple Developer console           |
| `private_key`      | One of   | Private key content (PEM format)              |
| `private_key_path` | One of   | Path to private key file (.p8)                |
| `scopes`           | No       | OAuth2 scopes (default: name, email)          |
| `timeout`          | No       | HTTP request timeout in seconds (default: 30) |

### Important Notes

1. **Name only on first auth**: Apple only sends the user's name on the FIRST authorization. Store it immediately.

2. **Email relay**: Users may hide their real email. You'll receive `abc123@privaterelay.appleid.com`.

3. **ES256 algorithm**: Apple uses ECDSA, not RSA.

4. **Client secret is JWT**: The provider automatically generates a signed JWT as the client secret.

### Handling User Data

```python
@app.post("/auth/sso/apple/callback")
async def apple_callback(
    code: str,
    state: str,
    user: Optional[str] = Form(None),  # JSON with name on first auth
):
    user_data = json.loads(user) if user else None

    tokens = await apple.exchange_code(code, redirect_uri)
    claims = apple.validate_id_token(
        tokens.id_token,
        user_data=user_data,  # Pass user data for name extraction
    )

    # On first auth:
    # claims["name"] = "John Doe"
    # claims["given_name"] = "John"
    # claims["family_name"] = "Doe"

    # Store the name now - you won't get it again!
    if "name" in claims:
        await store_user_name(claims["sub"], claims["name"])
```

## GitHub Provider

For GitHub OAuth (no OIDC).

### Configuration

```python
from nexus.auth.sso import GitHubProvider

github = GitHubProvider(
    client_id="your-client-id",
    client_secret="your-client-secret",
    scopes=["user:email"],
)
```

### Parameters

| Parameter       | Required | Description                                   |
| --------------- | -------- | --------------------------------------------- |
| `client_id`     | Yes      | OAuth App client ID                           |
| `client_secret` | Yes      | OAuth App client secret                       |
| `scopes`        | No       | OAuth2 scopes (default: user:email)           |
| `timeout`       | No       | HTTP request timeout in seconds (default: 30) |

### Important Notes

1. **No ID token**: GitHub doesn't support OIDC. User info comes from the API.

2. **Tokens don't expire**: GitHub access tokens are permanent until revoked.

3. **Email requires scope**: The `user:email` scope is needed to get the user's email.

### Getting User Info

```python
# Exchange code for token
tokens = await github.exchange_code(code, redirect_uri)

# Must use get_user_info (no ID token)
user_info = await github.get_user_info(tokens.access_token)

# user_info.provider_user_id = GitHub user ID
# user_info.email = Primary verified email
# user_info.name = Display name
# user_info.picture = Avatar URL
```

## SSOProvider Protocol

All providers implement this interface:

```python
from typing import Protocol

class SSOProvider(Protocol):
    @property
    def name(self) -> str:
        """Provider name (used in routes)."""
        ...

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate authorization URL."""
        ...

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens."""
        ...

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user information using access token."""
        ...

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """Validate and decode ID token."""
        ...
```

## Custom Provider

Implement a custom SSO provider:

```python
from nexus.auth.sso.base import (
    BaseSSOProvider,
    SSOTokenResponse,
    SSOUserInfo,
    SSOAuthError,
)

class CustomProvider(BaseSSOProvider):
    name = "custom"

    def __init__(self, client_id: str, client_secret: str):
        super().__init__(client_id, client_secret)

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        **kwargs,
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope or "openid profile email",
            "response_type": "code",
        }
        return f"https://auth.custom.com/authorize?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        response = await self._post_form("https://auth.custom.com/token", data)
        return SSOTokenResponse(
            access_token=response["access_token"],
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        data = await self._get_json("https://api.custom.com/userinfo", headers)
        return SSOUserInfo(
            provider_user_id=data["sub"],
            email=data.get("email"),
            name=data.get("name"),
        )

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        # Implement JWT validation
        ...
```

## Helper Functions

### initiate_sso_login

Starts the OAuth2 flow:

```python
from nexus.auth.sso import initiate_sso_login

@app.get("/auth/sso/{provider}/login")
async def sso_login(provider: str):
    provider_instance = get_provider(provider)
    return await initiate_sso_login(
        provider=provider_instance,
        callback_base_url="https://myapp.com",
        # Additional params passed to get_authorization_url
        prompt="select_account",
    )
```

### handle_sso_callback

Completes the OAuth2 flow and issues JWT:

```python
from nexus.auth.sso import handle_sso_callback

@app.get("/auth/sso/{provider}/callback")
async def sso_callback(provider: str, code: str, state: str):
    result = await handle_sso_callback(
        provider=get_provider(provider),
        code=code,
        state=state,
        auth_plugin=auth,
        callback_base_url="https://myapp.com",
    )
    # Returns:
    # {
    #     "access_token": "...",
    #     "refresh_token": "...",
    #     "token_type": "bearer",
    #     "user": {
    #         "id": "provider:user-id",
    #         "email": "user@example.com",
    #         "name": "John Doe",
    #         "provider": "azure",
    #     },
    # }
    return result
```

## CSRF Protection

The module includes built-in CSRF protection using the `state` parameter:

```python
# State is automatically:
# 1. Generated with secrets.token_urlsafe(32)
# 2. Stored with timestamp in memory
# 3. Validated on callback
# 4. Expires after 10 minutes

# If state is invalid or expired:
# InvalidStateError: Invalid or expired SSO state - possible CSRF attack
```

For production, use Redis for state storage:

```python
# Custom state management for distributed deployments
import redis

redis_client = redis.Redis()

async def custom_state_manager():
    # Store state in Redis instead of memory
    ...
```

## Complete Example

```python
from fastapi import FastAPI, Query
from fastapi.responses import RedirectResponse
from nexus.auth import NexusAuthPlugin, JWTConfig
from nexus.auth.sso import (
    AzureADProvider,
    GoogleProvider,
    initiate_sso_login,
    handle_sso_callback,
    InvalidStateError,
    SSOAuthError,
)

app = FastAPI()

# Configure auth
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
)
auth.install(app)

# Initialize providers
providers = {
    "azure": AzureADProvider(
        tenant_id="your-tenant",
        client_id="your-client-id",
        client_secret="your-client-secret",
    ),
    "google": GoogleProvider(
        client_id="your-client-id.apps.googleusercontent.com",
        client_secret="your-client-secret",
    ),
}

@app.get("/auth/sso/{provider}/login")
async def sso_login(provider: str):
    """Initiate SSO login."""
    if provider not in providers:
        return {"error": f"Unknown provider: {provider}"}

    return await initiate_sso_login(
        provider=providers[provider],
        callback_base_url="https://myapp.com",
    )

@app.get("/auth/sso/{provider}/callback")
async def sso_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle SSO callback."""
    if provider not in providers:
        return {"error": f"Unknown provider: {provider}"}

    try:
        result = await handle_sso_callback(
            provider=providers[provider],
            code=code,
            state=state,
            auth_plugin=auth,
            callback_base_url="https://myapp.com",
        )
        # Redirect to frontend with tokens
        return RedirectResponse(
            f"/login-success?token={result['access_token']}"
        )
    except InvalidStateError:
        return RedirectResponse("/login?error=invalid_state")
    except SSOAuthError as e:
        return RedirectResponse(f"/login?error={e}")
```

## Best Practices

1. **Use HTTPS everywhere**: OAuth2 requires secure connections
2. **Store client secrets securely**: Use environment variables or secret managers
3. **Validate state parameter**: Built-in, but ensure not bypassed
4. **Handle provider-specific quirks**: Apple name, GitHub no ID token
5. **Implement token refresh**: Access tokens expire
6. **Log SSO events**: Track successful/failed logins
7. **Use Redis for state in production**: Memory store doesn't work with multiple instances
8. **Map provider IDs to internal IDs**: `azure:user-123` -> internal user record
