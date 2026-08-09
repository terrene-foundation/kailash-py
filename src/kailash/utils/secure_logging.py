"""Secure logging utilities for masking sensitive data.

This module provides mixins and utilities for automatically detecting and
masking PII, credentials, and other sensitive information in logs.

It also provides two helpers that make a log line safe BY CONSTRUCTION rather
than by pattern-matching -- :func:`safe_callable_name` and
:func:`safe_exception_frames`. Prefer those wherever the object being logged is
CALLER-SUPPLIED: the masking below is best-effort over an open-ended payload,
while those two emit only source-level identifiers that cannot carry a payload
at all.
"""

import functools
import json
import logging
import os
import re
import traceback
from functools import wraps
from typing import Any, Dict, List, Optional, Pattern, Set, Union

from kailash.utils.url_credentials import is_sensitive_query_key

# A partial wrapping a partial is flattened by CPython, so one unwrap is the
# normal case; the bound keeps a hand-built chain from spinning.
_MAX_PARTIAL_UNWRAP = 10

# Frames kept per exception in safe_exception_frames. Deep recursive failures
# produce thousands of identical frames; the innermost ones locate the fault.
_DEFAULT_FRAME_LIMIT = 20


def safe_callable_name(obj: Any) -> str:
    """Name a CALLER-SUPPLIED callable for a log line without rendering its repr.

    The idiom this replaces is ``getattr(fn, "__name__", repr(fn))``. Python
    evaluates a ``getattr`` default eagerly but only USES it when the attribute
    is absent -- and the callables that lack ``__name__`` are exactly the ones
    that carry payloads:

    * ``functools.partial(connect, dsn="postgres://svc:<credential>@host/db")``
      renders its bound arguments verbatim.
    * a callable object with a dataclass-generated ``__repr__`` renders EVERY
      field, including a credential one, without the call or the exception
      mentioning it.

    A plain ``def`` function has ``__name__``, so the fallback never fires for
    one -- which is why the idiom reads as safe and is not.

    Resolution order:

    1. ``__qualname__`` / ``__name__`` when present -- unchanged behaviour for
       every plain function and method.
    2. For a ``functools.partial``, the WRAPPED function's own name, rendered
       ``partial(<name>)``. ``type(obj).__name__`` alone would be ``"partial"``
       for every partial ever passed, which on a dependency-injection surface
       is not a diagnostic at all -- it cannot tell the database dependency
       from the cache one. ``partial.func`` is the wrapped function; the
       payload lives in ``partial.args`` / ``partial.keywords``, which are
       never read here.
    3. Otherwise ``type(obj).__name__`` -- a class name, which is a
       source-level identifier and cannot carry a caller payload.

    Returns a string for every object that misbehaves; it does not raise on
    account of the object, because a logging call site must not fail on the
    thing it is trying to describe.

    THE ATTRIBUTE READS BELOW CAN RAISE, WHICH IS WHY THEY ARE GUARDED.
    ``getattr(x, attr, default)`` swallows ONLY ``AttributeError`` -- anything
    else the descriptor raises propagates -- and ``isinstance`` consults
    ``__class__``, which is equally caller-controlled. A lazy proxy is the
    ordinary case, not an exotic one: a Werkzeug/Flask ``LocalProxy`` raises
    ``RuntimeError("Working outside of request context")``, a Django
    ``SimpleLazyObject`` raises whatever its setup function raises, and an
    unbound client raises ``ConnectionError``. Unguarded, that escapes into
    callers which invoke this INSIDE an ``except`` block (``runtime/scheduler``,
    ``runtime/distributed``, the nexus resolver), where it would REPLACE the
    exception being handled -- turning a logging helper into a defect that
    destroys the diagnostic it exists to produce -- and into
    ``utils/lifespan``, which calls it BEFORE its ``try`` and documents that one
    handler raising must not prevent the next from running.

    ``Exception``, deliberately NOT ``BaseException``: ``KeyboardInterrupt``,
    ``SystemExit`` and ``CancelledError`` are the program being stopped, not the
    object misbehaving, and swallowing a cancellation here would re-open at the
    logging layer exactly the defect the channel-lifecycle work closed at the
    channel layer.
    """
    target = obj
    unwrapped = 0
    try:
        while True:
            for attribute in ("__qualname__", "__name__"):
                name = getattr(target, attribute, None)
                # A non-str __name__ is possible on an exotic object; only a real
                # string is usable, and only a non-empty one is a diagnostic.
                if isinstance(name, str) and name:
                    return f"partial({name})" if unwrapped else name
            if (
                isinstance(target, functools.partial)
                and unwrapped < _MAX_PARTIAL_UNWRAP
            ):
                target = target.func
                unwrapped += 1
                continue
            type_name = type(target).__name__
            return f"partial({type_name})" if unwrapped else type_name
    except Exception:
        # Fall back to the ONE read that cannot be intercepted by the object:
        # its type's name. Reached only when the object actively resisted
        # description, so the lost precision is the object's own doing.
        try:
            return type(obj).__name__
        except Exception:
            return "<unrepresentable>"


