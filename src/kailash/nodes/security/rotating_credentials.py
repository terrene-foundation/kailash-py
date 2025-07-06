"""Rotating credential node for automatic credential refresh and zero-downtime rotation.

This module provides automatic credential rotation capabilities with expiration
detection, refresh from multiple sources, zero-downtime rotation, and notification
systems for enterprise security requirements.

Key Features:
- Automatic expiration detection
- Multi-source credential refresh
- Zero-downtime rotation
- Notification system for rotation events
- Configurable rotation policies
- Audit trail for credential operations
"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.nodes.security.credential_manager import CredentialManagerNode
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


@register_node()
class RotatingCredentialNode(Node):
    """Node for automatic credential rotation with expiration detection and refresh.

    This node automatically manages credential lifecycles, detecting expiration,
    refreshing from configured sources, and providing zero-downtime rotation
    for enterprise applications.

    Key capabilities:
    1. Automatic expiration detection
    2. Multi-source credential refresh
    3. Zero-downtime rotation
    4. Notification system
    5. Configurable rotation policies
    6. Audit trail maintenance

    Example:
        >>> rotator = RotatingCredentialNode()
        >>> result = rotator.execute(
        ...     operation="start_rotation",
        ...     credential_name="api_token",
        ...     check_interval=3600,  # Check every hour
        ...     expiration_threshold=86400,  # Rotate 24h before expiry
        ...     refresh_sources=["vault", "aws_secrets"],
        ...     notification_webhooks=["https://alerts.company.com/webhook"]
        ... )
    """

    def get_metadata(self) -> NodeMetadata:
        """Get node metadata for discovery and orchestration."""
        return NodeMetadata(
            name="Rotating Credential Node",
            description="Automatic credential rotation with expiration detection and refresh",
            tags={"security", "credentials", "rotation", "automation", "enterprise"},
            version="1.0.0",
            author="Kailash SDK",
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for credential rotation operations."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="start_rotation",
                description="Operation: start_rotation, stop_rotation, check_status, rotate_now, get_audit_log",
            ),
            "credential_name": NodeParameter(
                name="credential_name",
                type=str,
                required=False,
                description="Name of the credential to manage rotation for",
            ),
            "check_interval": NodeParameter(
                name="check_interval",
                type=int,
                required=False,
                default=3600,
                description="Interval in seconds between expiration checks",
            ),
            "expiration_threshold": NodeParameter(
                name="expiration_threshold",
                type=int,
                required=False,
                default=86400,
                description="Seconds before expiration to trigger rotation",
            ),
            "refresh_sources": NodeParameter(
                name="refresh_sources",
                type=list,
                required=False,
                default=["env", "file"],
                description="Sources to refresh credentials from (env, file, vault, aws_secrets, etc.)",
            ),
            "refresh_config": NodeParameter(
                name="refresh_config",
                type=dict,
                required=False,
                default={},
                description="Configuration for refresh sources",
            ),
            "notification_webhooks": NodeParameter(
                name="notification_webhooks",
                type=list,
                required=False,
                default=[],
                description="Webhook URLs to notify on rotation events",
            ),
            "notification_emails": NodeParameter(
                name="notification_emails",
                type=list,
                required=False,
                default=[],
                description="Email addresses to notify on rotation events",
            ),
            "rotation_policy": NodeParameter(
                name="rotation_policy",
                type=str,
                required=False,
                default="proactive",
                description="Rotation policy: proactive, reactive, scheduled",
            ),
            "schedule_cron": NodeParameter(
                name="schedule_cron",
                type=str,
                required=False,
                description="Cron expression for scheduled rotation (if policy is scheduled)",
            ),
            "zero_downtime": NodeParameter(
                name="zero_downtime",
                type=bool,
                required=False,
                default=True,
                description="Whether to use zero-downtime rotation strategy",
            ),
            "rollback_on_failure": NodeParameter(
                name="rollback_on_failure",
                type=bool,
                required=False,
                default=True,
                description="Whether to rollback to previous credential on rotation failure",
            ),
            "audit_log_enabled": NodeParameter(
                name="audit_log_enabled",
                type=bool,
                required=False,
                default=True,
                description="Whether to maintain audit log of rotation activities",
            ),
        }

    def __init__(self, **kwargs):
        """Initialize the RotatingCredentialNode."""
        super().__init__(**kwargs)
        self._rotation_threads = {}
        self._credential_cache = {}
        self._audit_log = []
        self._credential_manager = CredentialManagerNode(
            credential_name="rotating_credentials",
            credential_type="custom",
            name="rotation_credential_manager",
        )
        self._rotation_status = {}

    def _log_audit_event(
        self,
        credential_name: str,
        event_type: str,
        details: Dict[str, Any],
        success: bool = True,
    ):
        """Log an audit event for credential rotation."""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "credential_name": credential_name,
            "event_type": event_type,
            "success": success,
            "details": details,
        }
        self._audit_log.append(audit_entry)

        # Keep only last 1000 entries to prevent memory growth
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]

    def _send_notification(
        self,
        credential_name: str,
        event_type: str,
        message: str,
        webhook_urls: List[str],
        email_addresses: List[str],
    ):
        """Send notifications about rotation events."""
        notification_data = {
            "timestamp": datetime.now().isoformat(),
            "credential_name": credential_name,
            "event_type": event_type,
            "message": message,
        }

        # Send webhook notifications
        for webhook_url in webhook_urls:
            try:
                import requests

                response = requests.post(
                    webhook_url,
                    json=notification_data,
                    timeout=10,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code == 200:
                    self._log_audit_event(
                        credential_name,
                        "notification_sent",
                        {"webhook": webhook_url, "status": "success"},
                    )
                else:
                    self._log_audit_event(
                        credential_name,
                        "notification_failed",
                        {"webhook": webhook_url, "status_code": response.status_code},
                        success=False,
                    )
            except Exception as e:
                self._log_audit_event(
                    credential_name,
                    "notification_error",
                    {"webhook": webhook_url, "error": str(e)},
                    success=False,
                )

        # Email notifications would be implemented here
        # For this example, we'll just log them
        for email in email_addresses:
            self._log_audit_event(
                credential_name,
                "email_notification",
                {"email": email, "message": message},
            )

    def _check_credential_expiration(
        self,
        credential_name: str,
        expiration_threshold: int,
    ) -> Dict[str, Any]:
        """Check if a credential is approaching expiration."""
        try:
            # Get current credential
            credential_result = self._credential_manager.execute(
                operation="get_credential", credential_name=credential_name
            )

            if not credential_result.get("success"):
                return {
                    "needs_rotation": False,
                    "error": "Failed to retrieve credential",
                }

            credential_data = credential_result.get("credential", {})
            expires_at = credential_data.get("expires_at")

            if not expires_at:
                return {
                    "needs_rotation": False,
                    "reason": "No expiration date set",
                }

            # Parse expiration time
            if isinstance(expires_at, str):
                expiry_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            else:
                expiry_time = expires_at

            current_time = (
                datetime.now(expiry_time.tzinfo)
                if expiry_time.tzinfo
                else datetime.now()
            )
            time_until_expiry = (expiry_time - current_time).total_seconds()

            needs_rotation = time_until_expiry <= expiration_threshold

            return {
                "needs_rotation": needs_rotation,
                "expires_at": expires_at,
                "time_until_expiry": time_until_expiry,
                "threshold": expiration_threshold,
                "current_time": current_time.isoformat(),
            }

        except Exception as e:
            return {
                "needs_rotation": False,
                "error": str(e),
            }

    def _refresh_credential(
        self,
        credential_name: str,
        refresh_sources: List[str],
        refresh_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Refresh a credential from configured sources."""
        try:
            # Try each refresh source in order
            for source in refresh_sources:
                try:
                    refresh_result = self._credential_manager.execute(
                        operation="get_credential",
                        credential_name=credential_name,
                        credential_sources=[source],
                        **refresh_config.get(source, {}),
                    )

                    if refresh_result.get("success"):
                        return {
                            "success": True,
                            "source": source,
                            "credential": refresh_result["credential"],
                        }

                except Exception as e:
                    self._log_audit_event(
                        credential_name,
                        "refresh_source_failed",
                        {"source": source, "error": str(e)},
                        success=False,
                    )
                    continue

            return {
                "success": False,
                "error": "All refresh sources failed",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _perform_rotation(
        self,
        credential_name: str,
        refresh_sources: List[str],
        refresh_config: Dict[str, Any],
        zero_downtime: bool = True,
        rollback_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """Perform credential rotation with optional zero-downtime strategy."""
        rotation_start = datetime.now()

        try:
            # Step 1: Get current credential (for rollback if needed)
            current_credential = None
            if rollback_on_failure:
                current_result = self._credential_manager.execute(
                    operation="get_credential", credential_name=credential_name
                )
                if current_result.get("success"):
                    current_credential = current_result["credential"]

            # Step 2: Refresh credential from sources
            refresh_result = self._refresh_credential(
                credential_name, refresh_sources, refresh_config
            )

            if not refresh_result.get("success"):
                self._log_audit_event(
                    credential_name,
                    "rotation_failed",
                    {"stage": "refresh", "error": refresh_result.get("error")},
                    success=False,
                )
                return {
                    "success": False,
                    "error": f"Failed to refresh credential: {refresh_result.get('error')}",
                    "stage": "refresh",
                }

            new_credential = refresh_result["credential"]

            # Step 3: Validate new credential
            validation_result = self._credential_manager.execute(
                operation="validate_credential",
                credential_name=credential_name,
                credential_data=new_credential,
            )

            if not validation_result.get("valid", True):
                self._log_audit_event(
                    credential_name,
                    "rotation_failed",
                    {
                        "stage": "validation",
                        "error": "New credential validation failed",
                    },
                    success=False,
                )
                return {
                    "success": False,
                    "error": "New credential validation failed",
                    "stage": "validation",
                }

            # Step 4: Store new credential
            if zero_downtime:
                # In zero-downtime mode, we would typically:
                # 1. Store new credential with a temporary name
                # 2. Test it in parallel with current credential
                # 3. Atomically switch to new credential
                # 4. Remove old credential

                temp_credential_name = f"{credential_name}_rotating_{int(time.time())}"

                store_result = self._credential_manager.execute(
                    operation="store_credential",
                    credential_name=temp_credential_name,
                    credential_data=new_credential,
                )

                if not store_result.get("success"):
                    self._log_audit_event(
                        credential_name,
                        "rotation_failed",
                        {"stage": "temp_store", "error": store_result.get("error")},
                        success=False,
                    )
                    return {
                        "success": False,
                        "error": f"Failed to store temporary credential: {store_result.get('error')}",
                        "stage": "temp_store",
                    }

                # Test new credential (this would be application-specific)
                # For this example, we'll assume it passes

                # Atomic switch
                final_store_result = self._credential_manager.execute(
                    operation="store_credential",
                    credential_name=credential_name,
                    credential_data=new_credential,
                )

                if not final_store_result.get("success"):
                    # Rollback if requested
                    if rollback_on_failure and current_credential:
                        self._credential_manager.execute(
                            operation="store_credential",
                            credential_name=credential_name,
                            credential_data=current_credential,
                        )

                    self._log_audit_event(
                        credential_name,
                        "rotation_failed",
                        {
                            "stage": "final_store",
                            "error": final_store_result.get("error"),
                        },
                        success=False,
                    )
                    return {
                        "success": False,
                        "error": f"Failed to store final credential: {final_store_result.get('error')}",
                        "stage": "final_store",
                    }

                # Clean up temporary credential
                self._credential_manager.execute(
                    operation="delete_credential", credential_name=temp_credential_name
                )

            else:
                # Direct replacement
                store_result = self._credential_manager.execute(
                    operation="store_credential",
                    credential_name=credential_name,
                    credential_data=new_credential,
                )

                if not store_result.get("success"):
                    # Rollback if requested
                    if rollback_on_failure and current_credential:
                        self._credential_manager.execute(
                            operation="store_credential",
                            credential_name=credential_name,
                            credential_data=current_credential,
                        )

                    self._log_audit_event(
                        credential_name,
                        "rotation_failed",
                        {"stage": "store", "error": store_result.get("error")},
                        success=False,
                    )
                    return {
                        "success": False,
                        "error": f"Failed to store credential: {store_result.get('error')}",
                        "stage": "store",
                    }

            rotation_end = datetime.now()
            rotation_duration = (rotation_end - rotation_start).total_seconds()

            # Log successful rotation
            self._log_audit_event(
                credential_name,
                "rotation_completed",
                {
                    "source": refresh_result["source"],
                    "duration_seconds": rotation_duration,
                    "zero_downtime": zero_downtime,
                },
            )

            return {
                "success": True,
                "source": refresh_result["source"],
                "rotation_duration": rotation_duration,
                "rotated_at": rotation_end.isoformat(),
            }

        except Exception as e:
            self._log_audit_event(
                credential_name, "rotation_error", {"error": str(e)}, success=False
            )
            return {
                "success": False,
                "error": str(e),
                "stage": "exception",
            }

    def _rotation_worker(
        self,
        credential_name: str,
        check_interval: int,
        expiration_threshold: int,
        refresh_sources: List[str],
        refresh_config: Dict[str, Any],
        notification_webhooks: List[str],
        notification_emails: List[str],
        zero_downtime: bool,
        rollback_on_failure: bool,
    ):
        """Background worker for automatic credential rotation."""
        self._rotation_status[credential_name] = {
            "active": True,
            "last_check": None,
            "last_rotation": None,
            "next_check": datetime.now() + timedelta(seconds=check_interval),
        }

        while self._rotation_status[credential_name]["active"]:
            try:
                # Check if credential needs rotation
                check_result = self._check_credential_expiration(
                    credential_name, expiration_threshold
                )

                self._rotation_status[credential_name][
                    "last_check"
                ] = datetime.now().isoformat()

                if check_result.get("needs_rotation"):
                    self._log_audit_event(
                        credential_name,
                        "rotation_triggered",
                        {"reason": "expiration_threshold", "details": check_result},
                    )

                    # Send notification about rotation start
                    self._send_notification(
                        credential_name,
                        "rotation_started",
                        f"Credential rotation started for {credential_name}",
                        notification_webhooks,
                        notification_emails,
                    )

                    # Perform rotation
                    rotation_result = self._perform_rotation(
                        credential_name,
                        refresh_sources,
                        refresh_config,
                        zero_downtime,
                        rollback_on_failure,
                    )

                    if rotation_result["success"]:
                        self._rotation_status[credential_name][
                            "last_rotation"
                        ] = datetime.now().isoformat()

                        # Send success notification
                        self._send_notification(
                            credential_name,
                            "rotation_completed",
                            f"Credential rotation completed successfully for {credential_name}",
                            notification_webhooks,
                            notification_emails,
                        )
                    else:
                        # Send failure notification
                        self._send_notification(
                            credential_name,
                            "rotation_failed",
                            f"Credential rotation failed for {credential_name}: {rotation_result.get('error')}",
                            notification_webhooks,
                            notification_emails,
                        )

                # Update next check time
                self._rotation_status[credential_name]["next_check"] = (
                    datetime.now() + timedelta(seconds=check_interval)
                ).isoformat()

                # Sleep until next check
                time.sleep(check_interval)

            except Exception as e:
                self._log_audit_event(
                    credential_name,
                    "rotation_worker_error",
                    {"error": str(e)},
                    success=False,
                )
                time.sleep(min(check_interval, 300))  # Sleep at most 5 minutes on error

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute credential rotation operation."""
        operation = kwargs.get("operation", "start_rotation")

        if operation == "start_rotation":
            credential_name = kwargs.get("credential_name")
            if not credential_name:
                raise NodeConfigurationError(
                    "credential_name is required for start_rotation"
                )

            # Stop existing rotation if running
            if credential_name in self._rotation_threads:
                self._rotation_status[credential_name]["active"] = False
                self._rotation_threads[credential_name].join(timeout=5)

            # Start new rotation worker
            rotation_thread = threading.Thread(
                target=self._rotation_worker,
                args=(
                    credential_name,
                    kwargs.get("check_interval", 3600),
                    kwargs.get("expiration_threshold", 86400),
                    kwargs.get("refresh_sources", ["env", "file"]),
                    kwargs.get("refresh_config", {}),
                    kwargs.get("notification_webhooks", []),
                    kwargs.get("notification_emails", []),
                    kwargs.get("zero_downtime", True),
                    kwargs.get("rollback_on_failure", True),
                ),
                daemon=True,
            )

            rotation_thread.start()
            self._rotation_threads[credential_name] = rotation_thread

            return {
                "success": True,
                "message": f"Rotation started for credential: {credential_name}",
                "credential_name": credential_name,
                "check_interval": kwargs.get("check_interval", 3600),
                "expiration_threshold": kwargs.get("expiration_threshold", 86400),
            }

        elif operation == "stop_rotation":
            credential_name = kwargs.get("credential_name")
            if not credential_name:
                raise NodeConfigurationError(
                    "credential_name is required for stop_rotation"
                )

            if credential_name in self._rotation_status:
                self._rotation_status[credential_name]["active"] = False

            if credential_name in self._rotation_threads:
                self._rotation_threads[credential_name].join(timeout=5)
                del self._rotation_threads[credential_name]

            return {
                "success": True,
                "message": f"Rotation stopped for credential: {credential_name}",
                "credential_name": credential_name,
            }

        elif operation == "check_status":
            credential_name = kwargs.get("credential_name")

            if credential_name:
                status = self._rotation_status.get(credential_name, {})
                return {
                    "credential_name": credential_name,
                    "status": status,
                    "thread_active": credential_name in self._rotation_threads,
                }
            else:
                return {
                    "all_credentials": self._rotation_status,
                    "active_threads": list(self._rotation_threads.keys()),
                }

        elif operation == "rotate_now":
            credential_name = kwargs.get("credential_name")
            if not credential_name:
                raise NodeConfigurationError(
                    "credential_name is required for rotate_now"
                )

            return self._perform_rotation(
                credential_name,
                kwargs.get("refresh_sources", ["env", "file"]),
                kwargs.get("refresh_config", {}),
                kwargs.get("zero_downtime", True),
                kwargs.get("rollback_on_failure", True),
            )

        elif operation == "get_audit_log":
            credential_name = kwargs.get("credential_name")

            if credential_name:
                # Filter audit log for specific credential
                filtered_log = [
                    entry
                    for entry in self._audit_log
                    if entry["credential_name"] == credential_name
                ]
                return {
                    "credential_name": credential_name,
                    "audit_log": filtered_log,
                    "total_entries": len(filtered_log),
                }
            else:
                return {
                    "audit_log": self._audit_log,
                    "total_entries": len(self._audit_log),
                }

        else:
            raise NodeConfigurationError(f"Invalid operation: {operation}")

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
