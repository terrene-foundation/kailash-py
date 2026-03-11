"""
API key authentication for metrics endpoint.

Prevents unauthorized access to /metrics endpoint by requiring API key authentication.
Addresses Finding #3 (CRITICAL): Unauthenticated HTTP Metrics Endpoint.

Security Features:
- API key authentication via X-API-Key header
- Key rotation support
- IP whitelist (optional)
- Rate limiting (optional)
- Audit logging
"""

import hashlib
import logging
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Set

from fastapi import FastAPI, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST

from ..builtin.metrics_hook import MetricsHook

logger = logging.getLogger(__name__)


@dataclass
class APIKey:
    """
    API key metadata.

    Example:
        >>> # Generate new API key
        >>> key = APIKey.generate(
        ...     name="prometheus-scraper",
        ...     owner="monitoring-team"
        ... )
        >>> print(f"API Key: {key.key}")
        >>> print(f"Hash: {key.key_hash}")
    """

    name: str
    key_hash: str  # SHA-256 hash of actual key
    owner: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def generate(
        cls,
        name: str,
        owner: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> tuple["APIKey", str]:
        """
        Generate new API key.

        Returns:
            Tuple of (APIKey instance, plaintext key)

        Note:
            Plaintext key is only available during generation.
            Store it securely - it cannot be recovered later.
        """
        # Generate random key (32 bytes = 256 bits)
        plaintext_key = secrets.token_urlsafe(32)

        # Hash key for storage
        key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()

        api_key = cls(
            name=name,
            key_hash=key_hash,
            owner=owner,
            metadata=metadata or {},
        )

        return api_key, plaintext_key

    def verify(self, plaintext_key: str) -> bool:
        """Verify plaintext key matches this API key."""
        key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
        return secrets.compare_digest(key_hash, self.key_hash)

    def mark_used(self) -> None:
        """Update last_used timestamp."""
        self.last_used = time.time()


class SecureMetricsEndpoint:
    """
    Secure HTTP /metrics endpoint with API key authentication.

    Prevents unauthorized access to Prometheus metrics by requiring
    X-API-Key header authentication.

    Example:
        >>> from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook
        >>> from kaizen.core.autonomy.hooks.security import SecureMetricsEndpoint
        >>>
        >>> # Create metrics hook
        >>> hook = MetricsHook()
        >>>
        >>> # Create secure endpoint
        >>> endpoint = SecureMetricsEndpoint(
        ...     metrics_hook=hook,
        ...     port=9090,
        ...     require_auth=True
        ... )
        >>>
        >>> # Generate API key
        >>> api_key, plaintext_key = endpoint.create_api_key(
        ...     name="prometheus",
        ...     owner="monitoring-team"
        ... )
        >>> print(f"Store this key securely: {plaintext_key}")
        >>>
        >>> # Start server
        >>> endpoint.start()  # Blocking call
        >>>
        >>> # Client usage:
        >>> # curl -H "X-API-Key: <plaintext_key>" http://localhost:9090/metrics
    """

    def __init__(
        self,
        metrics_hook: MetricsHook,
        port: int = 9090,
        require_auth: bool = True,
        allowed_ips: Optional[Set[str]] = None,
        enable_rate_limiting: bool = False,
        rate_limit: int = 100,  # requests per minute
    ):
        """
        Initialize secure metrics endpoint.

        Args:
            metrics_hook: MetricsHook instance to expose
            port: HTTP port (default: 9090)
            require_auth: If True, require X-API-Key header (default: True)
            allowed_ips: IP whitelist (None = allow all IPs)
            enable_rate_limiting: Enable rate limiting per IP
            rate_limit: Max requests per minute per IP (default: 100)
        """
        self.metrics_hook = metrics_hook
        self.port = port
        self.require_auth = require_auth
        self.allowed_ips = allowed_ips or set()
        self.enable_rate_limiting = enable_rate_limiting
        self.rate_limit = rate_limit

        # API key storage (key_hash -> APIKey)
        self._api_keys: dict[str, APIKey] = {}

        # Rate limiting state (ip -> [(timestamp, count)])
        self._rate_limit_state: dict[str, list[float]] = defaultdict(list)

        # Audit log
        self._audit_log: list[dict] = []

        # Create FastAPI app
        self.app = FastAPI(title="Kaizen Secure Metrics", version="1.0.0")

        # Register endpoints
        @self.app.get("/metrics")
        async def metrics(
            request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-Key")
        ):
            """
            Secure Prometheus metrics endpoint.

            Requires X-API-Key header authentication.

            Example:
                $ curl -H "X-API-Key: <key>" http://localhost:9090/metrics
            """
            # STEP 1: IP whitelist check
            client_ip = request.client.host
            if self.allowed_ips and client_ip not in self.allowed_ips:
                self._audit_log.append(
                    {
                        "timestamp": time.time(),
                        "event": "ip_rejected",
                        "ip": client_ip,
                        "reason": "not in whitelist",
                    }
                )
                raise HTTPException(status_code=403, detail="IP not allowed")

            # STEP 2: Rate limiting check
            if self.enable_rate_limiting:
                if not self._check_rate_limit(client_ip):
                    self._audit_log.append(
                        {
                            "timestamp": time.time(),
                            "event": "rate_limited",
                            "ip": client_ip,
                        }
                    )
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")

            # STEP 3: API key authentication
            if self.require_auth:
                if x_api_key is None:
                    self._audit_log.append(
                        {
                            "timestamp": time.time(),
                            "event": "auth_failed",
                            "ip": client_ip,
                            "reason": "missing api key",
                        }
                    )
                    raise HTTPException(
                        status_code=401, detail="X-API-Key header required"
                    )

                # Verify API key
                api_key = self._verify_api_key(x_api_key)
                if api_key is None:
                    self._audit_log.append(
                        {
                            "timestamp": time.time(),
                            "event": "auth_failed",
                            "ip": client_ip,
                            "reason": "invalid api key",
                        }
                    )
                    raise HTTPException(status_code=401, detail="Invalid API key")

                # Mark key as used
                api_key.mark_used()

                # Audit successful auth
                self._audit_log.append(
                    {
                        "timestamp": time.time(),
                        "event": "auth_success",
                        "ip": client_ip,
                        "api_key_name": api_key.name,
                        "api_key_owner": api_key.owner,
                    }
                )

            # STEP 4: Export metrics
            try:
                data = self.metrics_hook.export_prometheus()
                return Response(content=data, media_type=CONTENT_TYPE_LATEST)
            except Exception as e:
                logger.error(f"Error exporting metrics: {e}")
                # SECURITY: Don't leak error details (Finding #6)
                return Response(content="Internal server error", status_code=500)

        @self.app.get("/health")
        async def health():
            """Health check endpoint (no authentication required)."""
            return {"status": "healthy", "metrics": "available"}

    def create_api_key(
        self,
        name: str,
        owner: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> tuple[APIKey, str]:
        """
        Create new API key.

        Args:
            name: Human-readable name for key
            owner: Owner of key (e.g., team or service name)
            metadata: Additional metadata

        Returns:
            Tuple of (APIKey instance, plaintext key)

        Note:
            Plaintext key is only returned once. Store it securely.
        """
        api_key, plaintext_key = APIKey.generate(name, owner, metadata)
        self._api_keys[api_key.key_hash] = api_key

        logger.info(f"Created API key: {name} (owner: {owner})")

        return api_key, plaintext_key

    def revoke_api_key(self, key_hash: str) -> bool:
        """
        Revoke API key.

        Args:
            key_hash: Hash of key to revoke

        Returns:
            True if key was revoked
        """
        if key_hash in self._api_keys:
            api_key = self._api_keys[key_hash]
            del self._api_keys[key_hash]
            logger.info(f"Revoked API key: {api_key.name}")
            return True
        return False

    def _verify_api_key(self, plaintext_key: str) -> Optional[APIKey]:
        """
        Verify plaintext API key.

        Args:
            plaintext_key: Plaintext key from X-API-Key header

        Returns:
            APIKey if valid, None otherwise
        """
        key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()

        if key_hash in self._api_keys:
            return self._api_keys[key_hash]

        # Fallback: check all keys (for backwards compatibility)
        for api_key in self._api_keys.values():
            if api_key.verify(plaintext_key):
                return api_key

        return None

    def _check_rate_limit(self, ip: str) -> bool:
        """
        Check if IP is within rate limit.

        Args:
            ip: Client IP address

        Returns:
            True if request allowed, False if rate limited
        """
        now = time.time()
        minute_ago = now - 60

        # Clean old entries
        self._rate_limit_state[ip] = [
            ts for ts in self._rate_limit_state[ip] if ts > minute_ago
        ]

        # Check limit
        if len(self._rate_limit_state[ip]) >= self.rate_limit:
            return False

        # Add current request
        self._rate_limit_state[ip].append(now)
        return True

    def get_audit_log(self) -> list[dict]:
        """Get audit log of authentication attempts."""
        return self._audit_log.copy()

    def get_api_keys(self) -> list[APIKey]:
        """Get all API keys (without hashes)."""
        return list(self._api_keys.values())

    def start(self):
        """
        Start HTTP server (blocking).

        Example:
            >>> endpoint = SecureMetricsEndpoint(metrics_hook, port=9090)
            >>> endpoint.start()  # Runs forever
        """
        import uvicorn

        uvicorn.run(self.app, host="0.0.0.0", port=self.port)

    async def start_async(self):
        """
        Start HTTP server asynchronously.

        Example:
            >>> async with anyio.create_task_group() as tg:
            ...     tg.start_soon(endpoint.start_async)
        """
        import uvicorn

        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port)
        server = uvicorn.Server(config)
        await server.serve()


@dataclass
class MetricsAuthConfig:
    """
    Configuration for metrics endpoint authentication.

    Example:
        >>> config = MetricsAuthConfig(
        ...     require_api_key=True,
        ...     allowed_ip_ranges=["127.0.0.1/32"],
        ...     api_key_min_length=32
        ... )
        >>> config.valid_api_keys = {hashlib.sha256(b"secret").hexdigest()}
    """

    require_api_key: bool = True
    allowed_ip_ranges: list[str] = field(default_factory=list)
    api_key_min_length: int = 32
    valid_api_keys: set[str] = field(default_factory=set)
    enable_rate_limiting: bool = False
    rate_limit: int = 100  # requests per minute


class MetricsEndpoint:
    """
    Metrics endpoint with configurable authentication.

    Simpler alternative to SecureMetricsEndpoint for testing purposes.

    Example:
        >>> config = MetricsAuthConfig(require_api_key=True)
        >>> endpoint = MetricsEndpoint(auth_config=config)
        >>> is_auth = await endpoint._check_auth(
        ...     api_key="valid-key",
        ...     client_ip="127.0.0.1",
        ...     user_agent="pytest"
        ... )
    """

    def __init__(self, auth_config: MetricsAuthConfig):
        """
        Initialize metrics endpoint with auth config.

        Args:
            auth_config: Authentication configuration
        """
        self.auth_config = auth_config
        self._audit_log: list[dict] = []

    async def _check_auth(self, api_key: str, client_ip: str, user_agent: str) -> bool:
        """
        Check authentication for metrics access.

        Args:
            api_key: API key from X-API-Key header
            client_ip: Client IP address
            user_agent: User agent string

        Returns:
            True if authentication succeeds
        """
        # Step 1: IP whitelist check
        if self.auth_config.allowed_ip_ranges:
            # Simple IP matching (exact match or CIDR not implemented for simplicity)
            # In production, use ipaddress module for proper CIDR matching
            ip_allowed = False
            for allowed_range in self.auth_config.allowed_ip_ranges:
                if "/" in allowed_range:
                    # CIDR notation - extract base IP
                    base_ip = allowed_range.split("/")[0]
                    if client_ip == base_ip:
                        ip_allowed = True
                        break
                elif client_ip == allowed_range:
                    ip_allowed = True
                    break

            if not ip_allowed:
                self._audit_log.append(
                    {
                        "timestamp": time.time(),
                        "event": "ip_rejected",
                        "ip": client_ip,
                        "reason": "not in whitelist",
                    }
                )
                return False

        # Step 2: API key check
        if self.auth_config.require_api_key:
            if not api_key:
                self._audit_log.append(
                    {
                        "timestamp": time.time(),
                        "event": "auth_failed",
                        "ip": client_ip,
                        "reason": "missing api key",
                    }
                )
                return False

            # Check key length
            if len(api_key) < self.auth_config.api_key_min_length:
                self._audit_log.append(
                    {
                        "timestamp": time.time(),
                        "event": "auth_failed",
                        "ip": client_ip,
                        "reason": "api key too short",
                    }
                )
                return False

            # Check if key is valid
            if api_key not in self.auth_config.valid_api_keys:
                self._audit_log.append(
                    {
                        "timestamp": time.time(),
                        "event": "auth_failed",
                        "ip": client_ip,
                        "reason": "invalid api key",
                    }
                )
                return False

        # Success
        self._audit_log.append(
            {
                "timestamp": time.time(),
                "event": "auth_success",
                "ip": client_ip,
                "user_agent": user_agent,
            }
        )
        return True

    def get_audit_log(self) -> list[dict]:
        """Get audit log of authentication attempts."""
        return self._audit_log.copy()


__all__ = [
    "APIKey",
    "SecureMetricsEndpoint",
    "MetricsAuthConfig",
    "MetricsEndpoint",
]
