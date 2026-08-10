"""Regression tests for issue #2026 — production auth paths contained test stubs.

Two shipped auth paths carried test-compatibility shortcuts with security
consequences, plus siblings of the same shape found by sweeping
``src/kailash/nodes/auth/``:

* ``sso.py`` forged a successful OAuth token response when the token URL
  *contained* the substring ``oauth.example.com``, on the **exception** path.
* ``sso.py`` forged a user identity when the bearer token equalled
  ``test_access_token``, also on the exception path.
* ``mfa.py::_send_sms`` logged the SMS body (the OTP) at INFO and returned
  ``True`` having sent nothing.
* ``mfa.py`` accepted the hardcoded TOTP code ``123456`` for any secret, and
  accepted *any* 6-digit string as an SMS or email second factor.
* ``mfa.py`` swallowed provider send failures, so callers were told
  ``verification_sent: True`` for codes that were never delivered.

Every test here calls the function under test and asserts on its behaviour.
Source-grep assertions are deliberately avoided — they pass against code that
still contains the defect behind a different spelling.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.regression


class _FailingHTTPClient:
    """HTTP client double whose calls always fail — the attacker's easy path."""

    def __init__(self, name: str = "failing"):
        self.name = name
        self.calls: list = []

    async def async_run(self, **kwargs):
        self.calls.append(kwargs)
        raise ConnectionError("simulated network failure")


def _sso_node(**oauth_settings):
    from kailash.nodes.auth.sso import SSOAuthenticationNode

    node = SSOAuthenticationNode(
        name="sso_test",
        providers=["oauth2"],
        oauth_settings=oauth_settings or {},
    )
    node.http_client = _FailingHTTPClient()
    return node


# ---------------------------------------------------------------------------
# 1. SSO token exchange must fail closed for every URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token_endpoint",
    [
        # The attack from the issue: a lookalike host that satisfies the old
        # `"oauth.example.com" in token_url` substring test.
        "https://oauth.example.com.attacker.tld/token",
        # Substring in the query string rather than the host.
        "https://evil.tld/token?x=oauth.example.com",
        # A subdomain-prefixed lookalike.
        "https://oauth.example.com.evil.example/token",
        # The literal example host itself must not be special either.
        "https://oauth.example.com/token",
        # An unrelated host, for completeness.
        "https://legit-idp.example.net/token",
    ],
)
def test_token_exchange_never_forges_a_token(token_endpoint):
    """A failing token exchange raises for EVERY url — no synthetic success."""
    node = _sso_node(token_endpoint=token_endpoint)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(
            node._exchange_oauth_code(
                provider="oauth2",
                auth_code="attacker-supplied-code",
                cached_data={"redirect_uri": "https://app.example.net/cb"},
            )
        )

    assert "Token exchange failed" in str(excinfo.value)


def test_token_exchange_does_not_return_forged_token_fields():
    """The specific forged payload must not be reachable by any input."""
    node = _sso_node(token_endpoint="https://oauth.example.com.attacker.tld/token")

    try:
        result = asyncio.run(
            node._exchange_oauth_code(
                provider="oauth2",
                auth_code="code",
                cached_data={"redirect_uri": "https://app.example.net/cb"},
            )
        )
    except ValueError:
        return  # fail-closed is the correct outcome

    pytest.fail(f"token exchange returned a token instead of raising: {result}")


# ---------------------------------------------------------------------------
# 2. SSO userinfo must not derive an identity from the token's value
# ---------------------------------------------------------------------------


def test_userinfo_never_forges_identity_for_test_access_token():
    """Presenting the literal 'test_access_token' must not provision a user."""
    node = _sso_node(userinfo_endpoint="https://idp.example.net/userinfo")

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(
            node._get_oauth_user_info(
                provider="oauth2", access_token="test_access_token"
            )
        )

    assert "User info request failed" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3. MFA: the SMS transport must never log the OTP, and never fake a delivery
# ---------------------------------------------------------------------------


def test_send_sms_does_not_log_the_otp(caplog):
    """The message body carries the code; it must never reach the log."""
    from kailash.nodes.auth import mfa

    otp = "874193"
    body = f"Your verification code: {otp}"

    with caplog.at_level(logging.DEBUG, logger="kailash.nodes.auth.mfa"):
        with pytest.raises(mfa.MFADeliveryError):
            mfa._send_sms("+15555550123", body)

    assert otp not in caplog.text, f"OTP leaked into logs: {caplog.text!r}"
    assert body not in caplog.text, "SMS body leaked into logs"


def test_send_sms_raises_instead_of_returning_true():
    """It must not report success for a message it never sent."""
    from kailash.nodes.auth import mfa

    with pytest.raises(mfa.MFADeliveryError):
        mfa._send_sms("+15555550123", "Your verification code: 000000")


def test_send_sms_does_not_log_full_phone_number(caplog):
    """Only the last 4 digits may appear — the pre-existing behaviour, kept."""
    from kailash.nodes.auth import mfa

    with caplog.at_level(logging.DEBUG, logger="kailash.nodes.auth.mfa"):
        with pytest.raises(mfa.MFADeliveryError):
            mfa._send_sms("+15555550123", "body")

    assert "+15555550123" not in caplog.text


# ---------------------------------------------------------------------------
# 4. MFA verification must not accept hardcoded or shape-only codes
# ---------------------------------------------------------------------------


def _mfa_node(**kwargs):
    from kailash.nodes.auth.mfa import MultiFactorAuthNode

    return MultiFactorAuthNode(name="mfa_test", **kwargs)


def test_totp_rejects_the_hardcoded_test_code():
    """'123456' must not be a universal TOTP passphrase."""
    from kailash.nodes.auth.mfa import TOTPGenerator

    node = _mfa_node()
    secret = TOTPGenerator.generate_secret()

    # Guard against the 1-in-10^6 case where the live code really is 123456.
    if TOTPGenerator.generate_totp(secret) == "123456":
        secret = TOTPGenerator.generate_secret()

    assert node._verify_totp_code(secret, "123456") is False


