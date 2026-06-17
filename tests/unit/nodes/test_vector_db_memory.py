"""Behavioral regression tests for VectorDatabaseNode's in-memory backend.

These tests CALL the node and assert REAL computed results — proving the
similarity search, metadata round-trip, filtering, fetch, and delete operations
are backed by an actual in-memory store rather than the previously-shipped
fabricated ``doc_0..doc_4`` / ``score = 0.95 - i*0.05`` / ``[0.1]*dimension``
placeholders.

Guards:
- Upsert 3+ known vectors and assert the vector closest to a SPECIFIC id ranks
  first (real similarity, not a fixed ``doc_0`` list).
- Metadata round-trips through upsert -> query / fetch.
- A metadata filter narrows query results.
- Fetch returns the real stored vector; missing ids are omitted honestly.
- Delete removes a vector for real (count + subsequent fetch/query reflect it).
- External providers raise the honest typed ``NodeConfigurationError``.
- No query result ever carries the old fabricated ``doc_N`` / ``Document N``.
"""

import pytest

from kailash.nodes.data.vector_db import VectorDatabaseNode
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


def _memory_node(dimension: int, metric: str = "cosine") -> VectorDatabaseNode:
    """Build a configured in-memory VectorDatabaseNode."""
    node = VectorDatabaseNode()
    node.configure(
        {
            "provider": "memory",
            "index_name": "test-index",
            "dimension": dimension,
            "metric": metric,
        }
    )
    return node


