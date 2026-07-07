"""
E2E Tests: Startup Developer (Sarah) User Flows

Tests the complete experience of a startup developer using DataFlow
for rapid application development.
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List

import pytest

from dataflow import DataFlow

# Shared PostgreSQL test database (port 5434). Bare DataFlow() defaults to an
# ephemeral SQLite :memory: connection whose tables vanish across the
# multiple short-lived connections DataFlow opens; these e2e flows need a
# persistent backend so create → read → update spans one database.
_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.requires_docker
class TestStartupDeveloperZeroToFirstQuery:
    """
    Flow 1: Zero to First Query (5 minutes)

    A startup developer should be able to go from zero to executing
    their first database query in under 5 minutes.
    """

    def test_zero_config_initialization(self):
        """Test that DataFlow works with zero configuration."""
        start_time = time.time()

        # Step 1: Create DataFlow instance with zero config
        db = DataFlow()

        # Verify it initialized successfully
        assert db is not None
        assert db.config is not None
        assert db.config.environment is not None

        # Should use in-memory SQLite in development
        if db.config.environment.value == "development":
            assert (
                "sqlite"
                in db.config.database.get_connection_url(db.config.environment).lower()
            )

        elapsed = time.time() - start_time
        assert elapsed < 5.0, f"Initialization took {elapsed:.2f}s, should be < 5s"

    def test_first_model_definition(self):
        """Test defining the first model."""
        db = DataFlow()

        # Step 2: Define first model
        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        # Verify model was registered. db._models stores a metadata dict per
        # model; the class lives under the "class" key.
        assert "User" in db._models
        assert db._models["User"]["class"] == User

        # Verify CRUD nodes were generated (registered in db._nodes keyed by
        # the generated node-class name).
        for suffix in ("Create", "Read", "Update", "Delete", "List"):
            assert f"User{suffix}Node" in db._nodes

    @pytest.mark.asyncio
    async def test_first_crud_operations(self, clean_database):
        """Test executing first CRUD operations."""
        db = DataFlow(database_url=clean_database.config.database.url)
        runtime = LocalRuntime()

        # Define model. A unique __tablename__ isolates this test from other
        # test files sharing the model name "Product" on the shared database.
        @db.model
        class Product:
            __tablename__ = "e2e_crud_product"
            name: str
            price: float
            stock: int = 0

        await db.create_tables_async()

        # Step 3: Create first record. Create nodes return the flat persisted
        # record (with its primary key); there is no "status"/"output" wrapper.
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode",
            "create",
            {"name": "Laptop", "price": 999.99, "stock": 10},
        )

        results, run_id = await runtime.execute_async(workflow.build())

        product = results["create"]
        assert product["id"] is not None
        assert product["name"] == "Laptop"
        assert product["price"] == pytest.approx(999.99, abs=0.01)
        assert product["stock"] == 10

        # Step 4: Read the record back (state-persistence verification).
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductReadNode", "read", {"conditions": {"id": product["id"]}}
        )

        results, run_id = await runtime.execute_async(workflow.build())

        read_product = results["read"]
        assert read_product["found"] is True
        assert read_product["id"] == product["id"]
        assert read_product["name"] == "Laptop"

        # Step 5: List all records
        workflow = WorkflowBuilder()
        workflow.add_node("ProductListNode", "list", {"limit": 100})

        results, run_id = await runtime.execute_async(workflow.build())

        products = results["list"]["records"]
        assert len(products) >= 1
        assert any(p["name"] == "Laptop" for p in products)

    def test_complete_zero_to_query_time(self):
        """Test the complete flow completes in under 5 minutes."""
        start_time = time.time()

        # Simulate complete developer flow
        # 1. Initialize (persistent PostgreSQL so the table survives the
        #    create → query span; this is a sync test, so create_tables() is
        #    safe outside an event loop).
        db = DataFlow(database_url=_TEST_DB_URL)

        # 2. Define model (unique __tablename__ avoids colliding with the
        #    integration-suite "Task" model that maps to `tasks`).
        @db.model
        class Task:
            __tablename__ = "e2e_zero_task"
            title: str
            completed: bool = False
            priority: int = 1

        db.create_tables()

        # 3. Create runtime (context-managed for deterministic cleanup — the
        #    bare LocalRuntime().execute() form is deprecated).
        with LocalRuntime() as runtime:
            # 4. Create a task
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TaskCreateNode", "create", {"title": "Build MVP", "priority": 5}
            )

            results, _ = runtime.execute(workflow.build())
            assert results["create"]["id"] is not None

            # 5. Query tasks
            workflow = WorkflowBuilder()
            workflow.add_node(
                "TaskListNode",
                "list",
                {
                    "filter": {"completed": False},
                    "order_by": ["-priority"],
                    "limit": 100,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert isinstance(results["list"]["records"], list)

        elapsed = time.time() - start_time
        assert (
            elapsed < 300
        ), f"Complete flow took {elapsed:.2f}s, should be < 300s (5 min)"

        # Typically should be much faster
        print(f"Zero to first query completed in {elapsed:.2f} seconds")


@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.requires_docker
class TestStartupDeveloperBlogApplication:
    """
    Flow 2: Building a Blog Application

    A common use case for startup developers - building a blog
    with users, posts, comments, and basic features.
    """

    @pytest.mark.asyncio
    async def test_blog_models_and_relationships(self, clean_database):
        """Test creating blog models with relationships."""
        db = DataFlow()
        runtime = LocalRuntime()

        # Step 1: Define blog models
        @db.model
        class BlogUser:
            username: str
            email: str
            password_hash: str
            bio: str = ""
            verified: bool = False

        @db.model
        class BlogPost:
            author_id: int
            title: str
            slug: str
            content: str
            published: bool = False
            published_at: datetime = None
            views: int = 0

            __indexes__ = [
                {"name": "idx_slug", "fields": ["slug"], "unique": True},
                {"name": "idx_published", "fields": ["published", "published_at"]},
            ]

        @db.model
        class BlogComment:
            post_id: int
            author_id: int
            content: str
            approved: bool = True

            __indexes__ = [
                {"name": "idx_post_comments", "fields": ["post_id", "created_at"]},
            ]

        @db.model
        class BlogTag:
            name: str
            slug: str

            __indexes__ = [
                {"name": "idx_tag_slug", "fields": ["slug"], "unique": True},
            ]

        @db.model
        class PostTag:
            post_id: int
            tag_id: int

            __indexes__ = [
                {
                    "name": "idx_post_tags",
                    "fields": ["post_id", "tag_id"],
                    "unique": True,
                },
            ]

        # Verify all models registered
        assert all(
            model in db._models
            for model in ["BlogUser", "BlogPost", "BlogComment", "BlogTag", "PostTag"]
        )

    @pytest.mark.asyncio
    async def test_blog_user_authentication_workflow(self, clean_database):
        """Test user registration and authentication workflow."""
        db = DataFlow(database_url=clean_database.config.database.url)
        runtime = LocalRuntime(conditional_execution="skip_branches")

        @db.model
        class BlogUser:
            __tablename__ = "e2e_auth_blog_user"
            username: str
            email: str
            password_hash: str
            verified: bool = False
            last_login: datetime = None

        await db.create_tables_async()

        # Unique username per run keeps the login read-back isolated from rows
        # left by prior runs of the shared PostgreSQL test database.
        tok = str(int(time.time() * 1_000_000))
        username = f"startup_sarah_{tok}"
        password = "SecurePass123!"

        # Step 2: User registration workflow. PythonCodeNode receives connected
        # inputs / config values as local variables and returns its dict on the
        # `result` port (the current API — no inputs[]/outputs[] wrapper).
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "hash_password",
            {
                "code": """
