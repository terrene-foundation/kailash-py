"""
JWT Authentication and Tenant Isolation for Kailash Workflow Studio

This module provides:
- JWT token generation and validation
- User authentication and authorization
- Tenant isolation middleware
- Permission-based access control

Design Principles:
- Stateless authentication via JWT tokens
- Tenant data isolation at all levels
- Role-based access control (RBAC)
- Secure token storage and rotation

Dependencies:
- python-jose[cryptography]: JWT token handling
- passlib: Password hashing
- fastapi-security: Security utilities

Usage:
    >>> from kailash.api.auth import JWTAuth, get_current_user
    >>> auth = JWTAuth(secret_key="your-secret-key")
    >>> token = auth.create_access_token({"sub": "user@example.com", "tenant_id": "tenant1"})
    >>> decoded = auth.verify_token(token)

Implementation:
    The auth system uses JWT tokens with the following claims:
    - sub: User identifier (email or user_id)
    - tenant_id: Tenant identifier for isolation
    - roles: List of user roles
    - exp: Token expiration time
    - iat: Token issued at time

Security Considerations:
    - Tokens expire after 24 hours by default
    - Refresh tokens supported for seamless rotation
    - All tenant data queries filtered by tenant_id
    - Passwords hashed using bcrypt with salt

Testing:
    See tests/test_api/test_auth.py for comprehensive tests

Future Enhancements:
    - OAuth2/OIDC integration
    - Multi-factor authentication
    - API key authentication for service accounts
"""

import os
import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

# Import after database module to avoid circular imports
import kailash.api.database as db
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Session, relationship

Base = db.Base
get_db_session = db.get_db_session

# Security configuration
DEFAULT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token security
security = HTTPBearer()


# Database Models
class User(Base):
    """User account model with tenant association"""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # Tenant association
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    # User status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)

    # User roles and permissions
    roles = Column(JSON, default=lambda: ["user"])
    permissions = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_login = Column(DateTime)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    api_keys = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_user_tenant", "tenant_id"),
        Index("idx_user_email_tenant", "email", "tenant_id", unique=True),
    )


class Tenant(Base):
    """Tenant model for multi-tenancy"""

    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)

    # Tenant configuration
    settings = Column(JSON, default=dict)
    features = Column(JSON, default=lambda: ["workflows", "custom_nodes", "executions"])

    # Limits and quotas
    max_users = Column(JSON, default=lambda: {"limit": 10, "current": 0})
    max_workflows = Column(JSON, default=lambda: {"limit": 100, "current": 0})
    max_executions_per_month = Column(
        JSON, default=lambda: {"limit": 1000, "current": 0}
    )
    storage_quota_mb = Column(JSON, default=lambda: {"limit": 1024, "current": 0})

    # Status
    is_active = Column(Boolean, default=True)
    subscription_tier = Column(String(50), default="free")

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    api_keys = relationship(
        "APIKey", back_populates="tenant", cascade="all, delete-orphan"
    )


class APIKey(Base):
    """API Key model for service authentication"""

    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)

    # Association
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    # Permissions
    scopes = Column(JSON, default=lambda: ["read:workflows", "execute:workflows"])

    # Status and limits
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime)
    last_used_at = Column(DateTime)
    usage_count = Column(JSON, default=lambda: {"total": 0, "monthly": 0})

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    user = relationship("User", back_populates="api_keys")
    tenant = relationship("Tenant", back_populates="api_keys")

    __table_args__ = (Index("idx_apikey_tenant", "tenant_id"),)


# Pydantic models
class UserCreate(BaseModel):
    """User registration model"""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    tenant_id: str | None = None  # If None, create new tenant


class UserLogin(BaseModel):
    """User login model"""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Decoded token data"""

    sub: str
    tenant_id: str
    roles: list[str] = ["user"]
    permissions: list[str] = []
    exp: datetime | None = None


class JWTAuth:
    """JWT authentication handler"""

    def __init__(self, secret_key: str = DEFAULT_SECRET_KEY):
        self.secret_key = secret_key
        self.algorithm = ALGORITHM

    def create_access_token(
        self, data: dict[str, Any], expires_delta: timedelta | None = None
    ) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

        to_encode.update({"exp": expire, "iat": datetime.now(UTC), "type": "access"})

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def create_refresh_token(self, data: dict[str, Any]) -> str:
        """Create a JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode.update({"exp": expire, "iat": datetime.now(UTC), "type": "refresh"})

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str, token_type: str = "access") -> TokenData:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Verify token type
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )

            # Extract claims
            sub: str = payload.get("sub")
            tenant_id: str = payload.get("tenant_id")

            if sub is None or tenant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token claims",
                )

            return TokenData(
                sub=sub,
                tenant_id=tenant_id,
                roles=payload.get("roles", ["user"]),
                permissions=payload.get("permissions", []),
                exp=payload.get("exp"),
            )

        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def create_tokens(self, user: User) -> TokenResponse:
        """Create both access and refresh tokens for a user"""
        token_data = {
            "sub": user.email,
            "tenant_id": user.tenant_id,
            "roles": user.roles,
            "permissions": user.permissions,
        }

        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        )


# Authentication utilities
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_api_key() -> tuple[str, str]:
    """Create an API key and return (key, hash)"""
    key = f"kls_{secrets.token_urlsafe(32)}"
    key_hash = pwd_context.hash(key)
    return key, key_hash