def test_totp_still_accepts_a_genuine_code():
    """Positive control: the fix must not break real TOTP verification."""
    pytest.importorskip("pyotp")
    from kailash.nodes.auth.mfa import TOTPGenerator

    node = _mfa_node()
    secret = TOTPGenerator.generate_secret()
    real_code = TOTPGenerator.generate_totp(secret)

    assert node._verify_totp_code(secret, real_code) is True


@pytest.mark.parametrize("guess", ["000000", "123456", "999999", "111111"])
def test_sms_code_rejects_arbitrary_six_digit_guesses(guess):
    """Any 6-digit string used to clear the SMS factor; now it must not."""
    node = _mfa_node()
    assert node._verify_sms_code("user-with-no-challenge", guess) is False


@pytest.mark.parametrize("guess", ["000000", "123456", "999999", "111111"])
def test_email_code_rejects_arbitrary_six_digit_guesses(guess):
    """Any 6-digit string used to clear the email factor; now it must not."""
    node = _mfa_node()
    assert node._verify_email_code("user-with-no-challenge", guess) is False


def test_email_code_accepts_the_issued_challenge():
    """Positive control: a genuinely issued email code still verifies."""
    node = _mfa_node()
    node._send_email_code("user@example.net", "424242", "user-1")

    assert node._verify_email_code("user-1", "424242") is True
    # ...and is single-use.
    assert node._verify_email_code("user-1", "424242") is False


def test_email_code_rejects_another_users_challenge():
    """A code issued to one user must not clear another user's factor."""
    node = _mfa_node()
    node._send_email_code("victim@example.net", "313131", "victim")

    assert node._verify_email_code("attacker", "313131") is False


# ---------------------------------------------------------------------------
# 5. MFA delivery failures must not be reported as successful sends
# ---------------------------------------------------------------------------


def test_sms_provider_failure_raises_rather_than_claiming_delivery():
    """A configured provider that fails must not be swallowed."""
    from kailash.nodes.auth import mfa

    node = _mfa_node(
        sms_provider={
            "service": "twilio",
            "account_sid": "AC-test",
            "auth_token": "tok",
            "from_number": "+15550000000",
        }
    )

    # twilio may not be installed; either way the send fails and must raise.
    with pytest.raises(mfa.MFADeliveryError):
        node._send_sms_code("+15555550123", "424242", "user-1")


def test_email_provider_failure_raises_rather_than_claiming_delivery():
    """A configured SMTP provider that fails must not be swallowed."""
    from kailash.nodes.auth import mfa

    node = _mfa_node(
        email_provider={
            "smtp_host": "smtp.invalid",
            "smtp_port": 587,
            "username": "u",
            "password": "p",
        }
    )

    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        with pytest.raises(mfa.MFADeliveryError):
            node._send_email_code("user@example.net", "424242", "user-1")


def test_send_sms_code_reports_not_delivered_without_a_provider():
    """No provider configured => returns False, never a truthy 'sent'."""
    node = _mfa_node()
    assert node._send_sms_code("+15555550123", "424242", "user-1") is False


def test_setup_sms_does_not_claim_verification_sent_when_nothing_was_sent():
    """With no transport bound at all, setup must report failure.

    Driven through the public ``execute`` surface so the assertion covers what
    a caller actually observes.
    """
    node = _mfa_node()
    result = node.execute(
        action="setup",
        user_id="user-1",
        method="sms",
        user_phone="+15555550123",
    )

    assert result.get("verification_sent") is not True, (
        "setup reported an SMS as sent although no transport delivered it: " f"{result}"
    )
    assert result.get("success") is False


# ---------------------------------------------------------------------------
# 5b. MFA verify must never be a path to enrolment
# ---------------------------------------------------------------------------


def test_verify_does_not_auto_enrol_an_unconfigured_user_with_123456():
    """`verify` with '123456' auto-enrolled ANY user and minted a session."""
    node = _mfa_node()

    result = node.execute(
        action="verify", user_id="attacker", code="123456", method="totp"
    )

    assert (
        result.get("verified") is not True
    ), f"verify auto-enrolled an unconfigured user and verified them: {result}"
    assert result.get("session_id") is None
    assert (
        "attacker" not in node.user_mfa_data
    ), "verify enrolled a user who was never set up"


def test_verify_async_does_not_auto_enrol_an_unconfigured_user_with_123456():
    """Same bypass existed on the async verify path."""
    node = _mfa_node()

    result = asyncio.run(node._verify_mfa_async("attacker", "123456", "totp"))

    assert (
        result.get("verified") is not True
    ), f"async verify auto-enrolled an unconfigured user: {result}"
    assert result.get("session_id") is None
    assert "attacker" not in node.user_mfa_data


def test_no_hardcoded_shared_totp_secret_is_ever_installed():
    """The auto-enrolment used one shared secret for every 'test' user."""
    node = _mfa_node()

    for code in ("123456", "000000", "111111"):
        node.execute(action="verify", user_id=f"u-{code}", code=code, method="totp")

    installed = [
        m.get("totp", {}).get("secret")
        for m in (d.get("methods", {}) for d in node.user_mfa_data.values())
    ]
    assert "JBSWY3DPEHPK3PXP" not in installed


# ---------------------------------------------------------------------------
# 5c. MFA push challenges must not be reported as sent when undelivered
# ---------------------------------------------------------------------------


def test_push_challenge_raises_when_no_push_transport_configured():
    """It returned success:True after ignoring the FCM response entirely."""
    from kailash.nodes.auth import mfa

    node = _mfa_node()
    node.user_devices["user-1"] = [{"device_id": "d1", "push_token": "tok"}]

    with pytest.raises(mfa.MFADeliveryError):
        node._send_push_challenge("user-1", {"ip_address": "203.0.113.5"})

    assert (
        node.push_challenges == {}
    ), "an undelivered challenge was left pending and could be verified"


