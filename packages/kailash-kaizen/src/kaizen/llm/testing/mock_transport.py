# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MockLlmHttpClient — deterministic, offline, in-process transport (#1720
Wave-1b MOCK shard).

The four-axis ``LlmClient`` (``kaizen.llm.client``) always sends real HTTP
via ``LlmHttpClient`` (``kaizen.llm.http_client``) — every one of
``complete()`` / ``stream()`` / ``embed()`` accepts an ``http_client=``
injection parameter but has no offline in-process response path of its own.
``MockLlmHttpClient`` is that path: a **Protocol-satisfying deterministic
adapter** (per ``rules/testing.md`` § "3-Tier Testing" -- NOT a
Tier-2/3-blocked mock) that exposes the SAME async surface
``kaizen.llm.client.LlmClient`` calls on ``LlmHttpClient``
(``post`` / ``get`` / ``request`` / ``stream_lines`` / ``aclose`` /
``__aenter__`` / ``__aexit__`` / ``is_closed``) and returns DETERMINISTIC
OpenAI-shaped JSON WITHOUT ever constructing an ``httpx.AsyncClient`` or
opening a socket.

Usage::

    from kaizen.llm.testing import mock_preset, MockLlmHttpClient

    client = LlmClient.from_deployment(mock_preset())
    transport = MockLlmHttpClient()
    result = await client.complete(messages, http_client=transport)
    # -- zero network I/O; result is openai_chat.parse_response()'s
    #    normalized {text, usage, stop_reason, model} dict.

# Why this is a Protocol-satisfying adapter, not a blocked mock

``rules/testing.md`` blocks ``unittest.mock`` / ``MagicMock`` / ``@patch``
substitution in Tier 2/3 tests because those hide real infrastructure
behaviour (connection handling, schema drift, transaction semantics) behind
a stand-in that always agrees with the caller. ``MockLlmHttpClient`` is the
documented exception: "a class satisfying a ``typing.Protocol`` at runtime
with deterministic output is NOT a mock" (``rules/testing.md`` § "3-Tier
Testing"). It implements the SAME method signatures
``kaizen.llm.client.LlmClient`` calls, returns a SHAPE the production wire
shapers (``openai_chat.parse_response`` / ``openai_embeddings.parse_response``)
already consume unchanged, and its output is a pure function of its input
(md5-seeded, no unseeded ``random``, no wall-clock dependence except a fixed
constant ``created`` timestamp). It is a Tier-1 offline-by-construction test
double for the wire boundary, not a Tier-2/3 substitute for real
infrastructure.

# Physical separation invariant (#788 pattern, extended)

This module lives under ``kaizen.llm.testing`` -- the SAME physically
separated, test-only package that houses ``mock_preset()``. The invariant
``mock_preset.py``'s docstring documents (production code MUST NOT import
``kaizen.llm.testing``; the import path is the deliberate red flag,
grep-able via ``grep -rn 'kaizen.llm.testing' src/``) applies identically to
``MockLlmHttpClient``. ``tests/unit/llm/test_mock_preset_isolation.py``
extends its structural-defense suite to assert ``MockLlmHttpClient`` is
absent from the production import surface (``kaizen.llm.client`` /
``kaizen.llm.http_client`` / ``kaizen.llm.presets``).

# Determinism contract

Every response is a pure function of the request payload:

* Chat completion text is chosen by ``_generate_contextual_response`` --
  a deterministic keyword-shaped generator ported from the legacy
  ``kaizen.providers.llm.mock.MockProvider`` (contextual math / reasoning /
  planning / debate / JSON-shaped-agent-output responses). This IS
  keyword-matching, but it is a TEST-DOUBLE response generator producing
  canned test data -- not an agent decision path -- so
  ``rules/agent-reasoning.md`` (LLM-first reasoning; no keyword routing in
  AGENT decision logic) does not apply. No production agent ever runs this
  code; it exists to give offline tests a stable, inspectable chat reply.
