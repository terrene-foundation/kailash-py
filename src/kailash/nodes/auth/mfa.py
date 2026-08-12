"""
Enterprise multi-factor authentication node.

This module provides comprehensive MFA capabilities including TOTP, SMS, email
verification, backup codes, and integration with popular authenticator apps.
"""

import asyncio
import base64
import hashlib
import hmac
import io
import logging
import secrets
import threading
import time
import warnings
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import qrcode

from kailash.nodes.auth._actor import (
    MFA_ADMIN_CAPABILITY,
    ActorResolver,
    MFAActor,
    NullActorResolver,
)
from kailash.nodes.auth._log_hygiene import log_safe, redact_mapping
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.mixins import LoggingMixin, PerformanceMixin, SecurityMixin
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEventNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)

# One-time-per-process latches (issue #2047). Module-level rather than
# per-instance because a node constructed per request would otherwise emit the
# same message per request, which is the per-operation shape that gets a
# security signal filtered out of production logs. Tests re-arm them by
# assigning False here -- that is the intended and only supported way.
_ACTOR_DISABLED_WARNED = False
_ADMIN_OVERRIDE_WARNED = False
_ACTOR_WARN_LOCK = threading.Lock()


def _warn_actor_enforcement_disabled() -> None:
    """Say ONCE, at WARN, that (actor, action, subject) authorization is OFF."""
    global _ACTOR_DISABLED_WARNED
    with _ACTOR_WARN_LOCK:
        if _ACTOR_DISABLED_WARNED:
            return
        _ACTOR_DISABLED_WARNED = True
    logger.warning(
        "MultiFactorAuthNode(require_actor=False): actor authorization is "
        "DISABLED. Every action -- including revoke/disable/reset and every "
        "credential-issuing action -- is authorized on the caller-supplied "
        "user_id and admin_override, so a caller that can choose user_id can "
        "take over or lock out any account. The host MUST authenticate and "
        "authorize the caller before dispatch. To enable enforcement, pass "
        "MultiFactorAuthNode(actor_resolver=..., require_actor=True) and send "
        "actor_session_id on every call. This warning is emitted once per "
        "process."
    )


class MFADeliveryError(NodeExecutionError):
    """Raised when an MFA factor could not be delivered to the user.

    Callers MUST NOT report a challenge as sent when this is raised: the user
    never received a code, so any "verification_sent" claim would be false.
    """


def _send_sms(phone: str, message: str) -> bool:
    """Deliver an SMS through the module-level transport.

    This is the seam an SMS transport is bound to. No transport ships with the
    SDK, so the default implementation fails closed rather than reporting a
    delivery that never happened. Configure ``sms_provider`` on
    :class:`MultiFactorAuthNode` (Twilio) or patch this function with a real
    provider client.

    Args:
        phone: Destination phone number.
        message: Message body. NEVER logged — it carries the one-time code.

    Returns:
        True when a transport delivered the message.

    Raises:
        MFADeliveryError: Always, when no transport is bound.
    """
    # Log delivery metadata only. The body is a credential (it contains the
    # OTP), so it is never written to logs -- see rules/security.md
    # "No secrets in logs". The destination is reduced to a digest rather than
    # its last 4 digits: a digest still correlates entries for support without
    # putting any part of the subscriber number in cleartext.
    logger.warning(
        "SMS delivery requested (%d-char body) but no SMS transport is "
        "configured; nothing was sent.",
        len(message),
    )
    raise MFADeliveryError(
        "No SMS transport is configured. Set sms_provider={'service': 'twilio', "
        "...} on MultiFactorAuthNode, or bind a provider to "
        "kailash.nodes.auth.mfa._send_sms."
    )


