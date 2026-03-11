"""
E2E Tests: Startup Developer (Sarah) - Complete Blog Application

End-to-end test for building a complete blog application with DataFlow.
This represents a realistic startup MVP that Sarah would build.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from dataflow import DataFlow, DataFlowConfig

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestBlogApplicationE2E:
    """Complete blog application E2E test - startup developer scenario."""

    @pytest.fixture
    async def blog_dataflow(self):
        """DataFlow instance configured for blog application."""
        import os

        import asyncpg

        database_url = os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

        # Clean up any existing blog tables before test
        conn = await asyncpg.connect(database_url)
        try:
            # Drop all blog-related tables to ensure clean state
            tables_to_drop = [
                "blog_posts",
                "blog_users",
                "categories",
                "tags",
                "comments",
                "post_tags",
                "blog_settings",
            ]
            for table in tables_to_drop:
                await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        finally:
            await conn.close()

        config = DataFlowConfig(
            database_url=database_url,
            enable_monitoring=True,
            enable_relationships=True,
        )
        db = DataFlow(config=config)

        # Initialize database and create tables
        await db.initialize()

        yield db

        # Cleanup - close connections properly
        try:
            if hasattr(db, "close"):
                if asyncio.iscoroutinefunction(db.close):
                    await db.close()
                else:
                    db.close()
        except Exception:
            pass
        # Close handled in yield section above

    @pytest.mark.asyncio
    async def test_complete_blog_application_flow(self, blog_dataflow):
        """Test complete blog application from user registration to content publishing."""
        db = blog_dataflow

        # PHASE 1: Define the complete blog data model
        print("📝 Phase 1: Defining blog data models...")

        @db.model
        class BlogUser:
            username: str
            email: str
            password_hash: str
            display_name: str
            bio: str = ""
            avatar_url: str = ""
            is_active: bool = True
            is_verified: bool = False
            created_at: datetime = None
            last_login: datetime = None

            def validate_email(self, email: str) -> str:
                if "@" not in email or "." not in email:
                    raise ValueError("Please provide a valid email address")
                return email.lower()

            def validate_username(self, username: str) -> str:
                if len(username) < 3:
                    raise ValueError("Username must be at least 3 characters")
                if not username.isalnum():
                    raise ValueError("Username must contain only letters and numbers")
                return username.lower()

        @db.model
        class Category:
            name: str
            slug: str
            description: str = ""
            color: str = "#3B82F6"  # Default blue
            post_count: int = 0
            created_at: datetime = None

        @db.model
        class BlogPost:
            title: str
            slug: str
            content: str
            excerpt: str = ""
            featured_image: str = ""
            author_id: int
            category_id: int
            status: str = "draft"  # draft, published, archived
            is_featured: bool = False
            view_count: int = 0
            like_count: int = 0
            published_at: datetime = None
            created_at: datetime = None
            updated_at: datetime = None

            def validate_title(self, title: str) -> str:
                if len(title) < 5:
                    raise ValueError("Post title must be at least 5 characters")
                return title

            def validate_status(self, status: str) -> str:
                valid_statuses = ["draft", "published", "archived"]
                if status not in valid_statuses:
                    raise ValueError(
                        f"Status must be one of: {', '.join(valid_statuses)}"
                    )
                return status

        @db.model
        class Comment:
            content: str
            author_id: int
            post_id: int
            parent_comment_id: int = None  # For threaded comments
            is_approved: bool = True
            like_count: int = 0
            created_at: datetime = None

            def validate_content(self, content: str) -> str:
                if len(content.strip()) < 3:
                    raise ValueError("Comment must be at least 3 characters")
                return content.strip()

        @db.model
        class Tag:
            name: str
            slug: str
            usage_count: int = 0
            created_at: datetime = None

        @db.model
        class PostTag:
            post_id: int
            tag_id: int
            created_at: datetime = None

        print("✅ Phase 1 Complete: Blog models defined")

        # PHASE 2: User Registration and Authentication
        print("🔐 Phase 2: User registration and authentication...")

        user_registration_workflow = WorkflowBuilder()

        # Register blog author
        user_registration_workflow.add_node(
            "BlogUserCreateNode",
            "register_author",
            {
                "username": "sarahstartup",
                "email": "sarah@startup.com",
                "password_hash": "hashed_password_123",
                "display_name": "Sarah Startup",
                "bio": "Entrepreneur and tech enthusiast building the next big thing!",
                "is_active": True,
            },
        )

        # Register a commenter
        user_registration_workflow.add_node(
            "BlogUserCreateNode",
            "register_commenter",
            {
                "username": "johnreader",
                "email": "john@reader.com",
                "password_hash": "hashed_password_456",
                "display_name": "John Reader",
                "bio": "Avid reader and tech follower",
                "is_active": True,
            },
        )

        runtime = LocalRuntime()
        user_results, _ = runtime.execute(user_registration_workflow.build())

        author = user_results["register_author"]
        commenter = user_results["register_commenter"]

        assert author["username"] == "sarahstartup"
        assert author["email"] == "sarah@startup.com"
        assert commenter["username"] == "johnreader"

        print(f"✅ Phase 2 Complete: Registered {len(user_results)} users")

        # PHASE 3: Content Organization Setup
        print("📂 Phase 3: Setting up categories and tags...")

        content_setup_workflow = WorkflowBuilder()

        # Create categories
        categories = [
            {
                "name": "Technology",
                "slug": "technology",
                "description": "Latest tech trends and insights",
                "color": "#3B82F6",
            },
            {
                "name": "Startup Life",
                "slug": "startup-life",
                "description": "The entrepreneurial journey",
                "color": "#10B981",
            },
            {
                "name": "Product Development",
                "slug": "product-dev",
                "description": "Building great products",
                "color": "#F59E0B",
            },
        ]

        for i, cat in enumerate(categories):
            content_setup_workflow.add_node(
                "CategoryCreateNode", f"create_category_{i}", cat
            )

        # Create tags
        tags = [
            {"name": "React", "slug": "react"},
            {"name": "Python", "slug": "python"},
            {"name": "DataFlow", "slug": "dataflow"},
            {"name": "MVP", "slug": "mvp"},
            {"name": "Fundraising", "slug": "fundraising"},
        ]

        for i, tag in enumerate(tags):
            content_setup_workflow.add_node("TagCreateNode", f"create_tag_{i}", tag)

        content_results, _ = runtime.execute(content_setup_workflow.build())

        # Get created categories and tags
        tech_category = content_results["create_category_0"]
        startup_category = content_results["create_category_1"]
        product_category = content_results["create_category_2"]

        dataflow_tag = content_results["create_tag_2"]  # DataFlow tag
        python_tag = content_results["create_tag_1"]  # Python tag

        print(
            f"✅ Phase 3 Complete: Created {len(categories)} categories and {len(tags)} tags"
        )

        # PHASE 4: Blog Post Creation and Publishing
        print("📝 Phase 4: Creating and publishing blog posts...")

        blog_publishing_workflow = WorkflowBuilder()

        # Create multiple blog posts
        blog_posts = [
            {
                "title": "Getting Started with DataFlow: A Startup's Journey",
                "slug": "getting-started-dataflow-startup",
                "content": """