def test_push_challenge_does_not_contact_a_hardcoded_endpoint_with_a_fake_key():
    """No transport configured => no outbound request at all."""
    from kailash.nodes.auth import mfa

    node = _mfa_node()
    node.user_devices["user-1"] = [{"device_id": "d1", "push_token": "tok"}]

    with patch("requests.post") as post:
        with pytest.raises(mfa.MFADeliveryError):
            node._send_push_challenge("user-1", {})

    post.assert_not_called()


# ---------------------------------------------------------------------------
# 5d. MFA recovery must deliver the token, not hand it to the caller
# ---------------------------------------------------------------------------


def test_initiate_recovery_does_not_return_the_recovery_token():
    """The token clears the second factor; returning it defeats recovery."""
    node = _mfa_node()

    result = node.execute(
        action="initiate_recovery",
        user_id="victim",
        recovery_method="email",
        recovery_destination="victim@example.net",
    )

    assert (
        "recovery_token" not in result
    ), f"recovery token was handed straight back to the caller: {result}"


def test_initiate_recovery_requires_a_destination():
    """Without a destination there is nowhere to deliver; refuse."""
    node = _mfa_node()

    result = node.execute(
        action="initiate_recovery", user_id="victim", recovery_method="email"
    )

    assert result["success"] is False
    assert "recovery_token" not in result


def test_initiate_recovery_token_is_not_leaked_in_any_response_value():
    """Belt-and-braces: the stored token must not appear anywhere in output."""
    node = _enrolled_email_node()

    with patch.object(node, "_smtp_send", return_value=None):
        result = node.execute(
            action="initiate_recovery", user_id="victim", recovery_method="email"
        )

    stored = node.recovery_requests["victim"]["recovery_token"]
    assert stored not in str(result)


# ---------------------------------------------------------------------------
# 5e. Findings from the adversarial review of the fix itself
# ---------------------------------------------------------------------------


def _enrolled_email_node():
    """A node with a real SMTP provider and an enrolled email factor."""
    node = _mfa_node(
        email_provider={
            "smtp_host": "smtp.invalid",
            "smtp_port": 587,
            "username": "u",
            "password": "p",
        }
    )
    node.user_mfa_data["victim"] = {
        "methods": {"email": {"email": "victim@example.net", "verified": True}},
        "backup_codes": [],
    }
    return node


def test_recovery_token_is_not_redeemable_as_an_mfa_code():
    """Routing recovery through _send_email_code made the token a live factor.

    The recovery token is a 24-hour credential; storing it as temp_email_code
    would let it clear the second factor via action="verify".
    """
    node = _enrolled_email_node()

    with patch.object(node, "_smtp_send", return_value=None):
        node.execute(
            action="initiate_recovery", user_id="victim", recovery_method="email"
        )

    token = node.recovery_requests["victim"]["recovery_token"]

    assert (
        node._verify_email_code("victim", token) is False
    ), "the recovery token was accepted as a routine MFA second factor"
    assert (
        "temp_email_code" not in node.user_mfa_data["victim"]
    ), "recovery delivery registered the token as a live MFA challenge"


def test_recovery_is_delivered_to_the_enrolled_address_not_a_supplied_one():
    """A caller-chosen destination would mail the victim's token to them."""
    node = _enrolled_email_node()

    with patch.object(node, "_smtp_send", return_value=None) as smtp:
        result = node.execute(
            action="initiate_recovery",
            user_id="victim",
            recovery_method="email",
            recovery_destination="attacker@evil.tld",
        )

    assert (
        result["success"] is False
    ), f"recovery honoured an attacker-supplied destination: {result}"
    smtp.assert_not_called()


def test_recovery_uses_the_enrolled_address_when_none_is_supplied():
    """Positive control: delivery goes to the enrolled address."""
    node = _enrolled_email_node()

    with patch.object(node, "_smtp_send", return_value=None) as smtp:
        result = node.execute(
            action="initiate_recovery", user_id="victim", recovery_method="email"
        )

    assert result["success"] is True
    assert smtp.call_args[0][0] == "victim@example.net"


def test_recovery_reports_failure_when_no_transport_is_configured():
    """It must not claim 'Recovery token sent' having sent nothing."""
    node = _mfa_node()
    node.user_mfa_data["victim"] = {
        "methods": {"email": {"email": "victim@example.net"}},
        "backup_codes": [],
    }

    result = node.execute(
        action="initiate_recovery", user_id="victim", recovery_method="email"
    )

    assert result["success"] is False
    assert "victim" not in getattr(node, "recovery_requests", {})


def test_recovery_refuses_when_the_user_has_no_enrolled_destination():
    """No enrolled address => nowhere safe to deliver."""
    node = _mfa_node()

    result = node.execute(
        action="initiate_recovery", user_id="stranger", recovery_method="email"
    )

    assert result["success"] is False


def test_generate_backup_codes_does_not_enrol_an_unenrolled_user():
    """Issuing backup codes was enrolment by another name.

    The returned codes are accepted directly by verify, so this reached the
    same outcome as the removed "123456" auto-enrolment.
    """
    node = _mfa_node()

    result = node.execute(action="generate_backup_codes", user_id="attacker")

    assert result["success"] is False
    assert "backup_codes" not in result
    assert "attacker" not in node.user_mfa_data


def test_set_preference_then_backup_codes_does_not_yield_a_verified_session():
    """The round-1 guard checked key presence, which two actions create.

    set_preference creates an empty user_mfa_data entry, after which
    generate_backup_codes passed a `user_id in user_mfa_data` check and
    returned codes that _verify_mfa accepts directly.
    """
    node = _mfa_node()

    node.execute(action="set_preference", user_id="victim", preferred_method="totp")
    codes = node.execute(action="generate_backup_codes", user_id="victim")

    assert (
        codes["success"] is False
    ), f"backup codes were issued to an unenrolled user: {codes}"

    verified = node.execute(
        action="verify", user_id="victim", code="AAAAAAAA", method="totp"
    )
    assert verified.get("verified") is not True
    assert verified.get("session_id") is None


