# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for the OpenAI + Ollama embedding wire shapers (#462).

Shapers are pure functions (build_request_payload / parse_response) with
input validation. These tests exercise the documented contract and the
typed errors emitted at each shape boundary — no I/O, no mocking required.
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import EmbedOptions
from kaizen.llm.errors import InvalidResponse
from kaizen.llm.wire_protocols import ollama_embeddings, openai_embeddings


# ---------------------------------------------------------------------------
# OpenAI shaper — build_request_payload
# ---------------------------------------------------------------------------


class TestOpenAiBuildRequest:
    def test_minimal_payload(self):
        payload = openai_embeddings.build_request_payload(
            ["hello", "world"], "text-embedding-3-small"
        )
        assert payload == {
            "model": "text-embedding-3-small",
            "input": ["hello", "world"],
        }

    def test_dimensions_option_included_when_set(self):
        payload = openai_embeddings.build_request_payload(
            ["x"], "text-embedding-3-small", EmbedOptions(dimensions=256)
        )
        assert payload["dimensions"] == 256

    def test_dimensions_option_omitted_when_unset(self):
        payload = openai_embeddings.build_request_payload(
            ["x"], "text-embedding-3-small", EmbedOptions()
        )
        assert "dimensions" not in payload

    def test_user_option_included_when_set(self):
        payload = openai_embeddings.build_request_payload(
            ["x"], "text-embedding-3-small", EmbedOptions(user="abuse-track-id")
        )
        assert payload["user"] == "abuse-track-id"

    def test_empty_texts_rejected(self):
        with pytest.raises(ValueError, match="at least one text"):
            openai_embeddings.build_request_payload([], "text-embedding-3-small")

    def test_non_list_texts_rejected(self):
        with pytest.raises(TypeError, match="list\\[str\\]"):
            openai_embeddings.build_request_payload("hello", "text-embedding-3-small")  # type: ignore[arg-type]

    def test_bytes_element_rejected(self):
        with pytest.raises(TypeError, match="must be str"):
            openai_embeddings.build_request_payload(
                [b"hello"], "text-embedding-3-small"  # type: ignore[list-item]
            )

    def test_empty_model_rejected(self):
        with pytest.raises(ValueError, match="non-empty model"):
            openai_embeddings.build_request_payload(["x"], "")

    def test_bad_options_type_rejected(self):
        with pytest.raises(TypeError, match="EmbedOptions"):
            openai_embeddings.build_request_payload(
                ["x"], "text-embedding-3-small", {"dimensions": 256}  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# OpenAI shaper — parse_response
# ---------------------------------------------------------------------------


class TestOpenAiParseResponse:
    def test_basic_parse(self):
        response = {
            "object": "list",
            "data": [
                {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
            ],
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 4, "total_tokens": 4},
        }
        parsed = openai_embeddings.parse_response(response)
        assert parsed["vectors"] == [[0.1, 0.2, 0.3]]
        assert parsed["model"] == "text-embedding-3-small"
        assert parsed["usage"] == {"input_tokens": 4, "total_tokens": 4}

    def test_sorts_by_index(self):
        """Contract: OpenAI docs do not guarantee array order; we sort by index."""
        response = {
            "data": [
                {"index": 1, "embedding": [1.0, 1.1]},
                {"index": 0, "embedding": [0.0, 0.1]},
            ],
        }
        parsed = openai_embeddings.parse_response(response)
        assert parsed["vectors"] == [[0.0, 0.1], [1.0, 1.1]]

    def test_missing_data_field(self):
        with pytest.raises(InvalidResponse, match="missing or non-list 'data'"):
            openai_embeddings.parse_response({})

    def test_data_entry_missing_embedding(self):
        with pytest.raises(InvalidResponse, match="missing 'embedding' list"):
            openai_embeddings.parse_response({"data": [{"index": 0}]})

    def test_non_numeric_embedding_rejected(self):
        with pytest.raises(InvalidResponse, match="non-numeric value"):
            openai_embeddings.parse_response(
                {"data": [{"index": 0, "embedding": [0.1, "nope"]}]}
            )

    def test_bool_rejected_as_embedding_value(self):
        """bool is a subclass of int in Python; explicitly reject."""
        with pytest.raises(InvalidResponse, match="non-numeric value"):
            openai_embeddings.parse_response(
                {"data": [{"index": 0, "embedding": [True, False]}]}
            )


# ---------------------------------------------------------------------------
# Ollama shaper — build_request_payload
# ---------------------------------------------------------------------------


class TestOllamaBuildRequest:
    def test_minimal_payload(self):
        payload = ollama_embeddings.build_request_payload(
            ["a", "b"], "nomic-embed-text"
        )
        assert payload == {"model": "nomic-embed-text", "input": ["a", "b"]}

    def test_dimensions_option_silently_dropped(self):
        """Ollama's dimension is fixed at model level; EmbedOptions.dimensions ignored."""
        payload = ollama_embeddings.build_request_payload(
            ["x"], "nomic-embed-text", EmbedOptions(dimensions=256)
        )
        assert "dimensions" not in payload

    def test_empty_texts_rejected(self):
        with pytest.raises(ValueError, match="at least one text"):
            ollama_embeddings.build_request_payload([], "nomic-embed-text")

    def test_empty_model_rejected(self):
        with pytest.raises(ValueError, match="non-empty model"):
            ollama_embeddings.build_request_payload(["x"], "")


# ---------------------------------------------------------------------------
# Ollama shaper — parse_response
# ---------------------------------------------------------------------------


class TestOllamaParseResponse:
    def test_basic_parse(self):
        response = {
            "model": "nomic-embed-text",
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            "prompt_eval_count": 6,
        }
        parsed = ollama_embeddings.parse_response(response)
        assert parsed["vectors"] == [[0.1, 0.2], [0.3, 0.4]]
        assert parsed["model"] == "nomic-embed-text"
        assert parsed["usage"]["input_tokens"] == 6

    def test_missing_embeddings_field(self):
        with pytest.raises(InvalidResponse, match="missing or non-list 'embeddings'"):
            ollama_embeddings.parse_response({})

    def test_non_list_entry_rejected(self):
        with pytest.raises(InvalidResponse, match="not a list"):
            ollama_embeddings.parse_response({"embeddings": [0.1, 0.2]})

    def test_non_numeric_rejected(self):
        with pytest.raises(InvalidResponse, match="non-numeric value"):
            ollama_embeddings.parse_response({"embeddings": [[0.1, "nope"]]})