@pytest.mark.regression
def test_query_ranks_nearest_specific_id_first_cosine():
    """The vector closest to the query must rank first — real similarity."""
    node = _memory_node(dimension=3, metric="cosine")

    # Three well-separated directions in 3-space.
    node.execute(
        {
            "operation": "upsert",
            "ids": ["x_axis", "y_axis", "z_axis"],
            "vectors": [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            "metadata": [
                {"axis": "x"},
                {"axis": "y"},
                {"axis": "z"},
            ],
        }
    )

    # A query pointing mostly along +y must rank "y_axis" first.
    result = node.execute(
        {
            "operation": "query",
            "query_vector": [0.1, 0.9, 0.05],
            "k": 3,
        }
    )

    assert result["status"] == "success"
    assert result["count"] == 3
    top = result["results"][0]
    assert top["id"] == "y_axis", f"expected y_axis nearest, got {top['id']}"
    # Metadata round-trips through the query result.
    assert top["metadata"] == {"axis": "y"}
    # Scores are strictly descending (real ranking, not a fixed list).
    scores = [r["score"] for r in result["results"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[1] > scores[2]


@pytest.mark.regression
def test_query_ranks_nearest_specific_id_first_dot():
    """Dot-product metric ranks the highest dot first."""
    node = _memory_node(dimension=2, metric="dot")
    node.execute(
        {
            "operation": "upsert",
            "ids": ["small", "large"],
            "vectors": [[1.0, 1.0], [10.0, 10.0]],
        }
    )
    result = node.execute({"operation": "query", "query_vector": [1.0, 1.0], "k": 2})
    # Dot product with [10,10] (=20) beats [1,1] (=2).
    assert result["results"][0]["id"] == "large"
    assert result["results"][0]["score"] == pytest.approx(20.0)


@pytest.mark.regression
def test_query_ranks_nearest_specific_id_first_euclidean():
    """Euclidean metric ranks the smallest distance (closest vector) first."""
    node = _memory_node(dimension=2, metric="euclidean")
    node.execute(
        {
            "operation": "upsert",
            "ids": ["near", "far"],
            "vectors": [[1.0, 1.0], [9.0, 9.0]],
        }
    )
    result = node.execute({"operation": "query", "query_vector": [1.1, 1.1], "k": 2})
    assert result["results"][0]["id"] == "near"
    # Similarity = 1/(1+distance); the nearer vector has the larger score.
    assert result["results"][0]["score"] > result["results"][1]["score"]


@pytest.mark.regression
def test_metadata_filter_narrows_results():
    """A metadata filter restricts the candidate set to matching vectors."""
    node = _memory_node(dimension=2, metric="cosine")
    node.execute(
        {
            "operation": "upsert",
            "ids": ["a", "b", "c"],
            "vectors": [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]],
            "metadata": [
                {"category": "technical"},
                {"category": "marketing"},
                {"category": "technical"},
            ],
        }
    )

    result = node.execute(
        {
            "operation": "query",
            "query_vector": [1.0, 0.0],
            "k": 10,
            "filter": {"category": "technical"},
        }
    )

    returned_ids = {r["id"] for r in result["results"]}
    assert returned_ids == {"a", "c"}, returned_ids
    assert result["count"] == 2
    # The marketing-only vector "b" is excluded by the filter.
    assert "b" not in returned_ids


@pytest.mark.regression
def test_fetch_returns_real_stored_vector_and_omits_missing():
    """Fetch returns the actual stored values; missing ids are omitted."""
    node = _memory_node(dimension=3)
    stored_vector = [0.2, 0.4, 0.6]
    node.execute(
        {
            "operation": "upsert",
            "ids": ["real"],
            "vectors": [stored_vector],
            "metadata": [{"title": "Real Doc"}],
        }
    )

    result = node.execute({"operation": "fetch", "ids": ["real", "ghost"]})

    assert "real" in result["vectors"]
    # The REAL stored vector is returned — NOT a fabricated [0.1]*dimension.
    assert result["vectors"]["real"]["values"] == stored_vector
    assert result["vectors"]["real"]["metadata"] == {"title": "Real Doc"}
    # Missing id is honestly omitted, not fabricated.
    assert "ghost" not in result["vectors"]


@pytest.mark.regression
def test_delete_removes_vector_for_real():
    """Delete reports the real removed count and the vector is gone afterwards."""
    node = _memory_node(dimension=2)
    node.execute(
        {
            "operation": "upsert",
            "ids": ["keep", "drop"],
            "vectors": [[1.0, 0.0], [0.0, 1.0]],
        }
    )

    delete_result = node.execute(
        {"operation": "delete", "ids": ["drop", "never_existed"]}
    )
    # Only one of the two ids actually existed.
    assert delete_result["count"] == 1

    # The deleted vector no longer appears in fetch or query.
    fetched = node.execute({"operation": "fetch", "ids": ["drop"]})
    assert fetched["vectors"] == {}

    queried = node.execute({"operation": "query", "query_vector": [0.0, 1.0], "k": 10})
    remaining_ids = {r["id"] for r in queried["results"]}
    assert remaining_ids == {"keep"}


@pytest.mark.regression
def test_empty_store_query_returns_empty_results():
    """Querying an empty store returns zero real results, never fabricated docs."""
    node = _memory_node(dimension=4)
    result = node.execute(
        {"operation": "query", "query_vector": [0.1, 0.2, 0.3, 0.4], "k": 5}
    )
    assert result["results"] == []
    assert result["count"] == 0


@pytest.mark.regression
def test_metadata_round_trips_with_default_empty():
    """Vectors upserted without metadata default to {} and round-trip."""
    node = _memory_node(dimension=2)
    node.execute(
        {
            "operation": "upsert",
            "ids": ["no_meta"],
            "vectors": [[0.5, 0.5]],
        }
    )
    fetched = node.execute({"operation": "fetch", "ids": ["no_meta"]})
    assert fetched["vectors"]["no_meta"]["metadata"] == {}


@pytest.mark.regression
def test_upsert_dimension_mismatch_raises():
    """A vector whose length != configured dimension is rejected, not stored."""
    node = _memory_node(dimension=3)
    with pytest.raises(NodeExecutionError):
        node.execute(
            {
                "operation": "upsert",
                "ids": ["bad"],
                "vectors": [[1.0, 2.0]],  # length 2, configured dimension 3
            }
        )
    # Nothing was stored — store is still empty.
    fetched = node.execute({"operation": "fetch", "ids": ["bad"]})
    assert fetched["vectors"] == {}


@pytest.mark.regression
def test_query_dimension_mismatch_raises():
    """A query vector whose length != configured dimension is rejected."""
    node = _memory_node(dimension=3)
    node.execute({"operation": "upsert", "ids": ["a"], "vectors": [[1.0, 2.0, 3.0]]})
    with pytest.raises(NodeExecutionError):
        node.execute({"operation": "query", "query_vector": [1.0, 2.0], "k": 1})


@pytest.mark.regression
@pytest.mark.parametrize(
    "provider", ["pinecone", "weaviate", "milvus", "qdrant", "chroma"]
)
def test_external_provider_raises_honest_typed_error(provider):
    """External providers fail loud with a clear typed error — never faked."""
    node = VectorDatabaseNode()
    with pytest.raises(NodeConfigurationError) as exc_info:
        node.configure(
            {
                "provider": provider,
                "index_name": "test-index",
                "dimension": 8,
            }
        )
    message = str(exc_info.value)
    assert provider in message
    assert "not bundled with kailash" in message
    assert "provider='memory'" in message


@pytest.mark.regression
def test_query_results_never_contain_old_fabricated_pattern():
    """Guard: query output must never carry the old fabricated doc_N / Document N."""
    node = _memory_node(dimension=2)
    node.execute(
        {
            "operation": "upsert",
            "ids": ["alpha", "beta"],
            "vectors": [[1.0, 0.0], [0.0, 1.0]],
            "metadata": [{"title": "Alpha"}, {"title": "Beta"}],
        }
    )
    result = node.execute({"operation": "query", "query_vector": [1.0, 0.0], "k": 5})

    returned_ids = {r["id"] for r in result["results"]}
    # Real stored ids only — none of the fabricated doc_0..doc_4 placeholders.
    assert returned_ids == {"alpha", "beta"}
    for r in result["results"]:
        assert not r["id"].startswith("doc_"), f"fabricated id leaked: {r['id']}"
        title = r["metadata"].get("title", "")
        assert not title.startswith("Document "), f"fabricated title leaked: {title}"
        # No fabricated 0.95 - i*0.05 scores: scores derive from real vectors.
        assert r["metadata"] in ({"title": "Alpha"}, {"title": "Beta"})


@pytest.mark.regression
def test_max_vectors_cap_rejects_overflow_atomically():
    """An upsert exceeding ``max_vectors`` fails loud and stores nothing extra."""
    node = VectorDatabaseNode()
    node.configure(
        {
            "provider": "memory",
            "index_name": "capped",
            "dimension": 2,
            "max_vectors": 2,
        }
    )
    # Fill the store to the cap.
    node.execute(
        {"operation": "upsert", "ids": ["a", "b"], "vectors": [[1.0, 0.0], [0.0, 1.0]]}
    )
    # A third NEW id would exceed the cap -> typed error; nothing is stored.
    with pytest.raises(NodeExecutionError) as exc:
        node.execute({"operation": "upsert", "ids": ["c"], "vectors": [[1.0, 1.0]]})
    assert "capacity exceeded" in str(exc.value)
    fetched = node.execute({"operation": "fetch", "ids": ["c"]})
    assert fetched["vectors"] == {}
    # Updating an EXISTING id adds no new id, so it stays within the cap.
    ok = node.execute({"operation": "upsert", "ids": ["a"], "vectors": [[0.5, 0.5]]})
    assert ok["status"] == "success"


@pytest.mark.regression
def test_filter_must_be_a_dict():
    """A non-dict metadata filter raises a clear typed error, not an opaque one."""
    node = _memory_node(dimension=2)
    node.execute({"operation": "upsert", "ids": ["a"], "vectors": [[1.0, 0.0]]})
    with pytest.raises(NodeExecutionError) as exc:
        node.execute(
            {
                "operation": "query",
                "query_vector": [1.0, 0.0],
                "k": 5,
                "filter": ["not", "a", "dict"],
            }
        )
    assert "filter must be a dict" in str(exc.value)


@pytest.mark.regression
def test_multi_vector_upsert_is_atomic_on_dimension_mismatch():
    """A dimension mismatch mid-batch stores NONE of the batch (atomic upsert)."""
    node = _memory_node(dimension=3)
    with pytest.raises(NodeExecutionError):
        node.execute(
            {
                "operation": "upsert",
                "ids": ["good", "bad"],
                "vectors": [[1.0, 2.0, 3.0], [1.0, 2.0]],  # second is wrong dim
            }
        )
    # The valid first vector must NOT have leaked into the store.
    fetched = node.execute({"operation": "fetch", "ids": ["good", "bad"]})
    assert fetched["vectors"] == {}
