"""
OAuth 2.1 Authentication System for MCP.

This module implements a complete OAuth 2.1 authorization server and resource
server for MCP, following the latest OAuth 2.1 specification. It provides
secure authentication and authorization for MCP servers and clients.

Features:
- Complete OAuth 2.1 authorization server
- Dynamic client registration
- Multiple grant types (authorization code, client credentials)
- JWT access and refresh tokens
- Scope-based authorization
- PKCE support for public clients
- Token introspection and revocation
- Resource server middleware
- Well-known metadata endpoints

Examples:
    OAuth 2.1 Authorization Server:

    >>> from kailash.mcp_server.oauth import AuthorizationServer
    >>>
    >>> auth_server = AuthorizationServer(
    ...     issuer="https://auth.example.com",
    ...     private_key_path="private.pem",
    ...     client_store=InMemoryClientStore()
    ... )
    >>>
    >>> # Register client
    >>> client = await auth_server.register_client(
    ...     client_name="MCP Client",
    ...     redirect_uris=["http://localhost:8080/callback"],
    ...     grant_types=["authorization_code"],
    ...     scopes=["mcp.tools", "mcp.resources"]
    ... )

    Resource Server Integration:

    >>> from kailash.mcp_server.oauth import ResourceServer
    >>> from kailash.mcp_server import MCPServer
    >>>
    >>> resource_server = ResourceServer(
    ...     issuer="https://auth.example.com",
    ...     audience="mcp-api"
    ... )
    >>>
    >>> server = MCPServer("protected-server", auth_provider=resource_server)
    >>>
    >>> @server.tool(required_permission="mcp.tools")
    >>> def protected_tool():
    ...     return "Only accessible with proper token"

    Client Credentials Flow:

    >>> from kailash.mcp_server.oauth import OAuth2Client
    >>>
    >>> oauth_client = OAuth2Client(
    ...     client_id="client123",
    ...     client_secret="secret456",
    ...     token_endpoint="https://auth.example.com/token"
    ... )
    >>>
    >>> token = await oauth_client.get_client_credentials_token(
    ...     scopes=["mcp.tools", "mcp.resources"]
    ... )
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .auth import AuthProvider
from .errors import AuthenticationError, AuthorizationError, MCPError

logger = logging.getLogger(__name__)


class GrantType(Enum):
    """OAuth 2.1 grant types."""

    AUTHORIZATION_CODE = "authorization_code"
    CLIENT_CREDENTIALS = "client_credentials"
    REFRESH_TOKEN = "refresh_token"


class TokenType(Enum):
    """Token types."""

    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    ID_TOKEN = "id_token"


class ClientType(Enum):
    """OAuth client types."""

    CONFIDENTIAL = "confidential"
    PUBLIC = "public"


@dataclass
class OAuthClient:
    """OAuth 2.1 client registration."""

    client_id: str
    client_name: str = ""
    client_type: ClientType = ClientType.CONFIDENTIAL
    redirect_uris: List[str] = field(default_factory=list)
    grant_types: List[GrantType] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    client_secret: Optional[str] = None
    response_types: List[str] = field(default_factory=lambda: ["code"])
    token_endpoint_auth_method: str = "client_secret_basic"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = asdict(self)
        result["client_type"] = self.client_type.value
        result["grant_types"] = [gt.value for gt in self.grant_types]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthClient":
        """Create from dictionary format."""
        data = data.copy()
        data["client_type"] = ClientType(data["client_type"])
        data["grant_types"] = [GrantType(gt) for gt in data["grant_types"]]
        return cls(**data)

    def supports_grant_type(self, grant_type: GrantType) -> bool:
        """Check if client supports grant type."""
        return grant_type in self.grant_types

    def has_scope(self, scope: str) -> bool:
        """Check if client has scope."""
        return scope in self.scopes

    def validate_redirect_uri(self, redirect_uri: str) -> bool:
        """Validate redirect URI."""
        return redirect_uri in self.redirect_uris

    def is_valid_redirect_uri(self, redirect_uri: str) -> bool:
        """Validate redirect URI (alias for validate_redirect_uri)."""
        return redirect_uri in self.redirect_uris


@dataclass
class AccessToken:
    """OAuth 2.1 access token."""

    token: str
    client_id: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: Optional[str] = None
    scopes: Optional[List[str]] = None
    subject: Optional[str] = None
    user_id: Optional[str] = None  # Alias for subject
    audience: Optional[List[str]] = None
    issued_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    def __post_init__(self):
        # Handle user_id as alias for subject
        if self.user_id and not self.subject:
            self.subject = self.user_id
        elif self.subject and not self.user_id:
            self.user_id = self.subject

        # Set expires_at if not provided
        if self.expires_at is None:
            self.expires_at = self.issued_at + self.expires_in

        # Convert scopes list to scope string if needed
        if self.scopes and not self.scope:
            self.scope = " ".join(self.scopes)

    def is_expired(self) -> bool:
        """Check if token is expired."""
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "access_token": self.token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "scope": self.scope,
        }

    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope."""
        if self.scopes:
            return scope in self.scopes
        elif self.scope:
            return scope in self.scope.split()
        return False