def test_recovery_refuses_an_unverified_enrolled_destination():
    """`setup` can write a destination without verification.

    If recovery trusted it, an attacker could point a victim's recovery at
    their own address and then trigger recovery.
    """
    node = _mfa_node(
        email_provider={
            "smtp_host": "smtp.invalid",
            "smtp_port": 587,
            "username": "u",
            "password": "p",
        }
    )
    node.user_mfa_data["victim"] = {
        "methods": {"email": {"email": "attacker@evil.tld", "verified": False}},
        "backup_codes": [],
    }

    with patch.object(node, "_smtp_send", return_value=None) as smtp:
        result = node.execute(
            action="initiate_recovery", user_id="victim", recovery_method="email"
        )

    assert result["success"] is False
    smtp.assert_not_called()


def test_device_trust_requires_a_trust_token():
    """A device_id is an identifier, not a secret; omitting the token gave skip_mfa."""
    node = _mfa_node()
    node.trusted_devices["user-1"] = [
        {
            "device_id": "known-device",
            "trust_token": "the-real-token",
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
    ]

    result = node._check_device_trust("user-1", "known-device", None)

    assert (
        result.get("skip_mfa") is not True
    ), f"MFA was waived without presenting the trust token: {result}"
    assert result.get("trusted") is False


def test_device_trust_accepts_the_real_token():
    """Positive control: the enrolled token still works."""
    node = _mfa_node()
    node.trusted_devices["user-1"] = [
        {
            "device_id": "known-device",
            "trust_token": "the-real-token",
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
    ]

    result = node._check_device_trust("user-1", "known-device", "the-real-token")

    assert result["trusted"] is True


def test_setup_email_does_not_claim_sent_without_a_transport():
    """The SMS path failed closed here; its email twin did not."""
    node = _mfa_node()

    result = node.execute(
        action="setup", user_id="user-1", method="email", user_email="u@example.net"
    )

    assert (
        result.get("verification_sent") is not True
    ), f"email setup reported a code as sent with no transport: {result}"
    assert result.get("success") is False
    assert "email" not in node.user_mfa_data.get("user-1", {}).get("methods", {})


def test_recovery_destination_with_non_ascii_does_not_crash():
    """compare_digest raises TypeError on non-ASCII str."""
    node = _mfa_node()
    node.user_mfa_data["victim"] = {
        "methods": {"email": {"email": "üser@example.de", "verified": True}},
        "backup_codes": [],
    }

    result = node.execute(
        action="initiate_recovery",
        user_id="victim",
        recovery_method="email",
        recovery_destination="üser@example.de",
    )

    assert isinstance(result, dict)


def test_setup_then_verify_with_issued_backup_codes_does_not_yield_a_session():
    """The upstream route that defeated every downstream enrolment gate.

    setup mints a factor AND returns backup codes for an arbitrary user_id, and
    _verify_mfa accepted a backup code with nothing verified.
    """
    node = _mfa_node()

    setup = node.execute(action="setup", user_id="victim", method="totp")
    codes = setup.get("backup_codes") or setup.get("recovery_codes") or []

    if codes:
        verified = node.execute(action="verify", user_id="victim", code=codes[0])
        assert (
            verified.get("verified") is not True
        ), f"backup codes issued at setup verified with nothing proven: {verified}"
        assert verified.get("session_id") is None


def test_setup_does_not_overwrite_a_verified_enrolment():
    """setup silently replaced a victim's authenticator and issued new codes."""
    node = _mfa_node()
    node.user_mfa_data["victim"] = {
        "methods": {"totp": {"secret": "ORIGINALSECRET", "verified": True}},
        "backup_codes": ["ORIGINAL"],
    }

    result = node.execute(action="setup", user_id="victim", method="totp")

    assert (
        result["success"] is False
    ), f"setup overwrote a verified enrolment without a step-up: {result}"
    assert node.user_mfa_data["victim"]["methods"]["totp"]["secret"] == "ORIGINALSECRET"
    assert node.user_mfa_data["victim"]["backup_codes"] == ["ORIGINAL"]


def test_setup_push_does_not_mark_itself_verified():
    """Nothing was delivered to or acknowledged by the device."""
    node = _mfa_node()

    node.execute(
        action="setup",
        user_id="user-1",
        method="push",
        device_info={"device_id": "d1", "push_token": "t"},
    )

    push = node.user_mfa_data["user-1"]["methods"]["push"]
    assert (
        push["verified"] is False
    ), "push enrolment asserted a verification that never happened"


def test_reset_requires_admin_override():
    """reset destroys the existing factor and mints a new one."""
    node = _mfa_node()
    node.user_mfa_data["victim"] = {
        "methods": {"totp": {"secret": "ORIGINALSECRET", "verified": True}},
        "backup_codes": ["ORIGINAL"],
    }

    result = node.execute(action="reset", user_id="victim", method="totp")

    assert result["success"] is False
    assert node.user_mfa_data["victim"]["methods"]["totp"]["secret"] == (
        "ORIGINALSECRET"
    )


def test_revoke_all_does_not_deadlock_and_reports_revoked_methods():
    """_revoke_mfa took a non-reentrant lock, then re-took it via a helper.

    That wedged every MFA operation in the process permanently.
    """
    import threading

    node = _mfa_node()
    node.user_mfa_data["user-1"] = {
        "methods": {"totp": {"secret": "S", "verified": True}},
        "backup_codes": [],
    }

    done = {}

    def _revoke():
        done["result"] = node.execute(
            action="revoke", user_id="user-1", method="all", admin_override=True
        )

    t = threading.Thread(target=_revoke, daemon=True)
    t.start()
    t.join(timeout=10)

    assert not t.is_alive(), "revoke deadlocked on the non-reentrant _data_lock"
    assert done["result"]["revoked_methods"] == ["totp"]

    # The lock must still be usable afterwards.
    assert node.execute(action="get_methods", user_id="user-1")["success"] is True


def test_admin_recovery_requires_admin_override():
    """The admin branch skipped every destination check and always succeeded."""
    node = _mfa_node()

    result = node.execute(
        action="initiate_recovery", user_id="anyone-at-all", recovery_method="admin"
    )

    assert result["success"] is False
    assert "anyone-at-all" not in getattr(node, "recovery_requests", {})


def test_sms_setup_failure_rolls_back_the_enrolled_destination():
    """A failed setup must not leave an attacker-chosen number enrolled."""
    node = _mfa_node(
        sms_provider={
            "service": "twilio",
            "account_sid": "AC",
            "auth_token": "t",
            "from_number": "+1555",
        }
    )

    result = node.execute(
        action="setup", user_id="victim", method="sms", user_phone="+15555550199"
    )

    assert result["success"] is False
    assert "sms" not in node.user_mfa_data.get("victim", {}).get("methods", {})


def test_delivery_errors_do_not_disclose_the_destination():
    """Provider exceptions carry the recipient address/number."""
    node = _mfa_node(
        email_provider={
            "smtp_host": "smtp.invalid",
            "smtp_port": 587,
            "username": "u",
            "password": "p",
        }
    )

    with patch(
        "smtplib.SMTP", side_effect=OSError("refused for victim@secret.example")
    ):
        result = node.execute(
            action="setup",
            user_id="user-1",
            method="email",
            user_email="victim@secret.example",
        )

    assert "secret.example" not in str(
        result
    ), f"the enrolled destination leaked through the error text: {result}"


def test_send_push_failure_returns_a_result_dict_not_an_exception():
    """Every other MFA failure returns a dict; push must not abort a workflow."""
    node = _mfa_node()
    node.user_devices["user-1"] = [{"device_id": "d1", "push_token": "tok"}]

    result = node.execute(action="send_push", user_id="user-1", auth_context={})

    assert result["success"] is False
    assert result.get("challenge_sent") is False


# ---------------------------------------------------------------------------
# 6. Sibling: API keys must not be written to logs
# ---------------------------------------------------------------------------


def test_api_key_is_not_logged_in_full(caplog):
    """The full API key was logged at INFO on every authentication."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")
    api_key = "ak_supersecretkeymaterial_0123456789abcdef"

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            node._authenticate_api_key(
                credentials={"api_key": api_key},
                user_id="user-1",
                risk_context={},
            )
        )

    assert api_key not in caplog.text, "full API key leaked into logs"


# ---------------------------------------------------------------------------
# 6b. Sibling: JWT auth must verify the signature, not just decode the payload
# ---------------------------------------------------------------------------


def _forged_jwt(claims: dict) -> str:
    """Build an unsigned token the old decoder would have accepted."""
    import base64

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps(claims).encode())
    return f"{header}.{payload}.{b64(b'not-a-real-signature')}"


def test_jwt_rejects_a_forged_unsigned_token():
    """The signature is what makes a JWT a credential."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test", jwt_config={"secret": "the-real-signing-secret"}
    )
    forged = _forged_jwt({"sub": "admin", "exp": int(time.time()) + 3600})

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": forged}, user_id="nobody", risk_context={}
        )
    )

    assert (
        result["authenticated"] is False
    ), f"a token signed with nothing authenticated as admin: {result}"


