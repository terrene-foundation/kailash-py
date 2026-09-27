# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``kailash.utils.url_credentials.mask_error_text`` (#1840).

``mask_error_text`` is the arbitrary-string companion to ``mask_url``: it
scrubs credentials out of an OPAQUE error/log string that may embed a
credential-bearing URL anywhere inside it (a rendered exception ``{e}``).

The load-bearing regression these tests guard is the DOTALL / embedded-newline
invariant: database/provider drivers render a credential value's embedded
newline literally into the error text, and a naive ``\\S``/``[^\\s]``-based
scrubber stops at the first ``\\n`` and leaks the credential tail.
"""

import pytest

from kailash.utils.url_credentials import mask_error_text

SECRET = "s3cr3t"
TOKEN = "abc123token"


class TestUserinfoMasking:
    """``scheme://user:password@host`` userinfo masking in arbitrary text."""

    def test_masks_userinfo_in_error_prose(self):
        raw = f"connection failed: postgresql://admin:{SECRET}@db.internal:5432/app"
        out = mask_error_text(raw)
        assert SECRET not in out
        assert "admin" not in out
        assert "postgresql://***@db.internal:5432/app" in out

    def test_masks_userinfo_mid_sentence(self):
        raw = f"Error while dialing wss://user:{SECRET}@host:8080/mcp — timeout"
        out = mask_error_text(raw)
        assert SECRET not in out
        assert "wss://***@host:8080/mcp" in out
        assert out.endswith("— timeout")

    def test_masks_password_only_userinfo(self):
        # redis-style scheme://:password@host (empty user)
        raw = f"redis error: redis://:{SECRET}@cache:6379/0"
        out = mask_error_text(raw)
        assert SECRET not in out
        assert "redis://***@cache:6379/0" in out

    def test_bare_at_reference_not_masked(self):
        # git@host style (no scheme://, no user:pass) must be left intact.
        raw = "clone from git@github.com:org/repo.git failed"
        assert mask_error_text(raw) == raw

    def test_first_at_terminates_userinfo(self):
        raw = f"http://u:{SECRET}@host.example/path?x=1 returned 500"
        out = mask_error_text(raw)
        assert SECRET not in out
        assert "http://***@host.example/path?x=1" in out

    def test_raw_at_in_password_masked_whole_not_split(self):
        # A password containing a raw '@' must be masked WHOLE (bind to the
        # LAST '@' before the host), not split at its first '@' leaving a tail.
        raw = "OSError: postgresql://svc:S3cr3tP@ss@db.prod:5432/orders"
        out = mask_error_text(raw)
        assert "S3cr3tP" not in out
        assert "@ss@" not in out  # the tail after the raw '@' must not survive
        assert "postgresql://***@db.prod:5432/orders" in out


class TestQueryParamMasking:
    """Sensitive query parameter (``?token=`` / ``&password=``) masking."""

    def test_masks_token_query_param(self):
        raw = f"HTTP 401 for https://svc.example/api?token={TOKEN}"
        out = mask_error_text(raw)
        assert TOKEN not in out
        assert "token=***" in out

    def test_masks_multiple_sensitive_params(self):
        raw = f"bad url http://h/db?password={SECRET}&api_key={TOKEN}&sslmode=require"
        out = mask_error_text(raw)
        assert SECRET not in out
        assert TOKEN not in out
        assert "password=***" in out
        assert "api_key=***" in out
        # Non-sensitive param preserved verbatim.
        assert "sslmode=require" in out

    def test_non_sensitive_query_param_preserved(self):
        raw = "connect http://host/db?replicaSet=rs0&timeout=30"
        assert mask_error_text(raw) == raw

    def test_public_key_not_masked(self):
        # is_sensitive_query_key: public_key is NOT a secret (asymmetric public).
        raw = "cfg http://host/x?public_key=AAAApub"
        out = mask_error_text(raw)
        assert "public_key=AAAApub" in out