import hashlib
result = {'password_hash': hashlib.sha256(password.encode()).hexdigest()}
""",
                "password": password,
            },
        )

        workflow.add_node(
            "BlogUserCreateNode",
            "create_user",
            {"username": username, "email": "sarah@startup.com"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "send_verification",
            {
                "code": """
result = {
    'email_sent': True,
    'verification_token': 'mock_token_' + str(user_id),
}
"""
            },
        )

        # Connect: hashed password -> create_user; new id -> send_verification.
        workflow.add_connection(
            "hash_password", "result.password_hash", "create_user", "password_hash"
        )
        workflow.add_connection("create_user", "id", "send_verification", "user_id")

        results, _ = await runtime.execute_async(workflow.build())

        user = results["create_user"]
        assert user["id"] is not None
        assert user["username"] == username
        assert user["verified"] is False
        assert results["send_verification"]["result"]["email_sent"] is True

        # Step 3: Login workflow. verify_password decides authenticated; a
        # boolean SwitchNode routes the success branch to update_login and the
        # failure branch to reject. skip_branches prunes the untaken branch.
        login_workflow = WorkflowBuilder()

        login_workflow.add_node(
            "BlogUserListNode",
            "find_user",
            {"filter": {"username": username}, "limit": 1},
        )

        login_workflow.add_node(
            "PythonCodeNode",
            "verify_password",
            {
                "code": """
