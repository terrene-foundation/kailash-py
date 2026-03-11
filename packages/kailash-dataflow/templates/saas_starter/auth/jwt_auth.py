"""
SaaS Starter Template - Simplified JWT Authentication

Simplified authentication approach with direct Python functions.

Functions:
- hash_password(password) - Hash password with bcrypt
- verify_password(password, hashed) - Verify password against hash
- generate_access_token(user_id, org_id, email) - Generate JWT access token
- generate_refresh_token(user_id) - Generate JWT refresh token
- verify_token(token, secret) - Verify JWT token and return claims
- create_user_record(db, user_data) - Create user record using DataFlow
- find_user_by_email(db, email) - Find user by email using DataFlow
- login_user(db, email, password) - Complete login flow

Architecture:
- Direct Python functions for authentication logic (bcrypt, PyJWT)
- DataFlow workflows ONLY for database operations
- No complex SwitchNode conditionals in workflows
- Simple, testable, fast functions

Dependencies:
- bcrypt: Password hashing
- PyJWT: JWT token generation and verification
- DataFlow: Database operations only
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
import jwt

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# JWT Configuration
JWT_SECRET = "your-secret-key-change-in-production"  # Change in production
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY_SECONDS = 3600  # 1 hour
REFRESH_TOKEN_EXPIRY_SECONDS = 604800  # 7 days


# Password hashing functions (direct bcrypt usage)


def hash_password(password: str) -> str:
    """
    Hash password with bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string (starts with $2b$)

    Example:
        >>> hashed = hash_password("MyPassword123!")
        >>> print(hashed[:4])
        $2b$
    """
    if not password:
        raise ValueError("Password cannot be empty")

    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify password against bcrypt hash.

    Args:
        password: Plain text password
        hashed: Bcrypt hash string

    Returns:
        True if password matches hash, False otherwise

    Example:
        >>> hashed = hash_password("MyPassword123!")
        >>> verify_password("MyPassword123!", hashed)
        True
        >>> verify_password("WrongPassword", hashed)
        False
    """
    if not password or not hashed:
        return False

    try:
        password_bytes = password.encode("utf-8")
        hashed_bytes = hashed.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


# JWT token generation functions (direct PyJWT usage)


