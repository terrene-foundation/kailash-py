"""
Authentication Utilities for Kailash Middleware

Provides helper functions for authentication without circular dependencies.
"""

import base64
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple


def generate_secret_key(length: int = 32) -> str:
    """
    Generate a secure random secret key for HS256.

    Args:
        length: Length of the secret key (default: 32)

    Returns:
        URL-safe base64 encoded secret key
    """
    return secrets.token_urlsafe(length)


def generate_key_pair() -> Tuple[str, str]:
    """
    Generate RSA key pair for RS256.

    Returns:
        Tuple of (private_key_pem, public_key_pem)
    """
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )

        # Serialize private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        # Get public key
        public_key = private_key.public_key()

        # Serialize public key
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        return private_pem, public_pem

    except ImportError:
        raise ImportError(
            "RSA key generation requires 'cryptography' package. "
            "Install with: pip install cryptography"
        )


def calculate_token_expiry(
    token_type: str = "access", access_minutes: int = 15, refresh_days: int = 7
) -> datetime:
    """
    Calculate token expiration time.

    Args:
        token_type: Type of token ("access" or "refresh")
        access_minutes: Minutes until access token expires
        refresh_days: Days until refresh token expires

    Returns:
        Expiration datetime in UTC
    """
    now = datetime.now(timezone.utc)

    if token_type == "access":
        return now + timedelta(minutes=access_minutes)
    else:  # refresh
        return now + timedelta(days=refresh_days)


def is_token_expired(exp_timestamp: int) -> bool:
    """
    Check if token has expired based on exp claim.

    Args:
        exp_timestamp: Expiration timestamp from token

    Returns:
        True if token has expired
    """
    now = datetime.now(timezone.utc)
    exp_datetime = datetime.fromtimestamp(exp_timestamp, timezone.utc)
    return now > exp_datetime


def generate_jti() -> str:
    """
    Generate unique JWT ID.

    Returns:
        Unique identifier for JWT
    """
    return secrets.token_urlsafe(16)


def encode_for_jwks(number: int) -> str:
    """
    Encode integer for JWKS format.

    Args:
        number: Integer to encode (e.g., RSA modulus or exponent)

    Returns:
        Base64url encoded string without padding
    """
    byte_length = (number.bit_length() + 7) // 8
    number_bytes = number.to_bytes(byte_length, "big")
    return base64.urlsafe_b64encode(number_bytes).decode("ascii").rstrip("=")


def validate_algorithm(algorithm: str) -> bool:
    """
    Validate JWT algorithm.

    Args:
        algorithm: Algorithm name

    Returns:
        True if algorithm is supported
    """
    supported = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
    return algorithm in supported


def parse_bearer_token(authorization_header: str) -> Optional[str]:
    """
    Extract token from Authorization header.

    Args:
        authorization_header: Value of Authorization header

    Returns:
        Token string or None if invalid format
    """
    if not authorization_header:
        return None

    parts = authorization_header.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def generate_random_password(
    length: int = 16,
    include_uppercase: bool = True,
    include_lowercase: bool = True,
    include_digits: bool = True,
    include_symbols: bool = True,
) -> str:
    """
    Generate a random password.

    Args:
        length: Password length
        include_uppercase: Include uppercase letters
        include_lowercase: Include lowercase letters
        include_digits: Include digits
        include_symbols: Include symbols

    Returns:
        Random password string
    """
    characters = ""

    if include_uppercase:
        characters += string.ascii_uppercase
    if include_lowercase:
        characters += string.ascii_lowercase
    if include_digits:
        characters += string.digits
    if include_symbols:
        characters += string.punctuation

    if not characters:
        characters = string.ascii_letters + string.digits

    return "".join(secrets.choice(characters) for _ in range(length))


def hash_token_for_storage(token: str) -> str:
    """
    Hash token for secure storage (e.g., in blacklist).

    Args:
        token: JWT token to hash

    Returns:
        SHA256 hash of token
    """
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


def create_jwks_response(
    public_key_pem: str, key_id: str, algorithm: str = "RS256"
) -> Dict:
    """
    Create JWKS response for public key endpoint.

    Args:
        public_key_pem: Public key in PEM format
        key_id: Key identifier
        algorithm: Algorithm used

    Returns:
        JWKS formatted response
    """
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        # Load public key
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(), backend=default_backend()
        )

        # Get public numbers
        public_numbers = public_key.public_numbers()

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": key_id,
                    "use": "sig",
                    "alg": algorithm,
                    "n": encode_for_jwks(public_numbers.n),
                    "e": encode_for_jwks(public_numbers.e),
                }
            ]
        }
    except Exception:
        return {"keys": []}
