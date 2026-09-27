# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2111 — ``sanitize_provider_error`` must not carry a line terminator out.

The helper scrubbed credential SHAPES but never touched line terminators, so a
provider exception whose text an attacker can influence carried a raw ``\\n``
out of the function. Its return value is interpolated into ``logger.*`` calls
at 55 measured call sites across 45 modules, so that newline FORGED A SECOND
LOG RECORD at every one of them. The barrier belongs in the shared helper, not
in 55 call sites.

INSTRUMENT NOTE — READ BEFORE CHANGING THESE ASSERTIONS.
A ``\\n`` inside a message produces ONE ``LogRecord`` that renders across TWO
lines. Asserting on RECORD COUNT (``caplog.records``) is therefore NOT
discriminating: it reads 1 both before and after the fix, so such a test would
pass against the vulnerable code and pin nothing. These tests attach a real
``StreamHandler`` over a buffer and assert on the number of EMITTED LINES,
which is the property an operator, a log shipper, and a SIEM actually parse.
The record text is pinned alongside so a future "fix" that drops the message
entirely cannot pass either.
"""

from __future__ import annotations

import io
import logging

import pytest

from kailash.utils.secure_logging import _MAX_LOG_VALUE_CHARS
from kaizen.nodes.ai import error_sanitizer
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error


def _bound() -> int:
    """Read the module's explicit bound WITHOUT importing it at module scope.

    A top-level ``from ... import _PROVIDER_ERROR_MAX_CHARS`` would make this
    whole file fail to COLLECT against the unfixed helper, and a collection
    error is not a demonstration of the defect -- it proves nothing about log
    forging. Resolving the constant lazily keeps the security assertions above
    collectable and red FOR THE RIGHT REASON (a forged extra emitted line).
    """
    value = getattr(error_sanitizer, "_PROVIDER_ERROR_MAX_CHARS", None)
    assert value is not None, (
        "sanitize_provider_error does not pass an explicit bound to "
        "sanitize_log_value; it would inherit the 256-char default"
    )
    return value


def _marker() -> str:
    value = getattr(error_sanitizer, "_TRUNCATION_MARKER", None)
    assert value is not None, "truncation is not announced"
    return value


_FORGED = "ERROR:kaizen.audit:forged consent_granted=true"


def _emit(message_value: str) -> tuple[list[str], str]:
    """Log ``message_value`` through a REAL handler; return (lines, text).

    Deliberately not ``caplog``: caplog stores records, and the whole point of
    this file is that the record count cannot see the defect. A StreamHandler
    over a StringIO is the smallest thing that renders a record the way a log
    file does.
    """
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger = logging.getLogger("kaizen.test.issue_2111")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        # The exact interpolation shape used at the real call sites.
        logger.warning("Provider call failed: %s", message_value)
    finally:
        handler.flush()
        logger.handlers = []
    text = buffer.getvalue()
    return [line for line in text.split("\n") if line], text


def test_control_the_line_instrument_actually_fires() -> None:
    """The instrument must be shown able to REPORT a forged line.

    Without this control, a green below is unreadable: a helper that returned
    "" would also produce one line. Feeding the raw, UNSANITIZED message proves
    the harness can see two lines when two lines exist.
    """
    raw = f"boom\n{_FORGED}"
    lines, _ = _emit(raw)
    assert len(lines) == 2, (
        "the line-counting instrument cannot observe a forged record; every "
        f"assertion below would be vacuous. Got {lines!r}"
    )


def test_record_count_alone_is_not_discriminating() -> None:
    """Pins WHY this file counts lines rather than records.

    If this ever fails, the logging module changed such that a newline splits
    records, and the cheaper record-count assertion would then be valid.
    """
    raw = f"boom\n{_FORGED}"
    logger = logging.getLogger("kaizen.test.issue_2111_records")
    captured: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Collect()
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.warning("Provider call failed: %s", raw)
    finally:
        logger.handlers = []

    assert len(captured) == 1, (
        "a newline now splits LogRecords; the line-based assertions in this "
        "file could be simplified, but do NOT weaken them without re-measuring"
    )


@pytest.mark.parametrize(
    "terminator",
    ["\n", "\r\n", "\r", " ", " ", "\x0b", "\x0c", "\x85"],
    ids=["lf", "crlf", "cr", "ls", "ps", "vt", "ff", "nel"],
)
def test_no_terminator_can_forge_a_second_line(terminator: str) -> None:
    """THE REGRESSION. No line terminator survives into the emitted record."""
    error = ValueError(f"boom{terminator}{_FORGED}")
    sanitized = sanitize_provider_error(error, "LLM")

    lines, text = _emit(sanitized)
    assert len(lines) == 1, (
        f"terminator {terminator!r} forged an extra emitted LINE — an attacker-"
        f"influenced provider message can write its own log record. Got: {text!r}"
    )
    # Supporting detail, asserted AFTER the line count so the primary red is
    # the forged LINE itself rather than a character-level precondition.
    assert (
        "\n" not in sanitized and "\r" not in sanitized
    ), f"line terminator {terminator!r} survived sanitization: {sanitized!r}"
    # DISCRIMINATION NOTE. Only LF and CRLF split a stream written by
    # StreamHandler, so for VT/FF/LS/PS/NEL the line-count assertion above
    # reads 1 both before and after the fix -- it is VACUOUS for those five
    # and must not be the only thing asserted, or this parametrization would
    # be five green rows that pin nothing (``rules/instrument-discipline.md``
    # MUST-2). Those five ARE treated as line breaks by common log shippers,
    # terminals and SIEM parsers, so what actually needs pinning is that the
    # character does not survive at all. THIS assertion reds for all eight.
    assert terminator not in sanitized, (
        f"terminator {terminator!r} survived into the record verbatim; a log "
        f"shipper or terminal that honours it still sees two lines: "
        f"{sanitized!r}"
    )
    assert " " in sanitized, "the terminator should flatten to a space"

    # Pin the text too: a "fix" that discarded the message would also emit one
    # line, and must not be allowed to pass this file.
    assert lines[0].startswith("WARNING:kaizen.test.issue_2111:"), lines[0]
    assert "LLM error (ValueError): boom" in lines[0], lines[0]
    assert "forged" in lines[0], (
        "the diagnostic content was dropped rather than flattened; this helper "
        "neutralizes structure, it is not a redaction step"
    )


def test_provider_name_is_also_flattened() -> None:
    """``provider_name`` is not always a literal.

    ``llm/routing/fallback.py`` passes ``self.model_used`` — a configured model
    name — so it is a second injection vector into the same returned string.
    """
    sanitized = sanitize_provider_error(ValueError("x"), f"gpt-4\n{_FORGED}")
    lines, text = _emit(sanitized)
    assert len(lines) == 1, f"provider_name forged an extra line: {text!r}"


def test_bound_is_explicit_and_not_the_helper_default() -> None:
    """The 256-char default must NOT be inherited by accident.

    Of the 127 call sites, only 55 are log sinks; the other 72 return this
    string in a payload or raise it. Inheriting 256 would silently amputate
    their diagnostics.
    """
    from kailash.utils.secure_logging import _DEFAULT_LOG_VALUE_CHARS

    assert _bound() != _DEFAULT_LOG_VALUE_CHARS
    assert _bound() == _MAX_LOG_VALUE_CHARS, (
        "the bound passed to sanitize_log_value has drifted from that "
        "function's hard ceiling; a larger value would be silently clamped "
        "and this module's comments would misdescribe the behaviour"
    )

    # A message comfortably longer than the OLD default must survive intact.
    payload = "a.b-" * 60  # 240 chars, unclaimed by any credential pattern
    out = sanitize_provider_error(ValueError(payload), "LLM")
    assert out.endswith(payload), (
        "a message the 256-char default would have cut was truncated; the "
        f"explicit bound is not being passed. Got: {out!r}"
    )
    assert _marker() not in out


def test_truncation_is_announced_never_silent() -> None:
    """Silent truncation of a returned error payload is a silent fallback."""
    payload = "a.b-" * 2_000  # 8 KB, unclaimed by any credential pattern
    out = sanitize_provider_error(ValueError(payload), "LLM")

    assert len(out) == _bound() + len(_marker())
    assert out.endswith(_marker()), (
        "the message was shortened with no trace; a caller that raises or "
        "returns this string would lose diagnostics silently"
    )

    # And the boundary: exactly at the bound is NOT marked.
    prefix = len("LLM error (ValueError): ")
    exact = sanitize_provider_error(ValueError("-" * (_bound() - prefix)), "LLM")
    assert len(exact) == _bound()
    assert _marker() not in exact, "off-by-one: the bound was not hit"

    one_over = sanitize_provider_error(ValueError("-" * (_bound() - prefix + 1)), "LLM")
    assert one_over.endswith(_marker())


def test_credentials_are_scrubbed_before_the_bound_applies() -> None:
    """Order matters: bounding first could cut a secret into a survivor."""
    secret = "sk-" + "A" * 60
    padding = "-" * (_bound() + 500)
    out = sanitize_provider_error(ValueError(f"{padding} auth {secret}"), "LLM")
    assert secret not in out
    assert "A" * 60 not in out