import hashlib
if not records:
    result = {'authenticated': False, 'user_id': None}
else:
    user = records[0]
    computed = hashlib.sha256(password.encode()).hexdigest()
    ok = user['password_hash'] == computed
    result = {'authenticated': ok, 'user_id': user['id'] if ok else None}
""",
                "password": password,
            },
        )

        login_workflow.add_node(
            "SwitchNode",
            "decide",
            {"condition_field": "authenticated", "operator": "==", "value": True},
        )

        # Success branch: unpack the authenticated user id, then update.
        login_workflow.add_node(
            "PythonCodeNode",
            "approve",
            {"code": "result = {'id': input_data['user_id']}"},
        )
        login_workflow.add_node(
            "BlogUserUpdateNode",
            "update_login",
            {"last_login": datetime.now().isoformat()},
        )

        # Failure branch.
        login_workflow.add_node(
            "PythonCodeNode",
            "reject",
            {"code": "result = {'status': 'rejected'}"},
        )

        login_workflow.add_connection(
            "find_user", "records", "verify_password", "records"
        )
        login_workflow.add_connection(
            "verify_password", "result", "decide", "input_data"
        )
        login_workflow.add_connection("decide", "true_output", "approve", "input_data")
        login_workflow.add_connection("approve", "result.id", "update_login", "id")
        login_workflow.add_connection("decide", "false_output", "reject", "input_data")

        results, _ = await runtime.execute_async(login_workflow.build())

        assert results["verify_password"]["result"]["authenticated"] is True
        assert "update_login" in results
        assert results["update_login"]["id"] is not None
        assert results["update_login"]["last_login"] is not None

    @pytest.mark.asyncio
    async def test_blog_post_creation_and_publishing(self, clean_database):
        """Test creating and publishing blog posts."""
        db = DataFlow(database_url=clean_database.config.database.url)
        runtime = LocalRuntime()

        # Define models (unique table names isolate this test).
        @db.model
        class BlogUser:
            __tablename__ = "e2e_post_blog_user"
            username: str
            email: str

        @db.model
        class BlogPost:
            __tablename__ = "e2e_post_blog_post"
            author_id: int
            title: str
            slug: str
            content: str
            published: bool = False
            published_at: datetime = None
            views: int = 0

        await db.create_tables_async()

        # Create test user
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BlogUserCreateNode",
            "create_user",
            {"username": "blogger", "email": "blogger@example.com"},
        )

        results, _ = await runtime.execute_async(workflow.build())
        user_id = results["create_user"]["id"]

        # Step 4: Create blog post workflow
        post_workflow = WorkflowBuilder()

        # Generate slug from title (title supplied as node config).
        post_workflow.add_node(
            "PythonCodeNode",
            "generate_slug",
            {
                "code": """
slug = title.lower().replace(' ', '-').replace(',', '').replace('.', '')
result = {'slug': slug}
""",
                "title": "10 DataFlow Tips for Startups",
            },
        )

        # Create draft post; slug arrives from generate_slug via connection.
        post_workflow.add_node(
            "BlogPostCreateNode",
            "create_post",
            {
                "author_id": user_id,
                "title": "10 DataFlow Tips for Startups",
                "content": "Here are 10 tips for using DataFlow effectively...",
                "published": False,
            },
        )

        # Auto-save draft (post title arrives via connection).
        post_workflow.add_node(
            "PythonCodeNode",
            "auto_save_log",
            {
                "code": """
result = {'saved': True, 'message': f"Draft saved: {post_title}"}
"""
            },
        )

        # Connect workflow (4-positional; no template placeholders).
        post_workflow.add_connection(
            "generate_slug", "result.slug", "create_post", "slug"
        )
        post_workflow.add_connection(
            "create_post", "title", "auto_save_log", "post_title"
        )

        results, _ = await runtime.execute_async(post_workflow.build())

        post = results["create_post"]
        assert post["id"] is not None
        assert post["slug"] == "10-dataflow-tips-for-startups"
        assert post["published"] is False
        assert results["auto_save_log"]["result"]["saved"] is True

        # Step 5: Publish post workflow (filter + fields; id is a known value).
        publish_workflow = WorkflowBuilder()

        publish_workflow.add_node(
            "BlogPostUpdateNode",
            "publish",
            {
                "filter": {"id": post["id"]},
                "fields": {
                    "published": True,
                    "published_at": datetime.now().isoformat(),
                },
            },
        )

        # Notify subscribers (mock); post title arrives via connection.
        publish_workflow.add_node(
            "PythonCodeNode",
            "notify_subscribers",
            {
                "code": """
