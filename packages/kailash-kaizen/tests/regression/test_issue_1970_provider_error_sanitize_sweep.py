"""Regression tests — #1953-parity sanitize sweep across kaizen ``nodes/`` + ``providers/`` (#1970).

#1953 (kaizen 2.44.0) folded ``sanitize_provider_error`` into the
``IterativeLLMAgentNode`` surfaces. #1970 extends that to every OTHER site in
``kaizen/nodes/**`` and ``kaizen/providers/**`` where an exception that
plausibly originated from an LLM provider / external API / credentialed client
is formatted into a **user-visible dict field** or a **log record** without
sanitizing.

The issue text named ``MultiProviderNode`` in ``nodes/ai/ai_nodes.py`` — neither
exists. The real owner is ``KaizenAIModelNode`` in ``nodes/ai_nodes.py`` (class
declared at L1498); the line range (~L1540-1566) was correct.

These tests are organised by **leak SHAPE**, not per site — one test per distinct
surface through which a credential escapes:

  1. fallback dict fields + WARN log      -> ``KaizenAIModelNode.run``
  2. catch-all node-return dict           -> ``KaizenNode.execute``
  3. log-and-reraise ERROR record         -> ``KaizenTextGenerationNode.run``
  4. raised-exception message             -> ``OllamaModelManager.list_models``
  5. aggregated errors -> RuntimeError    -> ``ProviderManager.extract``
  6. bare-key residue past ``mask_error_text`` -> ``OllamaProvider.generate``
  7. RAG / security / auth node surfaces  -> representative sites

Every test injects a SYNTHETIC (fake) credential shaped to match the
``sanitize_provider_error`` regexes and asserts (a) the raw credential does NOT
appear on the surface and (b) the sanitizer's ``[REDACTED]`` marker DOES — so a
test cannot pass by the surface merely dropping the message.

Tier 1 unit tests: the provider/model seam is monkeypatched to raise, and the
REAL returned dict / REAL log record / REAL raised message is observed. No mock
stands in for the surface under test.
"""

import logging

import pytest

pytestmark = pytest.mark.regression


# Non-dispatching placeholder model identifier.
#
# ``rules/env-models.md`` governs which model PRODUCTION code talks to. It does
# not require a test that never reaches a provider to depend on a live model
# name — and reading ``DEFAULT_LLM_MODEL`` here made this whole file autouse-SKIP
# in CI, because ``.env`` is gitignored and CI has no model env var. All 14 tests
# reported green while verifying nothing: coverage-shaped with zero coverage,
# which is strictly worse than a placeholder literal. Every leak this sweep
# exists to catch went unverified on the only surface that gates merges.
#
# The literal is deliberately NOT a real model. It satisfies exactly the two
# things the constructors under test do with it:
#   1. ``kaizen.nodes._env_model.resolve_default_model`` returns it verbatim (it
#      performs no validation) instead of raising ``EnvModelMissing``;
#   2. ``kaizen.nodes._env_model.detect_provider`` substring-classifies it — the
#      ``gpt`` fragment routes it to the openai family rather than raising.
# Every provider seam below is monkeypatched to raise, so no request is ever
# constructed and this string never leaves the process. Same convention as
# tests/unit/conftest.py (``KAIZEN_DEFAULT_MODEL`` -> "gpt-4o-mini") and
# tests/unit/llm/test_governance_required_gate.py (``"gpt-test"``); the
# regression directory does not inherit tests/unit/conftest.py, which is why
# this module needs its own fixture.
_PLACEHOLDER_MODEL = "gpt-sanitize-sweep-placeholder"


@pytest.fixture(autouse=True)
def _kaizen_default_model(monkeypatch):
    """Give every node constructor a resolvable, non-dispatching model name.

    MUST NOT skip. This file tests SANITIZATION — a pure string transform with
    no provider dependency — so there is no environment in which skipping is the
    honest disposition.
    """
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", _PLACEHOLDER_MODEL)