def _relative_frame_path(filename: str) -> str:
    """Render a traceback filename workspace-relative.

    Absolute paths disclose the operator's home-directory layout to whatever
    ships the logs. Falls back to the basename when the file lives outside the
    working directory (or on another Windows drive) rather than emitting a
    ``../../..`` chain that hints at the same layout.
    """
    try:
        relative = os.path.relpath(filename, os.getcwd())
    except (ValueError, OSError):
        return os.path.basename(filename)
    if relative.startswith(".."):
        return os.path.basename(filename)
    return relative


def safe_exception_frames(
    exc: BaseException,
    *,
    limit: int = _DEFAULT_FRAME_LIMIT,
    follow_chain: bool = True,
) -> str:
    """Render WHERE an exception failed, without rendering WHAT it said.

    This is the replacement for ``exc_info=True`` on a log line whose exception
    is CALLER-SUPPLIED. ``logging`` renders ``exc_info`` by walking the whole
    exception chain and printing each exception's ``str()``, so a driver error
    reading ``could not connect to postgres://svc:<credential>@host/db`` lands
    in the record verbatim -- re-entering through the traceback even when the
    log message itself was built to carry nothing.

    Dropping the traceback outright would close that leak but destroy the
    diagnostic: the operator loses the only record of where the failure came
    from. This keeps the frames -- ``path:line:function`` per frame, plus each
    exception's TYPE -- and drops only the message. Every retained element is a
    source-level identifier (a file path, a line number, a function name, a
    class name), none of which can carry a runtime payload. Source text is NOT
    included, so a frame cannot echo an interpolated value either.

    Args:
        exc: The exception to describe.
        limit: Innermost frames kept per exception in the chain.
        follow_chain: Also describe ``__cause__`` / ``__context__``. The cause
            usually holds the real failure site, so this defaults on.

    Returns a string like
    ``RuntimeError@svc/db.py:31:connect <- ValueError@svc/dsn.py:12:parse``.
    """
    descriptions: List[str] = []
    seen: Set[int] = set()
    current: Optional[BaseException] = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        frames = traceback.extract_tb(current.__traceback__)
        if limit > 0:
            frames = frames[-limit:]
        rendered_frames = ">".join(
            f"{_relative_frame_path(frame.filename)}:{frame.lineno}:{frame.name}"
            for frame in frames
        )
        descriptions.append(
            f"{type(current).__name__}@{rendered_frames or '<no-frames>'}"
        )
        if not follow_chain:
            break
        current = current.__cause__ or current.__context__

    return " <- ".join(descriptions)


