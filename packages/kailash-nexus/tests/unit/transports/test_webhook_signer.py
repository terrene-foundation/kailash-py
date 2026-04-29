"""
Tier 1 unit tests for WebhookSigner protocol + built-in signers (#687).

Covers:

* HmacSha256Signer round-trip + tamper detection (default, current behavior)
* TwilioSigner against Twilio's published canonical test vector
* TwilioSigner JSON-body fallback
* WebhookTransport backward compatibility (no signer kwarg → HmacSha256Signer)
* WebhookTransport with custom signer
* verify-failure WARN log emits signer_class field, never the secret
"""

from __future__ import annotations

import logging

import pytest

from nexus.transports.webhook import (
    HmacSha256Signer,
    TwilioSigner,
    WebhookSigner,
    WebhookTransport,
)

# ---------- HmacSha256Signer (default) ------------------------------------


class TestHmacSha256Signer:
    def test_compute_returns_sha256_prefix(self) -> None:
        signer = HmacSha256Signer()
        sig = signer.compute(secret="topsecret", payload_bytes=b'{"event":"ping"}')
        assert sig.startswith("sha256=")
        assert len(sig) == len("sha256=") + 64  # hex(SHA-256) = 64 chars

    def test_round_trip(self) -> None:
        signer = HmacSha256Signer()
        body = b'{"event":"ping"}'
        sig = signer.compute(secret="topsecret", payload_bytes=body)
        assert signer.verify(
            secret="topsecret", provided_signature=sig, payload_bytes=body
        )

    def test_verify_rejects_wrong_secret(self) -> None:
        signer = HmacSha256Signer()
        body = b'{"event":"ping"}'
        sig = signer.compute(secret="topsecret", payload_bytes=body)
        assert not signer.verify(
            secret="WRONGSECRET", provided_signature=sig, payload_bytes=body
        )

    def test_verify_rejects_tampered_payload(self) -> None:
        signer = HmacSha256Signer()
        sig = signer.compute(secret="topsecret", payload_bytes=b'{"event":"ping"}')
        assert not signer.verify(
            secret="topsecret",
            provided_signature=sig,
            payload_bytes=b'{"event":"pwned"}',
        )

    def test_implements_protocol(self) -> None:
        # Structural typing check — HmacSha256Signer satisfies WebhookSigner.
        signer: WebhookSigner = HmacSha256Signer()
        assert callable(signer.compute)
        assert callable(signer.verify)


# ---------- TwilioSigner --------------------------------------------------


class TestTwilioSigner:
    """Test vectors derived from Twilio's published webhook security docs.

    Source: https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """

    # Published Twilio canonical test vector. Pinned per
    # `rules/cross-sdk-inspection.md` Rule 4 — byte vector, not abstract shape.
    TWILIO_URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
    TWILIO_AUTH_TOKEN = "12345"
    TWILIO_PARAMS = {
        "CallSid": "CA1234567890ABCDE",
        "Caller": "+14158675309",
        "Digits": "1234",
        "From": "+14158675309",
        "To": "+18005551212",
    }
    TWILIO_EXPECTED_SIGNATURE = "RSOYDt4T1cUTdK1PDd93/VVr8B8="

    def test_form_params_canonical_test_vector(self) -> None:
        signer = TwilioSigner()
        sig = signer.compute(
            secret=self.TWILIO_AUTH_TOKEN,
            payload_bytes=b"",
            request_url=self.TWILIO_URL,
            form_params=self.TWILIO_PARAMS,
        )
        assert sig == self.TWILIO_EXPECTED_SIGNATURE

    def test_verify_canonical_test_vector(self) -> None:
        signer = TwilioSigner()
        assert signer.verify(
            secret=self.TWILIO_AUTH_TOKEN,
            provided_signature=self.TWILIO_EXPECTED_SIGNATURE,
            payload_bytes=b"",
            request_url=self.TWILIO_URL,
            form_params=self.TWILIO_PARAMS,
        )

    def test_verify_rejects_tampered_param_value(self) -> None:
        signer = TwilioSigner()
        tampered = dict(self.TWILIO_PARAMS, Digits="9999")
        assert not signer.verify(
            secret=self.TWILIO_AUTH_TOKEN,
            provided_signature=self.TWILIO_EXPECTED_SIGNATURE,
            payload_bytes=b"",
            request_url=self.TWILIO_URL,
            form_params=tampered,
        )

    def test_verify_rejects_tampered_url(self) -> None:
        signer = TwilioSigner()
        assert not signer.verify(
            secret=self.TWILIO_AUTH_TOKEN,
            provided_signature=self.TWILIO_EXPECTED_SIGNATURE,
            payload_bytes=b"",
            request_url="https://attacker.example/myapp.php?foo=1&bar=2",
            form_params=self.TWILIO_PARAMS,
        )

    def test_verify_rejects_malformed_base64(self) -> None:
        signer = TwilioSigner()
        # Returns False, does NOT raise — matches HmacSha256Signer contract
        # for "wrong-shape signature is just invalid, not a protocol error."
        assert not signer.verify(
            secret=self.TWILIO_AUTH_TOKEN,
            provided_signature="!!!not-base64!!!",
            payload_bytes=b"",
            request_url=self.TWILIO_URL,
            form_params=self.TWILIO_PARAMS,
        )

    def test_json_body_fallback_round_trip(self) -> None:
        # When form_params is None and payload_bytes is non-empty, the
        # canonical input is url + sha256(body).hexdigest() per Twilio's
        # JSON-webhook validation rule.
        signer = TwilioSigner()
        body = b'{"event":"voice.recording.completed"}'
        sig = signer.compute(
            secret=self.TWILIO_AUTH_TOKEN,
            payload_bytes=body,
            request_url="https://mycompany.com/recording",
            form_params=None,
        )
        assert signer.verify(
            secret=self.TWILIO_AUTH_TOKEN,
            provided_signature=sig,
            payload_bytes=body,
            request_url="https://mycompany.com/recording",
            form_params=None,
        )

    def test_implements_protocol(self) -> None:
        signer: WebhookSigner = TwilioSigner()
        assert callable(signer.compute)
        assert callable(signer.verify)