@dataclass
class RefreshToken:
    """OAuth 2.1 refresh token."""

    token: str
    client_id: str
    subject: Optional[str] = None
    user_id: Optional[str] = None  # Alias for subject
    scope: Optional[str] = None
    scopes: Optional[List[str]] = None
    issued_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_revoked: bool = False

    def __post_init__(self):
        # Handle user_id as alias for subject
        if self.user_id and not self.subject:
            self.subject = self.user_id
        elif self.subject and not self.user_id:
            self.user_id = self.subject

        # Convert scopes list to scope string if needed
        if self.scopes and not self.scope:
            self.scope = " ".join(self.scopes)

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def revoke(self) -> None:
        """Revoke the refresh token."""
        self.is_revoked = True


@dataclass
class AuthorizationCode:
    """OAuth 2.1 authorization code."""

    code: str
    client_id: str
    redirect_uri: str
    scope: Optional[str] = None
    scopes: Optional[List[str]] = None
    subject: Optional[str] = None
    user_id: Optional[str] = None  # Alias for subject
    code_challenge: Optional[str] = None
    code_challenge_method: Optional[str] = None
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 600)  # 10 minutes

    def __post_init__(self):
        # Handle user_id as alias for subject
        if self.user_id and not self.subject:
            self.subject = self.user_id
        elif self.subject and not self.user_id:
            self.user_id = self.subject

        # Convert scopes list to scope string if needed
        if self.scopes and not self.scope:
            self.scope = " ".join(self.scopes)

    def is_expired(self) -> bool:
        """Check if code is expired."""
        return time.time() > self.expires_at

    def validate_pkce(self, code_verifier: str) -> bool:
        """Validate PKCE code verifier."""
        if not self.code_challenge:
            return True  # PKCE not used

        if self.code_challenge_method == "S256":
            # SHA256 challenge method
            verifier_hash = hashlib.sha256(code_verifier.encode()).digest()
            verifier_challenge = (
                base64.urlsafe_b64encode(verifier_hash).decode().rstrip("=")
            )
            return verifier_challenge == self.code_challenge
        elif self.code_challenge_method == "plain":
            # Plain challenge method
            return code_verifier == self.code_challenge
        else:
            return False


class ClientStore(ABC):
    """Abstract base class for OAuth client storage."""

    @abstractmethod
    async def store_client(self, client: OAuthClient) -> None:
        """Store OAuth client."""
        pass

    @abstractmethod
    async def get_client(self, client_id: str) -> Optional[OAuthClient]:
        """Get OAuth client by ID."""
        pass

    @abstractmethod
    async def delete_client(self, client_id: str) -> bool:
        """Delete OAuth client."""
        pass

    @abstractmethod
    async def list_clients(self) -> List[OAuthClient]:
        """List all OAuth clients."""
        pass


class InMemoryClientStore(ClientStore):
    """In-memory OAuth client store."""

    def __init__(self):
        """Initialize in-memory store."""
        self._clients: Dict[str, OAuthClient] = {}

    async def store_client(self, client: OAuthClient) -> None:
        """Store OAuth client."""
        self._clients[client.client_id] = client

    async def get_client(self, client_id: str) -> Optional[OAuthClient]:
        """Get OAuth client by ID."""
        return self._clients.get(client_id)

    async def delete_client(self, client_id: str) -> bool:
        """Delete OAuth client."""
        if client_id in self._clients:
            del self._clients[client_id]
            return True
        return False

    async def list_clients(self) -> List[OAuthClient]:
        """List all OAuth clients."""
        return list(self._clients.values())

    async def authenticate_client(
        self, client_id: str, client_secret: str
    ) -> Optional[OAuthClient]:
        """Authenticate OAuth client."""
        client = await self.get_client(client_id)
        if client and client.client_secret == client_secret:
            return client
        return None


class TokenStore(ABC):
    """Abstract base class for token storage."""

    @abstractmethod
    async def store_access_token(self, token: AccessToken) -> None:
        """Store access token."""
        pass

    @abstractmethod
    async def get_access_token(self, token: str) -> Optional[AccessToken]:
        """Get access token."""
        pass

    @abstractmethod
    async def revoke_access_token(self, token: str) -> bool:
        """Revoke access token."""
        pass

    @abstractmethod
    async def store_refresh_token(self, token: RefreshToken) -> None:
        """Store refresh token."""
        pass

    @abstractmethod
    async def get_refresh_token(self, token: str) -> Optional[RefreshToken]:
        """Get refresh token."""
        pass

    @abstractmethod
    async def revoke_refresh_token(self, token: str) -> bool:
        """Revoke refresh token."""
        pass

    @abstractmethod
    async def store_authorization_code(self, code: AuthorizationCode) -> None:
        """Store authorization code."""
        pass

    @abstractmethod
    async def get_authorization_code(self, code: str) -> Optional[AuthorizationCode]:
        """Get authorization code."""
        pass

    @abstractmethod
    async def consume_authorization_code(
        self, code: str
    ) -> Optional[AuthorizationCode]:
        """Consume authorization code (get and delete)."""
        pass


