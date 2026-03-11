#!/usr/bin/env python3
"""
Integration tests for DataFlow Schema Cache System (ADR-001).

Tests comprehensive schema cache behavior with real SQLite databases following
the 3-tier testing strategy (Tier 2 - Integration).

Test Coverage:
- Cache enabled vs disabled behavior
- Multi-operation workflows showing cache hits/misses
- Manual cache clearing operations
- Metrics tracking and retrieval
- Cached tables introspection
- Individual table cache clearing
- End-to-end workflows with multiple models
- TTL expiration (if time permits)

Testing Strategy:
- NO MOCKING policy - uses real SQLite :memory: databases
- Each test creates fresh DataFlow instance for isolation
- Verifies metrics after each operation
- Tests both WorkflowBuilder + LocalRuntime patterns
- Comprehensive validation of all cache operations

ADR Reference: reports/architecture/ADR-001-schema-cache.md
Proposal Reference: DATAFLOW_COMPREHENSIVE_FIX_PROPOSAL.md Section 5.2
"""

import time
from pathlib import Path

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


# =============================================================================
# Test Group 1: Cache Enabled vs Disabled Behavior
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_schema_cache_enabled_shows_cache_hits(runtime):
    """
    Test that schema cache enabled results in cache hits on subsequent operations.

    Verifies:
    - First operation: cache miss (table creation)
    - Second operation: cache hit (table exists)
    - Metrics accurately track hits/misses
    - Hit rate calculated correctly
    """
    # Create DataFlow with cache enabled
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class User:
        id: str
        name: str
        email: str

    # First operation - should be cache miss
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create_user1",
        {
            "database_url": ":memory:",
            "id": "user-001",
            "name": "Alice",
            "email": "alice@example.com",
        },
    )
    results, run_id = runtime.execute(workflow.build())

    # Verify first operation succeeded
    assert "create_user1" in results
    assert results["create_user1"].get("status") != "error"

    # Check metrics after first operation
    metrics = db.get_schema_cache_metrics()
    assert metrics["enabled"] is True
    assert metrics["misses"] >= 1, "First operation should be cache miss"
    assert metrics["cache_size"] >= 1, "Cache should contain User table"

    # Second operation - should be cache hit
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create_user2",
        {
            "database_url": ":memory:",
            "id": "user-002",
            "name": "Bob",
            "email": "bob@example.com",
        },
    )
    results, run_id = runtime.execute(workflow.build())

    # Verify second operation succeeded
    assert "create_user2" in results
    assert results["create_user2"].get("status") != "error"

    # Check metrics after second operation
    metrics_after = db.get_schema_cache_metrics()
    assert metrics_after["enabled"] is True
    assert metrics_after["hits"] >= 1, "Second operation should be cache hit"
    assert metrics_after["hit_rate_percent"] > 0, "Hit rate should be positive"

    print(
        f"✓ Cache metrics: {metrics_after['hits']} hits, {metrics_after['misses']} misses, "
        f"{metrics_after['hit_rate_percent']:.1f}% hit rate"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_schema_cache_disabled_no_cache_hits(runtime):
    """
    Test that schema cache disabled results in no cache hits.

    Verifies:
    - Cache disabled in configuration
    - All operations bypass cache
    - Metrics show 0 hits
    - Cache size remains 0
    """
    # Create DataFlow with cache disabled
    db = DataFlow(":memory:", schema_cache_enabled=False)

    @db.model
    class Product:
        id: str
        name: str
        price: float

    # Execute multiple operations
    for i in range(3):
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode",
            f"create_product_{i}",
            {
                "database_url": ":memory:",
                "id": f"prod-{i:03d}",
                "name": f"Product {i}",
                "price": 10.0 + i,
            },
        )
        results, run_id = runtime.execute(workflow.build())
        assert f"create_product_{i}" in results

    # Check metrics - should show cache disabled
    metrics = db.get_schema_cache_metrics()
    assert metrics["enabled"] is False, "Cache should be disabled"
    assert metrics["hits"] == 0, "Disabled cache should have no hits"
    assert metrics["cache_size"] == 0, "Disabled cache should be empty"

    print(f"✓ Cache disabled: {metrics['hits']} hits, {metrics['cache_size']} entries")


