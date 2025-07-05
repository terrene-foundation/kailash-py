# MCP Security Best Practices

## Overview

Security is paramount when deploying MCP (Model Context Protocol) servers that interact with AI systems and external tools. This guide provides comprehensive security best practices, implementation strategies, and compliance considerations for MCP deployments.

## Table of Contents

1. [Security Architecture](#security-architecture)
2. [Authentication](#authentication)
3. [Authorization](#authorization)
4. [Network Security](#network-security)
5. [Data Protection](#data-protection)
6. [Secret Management](#secret-management)
7. [Input Validation](#input-validation)
8. [Audit and Compliance](#audit-and-compliance)
9. [Security Monitoring](#security-monitoring)
10. [Incident Response](#incident-response)

## Security Architecture

### Defense in Depth

```
┌─────────────────────────────────────────┐
│          WAF / DDoS Protection          │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│            API Gateway                  │
│     (Rate Limiting, API Keys)          │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│          Load Balancer                  │
│         (SSL Termination)               │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│           MCP Server                    │
│    (Auth, Input Validation)            │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         Tool Execution                  │
│    (Sandboxing, Permissions)           │
└─────────────────────────────────────────┘
```

### Security Principles

1. **Least Privilege**: Grant minimum necessary permissions
2. **Zero Trust**: Verify everything, trust nothing
3. **Defense in Depth**: Multiple layers of security
4. **Fail Secure**: Default to secure state on failure
5. **Separation of Concerns**: Isolate components

## Authentication

### JWT Implementation

```python
# security/authentication.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets

class JWTAuthentication:
    """JWT-based authentication for MCP"""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.security = HTTPBearer()

    def create_access_token(self,
                          subject: str,
                          expires_delta: Optional[timedelta] = None,
                          additional_claims: Dict[str, Any] = None) -> str:
        """Create JWT access token"""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)

        to_encode = {
            "sub": subject,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": secrets.token_urlsafe(16),  # JWT ID for revocation
            **(additional_claims or {})
        }

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Check if token is revoked
            if self.is_token_revoked(payload.get("jti")):
                raise HTTPException(status_code=401, detail="Token has been revoked")

            return payload

        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    async def get_current_user(self,
                              credentials: HTTPAuthorizationCredentials = Security(HTTPBearer())):
        """Get current user from token"""
        token = credentials.credentials
        payload = self.verify_token(token)

        user = await self.get_user(payload["sub"])
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        return user

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return self.pwd_context.verify(plain_password, hashed_password)
```

### OAuth2 Integration

```python
# security/oauth2.py
from authlib.integrations.starlette_client import OAuth
from fastapi import Request
import httpx

class OAuth2Provider:
    """OAuth2 integration for MCP"""

    def __init__(self, providers: Dict[str, Dict[str, str]]):
        self.oauth = OAuth()
        self._register_providers(providers)

    def _register_providers(self, providers: Dict[str, Dict[str, str]]):
        """Register OAuth2 providers"""
        for name, config in providers.items():
            self.oauth.register(
                name=name,
                client_id=config['client_id'],
                client_secret=config['client_secret'],
                authorize_url=config['authorize_url'],
                access_token_url=config['token_url'],
                client_kwargs={'scope': config.get('scope', 'openid profile email')}
            )

    async def login(self, provider: str, request: Request):
        """Initiate OAuth2 login"""
        client = self.oauth.create_client(provider)
        redirect_uri = request.url_for('auth_callback', provider=provider)
        return await client.authorize_redirect(request, redirect_uri)

    async def callback(self, provider: str, request: Request):
        """Handle OAuth2 callback"""
        client = self.oauth.create_client(provider)
        token = await client.authorize_access_token(request)

        # Get user info
        user_info = await self._get_user_info(provider, token)

        # Create internal token
        access_token = self.create_access_token(
            subject=user_info['email'],
            additional_claims={
                'provider': provider,
                'external_id': user_info.get('id')
            }
        )

        return {"access_token": access_token, "token_type": "bearer"}

    async def _get_user_info(self, provider: str, token: Dict) -> Dict:
        """Get user info from OAuth2 provider"""
        async with httpx.AsyncClient() as client:
            if provider == "google":
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token['access_token']}"}
                )
            elif provider == "github":
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {token['access_token']}"}
                )
            # Add more providers as needed

        return resp.json()
```

### Multi-Factor Authentication

```python
# security/mfa.py
import pyotp
import qrcode
import io
import base64

class MFAManager:
    """Multi-factor authentication manager"""

    def __init__(self, issuer: str = "MCP Server"):
        self.issuer = issuer

    def generate_secret(self) -> str:
        """Generate TOTP secret"""
        return pyotp.random_base32()

    def generate_qr_code(self, user_email: str, secret: str) -> str:
        """Generate QR code for TOTP setup"""
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user_email,
            issuer_name=self.issuer
        )

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')

        return base64.b64encode(buf.getvalue()).decode()

    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        """Verify TOTP token"""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=window)

    def generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate backup codes"""
        return [secrets.token_hex(4) for _ in range(count)]
```

## Authorization

### Role-Based Access Control (RBAC)

```python
# security/rbac.py
from enum import Enum
from typing import List, Dict, Set
from functools import wraps

class Role(Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    SERVICE = "service"

class Permission(Enum):
    # Tool permissions
    TOOL_LIST = "tool:list"
    TOOL_EXECUTE = "tool:execute"
    TOOL_CREATE = "tool:create"
    TOOL_DELETE = "tool:delete"

    # Resource permissions
    RESOURCE_READ = "resource:read"
    RESOURCE_WRITE = "resource:write"

    # Admin permissions
    USER_MANAGE = "user:manage"
    SYSTEM_CONFIG = "system:config"

class RBACManager:
    """Role-based access control manager"""

    def __init__(self):
        self.role_permissions: Dict[Role, Set[Permission]] = {
            Role.ADMIN: set(Permission),  # All permissions
            Role.USER: {
                Permission.TOOL_LIST,
                Permission.TOOL_EXECUTE,
                Permission.RESOURCE_READ,
                Permission.RESOURCE_WRITE
            },
            Role.VIEWER: {
                Permission.TOOL_LIST,
                Permission.RESOURCE_READ
            },
            Role.SERVICE: {
                Permission.TOOL_LIST,
                Permission.TOOL_EXECUTE
            }
        }

    def has_permission(self, user_roles: List[Role], required_permission: Permission) -> bool:
        """Check if user has required permission"""
        user_permissions = set()
        for role in user_roles:
            user_permissions.update(self.role_permissions.get(role, set()))

        return required_permission in user_permissions

    def require_permission(self, permission: Permission):
        """Decorator to require specific permission"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Get current user from request context
                user = kwargs.get('current_user')
                if not user:
                    raise HTTPException(status_code=401, detail="Not authenticated")

                if not self.has_permission(user.roles, permission):
                    raise HTTPException(status_code=403, detail="Insufficient permissions")

                return await func(*args, **kwargs)
            return wrapper
        return decorator
```

### Attribute-Based Access Control (ABAC)

```python
# security/abac.py
from typing import Dict, Any, List
import json

class ABACPolicy:
    """ABAC policy definition"""

    def __init__(self, policy_json: str):
        self.policy = json.loads(policy_json)

    def evaluate(self, subject: Dict, resource: Dict, action: str, context: Dict) -> bool:
        """Evaluate ABAC policy"""
        for rule in self.policy['rules']:
            if self._match_rule(rule, subject, resource, action, context):
                return rule['effect'] == 'allow'
        return False

    def _match_rule(self, rule: Dict, subject: Dict, resource: Dict, action: str, context: Dict) -> bool:
        """Check if rule matches current request"""
        # Check action
        if action not in rule.get('actions', []):
            return False

        # Check subject attributes
        for attr, value in rule.get('subject', {}).items():
            if not self._match_attribute(subject.get(attr), value):
                return False

        # Check resource attributes
        for attr, value in rule.get('resource', {}).items():
            if not self._match_attribute(resource.get(attr), value):
                return False

        # Check context
        for attr, value in rule.get('context', {}).items():
            if not self._match_attribute(context.get(attr), value):
                return False

        return True

    def _match_attribute(self, actual: Any, expected: Any) -> bool:
        """Match attribute value"""
        if isinstance(expected, dict):
            operator = expected.get('operator', 'equals')
            value = expected.get('value')

            if operator == 'equals':
                return actual == value
            elif operator == 'contains':
                return value in actual
            elif operator == 'regex':
                return re.match(value, str(actual)) is not None
            # Add more operators as needed
        else:
            return actual == expected

# Example ABAC policy
abac_policy = """
{
  "version": "1.0",
  "rules": [
    {
      "effect": "allow",
      "actions": ["tool:execute"],
      "subject": {
        "role": "user",
        "department": "engineering"
      },
      "resource": {
        "type": "tool",
        "classification": {"operator": "contains", "value": "public"}
      },
      "context": {
        "time": {"operator": "between", "value": ["09:00", "17:00"]}
      }
    }
  ]
}
"""
```

### Tool-Specific Permissions

```python
# security/tool_permissions.py
class ToolPermissionManager:
    """Manage tool-specific permissions"""

    def __init__(self):
        self.tool_permissions: Dict[str, Dict[str, Any]] = {}

    def register_tool(self, tool_name: str, permissions: Dict[str, Any]):
        """Register tool with specific permissions"""
        self.tool_permissions[tool_name] = {
            'required_roles': permissions.get('required_roles', []),
            'required_scopes': permissions.get('required_scopes', []),
            'rate_limit': permissions.get('rate_limit', '100/hour'),
            'audit': permissions.get('audit', True),
            'sandbox': permissions.get('sandbox', False)
        }

    async def check_tool_access(self, tool_name: str, user: Dict) -> bool:
        """Check if user can access tool"""
        permissions = self.tool_permissions.get(tool_name, {})

        # Check roles
        required_roles = permissions.get('required_roles', [])
        if required_roles and not any(role in user.get('roles', []) for role in required_roles):
            return False

        # Check scopes
        required_scopes = permissions.get('required_scopes', [])
        user_scopes = set(user.get('scopes', []))
        if required_scopes and not all(scope in user_scopes for scope in required_scopes):
            return False

        return True
```

## Network Security

### TLS Configuration

```python
# security/tls.py
import ssl
from pathlib import Path

class TLSConfig:
    """TLS configuration for MCP server"""

    @staticmethod
    def create_ssl_context(cert_file: str, key_file: str, ca_file: str = None) -> ssl.SSLContext:
        """Create SSL context with secure defaults"""
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # Load certificate and key
        context.load_cert_chain(cert_file, key_file)

        # Load CA certificates if provided
        if ca_file:
            context.load_verify_locations(ca_file)
            context.verify_mode = ssl.CERT_REQUIRED

        # Set minimum TLS version
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Disable weak ciphers
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')

        # Enable OCSP stapling
        context.options |= ssl.OP_ENABLE_OCSP_STAPLING

        return context

# Nginx configuration for TLS
nginx_tls_config = """
server {
    listen 443 ssl http2;
    server_name mcp.example.com;

    # SSL certificates
    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/nginx/certs/ca.crt;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'" always;

    location / {
        proxy_pass http://mcp-backend;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""
```

### Network Policies

```yaml
# kubernetes/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-network-policy
  namespace: mcp-system
spec:
  podSelector:
    matchLabels:
      app: mcp-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    - podSelector:
        matchLabels:
          app: mcp-client
    ports:
    - protocol: TCP
      port: 3000
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: database
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - namespaceSelector:
        matchLabels:
          name: redis
    ports:
    - protocol: TCP
      port: 6379
  # Allow DNS
  - to:
    - namespaceSelector: {}
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
```

### API Gateway Security

```python
# security/api_gateway.py
from typing import Dict, Optional
import time
import hmac
import hashlib

class APIGatewaySecurity:
    """API Gateway security features"""

    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.ip_whitelist = set()
        self.ip_blacklist = set()

    async def validate_request(self, request: Request) -> bool:
        """Validate incoming request"""
        # Check IP whitelist/blacklist
        client_ip = request.client.host
        if self.ip_blacklist and client_ip in self.ip_blacklist:
            raise HTTPException(status_code=403, detail="IP blocked")
        if self.ip_whitelist and client_ip not in self.ip_whitelist:
            raise HTTPException(status_code=403, detail="IP not whitelisted")

        # Check rate limits
        if not await self.rate_limiter.check_rate_limit(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Validate API key
        api_key = request.headers.get("X-API-Key")
        if not self.validate_api_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Validate request signature (for webhook security)
        if request.headers.get("X-Webhook-Signature"):
            if not self.validate_webhook_signature(request):
                raise HTTPException(status_code=401, detail="Invalid signature")

        return True

    def validate_api_key(self, api_key: str) -> bool:
        """Validate API key"""
        # Implementation depends on your API key storage
        return api_key in self.valid_api_keys

    def validate_webhook_signature(self, request: Request) -> bool:
        """Validate webhook signature"""
        signature = request.headers.get("X-Webhook-Signature")
        timestamp = request.headers.get("X-Webhook-Timestamp")

        # Check timestamp to prevent replay attacks
        if abs(time.time() - int(timestamp)) > 300:  # 5 minutes
            return False

        # Compute expected signature
        body = request.body
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            f"{timestamp}.{body}".encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)
```

## Data Protection

### Encryption at Rest

```python
# security/encryption.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class DataEncryption:
    """Data encryption utilities"""

    def __init__(self, master_key: str):
        self.fernet = Fernet(self._derive_key(master_key))

    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'stable_salt',  # Use proper salt management in production
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def encrypt(self, data: str) -> str:
        """Encrypt data"""
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data"""
        return self.fernet.decrypt(encrypted_data.encode()).decode()

    def encrypt_field(self, obj: Dict, field: str):
        """Encrypt specific field in object"""
        if field in obj:
            obj[field] = self.encrypt(str(obj[field]))

    def decrypt_field(self, obj: Dict, field: str):
        """Decrypt specific field in object"""
        if field in obj:
            obj[field] = self.decrypt(obj[field])

# Database field encryption
class EncryptedField:
    """SQLAlchemy encrypted field"""

    def __init__(self, encryption: DataEncryption):
        self.encryption = encryption

    def process_bind_param(self, value, dialect):
        """Encrypt before storing"""
        if value is not None:
            return self.encryption.encrypt(value)
        return value

    def process_result_value(self, value, dialect):
        """Decrypt after retrieving"""
        if value is not None:
            return self.encryption.decrypt(value)
        return value
```

### Data Sanitization

```python
# security/sanitization.py
import re
import html
from typing import Any, Dict

class DataSanitizer:
    """Sanitize user input and output"""

    def __init__(self):
        self.pii_patterns = {
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
            'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        }

    def sanitize_input(self, data: Any) -> Any:
        """Sanitize user input"""
        if isinstance(data, str):
            # Remove SQL injection attempts
            data = self._remove_sql_injection(data)
            # Escape HTML
            data = html.escape(data)
            # Remove script tags
            data = re.sub(r'<script[^>]*>.*?</script>', '', data, flags=re.IGNORECASE)

        elif isinstance(data, dict):
            return {k: self.sanitize_input(v) for k, v in data.items()}

        elif isinstance(data, list):
            return [self.sanitize_input(item) for item in data]

        return data

    def _remove_sql_injection(self, text: str) -> str:
        """Remove common SQL injection patterns"""
        sql_patterns = [
            r'(union|select|insert|update|delete|drop|create|alter|exec|script)\s',
            r'--|;|/\*|\*/',
            r'xp_|sp_'
        ]

        for pattern in sql_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text

    def mask_pii(self, data: Any) -> Any:
        """Mask PII in data"""
        if isinstance(data, str):
            for pii_type, pattern in self.pii_patterns.items():
                data = re.sub(pattern, f'[REDACTED_{pii_type.upper()}]', data)

        elif isinstance(data, dict):
            return {k: self.mask_pii(v) for k, v in data.items()}

        elif isinstance(data, list):
            return [self.mask_pii(item) for item in data]

        return data
```

## Secret Management

### HashiCorp Vault Integration

```python
# security/vault.py
import hvac
from typing import Dict, Any

class VaultSecretManager:
    """HashiCorp Vault integration"""

    def __init__(self, vault_url: str, vault_token: str):
        self.client = hvac.Client(
            url=vault_url,
            token=vault_token
        )

        if not self.client.is_authenticated():
            raise Exception("Vault authentication failed")

    def get_secret(self, path: str) -> Dict[str, Any]:
        """Get secret from Vault"""
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path
        )
        return response['data']['data']

    def store_secret(self, path: str, secret: Dict[str, Any]):
        """Store secret in Vault"""
        self.client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=secret
        )

    def rotate_secret(self, path: str, new_secret: Dict[str, Any]):
        """Rotate secret"""
        # Get current version
        current = self.get_secret(path)

        # Store new version
        self.store_secret(path, new_secret)

        # Keep previous version for rollback
        self.store_secret(f"{path}-previous", current)

    def get_database_credentials(self, role: str) -> Dict[str, str]:
        """Get dynamic database credentials"""
        response = self.client.read(f'database/creds/{role}')
        return {
            'username': response['data']['username'],
            'password': response['data']['password']
        }
```

### Environment Variable Security

```python
# security/env_security.py
import os
from typing import Dict, Optional

class SecureEnvironment:
    """Secure environment variable management"""

    def __init__(self):
        self.required_vars = [
            'MCP_SECRET_KEY',
            'DATABASE_URL',
            'REDIS_URL',
            'JWT_SECRET'
        ]
        self.sensitive_vars = [
            'PASSWORD',
            'SECRET',
            'KEY',
            'TOKEN'
        ]

    def validate_environment(self):
        """Validate required environment variables"""
        missing = []
        for var in self.required_vars:
            if not os.getenv(var):
                missing.append(var)

        if missing:
            raise EnvironmentError(f"Missing required environment variables: {missing}")

    def get_secure(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable securely"""
        value = os.getenv(key, default)

        # Log access to sensitive variables
        if any(sensitive in key.upper() for sensitive in self.sensitive_vars):
            logger.info(f"Accessed sensitive environment variable: {key}")

        return value

    def mask_sensitive_vars(self) -> Dict[str, str]:
        """Get all environment variables with sensitive ones masked"""
        env_vars = {}

        for key, value in os.environ.items():
            if any(sensitive in key.upper() for sensitive in self.sensitive_vars):
                env_vars[key] = "***MASKED***"
            else:
                env_vars[key] = value

        return env_vars
```

## Input Validation

### Schema Validation

```python
# security/validation.py
from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any
import re

class ToolExecutionRequest(BaseModel):
    """Validated tool execution request"""

    tool_name: str = Field(..., min_length=1, max_length=100, regex="^[a-zA-Z0-9_-]+$")
    args: Dict[str, Any] = Field(default_factory=dict)
    timeout: Optional[int] = Field(default=30, ge=1, le=300)

    @validator('tool_name')
    def validate_tool_name(cls, v):
        """Validate tool name"""
        if v.startswith('_'):
            raise ValueError("Tool name cannot start with underscore")
        return v

    @validator('args')
    def validate_args(cls, v):
        """Validate tool arguments"""
        # Check for suspicious patterns
        args_str = str(v)
        if re.search(r'__[a-z]+__', args_str):  # Python magic methods
            raise ValueError("Invalid argument pattern detected")
        return v

class InputValidator:
    """Comprehensive input validation"""

    def __init__(self):
        self.max_string_length = 10000
        self.max_array_size = 1000
        self.max_object_depth = 10

    def validate_input(self, data: Any, depth: int = 0) -> Any:
        """Recursively validate input data"""
        if depth > self.max_object_depth:
            raise ValueError("Maximum object depth exceeded")

        if isinstance(data, str):
            if len(data) > self.max_string_length:
                raise ValueError(f"String exceeds maximum length of {self.max_string_length}")
            return self._validate_string(data)

        elif isinstance(data, list):
            if len(data) > self.max_array_size:
                raise ValueError(f"Array exceeds maximum size of {self.max_array_size}")
            return [self.validate_input(item, depth + 1) for item in data]

        elif isinstance(data, dict):
            return {
                self._validate_key(k): self.validate_input(v, depth + 1)
                for k, v in data.items()
            }

        elif isinstance(data, (int, float)):
            return self._validate_number(data)

        else:
            return data

    def _validate_string(self, s: str) -> str:
        """Validate string input"""
        # Check for null bytes
        if '\x00' in s:
            raise ValueError("Null bytes not allowed in strings")

        # Check for control characters
        if any(ord(char) < 32 and char not in '\t\n\r' for char in s):
            raise ValueError("Control characters not allowed")

        return s

    def _validate_key(self, key: str) -> str:
        """Validate dictionary keys"""
        if not isinstance(key, str):
            raise ValueError("Dictionary keys must be strings")

        if not re.match(r'^[a-zA-Z0-9_.-]+$', key):
            raise ValueError(f"Invalid key format: {key}")

        return key

    def _validate_number(self, n: Union[int, float]) -> Union[int, float]:
        """Validate numeric input"""
        if isinstance(n, float):
            if math.isnan(n) or math.isinf(n):
                raise ValueError("NaN and Infinity not allowed")

        return n
```

### Command Injection Prevention

```python
# security/command_injection.py
import shlex
import subprocess
from typing import List, Optional

class SafeCommandExecutor:
    """Safe command execution"""

    def __init__(self):
        self.allowed_commands = {
            'echo', 'ls', 'pwd', 'date', 'whoami'
        }
        self.forbidden_chars = ['&', '|', ';', '$', '`', '\n', '\r']

    def execute_command(self, command: str, args: List[str]) -> str:
        """Safely execute command"""
        # Validate command
        if command not in self.allowed_commands:
            raise ValueError(f"Command '{command}' not allowed")

        # Validate arguments
        for arg in args:
            if any(char in arg for char in self.forbidden_chars):
                raise ValueError(f"Invalid characters in argument: {arg}")

        # Use shlex to properly quote arguments
        safe_args = [shlex.quote(arg) for arg in args]

        # Execute with strict controls
        try:
            result = subprocess.run(
                [command] + safe_args,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
                shell=False  # Never use shell=True
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            raise TimeoutError("Command execution timed out")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Command failed: {e.stderr}")
```

## Audit and Compliance

### Comprehensive Audit Logging

```python
# security/audit.py
from datetime import datetime
from typing import Dict, Any, Optional
import hashlib

class AuditLogger:
    """Comprehensive audit logging"""

    def __init__(self, storage_backend):
        self.storage = storage_backend

    async def log_authentication(self,
                               user_id: Optional[str],
                               action: str,
                               success: bool,
                               ip_address: str,
                               user_agent: str,
                               details: Dict[str, Any] = None):
        """Log authentication events"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'authentication',
            'user_id': user_id,
            'action': action,  # login, logout, token_refresh
            'success': success,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'details': details or {}
        }

        await self.storage.store_audit_log(event)

    async def log_authorization(self,
                              user_id: str,
                              resource: str,
                              action: str,
                              granted: bool,
                              reason: str = None):
        """Log authorization decisions"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'authorization',
            'user_id': user_id,
            'resource': resource,
            'action': action,
            'granted': granted,
            'reason': reason
        }

        await self.storage.store_audit_log(event)

    async def log_data_access(self,
                            user_id: str,
                            data_type: str,
                            operation: str,
                            data_id: str,
                            fields_accessed: List[str] = None):
        """Log data access for compliance"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'data_access',
            'user_id': user_id,
            'data_type': data_type,
            'operation': operation,  # read, write, delete
            'data_id': data_id,
            'fields_accessed': fields_accessed or [],
            'data_hash': self._hash_data_reference(data_type, data_id)
        }

        await self.storage.store_audit_log(event)

    async def log_security_event(self,
                               event_type: str,
                               severity: str,
                               description: str,
                               source_ip: str = None,
                               user_id: str = None,
                               details: Dict[str, Any] = None):
        """Log security events"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'security',
            'security_event_type': event_type,
            'severity': severity,  # critical, high, medium, low
            'description': description,
            'source_ip': source_ip,
            'user_id': user_id,
            'details': details or {}
        }

        await self.storage.store_audit_log(event)

    def _hash_data_reference(self, data_type: str, data_id: str) -> str:
        """Create hash of data reference for integrity"""
        return hashlib.sha256(f"{data_type}:{data_id}".encode()).hexdigest()
```

### GDPR Compliance

```python
# security/gdpr.py
from datetime import datetime, timedelta
from typing import Dict, List, Any

class GDPRCompliance:
    """GDPR compliance utilities"""

    def __init__(self, storage):
        self.storage = storage

    async def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Export all user data (GDPR Article 20)"""
        user_data = {
            'export_date': datetime.utcnow().isoformat(),
            'user_id': user_id,
            'profile': await self.storage.get_user_profile(user_id),
            'activity_logs': await self.storage.get_user_activity(user_id),
            'preferences': await self.storage.get_user_preferences(user_id),
            'tool_usage': await self.storage.get_tool_usage(user_id)
        }

        # Log data export
        await self.audit_logger.log_data_access(
            user_id=user_id,
            data_type='user_data',
            operation='export',
            data_id=user_id
        )

        return user_data

    async def delete_user_data(self, user_id: str, confirm_token: str) -> bool:
        """Delete all user data (GDPR Article 17)"""
        # Verify deletion token
        if not self.verify_deletion_token(user_id, confirm_token):
            raise ValueError("Invalid deletion token")

        # Delete from all systems
        deletion_tasks = [
            self.storage.delete_user_profile(user_id),
            self.storage.delete_user_activity(user_id),
            self.storage.delete_user_preferences(user_id),
            self.storage.delete_tool_usage(user_id)
        ]

        await asyncio.gather(*deletion_tasks)

        # Log deletion
        await self.audit_logger.log_security_event(
            event_type='data_deletion',
            severity='high',
            description=f'User data deleted per GDPR request',
            user_id=user_id
        )

        return True

    async def anonymize_old_data(self, retention_days: int = 365):
        """Anonymize data older than retention period"""
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Get old records
        old_records = await self.storage.get_records_before(cutoff_date)

        for record in old_records:
            # Anonymize PII fields
            record['user_id'] = hashlib.sha256(record['user_id'].encode()).hexdigest()
            record['email'] = 'anonymized@example.com'
            record['ip_address'] = '0.0.0.0'

            await self.storage.update_record(record)
```

### SOC 2 Compliance

```python
# security/soc2.py
class SOC2Compliance:
    """SOC 2 compliance controls"""

    def __init__(self):
        self.controls = {
            'CC6.1': self.logical_access_controls,
            'CC6.2': self.new_user_access,
            'CC6.3': self.user_access_removal,
            'CC7.1': self.system_monitoring,
            'CC7.2': self.security_monitoring
        }

    async def logical_access_controls(self) -> Dict[str, Any]:
        """CC6.1: Logical access controls"""
        return {
            'control': 'CC6.1',
            'description': 'Logical access controls',
            'status': 'implemented',
            'evidence': {
                'authentication': 'JWT with MFA',
                'authorization': 'RBAC and ABAC',
                'password_policy': {
                    'min_length': 12,
                    'complexity': True,
                    'expiration_days': 90
                }
            }
        }

    async def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate SOC 2 compliance report"""
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'period': {
                'start': (datetime.utcnow() - timedelta(days=90)).isoformat(),
                'end': datetime.utcnow().isoformat()
            },
            'controls': {}
        }

        for control_id, control_func in self.controls.items():
            report['controls'][control_id] = await control_func()

        return report
```

## Security Monitoring

### Intrusion Detection

```python
# security/intrusion_detection.py
from collections import defaultdict
import asyncio

class IntrusionDetectionSystem:
    """Real-time intrusion detection"""

    def __init__(self):
        self.failed_attempts = defaultdict(list)
        self.suspicious_patterns = []
        self.blocked_ips = set()

    async def analyze_request(self, request: Dict[str, Any]) -> bool:
        """Analyze request for intrusion patterns"""
        ip_address = request.get('ip_address')

        # Check if IP is blocked
        if ip_address in self.blocked_ips:
            return False

        # Check for brute force
        if await self.check_brute_force(ip_address):
            await self.block_ip(ip_address, reason='brute_force')
            return False

        # Check for scanning attempts
        if await self.check_scanning(request):
            await self.block_ip(ip_address, reason='scanning')
            return False

        # Check for exploitation attempts
        if await self.check_exploitation(request):
            await self.block_ip(ip_address, reason='exploitation')
            return False

        return True

    async def check_brute_force(self, ip_address: str) -> bool:
        """Check for brute force attacks"""
        now = datetime.utcnow()

        # Clean old attempts
        self.failed_attempts[ip_address] = [
            attempt for attempt in self.failed_attempts[ip_address]
            if now - attempt < timedelta(minutes=10)
        ]

        # Check threshold
        return len(self.failed_attempts[ip_address]) > 5

    async def check_scanning(self, request: Dict[str, Any]) -> bool:
        """Check for scanning attempts"""
        suspicious_paths = [
            '/admin', '/wp-admin', '/phpmyadmin',
            '/.env', '/config', '/.git',
            '/backup', '/sql', '/db'
        ]

        path = request.get('path', '')
        return any(path.startswith(p) for p in suspicious_paths)

    async def block_ip(self, ip_address: str, reason: str):
        """Block IP address"""
        self.blocked_ips.add(ip_address)

        # Log security event
        await self.audit_logger.log_security_event(
            event_type='ip_blocked',
            severity='high',
            description=f'IP blocked for {reason}',
            source_ip=ip_address
        )

        # Update firewall rules
        await self.update_firewall_rules()
```

### Security Dashboard

```python
# security/dashboard.py
class SecurityDashboard:
    """Real-time security dashboard data"""

    def __init__(self):
        self.metrics = SecurityMetrics()

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get security dashboard data"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'threats': {
                'active_threats': await self.get_active_threats(),
                'blocked_ips': len(self.ids.blocked_ips),
                'failed_auth_24h': await self.get_failed_auth_count(hours=24)
            },
            'compliance': {
                'soc2_status': await self.get_soc2_status(),
                'gdpr_requests': await self.get_gdpr_request_count(),
                'audit_coverage': await self.get_audit_coverage()
            },
            'vulnerabilities': {
                'critical': await self.get_vulnerabilities('critical'),
                'high': await self.get_vulnerabilities('high'),
                'medium': await self.get_vulnerabilities('medium'),
                'low': await self.get_vulnerabilities('low')
            },
            'activity': {
                'auth_success_rate': await self.get_auth_success_rate(),
                'api_calls_per_minute': await self.get_api_call_rate(),
                'unique_users_24h': await self.get_unique_users(hours=24)
            }
        }
```

## Incident Response

### Incident Response Plan

```python
# security/incident_response.py
from enum import Enum

class IncidentSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class IncidentResponse:
    """Incident response management"""

    def __init__(self):
        self.active_incidents = {}

    async def create_incident(self,
                            incident_type: str,
                            severity: IncidentSeverity,
                            description: str,
                            affected_systems: List[str]) -> str:
        """Create new security incident"""
        incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        incident = {
            'id': incident_id,
            'type': incident_type,
            'severity': severity.value,
            'description': description,
            'affected_systems': affected_systems,
            'status': 'open',
            'created_at': datetime.utcnow().isoformat(),
            'timeline': []
        }

        self.active_incidents[incident_id] = incident

        # Trigger immediate actions
        await self.trigger_incident_response(incident)

        return incident_id

    async def trigger_incident_response(self, incident: Dict[str, Any]):
        """Trigger incident response procedures"""
        severity = IncidentSeverity(incident['severity'])

        # Notify appropriate teams
        if severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]:
            await self.notify_on_call(incident)
            await self.notify_management(incident)

        # Take automatic actions
        if incident['type'] == 'data_breach':
            await self.initiate_breach_response(incident)
        elif incident['type'] == 'ddos':
            await self.activate_ddos_mitigation(incident)
        elif incident['type'] == 'unauthorized_access':
            await self.lock_affected_accounts(incident)

    async def initiate_breach_response(self, incident: Dict[str, Any]):
        """Data breach response procedures"""
        # 1. Isolate affected systems
        for system in incident['affected_systems']:
            await self.isolate_system(system)

        # 2. Preserve evidence
        await self.capture_forensic_data(incident['id'])

        # 3. Assess impact
        impact = await self.assess_breach_impact(incident)

        # 4. Notify stakeholders
        if impact['users_affected'] > 0:
            await self.prepare_breach_notification(impact)

        # 5. Update incident
        await self.update_incident(incident['id'], {
            'impact_assessment': impact,
            'containment_status': 'isolated'
        })
```

### Forensics and Investigation

```python
# security/forensics.py
class ForensicsCollector:
    """Collect forensic data for security investigations"""

    async def capture_system_state(self, incident_id: str) -> Dict[str, Any]:
        """Capture complete system state"""
        state = {
            'incident_id': incident_id,
            'captured_at': datetime.utcnow().isoformat(),
            'system_info': await self.get_system_info(),
            'network_connections': await self.get_network_connections(),
            'running_processes': await self.get_running_processes(),
            'open_files': await self.get_open_files(),
            'memory_snapshot': await self.capture_memory_snapshot(),
            'logs': await self.collect_relevant_logs()
        }

        # Store securely
        await self.store_forensic_data(incident_id, state)

        return state

    async def analyze_attack_pattern(self, incident_id: str) -> Dict[str, Any]:
        """Analyze attack patterns from collected data"""
        data = await self.get_forensic_data(incident_id)

        analysis = {
            'attack_vectors': await self.identify_attack_vectors(data),
            'timeline': await self.reconstruct_timeline(data),
            'indicators_of_compromise': await self.extract_iocs(data),
            'affected_data': await self.identify_affected_data(data),
            'recommendations': await self.generate_recommendations(data)
        }

        return analysis
```

## Best Practices Summary

### 1. Authentication & Authorization
- Use strong authentication (JWT + MFA)
- Implement least privilege access
- Regular token rotation
- Session management

### 2. Network Security
- TLS 1.2+ everywhere
- Network segmentation
- API gateway protection
- DDoS mitigation

### 3. Data Protection
- Encryption at rest and in transit
- PII detection and masking
- Secure key management
- Data retention policies

### 4. Input Validation
- Whitelist validation
- Schema validation
- Command injection prevention
- SQL injection protection

### 5. Monitoring & Response
- Comprehensive audit logging
- Real-time threat detection
- Incident response procedures
- Regular security assessments

### 6. Compliance
- GDPR compliance tools
- SOC 2 controls
- Regular compliance audits
- Documentation maintenance

## Security Checklist

- [ ] TLS configured with strong ciphers
- [ ] Authentication implemented (JWT/OAuth2)
- [ ] MFA enabled for sensitive operations
- [ ] RBAC/ABAC configured
- [ ] Input validation on all endpoints
- [ ] Output encoding/sanitization
- [ ] Secrets stored securely
- [ ] Audit logging enabled
- [ ] Security monitoring active
- [ ] Incident response plan tested
- [ ] Regular security scans
- [ ] Dependency updates
- [ ] Security training completed
- [ ] Compliance requirements met
- [ ] Backup and recovery tested

## Conclusion

Security is not a one-time implementation but an ongoing process. Regular security assessments, staying updated with the latest threats, and maintaining a security-first culture are essential for protecting MCP deployments. By following these best practices and continuously improving your security posture, you can build and maintain secure MCP systems that protect both your infrastructure and your users' data.
