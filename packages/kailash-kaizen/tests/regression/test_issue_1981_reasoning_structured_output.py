"""Regression tests for issue #1981 — A2A capability scores always 0.0.

The defect
----------
``CapabilityMatchAgent`` / ``TextSimilarityAgent`` never asked their provider
for structured output and never told the model what shape to answer in. Their
``_generate_system_prompt`` overrides replaced BaseAgent's signature-derived
prompt with a paragraph of role prose that names NO output field and never
says "JSON". On any provider that does not enforce a schema natively the model
answered in prose, the strategy returned
``{"response": "<prose>", "error": "JSON_PARSE_FAILED"}``, ``match_score`` was
absent, and ``_coerce_float(None)`` fabricated ``0.0``.

The score then travelled through ``Capability.matches_requirement`` ->
``A2AAgentCard.calculate_match_score`` -> ``A2ACoordinatorNode.
_find_best_agents_for_task`` where EVERY candidate tied at 0.0 and "best agent"
became whichever the sort happened to emit first. A live run produced
``[('eng', 0.0), ('des', 0.0)]`` while the raw agent result carried
``'## Confidence Score\\n\\n**0.92**'`` — the model reasoned correctly; only
the transport of the number failed.

#1973 / PR #1980 made the condition observable (``*.degraded`` at WARN, no
longer cached). It did NOT make scoring correct, and a WARN log is not
reachable by a caller: ``0.0`` remained indistinguishable from a genuine
no-match at the API surface.

What these tests pin
--------------------
1. Both reasoning agents request structured output derived from THEIR OWN
   signature (strict ``json_schema`` where the provider enforces it,
   ``json_object`` + an explicit JSON instruction elsewhere), and never
   inherit a host agent's foreign ``response_format``.
2. A judgment that arrives without a usable score raises the typed
   ``ReasoningDegradedError`` instead of returning a fabricated ``0.0`` — the
   ONE shape an existing caller cannot silently coerce back to zero. A genuine
   ``0.0`` still returns normally, so the two are distinguishable.
3. A cross-provider matrix: a structured-output provider (openai / ollama) and
   one without (anthropic) both reach a non-zero score for a high-confidence
   match, asserted end-to-end through a deterministic fake at the TRANSPORT
   boundary plus the real wire-protocol payload builders.
4. ``_find_best_agents_for_task`` no longer emits an all-zero ranking when the
   judge degraded: degraded cards are excluded and logged, and a round in
   which NO card could be scored raises rather than returning arbitrary order.
"""

import json
import logging
import os

import pytest

from kaizen.core.base_agent import BaseAgentConfig
from kaizen.llm.reasoning import (
    CapabilityMatchSignature,
    ReasoningDegradedError,
    TextSimilaritySignature,
    clear_reasoning_cache,
    get_capability_match_agent,
    get_text_similarity_agent,
    llm_capability_match,
    llm_text_similarity,
)
from kaizen.nodes.ai.a2a import (
    A2AAgentCard,
    A2ACoordinatorNode,
    A2ATask,
    Capability,
    CapabilityLevel,
)

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_reasoning_cache():
    """Agents AND results are memoised per (provider, model) — clear both.

    Without this a config built for ``openai`` in one test hands its cached
    agent to the ``anthropic`` case in the next.
    """
    clear_reasoning_cache()
    yield
    clear_reasoning_cache()


def _config(provider: str, model: str = "test-model", **kw) -> BaseAgentConfig:
    return BaseAgentConfig(llm_provider=provider, model=model, **kw)


