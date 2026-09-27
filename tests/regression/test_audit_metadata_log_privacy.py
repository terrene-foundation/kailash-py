"""Automatic auth/audit diagnostics keep credential metadata out of log copies."""

import logging

import pytest

from kailash.nodes.auth import mfa
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEventNode
from kailash.trust.enforce.selective_disclosure import _redact_record
from kailash.utils.secure_logging import (
    redact_mapping,
    sanitize_log_structure,
    sanitize_log_value,
)

SECRET = "audit-metadata-canary-927418"
URL = f"https://user:{SECRET}@host.invalid/?token={SECRET}"
JSON = '{"password":"' + SECRET + '"}'
FIELDS = [URL, JSON, URL.encode(), JSON.encode(), URL + "\nFORGED\u202e"]


def assert_private(caplog):
    assert caplog.records
    for record in caplog.records:
        assert SECRET not in record.getMessage()
        assert SECRET not in record.name
        assert record.getMessage().isprintable()
        assert record.name.isprintable()


@pytest.mark.parametrize("value", FIELDS)
@pytest.mark.parametrize("level", ["info", "warning", "error"])
@pytest.mark.parametrize("output_format", ["json", "text"])
def test_audit_log_copy_preserves_public_entry(caplog, value, level, output_format):
    caplog.set_level(logging.DEBUG)
    node = AuditLogNode(
        "audit-privacy", output_format=output_format, include_timestamp=False
    )
    original = {"password": SECRET, "nested": [{"label": value, JSON: "value"}], "n": 7}
    result = node.execute(
        event_type=level, message=value, user_id=value, event_data=original
    )
    assert result["audit_entry"] == {
        "event_type": level,
        "message": sanitize_log_value(value, 512),
        "user_id": sanitize_log_value(value, 128),
        "data": sanitize_log_structure(redact_mapping(original)),
    }
    assert original["password"] == SECRET
    assert original["nested"][0]["label"] is value
    assert result["logged"] is True and result["log_level"] == level
    assert_private(caplog)


@pytest.mark.parametrize("value", FIELDS)
@pytest.mark.parametrize("severity", ["INFO", "MEDIUM", "CRITICAL"])
def test_security_event_copy_preserves_public_event(caplog, value, severity):
    node = SecurityEventNode("event-privacy")
    caplog.set_level(logging.INFO)
    original = {"password": SECRET, "url": value}
    result = node.execute(
        event_type=value,
        message=value,
        user_id=value,
        metadata=original,
        severity=severity,
    )
    event = result["security_event"]
    assert event["message"] == sanitize_log_value(value, 512)
    assert event["event_type"] == sanitize_log_value(value, 128)
    assert event["user_id"] == sanitize_log_value(value, 128)
    assert event["metadata"] == sanitize_log_structure(redact_mapping(original))
    assert result["alert_triggered"] is (severity == "CRITICAL")
    assert_private(caplog)


@pytest.mark.parametrize("value", FIELDS)
def test_security_unknown_severity_still_escalates(caplog, value):
    caplog.set_level(logging.INFO)
    result = SecurityEventNode("invalid-severity").execute(severity=value)
    assert result["security_event"]["severity"] == "CRITICAL"
    assert result["alert_triggered"] is True
    assert_private(caplog)


@pytest.mark.parametrize("value", [URL, JSON, URL + "\nFORGED"])
def test_mfa_real_constructor_warns_without_changing_identity(caplog, value):
    mfa._WARNED_ONCE.clear()
    caplog.set_level(logging.WARNING)
    node = mfa.MultiFactorAuthNode(name=value, require_actor=False)
    assert node.metadata.name == value and node.require_actor is False
    assert any("authorization is DISABLED" in r.getMessage() for r in caplog.records)
    node.audit_log_node.execute(message="ordinary event")
    node.security_event_node.execute(message="ordinary event", severity="HIGH")
    assert_private(caplog)


@pytest.mark.parametrize("value", [URL, JSON, URL + "\nFORGED"])
def test_unknown_disclosure_is_hashed_without_logging_content(caplog, value):
    caplog.set_level(logging.WARNING)
    record = {
        "id": "audit1",
        "reasoning_trace": {"confidentiality": value, "reasoning_text": SECRET},
    }
    result = _redact_record(record, [])
    assert "reasoning_trace" in result.redacted_fields
    assert isinstance(result.data["reasoning_trace"], str)
    assert SECRET not in result.data["reasoning_trace"]
    assert record["reasoning_trace"]["reasoning_text"] == SECRET
    assert_private(caplog)


@pytest.mark.parametrize("sink", [AuditLogNode, SecurityEventNode])
def test_logger_namespace_uses_safe_copy(caplog, sink):
    caplog.set_level(logging.INFO)
    node = sink(name=URL + "\nFORGED")
    assert node.metadata.name == URL + "\nFORGED"
    node.execute(message="ordinary event")
    assert_private(caplog)


def test_opaque_audit_leaf_is_never_rendered_by_log_copy(caplog):
    class Opaque:
        def __repr__(self):
            return SECRET

    caplog.set_level(logging.INFO)
    result = AuditLogNode("opaque").execute(event_data={"opaque": Opaque()})
    # Existing public result representation is deliberately preserved.
    assert result["audit_entry"]["data"]["opaque"] == SECRET
    assert_private(caplog)