def generate_access_token(user_id: str, org_id: str, email: str) -> Dict[str, Any]:
    """
    Generate JWT access token.

    Args:
        user_id: User ID
        org_id: Organization ID
        email: User email

    Returns:
        dict: {
            "access_token": str,
            "expires_in": int
        }

    Example:
        >>> result = generate_access_token("user_123", "org_456", "test@example.com")
        >>> print(result.keys())
        dict_keys(['access_token', 'expires_in'])
    """
    if not user_id or not org_id or not email:
        raise ValueError("user_id, org_id, and email are required")

    payload = {
        "user_id": user_id,
        "org_id": org_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(seconds=ACCESS_TOKEN_EXPIRY_SECONDS),
        "iat": datetime.utcnow(),
        "type": "access",
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {"access_token": token, "expires_in": ACCESS_TOKEN_EXPIRY_SECONDS}


def generate_refresh_token(user_id: str) -> Dict[str, Any]:
    """
    Generate JWT refresh token.

    Args:
        user_id: User ID

    Returns:
        dict: {
            "refresh_token": str,
            "expires_in": int
        }

    Example:
        >>> result = generate_refresh_token("user_789")
        >>> print(result.keys())
        dict_keys(['refresh_token', 'expires_in'])
    """
    if not user_id:
        raise ValueError("user_id is required")

    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(seconds=REFRESH_TOKEN_EXPIRY_SECONDS),
        "iat": datetime.utcnow(),
        "type": "refresh",
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {"refresh_token": token, "expires_in": REFRESH_TOKEN_EXPIRY_SECONDS}


def verify_token(access_token: str, secret: str = JWT_SECRET) -> Dict[str, Any]:
    """
    Verify JWT token and return claims.

    Args:
        access_token: JWT token to verify
        secret: JWT secret key (default: JWT_SECRET)

    Returns:
        dict: {
            "valid": bool,
            "user_id": str (if valid),
            "org_id": str (if valid),
            "exp": float (if valid),
            "error": str (if invalid),
            "error_code": str (if invalid)
        }

    Example:
        >>> token_data = generate_access_token("user_123", "org_456", "test@example.com")
        >>> result = verify_token(token_data["access_token"])
        >>> print(result["valid"])
        True
    """
    try:
        decoded = jwt.decode(access_token, secret, algorithms=[JWT_ALGORITHM])

        return {
            "valid": True,
            "user_id": decoded["user_id"],
            "org_id": decoded.get("org_id"),
            "exp": decoded["exp"],
        }

    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Token expired", "error_code": "TOKEN_EXPIRED"}

    except jwt.InvalidTokenError:
        return {"valid": False, "error": "Invalid token", "error_code": "INVALID_TOKEN"}


# Database operation functions (DataFlow workflows only)


def create_user_record(db, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Create user record using DataFlow UserCreateNode.

    Args:
        db: DataFlow instance
        user_data: User data dict with id, organization_id, email, password_hash, role, status

    Returns:
        Created user record dict

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow(":memory:")
        >>> user_data = {
        ...     "id": "user_123",
        ...     "organization_id": "org_456",
        ...     "email": "test@example.com",
        ...     "password_hash": hash_password("password"),
        ...     "role": "member",
        ...     "status": "active"
        ... }
        >>> user = create_user_record(db, user_data)
        >>> print(user["email"])
        test@example.com
    """
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create_user", user_data)

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("create_user")


def find_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    """
    Find user by email using DataFlow UserListNode.

    Args:
        db: DataFlow instance
        email: User email to search

    Returns:
        User dict if found, None otherwise

    Example:
        >>> user = find_user_by_email(db, "test@example.com")
        >>> if user:
        ...     print(user["email"])
        test@example.com
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserListNode", "find_user", {"filters": {"email": email}, "limit": 1}
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    users = results.get("find_user", [])
    return users[0] if users else None


# Complete authentication flows


def login_user(db, email: str, password: str) -> Dict[str, Any]:
    """
    Complete login flow with password verification and token generation.

    Args:
        db: DataFlow instance
        email: User email
        password: Plain text password

    Returns:
        dict: {
            "success": bool,
            "user": dict (if success),
            "access_token": str (if success),
            "refresh_token": str (if success),
            "expires_in": int (if success),
            "error": str (if failure),
            "error_code": str (if failure)
        }

    Example:
        >>> result = login_user(db, "test@example.com", "password123")
        >>> if result["success"]:
        ...     print(result["access_token"])
    """
    # Find user by email
    user = find_user_by_email(db, email)

    if not user:
        return {
            "success": False,
            "error": "User not found",
            "error_code": "USER_NOT_FOUND",
        }

    # Verify password
    if not verify_password(password, user["password_hash"]):
        return {
            "success": False,
            "error": "Invalid credentials",
            "error_code": "INVALID_CREDENTIALS",
        }

    # Generate tokens
    access_token_data = generate_access_token(
        user["id"], user["organization_id"], user["email"]
    )

    refresh_token_data = generate_refresh_token(user["id"])

    return {
        "success": True,
        "user": user,
        "access_token": access_token_data["access_token"],
        "refresh_token": refresh_token_data["refresh_token"],
        "expires_in": access_token_data["expires_in"],
    }


def register_user(
    db, email: str, name: str, password: str, organization_id: str
) -> Dict[str, Any]:
    """
    Register new user with hashed password and JWT tokens.

    Args:
        db: DataFlow instance
        email: User email address
        name: User full name
        password: Plain text password (will be hashed)
        organization_id: Organization FK for multi-tenancy

    Returns:
        dict: {
            "success": bool,
            "user": dict (if success),
            "access_token": str (if success),
            "refresh_token": str (if success),
            "expires_in": int (if success),
            "error": str (if failure),
            "error_code": str (if failure)
        }

    Example:
        >>> result = register_user(
        ...     db,
        ...     email="alice@example.com",
        ...     name="Alice Smith",
        ...     password="SecurePass123!",
        ...     organization_id="org_abc123"
        ... )
        >>> if result["success"]:
        ...     print(result["access_token"])
    """
    # Check if email already exists
    existing_user = find_user_by_email(db, email)

    if existing_user:
        return {
            "success": False,
            "error": "Email already registered",
            "error_code": "DUPLICATE_EMAIL",
        }

    # Hash password
    password_hash = hash_password(password)

    # Generate user ID
    import uuid

    user_id = f"user_{uuid.uuid4().hex[:16]}"

    # Create user record
    user_data = {
        "id": user_id,
        "organization_id": organization_id,
        "email": email,
        "password_hash": password_hash,
        "role": "member",
        "status": "active",
    }

    user = create_user_record(db, user_data)

    if not user:
        return {
            "success": False,
            "error": "Failed to create user",
            "error_code": "CREATE_FAILED",
        }

    # Generate tokens
    access_token_data = generate_access_token(user_id, organization_id, email)
    refresh_token_data = generate_refresh_token(user_id)

    return {
        "success": True,
        "user": user,
        "access_token": access_token_data["access_token"],
        "refresh_token": refresh_token_data["refresh_token"],
        "expires_in": access_token_data["expires_in"],
    }


def refresh_token(refresh_token: str) -> Dict[str, Any]:
    """
    Generate new access token from refresh token.

    Args:
        refresh_token: Valid JWT refresh token

    Returns:
        dict: {
            "success": bool,
            "access_token": str (if success),
            "expires_in": int (if success),
            "error": str (if failure),
            "error_code": str (if failure)
        }

    Example:
        >>> result = refresh_token(refresh_token="eyJ0eXAiOiJKV1QiLCJhbGc...")
        >>> if result["success"]:
        ...     print(result['access_token'])
    """
    # Verify refresh token
    verification = verify_token(refresh_token)

    if not verification["valid"]:
        return {
            "success": False,
            "error": verification["error"],
            "error_code": verification["error_code"],
        }

    # Check token type
    try:
        decoded = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if decoded.get("type") != "refresh":
            return {
                "success": False,
                "error": "Invalid token type",
                "error_code": "INVALID_TOKEN_TYPE",
            }

        # Generate new access token (minimal claims from refresh token)
        user_id = decoded["user_id"]

        # Note: refresh token may not have org_id/email, so generate minimal token
        # In production, you'd fetch user from database to get complete claims
        access_token_data = generate_access_token(
            user_id,
            decoded.get("org_id", ""),  # May be missing
            decoded.get("email", ""),  # May be missing
        )

        return {
            "success": True,
            "access_token": access_token_data["access_token"],
            "expires_in": access_token_data["expires_in"],
        }

    except jwt.InvalidTokenError:
        return {
            "success": False,
            "error": "Invalid refresh token",
            "error_code": "INVALID_TOKEN",
        }


def logout_user(user_id: str) -> Dict[str, Any]:
    """
    Logout user (invalidate refresh token).

    In a production system, this would:
    1. Add refresh token to revocation list
    2. Or update user record with last_logout timestamp

    For this example, we return a success message.
    Clients should discard tokens on logout.

    Args:
        user_id: User ID to logout

    Returns:
        dict: {
            "success": bool,
            "message": str
        }

    Example:
        >>> result = logout_user(user_id="user_abc123")
        >>> print(result['message'])
        Logged out successfully
    """
    # In production, add token to revocation list or update user record
    # For now, just return success
    return {"success": True, "message": "Logged out successfully"}
