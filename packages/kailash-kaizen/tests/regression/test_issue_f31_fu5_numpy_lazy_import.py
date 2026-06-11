"""Regression: F31-FU5 — numpy is a [rag]-extra dependency; the base import
surface must not require it.

Pre-fix failure chain: ``kaizen/__init__.py`` -> ``kaizen_agents`` ->
``patterns/runtime.py`` -> ``from kaizen.nodes.ai.a2a import A2AAgentCard``
-> ``kaizen/nodes/ai/__init__.py`` eagerly imports ``hybrid_search`` /
``semantic_memory`` (module-scope ``import numpy``) -> ImportError ->
runtime.py fallback sets ``A2AAgentCard = None`` -> the eagerly-evaluated
PEP-604 annotation ``A2AAgentCard | None`` raises
``TypeError: unsupported operand type(s) for |: 'NoneType' and 'NoneType'``
at class-creation time, so even bare ``import kaizen`` hard-crashed on any
install without the [rag] extra.

Fix: lazy numpy in nodes/ai (TYPE_CHECKING + ``require_numpy()`` with [rag]
install guidance) + ``from __future__ import annotations`` in
kaizen_agents/patterns/runtime.py.

``import kaizen.nodes.rag`` still requires the [rag] extra BY DESIGN (the
pyproject [rag] extra is documented as "the complete `import kaizen.nodes.rag`
dependency set") — the test asserts that failure stays a clean
ModuleNotFoundError, never a TypeError.

Subprocess-based: sys.modules isolation is impossible in-process once numpy
has been imported by a sibling test.
"""

import subprocess
import sys
import textwrap

import pytest

# Meta-path blocker that simulates the [rag] extra being absent.
BLOCKER_PRELUDE = textwrap.dedent(
    """
    import sys
    from importlib.abc import MetaPathFinder

    BLOCKED = {"numpy", "PIL", "networkx"}

    class _AbsentExtras(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in BLOCKED:
                raise ModuleNotFoundError(
                    f"No module named '{fullname}' (simulated absent)",
                    name=fullname,
                )
            return None

    for _m in list(sys.modules):
        if _m.split(".")[0] in BLOCKED:
            del sys.modules[_m]
    sys.meta_path.insert(0, _AbsentExtras())
    """
)


def _run_without_rag_extras(body: str) -> subprocess.CompletedProcess:
    """Run python code in a subprocess with numpy/PIL/networkx blocked."""
    return subprocess.run(
        [sys.executable, "-c", BLOCKER_PRELUDE + textwrap.dedent(body)],
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.regression
@pytest.mark.parametrize(
    "target",
    [
        "kaizen",
        "kaizen.nodes",
        "kaizen.nodes.ai",
        "kaizen_agents.patterns.runtime",
    ],
)
def test_base_import_succeeds_without_numpy(target):
    """Base import surface MUST NOT require the [rag] extra."""
    result = _run_without_rag_extras(f"import {target}")
    assert result.returncode == 0, (
        f"`import {target}` failed without numpy (the [rag] extra must not be "
        f"required on the base import surface):\n{result.stderr}"
    )


@pytest.mark.regression
def test_runtime_degrades_gracefully_when_a2a_unavailable():
    """runtime.py must import + AgentMetadata must be constructible when the
    a2a import chain is unavailable (the pre-fix TypeError fired at
    class-creation time, so module import itself crashed)."""
    result = _run_without_rag_extras(
        """
        # Block the a2a module itself to force the fallback branch
        import sys
        from importlib.abc import MetaPathFinder

        class _BlockA2A(MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "kaizen.nodes.ai.a2a":
                    raise ModuleNotFoundError(
                        "No module named 'kaizen.nodes.ai.a2a' (simulated)",
                        name=fullname,
                    )
                return None

        sys.meta_path.insert(0, _BlockA2A())

        import kaizen_agents.patterns.runtime as rt

        assert rt.A2A_AVAILABLE is False, "A2A_AVAILABLE must be False"
        assert rt.A2AAgentCard is None, "A2AAgentCard fallback must be None"

        # The crash site: AgentMetadata class creation + instantiation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(rt.AgentMetadata)}
        assert "a2a_card" in fields, "a2a_card field must survive the fallback"
        print("graceful-degrade OK")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "graceful-degrade OK" in result.stdout


@pytest.mark.regression
def test_rag_import_without_extra_raises_clean_modulenotfound():
    """`import kaizen.nodes.rag` without [rag] requires the extra BY DESIGN —
    but the failure MUST be a clean ModuleNotFoundError, never the TypeError
    crash class this regression pins."""
    result = _run_without_rag_extras(
        """
        try:
            import kaizen.nodes.rag
        except ModuleNotFoundError:
            print("clean-mnfe")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "clean-mnfe" in result.stdout


@pytest.mark.regression
def test_require_numpy_raises_with_rag_install_guidance():
    """The lazy-import helper must raise a typed error naming the [rag] extra."""
    result = _run_without_rag_extras(
        """
        from kaizen.nodes._optional import require_numpy
        try:
            require_numpy("regression probe")
        except ImportError as exc:
            assert "kailash-kaizen[rag]" in str(exc), str(exc)
            assert "regression probe" in str(exc), str(exc)
            print("guidance OK")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "guidance OK" in result.stdout


@pytest.mark.regression
def test_require_numpy_returns_module_when_present():
    """With numpy installed, the helper returns the real module (in-process)."""
    from kaizen.nodes._optional import require_numpy

    np = require_numpy("regression probe")
    assert np.__name__ == "numpy"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_hash_embedding_and_search_still_work_with_numpy_present():
    """Behavioral: the lazy-import refactor must not change numeric behavior."""
    from datetime import UTC, datetime

    from kaizen.nodes.ai.semantic_memory import (
        InMemoryVectorStore,
        SemanticMemoryItem,
        SimpleEmbeddingProvider,
    )

    provider = SimpleEmbeddingProvider()
    emb = provider._hash_embedding("hello world")
    assert emb.shape == (384,)

    store = InMemoryVectorStore()
    await store.add(
        SemanticMemoryItem(
            id="i1",
            content="hello world",
            embedding=emb,
            metadata={},
            created_at=datetime.now(UTC),
        )
    )
    results = await store.search_similar(emb, threshold=0.9)
    assert len(results) == 1
    assert results[0][0].id == "i1"
    assert results[0][1] == pytest.approx(1.0)


@pytest.mark.regression
def test_tfidf_transform_and_cosine_still_work_with_numpy_present():
    """Behavioral: hybrid_search TF-IDF path unchanged with numpy installed."""
    from kaizen.nodes.ai.hybrid_search import TFIDFVectorizer

    v = TFIDFVectorizer()
    docs = ["the quick brown fox", "the lazy dog", "quick quick fox"]
    v.fit(docs)
    vectors = v.transform(docs)
    assert vectors.shape[0] == 3
    sim_self = v.cosine_similarity(vectors[0], vectors[0])
    assert sim_self == pytest.approx(1.0)
    assert v.cosine_similarity(vectors[0], vectors[1]) < sim_self
