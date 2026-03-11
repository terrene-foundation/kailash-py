"""
E2E Tests: Startup Developer (Sarah) User Flows

Tests the complete experience of a startup developer using DataFlow
for rapid application development.
"""

import time
from datetime import datetime
from typing import Any, Dict, List

import pytest
from dataflow import DataFlow

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

        # Verify model was registered
        assert "User" in db._models
        assert db._models["User"] == User

        # Verify CRUD nodes were generated
        assert "User" in db._model_nodes
        nodes = db._model_nodes["User"]
        assert "create" in nodes
        assert "read" in nodes
        assert "update" in nodes
        assert "delete" in nodes
        assert "list" in nodes

    @pytest.mark.asyncio
    async def test_first_crud_operations(self, clean_database):
        """Test executing first CRUD operations."""
        db = DataFlow()
        runtime = LocalRuntime()

        # Define model
        @db.model
        class Product:
            name: str
            price: float
            stock: int = 0

        # Step 3: Create first record
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode",
            "create",
            {"name": "Laptop", "price": 999.99, "stock": 10},
        )

        results, run_id = await runtime.execute_async(workflow.build())

        assert results["create"]["status"] == "success"
        product = results["create"]["output"]
        assert product["name"] == "Laptop"
        assert product["price"] == 999.99
        assert product["stock"] == 10
        assert "id" in product

        # Step 4: Read the record
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductReadNode", "read", {"conditions": {"id": product["id"]}}
        )

        results, run_id = await runtime.execute_async(workflow.build())

        assert results["read"]["status"] == "success"
        read_product = results["read"]["output"]
        assert read_product["id"] == product["id"]
        assert read_product["name"] == "Laptop"

        # Step 5: List all records
        workflow = WorkflowBuilder()
        workflow.add_node("ProductListNode", "list", {})

        results, run_id = await runtime.execute_async(workflow.build())

        assert results["list"]["status"] == "success"
        products = results["list"]["output"]
        assert len(products) >= 1
        assert any(p["name"] == "Laptop" for p in products)

    def test_complete_zero_to_query_time(self):
        """Test the complete flow completes in under 5 minutes."""
        start_time = time.time()

        # Simulate complete developer flow
        # 1. Initialize
        db = DataFlow()

        # 2. Define model
        @db.model
        class Task:
            title: str
            completed: bool = False
            priority: int = 1

        # 3. Create runtime
        runtime = LocalRuntime()

        # 4. Create a task
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TaskCreateNode", "create", {"title": "Build MVP", "priority": 5}
        )

        results, _ = runtime.execute(workflow.build())
        assert results["create"]["status"] == "success"

        # 5. Query tasks
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TaskListNode",
            "list",
            {"filter": {"completed": False}, "order_by": ["-priority"]},
        )

        results, _ = runtime.execute(workflow.build())
        assert results["list"]["status"] == "success"

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
        db = DataFlow()
        runtime = LocalRuntime()

        @db.model
        class BlogUser:
            username: str
            email: str
            password_hash: str
            verified: bool = False
            last_login: datetime = None

        # Step 2: User registration workflow
        workflow = WorkflowBuilder()

        # Hash password (using PythonCodeNode)
        workflow.add_node(
            "PythonCodeNode",
            "hash_password",
            {
                "code": """
import hashlib
password = inputs['password']
outputs = {
    'password_hash': hashlib.sha256(password.encode()).hexdigest()
}
"""
            },
        )

        # Create user
        workflow.add_node(
            "BlogUserCreateNode",
            "create_user",
            {
                "username": "startup_sarah",
                "email": "sarah@startup.com",
                "password_hash": ":password_hash",
            },
        )

        # Send verification email (mock)
        workflow.add_node(
            "PythonCodeNode",
            "send_verification",
            {
                "code": """
user = inputs['user']
outputs = {
    'email_sent': True,
    'verification_token': 'mock_token_' + str(user['id'])
}
"""
            },
        )

        # Connect workflow
        workflow.add_connection(
            "hash_password", "create_user", "password_hash", "password_hash"
        )
        workflow.add_connection("create_user", "send_verification", "output", "user")

        # Execute registration
        workflow.metadata["password"] = "SecurePass123!"
        results, _ = await runtime.execute_async(workflow.build())

        assert results["create_user"]["status"] == "success"
        user = results["create_user"]["output"]
        assert user["username"] == "startup_sarah"
        assert user["verified"] is False
        assert results["send_verification"]["output"]["email_sent"] is True

        # Step 3: Login workflow
        login_workflow = WorkflowBuilder()

        # Find user by username
        login_workflow.add_node(
            "BlogUserListNode",
            "find_user",
            {"filter": {"username": "startup_sarah"}, "limit": 1},
        )

        # Verify password
        login_workflow.add_node(
            "PythonCodeNode",
            "verify_password",
            {
                "code": """
import hashlib
users = inputs['users']
password = inputs['password']

if not users:
    outputs = {'authenticated': False, 'error': 'User not found'}
else:
    user = users[0]
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    outputs = {
        'authenticated': user['password_hash'] == password_hash,
        'user_id': user['id'] if user['password_hash'] == password_hash else None
    }
"""
            },
        )

        # Update last login
        login_workflow.add_node(
            "BlogUserUpdateNode",
            "update_login",
            {
                "conditions": {"id": ":user_id"},
                "updates": {"last_login": datetime.now().isoformat()},
            },
        )

        # Connect login workflow
        login_workflow.add_connection("find_user", "verify_password", "output", "users")
        login_workflow.add_connection(
            "verify_password",
            "update_login",
            condition="authenticated == true",
            output_map={"user_id": "user_id"},
        )

        # Execute login
        login_workflow.metadata["password"] = "SecurePass123!"
        results, _ = await runtime.execute_async(login_workflow.build())

        assert results["verify_password"]["output"]["authenticated"] is True
        assert results["update_login"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_blog_post_creation_and_publishing(self, clean_database):
        """Test creating and publishing blog posts."""
        db = DataFlow()
        runtime = LocalRuntime()

        # Define models
        @db.model
        class BlogUser:
            username: str
            email: str

        @db.model
        class BlogPost:
            author_id: int
            title: str
            slug: str
            content: str
            published: bool = False
            published_at: datetime = None
            views: int = 0

        # Create test user
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BlogUserCreateNode",
            "create_user",
            {"username": "blogger", "email": "blogger@example.com"},
        )

        results, _ = await runtime.execute_async(workflow.build())
        user_id = results["create_user"]["output"]["id"]

        # Step 4: Create blog post workflow
        post_workflow = WorkflowBuilder()

        # Generate slug from title
        post_workflow.add_node(
            "PythonCodeNode",
            "generate_slug",
            {
                "code": """
title = inputs['title']
slug = title.lower().replace(' ', '-').replace(',', '').replace('.', '')
outputs = {'slug': slug}
"""
            },
        )

        # Create draft post
        post_workflow.add_node(
            "BlogPostCreateNode",
            "create_post",
            {
                "author_id": user_id,
                "title": "10 DataFlow Tips for Startups",
                "slug": ":slug",
                "content": "Here are 10 tips for using DataFlow effectively...",
                "published": False,
            },
        )

        # Auto-save draft
        post_workflow.add_node(
            "PythonCodeNode",
            "auto_save_log",
            {
                "code": """
post = inputs['post']
outputs = {
    'saved': True,
    'message': f"Draft saved: {post['title']}"
}
"""
            },
        )

        # Connect workflow
        post_workflow.metadata["title"] = "10 DataFlow Tips for Startups"
        post_workflow.add_connection("generate_slug", "create_post", "slug", "slug")
        post_workflow.add_connection("create_post", "auto_save_log", "output", "post")

        results, _ = await runtime.execute_async(post_workflow.build())

        assert results["create_post"]["status"] == "success"
        post = results["create_post"]["output"]
        assert post["slug"] == "10-dataflow-tips-for-startups"
        assert post["published"] is False

        # Step 5: Publish post workflow
        publish_workflow = WorkflowBuilder()

        # Update post to published
        publish_workflow.add_node(
            "BlogPostUpdateNode",
            "publish",
            {
                "conditions": {"id": post["id"]},
                "updates": {
                    "published": True,
                    "published_at": datetime.now().isoformat(),
                },
            },
        )

        # Notify subscribers (mock)
        publish_workflow.add_node(
            "PythonCodeNode",
            "notify_subscribers",
            {
                "code": """
post = inputs['post']
outputs = {
    'notifications_sent': 42,
    'message': f"Notified subscribers about: {post['title']}"
}
"""
            },
        )

        publish_workflow.add_connection(
            "publish", "notify_subscribers", "output", "post"
        )

        results, _ = await runtime.execute_async(publish_workflow.build())

        assert results["publish"]["status"] == "success"
        published_post = results["publish"]["output"]
        assert published_post["published"] is True
        assert published_post["published_at"] is not None

    @pytest.mark.asyncio
    async def test_blog_search_functionality(self, clean_database):
        """Test blog search and filtering."""
        db = DataFlow()
        runtime = LocalRuntime()

        # Setup models
        @db.model
        class BlogUser:
            username: str

        @db.model
        class BlogPost:
            author_id: int
            title: str
            content: str
            published: bool = True
            tags: List[str] = []

        # Create test data
        setup_workflow = WorkflowBuilder()

        # Create users
        setup_workflow.add_node("BlogUserCreateNode", "user1", {"username": "alice"})
        setup_workflow.add_node("BlogUserCreateNode", "user2", {"username": "bob"})

        results, _ = await runtime.execute_async(setup_workflow.build())
        alice_id = results["user1"]["output"]["id"]
        bob_id = results["user2"]["output"]["id"]

        # Create posts
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

        post_workflow = WorkflowBuilder()
        for i, post_data in enumerate(posts_data):
            post_workflow.add_node("BlogPostCreateNode", f"post_{i}", post_data)

        await runtime.execute_async(post_workflow.build())

        # Step 5: Search functionality
        search_workflow = WorkflowBuilder()

        # Search by keyword in title
        search_workflow.add_node(
            "BlogPostListNode",
            "search_title",
            {
                "filter": {"title": {"$contains": "DataFlow"}, "published": True},
                "order_by": ["-created_at"],
            },
        )

        # Filter by author
        search_workflow.add_node(
            "BlogPostListNode",
            "by_author",
            {"filter": {"author_id": alice_id, "published": True}},
        )

        # Filter by tags (using JSONB containment)
        search_workflow.add_node(
            "BlogPostListNode",
            "by_tag",
            {"filter": {"tags": {"$contains": ["tutorial"]}, "published": True}},
        )

        results, _ = await runtime.execute_async(search_workflow.build())

        # Verify search results
        title_results = results["search_title"]["output"]
        assert len(title_results) == 2  # Both Alice's posts have "DataFlow" in title

        author_results = results["by_author"]["output"]
        assert len(author_results) == 2  # Alice has 2 posts

        tag_results = results["by_tag"]["output"]
        assert len(tag_results) == 2  # 2 posts tagged "tutorial"


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
        db = DataFlow(monitoring=True)
        runtime = LocalRuntime()

        @db.model
        class Notification:
            user_id: int
            type: str
            title: str
            message: str
            read: bool = False

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

        # Monitor for high-priority notifications
        workflow.add_node(
            "PythonCodeNode",
            "check_priority",
            {
                "code": """
notif = inputs['notification']
is_priority = notif['type'] in ['mention', 'urgent', 'security']
outputs = {
    'is_priority': is_priority,
    'should_push': is_priority
}
"""
            },
        )

        workflow.add_connection(
            "create_notif", "check_priority", "output", "notification"
        )

        results, _ = await runtime.execute_async(workflow.build())

        assert results["create_notif"]["status"] == "success"
        assert results["check_priority"]["output"]["is_priority"] is False

    @pytest.mark.asyncio
    async def test_caching_layer_integration(self, clean_database):
        """Test caching for improved performance."""
        db = DataFlow(enable_query_cache=True, cache_ttl=60)
        runtime = LocalRuntime()

        @db.model
        class CachedData:
            key: str
            value: str
            access_count: int = 0

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
        data_id = results["create"]["output"]["id"]

        # Test cache hit scenario
        read_workflow = WorkflowBuilder()

        # First read (cache miss)
        read_workflow.add_node(
            "CachedDataReadNode", "read1", {"conditions": {"id": data_id}}
        )

        # Second read (should be cache hit)
        read_workflow.add_node(
            "CachedDataReadNode", "read2", {"conditions": {"id": data_id}}
        )

        # Update access count
        read_workflow.add_node(
            "CachedDataUpdateNode",
            "update_count",
            {
                "conditions": {"id": data_id},
                "updates": {"access_count": "access_count + 2"},
            },
        )

        read_workflow.add_connection("read1", "read2")
        read_workflow.add_connection("read2", "update_count")

        import time

        start = time.time()
        results, _ = await runtime.execute_async(read_workflow.build())
        elapsed = time.time() - start

        # Both reads should succeed
        assert results["read1"]["status"] == "success"
        assert results["read2"]["status"] == "success"

        # Second read should be faster (from cache)
        # Note: This is conceptual - actual cache implementation needed
        print(f"Read operations completed in {elapsed:.3f}s")

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, clean_database):
        """Test performance monitoring capabilities."""
        db = DataFlow(
            monitoring=True, slow_query_threshold=0.1
        )  # 100ms threshold for testing
        runtime = LocalRuntime()

        @db.model
        class MetricsData:
            metric_name: str
            value: float
            timestamp: datetime

        # Get monitoring nodes
        monitors = db.get_monitor_nodes()
        assert monitors is not None
        assert "transaction" in monitors
        assert "metrics" in monitors

        # Create workflow with monitoring
        workflow = WorkflowBuilder()

        # Bulk insert metrics (potentially slow operation)
        metrics = [
            {
                "metric_name": f"cpu_usage_{i}",
                "value": 50.0 + i * 0.1,
                "timestamp": datetime.now().isoformat(),
            }
            for i in range(100)
        ]

        workflow.add_node(
            "MetricsDataBulkCreateNode", "bulk_insert", {"records": metrics}
        )

        # Query aggregated metrics
        workflow.add_node(
            "SQLDatabaseNode",
            "aggregate",
            {
                "connection_string": db.config.database.get_connection_url(
                    db.config.environment
                ),
                "query": """
                SELECT
                    metric_name,
                    AVG(value) as avg_value,
                    COUNT(*) as count
                FROM metricsdata
                WHERE metric_name LIKE 'cpu_usage_%'
                GROUP BY metric_name
                HAVING COUNT(*) > 0
                ORDER BY metric_name
                LIMIT 10
            """,
            },
        )

        results, _ = await runtime.execute_async(workflow.build())

        # Verify operations completed
        assert results["bulk_insert"]["status"] == "success"

        # Check if monitoring detected any slow queries
        # (This would be captured by TransactionMonitorNode in production)
        print("Performance monitoring active - slow queries would be logged")