class InMemoryTokenStore(TokenStore):
    """In-memory token store."""

    def __init__(self):
        """Initialize in-memory store."""
        self._access_tokens: Dict[str, AccessToken] = {}
        self._refresh_tokens: Dict[str, RefreshToken] = {}
        self._authorization_codes: Dict[str, AuthorizationCode] = {}

    async def store_access_token(self, token: AccessToken) -> None:
        """Store access token."""
        self._access_tokens[token.token] = token

    async def get_access_token(self, token: str) -> Optional[AccessToken]:
        """Get access token."""
        access_token = self._access_tokens.get(token)
        if access_token and access_token.is_expired():
            del self._access_tokens[token]
            return None
        return access_token

    async def revoke_access_token(self, token: str) -> bool:
        """Revoke access token."""
        if token in self._access_tokens:
            del self._access_tokens[token]
            return True
        return False

    async def store_refresh_token(self, token: RefreshToken) -> None:
        """Store refresh token."""
        self._refresh_tokens[token.token] = token

    async def get_refresh_token(self, token: str) -> Optional[RefreshToken]:
        """Get refresh token."""
        refresh_token = self._refresh_tokens.get(token)
        if refresh_token and refresh_token.is_expired():
            del self._refresh_tokens[token]
            return None
        return refresh_token

    async def revoke_refresh_token(self, token: str) -> bool:
        """Revoke refresh token."""
        if token in self._refresh_tokens:
            del self._refresh_tokens[token]
            return True
        return False

    async def store_authorization_code(self, code: AuthorizationCode) -> None:
        """Store authorization code."""
        self._authorization_codes[code.code] = code

    async def get_authorization_code(self, code: str) -> Optional[AuthorizationCode]:
        """Get authorization code."""
        auth_code = self._authorization_codes.get(code)
        if auth_code and auth_code.is_expired():
            del self._authorization_codes[code]
            return None
        return auth_code

    async def consume_authorization_code(
        self, code: str
    ) -> Optional[AuthorizationCode]:
        """Consume authorization code."""
        auth_code = await self.get_authorization_code(code)
        if auth_code:
            del self._authorization_codes[code]
        return auth_code