# --------------------------------------------------------------------------
# Synthetic credentials. NOT real secrets. Each matches a distinct
# ``_CREDENTIAL_PATTERNS`` entry in ``kaizen.nodes.ai.error_sanitizer``.
# --------------------------------------------------------------------------
FAKE_OPENAI_KEY = "sk-proj-AAAABBBBCCCCDDDDEEEEFFFF1234"
FAKE_AWS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
FAKE_BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.fakepayload.fakesig"

RAW_PROVIDER_ERROR = (
    f"401 Unauthorized: incorrect api_key={FAKE_OPENAI_KEY} " f"(request id abc123)"
)
RAW_FALLBACK_ERROR = f"403 Forbidden: credentials {FAKE_AWS_KEY_ID} rejected"


def assert_scrubbed(surface: str, *, raw_secret: str, label: str) -> None:
    """The surface MUST NOT carry ``raw_secret`` and MUST carry ``[REDACTED]``.

    Asserting the positive marker as well as the negative is what stops a
    surface that simply swallowed the message from passing vacuously.
    """
    assert raw_secret not in surface, (
        f"{label}: raw credential leaked to a user-visible surface.\n"
        f"  surface: {surface!r}"
    )
    assert "[REDACTED]" in surface, (
        f"{label}: surface neither carries the credential nor the sanitizer's "
        f"[REDACTED] marker — the message was dropped rather than sanitized.\n"
        f"  surface: {surface!r}"
    )


# ==========================================================================
# SHAPE 1 — KaizenAIModelNode fallback: user-visible dict fields + WARN log
#           (the site named in the issue: ai_nodes.py ~L1540-1566)
# ==========================================================================