# Getting Started with DataFlow: A Startup's Journey

As a startup founder, I'm always looking for tools that can help us move fast without compromising on quality.
That's when I discovered DataFlow - a game-changing framework that makes database operations incredibly intuitive.

## Why DataFlow?

1. **Zero Configuration**: We were up and running in minutes
2. **Type Safety**: Fewer bugs in production
3. **Workflow Integration**: Perfect for our automation needs
4. **Enterprise Ready**: Scales with our growth

## Our Experience

Within just a few hours, we had:
- Defined our data models
- Created complex workflows
- Implemented real-time features
- Deployed to production

The learning curve was almost non-existent, which was crucial for our small team.

## Next Steps

We're planning to explore DataFlow's advanced features like multi-tenancy and bulk operations
as we scale our user base.

What has your experience been with DataFlow? Let me know in the comments!
                """,
                "excerpt": "Our startup's experience getting up and running with DataFlow in record time.",
                "category_id": tech_category["id"],
                "author_id": author["id"],
                "status": "published",
                "is_featured": True,
                "published_at": datetime.now(),
            },
            {
                "title": "5 Lessons Learned Building Our MVP",
                "slug": "5-lessons-learned-building-mvp",
                "content": """
# 5 Lessons Learned Building Our MVP

Building our first MVP taught us invaluable lessons about product development, user feedback, and iteration cycles.

