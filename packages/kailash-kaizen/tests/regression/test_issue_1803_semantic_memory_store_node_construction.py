# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: SemanticMemoryStoreNode was unconstructible (#1803 discovery).

Surfaced while adding the #1803 governance-gate test for this node's
``ungoverned`` threading: ``SemanticMemoryStoreNode.__init__`` assigned
``self.metadata = None`` BEFORE calling ``super().__init__()``. ``Node.metadata``
is a property whose setter (for a dict/None value) routes to
``self.config["metadata"]`` -- but ``self.config`` does not exist until
``Node.__init__`` runs, so ANY construction of this node (with or without
kwargs) raised ``AttributeError: 'SemanticMemoryStoreNode' object has no
attribute 'config'``. No test constructed this registered, exported node
before this discovery -- it was a silently orphaned, always-broken class.

Fix: the ``metadata`` default is set via ``self.config.setdefault("metadata",
None)`` AFTER ``super().__init__()``, and ``run()`` reads the user parameter
from ``self.config.get("metadata")`` instead of the ``self.metadata`` property
(which returns the framework's own ``NodeMetadata`` bookkeeping object, not
this node's per-item metadata dict).
"""

from __future__ import annotations

import pytest

from kaizen.nodes.ai.semantic_memory import SemanticMemoryStoreNode


def test_construction_succeeds_with_no_kwargs() -> None:
    node = SemanticMemoryStoreNode(name="store_regression_bare")
    assert node is not None
    assert node.config.get("metadata") is None


def test_construction_succeeds_with_metadata_kwarg() -> None:
    node = SemanticMemoryStoreNode(
        name="store_regression_with_metadata", metadata={"source": "test"}
    )
    assert node.config.get("metadata") == {"source": "test"}


@pytest.mark.asyncio
async def test_run_defaults_metadata_to_empty_dict_when_absent(monkeypatch) -> None:
    """run() must default to {} (not the framework NodeMetadata object) when
    neither the constructor nor the run() call supplies a metadata dict."""
    from unittest.mock import AsyncMock, MagicMock

    node = SemanticMemoryStoreNode(name="store_regression_run_default")
    mock_provider = MagicMock()
    mock_provider.embed_text = AsyncMock(
        return_value=MagicMock(embeddings=[MagicMock()], model="test-model")
    )
    # _provider is instance-level (#1803 security-review MEDIUM fix -- no
    # longer class-cached), so patch the instance, not the class.
    monkeypatch.setattr(node, "_provider", mock_provider)
    mock_store = MagicMock()
    mock_store.add = AsyncMock(return_value="item-1")
    monkeypatch.setattr(SemanticMemoryStoreNode, "_store", mock_store)

    result = await node.run(content="hello")
    assert result["success"] is True
    stored_item = mock_store.add.call_args[0][0]
    assert stored_item.metadata == {}


@pytest.mark.asyncio
async def test_run_uses_construction_time_metadata_default(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    node = SemanticMemoryStoreNode(
        name="store_regression_run_ctor_default", metadata={"source": "ctor"}
    )
    mock_provider = MagicMock()
    mock_provider.embed_text = AsyncMock(
        return_value=MagicMock(embeddings=[MagicMock()], model="test-model")
    )
    monkeypatch.setattr(node, "_provider", mock_provider)
    mock_store = MagicMock()
    mock_store.add = AsyncMock(return_value="item-1")
    monkeypatch.setattr(SemanticMemoryStoreNode, "_store", mock_store)

    result = await node.run(content="hello")
    assert result["success"] is True
    stored_item = mock_store.add.call_args[0][0]
    assert stored_item.metadata == {"source": "ctor"}