# ---------- WebhookTransport integration ----------------------------------


class TestWebhookTransportSignerWiring:
    def test_default_signer_preserves_sha256_prefix(self) -> None:
        # No `signer=` → HmacSha256Signer default → existing behavior.
        transport = WebhookTransport(secret="topsecret")
        sig = transport.compute_signature(b'{"event":"ping"}')
        assert sig.startswith("sha256=")

    def test_default_signer_round_trip(self) -> None:
        transport = WebhookTransport(secret="topsecret")
        body = b'{"event":"ping"}'
        sig = transport.compute_signature(body)
        assert transport.verify_signature(body, sig)

    def test_custom_signer_replaces_default(self) -> None:
        transport = WebhookTransport(
            secret=TestTwilioSigner.TWILIO_AUTH_TOKEN,
            signer=TwilioSigner(),
            signature_header="X-Twilio-Signature",
        )
        # The bytes-only compute_signature path delegates to the signer with
        # empty url + None params → Twilio's degenerate "URL-only" canonical.
        sig = transport.compute_signature(b"")
        assert transport.verify_signature(b"", sig)
        # And it does NOT produce the `sha256=` prefix.
        assert not sig.startswith("sha256=")

    def test_request_aware_compute_with_twilio_signer(self) -> None:
        transport = WebhookTransport(
            secret=TestTwilioSigner.TWILIO_AUTH_TOKEN,
            signer=TwilioSigner(),
            signature_header="X-Twilio-Signature",
        )
        sig = transport.compute_signature_for_request(
            url=TestTwilioSigner.TWILIO_URL,
            form_params=TestTwilioSigner.TWILIO_PARAMS,
        )
        assert sig == TestTwilioSigner.TWILIO_EXPECTED_SIGNATURE
        assert transport.verify_signature_for_request(
            signature=sig,
            url=TestTwilioSigner.TWILIO_URL,
            form_params=TestTwilioSigner.TWILIO_PARAMS,
        )


class TestVerifyFailureLogging:
    """`rules/observability.md` Rule 1 + Rule 3: WARN on verify failure with
    signer_class. `rules/security.md` "No secrets in logs": never log the
    secret or the provided signature value.
    """

    def test_failure_logs_signer_class_not_secret(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        transport = WebhookTransport(secret="topsecret")
        body = b'{"event":"ping"}'
        bogus_sig = "sha256=" + "0" * 64

        with caplog.at_level(logging.WARNING):
            assert not transport.verify_signature(body, bogus_sig)

        # Find the verify-failure log line
        warn_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warn_records, "expected at least one WARNING on verify failure"
        rec = warn_records[-1]

        # signer_class is structurally captured
        assert getattr(rec, "signer_class", None) == "HmacSha256Signer"

        # Secret and provided signature MUST NOT appear in the formatted record
        formatted = rec.getMessage()
        assert "topsecret" not in formatted
        assert bogus_sig not in formatted