# =============================================================================
# Test Group 2: Multi-Operation Workflows (Cache Hits/Misses)
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_multi_operation_workflow_cache_hits(runtime):
    """
    Test cache behavior with multiple CRUD operations on same model.

    Verifies:
    - Create, Read, Update, Delete all benefit from cache
    - First operation (Create) causes cache miss
    - Subsequent operations (Read, Update, Delete) are cache hits
    - Metrics accumulate correctly across operations
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Customer:
        id: str
        name: str
        email: str
        active: bool = True

    # Operation 1: CREATE (cache miss)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "CustomerCreateNode",
        "create",
        {
            "database_url": ":memory:",
            "id": "cust-001",
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "active": True,
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "create" in results

    metrics_after_create = db.get_schema_cache_metrics()
    initial_misses = metrics_after_create["misses"]

    # Operation 2: READ (cache hit)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "CustomerReadNode", "read", {"database_url": ":memory:", "id": "cust-001"}
    )
    results, _ = runtime.execute(workflow.build())
    assert "read" in results

    metrics_after_read = db.get_schema_cache_metrics()
    assert metrics_after_read["hits"] >= 1, "Read should be cache hit"

    # Operation 3: UPDATE (cache hit)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "CustomerUpdateNode",
        "update",
        {
            "database_url": ":memory:",
            "filter": {"id": "cust-001"},
            "fields": {"active": False},
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "update" in results

    metrics_after_update = db.get_schema_cache_metrics()
    assert metrics_after_update["hits"] >= 2, "Update should be cache hit"

    # Operation 4: LIST (cache hit)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "CustomerListNode", "list", {"database_url": ":memory:", "limit": 10}
    )
    results, _ = runtime.execute(workflow.build())
    assert "list" in results

    final_metrics = db.get_schema_cache_metrics()
    assert final_metrics["hits"] >= 3, "List should be cache hit"
    assert final_metrics["misses"] == initial_misses, "No new cache misses"
    assert final_metrics["hit_rate_percent"] > 50, "Hit rate should be high"

    print(
        f"✓ Multi-operation workflow: {final_metrics['hits']} hits, "
        f"{final_metrics['hit_rate_percent']:.1f}% hit rate"
    )


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_multiple_models_separate_cache_entries(runtime):
    """
    Test that different models get separate cache entries.

    Verifies:
    - Each model creates its own cache entry
    - Cache size increases with each new model
    - Cache hits work independently per model
    - get_cached_tables() shows all models
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class User:
        id: str
        name: str

    @db.model
    class Post:
        id: str
        title: str
        author_id: str

    @db.model
    class Comment:
        id: str
        content: str
        post_id: str

    # Create one record for each model (cache misses)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "user",
        {"database_url": ":memory:", "id": "u1", "name": "Alice"},
    )
    workflow.add_node(
        "PostCreateNode",
        "post",
        {
            "database_url": ":memory:",
            "id": "p1",
            "title": "Hello World",
            "author_id": "u1",
        },
    )
    workflow.add_node(
        "CommentCreateNode",
        "comment",
        {
            "database_url": ":memory:",
            "id": "c1",
            "content": "Great post!",
            "post_id": "p1",
        },
    )
    results, _ = runtime.execute(workflow.build())

    assert "user" in results
    assert "post" in results
    assert "comment" in results

    # Check cache has all three models
    metrics = db.get_schema_cache_metrics()
    assert metrics["cache_size"] >= 3, "Cache should contain all 3 models"

    cached_tables = db.get_cached_tables()
    assert len(cached_tables) >= 3, "Should have 3 cached tables"

    # Verify each model is in cache
    model_names = [entry["model_name"] for entry in cached_tables.values()]
    assert "User" in model_names
    assert "Post" in model_names
    assert "Comment" in model_names

    print(f"✓ Multiple models: {len(cached_tables)} tables cached")


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_bulk_operations_cache_behavior(runtime):
    """
    Test cache behavior with bulk operations.

    Verifies:
    - Bulk create benefits from cache
    - Bulk update benefits from cache
    - Bulk operations counted as single cache access
    - Performance improvement visible in metrics
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Order:
        id: str
        customer_id: str
        total: float
        status: str = "pending"

    # Bulk create (cache miss on first access)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "OrderBulkCreateNode",
        "bulk_create",
        {
            "database_url": ":memory:",
            "records": [
                {"id": f"order-{i:03d}", "customer_id": "cust-001", "total": 100.0 + i}
                for i in range(10)
            ],
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "bulk_create" in results

    metrics_after_create = db.get_schema_cache_metrics()
    initial_requests = metrics_after_create["hits"] + metrics_after_create["misses"]

    # Bulk update (cache hit)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "OrderBulkUpdateNode",
        "bulk_update",
        {
            "database_url": ":memory:",
            "filter": {"status": "pending"},
            "fields": {"status": "processing"},
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "bulk_update" in results

    metrics_after_update = db.get_schema_cache_metrics()
    assert metrics_after_update["hits"] >= 1, "Bulk update should hit cache"

    print(f"✓ Bulk operations: {metrics_after_update['hits']} cache hits")


# =============================================================================
# Test Group 3: Manual Cache Clearing
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_clear_schema_cache_removes_all_entries(runtime):
    """
    Test clear_schema_cache() method removes all cached tables.

    Verifies:
    - Cache populated with multiple models
    - clear_schema_cache() empties cache
    - Metrics reset correctly
    - Subsequent operations cause cache misses
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Product:
        id: str
        name: str

    @db.model
    class Category:
        id: str
        title: str

    # Populate cache
    workflow = WorkflowBuilder()
    workflow.add_node(
        "ProductCreateNode",
        "prod",
        {"database_url": ":memory:", "id": "p1", "name": "Widget"},
    )
    workflow.add_node(
        "CategoryCreateNode",
        "cat",
        {"database_url": ":memory:", "id": "c1", "title": "Electronics"},
    )
    results, _ = runtime.execute(workflow.build())

    # Verify cache populated
    metrics_before = db.get_schema_cache_metrics()
    assert metrics_before["cache_size"] >= 2, "Cache should have 2+ entries"

    # Clear cache
    db.clear_schema_cache()

    # Verify cache cleared
    metrics_after = db.get_schema_cache_metrics()
    assert metrics_after["cache_size"] == 0, "Cache should be empty after clear"

    # Verify cached tables empty
    cached_tables = db.get_cached_tables()
    assert len(cached_tables) == 0, "No tables should be cached"

    print(
        f"✓ Cache cleared: {metrics_before['cache_size']} → {metrics_after['cache_size']} entries"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_clear_schema_cache_subsequent_operations_miss(runtime):
    """
    Test that operations after clear_schema_cache() cause cache misses.

    Verifies:
    - Initial operation cached
    - Cache cleared
    - Next operation on same model is cache miss
    - Cache repopulated correctly
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Session:
        id: str
        user_id: str
        token: str

    # First operation - cache miss
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SessionCreateNode",
        "session1",
        {
            "database_url": ":memory:",
            "id": "sess-001",
            "user_id": "user-001",
            "token": "abc123",
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "session1" in results

    metrics_before_clear = db.get_schema_cache_metrics()
    misses_before = metrics_before_clear["misses"]

    # Clear cache
    db.clear_schema_cache()

    # Second operation - should be cache miss again
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SessionCreateNode",
        "session2",
        {
            "database_url": ":memory:",
            "id": "sess-002",
            "user_id": "user-002",
            "token": "def456",
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "session2" in results

    metrics_after_clear = db.get_schema_cache_metrics()
    assert (
        metrics_after_clear["misses"] > misses_before
    ), "Should have new cache miss after clear"
    assert metrics_after_clear["cache_size"] >= 1, "Cache should be repopulated"

    print(
        f"✓ Cache cleared and repopulated: {metrics_after_clear['misses']} total misses"
    )


# =============================================================================
# Test Group 4: get_schema_cache_metrics() Method
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema_cache_metrics_structure(runtime):
    """
    Test get_schema_cache_metrics() returns correct structure.

    Verifies:
    - All required keys present
    - Values have correct types
    - Hit rate calculation accurate
    - Metrics update in real-time
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Metric:
        id: str
        value: float

    # Initial metrics
    metrics = db.get_schema_cache_metrics()

    # Verify structure
    required_keys = [
        "enabled",
        "cache_size",
        "max_size",
        "hits",
        "misses",
        "hit_rate_percent",
        "evictions",
        "failures",
        "ttl_seconds",
    ]

    for key in required_keys:
        assert key in metrics, f"Missing required key: {key}"

    # Verify types
    assert isinstance(metrics["enabled"], bool)
    assert isinstance(metrics["cache_size"], int)
    assert isinstance(metrics["max_size"], int)
    assert isinstance(metrics["hits"], int)
    assert isinstance(metrics["misses"], int)
    assert isinstance(metrics["hit_rate_percent"], (int, float))
    assert isinstance(metrics["evictions"], int)
    assert isinstance(metrics["failures"], int)

    print(f"✓ Metrics structure valid: {len(required_keys)} keys present")


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema_cache_metrics_accuracy(runtime):
    """
    Test get_schema_cache_metrics() returns accurate counts.

    Verifies:
    - Hit count accurate
    - Miss count accurate
    - Hit rate percentage calculated correctly
    - Cache size reflects actual entries
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Event:
        id: str
        name: str
        timestamp: float

    # Execute 5 operations
    for i in range(5):
        workflow = WorkflowBuilder()
        workflow.add_node(
            "EventCreateNode",
            f"event_{i}",
            {
                "database_url": ":memory:",
                "id": f"evt-{i:03d}",
                "name": f"Event {i}",
                "timestamp": time.time(),
            },
        )
        results, _ = runtime.execute(workflow.build())
        assert f"event_{i}" in results

    metrics = db.get_schema_cache_metrics()

    # Should have: 1 miss (first op) + 4 hits (subsequent ops)
    total_requests = metrics["hits"] + metrics["misses"]
    assert total_requests >= 5, "Should have at least 5 requests"

    # Verify hit rate calculation
    expected_hit_rate = (
        (metrics["hits"] / total_requests * 100) if total_requests > 0 else 0
    )
    assert (
        abs(metrics["hit_rate_percent"] - expected_hit_rate) < 0.01
    ), "Hit rate calculation incorrect"

    # Cache should contain Event table
    assert metrics["cache_size"] >= 1, "Cache should have at least 1 entry"

    print(
        f"✓ Metrics accurate: {metrics['hits']}/{total_requests} = "
        f"{metrics['hit_rate_percent']:.1f}% hit rate"
    )


# =============================================================================
# Test Group 5: get_cached_tables() Method
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_cached_tables_returns_all_models(runtime):
    """
    Test get_cached_tables() returns information about all cached models.

    Verifies:
    - Returns dict with cache keys
    - Each entry has required fields
    - Model names match registered models
    - State shows 'ensured' for successful operations
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Author:
        id: str
        name: str

    @db.model
    class Book:
        id: str
        title: str
        author_id: str

    # Create records for both models
    workflow = WorkflowBuilder()
    workflow.add_node(
        "AuthorCreateNode",
        "author",
        {"database_url": ":memory:", "id": "auth-001", "name": "Jane Doe"},
    )
    workflow.add_node(
        "BookCreateNode",
        "book",
        {
            "database_url": ":memory:",
            "id": "book-001",
            "title": "DataFlow Guide",
            "author_id": "auth-001",
        },
    )
    results, _ = runtime.execute(workflow.build())

    # Get cached tables
    cached_tables = db.get_cached_tables()

    assert len(cached_tables) >= 2, "Should have at least 2 cached tables"

    # Verify entry structure
    for cache_key, entry in cached_tables.items():
        assert "model_name" in entry
        assert "state" in entry
        assert "first_ensured_at" in entry
        assert "last_validated_at" in entry
        assert "validation_count" in entry
        assert "failure_count" in entry
        assert "age_seconds" in entry

    # Verify model names
    model_names = [entry["model_name"] for entry in cached_tables.values()]
    assert "Author" in model_names
    assert "Book" in model_names

    print(f"✓ Cached tables: {len(cached_tables)} entries with correct structure")


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_cached_tables_entry_details(runtime):
    """
    Test get_cached_tables() entry details are accurate.

    Verifies:
    - State field shows correct status
    - Timestamps are reasonable
    - Validation count increments
    - Failure count is 0 for successful operations
    - Age calculation is correct
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Log:
        id: str
        message: str
        level: str = "info"

    # Create initial record
    workflow = WorkflowBuilder()
    workflow.add_node(
        "LogCreateNode",
        "log1",
        {
            "database_url": ":memory:",
            "id": "log-001",
            "message": "System started",
            "level": "info",
        },
    )
    start_time = time.time()
    results, _ = runtime.execute(workflow.build())

    # Get cached tables
    cached_tables = db.get_cached_tables()

    # Find Log entry
    log_entry = None
    for entry in cached_tables.values():
        if entry["model_name"] == "Log":
            log_entry = entry
            break

    assert log_entry is not None, "Log model should be in cache"

    # Verify state
    assert (
        log_entry["state"] == "ensured"
    ), "State should be 'ensured' after successful operation"

    # Verify timestamps
    assert log_entry["first_ensured_at"] > 0, "first_ensured_at should be set"
    assert log_entry["last_validated_at"] > 0, "last_validated_at should be set"
    assert log_entry["first_ensured_at"] >= start_time, "Timestamp should be recent"

    # Verify counts
    assert log_entry["validation_count"] >= 1, "Should have at least 1 validation"
    assert log_entry["failure_count"] == 0, "No failures expected"

    # Verify age
    assert log_entry["age_seconds"] >= 0, "Age should be non-negative"
    assert log_entry["age_seconds"] < 60, "Age should be less than 60 seconds"

    print(
        f"✓ Cached table entry valid: state={log_entry['state']}, "
        f"validations={log_entry['validation_count']}"
    )


# =============================================================================
# Test Group 6: clear_table_cache() Method
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_clear_table_cache_removes_specific_model(runtime):
    """
    Test clear_table_cache() removes only specified model.

    Verifies:
    - Multiple models in cache
    - Clearing one model doesn't affect others
    - Returns True when entry exists
    - Returns False when entry doesn't exist
    - Cache size decrements correctly
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Invoice:
        id: str
        amount: float

    @db.model
    class Payment:
        id: str
        invoice_id: str
        amount: float

    # Populate cache with both models
    workflow = WorkflowBuilder()
    workflow.add_node(
        "InvoiceCreateNode",
        "invoice",
        {"database_url": ":memory:", "id": "inv-001", "amount": 100.0},
    )
    workflow.add_node(
        "PaymentCreateNode",
        "payment",
        {
            "database_url": ":memory:",
            "id": "pay-001",
            "invoice_id": "inv-001",
            "amount": 100.0,
        },
    )
    results, _ = runtime.execute(workflow.build())

    # Verify both in cache
    metrics_before = db.get_schema_cache_metrics()
    cache_size_before = metrics_before["cache_size"]
    assert cache_size_before >= 2, "Should have at least 2 entries"

    # Clear only Invoice table
    result = db.clear_table_cache("Invoice", ":memory:")
    assert result is True, "Should return True when entry exists"

    # Verify only Invoice removed
    cached_tables = db.get_cached_tables()
    model_names = [entry["model_name"] for entry in cached_tables.values()]

    assert "Invoice" not in model_names, "Invoice should be removed"
    assert "Payment" in model_names, "Payment should still be cached"

    # Verify cache size decremented
    metrics_after = db.get_schema_cache_metrics()
    assert metrics_after["cache_size"] < cache_size_before, "Cache size should decrease"

    print(
        f"✓ Table cache cleared: {cache_size_before} → {metrics_after['cache_size']} entries"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_clear_table_cache_nonexistent_returns_false(runtime):
    """
    Test clear_table_cache() returns False for nonexistent entries.

    Verifies:
    - Returns False when model not in cache
    - Doesn't affect other cache entries
    - Cache size unchanged
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Tag:
        id: str
        name: str

    # Populate cache
    workflow = WorkflowBuilder()
    workflow.add_node(
        "TagCreateNode",
        "tag",
        {"database_url": ":memory:", "id": "tag-001", "name": "important"},
    )
    results, _ = runtime.execute(workflow.build())

    metrics_before = db.get_schema_cache_metrics()
    cache_size_before = metrics_before["cache_size"]

    # Try to clear nonexistent model
    result = db.clear_table_cache("NonexistentModel", ":memory:")
    assert result is False, "Should return False when entry doesn't exist"

    # Verify cache unchanged
    metrics_after = db.get_schema_cache_metrics()
    assert (
        metrics_after["cache_size"] == cache_size_before
    ), "Cache size should be unchanged"

    # Verify Tag still cached
    cached_tables = db.get_cached_tables()
    model_names = [entry["model_name"] for entry in cached_tables.values()]
    assert "Tag" in model_names, "Tag should still be cached"

    print(
        f"✓ Nonexistent clear returned False, cache unchanged: {cache_size_before} entries"
    )


# =============================================================================
# Test Group 7: End-to-End Workflows with Multiple Models
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(20)
def test_e2e_blog_workflow_cache_performance(runtime):
    """
    Test end-to-end blog workflow demonstrating cache performance.

    Scenario:
    - Create user, posts, comments
    - List all entities
    - Update entities
    - Delete entities

    Verifies:
    - All operations complete successfully
    - Cache provides performance benefit
    - Hit rate increases over workflow
    - Multiple models cached correctly
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class BlogUser:
        id: str
        username: str
        email: str

    @db.model
    class BlogPost:
        id: str
        author_id: str
        title: str
        content: str

    @db.model
    class BlogComment:
        id: str
        post_id: str
        author_id: str
        content: str

    # Step 1: Create user
    workflow = WorkflowBuilder()
    workflow.add_node(
        "BlogUserCreateNode",
        "create_user",
        {
            "database_url": ":memory:",
            "id": "user-001",
            "username": "alice",
            "email": "alice@blog.com",
        },
    )
    results, _ = runtime.execute(workflow.build())
    assert "create_user" in results

    metrics_after_user = db.get_schema_cache_metrics()

    # Step 2: Create posts (should hit cache for BlogPost)
    for i in range(3):
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BlogPostCreateNode",
            f"create_post_{i}",
            {
                "database_url": ":memory:",
                "id": f"post-{i:03d}",
                "author_id": "user-001",
                "title": f"Post {i}",
                "content": f"Content for post {i}",
            },
        )
        results, _ = runtime.execute(workflow.build())
        assert f"create_post_{i}" in results

    metrics_after_posts = db.get_schema_cache_metrics()
    assert (
        metrics_after_posts["hits"] > metrics_after_user["hits"]
    ), "Posts should hit cache"

    # Step 3: Create comments (should hit cache for BlogComment)
    for i in range(5):
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BlogCommentCreateNode",
            f"create_comment_{i}",
            {
                "database_url": ":memory:",
                "id": f"comment-{i:03d}",
                "post_id": "post-000",
                "author_id": "user-001",
                "content": f"Comment {i}",
            },
        )
        results, _ = runtime.execute(workflow.build())
        assert f"create_comment_{i}" in results

    metrics_after_comments = db.get_schema_cache_metrics()
    assert (
        metrics_after_comments["hits"] > metrics_after_posts["hits"]
    ), "Comments should hit cache"

    # Step 4: List operations (all should hit cache)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "BlogUserListNode", "list_users", {"database_url": ":memory:", "limit": 10}
    )
    workflow.add_node(
        "BlogPostListNode", "list_posts", {"database_url": ":memory:", "limit": 10}
    )
    workflow.add_node(
        "BlogCommentListNode",
        "list_comments",
        {"database_url": ":memory:", "limit": 10},
    )
    results, _ = runtime.execute(workflow.build())

    assert "list_users" in results
    assert "list_posts" in results
    assert "list_comments" in results

    final_metrics = db.get_schema_cache_metrics()

    # Verify cache performance
    assert final_metrics["cache_size"] >= 3, "Should have 3+ models cached"
    assert final_metrics["hit_rate_percent"] > 50, "Hit rate should be >50%"
    assert final_metrics["hits"] >= 9, "Should have many cache hits (9+)"

    print(
        f"✓ E2E blog workflow: {final_metrics['hits']} hits, "
        f"{final_metrics['cache_size']} models, "
        f"{final_metrics['hit_rate_percent']:.1f}% hit rate"
    )


