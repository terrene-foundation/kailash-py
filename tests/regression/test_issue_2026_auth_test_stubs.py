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
import logging
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
        "setup reported an SMS as sent although no transport delivered it: "
        f"{result}"
    )
    assert result.get("success") is False


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
