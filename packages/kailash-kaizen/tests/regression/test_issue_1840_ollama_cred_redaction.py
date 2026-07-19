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
