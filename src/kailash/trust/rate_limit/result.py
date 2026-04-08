"""Rate limit result dataclass.

Provides RateLimitResult for representing the outcome of a rate limit check,
including standard HTTP response header generation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed
        limit: Maximum requests in the window
        remaining: Requests remaining in current window
        reset_at: When the rate limit window resets
        retry_after_seconds: Seconds to wait before retrying (if not allowed)
        identifier: The identifier that was checked
    """

    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after_seconds: Optional[int] = None
    identifier: Optional[str] = None

    def to_headers(self) -> Dict[str, str]:
        """Generate X-RateLimit-* headers.

        Returns:
            Dictionary of header name -> value
        """
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": self.reset_at.isoformat(),
        }

        if not self.allowed and self.retry_after_seconds:
            headers["Retry-After"] = str(self.retry_after_seconds)

        return headers