def test_jwt_rejects_a_token_signed_with_the_wrong_key():
    """Signed, well-formed, unexpired — but not by us."""
    pyjwt = pytest.importorskip("jwt")
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test", jwt_config={"secret": "the-real-signing-secret"}
    )
    attacker_token = pyjwt.encode(
        {"sub": "admin", "exp": int(time.time()) + 3600},
        "attacker-chosen-key",
        algorithm="HS256",
    )

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": attacker_token},
            user_id="nobody",
            risk_context={},
        )
    )

    assert result["authenticated"] is False


def test_jwt_accepts_a_properly_signed_token():
    """Positive control: a genuinely signed token still authenticates."""
    pyjwt = pytest.importorskip("jwt")
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    secret = "the-real-signing-secret"
    node = EnterpriseAuthProviderNode(name="eap_test", jwt_config={"secret": secret})
    good = pyjwt.encode(
        {"sub": "alice", "exp": int(time.time()) + 3600}, secret, algorithm="HS256"
    )

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": good}, user_id="nobody", risk_context={}
        )
    )

    assert result["authenticated"] is True
    assert result["user_id"] == "alice"


def test_jwt_fails_closed_when_no_verification_key_is_configured():
    """No key configured must mean refuse, not 'skip verification'."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")
    forged = _forged_jwt({"sub": "admin", "exp": int(time.time()) + 3600})

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": forged}, user_id="nobody", risk_context={}
        )
    )

    assert result["authenticated"] is False


def test_jwt_error_does_not_leak_which_check_failed():
    """A distinguishing error message is a forging oracle."""
    pyjwt = pytest.importorskip("jwt")
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    secret = "the-real-signing-secret"
    node = EnterpriseAuthProviderNode(name="eap_test", jwt_config={"secret": secret})

    expired = pyjwt.encode(
        {"sub": "alice", "exp": int(time.time()) - 10}, secret, algorithm="HS256"
    )
    bad_sig = pyjwt.encode(
        {"sub": "alice", "exp": int(time.time()) + 3600}, "wrong", algorithm="HS256"
    )

    errors = {
        asyncio.run(
            node._authenticate_jwt(
                credentials={"jwt_token": tok}, user_id="n", risk_context={}
            )
        )["error"]
        for tok in (expired, bad_sig)
    }

    assert len(errors) == 1, f"error message distinguishes failure modes: {errors}"


# ---------------------------------------------------------------------------
# 6c. Sibling: API keys must be checked against issued material
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forged",
    [
        "ak_" + "a" * 29 + "_admin",  # >=32 chars, "ak_" prefix, admin suffix
        "ak_" + "0123456789abcdef0123456789abcdef" + "_test_service",
        "ak_" + "z" * 64,
    ],
)
def test_api_key_rejects_a_self_minted_key(forged):
    """Format was the whole check; anyone could mint a valid-looking key."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test",
        api_key_store={
            hashlib.sha256(b"the-only-issued-key").hexdigest(): {"user_id": "svc"}
        },
    )

    result = asyncio.run(
        node._authenticate_api_key(
            credentials={"api_key": forged}, user_id="nobody", risk_context={}
        )
    )

    assert (
        result["authenticated"] is False
    ), f"a self-minted API key authenticated: {result}"


