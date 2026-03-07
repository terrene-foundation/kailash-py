# JWT Authentication Migration Guide

## Overview

The JWT authentication implementation in Kailash SDK has been consolidated to resolve circular import issues and improve the architecture. The `KailashJWTAuthManager` has been merged into `JWTAuthManager` with support for both HS256 (default) and RSA algorithms.

> **For SDK Users**: This guide focuses on how to update your code to use the new consolidated authentication. For internal architecture details, see the SDK contributor documentation.

## Key Changes

### 1. Consolidated JWT Implementation

**Before:**
- Two separate implementations: `JWTAuthManager` and `KailashJWTAuthManager`
- `KailashJWTAuthManager` used Kailash nodes (causing circular imports)
- Different APIs and features

**After:**
- Single `JWTAuthManager` with all features
- No circular dependencies
- Consistent API with both HS256 and RSA support

### 2. Dependency Injection Pattern

**Before:**
```python
# Direct import causing circular dependency
from kailash.middleware.auth import KailashJWTAuthManager

class APIGateway:
    def __init__(self):
        self.auth_manager = KailashJWTAuthManager()
```

**After:**
```python
# Dependency injection pattern
class APIGateway:
    def __init__(self, auth_manager=None):
        if auth_manager is None and self.enable_auth:
            from ..auth import JWTAuthManager
            self.auth_manager = JWTAuthManager()
        else:
            self.auth_manager = auth_manager

# Usage
auth = JWTAuthManager(secret_key="my-secret")
gateway = create_gateway(auth_manager=auth)
```

### 3. Module Structure

**New structure:**
```
kailash/middleware/auth/
├── __init__.py          # Main exports
├── jwt_auth.py          # Consolidated JWTAuthManager
├── models.py            # Data models (no circular deps)
├── exceptions.py        # Auth exceptions
├── utils.py            # Helper functions
└── access_control.py    # RBAC/ABAC (uses dependency injection)
```

## Migration Steps

### Step 1: Update Imports

**Before:**
```python
from kailash.middleware.auth.kailash_jwt_auth import KailashJWTAuthManager
from kailash.middleware.auth.jwt_auth import JWTAuthManager
```

**After:**
```python
from kailash.middleware.auth import JWTAuthManager
```

### Step 2: Update Instantiation

**Before:**
```python
# Using KailashJWTAuthManager
auth = KailashJWTAuthManager(secret_key="my-secret")

# Using old JWTAuthManager
auth = JWTAuthManager(use_rsa=True)
```

**After:**
```python
# HS256 (default)
auth = JWTAuthManager(secret_key="my-secret")

# RSA
auth = JWTAuthManager(use_rsa=True)
# or
auth = JWTAuthManager(algorithm="RS256")
```

### Step 3: Update Method Calls

The new `JWTAuthManager` maintains backward compatibility with deprecation warnings:

**Deprecated methods (will be removed in v1.0.0):**
```python
# Old KailashJWTAuthManager methods
token = auth.generate_token(user_id)  # Use create_access_token()
payload = auth.verify_and_decode_token(token)  # Use verify_token()
refresh = auth.generate_refresh_token(user_id)  # Use create_refresh_token()
```

**New methods (preferred):**
```python
# Create tokens
token = auth.create_access_token(user_id, permissions=["read", "write"])
refresh = auth.create_refresh_token(user_id)
pair = auth.create_token_pair(user_id, tenant_id="tenant-123")

# Verify tokens
payload = auth.verify_token(token)

# Refresh tokens
new_pair = auth.refresh_access_token(refresh_token)
```

### Step 4: Update Gateway Creation

**Before:**
```python
gateway = APIGateway()
# Auth was created internally, causing circular imports
```

**After:**
```python
# Option 1: Let gateway create default auth
gateway = create_gateway(title="My API")

# Option 2: Provide custom auth
auth = JWTAuthManager(
    secret_key="my-secret",
    algorithm="HS256",
    issuer="my-app"
)
gateway = create_gateway(
    title="My API",
    auth_manager=auth
)
```

## New Features

### 1. Unified Configuration

```python
from kailash.middleware.auth import JWTConfig

config = JWTConfig(
    secret_key="my-secret",
    algorithm="HS256",  # or "RS256"
    use_rsa=False,
    access_token_expire_minutes=15,
    refresh_token_expire_days=7,
    enable_blacklist=True,
    issuer="my-app",
    audience="my-api"
)

auth = JWTAuthManager(config=config)
```

### 2. RSA Support

```python
# Auto-generate RSA keys
auth = JWTAuthManager(use_rsa=True, auto_generate_keys=True)

# Use existing RSA keys
auth = JWTAuthManager(
    use_rsa=True,
    private_key=private_key_pem,
    public_key=public_key_pem
)

# Get public key for external verification
jwks = auth.get_public_key_jwks()
```

### 3. Enhanced Token Management

```python
# Token with claims
token = auth.create_access_token(
    user_id="user-123",
    tenant_id="tenant-456",
    permissions=["read", "write"],
    roles=["admin"],
    custom_claim="value"
)

# Token pair with automatic refresh tracking
pair = auth.create_token_pair(user_id="user-123")
print(f"Access token expires in: {pair.expires_in} seconds")
print(f"Expires at: {pair.expires_at}")

# Revoke tokens
auth.revoke_token(token)
auth.revoke_all_user_tokens("user-123")

# Cleanup expired tokens
auth.cleanup_expired_tokens()
```

## Testing

Run the circular import test to verify your migration:

```bash
python tests/middleware/test_circular_imports.py
```

Expected output:
```
✅ All circular import tests passed!
🎉 Auth refactoring successfully resolved circular dependencies
```

## Removed Components

The following components have been removed:

1. `kailash_jwt_auth.py` file
2. `JWTConfigNode` - No longer needed
3. `TokenGeneratorNode` - Functionality integrated
4. `TokenVerifierNode` - Functionality integrated
5. `RefreshTokenNode` - Functionality integrated

## Troubleshooting

### Import Errors

If you see:
```
ImportError: cannot import name 'KailashJWTAuthManager'
```

Update your import to:
```python
from kailash.middleware.auth import JWTAuthManager
```

### Circular Import Errors

If you encounter circular imports:
1. Use dependency injection pattern
2. Import at usage point, not module level
3. Check that you're not importing from `kailash_jwt_auth.py`

### Method Not Found

If you see:
```
AttributeError: 'JWTAuthManager' object has no attribute 'generate_token'
```

The method exists but is deprecated. You'll see a deprecation warning. Update to use `create_access_token()` instead.

## Support

For questions or issues with the migration:
1. Check the [ADR-0048](../adr/0048-auth-consolidation-circular-import-fix.md)
2. Review the test file: `tests/middleware/test_circular_imports.py`
3. Open an issue on GitHub with the `auth-migration` label
