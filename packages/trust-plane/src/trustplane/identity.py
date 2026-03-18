# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OIDC identity verification for TrustPlane.

Provides identity provider configuration, persistence, and JWT token
verification for SSO integration. Supports Okta, Azure AD, Google,
and generic OIDC providers.

Security:
    - Token verification checks signature, expiry, issuer, and audience.
    - Token age is checked against a configurable ``max_age_hours`` to
      prevent stale tokens from being reused.
    - Identity config is persisted atomically via ``atomic_write()``.
    - JWKS keys are cached in memory with configurable TTL. On ``kid``
      mismatch, the cache is invalidated and keys are re-fetched to
      support automatic key rotation.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import jwt as pyjwt
except ImportError:
    raise ImportError(
        "PyJWT is required for OIDC identity verification. "
        "Install it with: pip install PyJWT"
    )

from trustplane._locking import atomic_write, safe_read_json
from trustplane.exceptions import IdentityError, JWKSError, TokenVerificationError

logger = logging.getLogger(__name__)

__all__ = [
    "IdentityProvider",
    "IdentityConfig",
    "JWKSProvider",
    "OIDCVerifier",
    "SUPPORTED_PROVIDERS",
]

# ---------------------------------------------------------------------------
# Supported signing algorithms for JWKS
# ---------------------------------------------------------------------------

SUPPORTED_JWKS_ALGORITHMS: frozenset[str] = frozenset(
    {"RS256", "RS384", "RS512", "ES256"}
)


# ---------------------------------------------------------------------------
# Supported provider types
# ---------------------------------------------------------------------------

SUPPORTED_PROVIDERS: frozenset[str] = frozenset(
    {"okta", "azure_ad", "google", "generic_oidc"}
)


# ---------------------------------------------------------------------------
# IdentityProvider
# ---------------------------------------------------------------------------