def _install_fake_transport(monkeypatch, content):
    """Replace the LAST hop before the network and capture what reached it.

    ``LLMAgentNode._provider_llm_response`` is the transport boundary: config
    resolution, ``response_format`` wiring, system-prompt generation, workflow
    build, strategy parse and output-field extraction — everything this issue
    is about — all still run for real. ``content`` is the provider's reply
    body, or a callable ``provider -> body`` for the cross-provider matrix.

    Returns the list the fake appends each call's ``provider`` / ``model`` /
    ``messages`` / ``generation_config`` to.
    """
    from kaizen.nodes.ai.llm_agent import LLMAgentNode

    captured = []

    def _fake_transport(
        self,
        provider,
        model,
        messages,
        tools,
        generation_config,
        api_key=None,
        base_url=None,
        provider_config=None,
    ):
        captured.append(
            {
                "provider": provider,
                "model": model,
                "messages": messages,
                "generation_config": generation_config,
            }
        )
        body = content(provider) if callable(content) else content
        return {
            "content": body,
            "finish_reason": "stop",
            "model": model,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

    monkeypatch.setattr(LLMAgentNode, "_provider_llm_response", _fake_transport)
    return captured


def _stub_judge_result(monkeypatch, getter_name, payload):
    """Stub the reasoning AGENT to a fixed result dict.

    Used only where the test is about the helper's own return contract (what
    it does with a given judge result), not about the wiring below it.
    """
    import kaizen.llm.reasoning as reasoning

    class _Agent:
        def run(self, **kwargs):
            return payload

    monkeypatch.setattr(reasoning, getter_name, lambda cfg: _Agent())


def _system_message(call) -> str:
    for msg in call["messages"]:
        if msg.get("role") == "system":
            return msg.get("content") or ""
    return ""


def _cap(name: str) -> Capability:
    return Capability(
        name=name,
        domain="engineering",
        level=CapabilityLevel.EXPERT,
        description=f"can do {name}",
        keywords=[name],
    )


def _card(agent_id: str, **caps) -> A2AAgentCard:
    return A2AAgentCard(
        agent_id=agent_id,
        agent_name=agent_id.upper(),
        agent_type="worker",
        version="1.0.0",
        **caps,
    )


# ---------------------------------------------------------------------------
# AC-1 — structured output is requested
# ---------------------------------------------------------------------------


class TestStructuredOutputIsRequested:
    """AC-1: both agents ask for structured output where the provider has it."""

    @pytest.mark.parametrize(
        "getter,score_field",
        [
            (get_capability_match_agent, "match_score"),
            (get_text_similarity_agent, "similarity"),
        ],
    )
    def test_strict_json_schema_on_a_provider_that_enforces_it(
        self, getter, score_field
    ):
        agent = getter(_config("openai"))
        rf = agent.config.response_format

        assert rf is not None, (
            "the reasoning agent asked for no structured output — on any "
            "provider that answers in prose the score is fabricated as 0.0"
        )
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is True
        properties = rf["json_schema"]["schema"]["properties"]
        assert score_field in properties, (
            f"the enforced schema does not carry {score_field!r}; the provider "
            "cannot constrain the one field the caller reads"
        )
        assert agent.config.structured_output_mode == "explicit"

    @pytest.mark.parametrize(
        "getter", [get_capability_match_agent, get_text_similarity_agent]
    )
    def test_json_object_on_a_provider_without_native_schema_support(self, getter):
        # Anthropic /v1/messages has no response_format param; the wire drops
        # it deliberately. The agent still declares json_object AND must carry
        # the instruction in the prompt (asserted below).
        agent = getter(_config("anthropic"))
        assert agent.config.response_format == {"type": "json_object"}

    @pytest.mark.parametrize(
        "getter,signature_cls",
        [
            (get_capability_match_agent, CapabilityMatchSignature),
            (get_text_similarity_agent, TextSimilaritySignature),
        ],
    )
    def test_system_prompt_states_the_output_contract(self, getter, signature_cls):
        agent = getter(_config("anthropic"))
        prompt = agent._generate_system_prompt()

        assert "JSON" in prompt.upper(), (
            "the system prompt never asks for JSON — this is the whole reason "
            "the model answered in prose and match_score went missing"
        )
        for field_name in signature_cls().output_fields:
            assert field_name in prompt, (
                f"output field {field_name!r} is absent from the system prompt; "
                "the model is not told which keys to emit"
            )

    @pytest.mark.parametrize(
        "getter,score_field",
        [
            (get_capability_match_agent, "match_score"),
            (get_text_similarity_agent, "similarity"),
        ],
    )
    def test_host_response_format_is_never_inherited(self, getter, score_field):
        # runtime.py / registry.py hand the HOST agent's config to the judge so
        # the model selection is shared. Copying the host's response_format
        # along with it would force the judge to answer in a schema that has
        # no score field at all.
        host = _config(
            "openai",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "HostSignature",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        agent = getter(host)
        schema = agent.config.response_format["json_schema"]["schema"]
        assert score_field in schema["properties"], (
            "the judge inherited the host agent's schema; it can never emit "
            f"{score_field!r} and every score degrades"
        )
        assert "answer" not in schema["properties"]


# ---------------------------------------------------------------------------
# AC-2 — degradation is distinguishable from a genuine 0.0
# ---------------------------------------------------------------------------


class TestDegradationIsDistinguishableFromZero:
    """AC-2: a parse failure is reachable by the CALLER, not only by a log."""

    def test_json_parse_failure_raises_instead_of_returning_zero(self, monkeypatch):
        _stub_judge_result(
            monkeypatch,
            "get_capability_match_agent",
            {
                "response": "## Confidence Score\n\n**0.92**",
                "error": "JSON_PARSE_FAILED",
            },
        )
        with pytest.raises(ReasoningDegradedError) as excinfo:
            llm_capability_match(
                capability_name="python",
                capability_description="writes python",
                requirement="build an API",
                config=_config("anthropic"),
            )
        assert excinfo.value.error == "JSON_PARSE_FAILED"
        assert excinfo.value.helper == "llm_capability_match"
        assert "0.92" in (excinfo.value.raw_response or ""), (
            "the model's actual answer is dropped; a caller cannot see that "
            "the judge reasoned correctly and only the transport failed"
        )

    def test_absent_score_key_raises(self, monkeypatch):
        _stub_judge_result(
            monkeypatch, "get_capability_match_agent", {"response": "some prose"}
        )
        with pytest.raises(ReasoningDegradedError):
            llm_capability_match(
                capability_name="python",
                capability_description="writes python",
                requirement="build an API",
                config=_config("anthropic"),
            )

    @pytest.mark.parametrize(
        "bad_score", ["high", "", None, [], {}, True, float("nan")]
    )
    def test_unusable_score_value_raises(self, monkeypatch, bad_score):
        # The second silent-zero path: a present-but-uncoercible score fell
        # through _coerce_float's except branch to the 0.0 default and was
        # CACHED as a success.
        _stub_judge_result(
            monkeypatch,
            "get_capability_match_agent",
            {"match_score": bad_score, "matches": True},
        )
        with pytest.raises(ReasoningDegradedError):
            llm_capability_match(
                capability_name="python",
                capability_description="writes python",
                requirement="build an API",
                config=_config("anthropic"),
            )

    def test_a_genuine_zero_is_returned_not_raised(self, monkeypatch):
        # The other half of the contract: 0.0 stays a legitimate answer.
        _stub_judge_result(
            monkeypatch,
            "get_capability_match_agent",
            {"match_score": 0.0, "matches": False, "reasoning": "unrelated domain"},
        )
        score = llm_capability_match(
            capability_name="python",
            capability_description="writes python",
            requirement="bake a cake",
            config=_config("anthropic"),
        )
        assert score == 0.0
        assert isinstance(score, float)

    def test_similarity_helper_carries_the_same_contract(self, monkeypatch):
        # Multi-site parity — the two helpers share one failure shape and must
        # not drift (security.md § Multi-Site Kwarg Plumbing).
        _stub_judge_result(
            monkeypatch, "get_text_similarity_agent", {"error": "JSON_PARSE_FAILED"}
        )
        with pytest.raises(ReasoningDegradedError) as excinfo:
            llm_text_similarity(text_a="a", text_b="b", config=_config("anthropic"))
        assert excinfo.value.helper == "llm_text_similarity"

    def test_degradation_still_warns_and_is_not_cached(self, monkeypatch, caplog):
        # #1973's observability half must survive the contract change.
        from kaizen.llm.reasoning import _CACHE

        _stub_judge_result(
            monkeypatch,
            "get_capability_match_agent",
            {"response": "prose", "error": "JSON_PARSE_FAILED"},
        )
        with caplog.at_level(logging.WARNING, logger="kaizen.llm.reasoning"):
            with pytest.raises(ReasoningDegradedError):
                llm_capability_match(
                    capability_name="python",
                    capability_description="writes python",
                    requirement="build an API",
                    config=_config("anthropic"),
                )
        degraded = [
            r
            for r in caplog.records
            if r.getMessage() == "llm_capability_match.degraded"
        ]
        assert degraded, "the degradation stopped being observable"
        assert getattr(degraded[0], "error", "") == "JSON_PARSE_FAILED"
        assert not _CACHE._match_results, "a parse failure was cached"

    def test_error_carries_the_triage_fields(self, monkeypatch):
        _stub_judge_result(
            monkeypatch,
            "get_capability_match_agent",
            {"response": "prose", "error": "JSON_PARSE_FAILED"},
        )
        with pytest.raises(ReasoningDegradedError) as excinfo:
            llm_capability_match(
                capability_name="python",
                capability_description="writes python",
                requirement="build an API",
                config=_config("anthropic", model="a-model"),
                correlation_id="cid-1981",
            )
        exc = excinfo.value
        assert exc.model == "a-model"
        assert exc.correlation_id == "cid-1981"
        assert "JSON_PARSE_FAILED" in str(exc)


# ---------------------------------------------------------------------------
# AC-3 — cross-provider matrix
# ---------------------------------------------------------------------------


_JUDGE_REPLY = json.dumps(
    {
        "matches": True,
        "match_score": 0.92,
        "reasoning": "the capability names the exact task domain",
    }
)


class TestCrossProviderMatrix:
    """AC-3: a high-confidence match scores non-zero on every provider class."""

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "ollama"])
    def test_high_confidence_match_scores_non_zero_end_to_end(
        self, monkeypatch, provider
    ):
        captured = _install_fake_transport(monkeypatch, _JUDGE_REPLY)

        score = llm_capability_match(
            capability_name="python",
            capability_description="writes python services",
            requirement="build a python API",
            config=_config(provider),
        )

        assert score == pytest.approx(0.92), (
            f"provider {provider!r} produced {score} for a high-confidence "
            "match — the judge's number did not survive the transport"
        )
        assert captured, "the request never reached the transport boundary"
        assert captured[0]["generation_config"].get(
            "response_format"
        ), f"no response_format reached the wire for {provider!r}"

    def test_prose_answer_no_longer_silently_scores_zero(self, monkeypatch):
        # The exact live failure from the issue, end-to-end.
        _install_fake_transport(
            monkeypatch, "## Confidence Score\n\n**0.92**\n\nStrong match."
        )
        with pytest.raises(ReasoningDegradedError):
            llm_capability_match(
                capability_name="python",
                capability_description="writes python services",
                requirement="build a python API",
                config=_config("anthropic"),
            )

    def test_openai_wire_payload_carries_the_schema(self, monkeypatch):
        from kaizen.llm.deployment import CompletionRequest
        from kaizen.llm.wire_protocols import openai_chat

        captured = _install_fake_transport(monkeypatch, _JUDGE_REPLY)
        llm_capability_match(
            capability_name="python",
            capability_description="writes python services",
            requirement="build a python API",
            config=_config("openai"),
        )
        rf = captured[0]["generation_config"]["response_format"]
        payload = openai_chat.build_request_payload(
            CompletionRequest(
                model="test-model",
                messages=[{"role": "user", "content": "x"}],
                response_format=rf,
            )
        )
        assert payload["response_format"]["type"] == "json_schema"
        assert (
            "match_score"
            in payload["response_format"]["json_schema"]["schema"]["properties"]
        )

    def test_ollama_wire_payload_maps_to_format(self, monkeypatch):
        from kaizen.llm.deployment import CompletionRequest
        from kaizen.llm.wire_protocols import ollama_native

        captured = _install_fake_transport(monkeypatch, _JUDGE_REPLY)
        llm_capability_match(
            capability_name="python",
            capability_description="writes python services",
            requirement="build a python API",
            config=_config("ollama"),
        )
        rf = captured[0]["generation_config"]["response_format"]
        payload = ollama_native.build_request_payload(
            CompletionRequest(
                model="test-model",
                messages=[{"role": "user", "content": "x"}],
                response_format=rf,
            )
        )
        assert payload.get(
            "format"
        ), "ollama's json mode was not requested; the model may answer in prose"

    def test_anthropic_has_no_wire_slot_so_the_prompt_must_carry_it(self, monkeypatch):
        # The provider WITHOUT structured output: the wire emits nothing, so
        # the JSON contract has to travel in the system prompt or the score is
        # lost exactly as #1981 describes.
        from kaizen.llm.deployment import CompletionRequest
        from kaizen.llm.wire_protocols import anthropic_messages

        captured = _install_fake_transport(monkeypatch, _JUDGE_REPLY)
        llm_capability_match(
            capability_name="python",
            capability_description="writes python services",
            requirement="build a python API",
            config=_config("anthropic"),
        )
        rf = captured[0]["generation_config"]["response_format"]
        payload = anthropic_messages.build_request_payload(
            CompletionRequest(
                model="test-model",
                messages=[{"role": "user", "content": "x"}],
                response_format=rf,
            )
        )
        assert "response_format" not in payload  # documents the wire's contract

        system = _system_message(captured[0])
        assert "JSON" in system.upper()
        assert "match_score" in system

    @pytest.mark.integration
    @pytest.mark.requires_real_llm
    @pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="live provider leg of the matrix requires ANTHROPIC_API_KEY",
    )
    def test_live_anthropic_high_confidence_match_is_non_zero(self):
        # Real provider, no fakes: the leg of the matrix that proves the
        # prompt-carried contract actually works against a model that has no
        # response_format parameter at all.
        from kaizen.config.providers import DEFAULT_ANTHROPIC_MODEL

        model = (
            os.environ.get("ANTHROPIC_PROD_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or os.environ.get("KAIZEN_ANTHROPIC_MODEL")
            or DEFAULT_ANTHROPIC_MODEL
        )
        score = llm_capability_match(
            capability_name="python_api_development",
            capability_description=(
                "Designs and implements production HTTP APIs in Python, "
                "including routing, validation and persistence."
            ),
            requirement="Build a REST API in Python with database persistence",
            config=_config("anthropic", model=model),
        )
        assert score > 0.5, (
            f"a textbook high-confidence match scored {score} against a live "
            "provider — the structured-output contract is not reaching it"
        )


# ---------------------------------------------------------------------------
# AC-4 — the A2A ranking signals degradation
# ---------------------------------------------------------------------------


class TestFindBestAgentsSignalsDegradation:
    """AC-4: no more arbitrary order behind an all-zero ranking."""

    @staticmethod
    def _coordinator():
        node = A2ACoordinatorNode()
        node.agent_cards = {
            "eng": _card("eng", primary_capabilities=[_cap("python")]),
            "des": _card("des", primary_capabilities=[_cap("design")]),
        }
        return node

    @staticmethod
    def _task():
        return A2ATask(name="api", requirements=["build a python API"])

    def test_every_judge_degraded_raises_instead_of_all_zero_ranking(self, monkeypatch):
        import kaizen.llm.reasoning as reasoning

        def _degraded(**kwargs):
            raise ReasoningDegradedError(
                "llm_capability_match",
                model="test-model",
                correlation_id="cid",
                error="JSON_PARSE_FAILED",
            )

        monkeypatch.setattr(reasoning, "llm_capability_match", _degraded)

        with pytest.raises(ReasoningDegradedError):
            self._coordinator()._find_best_agents_for_task(self._task())

    def test_partially_degraded_round_drops_the_unscored_card_and_warns(
        self, monkeypatch, caplog
    ):
        import kaizen.llm.reasoning as reasoning

        def _judge(*, capability_name, capability_description, requirement, **kw):
            if capability_name == "design":
                raise ReasoningDegradedError(
                    "llm_capability_match",
                    model="test-model",
                    correlation_id="cid",
                    error="JSON_PARSE_FAILED",
                )
            return 1.0

        monkeypatch.setattr(reasoning, "llm_capability_match", _judge)

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai.a2a"):
            matches = self._coordinator()._find_best_agents_for_task(self._task())

        assert [agent_id for agent_id, _ in matches] == ["eng"], (
            "the unscoreable card was ranked anyway — at 0.0 it is "
            "indistinguishable from a genuine no-match"
        )
        assert [
            r for r in caplog.records if "degraded" in r.getMessage()
        ], "a dropped candidate left no WARN trail"

    def test_healthy_ranking_is_unchanged(self, monkeypatch):
        import kaizen.llm.reasoning as reasoning

        def _judge(*, capability_name, capability_description, requirement, **kw):
            return 1.0 if capability_name in requirement else 0.0

        monkeypatch.setattr(reasoning, "llm_capability_match", _judge)

        matches = self._coordinator()._find_best_agents_for_task(self._task())
        assert [agent_id for agent_id, _ in matches] == ["eng", "des"]
        assert matches[0][1] > matches[1][1]
