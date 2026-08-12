"""
Enterprise Authentication Provider Node

Unified authentication provider that orchestrates multiple authentication methods:
- Single Sign-On (SSO) - SAML, OAuth2, OIDC
- Multi-Factor Authentication (MFA)
- Directory Integration (LDAP, AD, Azure AD)
- Passwordless Authentication (WebAuthn, FIDO2)
- Social Login (Google, Microsoft, GitHub, etc.)
- Enterprise Identity Providers (Okta, Auth0, Ping, etc.)
- API Key Authentication
- JWT Token Authentication
- Certificate-based Authentication
"""

import asyncio
import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from kailash.nodes.api import AsyncHTTPRequestNode
from kailash.nodes.auth._http_response import http_body
from kailash.nodes.auth._log_hygiene import log_safe, redact_mapping
from kailash.nodes.auth.directory_integration import DirectoryIntegrationNode
from kailash.nodes.auth.mfa import MultiFactorAuthNode
from kailash.nodes.auth.session_management import SessionManagementNode
from kailash.nodes.auth.sso import SSOAuthenticationNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import JSONReaderNode
from kailash.nodes.mixins import LoggingMixin, PerformanceMixin, SecurityMixin
from kailash.nodes.security import AuditLogNode, SecurityEventNode

# One-time-per-process latch for the "JWT issuer is not pinned" warning
# (issue #2089). Module-level, not per-instance: a provider constructed per
# request would warn per request, which is the per-operation shape that got
# the original signal filtered out.
#
# A mutated SET rather than a rebound bool, so no function needs a `global`
# statement; a test re-arms it with `_WARNED_ONCE.clear()`.
_WARNED_ONCE: set = set()
_ISSUER_WARN_LOCK = threading.Lock()