def test_api_key_accepts_an_issued_key_and_uses_the_stored_identity():
    """Positive control — and the identity comes from the store, not the key."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    issued = "ak_" + "issued-key-material-0123456789ab"
    node = EnterpriseAuthProviderNode(
        name="eap_test",
        api_key_store={
            hashlib.sha256(issued.encode()).hexdigest(): {"user_id": "billing-svc"}
        },
    )

    result = asyncio.run(
        node._authenticate_api_key(
            credentials={"api_key": issued}, user_id="ignored", risk_context={}
        )
    )

    assert result["authenticated"] is True
    assert result["user_id"] == "billing-svc"


def test_api_key_identity_is_not_derived_from_the_key_text():
    """The old code took user_id from the key's own trailing segment."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    issued = "ak_" + "material-0123456789abcdef0123" + "_admin"
    node = EnterpriseAuthProviderNode(
        name="eap_test",
        api_key_store={
            hashlib.sha256(issued.encode()).hexdigest(): {"user_id": "lowpriv"}
        },
    )

    result = asyncio.run(
        node._authenticate_api_key(
            credentials={"api_key": issued}, user_id="ignored", risk_context={}
        )
    )

    assert (
        result["user_id"] == "lowpriv"
    ), "identity was derived from the key text rather than the store"


def test_api_key_fails_closed_when_no_store_is_configured():
    """No store must mean refuse, not accept-anything-well-formed."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")

    result = asyncio.run(
        node._authenticate_api_key(
            credentials={"api_key": "ak_" + "a" * 40}, user_id="n", risk_context={}
        )
    )

    assert result["authenticated"] is False


def test_api_key_honours_revocation_and_expiry():
    """A revoked or expired key must stop working."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    revoked = "ak_" + "revoked-key-material-0123456789"
    expired = "ak_" + "expired-key-material-0123456789"
    node = EnterpriseAuthProviderNode(
        name="eap_test",
        api_key_store={
            hashlib.sha256(revoked.encode()).hexdigest(): {
                "user_id": "svc",
                "revoked": True,
            },
            hashlib.sha256(expired.encode()).hexdigest(): {
                "user_id": "svc",
                "expires_at": time.time() - 1,
            },
        },
    )

    for key in (revoked, expired):
        result = asyncio.run(
            node._authenticate_api_key(
                credentials={"api_key": key}, user_id="n", risk_context={}
            )
        )
        assert result["authenticated"] is False


def test_jwt_without_a_sub_claim_does_not_authenticate_as_the_caller():
    """A signed token with no subject fell back to the caller's user_id.

    Any other token signed with the same key (a reset token, a service token)
    became an impersonation primitive.
    """
    pyjwt = pytest.importorskip("jwt")
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    secret = "shared-signing-secret"
    node = EnterpriseAuthProviderNode(name="eap_test", jwt_config={"secret": secret})
    subjectless = pyjwt.encode(
        {"exp": int(time.time()) + 3600, "purpose": "password-reset"},
        secret,
        algorithm="HS256",
    )

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": subjectless},
            user_id="admin",
            risk_context={},
        )
    )

    assert (
        result["authenticated"] is False
    ), f"a subject-less token authenticated as the caller's user_id: {result}"


def test_jwt_public_key_cannot_be_used_with_an_hmac_algorithm():
    """Otherwise anyone holding the PUBLIC key can mint HS256 tokens."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test",
        jwt_config={"public_key": "not-a-pem-blob", "algorithms": ["HS256"]},
    )

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": "a.b.c"}, user_id="n", risk_context={}
        )
    )

    assert result["authenticated"] is False


def test_api_key_record_without_a_user_id_does_not_authenticate():
    """An operator typo must not become an impersonation primitive."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    issued = "ak_" + "material-with-no-user-id-01234567"
    node = EnterpriseAuthProviderNode(
        name="eap_test",
        api_key_store={hashlib.sha256(issued.encode()).hexdigest(): {"note": "oops"}},
    )

    result = asyncio.run(
        node._authenticate_api_key(
            credentials={"api_key": issued}, user_id="admin", risk_context={}
        )
    )

    assert result["authenticated"] is False


def test_api_key_prefix_is_not_logged(caplog):
    """api_key[:6] exposed 3 characters of real secret on every attempt."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")
    api_key = "ak_SECRETMATERIAL0123456789abcdef"

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            node._authenticate_api_key(
                credentials={"api_key": api_key}, user_id="n", risk_context={}
            )
        )

    assert api_key[:6] not in caplog.text
    assert "SECRET" not in caplog.text


# ---------------------------------------------------------------------------
# 6d. Sibling: permissions must not be inferred from the user_id's text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_id",
    ["admin", "admin.intern", "sysadmin-contractor", "ADMIN", "not-an-admin"],
)
def test_permissions_are_not_granted_by_a_username_containing_admin(user_id):
    """Any user_id containing 'admin' used to receive delete+admin."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")

    perms = asyncio.run(node._get_user_permissions(user_id))

    assert (
        "admin" not in perms
    ), f"user_id={user_id!r} was granted admin from its own text: {perms}"
    assert "delete" not in perms


