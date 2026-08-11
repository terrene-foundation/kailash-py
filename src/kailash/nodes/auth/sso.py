"""
Single Sign-On (SSO) Authentication Node

Enterprise-grade SSO implementation supporting multiple protocols:
- SAML 2.0 (Security Assertion Markup Language)
- OAuth 2.0 / OpenID Connect (OIDC)
- LDAP / Active Directory
- Microsoft Azure AD
- Google Workspace
- Okta
- Auth0
- Custom JWT providers
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs, urlencode, urlparse

from kailash.nodes.api import AsyncHTTPRequestNode
from kailash.nodes.auth._http_response import http_body
from kailash.nodes.auth._log_hygiene import log_safe, redact_mapping
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import JSONReaderNode
from kailash.nodes.mixins import LoggingMixin, PerformanceMixin, SecurityMixin
from kailash.nodes.security import AuditLogNode, SecurityEventNode


# Shared, BOUNDED executor for the sync->async bridge in ``run()``. A per-call
# ThreadPoolExecutor would spawn one OS thread plus one event loop per request,
# which a burst of unauthenticated SSO callbacks could turn into resource
# exhaustion.
def _sync_bridge_workers() -> int:
    """Worker count for the sync bridge, validated so a typo cannot brick import."""
    raw = os.environ.get("KAILASH_SSO_SYNC_BRIDGE_WORKERS", "8")
    try:
        workers = int(raw)
    except (TypeError, ValueError):
        return 8
    return workers if workers >= 1 else 8


_SYNC_BRIDGE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_sync_bridge_workers(),
    thread_name_prefix="kailash-sso-sync-bridge",
)

# Default ceiling on a single bridged operation, so a hung IdP cannot pin the
# caller's event loop indefinitely.
_SYNC_BRIDGE_TIMEOUT_SECONDS = 30.0


@register_node()
class SSOAuthenticationNode(SecurityMixin, PerformanceMixin, LoggingMixin, Node):
    """
    Enterprise SSO Authentication Node

    Supports multiple SSO protocols and providers with advanced security features.
    """

    def __init__(
        self,
        name: str = "sso_auth",
        providers: List[str] | None = None,
        saml_settings: Dict[str, Any] | None = None,
        oauth_settings: Dict[str, Any] | None = None,
        ldap_settings: Dict[str, Any] | None = None,
        jwt_settings: Dict[str, Any] | None = None,
        enable_jit_provisioning: bool = True,
        attribute_mapping: Dict[str, str] | None = None,
        encryption_enabled: bool = True,
        session_timeout: timedelta = timedelta(hours=8),
        max_concurrent_sessions: int = 5,
        sync_bridge_timeout: float = _SYNC_BRIDGE_TIMEOUT_SECONDS,
    ):
        # Set attributes before calling super().__init__()
        self.name = name
        self.providers = providers or ["oauth2", "oidc"]
        self.saml_settings = saml_settings or {}
        self.oauth_settings = oauth_settings or {}
        self.ldap_settings = ldap_settings or {}
        self.jwt_settings = jwt_settings or {}
        self.enable_jit_provisioning = enable_jit_provisioning
        self.attribute_mapping = attribute_mapping or {
            "email": "email",
            "firstName": "given_name",
            "lastName": "family_name",
            "groups": "groups",
            "department": "department",
        }
        self.encryption_enabled = encryption_enabled
        self.session_timeout = session_timeout
        self.max_concurrent_sessions = max_concurrent_sessions
        # Ceiling on a bridged sync call (see _run_async_in_worker_thread).
        self.sync_bridge_timeout = sync_bridge_timeout

        # Internal state
        self.active_sessions = {}
        self.provider_cache = {}
        self.security_events = []

        super().__init__(name=name)

        # Initialize supporting nodes
        self._setup_supporting_nodes()

    def _setup_supporting_nodes(self):
        """Initialize supporting Kailash nodes."""
        # AsyncHTTPRequestNode, not HTTPRequestNode: every call site here is
        # on an async path and awaits the client. The sync HTTPRequestNode
        # defines neither async_run nor execute_async, so those awaits
        # raised AttributeError (issue #2060). Both return
        # {"success": ..., "response": ...}.
        self.http_client = AsyncHTTPRequestNode(name=f"{self.name}_http")

        self.json_reader = JSONReaderNode(name=f"{self.name}_json")

        self.security_logger = SecurityEventNode(name=f"{self.name}_security")

        self.audit_logger = AuditLogNode(name=f"{self.name}_audit")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="SSO action: initiate, callback, validate, logout, status",
            ),
            "provider": NodeParameter(
                name="provider",
                type=str,
                required=False,
                description="SSO provider: saml, oauth2, oidc, ldap, azure, google, okta",
            ),
            "request_data": NodeParameter(
                name="request_data",
                type=dict,
                required=False,
                description="Request data from SSO provider (tokens, assertions, etc.)",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User ID for session operations",
            ),
            "redirect_uri": NodeParameter(
                name="redirect_uri",
                type=str,
                required=False,
                description="Redirect URI for OAuth flows",
            ),
            "attributes": NodeParameter(
                name="attributes",
                type=dict,
                required=False,
                description="User attributes from SSO provider",
            ),
            "callback_data": NodeParameter(
                name="callback_data",
                type=dict,
                required=False,
                description="Callback data from SSO provider (alias for request_data)",
            ),
        }

    def run(  # type: ignore[reportIncompatibleMethodOverride]
        self,
        action: str,
        provider: str | None = None,
        request_data: Dict[str, Any] | None = None,
        user_id: str | None = None,
        redirect_uri: str | None = None,
        attributes: Dict[str, Any] | None = None,
        callback_data: Dict[str, Any] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute SSO authentication operations (synchronous wrapper).

        Args:
            action: SSO action to perform
            provider: SSO provider type
            request_data: Request data from provider
            user_id: User ID for operations
            redirect_uri: OAuth redirect URI
            attributes: User attributes

        Returns:
            Dict containing operation results
        """

        # Run the async method in the current event loop or create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already inside a running loop (FastAPI/Nexus calling the sync
                # surface). Run the REAL async implementation on a private loop
                # in a worker thread. This previously dispatched to a
                # "simplified synchronous implementation" that returned
                # authenticated=True for any non-empty token -- a full SSO
                # bypass for every async caller (issue #2026).
                return self._run_async_in_worker_thread(
                    action=action,
                    provider=provider,
                    request_data=request_data,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    attributes=attributes,
                    callback_data=callback_data,
                    **kwargs,
                )
            else:
                return loop.run_until_complete(
                    self.async_run(
                        action=action,
                        provider=provider,
                        request_data=request_data,
                        user_id=user_id,
                        redirect_uri=redirect_uri,
                        attributes=attributes,
                        callback_data=callback_data,
                        **kwargs,
                    )
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(
                self.async_run(
                    action=action,
                    provider=provider,
                    request_data=request_data,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    attributes=attributes,
                    callback_data=callback_data,
                    **kwargs,
                )
            )

    def _run_async_in_worker_thread(
        self,
        action: str,
        provider: str | None = None,
        request_data: Dict[str, Any] | None = None,
        user_id: str | None = None,
        redirect_uri: str | None = None,
        attributes: Dict[str, Any] | None = None,
        callback_data: Dict[str, Any] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Run the real :meth:`async_run` on a private loop in a worker thread.

        ``run()`` is a synchronous surface, but the implementation is async. When
        the caller is already inside a running event loop we cannot block it, so
        the coroutine is executed on its own loop in a worker thread and the
        genuine result is returned.

        This replaces a "simplified synchronous implementation" that fabricated
        results: ``action="validate"`` returned ``authenticated: True`` with a
        caller-supplied ``user_id`` for ANY non-empty token, ``status`` always
        reported ``active: True``, and ``initiate`` returned a hardcoded
        Microsoft URL with ``client_id=test``. See issue #2026.

        Note that ``future.result()`` blocks the calling thread, which IS the
        event-loop thread. A shared bounded executor and a hard timeout keep a
        slow or hung IdP from pinning the loop indefinitely or spawning an
        unbounded number of threads. Async callers should await
        :meth:`async_run` directly and avoid this path entirely.
        """
        start_time = time.time()

        # The coroutine is built INSIDE the worker: constructing it here and
        # handing it to a saturated pool leaves an un-awaited coroutine if the
        # job is later cancelled.
        def _invoke() -> Dict[str, Any]:
            return asyncio.run(
                self.async_run(
                    action=action,
                    provider=provider,
                    request_data=request_data,
                    user_id=user_id,
                    redirect_uri=redirect_uri,
                    attributes=attributes,
                    callback_data=callback_data,
                    **kwargs,
                )
            )

        future = _SYNC_BRIDGE_EXECUTOR.submit(_invoke)
        try:
            return future.result(timeout=self.sync_bridge_timeout)
        except FuturesTimeoutError as e:
            # Drop it from the queue if it has not started. An already-running
            # job cannot be cancelled and is abandoned, which is why the
            # provider-side call needs its own timeout too.
            future.cancel()
            raise TimeoutError(
                f"SSO operation {action!r} exceeded "
                f"{self.sync_bridge_timeout}s on the synchronous bridge"
            ) from e
        finally:
            duration = time.time() - start_time
            self.log_info(f"SSO operation {action} completed in {duration:.3f}s")

    async def async_run(
        self,
        action: str,
        provider: str | None = None,
        request_data: Dict[str, Any] | None = None,
        user_id: str | None = None,
        redirect_uri: str | None = None,
        attributes: Dict[str, Any] | None = None,
        callback_data: Dict[str, Any] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute SSO authentication operations.

        Args:
            action: SSO action to perform
            provider: SSO provider type
            request_data: Request data from provider
            user_id: User ID for operations
            redirect_uri: OAuth redirect URI
            attributes: User attributes

        Returns:
            Dict containing operation results
        """
        start_time = time.time()

        try:
            self.log_info(f"Starting SSO operation: {action} with provider: {provider}")

            # Handle callback_data parameter alias for test compatibility
            if callback_data and not request_data:
                request_data = callback_data

            # Route to appropriate handler
            if action == "initiate":
                result = await self._initiate_sso(provider, redirect_uri, **kwargs)  # type: ignore[reportArgumentType]
            elif action == "callback":
                result = await self._handle_callback(provider, request_data, **kwargs)  # type: ignore[reportArgumentType]
            elif action == "validate":
                result = await self._validate_token(provider, request_data, **kwargs)  # type: ignore[reportArgumentType]
            elif action == "logout":
                result = await self._handle_logout(user_id, provider, **kwargs)  # type: ignore[reportArgumentType]
            elif action == "status":
                result = await self._get_sso_status(user_id, **kwargs)  # type: ignore[reportArgumentType]
            elif action == "provision_user":
                result = await self._provision_user(attributes, provider, **kwargs)  # type: ignore[reportArgumentType]
            else:
                raise ValueError(f"Unsupported SSO action: {action}")

            # Log successful operation
            processing_time = (time.time() - start_time) * 1000
            result["processing_time_ms"] = processing_time
            # Derive from the operation's verdict: unconditionally stamping
            # success=True turned an {"authenticated": False} / {"valid": False}
            # result into a success for any caller gating on that field
            # (issue #2026).
            if "authenticated" in result:
                result["success"] = bool(result["authenticated"])
            elif "valid" in result:
                result["success"] = bool(result["valid"])
            elif "error" in result:
                result["success"] = False
            else:
                result["success"] = True

            # Log security event. The verdict is the operation's own, not a
            # hardcoded True: this recorded success=True three lines after
            # deriving result["success"] = False, so a failed SSO operation was
            # audited as a successful one (issue #2060).
            await self._log_security_event(
                event_type=(
                    "sso_operation" if result["success"] else "sso_operation_denied"
                ),
                action=action,
                provider=provider,
                user_id=user_id,
                success=result["success"],
                processing_time_ms=processing_time,
            )

            self.log_info(
                f"SSO operation completed successfully in {processing_time:.1f}ms"
            )
            return result

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000

            # Log security event for failure
            await self._log_security_event(
                event_type="sso_failure",
                action=action,
                provider=provider,
                user_id=user_id,
                success=False,
                error=str(e),
                processing_time_ms=processing_time,
            )

            self.log_error(f"SSO operation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time_ms": processing_time,
                "action": action,
                "provider": provider,
            }

    async def _initiate_sso(
        self, provider: str, redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        """Initiate SSO flow with specified provider."""
        if provider == "saml":
            return await self._initiate_saml(redirect_uri, **kwargs)
        elif provider in ["oauth2", "oidc"]:
            return await self._initiate_oauth(provider, redirect_uri, **kwargs)
        elif provider == "ldap":
            return await self._initiate_ldap(**kwargs)
        elif provider == "azure":
            return await self._initiate_azure_ad(redirect_uri, **kwargs)
        elif provider == "google":
            return await self._initiate_google(redirect_uri, **kwargs)
        elif provider == "okta":
            return await self._initiate_okta(redirect_uri, **kwargs)
        else:
            raise ValueError(f"Unsupported SSO provider: {provider}")

    async def _initiate_saml(self, redirect_uri: str, **kwargs) -> Dict[str, Any]:
        """Initiate SAML 2.0 authentication flow."""
        # Generate SAML AuthnRequest
        request_id = f"_{uuid.uuid4()}"
        timestamp = datetime.now(UTC).isoformat()

        # Create SAML AuthnRequest XML
        authn_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{timestamp}"
    Destination="{self.saml_settings.get("sso_url", "")}"
    AssertionConsumerServiceURL="{redirect_uri}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>{self.saml_settings.get("entity_id", "kailash-admin")}</saml:Issuer>
    <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:2.0:nameid-format:emailAddress" AllowCreate="true"/>
</samlp:AuthnRequest>"""

        # Base64 encode the request
        encoded_request = base64.b64encode(authn_request.encode()).decode()

        # Create SSO URL with parameters
        sso_params = {
            "SAMLRequest": encoded_request,
            "RelayState": kwargs.get("relay_state", ""),
        }

        sso_url = f"{self.saml_settings.get('sso_url')}?{urlencode(sso_params)}"

        return {
            "provider": "saml",
            "sso_url": sso_url,
            "request_id": request_id,
            "redirect_uri": redirect_uri,
            "relay_state": kwargs.get("relay_state"),
        }

    @staticmethod
    def _pkce_pair() -> tuple[str, str]:
        """Generate a PKCE (RFC 7636) ``code_verifier`` / ``code_challenge`` pair.

        The verifier is a high-entropy secret retained by the client; the
        challenge is its S256 (SHA-256, base64url, no padding) transform sent on
        the authorization request. Binding the two proves the client that later
        redeems the authorization code is the same one that requested it,
        closing the auth-code interception attack on public clients.
        """
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return code_verifier, code_challenge

    def _verify_id_token(self, provider: str, id_token: str) -> Dict[str, Any]:
        """Cryptographically verify an OIDC id_token against the provider's JWKS.

        Fail-closed. Any id_token whose claims (including ``nonce``) will be
        trusted MUST first have its RS256/ES256 signature verified against the
        provider's published JWKS AND its ``aud`` / ``iss`` / ``exp`` validated.
        This reuses the same PyJWT ``PyJWKClient`` + ``jwt.decode`` pattern the
        provider classes use (``kailash.trust.auth.sso.google`` et al.).

        Configuration is read from ``oauth_settings``:

        - ``jwks_uri`` — the provider's JWKS endpoint (required)
        - ``issuer`` — the expected ``iss`` claim (required)
        - ``{provider}_client_id`` or ``client_id`` — the expected ``aud``
          claim (required)

        If any of these are unconfigured, the JWKS is unreachable, or
        verification fails (bad signature / audience / issuer / expiry), this
        raises a typed :class:`ValueError` and REJECTS — it NEVER falls back to
        the unverified base64url read for a trust decision.
        """
        try:
            import jwt
            from jwt import PyJWKClient
        except ImportError as exc:  # pragma: no cover - optional-extra guard
            raise ValueError(
                "OIDC id_token signature verification requires PyJWT. Install "
                "with: pip install 'kailash[server]' (or 'kailash[trust]')"
            ) from exc

        jwks_uri = self.oauth_settings.get("jwks_uri")
        issuer = self.oauth_settings.get("issuer")
        audience = self.oauth_settings.get(
            f"{provider}_client_id"
        ) or self.oauth_settings.get("client_id")

        missing = [
            name
            for name, value in (
                ("jwks_uri", jwks_uri),
                ("issuer", issuer),
                ("client_id", audience),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "OIDC id_token signature verification is required for the nonce "
                f"flow but oauth_settings is missing: {', '.join(missing)}. "
                "Configure jwks_uri, issuer, and client_id; refusing to trust "
                "an unverified id_token."
            )

        try:
            jwks_client = PyJWKClient(jwks_uri)
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=audience,
                issuer=issuer,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ValueError(
                f"OIDC id_token verification failed: token expired ({exc})"
            )
        except jwt.InvalidAudienceError as exc:
            raise ValueError(
                f"OIDC id_token verification failed: audience mismatch ({exc})"
            )
        except jwt.InvalidIssuerError as exc:
            raise ValueError(
                f"OIDC id_token verification failed: issuer mismatch ({exc})"
            )
        except jwt.PyJWKClientError as exc:
            raise ValueError(
                "OIDC id_token verification failed: JWKS unreachable or signing "
                f"key not found ({exc})"
            )
        except jwt.InvalidTokenError as exc:
            raise ValueError(
                f"OIDC id_token verification failed: invalid token ({exc})"
            )
        except Exception as exc:
            # Fail-closed catch-all: some PyJWT versions surface a JWKS network
            # fetch failure OUTSIDE the jwt exception hierarchy (e.g.
            # urllib.error.URLError). It already REJECTS by propagating, but this
            # normalizes it to the SAME typed ValueError so the fail-closed
            # contract is uniform across PyJWT versions. It NEVER falls back to
            # the unverified base64url read — it re-raises a rejection.
            raise ValueError(f"OIDC id_token verification failed: {exc}") from exc

        if not isinstance(claims, dict):
            # jwt.decode returns a dict for a JWS; guard defensively so a later
            # ``claims.get(...)`` cannot raise an opaque AttributeError.
            raise ValueError("OIDC id_token verification produced a non-object payload")
        return claims

    @staticmethod
    def _decode_id_token_claims(id_token: str) -> Dict[str, Any]:
        """Decode the (base64url) payload segment of a JWT id_token.

        This reads the claims WITHOUT verifying the signature. It is a
        DISPLAY-ONLY helper and MUST NOT be used for any trust decision — the
        nonce comparison in ``_handle_oauth_callback`` uses the cryptographically
        verified claims from :meth:`_verify_id_token` instead.
        """
        parts = id_token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid id_token: not a JWT (missing payload segment)")
        payload_segment = parts[1]
        # Restore base64url padding stripped by the encoder.
        padding = "=" * (-len(payload_segment) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload_segment + padding)
            claims = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid id_token: undecodable payload ({e})")
        if not isinstance(claims, dict):
            # A valid-JSON but non-object payload (e.g. "123", "[]") has no
            # claims to read; fail closed with a typed error rather than let
            # a later ``claims.get(...)`` raise an opaque AttributeError.
            raise ValueError("Invalid id_token: payload is not a JSON object")
        return claims

    async def _initiate_oauth(
        self, provider: str, redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        """Initiate OAuth 2.0 / OIDC authentication flow."""
        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)

        # PKCE (RFC 7636) — proof-of-possession binding for the auth-code flow
        code_verifier, code_challenge = self._pkce_pair()

        # OAuth parameters
        auth_params = {
            "response_type": "code",
            "client_id": self.oauth_settings.get("client_id"),
            "redirect_uri": redirect_uri,
            "scope": self.oauth_settings.get("scope", "openid profile email"),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # Add OIDC-specific parameters
        if provider == "oidc":
            auth_params["nonce"] = secrets.token_urlsafe(16)

        # Build authorization URL
        auth_url = (
            f"{self.oauth_settings.get('auth_endpoint')}?{urlencode(auth_params)}"
        )

        # Store state for validation
        self.provider_cache[state] = {
            "provider": provider,
            "timestamp": time.time(),
            "redirect_uri": redirect_uri,
            "nonce": auth_params.get("nonce"),
            "code_verifier": code_verifier,
        }

        return {
            "provider": provider,
            "auth_url": auth_url,
            "state": state,
            "redirect_uri": redirect_uri,
        }

    async def _initiate_ldap(self, **kwargs) -> Dict[str, Any]:
        """Initiate LDAP/Active Directory authentication."""
        # LDAP is typically username/password based, not redirect-based
        return {
            "provider": "ldap",
            "auth_method": "username_password",
            "ldap_server": self.ldap_settings.get("server"),
            "base_dn": self.ldap_settings.get("base_dn"),
            "requires_credentials": True,
        }

    async def _initiate_azure_ad(self, redirect_uri: str, **kwargs) -> Dict[str, Any]:
        """Initiate Microsoft Azure AD authentication."""
        tenant_id = self.oauth_settings.get("azure_tenant_id", "common")

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # PKCE (RFC 7636) — proof-of-possession binding for the auth-code flow
        code_verifier, code_challenge = self._pkce_pair()

        # OIDC nonce (id_token replay/injection defense). Azure AD is
        # OIDC-capable, so mint + cache a nonce; the callback's
        # ``expected_nonce`` then activates enforcement against the
        # JWKS-verified id_token in ``_handle_oauth_callback``.
        nonce = secrets.token_urlsafe(16)

        auth_params = {
            "response_type": "code",
            "client_id": self.oauth_settings.get("azure_client_id"),
            "redirect_uri": redirect_uri,
            "scope": "openid profile email User.Read",
            "state": state,
            "response_mode": "query",
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{urlencode(auth_params)}"

        # Store state for validation
        self.provider_cache[state] = {
            "provider": "azure",
            "timestamp": time.time(),
            "redirect_uri": redirect_uri,
            "tenant_id": tenant_id,
            "nonce": nonce,
            "code_verifier": code_verifier,
        }

        return {
            "provider": "azure",
            "auth_url": auth_url,
            "state": state,
            "tenant_id": tenant_id,
            "redirect_uri": redirect_uri,
        }

    async def _initiate_google(self, redirect_uri: str, **kwargs) -> Dict[str, Any]:
        """Initiate Google Workspace authentication."""
        state = secrets.token_urlsafe(32)

        # PKCE (RFC 7636) — proof-of-possession binding for the auth-code flow
        code_verifier, code_challenge = self._pkce_pair()

        # OIDC nonce (id_token replay/injection defense). Google is
        # OIDC-capable; caching the nonce activates callback enforcement
        # against the JWKS-verified id_token in ``_handle_oauth_callback``.
        nonce = secrets.token_urlsafe(16)

        auth_params = {
            "response_type": "code",
            "client_id": self.oauth_settings.get("google_client_id"),
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "access_type": "offline",
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(auth_params)}"
        )

        self.provider_cache[state] = {
            "provider": "google",
            "timestamp": time.time(),
            "redirect_uri": redirect_uri,
            "nonce": nonce,
            "code_verifier": code_verifier,
        }

        return {
            "provider": "google",
            "auth_url": auth_url,
            "state": state,
            "redirect_uri": redirect_uri,
        }

    async def _initiate_okta(self, redirect_uri: str, **kwargs) -> Dict[str, Any]:
        """Initiate Okta authentication."""
        state = secrets.token_urlsafe(32)

        # PKCE (RFC 7636) — proof-of-possession binding for the auth-code flow
        code_verifier, code_challenge = self._pkce_pair()

        # OIDC nonce (id_token replay/injection defense). Okta is OIDC-capable;
        # caching the nonce activates callback enforcement against the
        # JWKS-verified id_token in ``_handle_oauth_callback``.
        nonce = secrets.token_urlsafe(16)

        auth_params = {
            "response_type": "code",
            "client_id": self.oauth_settings.get("okta_client_id"),
            "redirect_uri": redirect_uri,
            "scope": "openid profile email groups",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        okta_domain = self.oauth_settings.get("okta_domain")
        auth_url = f"https://{okta_domain}/oauth2/default/v1/authorize?{urlencode(auth_params)}"

        self.provider_cache[state] = {
            "provider": "okta",
            "timestamp": time.time(),
            "redirect_uri": redirect_uri,
            "okta_domain": okta_domain,
            "nonce": nonce,
            "code_verifier": code_verifier,
        }

        return {
            "provider": "okta",
            "auth_url": auth_url,
            "state": state,
            "okta_domain": okta_domain,
            "redirect_uri": redirect_uri,
        }

    async def _handle_callback(
        self, provider: str, request_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Handle SSO callback from provider.

        SAML and LDAP require protocol-specific cryptography (XML-DSig
        canonicalization for SAML, LDAP bind/search for directory) that is
        not implemented in the Core SDK. Subclass and override
        ``_handle_callback`` to add ``provider="saml"`` or ``provider="ldap"``
        support backed by ``python3-saml`` / ``ldap3``.
        """
        if provider in ["oauth2", "oidc", "azure", "google", "okta"]:
            return await self._handle_oauth_callback(provider, request_data, **kwargs)
        elif provider in {"saml", "ldap"}:
            raise ValueError(
                f"SSO provider {provider!r} is not implemented in the Core SDK class — "
                f"it requires protocol-specific cryptography "
                f"({'XML-DSig validation' if provider == 'saml' else 'LDAP bind/search'}). "
                f"Subclass SSOAuthenticationNode and override _handle_callback() to add "
                f"this provider, or use a specialized auth provider package."
            )
        else:
            raise ValueError(f"Unsupported callback provider: {provider}")

    async def _handle_oauth_callback(
        self, provider: str, request_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Handle OAuth/OIDC callback."""
        # Validate state parameter
        state = request_data.get("state")
        if not state or state not in self.provider_cache:
            raise ValueError("Invalid or missing state parameter")

        cached_data = self.provider_cache.pop(state)

        # Check for authorization code
        auth_code = request_data.get("code")
        if not auth_code:
            error = request_data.get("error", "authorization_denied")
            raise ValueError(f"OAuth authorization failed: {error}")

        # Exchange code for tokens
        token_result = await self._exchange_oauth_code(provider, auth_code, cached_data)

        # OIDC nonce enforcement (id_token replay/injection defense).
        # When a nonce was minted at authorization time, the returned id_token
        # MUST be present, cryptographically verified against the provider's
        # JWKS (signature + aud + iss + exp), and its ``nonce`` claim MUST match
        # the minted value. The nonce is compared ONLY against VERIFIED claims —
        # a forged id_token whose signature fails JWKS verification is rejected
        # before any claim is trusted. Fail-closed: any verification failure
        # raises a typed error and rejects authentication.
        expected_nonce = cached_data.get("nonce")
        if expected_nonce is not None:
            id_token = token_result.get("id_token")
            if not id_token:
                raise ValueError(
                    "OIDC nonce was minted but the token response carried no "
                    "id_token — cannot verify nonce; rejecting authentication"
                )
            claims = self._verify_id_token(provider, id_token)
            returned_nonce = claims.get("nonce")
            # Constant-time compare (defense-in-depth; the one-shot state pop
            # already bounds attempts). A missing/non-string claim fails closed.
            if not isinstance(returned_nonce, str) or not hmac.compare_digest(
                returned_nonce, expected_nonce
            ):
                raise ValueError(
                    "OIDC nonce mismatch — id_token nonce claim does not match "
                    "the value minted at authorization time; rejecting "
                    "authentication (possible id_token replay/injection)"
                )

        # Get user info
        user_info = await self._get_oauth_user_info(
            provider, token_result["access_token"]
        )

        # Map attributes
        mapped_attributes = self._map_attributes(user_info, provider)

        # Provision user if enabled
        if self.enable_jit_provisioning:
            user_result = await self._provision_user(mapped_attributes, provider)
        else:
            user_result = {"user_id": mapped_attributes.get("email")}

        # Create session
        session_result = await self._create_sso_session(
            user_result["user_id"], provider, mapped_attributes, tokens=token_result  # type: ignore[reportArgumentType]
        )

        return {
            "provider": provider,
            "user_attributes": mapped_attributes,
            "user_id": user_result["user_id"],
            "session_id": session_result["session_id"],
            "tokens": token_result,
            "access_token": token_result.get("access_token"),  # For test compatibility
            "authenticated": True,
        }

    async def _exchange_oauth_code(
        self, provider: str, auth_code: str, cached_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Exchange OAuth authorization code for access token."""
        # Build token request
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": cached_data["redirect_uri"],
            "client_id": self.oauth_settings.get(f"{provider}_client_id"),
            "client_secret": self.oauth_settings.get(f"{provider}_client_secret"),
        }

        # PKCE (RFC 7636) — return the code_verifier bound to this authorization
        # request so the token endpoint can confirm proof-of-possession. Guarded
        # for presence to stay backward-safe if a cached entry predates PKCE.
        code_verifier = cached_data.get("code_verifier")
        if code_verifier:
            token_data["code_verifier"] = code_verifier

        # Determine token endpoint
        if provider == "azure":
            tenant_id = cached_data.get("tenant_id", "common")
            token_url = (
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            )
        elif provider == "google":
            token_url = "https://oauth2.googleapis.com/token"
        elif provider == "okta":
            okta_domain = cached_data["okta_domain"]
            token_url = f"https://{okta_domain}/oauth2/default/v1/token"
        else:
            # No silent default. The previous fallback posted the authorization
            # code AND client_secret to https://oauth.example.com/token -- a
            # host the operator does not control -- whenever token_endpoint was
            # left unset (issue #2026).
            token_url = self.oauth_settings.get("token_endpoint")
            if not token_url:
                raise ValueError(
                    f"No token_endpoint configured for provider {provider!r}. "
                    "Set oauth_settings['token_endpoint']; refusing to send the "
                    "authorization code and client_secret to a default host."
                )

        # Make token request using HTTPRequestNode
        try:
            token_response = await self.http_client.async_run(
                method="POST",
                url=token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if not token_response["success"]:
                raise ValueError(
                    f"Token exchange failed: {token_response.get('error')}"
                )

            # The token document lives at the envelope's "content" key;
            # returning the envelope made the caller's
            # token_result["access_token"] raise KeyError (issue #2060).
            return http_body(token_response)
        except Exception as e:
            # Fail closed for every endpoint. A failed token exchange NEVER
            # yields a token: there is no URL, host, or substring for which a
            # synthetic "success" is correct. Tests that need a token supply an
            # explicit http_client double.
            raise ValueError(f"Token exchange failed: {e}") from e

    async def _get_oauth_user_info(
        self, provider: str, access_token: str
    ) -> Dict[str, Any]:
        """Get user information from OAuth provider."""
        # Determine user info endpoint
        if provider == "azure":
            userinfo_url = "https://graph.microsoft.com/v1.0/me"
        elif provider == "google":
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        elif provider == "okta":
            userinfo_url = f"https://{self.oauth_settings.get('okta_domain')}/oauth2/default/v1/userinfo"
        else:
            userinfo_url = self.oauth_settings.get("userinfo_endpoint")

        # Make user info request
        try:
            userinfo_response = await self.http_client.async_run(
                method="GET",
                url=userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if not userinfo_response["success"]:
                raise ValueError(
                    f"User info request failed: {userinfo_response.get('error')}"
                )

            return http_body(userinfo_response)
        except Exception as e:
            # Fail closed. Deriving an identity from the *value* of a bearer
            # token let anyone presenting "test_access_token" be provisioned as
            # test.user@example.com once the userinfo call failed.
            raise ValueError(f"User info request failed: {e}") from e

    def _map_attributes(
        self, raw_attributes: Dict[str, Any], provider: str
    ) -> Dict[str, Any]:
        """Map provider-specific attributes to internal format."""
        mapped = {}

        for internal_key, provider_key in self.attribute_mapping.items():
            if provider_key in raw_attributes:
                mapped[internal_key] = raw_attributes[provider_key]

        # Provider-specific mappings
        if provider == "azure":
            mapped["email"] = raw_attributes.get("mail") or raw_attributes.get(
                "userPrincipalName"
            )
            mapped["firstName"] = raw_attributes.get("givenName")
            mapped["lastName"] = raw_attributes.get("surname")
        elif provider == "google":
            mapped["email"] = raw_attributes.get("email")
            mapped["firstName"] = raw_attributes.get("given_name")
            mapped["lastName"] = raw_attributes.get("family_name")
        elif provider == "ldap":
            mapped["email"] = raw_attributes.get("mail")
            mapped["firstName"] = raw_attributes.get("givenName")
            mapped["lastName"] = raw_attributes.get("sn")
            mapped["groups"] = raw_attributes.get("memberOf", [])

        # Ensure required fields
        if not mapped.get("email"):
            mapped["email"] = raw_attributes.get("email") or raw_attributes.get("mail")

        return mapped

    async def _provision_user(
        self, attributes: Dict[str, Any], provider: str
    ) -> Dict[str, Any]:
        """Provision user using Just-In-Time (JIT) provisioning.

        Note:
            This is the rule-based Core SDK version. For AI-powered intelligent
            field mapping and role assignment, use the Kaizen version:
            `from kaizen.nodes.auth import SSOAuthenticationNode`
        """
        email = attributes.get("email")
        if not email:
            raise ValueError("Email is required for user provisioning")

        # Rule-based user provisioning with attribute mapping
        user_profile = {
            "user_id": email,
            "email": email,
            "first_name": attributes.get("firstName", ""),
            "last_name": attributes.get("lastName", ""),
            "department": attributes.get("department", ""),
            "roles": self._assign_roles_from_attributes(attributes, provider),
        }

        # Log user provisioning. AuditLogNode is sync-only -- it defines
        # neither async_run nor execute_async, so awaiting async_run raised
        # AttributeError after the provisioning had already happened, and no
        # provisioning was ever recorded (issue #2060). It is offloaded to a
        # worker thread, and given the parameters it actually reads
        # (event_type/message/user_id/event_data) rather than action=/details=,
        # which it drops.
        await asyncio.to_thread(
            self.audit_logger.execute,
            event_type="user_provisioned",
            message=f"Provisioned SSO user {email} from {provider}",
            user_id=log_safe(email),
            event_data=redact_mapping(
                {
                    "provider": provider,
                    "attributes": attributes,
                    "profile": user_profile,
                }
            ),
        )

        return user_profile

    def _assign_roles_from_attributes(
        self, attributes: Dict[str, Any], provider: str
    ) -> List[str]:
        """Assign roles based on user attributes using rule-based logic."""
        roles = ["user"]  # Default role

        # Check groups for role assignment
        groups = attributes.get("groups", [])
        for group in groups:
            group_lower = group.lower()
            if "admin" in group_lower or "administrator" in group_lower:
                roles.append("admin")
            elif "manager" in group_lower:
                roles.append("manager")
            elif "developer" in group_lower or "engineer" in group_lower:
                roles.append("developer")

        # Check department for additional roles
        department = attributes.get("department", "").lower()
        if "it" in department or "technology" in department:
            if "developer" not in roles:
                roles.append("developer")

        return list(set(roles))  # Remove duplicates

    async def _create_sso_session(
        self,
        user_id: str,
        provider: str,
        attributes: Dict[str, Any],
        tokens: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Create SSO session for authenticated user."""
        session_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + self.session_timeout

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "provider": provider,
            "attributes": attributes,
            "tokens": tokens,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_activity": datetime.now(UTC).isoformat(),
        }

        # Store session
        self.active_sessions[session_id] = session_data

        # Cleanup old sessions for user
        await self._cleanup_user_sessions(user_id)

        return session_data

    async def _cleanup_user_sessions(self, user_id: str):
        """Clean up old sessions for user based on max concurrent sessions."""
        user_sessions = []
        for session_id, session_data in self.active_sessions.items():
            if session_data["user_id"] == user_id:
                user_sessions.append((session_id, session_data))

        # Sort by creation time, keep most recent
        user_sessions.sort(key=lambda x: x[1]["created_at"], reverse=True)

        # Remove excess sessions
        if len(user_sessions) > self.max_concurrent_sessions:
            for session_id, _ in user_sessions[self.max_concurrent_sessions :]:
                del self.active_sessions[session_id]

    async def _validate_token(
        self, provider: str, request_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate SSO token or session."""
        token = request_data.get("token") or request_data.get("session_id")
        if not token:
            raise ValueError("Token or session_id required for validation")

        # Check if it's a session ID
        if token in self.active_sessions:
            session_data = self.active_sessions[token]

            # Check expiration
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.now(UTC) > expires_at:
                del self.active_sessions[token]
                return {"valid": False, "reason": "session_expired"}

            # Update last activity
            session_data["last_activity"] = datetime.now(UTC).isoformat()

            # Never hand the upstream IdP tokens back to a session holder.
            # Returning session_data verbatim upgraded an app-scoped, revocable
            # session id into the IdP's access_token AND refresh_token, which
            # this app cannot revoke and which work directly against the
            # provider's APIs (issue #2026). They stay in the internal store.
            public_session_data = {
                k: v for k, v in session_data.items() if k != "tokens"
            }

            return {
                "valid": True,
                "session_data": public_session_data,
                "user_id": session_data["user_id"],
                "provider": session_data["provider"],
            }

        # Token-based validation (JWT, access tokens, etc.)
        return await self._validate_external_token(provider, token)

    async def _validate_external_token(
        self, provider: str, token: str
    ) -> Dict[str, Any]:
        """Validate external tokens (JWT, OAuth access tokens)."""
        if provider in ["azure", "google", "okta"]:
            # Validate OAuth token by calling userinfo endpoint
            try:
                user_info = await self._get_oauth_user_info(provider, token)
                return {"valid": True, "user_info": user_info, "provider": provider}
            except Exception:
                return {"valid": False, "reason": "invalid_token"}

        return {"valid": False, "reason": "unsupported_provider"}

    async def _handle_logout(
        self, user_id: str, provider: str, **kwargs
    ) -> Dict[str, Any]:
        """Handle SSO logout."""
        sessions_removed = 0

        # Remove all sessions for user
        sessions_to_remove = []
        for session_id, session_data in self.active_sessions.items():
            if session_data["user_id"] == user_id:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.active_sessions[session_id]
            sessions_removed += 1

        # Log logout. Sync-only sink -- see _provision_user for why this is a
        # thread offload with event_type/message/event_data (issue #2060).
        await asyncio.to_thread(
            self.audit_logger.execute,
            event_type="sso_logout",
            message=f"SSO logout for user {user_id}",
            user_id=log_safe(user_id),
            event_data={"provider": provider, "sessions_removed": sessions_removed},
        )

        return {
            "logged_out": True,
            "user_id": user_id,
            "provider": provider,
            "sessions_removed": sessions_removed,
        }

    async def _get_sso_status(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Get SSO status for user."""
        user_sessions = []
        for session_id, session_data in self.active_sessions.items():
            if session_data["user_id"] == user_id:
                user_sessions.append(
                    {
                        "session_id": session_id,
                        "provider": session_data["provider"],
                        "created_at": session_data["created_at"],
                        "last_activity": session_data["last_activity"],
                        "expires_at": session_data["expires_at"],
                    }
                )

        return {
            "user_id": user_id,
            "active_sessions": len(user_sessions),
            "sessions": user_sessions,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "providers_enabled": self.providers,
        }

    async def _log_security_event(self, **event_data):
        """Log security events using SecurityEventNode.

        This called ``security_logger.async_run``, which ``SecurityEventNode``
        does not define -- it exposes ``execute``. Every successful
        :meth:`async_run` therefore raised ``AttributeError`` after doing its
        work, so the whole async SSO surface was unusable and NO security event
        was ever recorded. Invisible to the suite because nothing drove
        ``async_run`` end to end; surfaced by the sync-bridge tests added for
        issue #2026.

        The probe loop that used to stand here -- ``getattr(self.security_logger,
        surface, None)`` over ``("async_run", "execute_async")`` -- was dead
        code: ``SecurityEventNode`` extends the plain ``Node`` and defines
        neither, so both probes yielded ``None`` on every call and execution
        always fell through. That is the dead-attribute-guard shape issue #2057
        names as BLOCKED, and it hid the second half of the defect: the payload
        below was built from ``source``/``timestamp``/``details``, none of which
        are parameters of the node, so they were dropped and ``severity`` /
        ``message`` / ``user_id`` were never supplied. Every SSO security event
        -- including authentication FAILURES -- was recorded as a blank INFO
        line with no user, well under any alerting threshold (issue #2060).

        The sink is now named statically and offloaded to a worker thread, and
        it is given the parameters it reads.
        """
        event_type = event_data.get("event_type", "sso_event")
        severity = str(event_data.get("severity") or "INFO").upper()
        if severity == "INFO" and (
            "failure" in event_type or "error" in event_type or "denied" in event_type
        ):
            # An authentication failure recorded at INFO sits below the default
            # HIGH alert threshold and never pages anyone.
            severity = "HIGH"

        try:
            await asyncio.to_thread(
                self.security_logger.execute,
                event_type=event_type,
                severity=severity,
                message=f"{event_type} via sso_authentication_node",
                user_id=log_safe(event_data.get("user_id")),
                metadata=redact_mapping(
                    {
                        "source": "sso_authentication_node",
                        **{k: v for k, v in event_data.items() if k != "severity"},
                    }
                ),
            )
        except Exception as e:  # noqa: BLE001 - logging must not break auth
            self.log_info(
                f"Security event was NOT recorded ({type(e).__name__}); "
                "the operation itself is unaffected."
            )

    def get_sso_statistics(self) -> Dict[str, Any]:
        """Get SSO usage statistics."""
        total_sessions = len(self.active_sessions)
        provider_counts = {}

        for session_data in self.active_sessions.values():
            provider = session_data["provider"]
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

        return {
            "total_active_sessions": total_sessions,
            "sessions_by_provider": provider_counts,
            "providers_configured": self.providers,
            "jit_provisioning_enabled": self.enable_jit_provisioning,
            "encryption_enabled": self.encryption_enabled,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "session_timeout_hours": self.session_timeout.total_seconds() / 3600,
        }