class TestDotAllNewlineInvariant:
    """The #1840 regression: a credential value with an EMBEDDED newline.

    Drivers render an embedded ``\\n`` in a credential literally. A scrubber
    whose value class excludes newlines (``\\S`` / ``[^\\s]``) stops at the
    ``\\n`` and leaks the tail. ``mask_error_text`` compiles with re.DOTALL and
    bounds the password by ``@`` (a negated class matches newlines), so the
    WHOLE credential span — across the newline — is masked.
    """

    def test_embedded_newline_in_password_fully_masked(self):
        # Password contains a literal newline: "sec\nret".
        raw = "psql fatal: postgresql://admin:sec\nret@db.host:5432/app"
        out = mask_error_text(raw)
        # The tail after the newline ("ret") MUST NOT survive.
        assert "ret@" not in out
        assert "sec\nret" not in out
        assert "postgresql://***@db.host:5432/app" in out

    def test_embedded_newline_in_query_value_fully_masked(self):
        raw = "http error http://h/db?sslpassword=sec\nret&sslmode=require"
        out = mask_error_text(raw)
        assert "sec\nret" not in out
        assert "ret" not in out.split("sslmode", 1)[0]
        assert "sslpassword=***" in out
        assert "sslmode=require" in out

    def test_naive_scrubber_would_leak_but_ours_does_not(self):
        # Explicit demonstration that a \S-terminated match would leak "ret".
        import re

        raw = "postgresql://admin:sec\nret@db/app"
        naive = re.sub(r"(\w+://)[^\s]*@", r"\1***@", raw)
        # The naive scrubber leaks because [^\s] stops at the newline.
        assert "ret@" in naive  # proves the failure mode the DOTALL guard fixes
        # Our helper does not leak.
        assert "ret@" not in mask_error_text(raw)


class TestNonCredentialAndEdgeCases:
    def test_clean_url_passthrough(self):
        raw = "ok: postgresql://localhost:5432/db connected"
        assert mask_error_text(raw) == raw

    def test_plain_text_passthrough(self):
        raw = "Connection refused after 3 retries"
        assert mask_error_text(raw) == raw

    def test_none_returns_empty_string(self):
        assert mask_error_text(None) == ""

    def test_empty_string(self):
        assert mask_error_text("") == ""

    def test_non_string_coerced(self):
        # mask_error_text(some_exception) must work (coerces via str()).
        exc = RuntimeError("failed https://u:p3ss@host/x?token=t0k")
        out = mask_error_text(exc)
        assert "p3ss" not in out
        assert "t0k" not in out
        assert "https://***@host/x?token=***" in out


def test_before_after_demo(capsys):
    """Human-readable before/after receipt (printed with -s)."""
    raw = (
        "OSError: could not connect to "
        "postgresql://svc_user:S3cr3tP@ss@db.prod:5432/orders"
        "?password=S3cr3tP@ss"
    )
    masked = mask_error_text(raw)
    print("\n--- BEFORE (raw {e}) ---\n" + raw)
    print("\n--- AFTER (mask_error_text) ---\n" + masked)
    assert "S3cr3tP" not in masked


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v", "-s"])


@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_parser_normalized_controls_masked_before_diagnostic_flatten(control):
    raw = f"connect http://admin:sec{control}ret@host/api?token=sec{control}ret&mode=fast failed"
    assert (
        mask_error_text(raw) == "connect http://***@host/api?token=***&mode=fast failed"
    )
    plain = f"connect http://host/api?mode=fast failed{control}retry later"
    assert mask_error_text(plain) == plain


def test_query_only_masker_preserves_boundaries_and_literal_placeholder():
    from kailash.utils.url_credentials import mask_error_query_params

    assert (
        mask_error_query_params("?token=secret diagnostic&mode=fast")
        == "?token=*** diagnostic&mode=fast"
    )
    assert (
        mask_error_query_params("?token=secret&mode=fast", placeholder=r"\1")
        == r"?token=\1&mode=fast"
    )


@pytest.mark.parametrize("delim", [",", "}", "]", ":"])
def test_quotes_inside_json_credentials_are_data_not_field_boundaries(delim):
    import json

    secret = 'short"' + delim + "credentialTAIL42"
    url = "postgresql://user:" + secret + "@db.host/app"
    raw = json.dumps({"url": url, "message": "connection refused"})
    result = mask_error_text(raw)
    assert "credentialTAIL42" not in result
    decoded = json.loads(result)
    assert decoded == {
        "url": "postgresql://***@db.host/app",
        "message": "connection refused",
    }


def test_json_raw_spans_preserve_duplicate_keys_and_mask_sensitive_values():
    import json

    raw = ' { "url" : "http://u:secret@host/api", "url" : "keep", "password" : 1234, "token": {"nested":"secret"} } '
    result = mask_error_text(raw)
    assert result.startswith(" { ") and result.endswith(" } ")
    assert result.count('"url"') == 2
    assert '"url" : "keep"' in result
    assert json.loads(result) == {"url": "keep", "password": "***", "token": "***"}
    assert "secret" not in result


def test_encoded_separator_and_embedded_at_do_not_expose_password_suffix():
    assert mask_error_text("http://user:secret%40host/api") == "http://***%40host/api"
    assert mask_error_text("http://user:sec%40ret@host/api") == "http://***@host/api"
    assert (
        mask_error_text("http://user:" + "x" * 300 + "@tail@host/api")
        == "http://***@host/api"
    )


