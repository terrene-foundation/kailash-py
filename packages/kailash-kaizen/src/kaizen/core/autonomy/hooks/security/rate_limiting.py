"""
Rate limiting for hook registration (SECURITY FIX #7).

Prevents DoS attacks via hook flooding by limiting registration rate per user/principal.

SECURITY: CWE-770 (Allocation of Resources Without Limits or Throttling)
"""

import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from ..manager import HookManager
from ..protocol import HookHandler
from ..types import HookEvent, HookPriority

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""

    pass


class RateLimitedHookManager(HookManager):
    """
    HookManager with rate limiting to prevent DoS attacks.

    Features:
    - Configurable rate limits (default: 10 registrations/minute)
    - Per-user/principal tracking
    - Automatic timestamp cleanup (sliding window)
    - Audit logging of rate limit violations

    Example:
        >>> from kaizen.core.autonomy.hooks.security import RateLimitedHookManager
        >>> from kaizen.core.autonomy.hooks.types import HookEvent, HookPriority
        >>>
        >>> # Create manager with rate limiting (10/minute default)
        >>> manager = RateLimitedHookManager(max_registrations_per_minute=10)
        >>>
        >>> # Register hooks (tracked per principal_id)
        >>> try:
        >>>     manager.register(
        >>>         HookEvent.POST_AGENT_LOOP,
        >>>         my_hook,
        >>>         priority=HookPriority.NORMAL,
        >>>         principal_id="user123"  # Required for rate limiting
        >>>     )
        >>> except RateLimitError as e:
        >>>     print(f"Rate limit exceeded: {e}")

    SECURITY FIX #7:
    - Prevents attacker from registering thousands of hooks
    - Limits memory exhaustion and performance degradation
    - Tracks violations for security monitoring
    """

    def __init__(
        self,
        max_registrations_per_minute: int = 10,
        enable_audit_logging: bool = True,
    ):
        """
        Initialize rate-limited hook manager.

        Args:
            max_registrations_per_minute: Maximum registrations allowed per minute per user
            enable_audit_logging: Whether to log rate limit violations
        """
        super().__init__()
        self.max_registrations = max_registrations_per_minute
        self.enable_audit_logging = enable_audit_logging

        # Track registration timestamps per principal
        self.registration_timestamps: dict[str, list[float]] = defaultdict(list)

        # Track rate limit violations for security monitoring
        self.violation_count: dict[str, int] = defaultdict(int)

    def register(
        self,
        event_type: HookEvent | str,
        handler: HookHandler | Callable[[Any], Awaitable[Any]],
        priority: HookPriority = HookPriority.NORMAL,
        principal_id: str = "anonymous",
    ) -> None:
        """
        Register a hook handler with rate limiting.

        Args:
            event_type: Event to trigger hook on
            handler: Hook handler (HookHandler or async callable)
            priority: Execution priority (lower = earlier)
            principal_id: User/principal ID for rate limiting (default: "anonymous")

        Raises:
            RateLimitError: If rate limit is exceeded
            ValueError: If event_type is invalid

        Example:
            >>> manager = RateLimitedHookManager(max_registrations_per_minute=5)
            >>> manager.register(HookEvent.POST_AGENT_LOOP, my_hook, principal_id="user123")
        """
        # Check rate limit BEFORE registration
        self._check_rate_limit(principal_id, handler)

        # Record registration timestamp
        self.registration_timestamps[principal_id].append(time.time())

        # Proceed with registration (delegates to HookManager)
        super().register(event_type, handler, priority)

        # Log successful registration for audit trail
        if self.enable_audit_logging:
            handler_name = getattr(handler, "name", repr(handler))
            logger.info(
                f"Rate limit check passed: principal={principal_id}, "
                f"handler={handler_name}, "
                f"current_rate={len(self.registration_timestamps[principal_id])}/{self.max_registrations}"
            )

    def _check_rate_limit(self, principal_id: str, handler: Any) -> None:
        """
        Check if registration is within rate limit.

        Args:
            principal_id: User/principal ID
            handler: Hook handler (for logging)

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        now = time.time()

        # Remove old timestamps (>1 minute ago) - sliding window
        self.registration_timestamps[principal_id] = [
            ts
            for ts in self.registration_timestamps[principal_id]
            if now - ts < 60  # 60 seconds = 1 minute
        ]

        # Check if limit exceeded
        current_count = len(self.registration_timestamps[principal_id])
        if current_count >= self.max_registrations:
            # Track violation
            self.violation_count[principal_id] += 1

            # Audit log CRITICAL violation
            if self.enable_audit_logging:
                handler_name = getattr(handler, "name", repr(handler))
                logger.critical(
                    f"SECURITY: Rate limit exceeded - principal={principal_id}, "
                    f"handler={handler_name}, "
                    f"limit={self.max_registrations}/minute, "
                    f"current={current_count}, "
                    f"total_violations={self.violation_count[principal_id]}"
                )

            raise RateLimitError(
                f"Rate limit exceeded for principal '{principal_id}': "
                f"{self.max_registrations} registrations per minute (current: {current_count})"
            )

    def get_rate_limit_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get rate limit statistics for security monitoring.

        Returns:
            Dictionary mapping principal_id to stats:
            - current_count: Current registrations in sliding window
            - total_violations: Total rate limit violations
            - last_registration: Timestamp of last registration

        Example:
            >>> manager = RateLimitedHookManager()
            >>> stats = manager.get_rate_limit_stats()
            >>> print(stats["user123"])
            {'current_count': 5, 'total_violations': 2, 'last_registration': 1699564800.0}
        """
        now = time.time()
        stats = {}

        for principal_id, timestamps in self.registration_timestamps.items():
            # Filter to current window (last minute)
            current_timestamps = [ts for ts in timestamps if now - ts < 60]

            stats[principal_id] = {
                "current_count": len(current_timestamps),
                "total_violations": self.violation_count[principal_id],
                "last_registration": (
                    max(current_timestamps) if current_timestamps else None
                ),
                "limit": self.max_registrations,
            }

        return stats

    def reset_rate_limits(self, principal_id: str | None = None) -> None:
        """
        Reset rate limit counters (for testing or admin override).

        Args:
            principal_id: Specific principal to reset (None = reset all)

        Example:
            >>> manager = RateLimitedHookManager()
            >>> manager.reset_rate_limits("user123")  # Reset specific user
            >>> manager.reset_rate_limits()  # Reset all users
        """
        if principal_id is None:
            # Reset all
            self.registration_timestamps.clear()
            self.violation_count.clear()
            logger.info("Rate limits reset for all principals")
        else:
            # Reset specific principal
            if principal_id in self.registration_timestamps:
                del self.registration_timestamps[principal_id]
            if principal_id in self.violation_count:
                del self.violation_count[principal_id]
            logger.info(f"Rate limits reset for principal: {principal_id}")


# Alias for backward compatibility with tests
RateLimiter = RateLimitedHookManager


# Export public API
__all__ = [
    "RateLimitedHookManager",
    "RateLimitError",
    "RateLimiter",
]