## Lesson 1: Start Even Smaller
We thought we started small, but we could have started even smaller...

## Lesson 2: User Feedback is Gold
Early user feedback shaped our product in ways we never expected...

## Lesson 3: Technical Debt is Real
Choose your tools wisely from the beginning...

## Lesson 4: Performance Matters
Users notice slow applications immediately...

## Lesson 5: Monitoring is Essential
You can't improve what you don't measure...
                """,
                "excerpt": "Key insights from our MVP development journey.",
                "category_id": startup_category["id"],
                "author_id": author["id"],
                "status": "published",
                "is_featured": False,
                "published_at": datetime.now(),
            },
            {
                "title": "Database Design Patterns for Modern Apps",
                "slug": "database-design-patterns-modern-apps",
                "content": """
# Database Design Patterns for Modern Apps

Modern applications require thoughtful database design. Here are the patterns we use...
                """,
                "excerpt": "Essential database design patterns every developer should know.",
                "category_id": product_category["id"],
                "author_id": author["id"],
                "status": "draft",  # This one is still a draft
            },
        ]

        for i, post in enumerate(blog_posts):
            blog_publishing_workflow.add_node(
                "BlogPostCreateNode", f"create_post_{i}", post
            )

        post_results, _ = runtime.execute(blog_publishing_workflow.build())

        published_post_1 = post_results["create_post_0"]
        published_post_2 = post_results["create_post_1"]
        draft_post = post_results["create_post_2"]

        assert published_post_1["status"] == "published"
        assert published_post_1["is_featured"] is True
        assert published_post_2["status"] == "published"
        assert draft_post["status"] == "draft"

        print(f"✅ Phase 4 Complete: Created {len(blog_posts)} blog posts")

        # PHASE 5: Tag Assignment
        print("🏷️ Phase 5: Assigning tags to posts...")

        tagging_workflow = WorkflowBuilder()

        # Tag the DataFlow post
        tagging_workflow.add_node(
            "PostTagCreateNode",
            "tag_dataflow_post_1",
            {"post_id": published_post_1["id"], "tag_id": dataflow_tag["id"]},
        )

        tagging_workflow.add_node(
            "PostTagCreateNode",
            "tag_dataflow_post_2",
            {"post_id": published_post_1["id"], "tag_id": python_tag["id"]},
        )

        tag_results, _ = runtime.execute(tagging_workflow.build())

        print("✅ Phase 5 Complete: Tagged posts")

        # PHASE 6: Community Engagement - Comments
        print("💬 Phase 6: Community engagement through comments...")

        commenting_workflow = WorkflowBuilder()

        # Add comments to the featured post
        comments = [
            {
                "content": "Great post! I've been looking for something like DataFlow for our startup too. How was the learning curve?",
                "author_id": commenter["id"],
                "post_id": published_post_1["id"],
                "is_approved": True,
            },
            {
                "content": "Thanks for sharing your experience! The zero-config aspect sounds amazing. We spend way too much time on database setup.",
                "author_id": commenter["id"],
                "post_id": published_post_1["id"],
                "is_approved": True,
            },
        ]

        for i, comment in enumerate(comments):
            commenting_workflow.add_node(
                "CommentCreateNode", f"create_comment_{i}", comment
            )

        # Author replies to first comment (threaded)
        commenting_workflow.add_node(
            "CommentCreateNode",
            "author_reply",
            {
                "content": "The learning curve was surprisingly gentle! We were productive within hours. Happy to answer any specific questions!",
                "author_id": author["id"],
                "post_id": published_post_1["id"],
                "is_approved": True,
                # parent_comment_id will be set via connection from create_comment_0
            },
        )

        # Connect reply to parent comment
        commenting_workflow.add_connection(
            "create_comment_0", "id", "author_reply", "parent_comment_id"
        )

        comment_results, _ = runtime.execute(commenting_workflow.build())

        comment_1 = comment_results["create_comment_0"]
        comment_2 = comment_results["create_comment_1"]
        author_reply = comment_results["author_reply"]

        assert comment_1["post_id"] == published_post_1["id"]
        assert author_reply["parent_comment_id"] == comment_1["id"]  # Threaded comment

        print(f"✅ Phase 6 Complete: Added {len(comment_results)} comments")

        # PHASE 7: Content Discovery and Search
        print("🔍 Phase 7: Testing content discovery features...")

        discovery_workflow = WorkflowBuilder()

        # Find all published posts
        discovery_workflow.add_node(
            "BlogPostListNode",
            "get_published_posts",
            {
                "filter": {"status": "published"},
                "order_by": ["-created_at"],
                "limit": 10,
            },
        )

        # Find posts by category
        discovery_workflow.add_node(
            "BlogPostListNode",
            "get_tech_posts",
            {
                "filter": {"category_id": tech_category["id"], "status": "published"},
                "limit": 5,
            },
        )

        # Find featured posts
        discovery_workflow.add_node(
            "BlogPostListNode",
            "get_featured_posts",
            {"filter": {"is_featured": True, "status": "published"}, "limit": 3},
        )

        # Get post with comments (simulate post detail view)
        discovery_workflow.add_node(
            "BlogPostReadNode",
            "get_post_details",
            {"record_id": published_post_1["id"]},
        )

        discovery_workflow.add_node(
            "CommentListNode",
            "get_post_comments",
            {
                "filter": {"post_id": published_post_1["id"], "is_approved": True},
                "order_by": ["created_at"],
                "limit": 20,
            },
        )

        discovery_results, _ = runtime.execute(discovery_workflow.build())

        published_posts = discovery_results["get_published_posts"]
        tech_posts = discovery_results["get_tech_posts"]
        featured_posts = discovery_results["get_featured_posts"]
        post_details = discovery_results["get_post_details"]
        post_comments = discovery_results["get_post_comments"]

        # Verify discovery results
        assert (
            len(published_posts) >= 2
        )  # At least two published posts (handles multiple test runs)
        assert len(tech_posts) >= 1  # At least the DataFlow post
        assert (
            len(featured_posts) >= 1
        )  # At least one featured post (handles multiple test runs)
        assert post_details["id"] == published_post_1["id"]
        assert len(post_comments) >= 2  # At least 2 comments

        print(
            f"✅ Phase 7 Complete: Content discovery working ({len(published_posts)} published posts)"
        )

        # PHASE 8: Analytics and Performance Tracking
        print("📊 Phase 8: Analytics and performance tracking...")

        analytics_workflow = WorkflowBuilder()

        # Simulate post view tracking
        analytics_workflow.add_node(
            "BlogPostUpdateNode",
            "track_post_view",
            {
                "record_id": published_post_1["id"],
                "updates": {"view_count": published_post_1["view_count"] + 1},
            },
        )

        # Update category post count
        analytics_workflow.add_node(
            "CategoryUpdateNode",
            "update_category_count",
            {
                "record_id": tech_category["id"],
                "updates": {"post_count": tech_category["post_count"] + 1},
            },
        )

        # Get blog statistics - using simple list operations
        analytics_workflow.add_node(
            "BlogUserListNode",
            "get_all_users",
            {"limit": 100},  # Get all users to count them
        )

        analytics_workflow.add_node(
            "BlogPostListNode",
            "get_all_posts",
            {"limit": 100},  # Get all posts to analyze them
        )

        analytics_results, _ = runtime.execute(analytics_workflow.build())

        # DataFlow list nodes return {'records': [...], 'count': N, ...}
        all_users_records = analytics_results["get_all_users"]["records"]
        all_posts_records = analytics_results["get_all_posts"]["records"]

        # Calculate statistics from the returned data
        total_users = len(all_users_records)
        active_users = len(
            [user for user in all_users_records if user.get("is_active", True)]
        )
        total_posts = len(all_posts_records)
        published_posts = len(
            [post for post in all_posts_records if post.get("status") == "published"]
        )
        draft_posts = len(
            [post for post in all_posts_records if post.get("status") == "draft"]
        )

        assert total_users >= 2  # At least 2 users (this test creates 2)
        assert active_users >= 2  # At least 2 active users
        assert total_posts >= 3  # At least 3 posts (this test creates 3)
        assert published_posts >= 2  # At least 2 published posts
        assert draft_posts >= 1  # At least 1 draft post

        print("✅ Phase 8 Complete: Analytics tracking working")

        # FINAL VERIFICATION: Complete Blog Application Health Check
        print("🏥 Final Phase: Complete application health check...")

        health_check_workflow = WorkflowBuilder()

        # Verify all major components
        health_check_workflow.add_node("BlogUserListNode", "check_users", {"limit": 1})
        health_check_workflow.add_node(
            "CategoryListNode", "check_categories", {"limit": 1}
        )
        health_check_workflow.add_node("BlogPostListNode", "check_posts", {"limit": 1})
        health_check_workflow.add_node(
            "CommentListNode", "check_comments", {"limit": 1}
        )
        health_check_workflow.add_node("TagListNode", "check_tags", {"limit": 1})
        health_check_workflow.add_node(
            "PostTagListNode", "check_post_tags", {"limit": 1}
        )

        health_results, _ = runtime.execute(health_check_workflow.build())

        # Verify all components are working
        assert len(health_results["check_users"]) > 0
        assert len(health_results["check_categories"]) > 0
        assert len(health_results["check_posts"]) > 0
        assert len(health_results["check_comments"]) > 0
        assert len(health_results["check_tags"]) > 0
        assert len(health_results["check_post_tags"]) > 0

        print("🎉 BLOG APPLICATION E2E TEST COMPLETE!")
        print(f"✅ Users: {total_users}")
        print(f"✅ Categories: {len(categories)}")
        print(f"✅ Published Posts: {published_posts}")
        print(f"✅ Comments: {len(post_comments)}")
        print(f"✅ Tags: {len(tags)}")
        print(
            "✅ All features working: ✓ User management ✓ Content creation ✓ Categories ✓ Tags ✓ Comments ✓ Search ✓ Analytics"
        )

        # Return summary for additional assertions if needed
        return {
            "users_created": total_users,
            "posts_published": published_posts,
            "comments_added": len(post_comments),
            "categories_created": len(categories),
            "tags_created": len(tags),
            "featured_posts": len(featured_posts),
        }

    @pytest.mark.asyncio
    async def test_blog_application_performance(self, blog_dataflow):
        """Test that the blog application performs well under realistic load."""
        db = blog_dataflow

        # Set up basic blog structure first
        @db.model
        class QuickUser:
            username: str
            email: str

        @db.model
        class QuickPost:
            title: str
            content: str
            author_id: int
            status: str = "published"

        # Performance test: Create multiple users and posts quickly
        start_time = time.time()

        bulk_workflow = WorkflowBuilder()

        # Create 10 users quickly
        for i in range(10):
            bulk_workflow.add_node(
                "QuickUserCreateNode",
                f"user_{i}",
                {"username": f"user{i:03d}", "email": f"user{i:03d}@example.com"},
            )

        # Create 50 posts quickly (5 per user)
        for user_idx in range(10):
            for post_idx in range(5):
                node_id = f"post_{user_idx}_{post_idx}"
                user_node_id = f"user_{user_idx}"

                bulk_workflow.add_node(
                    "QuickPostCreateNode",
                    node_id,
                    {
                        "title": f"Post {post_idx + 1} by User {user_idx + 1}",
                        "content": f"This is post content for post {post_idx + 1}...",
                        "status": "published",
                    },
                )

                # Connect to user
                bulk_workflow.add_connection(user_node_id, node_id, "id", "author_id")

        runtime = LocalRuntime()
        results, _ = runtime.execute(bulk_workflow.build())

        creation_time = time.time() - start_time

        # Verify performance
        assert len(results) == 60  # 10 users + 50 posts
        assert creation_time < 30  # Should complete within 30 seconds

        print(
            f"⚡ Performance Test: Created 10 users + 50 posts in {creation_time:.2f}s"
        )

        # Query performance test
        query_start = time.time()

        query_workflow = WorkflowBuilder()

        # Complex queries that a blog would need
        query_workflow.add_node(
            "QuickPostListNode",
            "recent_posts",
            {
                "filter": {"status": "published"},
                "order_by": ["-created_at"],
                "limit": 20,
            },
        )

        query_workflow.add_node(
            "QuickUserListNode",
            "active_authors",
            {"filter": {}, "limit": 10},  # All users
        )

        query_results, _ = runtime.execute(query_workflow.build())

        query_time = time.time() - query_start

        assert len(query_results["recent_posts"]) == 20
        assert len(query_results["active_authors"]) == 10
        assert query_time < 2  # Queries should be fast

        print(f"🔍 Query Performance: Complex queries in {query_time:.2f}s")