* Embedding vectors are md5-seeded via a PER-CALL ``random.Random(seed)``
  instance (never the process-global ``random`` module, so this transport
  is safe to use concurrently and does not perturb any other test's
  randomness), matching the legacy ``MockProvider.embed`` seeding contract
  (``seed = md5(f"{model}:{text}")``) but scoped correctly.
* The chat-completion ``id`` is also md5-derived from ``model`` + the last
  user message -- deterministic, unlike the legacy provider's
  process-hash-randomized ``hash(last_user_message)``.

Given the SAME request payload, EVERY field of the response is byte-for-byte
identical across calls and across processes (Python's hash randomization
never enters the picture).
"""

from __future__ import annotations

import hashlib
import json
import random
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

import httpx

# ---------------------------------------------------------------------------
# Typed errors -- zero-tolerance Rule 3 (no silent fallback on an
# unsupported/malformed request shape).
# ---------------------------------------------------------------------------


class UnsupportedMockRequest(ValueError):
    """Raised when ``MockLlmHttpClient`` cannot determine, or does not
    support, the requested wire shape.

    Covers: a request body carrying neither ``content=`` bytes nor a
    ``json=`` kwarg (nothing to parse), a body that is not valid JSON, a
    body that is not a JSON object, or a URL whose path does not match one
    of the two shapes ``mock_preset()``'s ``WireProtocol.OpenAiChat``
    deployment ever targets (``.../chat/completions``,
    ``.../embeddings``). Per ``rules/zero-tolerance.md`` Rule 3 this is a
    LOUD typed error, never a fabricated 200 response.
    """


# ---------------------------------------------------------------------------
# Deterministic chat-completion text generator (ported from the legacy
# kaizen.providers.llm.mock.MockProvider._generate_contextual_response).
# Pure function of its inputs -- no randomness, no wall-clock dependence.
# ---------------------------------------------------------------------------


def _generate_contextual_response(
    message_lower: str,
    conversation_text: str,
    has_images: bool,
    original_message: str,
) -> str:
    if has_images:
        return (
            "I can see the image(s) you've provided. The image contains several "
            "distinct elements that I can analyze for you. "
            "[Mock vision response with detailed observation]"
        )

    if any(
        pattern in message_lower
        for pattern in [
            "calculate",
            "math",
            "time",
            "hour",
            "minute",
            "second",
            "duration",
        ]
    ) or any(
        op in message_lower
        for op in ["+", "-", "*", "/", "plus", "minus", "times", "divide"]
    ):
        if (
            "train" in conversation_text
            and "travels" in conversation_text
            and any(num in conversation_text for num in ["300", "450", "4"])
        ):
            return (
                "Step 1: Calculate the train's speed\n"
                "First, I need to find the train's speed using the given information.\n"
                "Given: Distance = 300 km, Time = 4 hours\n"
                "Speed = Distance / Time = 300 km / 4 hours = 75 km/hour\n\n"
                "Step 2: Apply the speed to find time for new distance\n"
                "Now I can use this speed to find how long it takes to travel 450 km.\n"
                "Given: Speed = 75 km/hour, Distance = 450 km\n"
                "Time = Distance / Speed = 450 km / 75 km/hour = 6 hours\n\n"
                "Final Answer: 6 hours"
            )
        if (
            "9" in message_lower
            and "3" in message_lower
            and ("-" in message_lower or "minus" in message_lower)
        ) or (
            "time" in message_lower
            and any(num in message_lower for num in ["9", "3", "6"])
        ):
            return (
                "Let me calculate this step by step:\n\n"
                "1. Starting with 9\n2. Subtracting 3: 9 - 3 = 6\n"
                "3. The result is 6\n\n"
                "So the answer is 6 hours. This represents a time duration of 6 hours."
            )
        if any(
            op in message_lower
            for op in ["+", "-", "*", "/", "plus", "minus", "times", "divide"]
        ):
            return (
                "I'll solve this mathematical problem step by step:\n\n"
                "1. First, I'll identify the operation\n"
                "2. Then apply the calculation\n"
                "3. Finally, provide the result with explanation\n\n"
                "The calculation shows a clear mathematical relationship."
            )
        if any(
            tw in message_lower
            for tw in ["time", "hour", "minute", "second", "duration"]
        ):
            return (
                "I'll help you with this time calculation. Let me work through this systematically:\n\n"
                "1. Identifying the time units involved\n"
                "2. Performing the calculation\n"
                "3. Providing the result in appropriate time format\n\n"
                "Time calculations require careful attention to units and precision."
            )
        return (
            "I'll help you with this calculation. Let me work through this "
            "systematically to provide an accurate result with proper explanation "
            "of the mathematical process."
        )

    if any(
        p in message_lower
        for p in [
            "step by step",
            "think through",
            "reasoning",
            "explain",
            "how do",
            "why does",
        ]
    ):
        return (
            "Let me think through this step by step:\n\n"
            "1. **Understanding the problem**: I need to break down the key components\n"
            "2. **Analyzing the context**: Looking at the relevant factors and constraints\n"
            "3. **Reasoning process**: Working through the logical connections\n"
            "4. **Arriving at conclusion**: Based on the systematic analysis\n\n"
            "This step-by-step approach ensures thorough reasoning and accurate results."
        )

    if any(
        p in message_lower
        for p in ["plan", "action", "strategy", "approach", "implement", "execute"]
    ):
        return (
            "**Thought**: I need to analyze this request and determine the best approach.\n\n"
            "**Action**: Let me break this down into actionable steps:\n"
            "1. Assess the current situation\n"
            "2. Identify required resources and constraints\n"
            "3. Develop a systematic plan\n"
            "4. Execute with monitoring\n\n"
            "**Observation**: This approach allows for systematic problem-solving with clear action items.\n\n"
            "**Final Action**: Proceeding with the structured implementation plan."
        )

    if any(
        p in message_lower
        for p in ["analyze", "data", "pattern", "trend", "statistics"]
    ):
        return (
            "Based on my analysis of the provided data, I can identify several key patterns:\n\n"
            "- **Trend Analysis**: The data shows distinct patterns over time\n"
            "- **Statistical Insights**: Key metrics indicate significant relationships\n"
            "- **Pattern Recognition**: I've identified recurring themes and anomalies\n"
            "- **Recommendations**: Based on this analysis, I suggest specific next steps"
        )

    if any(
        p in message_lower
        for p in ["create", "generate", "write", "compose", "design", "build"]
    ):
        return (
            "I'll help you create that. Let me approach this systematically:\n\n"
            "**Planning Phase**:\n- Understanding your requirements\n- Identifying key components needed\n\n"
            "**Creation Process**:\n- Developing the core structure\n- Adding details and refinements\n\n"
            "**Quality Assurance**:\n- Reviewing for completeness\n- Ensuring it meets your needs"
        )

    if "?" in message_lower or any(
        p in message_lower
        for p in ["what is", "how does", "why is", "when does", "where is"]
    ):
        return (
            f"Regarding your question about '{original_message[:100]}...', here's a comprehensive answer:\n\n"
            "The key points to understand are:\n"
            "- **Primary concept**: This relates to fundamental principles\n"
            "- **Practical application**: How this applies in real-world scenarios\n"
            "- **Important considerations**: Factors to keep in mind\n"
            "- **Next steps**: Recommendations for further exploration"
        )

    if any(
        p in message_lower
        for p in ["problem", "issue", "error", "fix", "solve", "troubleshoot"]
    ):
        return (
            "I'll help you solve this problem systematically:\n\n"
            "**Problem Analysis**:\n- Identifying the core issue\n- Understanding contributing factors\n\n"
            "**Solution Development**:\n- Exploring potential approaches\n- Evaluating pros and cons\n\n"
            "**Implementation Plan**:\n- Step-by-step resolution process\n- Monitoring and validation steps"
        )

    if any(
        p in message_lower
        for p in ["tool", "function", "call", "api", "service", "endpoint"]
    ):
        return (
            "I'll help you with this tool/function call. Let me identify the appropriate tools "
            "and execute them systematically:\n\n"
            "**Tool Selection**: Identifying the best tools for this task\n"
            "**Parameter Preparation**: Setting up the required parameters\n"
            "**Execution**: Calling the tools with proper error handling\n"
            "**Result Processing**: Interpreting and formatting the results\n\n"
            "This ensures reliable tool execution with comprehensive error handling."
        )

    if any(
        p in message_lower for p in ["code", "algorithm", "script", "program", "debug"]
    ):
        return (
            "I'll help you with this technical implementation:\n\n"
            "```\n# Technical solution approach\n"
            "# 1. Understanding requirements\n"
            "# 2. Designing the solution\n"
            "# 3. Implementation details\n"
            "# 4. Testing and validation\n```\n\n"
            "This approach ensures robust, maintainable code with proper error handling."
        )

    if any(
        p in message_lower
        for p in ["explain", "teach", "learn", "understand", "clarify"]
    ):
        return (
            "Let me explain this concept clearly:\n\n"
            "**Foundation**: Starting with the basic principles\n"
            "**Key Concepts**: The essential ideas you need to understand\n"
            "**Examples**: Practical illustrations to make it concrete\n"
            "**Application**: How to use this knowledge effectively\n\n"
            "This explanation provides a solid foundation for understanding."
        )

    if any(
        p in message_lower
        for p in [
            "argument",
            "debate",
            "position",
            "for or against",
            "key_points",
            "evidence",
            "argue about",
            "topic to argue",
        ]
    ) or (
        "topic" in message_lower
        and ("for" in message_lower or "against" in message_lower)
    ):
        return json.dumps(
            {
                "argument": "This is a well-reasoned argument supporting the given position with logical analysis and evidence-based conclusions.",
                "key_points": [
                    "Point 1: Analysis of key factors",
                    "Point 2: Supporting evidence and reasoning",
                    "Point 3: Practical implications",
                ],
                "evidence": "Research and analysis support this position based on established principles and documented outcomes.",
            }
        )

    if any(
        p in message_lower
        for p in ["judgment", "decision", "winner", "judge", "verdict"]
    ):
        return json.dumps(
            {
                "decision": "for",
                "winner": "proponent",
                "reasoning": "After careful analysis of both arguments, the proponent presented stronger evidence and more compelling logic.",
                "confidence": 0.85,
            }
        )

    if any(
        p in message_lower
        for p in ["rebuttal", "counterpoint", "counter argument", "rebut"]
    ):
        return json.dumps(
            {
                "rebuttal": "This rebuttal addresses the key weaknesses in the opposing argument with focused counterpoints.",
                "counterpoints": [
                    "Counter 1: Logical flaw in premise",
                    "Counter 2: Missing evidence for claims",
                    "Counter 3: Alternative interpretation",
                ],
                "strength": 0.75,
            }
        )

    if any(
        p in message_lower
        for p in ["step1", "step2", "step3", "final_answer", "confidence"]
    ):
        return json.dumps(
            {
                "step1": "First, I identify and understand the problem components.",
                "step2": "Next, I analyze the relevant factors and constraints.",
                "step3": "Then, I develop a systematic approach to solve the problem.",
                "step4": "I apply the method and verify intermediate results.",
                "step5": "Finally, I synthesize the findings into a coherent answer.",
                "final_answer": "Based on the step-by-step analysis, the answer is derived systematically.",
                "confidence": 0.85,
            }
        )

    if len(original_message) > 100:
        return (
            f"I understand you're asking about '{original_message[:100]}...'. "
            "This is a complex topic that requires careful consideration of multiple factors. "
            "Let me provide a thorough response that addresses your key concerns and offers actionable insights."
        )
    return (
        f"I understand your request about '{original_message}'. "
        "Based on the context and requirements, I can provide a comprehensive response "
        "that addresses your specific needs with practical solutions and clear explanations."
    )


def _extract_last_user_message_and_conversation(
    messages: List[Dict[str, Any]],
) -> tuple[str, str, bool]:
    """Port of the legacy MockProvider.chat() message-shape extraction.

    Returns ``(last_user_message, conversation_text_lower, has_images)``.
    Handles both plain-string ``content`` and multimodal
    ``[{"type": "text"|"image"|"image_url", ...}]`` content lists.
    """
    full_conversation: List[str] = []
    has_images = False
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else None
        if role in ("user", "system", "assistant"):
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts: List[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type in ("image", "image_url"):
                        has_images = True
                full_conversation.append(f"{role}: {' '.join(text_parts)}")
            else:
                full_conversation.append(f"{role}: {content}")

    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type in ("image", "image_url"):
                        has_images = True
                last_user_message = " ".join(text_parts)
            else:
                last_user_message = (
                    content if isinstance(content, str) else str(content)
                )
            break

    conversation_text = " ".join(full_conversation).lower()
    return last_user_message, conversation_text, has_images


def _build_chat_completion_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic OpenAI ``chat.completion`` response body.

    Consumed unchanged by ``kaizen.llm.wire_protocols.openai_chat.parse_response``.
    """
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise UnsupportedMockRequest(
            "MockLlmHttpClient: chat completion request missing a 'messages' "
            f"list; got {type(messages).__name__ if messages is not None else 'None'}"
        )
    model = payload.get("model") or "mock-model"
    last_user_message, conversation_text, has_images = (
        _extract_last_user_message_and_conversation(messages)
    )
    message_lower = (last_user_message or "").lower()
    response_content = _generate_contextual_response(
        message_lower, conversation_text, has_images, last_user_message
    )
    deterministic_id = hashlib.md5(
        f"{model}:{last_user_message}".encode("utf-8")
    ).hexdigest()[:16]
    completion_tokens = max(len(response_content) // 4, 1)
    return {
        "id": f"chatcmpl-mock-{deterministic_id}",
        "object": "chat.completion",
        "created": 1701234567,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": completion_tokens,
            "total_tokens": 100 + completion_tokens,
        },
    }


