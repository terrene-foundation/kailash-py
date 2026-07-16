# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for `MockLlmHttpClient` -- the offline in-process transport (#1720
Wave-1b MOCK shard).

Every test in this module runs with a structural guard
(`_guard_no_real_network`) that patches `httpx.AsyncClient.send` to raise if
ever invoked -- since `MockLlmHttpClient` never constructs an
`httpx.AsyncClient`, the guard should never fire. Its presence converts a
silent regression (someone swaps in the real `LlmHttpClient`, or a code path
starts constructing a real transport) into an immediate, loud test failure.

Covers (per the task brief):
  1. `complete()` via `mock_preset()` + `MockLlmHttpClient` returns a
     deterministic dict with NO network.
  2. `stream()` concatenation == chat content + terminal `[DONE]` handled.
  3. `embed()` deterministic vectors + dimension + L2-normalization.
  4. Direct unit coverage of `MockLlmHttpClient`'s own typed-error /
     lifecycle behavior (closed-transport reuse, unsupported request shapes).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.deployment import EmbedOptions
from kaizen.llm.testing import MockLlmHttpClient, UnsupportedMockRequest, mock_preset


@pytest.fixture(autouse=True)
def _guard_no_real_network():
    """Fail loudly if any test in this module attempts a real httpx send.

    `MockLlmHttpClient` never constructs `httpx.AsyncClient`, so this patch
    should never actually fire for a correctly-wired test. If it DOES fire,
    something regressed to a real network path.
    """
    with patch(
        "httpx.AsyncClient.send",
        side_effect=AssertionError(
            "MockLlmHttpClient tests must never reach a real network send"
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# 1. complete() -- deterministic, no network
# ---------------------------------------------------------------------------


class TestCompleteViaMockTransport:
    @pytest.mark.asyncio
    async def test_complete_returns_deterministic_dict_without_network(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()
        messages = [{"role": "user", "content": "What is the capital of France?"}]

        result1 = await client.complete(messages, http_client=transport)
        result2 = await client.complete(messages, http_client=transport)

        assert result1 == result2
        assert isinstance(result1["text"], str) and result1["text"]
        assert result1["stop_reason"] == "stop"
        assert result1["model"] == deployment.default_model
        assert result1["usage"]["input_tokens"] == 100
        assert result1["usage"]["output_tokens"] > 0
        assert result1["usage"]["total_tokens"] == (
            result1["usage"]["input_tokens"] + result1["usage"]["output_tokens"]
        )

    @pytest.mark.asyncio
    async def test_complete_response_varies_with_input(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()

        r1 = await client.complete(
            [{"role": "user", "content": "hello there"}], http_client=transport
        )
        r2 = await client.complete(
            [{"role": "user", "content": "calculate 9 - 3"}], http_client=transport
        )

        assert r1["text"] != r2["text"]

    @pytest.mark.asyncio
    async def test_complete_contextual_math_response_is_deterministic(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()
        messages = [
            {
                "role": "user",
                "content": "A train travels 300 km and then 450 km more, over 4 hours",
            }
        ]

        result = await client.complete(messages, http_client=transport)

        assert "75 km/hour" in result["text"]
        # Determinism: a second identical call yields byte-identical text.
        result_again = await client.complete(messages, http_client=transport)
        assert result_again["text"] == result["text"]

    @pytest.mark.asyncio
    async def test_complete_across_two_fresh_transports_is_still_deterministic(
        self,
    ) -> None:
        """No shared instance state, no process-hash-randomized id -- two
        independently constructed transports produce byte-identical output
        for the same input."""
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        messages = [
            {"role": "user", "content": "explain step by step how gravity works"}
        ]

        r1 = await client.complete(messages, http_client=MockLlmHttpClient())
        r2 = await client.complete(messages, http_client=MockLlmHttpClient())

        assert r1 == r2


# ---------------------------------------------------------------------------
# 2. stream() -- concatenation == complete() content, terminal handled
# ---------------------------------------------------------------------------


class TestStreamViaMockTransport:
    @pytest.mark.asyncio
    async def test_stream_concatenation_matches_complete_content(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()
        messages = [
            {"role": "user", "content": "Explain step by step how gravity works"}
        ]

        full = await client.complete(messages, http_client=transport)

        chunks = []
        async for chunk in client.stream(messages, http_client=transport):
            chunks.append(chunk)

        assert len(chunks) > 1, "expected multiple word-by-word streaming chunks"
        concatenated = "".join(c.get("text", "") for c in chunks)
        assert concatenated == full["text"]

    @pytest.mark.asyncio
    async def test_stream_terminal_chunk_carries_stop_reason(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()
        messages = [{"role": "user", "content": "hi"}]

        chunks = []
        async for chunk in client.stream(messages, http_client=transport):
            chunks.append(chunk)

        # The [DONE] sentinel line is skipped by _parse_stream_line; the last
        # yielded chunk is the terminal finish_reason="stop" frame.
        assert chunks[-1]["stop_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_stream_is_deterministic_across_calls(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        messages = [{"role": "user", "content": "plan a systematic approach"}]

        chunks1 = [
            c async for c in client.stream(messages, http_client=MockLlmHttpClient())
        ]
        chunks2 = [
            c async for c in client.stream(messages, http_client=MockLlmHttpClient())
        ]

        assert chunks1 == chunks2

    @pytest.mark.asyncio
    async def test_direct_stream_lines_yields_sse_frames_with_done_terminal(
        self,
    ) -> None:
        """Exercise MockLlmHttpClient.stream_lines() directly (below the
        LlmClient/_parse_stream_line layer) to assert the raw SSE framing
        contract: 'data: {json}' lines, terminal 'data: [DONE]'."""
        transport = MockLlmHttpClient()
        body = (
            b'{"model": "mock-model", "messages": [{"role": "user", "content": "hi"}]}'
        )

        lines = [
            line
            async for line in transport.stream_lines(
                "POST",
                "https://example.com/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                content=body,
            )
        ]

        assert lines[-1] == "data: [DONE]"
        assert all(line.startswith("data: ") for line in lines)


# ---------------------------------------------------------------------------
# 3. embed() -- deterministic vectors, dimension, L2-normalization
# ---------------------------------------------------------------------------


class TestEmbedViaMockTransport:
    @pytest.mark.asyncio
    async def test_embed_deterministic_and_default_dimension(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()

        v1 = await client.embed(
            ["hello world"], model="mock-embedding", http_client=transport
        )
        v2 = await client.embed(
            ["hello world"], model="mock-embedding", http_client=transport
        )

        assert v1 == v2
        assert len(v1) == 1
        assert len(v1[0]) == 1536

    @pytest.mark.asyncio
    async def test_embed_normalized_by_default(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()

        vectors = await client.embed(
            ["normalize me"], model="mock-embedding", http_client=transport
        )

        magnitude = sum(x * x for x in vectors[0]) ** 0.5
        assert magnitude == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_embed_unnormalized_when_disabled(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient(normalize=False)

        vectors = await client.embed(
            ["raw vector please"], model="mock-embedding", http_client=transport
        )

        magnitude = sum(x * x for x in vectors[0]) ** 0.5
        # A 1536-dim standard-gaussian vector's magnitude concentrates near
        # sqrt(1536) ~= 39.2, nowhere near a normalized 1.0.
        assert magnitude != pytest.approx(1.0, abs=1e-3)

    @pytest.mark.asyncio
    async def test_embed_respects_custom_dimensions_option(self) -> None:
        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()

        vectors = await client.embed(
            ["a", "b"],
            model="mock-embedding",
            options=EmbedOptions(dimensions=384),
            http_client=transport,
        )

        assert len(vectors) == 2
        assert all(len(v) == 384 for v in vectors)
        # Different input text -> different (md5-seeded) vector.
        assert vectors[0] != vectors[1]

    @pytest.mark.asyncio
    async def test_embed_seed_scoped_per_call_no_global_random_mutation(self) -> None:
        """The embedding RNG is a per-call `random.Random(seed)` instance,
        never the process-global `random` module -- so using
        MockLlmHttpClient must not perturb an unrelated caller's global
        random state."""
        import random

        random.seed(42)
        expected_next = random.random()
        random.seed(42)

        deployment = mock_preset()
        client = LlmClient.from_deployment(deployment)
        transport = MockLlmHttpClient()
        await client.embed(
            ["side effect check"], model="mock-embedding", http_client=transport
        )

        actual_next = random.random()
        assert actual_next == expected_next


# ---------------------------------------------------------------------------
# 4. MockLlmHttpClient direct unit coverage -- lifecycle + typed errors
# ---------------------------------------------------------------------------


class TestMockLlmHttpClientDirect:
    def test_exposes_llmhttpclient_interface(self) -> None:
        transport = MockLlmHttpClient()
        for method in ("post", "get", "request", "stream_lines", "aclose"):
            assert callable(
                getattr(transport, method, None)
            ), f"MockLlmHttpClient missing callable {method}()"
        assert transport.is_closed is False

    @pytest.mark.asyncio
    async def test_async_context_manager_closes_on_exit(self) -> None:
        async with MockLlmHttpClient() as transport:
            assert transport.is_closed is False
        assert transport.is_closed is True

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self) -> None:
        transport = MockLlmHttpClient()
        await transport.aclose()
        await transport.aclose()
        assert transport.is_closed is True

    @pytest.mark.asyncio
    async def test_post_after_close_raises_runtime_error(self) -> None:
        transport = MockLlmHttpClient()
        await transport.aclose()

        with pytest.raises(RuntimeError, match="closed"):
            await transport.post(
                "https://example.com/v1/chat/completions",
                content=b'{"model": "m", "messages": []}',
            )

    @pytest.mark.asyncio
    async def test_stream_lines_after_close_raises_runtime_error(self) -> None:
        transport = MockLlmHttpClient()
        await transport.aclose()

        with pytest.raises(RuntimeError, match="closed"):
            async for _ in transport.stream_lines(
                "POST",
                "https://example.com/v1/chat/completions",
                content=b'{"model": "m", "messages": []}',
            ):
                pass

    @pytest.mark.asyncio
    async def test_unsupported_endpoint_path_raises_typed_error(self) -> None:
        transport = MockLlmHttpClient()

        with pytest.raises(UnsupportedMockRequest):
            await transport.post(
                "https://example.com/v1/unsupported-endpoint",
                content=b"{}",
            )

    @pytest.mark.asyncio
    async def test_request_without_content_or_json_raises_typed_error(self) -> None:
        transport = MockLlmHttpClient()

        with pytest.raises(UnsupportedMockRequest):
            await transport.post("https://example.com/v1/chat/completions")

    @pytest.mark.asyncio
    async def test_request_with_malformed_json_body_raises_typed_error(self) -> None:
        transport = MockLlmHttpClient()

        with pytest.raises(UnsupportedMockRequest):
            await transport.post(
                "https://example.com/v1/chat/completions",
                content=b"not valid json{{{",
            )

    @pytest.mark.asyncio
    async def test_chat_completion_missing_messages_raises_typed_error(self) -> None:
        transport = MockLlmHttpClient()

        with pytest.raises(UnsupportedMockRequest):
            await transport.post(
                "https://example.com/v1/chat/completions",
                content=b'{"model": "mock-model"}',
            )

    @pytest.mark.asyncio
    async def test_embeddings_missing_input_raises_typed_error(self) -> None:
        transport = MockLlmHttpClient()

        with pytest.raises(UnsupportedMockRequest):
            await transport.post(
                "https://example.com/v1/embeddings",
                content=b'{"model": "mock-embedding"}',
            )

    @pytest.mark.asyncio
    async def test_get_requests_raise_typed_error(self) -> None:
        transport = MockLlmHttpClient()

        with pytest.raises(UnsupportedMockRequest):
            await transport.get("https://example.com/v1/models")

    @pytest.mark.asyncio
    async def test_post_returns_valid_httpx_response_shape(self) -> None:
        transport = MockLlmHttpClient()

        resp = await transport.post(
            "https://example.com/v1/chat/completions",
            content=b'{"model": "mock-model", "messages": [{"role": "user", "content": "hi"}]}',
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"]["content"]
        assert resp.headers.get("retry-after") is None