@dataclass
class IdentityProvider:
    """An OIDC identity provider configuration.

    Attributes:
        provider_type: Provider identifier (``okta``, ``azure_ad``,
            ``google``, or ``generic_oidc``).
        domain: The IdP domain (e.g., ``dev-12345.okta.com``).
        client_id: OAuth2 client ID for this application.
        issuer_url: The OIDC issuer URL for token verification.
    """

    provider_type: str
    domain: str
    client_id: str
    issuer_url: str

    def __post_init__(self) -> None:
        if self.provider_type not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider type: {self.provider_type!r}. "
                f"Must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        if not self.issuer_url.startswith("https://"):
            raise ValueError(f"issuer_url must use HTTPS, got: {self.issuer_url!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "domain": self.domain,
            "client_id": self.client_id,
            "issuer_url": self.issuer_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdentityProvider:
        for field_name in ("provider_type", "domain", "client_id", "issuer_url"):
            if field_name not in data:
                raise ValueError(
                    f"IdentityProvider.from_dict: missing required field '{field_name}'"
                )
        return cls(
            provider_type=data["provider_type"],
            domain=data["domain"],
            client_id=data["client_id"],
            issuer_url=data["issuer_url"],
        )


# ---------------------------------------------------------------------------
# IdentityConfig
# ---------------------------------------------------------------------------


class IdentityConfig:
    """Manages identity provider configuration persistence.

    Stores and loads the OIDC provider configuration from a JSON file.

    Args:
        config_path: Path to ``identity-config.json``. The file and parent
            directories are created on the first ``configure()`` call.
    """

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._provider: IdentityProvider | None = None
        self._load()

    def configure(self, provider: IdentityProvider) -> None:
        """Set the identity provider and persist to disk.

        Args:
            provider: The OIDC provider configuration.
        """
        logger.info(
            "Configuring identity provider: type=%s, domain=%s",
            provider.provider_type,
            provider.domain,
        )
        self._provider = provider
        self._save()

    def get_provider(self) -> IdentityProvider | None:
        """Return the configured provider, or ``None`` if not configured."""
        return self._provider

    def is_configured(self) -> bool:
        """Return ``True`` if an identity provider has been configured."""
        return self._provider is not None

    # -- Persistence -------------------------------------------------------

    def _load(self) -> None:
        """Load provider config from disk if the file exists."""
        if not self._config_path.exists():
            logger.debug("No identity config at %s — not configured", self._config_path)
            return
        try:
            data = safe_read_json(self._config_path)
        except json.JSONDecodeError as exc:
            raise IdentityError(
                f"Identity config file contains invalid JSON: "
                f"{self._config_path}: {exc}"
            ) from exc
        except OSError as exc:
            raise IdentityError(
                f"Failed to read identity config: {self._config_path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise IdentityError(
                f"Identity config root must be a JSON object, "
                f"got {type(data).__name__}: {self._config_path}"
            )
        provider_data = data.get("provider")
        if provider_data is not None:
            self._provider = IdentityProvider.from_dict(provider_data)

    def _save(self) -> None:
        """Persist provider config to disk atomically."""
        data: dict[str, Any] = {}
        if self._provider is not None:
            data["provider"] = self._provider.to_dict()
        atomic_write(self._config_path, data)
        logger.debug("Saved identity config to %s", self._config_path)


# ---------------------------------------------------------------------------
# JWKSProvider
# ---------------------------------------------------------------------------


class JWKSProvider:
    """Fetches and caches JWKS keys from an OIDC provider.

    Performs auto-discovery via the ``/.well-known/openid-configuration``
    endpoint to locate the ``jwks_uri``, then fetches the JSON Web Key Set.
    Keys are cached in memory with a configurable TTL.

    When a requested ``kid`` is not found in the cached key set, the
    provider automatically re-fetches the JWKS to support key rotation.

    Args:
        issuer_url: The OIDC issuer URL (e.g.,
            ``https://dev-12345.okta.com/oauth2/default``).
        ttl_seconds: How long cached keys remain valid, in seconds.
            Default is 3600 (1 hour).
        http_timeout_seconds: Timeout for HTTP requests to the OIDC
            discovery and JWKS endpoints. Default is 10 seconds.
    """

    def __init__(
        self,
        issuer_url: str,
        ttl_seconds: int = 3600,
        http_timeout_seconds: int = 10,
    ) -> None:
        if not issuer_url:
            raise ValueError("issuer_url must not be empty")
        # Strip trailing slash for consistent URL construction.
        self._issuer_url = issuer_url.rstrip("/")
        self._ttl_seconds = ttl_seconds
        self._http_timeout_seconds = http_timeout_seconds

        # Cache state
        self._keys: dict[str, dict[str, Any]] = {}
        self._jwks_uri: str | None = None
        self._last_fetch_time: float = 0.0

    # -- Public API --------------------------------------------------------

    def get_key(self, kid: str) -> dict[str, Any]:
        """Return the JWK dict for the given key ID.

        If the key is not in the cache or the cache has expired, the JWKS
        endpoint is re-fetched. If the ``kid`` is still not found after a
        fresh fetch, :class:`JWKSError` is raised.

        Args:
            kid: The ``kid`` (key ID) from the JWT header.

        Returns:
            The JWK dict containing ``kty``, ``kid``, ``n``, ``e``, etc.

        Raises:
            JWKSError: If the key cannot be found after a fresh fetch.
        """
        if not kid:
            raise JWKSError("JWT header is missing 'kid' claim")

        # Try cached key first.
        if self._is_cache_valid() and kid in self._keys:
            logger.debug("JWKS cache hit for kid=%s", kid)
            return self._keys[kid]

        # Cache miss or expired — re-fetch.
        logger.info(
            "JWKS cache miss for kid=%s (valid=%s), re-fetching",
            kid,
            self._is_cache_valid(),
        )
        self._fetch_jwks()

        if kid not in self._keys:
            raise JWKSError(
                f"Key ID '{kid}' not found in JWKS from {self._issuer_url}. "
                f"Available key IDs: {sorted(self._keys.keys())}"
            )
        return self._keys[kid]

    # -- Internal ----------------------------------------------------------

    def _is_cache_valid(self) -> bool:
        """Return ``True`` if the cached keys are still within the TTL."""
        if not self._keys:
            return False
        elapsed = time.monotonic() - self._last_fetch_time
        return elapsed < self._ttl_seconds

    def _fetch_jwks(self) -> None:
        """Fetch the JWKS from the provider's ``jwks_uri``.

        First discovers the ``jwks_uri`` from the OpenID Configuration
        endpoint if it hasn't been resolved yet, then fetches and
        validates the JWKS response.

        Raises:
            JWKSError: On network errors, invalid responses, or missing
                required fields.
        """
        if self._jwks_uri is None:
            self._discover_jwks_uri()

        jwks_data = self._http_get_json(self._jwks_uri)  # type: ignore[arg-type]

        if not isinstance(jwks_data, dict):
            raise JWKSError(
                f"JWKS response must be a JSON object, got {type(jwks_data).__name__}"
            )

        keys_list = jwks_data.get("keys")
        if keys_list is None:
            raise JWKSError("JWKS response missing required 'keys' field")
        if not isinstance(keys_list, list):
            raise JWKSError(
                f"JWKS 'keys' field must be an array, got {type(keys_list).__name__}"
            )

        parsed_keys: dict[str, dict[str, Any]] = {}
        for key_data in keys_list:
            if not isinstance(key_data, dict):
                logger.warning("Skipping non-object entry in JWKS keys array")
                continue

            kid = key_data.get("kid")
            if kid is None:
                logger.warning("Skipping JWKS key without 'kid' field")
                continue

            kty = key_data.get("kty")
            if kty is None:
                logger.warning("Skipping JWKS key kid=%s without 'kty' field", kid)
                continue

            # Only accept keys with supported algorithms, or keys without
            # an explicit ``alg`` field (the algorithm will be determined
            # from the JWT header).
            alg = key_data.get("alg")
            if alg is not None and alg not in SUPPORTED_JWKS_ALGORITHMS:
                logger.warning(
                    "Skipping JWKS key kid=%s with unsupported algorithm %s",
                    kid,
                    alg,
                )
                continue

            # Only accept signing keys (``use`` is ``sig`` or absent).
            use = key_data.get("use")
            if use is not None and use != "sig":
                logger.debug(
                    "Skipping JWKS key kid=%s with use=%s (not signing)", kid, use
                )
                continue

            parsed_keys[kid] = key_data

        if not parsed_keys:
            raise JWKSError(
                "JWKS response contained no usable signing keys. "
                "Ensure the provider publishes keys with 'kid' and 'kty' fields."
            )

        self._keys = parsed_keys
        self._last_fetch_time = time.monotonic()
        logger.info(
            "Fetched %d JWKS key(s) from %s: %s",
            len(parsed_keys),
            self._jwks_uri,
            sorted(parsed_keys.keys()),
        )

    def _discover_jwks_uri(self) -> None:
        """Discover the ``jwks_uri`` from the OIDC discovery document.

        Fetches ``{issuer_url}/.well-known/openid-configuration`` and
        extracts the ``jwks_uri`` field.

        Raises:
            JWKSError: If the discovery document is unreachable, invalid,
                or missing ``jwks_uri``.
        """
        discovery_url = f"{self._issuer_url}/.well-known/openid-configuration"
        logger.info("Discovering JWKS URI from %s", discovery_url)

        config_data = self._http_get_json(discovery_url)

        if not isinstance(config_data, dict):
            raise JWKSError(
                f"OIDC discovery response must be a JSON object, "
                f"got {type(config_data).__name__}"
            )

        jwks_uri = config_data.get("jwks_uri")
        if jwks_uri is None:
            raise JWKSError(
                f"OIDC discovery document at {discovery_url} "
                f"missing required 'jwks_uri' field"
            )
        if not isinstance(jwks_uri, str) or not jwks_uri.startswith("https://"):
            raise JWKSError(
                f"OIDC discovery 'jwks_uri' must be an HTTPS URL, got: {jwks_uri!r}"
            )

        self._jwks_uri = jwks_uri
        logger.info("Discovered JWKS URI: %s", jwks_uri)

    def _http_get_json(self, url: str) -> Any:
        """Fetch a URL and parse the response as JSON.

        Uses ``urllib.request`` so no extra dependencies are required.

        Args:
            url: The URL to fetch. Must use HTTPS.

        Returns:
            The parsed JSON response.

        Raises:
            JWKSError: On network errors, non-200 responses, or invalid JSON.
        """
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(
                req, timeout=self._http_timeout_seconds, context=ctx
            ) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise JWKSError(f"HTTP {exc.code} fetching {url}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise JWKSError(f"Failed to connect to {url}: {exc.reason}") from exc
        except OSError as exc:
            raise JWKSError(f"Network error fetching {url}: {exc}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise JWKSError(f"Invalid JSON response from {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# OIDCVerifier
# ---------------------------------------------------------------------------


class OIDCVerifier:
    """Verifies OIDC JWT tokens against a configured identity provider.

    Supports two modes of key resolution:

    1. **JWKS auto-discovery** (preferred for production): Pass a
       :class:`JWKSProvider` to the constructor. The verifier extracts
       the ``kid`` from the JWT header, fetches the matching key from
       the JWKS endpoint, and uses it for signature verification.
    2. **Explicit PEM key** (for testing / offline): Pass
       ``public_key_pem`` to :meth:`verify_token`. This bypasses JWKS.

    If both ``jwks_provider`` and ``public_key_pem`` are supplied,
    ``public_key_pem`` takes precedence.

    Args:
        provider: The OIDC identity provider configuration.
        max_age_hours: Maximum token age in hours. Tokens issued longer
            than this many hours ago are rejected even if their ``exp``
            claim is still valid. Default is 8 hours.
        jwks_provider: Optional :class:`JWKSProvider` for automatic key
            discovery via the OIDC JWKS endpoint.
    """

    def __init__(
        self,
        provider: IdentityProvider,
        max_age_hours: float = 8.0,
        jwks_provider: JWKSProvider | None = None,
    ) -> None:
        import math

        if not math.isfinite(max_age_hours):
            raise ValueError(f"max_age_hours must be finite, got: {max_age_hours}")
        if max_age_hours <= 0:
            raise ValueError(f"max_age_hours must be positive, got: {max_age_hours}")
        self._provider = provider
        self.max_age_hours = max_age_hours
        self._jwks_provider = jwks_provider

    def verify_token(
        self,
        token: str,
        *,
        public_key_pem: bytes | None = None,
    ) -> dict[str, Any]:
        """Verify a JWT token and return its claims.

        Checks:
            1. Signature validity (using ``public_key_pem`` or JWKS).
            2. Token expiry (``exp`` claim).
            3. Issuer match (``iss`` claim vs. provider's ``issuer_url``).
            4. Audience match (``aud`` claim vs. provider's ``client_id``).
            5. Token age (``iat`` claim vs. ``max_age_hours``).

        Args:
            token: The encoded JWT string.
            public_key_pem: PEM-encoded public key bytes for signature
                verification. When provided, this takes precedence over
                JWKS auto-discovery.

        Returns:
            A dict of verified JWT claims.

        Raises:
            TokenVerificationError: If any verification check fails.
        """
        # Determine the verification key and allowed algorithms.
        key, algorithms = self._resolve_key(token, public_key_pem)

        try:
            claims = pyjwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self._provider.client_id,
                issuer=self._provider.issuer_url,
                options={
                    "require": ["exp", "iss", "aud", "iat", "sub"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise TokenVerificationError(f"Token has expired: {exc}") from exc
        except pyjwt.InvalidIssuerError as exc:
            raise TokenVerificationError(
                f"Token issuer does not match expected issuer "
                f"'{self._provider.issuer_url}': {exc}"
            ) from exc
        except pyjwt.InvalidAudienceError as exc:
            raise TokenVerificationError(
                f"Token audience does not match expected audience "
                f"'{self._provider.client_id}': {exc}"
            ) from exc
        except pyjwt.InvalidSignatureError as exc:
            raise TokenVerificationError(
                f"Token signature verification failed: {exc}"
            ) from exc
        except pyjwt.DecodeError as exc:
            raise TokenVerificationError(
                f"Token decode failed (malformed or invalid): {exc}"
            ) from exc
        except pyjwt.PyJWTError as exc:
            raise TokenVerificationError(f"Token verification failed: {exc}") from exc

        # Check token age
        iat = claims.get("iat")
        if iat is not None:
            now = time.time()
            age_seconds = now - iat
            max_age_seconds = self.max_age_hours * 3600
            if age_seconds > max_age_seconds:
                raise TokenVerificationError(
                    f"Token is too old: issued {age_seconds / 3600:.1f} hours ago, "
                    f"maximum age is {self.max_age_hours} hours"
                )

        logger.info(
            "Token verified successfully: sub=%s, iss=%s",
            claims.get("sub"),
            claims.get("iss"),
        )
        return claims

    def _resolve_key(
        self,
        token: str,
        public_key_pem: bytes | None,
    ) -> tuple[Any, list[str]]:
        """Determine the verification key and algorithms for a token.

        Args:
            token: The encoded JWT string (used to extract the header
                for JWKS ``kid`` lookup).
            public_key_pem: Explicit PEM key, if provided.

        Returns:
            A tuple of ``(key, algorithms)`` suitable for
            ``pyjwt.decode()``.

        Raises:
            TokenVerificationError: If no key source is available or
                the JWKS lookup fails.
        """
        # Explicit PEM always takes precedence.
        if public_key_pem is not None:
            return public_key_pem, ["RS256"]

        # JWKS auto-discovery.
        if self._jwks_provider is not None:
            try:
                unverified_header = pyjwt.get_unverified_header(token)
            except pyjwt.DecodeError as exc:
                raise TokenVerificationError(
                    f"Cannot decode JWT header for JWKS lookup: {exc}"
                ) from exc

            kid = unverified_header.get("kid")
            if kid is None:
                raise TokenVerificationError(
                    "JWT header missing 'kid' claim — cannot look up JWKS key"
                )

            alg = unverified_header.get("alg", "RS256")
            if alg not in SUPPORTED_JWKS_ALGORITHMS:
                raise TokenVerificationError(
                    f"JWT algorithm '{alg}' is not supported. "
                    f"Supported: {sorted(SUPPORTED_JWKS_ALGORITHMS)}"
                )

            try:
                jwk_data = self._jwks_provider.get_key(kid)
            except JWKSError as exc:
                raise TokenVerificationError(f"JWKS key lookup failed: {exc}") from exc

            # Convert the JWK dict to a key object that PyJWT can use.
            # Determine key type from algorithm to avoid algorithm confusion.
            try:
                if alg.startswith("ES"):
                    key = pyjwt.algorithms.ECAlgorithm.from_jwk(jwk_data)  # type: ignore[arg-type]
                else:
                    # RS256, RS384, RS512
                    key = pyjwt.algorithms.RSAAlgorithm.from_jwk(jwk_data)  # type: ignore[arg-type]
            except Exception as exc:
                raise TokenVerificationError(
                    f"Failed to construct key from JWK kid={kid} (alg={alg}): {exc}"
                ) from exc

            return key, [alg]

        # No key source available.
        raise TokenVerificationError(
            "No public key or JWKS provider configured for token verification. "
            "Supply public_key_pem or pass a JWKSProvider to OIDCVerifier."
        )
