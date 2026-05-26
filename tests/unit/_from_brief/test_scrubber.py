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
