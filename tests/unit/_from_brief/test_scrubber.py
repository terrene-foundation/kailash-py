# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the credential scrubber.

Per ``rules/security.md`` § "No secrets in logs" and ``rules/testing.md``
§ "Behavioral Regression Tests Over Source-Grep", these tests assert
the function's behavior — they do NOT grep the source. Each test
constructs an input shaped like the failure mode the scrubber MUST
catch and asserts that the credential bytes are absent from the
output.
"""

from __future__ import annotations

import pytest

from kailash._from_brief.scrubber import scrub_brief

# Sentinel credentials. These exact byte sequences MUST be absent from
# every scrubbed output. Defined once at module scope so the assertions
# can rely on grep-like equality without re-typing.
SECRET_PASSWORD = "hunter2-shh"
SECRET_API_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
SECRET_BEARER_TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789"
SECRET_AWS_KEY = "AKIA1234567890ABCDEF"


class TestApiKeyScrubbing:
    """The OpenAI/Anthropic ``sk-`` API-key shape is replaced."""

    def test_sk_proj_key_redacted(self):
        brief = f"Use the API key {SECRET_API_KEY} when calling the service."
        scrubbed = scrub_brief(brief)
        assert SECRET_API_KEY not in scrubbed
        assert "[REDACTED]" in scrubbed

    def test_sk_ant_key_redacted(self):
        key = "sk-ant-api03-XXXXXXXXXXXXXXXXXXXX-deadbeef"
        scrubbed = scrub_brief(f"ANTHROPIC_API_KEY={key}")
        assert key not in scrubbed

    def test_short_sk_literal_in_prose_is_not_clobbered(self):
        # ``sk-1`` is 4 chars; should NOT match the 20-char floor.
        brief = "Reference the protocol abbreviation sk-1 in section 2."
        scrubbed = scrub_brief(brief)
        assert "sk-1" in scrubbed


class TestUrlCredentialScrubbing:
    """URLs with embedded ``user:password@host`` are masked."""

    def test_postgres_url_redacted(self):
        url = f"postgres://admin:{SECRET_PASSWORD}@db.internal:5432/myapp"
        brief = f"Connect to {url} and read the users table."
        scrubbed = scrub_brief(brief)
        assert SECRET_PASSWORD not in scrubbed
        assert "admin" not in scrubbed
        assert "db.internal:5432" in scrubbed
        assert "myapp" in scrubbed

    def test_mysql_url_redacted(self):
        url = f"mysql://root:{SECRET_PASSWORD}@localhost:3306/mydb"
        scrubbed = scrub_brief(f"DATABASE_URL={url}")
        assert SECRET_PASSWORD not in scrubbed
        assert "localhost:3306" in scrubbed

    def test_redis_url_redacted(self):
        url = f"redis://default:{SECRET_PASSWORD}@cache:6379/0"
        scrubbed = scrub_brief(f"use {url} as the cache")
        assert SECRET_PASSWORD not in scrubbed
        assert "cache:6379" in scrubbed


class TestBearerTokenScrubbing:
    """``Bearer <token>`` headers have the token replaced, prefix kept."""

    def test_bearer_token_redacted(self):
        brief = f"Set Authorization: Bearer {SECRET_BEARER_TOKEN} " f"on every request."
        scrubbed = scrub_brief(brief)
        assert SECRET_BEARER_TOKEN not in scrubbed
        # Bearer prefix is preserved so the LLM still knows the shape.
        assert "Bearer [REDACTED]" in scrubbed


class TestAwsAccessKeyScrubbing:
    """AWS access-key shapes (``AKIA…``) are replaced."""

    def test_aws_access_key_redacted(self):
        brief = f"AWS_ACCESS_KEY_ID={SECRET_AWS_KEY}"
        scrubbed = scrub_brief(brief)
        assert SECRET_AWS_KEY not in scrubbed


class TestKvSecretScrubbing:
    """``password=<value>`` and ``api_key=<value>`` kv-pairs are redacted."""

    def test_password_kv_redacted(self):
        brief = f"set password={SECRET_PASSWORD} in the config"
        scrubbed = scrub_brief(brief)
        assert SECRET_PASSWORD not in scrubbed
        assert "password=[REDACTED]" in scrubbed

    def test_api_key_kv_redacted(self):
        brief = "set api_key=verysecretvaluehere in production"
        scrubbed = scrub_brief(brief)
        assert "verysecretvaluehere" not in scrubbed
        assert "api_key=[REDACTED]" in scrubbed

    def test_token_kv_redacted(self):
        brief = "use token=mytoken123secret to authenticate"
        scrubbed = scrub_brief(brief)
        assert "mytoken123secret" not in scrubbed


class TestNoOpOnCleanBrief:
    """Briefs containing no credentials pass through unchanged."""

    def test_plain_prose_unchanged(self):
        brief = (
            "Build a workflow that reads CSV files from disk and writes "
            "the deduplicated rows to a parquet output."
        )
        assert scrub_brief(brief) == brief

    def test_empty_string_unchanged(self):
        assert scrub_brief("") == ""

    def test_prose_with_url_but_no_credentials_unchanged(self):
        brief = "Fetch data from https://api.example.com/v1/users."
        assert scrub_brief(brief) == brief


class TestIdempotency:
    """scrub(scrub(x)) == scrub(x) for every credential shape."""

    @pytest.mark.parametrize(
        "brief",
        [
            f"connect to postgres://admin:{SECRET_PASSWORD}@db/app",
            f"use API key {SECRET_API_KEY} for auth",
            f"Authorization: Bearer {SECRET_BEARER_TOKEN}",
            f"AWS_ACCESS_KEY_ID={SECRET_AWS_KEY}",
            f"password={SECRET_PASSWORD} api_key={SECRET_API_KEY}",
            "no credentials here",
            "",
        ],
    )
    def test_idempotent(self, brief: str):
        once = scrub_brief(brief)
        twice = scrub_brief(once)
        assert once == twice


# ---------------------------------------------------------------------------
# SEC-3 — extended credential corpus regression tests
# ---------------------------------------------------------------------------
#
# Closes the credential-corpus gap surfaced at
# workspaces/from-brief-1125/04-validate/round-02-security.md:78-103.
# Each test asserts (a) the matched substring is replaced by [REDACTED]
# AND (b) the raw token does NOT survive in the scrubbed output.

# SEC-3 sample tokens — synthetic-looking, intentionally shaped to match
# the published vendor patterns so the test exercises the real regex
# alternation, NOT a tame "abc123" placeholder. None of these are valid
# upstream credentials.
GITHUB_PAT_CLASSIC = "ghp_" + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
GITHUB_PAT_FINEGRAINED = "github_pat_" + "11ABCDEFG0aaaaaaaaaaaa_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
GOOGLE_API_KEY = "AIza" + "SyA-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # 4+35=39
SLACK_BOT_TOKEN = "xoxb" + "-1234567890-abcdef"
JWT_SAMPLE = (
    "ey" + "JhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJK"
)
STRIPE_SECRET = "sk_" + "test_abcdefghijklmnopqrstuvwxyz0123"
TWILIO_TOKEN = "SK" + "0123456789abcdef0123456789abcdef"


class TestSec3GithubToken:
    def test_github_classic_pat_redacted(self):
        brief = f"my token is {GITHUB_PAT_CLASSIC}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert GITHUB_PAT_CLASSIC not in out

    def test_github_finegrained_pat_redacted(self):
        brief = f"export GH_TOKEN={GITHUB_PAT_FINEGRAINED}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert GITHUB_PAT_FINEGRAINED not in out


class TestSec3GoogleApiKey:
    def test_google_api_key_redacted(self):
        brief = f"use {GOOGLE_API_KEY} for Maps API"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert GOOGLE_API_KEY not in out


class TestSec3SlackToken:
    def test_slack_bot_token_redacted(self):
        brief = f"slack hook uses {SLACK_BOT_TOKEN}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert SLACK_BOT_TOKEN not in out


class TestSec3JwtToken:
    def test_jwt_redacted(self):
        brief = f"Authorization header value: {JWT_SAMPLE}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert JWT_SAMPLE not in out


class TestSec3StripeKey:
    def test_stripe_secret_redacted(self):
        brief = f"STRIPE_SECRET_KEY={STRIPE_SECRET}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert STRIPE_SECRET not in out


class TestSec3TwilioToken:
    def test_twilio_token_redacted(self):
        brief = f"twilio auth token {TWILIO_TOKEN}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert TWILIO_TOKEN not in out


class TestSec3LegacyCorpusUnregressed:
    """Pre-SEC-3 credential corpus continues to scrub after extension."""

    def test_openai_key_still_scrubbed(self):
        brief = f"openai key {SECRET_API_KEY}"
        out = scrub_brief(brief)
        assert "[REDACTED]" in out
        assert SECRET_API_KEY not in out

    def test_aws_key_still_scrubbed(self):
        brief = f"AWS_ACCESS_KEY_ID={SECRET_AWS_KEY}"
        out = scrub_brief(brief)
        assert SECRET_AWS_KEY not in out


def test_fixture_scanner_flags_slack_token_in_temp_fixture(tmp_path, monkeypatch):
    """SEC-3 fixture-scanner mirror: a temp fixture file with a new
    pattern MUST be flagged by the regression scanner.

    Uses ``tmp_path`` so no real fixture is touched; the temp directory
    is monkey-patched onto FIXTURE_DIR for the duration of the test.
    """
    from tests.regression.from_brief import test_fixtures_no_secrets as mod

    monkeypatch.setattr(mod, "FIXTURE_DIR", tmp_path)
    leak_file = tmp_path / "test_temp_leak.yaml"
    leak_file.write_text("token: xoxb-12345-fakebut-shaped-like-slack")
    with pytest.raises(mod.BriefFixtureLeakError) as exc:
        mod.test_from_brief_fixtures_contain_no_credentials()
    assert "slack" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# SEC-4 — URL password pre-encoding regression
# ---------------------------------------------------------------------------


def test_scrub_brief_masks_password_with_at_sign():
    """SEC-4: a raw ``@`` in the password (``hunt@er#1``) used to defeat
    the URL regex; the pre-encoder pass converts ``@``/``#`` to percent
    encodings before the regex runs, so the URL is now well-formed and
    the masker hides the credential. Per
    workspaces/from-brief-1125/04-validate/round-02-security.md:108-124.
    """
    brief = "connect to postgres://admin:hunt@er#1@db.example.com/app"
    scrubbed = scrub_brief(brief)
    # The raw password substring MUST NOT survive in the scrubbed output.
    assert "hunt@er#1" not in scrubbed
    assert "hunter" not in scrubbed  # noqa: SIM118 — substring check
    # The mask form is preserved (***@host:port/path) and the database
    # host survives so the LLM can still reason about intent.
    assert "***@db.example.com" in scrubbed


def test_scrub_brief_masks_password_with_question_mark():
    """SEC-4: ``?`` inside a password used to terminate URL prematurely
    (urlparse interprets it as start-of-query)."""
    brief = "url postgres://admin:s3cret?val@db/app for ops"
    scrubbed = scrub_brief(brief)
    assert "s3cret?val" not in scrubbed
    assert "***@db" in scrubbed


# ---------------------------------------------------------------------------
# SEC-7 — brief length cap regression
# ---------------------------------------------------------------------------


def test_scrub_brief_rejects_oversized_brief():
    """SEC-7: a brief exceeding MAX_BRIEF_LENGTH raises typed
    BriefInterpretationError(malformed=True) BEFORE any regex / LLM
    runs. Per workspaces/from-brief-1125/04-validate/round-02-security.md:168-175.
    """
    from kailash._from_brief.exceptions import BriefInterpretationError
    from kailash._from_brief.scrubber import MAX_BRIEF_LENGTH

    oversized = "x" * (MAX_BRIEF_LENGTH + 100)
    with pytest.raises(BriefInterpretationError) as exc:
        scrub_brief(oversized)
    assert exc.value.malformed


def test_scrub_brief_accepts_under_cap_brief():
    """Regression guard: a brief just under the cap MUST pass."""
    from kailash._from_brief.scrubber import MAX_BRIEF_LENGTH

    under_cap = "x" * (MAX_BRIEF_LENGTH - 1000)
    out = scrub_brief(under_cap)
    assert out == under_cap  # no credentials, idempotent passthrough
