"""MFA diagnostics omit delivery payloads without changing auth or responses."""

import io
import logging
import sys
import types

import pytest

from kailash.nodes.auth import mfa
from kailash.nodes.auth._actor import MFAActor, StaticActorResolver
from kailash.nodes.auth.mfa import MFADeliveryError, MultiFactorAuthNode

pytestmark = pytest.mark.regression
PAYLOAD = "private.example SECRET_PAYLOAD_781924"
RECIPIENT = "person@private.example"


@pytest.fixture
def diagnostics():
    records = []
    stream = io.StringIO()

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    raw = Capture()
    rendered = logging.StreamHandler(stream)
    rendered.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    # Both the canonical module producer and the previous mixin producer.
    loggers = [
        logging.getLogger(mfa.__name__),
        logging.getLogger("MultiFactorAuthNode"),
    ]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(raw)
        logger.addHandler(rendered)
    try:
        yield records, stream
        assert records, "diagnostic path was not reached"
        for record in records:
            assert not record.exc_info and not record.stack_info
            assert "private.example" not in repr(record.__dict__)
            assert "SECRET_PAYLOAD_781924" not in repr(record.__dict__)
        assert "private.example" not in stream.getvalue()
        assert "SECRET_PAYLOAD_781924" not in stream.getvalue()
    finally:
        for logger, level in zip(loggers, levels):
            logger.removeHandler(raw)
            logger.removeHandler(rendered)
            logger.setLevel(level)


def _node(**kwargs):
    resolver = StaticActorResolver({"proof": MFAActor(user_id="subject")})
    return MultiFactorAuthNode(actor_resolver=resolver, **kwargs)


def _raise(*args, **kwargs):
    raise OSError(PAYLOAD)


def _twilio(monkeypatch, *, fail):
    package = types.ModuleType("twilio")
    rest = types.ModuleType("twilio.rest")

    class Client:
        def __init__(self, *args):
            self.messages = self

        def create(self, **kwargs):
            if fail:
                _raise()
            return types.SimpleNamespace(sid=PAYLOAD)

    rest.Client = Client
    monkeypatch.setitem(sys.modules, "twilio", package)
    monkeypatch.setitem(sys.modules, "twilio.rest", rest)


def _smtp(monkeypatch, *, fail):
    class SMTP:
        def __init__(self, *args, **kwargs):
            if fail:
                _raise()

        def starttls(self):
            return None

        def login(self, *args):
            return None

        def send_message(self, message):
            return None

        def quit(self):
            return None

    monkeypatch.setattr("smtplib.SMTP", SMTP)


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_actual_provider_failure_and_setup_wrapper_keep_response_contract(
    channel, monkeypatch, diagnostics
):
    if channel == "email":
        _smtp(monkeypatch, fail=True)
        node = _node(
            email_provider={
                "smtp_host": "smtp.invalid",
                "username": "sender",
                "password": "synthetic",
            }
        )
        inputs = {"user_email": RECIPIENT}
    else:
        _twilio(monkeypatch, fail=True)
        node = _node(sms_provider={"service": "twilio"})
        inputs = {"user_phone": "+15555550199"}
    result = node.execute(
        action="setup",
        user_id="subject",
        actor_session_id="proof",
        method=channel,
        **inputs,
    )
    assert result["success"] is False and result["verification_sent"] is False
    assert result["error"] == f"{channel.title()} delivery failed".replace("Sms", "SMS")
    assert channel not in node.user_mfa_data["subject"]["methods"]
    events = [r.getMessage().split()[0] for r in diagnostics[0]]
    assert f"mfa.{channel}_delivery_failed" in events
    assert f"mfa.{channel}_setup_failed" in events
    assert all(
        "type=" in r.getMessage() and "frames=" in r.getMessage()
        for r in diagnostics[0]
        if r.levelno >= logging.ERROR
    )


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_transport_exception_type_message_and_cause_are_unchanged(
    channel, monkeypatch, diagnostics
):
    node = _node(
        email_provider={"smtp_host": "smtp.invalid", "username": "sender"},
        sms_provider={"service": "twilio"},
    )
    _smtp(monkeypatch, fail=True)
    _twilio(monkeypatch, fail=True)
    call = node._smtp_send if channel == "email" else node._twilio_send
    args = (
        (RECIPIENT, "subject", PAYLOAD)
        if channel == "email"
        else ("+15555550199", PAYLOAD)
    )
    with pytest.raises(MFADeliveryError) as error:
        call(*args)
    assert PAYLOAD in str(error.value)
    assert isinstance(error.value.__cause__, OSError)
    assert str(error.value.__cause__) == PAYLOAD