@pytest.mark.parametrize("user_id", ["manager", "product.manager", "middle-manager"])
def test_permissions_are_not_granted_by_a_username_containing_manager(user_id):
    """Same escalation, one rung lower."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")

    perms = asyncio.run(node._get_user_permissions(user_id))

    assert "write" not in perms, f"user_id={user_id!r} was granted write: {perms}"


def test_permissions_come_from_the_configured_mapping():
    """Positive control: an explicitly granted user still gets their rights."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test",
        user_permissions={"alice": ["read", "write", "delete", "admin"]},
    )

    assert asyncio.run(node._get_user_permissions("alice")) == [
        "read",
        "write",
        "delete",
        "admin",
    ]
    assert asyncio.run(node._get_user_permissions("admin.intern")) == ["read"]


def test_authorize_refuses_admin_action_for_a_username_containing_admin():
    """The escalation observed through the authorization surface."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")

    result = asyncio.run(
        node._authorize(
            user_id="admin.intern",
            session_id=None,
            resource="billing",
            permissions=["admin"],
            risk_context={},
        )
    )

    assert result["authorized"] is False


def test_authorize_requires_a_session():
    """Without a session, user_id is just a string the caller typed."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test", user_permissions={"alice": ["read", "write"]}
    )

    result = asyncio.run(
        node._authorize(
            user_id="alice",
            session_id=None,
            resource="billing",
            permissions=["read"],
            risk_context={},
        )
    )

    assert result["authorized"] is False
    assert result["reason"] == "session_required"


def test_authorize_does_not_treat_an_empty_permission_request_as_a_pass():
    """`permissions=[]` produced no missing permissions => authorized=True."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test")

    result = asyncio.run(
        node._authorize(
            user_id="anyone",
            session_id=None,
            resource="billing",
            permissions=[],
            risk_context={},
        )
    )

    assert result["authorized"] is False


# ---------------------------------------------------------------------------
# 6e. The session must belong to the principal the CREDENTIAL asserts
# ---------------------------------------------------------------------------


def test_authenticate_does_not_mint_a_session_for_a_caller_chosen_user_id():
    """Verifying a credential then honouring a different requested identity.

    An attacker holding any valid credential for 'alice' could request
    user_id='admin' and receive an admin session.
    """
    pyjwt = pytest.importorskip("jwt")
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    secret = "signing-secret"
    node = EnterpriseAuthProviderNode(
        name="eap_test",
        enabled_methods=["jwt"],
        adaptive_auth_enabled=False,
        risk_assessment_enabled=False,
        jwt_config={"secret": secret},
    )
    alice_token = pyjwt.encode(
        {"sub": "alice", "exp": int(time.time()) + 3600}, secret, algorithm="HS256"
    )

    # SessionManagementNode has no execute_async (a separate, pre-existing
    # defect), so the session call is stubbed to record who the session is for.
    created_for = {}

    async def _fake_create(**kwargs):
        created_for.update(kwargs)
        return {"session_id": "sess-1"}

    node.session_node.execute_async = _fake_create

    result = asyncio.run(
        node._authenticate(
            auth_method="jwt",
            credentials={"jwt_token": alice_token},
            user_id="admin",
            risk_context={},
            auth_id="auth-1",
        )
    )

    assert (
        result["user_id"] == "alice"
    ), f"session minted for the caller-supplied identity, not the credential's: {result}"
    assert (
        created_for["user_id"] == "alice"
    ), f"the session itself was created for the wrong principal: {created_for}"


def test_authenticate_refuses_a_method_that_asserts_no_principal():
    """An opportunistic override fell back to the caller's user_id.

    The directory methods return "username" rather than "user_id", and social
    can return user_id=None, so an attacker authenticating as themselves could
    request user_id="admin".
    """
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test",
        enabled_methods=["directory"],
        adaptive_auth_enabled=False,
        risk_assessment_enabled=False,
    )

    async def _anon_auth(*args, **kwargs):
        # authenticated, but naming no principal at all
        return {"authenticated": True, "directory_type": "ldap"}

    node._perform_authentication = _anon_auth

    result = asyncio.run(
        node._authenticate(
            auth_method="directory",
            credentials={"username": "lowpriv", "password": "p"},
            user_id="admin",
            risk_context={},
            auth_id="auth-1",
        )
    )

    assert (
        result["authenticated"] is False
    ), f"a principal-less authentication minted a session for 'admin': {result}"


def test_authorize_reads_the_session_subject_from_session_data():
    """The subject is nested under session_data; a top-level read always missed."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test", user_permissions={"admin": ["admin"], "attacker": ["read"]}
    )

    async def _validate(**kwargs):
        # The real SessionManagementNode shape: subject nested, not top-level.
        return {"success": True, "valid": True, "session_data": {"user_id": "attacker"}}

    node.session_node.execute_async = _validate

    result = asyncio.run(
        node._authorize(
            user_id="admin",  # caller's claim, must be ignored
            session_id="sess-1",
            resource="billing",
            permissions=["admin"],
            risk_context={},
        )
    )

    assert (
        result["authorized"] is False
    ), f"the caller's claimed user_id was used instead of the session subject: {result}"


@pytest.mark.parametrize("algorithms", [["none"], ["none", "RS256"], [], "HS256junk"])
def test_jwt_rejects_unsupported_algorithm_configuration(algorithms):
    """A denylist bucketed 'none' as asymmetric and let it through the check.

    Asserts the CONFIGURATION is rejected, not merely that a malformed token
    fails: the old code reached pyjwt with alg='none' configured and refused
    only because the token did not parse, which is a different guarantee.
    """
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test",
        jwt_config={"public_key": "not-a-pem-blob", "algorithms": algorithms},
    )

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": "a.b.c"}, user_id="n", risk_context={}
        )
    )

    assert result["authenticated"] is False
    assert (
        "algorithms" in result["error"]
    ), f"the algorithm configuration was not itself rejected: {result}"


