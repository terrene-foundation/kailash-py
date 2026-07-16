# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-1b MULTIMODAL — ``_content_parts`` translator + per-wire coverage.

Behavioral tests (construct -> call -> assert the produced dict/log record;
no source-grep) for the canonical content-part translator and its three
consuming wires:

* ``_content_parts`` — the pure classify/emit functions in isolation.
* ``anthropic_messages`` — OpenAI ``image_url`` -> Anthropic ``image`` block
  (base64 ``source`` for a data-URI, ``url`` ``source`` for a remote url).
* ``google_generate_content`` — OpenAI ``image_url`` -> Gemini ``inlineData``
  (data-URI) / ``fileData`` (remote url) part.
* ``ollama_native`` — OpenAI ``image_url`` -> Ollama-native's per-message
  ``images`` field (bare base64 list), text stays in ``content``.
* ``cohere_generate`` — text-only wire; a dropped image block now logs a
  WARNING (was DEBUG pre-Wave-1b).

Plus a byte-identity PIN: ``openai_chat`` and ``mistral_chat`` need NO
translation because the canonical shape already IS their wire shape — this
file imports both read-only and asserts their emitted ``messages`` field is
byte-identical to the raw multimodal input.

No real model names are hardcoded (env-models.md) — tests use
``"test-model"``.
"""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import (
    _content_parts,
    anthropic_messages,
    cohere_generate,
    google_generate_content,
    mistral_chat,
    ollama_native,
    openai_chat,
)

# --- Shared fixtures ------------------------------------------------------

_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
_DATA_URI = f"data:image/png;base64,{_PNG_B64}"
_REMOTE_URL = "https://example.com/images/cat.png"
_REMOTE_URL_NO_EXT = "https://example.com/images/cat"


def _data_uri_image_block():
    return {"type": "image_url", "image_url": {"url": _DATA_URI}}


def _remote_url_image_block():
    return {"type": "image_url", "image_url": {"url": _REMOTE_URL}}


def _text_block(text="What is in this image?"):
    return {"type": "text", "text": text}


def _base_request(messages, **overrides) -> CompletionRequest:
    fields = {"model": "test-model", "messages": messages}
    fields.update(overrides)
    return CompletionRequest(**fields)


# ===========================================================================
# _content_parts — pure classify/emit functions
# ===========================================================================


class TestParseDataUri:
    def test_valid_data_uri_splits_media_type_and_data(self):
        result = _content_parts.parse_data_uri(_DATA_URI)
        assert result == ("image/png", _PNG_B64)

    def test_missing_data_scheme_returns_none(self):
        assert _content_parts.parse_data_uri(_REMOTE_URL) is None

    def test_missing_base64_marker_returns_none(self):
        assert _content_parts.parse_data_uri("data:image/png,notbase64") is None

    def test_empty_media_type_returns_none(self):
        assert _content_parts.parse_data_uri("data:;base64,abcd") is None

    def test_empty_data_returns_none(self):
        assert _content_parts.parse_data_uri("data:image/png;base64,") is None

    def test_non_string_input_returns_none(self):
        assert _content_parts.parse_data_uri(None) is None  # type: ignore[arg-type]


class TestIsRemoteUrl:
    @pytest.mark.parametrize(
        "url",
        ["https://example.com/x.png", "http://example.com/x.png"],
    )
    def test_http_and_https_are_remote(self, url):
        assert _content_parts.is_remote_url(url) is True

    def test_data_uri_is_not_remote(self):
        assert _content_parts.is_remote_url(_DATA_URI) is False

    def test_non_string_is_not_remote(self):
        assert _content_parts.is_remote_url(None) is False  # type: ignore[arg-type]


class TestParseContentPart:
    def test_text_block_returns_text_part(self):
        part = _content_parts.parse_content_part(_text_block("hello"))
        assert isinstance(part, _content_parts.TextPart)
        assert part.text == "hello"

    def test_text_block_missing_text_key_defaults_empty(self):
        part = _content_parts.parse_content_part({"type": "text"})
        assert isinstance(part, _content_parts.TextPart)
        assert part.text == ""

    def test_data_uri_image_block_returns_image_part(self):
        part = _content_parts.parse_content_part(_data_uri_image_block())
        assert isinstance(part, _content_parts.ImagePart)
        assert part.is_data_uri is True
        assert part.media_type == "image/png"
        assert part.data == _PNG_B64
        assert part.url is None

    def test_remote_url_image_block_returns_image_part(self):
        part = _content_parts.parse_content_part(_remote_url_image_block())
        assert isinstance(part, _content_parts.ImagePart)
        assert part.is_data_uri is False
        assert part.url == _REMOTE_URL
        assert part.media_type is None
        assert part.data is None

    def test_unrecognized_block_type_returns_none(self):
        assert _content_parts.parse_content_part({"type": "tool_use"}) is None

    def test_image_url_missing_url_key_returns_none(self):
        assert (
            _content_parts.parse_content_part({"type": "image_url", "image_url": {}})
            is None
        )

    def test_image_url_malformed_not_data_or_remote_returns_none(self):
        block = {"type": "image_url", "image_url": {"url": "ftp://example.com/x.png"}}
        assert _content_parts.parse_content_part(block) is None

    def test_non_dict_block_returns_none(self):
        assert _content_parts.parse_content_part("just a string") is None


class TestGuessMediaType:
    def test_known_extension_png(self):
        assert _content_parts.guess_media_type("https://x.com/a.png") == "image/png"

    def test_known_extension_jpg(self):
        assert _content_parts.guess_media_type("https://x.com/a.jpg") == "image/jpeg"

    def test_unknown_extension_falls_back(self):
        assert (
            _content_parts.guess_media_type(_REMOTE_URL_NO_EXT)
            == "application/octet-stream"
        )


class TestToAnthropicBlock:
    def test_data_uri_emits_base64_source(self):
        part = _content_parts.ImagePart(
            is_data_uri=True, media_type="image/png", data=_PNG_B64
        )
        assert _content_parts.to_anthropic_block(part) == {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _PNG_B64,
            },
        }

    def test_remote_url_emits_url_source(self):
        part = _content_parts.ImagePart(is_data_uri=False, url=_REMOTE_URL)
        assert _content_parts.to_anthropic_block(part) == {
            "type": "image",
            "source": {"type": "url", "url": _REMOTE_URL},
        }


class TestToGeminiPart:
    def test_data_uri_emits_inline_data(self):
        part = _content_parts.ImagePart(
            is_data_uri=True, media_type="image/png", data=_PNG_B64
        )
        assert _content_parts.to_gemini_part(part) == {
            "inlineData": {"mimeType": "image/png", "data": _PNG_B64}
        }

    def test_remote_url_emits_file_data_with_guessed_mime_type(self):
        part = _content_parts.ImagePart(is_data_uri=False, url=_REMOTE_URL)
        assert _content_parts.to_gemini_part(part) == {
            "fileData": {"mimeType": "image/png", "fileUri": _REMOTE_URL}
        }

    def test_remote_url_no_extension_falls_back_mime_type(self):
        part = _content_parts.ImagePart(is_data_uri=False, url=_REMOTE_URL_NO_EXT)
        result = _content_parts.to_gemini_part(part)
        assert result["fileData"]["mimeType"] == "application/octet-stream"
        assert result["fileData"]["fileUri"] == _REMOTE_URL_NO_EXT


class TestToOllamaImages:
    def test_filters_to_data_uri_base64_only(self):
        data_part = _content_parts.ImagePart(
            is_data_uri=True, media_type="image/png", data=_PNG_B64
        )
        remote_part = _content_parts.ImagePart(is_data_uri=False, url=_REMOTE_URL)
        assert _content_parts.to_ollama_images([data_part, remote_part]) == [_PNG_B64]

    def test_empty_list_returns_empty(self):
        assert _content_parts.to_ollama_images([]) == []


# ===========================================================================
# anthropic_messages — image_url -> Anthropic image block
# ===========================================================================


class TestAnthropicMultimodalTranslation:
    def test_data_uri_image_translated_to_base64_block(self):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _data_uri_image_block()],
                }
            ]
        )
        payload = anthropic_messages.build_request_payload(req)
        content = payload["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "hi"}
        assert content[1] == {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _PNG_B64,
            },
        }

    def test_remote_url_image_translated_to_url_source(self):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _remote_url_image_block()],
                }
            ]
        )
        payload = anthropic_messages.build_request_payload(req)
        content = payload["messages"][0]["content"]
        assert content[1] == {
            "type": "image",
            "source": {"type": "url", "url": _REMOTE_URL},
        }

    def test_text_only_message_unchanged(self):
        req = _base_request([{"role": "user", "content": "hello there"}])
        payload = anthropic_messages.build_request_payload(req)
        assert payload["messages"] == [{"role": "user", "content": "hello there"}]

    def test_text_only_content_list_unchanged(self):
        req = _base_request(
            [{"role": "user", "content": [_text_block("hello"), _text_block("world")]}]
        )
        payload = anthropic_messages.build_request_payload(req)
        assert payload["messages"][0]["content"] == [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]

    def test_unrecognized_block_passes_through_unchanged(self):
        weird_block = {"type": "tool_use", "id": "x", "name": "foo", "input": {}}
        req = _base_request([{"role": "user", "content": [weird_block]}])
        payload = anthropic_messages.build_request_payload(req)
        assert payload["messages"][0]["content"] == [weird_block]


# ===========================================================================
# google_generate_content — image_url -> Gemini inlineData/fileData
# ===========================================================================


class TestGeminiMultimodalTranslation:
    def test_data_uri_image_translated_to_inline_data(self):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _data_uri_image_block()],
                }
            ]
        )
        payload = google_generate_content.build_request_payload(req)
        parts = payload["contents"][0]["parts"]
        assert parts[0] == {"text": "hi"}
        assert parts[1] == {"inlineData": {"mimeType": "image/png", "data": _PNG_B64}}

    def test_remote_url_image_translated_to_file_data(self):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _remote_url_image_block()],
                }
            ]
        )
        payload = google_generate_content.build_request_payload(req)
        parts = payload["contents"][0]["parts"]
        assert parts[1] == {
            "fileData": {"mimeType": "image/png", "fileUri": _REMOTE_URL}
        }

    def test_text_only_message_unchanged(self):
        req = _base_request([{"role": "user", "content": "hello there"}])
        payload = google_generate_content.build_request_payload(req)
        assert payload["contents"][0]["parts"] == [{"text": "hello there"}]

    def test_unrecognized_block_passes_through_unchanged(self):
        weird_block = {"functionCall": {"name": "foo", "args": {}}}
        req = _base_request([{"role": "assistant", "content": [weird_block]}])
        payload = google_generate_content.build_request_payload(req)
        assert payload["contents"][0]["parts"] == [weird_block]


# ===========================================================================
# ollama_native — image_url -> per-message `images` field
# ===========================================================================


class TestOllamaMultimodalTranslation:
    def test_data_uri_image_moved_to_images_field(self):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _data_uri_image_block()],
                }
            ]
        )
        payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        assert msg["content"] == "hi"
        assert msg["images"] == [_PNG_B64]

    def test_multiple_data_uri_images_all_moved(self):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [
                        _text_block("compare"),
                        _data_uri_image_block(),
                        _data_uri_image_block(),
                    ],
                }
            ]
        )
        payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        assert msg["content"] == "compare"
        assert msg["images"] == [_PNG_B64, _PNG_B64]

    def test_text_only_string_content_unchanged(self):
        req = _base_request([{"role": "user", "content": "hello there"}])
        payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        assert msg["content"] == "hello there"
        assert "images" not in msg

    def test_text_only_content_list_unchanged(self):
        blocks = [_text_block("hello"), _text_block("world")]
        req = _base_request([{"role": "user", "content": blocks}])
        payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        # No image_url part present -> content list passed through as-is.
        assert msg["content"] == blocks
        assert "images" not in msg

    def test_remote_url_image_dropped_with_warning(self, caplog):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("describe"), _remote_url_image_block()],
                }
            ]
        )
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.ollama_native"
        ):
            payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        assert msg["content"] == "describe"
        assert "images" not in msg
        assert any(
            r.levelno == logging.WARNING
            and "ollama_native.remote_image_url_not_translated" in r.message
            for r in caplog.records
        )

    def test_mixed_data_uri_and_remote_url(self, caplog):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [
                        _text_block("mixed"),
                        _data_uri_image_block(),
                        _remote_url_image_block(),
                    ],
                }
            ]
        )
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.ollama_native"
        ):
            payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        assert msg["content"] == "mixed"
        assert msg["images"] == [_PNG_B64]
        assert any(
            "ollama_native.remote_image_url_not_translated" in r.message
            for r in caplog.records
        )

    def test_malformed_image_url_block_dropped_with_warning(self, caplog):
        """/redteam Round-1 (#1720 Wave-1b): a malformed image_url block
        (missing `url`) has no Ollama-native slot and is dropped -- this
        branch previously fell through with NO log. Must WARN, never
        silent, per rules/observability.md Rule 7."""
        malformed_block = {"type": "image_url", "image_url": {}}
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("describe"), malformed_block],
                }
            ]
        )
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.ollama_native"
        ):
            payload = ollama_native.build_request_payload(req)
        msg = payload["messages"][0]
        assert msg["content"] == "describe"
        assert "images" not in msg
        assert any(
            r.levelno == logging.WARNING
            and "ollama_native.content_block_dropped" in r.message
            for r in caplog.records
        )

    def test_no_malformed_block_no_content_block_dropped_warning(self, caplog):
        """Byte-neutral: a data-URI-only message emits no
        content_block_dropped warning."""
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _data_uri_image_block()],
                }
            ]
        )
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.ollama_native"
        ):
            ollama_native.build_request_payload(req)
        assert not any(
            "ollama_native.content_block_dropped" in r.message for r in caplog.records
        )


# ===========================================================================
# cohere_generate — text-only wire; drop now WARNs (was DEBUG)
# ===========================================================================


class TestCohereImageDropWarns:
    def test_data_uri_image_block_dropped_with_warning(self, caplog):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _data_uri_image_block()],
                }
            ]
        )
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.cohere_generate"
        ):
            payload = cohere_generate.build_request_payload(req)
        # Only the text survives into Cohere's `message` field.
        assert payload["message"] == "hi"
        warn_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "cohere_generate.non_text_block_dropped" in r.message
        ]
        assert len(warn_records) == 1

    def test_remote_url_image_block_dropped_with_warning(self, caplog):
        req = _base_request(
            [
                {
                    "role": "user",
                    "content": [_text_block("hi"), _remote_url_image_block()],
                }
            ]
        )
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.cohere_generate"
        ):
            payload = cohere_generate.build_request_payload(req)
        assert payload["message"] == "hi"
        assert any(
            r.levelno == logging.WARNING
            and "cohere_generate.non_text_block_dropped" in r.message
            for r in caplog.records
        )

    def test_no_image_no_warning(self, caplog):
        req = _base_request([{"role": "user", "content": "plain text only"}])
        with caplog.at_level(
            logging.WARNING, logger="kaizen.llm.wire_protocols.cohere_generate"
        ):
            cohere_generate.build_request_payload(req)
        assert not any(
            "cohere_generate.non_text_block_dropped" in r.message
            for r in caplog.records
        )


# ===========================================================================
# Byte-identity pin: openai_chat + mistral_chat need NO translation
# ===========================================================================


class TestOpenAiAndMistralByteIdentityPin:
    """openai_chat + mistral_chat pass ``messages`` through verbatim — the
    canonical content-part shape already IS their wire shape. No code
    change was made to either shaper in this shard; these tests PIN that
    invariant against the raw multimodal input.
    """

    @staticmethod
    def _multimodal_messages():
        return [
            {
                "role": "user",
                "content": [
                    _text_block("What's in these images?"),
                    _data_uri_image_block(),
                    _remote_url_image_block(),
                ],
            }
        ]

    def test_openai_chat_messages_byte_identical_to_raw_input(self):
        messages = self._multimodal_messages()
        req = _base_request(messages)
        payload = openai_chat.build_request_payload(req)
        assert payload["messages"] == messages

    def test_mistral_chat_messages_byte_identical_to_raw_input(self):
        messages = self._multimodal_messages()
        req = _base_request(messages)
        payload = mistral_chat.build_request_payload(req)
        assert payload["messages"] == messages

    def test_openai_and_mistral_agree_on_multimodal_messages_shape(self):
        messages = self._multimodal_messages()
        req = _base_request(messages)
        openai_payload = openai_chat.build_request_payload(req)
        mistral_payload = mistral_chat.build_request_payload(req)
        assert openai_payload["messages"] == mistral_payload["messages"] == messages
