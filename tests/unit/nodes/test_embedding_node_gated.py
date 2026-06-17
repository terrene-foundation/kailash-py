"""Regression: EmbeddingNode no longer fabricates random embeddings.

EmbeddingNode previously returned ``np.random.randn`` vectors presented as real
embeddings (meaningless for similarity search). It now fails loudly with a clear
typed error directing users to a real embedding provider or the embedding-free
``bm25``/``tfidf`` retrieval path.
"""

import pytest

from kailash.nodes.data.vector_db import EmbeddingNode
from kailash.sdk_exceptions import NodeExecutionError


@pytest.mark.regression
def test_embedding_node_fails_loud_not_fake_random():
    """execute() raises a clear error instead of returning random vectors."""
    node = EmbeddingNode()
    with pytest.raises(NodeExecutionError) as exc:
        node.execute({"texts": ["hello world", "second text"]})
    msg = str(exc.value)
    assert "real embedding model" in msg
    # Points users at the embedding-free retrieval path.
    assert "bm25" in msg or "tfidf" in msg


@pytest.mark.regression
def test_embedding_node_generate_helper_raises():
    """The fabrication site itself raises (guards against re-introduction)."""
    node = EmbeddingNode()
    with pytest.raises(NodeExecutionError):
        node._generate_embeddings(["x"])
