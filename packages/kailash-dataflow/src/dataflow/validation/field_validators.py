# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Common field-level validator functions.

All validators use stdlib only (``re``, ``uuid``, ``ipaddress``). No
external dependencies. Each validator either returns ``True`` / ``False``
or is a factory that returns a validator callable.

Thread-safe: validators are pure functions with no shared mutable state.
"""

from __future__ import annotations

import logging
import re
import uuid as _uuid_mod
from typing import Callable, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "email_validator",
    "url_validator",
    "uuid_validator",
    "length_validator",
    "range_validator",
    "pattern_validator",
    "phone_validator",
]

# ---------------------------------------------------------------------------
# Internal compiled patterns
# ---------------------------------------------------------------------------

# RFC 5322 simplified — intentionally permissive to avoid false negatives.
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# URL — requires scheme (http / https / ftp).
_URL_RE = re.compile(
    r"^https?://"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}"
    r"(?::\d{1,5})?"
    r"(?:/[^\s]*)?$"
)

# E.164 international phone — optional leading ``+``, then 7-15 digits.
# Allows spaces, dashes, dots, and parentheses as separators.
_PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")


# ---------------------------------------------------------------------------
# Simple validators (value -> bool)
# ---------------------------------------------------------------------------


def email_validator(value: object) -> bool:
    """Return ``True`` if *value* looks like a valid email address.

    Uses a simplified RFC 5322 pattern. Does not perform DNS or
    mailbox verification.
    """
    if not isinstance(value, str):
        return False
    return _EMAIL_RE.match(value) is not None


def url_validator(value: object) -> bool:
    """Return ``True`` if *value* is a well-formed HTTP(S) URL."""
    if not isinstance(value, str):
        return False
    return _URL_RE.match(value) is not None


def uuid_validator(value: object) -> bool:
    """Return ``True`` if *value* is a valid UUID (any version)."""
    if isinstance(value, _uuid_mod.UUID):
        return True
    if not isinstance(value, str):
        return False
    try:
        _uuid_mod.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def phone_validator(value: object) -> bool:
    """Return ``True`` if *value* matches a plausible phone number format.

    Accepts E.164 and common formatted variants (spaces, dashes, dots,
    parentheses). Does not verify the number actually exists.
    """
    if not isinstance(value, str):
        return False
    # Strip formatting characters to count actual digits.
    digits = re.sub(r"[^\d]", "", value)
    if len(digits) < 7 or len(digits) > 15:
        return False
    return _PHONE_RE.match(value) is not None


# ---------------------------------------------------------------------------
# Factory validators (return a Callable[[value], bool])
# ---------------------------------------------------------------------------


def length_validator(
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
) -> Callable[[object], bool]:
    """Return a validator that checks string / sequence length bounds.

    Args:
        min_len: Minimum acceptable length (inclusive). ``None`` = no lower bound.
        max_len: Maximum acceptable length (inclusive). ``None`` = no upper bound.

    Returns:
        A callable ``(value) -> bool``.
    """
    if min_len is not None and max_len is not None and min_len > max_len:
        raise ValueError(
            f"min_len ({min_len}) must not exceed max_len ({max_len})"
        )

    def _check(value: object) -> bool:
        if not hasattr(value, "__len__"):
            return False
        length = len(value)  # type: ignore[arg-type]
        if min_len is not None and length < min_len:
            return False
        if max_len is not None and length > max_len:
            return False
        return True

    _check.__qualname__ = f"length_validator(min_len={min_len}, max_len={max_len})"
    return _check


def range_validator(
    min_val: Optional[Union[int, float]] = None,
    max_val: Optional[Union[int, float]] = None,
) -> Callable[[object], bool]:
    """Return a validator that checks numeric value bounds.

    Args:
        min_val: Minimum acceptable value (inclusive). ``None`` = no lower bound.
        max_val: Maximum acceptable value (inclusive). ``None`` = no upper bound.

    Returns:
        A callable ``(value) -> bool``.
    """
    import math

    if min_val is not None and not math.isfinite(min_val):
        raise ValueError(f"min_val must be finite, got {min_val}")
    if max_val is not None and not math.isfinite(max_val):
        raise ValueError(f"max_val must be finite, got {max_val}")
    if (
        min_val is not None
        and max_val is not None
        and min_val > max_val
    ):
        raise ValueError(
            f"min_val ({min_val}) must not exceed max_val ({max_val})"
        )

    def _check(value: object) -> bool:
        if not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value):
            return False
        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False
        return True

    _check.__qualname__ = f"range_validator(min_val={min_val}, max_val={max_val})"
    return _check


def pattern_validator(regex: str) -> Callable[[object], bool]:
    """Return a validator that checks string values against a regex.

    The pattern is compiled once and reused for every call. The match
    is full-string (uses ``re.fullmatch``).

    Args:
        regex: Regular expression pattern. Must be a valid ``re`` pattern.

    Returns:
        A callable ``(value) -> bool``.

    Raises:
        re.error: If *regex* is not a valid regular expression.
    """
    compiled = re.compile(regex)

    def _check(value: object) -> bool:
        if not isinstance(value, str):
            return False
        return compiled.fullmatch(value) is not None

    _check.__qualname__ = f"pattern_validator({regex!r})"
    return _check