@register_node()
class EnterpriseAuthProviderNode(SecurityMixin, PerformanceMixin, LoggingMixin, Node):
    """
    Enterprise Authentication Provider Node

    Unified authentication orchestration with advanced security features,
    adaptive authentication, risk assessment, and comprehensive audit trails.
    """

    def __init__(
        self,
        name: str = "enterprise_auth_provider",
        enabled_methods: List[str] | None = None,
        primary_method: str = "sso",
        fallback_methods: List[str] | None = None,
        sso_config: Dict[str, Any] | None = None,
        mfa_config: Dict[str, Any] | None = None,
        directory_config: Dict[str, Any] | None = None,
        session_config: Dict[str, Any] | None = None,
        jwt_config: Dict[str, Any] | None = None,
        api_key_store: Dict[str, Dict[str, Any]] | None = None,
        api_key_pepper: str | None = None,
        api_key_kdf_iterations: int = 10_000,
        user_permissions: Dict[str, List[str]] | None = None,
        default_permissions: List[str] | None = None,
        risk_assessment_enabled: bool = True,
        adaptive_auth_enabled: bool = True,
        fraud_detection_enabled: bool = True,
        compliance_mode: str = "strict",
        audit_level: str = "detailed",
        rate_limiting_enabled: bool = True,
        max_login_attempts: int = 5,
        lockout_duration: timedelta = timedelta(minutes=30),
    ):
        # Set attributes before calling super().__init__()
        self.name = name
        self.enabled_methods = enabled_methods or [
            "sso",
            "mfa",
            "directory",
            "social",
            "api_key",
            "jwt",
        ]
        self.primary_method = primary_method
        self.fallback_methods = fallback_methods or ["directory", "mfa"]
        self.sso_config = sso_config or {}
        self.mfa_config = mfa_config or {}
        self.directory_config = directory_config or {}
        self.session_config = session_config or {}
        # JWT verification material. Without a key, 'jwt' authentication fails
        # closed rather than trusting an unverified payload (issue #2026).
        self.jwt_config = jwt_config or {}
        # Issued API keys, keyed by _api_key_digest(key) -> {"user_id": ...,
        # optional "expires_at" (epoch seconds) and "revoked" (bool)}. Empty
        # means 'api_key' authentication fails closed.
        self.api_key_store = api_key_store or {}
        # Server-side secret mixed into the API-key lookup digest so a stolen
        # api_key_store cannot be attacked by precomputation.
        self.api_key_pepper = api_key_pepper or ""
        self.api_key_kdf_iterations = max(1, int(api_key_kdf_iterations))
        # Explicit user -> permissions mapping. Permissions are never inferred
        # from the text of a user_id (issue #2026); unlisted users get
        # default_permissions only.
        self.user_permissions = user_permissions or {}
        self.default_permissions = (
            ["read"] if default_permissions is None else list(default_permissions)
        )
        self.risk_assessment_enabled = risk_assessment_enabled
        self.adaptive_auth_enabled = adaptive_auth_enabled
        self.fraud_detection_enabled = fraud_detection_enabled
        self.compliance_mode = compliance_mode
        self.audit_level = audit_level
        self.rate_limiting_enabled = rate_limiting_enabled
        self.max_login_attempts = max_login_attempts
        self.lockout_duration = lockout_duration

        # Internal state
        self.auth_sessions = {}
        self.failed_attempts = {}
        self.locked_accounts = {}
        self.risk_scores = {}
        self.auth_statistics = {
            "total_attempts": 0,
            "successful_auths": 0,
            "failed_auths": 0,
            "mfa_challenges": 0,
            "blocked_attempts": 0,
        }

        super().__init__(name=name)

        # Initialize authentication nodes
        self._setup_auth_nodes()

    def _warn_if_issuer_unpinned(self) -> None:
        """Say ONCE, at WARN, that no issuer is pinned for JWT auth.

        An unset ``jwt_config['issuer']`` means every token signed with the
        configured key is accepted regardless of who minted it. The code
        already detected that and said so -- at ``INFO``, once per validated
        token. Both halves of that were the defect (issue #2089):

        * ``INFO`` is below every default alert threshold and below most
          production log-shipping filters, so in practice the operator was
          never told. ``rules/security.md`` § "Secure-Default For A New
          Security Feature" requires a protection that is OFF to fail closed
          or emit a LOUD signal naming the unprotected state and its exact
          wiring. This one cannot fail closed without breaking every
          deployment that legitimately accepts multi-issuer tokens, so it
          takes the loud-WARN branch.
        * Per-token, it read as transient and got filtered -- the same
          mistake this repo already made and corrected in #2035. Once per
          process is what an operator can actually act on.

        The flag is module-level rather than per-instance because a provider
        constructed per request would otherwise warn per request, which is
        the per-operation shape all over again.
        """
        if self.jwt_config.get("issuer"):
            return
        with _ISSUER_WARN_LOCK:
            if "issuer_unpinned" in _WARNED_ONCE:
                return
            _WARNED_ONCE.add("issuer_unpinned")
        self.log_warning(
            "JWT issuer is NOT pinned: jwt_config['issuer'] is unset, so ANY "
            "token signed with the configured key is accepted, whoever minted "
            "it. Pin it with "
            "EnterpriseAuthProviderNode(jwt_config={..., 'issuer': "
            "'https://issuer.example.com'}). This warning is emitted once per "
            "process."
        )

    def _setup_auth_nodes(self):
        """Initialize all authentication-related nodes."""
        # Say it at construction, not only on the first token that happens to
        # arrive: an operator reads startup output, and a deployment that
        # never validates a token before the incident never saw the signal.
        if "jwt" in self.enabled_methods:
            self._warn_if_issuer_unpinned()

        # Core authentication nodes
        self.sso_node = SSOAuthenticationNode(
            name=f"{self.name}_sso", **self.sso_config
        )

        # This provider is the authorizing host for its own MFA node, so it
        # takes the explicit require_actor=False opt-out rather than a fake
        # actor (issue #2047).
        #
        # It is entitled to: every call it makes passes a SERVER-DERIVED
        # subject. `_authenticate` refuses a request whose credential asserts
        # no principal and overrides a mismatched caller-supplied user_id with
        # the asserted one (#2035, ~:455-470), so `user_id` reaching the MFA
        # node is the principal the credential proved -- not the one the
        # request asked for. It also cannot pass an actor session: MFA
        # verification happens BEFORE a session exists, which is what it is
        # gating the creation of.
        #
        # An operator wanting enforcement here supplies it explicitly, e.g.
        # mfa_config={"require_actor": True, "actor_resolver": ...}; the
        # setdefault below means their value wins.
        mfa_config = dict(self.mfa_config)
        mfa_config.setdefault("require_actor", False)
        self.mfa_node = MultiFactorAuthNode(name=f"{self.name}_mfa", **mfa_config)

        self.directory_node = DirectoryIntegrationNode(
            name=f"{self.name}_directory", **self.directory_config
        )

        self.session_node = SessionManagementNode(
            name=f"{self.name}_session", **self.session_config
        )

        # Supporting nodes
        #
        # AsyncHTTPRequestNode, not HTTPRequestNode: every caller of this node
        # is on an async path (_validate_social_token), and the sync
        # HTTPRequestNode has no awaitable surface at all -- the previous
        # execute_async() call against it raised AttributeError, which the
        # caller's except-clause then reported as "Token validation failed"
        # (issue #2060). Both return {"success": ..., "response": ...}.
        self.http_client = AsyncHTTPRequestNode(name=f"{self.name}_http")

        self.security_logger = SecurityEventNode(name=f"{self.name}_security")

        self.audit_logger = AuditLogNode(name=f"{self.name}_audit")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="Auth action: authenticate, authorize, logout, validate, assess_risk",
            ),
            "auth_method": NodeParameter(
                name="auth_method",
                type=str,
                required=False,
                description="Authentication method: sso, mfa, directory, passwordless, social, api_key, jwt",
            ),
            "credentials": NodeParameter(
                name="credentials",
                type=dict,
                required=False,
                description="Authentication credentials",
            ),
            "user_id": NodeParameter(
                name="user_id", type=str, required=False, description="User identifier"
            ),
            "session_id": NodeParameter(
                name="session_id",
                type=str,
                required=False,
                description="Session identifier",
            ),
            "risk_context": NodeParameter(
                name="risk_context",
                type=dict,
                required=False,
                description="Risk assessment context (IP, device, location, etc.)",
            ),
            "permissions": NodeParameter(
                name="permissions",
                type=list,
                required=False,
                description="Required permissions for authorization",
            ),
            "resource": NodeParameter(
                name="resource",
                type=str,
                required=False,
                description="Resource being accessed",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Sync entry point (Node ABC contract). Use async_run() for this node."""
        raise RuntimeError(
            f"{type(self).__name__} is async-only. Use async_run() instead."
        )

    async def async_run(
        self,
        action: str,
        auth_method: str | None = None,
        credentials: Dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        risk_context: Dict[str, Any] | None = None,
        permissions: List[str] | None = None,
        resource: str | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute enterprise authentication operations.

        Args:
            action: Authentication action to perform
            auth_method: Specific authentication method
            credentials: Authentication credentials
            user_id: User identifier
            session_id: Session identifier
            risk_context: Risk assessment context
            permissions: Required permissions
            resource: Resource being accessed

        Returns:
            Dict containing authentication results
        """
        start_time = time.time()
        auth_id = str(uuid.uuid4())

        try:
            self.log_info(f"Starting enterprise auth operation: {action}")
            self.auth_statistics["total_attempts"] += 1

            # Initialize risk context
            if not risk_context:
                risk_context = self._extract_risk_context(kwargs)

            # Check rate limiting
            if self.rate_limiting_enabled and action == "authenticate":
                rate_limit_check = await self._check_rate_limiting(
                    user_id, risk_context  # type: ignore[arg-type]
                )
                if not rate_limit_check["allowed"]:
                    return rate_limit_check

            # Route to appropriate handler
            if action == "authenticate":
                result = await self._authenticate(
                    auth_method, credentials, user_id, risk_context, auth_id, **kwargs  # type: ignore[arg-type]
                )
            elif action == "authorize":
                result = await self._authorize(
                    user_id, session_id, permissions, resource, risk_context, **kwargs  # type: ignore[arg-type]
                )
            elif action == "logout":
                result = await self._logout(user_id, session_id, **kwargs)  # type: ignore[arg-type]
            elif action == "validate":
                result = await self._validate_session(session_id, **kwargs)  # type: ignore[arg-type]
            elif action == "assess_risk":
                result = await self._assess_risk(user_id, risk_context, **kwargs)  # type: ignore[arg-type]
            elif action == "get_methods":
                result = await self._get_available_methods(user_id, **kwargs)  # type: ignore[arg-type]
            elif action == "challenge_mfa":
                result = await self._challenge_mfa(user_id, auth_method, **kwargs)  # type: ignore[arg-type]
            else:
                raise ValueError(f"Unsupported authentication action: {action}")

            # Add processing metrics
            processing_time = (time.time() - start_time) * 1000
            result["processing_time_ms"] = processing_time
            result["auth_id"] = auth_id
            result["timestamp"] = datetime.now(UTC).isoformat()

            # Derive success from the operation's own verdict before applying
            # any default. Defaulting to True stamped every authorization
            # DENIAL as success=True and audited it as "auth_success", so a
            # caller gating on the SDK's conventional success field granted
            # access on a denial (issue #2026).
            if "success" not in result:
                if "authorized" in result:
                    result["success"] = bool(result["authorized"])
                elif "authenticated" in result:
                    result["success"] = bool(result["authenticated"])
                elif "valid" in result:
                    result["success"] = bool(result["valid"])
                elif "error" in result:
                    result["success"] = False
                else:
                    result["success"] = True

            # Log successful operation.
            #
            # The event is attributed to the principal the operation RESOLVED
            # to, not to the user_id the caller typed. _authenticate and
            # _authorize both discard the caller's claim in favour of the
            # credential's / session's subject (issue #2026, PR #2035); an
            # audit record still naming the caller's claim would attribute
            # alice's login to "admin" and defeat the same fix one layer up.
            # The claim is retained alongside it, because a caller asserting a
            # subject it did not authenticate as is exactly what an auditor
            # needs to see.
            # "auth_success" is reserved for actions that actually authenticate
            # a principal. get_methods / assess_risk / challenge_mfa echo the
            # caller's own user_id back and default to success=True, so emitting
            # auth_success for them wrote a record byte-identical to a genuine
            # login for a subject nobody authenticated -- an unauthenticated
            # caller could forge "alice logged in" at will, and the counter
            # agreed with it (issue #2060).
            # "validate" is deliberately NOT here. It is a per-request session
            # check, and counting each one as a successful authentication makes
            # auth_statistics["successful_auths"] mean something other than
            # "logins" -- an auditor counting auth_success would over-count by
            # however chatty the caller is.
            authenticating = action in {"authenticate", "authorize"}
            if result.get("success", True):
                if authenticating:
                    self.auth_statistics["successful_auths"] += 1
                resolved_user_id = result.get("user_id") or user_id
                await self._log_auth_event(
                    event_type=(
                        "auth_success" if authenticating else f"{action}_success"
                    ),
                    action=action,
                    auth_id=auth_id,
                    user_id=resolved_user_id,
                    claimed_user_id=user_id,
                    auth_method=auth_method,
                    risk_context=risk_context,
                    processing_time_ms=processing_time,
                )
            else:
                self.auth_statistics["failed_auths"] += 1
                await self._log_auth_event(
                    event_type="auth_failure",
                    action=action,
                    auth_id=auth_id,
                    user_id=user_id,
                    auth_method=auth_method,
                    risk_context=risk_context,
                    error=result.get("error"),
                    processing_time_ms=processing_time,
                )

            self.log_info(
                f"Enterprise auth operation completed in {processing_time:.1f}ms"
            )
            return result

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.auth_statistics["failed_auths"] += 1

            # Log failure
            await self._log_auth_event(
                event_type="auth_error",
                action=action,
                auth_id=auth_id,
                user_id=user_id,
                auth_method=auth_method,
                error=str(e),
                processing_time_ms=processing_time,
            )

            self.log_error(f"Enterprise auth operation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time_ms": processing_time,
                "auth_id": auth_id,
                "action": action,
            }

    async def _authenticate(
        self,
        auth_method: str,
        credentials: Dict[str, Any],
        user_id: str,
        risk_context: Dict[str, Any],
        auth_id: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Orchestrate authentication process."""
        # Risk assessment
        if self.risk_assessment_enabled:
            risk_assessment = await self._assess_risk(user_id, risk_context)
            risk_score = risk_assessment["risk_score"]
        else:
            risk_score = 0.0

        # Determine authentication method
        if not auth_method:
            auth_method = await self._determine_auth_method(
                user_id, risk_score, credentials
            )

        # Validate authentication method
        if auth_method not in self.enabled_methods:
            raise ValueError(f"Authentication method {auth_method} is not enabled")

        # Perform primary authentication
        primary_auth_result = await self._perform_authentication(
            auth_method, credentials, user_id, risk_context
        )

        if not primary_auth_result.get("authenticated"):
            # Record failed attempt
            await self._record_failed_attempt(user_id, risk_context)
            return {
                "success": False,
                "authenticated": False,
                "error": primary_auth_result.get("error", "Authentication failed"),
                "auth_method": auth_method,
                "risk_score": risk_score,
            }

        # The session belongs to the principal the CREDENTIAL asserts, not to
        # the user_id the caller typed. Verifying a JWT/API key and then minting
        # a session for a caller-chosen name let anyone holding any valid
        # credential authenticate as anyone else (issue #2026).
        #
        # The assertion is MANDATORY, not opportunistic: an opportunistic
        # override silently fell back to the caller's user_id for any method
        # that authenticates without naming a principal (the directory methods
        # return "username", and social can return user_id=None).
        asserted_user_id = primary_auth_result.get(
            "user_id"
        ) or primary_auth_result.get("username")
        if not isinstance(asserted_user_id, str) or not asserted_user_id:
            self.log_info(
                f"Authentication method {auth_method} asserted no principal; "
                "refusing rather than trusting the requested user_id."
            )
            return {
                "success": False,
                "authenticated": False,
                "error": "Authentication method asserted no principal",
                "auth_method": auth_method,
                "risk_score": risk_score,
            }
        if user_id and asserted_user_id != user_id:
            self.log_info(
                "Requested user_id does not match the authenticated "
                "principal; using the authenticated principal."
            )
        user_id = asserted_user_id

        # Adaptive authentication - determine if additional factors needed
        additional_factors_required = []
        if self.adaptive_auth_enabled:
            additional_factors_required = await self._determine_additional_factors(
                user_id, risk_score, auth_method, primary_auth_result
            )

        # Handle additional authentication factors
        additional_auth_results = []
        for factor in additional_factors_required:
            factor_result = await self._handle_additional_factor(
                factor, user_id, credentials, risk_context
            )
            additional_auth_results.append(factor_result)

            if not factor_result.get("success"):
                return {
                    "success": False,
                    "authenticated": False,
                    "error": f"Additional factor {factor} failed",
                    "auth_method": auth_method,
                    "additional_factors_required": additional_factors_required,
                    "risk_score": risk_score,
                }

        # All authentication successful - create session
        self.log_info(f"Creating session for user {user_id}...")
        session_result = await self.session_node.async_run(
            action="create",
            user_id=user_id,
            auth_method=auth_method,
            risk_score=risk_score,
            additional_factors=additional_factors_required,
            ip_address=risk_context.get("ip_address"),
            device_info=risk_context.get("device_info"),
        )
        # A credential that verifies but yields no session is NOT an
        # authentication. This returned success=True / authenticated=True with
        # session_id=None whenever the session step refused, took the caller's
        # success branch, incremented successful_auths, and emitted an
        # auth_success record for a login that minted nothing (issue #2060).
        #
        # Reachable today: SessionManagementNode refuses "create" without an
        # ip_address, and _extract_risk_context only supplies a default when
        # risk_context is FALSY. A caller passing a non-empty risk_context that
        # omits ip_address -- device_info or user_agent only, the ordinary
        # shape -- skips that fallback and lands here. Same class as the
        # success-derivation fix in async_run: the verdict comes from the
        # operation, never from a default.
        if not session_result.get("success") or not session_result.get("session_id"):
            return {
                "success": False,
                "authenticated": False,
                "error": "session_creation_failed",
                "reason": "session_creation_failed",
                "user_id": user_id,
                "auth_method": auth_method,
                "risk_score": risk_score,
                "session_details": session_result,
            }

        self.log_info(f"Session created: {session_result.get('session_id')}")

        # Clear failed attempts on successful auth
        if user_id in self.failed_attempts:
            del self.failed_attempts[user_id]

        return {
            "success": True,
            "authenticated": True,
            "user_id": user_id,
            "session_id": session_result.get("session_id"),
            "auth_method": auth_method,
            "additional_factors_used": additional_factors_required,
            "risk_score": risk_score,
            "primary_auth_result": primary_auth_result,
            "additional_auth_results": additional_auth_results,
            "session_details": session_result,
        }

    async def _perform_authentication(
        self,
        auth_method: str,
        credentials: Dict[str, Any],
        user_id: str,
        risk_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Perform authentication using specified method."""
        if auth_method == "sso":
            return await self.sso_node.async_run(
                action="callback",
                provider=credentials.get("provider"),
                request_data=credentials.get("request_data"),
                user_id=user_id,
            )

        elif auth_method == "directory":
            return await self.directory_node.async_run(
                action="authenticate", credentials=credentials
            )

        elif auth_method == "mfa":
            return await self.mfa_node.async_run(
                action="verify",
                user_id=user_id,
                code=credentials.get("mfa_code"),
                method=credentials.get("mfa_method", "totp"),
            )

        elif auth_method == "social":
            return await self._authenticate_social(credentials, user_id, risk_context)

        elif auth_method == "api_key":
            return await self._authenticate_api_key(credentials, user_id, risk_context)

        elif auth_method == "jwt":
            return await self._authenticate_jwt(credentials, user_id, risk_context)

        elif auth_method in {"passwordless", "certificate"}:
            raise ValueError(
                f"Authentication method {auth_method!r} is not implemented in the "
                f"Core SDK class — it requires protocol-specific cryptography "
                f"(WebAuthn/FIDO2 or X.509 client certificate validation). "
                f"Subclass EnterpriseAuthProviderNode and override "
                f"_perform_authentication() to add this method, or use a "
                f"specialized auth provider package."
            )

        else:
            raise ValueError(f"Unsupported authentication method: {auth_method}")

    async def _authenticate_social(
        self, credentials: Dict[str, Any], user_id: str, risk_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Authenticate using social providers."""
        provider = credentials.get("social_provider")
        access_token = credentials.get("access_token")

        if not provider or not access_token:
            return {
                "authenticated": False,
                "error": "Social provider and access token required",
            }

        # Validate token with social provider
        validation_result = await self._validate_social_token(provider, access_token)

        if validation_result.get("valid"):
            # The provider must name the principal. The key is always present
            # here but may be None (a provider returning neither email nor
            # login), so a `.get(key, default)` fallback never fired and the
            # caller-supplied user_id was used instead (issue #2026).
            social_user_id = validation_result.get("user_id")
            if not isinstance(social_user_id, str) or not social_user_id:
                return {
                    "authenticated": False,
                    "error": "Social provider returned no user identity",
                }
            return {
                "authenticated": True,
                "user_id": social_user_id,
                "auth_method": "social",
                "social_provider": provider,
                "user_info": validation_result.get("user_info"),
            }
        else:
            return {"authenticated": False, "error": "Invalid social token"}

    def _api_key_digest(self, api_key: str) -> str:
        """Derive the lookup digest for an issued API key.

        PBKDF2-HMAC-SHA256, salted with ``api_key_pepper``. The derivation runs
        ONCE per authentication -- the result is a lookup key, not a value
        compared against every stored entry -- so an iteration count is
        affordable here in a way it would not be for a scan.

        The iteration count (``api_key_kdf_iterations``, default 10_000) is
        modest by password-hashing standards, deliberately: API keys are
        high-entropy values this system generates, so the offline-guessing
        attack that motivates a 100k+ count does not apply. It buys
        defence-in-depth against a leaked ``api_key_store`` without putting a
        password-grade derivation on every API request.

        Args:
            api_key: The presented key.

        Returns:
            Hex digest used as the ``api_key_store`` lookup key.
        """
        salt = str(self.api_key_pepper or "kailash-api-key").encode("utf-8")
        return hashlib.pbkdf2_hmac(
            "sha256",
            api_key.encode("utf-8"),
            salt,
            self.api_key_kdf_iterations,
        ).hex()

    async def _authenticate_api_key(
        self, credentials: Dict[str, Any], user_id: str, risk_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Authenticate using API key."""
        api_key = credentials.get("api_key")
        if not api_key:
            return {"authenticated": False, "error": "API key required"}

        if not isinstance(api_key, str):
            return {"authenticated": False, "error": "Invalid API key"}

        # Log a DIGEST prefix, never key material: api_key[:6] on an "ak_"-
        # prefixed key exposed 3 real secret characters on every attempt.
        key_digest = self._api_key_digest(api_key)
        self.log_info(
            f"_authenticate_api_key - digest_prefix={key_digest[:8]}, "
            f"length={len(api_key)}"
        )

        # An API key is a bearer credential and MUST be checked against issued
        # key material. This previously accepted ANY string >= 32 chars starting
        # with "ak_" and derived the user_id from the key's own text, so an
        # attacker minted "ak_" + 29 chars + "_admin" and was authenticated as
        # admin without any key ever having been issued (issue #2026).
        if not self.api_key_store:
            self.log_info(
                "API key authentication attempted but no api_key_store is "
                "configured; refusing."
            )
            return {
                "authenticated": False,
                "error": (
                    "API key authentication is not configured. Provide "
                    "api_key_store={<digest(key)>: {'user_id': ...}} or remove "
                    "'api_key' from enabled_methods."
                ),
            }

        record = None
        for candidate_digest, candidate_record in self.api_key_store.items():
            # Constant-time compare so a timing signal cannot reveal which
            # issued key a guess is converging on.
            if secrets.compare_digest(key_digest, candidate_digest):
                record = candidate_record
                break

        if record is None:
            self.log_info("API key validation failed - key not recognised")
            return {"authenticated": False, "error": "Invalid API key"}

        if record.get("revoked"):
            self.log_info("API key validation failed - key revoked")
            return {"authenticated": False, "error": "Invalid API key"}

        expires_at = record.get("expires_at")
        if expires_at is not None and float(expires_at) <= time.time():
            self.log_info("API key validation failed - key expired")
            return {"authenticated": False, "error": "Invalid API key"}

        # A record without a user_id used to fall back to the CALLER-supplied
        # user_id, turning an operator typo into an impersonation primitive.
        principal = record.get("user_id")
        if not isinstance(principal, str) or not principal:
            self.log_info("API key validation failed - store record has no user_id")
            return {"authenticated": False, "error": "Invalid API key"}

        return {
            "authenticated": True,
            "user_id": principal,
            "auth_method": "api_key",
            "api_key_id": key_digest[:10] + "...",
        }

    async def _authenticate_jwt(
        self, credentials: Dict[str, Any], user_id: str, risk_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Authenticate using JWT token."""
        jwt_token = credentials.get("jwt_token")
        if not jwt_token:
            return {"authenticated": False, "error": "JWT token required"}

        # The signature is the ONLY thing that makes a JWT a credential. This
        # previously base64-decoded the payload with NO signature verification
        # and returned authenticated=True with user_id taken from the token's
        # own "sub" claim, so anyone could mint {"sub": "admin", "exp": <future>}
        # and be authenticated as admin (issue #2026).
        verification_key = self.jwt_config.get("secret") or self.jwt_config.get(
            "public_key"
        )
        if not verification_key:
            self.log_info(
                "JWT authentication attempted but no jwt_config verification "
                "key is configured; refusing."
            )
            return {
                "authenticated": False,
                "error": (
                    "JWT authentication is not configured. Provide "
                    "jwt_config={'secret': ...} or {'public_key': ...}, or "
                    "remove 'jwt' from enabled_methods."
                ),
            }

        try:
            import jwt as pyjwt
        except ImportError:
            return {
                "authenticated": False,
                "error": ("JWT authentication requires PyJWT. Install kailash[auth]."),
            }

        # Refuse a key/algorithm family mismatch rather than letting an
        # asymmetric public key be used as an HMAC secret: with a non-PEM
        # public key and HS256 in the list, anyone holding the PUBLIC key can
        # mint tokens.
        configured_algorithms = self.jwt_config.get("algorithms", ["HS256"])
        if isinstance(configured_algorithms, str):
            configured_algorithms = [configured_algorithms]
        algorithms = [str(a) for a in configured_algorithms]

        # Explicit allowlist. A denylist bucketed "none" as asymmetric and left
        # the whole defence resting on PyJWT's key-presence rule.
        allowed = {
            "HS256",
            "HS384",
            "HS512",
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512",
            "PS256",
            "PS384",
            "PS512",
            "EDDSA",
        }
        unknown = [a for a in algorithms if a.upper() not in allowed]
        if not algorithms or unknown:
            return {
                "authenticated": False,
                "error": (
                    "jwt_config['algorithms'] must be a non-empty list of "
                    f"supported signing algorithms; rejected: {unknown or algorithms}"
                ),
            }

        if self.jwt_config.get("secret") and self.jwt_config.get("public_key"):
            return {
                "authenticated": False,
                "error": (
                    "jwt_config sets both 'secret' and 'public_key'; configure "
                    "exactly one."
                ),
            }

        symmetric = {a for a in algorithms if a.upper().startswith("HS")}
        asymmetric = {a for a in algorithms if not a.upper().startswith("HS")}
        if symmetric and asymmetric:
            return {
                "authenticated": False,
                "error": (
                    "jwt_config['algorithms'] mixes symmetric and asymmetric "
                    "families; configure exactly one family."
                ),
            }
        if self.jwt_config.get("public_key") and symmetric:
            return {
                "authenticated": False,
                "error": (
                    "jwt_config['public_key'] cannot be used with an HMAC "
                    "algorithm; set an asymmetric algorithm (e.g. RS256)."
                ),
            }

        try:
            payload = pyjwt.decode(
                jwt_token,
                verification_key,
                algorithms=algorithms,
                audience=self.jwt_config.get("audience"),
                issuer=self.jwt_config.get("issuer"),
                # "sub" is required: without it the identity silently fell back
                # to the CALLER-supplied user_id, so any token signed with this
                # key that carries no subject (a reset token, a service token)
                # became an impersonation primitive.
                options={"require": ["exp", "sub"]},
            )
        except Exception as e:
            # Do not echo the library's message back to the caller: it
            # distinguishes "bad signature" from "expired" from "wrong
            # audience", which is an oracle for forging attempts.
            self.log_info(f"JWT validation failed: {type(e).__name__}")
            return {"authenticated": False, "error": "Invalid JWT token"}

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            self.log_info("JWT validation failed: missing or non-string sub")
            return {"authenticated": False, "error": "Invalid JWT token"}

        self._warn_if_issuer_unpinned()

        return {
            "authenticated": True,
            "user_id": subject,
            "auth_method": "jwt",
            "jwt_claims": payload,
        }

    async def _validate_social_token(
        self, provider: str, access_token: str
    ) -> Dict[str, Any]:
        """Validate social provider access token."""
        # Provider-specific token validation endpoints
        validation_urls = {
            "google": "https://www.googleapis.com/oauth2/v2/userinfo",
            "microsoft": "https://graph.microsoft.com/v1.0/me",
            "github": "https://api.github.com/user",
            "facebook": "https://graph.facebook.com/me",
        }

        url = validation_urls.get(provider)
        if not url:
            return {"valid": False, "error": f"Unsupported social provider: {provider}"}

        try:
            # Make request to validate token
            response = await self.http_client.async_run(
                method="GET",
                url=url,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.get("success"):
                # http_body(), not response["response"]: the value under
                # "response" is the HTTPResponse envelope and the provider's
                # userinfo document lives at its "content" key. Reading the
                # envelope found no email/login and reported a valid token as
                # invalid (issue #2060).
                user_info = http_body(response)
                return {
                    "valid": True,
                    "user_id": user_info.get("email") or user_info.get("login"),
                    "user_info": user_info,
                }
            else:
                return {"valid": False, "error": "Token validation failed"}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def _determine_auth_method(
        self, user_id: str, risk_score: float, credentials: Dict[str, Any]
    ) -> str:
        """Determine the most appropriate authentication method."""
        # Check available credential types
        available_methods = []

        if credentials.get("provider") or credentials.get("request_data"):
            available_methods.append("sso")
        if credentials.get("username") and credentials.get("password"):
            available_methods.append("directory")
        if credentials.get("mfa_code"):
            available_methods.append("mfa")
        if credentials.get("webauthn_data"):
            available_methods.append("passwordless")
        if credentials.get("social_provider") and credentials.get("access_token"):
            available_methods.append("social")
        if credentials.get("api_key"):
            available_methods.append("api_key")
        if credentials.get("jwt_token"):
            available_methods.append("jwt")
        if credentials.get("client_certificate"):
            available_methods.append("certificate")

        # Filter by enabled methods
        available_methods = [m for m in available_methods if m in self.enabled_methods]

        if not available_methods:
            raise ValueError("No suitable authentication method available")

        # Prefer primary method if available
        if self.primary_method in available_methods:
            return self.primary_method

        # Use first available method
        return available_methods[0]

    async def _determine_additional_factors(
        self,
        user_id: str,
        risk_score: float,
        primary_method: str,
        primary_auth_result: Dict[str, Any],
    ) -> List[str]:
        """Determine if additional authentication factors are required.

        Step-up requirements are derived from risk and method only. They are
        NEVER relaxed based on the *content* of an identifier: a principal who
        chooses their own user_id or API key would otherwise pick one
        containing "test." and opt themselves out of MFA.
        """
        additional_factors = []

        self.log_info(
            f"_determine_additional_factors - primary_method={primary_method}, "
            f"risk_score={risk_score}"
        )

        # Risk-based additional factors
        if risk_score > 0.7:  # High risk
            if "mfa" in self.enabled_methods and primary_method != "mfa":
                additional_factors.append("mfa")

        if risk_score > 0.9:  # Very high risk
            if "passwordless" in self.enabled_methods:
                additional_factors.append("passwordless")

        # Method-specific requirements
        if primary_method == "api_key":
            # API keys are bearer credentials: require a second factor.
            if "mfa" in self.enabled_methods and "mfa" not in additional_factors:
                additional_factors.append("mfa")

        # User-specific requirements (pre-existing sampling rule, retained)
        if user_id and hash(user_id) % 3 == 0:  # Every 3rd user
            if "mfa" in self.enabled_methods and "mfa" not in additional_factors:
                additional_factors.append("mfa")

        return additional_factors

    async def _handle_additional_factor(
        self,
        factor: str,
        user_id: str,
        credentials: Dict[str, Any],
        risk_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle additional authentication factor."""
        self.auth_statistics["mfa_challenges"] += 1

        if factor == "mfa":
            # Check if MFA code provided
            mfa_code = credentials.get("mfa_code")
            if not mfa_code:
                return {
                    "success": False,
                    "factor": factor,
                    "error": "MFA code required",
                    "challenge_required": True,
                }

            # Verify MFA
            mfa_result = await self.mfa_node.async_run(
                action="verify",
                user_id=user_id,
                code=mfa_code,
                method=credentials.get("mfa_method", "totp"),
            )

            return {
                "success": mfa_result.get("verified", False),
                "factor": factor,
                "mfa_result": mfa_result,
            }

        else:
            return {
                "success": False,
                "factor": factor,
                "error": f"Unsupported additional factor: {factor}",
            }

    async def _assess_risk(
        self, user_id: str, risk_context: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Assess authentication risk using AI and rule-based analysis."""
        if not self.risk_assessment_enabled:
            return {"risk_score": 0.0, "risk_level": "low", "factors": []}

        risk_factors = []
        risk_score = 0.0

        # IP-based risk assessment
        ip_address = risk_context.get("ip_address")
        if ip_address:
            ip_risk = await self._assess_ip_risk(ip_address, user_id)
            risk_score += ip_risk["score"]
            if ip_risk["score"] > 0:
                risk_factors.extend(ip_risk["factors"])

        # Device-based risk assessment
        device_info = risk_context.get("device_info")
        if device_info:
            device_risk = await self._assess_device_risk(device_info, user_id)
            risk_score += device_risk["score"]
            if device_risk["score"] > 0:
                risk_factors.extend(device_risk["factors"])

        # Time-based risk assessment
        login_time = risk_context.get("timestamp", datetime.now(UTC).isoformat())
        time_risk = await self._assess_time_risk(login_time, user_id)
        risk_score += time_risk["score"]
        if time_risk["score"] > 0:
            risk_factors.extend(time_risk["factors"])

        # Behavioral risk assessment
        if user_id:
            behavior_risk = await self._assess_behavior_risk(user_id, risk_context)
            risk_score += behavior_risk["score"]
            if behavior_risk["score"] > 0:
                risk_factors.extend(behavior_risk["factors"])

        # AI-based risk assessment
        if self.fraud_detection_enabled:
            ai_risk = await self._ai_risk_assessment(
                user_id, risk_context, risk_factors
            )
            risk_score += ai_risk["score"]
            if ai_risk["score"] > 0:
                risk_factors.extend(ai_risk["factors"])

        # Normalize risk score (0.0 to 1.0)
        risk_score = min(risk_score, 1.0)

        # Determine risk level
        if risk_score < 0.3:
            risk_level = "low"
        elif risk_score < 0.6:
            risk_level = "medium"
        elif risk_score < 0.8:
            risk_level = "high"
        else:
            risk_level = "critical"

        # Store risk score for user
        if user_id:
            self.risk_scores[user_id] = {
                "score": risk_score,
                "level": risk_level,
                "timestamp": datetime.now(UTC).isoformat(),
                "factors": risk_factors,
            }

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "factors": risk_factors,
            "assessment_timestamp": datetime.now(UTC).isoformat(),
        }

    async def _assess_ip_risk(self, ip_address: str, user_id: str) -> Dict[str, Any]:
        """Assess risk based on IP address."""
        risk_score = 0.0
        factors = []

        # Check if IP is from suspicious location (simulation)
        if ip_address.startswith("192.168."):
            # Local IP - low risk
            risk_score = 0.0
        elif ip_address.startswith("10."):
            # Private network - low risk
            risk_score = 0.1
        else:
            # External IP - check against threat databases (simulation)
            if hash(ip_address) % 10 == 0:  # 10% of IPs flagged as suspicious
                risk_score = 0.4
                factors.append("suspicious_ip")
            else:
                risk_score = 0.2
                factors.append("external_ip")

        # Check if IP has failed attempts recently
        if ip_address in self.failed_attempts:
            attempts = len(self.failed_attempts[ip_address])
            if attempts > 3:
                risk_score += 0.3
                factors.append("multiple_failed_attempts")

        return {"score": risk_score, "factors": factors}

    async def _assess_device_risk(
        self, device_info: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """Assess risk based on device information."""
        risk_score = 0.0
        factors = []

        # Check if device is recognized
        device_fingerprint = self._generate_device_fingerprint(device_info)

        # Check if device is explicitly marked as recognized
        if device_info.get("recognized", False):
            # Known device
            risk_score = 0.0
        else:
            # Unknown device
            risk_score = 0.3
            factors.append("unknown_device")

        # Check device characteristics
        if device_info.get("jailbroken") or device_info.get("rooted"):
            risk_score += 0.2
            factors.append("compromised_device")

        return {"score": risk_score, "factors": factors}

    async def _assess_time_risk(self, login_time: str, user_id: str) -> Dict[str, Any]:
        """Assess risk based on login time."""
        risk_score = 0.0
        factors = []

        try:
            login_dt = datetime.fromisoformat(login_time.replace("Z", "+00:00"))
            hour = login_dt.hour

            # Business hours (9 AM - 5 PM) are lower risk
            if 9 <= hour <= 17:
                risk_score = 0.0
            elif 6 <= hour <= 9 or 17 <= hour <= 22:
                risk_score = 0.1
                factors.append("unusual_hour")
            else:
                risk_score = 0.3
                factors.append("off_hours_login")

        except Exception:
            # If time parsing fails, assume medium risk
            risk_score = 0.2
            factors.append("invalid_timestamp")

        return {"score": risk_score, "factors": factors}

    async def _assess_behavior_risk(
        self, user_id: str, risk_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess risk based on user behavior patterns.

        Default implementation returns zero risk. Subclasses backed by a
        user activity store or behavioral analysis engine should override
        this method to inspect ``risk_context`` against historical patterns
        (recent IPs, devices, login times) and return a non-zero score.
        """
        return {"score": 0.0, "factors": []}

    async def _ai_risk_assessment(
        self, user_id: str, risk_context: Dict[str, Any], existing_factors: List[str]
    ) -> Dict[str, Any]:
        """Rule-based risk assessment.

        Note:
            This is the rule-based Core SDK version. For AI-powered fraud detection
            with intelligent pattern recognition, use the Kaizen version:
            `from kaizen.nodes.auth import EnterpriseAuthProviderNode`
        """
        # For low-risk scenarios with minimal factors, return low risk
        if not existing_factors or (
            len(existing_factors) == 1 and existing_factors[0] in ["unusual_hour"]
        ):
            # Check if it's a trusted scenario
            ip = risk_context.get("ip_address", "")
            device = risk_context.get("device_info", {})

            if (ip.startswith("10.") or ip.startswith("192.168.")) and device.get(
                "recognized"
            ):
                # Internal IP with recognized device - very low risk
                return {
                    "score": 0.0,
                    "factors": [],
                    "reasoning": "Trusted internal access from recognized device",
                }

        # Rule-based risk scoring
        risk_score = 0.0
        additional_factors = []

        # High number of existing factors = higher base risk
        if len(existing_factors) >= 3:
            risk_score += 0.3
            additional_factors.append("multiple_risk_factors")
        elif len(existing_factors) >= 2:
            risk_score += 0.2
            additional_factors.append("elevated_risk_factors")

        # Pattern matching for specific risk combinations
        if "suspicious_ip" in existing_factors and "unknown_device" in existing_factors:
            risk_score += 0.3
            additional_factors.append("suspicious_ip_and_device")

        if "geographic_anomaly" in existing_factors:
            risk_score += 0.2
            additional_factors.append("geographic_risk")

        if (
            "off_hours_login" in existing_factors
            and "unknown_device" in existing_factors
        ):
            risk_score += 0.15
            additional_factors.append("unusual_access_pattern")

        # Cap at 1.0
        risk_score = min(risk_score, 1.0)

        # Generate reasoning
        if risk_score < 0.3:
            reasoning = "Low risk based on standard authentication patterns"
        elif risk_score < 0.6:
            reasoning = "Medium risk due to unusual access patterns"
        else:
            reasoning = "High risk due to multiple suspicious indicators"

        return {
            "score": risk_score,
            "factors": additional_factors,
            "reasoning": reasoning,
        }

    def _generate_device_fingerprint(self, device_info: Dict[str, Any]) -> str:
        """Generate device fingerprint from device information."""
        fingerprint_data = {
            "user_agent": device_info.get("user_agent", ""),
            "screen_resolution": device_info.get("screen_resolution", ""),
            "timezone": device_info.get("timezone", ""),
            "language": device_info.get("language", ""),
            "platform": device_info.get("platform", ""),
        }

        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:16]

    async def _check_rate_limiting(
        self, user_id: str, risk_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check rate limiting for authentication attempts."""
        ip_address = risk_context.get("ip_address")
        current_time = datetime.now(UTC)

        # Check user-based rate limiting
        if user_id and user_id in self.locked_accounts:
            lock_info = self.locked_accounts[user_id]
            lock_expires = datetime.fromisoformat(lock_info["expires_at"])

            if current_time < lock_expires:
                self.auth_statistics["blocked_attempts"] += 1
                return {
                    "success": False,
                    "allowed": False,
                    "error": "Account temporarily locked",
                    "locked_until": lock_info["expires_at"],
                    "reason": "rate_limit_exceeded",
                }
            else:
                # Lock expired, remove it
                del self.locked_accounts[user_id]

        # Check failed attempts
        key = user_id or ip_address
        if key in self.failed_attempts:
            attempts = self.failed_attempts[key]
            recent_attempts = [
                attempt
                for attempt in attempts
                if (
                    current_time - datetime.fromisoformat(attempt["timestamp"])
                ).total_seconds()
                < 3600
            ]

            if len(recent_attempts) >= self.max_login_attempts:
                # Lock account
                lock_expires = current_time + self.lockout_duration
                self.locked_accounts[key] = {
                    "locked_at": current_time.isoformat(),
                    "expires_at": lock_expires.isoformat(),
                    "attempts": len(recent_attempts),
                }

                self.auth_statistics["blocked_attempts"] += 1
                return {
                    "success": False,
                    "allowed": False,
                    "error": "Too many failed attempts",
                    "locked_until": lock_expires.isoformat(),
                    "reason": "rate_limit_exceeded",
                }

        return {"allowed": True}

    async def _record_failed_attempt(self, user_id: str, risk_context: Dict[str, Any]):
        """Record failed authentication attempt."""
        key = user_id or risk_context.get("ip_address")
        if not key:
            return

        if key not in self.failed_attempts:
            self.failed_attempts[key] = []

        self.failed_attempts[key].append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "ip_address": risk_context.get("ip_address"),
                "user_agent": risk_context.get("user_agent"),
                "risk_context": risk_context,
            }
        )

        # Keep only recent attempts (last 24 hours)
        cutoff_time = datetime.now(UTC) - timedelta(hours=24)
        self.failed_attempts[key] = [
            attempt
            for attempt in self.failed_attempts[key]
            if datetime.fromisoformat(attempt["timestamp"]) > cutoff_time
        ]

    def _extract_risk_context(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Extract risk context from request data."""
        return {
            "ip_address": kwargs.get("ip_address", "127.0.0.1"),
            "user_agent": kwargs.get("user_agent", ""),
            "device_info": kwargs.get("device_info", {}),
            "location": kwargs.get("location", ""),
            "timestamp": kwargs.get("timestamp", datetime.now(UTC).isoformat()),
        }

    async def _authorize(
        self,
        user_id: str,
        session_id: str,
        permissions: List[str],
        resource: str,
        risk_context: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """Authorize user access to resource."""
        # A session is proof of authentication. Without one, user_id is just a
        # string the caller typed, so authorization cannot proceed: this
        # previously skipped validation entirely and authorized the caller's
        # claimed identity (issue #2026).
        if not session_id:
            return {
                "authorized": False,
                "error": "Session required for authorization",
                "reason": "session_required",
            }

        session_validation = await self.session_node.async_run(
            action="validate", session_id=session_id
        )

        if not session_validation.get("valid"):
            return {
                "authorized": False,
                "error": "Invalid session",
                "reason": "session_invalid",
            }

        # The session's subject wins over any caller-supplied user_id. The
        # subject is NESTED under "session_data" (see SessionManagementNode's
        # validate result); reading a top-level "user_id" always missed and
        # silently fell back to the caller's claim.
        session_data = session_validation.get("session_data") or {}
        session_user_id = session_data.get("user_id") or session_validation.get(
            "user_id"
        )
        if not session_user_id:
            return {
                "authorized": False,
                "error": "Session has no subject",
                "reason": "session_subject_missing",
            }
        user_id = session_user_id

        # An empty permission request is not a free pass.
        if not permissions:
            return {
                "authorized": False,
                "error": "No permissions requested",
                "reason": "no_permissions_requested",
            }

        # Check permissions (simulation)
        # In production, integrate with RBAC/ABAC system
        user_permissions = await self._get_user_permissions(user_id)

        missing_permissions = []
        for permission in permissions or []:
            if permission not in user_permissions:
                missing_permissions.append(permission)

        if missing_permissions:
            return {
                "authorized": False,
                "error": "Insufficient permissions",
                "missing_permissions": missing_permissions,
                "reason": "insufficient_permissions",
            }

        return {
            "authorized": True,
            "user_id": user_id,
            "permissions": permissions,
            "resource": resource,
        }

    async def _get_user_permissions(self, user_id: str) -> List[str]:
        """Get the permissions granted to a user.

        Resolved from the configured ``user_permissions`` mapping. Users with no
        entry receive the least-privilege default only.

        This previously derived permissions from the TEXT of the user_id --
        anything containing "admin" was granted ["read", "write", "delete",
        "admin"], and anything containing "manager" got write. Any directory or
        IdP that lets a principal influence their own username (``admin.intern``,
        ``sysadmin-contractor``) was therefore a privilege escalation
        (issue #2026).

        For real role/policy evaluation, use PACT rather than this mapping.
        """
        return list(self.user_permissions.get(user_id, self.default_permissions))

    async def _logout(self, user_id: str, session_id: str, **kwargs) -> Dict[str, Any]:
        """Handle user logout."""
        logout_results = []

        # Logout from session management
        if session_id:
            session_result = await self.session_node.async_run(
                action="terminate", session_id=session_id
            )
            logout_results.append({"component": "session", "result": session_result})

        # Logout from SSO if applicable
        sso_result = await self.sso_node.async_run(action="logout", user_id=user_id)
        logout_results.append({"component": "sso", "result": sso_result})

        # Clear risk scores
        if user_id in self.risk_scores:
            del self.risk_scores[user_id]

        # Log logout
        # AuditLogNode is a sync-only Node: it defines neither execute_async nor
        # async_run, so it is offloaded to a worker thread rather than awaited.
        # Its parameters are event_type/message/user_id/event_data -- the
        # action=/details= this used to pass were not read by execute() at all,
        # so a working call would still have written {"message": "", "data": {}}:
        # an audit record that does not say what happened (issue #2060).
        await asyncio.to_thread(
            self.audit_logger.execute,
            event_type="user_logout",
            message=f"User {log_safe(user_id, 64)} logged out",
            user_id=log_safe(user_id),
            event_data={"session_id": session_id, "logout_results": logout_results},
        )

        return {
            "logged_out": True,
            "user_id": user_id,
            "session_id": session_id,
            "logout_results": logout_results,
        }

    async def _validate_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """Validate session."""
        result = await self.session_node.async_run(
            action="validate", session_id=session_id
        )

        # Extract user_id from session_data for convenience
        if result.get("valid") and "session_data" in result:
            session_data = result["session_data"]
            if "user_id" in session_data:
                result["user_id"] = session_data["user_id"]

        return result

    async def _get_available_methods(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Get available authentication methods for user."""
        # In production, check user preferences and capabilities
        user_methods = []

        for method in self.enabled_methods:
            method_info = {"method": method, "available": True}

            if method == "mfa":
                # Check if user has MFA configured
                mfa_status = await self.mfa_node.async_run(
                    action="status", user_id=user_id
                )
                method_info["configured"] = mfa_status.get("mfa_enabled", False)

            user_methods.append(method_info)

        return {
            "user_id": user_id,
            "available_methods": user_methods,
            "primary_method": self.primary_method,
            "fallback_methods": self.fallback_methods,
        }

    async def _challenge_mfa(
        self, user_id: str, auth_method: str, **kwargs
    ) -> Dict[str, Any]:
        """Challenge user for MFA."""
        return await self.mfa_node.async_run(
            action="challenge", user_id=user_id, method=auth_method
        )

    async def _log_auth_event(self, **event_data):
        """Log authentication events."""
        # Determine severity based on event type
        event_type = event_data.get("event_type", "auth_event")
        if "error" in event_type or "failure" in event_type:
            severity = "HIGH"
        elif "success" in event_type:
            severity = "INFO"
        else:
            severity = "MEDIUM"

        # SecurityEventNode is a sync-only Node (neither execute_async nor
        # async_run), so it is offloaded to a worker thread. Its parameters are
        # event_type/severity/message/user_id/metadata; the source=/timestamp=/
        # details= this used to pass were dropped on the floor by execute(), and
        # message/user_id/metadata were never supplied -- so every event would
        # have been recorded blank even once the call resolved (issue #2060).
        # The node stamps its own timestamp. The action is named in the message
        # so a record cannot be mistaken for one from a different action.
        await asyncio.to_thread(
            self.security_logger.execute,
            event_type=event_type,
            severity=severity,
            message=(
                f"{event_type} (action={log_safe(event_data.get('action'), 64)}) "
                f"via enterprise_auth_provider"
            ),
            user_id=log_safe(event_data.get("user_id")),
            metadata=redact_mapping(
                {"source": "enterprise_auth_provider", **event_data}
            ),
        )

    def get_auth_statistics(self) -> Dict[str, Any]:
        """Get authentication statistics."""
        return {
            **self.auth_statistics,
            "enabled_methods": self.enabled_methods,
            "primary_method": self.primary_method,
            "risk_assessment_enabled": self.risk_assessment_enabled,
            "adaptive_auth_enabled": self.adaptive_auth_enabled,
            "fraud_detection_enabled": self.fraud_detection_enabled,
            "compliance_mode": self.compliance_mode,
            "active_sessions": len(self.auth_sessions),
            "locked_accounts": len(self.locked_accounts),
            "users_with_risk_scores": len(self.risk_scores),
        }