result = {'notifications_sent': 42, 'message': f"Notified about: {post_title}"}
"""
            },
        )

        publish_workflow.add_connection(
            "publish", "title", "notify_subscribers", "post_title"
        )

        results, _ = await runtime.execute_async(publish_workflow.build())

        published_post = results["publish"]
        assert published_post["id"] is not None
        assert published_post["published"] is True
        assert published_post["published_at"] is not None

    @pytest.mark.asyncio
    async def test_blog_search_functionality(self, clean_database):
        """Test blog search and filtering."""
        db = DataFlow(database_url=clean_database.config.database.url)
        runtime = LocalRuntime()

        # Setup models (unique table names isolate this test).
        @db.model
        class BlogUser:
            __tablename__ = "e2e_search_blog_user"
            username: str

        @db.model
        class BlogPost:
            __tablename__ = "e2e_search_blog_post"
            author_id: int
            title: str
            content: str
            published: bool = True
            tags: List[str] = []

        await db.create_tables_async()

        # Create test data. express.create returns the persisted record (with
        # its id on PostgreSQL); the fresh ids scope the search to this run.
        alice = await db.express.create("BlogUser", {"username": "alice"})
        bob = await db.express.create("BlogUser", {"username": "bob"})
        alice_id = alice["id"]
        bob_id = bob["id"]

        posts_data = [
            {
                "author_id": alice_id,
                "title": "Getting Started with DataFlow",
                "content": "DataFlow is a powerful database framework...",
                "tags": ["tutorial", "database", "python"],
            },
            {
                "author_id": alice_id,
                "title": "DataFlow Performance Optimization",
                "content": "Learn how to optimize DataFlow queries...",
                "tags": ["performance", "database", "advanced"],
            },
            {
                "author_id": bob_id,
                "title": "Building APIs with DataFlow",
                "content": "Create REST APIs using DataFlow and Kailash...",
                "tags": ["api", "tutorial", "web"],
            },
        ]
        for post_data in posts_data:
            await db.express.create("BlogPost", post_data)

        # Step 5: Search with the real $like operator (maps to SQL LIKE). The
        # search is run through db.express — express supports $like on string
        # columns, and the query is scoped to alice_id (unique per run) so it
        # is isolated from rows left by prior runs on the shared database.
        # (Tag search is intentionally omitted: $like is unsupported on the
        # JSONB tags column — `operator does not exist: jsonb ~~` — and
        # python-side filtering is disallowed.)
        title_results = await db.express.list(
            "BlogPost", {"author_id": alice_id, "title": {"$like": "%DataFlow%"}}
        )
        # Both of Alice's posts mention "DataFlow" in the title.
        assert len(title_results) == 2

        # Filter by author (equality): Alice authored 2 posts.
        author_results = await db.express.list(
            "BlogPost", {"author_id": alice_id, "published": True}
        )
        assert len(author_results) == 2

        # State-persistence read-back: re-read one matched post by id.
        first = await db.express.read("BlogPost", title_results[0]["id"])
        assert first is not None
        assert first["author_id"] == alice_id
        assert "DataFlow" in first["title"]


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestStartupDeveloperRealTimeFeatures:
    """
    Flow 3: Adding Real-time Features

    Testing real-time capabilities like notifications, WebSocket updates,
    and performance monitoring.
    """

    @pytest.mark.asyncio
    async def test_event_monitoring_setup(self, clean_database):
        """Test setting up event monitoring for real-time features."""
        db = DataFlow(database_url=clean_database.config.database.url, monitoring=True)
        runtime = LocalRuntime()

        @db.model
        class Notification:
            __tablename__ = "e2e_notification"
            user_id: int
            type: str
            title: str
            message: str
            read: bool = False

        await db.create_tables_async()

        # Create notification workflow with monitoring
        workflow = WorkflowBuilder()

        # Create notification
        workflow.add_node(
            "NotificationCreateNode",
            "create_notif",
            {
                "user_id": 1,
                "type": "comment",
                "title": "New Comment",
                "message": "Someone commented on your post",
            },
        )

        # Monitor for high-priority notifications (notif type arrives via
        # connection as a local variable).
        workflow.add_node(
            "PythonCodeNode",
            "check_priority",
            {
                "code": """