class TestShape1KaizenAIModelNodeFallback:
    """``KaizenAIModelNode.run`` stores raw provider exceptions in three dict
    fields (``primary_error``, two ``error`` variants) and one WARN log."""

    @staticmethod
    def _node():
        from kaizen.nodes.ai_nodes import KaizenAIModelNode

        return KaizenAIModelNode()

    def test_primary_error_field_is_sanitized_when_fallback_succeeds(self, monkeypatch):
        """Primary provider fails, fallback succeeds -> ``result["primary_error"]``."""
        node = self._node()
        calls = {"n": 0}

        def fake_execute(self, provider, inputs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(RAW_PROVIDER_ERROR)
            return {"response": "fallback ok"}

        monkeypatch.setattr(
            type(node), "_execute_with_provider", fake_execute, raising=True
        )

        result = node.run(prompt="hi", use_fallback=True)

        assert result["fallback_used"] is True
        assert_scrubbed(
            str(result["primary_error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenAIModelNode.run -> result['primary_error']",
        )

    def test_both_providers_failed_error_field_is_sanitized(self, monkeypatch):
        """Both providers fail -> the combined ``result["error"]``."""
        node = self._node()
        calls = {"n": 0}

        def fake_execute(self, provider, inputs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(RAW_PROVIDER_ERROR)
            raise RuntimeError(RAW_FALLBACK_ERROR)

        monkeypatch.setattr(
            type(node), "_execute_with_provider", fake_execute, raising=True
        )

        result = node.run(prompt="hi", use_fallback=True)

        surface = str(result["error"])
        # BOTH exceptions are interpolated into this one field — both must scrub.
        assert_scrubbed(
            surface,
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenAIModelNode.run -> result['error'] (primary half)",
        )
        assert FAKE_AWS_KEY_ID not in surface, (
            "KaizenAIModelNode.run -> result['error'] (fallback half): raw "
            f"credential leaked.\n  surface: {surface!r}"
        )

    def test_no_fallback_error_field_is_sanitized(self, monkeypatch):
        """``use_fallback=False`` -> the single-provider ``result["error"]``."""
        node = self._node()

        def fake_execute(self, provider, inputs):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(
            type(node), "_execute_with_provider", fake_execute, raising=True
        )

        result = node.run(prompt="hi", use_fallback=False)

        assert_scrubbed(
            str(result["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenAIModelNode.run -> result['error'] (no fallback)",
        )

    def test_primary_failure_warn_log_is_sanitized(self, monkeypatch, caplog):
        """The WARN log emitted before the fallback attempt."""
        node = self._node()
        calls = {"n": 0}

        def fake_execute(self, provider, inputs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(RAW_PROVIDER_ERROR)
            return {"response": "fallback ok"}

        monkeypatch.setattr(
            type(node), "_execute_with_provider", fake_execute, raising=True
        )

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai_nodes"):
            node.run(prompt="hi", use_fallback=True)

        records = "\n".join(r.getMessage() for r in caplog.records)
        assert_scrubbed(
            records,
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenAIModelNode.run -> WARN log record",
        )


# ==========================================================================
# SHAPE 2 — KaizenNode.execute() catch-all dict (base.py L254-255).
#           This is the convergence point for EVERY KaizenNode subclass:
#           any node whose run() re-raises a provider exception lands here.
# ==========================================================================


class TestShape2KaizenNodeExecuteCatchAll:
    def test_execute_error_dict_is_sanitized(self, monkeypatch):
        from kaizen.nodes.base import KaizenNode

        node = KaizenNode()

        def boom(self, **kwargs):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(KaizenNode, "run", boom, raising=True)

        result = node.execute(prompt="hi")

        assert result["status"] == "failed"
        assert_scrubbed(
            str(result["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenNode.execute -> result['error']",
        )

    def test_execute_error_log_is_sanitized(self, monkeypatch, caplog):
        from kaizen.nodes.base import KaizenNode

        node = KaizenNode()

        def boom(self, **kwargs):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(KaizenNode, "run", boom, raising=True)

        with caplog.at_level(logging.ERROR):
            node.execute(prompt="hi")

        records = "\n".join(r.getMessage() for r in caplog.records)
        assert_scrubbed(
            records,
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenNode.execute -> ERROR log record",
        )


# ==========================================================================
# SHAPE 3 — log-and-reraise: the ERROR log is the only surface, the exception
#           itself propagates unchanged to the caller.
# ==========================================================================


class TestShape3LogAndReraise:
    def test_text_generation_node_error_log_is_sanitized(self, monkeypatch, caplog):
        from kaizen.nodes.ai_nodes import KaizenTextGenerationNode

        node = KaizenTextGenerationNode()

        def boom(self, **kwargs):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(
            type(node).__mro__[1], "_execute_ai_model", boom, raising=True
        )

        with caplog.at_level(logging.ERROR, logger="kaizen.nodes.ai_nodes"):
            with pytest.raises(RuntimeError):
                node.run(prompt="hi")

        records = "\n".join(r.getMessage() for r in caplog.records)
        assert_scrubbed(
            records,
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenTextGenerationNode.run -> ERROR log record",
        )

    def test_base_kaizen_node_run_error_log_is_sanitized(self, monkeypatch, caplog):
        from kaizen.nodes.base import KaizenNode

        node = KaizenNode()

        def boom(self, **kwargs):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(KaizenNode, "_execute_ai_model", boom, raising=True)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError):
                node.run(prompt="hi")

        records = "\n".join(r.getMessage() for r in caplog.records)
        assert_scrubbed(
            records,
            raw_secret=FAKE_OPENAI_KEY,
            label="KaizenNode.run -> ERROR log record",
        )


# ==========================================================================
# SHAPE 4 — raised-exception message: a provider client error re-raised as a
#           RuntimeError whose message interpolates the original.
# ==========================================================================


class TestShape4RaisedExceptionMessage:
    def test_ollama_model_manager_list_models_message_is_sanitized(self, monkeypatch):
        import sys
        import types

        from kaizen.providers.ollama_model_manager import OllamaModelManager

        fake_ollama = types.ModuleType("ollama")

        def boom(*a, **k):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        fake_ollama.list = boom
        monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

        with pytest.raises(RuntimeError) as excinfo:
            OllamaModelManager().list_models()

        assert_scrubbed(
            str(excinfo.value),
            raw_secret=FAKE_OPENAI_KEY,
            label="OllamaModelManager.list_models -> RuntimeError message",
        )


# ==========================================================================
# SHAPE 5 — aggregated errors joined into a terminal RuntimeError.
# ==========================================================================


class TestShape5AggregatedErrors:
    @pytest.mark.asyncio
    async def test_provider_manager_extract_aggregated_errors_are_sanitized(
        self, monkeypatch
    ):
        from kaizen.providers.document.provider_manager import ProviderManager

        manager = ProviderManager()

        async def boom(self, provider_name, file_path, file_type=None, **options):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(
            ProviderManager, "_extract_with_provider", boom, raising=True
        )

        with pytest.raises(RuntimeError) as excinfo:
            await manager.extract("report.pdf")

        assert_scrubbed(
            str(excinfo.value),
            raw_secret=FAKE_OPENAI_KEY,
            label="ProviderManager.extract -> aggregated RuntimeError message",
        )


# ==========================================================================
# SHAPE 6 — residue past ``mask_error_text``.
#
# ``kailash.utils.url_credentials.mask_error_text`` masks ONLY URL userinfo
# (``scheme://user:pass@``) and sensitive query params. A BARE api key or
# ``Bearer <token>`` in an Ollama-proxy 401 body survives it untouched. These
# sites need ``sanitize_provider_error`` composed over the mask, not instead of
# it (the mask still covers non-http schemes + ``?token=`` which the sanitizer
# does not).
# ==========================================================================


class TestShape6BareKeyResiduePastMaskErrorText:
    @staticmethod
    def _provider_whose_chat_raises(monkeypatch, raw_message):
        """Construct a real ``OllamaProvider`` whose ``ollama.chat`` raises.

        ``__init__`` calls ``ollama.list()`` through ``_check_ollama_available``,
        so ``list`` must SUCCEED for construction to reach ``generate``. Only
        ``chat`` raises — that is the L114 site under test.
        """
        import sys
        import types

        from kaizen.providers.ollama_provider import OllamaConfig, OllamaProvider

        fake = types.ModuleType("ollama")
        fake.list = lambda *a, **k: types.SimpleNamespace(models=[])

        def boom(*a, **k):
            raise RuntimeError(raw_message)

        fake.chat = boom
        fake.embeddings = boom
        monkeypatch.setitem(sys.modules, "ollama", fake)

        # ungoverned=True: this is a unit test with no real egress (the ollama
        # module is a stub); the #1803 construction-time governance gate is not
        # what is under test here.
        return OllamaProvider(config=OllamaConfig(ungoverned=True))

    def test_ollama_provider_generate_scrubs_bare_bearer_token(self, monkeypatch):
        raw = f"401 from auth proxy: {FAKE_BEARER}"
        provider = self._provider_whose_chat_raises(monkeypatch, raw)

        with pytest.raises(RuntimeError) as excinfo:
            provider.generate("hello")

        surface = str(excinfo.value)
        assert FAKE_BEARER not in surface, (
            "OllamaProvider.generate -> RuntimeError message: bare Bearer token "
            f"survived mask_error_text.\n  surface: {surface!r}"
        )
        assert "[REDACTED]" in surface, (
            "OllamaProvider.generate -> RuntimeError message: no [REDACTED] "
            f"marker.\n  surface: {surface!r}"
        )

    def test_ollama_provider_still_masks_url_userinfo(self, monkeypatch):
        """The mask_error_text half MUST survive the upgrade (no regression)."""
        raw = "connect failed: http://admin:hunter2@ollama.internal:11434/api"
        provider = self._provider_whose_chat_raises(monkeypatch, raw)

        with pytest.raises(RuntimeError) as excinfo:
            provider.generate("hello")

        surface = str(excinfo.value)
        assert "hunter2" not in surface, (
            "OllamaProvider.generate: URL-embedded password leaked — the "
            f"mask_error_text half regressed.\n  surface: {surface!r}"
        )


# ==========================================================================
# SHAPE 7 — representative node-return dicts across the remaining IN-SCOPE
#           families: RAG, security, auth.
# ==========================================================================


class TestShape7NodeReturnDicts:
    def test_rag_advanced_execution_error_dict_is_sanitized(self, monkeypatch):
        """``SelfCorrectingRAGNode._perform_rag`` -> ``error`` + ``generated_response``."""
        from kaizen.nodes.rag.advanced import SelfCorrectingRAGNode

        node = SelfCorrectingRAGNode()

        class BoomWorkflow:
            def run(self, **kwargs):
                raise RuntimeError(RAW_PROVIDER_ERROR)

        node.base_rag_workflow = BoomWorkflow()

        result = node._perform_rag([{"content": "doc"}], "q", 0)

        assert_scrubbed(
            str(result["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="SelfCorrectingRAGNode._perform_rag -> result['error']",
        )
        assert_scrubbed(
            str(result["generated_response"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="SelfCorrectingRAGNode._perform_rag -> result['generated_response']",
        )

    def test_security_behavior_analysis_error_dict_is_sanitized(self, monkeypatch):
        from kaizen.nodes.security.ai_behavior_analysis import AIBehaviorAnalysisNode

        node = AIBehaviorAnalysisNode()

        def boom(self, *a, **k):
            raise RuntimeError(RAW_PROVIDER_ERROR)

        monkeypatch.setattr(
            AIBehaviorAnalysisNode, "_get_core_behavior_node", boom, raising=True
        )

        result = node.run(user_id="u1", activity_data=[{"action": "login"}])

        assert_scrubbed(
            str(result["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="AIBehaviorAnalysisNode.run -> result['error']",
        )
        assert_scrubbed(
            str(result["analysis_metadata"]["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="AIBehaviorAnalysisNode.run -> analysis_metadata['error']",
        )


# ==========================================================================
# SHAPE 8 — FallbackResult.to_dict()["error"]: the RAW provider exception on
#           the caller's serialization surface.
#
#           This shape is the reason a per-SHAPE sweep beats a per-SITE one.
#           ``FallbackRouter`` already sanitized the SAME exception into
#           ``FallbackEvent.error_message`` at both construction sites, so a
#           reviewer reading the file saw sanitization and moved on — while
#           ``to_dict`` two lines below serialized ``str(self.error)`` raw.
#           One dict emitted one provider exception twice: scrubbed under
#           ``fallback_events[*]``, raw under ``error``.
# ==========================================================================


class TestShape8FallbackResultSerialization:
    """``FallbackResult.error`` holds the raw ``Exception`` object; every
    ``FallbackResult(error=...)`` site in ``FallbackRouter`` assigns the caught
    provider exception directly, and ``execute_fn`` dispatches to an LLM
    provider whose exception can embed the API key."""

    def test_to_dict_error_field_is_sanitized(self):
        from kaizen.llm.routing.fallback import FallbackEvent, FallbackResult

        result = FallbackResult(
            success=False,
            model_used="primary-model",
            attempts=3,
            fallback_events=[
                FallbackEvent(
                    original_model="primary-model",
                    fallback_model="none",
                    error_type="AuthenticationError",
                    error_message="primary-model error: 401 [REDACTED]",
                )
            ],
            error=RuntimeError(RAW_PROVIDER_ERROR),
        )

        payload = result.to_dict()

        assert_scrubbed(
            str(payload["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="FallbackResult.to_dict() -> ['error']",
        )
        # The whole serialized payload, not just the field we patched — a future
        # field that re-introduces the raw exception fails here too.
        assert FAKE_OPENAI_KEY not in str(payload), (
            "the credential survived elsewhere in the serialized FallbackResult: "
            f"{payload!r}"
        )

    def test_to_dict_error_is_none_when_no_error(self):
        """The sanitizer must not fabricate a message on the success path."""
        from kaizen.llm.routing.fallback import FallbackResult

        assert FallbackResult(success=True, model_used="m").to_dict()["error"] is None

    def test_to_dict_survives_empty_model_used(self):
        """``model_used`` is ``""`` on the capability-filter-failure and
        empty-``execution_order`` paths; the provider label must still resolve
        rather than passing an empty string to the sanitizer."""
        from kaizen.llm.routing.fallback import FallbackResult

        payload = FallbackResult(
            success=False, model_used="", error=RuntimeError(RAW_PROVIDER_ERROR)
        ).to_dict()

        assert_scrubbed(
            str(payload["error"]),
            raw_secret=FAKE_OPENAI_KEY,
            label="FallbackResult.to_dict() with empty model_used",
        )
