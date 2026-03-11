"""DataFlow Security Multi-Factor Authentication Node - SDK Compliant Implementation."""

import asyncio
import datetime
from typing import Any, Dict, Optional

from kailash.nodes.auth.mfa import MultiFactorAuthNode as SDKMultiFactorAuthNode
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class DataFlowMFANode(AsyncNode):
    """Node for multi-factor authentication in DataFlow operations.

    This node extends AsyncNode and leverages the SDK's MultiFactorAuthNode
    to provide enterprise-grade MFA following SDK patterns.

    Configuration Parameters (set during initialization):
        mfa_type: Type of MFA (totp, sms, email, push)
        timeout_seconds: Timeout for MFA verification
        max_attempts: Maximum verification attempts
        enable_backup_codes: Enable backup code support
        require_strong_factors: Require strong authentication factors

    Runtime Parameters (provided during execution):
        user_id: User ID to authenticate
        auth_code: Authentication code provided by user
        factor_type: Type of factor being verified
        session_id: Session ID for tracking
        device_id: Device ID for device-based authentication
    """

    def __init__(self, **kwargs):
        """Initialize the DataFlowMFANode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.mfa_type = kwargs.pop("mfa_type", "totp")
        self.timeout_seconds = kwargs.pop("timeout_seconds", 300)
        self.max_attempts = kwargs.pop("max_attempts", 3)
        self.enable_backup_codes = kwargs.pop("enable_backup_codes", True)
        self.require_strong_factors = kwargs.pop("require_strong_factors", False)

        # Call parent constructor
        super().__init__(**kwargs)

        # Initialize the SDK MultiFactorAuthNode
        self.mfa_node = SDKMultiFactorAuthNode(
            name=f"{getattr(self, 'node_id', 'unknown')}_sdk_mfa",
            methods=[self.mfa_type] if hasattr(self, "mfa_type") else ["totp"],
            session_timeout=datetime.timedelta(
                seconds=getattr(self, "timeout_seconds", 900)
            ),
            rate_limit_attempts=getattr(self, "max_attempts", 5),
        )

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=True,
                description="User ID to authenticate",
            ),
            "auth_code": NodeParameter(
                name="auth_code",
                type=str,
                required=False,
                description="Authentication code provided by user",
                auto_map_from=["code", "otp", "verification_code", "mfa_token"],
            ),
            "factor_type": NodeParameter(
                name="factor_type",
                type=str,
                required=False,
                default=None,
                description="Type of factor being verified (overrides config)",
            ),
            "session_id": NodeParameter(
                name="session_id",
                type=str,
                required=False,
                description="Session ID for tracking authentication flow",
            ),
            "device_id": NodeParameter(
                name="device_id",
                type=str,
                required=False,
                description="Device ID for device-based authentication",
            ),
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="verify",
                description="MFA action: setup, verify, disable",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute MFA operation asynchronously."""
        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            user_id = validated_inputs.get("user_id")
            auth_code = validated_inputs.get("auth_code")
            factor_type = validated_inputs.get("factor_type") or self.mfa_type
            session_id = validated_inputs.get("session_id")
            device_id = validated_inputs.get("device_id")
            action = validated_inputs.get("action", "verify")

            # Execute MFA operation based on action
            if action == "setup":
                mfa_result = await self._setup_mfa(user_id, factor_type, device_id)
            elif action in [
                "verify",
                "login",
                "sensitive_operation",
                "account_recovery",
            ]:
                # All these actions require verification of auth code
                if not auth_code:
                    raise NodeValidationError("auth_code is required for verification")
                mfa_result = await self._verify_mfa(
                    user_id, auth_code, factor_type, session_id
                )
            elif action == "disable":
                mfa_result = await self._disable_mfa(user_id, factor_type)
            else:
                raise NodeValidationError(f"Invalid action: {action}")

            # Build result following SDK patterns
            authenticated = mfa_result.get("verified", False)

            # Use the reason from the MFA result if provided, otherwise use default
            if "reason" in mfa_result:
                reason = mfa_result["reason"]
            else:
                reason = (
                    "Authentication completed"
                    if authenticated
                    else "Authentication failed"
                )

            result = {
                "success": True,
                "authenticated": authenticated,
                "mfa_verified": authenticated,  # Compatibility alias for tests
                "verification_method": mfa_result.get(
                    "method", factor_type
                ),  # Compatibility for tests
                "reason": reason,  # Use reason from MFA result
                "user_id": user_id,
                "action": action,
                "factor_type": factor_type,
                "metadata": {
                    "mfa_type": factor_type,
                    "attempts_remaining": mfa_result.get("attempts_remaining"),
                    "backup_codes_available": mfa_result.get(
                        "backup_codes_available", 0
                    ),
                    "backup_codes_remaining": mfa_result.get("backup_codes_remaining"),
                    "strong_factor": self._is_strong_factor(factor_type),
                },
            }

            # Add setup-specific data
            if action == "setup" and "setup_data" in mfa_result:
                result["setup_data"] = mfa_result["setup_data"]
                if "qr_code" in mfa_result:
                    result["qr_code"] = mfa_result["qr_code"]
                if "backup_codes" in mfa_result:
                    result["backup_codes"] = mfa_result["backup_codes"]

            # Add session tracking
            if session_id:
                result["session_id"] = session_id
                result["session_valid"] = mfa_result.get("session_valid", True)

            return result

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            return {"success": False, "error": str(e), "authenticated": False}

    async def _setup_mfa(
        self, user_id: str, factor_type: str, device_id: Optional[str]
    ) -> Dict[str, Any]:
        """Setup MFA for a user."""
        try:
            # Use SDK MultiFactorAuthNode to setup MFA
            setup_result = self.mfa_node.execute(
                action="setup",
                user_id=user_id,
                factor_type=factor_type,
                device_id=device_id,
            )

            # Generate backup codes if enabled
            if self.enable_backup_codes:
                backup_codes = self._generate_backup_codes()
                setup_result["backup_codes"] = backup_codes
                setup_result["backup_codes_available"] = len(backup_codes)

            return setup_result

        except Exception as e:
            raise NodeExecutionError(f"MFA setup error: {str(e)}")

    async def _verify_mfa(
        self, user_id: str, auth_code: str, factor_type: str, session_id: Optional[str]
    ) -> Dict[str, Any]:
        """Verify MFA code."""
        try:
            # Use SDK MultiFactorAuthNode to verify
            verify_result = self.mfa_node.execute(
                action="verify",
                user_id=user_id,
                code=auth_code,
                factor_type=factor_type,
                session_id=session_id,
            )

            # Check if strong factor is required
            if self.require_strong_factors and not self._is_strong_factor(factor_type):
                verify_result["verified"] = False
                verify_result["reason"] = "Strong authentication factor required"

            return verify_result

        except Exception as e:
            raise NodeExecutionError(f"MFA verification error: {str(e)}")

    async def _disable_mfa(self, user_id: str, factor_type: str) -> Dict[str, Any]:
        """Disable MFA for a user."""
        try:
            # Use SDK MultiFactorAuthNode to disable
            disable_result = self.mfa_node.execute(
                action="disable", user_id=user_id, factor_type=factor_type
            )

            return disable_result

        except Exception as e:
            raise NodeExecutionError(f"MFA disable error: {str(e)}")

    def _is_strong_factor(self, factor_type: str) -> bool:
        """Determine if a factor type is considered strong."""
        strong_factors = ["totp", "push", "hardware_key", "biometric"]
        return factor_type in strong_factors

    def _generate_backup_codes(self, count: int = 10) -> list[str]:
        """Generate backup codes for MFA."""
        import secrets
        import string

        codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric codes
            code = "".join(
                secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
            )
            codes.append(f"{code[:4]}-{code[4:]}")  # Format as XXXX-XXXX

        return codes
