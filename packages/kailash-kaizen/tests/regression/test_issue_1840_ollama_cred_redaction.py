# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: Ollama provider must not leak base_url credentials (#1840).

Before the fix, ``OllamaProvider`` raised ``RuntimeError(f"... {e}")`` at four
sites (``_check_ollama_available``, ``generate``, ``generate_stream``,
``generate_vision``). The underlying ``ollama`` client renders the configured
``base_url`` / ``OLLAMA_HOST`` (which may carry ``user:pass@host`` or a
``?token=`` param) into its exception text, so ``{e}`` leaked the credential.

The fix routes every ``{e}`` through ``mask_error_text`` (the ONE shared helper
in ``kailash.utils.url_credentials``).

These tests INJECT a fake ``ollama`` backend (the external boundary) whose
calls raise exceptions carrying a credential-bearing base_url; the redaction
helper itself is exercised for real (never mocked).
"""

import sys
import types

import pytest

from kaizen.providers.ollama_provider import OllamaConfig, OllamaProvider

CRED_URL = "http://ollama_user:S3cr3tOLLAMA@ollama.host:11434/api?token=oltok123"
SECRET = "S3cr3tOLLAMA"
TOKEN = "oltok123"


def _install_fake_ollama(monkeypatch, *, list_exc=None, chat_exc=None):
    """Install a fake ``ollama`` module into sys.modules (boundary injection)."""
    mod = types.ModuleType("ollama")

    def _list(*a, **k):
        if list_exc is not None:
            raise list_exc
        return {"models": []}

    def _chat(*a, **k):
        if chat_exc is not None:
            raise chat_exc
        return {"message": {"content": "ok"}, "model": "llama2", "done": True}

    mod.list = _list
    mod.chat = _chat
    monkeypatch.setitem(sys.modules, "ollama", mod)
    return mod


def _config():
    return OllamaConfig(base_url=CRED_URL)


def _assert_masked(text):
    assert SECRET not in text
    assert TOKEN not in text


def test_check_available_raise_masks_credentials(monkeypatch):
    exc = ConnectionError(f"Failed to reach {CRED_URL}: connection refused")
    _install_fake_ollama(monkeypatch, list_exc=exc)
    with pytest.raises(RuntimeError) as ei:
        OllamaProvider(config=_config())
    msg = str(ei.value)
    _assert_masked(msg)
    assert "***@ollama.host" in msg


def test_generate_raise_masks_credentials(monkeypatch):
    exc = ConnectionError(f"httpx.ConnectError to {CRED_URL}")
    _install_fake_ollama(monkeypatch, chat_exc=exc)  # list() ok → construct passes
    provider = OllamaProvider(config=_config())
    with pytest.raises(RuntimeError) as ei:
        provider.generate("hello")
    msg = str(ei.value)
    _assert_masked(msg)
    assert "***@ollama.host" in msg


def test_generate_stream_raise_masks_credentials(monkeypatch):
    exc = ConnectionError(f"stream broke on {CRED_URL}")
    _install_fake_ollama(monkeypatch, chat_exc=exc)
    provider = OllamaProvider(config=_config())
    with pytest.raises(RuntimeError) as ei:
        list(provider.generate_stream("hello"))  # iterate to trigger the body
    msg = str(ei.value)
    _assert_masked(msg)
    assert "***@ollama.host" in msg


def test_generate_vision_raise_masks_credentials(monkeypatch):
    exc = ConnectionError(f"vision call failed to {CRED_URL}")
    _install_fake_ollama(monkeypatch, chat_exc=exc)
    provider = OllamaProvider(config=_config())
    with pytest.raises(RuntimeError) as ei:
        provider.generate_vision("describe", image_path="/tmp/x.png")
    msg = str(ei.value)
    _assert_masked(msg)
    assert "***@ollama.host" in msg


def test_dotall_embedded_newline_in_base_url_fully_masked(monkeypatch):
    """The #1840 DOTALL regression via the Ollama raise path.

    A credential whose password contains a literal newline must be fully
    masked — the tail after the ``\\n`` must not leak.
    """
    leaky = "http://admin:sec\nret@ollama.host:11434/api"
    exc = ConnectionError(f"connect error: {leaky}")
    _install_fake_ollama(monkeypatch, chat_exc=exc)
    provider = OllamaProvider(config=OllamaConfig(base_url=leaky))
    with pytest.raises(RuntimeError) as ei:
        provider.generate("hi")
    msg = str(ei.value)
    assert "ret@" not in msg  # tail after the newline must not survive
    assert "sec\nret" not in msg
    assert "***@ollama.host" in msg


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])


@pytest.mark.parametrize(
    "surface", ["available", "generate", "stream", "vision", "models", "download"]
)
@pytest.mark.parametrize(
    "url,tail",
    [
        ("http://admin:sec\nret@ollama.host:11434/api", "ret@"),
        ("http://ollama.host:11434/api?token=sec\nret", "ret"),
    ],
)
@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_newline_credential_masking_precedes_flatten(
    monkeypatch, caplog, surface, url, tail, control
):
    url = url.replace("\n", control)
    from kaizen.providers.ollama_model_manager import OllamaModelManager

    exc = ConnectionError(f"connect failed: {url}")
    mod = _install_fake_ollama(monkeypatch, chat_exc=exc)
    if surface in ("available", "models"):

        def fail_list():
            raise exc

        mod.list = fail_list
    if surface == "download":

        def fail_pull(*args, **kwargs):
            raise exc

        mod.pull = fail_pull
        assert OllamaModelManager().download_model("llama2") is False
        text = caplog.text
    else:
        with pytest.raises(RuntimeError) as caught:
            if surface == "models":
                OllamaModelManager().list_models()
            else:
                provider = OllamaProvider(config=OllamaConfig(base_url=url))
                if surface == "generate":
                    provider.generate("hello")
                elif surface == "stream":
                    list(provider.generate_stream("hello"))
                elif surface == "vision":
                    provider.generate_vision("describe", image_path="/tmp/x.png")
        text = str(caught.value)
    assert tail not in text
    assert "sec" not in text
    assert "ConnectionError" in text
    assert "ollama.host" in text


@pytest.mark.parametrize(
    "url",
    [
        "http://admin:sec\nret@ollama.host/api",
        "http://admin:" + "z" * 257 + "\nret@ollama.host/api",
        "http://sec\nret@ollama.host/api",
        "http://ollama.host/api?token=sec\nret&mode=fast",
    ],
)
@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_shared_error_surfaces_scrub_before_bounds(url, control):
    url = url.replace("\n", control)
    from kaizen.llm.errors import ProviderError
    from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
    from kaizen.utils.credential_scrub import scrub_credentials

    for text in (
        sanitize_provider_error(ConnectionError(url), "test"),
        ProviderError(500, url).body_snippet,
        scrub_credentials(url, redact_opaque_tokens=False),
    ):
        assert "ret" not in text
        assert "sec" not in text
        assert "ollama.host" in text
    assert "\n" not in sanitize_provider_error(ConnectionError(url), "test")


def test_noncredential_url_diagnostics_survive():
    from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

    text = "connect http://ollama.host/api?mode=fast failed\nretry later"
    sanitized = sanitize_provider_error(ConnectionError(text), "test")
    assert "http://ollama.host/api?mode=fast" in sanitized
    assert "retry later" in sanitized
    assert "\n" not in sanitized


@pytest.mark.parametrize(
    "pattern_name, raw",
    [
        ("_URL_WITH_AUTH", "http://admin:sec\nret@"),
        ("_URL_WITH_AUTH_OVERFLOW", "http://admin:" + "z" * 257 + "\nret@"),
        ("_URL_WITH_USERINFO_ONLY", "http://sec\nret@"),
    ],
)
@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_newline_reaches_each_url_rule(pattern_name, raw, control):
    raw = raw.replace("\n", control)
    import re

    from kaizen.utils import credential_scrub

    pattern = getattr(credential_scrub, pattern_name)
    match = pattern.match(raw + "ollama.host/api")
    assert match is not None and match.group(0) == raw
    assert pattern.search("http://ollama.host/api ordinary text") is None
    # Restoring the former whitespace fence must miss this exact credential.
    old_pattern = re.compile(pattern.pattern.replace(r"\f\v ", r"\s"), pattern.flags)
    assert old_pattern.match(raw + "ollama.host/api") is None


@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_long_username_scrubbed_before_opaque_token_rules(control):
    from kaizen.llm.errors import ProviderError
    from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
    from kaizen.utils.credential_scrub import scrub_credentials

    raw = "http://" + "z" * 257 + f":short{control}credentialTAIL42@ollama.host/api"
    for output in (
        scrub_credentials(raw),
        sanitize_provider_error(ConnectionError(raw), "test"),
        ProviderError(500, raw).body_snippet,
    ):
        assert "credentialTAIL42" not in output
        assert "short" not in output
        assert "ollama.host" in output


@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_url_authority_does_not_consume_later_diagnostic(control):
    from kaizen.utils.credential_scrub import scrub_credentials

    raw = f"http://docs.host/api{control}contact:info@example.com"
    assert scrub_credentials(raw, redact_opaque_tokens=False) == raw
    encoded = "http://user:short%2FencodedTAIL@ollama.host/api"
    assert "encodedTAIL" not in scrub_credentials(encoded)


def test_replacement_markers_are_not_reinterpreted_by_other_rules():
    from kaizen.utils.credential_scrub import scrub_credentials

    marker = "prefix-sk-" + "a" * 24
    raw = "http://user:secret@host/api?token=secret"
    assert (
        scrub_credentials(raw, placeholder=marker)
        == f"http://{marker}:{marker}@host/api?token={marker}"
    )


def test_sensitive_query_value_owns_embedded_url_span():
    from kaizen.utils.credential_scrub import scrub_credentials

    raw = "http://host/api?token=http://user:secret@private-token-host/path&mode=fast"
    assert scrub_credentials(raw) == "http://host/api?token=[REDACTED]&mode=fast"


@pytest.mark.parametrize(
    "key", ["passphrase", "OPENAI_API_KEY", "refresh_token", "encryption_key"]
)
@pytest.mark.parametrize("opaque", [False, True])
def test_json_credential_keys_retain_kaizen_vocabulary(key, opaque):
    import json

    from kaizen.utils.credential_scrub import scrub_credentials

    raw = json.dumps({key: "hunter2secret", "message": "connection refused"})
    result = scrub_credentials(raw, redact_opaque_tokens=opaque)
    assert json.loads(result) == {key: "[REDACTED]", "message": "connection refused"}
    harmless = json.dumps({"cache_key": "lookup42", "public_key": "visible42"})
    assert scrub_credentials(harmless, redact_opaque_tokens=opaque) == harmless


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
@pytest.mark.parametrize("opaque", [False, True])
def test_bearer_scheme_and_complete_token_alphabet(scheme, opaque):
    from kaizen.utils.credential_scrub import scrub_credentials

    raw = f"Authorization: {scheme} hunter2secret/TAIL+END~="
    assert (
        scrub_credentials(raw, redact_opaque_tokens=opaque)
        == "Authorization: [REDACTED]"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://user:SECRET_PREFIX;token=SECRET_TAIL@host/path?token=QUERY_SECRET",
        "https://user:SECRET_PREFIX&token=SECRET_TAIL@host/path?token=QUERY_SECRET",
        "https://host/?%74oken=SECRET_TAIL",
        "https://host/?token=http://user:SECRET_PREFIX@SECRET_TAIL/path",
    ],
)
def test_provider_scanner_preserves_credential_carrier_boundaries(value):
    from kaizen.llm.errors import ProviderError
    from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
    from kaizen.utils.credential_scrub import scrub_credentials

    for result in (
        scrub_credentials(value, redact_opaque_tokens=False),
        sanitize_provider_error(RuntimeError(value), "test"),
        ProviderError(500, value).body_snippet,
    ):
        assert "SECRET_" not in result
        assert "QUERY_SECRET" not in result
        assert "host" in result


@pytest.mark.parametrize(
    "header", ["Authorization", "authorization", "Proxy-Authorization"]
)
@pytest.mark.parametrize("opaque", [False, True])
def test_explicit_basic_auth_header_masks_all_letter_base64(header, opaque):
    import base64
    import json

    from kaizen.utils.credential_scrub import scrub_credentials

    token = base64.b64encode(b"abc:defgh").decode("ascii")
    assert token.isalpha(), "control must reach the all-letter base64 gap"
    plain = scrub_credentials(f"{header}: Basic {token}", redact_opaque_tokens=opaque)
    assert token not in plain and "[REDACTED]" in plain
    body = json.dumps({header: f"Basic {token}", "message": "connection refused"})
    assert json.loads(scrub_credentials(body, redact_opaque_tokens=opaque)) == {
        header: "[REDACTED]",
        "message": "connection refused",
    }
    harmless = "Basic authentication is not configured"
    assert scrub_credentials(harmless, redact_opaque_tokens=opaque) == harmless


@pytest.mark.parametrize(
    "header", ["Authorization", "aUtHoRiZaTiOn", "Proxy-Authorization"]
)
@pytest.mark.parametrize("separator", [":", "="])
@pytest.mark.parametrize("quote", ["", chr(34), chr(39)])
@pytest.mark.parametrize("scheme", ["Basic", "basic", "Bearer", "bearer"])
def test_quoted_header_and_config_contexts_mask_complete_auth_tokens(
    header, separator, quote, scheme
):
    from kaizen.utils.credential_scrub import scrub_credentials

    token = "YWJjOmRlZmdo" if scheme.lower() == "basic" else "hunter2secret/TAIL+END~="
    raw = (
        "{"
        + quote
        + header
        + quote
        + separator
        + " "
        + quote
        + scheme
        + " "
        + token
        + quote
        + "}"
    )
    for opaque in (False, True):
        result = scrub_credentials(raw, redact_opaque_tokens=opaque)
        assert token not in result
        assert "TAIL" not in result
        assert "[REDACTED]" in result
        harmless = "Basic authentication is not configured"
        assert scrub_credentials(harmless, redact_opaque_tokens=opaque) == harmless


@pytest.mark.parametrize("userinfo_delimiter", ["&", ";"])
@pytest.mark.parametrize("at", ["@", "%40"])
def test_provider_nested_query_userinfo_overlap_masks_both_carriers(
    userinfo_delimiter, at
):
    from kaizen.llm.errors import ProviderError
    from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
    from kaizen.utils.credential_scrub import scrub_credentials

    value = (
        "https://outer/?password=https://user:SECRET_HEAD"
        + userinfo_delimiter
        + "note=SECRET_TAIL"
        + at
        + "inner/path&mode=harmless"
    )
    for output in (
        scrub_credentials(value, redact_opaque_tokens=False),
        sanitize_provider_error(RuntimeError(value), "test"),
        ProviderError(500, value).body_snippet,
    ):
        assert "SECRET_" not in output
        assert "mode=harmless" in output