class TOTPGenerator:
    """Time-based One-Time Password generator."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a new TOTP secret.

        Returns:
            Base32-encoded secret
        """
        # Generate 20 random bytes and encode as base32 (without padding)
        secret_bytes = secrets.token_bytes(20)
        secret = base64.b32encode(secret_bytes).decode("utf-8")
        # Remove any padding characters for consistency
        return secret.rstrip("=")

    @staticmethod
    def generate_totp(secret: str, time_step: int = 30, digits: int = 6) -> str:
        """Generate TOTP code.

        Args:
            secret: Base32-encoded secret
            time_step: Time step in seconds
            digits: Number of digits in the code

        Returns:
            TOTP code
        """
        # Convert secret from base32, handling padding properly
        secret_upper = secret.upper()
        # Add padding if needed (base32 strings should be multiple of 8)
        missing_padding = len(secret_upper) % 8
        if missing_padding:
            secret_upper += "=" * (8 - missing_padding)
        key = base64.b32decode(secret_upper)

        # Get current time step
        current_time = int(time.time() // time_step)

        # Convert to bytes
        time_bytes = current_time.to_bytes(8, byteorder="big")

        # Generate HMAC
        hmac_result = hmac.new(key, time_bytes, hashlib.sha1).digest()

        # Dynamic truncation
        offset = hmac_result[-1] & 0x0F
        truncated = hmac_result[offset : offset + 4]
        code = int.from_bytes(truncated, byteorder="big") & 0x7FFFFFFF

        # Generate final code
        return str(code % (10**digits)).zfill(digits)

    @staticmethod
    def verify_totp(
        secret: str, code: str, time_window: int = 1, time_step: int = 30
    ) -> bool:
        """Verify TOTP code.

        Args:
            secret: Base32-encoded secret
            code: TOTP code to verify
            time_window: Number of time steps to check (for clock drift)
            time_step: Time step in seconds

        Returns:
            True if code is valid
        """
        current_time = int(time.time() // time_step)

        # Check current time and surrounding windows
        for i in range(-time_window, time_window + 1):
            test_time = current_time + i
            test_time_bytes = test_time.to_bytes(8, byteorder="big")

            # Generate code for this time step, handling padding properly
            secret_upper = secret.upper()
            missing_padding = len(secret_upper) % 8
            if missing_padding:
                secret_upper += "=" * (8 - missing_padding)
            key = base64.b32decode(secret_upper)
            hmac_result = hmac.new(key, test_time_bytes, hashlib.sha1).digest()
            offset = hmac_result[-1] & 0x0F
            truncated = hmac_result[offset : offset + 4]
            test_code = int.from_bytes(truncated, byteorder="big") & 0x7FFFFFFF
            generated_code = str(test_code % 1000000).zfill(6)

            if generated_code == code:
                return True

        return False


@register_node()
class MultiFactorAuthNode(SecurityMixin, PerformanceMixin, LoggingMixin, Node):
    """Enterprise multi-factor authentication.

    This node provides comprehensive MFA capabilities including:
    - TOTP authentication with authenticator app support
    - SMS verification with rate limiting
    - Email verification with templates
    - Backup codes for account recovery
    - Session management and timeout handling
    - Integration with audit logging

    **Authorization: the node authorizes the (actor, action, subject) triple**
    (issue #2047). ``user_id`` names the SUBJECT of an action. The ACTOR --
    who is doing it -- is resolved server-side from ``actor_session_id``
    through the injected :class:`~kailash.nodes.auth._actor.ActorResolver`,
    never from a request field naming a principal. A caller supplies PROOF of
    authentication; it never supplies the CLAIM of who it is.

    Default policy:

    * An actor may act on ITSELF for ``setup``, ``verify``, ``status``,
      ``generate_backup_codes``, ``trust_device``, ``initiate_recovery`` and
      the other self-service actions.
    * Acting on ANY other subject requires the actor to hold
      :data:`~kailash.nodes.auth._actor.MFA_ADMIN_CAPABILITY`.
    * The destructive actions -- ``revoke``, ``disable``, ``reset`` -- and
      administrative recovery and re-enrolment over a verified factor require
      that capability regardless of subject.

    With no resolver configured the default is
    :class:`~kailash.nodes.auth._actor.NullActorResolver`, which resolves
    nothing, so every action is DENIED. An unwired authorizer surfaces as a
    refusal, not as an open door.

    .. warning::
       ``admin_override`` is DEPRECATED and no longer grants anything
       (issue #2047). It was an ordinary caller-supplied boolean, so every
       admin-gated action authorized on data the caller controlled. It is
       still accepted, and emits a :class:`DeprecationWarning`; authority now
       comes from a verified capability on a resolved actor. Pass
       ``actor_session_id`` instead.

    .. warning::
       ``require_actor=False`` restores the pre-#2047 behaviour for a host
       that authorizes the caller itself before dispatch: ``user_id`` is then
       taken on trust and ``admin_override`` gates the destructive actions
       again. It is an EXPLICIT, LOUD opt-out -- the node warns once per
       process naming the protection that is off -- and it is unsafe for any
       deployment that lets a caller choose ``user_id``.

    Example:
        >>> mfa_node = MultiFactorAuthNode(
        ...     methods=["totp", "sms", "email"],
        ...     backup_codes=True,
        ...     session_timeout=timedelta(minutes=15)
        ... )
        >>>
        >>> # Setup MFA for user
        >>> setup_result = mfa_node.execute(
        ...     action="setup",
        ...     user_id="user123",
        ...     method="totp",
        ...     user_email="user@example.com"
        ... )
        >>> print(f"QR Code: {setup_result['qr_code_url']}")
        >>>
        >>> # Verify MFA code
        >>> verify_result = mfa_node.execute(
        ...     action="verify",
        ...     user_id="user123",
        ...     code="123456",
        ...     method="totp"
        ... )
        >>> print(f"Verified: {verify_result['verified']}")
    """

    def __init__(
        self,
        name: str = "multi_factor_auth",
        methods: Optional[List[str]] = None,
        default_method: str = "totp",
        issuer: str = "KailashSDK",
        sms_provider: Optional[Dict[str, Any]] = None,
        email_provider: Optional[Dict[str, Any]] = None,
        push_provider: Optional[Dict[str, Any]] = None,
        backup_codes: bool = True,
        backup_codes_count: int = 10,
        totp_period: int = 30,
        session_timeout: timedelta = timedelta(minutes=15),
        rate_limit_attempts: int = 5,
        rate_limit_window: int = 300,  # 5 minutes
        actor_resolver: Optional[ActorResolver] = None,
        require_actor: bool = True,
        **kwargs,
    ):
        """Initialize multi-factor authentication node.

        Args:
            name: Node name
            methods: Supported MFA methods
            default_method: Default MFA method preference
            issuer: TOTP issuer name for authenticator apps
            sms_provider: SMS transport config, e.g.
                ``{"service": "twilio", "account_sid": ..., "auth_token": ...,
                "from_number": ...}``. Unset means SMS codes cannot be sent.
            email_provider: SMTP transport config, e.g.
                ``{"smtp_host": ..., "smtp_port": 587, "username": ...,
                "password": ...}``. Unset means email codes cannot be sent.
            push_provider: Push transport config, e.g.
                ``{"service": "fcm", "server_key": ..., "endpoint": ...}``.
                Unset means push challenges cannot be sent.
            backup_codes: Enable backup codes for recovery
            backup_codes_count: Number of backup codes to generate
            totp_period: TOTP time period in seconds
            session_timeout: MFA session timeout
            rate_limit_attempts: Max attempts per time window
            rate_limit_window: Rate limit window in seconds
            actor_resolver: Resolves a caller-presented ``actor_session_id``
                to an authenticated principal. Defaults to
                :class:`~kailash.nodes.auth._actor.NullActorResolver`, which
                resolves nothing and therefore denies every action -- an
                unwired authorizer is a refusal, not an open door.
            require_actor: When True (the default) every action authorizes the
                ``(actor, action, subject)`` triple and ``admin_override``
                grants nothing. Set False ONLY when the host authenticates and
                authorizes the caller before dispatch; that restores the
                pre-#2047 behaviour, where ``user_id`` is trusted, and warns
                once per process to say so.
            **kwargs: Additional node parameters
        """
        # Set attributes before calling super().__init__()
        self.methods = methods or ["totp", "sms", "email", "push", "backup_codes"]
        self.default_method = default_method
        self.issuer = issuer
        self.sms_provider = sms_provider or {}
        self.email_provider = email_provider or {}
        self.push_provider = push_provider or {}
        self.backup_codes = backup_codes
        self.backup_codes_count = backup_codes_count
        self.totp_period = totp_period
        self.session_timeout = session_timeout
        self.rate_limit_attempts = rate_limit_attempts
        self.rate_limit_window = rate_limit_window

        # Actor resolution (issue #2047). NullActorResolver is the fail-closed
        # default: with no resolver wired, nothing resolves and every action is
        # denied. The alternative -- falling back to trusting `user_id` -- is
        # the exact behaviour this node is being fixed for.
        self.actor_resolver: ActorResolver = actor_resolver or NullActorResolver()
        self.require_actor = bool(require_actor)

        # Initialize parent classes
        super().__init__(name=name, **kwargs)

        if not self.require_actor:
            # `require_actor=False` turns OFF the authorization this node
            # performs, so it announces itself once per process at WARN,
            # naming the protection and its wiring
            # (`rules/security.md` § Secure-Default For A New Security
            # Feature). Once per process, not per call: a per-operation
            # message reads as transient and gets filtered.
            _warn_actor_enforcement_disabled()

        # Audit logging IS wired (issue #2060).
        #
        # These two sinks stood at None from this file's first commit
        # (7dc4e6773, 2025-06-16) behind the comment "disabled for now to fix
        # deadlock". The deadlock was re-investigated before re-wiring and
        # there is no evidence for it:
        #   * `git log -S "AuditLogNode(" -- src/kailash/nodes/auth/mfa.py`
        #     returns the birth commit and nothing earlier -- the wiring was
        #     ALREADY commented out when the file first landed, so no commit
        #     ever wired it and no commit ever disabled it in response to a
        #     hang. There is no repro anywhere in history.
        #   * AuditLogNode.execute and SecurityEventNode.execute take no lock,
        #     open no socket, and enter no event loop; each is dict
        #     construction plus one `logger` call.
        #   * SessionManagementNode constructs and calls these exact two nodes
        #     today, synchronously, from inside a held non-reentrant
        #     threading.Lock, and ships.
        # The real MFA deadlock -- `_revoke_mfa` re-acquiring the non-reentrant
        # `_data_lock` -- was a different defect, fixed under #2026, and had no
        # audit-node involvement.
        self.audit_log_node = AuditLogNode(name=f"{name}_audit_log")
        self.security_event_node = SecurityEventNode(name=f"{name}_security_events")

        # User MFA data storage (in production, this would be a database)
        self.user_mfa_data: Dict[str, Dict[str, Any]] = {}
        self.user_sessions: Dict[str, Dict[str, Any]] = {}
        self.rate_limit_data: Dict[str, List[datetime]] = {}
        self.pending_verifications: Dict[str, Dict[str, Any]] = {}
        self.user_devices: Dict[str, List[Dict[str, Any]]] = {}
        self.push_challenges: Dict[str, Dict[str, Any]] = {}
        self.trusted_devices: Dict[str, List[Dict[str, Any]]] = {}

        # Thread lock for concurrent access
        self._data_lock = threading.Lock()

        # Audit records queued by handlers running under _data_lock, flushed by
        # the dispatcher once the lock is released (see _log_mfa_event).
        # Bounded so a caller that never reaches a flush cannot grow it without
        # limit; the oldest record is dropped rather than the process.
        self._pending_audit_records: deque = deque(maxlen=10000)
        # In-process record of emitted events. Bounded for the same reason
        # as the queue above: an unbounded sibling list would retain every
        # event for the node's lifetime and defeat the cap next to it.
        self.audit_events: deque = deque(maxlen=10000)

        # MFA statistics
        self.mfa_stats = {
            "total_setups": 0,
            "total_verifications": 0,
            "successful_verifications": 0,
            "failed_verifications": 0,
            "backup_codes_used": 0,
            "rate_limited_attempts": 0,
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters for validation and documentation.

        Returns:
            Dictionary mapping parameter names to NodeParameter objects
        """
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                description="MFA action to perform",
                required=True,
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                description="User ID for MFA operation",
                required=True,
            ),
            "method": NodeParameter(
                name="method",
                type=str,
                description="MFA method (totp, sms, email)",
                required=False,
                default=self.default_method,
            ),
            "code": NodeParameter(
                name="code",
                type=str,
                description="MFA code for verification",
                required=False,
            ),
            "user_email": NodeParameter(
                name="user_email",
                type=str,
                description="User email for setup/notifications",
                required=False,
            ),
            "user_phone": NodeParameter(
                name="user_phone",
                type=str,
                description="User phone for SMS verification",
                required=False,
            ),
            "phone_number": NodeParameter(
                name="phone_number",
                type=str,
                description="Phone number for SMS verification (alias for user_phone)",
                required=False,
            ),
            "device_info": NodeParameter(
                name="device_info",
                type=dict,
                description="Device information for trusted device management",
                required=False,
            ),
            "user_data": NodeParameter(
                name="user_data",
                type=dict,
                description="User data including username, email, phone for enrollment",
                required=False,
            ),
            "challenge_id": NodeParameter(
                name="challenge_id",
                type=str,
                description="Challenge ID for push notification verification",
                required=False,
            ),
            "trust_duration_days": NodeParameter(
                name="trust_duration_days",
                type=int,
                description="Number of days to trust a device",
                required=False,
            ),
            "challenge_token": NodeParameter(
                name="challenge_token",
                type=str,
                description=(
                    "Secret delivered to the device inside a push challenge; "
                    "required to approve or deny that challenge."
                ),
                required=False,
            ),
            "trust_token": NodeParameter(
                name="trust_token",
                type=str,
                description="Trust token for device verification",
                required=False,
            ),
            "preferred_method": NodeParameter(
                name="preferred_method",
                type=str,
                description="User's preferred MFA method",
                required=False,
            ),
            "actor_session_id": NodeParameter(
                name="actor_session_id",
                type=str,
                description=(
                    "Opaque session id proving WHO is making this call. The "
                    "node resolves it server-side to an authenticated "
                    "principal via its actor_resolver and authorises the "
                    "(actor, action, subject) triple; the caller never names "
                    "the principal itself. Required unless the node was "
                    "constructed with require_actor=False."
                ),
                required=False,
            ),
            "admin_override": NodeParameter(
                name="admin_override",
                type=bool,
                description=(
                    "DEPRECATED and INERT under require_actor=True (issue "
                    "#2047): it was an ordinary caller-supplied boolean, so "
                    "every admin-gated action authorised on data the caller "
                    "controlled. Authority now comes from the "
                    f"'{MFA_ADMIN_CAPABILITY}' capability on a resolved actor. "
                    "Still accepted, and still gates the destructive actions, "
                    "under the explicit require_actor=False opt-out."
                ),
                required=False,
            ),
            "recovery_method": NodeParameter(
                name="recovery_method",
                type=str,
                description="Recovery method for MFA recovery",
                required=False,
            ),
            "recovery_destination": NodeParameter(
                name="recovery_destination",
                type=str,
                description=(
                    "Enrolled address/number the recovery token is delivered "
                    "to. Required for email/sms recovery."
                ),
                required=False,
            ),
        }

    def run(  # type: ignore[override]
        self,
        action: str,
        user_id: str,
        method: Optional[str] = None,
        code: Optional[str] = None,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None,
        phone_number: Optional[str] = None,
        user_data: Optional[Dict[str, Any]] = None,
        device_info: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        challenge_id: Optional[str] = None,
        trust_duration_days: Optional[int] = None,
        trust_token: Optional[str] = None,
        challenge_token: Optional[str] = None,
        preferred_method: Optional[str] = None,
        actor_session_id: Optional[str] = None,
        admin_override: Optional[bool] = None,
        recovery_method: Optional[str] = None,
        recovery_destination: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Run MFA operation.

        Args:
            action: MFA action (setup, verify, generate_backup_codes, revoke)
            user_id: SUBJECT of the operation -- never the caller
            actor_session_id: Opaque proof of WHO is calling; resolved
                server-side to the authenticated principal (issue #2047)
            method: MFA method
            code: MFA code for verification
            user_email: User email
            user_phone: User phone
            phone_number: Phone number (alias for user_phone)
            **kwargs: Additional parameters

        Returns:
            Dictionary containing operation results
        """
        params = dict(kwargs)
        params.update(
            action=action,
            user_id=user_id,
            method=method,
            code=code,
            user_email=user_email,
            user_phone=user_phone,
            phone_number=phone_number,
            user_data=user_data,
            device_info=device_info,
            auth_context=auth_context,
            challenge_id=challenge_id,
            trust_duration_days=trust_duration_days,
            trust_token=trust_token,
            challenge_token=challenge_token,
            preferred_method=preferred_method,
            actor_session_id=actor_session_id,
            recovery_method=recovery_method,
            recovery_destination=recovery_destination,
        )
        # Only forward admin_override when the caller actually passed it, so
        # the deprecation warning fires for callers that use it and stays
        # silent for callers that do not.
        if admin_override is not None:
            params["admin_override"] = admin_override
        return self._dispatch(params)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async surface. Delegates to the SAME dispatcher as :meth:`run`.

        There used to be two dispatchers with two action sets, two sets of
        gates and two trusted-device stores. A gate present in one and absent
        in the other is not a gate: the async surface accepted ``setup``
        ungated while the sync one required re-enrolment authority, and the
        sync surface's ``disable`` guard was reachable-around on the async one
        (issue #2026 patched instances of this twice). Collapsing them is what
        makes the actor check in :meth:`_dispatch` a property of the NODE
        rather than of whichever entry point a caller happened to use.

        The body is genuinely synchronous -- every handler is CPU-and-dict
        work -- so it is offloaded to a worker thread, the same shape
        ``SessionManagementNode.async_run`` already ships.
        """
        return await asyncio.to_thread(self._dispatch, dict(kwargs))

    def _dispatch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """The single dispatcher behind both :meth:`run` and :meth:`async_run`."""
        action = params.get("action")
        user_id = params.get("user_id")
        method = params.get("method")
        code = params.get("code")
        user_email = params.get("user_email")
        user_phone = params.get("user_phone")
        phone_number = params.get("phone_number")
        user_data = params.get("user_data")
        device_info = params.get("device_info")
        auth_context = params.get("auth_context")
        challenge_id = params.get("challenge_id")
        trust_duration_days = params.get("trust_duration_days")
        trust_token = params.get("trust_token")
        challenge_token = params.get("challenge_token")
        preferred_method = params.get("preferred_method")
        actor_session_id = params.get("actor_session_id")
        recovery_method = params.get("recovery_method")
        recovery_destination = params.get("recovery_destination")
        device_fingerprint = params.get("device_fingerprint")
        admin_override_supplied = "admin_override" in params
        admin_override = bool(params.get("admin_override"))

        if admin_override_supplied:
            # The message states what admin_override does IN THIS NODE'S mode.
            # A single message claiming it "grants nothing" would be false for
            # a require_actor=False node, where it is still the only gate --
            # and a deprecation notice that misdescribes the live behaviour is
            # worse than none.
            warnings.warn(
                "MultiFactorAuthNode: admin_override is deprecated (issue "
                "#2047) -- it is a caller-supplied boolean, so it authorised "
                "administrative actions on data the caller controlled. "
                + (
                    "It grants NOTHING here: authority comes from the "
                    f"'{MFA_ADMIN_CAPABILITY}' capability on the actor "
                    "resolved from actor_session_id."
                    if self.require_actor
                    else "This node is in require_actor=False mode, so it "
                    "still gates the destructive actions and is still not an "
                    "authentication control. Wire actor_resolver= and "
                    "require_actor=True to replace it."
                ),
                DeprecationWarning,
                stacklevel=3,
            )

        start_time = datetime.now(UTC)
        actor: Optional[MFAActor] = None

        try:
            # Validate required user_id — empty or whitespace-only is invalid input.
            # Prevents accidental setup under "" key in user_mfa_data, which causes
            # silent state corruption (issue #803).
            if not user_id or not str(user_id).strip():
                return {
                    "success": False,
                    "error": "user_id is required and must be non-empty",
                    "user_id": user_id,
                    "processing_time_ms": 0.0,
                    "timestamp": start_time.isoformat(),
                }

            # Handle phone_number parameter alias
            final_user_phone = user_phone or phone_number or ""

            # Validate and sanitize inputs (disabled for debugging)
            # safe_params = self.validate_and_sanitize_inputs({
            #     "action": action,
            #     "user_id": user_id,
            #     "method": method or "totp",
            #     "code": code or "",
            #     "user_email": user_email or "",
            #     "user_phone": final_user_phone
            # })

            # action = safe_params["action"]
            # user_id = safe_params["user_id"]
            # method = safe_params["method"]
            # code = safe_params["code"]
            # user_email = safe_params["user_email"]
            # user_phone = safe_params["user_phone"]

            # Use direct parameters for now
            method = method or "totp"
            code = code or ""
            user_email = user_email or ""
            user_phone = final_user_phone

            # Reject malformed identifiers BEFORE any state is written. These
            # used to reach the enrolment writers and only fail deeper in
            # (len() / "in" on an int), leaving a half-written method record
            # behind even though the call reported failure (issue #2026).
            for _label, _value in (
                ("user_email", user_email),
                ("user_phone", user_phone),
                ("code", code),
                ("method", method),
            ):
                if _value is not None and not isinstance(_value, str):
                    return {
                        "success": False,
                        "error": f"{_label} must be a string",
                        "action": action,
                    }

            # AUTHORIZE THE (ACTOR, ACTION, SUBJECT) TRIPLE (issue #2047).
            #
            # Before this, `user_id` WAS the authority: whoever could name a
            # subject could set up, reset, revoke or issue credentials for it,
            # and `admin_override` -- a caller-supplied boolean -- was the only
            # thing standing in front of the destructive actions. Five review
            # rounds each patched the action the previous round exploited.
            #
            # The check runs HERE, once, ahead of every handler, rather than
            # inside the ones that looked dangerous: the last five reviews each
            # found a DIFFERENT action to be a credential-issuing or
            # state-destroying primitive, so an enumeration of the dangerous
            # ones is the thing that kept failing.
            actor, denial = self._resolve_and_authorize(
                action=str(action or ""),
                subject_user_id=str(user_id),
                actor_session_id=actor_session_id,
                recovery_method=recovery_method,
            )
            if denial is not None:
                denial["processing_time_ms"] = 0.0
                denial["timestamp"] = start_time.isoformat()
                # A refused action is exactly what an audit trail exists to
                # record; returning before the audit call at the bottom would
                # make every rejected attempt invisible.
                self._audit_mfa_operation_sync(
                    user_id, action, method, denial, actor=actor
                )
                return denial

            # An actor holding the admin capability is what now authorises
            # re-enrolment over a verified factor and administrative recovery.
            # Under the require_actor=False opt-out the legacy caller-supplied
            # boolean still fills that role, unchanged and still documented as
            # not an authentication control.
            admin_authorized = (
                bool(actor and actor.has_capability(MFA_ADMIN_CAPABILITY))
                if self.require_actor
                else admin_override
            )

            # self.log_node_execution("mfa_operation_start", action=action, method=method)

            # Check rate limits for verification operations (issue #803).
            # Brute-force protection: at rate_limit_attempts (default 5) failed
            # verify attempts within rate_limit_window (default 300s), reject
            # further verify calls. Setup/status/disable are not rate-limited
            # because they are not attacker-driven probe surfaces.
            if action == "verify" and not self._check_rate_limit(user_id):
                self.mfa_stats["rate_limited_attempts"] += 1
                rate_limited = {
                    "success": False,
                    "verified": False,
                    "user_id": user_id,
                    "error": "Rate limit exceeded. Please try again later.",
                    "rate_limited": True,
                    "too_many_attempts": True,
                    "processing_time_ms": 0.0,
                    "timestamp": start_time.isoformat(),
                }
                # Audit before returning. This early return used to skip the
                # audit call at the end of the dispatcher, so a sustained
                # brute-force produced records up to the rate-limit threshold
                # and then went SILENT for the rest of the attack -- the trail
                # stopped exactly when it became interesting (issue #2060).
                self._audit_mfa_operation_sync(
                    user_id, action, method, rate_limited, actor=actor
                )
                return rate_limited

            # Route to appropriate action handler. ONE table for both surfaces
            # (issue #2047): `verify_backup` and `list_methods` used to exist
            # only on the async dispatcher and `enroll`/`send_push`/
            # `verify_push`/`approve_push`/`deny_push`/`set_preference`/
            # `get_methods`/`initiate_recovery`/`reset` only on the sync one,
            # so the two surfaces disagreed on both WHAT you could do and WHAT
            # was gated.
            if action in ["setup", "enroll"]:  # Handle both setup and enroll
                result = self._setup_mfa(
                    user_id,
                    method,
                    user_email,
                    user_phone,
                    user_data or {},
                    device_info or {},
                    allow_reenrolment=bool(admin_authorized),
                )
                self.mfa_stats["total_setups"] += 1
            elif action == "verify":
                result = self._verify_mfa(user_id, code, method)
                self.mfa_stats["total_verifications"] += 1
                if result.get("verified", False):
                    self.mfa_stats["successful_verifications"] += 1
                else:
                    self.mfa_stats["failed_verifications"] += 1
            elif action == "generate_backup_codes":
                result = self._generate_backup_codes(user_id)
            elif action == "verify_backup":
                # Was reachable only through async_run. Its own #2026 fix note
                # records that it shipped without the guarantees the other four
                # backup-code sites had; being on one dispatcher only is how it
                # stayed that way for so long.
                result = self._verify_backup_code(user_id, code)
            elif action == "revoke":
                # Destroying a user's factors is reset-equivalent: revoke then
                # setup re-creates the enrolment the setup guard protects, so
                # it carries the same requirement (issue #2026). The gate is
                # now the actor's verified capability, checked in
                # _resolve_and_authorize before this table runs; under the
                # require_actor=False opt-out it is the legacy boolean.
                if not admin_authorized:
                    result = self._admin_action_denied("revoke")
                else:
                    result = self._revoke_mfa(user_id, method)
            elif action == "status":
                result = self._get_mfa_status(user_id)
            elif action == "send_push":
                # Keep the node's result-dict contract: every other MFA failure
                # returns {"success": False, ...} rather than raising out of
                # execute(), so an undelivered push must not abort the workflow.
                try:
                    result = self._send_push_challenge(user_id, auth_context or {})
                except MFADeliveryError as e:
                    result = {
                        "success": False,
                        "method": "push",
                        "error": "Push delivery failed",
                        "challenge_sent": False,
                    }
            elif action == "verify_push":
                result = self._verify_push_challenge(user_id, challenge_id)
            elif action in ("approve_push", "deny_push"):
                result = self._respond_to_push_challenge(
                    user_id,
                    challenge_id,
                    approved=(action == "approve_push"),
                    challenge_token=challenge_token,
                )
            elif action == "trust_device":
                # ONE trusted-device store (issue #2047). The async surface
                # wrote a `device_fingerprint` key into
                # user_mfa_data[user]["trusted_devices"] while the sync one
                # appended a record to self.trusted_devices, and the reader
                # consulted both -- so which store a trust landed in, and
                # therefore which code could revoke it, depended on the entry
                # point. `device_fingerprint` is still accepted as an input;
                # it is now just another way to name the device.
                result = self._trust_device(
                    user_id,
                    self._device_selector(device_info, device_fingerprint),
                    trust_duration_days or 30,
                )
            elif action == "check_device_trust":
                result = self._check_device_trust(
                    user_id,
                    self._device_selector(device_info, device_fingerprint),
                    trust_token,
                )
            elif action == "set_preference":
                result = self._set_user_preference(user_id, preferred_method)  # type: ignore[reportArgumentType]
            elif action in ("get_methods", "list_methods"):
                # `list_methods` was async-only and `get_methods` sync-only,
                # for the same question. Both now answer it.
                result = (
                    self._list_methods(user_id)
                    if action == "list_methods"
                    else self._get_user_methods(user_id)
                )
            elif action == "disable":
                # `disable` deletes a factor, which is what `revoke` does and
                # what `reset` does: it clears the way for a fresh `setup`, so
                # it carries the same requirement. The `elif method:` branch
                # that used to run ungated was ALWAYS taken -- `method` is
                # defaulted to "totp" above, so the "method required" branch
                # below it was unreachable -- which left the whole
                # setup/revoke/reset guard reachable-around on this dispatcher
                # while the async one was gated (issue #2026).
                if not admin_authorized:
                    result = self._admin_action_denied("disable")
                elif method:
                    # Disable a specific method.
                    result = self._disable_method(user_id, method)
                else:
                    # Disable all MFA for user.
                    result = self._disable_all_mfa(user_id)
            elif action == "initiate_recovery":
                result = self._initiate_recovery(
                    user_id,
                    recovery_method or "email",
                    recovery_destination,
                    admin_authorized=bool(admin_authorized),
                )
            elif action == "reset":
                # Reset: clear existing MFA state, then re-run setup. Returns
                # the new setup payload (fresh secret + backup codes) so the
                # caller can re-enroll the user (issue #803).
                #
                # Destroying a user's second factor and minting a new one is an
                # administrative action: ungated it was the strongest form of
                # the setup-overwrite takeover (issue #2026). It now matches
                # the requirement `disable` already carries.
                if not admin_authorized:
                    result = self._admin_action_denied("reset")
                else:
                    with self._data_lock:
                        self.user_mfa_data.pop(user_id, None)
                        self.pending_verifications.pop(user_id, None)
                        self.trusted_devices.pop(user_id, None)
                    result = self._setup_mfa(
                        user_id,
                        method,
                        user_email,
                        user_phone,
                        user_data or {},
                        device_info or {},
                        allow_reenrolment=True,
                    )
                if result.get("success"):
                    result["reset"] = True
                    result["user_id"] = user_id
            else:
                result = {"success": False, "error": f"Unknown action: {action}"}

            # Add timing information
            processing_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            result["processing_time_ms"] = processing_time
            result["timestamp"] = start_time.isoformat()

            # Audit the operation. This stood commented out from this file's
            # first commit behind "disabled for now to fix deadlock", which
            # meant every admin-gated destructive action (revoke, disable,
            # reset) taken through the SYNC surface completed with no record.
            # The deadlock claim was re-investigated and has no supporting
            # evidence -- see the sink construction in __init__ (issue #2060).
            # This is deliberately OUTSIDE any `_data_lock` held above: the
            # action handlers acquire and release it themselves, so the sink
            # never runs under the lock.
            self._audit_mfa_operation_sync(user_id, action, method, result, actor=actor)

            self.log_node_execution(
                "mfa_operation_complete",
                action=action,
                success=result.get("success", False),
                processing_time_ms=processing_time,
            )

            return result

        except MFADeliveryError:
            # Delivery failures are already converted to result dicts at their
            # dispatch sites; anything reaching here is a genuine bug.
            raise
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            # Malformed input (a non-string user_phone/user_email, a non-dict
            # device_info) used to raise out of execute(), contradicting the
            # node's own result-dict contract that every other failure honours
            # (issue #2026). The detail is logged, not returned.
            self.log_with_context(
                "ERROR", f"MFA operation {action} failed on invalid input: {e!r}"
            )
            return {
                "success": False,
                "error": "Invalid input for MFA operation",
                "action": action,
            }
        except Exception as e:
            # self.log_error_with_traceback(e, "mfa_operation")
            raise
        finally:
            # In a finally so that the early returns above (rate limit,
            # malformed input) and the exception paths still drain the queue.
            # A record queued under _data_lock and never flushed would sit in
            # the deque until some later dispatch happened to pick it up, or
            # fall off the end of the bounded queue entirely.
            self._flush_audit_records()

    async def execute_async(self, **kwargs) -> Dict[str, Any]:
        """Execute method for async compatibility."""
        return await self.async_run(**kwargs)

    # Actions that DESTROY or REPLACE a subject's enrolled factors. Each is
    # reset-equivalent: revoke-then-setup, disable-then-setup and reset all
    # arrive at "this account now has a second factor the operator chose", so
    # they carry one requirement rather than three (issue #2026 reached this
    # conclusion action by action; #2047 states it once).
    _ADMIN_ONLY_ACTIONS = frozenset({"revoke", "disable", "reset"})

    # Actions that are read-only with respect to a subject's factors. Listed
    # to document the split, NOT to relax anything: acting on a subject other
    # than yourself requires the admin capability whatever the action, because
    # `status` and `get_methods` disclose which factors an account holds.
    _SELF_SERVICE_ACTIONS = frozenset(
        {
            "setup",
            "enroll",
            "verify",
            "verify_backup",
            "verify_push",
            "approve_push",
            "deny_push",
            "send_push",
            "status",
            "get_methods",
            "list_methods",
            "generate_backup_codes",
            "trust_device",
            "check_device_trust",
            "set_preference",
            "initiate_recovery",
        }
    )

    @staticmethod
    def _device_selector(
        device_info: Optional[Dict[str, Any]], device_fingerprint: Optional[str]
    ) -> Dict[str, Any]:
        """Normalize the two ways a caller can name a device to ONE shape.

        The sync surface took ``device_info={"device_id": ...}`` and the async
        one took a bare ``device_fingerprint`` string, and each wrote to a
        DIFFERENT store. Callers keep both spellings; the node keeps one
        record.
        """
        if isinstance(device_info, dict) and device_info:
            return device_info
        if isinstance(device_info, str) and device_info:
            return {"device_id": device_info, "device_fingerprint": device_info}
        if isinstance(device_fingerprint, str) and device_fingerprint:
            return {
                "device_id": device_fingerprint,
                "device_fingerprint": device_fingerprint,
            }
        return {}

    @staticmethod
    def _admin_action_denied(action: str) -> Dict[str, Any]:
        """The refusal for a destructive action taken without the capability."""
        return {
            "success": False,
            "error": (
                f"'{action}' destroys or replaces the subject's enrolled "
                f"factors and requires an actor holding the "
                f"'{MFA_ADMIN_CAPABILITY}' capability."
            ),
            "authorized": False,
        }

    def _resolve_and_authorize(
        self,
        *,
        action: str,
        subject_user_id: str,
        actor_session_id: Optional[str],
        recovery_method: Optional[str],
    ) -> Tuple[Optional[MFAActor], Optional[Dict[str, Any]]]:
        """Resolve the caller to a principal and authorize (actor, action, subject).

        Returns ``(actor, None)`` when the call may proceed, or
        ``(actor_or_None, denial_result)`` when it may not. Fail-closed at
        every exit: an unresolvable session, a resolver that raises, and an
        actor without the required capability all deny.

        BOTH SIDES of the comparison are server-derived. The actor comes from
        the resolver's session store; the subject is the key this node's own
        MFA records are held under. Nothing in the request names a principal.
        """
        if not self.require_actor:
            # The explicit opt-out. The host asserts it authorized the caller
            # before dispatch; the node has already said once, loudly, that it
            # is not checking (see _warn_actor_enforcement_disabled).
            return None, None

        if not isinstance(actor_session_id, str) or not actor_session_id.strip():
            return None, {
                "success": False,
                "error": (
                    "actor_session_id is required: this node authorises the "
                    "(actor, action, subject) triple and will not accept "
                    "user_id as authority. Pass the caller's authenticated "
                    "session id, or construct the node with "
                    "require_actor=False if the host authorises callers "
                    "itself."
                ),
                "authorized": False,
            }

        try:
            actor = self.actor_resolver.resolve_actor(actor_session_id)
        except Exception as exc:
            # A resolver is a Protocol implemented by the host; it MUST NOT
            # raise, but a node on the auth path must not crash if one does.
            # Deny, and say why -- a silent None here would be indistinguishable
            # from a correctly rejected session (`rules/zero-tolerance.md`
            # Rule 3).
            self.log_with_context(
                "ERROR",
                f"MFA actor resolver raised {type(exc).__name__}; denying.",
            )
            actor = None

        if actor is None:
            return None, {
                "success": False,
                "error": "Unrecognised or expired actor_session_id.",
                "authorized": False,
            }
        if not isinstance(actor, MFAActor):
            # A resolver returning something else is a wiring bug, and
            # duck-typing it would mean authorizing against an object whose
            # `has_capability` the host controls.
            self.log_with_context(
                "ERROR",
                "MFA actor resolver returned a non-MFAActor; denying.",
            )
            return None, {
                "success": False,
                "error": "Actor resolution failed.",
                "authorized": False,
            }

        acting_on_self = actor.user_id == subject_user_id
        needs_admin = (
            action in self._ADMIN_ONLY_ACTIONS
            or not acting_on_self
            or (action == "initiate_recovery" and recovery_method == "admin")
        )
        if needs_admin and not actor.has_capability(MFA_ADMIN_CAPABILITY):
            if not acting_on_self:
                reason = (
                    "Acting on another subject requires an actor holding the "
                    f"'{MFA_ADMIN_CAPABILITY}' capability."
                )
            elif action == "initiate_recovery":
                reason = (
                    "Administrative recovery requires an actor holding the "
                    f"'{MFA_ADMIN_CAPABILITY}' capability."
                )
            else:
                return actor, self._admin_action_denied(action)
            return actor, {"success": False, "error": reason, "authorized": False}

        return actor, None

    def _setup_mfa(
        self,
        user_id: str,
        method: str,
        user_email: str,
        user_phone: str,
        user_data: Optional[Dict[str, Any]] = None,
        device_info: Optional[Dict[str, Any]] = None,
        allow_reenrolment: bool = False,
    ) -> Dict[str, Any]:
        """Setup MFA for user.

        Args:
            user_id: User ID
            method: MFA method to setup
            user_email: User email
            user_phone: User phone
            allow_reenrolment: Whether replacing an already-VERIFIED factor is
                permitted. Set by the dispatcher from the ACTOR's verified
                capability (issue #2047); it was previously named
                ``admin_override`` and set from the caller-supplied boolean of
                the same name, which is the defect.

        Returns:
            Setup result
        """
        if method not in self.methods:
            return {
                "success": False,
                "error": f"Method {method} not supported. Available: {self.methods}",
            }

        with self._data_lock:
            # Re-enrolling an already-VERIFIED factor is a step-up operation.
            # Without this, setup silently replaced a victim's authenticator
            # secret, phone, or address and handed the caller fresh backup
            # codes -- a complete MFA takeover in one call, and the upstream
            # route that defeated every downstream enrolment guard
            # (issue #2026).
            existing = self.user_mfa_data.get(user_id, {}).get("methods", {})
            if (
                any(m.get("verified") for m in existing.values())
                and not allow_reenrolment
            ):
                return {
                    "success": False,
                    "method": method,
                    "error": (
                        "MFA is already set up and verified for this user. "
                        "Re-enrolment requires an actor holding the "
                        f"'{MFA_ADMIN_CAPABILITY}' capability, or a completed "
                        "recovery."
                    ),
                }

            if user_id not in self.user_mfa_data:
                self.user_mfa_data[user_id] = {
                    "methods": {},
                    "backup_codes": [],
                    "created_at": datetime.now(UTC).isoformat(),
                }

            if method == "totp":
                return self._setup_totp(user_id, user_email, user_data)
            elif method == "sms":
                # Use provided user_phone or extract from user_data
                phone_number = user_phone or (user_data or {}).get("phone", "")
                return self._setup_sms(user_id, phone_number)
            elif method == "email":
                # Use provided user_email or extract from user_data
                email_address = user_email or (user_data or {}).get("email", "")
                return self._setup_email(user_id, email_address)
            elif method == "push":
                return self._setup_push(user_id, device_info or {})
            else:
                return {
                    "success": False,
                    "error": f"Setup not implemented for method: {method}",
                }

    def _setup_totp(
        self, user_id: str, user_email: str, user_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Setup TOTP authentication.

        Args:
            user_id: User ID
            user_email: User email for QR code
            user_data: Additional user data with username, etc.

        Returns:
            TOTP setup result with QR code
        """
        # Generate TOTP secret
        secret = TOTPGenerator.generate_secret()

        # Store TOTP data
        self.user_mfa_data[user_id]["methods"]["totp"] = {
            "secret": secret,
            "setup_at": datetime.now(UTC).isoformat(),
            "verified": False,
        }

        # Generate QR code for authenticator apps
        issuer = self.issuer
        # Use username from user_data if available, otherwise fall back to user_id
        username = (user_data or {}).get("username")
        account_name = username if username else user_id
        logger.debug(
            "totp_setup.account_name_resolved",
            extra={
                "has_user_data": bool(user_data),
                "username_present": username is not None,
                "account_name_present": bool(account_name),
            },
        )

        # Create TOTP URI
        totp_uri = (
            f"otpauth://totp/{issuer}:{account_name}?secret={secret}&issuer={issuer}"
        )

        # Generate QR code
        qr_code_data = self._generate_qr_code(totp_uri)

        # Generate recovery codes if backup codes are enabled
        recovery_codes = []
        if self.backup_codes:
            recovery_codes = self._generate_backup_codes_for_user(user_id)

        # Log MFA enrollment event
        self._log_mfa_event(
            "mfa_enrollment",
            {
                "user_id": user_id,
                "method": "totp",
                "setup_at": datetime.now(UTC).isoformat(),
            },
        )

        return {
            "success": True,
            "method": "totp",
            "secret": secret,
            "qr_code": qr_code_data,
            "qr_code_data": qr_code_data,  # Keep both for compatibility
            "provisioning_uri": totp_uri,
            "qr_code_uri": totp_uri,  # Keep both for compatibility
            "backup_codes": recovery_codes,
            "recovery_codes": recovery_codes,  # Keep both for compatibility
            "instructions": [
                "Install an authenticator app (Google Authenticator, Authy, etc.)",
                "Scan the QR code or enter the secret manually",
                "Verify setup by entering a code from your authenticator app",
            ],
        }

    def _setup_sms(self, user_id: str, user_phone: str) -> Dict[str, Any]:
        """Setup SMS authentication.

        Args:
            user_id: User ID
            user_phone: User phone number

        Returns:
            SMS setup result
        """
        if not user_phone:
            return {"success": False, "error": "Phone number required for SMS setup"}

        # Store SMS data
        self.user_mfa_data[user_id]["methods"]["sms"] = {
            "phone": user_phone,
            "setup_at": datetime.now(UTC).isoformat(),
            "verified": False,
        }

        # Deliver the verification SMS. If nothing was actually delivered the
        # caller is told so -- it must not act on a "verification_sent" that
        # never happened.
        verification_code = self._generate_verification_code()
        try:
            delivered = self._send_sms_code(user_phone, verification_code, user_id)
            if not delivered:
                # No node-level provider: fall through to the module-level
                # transport seam, which fails closed when nothing is bound.
                _send_sms(user_phone, f"Your verification code: {verification_code}")
        except MFADeliveryError as e:
            # Log the detail; do NOT return it. Provider exceptions routinely
            # carry the recipient address/number, which would disclose the
            # enrolled destination to the caller (issue #2026).
            self.log_with_context("ERROR", f"SMS setup failed for user {user_id}: {e}")
            # Roll back the half-enrolment, as the email path does: leaving it
            # in place let a failed setup permanently replace a victim's
            # verified destination with an attacker-chosen number. The temp
            # code is dropped too -- _send_sms_code stores it BEFORE the
            # transport raises, and it would go live again on re-enrolment.
            self.user_mfa_data[user_id]["methods"].pop("sms", None)
            self.user_mfa_data[user_id].pop("temp_sms_code", None)
            return {
                "success": False,
                "method": "sms",
                "error": "SMS delivery failed",
                "verification_sent": False,
            }

        # Create masked phone number for display
        if len(user_phone) > 6:
            phone_masked = (
                user_phone[:2] + "*" * (len(user_phone) - 6) + user_phone[-4:]
            )
        else:
            phone_masked = "*" * len(user_phone)

        return {
            "success": True,
            "method": "sms",
            "phone": user_phone,
            "phone_number": user_phone,  # Alias for test compatibility
            "masked_phone": phone_masked,
            "verification_sent": True,
            "instructions": [
                "A verification code has been sent to your phone",
                "Enter the code to complete SMS setup",
            ],
        }

    def _setup_email(self, user_id: str, user_email: str) -> Dict[str, Any]:
        """Setup email authentication.

        Args:
            user_id: User ID
            user_email: User email address

        Returns:
            Email setup result
        """
        if not user_email:
            return {"success": False, "error": "Email address required for email setup"}

        # Store email data
        self.user_mfa_data[user_id]["methods"]["email"] = {
            "email": user_email,
            "setup_at": datetime.now(UTC).isoformat(),
            "verified": False,
        }

        # Deliver the verification email. A configured-but-failing provider
        # raises; the caller is never told a code was sent when it was not.
        verification_code = self._generate_verification_code()
        try:
            delivered = self._send_email_code(user_email, verification_code, user_id)
        except MFADeliveryError as e:
            self.log_with_context(
                "ERROR", f"Email setup failed for user {user_id}: {e}"
            )
            self.user_mfa_data[user_id]["methods"].pop("email", None)
            self.user_mfa_data[user_id].pop("temp_email_code", None)
            return {
                "success": False,
                "method": "email",
                "error": "Email delivery failed",
                "verification_sent": False,
            }

        if not delivered:
            # Mirror the SMS path: no transport means no code reached the user,
            # so do not leave them enrolled against a code nobody received.
            self.user_mfa_data[user_id]["methods"].pop("email", None)
            self.user_mfa_data[user_id].pop("temp_email_code", None)
            return {
                "success": False,
                "method": "email",
                "error": (
                    "No email transport is configured. Set email_provider="
                    "{'smtp_host': ...} on MultiFactorAuthNode."
                ),
                "verification_sent": False,
            }

        # Create masked email for display
        if "@" in user_email:
            local, domain = user_email.split("@", 1)
            if len(local) > 2:
                masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
            else:
                masked_local = "*" * len(local)
            masked_email = f"{masked_local}@{domain}"
        else:
            masked_email = "*" * len(user_email)

        return {
            "success": True,
            "method": "email",
            "email": user_email,
            "masked_email": masked_email,
            "verification_sent": True,
            "instructions": [
                "A verification code has been sent to your email",
                "Enter the code to complete email setup",
            ],
        }

    def _setup_push(self, user_id: str, device_info: Dict[str, Any]) -> Dict[str, Any]:
        """Setup push notification authentication.

        Args:
            user_id: User ID
            device_info: Device information including device_id, device_name, push_token, platform

        Returns:
            Push setup result
        """
        if not device_info.get("device_id") or not device_info.get("push_token"):
            return {
                "success": False,
                "error": "Device ID and push token required for push setup",
            }

        # Store push data
        self.user_mfa_data[user_id]["methods"]["push"] = {
            "device_id": device_info.get("device_id"),
            "device_name": device_info.get("device_name", "Unknown Device"),
            "push_token": device_info.get("push_token"),
            "platform": device_info.get("platform", "unknown"),
            "setup_at": datetime.now(UTC).isoformat(),
            # NOT verified at setup: nothing has been delivered to, or
            # acknowledged by, the device. Marking it verified here asserted a
            # proof that never happened and satisfied every downstream
            # "is a factor verified" gate (issue #2026). A push challenge must
            # be sent and approved first.
            "verified": False,
        }

        # Initialize user's device list if needed
        if user_id not in self.user_devices:
            self.user_devices[user_id] = []

        # Add device to user's device list
        self.user_devices[user_id].append(
            {
                "device_id": device_info.get("device_id"),
                "device_name": device_info.get("device_name", "Unknown Device"),
                "push_token": device_info.get("push_token"),
                "platform": device_info.get("platform", "unknown"),
                "trusted": False,
                "enrolled_at": datetime.now(UTC).isoformat(),
            }
        )

        return {
            "success": True,
            "method": "push",
            "device_enrolled": True,
            "device_id": device_info.get("device_id"),
            "device_name": device_info.get("device_name", "Unknown Device"),
            "platform": device_info.get("platform", "unknown"),
            "instructions": [
                "Push notifications have been enabled for this device",
                "You will receive push notifications for MFA verification",
            ],
        }

    def _send_push_challenge(
        self, user_id: str, auth_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send push notification challenge.

        Args:
            user_id: User ID
            auth_context: Authentication context (ip_address, location, browser, etc.)

        Returns:
            Push challenge result
        """
        # Check if user has push devices registered
        if user_id not in self.user_devices or not self.user_devices[user_id]:
            return {"success": False, "error": "No push devices registered for user"}

        # Generate challenge ID
        challenge_id = secrets.token_urlsafe(32)

        # Store challenge
        # The token proves the responder is the DEVICE: it travels only in the
        # push payload, never in this method's return value, so a caller holding
        # challenge_id alone cannot approve its own challenge.
        challenge_token = secrets.token_urlsafe(32)

        self.push_challenges[challenge_id] = {
            "user_id": user_id,
            "created_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
            "status": "pending",
            "challenge_token": challenge_token,
            "auth_context": auth_context,
            "device_id": self.user_devices[user_id][0].get(
                "device_id"
            ),  # Use first device
        }

        # Deliver the push challenge. Previously this POSTed to the live FCM
        # endpoint with a hardcoded "key=test_server_key", ignored the outcome,
        # and returned success unconditionally -- so the caller was told
        # "Push notification sent to your device" for a challenge that was
        # never delivered (issue #2026).
        server_key = self.push_provider.get("server_key")
        if not server_key:
            self.push_challenges.pop(challenge_id, None)
            self.log_with_context(
                "ERROR",
                "Push challenge requested but no push transport is configured; "
                "nothing was sent.",
            )
            raise MFADeliveryError(
                "No push transport is configured. Set push_provider="
                "{'service': 'fcm', 'server_key': ...} on MultiFactorAuthNode."
            )

        device = self.user_devices[user_id][0]  # Use first device for simplicity
        endpoint = self.push_provider.get(
            "endpoint", "https://fcm.googleapis.com/fcm/send"
        )
        fcm_data = {
            "to": device.get("push_token"),
            "notification": {
                "title": "MFA Verification Required",
                "body": f"Login attempt from {auth_context.get('location', 'Unknown location')}",
            },
            "data": {
                "challenge_id": challenge_id,
                # Delivered to the device only; never returned to the caller.
                "challenge_token": challenge_token,
                "ip_address": auth_context.get("ip_address", "Unknown"),
                "browser": auth_context.get("browser", "Unknown"),
            },
        }

        try:
            import requests

            response = requests.post(
                endpoint,
                json=fcm_data,
                headers={"Authorization": f"key={server_key}"},
                timeout=self.push_provider.get("timeout", 10),
            )
        except Exception as e:
            # Fail closed: an undelivered challenge must not be reported as sent.
            self.push_challenges.pop(challenge_id, None)
            self.log_with_context("ERROR", f"Failed to send push notification: {e}")
            raise MFADeliveryError(f"Failed to send push notification: {e}") from e

        if response.status_code != 200:
            self.push_challenges.pop(challenge_id, None)
            self.log_with_context(
                "ERROR", f"Push notification failed: {response.status_code}"
            )
            raise MFADeliveryError(
                f"Push provider rejected the challenge (HTTP {response.status_code})"
            )

        self.log_with_context(
            "INFO", f"Push challenge sent to device {device.get('device_id')}"
        )
        return {
            "success": True,
            "challenge_id": challenge_id,
            "expires_in": 300,  # 5 minutes
            "message": "Push notification sent to your device",
        }

    def _verify_push_challenge(
        self, user_id: str, challenge_id: Optional[str]
    ) -> Dict[str, Any]:
        """Verify push notification challenge.

        Args:
            user_id: User ID
            challenge_id: Challenge ID to verify

        Returns:
            Push verification result
        """
        if not challenge_id:
            return {
                "success": False,
                "verified": False,
                "error": "Challenge ID required for push verification",
            }

        # Check if challenge exists
        if challenge_id not in self.push_challenges:
            return {
                "success": False,
                "verified": False,
                "error": "Invalid or expired challenge ID",
            }

        challenge = self.push_challenges[challenge_id]

        # Verify challenge belongs to the user
        if challenge.get("user_id") != user_id:
            return {
                "success": False,
                "verified": False,
                "error": "Challenge does not belong to user",
            }

        # Check if challenge is expired
        if challenge.get("expires_at", datetime.now(UTC)) <= datetime.now(UTC):
            # Remove expired challenge
            del self.push_challenges[challenge_id]
            return {
                "success": False,
                "verified": False,
                "error": "Challenge has expired",
            }

        # Check challenge status
        if challenge.get("status") == "approved":
            # Remove successful challenge
            device_id = challenge.get("device_id")
            del self.push_challenges[challenge_id]

            # First approval proves the device: push enrolment is verified here
            # rather than at setup time, where nothing had been delivered to or
            # acknowledged by the device (issue #2026).
            push_method = (
                self.user_mfa_data.get(user_id, {}).get("methods", {}).get("push")
            )
            if push_method is not None and not push_method.get("verified"):
                push_method["verified"] = True
                push_method["verified_at"] = datetime.now(UTC).isoformat()

            # Create MFA session
            session_id = self._create_mfa_session(user_id)

            return {
                "success": True,
                "verified": True,
                "method": "push",
                "device_id": device_id,
                "session_id": session_id,
            }
        elif challenge.get("status") == "denied":
            # Remove denied challenge
            del self.push_challenges[challenge_id]
            return {
                "success": True,
                "verified": False,
                "message": "Push challenge was denied by user",
            }
        else:
            # Challenge still pending
            return {
                "success": True,
                "verified": False,
                "message": "Push challenge is still pending user response",
            }

    def _respond_to_push_challenge(
        self,
        user_id: str,
        challenge_id: Optional[str],
        approved: bool,
        challenge_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record the device's approve/deny response to a push challenge.

        Without this, nothing ever wrote ``status`` other than ``"pending"``, so
        :meth:`_verify_push_challenge` could never succeed and ``push`` was a
        permanently incompletable factor (issue #2026).

        The response is authenticated by ``challenge_token`` -- the secret handed
        to the device in the push payload. A ``challenge_id`` alone is not
        sufficient: it is echoed to the caller by ``send_push``.

        Args:
            user_id: User the challenge belongs to.
            challenge_id: Challenge identifier.
            approved: True to approve, False to deny.
            challenge_token: Secret delivered to the device with the challenge.

        Returns:
            Result describing the recorded response.
        """
        if not challenge_id:
            return {"success": False, "error": "challenge_id required"}

        challenge = self.push_challenges.get(challenge_id)
        if not challenge or challenge.get("user_id") != user_id:
            return {"success": False, "error": "Invalid or unknown challenge"}

        if challenge.get("expires_at", datetime.now(UTC)) <= datetime.now(UTC):
            del self.push_challenges[challenge_id]
            return {"success": False, "error": "Challenge has expired"}

        expected = challenge.get("challenge_token") or ""
        if not challenge_token or not secrets.compare_digest(
            str(expected).encode("utf-8"), str(challenge_token).encode("utf-8")
        ):
            return {"success": False, "error": "Invalid challenge response"}

        challenge["status"] = "approved" if approved else "denied"
        challenge["responded_at"] = datetime.now(UTC).isoformat()

        return {
            "success": True,
            "challenge_id": challenge_id,
            "status": challenge["status"],
        }

    def _trust_device(
        self, user_id: str, device_info: Dict[str, Any], trust_duration_days: int
    ) -> Dict[str, Any]:
        """Trust a device for the user.

        Args:
            user_id: User ID
            device_info: Device information including device_id, device_fingerprint, etc.
            trust_duration_days: Number of days to trust the device

        Returns:
            Device trust result
        """
        if not device_info.get("device_id"):
            return {"success": False, "error": "Device ID required for device trust"}

        # Generate trust token
        trust_token = secrets.token_urlsafe(32)

        # Create trusted device entry
        trusted_device = {
            "device_id": device_info.get("device_id"),
            "device_fingerprint": device_info.get("device_fingerprint", ""),
            "user_agent": device_info.get("user_agent", ""),
            "platform": device_info.get("platform", "unknown"),
            "trust_token": trust_token,
            "trusted_at": datetime.now(UTC).isoformat(),
            "expires_at": (
                datetime.now(UTC) + timedelta(days=trust_duration_days)
            ).isoformat(),
            "trust_duration_days": trust_duration_days,
        }

        # Initialize user's trusted devices if needed
        if user_id not in self.trusted_devices:
            self.trusted_devices[user_id] = []

        # Remove any existing trust for this device
        self.trusted_devices[user_id] = [
            device
            for device in self.trusted_devices[user_id]
            if device.get("device_id") != device_info.get("device_id")
        ]

        # Add new trusted device
        self.trusted_devices[user_id].append(trusted_device)

        return {
            "success": True,
            "device_trusted": True,
            "trust_token": trust_token,
            "expires_in_days": trust_duration_days,
            "expires_at": trusted_device["expires_at"],
        }

    def _check_device_trust(
        self, user_id: str, device_info: Dict[str, Any], trust_token: Optional[str]
    ) -> Dict[str, Any]:
        """Check if a device is trusted.

        Args:
            user_id: User ID
            device_info: Device information including device_id
            trust_token: Trust token to verify

        Returns:
            Device trust check result
        """
        if isinstance(device_info, str):
            device_id = device_info
        else:
            device_id = device_info.get("device_id") if device_info else None
        if not device_id:
            return {"success": False, "error": "Device ID required"}

        # ONE store (issue #2047). This used to consult `self.trusted_devices`
        # AND `user_mfa_data[user]["trusted_devices"]`, synthesising a record
        # shape for the second and tagging each with `_store` so expiry
        # cleanup could delete from whichever one it came from. Two stores for
        # one fact is why that tagging was needed at all, and why removing a
        # synthesised dict from the wrong store raised out of execute()
        # (issue #2026 patched the symptom). Both writers now land in
        # `self.trusted_devices`, so there is one place to read, one place to
        # expire, and one place `revoke`/`reset`/`_disable_all_mfa` clear.
        if user_id not in self.trusted_devices or not self.trusted_devices[user_id]:
            return {
                "success": True,
                "trusted": False,
                "skip_mfa": False,
                "reason": "No trusted devices found",
            }

        devices_to_check = list(self.trusted_devices[user_id])

        # A device_id is an identifier, not a secret -- it is echoed back by
        # setup_push and trust_device. Without a token requirement, anyone
        # naming a device_id got skip_mfa=True (issue #2026).
        if not trust_token:
            return {
                "success": True,
                "trusted": False,
                "skip_mfa": False,
                "reason": "trust_token required",
            }

        for device in devices_to_check:
            device_matches = device.get("device_id") == device_id
            stored_token = device.get("trust_token") or ""
            token_matches = secrets.compare_digest(
                str(stored_token).encode("utf-8"), str(trust_token).encode("utf-8")
            )

            if device_matches and token_matches:
                # A missing/malformed expiry is treated as expired rather than
                # raising out of execute().
                try:
                    expires_at = datetime.fromisoformat(device.get("expires_at") or "")
                except (TypeError, ValueError):
                    expires_at = datetime.now(UTC) - timedelta(seconds=1)

                if expires_at <= datetime.now(UTC):
                    # Remove expired trust. One store, so no origin tag and no
                    # branch on which store to delete from.
                    if user_id in self.trusted_devices:
                        try:
                            self.trusted_devices[user_id].remove(device)
                        except ValueError:
                            # Already removed by a concurrent expiry cleanup.
                            # The device is gone either way, which is the
                            # outcome this branch exists to produce, so there
                            # is nothing to recover from.
                            self.log_with_context(
                                "DEBUG",
                                "Expired trusted device was already removed",
                            )
                    return {
                        "success": True,
                        "trusted": False,
                        "skip_mfa": False,
                        "reason": "Device trust has expired",
                    }

                return {
                    "success": True,
                    "trusted": True,
                    "skip_mfa": True,
                    "device_id": device.get("device_id"),
                    "expires_at": device.get("expires_at"),
                }

        return {
            "success": True,
            "trusted": False,
            "skip_mfa": False,
            "reason": "Device not trusted or invalid token",
        }

    def _verify_mfa(self, user_id: str, code: str, method: str) -> Dict[str, Any]:
        """Verify MFA code.

        Args:
            user_id: User ID
            code: MFA code to verify
            method: MFA method to verify

        Returns:
            Verification result
        """
        if not code:
            return {
                "success": False,
                "verified": False,
                "error": "Verification code required",
            }

        with self._data_lock:
            if user_id not in self.user_mfa_data:
                # Check if there's a pending verification (for tests)
                if user_id in self.pending_verifications:
                    pending = self.pending_verifications[user_id]

                    # Check rate limiting
                    attempts = pending.get("attempts", 0)
                    if attempts >= 5:  # Max 5 attempts
                        return {
                            "success": False,
                            "verified": False,
                            "error": "Too many attempts. Please request a new verification code.",
                        }

                    if (
                        pending.get("method") == method
                        and pending.get("code") == code
                        and pending.get("expires_at", datetime.now(UTC))
                        > datetime.now(UTC)
                    ):
                        # Remove from pending and create session
                        del self.pending_verifications[user_id]
                        session_id = self._create_mfa_session_internal(user_id)

                        return {
                            "success": True,
                            "verified": True,
                            "method": method,
                            "session_id": session_id,
                            "pending_verification": True,
                        }
                    else:
                        # Increment attempts on failed verification.
                        # Return success=False to keep `success` consistent with
                        # `verified`: an invalid/expired code is a verification
                        # failure, not a successful operation (issue #803).
                        self.pending_verifications[user_id]["attempts"] = attempts + 1
                        return {
                            "success": False,
                            "verified": False,
                            "user_id": user_id,
                            "method": method,
                            "message": "Invalid code or expired verification",
                            "error": "Invalid code or expired verification",
                        }

                # A user with no MFA enrolled cannot satisfy a second factor.
                # This previously auto-enrolled ANY user who presented the
                # literal code "123456" against a hardcoded shared secret and
                # handed back a fully verified MFA session (issue #2026):
                # verification is never a path to enrolment.
                return {
                    "success": False,
                    "verified": False,
                    "error": "MFA not setup for user",
                }

            user_data = self.user_mfa_data[user_id]

            # Check if it's a backup code first
            # A backup code only substitutes for a factor that EXISTS and has
            # been verified. Codes are minted at setup time, so accepting them
            # against an unverified enrolment made `setup -> verify` a
            # complete second factor with nothing proven (issue #2026).
            if (
                self.backup_codes
                and any(
                    m.get("verified") for m in user_data.get("methods", {}).values()
                )
                and code in user_data.get("backup_codes", [])
            ):
                # Remove used backup code
                user_data["backup_codes"].remove(code)
                self.mfa_stats["backup_codes_used"] += 1

                # Create MFA session (internal, lock-free)
                session_id = self._create_mfa_session_internal(user_id)

                self._queue_security_event(user_id, "backup_code_used", "medium")

                return {
                    "success": True,
                    "verified": True,
                    "user_id": user_id,
                    "method": "backup_code",
                    "session_id": session_id,
                    "codes_remaining": len(user_data.get("backup_codes", [])),
                    "warning": "Backup code used. Consider regenerating backup codes.",
                }

            # Handle backup_code method specially
            if method == "backup_code":
                # A backup code only substitutes for a factor that EXISTS and
                # has been verified (issue #2026).
                if (
                    self.backup_codes
                    and any(
                        m.get("verified") for m in user_data.get("methods", {}).values()
                    )
                    and code in user_data.get("backup_codes", [])
                ):
                    # Remove used backup code
                    user_data["backup_codes"].remove(code)
                    self.mfa_stats["backup_codes_used"] += 1

                    # Create MFA session (internal, lock-free)
                    session_id = self._create_mfa_session_internal(user_id)

                    return {
                        "success": True,
                        "verified": True,
                        "user_id": user_id,
                        "method": "backup_code",
                        "session_id": session_id,
                        "codes_remaining": len(user_data.get("backup_codes", [])),
                    }
                else:
                    # Failed verification — return success=False for consistency
                    # with `verified=False` (issue #803).
                    return {
                        "success": False,
                        "verified": False,
                        "user_id": user_id,
                        "method": "backup_code",
                        "message": "Backup code already used or invalid",
                        "error": "Backup code already used or invalid",
                    }

            # Verify using specified method
            if method not in user_data["methods"]:
                return {
                    "success": False,
                    "verified": False,
                    "error": f"Method {method} not setup for user",
                }

            method_data = user_data["methods"][method]

            if method == "totp":
                verified = self._verify_totp_code(method_data["secret"], code)
            elif method == "sms":
                verified = self._verify_sms_code(user_id, code)
            elif method == "email":
                verified = self._verify_email_code(user_id, code)
            else:
                return {
                    "success": False,
                    "verified": False,
                    "error": f"Verification not implemented for method: {method}",
                }

            if verified:
                # Mark method as verified if it's the first time
                if not method_data.get("verified", False):
                    method_data["verified"] = True
                    method_data["verified_at"] = datetime.now(UTC).isoformat()

                # Create MFA session (internal, lock-free)
                session_id = self._create_mfa_session_internal(user_id)

                self._queue_security_event(user_id, "mfa_verification_success", "low")

                return {
                    "success": True,
                    "verified": True,
                    "method": method,
                    "session_id": session_id,
                }
            else:
                # Log failed verification (sync version - no security event logging)
                # Return success=False for consistency with `verified=False`
                # (issue #803). Previously returned success=True which conflated
                # "operation completed" with "verification succeeded" and risked
                # callers gating access on `success` alone.
                return {
                    "success": False,
                    "verified": False,
                    "user_id": user_id,
                    "method": method,
                    "message": "Invalid code",
                    "error": "Invalid code",
                }

    def _verify_totp_code(self, secret: str, code: str) -> bool:
        """Verify TOTP code.

        Args:
            secret: TOTP secret
            code: Code to verify

        Returns:
            True if code is valid
        """
        try:
            # Use pyotp for compatibility with test
            import pyotp

            totp = pyotp.TOTP(secret)
            return totp.verify(code)
        except Exception as e:
            self.log_with_context("WARNING", f"TOTP verification error: {e}")
            return False

    def _verify_sms_code(self, user_id: str, code: str) -> bool:
        """Verify SMS code.

        Args:
            user_id: User ID
            code: Code to verify

        Returns:
            True if code is valid
        """
        # Check pending verifications first (for test compatibility)
        if user_id in self.pending_verifications:
            pending = self.pending_verifications[user_id]
            if (
                pending.get("method") == "sms"
                and pending.get("code") == code
                and pending.get("expires_at", datetime.now(UTC)) > datetime.now(UTC)
            ):
                # Remove from pending after successful verification
                del self.pending_verifications[user_id]
                return True

        # Check temp SMS code (from actual SMS sending)
        if user_id in self.user_mfa_data:
            temp_code_data = self.user_mfa_data[user_id].get("temp_sms_code")
            if (
                temp_code_data
                and temp_code_data.get("code") == code
                and temp_code_data.get("expires_at", datetime.now(UTC))
                > datetime.now(UTC)
            ):
                # Remove temp code after use
                del self.user_mfa_data[user_id]["temp_sms_code"]
                return True

        # Fail closed: a code that matches no issued challenge is invalid. The
        # previous shape-only fallback accepted ANY 6-digit string, so every
        # SMS second factor could be cleared by guessing "000000".
        return False

    def _verify_email_code(self, user_id: str, code: str) -> bool:
        """Verify email code.

        Verified against the challenge actually issued to this user by
        :meth:`_send_email_code` (or a pending verification), never by shape.

        Args:
            user_id: User ID
            code: Code to verify

        Returns:
            True if code matches a live, unexpired challenge for this user
        """
        # Check pending verifications first
        if user_id in self.pending_verifications:
            pending = self.pending_verifications[user_id]
            if (
                pending.get("method") == "email"
                and pending.get("code") == code
                and pending.get("expires_at", datetime.now(UTC)) > datetime.now(UTC)
            ):
                del self.pending_verifications[user_id]
                return True

        # Check the code stored when the email challenge was delivered
        if user_id in self.user_mfa_data:
            temp_code_data = self.user_mfa_data[user_id].get("temp_email_code")
            if (
                temp_code_data
                and temp_code_data.get("code") == code
                and temp_code_data.get("expires_at", datetime.now(UTC))
                > datetime.now(UTC)
            ):
                del self.user_mfa_data[user_id]["temp_email_code"]
                return True

        # Fail closed: previously ANY 6-digit string was accepted.
        return False

    def _generate_backup_codes_for_user(self, user_id: str) -> List[str]:
        """Generate backup codes for user and return just the codes list."""
        backup_codes = []
        for _ in range(self.backup_codes_count):
            # Generate 8-character alphanumeric code
            code = "".join(
                secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8)
            )
            backup_codes.append(code)

        # Store backup codes
        if user_id not in self.user_mfa_data:
            self.user_mfa_data[user_id] = {"methods": {}, "backup_codes": []}

        self.user_mfa_data[user_id]["backup_codes"] = backup_codes
        self.user_mfa_data[user_id]["backup_codes_generated_at"] = datetime.now(
            UTC
        ).isoformat()

        return backup_codes

    def _generate_backup_codes(self, user_id: str) -> Dict[str, Any]:
        """Generate backup codes for user.

        Args:
            user_id: User ID

        Returns:
            Backup codes result
        """
        if not self.backup_codes:
            return {"success": False, "error": "Backup codes not enabled"}

        with self._data_lock:
            # Gate on an ENROLLED FACTOR, not on the presence of a record:
            # set_preference and trust_device both create an empty
            # user_mfa_data entry, so a key-presence check was bypassable in
            # two calls. The codes returned here are accepted directly by
            # _verify_mfa, so issuing them to an unenrolled user reached the
            # same outcome as the removed "123456" auto-enrolment stub
            # (issue #2026). Backup codes supplement a factor; never establish one.
            if not self.user_mfa_data.get(user_id, {}).get("methods"):
                return {
                    "success": False,
                    "user_id": user_id,
                    "error": "MFA not setup for user",
                }

            # Generate backup codes
            backup_codes = []
            for _ in range(self.backup_codes_count):
                # Generate 8-character alphanumeric code
                code = "".join(
                    secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
                    for _ in range(8)
                )
                backup_codes.append(code)

            # Store backup codes
            self.user_mfa_data[user_id]["backup_codes"] = backup_codes
            self.user_mfa_data[user_id]["backup_codes_generated_at"] = datetime.now(
                UTC
            ).isoformat()

            self._queue_security_event(user_id, "backup_codes_generated", "low")

            return {
                "success": True,
                "backup_codes": backup_codes,
                "instructions": [
                    "Store these backup codes in a safe place",
                    "Each code can only be used once",
                    "Use backup codes if you lose access to your MFA device",
                ],
            }

    def _revoke_mfa(self, user_id: str, method: str) -> Dict[str, Any]:
        """Revoke MFA method for user.

        Args:
            user_id: User ID
            method: MFA method to revoke

        Returns:
            Revocation result
        """
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {"success": False, "error": "MFA not setup for user"}

            user_data = self.user_mfa_data[user_id]

            if method == "all":
                # Capture the method list BEFORE clearing it: reading it after
                # the reset always reported an empty revoked_methods.
                revoked_methods = list(user_data.get("methods", {}).keys())
                user_data["methods"] = {}
                user_data["backup_codes"] = []
            else:
                if method not in user_data["methods"]:
                    return {
                        "success": False,
                        "error": f"Method {method} not setup for user",
                    }

                # Revoke specific method
                del user_data["methods"][method]
                revoked_methods = [method]

            # Invalidate all sessions. The lock-free variant: _data_lock is
            # already held here and is not reentrant.
            self._invalidate_user_sessions_internal(user_id)

            self._queue_security_event(user_id, "mfa_revoked", "high")

            return {
                "success": True,
                "revoked_methods": revoked_methods,
                "message": "MFA has been revoked. All sessions have been invalidated.",
            }

    def _get_mfa_status(self, user_id: str) -> Dict[str, Any]:
        """Get MFA status for user.

        Args:
            user_id: User ID

        Returns:
            MFA status
        """
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {
                    "success": True,
                    "user_id": user_id,
                    "mfa_enabled": False,
                    "methods": [],
                    "enrolled_methods": [],
                    "enabled_methods": [],
                }

            user_data = self.user_mfa_data[user_id]

            methods_status = []
            for method, method_data in user_data["methods"].items():
                methods_status.append(
                    {
                        "method": method,
                        "verified": method_data.get("verified", False),
                        "setup_at": method_data.get("setup_at"),
                        "verified_at": method_data.get("verified_at"),
                    }
                )

            enrolled_methods = list(user_data["methods"].keys())
            return {
                "success": True,
                "user_id": user_id,
                "mfa_enabled": len(user_data["methods"]) > 0,
                "methods": methods_status,
                "enrolled_methods": enrolled_methods,
                # Alias for `enrolled_methods` — preserved for callers that
                # consumed the older response shape (issue #803).
                "enabled_methods": enrolled_methods,
                "backup_codes_available": len(user_data.get("backup_codes", [])),
                "backup_codes_generated_at": user_data.get("backup_codes_generated_at"),
                "created_at": user_data.get("created_at"),
            }

    def _create_mfa_session(self, user_id: str) -> str:
        """Create MFA session.

        Args:
            user_id: User ID

        Returns:
            Session ID
        """
        session_id = secrets.token_urlsafe(32)

        with self._data_lock:
            self.user_sessions[session_id] = {
                "user_id": user_id,
                "created_at": datetime.now(UTC),
                "expires_at": datetime.now(UTC) + self.session_timeout,
            }

        return session_id

    def _create_mfa_session_internal(self, user_id: str) -> str:
        """Create MFA session (internal, assumes lock is already held).

        Args:
            user_id: User ID

        Returns:
            Session ID
        """
        session_id = secrets.token_urlsafe(32)

        # No lock needed - assumes caller holds lock
        self.user_sessions[session_id] = {
            "user_id": user_id,
            "created_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + self.session_timeout,
        }

        return session_id

    def _invalidate_user_sessions(self, user_id: str) -> None:
        """Invalidate all sessions for user.

        Args:
            user_id: User ID
        """
        with self._data_lock:
            self._invalidate_user_sessions_internal(user_id)

    def _invalidate_user_sessions_internal(self, user_id: str) -> None:
        """Invalidate all sessions for user. Caller MUST hold ``_data_lock``.

        ``_data_lock`` is a non-reentrant ``threading.Lock``, so the locking
        wrapper above cannot be called from a context that already holds it --
        ``_revoke_mfa`` did exactly that and self-deadlocked while holding the
        lock, wedging every MFA operation in the process (issue #2026). Mirrors
        the ``_create_mfa_session_internal`` split.

        Args:
            user_id: User ID
        """
        sessions_to_remove = [
            session_id
            for session_id, session_data in self.user_sessions.items()
            if session_data["user_id"] == user_id
        ]
        for session_id in sessions_to_remove:
            del self.user_sessions[session_id]

    def _check_rate_limit(self, user_id: str) -> bool:
        """Check rate limit for user.

        Args:
            user_id: User ID

        Returns:
            True if within rate limit
        """
        current_time = datetime.now(UTC)
        cutoff_time = current_time - timedelta(seconds=self.rate_limit_window)

        with self._data_lock:
            if user_id not in self.rate_limit_data:
                self.rate_limit_data[user_id] = []

            # Remove old attempts
            self.rate_limit_data[user_id] = [
                attempt_time
                for attempt_time in self.rate_limit_data[user_id]
                if attempt_time > cutoff_time
            ]

            # Check if under limit
            if len(self.rate_limit_data[user_id]) >= self.rate_limit_attempts:
                return False

            # Add current attempt
            self.rate_limit_data[user_id].append(current_time)
            return True

    def _generate_verification_code(self) -> str:
        """Generate verification code.

        Returns:
            6-digit verification code
        """
        return "".join(secrets.choice("0123456789") for _ in range(6))

    def _generate_qr_code(self, data: str) -> str:
        """Generate QR code for data.

        Args:
            data: Data to encode

        Returns:
            Base64-encoded QR code image
        """
        try:
            qr = qrcode.QRCode(  # type: ignore[reportAttributeAccessIssue]
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,  # type: ignore[reportAttributeAccessIssue]
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode()

            return f"data:image/png;base64,{img_str}"
        except Exception as e:
            self.log_with_context("WARNING", f"QR code generation failed: {e}")
            return ""

    def _send_sms_code(self, phone: str, code: str, user_id: str) -> bool:
        """Send SMS verification code via the configured provider.

        Args:
            phone: Phone number
            code: Verification code
            user_id: User ID

        Returns:
            True if a configured provider actually delivered the message,
            False if no provider is configured (nothing was sent).

        Raises:
            MFADeliveryError: A provider IS configured but delivery failed.
        """
        delivered = False

        # Use Twilio if configured
        if self.sms_provider and self.sms_provider.get("service") == "twilio":
            self._twilio_send(phone, f"Your verification code: {code}")
            delivered = True
        else:
            # No provider bound: say so at WARNING. This previously logged
            # "SMS code sent", which was false.
            self.log_with_context(
                "WARNING",
                f"No SMS provider configured; no code was delivered to "
                f"the enrolled destination for user {user_id}",
            )

        # Store code for verification (in production, use secure storage)
        # Note: No lock needed here as this is called within locked context
        if user_id not in self.user_mfa_data:
            self.user_mfa_data[user_id] = {"methods": {}}

        self.user_mfa_data[user_id]["temp_sms_code"] = {
            "code": code,
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        }

        return delivered

    def _send_email_code(self, email: str, code: str, user_id: str) -> bool:
        """Send email verification code via the configured SMTP provider.

        Args:
            email: Email address
            code: Verification code
            user_id: User ID

        Returns:
            True if a configured provider actually delivered the message,
            False if no provider is configured (nothing was sent).

        Raises:
            MFADeliveryError: A provider IS configured but delivery failed.
        """
        delivered = False

        # Use SMTP if configured
        if self.email_provider and self.email_provider.get("smtp_host"):
            self._smtp_send(
                email, "MFA Verification Code", f"Your verification code: {code}"
            )
            delivered = True
        else:
            # No provider bound: say so at WARNING. This previously logged
            # "Email code sent", which was false.
            self.log_with_context(
                "WARNING",
                f"No email provider configured; no code was delivered to "
                f"{self._mask_email(email)} for user {user_id}",
            )

        # Store code for verification (in production, use secure storage)
        # Note: No lock needed here as this is called within locked context
        if user_id not in self.user_mfa_data:
            self.user_mfa_data[user_id] = {"methods": {}}

        self.user_mfa_data[user_id]["temp_email_code"] = {
            "code": code,
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        }

        return delivered

    def _twilio_send(self, phone: Optional[str], body: str) -> None:
        """Send one SMS via the configured Twilio provider.

        The single Twilio transport, shared by code delivery and recovery-token
        delivery. ``body`` is a credential-bearing message and is never logged.

        Raises:
            MFADeliveryError: Delivery failed.
        """
        try:
            from twilio.rest import Client

            client = Client(
                self.sms_provider.get("account_sid"),
                self.sms_provider.get("auth_token"),
            )
            message = client.messages.create(
                body=body,
                from_=self.sms_provider.get("from_number"),
                to=phone,
            )
            masked = "the enrolled destination"
            self.log_with_context(
                "INFO", f"SMS sent via Twilio to {masked} (SID: {message.sid})"
            )
        except Exception as e:
            # Fail closed. Swallowing this made the caller report
            # "verification_sent": True for a code the user never got.
            self.log_with_context("ERROR", f"Failed to send SMS via Twilio: {e}")
            raise MFADeliveryError(f"Failed to send SMS via Twilio: {e}") from e

    def _smtp_send(self, email: Optional[str], subject: str, body: str) -> None:
        """Send one email via the configured SMTP provider.

        The single SMTP transport, shared by code delivery and recovery-token
        delivery. ``body`` is credential-bearing and is never logged; the
        recipient is logged masked.

        Raises:
            MFADeliveryError: Delivery failed.
        """
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart()
            msg["From"] = self.email_provider.get("username")  # type: ignore[reportArgumentType]
            msg["To"] = email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            # An explicit timeout: smtplib defaults to the global socket
            # timeout (None), so a blackholing host blocked forever.
            server = smtplib.SMTP(
                self.email_provider.get("smtp_host"),  # type: ignore[reportArgumentType]
                self.email_provider.get("smtp_port", 587),
                timeout=self.email_provider.get("timeout", 15),
            )
            server.starttls()
            server.login(
                self.email_provider.get("username"),  # type: ignore[reportArgumentType]
                self.email_provider.get("password"),  # type: ignore[reportArgumentType]
            )
            server.send_message(msg)
            server.quit()

            self.log_with_context(
                "INFO", f"Email sent via SMTP to {self._mask_email(email)}"
            )
        except Exception as e:
            # Fail closed. Swallowing this made the caller report
            # "verification_sent": True for a code the user never got.
            self.log_with_context("ERROR", f"Failed to send email via SMTP: {e}")
            raise MFADeliveryError(f"Failed to send email via SMTP: {e}") from e

    @staticmethod
    def _mask_email(email: Optional[str]) -> str:
        """Mask an address for logging, mirroring the SMS last-4 treatment."""
        if not email or "@" not in email:
            return "****"
        local, _, domain = email.partition("@")
        head = local[:2] if len(local) > 2 else local[:1]
        return f"{head}***@{domain}"

    async def _audit_mfa_operation(
        self, user_id: str, action: str, method: str, result: Dict[str, Any]
    ) -> None:
        """Audit MFA operation.

        Args:
            user_id: User ID
            action: MFA action
            method: MFA method
            result: Operation result
        """
        await asyncio.to_thread(
            self._audit_mfa_operation_sync, user_id, action, method, result
        )

    # Result keys that may be copied into an audit record. This is an
    # ALLOWLIST, not a denylist, and that is deliberate: MFA results carry
    # credential material -- the TOTP seed, the provisioning URI that embeds
    # it, backup/recovery codes, device trust tokens, MFA session ids, and
    # unmasked phone/email -- and an audit sink writes to whatever handler the
    # operator attached, typically a log aggregator with far wider read access
    # than the credential store. Copying a whole result dict here would put a
    # user's second factor in the SIEM: strictly worse than the unwired sink
    # this replaced. A new result key is omitted until it is reviewed and
    # added, so the failure mode of forgetting to update this list is a
    # thinner record rather than a leaked secret.
    _AUDITABLE_RESULT_KEYS = frozenset(
        {
            "success",
            "action",
            "method",
            "user_id",
            "verified",
            "error",
            "reason",
            "reset",
            "revoked",
            "disabled",
            "enabled",
            "mfa_enabled",
            "methods",
            "challenge_required",
            # A trusted-device bypass is arguably the single most important
            # fact this node can record: it means the second factor was NOT
            # presented for this login.
            "trusted",
            "skip_mfa",
            "device_id",
            # What a destructive admin action actually destroyed.
            "revoked_methods",
            "disabled_methods",
            "mfa_disabled",
            "method_disabled",
            "challenge_id",
            "recovery_method",
            "pending_verification",
            "valid",
            "enrolled_methods",
            "rate_limited",
            "too_many_attempts",
            "locked",
            "admin_override",
            # Whether the (actor, action, subject) check permitted the call.
            # A refused attempt is the record an auditor most wants.
            "authorized",
            "codes_remaining",
            "backup_codes_remaining",
            "attempts_remaining",
            "verification_sent",
            "masked_phone",
            "masked_email",
            "expires_at",
            "setup_at",
            "processing_time_ms",
            "timestamp",
        }
    )

    @classmethod
    def _audit_safe_result(cls, result: Dict[str, Any]) -> Dict[str, Any]:
        """Project a result down to the keys that are safe to record.

        Returns the allowlisted keys plus ``omitted_keys``, so the record
        states what it withheld rather than silently presenting a partial
        result as a whole one.
        """
        if not isinstance(result, dict):
            return {"omitted_keys": []}
        safe = {k: v for k, v in result.items() if k in cls._AUDITABLE_RESULT_KEYS}
        safe["omitted_keys"] = sorted(
            k for k in result if k not in cls._AUDITABLE_RESULT_KEYS
        )
        # The allowlist is FLAT -- it admits a key, not the shape underneath
        # it. "methods" is safe only because its producer happens to be a
        # curated projection; a future change returning user_mfa_data["methods"]
        # directly would hand this the TOTP seed and push_token nested one level
        # down, and the allowlist would copy them straight through. Composing
        # the same redactor used at every SSO and directory sink closes that,
        # and puts the strongest filter where the credential material actually
        # lives rather than only where it does not.
        return redact_mapping(safe)

    def _audit_mfa_operation_sync(
        self,
        user_id: str,
        action: str,
        method: str,
        result: Dict[str, Any],
        actor: Optional[MFAActor] = None,
    ) -> None:
        """Audit an MFA operation from a synchronous caller.

        Both dispatchers audit through this: ``run()`` calls it directly and
        ``async_run()`` offloads it to a worker thread. Previously only the
        async dispatcher audited at all, and the sync one carried a commented
        out call, so ``revoke`` / ``disable`` / ``reset`` through the sync
        surface completed with no record whatsoever (issue #2060).

        AuditLogNode is a sync-only Node -- see ``_flush_audit_records``. Its
        parameters are event_type/message/user_id/event_data; the previous
        action=/resource_type=/resource_id=/metadata=/ip_address= were all
        dropped by execute(), so even a resolved call would have written
        {"event_type": "info", "message": "", "data": {}}.
        """
        audit_entry = {
            "event_type": f"mfa_{action}",
            "message": f"MFA {action} ({method}) for user {log_safe(user_id, 64)}",
            "user_id": log_safe(user_id),
            "event_data": {
                "action": action,
                "method": method,
                "resource_type": "mfa",
                "resource_id": f"{user_id}:{method}",
                "success": (
                    result.get("success", False) if isinstance(result, dict) else False
                ),
                "result": self._audit_safe_result(result),
                # user_id above is the SUBJECT; this is the ACTOR -- who did
                # it. #2066 shipped this key as a hard-coded None with a test
                # asserting it, DELIBERATELY as a tripwire: the trail was
                # honest about attribution it could not support, and the test
                # was a marker to revisit when an actor landed. It has landed
                # (#2047), so the field now carries the server-derived
                # principal and the tripwire test is updated rather than
                # deleted.
                #
                # Still None under the explicit require_actor=False opt-out,
                # where the node genuinely does not know the caller: recording
                # the subject as the actor there would be a fabricated
                # attribution, which is worse than an absent one.
                "actor": actor.user_id if actor is not None else None,
                "ip_address": "unknown",
            },
        }

        try:
            self.audit_log_node.execute(**audit_entry)
        except (AttributeError, TypeError, ValueError) as e:
            # Narrow: a broad `except Exception` here hid the fact that the
            # sink was None behind a warning that looked transient.
            self.log_with_context("WARNING", f"Failed to audit MFA operation: {e}")

    def validate_session(self, session_id: str) -> Dict[str, Any]:
        """Validate MFA session.

        Args:
            session_id: Session ID to validate

        Returns:
            Session validation result
        """
        with self._data_lock:
            if session_id not in self.user_sessions:
                return {"valid": False, "reason": "Session not found"}

            session_data = self.user_sessions[session_id]
            current_time = datetime.now(UTC)

            if current_time > session_data["expires_at"]:
                # Remove expired session
                del self.user_sessions[session_id]
                return {"valid": False, "reason": "Session expired"}

            return {
                "valid": True,
                "user_id": session_data["user_id"],
                "created_at": session_data["created_at"].isoformat(),
                "expires_at": session_data["expires_at"].isoformat(),
            }

    def get_mfa_stats(self) -> Dict[str, Any]:
        """Get MFA statistics.

        Returns:
            Dictionary with MFA statistics
        """
        return {
            **self.mfa_stats,
            "supported_methods": self.methods,
            "backup_codes_enabled": self.backup_codes,
            "session_timeout_minutes": self.session_timeout.total_seconds() / 60,
            "rate_limit_attempts": self.rate_limit_attempts,
            "rate_limit_window_seconds": self.rate_limit_window,
            "active_users": len(self.user_mfa_data),
            "active_sessions": len(self.user_sessions),
        }

    def _verify_backup_code(self, user_id: str, code: str) -> Dict[str, Any]:
        """Verify backup code for user.

        The fifth backup-code verification site. It carried none of the
        guarantees the other four gained in issue #2026: it accepted a code
        against an enrolment that had verified nothing, and it reported
        ``success: True`` for a REJECTED code, so a caller gating on the
        conventional ``success`` field granted access on a failed verification.
        """
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {
                    "success": False,
                    "verified": False,
                    "reason": "user_not_found",
                }

            user_data = self.user_mfa_data[user_id]
            backup_codes = user_data.get("backup_codes", [])

            # A backup code substitutes for a VERIFIED factor; it never
            # establishes one (issue #2026).
            if not any(
                m.get("verified") for m in user_data.get("methods", {}).values()
            ):
                return {
                    "success": False,
                    "verified": False,
                    "reason": "no_verified_factor",
                }

            if code in backup_codes:
                # Remove used backup code
                backup_codes.remove(code)
                user_data["backup_codes"] = backup_codes
                self.mfa_stats["backup_codes_used"] += 1

                return {"success": True, "verified": True, "method": "backup_code"}

            return {
                "success": False,
                "verified": False,
                "reason": "invalid_code",
            }

    def _trust_device_by_fingerprint(
        self, user_id: str, device_fingerprint: str
    ) -> Dict[str, Any]:
        """Trust a device named by fingerprint. ONE store (issue #2047).

        This wrote into ``user_mfa_data[user]["trusted_devices"]`` while the
        sync path wrote into ``self.trusted_devices``. Two stores for one fact
        meant which one a trust landed in -- and therefore whether `revoke`,
        `reset` or `_disable_all_mfa` could clear it -- depended on which
        dispatcher the caller happened to reach. It also CREATED an MFA record
        for any subject as a side effect, so trusting a device enrolled a user
        who had never enrolled.

        It is now the fingerprint spelling of :meth:`_trust_device`.
        """
        if not device_fingerprint:
            return {"success": False, "error": "Device fingerprint required"}
        return self._trust_device(
            user_id,
            {
                "device_id": device_fingerprint,
                "device_fingerprint": device_fingerprint,
            },
            30,
        )

    def _set_user_preference(
        self, user_id: str, preferred_method: str
    ) -> Dict[str, Any]:
        """Set user's preferred MFA method."""
        if not preferred_method:
            return {"success": False, "error": "Preferred method is required"}

        if preferred_method not in self.methods:
            return {
                "success": False,
                "error": f"Unsupported method: {preferred_method}",
            }

        with self._data_lock:
            if user_id not in self.user_mfa_data:
                self.user_mfa_data[user_id] = {
                    "methods": {},
                    "backup_codes": [],
                    "preferences": {},
                }

            if "preferences" not in self.user_mfa_data[user_id]:
                self.user_mfa_data[user_id]["preferences"] = {}

            self.user_mfa_data[user_id]["preferences"][
                "preferred_method"
            ] = preferred_method

        return {"success": True, "preferred_method": preferred_method}

    def _get_user_methods(self, user_id: str) -> Dict[str, Any]:
        """Get user's available MFA methods and preferences."""
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {
                    "success": True,
                    "available_methods": [],
                    "preferred_method": self.default_method,
                }

            user_data = self.user_mfa_data[user_id]
            enrolled_methods = list(user_data.get("methods", {}).keys())
            preferred_method = user_data.get("preferences", {}).get(
                "preferred_method", self.default_method
            )

            return {
                "success": True,
                "available_methods": enrolled_methods,
                "preferred_method": preferred_method,
            }

    def _list_methods(self, user_id: str) -> Dict[str, Any]:
        """List MFA methods for user."""
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {"success": True, "methods": []}

            user_data = self.user_mfa_data[user_id]
            methods = list(user_data.get("methods", {}).keys())

            return {"success": True, "methods": methods}

    def _log_mfa_event(self, event_type: str, metadata: Dict[str, Any]) -> None:
        """Record an MFA event for the audit sink.

        This is called from handlers that hold ``_data_lock`` (``_setup_totp``
        runs inside ``_setup_mfa``'s ``with self._data_lock:``), so it does NOT
        write to the sink here. ``AuditLogNode.execute`` calls whatever logging
        handler the operator attached; a syslog/HTTP/SIEM handler blocking on
        the network while ``_data_lock`` is held would stall every MFA
        operation in the process behind it -- a slow log collector becoming an
        authentication outage. The record is queued and flushed by the
        dispatcher after the lock is released.
        """
        event = {
            "kind": "audit",
            "event_type": event_type,
            "metadata": metadata,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.audit_events.append(event)
        self._pending_audit_records.append(event)

    def _queue_security_event(
        self, user_id: str, event_type: str, severity: str
    ) -> None:
        """Queue a security event for the sink. Safe to call under ``_data_lock``.

        The four callers of this sit inside ``_data_lock``-held handlers, which
        is why they stood commented out as "disabled for sync operation": the
        only surface available was an async ``_log_security_event``. So the
        ``mfa_revoked`` HIGH-severity event -- the one that pages someone when
        a second factor is destroyed -- has never fired (issue #2060). Queueing
        is synchronous and lock-safe; the dispatcher flushes after release.
        """
        self._pending_audit_records.append(
            {
                "kind": "security",
                "event_type": event_type,
                "severity": severity,
                "user_id": user_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def _flush_audit_records(self) -> None:
        """Write queued records to the sinks. MUST run outside ``_data_lock``.

        The ``hasattr(...) and self.audit_log_node`` guard that used to stand
        at the write site is gone: ``__init__`` always constructs the sink now,
        so the absent-branch was unreachable and would have returned success
        while recording nothing (issue #2060).
        """
        while True:
            try:
                event = self._pending_audit_records.popleft()
            except IndexError:
                # Empty, or drained concurrently by the other dispatcher. Both
                # are the same non-event; popleft is checked rather than
                # guarded by a truthiness test so a concurrent drain cannot
                # raise out of a logging call.
                return

            try:
                if event["kind"] == "security":
                    self.security_event_node.execute(
                        event_type=event["event_type"],
                        severity=str(event["severity"] or "INFO").upper(),
                        message=f"MFA {event['event_type']} for user {log_safe(event['user_id'], 64)}",
                        user_id=log_safe(event["user_id"]),
                        metadata={"mfa_operation": True, "source_ip": "unknown"},
                    )
                else:
                    metadata = event["metadata"]
                    self.audit_log_node.execute(
                        event_type=event["event_type"],
                        message=f"MFA event {event['event_type']}",
                        user_id=log_safe(metadata.get("user_id")),
                        event_data=self._audit_safe_result(metadata),
                    )
            except Exception as e:
                # Don't fail the main operation if audit logging fails
                logger.warning(f"Audit logging failed: {e}")

    def _initiate_recovery(
        self,
        user_id: str,
        recovery_method: str,
        recovery_destination: Optional[str] = None,
        admin_authorized: bool = False,
    ) -> Dict[str, Any]:
        """Initiate MFA recovery for user.

        The recovery token is a bearer credential that clears the second factor.
        It is delivered out-of-band to the enrolled destination and is NEVER
        returned to the caller: previously the token was both returned in the
        response and never sent anywhere, so anyone who could reach this action
        for a victim's user_id received their recovery credential directly
        (issue #2026).

        The destination is resolved from the user's ENROLLED method record, not
        from anything the caller supplies: recovery is by definition reachable by
        an un-MFA'd principal, so a caller-chosen address would simply mail the
        victim's recovery credential to the attacker.

        The token is also delivered through a dedicated transport rather than
        :meth:`_send_email_code` / :meth:`_send_sms_code`, because those store
        what they send as ``temp_email_code`` / ``temp_sms_code`` -- which would
        make the 24-hour recovery token redeemable as a routine second factor.

        Args:
            user_id: User initiating recovery.
            recovery_method: ``email``, ``sms``, or ``admin``.
            recovery_destination: Ignored for delivery. When supplied it must
                match the enrolled destination, and is rejected otherwise.
            admin_authorized: Whether the resolved ACTOR holds the admin
                capability (issue #2047). Was ``admin_override``, set from the
                caller-supplied boolean of the same name.

        Returns:
            Result describing that a token was issued and delivered. The token
            itself is not included.
        """
        if recovery_method not in ["email", "sms", "admin"]:
            return {
                "success": False,
                "error": f"Unsupported recovery method: {recovery_method}",
            }

        # "admin" bypasses the enrolled-destination checks entirely and always
        # reports delivered, so ungated it minted a recovery_requests entry for
        # any caller-chosen user_id (issue #2026).
        if recovery_method == "admin" and not admin_authorized:
            return {
                "success": False,
                "error": (
                    "Admin recovery requires an actor holding the "
                    f"'{MFA_ADMIN_CAPABILITY}' capability."
                ),
                "authorized": False,
            }

        # Resolve the destination under the lock, then RELEASE it before the
        # network call: delivery previously ran inside _data_lock, so one hung
        # SMTP host wedged every MFA operation in the process.
        with self._data_lock:
            enrolled = (
                self.user_mfa_data.get(user_id, {})
                .get("methods", {})
                .get(recovery_method, {})
                if recovery_method in ("email", "sms")
                else {}
            )

            destination = None
            if recovery_method == "email":
                destination = enrolled.get("email")
            elif recovery_method == "sms":
                destination = enrolled.get("phone")

            if recovery_method in ("email", "sms"):
                if not destination:
                    return {
                        "success": False,
                        "error": (
                            f"No enrolled {recovery_method} destination for this "
                            "user; recovery cannot be delivered."
                        ),
                    }
                # An UNVERIFIED destination is one an unauthenticated `setup`
                # call could have just written, which would redirect the
                # victim's recovery token to an attacker's address.
                if not enrolled.get("verified"):
                    return {
                        "success": False,
                        "error": (
                            f"The enrolled {recovery_method} destination is not "
                            "verified; recovery cannot be delivered to it."
                        ),
                    }

            # A supplied destination is a confirmation value, never a routing
            # instruction. Mismatch is refused rather than honoured. Compared as
            # UTF-8 bytes because compare_digest rejects non-ASCII str.
            if recovery_destination and not secrets.compare_digest(
                str(recovery_destination).encode("utf-8"),
                str(destination or "").encode("utf-8"),
            ):
                return {
                    "success": False,
                    "error": "recovery_destination does not match the enrolled destination",
                }

        recovery_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=24)  # 24 hour expiry

        # Deliver BEFORE recording the request, so a request is never left
        # pending against a token the user cannot have received.
        try:
            delivered = self._deliver_recovery_token(
                recovery_method, destination, recovery_token, user_id
            )
        except MFADeliveryError as e:
            self.log_with_context(
                "ERROR", f"Recovery delivery failed for user {user_id}: {e}"
            )
            return {
                "success": False,
                "recovery_method": recovery_method,
                "error": "Recovery token delivery failed",
            }

        if not delivered:
            return {
                "success": False,
                "recovery_method": recovery_method,
                "error": (
                    f"No {recovery_method} transport is configured; the "
                    "recovery token was not delivered."
                ),
            }

        with self._data_lock:
            if not hasattr(self, "recovery_requests"):
                self.recovery_requests = {}

            self.recovery_requests[user_id] = {
                "recovery_token": recovery_token,
                "recovery_method": recovery_method,
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": expires_at.isoformat(),
                "used": False,
            }

        return {
            "success": True,
            "recovery_method": recovery_method,
            "expires_in": 24 * 60 * 60,  # 24 hours in seconds
            "message": f"Recovery token sent via {recovery_method}",
        }

    def _deliver_recovery_token(
        self,
        recovery_method: str,
        destination: Optional[str],
        recovery_token: str,
        user_id: str,
    ) -> bool:
        """Deliver a recovery token WITHOUT registering it as an MFA code.

        Deliberately does not reuse :meth:`_send_email_code` /
        :meth:`_send_sms_code`: those persist the delivered value as a live
        second-factor challenge, which would let the recovery token be replayed
        against ``action="verify"``.

        Returns:
            True if a transport delivered the token, False if none is configured.

        Raises:
            MFADeliveryError: A transport IS configured but delivery failed.
        """
        body = (
            "Your account recovery token (valid 24 hours): "
            f"{recovery_token}\nIf you did not request this, ignore this message."
        )

        if recovery_method == "admin":
            # Operator-mediated channel; the token is retrieved from
            # recovery_requests by an authorised operator, never echoed here.
            self.log_with_context(
                "WARNING",
                f"Admin MFA recovery issued for user {user_id}; the token must "
                "be retrieved by an authorised operator.",
            )
            return True

        if recovery_method == "email":
            if not (self.email_provider and self.email_provider.get("smtp_host")):
                return False
            self._smtp_send(destination, "Account recovery", body)
            self.log_with_context(
                "INFO", f"Recovery token delivered by email for user {user_id}"
            )
            return True

        if not (self.sms_provider and self.sms_provider.get("service") == "twilio"):
            return False
        self._twilio_send(destination, body)
        self.log_with_context(
            "INFO", f"Recovery token delivered by SMS for user {user_id}"
        )
        return True

    def _disable_all_mfa(self, user_id: str) -> Dict[str, Any]:
        """Disable all MFA for user (admin override)."""
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {
                    "success": True,  # Already disabled
                    "user_id": user_id,
                    "mfa_disabled": True,
                    "disabled_methods": [],
                    "message": "MFA was not enabled for user",
                }

            # Capture which methods were enabled before deletion (issue #803).
            disabled_methods = list(
                self.user_mfa_data[user_id].get("methods", {}).keys()
            )

            # Clear all MFA data for user
            del self.user_mfa_data[user_id]

            # Also clear any pending verifications
            if user_id in self.pending_verifications:
                del self.pending_verifications[user_id]

            # Clear trusted devices
            if user_id in self.trusted_devices:
                del self.trusted_devices[user_id]

            return {
                "success": True,
                "user_id": user_id,
                "mfa_disabled": True,
                "disabled_methods": disabled_methods,
                "message": "All MFA methods disabled for user",
            }

    def _disable_method(self, user_id: str, method: str) -> Dict[str, Any]:
        """Disable specific MFA method for user."""
        with self._data_lock:
            if user_id not in self.user_mfa_data:
                return {
                    "success": False,
                    "user_id": user_id,
                    "error": "MFA not setup for user",
                }

            user_data = self.user_mfa_data[user_id]
            methods = user_data.get("methods", {})

            if method not in methods:
                return {
                    "success": False,
                    "user_id": user_id,
                    "error": f"Method {method} not setup for user",
                }

            # Remove the method
            del methods[method]

            return {
                "success": True,
                "user_id": user_id,
                "method_disabled": method,
                "disabled_methods": [method],
            }