class JWTManager:
    """JWT token manager for OAuth 2.1."""

    def __init__(
        self,
        private_key: Optional[str] = None,
        public_key: Optional[str] = None,
        algorithm: str = "RS256",
        issuer: Optional[str] = None,
        private_key_pem: Optional[str] = None,  # Backward compatibility
        public_key_pem: Optional[str] = None,  # Backward compatibility
    ):
        """Initialize JWT manager.

        Args:
            private_key: Private key for signing (PEM format)
            public_key: Public key for verification (PEM format)
            algorithm: JWT algorithm
            issuer: Token issuer
        """
        self.algorithm = algorithm
        self.issuer = issuer

        # Handle backward compatibility
        private_key = private_key or private_key_pem
        public_key = public_key or public_key_pem

        if private_key:
            self.private_key = serialization.load_pem_private_key(
                private_key.encode(), password=None
            )
        else:
            # Generate key pair
            self.private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )

        if public_key:
            self.public_key = serialization.load_pem_public_key(public_key.encode())
        else:
            self.public_key = self.private_key.public_key()

    def create_access_token(
        self,
        subject: Optional[Union[str, Dict[str, Any]]] = None,
        client_id: Optional[str] = None,
        scope: Optional[str] = None,
        audience: Optional[List[str]] = None,
        expires_in: int = 3600,
    ) -> Union[AccessToken, str]:
        """Create JWT access token.

        Args:
            subject: Token subject (user ID)
            client_id: OAuth client ID
            scope: Token scope
            audience: Token audience
            expires_in: Token lifetime in seconds

        Returns:
            Access token
        """
        # Handle dictionary input for backward compatibility
        token_data_dict = None
        if isinstance(subject, dict):
            token_data_dict = subject
            subject = token_data_dict.get("user_id")
            client_id = token_data_dict.get("client_id", client_id)
            scope = token_data_dict.get("scope")
            if not scope and "scopes" in token_data_dict:
                scope = " ".join(token_data_dict["scopes"])
            audience = token_data_dict.get("audience", audience)
            expires_in = token_data_dict.get("expires_in", expires_in)

        now = time.time()
        expires_at = now + expires_in

        payload = {
            "iss": self.issuer,
            "iat": int(now),
            "exp": int(expires_at),
            "jti": str(uuid.uuid4()),
            "token_type": "access_token",
        }

        if subject:
            payload["sub"] = subject
        if client_id:
            payload["client_id"] = client_id
        if scope:
            payload["scope"] = scope
        if audience:
            payload["aud"] = audience

        # Add custom claims from token_data if it was a dict
        if token_data_dict:
            for key in ["user_id", "scopes"]:
                if key in token_data_dict and key not in [
                    "client_id",
                    "scope",
                    "audience",
                    "expires_in",
                ]:
                    payload[key] = token_data_dict[key]

        token = jwt.encode(payload, self.private_key, algorithm=self.algorithm)

        # For backward compatibility, return string if called with dict
        if token_data_dict:
            return token

        return AccessToken(
            token=token,
            expires_in=expires_in,
            scope=scope,
            client_id=client_id,
            subject=subject,
            audience=audience,
            issued_at=now,
            expires_at=expires_at,
        )

    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT access token.

        Args:
            token: JWT token to verify

        Returns:
            Token payload or None if invalid
        """
        try:
            payload = jwt.decode(token, self.public_key, algorithms=[self.algorithm])

            # Verify token type
            if payload.get("token_type") != "access_token":
                return None

            return payload

        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")

    def create_refresh_token(
        self,
        token_data: Union[Dict[str, Any], str],
        expires_in: int = 2592000,  # 30 days
    ) -> str:
        """Create JWT refresh token.

        Args:
            token_data: Token data dict or client ID
            expires_in: Token lifetime in seconds

        Returns:
            JWT refresh token string
        """
        now = time.time()
        expires_at = now + expires_in

        payload = {
            "iss": self.issuer,
            "iat": int(now),
            "exp": int(expires_at),
            "jti": str(uuid.uuid4()),
            "token_type": "refresh_token",
        }

        if isinstance(token_data, dict):
            if "client_id" in token_data:
                payload["client_id"] = token_data["client_id"]
            if "user_id" in token_data:
                payload["sub"] = token_data["user_id"]
                payload["user_id"] = token_data["user_id"]
        else:
            payload["client_id"] = token_data

        return jwt.encode(payload, self.private_key, algorithm=self.algorithm)

    def verify_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT refresh token.

        Args:
            token: JWT token to verify

        Returns:
            Token payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.algorithm],
                options={"verify_aud": False},
            )

            # Check token type
            if payload.get("token_type") != "refresh_token":
                raise AuthenticationError("Invalid token type")

            # Check issuer
            if self.issuer and payload.get("iss") != self.issuer:
                raise AuthenticationError("Invalid issuer")

            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None

    def get_public_key_jwks(self) -> Dict[str, Any]:
        """Get public key in JWKS format.

        Returns:
            JWKS public key
        """
        public_numbers = self.public_key.public_numbers()

        # Convert to base64url encoding
        def int_to_base64url(value: int) -> str:
            byte_length = (value.bit_length() + 7) // 8
            bytes_value = value.to_bytes(byte_length, byteorder="big")
            return base64.urlsafe_b64encode(bytes_value).decode().rstrip("=")

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": self.algorithm,
                    "n": int_to_base64url(public_numbers.n),
                    "e": int_to_base64url(public_numbers.e),
                }
            ]
        }


class AuthorizationServer:
    """OAuth 2.1 Authorization Server."""

    def __init__(
        self,
        issuer: str,
        client_store: Optional[ClientStore] = None,
        token_store: Optional[TokenStore] = None,
        jwt_manager: Optional[JWTManager] = None,
        default_scopes: Optional[List[str]] = None,
        private_key_path: Optional[str] = None,  # For backward compatibility
    ):
        """Initialize authorization server.

        Args:
            issuer: Server issuer URL
            client_store: Client storage
            token_store: Token storage
            jwt_manager: JWT manager
            default_scopes: Default scopes
        """
        self.issuer = issuer
        self.client_store = client_store or InMemoryClientStore()
        self.token_store = token_store or InMemoryTokenStore()

        # Create JWT manager with private key if provided
        if jwt_manager:
            self.jwt_manager = jwt_manager
        elif private_key_path:
            # Read private key from file
            try:
                with open(private_key_path, "r") as f:
                    private_key = f.read()
                self.jwt_manager = JWTManager(issuer=issuer, private_key=private_key)
            except FileNotFoundError:
                # For testing, create a default JWT manager
                self.jwt_manager = JWTManager(issuer=issuer)
        else:
            self.jwt_manager = JWTManager(issuer=issuer)

        self.default_scopes = default_scopes or ["mcp.basic"]

    async def register_client(
        self,
        client_name: str,
        redirect_uris: Optional[List[str]] = None,
        grant_types: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None,
        client_type: Optional[str] = None,
        **metadata,
    ) -> OAuthClient:
        """Register OAuth client.

        Args:
            client_name: Client name
            redirect_uris: Redirect URIs
            grant_types: Allowed grant types
            scopes: Allowed scopes
            client_type: Client type (confidential/public)
            **metadata: Additional metadata

        Returns:
            Registered client
        """
        client_id = f"client_{uuid.uuid4().hex[:16]}"

        # Determine client type
        if client_type:
            client_type_enum = ClientType(client_type)
        else:
            # Default to confidential
            client_type_enum = ClientType.CONFIDENTIAL

        # Generate client secret for confidential clients
        client_secret = None
        if client_type_enum == ClientType.CONFIDENTIAL:
            client_secret = secrets.token_urlsafe(32)

        # Parse grant types
        grant_type_enums = []
        if grant_types:
            grant_type_enums = [GrantType(gt) for gt in grant_types]
        else:
            grant_type_enums = [GrantType.AUTHORIZATION_CODE]

        # Use default scopes if not provided
        if not scopes:
            scopes = self.default_scopes.copy()

        # Default redirect URIs for certain grant types
        if not redirect_uris:
            redirect_uris = []

        client = OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            client_name=client_name,
            client_type=client_type_enum,
            redirect_uris=redirect_uris,
            grant_types=grant_type_enums,
            scopes=scopes,
            metadata=metadata,
        )

        await self.client_store.store_client(client)

        logger.info(f"Registered OAuth client: {client_name} ({client_id})")
        return client

    async def create_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> str:
        """Create authorization URL.

        Args:
            client_id: OAuth client ID
            redirect_uri: Redirect URI
            scope: Requested scope
            state: State parameter
            code_challenge: PKCE code challenge
            code_challenge_method: PKCE challenge method

        Returns:
            Authorization URL
        """
        # Validate client
        client = await self.client_store.get_client(client_id)
        if not client:
            raise AuthorizationError("Invalid client")

        if not client.validate_redirect_uri(redirect_uri):
            raise AuthorizationError("Invalid redirect URI")

        # Build authorization URL parameters
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }

        if scope:
            params["scope"] = scope
        if state:
            params["state"] = state
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        query_string = urlencode(params)
        return f"{self.issuer}/authorize?{query_string}"

    async def generate_authorization_code(
        self,
        client_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
    ) -> str:
        """Generate authorization code for the user.

        Args:
            client_id: OAuth client ID
            user_id: User ID
            redirect_uri: Redirect URI
            scopes: Requested scopes
            state: State parameter
            code_challenge: PKCE code challenge
            code_challenge_method: PKCE challenge method

        Returns:
            Authorization code
        """
        # Validate client
        client = await self.client_store.get_client(client_id)
        if not client:
            raise AuthorizationError("Invalid client")

        if not client.validate_redirect_uri(redirect_uri):
            raise AuthorizationError("Invalid redirect URI")

        # Convert scopes list to string
        scope = " ".join(scopes) if scopes else None

        # Create authorization code
        auth_code = AuthorizationCode(
            code=secrets.token_urlsafe(32),
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            scopes=scopes,
            subject=user_id,
            user_id=user_id,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

        await self.token_store.store_authorization_code(auth_code)

        return auth_code.code

    async def exchange_authorization_code(
        self,
        client_id: str,
        client_secret: Optional[str],
        code: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchange authorization code for tokens.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            code: Authorization code
            redirect_uri: Redirect URI
            code_verifier: PKCE code verifier

        Returns:
            Token response
        """
        # Validate client
        client = await self.client_store.get_client(client_id)
        if not client:
            raise AuthorizationError("Invalid client")

        # Validate client secret for confidential clients
        if client.client_type == ClientType.CONFIDENTIAL:
            if not client_secret or client_secret != client.client_secret:
                raise AuthorizationError("Invalid client credentials")

        # Get and consume authorization code
        auth_code = await self.token_store.consume_authorization_code(code)
        if not auth_code:
            raise AuthorizationError("Invalid or expired authorization code")

        # Validate authorization code
        if auth_code.client_id != client_id:
            raise AuthorizationError("Authorization code mismatch")

        if auth_code.redirect_uri != redirect_uri:
            raise AuthorizationError("Redirect URI mismatch")

        # Validate PKCE if used
        if auth_code.code_challenge:
            if not code_verifier:
                raise AuthorizationError("Code verifier required")

            if not auth_code.validate_pkce(code_verifier):
                raise AuthorizationError("Invalid code verifier")

        # Create access token
        access_token_jwt = self.jwt_manager.create_access_token(
            subject=auth_code.subject,
            client_id=client_id,
            scope=auth_code.scope,
            audience=["mcp-api"],
        )

        # Create AccessToken object if JWT string was returned
        if isinstance(access_token_jwt, str):
            access_token = AccessToken(
                token=access_token_jwt,
                client_id=client_id,
                subject=auth_code.subject,
                user_id=auth_code.user_id,
                scope=auth_code.scope,
                scopes=auth_code.scopes,
            )
        else:
            access_token = access_token_jwt

        # Create refresh token JWT
        refresh_token_jwt = self.jwt_manager.create_refresh_token(
            {"client_id": client_id, "user_id": auth_code.subject}
        )

        # Create RefreshToken object
        refresh_token = RefreshToken(
            token=refresh_token_jwt,
            client_id=client_id,
            subject=auth_code.subject,
            scope=auth_code.scope,
        )

        # Store tokens
        await self.token_store.store_access_token(access_token)
        await self.token_store.store_refresh_token(refresh_token)

        response = access_token.to_dict()
        response["refresh_token"] = refresh_token.token

        return response

    async def client_credentials_grant(
        self, client_id: str, client_secret: str, scopes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Handle client credentials grant.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            scopes: Requested scopes

        Returns:
            Token response
        """
        # Validate client
        client = await self.client_store.get_client(client_id)
        if not client:
            raise AuthorizationError("Invalid client")

        if not client.supports_grant_type(GrantType.CLIENT_CREDENTIALS):
            raise AuthorizationError("Grant type not supported")

        # Validate client secret
        if client_secret != client.client_secret:
            raise AuthorizationError("Invalid client credentials")

        # Validate scope
        scope = None
        if scopes:
            for requested_scope in scopes:
                if not client.has_scope(requested_scope):
                    raise AuthorizationError(f"Invalid scope: {requested_scope}")
            scope = " ".join(scopes)

        # Create access token
        access_token_jwt = self.jwt_manager.create_access_token(
            client_id=client_id, scope=scope, audience=["mcp-api"]
        )

        # Create AccessToken object if JWT string was returned
        if isinstance(access_token_jwt, str):
            access_token = AccessToken(
                token=access_token_jwt,
                client_id=client_id,
                scope=scope,
                scopes=scopes,
            )
        else:
            access_token = access_token_jwt

        # Store token
        await self.token_store.store_access_token(access_token)

        return access_token.to_dict()

    async def refresh_token_grant(
        self, client_id: str, client_secret: Optional[str], refresh_token: str
    ) -> Dict[str, Any]:
        """Handle refresh token grant.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            refresh_token: Refresh token

        Returns:
            Token response
        """
        # Validate client
        client = await self.client_store.get_client(client_id)
        if not client:
            raise AuthorizationError("Invalid client")

        # Validate client secret for confidential clients
        if client.client_type == ClientType.CONFIDENTIAL:
            if not client_secret or client_secret != client.client_secret:
                raise AuthorizationError("Invalid client credentials")

        # First try to verify the refresh token as JWT
        try:
            token_data = self.jwt_manager.verify_refresh_token(refresh_token)
            if token_data:
                # Create RefreshToken object from JWT data
                refresh_token_obj = RefreshToken(
                    token=refresh_token,
                    client_id=token_data.get("client_id", client_id),
                    subject=token_data.get("sub") or token_data.get("user_id"),
                    user_id=token_data.get("user_id") or token_data.get("sub"),
                    scope=(
                        " ".join(token_data.get("scopes", []))
                        if token_data.get("scopes")
                        else None
                    ),
                    scopes=token_data.get("scopes"),
                )
        except:
            # Fall back to token store
            refresh_token_obj = await self.token_store.get_refresh_token(refresh_token)
            if not refresh_token_obj:
                raise AuthorizationError("Invalid refresh token")

        if refresh_token_obj.client_id != client_id:
            raise AuthorizationError("Client mismatch")

        # Create new access token
        access_token_jwt = self.jwt_manager.create_access_token(
            subject=refresh_token_obj.subject,
            client_id=client_id,
            scope=refresh_token_obj.scope,
            audience=["mcp-api"],
        )

        # Create AccessToken object if JWT string was returned
        if isinstance(access_token_jwt, str):
            access_token = AccessToken(
                token=access_token_jwt,
                client_id=client_id,
                subject=refresh_token_obj.subject,
                user_id=refresh_token_obj.user_id,
                scope=refresh_token_obj.scope,
                scopes=(
                    refresh_token_obj.scopes
                    if hasattr(refresh_token_obj, "scopes")
                    else None
                ),
            )
        else:
            access_token = access_token_jwt

        # Store new access token
        await self.token_store.store_access_token(access_token)

        return access_token.to_dict()

    async def introspect_token(self, token: str) -> Dict[str, Any]:
        """Introspect token.

        Args:
            token: Token to introspect

        Returns:
            Token introspection response
        """
        try:
            # Try to verify as JWT access token
            payload = self.jwt_manager.verify_access_token(token)
            if payload:
                # Extract token information from JWT payload
                client_id = payload.get("client_id")
                scope = payload.get("scope", "")
                exp = payload.get("exp")
                iat = payload.get("iat", time.time())
                sub = payload.get("sub") or payload.get("user_id")
                aud = payload.get("aud", [])

                # Get scopes from payload
                scopes = payload.get("scopes", [])
                if not scopes and scope:
                    scopes = scope.split()

                return {
                    "active": True,
                    "client_id": client_id,
                    "scope": " ".join(scopes) if scopes else scope,
                    "exp": exp,
                    "iat": iat,
                    "sub": sub,
                    "aud": aud,
                    "token_type": "access_token",
                }
        except AuthenticationError:
            # Token is invalid or expired
            pass

        return {"active": False}

    async def revoke_token(
        self,
        token: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> bool:
        """Revoke token.

        Args:
            token: Token to revoke
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Returns:
            True if revoked successfully
        """
        # If client_id is provided, validate client
        if client_id:
            client = await self.client_store.get_client(client_id)
            if not client:
                return False

            # Validate client secret for confidential clients
            if client.client_type == ClientType.CONFIDENTIAL:
                if not client_secret or client_secret != client.client_secret:
                    return False

        # Try to revoke as access token
        if await self.token_store.revoke_access_token(token):
            return True

        # Try to revoke as refresh token
        return await self.token_store.revoke_refresh_token(token)

    async def refresh_access_token(
        self, client_id: str, client_secret: Optional[str], refresh_token: str
    ) -> Dict[str, Any]:
        """Refresh access token (alias for refresh_token_grant).

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            refresh_token: Refresh token

        Returns:
            Token response
        """
        return await self.refresh_token_grant(client_id, client_secret, refresh_token)

    def get_well_known_metadata(self) -> Dict[str, Any]:
        """Get well-known authorization server metadata.

        Returns:
            Authorization server metadata
        """
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "introspection_endpoint": f"{self.issuer}/introspect",
            "revocation_endpoint": f"{self.issuer}/revoke",
            "jwks_uri": f"{self.issuer}/.well-known/jwks.json",
            "registration_endpoint": f"{self.issuer}/register",
            "scopes_supported": self.default_scopes,
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "client_credentials",
                "refresh_token",
            ],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
            ],
            "code_challenge_methods_supported": ["S256", "plain"],
        }


class ResourceServer:
    """OAuth 2.1 Resource Server for MCP."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwt_manager: Optional[JWTManager] = None,
        required_scopes: Optional[List[str]] = None,
    ):
        """Initialize resource server.

        Args:
            issuer: Authorization server issuer
            audience: Expected token audience
            jwt_manager: JWT manager for token verification
            required_scopes: Required scopes for access
        """
        self.issuer = issuer
        self.audience = audience
        self.jwt_manager = jwt_manager or JWTManager(issuer=issuer)
        self.required_scopes = required_scopes or []

    async def authenticate(
        self, credentials: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Authenticate using OAuth 2.1 access token.

        Args:
            credentials: Token string or dict with 'token' key

        Returns:
            Authentication result
        """
        # Handle both string and dict inputs
        if isinstance(credentials, str):
            token = credentials
        else:
            token = credentials.get("token")
            if not token:
                raise AuthenticationError("No token provided")

        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        # Verify JWT token
        payload = self.jwt_manager.verify_access_token(token)
        if not payload:
            raise AuthenticationError("Invalid token")

        # Check audience
        token_audience = payload.get("aud", [])
        if isinstance(token_audience, str):
            token_audience = [token_audience]

        if self.audience not in token_audience:
            raise AuthorizationError("Invalid token audience")

        # Check required scopes
        token_scope = payload.get("scope", "")
        token_scopes = token_scope.split() if token_scope else []

        for required_scope in self.required_scopes:
            if required_scope not in token_scopes:
                raise AuthenticationError(f"Missing required scope: {required_scope}")

        return {
            "id": payload.get("sub") or payload.get("client_id"),
            "client_id": payload.get("client_id"),
            "subject": payload.get("sub"),
            "user_id": payload.get("sub") or payload.get("user_id"),
            "scopes": token_scopes,
            "token_type": "Bearer",
        }

    async def check_permission(
        self, auth_info: Dict[str, Any], required_permission: str
    ) -> None:
        """Check if authenticated entity has required permission.

        Args:
            auth_info: Authentication information from authenticate()
            required_permission: Required permission/scope

        Raises:
            AuthorizationError: If permission is missing
        """
        scopes = auth_info.get("scopes", [])
        if required_permission not in scopes:
            raise AuthorizationError(
                f"Missing required permission: {required_permission}"
            )

    async def get_headers(self) -> Dict[str, str]:
        """Get headers for authentication (empty for resource server).

        Returns:
            Empty dict as resource server doesn't add headers
        """
        return {}


class OAuth2Client:
    """OAuth 2.1 client for MCP."""

    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
        token_endpoint: Optional[str] = None,
        authorization_endpoint: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        """Initialize OAuth 2.1 client.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            token_endpoint: Token endpoint URL
            authorization_endpoint: Authorization endpoint URL
            redirect_uri: Redirect URI
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = token_endpoint
        self.authorization_endpoint = authorization_endpoint
        self.redirect_uri = redirect_uri

        # Token storage
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

    async def get_client_credentials_token(
        self, scopes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get access token using client credentials grant.

        Args:
            scopes: Requested scopes

        Returns:
            Token response dict
        """
        if not self.token_endpoint:
            raise AuthenticationError("Token endpoint not configured")

        if not self.client_secret:
            raise AuthenticationError("Client secret required for client credentials")

        # Prepare token request
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        if scopes:
            data["scope"] = " ".join(scopes)

        # Make token request
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AuthenticationError(f"Token request failed: {error_text}")

                token_response = await response.json()

        # Store token information
        self._access_token = token_response["access_token"]
        self._refresh_token = token_response.get("refresh_token")

        expires_in = token_response.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in

        return token_response

    def get_authorization_url(
        self,
        scopes: Optional[List[str]] = None,
        state: Optional[str] = None,
        use_pkce: bool = True,
    ) -> Tuple[str, Optional[str]]:
        """Get authorization URL for authorization code flow.

        Args:
            scopes: Requested scopes
            state: State parameter
            use_pkce: Use PKCE for security

        Returns:
            Tuple of (authorization_url, code_verifier)
        """
        if not self.authorization_endpoint:
            raise AuthenticationError("Authorization endpoint not configured")

        if not self.redirect_uri:
            raise AuthenticationError("Redirect URI not configured")

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }

        if scopes:
            params["scope"] = " ".join(scopes)

        if state:
            params["state"] = state

        code_verifier = None
        if use_pkce:
            # Generate PKCE parameters
            code_verifier = (
                base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
            )
            code_challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                )
                .decode()
                .rstrip("=")
            )

            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        query_string = urlencode(params)
        authorization_url = f"{self.authorization_endpoint}?{query_string}"

        return authorization_url, code_verifier

    async def exchange_authorization_code(
        self, code: str, code_verifier: Optional[str] = None
    ) -> str:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code
            code_verifier: PKCE code verifier

        Returns:
            Access token
        """
        if not self.token_endpoint:
            raise AuthenticationError("Token endpoint not configured")

        if not self.redirect_uri:
            raise AuthenticationError("Redirect URI not configured")

        # Prepare token request
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        if code_verifier:
            data["code_verifier"] = code_verifier

        # Make token request
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AuthenticationError(f"Token exchange failed: {error_text}")

                token_response = await response.json()

        # Store token information
        self._access_token = token_response["access_token"]
        self._refresh_token = token_response.get("refresh_token")

        expires_in = token_response.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in

        return token_response

    async def get_valid_token(self) -> Optional[str]:
        """Get valid access token, refreshing if necessary.

        Returns:
            Valid access token or None
        """
        # Check if current token is valid
        if self._access_token and self._token_expires_at:
            if time.time() < self._token_expires_at - 60:  # 1 minute buffer
                return self._access_token

        # Try to refresh token
        if self._refresh_token:
            try:
                return await self._refresh_access_token()
            except Exception as e:
                logger.error(f"Token refresh failed: {e}")

        return None

    async def _refresh_access_token(self) -> str:
        """Refresh access token using refresh token.

        Returns:
            New access token
        """
        if not self.token_endpoint or not self._refresh_token:
            raise AuthenticationError("Cannot refresh token")

        # Prepare refresh request
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self._refresh_token,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        # Make refresh request
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AuthenticationError(f"Token refresh failed: {error_text}")

                token_response = await response.json()

        # Update token information
        self._access_token = token_response["access_token"]

        # Update refresh token if provided
        if "refresh_token" in token_response:
            self._refresh_token = token_response["refresh_token"]

        expires_in = token_response.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in

        return self._access_token

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token.

        Args:
            refresh_token: Refresh token

        Returns:
            Token response
        """
        if not self.token_endpoint:
            raise AuthenticationError("Token endpoint not configured")

        # Prepare token request
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        # Make token request
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    error_data = await response.json()
                    error = error_data.get("error", "unknown_error")
                    error_description = error_data.get(
                        "error_description", "Token refresh failed"
                    )
                    raise AuthenticationError(f"{error}: {error_description}")

                token_response = await response.json()

        # Store token information
        self._access_token = token_response["access_token"]
        self._refresh_token = token_response.get("refresh_token", refresh_token)

        expires_in = token_response.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in

        return token_response

    async def introspect_token(
        self, token: str, introspection_endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Introspect a token.

        Args:
            token: Token to introspect
            introspection_endpoint: Introspection endpoint URL

        Returns:
            Introspection response
        """
        if not introspection_endpoint and self.token_endpoint:
            # Try to derive introspection endpoint from token endpoint
            introspection_endpoint = self.token_endpoint.replace(
                "/token", "/introspect"
            )

        if not introspection_endpoint:
            raise AuthenticationError("Introspection endpoint not configured")

        data = {
            "token": token,
            "client_id": self.client_id,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(
                introspection_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise AuthenticationError(
                        f"Token introspection failed: {error_text}"
                    )

                return await response.json()
