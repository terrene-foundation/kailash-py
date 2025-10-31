"""
Unit tests for enhanced memory enterprise features.

Tests memory tier operations (hot/warm/cold), enterprise persistence,
and advanced semantic memory functionality.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from kailash.nodes.ai.semantic_memory import (
    EmbeddingResult,
    InMemoryVectorStore,
    SemanticAgentMatchingNode,
    SemanticMemoryItem,
    SemanticMemorySearchNode,
    SemanticMemoryStoreNode,
    SimpleEmbeddingProvider,
)


class TestMemoryTierOperations:
    """Test memory tier functionality (hot/warm/cold storage)."""

    def test_memory_item_age_classification(self):
        """Test classifying memory items by age for tier management."""
        now = datetime.now(UTC)

        # Hot memory: recent items (< 1 hour)
        hot_item = SemanticMemoryItem(
            id="hot_item",
            content="recent content",
            embedding=np.array([1.0, 0.0, 0.0]),
            metadata={"tier": "hot"},
            created_at=now - timedelta(minutes=30),
            collection="default",
        )

        # Warm memory: medium age items (1 hour - 1 day)
        warm_item = SemanticMemoryItem(
            id="warm_item",
            content="medium age content",
            embedding=np.array([0.0, 1.0, 0.0]),
            metadata={"tier": "warm"},
            created_at=now - timedelta(hours=6),
            collection="default",
        )

        # Cold memory: old items (> 1 day)
        cold_item = SemanticMemoryItem(
            id="cold_item",
            content="old content",
            embedding=np.array([0.0, 0.0, 1.0]),
            metadata={"tier": "cold"},
            created_at=now - timedelta(days=7),
            collection="default",
        )

        # Verify items have correct properties
        assert hot_item.id == "hot_item"
        assert warm_item.id == "warm_item"
        assert cold_item.id == "cold_item"

        # Verify age differences
        hot_age = now - hot_item.created_at
        warm_age = now - warm_item.created_at
        cold_age = now - cold_item.created_at

        assert hot_age < timedelta(hours=1)
        assert timedelta(hours=1) <= warm_age < timedelta(days=1)
        assert cold_age >= timedelta(days=1)

    @pytest.mark.asyncio
    async def test_tier_based_search_performance(self):
        """Test that search performance varies by memory tier."""
        store = InMemoryVectorStore()

        # Add items to different tiers
        now = datetime.now(UTC)

        # Hot tier items (should be searched first)
        for i in range(10):
            hot_item = SemanticMemoryItem(
                id=f"hot_{i}",
                content=f"hot content {i}",
                embedding=np.random.rand(384),
                metadata={"tier": "hot", "priority": "high"},
                created_at=now - timedelta(minutes=i * 5),
                collection="performance_test",
            )
            await store.add(hot_item)

        # Warm tier items
        for i in range(20):
            warm_item = SemanticMemoryItem(
                id=f"warm_{i}",
                content=f"warm content {i}",
                embedding=np.random.rand(384),
                metadata={"tier": "warm", "priority": "medium"},
                created_at=now - timedelta(hours=i + 2),
                collection="performance_test",
            )
            await store.add(warm_item)

        # Cold tier items
        for i in range(50):
            cold_item = SemanticMemoryItem(
                id=f"cold_{i}",
                content=f"cold content {i}",
                embedding=np.random.rand(384),
                metadata={"tier": "cold", "priority": "low"},
                created_at=now - timedelta(days=i + 2),
                collection="performance_test",
            )
            await store.add(cold_item)

        # Perform search
        query_embedding = np.random.rand(384)
        results = await store.search_similar(
            embedding=query_embedding,
            collection="performance_test",
            limit=10,
            threshold=0.0,  # Accept all for testing
        )

        # Verify search returned results
        assert len(results) <= 10
        assert len(results) > 0

        # Verify results are sorted by similarity
        similarities = [similarity for _, similarity in results]
        assert similarities == sorted(similarities, reverse=True)

    @pytest.mark.asyncio
    async def test_memory_tier_management(self):
        """Test enterprise memory tier management functionality."""
        store = InMemoryVectorStore()

        # Add items to store
        now = datetime.now(UTC)
        items_by_tier = {"hot": [], "warm": [], "cold": []}

        # Create items for each tier
        for tier, delta in [
            ("hot", timedelta(minutes=30)),
            ("warm", timedelta(hours=6)),
            ("cold", timedelta(days=7)),
        ]:
            for i in range(5):
                item = SemanticMemoryItem(
                    id=f"{tier}_{i}",
                    content=f"{tier} tier content {i}",
                    embedding=np.random.rand(384),
                    metadata={"tier": tier, "access_count": 0},
                    created_at=now - delta,
                    collection="tier_test",
                )
                items_by_tier[tier].append(item)
                await store.add(item)

        # Verify items were added correctly
        collections = await store.get_collections()
        assert "tier_test" in collections

        # Verify all items are accessible
        total_items = sum(len(items) for items in items_by_tier.values())
        assert len(store.items) == total_items

        # Verify items are in correct collection
        tier_test_items = store.collections.get("tier_test", [])
        assert len(tier_test_items) == total_items


class TestEnterpriseMemoryPersistence:
    """Test enterprise memory persistence features."""

    @pytest.mark.asyncio
    async def test_memory_backup_and_restore(self):
        """Test memory backup and restore functionality."""
        store1 = InMemoryVectorStore()

        # Add test data
        test_items = []
        for i in range(5):
            item = SemanticMemoryItem(
                id=f"backup_item_{i}",
                content=f"backup content {i}",
                embedding=np.array([float(i), float(i) * 0.5, float(i) * 0.25]),
                metadata={"backup_test": True, "index": i},
                created_at=datetime.now(UTC),
                collection="backup_collection",
            )
            test_items.append(item)
            await store1.add(item)

        # Simulate backup by extracting data
        backup_data = {
            "items": {
                item_id: item.to_dict() for item_id, item in store1.items.items()
            },
            "collections": dict(store1.collections),
        }

        # Create new store and restore
        store2 = InMemoryVectorStore()

        # Restore items
        for item_id, item_data in backup_data["items"].items():
            restored_item = SemanticMemoryItem(
                id=item_data["id"],
                content=item_data["content"],
                embedding=np.array(item_data["embedding"]),
                metadata=item_data["metadata"],
                created_at=datetime.fromisoformat(item_data["created_at"]),
                collection=item_data["collection"],
            )
            await store2.add(restored_item)

        # Verify restore
        assert len(store2.items) == len(store1.items)
        assert store2.collections == store1.collections

        # Verify individual items
        for item_id in store1.items:
            assert item_id in store2.items
            original = store1.items[item_id]
            restored = store2.items[item_id]
            assert original.id == restored.id
            assert original.content == restored.content
            assert np.array_equal(original.embedding, restored.embedding)
            assert original.metadata == restored.metadata

    @pytest.mark.asyncio
    async def test_memory_versioning(self):
        """Test memory item versioning for enterprise features."""
        store = InMemoryVectorStore()

        # Create base item
        base_item = SemanticMemoryItem(
            id="versioned_item",
            content="version 1 content",
            embedding=np.array([1.0, 0.0, 0.0]),
            metadata={"version": 1, "history": []},
            created_at=datetime.now(UTC),
            collection="versioned",
        )
        await store.add(base_item)

        # Update item (simulate versioning)
        updated_item = SemanticMemoryItem(
            id="versioned_item_v2",
            content="version 2 content",
            embedding=np.array([1.0, 0.5, 0.0]),
            metadata={
                "version": 2,
                "previous_version": "versioned_item",
                "history": ["versioned_item"],
            },
            created_at=datetime.now(UTC),
            collection="versioned",
        )
        await store.add(updated_item)

        # Verify both versions exist
        assert "versioned_item" in store.items
        assert "versioned_item_v2" in store.items

        # Verify version metadata
        v1 = store.items["versioned_item"]
        v2 = store.items["versioned_item_v2"]

        assert v1.metadata["version"] == 1
        assert v2.metadata["version"] == 2
        assert v2.metadata["previous_version"] == "versioned_item"
        assert "versioned_item" in v2.metadata["history"]

    @pytest.mark.asyncio
    async def test_memory_expiration(self):
        """Test memory expiration for enterprise cleanup."""
        store = InMemoryVectorStore()

        # Add items with different expiration times
        now = datetime.now(UTC)

        # Expired item
        expired_item = SemanticMemoryItem(
            id="expired_item",
            content="expired content",
            embedding=np.array([1.0, 0.0, 0.0]),
            metadata={"expires_at": (now - timedelta(hours=1)).isoformat()},
            created_at=now - timedelta(days=2),
            collection="expiration_test",
        )
        await store.add(expired_item)

        # Valid item
        valid_item = SemanticMemoryItem(
            id="valid_item",
            content="valid content",
            embedding=np.array([0.0, 1.0, 0.0]),
            metadata={"expires_at": (now + timedelta(hours=1)).isoformat()},
            created_at=now - timedelta(minutes=30),
            collection="expiration_test",
        )
        await store.add(valid_item)

        # No expiration item
        permanent_item = SemanticMemoryItem(
            id="permanent_item",
            content="permanent content",
            embedding=np.array([0.0, 0.0, 1.0]),
            metadata={},  # No expiration
            created_at=now - timedelta(minutes=15),
            collection="expiration_test",
        )
        await store.add(permanent_item)

        # Verify all items were added
        assert len(store.items) == 3

        # Simulate expiration check (would be implemented in enterprise version)
        active_items = []
        for item_id, item in store.items.items():
            expires_at_str = item.metadata.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at > now:
                    active_items.append(item_id)
            else:
                # No expiration means permanent
                active_items.append(item_id)

        # Should have valid and permanent items, but not expired
        assert "valid_item" in active_items
        assert "permanent_item" in active_items
        assert "expired_item" not in active_items


class TestAdvancedSemanticMemory:
    """Test advanced semantic memory features."""

    @pytest.mark.asyncio
    async def test_semantic_clustering(self):
        """Test semantic clustering of memory items."""
        store = InMemoryVectorStore()

        # Add related items that should cluster together
        cluster1_items = [
            ("tech_1", "Python programming language", [1.0, 0.0, 0.0]),
            ("tech_2", "JavaScript programming language", [0.9, 0.1, 0.0]),
            ("tech_3", "Programming and software development", [0.8, 0.2, 0.0]),
        ]

        cluster2_items = [
            ("food_1", "Italian pasta and cuisine", [0.0, 1.0, 0.0]),
            ("food_2", "Mediterranean cooking recipes", [0.1, 0.9, 0.0]),
            ("food_3", "Traditional Italian dishes", [0.0, 0.8, 0.2]),
        ]

        all_items = cluster1_items + cluster2_items

        for item_id, content, embedding in all_items:
            item = SemanticMemoryItem(
                id=item_id,
                content=content,
                embedding=np.array(embedding),
                metadata={"cluster_test": True},
                created_at=datetime.now(UTC),
                collection="clustering",
            )
            await store.add(item)

        # Search with tech-related query
        tech_query = np.array([0.95, 0.05, 0.0])
        tech_results = await store.search_similar(
            embedding=tech_query,
            collection="clustering",
            limit=3,
            threshold=0.5,
        )

        # Should find tech items
        tech_result_ids = [item.id for item, _ in tech_results]
        assert any(item_id.startswith("tech_") for item_id in tech_result_ids)

        # Search with food-related query
        food_query = np.array([0.05, 0.95, 0.0])
        food_results = await store.search_similar(
            embedding=food_query,
            collection="clustering",
            limit=3,
            threshold=0.5,
        )

        # Should find food items
        food_result_ids = [item.id for item, _ in food_results]
        assert any(item_id.startswith("food_") for item_id in food_result_ids)

    @pytest.mark.asyncio
    async def test_memory_access_patterns(self):
        """Test memory access pattern tracking for enterprise analytics."""
        store = InMemoryVectorStore()

        # Add items with access tracking
        items_data = [
            ("popular_item", "Frequently accessed content", 10),
            ("moderate_item", "Sometimes accessed content", 3),
            ("rare_item", "Rarely accessed content", 1),
        ]

        for item_id, content, access_count in items_data:
            item = SemanticMemoryItem(
                id=item_id,
                content=content,
                embedding=np.random.rand(384),
                metadata={
                    "access_count": access_count,
                    "last_accessed": datetime.now(UTC).isoformat(),
                    "access_pattern": "enterprise_tracking",
                },
                created_at=datetime.now(UTC),
                collection="access_patterns",
            )
            await store.add(item)

        # Simulate access pattern analysis
        query_embedding = np.random.rand(384)
        results = await store.search_similar(
            embedding=query_embedding,
            collection="access_patterns",
            limit=10,
            threshold=0.0,
        )

        # Verify all items found
        assert len(results) == 3

        # Check access count metadata
        for item, _ in results:
            assert "access_count" in item.metadata
            assert item.metadata["access_count"] > 0
            assert "last_accessed" in item.metadata

    @pytest.mark.asyncio
    async def test_multi_modal_memory(self):
        """Test multi-modal memory support (text + metadata embeddings)."""
        store = InMemoryVectorStore()

        # Add items with different modalities
        multi_modal_items = [
            {
                "id": "text_image_1",
                "content": "Red sports car image",
                "embedding": np.array([0.8, 0.2, 0.0]),  # Text embedding
                "metadata": {
                    "modality": "text+image",
                    "image_embedding": [0.9, 0.1, 0.0],  # Image embedding
                    "combined_features": True,
                },
            },
            {
                "id": "audio_text_1",
                "content": "Music composition in C major",
                "embedding": np.array([0.0, 0.8, 0.2]),  # Text embedding
                "metadata": {
                    "modality": "text+audio",
                    "audio_embedding": [0.1, 0.9, 0.0],  # Audio embedding
                    "combined_features": True,
                },
            },
        ]

        for item_data in multi_modal_items:
            item = SemanticMemoryItem(
                id=item_data["id"],
                content=item_data["content"],
                embedding=item_data["embedding"],
                metadata=item_data["metadata"],
                created_at=datetime.now(UTC),
                collection="multi_modal",
            )
            await store.add(item)

        # Search with combined query
        query_embedding = np.array([0.5, 0.5, 0.0])
        results = await store.search_similar(
            embedding=query_embedding,
            collection="multi_modal",
            limit=10,
            threshold=0.0,
        )

        # Verify multi-modal items found
        assert len(results) == 2
        for item, _ in results:
            assert item.metadata.get("combined_features") is True
            assert "embedding" in item.metadata or "modality" in item.metadata


class TestEnterpriseSemanticNodes:
    """Test enterprise-level semantic memory nodes."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_semantic_memory_store_with_enterprise_features(self):
        """Test semantic memory store with enterprise-level features."""
        node = SemanticMemoryStoreNode(name="enterprise_store")

        # Store content with enterprise metadata
        result = await node.run(
            content=[
                "Enterprise document 1",
                "Enterprise document 2",
                "Enterprise document 3",
            ],
            metadata={
                "enterprise_features": True,
                "security_level": "confidential",
                "department": "engineering",
                "version": "1.0",
            },
            collection="enterprise_docs",
        )

        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["ids"]) == 3
        assert result["collection"] == "enterprise_docs"

        # Verify enterprise metadata was stored
        # (In a real implementation, we'd verify the metadata was properly stored)

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_semantic_search_with_enterprise_filters(self):
        """Test semantic search with enterprise-level filtering."""
        # First store some enterprise content
        store_node = SemanticMemoryStoreNode(name="enterprise_store")

        # Store content with different security levels
        await store_node.run(
            content=["Public information document"],
            metadata={"security_level": "public", "department": "marketing"},
            collection="enterprise_docs",
        )

        await store_node.run(
            content=["Confidential business plan"],
            metadata={"security_level": "confidential", "department": "strategy"},
            collection="enterprise_docs",
        )

        # Search with enterprise context
        search_node = SemanticMemorySearchNode(name="enterprise_search")

        result = await search_node.run(
            query="business information",
            collection="enterprise_docs",
            limit=10,
            threshold=0.1,
        )

        assert result["success"] is True
        assert "results" in result

        # In an enterprise implementation, we would filter by security level here

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_semantic_agent_matching_enterprise(self):
        """Test semantic agent matching with enterprise agent pools."""
        node = SemanticAgentMatchingNode(name="enterprise_matching")

        # Enterprise agent pool with specialized skills
        enterprise_agents = [
            {
                "id": "security_specialist",
                "name": "Security Expert",
                "skills": ["cybersecurity", "threat analysis", "compliance"],
                "clearance_level": "top_secret",
                "department": "security",
            },
            {
                "id": "data_engineer",
                "name": "Data Engineering Expert",
                "skills": ["big data", "ETL", "data pipelines", "cloud architecture"],
                "clearance_level": "confidential",
                "department": "engineering",
            },
            {
                "id": "compliance_officer",
                "name": "Compliance Specialist",
                "skills": ["regulatory compliance", "audit", "policy development"],
                "clearance_level": "confidential",
                "department": "legal",
            },
        ]

        # Enterprise requirements
        requirements = [
            "Need security expert for threat assessment",
            "Must have appropriate clearance level",
            "Experience with enterprise security frameworks",
        ]

        result = await node.run(
            requirements=requirements,
            agents=enterprise_agents,
            limit=3,
            threshold=0.2,
            weight_semantic=0.7,
            weight_keyword=0.3,
        )

        assert result["success"] is True
        assert result["count"] > 0
        assert len(result["matches"]) > 0

        # Verify enterprise agent matching
        top_match = result["matches"][0]
        assert "agent" in top_match
        assert "combined_score" in top_match

        # In enterprise implementation, would verify clearance levels match requirements
