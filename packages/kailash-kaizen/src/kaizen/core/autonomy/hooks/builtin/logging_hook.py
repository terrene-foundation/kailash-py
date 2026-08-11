"""
Logging hook for structured event logging.

Logs all hook events with configurable log levels and formats (text or JSON).
Supports ELK-compatible JSON logging via structlog.

SECURITY: Supports sensitive data redaction (Finding #4 fix).
"""

import logging
from typing import Any, ClassVar, Optional

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult

logger = logging.getLogger(__name__)

#: Cap on a rendered payload before it reaches the DEBUG sink. Applied BEFORE
#: scrubbing: ``scrub_credentials`` runs ~25 regex passes, each building a fresh
#: string, and it was written for error text — whereas a hook payload can carry
#: a whole retrieved document. Capping first bounds both scrub cost and log
#: volume. Mirrors the same constant in the ``BaseAgent`` fix (#2030).
MAX_PAYLOAD_CHARS = 2000


def _summarize(payload: Any) -> dict[str, Any]:
    """Describe a payload's SHAPE without reproducing any of its values.

    Key names are structure, not content: they come from the signature /
    event schema, not from user input, so they are safe to log where the
    values they index are not.
    """
    if isinstance(payload, dict):
        return {"count": len(payload), "keys": sorted(str(k) for k in payload)}
    return {"count": 0 if payload is None else 1, "keys": []}