class SecureLoggingPatterns:
    """Patterns for detecting sensitive data."""

    # Credit card patterns
    CREDIT_CARD = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

    # SSN patterns
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

    # Email pattern
    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    # Phone patterns
    PHONE = re.compile(
        r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b"
    )

    # API key patterns
    API_KEY_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{48}"),  # OpenAI
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub
        re.compile(r"[a-zA-Z0-9]{32}"),  # Generic 32-char
    ]

    # Password in various formats
    PASSWORD_PATTERNS = [
        re.compile(r'["\']?password["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?pwd["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?pass["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
    ]

    # Token patterns
    TOKEN_PATTERNS = [
        re.compile(r'["\']?token["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?api_key["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?secret["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
    ]

    # Common PII field names.
    #
    # Credential query-key names (password / pwd / passwd / token /
    # api_key / apikey / secret / access_token / client_secret /
    # private_key / ...) are NOT listed here — they are owned by the SINGLE
    # canonical set ``kailash.utils.url_credentials._SENSITIVE_QUERY_KEYS``
    # and matched via ``is_sensitive_query_key`` in
    # :meth:`SecureLogger._mask_dict`, so there is no local copy to drift.
    # This set holds only the broader PII field names (SSN, email,
    # address, ...) plus ``pass`` (ambiguous; outside the URL-query set).
    PII_FIELD_NAMES = {
        "ssn",
        "social_security",
        "social_security_number",
        "credit_card",
        "card_number",
        "cc_number",
        "pass",
        "email",
        "email_address",
        "phone",
        "phone_number",
        "address",
        "street_address",
        "home_address",
        "date_of_birth",
        "dob",
        "birthdate",
        "driver_license",
        "license_number",
        "passport",
        "passport_number",
        "bank_account",
        "account_number",
        "routing_number",
    }


class SecureLogger:
    """Logger that automatically masks sensitive data."""

    def __init__(
        self,
        name: str,
        mask_char: str = "*",
        mask_length: int = 8,
        custom_patterns: Optional[List[Pattern]] = None,
        custom_fields: Optional[Set[str]] = None,
    ):
        """
        Initialize secure logger.

        Args:
            name: Logger name
            mask_char: Character to use for masking
            mask_length: Fixed length for masks (0 = preserve length)
            custom_patterns: Additional regex patterns to mask
            custom_fields: Additional field names to mask
        """
        self.logger = logging.getLogger(name)
        self.mask_char = mask_char
        self.mask_length = mask_length
        self.custom_patterns = custom_patterns or []
        self.custom_fields = custom_fields or set()

    def _mask_value(self, value: str, preserve_partial: bool = True) -> str:
        """Mask a sensitive value."""
        if not value:
            return value

        if self.mask_length > 0:
            # Fixed length mask
            return self.mask_char * self.mask_length
        elif preserve_partial and len(value) > 8:
            # Preserve first 2 and last 2 chars
            return value[:2] + self.mask_char * (len(value) - 4) + value[-2:]
        else:
            # Full mask
            return self.mask_char * len(value)

    def _mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively mask sensitive fields in dictionary."""
        masked = {}

        for key, value in data.items():
            # Check if field name indicates sensitive data. Credential
            # query-key names route through the single canonical helper
            # (normalized match: ``access_token``/``client_secret``/... all
            # covered); PII field names + custom fields use exact match.
            if (
                key.lower() in SecureLoggingPatterns.PII_FIELD_NAMES
                or key.lower() in self.custom_fields
                or is_sensitive_query_key(key)
            ):
                masked[key] = (
                    self._mask_value(str(value)) if value is not None else None
                )
            elif isinstance(value, dict):
                masked[key] = self._mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    self._mask_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def _mask_string(self, text: str) -> str:
        """Mask sensitive patterns in string."""
        # Credit cards
        text = SecureLoggingPatterns.CREDIT_CARD.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=True), text
        )

        # SSNs
        text = SecureLoggingPatterns.SSN.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=False), text
        )

        # Emails - preserve domain
        text = SecureLoggingPatterns.EMAIL.sub(
            lambda m: self._mask_email(m.group()), text
        )

        # Phone numbers
        text = SecureLoggingPatterns.PHONE.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=True), text
        )

        # API keys
        for pattern in SecureLoggingPatterns.API_KEY_PATTERNS:
            text = pattern.sub(lambda m: self._mask_value(m.group()), text)

        # Passwords and tokens
        for pattern in (
            SecureLoggingPatterns.PASSWORD_PATTERNS
            + SecureLoggingPatterns.TOKEN_PATTERNS
        ):
            text = pattern.sub(
                lambda m: m.group().replace(m.group(1), self._mask_value(m.group(1))),
                text,
            )

        # Custom patterns
        for pattern in self.custom_patterns:
            text = pattern.sub(lambda m: self._mask_value(m.group()), text)

        return text

    def _mask_email(self, email: str) -> str:
        """Mask email preserving domain."""
        if "@" in email:
            local, domain = email.split("@", 1)
            return self._mask_value(local, preserve_partial=True) + "@" + domain
        return self._mask_value(email)

    def _mask_data(self, data: Any) -> Any:
        """Mask sensitive data in any format."""
        if isinstance(data, str):
            return self._mask_string(data)
        elif isinstance(data, dict):
            return self._mask_dict(data)
        elif isinstance(data, (list, tuple)):
            return [self._mask_data(item) for item in data]
        else:
            return data

    def debug(self, msg: str, *args, **kwargs):
        """Log debug with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.debug(masked_msg, **masked_kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.info(masked_msg, **masked_kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.warning(masked_msg, **masked_kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.error(masked_msg, **masked_kwargs)


class SecureLoggingMixin:
    """Mixin to add secure logging to any class."""

    def __init__(self, *args, **kwargs):
        """Initialize with secure logger."""
        super().__init__(*args, **kwargs)
        self._secure_logger = SecureLogger(
            name=f"{self.__class__.__module__}.{self.__class__.__name__}",
            custom_fields=getattr(self, "_sensitive_fields", set()),
        )

    def log_debug(self, msg: str, data: Optional[Dict[str, Any]] = None):
        """Log debug with automatic masking."""
        if data:
            self._secure_logger.debug(
                f"{msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.debug(msg)

    def log_info(self, msg: str, data: Optional[Dict[str, Any]] = None):
        """Log info with automatic masking."""
        if data:
            self._secure_logger.info(
                f"{msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.info(msg)

    def log_error(
        self,
        msg: str,
        error: Optional[Exception] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Log error with automatic masking."""
        error_msg = f"{msg}: {str(error)}" if error else msg
        if data:
            self._secure_logger.error(
                f"{error_msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.error(error_msg)


def secure_log(mask_params: Optional[List[str]] = None):
    """Decorator for secure logging of function calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = SecureLogger(f"{func.__module__}.{func.__name__}")

            # Mask specified parameters
            masked_kwargs = {}
            for key, value in kwargs.items():
                if mask_params and key in mask_params:
                    masked_kwargs[key] = logger._mask_value(str(value))
                else:
                    masked_kwargs[key] = logger._mask_data(value)

            logger.debug(f"Calling {func.__name__} with args: {masked_kwargs}")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} failed: {str(e)}")
                raise

        return wrapper

    return decorator


def apply_secure_logging_to_node(node_class):
    """Decorator to add secure logging to a node class."""

    # Create new class that inherits from both
    class SecureNode(SecureLoggingMixin, node_class):
        """Node with secure logging enabled."""

        def run(self, **inputs):
            """Run with secure logging."""
            self.log_debug("Node execution started", inputs)

            try:
                result = super().run(**inputs)
                self.log_debug("Node execution completed")
                return result
            except Exception as e:
                self.log_error("Node execution failed", e, inputs)
                raise

    # Preserve original class name and module
    SecureNode.__name__ = node_class.__name__
    SecureNode.__module__ = node_class.__module__
    SecureNode.__qualname__ = node_class.__qualname__

    return SecureNode