def _split_preserving_whitespace(content: str) -> List[str]:
    """Split ``content`` on whitespace boundaries, preserving separators, so
    the concatenation of every returned piece reconstructs ``content``
    byte-for-byte. Ported from the legacy ``MockProvider.stream_chat``.
    """
    pieces: List[str] = []
    current = ""
    for ch in content:
        if ch.isspace() and current:
            pieces.append(current)
            current = ch
        else:
            current += ch
    if current:
        pieces.append(current)
    if not pieces:
        pieces = [content or ""]
    return pieces


# ---------------------------------------------------------------------------
# Deterministic embeddings response builder.
# ---------------------------------------------------------------------------


def _deterministic_embedding(
    model: str, text: str, dimensions: int, *, normalize: bool
) -> List[float]:
    """md5-seed a PER-CALL ``random.Random`` instance -- never the global
    ``random`` module -- so this transport never perturbs another test's
    randomness and stays deterministic under concurrent use.
    """
    seed_material = f"{model}:{text}".encode("utf-8")
    seed = int(hashlib.md5(seed_material).hexdigest()[:8], 16)
    rng = random.Random(seed)
    vector = [rng.gauss(0.0, 1.0) for _ in range(dimensions)]
    if normalize:
        magnitude = sum(v * v for v in vector) ** 0.5
        if magnitude > 0:
            vector = [v / magnitude for v in vector]
    return vector