# FastAPI dependencies
auth = JWTAuth()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_db_session),
) -> User:
    """Get current authenticated user from JWT token"""
    token = credentials.credentials
    token_data = auth.verify_token(token)

    user = (
        session.query(User)
        .filter(User.email == token_data.sub, User.tenant_id == token_data.tenant_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    return user


async def get_current_tenant(
    user: User = Depends(get_current_user), session: Session = Depends(get_db_session)
) -> Tenant:
    """Get current tenant from authenticated user"""
    tenant = session.query(Tenant).filter(Tenant.id == user.tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Tenant account is inactive"
        )

    return tenant


async def verify_api_key(
    request: Request, session: Session = Depends(get_db_session)
) -> APIKey:
    """Verify API key from request header"""
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required"
        )

    # Find API key by verifying against hashes
    api_keys = session.query(APIKey).filter(APIKey.is_active).all()

    valid_key = None
    for key_record in api_keys:
        if pwd_context.verify(api_key, key_record.key_hash):
            valid_key = key_record
            break

    if not valid_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    # Check expiration
    if valid_key.expires_at and valid_key.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired"
        )

    # Update usage
    valid_key.last_used_at = datetime.now(UTC)
    valid_key.usage_count["total"] += 1
    valid_key.usage_count["monthly"] += 1
    session.commit()

    return valid_key


# Permission checking
def check_permission(user: User, permission: str) -> bool:
    """Check if user has a specific permission"""
    # Superusers have all permissions
    if user.is_superuser:
        return True

    # Check explicit permissions
    if permission in user.permissions:
        return True

    # Check role-based permissions
    role_permissions = {
        "admin": [
            "read:all",
            "write:all",
            "delete:all",
            "manage:users",
            "manage:tenant",
        ],
        "editor": [
            "read:workflows",
            "write:workflows",
            "delete:workflows",
            "read:nodes",
            "write:nodes",
            "execute:workflows",
        ],
        "viewer": ["read:workflows", "read:nodes", "read:executions"],
        "user": ["read:own", "write:own", "execute:own"],
    }

    for role in user.roles:
        if permission in role_permissions.get(role, []):
            return True

    return False


def require_permission(permission: str):
    """Decorator to require specific permission"""

    def permission_checker(user: User = Depends(get_current_user)):
        if not check_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return user

    return permission_checker


# Tenant isolation utilities
class TenantContext:
    """Context manager for tenant-scoped operations"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._previous_tenant = None

    def __enter__(self):
        # Store current tenant context
        self._previous_tenant = getattr(_tenant_context, "tenant_id", None)
        _tenant_context.tenant_id = self.tenant_id
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore previous tenant context
        if self._previous_tenant:
            _tenant_context.tenant_id = self._previous_tenant
        else:
            delattr(_tenant_context, "tenant_id")


# Thread-local storage for tenant context
_tenant_context = threading.local()


def get_current_tenant_id() -> str | None:
    """Get current tenant ID from context"""
    return getattr(_tenant_context, "tenant_id", None)


def set_current_tenant_id(tenant_id: str):
    """Set current tenant ID in context"""
    _tenant_context.tenant_id = tenant_id


# Authentication service
class AuthService:
    """High-level authentication service"""

    def __init__(self, session: Session):
        self.session = session
        self.auth = JWTAuth()

    def register_user(self, user_data: UserCreate) -> tuple[User, TokenResponse]:
        """Register a new user"""
        # Check if email already exists
        existing = (
            self.session.query(User).filter(User.email == user_data.email).first()
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create or get tenant
        if user_data.tenant_id:
            tenant = (
                self.session.query(Tenant)
                .filter(Tenant.id == user_data.tenant_id)
                .first()
            )

            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
                )

            # Check tenant user limit
            if tenant.max_users["current"] >= tenant.max_users["limit"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant user limit reached",
                )
        else:
            # Create new tenant for user
            import uuid

            tenant = Tenant(
                id=str(uuid.uuid4()),
                name=f"{user_data.username}'s Workspace",
                slug=f"tenant-{uuid.uuid4().hex[:8]}",
            )
            self.session.add(tenant)
            self.session.flush()

        # Create user
        import uuid

        user = User(
            id=str(uuid.uuid4()),
            email=user_data.email,
            username=user_data.username,
            hashed_password=get_password_hash(user_data.password),
            tenant_id=tenant.id,
        )

        self.session.add(user)

        # Update tenant user count
        tenant.max_users["current"] += 1

        self.session.commit()

        # Generate tokens
        tokens = self.auth.create_tokens(user)

        return user, tokens

    def login_user(self, credentials: UserLogin) -> tuple[User, TokenResponse]:
        """Authenticate user and generate tokens"""
        user = self.session.query(User).filter(User.email == credentials.email).first()

        if not user or not verify_password(credentials.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
            )

        # Update last login
        user.last_login = datetime.now(UTC)
        self.session.commit()

        # Generate tokens
        tokens = self.auth.create_tokens(user)

        return user, tokens

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token using refresh token"""
        token_data = self.auth.verify_token(refresh_token, token_type="refresh")

        # Get user to ensure they still exist and are active
        user = (
            self.session.query(User)
            .filter(
                User.email == token_data.sub, User.tenant_id == token_data.tenant_id
            )
            .first()
        )

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Generate new tokens
        return self.auth.create_tokens(user)

    def create_api_key(
        self, name: str, user: User, scopes: list[str] = None
    ) -> tuple[str, APIKey]:
        """Create an API key for a user"""
        key, key_hash = create_api_key()

        import uuid

        api_key = APIKey(
            id=str(uuid.uuid4()),
            key_hash=key_hash,
            name=name,
            user_id=user.id,
            tenant_id=user.tenant_id,
            scopes=scopes or ["read:workflows", "execute:workflows"],
        )

        self.session.add(api_key)
        self.session.commit()

        return key, api_key