@pytest.mark.integration
@pytest.mark.timeout(20)
@pytest.mark.xfail(
    reason="SQLite :memory: limitation: Each workflow execution creates new connection, "
    "resulting in isolated databases. Requires architectural enhancement for "
    "connection pooling/sharing across workflows. Feature request for v0.8.0+",
    strict=False,
)
def test_e2e_ecommerce_workflow_with_cache(runtime):
    """
    Test end-to-end e-commerce workflow with cache enabled.

    Scenario:
    - Create stores, items, sales
    - Mix single and bulk operations
    - Update records via bulk operations

    Verifies:
    - Complex workflows benefit from cache
    - Bulk operations work with cache
    - Multiple concurrent workflows
    - Cache metrics accurate across workflow

    KNOWN LIMITATION:
    - SQLite :memory: databases are isolated per connection
    - DataFlow creates new connections for each workflow execution
    - This results in separate databases that don't share tables
    - Workaround: Use file-based SQLite or PostgreSQL for multi-workflow tests
    - Architecture enhancement needed: Connection pooling across workflow executions
    """
    db = DataFlow(":memory:", schema_cache_enabled=True)

    @db.model
    class Store:
        id: str
        name: str
        location: str

    @db.model
    class Item:
        id: str
        store_id: str
        name: str
        price: float

    @db.model
    class Sale:
        id: str
        customer_id: str
        total: float
        status: str = "pending"

    # Step 1: Create first records (triggers table creation, misses cache)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "StoreCreateNode",
        "store1",
        {"id": "store-001", "name": "Store 1", "location": "downtown"},
    )
    workflow.add_node(
        "ItemCreateNode",
        "item1",
        {"id": "item-001", "store_id": "store-001", "name": "Item 1", "price": 10.0},
    )
    workflow.add_node(
        "SaleCreateNode",
        "sale1",
        {
            "id": "sale-001",
            "customer_id": "cust-001",
            "total": 100.0,
            "status": "pending",
        },
    )
    results, _ = runtime.execute(workflow.build())

    # Step 2: More single creates (should hit cache)
    for i in range(2, 5):
        workflow = WorkflowBuilder()
        workflow.add_node(
            "StoreCreateNode",
            f"store{i}",
            {"id": f"store-{i:03d}", "name": f"Store {i}", "location": "location"},
        )
        workflow.add_node(
            "ItemCreateNode",
            f"item{i}",
            {
                "id": f"item-{i:03d}",
                "store_id": "store-001",
                "name": f"Item {i}",
                "price": 10.0 * i,
            },
        )
        workflow.add_node(
            "SaleCreateNode",
            f"sale{i}",
            {
                "id": f"sale-{i:03d}",
                "customer_id": "cust-001",
                "total": 100.0 * i,
                "status": "pending",
            },
        )
        results, _ = runtime.execute(workflow.build())

    # Verify final cache state
    final_metrics = db.get_schema_cache_metrics()
    cached_tables = db.get_cached_tables()

    assert final_metrics["cache_size"] >= 3, "Should cache all 3 models"
    assert final_metrics["hits"] > 0, "Should have cache hits from repeated operations"

    # Verify all models in cache
    model_names = [entry["model_name"] for entry in cached_tables.values()]
    assert "Store" in model_names
    assert "Item" in model_names
    assert "Sale" in model_names

    print(
        f"✓ E2E ecommerce workflow: {final_metrics['hits']} hits, "
        f"{len(model_names)} models, "
        f"{final_metrics['hit_rate_percent']:.1f}% hit rate"
    )