def test_json_too_deep_to_segment_is_redacted():
    raw = "[" * 2000 + '"http://u:secret@host/api"' + "]" * 2000
    assert "secret" not in mask_error_text(raw)


@pytest.mark.parametrize(
    "prefix,unit", [("", "a"), ("http://", "a:"), ("http://", "http://a:\n")]
)
def test_public_scanner_failure_cost_scales_with_input(prefix, unit):
    import statistics
    import time

    def elapsed(size):
        raw = prefix + unit * size
        positive = raw + ("@host" if prefix else "://u:secret@host")
        assert mask_error_text(positive) != positive
        samples = []
        for _ in range(5):
            start = time.process_time()
            for _ in range(10):
                assert mask_error_text(raw) == raw
            samples.append(time.process_time() - start)
        return statistics.median(samples)

    small = elapsed(1000)
    large = elapsed(8000)
    assert large / small < 25, (small, large)


@pytest.mark.parametrize("delimiter", [";", "&"])
def test_authority_key_value_is_not_split_before_userinfo_redaction(delimiter):
    raw = f"https://user:SECRET_PREFIX{delimiter}token=SECRET_TAIL@host/path?token=QUERY_SECRET"
    assert mask_error_text(raw) == "https://***@host/path?token=***"


@pytest.mark.parametrize("key", ["%74oken", "pass%77ord", "%61pi%5Fkey"])
def test_encoded_query_keys_use_decoded_credential_classification(key):
    import json

    raw = f"https://host/?{key}=SECRET_TAIL&mode=fast"
    expected = f"https://host/?{key}=***&mode=fast"
    assert mask_error_text(raw) == expected
    assert json.loads(mask_error_text(json.dumps({"url": raw}))) == {"url": expected}
    harmless = "https://host/?%6eote=harmless&mode=fast"
    assert mask_error_text(harmless) == harmless


@pytest.mark.parametrize(
    "value", ["http://user:pass@SECRET_TAIL/path", "http://SECRET_TAIL@host/path"]
)
def test_nested_url_query_value_is_redacted_whole(value):
    assert mask_error_text(f"http://public.host/?token={value}&mode=fast") == (
        "http://public.host/?token=***&mode=fast"
    )


def test_semicolon_parameter_delimiter_does_not_hide_following_secret():
    assert mask_error_text("https://host/?mode=fast;token=SECRET_TAIL&note=ok") == (
        "https://host/?mode=fast;token=***&note=ok"
    )


@pytest.mark.parametrize(
    "value",
    [
        "SECRET_HEAD;SECRET_TAIL",
        "http://u:SECRET_HEAD;param=SECRET_TAIL@hidden/path",
    ],
)
def test_semicolon_inside_sensitive_query_value_cannot_expose_tail(value):
    assert mask_error_text(f"https://host/?token={value}&mode=fast") == (
        "https://host/?token=***&mode=fast"
    )


@pytest.mark.parametrize("nested", ["https://inner", "https://u:secret@inner"])
def test_nonsensitive_nested_url_does_not_hide_outer_query_credentials(nested):
    raw = f"https://outer/?next={nested}&token=SECRET_TAIL"
    output = mask_error_text(raw)
    assert "SECRET_TAIL" not in output
    assert "secret" not in output
    assert output.endswith("inner&token=***")


@pytest.mark.parametrize("userinfo_delimiter", ["&", ";"])
@pytest.mark.parametrize("at", ["@", "%40"])
@pytest.mark.parametrize(
    "query_prefix", ["password=", "next=https://middle/?password="]
)
def test_sensitive_query_and_nested_userinfo_mask_their_union(
    userinfo_delimiter, at, query_prefix
):
    raw = (
        "https://outer/?"
        + query_prefix
        + "https://user:SECRET_HEAD"
        + userinfo_delimiter
        + "note=SECRET_TAIL"
        + at
        + "inner/path&mode=harmless"
    )
    output = mask_error_text(raw)
    assert "SECRET_" not in output
    assert output.endswith("password=***&mode=harmless")


def test_sensitive_query_union_can_span_two_nested_credential_urls():
    raw = (
        "https://outer/?password=https://u:HEAD&note=TAIL@inner/path"
        "&next=https://u:SECOND&note=LAST@other/path&mode=harmless"
    )
    output = mask_error_text(raw)
    assert (
        output
        == "https://outer/?password=***&next=https://***@other/path&mode=harmless"
    )
