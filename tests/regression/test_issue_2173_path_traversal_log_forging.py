"""Regression: the path-traversal guard must not log the attack into its own record.

``kailash.security.validate_file_path`` rejects hostile paths and, when audit
logging is on, records what it rejected. The rejected value is attacker-chosen
BY CONSTRUCTION -- it is the payload that just failed validation -- and it was
being interpolated into the log line verbatim. A newline inside it forges a
second, fully-formed log record inside the exact log an auditor reads after an
attack: the control logged the attack into the account of the attack.

These tests assert on the EMITTED STREAM, not on a ``LogRecord`` count. A forged
record is forged at FORMAT time -- the logging module still sees one record --
so counting records cannot tell a clean rejection from a forged one. Only the
rendered output can, which is why a realistic formatter is attached.
"""

import logging

import pytest

from kailash.security import (
    PathTraversalError,
    SecurityConfig,
    SecurityError,
    validate_file_path,
)

pytestmark = pytest.mark.regression

# A newline plus a plausible record prefix: if the value reaches the formatter
# unflattened, the log gains a second line that reads as a genuine record.
FORGED_TAIL = "WARNING:kailash.security:AUDIT OK - access granted to admin"


@pytest.fixture
def captured():
    """Attach a stream handler with a realistic multi-field formatter."""
    import io

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger = logging.getLogger("kailash.security")
    logger.addHandler(handler)
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


@pytest.fixture
def config() -> SecurityConfig:
    return SecurityConfig(enable_audit_logging=True, enable_path_validation=True)


def _emitted_lines(stream) -> list[str]:
    return [line for line in stream.getvalue().splitlines() if line.strip()]


def test_traversal_rejection_emits_exactly_one_line(captured, config):
    """A newline-bearing rejected path must not become two log records."""
    hostile = f"/tmp/../etc/passwd\n{FORGED_TAIL}"

    with pytest.raises(PathTraversalError):
        validate_file_path(hostile, config=config)

    lines = _emitted_lines(captured)
    assert len(lines) == 1, f"log forging: expected 1 line, got {len(lines)}: {lines}"
    assert FORGED_TAIL not in "\n".join(lines[1:])


def test_carriage_return_does_not_forge_a_record(captured, config):
    """`\\r` rewrites a console line just as `\\n` splits one."""
    hostile = f"/tmp/../etc/passwd\r{FORGED_TAIL}"

    with pytest.raises(PathTraversalError):
        validate_file_path(hostile, config=config)

    output = captured.getvalue()
    assert "\r" not in output
    assert len(_emitted_lines(captured)) == 1


def test_sensitive_directory_rejection_emits_exactly_one_line(captured, config):
    """The sibling branch guarding /etc, /var, ... shares the same defect class."""
    hostile = f"/etc/shadow\n{FORGED_TAIL}"

    with pytest.raises(SecurityError):
        validate_file_path(hostile, config=config)

    assert len(_emitted_lines(captured)) == 1


def test_diagnostic_value_survives_flattening(captured, config):
    """Flattening is not redaction: the operator still needs to see what was sent."""
    with pytest.raises(PathTraversalError):
        validate_file_path("/tmp/../etc/passwd", config=config)

    output = captured.getvalue()
    assert "etc/passwd" in output, "the rejected path must remain diagnosable"