def _build_embeddings_response(
    payload: Dict[str, Any], *, normalize: bool
) -> Dict[str, Any]:
    """Build a deterministic OpenAI ``embeddings`` response body.

    Consumed unchanged by
    ``kaizen.llm.wire_protocols.openai_embeddings.parse_response``.
    """
    texts = payload.get("input")
    if not isinstance(texts, list) or not texts:
        raise UnsupportedMockRequest(
            "MockLlmHttpClient: embeddings request missing a non-empty "
            f"'input' list; got {texts!r}"
        )
    for idx, t in enumerate(texts):
        if not isinstance(t, str):
            raise UnsupportedMockRequest(
                f"MockLlmHttpClient: embeddings request 'input[{idx}]' must be "
                f"str; got {type(t).__name__}"
            )
    model = payload.get("model") or "mock-embedding"
    dimensions = payload.get("dimensions") or 1536
    if not isinstance(dimensions, int) or dimensions <= 0:
        raise UnsupportedMockRequest(
            f"MockLlmHttpClient: embeddings request 'dimensions' must be a "
            f"positive int; got {dimensions!r}"
        )
    data = []
    for idx, text in enumerate(texts):
        vector = _deterministic_embedding(model, text, dimensions, normalize=normalize)
        data.append({"object": "embedding", "index": idx, "embedding": vector})
    total_tokens = sum(max(len(t) // 4, 1) for t in texts)
    return {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    }


# ---------------------------------------------------------------------------
# Request-body extraction -- LlmClient.complete()/stream() pass a raw
# `content=` byte-string body; LlmClient.embed() passes a `json=` dict.
# Both are normalized to a plain dict here.
# ---------------------------------------------------------------------------


def _extract_request_payload(
    *, content: Any = None, json_body: Any = None
) -> Dict[str, Any]:
    if json_body is not None:
        if not isinstance(json_body, dict):
            raise UnsupportedMockRequest(
                "MockLlmHttpClient: json= body must be a dict; got "
                f"{type(json_body).__name__}"
            )
        return json_body
    if content is not None:
        if isinstance(content, (bytes, bytearray)):
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise UnsupportedMockRequest(
                    "MockLlmHttpClient: content= body is not valid UTF-8"
                ) from exc
        elif isinstance(content, str):
            decoded = content
        else:
            raise UnsupportedMockRequest(
                "MockLlmHttpClient: content= body must be bytes or str; got "
                f"{type(content).__name__}"
            )
        try:
            obj = json.loads(decoded)
        except ValueError as exc:
            raise UnsupportedMockRequest(
                "MockLlmHttpClient: content= body is not valid JSON"
            ) from exc
        if not isinstance(obj, dict):
            raise UnsupportedMockRequest(
                "MockLlmHttpClient: content= body must decode to a JSON object; "
                f"got {type(obj).__name__}"
            )
        return obj
    raise UnsupportedMockRequest(
        "MockLlmHttpClient: request carries neither content= bytes nor a "
        "json= dict -- cannot determine the response shape"
    )


def _url_path(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/")


# ---------------------------------------------------------------------------
# MockLlmHttpClient -- the offline in-process transport.
# ---------------------------------------------------------------------------


class MockLlmHttpClient:
    """Deterministic, offline, in-process transport satisfying the same
    async surface ``kaizen.llm.client.LlmClient`` calls on
    ``kaizen.llm.http_client.LlmHttpClient``.

    Constructed with NO real transport underneath -- ``post()`` / ``get()`` /
    ``request()`` / ``stream_lines()`` never construct an
    ``httpx.AsyncClient`` and never open a socket. Responses are built
    in-process from ``httpx.Response(status_code=..., json=..., request=...)``
    -- a pure Python object construction, not a network send.

    Only the two shapes ``mock_preset()``'s ``WireProtocol.OpenAiChat``
    deployment ever targets are supported: a chat-completions URL
    (``.../chat/completions``) and an embeddings URL (``.../embeddings``).
    Any other URL, or a request body ``MockLlmHttpClient`` cannot parse,
    raises :class:`UnsupportedMockRequest` -- a typed error, never a
    fabricated success response (``rules/zero-tolerance.md`` Rule 3).

    Example::

        from kaizen.llm import LlmClient
        from kaizen.llm.testing import mock_preset, MockLlmHttpClient

        client = LlmClient.from_deployment(mock_preset())
        transport = MockLlmHttpClient()
        result = await client.complete(
            [{"role": "user", "content": "hello"}], http_client=transport,
        )
        assert result["text"]

        vectors = await client.embed(["a", "b"], model="mock-embedding",
                                      http_client=transport)
        assert len(vectors) == 2
    """

    __slots__ = ("_closed", "_normalize")

    # #1779 duck-typed mock marker. Read by production code
    # (``LlmClient._enforce_lazy_governance``) via ``getattr(transport,
    # "is_mock_transport", False)`` so the governance gate can exempt an
    # injected mock transport WITHOUT production code importing from
    # ``kaizen.llm.testing`` (which the test-isolation invariant forbids). A
    # class attribute coexists with ``__slots__`` (it is not an instance slot).
    is_mock_transport: bool = True

    def __init__(self, *, normalize: bool = True) -> None:
        """``normalize``: L2-normalize embedding vectors (default ``True``,
        matching the legacy ``MockProvider.embed`` contract). Set ``False``
        to get raw (unnormalized) deterministic gaussian vectors -- useful
        for tests asserting the normalization behavior itself.
        """
        self._closed = False
        self._normalize = normalize

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> "MockLlmHttpClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Idempotent close -- mirrors ``LlmHttpClient.aclose()``."""
        self._closed = True

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        content: Any = None,
        auth_strategy_kind: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Build an in-process ``httpx.Response`` -- NO network I/O.

        Mirrors ``LlmHttpClient.request()``'s signature. ``**kwargs`` may
        carry ``json=`` (used by ``LlmClient.embed()``); ``content=`` (used
        by ``LlmClient.complete()`` / ``stream()``) is a named parameter for
        signature parity with the production client.
        """
        if self._closed:
            raise RuntimeError(
                "MockLlmHttpClient is closed; cannot issue new requests "
                "(construct a new instance or avoid aclose() before reuse)"
            )
        if method.upper() != "GET":
            payload = _extract_request_payload(
                content=content, json_body=kwargs.get("json")
            )
            path = _url_path(url)
            if path.endswith("/embeddings"):
                body = _build_embeddings_response(payload, normalize=self._normalize)
            elif path.endswith("/chat/completions"):
                body = _build_chat_completion_response(payload)
            else:
                raise UnsupportedMockRequest(
                    "MockLlmHttpClient does not support the requested endpoint "
                    f"shape: {url!r}. Supported: '.../chat/completions' (OpenAI "
                    "chat) and '.../embeddings' (OpenAI embeddings) -- the two "
                    "shapes produced by mock_preset()'s WireProtocol.OpenAiChat "
                    "deployment."
                )
        else:
            raise UnsupportedMockRequest(
                "MockLlmHttpClient does not support GET requests -- no "
                "production kaizen.llm code path issues a GET through "
                "LlmHttpClient today"
            )
        request_obj = httpx.Request(
            method, url, headers=dict(headers) if headers else None
        )
        return httpx.Response(200, json=body, request=request_obj)

    async def stream_lines(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        content: Any = None,
        auth_strategy_kind: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Yield deterministic SSE ``data: {json}`` lines -- NO network I/O.

        The concatenation of every yielded chunk's ``choices[0].delta.content``
        reconstructs the SAME chat text ``request()``/``post()`` would return
        for an equivalent non-streaming request against the same payload.
        Terminates with a bare ``data: [DONE]`` sentinel line, matching the
        OpenAI SSE contract ``kaizen.llm.client._parse_stream_line`` expects
        (it strips the ``data:`` prefix and skips ``[DONE]``).
        """
        if self._closed:
            raise RuntimeError(
                "MockLlmHttpClient is closed; cannot issue new requests "
                "(construct a new instance or avoid aclose() before reuse)"
            )
        payload = _extract_request_payload(
            content=content, json_body=kwargs.get("json")
        )
        path = _url_path(url)
        if not path.endswith("/chat/completions"):
            raise UnsupportedMockRequest(
                "MockLlmHttpClient.stream_lines only supports a "
                f"'.../chat/completions' URL; got {url!r}"
            )
        chat_response = _build_chat_completion_response(payload)
        full_content = chat_response["choices"][0]["message"]["content"]
        model = chat_response["model"]
        response_id = chat_response["id"]
        created = chat_response["created"]

        for piece in _split_preserving_whitespace(full_content):
            chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {"index": 0, "delta": {"content": piece}, "finish_reason": None}
                ],
            }
            yield f"data: {json.dumps(chunk)}"

        final_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": chat_response["usage"],
        }
        yield f"data: {json.dumps(final_chunk)}"
        yield "data: [DONE]"


__all__ = ["MockLlmHttpClient", "UnsupportedMockRequest"]