def test_push_failure_clears_challenge_and_retains_failure_result(
    monkeypatch, diagnostics
):
    node = _node(push_provider={"server_key": "synthetic"})
    node.user_devices["subject"] = [{"device_id": PAYLOAD, "push_token": "synthetic"}]
    monkeypatch.setattr("requests.post", _raise)
    result = node.execute(
        action="send_push", user_id="subject", actor_session_id="proof"
    )
    assert result["success"] is False and result["challenge_sent"] is False
    assert result["error"] == "Push delivery failed"
    assert node.push_challenges == {}
    assert any("mfa.push_delivery_failed" in r.getMessage() for r in diagnostics[0])


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_recovery_failure_keeps_no_pending_request(channel, monkeypatch, diagnostics):
    node = _node(
        email_provider={"smtp_host": "smtp.invalid", "username": "sender"},
        sms_provider={"service": "twilio"},
    )
    node.user_mfa_data["subject"] = {
        "methods": {
            channel: {"verified": True, "email": RECIPIENT, "phone": "+15555550199"}
        }
    }
    _smtp(monkeypatch, fail=True)
    _twilio(monkeypatch, fail=True)
    result = node._initiate_recovery("subject", channel)
    assert result == {
        "success": False,
        "recovery_method": channel,
        "error": "Recovery token delivery failed",
    }
    assert not getattr(node, "recovery_requests", {})
    assert any("mfa.recovery_delivery_failed" in r.getMessage() for r in diagnostics[0])


@pytest.mark.parametrize(
    "channel", ["email", "sms", "push", "recovery_email", "recovery_sms", "admin"]
)
def test_success_diagnostics_omit_destination_device_and_provider_id(
    channel, monkeypatch, diagnostics
):
    node = _node(
        email_provider={"smtp_host": "smtp.invalid", "username": "sender"},
        sms_provider={"service": "twilio"},
        push_provider={"server_key": "synthetic"},
    )
    _smtp(monkeypatch, fail=False)
    _twilio(monkeypatch, fail=False)
    if channel == "email":
        node._smtp_send(RECIPIENT, "subject", PAYLOAD)
    elif channel == "sms":
        node._twilio_send("+15555550199", PAYLOAD)
    elif channel == "push":
        node.user_devices["subject"] = [
            {"device_id": PAYLOAD, "push_token": "synthetic"}
        ]
        monkeypatch.setattr(
            "requests.post", lambda *a, **kw: types.SimpleNamespace(status_code=200)
        )
        assert node._send_push_challenge("subject", {})["success"] is True
    else:
        method = channel.removeprefix("recovery_")
        assert (
            node._deliver_recovery_token(method, RECIPIENT, PAYLOAD, RECIPIENT) is True
        )
    assert any(r.getMessage().startswith("mfa.") for r in diagnostics[0])


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_missing_transport_warns_without_user_or_destination(channel, diagnostics):
    node = _node()
    call = node._send_email_code if channel == "email" else node._send_sms_code
    assert call(RECIPIENT, "426819", RECIPIENT) is False
    assert diagnostics[0][0].levelno == logging.WARNING
    assert (
        diagnostics[0][0].getMessage()
        == f"mfa.{channel}_transport_unconfigured; no code delivered"
    )


@pytest.mark.parametrize(
    "operation", ["totp", "qr", "audit", "audit_flush", "resolver", "invalid_input"]
)
def test_other_exception_diagnostics_retain_safe_structure(
    operation, monkeypatch, diagnostics
):
    node = _node()
    if operation == "totp":
        monkeypatch.setattr("pyotp.TOTP", _raise)
        assert node._verify_totp_code("synthetic", "123456") is False
    elif operation == "qr":
        monkeypatch.setattr("qrcode.QRCode", _raise)
        assert node._generate_qr_code(PAYLOAD) == ""
    elif operation in ("audit", "audit_flush"):

        def broken(**kwargs):
            raise ValueError(PAYLOAD)

        monkeypatch.setattr(node.audit_log_node, "execute", broken)
        if operation == "audit":
            node._audit_mfa_operation_sync(
                "subject", "status", "totp", {"success": True}
            )
        else:
            node._log_mfa_event("status", {"user_id": "subject"})
            node._flush_audit_records()
            assert not node._pending_audit_records
    elif operation == "resolver":
        monkeypatch.setattr(node.actor_resolver, "resolve_actor", _raise)
        result = node.execute(
            action="status", user_id="subject", actor_session_id="proof"
        )
        assert result["success"] is False and result["authorized"] is False
    else:

        def invalid(*args, **kwargs):
            raise ValueError(PAYLOAD)

        monkeypatch.setattr(node, "_get_mfa_status", invalid)
        result = node.execute(
            action="status", user_id="subject", actor_session_id="proof"
        )
        assert result == {
            "success": False,
            "error": "Invalid input for MFA operation",
            "action": "status",
        }
    assert any(
        "type=" in r.getMessage() and "frames=" in r.getMessage()
        for r in diagnostics[0]
    )


def test_hostile_exception_type_is_flattened_in_both_diagnostic_fields(
    monkeypatch, diagnostics
):
    hostile = type("Remote\nERROR forged", (OSError,), {})

    def fail(*args, **kwargs):
        raise hostile(PAYLOAD)

    monkeypatch.setattr("smtplib.SMTP", fail)
    node = _node(email_provider={"smtp_host": "smtp.invalid", "username": "sender"})
    with pytest.raises(MFADeliveryError):
        node._smtp_send(RECIPIENT, "subject", PAYLOAD)
    assert len(diagnostics[0]) == 1
    assert all("\n" not in str(value) for value in diagnostics[0][0].args)
    assert "\nERROR forged" not in repr(diagnostics[0][0].__dict__)
    assert len(diagnostics[1].getvalue().splitlines()) == 1
    assert "type=Remote?ERROR?forged" in diagnostics[0][0].getMessage()