is_priority = notif_type in ['mention', 'urgent', 'security']
result = {'is_priority': is_priority, 'should_push': is_priority}
"""
            },
        )

        workflow.add_connection("create_notif", "type", "check_priority", "notif_type")

        results, _ = await runtime.execute_async(workflow.build())

        assert results["create_notif"]["id"] is not None
        assert results["check_priority"]["result"]["is_priority"] is False

    @pytest.mark.asyncio
    async def test_caching_layer_integration(self, clean_database):
        """Test caching for improved performance."""
        # Query caching is enabled via cache_enabled (the real kwarg;
        # enable_query_cache is not a DataFlow parameter). Point at the
        # fixture's PostgreSQL so the table persists across reads.
        db = DataFlow(
            database_url=clean_database.config.database.url,
            cache_enabled=True,
            cache_ttl=60,
        )
        runtime = LocalRuntime()

        @db.model
        class CachedData:
            __tablename__ = "e2e_cached_data"
            key: str
            value: str
            access_count: int = 0

        await db.create_tables_async()

        # Create cacheable data
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CachedDataCreateNode",
            "create",
            {
                "key": "api_config",
                "value": '{"version": "1.0", "features": ["cache", "monitor"]}',
            },
        )

        results, _ = await runtime.execute_async(workflow.build())
        data_id = results["create"]["id"]

        # Test cache hit scenario
        read_workflow = WorkflowBuilder()

        # First read (cache miss)
        read_workflow.add_node(
            "CachedDataReadNode", "read1", {"conditions": {"id": data_id}}
        )

        # Second read (should be a cache hit)
        read_workflow.add_node(
            "CachedDataReadNode", "read2", {"conditions": {"id": data_id}}
        )

        # Update access count (ordered after both reads via connections).
        read_workflow.add_node(
            "CachedDataUpdateNode",
            "update_count",
            {"filter": {"id": data_id}, "fields": {"access_count": 2}},
        )

        read_workflow.add_connection("read1", "id", "update_count", "after_read1")
        read_workflow.add_connection("read2", "id", "update_count", "after_read2")

        start = time.time()
        results, _ = await runtime.execute_async(read_workflow.build())
        elapsed = time.time() - start

        # Both reads should succeed (return the flat record with `found`).
        assert results["read1"]["found"] is True
        assert results["read2"]["found"] is True
        assert results["read1"]["id"] == data_id

        # State-persistence read-back: the update landed.
        assert results["update_count"]["access_count"] == 2

        print(f"Read operations completed in {elapsed:.3f}s")

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, clean_database):
        """Test performance monitoring capabilities."""
        # Use the fixture-provided (PostgreSQL) URL so the bulk write and the
        # read-back share a real database rather than an ephemeral SQLite
        # :memory: connection.
        db = DataFlow(
            database_url=clean_database.config.database.url,
            monitoring=True,
            slow_query_threshold=0.1,  # 100ms threshold for testing
        )
        runtime = LocalRuntime()

        @db.model
        class MetricsData:
            metric_name: str
            value: float
            timestamp: datetime

        await db.create_tables_async()

        # Real monitoring surface: inspect the connection pool. The old
        # monitor-nodes accessor was removed; monitoring is monitoring=True +
        # the connection-pool inspection API (get_connection_pool /
        # get_health_status / get_metrics).
        pool = db.get_connection_pool()
        health = await pool.get_health_status()
        assert health["status"] == "healthy"

        tok = str(int(time.time() * 1_000_000))

        # Create workflow with monitoring
        workflow = WorkflowBuilder()

        # Bulk insert metrics (the heavier / potentially slow operation).
        metrics = [
            {
                "metric_name": f"cpu_usage_{tok}_{i}",
                "value": 50.0 + i * 0.1,
                "timestamp": datetime.now().isoformat(),
            }
            for i in range(100)
        ]
        workflow.add_node("MetricsDataBulkCreateNode", "bulk_insert", {"data": metrics})

        # Read the metrics back (a query pattern exercised under monitoring).
        workflow.add_node(
            "MetricsDataListNode",
            "aggregate",
            {"filter": {"metric_name": f"cpu_usage_{tok}_0"}, "limit": 10},
        )
        # Order the read after the bulk write so it sees the committed rows.
        workflow.add_connection("bulk_insert", "inserted", "aggregate", "after_bulk")

        results, _ = await runtime.execute_async(workflow.build())

        # Verify operations completed.
        assert results["bulk_insert"]["success"] is True
        assert results["bulk_insert"]["inserted"] == 100
        # State-persistence read-back: the first metric is queryable.
        assert results["aggregate"]["count"] == 1

        # Monitoring surface: pool metrics are available for the operator.
        pool_metrics = await pool.get_metrics()
        assert pool_metrics["total_connections"] == pool.max_connections
        print("Performance monitoring active - slow queries would be logged")
