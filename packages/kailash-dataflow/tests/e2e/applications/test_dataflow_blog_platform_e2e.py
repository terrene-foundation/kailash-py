"""End-to-end test for a blog platform using DataFlow."""

from datetime import datetime

import pytest

from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.requires_postgres
@pytest.mark.requires_docker
class TestBlogPlatformE2E:
    """Test complete blog platform workflow using DataFlow."""

    @pytest.mark.asyncio
    async def test_complete_blog_workflow(self, dataflow, runtime):
        """Test complete blog platform workflow from user creation to comments."""

        # Define models for blog platform
        @dataflow.model
        class User:
            username: str
            email: str
            full_name: str
            bio: str = ""
            active: bool = True
            created_at: datetime

        @dataflow.model
        class BlogPost:
            author_id: int
            title: str
            slug: str
            content: str
            excerpt: str
            published: bool = False
            featured: bool = False
            view_count: int = 0
            created_at: datetime
            published_at: datetime = None

        @dataflow.model
        class Comment:
            post_id: int
            author_id: int
            content: str
            approved: bool = True
            created_at: datetime

        @dataflow.model
        class Tag:
            name: str
            slug: str

        @dataflow.model
        class PostTag:
            post_id: int
            tag_id: int

        # Create tables
        dataflow.create_tables()

        # Build the workflow
        workflow = WorkflowBuilder()

        # Step 1: Create blog authors
        workflow.add_node(
            "UserCreateNode",
            "create_author1",
            {
                "username": "tech_writer",
                "email": "tech@blog.com",
                "full_name": "Tech Writer",
                "bio": "Writing about technology trends",
            },
        )

        workflow.add_node(
            "UserCreateNode",
            "create_author2",
            {
                "username": "data_scientist",
                "email": "data@blog.com",
                "full_name": "Data Scientist",
                "bio": "Exploring data and ML",
            },
        )

        # Step 2: Create tags
        tags_data = [
            {"name": "Python", "slug": "python"},
            {"name": "Machine Learning", "slug": "machine-learning"},
            {"name": "Web Development", "slug": "web-development"},
            {"name": "DataFlow", "slug": "dataflow"},
        ]

        workflow.add_node("TagBulkCreateNode", "create_tags", {"data": tags_data})

        # Step 3: Create blog posts
        def create_blog_posts(author1, author2, tags):
            """Create blog posts with proper author IDs."""
            posts = [
                {
                    "author_id": author1["data"]["id"],
                    "title": "Getting Started with DataFlow",
                    "slug": "getting-started-dataflow",
                    "excerpt": "Learn how to use DataFlow for database operations",
                    "content": "DataFlow is a powerful framework...",
                    "published": True,
                    "featured": True,
                },
                {
                    "author_id": author1["data"]["id"],
                    "title": "Advanced DataFlow Patterns",
                    "slug": "advanced-dataflow-patterns",
                    "excerpt": "Deep dive into DataFlow patterns",
                    "content": "Let's explore advanced patterns...",
                    "published": True,
                },
                {
                    "author_id": author2["data"]["id"],
                    "title": "Machine Learning with DataFlow",
                    "slug": "ml-with-dataflow",
                    "excerpt": "Using DataFlow for ML pipelines",
                    "content": "DataFlow can power ML workflows...",
                    "published": False,
                },
            ]
            return {"posts": posts}

        # Add posts creation node
        create_posts_node = PythonCodeNode.from_function(
            create_blog_posts, name="prepare_posts"
        )
        workflow.add_node_instance(create_posts_node, "prepare_posts")

        # Connect authors to post preparation
        workflow.add_connection("create_author1", "result", "prepare_posts", "author1")
        workflow.add_connection("create_author2", "result", "prepare_posts", "author2")
        workflow.add_connection("create_tags", "result", "prepare_posts", "tags")

        # Bulk create posts
        workflow.add_node("BlogPostBulkCreateNode", "create_posts")
        workflow.add_connection("prepare_posts", "posts", "create_posts", "data")

        # Step 4: Add comments to published posts
        workflow.add_node(
            "BlogPostListNode",
            "get_published_posts",
            {"filter": {"published": True}, "order_by": ["-created_at"]},
        )

        # Create reader user
        workflow.add_node(
            "UserCreateNode",
            "create_reader",
            {
                "username": "blog_reader",
                "email": "reader@example.com",
                "full_name": "Blog Reader",
            },
        )

        # Add comments function
        def create_comments(posts, reader):
            """Create comments for published posts."""
            comments = []
            for post in posts["data"]:
                comments.append(
                    {
                        "post_id": post["id"],
                        "author_id": reader["data"]["id"],
                        "content": f"Great article about {post['title']}!",
                    }
                )
            return {"comments": comments}

        comment_node = PythonCodeNode.from_function(
            create_comments, name="prepare_comments"
        )
        workflow.add_node_instance(comment_node, "prepare_comments")

        # Connect to create comments
        workflow.add_connection(
            "get_published_posts", "result", "prepare_comments", "posts"
        )
        workflow.add_connection("create_reader", "result", "prepare_comments", "reader")

        # Bulk create comments
        workflow.add_node("CommentBulkCreateNode", "create_comments")
        workflow.add_connection(
            "prepare_comments", "comments", "create_comments", "data"
        )

        # Step 5: Update view counts
        def update_view_counts(posts):
            """Simulate view count updates."""
            updates = []
            for i, post in enumerate(posts["data"]):
                updates.append(
                    {
                        "id": post["id"],
                        "view_count": (i + 1) * 50,  # Simulate different view counts
                    }
                )
            return {"updates": updates}

        view_node = PythonCodeNode.from_function(
            update_view_counts, name="prepare_view_updates"
        )
        workflow.add_node_instance(view_node, "prepare_view_updates")
        workflow.add_connection(
            "get_published_posts", "result", "prepare_view_updates", "posts"
        )

        workflow.add_node("BlogPostBulkUpdateNode", "update_views")
        workflow.add_connection(
            "prepare_view_updates", "updates", "update_views", "data"
        )

        # Step 6: Generate analytics
        workflow.add_node("BlogPostListNode", "get_all_posts")
        workflow.add_node("CommentListNode", "get_all_comments")

        def generate_analytics(posts, comments, users):
            """Generate blog analytics."""
            total_posts = len(posts["data"])
            published_posts = len([p for p in posts["data"] if p["published"]])
            total_comments = len(comments["data"])
            total_views = sum(p["view_count"] for p in posts["data"])

            # Posts per author
            author_stats = {}
            for post in posts["data"]:
                author_id = post["author_id"]
                if author_id not in author_stats:
                    author_stats[author_id] = {"posts": 0, "views": 0}
                author_stats[author_id]["posts"] += 1
                author_stats[author_id]["views"] += post["view_count"]

            return {
                "analytics": {
                    "total_posts": total_posts,
                    "published_posts": published_posts,
                    "draft_posts": total_posts - published_posts,
                    "total_comments": total_comments,
                    "total_views": total_views,
                    "avg_views_per_post": (
                        total_views / total_posts if total_posts > 0 else 0
                    ),
                    "author_stats": author_stats,
                }
            }

        analytics_node = PythonCodeNode.from_function(
            generate_analytics, name="generate_analytics"
        )
        workflow.add_node_instance(analytics_node, "generate_analytics")

        # Get all users for analytics
        workflow.add_node("UserListNode", "get_all_users")

        # Connect to analytics
        workflow.add_connection(
            "get_all_posts", "result", "generate_analytics", "posts"
        )
        workflow.add_connection(
            "get_all_comments", "result", "generate_analytics", "comments"
        )
        workflow.add_connection(
            "get_all_users", "result", "generate_analytics", "users"
        )

        # Execute the complete workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        # Check users created
        assert results["create_author1"]["data"]["username"] == "tech_writer"
        assert results["create_author2"]["data"]["username"] == "data_scientist"
        assert results["create_reader"]["data"]["username"] == "blog_reader"

        # Check tags created
        tags = results["create_tags"]["data"]
        assert len(tags) == 4
        tag_names = [tag["name"] for tag in tags]
        assert "Python" in tag_names
        assert "DataFlow" in tag_names

        # Check posts created
        posts = results["create_posts"]["data"]
        assert len(posts) == 3

        # Check published posts
        published = results["get_published_posts"]["data"]
        assert len(published) == 2
        assert all(post["published"] for post in published)

        # Check comments
        comments = results["create_comments"]["data"]
        assert len(comments) == len(published)

        # Check view counts updated
        updated_posts = results["update_views"]["data"]
        assert all(post["view_count"] > 0 for post in updated_posts)

        # Check analytics
        analytics = results["generate_analytics"]["analytics"]
        assert analytics["total_posts"] == 3
        assert analytics["published_posts"] == 2
        assert analytics["draft_posts"] == 1
        assert analytics["total_comments"] == 2
        assert analytics["total_views"] > 0
        assert len(analytics["author_stats"]) == 2  # Two authors with posts

        print("\nBlog Platform Analytics:")
        print(f"Total Posts: {analytics['total_posts']}")
        print(f"Published: {analytics['published_posts']}")
        print(f"Drafts: {analytics['draft_posts']}")
        print(f"Total Views: {analytics['total_views']}")
        print(f"Total Comments: {analytics['total_comments']}")
        print(f"Average Views per Post: {analytics['avg_views_per_post']:.1f}")

        return results
