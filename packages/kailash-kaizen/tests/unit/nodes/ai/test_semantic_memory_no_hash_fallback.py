"""#2174 sibling: SimpleEmbeddingProvider must not fabricate hash embeddings.

Both arms of the embedding request used to fall back to an MD5-derived vector
when the embedding service returned non-200 or raised — with no log line and
no raise. The resulting ``EmbeddingResult`` even carried ``model=<the real
model name>``, so the fabricated vectors were labelled with the real model's
provenance and were indistinguishable downstream.

`hybrid_search.py` constructs this provider, so the degraded path was live in
production, not just reachable in theory.
"""

import pytest

from kaizen.nodes.ai.semantic_memory import (
    EmbeddingUnavailable,
    SimpleEmbeddingProvider,
)

# A non-loopback host, so the unit tier's egress block refuses the connect
# deterministically. The provider's DEFAULT host is http://localhost:11434,
# which the block deliberately permits — on a developer machine with ollama
# running, the request SUCCEEDS and a test written against the default would
# pass for the wrong reason, then fail in CI. That is the same ambient-state
# dependency #2169 removed from this tier, so it is not reintroduced here.
_UNREACHABLE_HOST = "http://embedding-service.invalid:11434"


class TestNoHashFallback:
    def test_hash_embedding_helper_is_gone(self):
        """The fabricating helper must not survive on the class.

        If it comes back, the fallback can be silently re-wired.
        """
        assert not hasattr(SimpleEmbeddingProvider, "_hash_embedding")

    @pytest.mark.asyncio
    async def test_unreachable_service_raises_instead_of_fabricating(self):
        """A failed embedding request raises rather than returning hash noise.

        The unit tier refuses non-loopback egress (see tests/unit/conftest.py),
        so the request genuinely fails here — which is exactly the condition
        that used to yield fabricated vectors.
        """
        provider = SimpleEmbeddingProvider(host=_UNREACHABLE_HOST, ungoverned=True)

        with pytest.raises(EmbeddingUnavailable) as exc:
            await provider.embed_text("hello world")

        msg = str(exc.value)
        # The error must say what failed and refuse explicitly, so the next
        # reader does not reintroduce the fallback as a "fix".
        assert "SimpleEmbeddingProvider" in msg
        assert "hash-derived" in msg

    @pytest.mark.asyncio
    async def test_failure_is_not_reported_as_a_successful_embedding(self):
        """No EmbeddingResult may be returned for a failed request.

        The regression this guards is the original defect's shape: a control
        that reports success without doing its job.
        """
        provider = SimpleEmbeddingProvider(host=_UNREACHABLE_HOST, ungoverned=True)

        result = None
        with pytest.raises(EmbeddingUnavailable):
            result = await provider.embed_text("hello world")

        assert result is None