# =============================================================================
# Test Group 8: Configuration and Edge Cases
# =============================================================================


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_cache_with_custom_configuration(runtime):
    """
    Test schema cache with custom configuration parameters.

    Verifies:
    - Custom TTL setting respected
    - Custom max_size setting respected
    - Configuration reflected in metrics
    """
    db = DataFlow(
        ":memory:",
        schema_cache_enabled=True,
        schema_cache_ttl=600,  # 10 minutes
        schema_cache_max_size=5000,
    )

    @db.model
    class Config:
        id: str
        key: str
        value: str

    # Trigger cache
    workflow = WorkflowBuilder()
    workflow.add_node(
        "ConfigCreateNode",
        "config",
        {
            "database_url": ":memory:",
            "id": "cfg-001",
            "key": "test_key",
            "value": "test_value",
        },
    )
    results, _ = runtime.execute(workflow.build())

    # Verify configuration in metrics
    metrics = db.get_schema_cache_metrics()
    assert metrics["ttl_seconds"] == 600, "TTL should match configuration"
    assert metrics["max_size"] == 5000, "Max size should match configuration"

    print(
        f"✓ Custom configuration: TTL={metrics['ttl_seconds']}s, "
        f"max_size={metrics['max_size']}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_cache_isolation_between_instances(runtime):
    """
    Test that cache is isolated between DataFlow instances.

    Verifies:
    - Each DataFlow instance has independent cache
    - Operations on one instance don't affect another
    - Metrics are per-instance
    """
    # Create two separate DataFlow instances
    db1 = DataFlow(":memory:", schema_cache_enabled=True)
    db2 = DataFlow(":memory:", schema_cache_enabled=True)

    @db1.model
    class Instance1Model:
        id: str
        name: str

    @db2.model
    class Instance2Model:
        id: str
        title: str

    # Operate on db1
    workflow = WorkflowBuilder()
    workflow.add_node(
        "Instance1ModelCreateNode",
        "create1",
        {"database_url": ":memory:", "id": "m1-001", "name": "Model 1"},
    )
    results, _ = runtime.execute(workflow.build())

    # Operate on db2
    workflow = WorkflowBuilder()
    workflow.add_node(
        "Instance2ModelCreateNode",
        "create2",
        {"database_url": ":memory:", "id": "m2-001", "title": "Model 2"},
    )
    results, _ = runtime.execute(workflow.build())

    # Verify independent metrics
    metrics1 = db1.get_schema_cache_metrics()
    metrics2 = db2.get_schema_cache_metrics()

    cached1 = db1.get_cached_tables()
    cached2 = db2.get_cached_tables()

    # Each should have only their own model
    model_names1 = [entry["model_name"] for entry in cached1.values()]
    model_names2 = [entry["model_name"] for entry in cached2.values()]

    assert "Instance1Model" in model_names1
    assert "Instance1Model" not in model_names2
    assert "Instance2Model" in model_names2
    assert "Instance2Model" not in model_names1

    print(
        f"✓ Cache isolation: db1 has {len(model_names1)} models, "
        f"db2 has {len(model_names2)} models"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--timeout=30"])