class LoggingHook(BaseHook):
    """
    Logs all hook events for debugging and audit trails.

    Supports both text and JSON (structlog) formats for ELK compatibility.

    Features:
    - Configurable log level (DEBUG, INFO, WARNING, ERROR)
    - Text format (backward compatible)
    - JSON format (ELK-compatible via structlog)
    - trace_id propagation for distributed tracing
    - Privacy-aware data logging (optional)

    Example:
        >>> # Text format (backward compatible)
        >>> hook = LoggingHook(log_level="INFO", format="text")

        >>> # JSON format for ELK
        >>> hook = LoggingHook(log_level="INFO", format="json")
    """

    # Define which events this hook handles
    events: ClassVar[list[HookEvent]] = list(HookEvent)  # All events

    def __init__(
        self,
        log_level: str = "INFO",
        include_data: bool = True,
        format: str = "text",
        redact_sensitive: Optional[bool] = None,
        log_full_payloads: bool = False,
    ):
        """
        Initialize logging hook.

        Args:
            log_level: Log level (DEBUG, INFO, WARNING, ERROR)
            include_data: Whether to log event data STRUCTURE (key names and
                counts). Payload VALUES are never emitted at this level; see
                ``log_full_payloads``.
            format: Log format ("text" or "json")
            redact_sensitive: Enable sensitive-data redaction. ``None`` (the
                default) enables it but permits degradation if the redactor
                cannot be loaded; ``True`` is an EXPLICIT opt-in and raises
                rather than degrading; ``False`` disables it outright.
            log_full_payloads: Emit payload VALUES, at DEBUG only, scrubbed.
                Defaults False so that turning DEBUG on globally — routine
                during incident response — does not start dumping user prompts,
                retrieved documents and PII.

        Raises:
            RuntimeError: if ``redact_sensitive=True`` was requested explicitly
                and ``SensitiveDataRedactor`` cannot be imported.

        Example:
            >>> # Production usage with redaction
            >>> hook = LoggingHook(
            ...     log_level="INFO",
            ...     include_data=True,
            ...     redact_sensitive=True  # Enable redaction
            ... )
        """
        super().__init__(name="logging_hook")
        self.log_level = log_level
        self.include_data = include_data
        self.format = format
        self.log_full_payloads = log_full_payloads

        # An EXPLICIT `True` is a different request from the default (#2070).
        # The distinction is load-bearing and is the reason this is tri-state
        # rather than a bool: raising on a default nobody asked for would break
        # installs where the redactor is genuinely absent, while degrading an
        # explicit opt-in silently overrides an operator who already made the
        # correct decision.
        redaction_explicitly_requested = redact_sensitive is True
        self.redact_sensitive = True if redact_sensitive is None else redact_sensitive

        # Initialize redactor if needed (SECURITY FIX #4)
        if self.redact_sensitive:
            try:
                from ..security.redaction import SensitiveDataRedactor

                self.redactor: Optional[SensitiveDataRedactor] = SensitiveDataRedactor()
            except ImportError as exc:
                if redaction_explicitly_requested:
                    # FAIL CLOSED. Previously this branch set
                    # `redact_sensitive = False` and carried on logging at full
                    # fidelity behind a WARNING — defeating the operator's own
                    # explicit choice, which `zero-tolerance.md` Rule 3 blocks.
                    raise RuntimeError(
                        "redact_sensitive=True was requested but "
                        "SensitiveDataRedactor could not be imported, so "
                        "redaction cannot be performed. Refusing to log "
                        "unredacted instead. Install the security module, or "
                        "pass redact_sensitive=False to accept unredacted "
                        "logging deliberately."
                    ) from exc

                # NOT explicitly requested: degrading is acceptable, but the
                # payloads redaction was protecting MUST stop too. A degraded
                # control that keeps emitting is the disclosure the control
                # existed to prevent.
                logger.warning(
                    "SensitiveDataRedactor not available, disabling redaction "
                    "AND payload-value logging. Install security module to "
                    "enable redaction."
                )
                self.redactor = None
                self.redact_sensitive = False
                self.log_full_payloads = False
        else:
            self.redactor = None

        # Configure logger based on format
        if format == "json":
            # structlog is an optional observability dependency (slim core).
            # Import it lazily so the text format (default) and merely importing
            # this module never require it; raise a clear, actionable error only
            # when JSON output is actually requested without the extra installed.
            try:
                import structlog
            except ImportError as exc:
                raise ImportError(
                    "LoggingHook(format='json') requires structlog. Install the "
                    "observability extra: pip install 'kailash-kaizen[observability]'"
                ) from exc

            # Configure structlog for JSON output
            structlog.configure(
                processors=[
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.stdlib.add_log_level,
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    structlog.processors.JSONRenderer(),
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                cache_logger_on_first_use=True,
            )
            self.logger = structlog.get_logger()
        else:
            # Use standard Python logging
            self.logger = logger

    async def handle(self, context: HookContext) -> HookResult:
        """
        Log the hook event with optional sensitive data redaction.

        Args:
            context: Hook execution context

        Returns:
            HookResult indicating success
        """
        try:
            # STEP 1: Redact sensitive data if enabled (SECURITY FIX #4)
            if self.redact_sensitive and self.redactor:
                safe_context = self.redactor.redact_hook_context(context)
            else:
                safe_context = context

            # STEP 2: Log STRUCTURE, never values (#2070).
            #
            # `agent_loop` feeds this hook whole agent I/O — PRE_AGENT_LOOP
            # carries {"inputs": ...}, POST_AGENT_LOOP carries {"result": ...} —
            # so the previous `Data={safe_context.data}` put user prompts,
            # retrieved documents and any credential-bearing parameter on the
            # INFO log. Redaction is not a substitute here: it claims credential
            # SHAPES and PII patterns, and a user's prose matches neither.
            # Withholding values is what actually closes it.
            data_summary = _summarize(safe_context.data)
            meta_summary = _summarize(safe_context.metadata)

            if self.format == "json":
                # Structured JSON logging
                log_event = {
                    "event_type": safe_context.event_type.value,
                    "agent_id": safe_context.agent_id,
                    "trace_id": safe_context.trace_id,
                    "timestamp": safe_context.timestamp,
                    "level": self.log_level.lower(),
                }

                if self.include_data:
                    log_event["context_keys"] = data_summary["keys"]
                    log_event["context_field_count"] = data_summary["count"]
                    log_event["metadata_keys"] = meta_summary["keys"]

                # Log using structlog (outputs JSON)
                log_fn = getattr(self.logger, self.log_level.lower())
                log_fn("hook_event", **log_event)

            else:
                # Text format (backward compatible)
                log_fn = getattr(self.logger, self.log_level.lower())

                if self.include_data:
                    log_fn(
                        f"[{safe_context.event_type.value}] "
                        f"Agent={safe_context.agent_id} "
                        f"TraceID={safe_context.trace_id} "
                        f"DataKeys={data_summary['keys']} "
                        f"({data_summary['count']} field(s))"
                    )
                else:
                    log_fn(
                        f"[{safe_context.event_type.value}] "
                        f"Agent={safe_context.agent_id} "
                        f"TraceID={safe_context.trace_id}"
                    )

            # STEP 3: Values, only on deliberate opt-in, only at DEBUG,
            # only scrubbed. Two independent gates, because either alone is
            # routinely satisfied by accident: `log_full_payloads` defaults
            # False so global DEBUG does not start dumping payloads, and the
            # DEBUG check keeps the render cost off the INFO path entirely.
            self._log_full_payload(safe_context)

            return HookResult(success=True)

        except Exception as e:
            # Even logging can fail!
            return HookResult(success=False, error=str(e))

    def _log_full_payload(self, safe_context: HookContext) -> None:
        """Emit payload VALUES at DEBUG, scrubbed, on explicit opt-in only.

        `safe_context` has already been through the redactor when one is
        wired; `scrub_credentials` is applied on top because the two cover
        different classes — the redactor owns PII and payment shapes and
        delegates vendor credentials to `scrub_credentials`, which is the
        single credential-scrub implementation in Kaizen.

        Scrubbing claims credential SHAPES, not arbitrary PII, which is
        precisely why the `log_full_payloads` gate defaults False rather than
        relying on the scrubber to make payloads safe.
        """
        if not self.log_full_payloads:
            return
        if not logger.isEnabledFor(logging.DEBUG):
            return

        from kaizen.utils.credential_scrub import scrub_credentials

        rendered = repr(safe_context.data)
        if len(rendered) > MAX_PAYLOAD_CHARS:
            rendered = (
                f"{rendered[:MAX_PAYLOAD_CHARS]}"
                f"...[truncated {len(rendered)} chars]"
            )
        scrubbed = scrub_credentials(rendered)

        if self.format == "json":
            self.logger.debug("hook_event_payload", payload=scrubbed)
        else:
            self.logger.debug(
                f"[{safe_context.event_type.value}] "
                f"Agent={safe_context.agent_id} "
                f"Payload={scrubbed}"
            )

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """Log errors to stderr"""
        logger.error(f"LoggingHook failed for {context.event_type.value}: {error}")
