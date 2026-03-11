"""PII filtering utility (TODO-310F).

Provides methods to redact sensitive information from headers,
bodies, and other data structures before logging.
"""

import re
from typing import Any, Dict, List, Set


class PIIFilter:
    """Filters PII from audit data.

    Redacts sensitive headers, body fields, and common PII patterns
    (email, SSN, credit card numbers) from audit records.
    """

    def __init__(
        self,
        redact_fields: List[str],
        redact_headers: List[str],
        replacement: str = "[REDACTED]",
    ):
        """Initialize PII filter.

        Args:
            redact_fields: Field names to redact (case-insensitive)
            redact_headers: Header names to redact (case-insensitive)
            replacement: Replacement string for redacted values
        """
        self._redact_fields: Set[str] = {f.lower() for f in redact_fields}
        self._redact_headers: Set[str] = {h.lower() for h in redact_headers}
        self._replacement = replacement

        # Common PII patterns
        self._patterns = [
            (
                re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
                "EMAIL",
            ),
            (re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"), "SSN"),
            (
                re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
                "CARD",
            ),
        ]

    def redact_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Redact sensitive headers.

        Args:
            headers: Dictionary of header name -> value

        Returns:
            Headers with sensitive values redacted
        """
        result = {}
        for name, value in headers.items():
            if name.lower() in self._redact_headers:
                result[name] = self._replacement
            else:
                result[name] = value
        return result

    def redact_body(self, body: Any) -> Any:
        """Recursively redact sensitive fields from body.

        Args:
            body: Request/response body (dict, list, or primitive)

        Returns:
            Body with sensitive fields redacted
        """
        if isinstance(body, dict):
            return {
                k: (
                    self._replacement
                    if k.lower() in self._redact_fields
                    else self.redact_body(v)
                )
                for k, v in body.items()
            }
        elif isinstance(body, list):
            return [self.redact_body(item) for item in body]
        elif isinstance(body, str):
            return self._redact_patterns(body)
        else:
            return body

    def _redact_patterns(self, text: str) -> str:
        """Redact common PII patterns from text.

        Args:
            text: Text to scan for PII patterns

        Returns:
            Text with patterns redacted
        """
        result = text
        for pattern, label in self._patterns:
            result = pattern.sub(f"[{label}_REDACTED]", result)
        return result

    def redact_query_params(self, params: Dict[str, str]) -> Dict[str, str]:
        """Redact sensitive query parameters.

        Args:
            params: Dictionary of parameter name -> value

        Returns:
            Parameters with sensitive values redacted
        """
        result = {}
        for name, value in params.items():
            if name.lower() in self._redact_fields:
                result[name] = self._replacement
            else:
                result[name] = value
        return result