def test_jwt_refuses_when_both_secret_and_public_key_are_set():
    """Ambiguous key material must not silently pick one."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test",
        jwt_config={"secret": "s", "public_key": "p", "algorithms": ["HS256"]},
    )

    result = asyncio.run(
        node._authenticate_jwt(
            credentials={"jwt_token": "a.b.c"}, user_id="n", risk_context={}
        )
    )

    assert result["authenticated"] is False
    assert "public_key" in result["error"]


# ---------------------------------------------------------------------------
# 6f. Directory search fallback must be gated like the credential table
# ---------------------------------------------------------------------------


def test_directory_search_does_not_fabricate_users_when_ldap_fails():
    """The sample roster feeds role/permission mapping that grants admin."""
    node = _directory_node()

    with patch.object(
        node, "_ldap_directory_search", side_effect=ConnectionError("unreachable")
    ):
        results = asyncio.run(node._simulate_directory_search("users", {}))

    assert (
        results == []
    ), f"fabricated directory users were returned on LDAP failure: {results}"


def test_directory_search_fallback_still_available_when_opted_in():
    """Positive control: dev/test use survives the gate."""
    node = _directory_node(allow_insecure_credential_fallback=True)

    with patch.object(
        node, "_ldap_directory_search", side_effect=ConnectionError("unreachable")
    ):
        results = asyncio.run(node._simulate_directory_search("users", {}))

    assert len(results) > 0


# ---------------------------------------------------------------------------
# 7. Sibling: MFA step-up must not be waived by identifier content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_id",
    [
        "test.attacker",  # matched the old `"test." in user_id`
        "attacker@company.com",  # matched the old `"@company.com" in user_id`
        "test_attacker",  # matched the old `"test_" in user_id`
    ],
)
def test_step_up_is_not_waived_by_a_chosen_user_id(user_id):
    """A principal must not opt out of MFA by naming themselves 'test.*'."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(name="eap_test", enabled_methods=["sso", "mfa"])

    factors = asyncio.run(
        node._determine_additional_factors(
            user_id=user_id,
            risk_score=0.85,  # high risk: MFA is required
            primary_method="sso",
            primary_auth_result={},
        )
    )

    assert "mfa" in factors, (
        f"MFA step-up was waived for user_id={user_id!r} at risk 0.85 — "
        "identifier content must not relax authentication requirements"
    )


def test_step_up_is_not_waived_by_a_chosen_api_key():
    """Same, via the API-key-derived identifier."""
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode(
        name="eap_test", enabled_methods=["api_key", "mfa"]
    )

    factors = asyncio.run(
        node._determine_additional_factors(
            user_id="attacker",
            risk_score=0.1,
            primary_method="api_key",
            primary_auth_result={"user_id": "test_service"},
        )
    )

    assert "mfa" in factors, "API-key auth waived MFA for a 'test'-named key"


# ---------------------------------------------------------------------------
# 8. Sibling: the directory credential table must fail closed by default
# ---------------------------------------------------------------------------


def _directory_node(**connection_config):
    from kailash.nodes.auth.directory_integration import DirectoryIntegrationNode

    return DirectoryIntegrationNode(
        name="dir_test",
        directory_type="ldap",
        connection_config={
            "server": "ldap://directory.invalid:389",
            **connection_config,
        },
    )


@pytest.mark.parametrize(
    "username,password",
    [
        ("unknown_user", "password123"),  # default password, ANY username
        ("jdoe", "user_password"),  # a table entry
        ("admin.user", "password123"),
    ],
)
def test_directory_credential_fallback_fails_closed_by_default(username, password):
    """The built-in table must not authenticate unless explicitly enabled."""
    node = _directory_node()
    result = node._fallback_directory_auth(username, password)

    assert result["authenticated"] is False
    assert result["reason"] == "directory_unavailable"


def test_directory_fallback_still_works_when_explicitly_enabled():
    """Positive control: the opt-in path is unchanged for dev/test use."""
    node = _directory_node(allow_insecure_credential_fallback=True)
    result = node._fallback_directory_auth("jdoe", "user_password")

    assert result["authenticated"] is True


def test_simulation_is_not_selected_by_the_server_hostname():
    """A real directory named 'test.*' must still be contacted for real.

    Simulation used to be inferred from the server URL containing "test." or
    starting with "ldap://test", so a production directory with such a name was
    silently never contacted.
    """
    node = _directory_node()
    node.connection_config["server"] = "ldap://test.corp.example.net:389"

    # No explicit simulate_directory opt-in => the real connector is used, and
    # because the host does not resolve the attempt FAILS rather than quietly
    # succeeding against the simulated backend.
    result = asyncio.run(node._test_connection())

    assert result["connection_status"] != "connected", (
        "a 'test.'-named server was routed to simulation and reported a "
        f"successful connection it never made: {result}"
    )
    assert "Simulated" not in str(
        result.get("server_info", {})
    ), f"simulation was selected from the hostname: {result}"


def test_unreachable_directory_does_not_authenticate():
    """An attacker who makes the directory unreachable must not get in.

    ``_simulate_directory_auth`` falls back when the real bind raises; with the
    fallback disabled that path must NOT yield an authenticated result.
    """
    node = _directory_node()

    with patch.object(
        node, "_ldap_directory_auth", side_effect=ConnectionError("unreachable")
    ):
        result = asyncio.run(node._simulate_directory_auth("anyone", "password123"))

    assert result["authenticated"] is False


# Auto-enrolment and push-delivery coverage lives in sections 5b/5c above.
