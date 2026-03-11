"""
SaaS Starter Template - API Key Management

Simplified API key management with direct Python functions.

Functions:
- generate_api_key() - Generate secure API key
- hash_api_key(api_key) - Hash API key for storage
- create_api_key(db, organization_id, name, scopes) - Create API key
- verify_api_key(db, api_key) - Verify and return key info
- revoke_api_key(db, key_id) - Revoke API key
- list_organization_api_keys(db, organization_id) - List all keys
- validate_scopes(scopes, deduplicate=False) - Validate API key scopes

Architecture:
- Direct Python functions for key management logic
- Uses secrets module for secure key generation
- Uses hashlib for key hashing
- DataFlow workflows ONLY for database operations
- Simple, testable, fast functions
"""

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Valid API key scopes
VALID_SCOPES = {"read", "write", "admin", "delete"}


def generate_api_key() -> str:
    """
    Generate secure API key.

    Returns:
        Cryptographically secure random API key string

    Example:
        >>> api_key = generate_api_key()
        >>> len(api_key) >= 32
        True
    """
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """
    Hash API key for storage.

    Args:
        api_key: Plain API key

    Returns:
        SHA256 hash of API key

    Example:
        >>> hashed = hash_api_key("test_key_123")
        >>> len(hashed) == 64
        True
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def validate_scopes(scopes: List[str], deduplicate: bool = False) -> bool:
    """
    Validate API key scopes.

    Args:
        scopes: List of scope strings
        deduplicate: If True, allow duplicates (returns True regardless)

    Returns:
        True if all scopes are valid

    Raises:
        ValueError: If any scope is invalid

    Example:
        >>> validate_scopes(["read", "write"])
        True
        >>> validate_scopes(["read", "invalid"])
        Traceback (most recent call last):
        ...
        ValueError: Invalid scope: invalid_scope
    """
    for scope in scopes:
        if scope not in VALID_SCOPES:
            raise ValueError(f"Invalid scope: {scope}")
    return True


def create_api_key(db, organization_id: str, name: str, scopes: List[str]) -> Dict:
    """
    Create API key record.

    Args:
        db: DataFlow instance
        organization_id: Organization ID
        name: API key name
        scopes: List of scopes (read, write, admin, delete)

    Returns:
        dict: {
            "key": str (plain key, shown only once),
            "record": dict (database record)
        }

    Example:
        >>> result = create_api_key(db, "org_123", "Production Key", ["read", "write"])
        >>> print(result["key"])
        sk_abc123...
    """
    # Validate scopes
    validate_scopes(scopes)

    # Generate plain API key
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)

    # Generate key ID
    key_id = f"key_{uuid.uuid4().hex[:16]}"

    # Create API key record
    workflow = WorkflowBuilder()
    workflow.add_node(
        "APIKeyCreateNode",
        "create_key",
        {
            "id": key_id,
            "organization_id": organization_id,
            "name": name,
            "key_hash": key_hash,
            "scopes": scopes,
            "status": "active",
        },
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    record = results.get("create_key")

    return {"key": plain_key, "record": record}


def verify_api_key(db, api_key: str) -> Dict:
    """
    Verify API key and return key info.

    Args:
        db: DataFlow instance
        api_key: Plain API key to verify

    Returns:
        dict: {
            "valid": bool,
            "organization_id": str (if valid),
            "scopes": list (if valid),
            "rate_limit": int (if valid and has rate limit),
            "error": str (if invalid)
        }

    Example:
        >>> result = verify_api_key(db, "sk_abc123...")
        >>> if result["valid"]:
        ...     print(result["organization_id"])
        org_123
    """
    # Hash the key for lookup
    key_hash = hash_api_key(api_key)

    # Find API key by hash
    workflow = WorkflowBuilder()
    workflow.add_node(
        "APIKeyListNode", "list_keys", {"filters": {"key_hash": key_hash}, "limit": 1}
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    keys = results.get("list_keys", [])

    if not keys:
        return {"valid": False, "error": "API key not found"}

    key_record = keys[0]

    # Check if key is active
    if key_record.get("status") != "active":
        return {"valid": False, "error": "API key is revoked or inactive"}

    # Check if key is expired
    expires_at = key_record.get("expires_at")
    if expires_at and expires_at < datetime.now():
        return {"valid": False, "error": "API key has expired"}

    # Return key info
    result = {
        "valid": True,
        "organization_id": key_record["organization_id"],
        "scopes": key_record["scopes"],
    }

    # Include rate limit if present
    if "rate_limit" in key_record:
        result["rate_limit"] = key_record["rate_limit"]

    return result


def revoke_api_key(db, key_id: str) -> Optional[Dict]:
    """
    Revoke API key.

    Args:
        db: DataFlow instance
        key_id: API key ID to revoke

    Returns:
        Updated API key dict with status="revoked"

    Example:
        >>> key = revoke_api_key(db, "key_123")
        >>> print(key["status"])
        revoked
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "APIKeyUpdateNode",
        "update_key",
        {"filters": {"id": key_id}, "fields": {"status": "revoked"}},
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("update_key")


def list_organization_api_keys(db, organization_id: str) -> List[Dict]:
    """
    List organization API keys.

    Args:
        db: DataFlow instance
        organization_id: Organization ID

    Returns:
        List of API key dicts (without plain keys)

    Example:
        >>> keys = list_organization_api_keys(db, "org_123")
        >>> for key in keys:
        ...     print(key["name"])
        Production Key
        Dev Key
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "APIKeyListNode", "list_keys", {"filters": {"organization_id": organization_id}}
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("list_keys", [])
