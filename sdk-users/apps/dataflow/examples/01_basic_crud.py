"""
Basic CRUD Operations with DataFlow

This example demonstrates:
- Zero configuration setup
- Model definition with type hints
- Automatic node generation
- CRUD operations in workflows
"""

from datetime import datetime
from typing import Optional

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# Zero configuration - just works!
db = DataFlow()


# Define a model using Python type hints
@db.model
class BlogPost:
    """A simple blog post model"""

    title: str
    content: str
    author: str
    published: bool = False
    views: int = 0
    tags: Optional[list] = None

    # DataFlow automatically adds:
    # - id: int (primary key)
    # - created_at: datetime (auto-managed - don't set manually!)
    # - updated_at: datetime (auto-managed - don't set manually!)


def demo_create():
    """Demonstrate creating records"""
    print("\n=== CREATE OPERATION ===")

    workflow = WorkflowBuilder()

    # ==========================================
    # CRITICAL: CreateNode uses FLAT individual fields
    # ==========================================
    # ✅ CORRECT Pattern:
    #   workflow.add_node("BlogPostCreateNode", "create", {
    #       "title": "...",    # ← Individual field 1
    #       "content": "...",  # ← Individual field 2
    #       "author": "..."    # ← Individual field 3
    #   })
    #
    # ❌ WRONG - Do NOT nest under 'data':
    #   workflow.add_node("BlogPostCreateNode", "create", {
    #       "data": {          # ← This creates a FIELD named "data"!
    #           "title": "...",
    #           "content": "..."
    #       }
    #   })
    # ==========================================

    # Create a blog post
    workflow.add_node(
        "BlogPostCreateNode",
        "create_post",
        {
            "title": "Introduction to DataFlow",
            "content": "DataFlow makes database operations incredibly simple...",
            "author": "Alice Smith",
            "tags": ["database", "python", "kailash"],
        },
    )

    # Execute workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    post = results["create_post"]["output"]
    print(f"Created post: {post['title']} (ID: {post['id']})")
    return post["id"]


def demo_read(post_id: int):
    """Demonstrate reading a single record"""
    print("\n=== READ OPERATION ===")

    workflow = WorkflowBuilder()

    # Read the blog post
    workflow.add_node("BlogPostReadNode", "read_post", {"filter": {"id": post_id}})

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    post = results["read_post"]["output"]
    print(f"Read post: {post['title']} by {post['author']}")
    print(f"Views: {post['views']}, Published: {post['published']}")


def demo_update(post_id: int):
    """Demonstrate updating records"""
    print("\n=== UPDATE OPERATION ===")

    workflow = WorkflowBuilder()

    # ==========================================
    # CRITICAL: UpdateNode uses NESTED filter + fields
    # ==========================================
    # ✅ CORRECT Pattern:
    #   workflow.add_node("BlogPostUpdateNode", "update", {
    #       "filter": {"id": post_id},  # ← Which records to update
    #       "fields": {                  # ← What to change
    #           "published": True,
    #           "views": 100
    #       }
    #   })
    #
    # ❌ WRONG - Do NOT use flat fields like CreateNode:
    #   workflow.add_node("BlogPostUpdateNode", "update", {
    #       "id": post_id,      # ← This is CreateNode pattern!
    #       "published": True,
    #       "views": 100
    #   })
    #
    # ❌ WRONG - Do NOT set updated_at manually:
    #   "fields": {
    #       "published": True,
    #       "updated_at": datetime.now()  # ← Auto-managed!
    #   }
    # ==========================================

    # Update the post
    workflow.add_node(
        "BlogPostUpdateNode",
        "update_post",
        {
            "filter": {"id": post_id},  # Which record to update
            "fields": {  # What to change
                "published": True,
                "views": 100,
                # NOTE: updated_at is automatic - don't include it!
            },
        },
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    post = results["update_post"]["output"]
    print(f"Updated post: Published={post['published']}, Views={post['views']}")


def demo_list():
    """Demonstrate listing records with filters"""
    print("\n=== LIST OPERATION ===")

    workflow = WorkflowBuilder()

    # Create multiple posts for demonstration
    for i in range(5):
        workflow.add_node(
            "BlogPostCreateNode",
            f"create_{i}",
            {
                "title": f"Post {i+1}",
                "content": f"Content for post {i+1}",
                "author": "Bob Jones" if i % 2 == 0 else "Alice Smith",
                "published": i % 2 == 0,
                "views": i * 10,
            },
        )

    # List published posts
    workflow.add_node(
        "BlogPostListNode",
        "list_published",
        {
            "filter": {"published": True},
            "order_by": ["-views"],  # Sort by views descending
            "limit": 10,
        },
    )

    # List posts by author
    workflow.add_node(
        "BlogPostListNode",
        "list_by_author",
        {"filter": {"author": "Alice Smith"}, "order_by": ["created_at"]},
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    published = results["list_published"]["output"]
    print(f"\nPublished posts: {len(published)}")
    for post in published:
        print(f"  - {post['title']} ({post['views']} views)")

    alice_posts = results["list_by_author"]["output"]
    print(f"\nPosts by Alice: {len(alice_posts)}")
    for post in alice_posts:
        print(f"  - {post['title']}")


def demo_delete(post_id: int):
    """Demonstrate deleting records"""
    print("\n=== DELETE OPERATION ===")

    workflow = WorkflowBuilder()

    # Delete the post
    workflow.add_node("BlogPostDeleteNode", "delete_post", {"filter": {"id": post_id}})

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    deleted = results["delete_post"]["output"]
    print(f"Deleted post: {deleted['title']}")


def demo_complex_workflow():
    """Demonstrate a complex workflow with multiple operations"""
    print("\n=== COMPLEX WORKFLOW ===")

    workflow = WorkflowBuilder()

    # Create a post
    workflow.add_node(
        "BlogPostCreateNode",
        "create",
        {
            "title": "Advanced DataFlow Features",
            "content": "This post demonstrates advanced features...",
            "author": "Charlie Brown",
        },
    )

    # Increment view counter
    workflow.add_node(
        "BlogPostUpdateNode",
        "increment_views",
        {"filter": {"id": ":post_id"}, "fields": {"views": "views + 1"}},
    )

    # Publish the post
    workflow.add_node(
        "BlogPostUpdateNode",
        "publish",
        {"filter": {"id": ":post_id"}, "fields": {"published": True}},
    )

    # Read the final state
    workflow.add_node("BlogPostReadNode", "final_state", {"filter": {"id": ":post_id"}})

    # Connect nodes - data flows between them
    workflow.add_connection("create", "increment_views", "id", "post_id")
    workflow.add_connection("increment_views", "publish", "id", "post_id")
    workflow.add_connection("publish", "final_state", "id", "post_id")

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    final = results["final_state"]["output"]
    print("Final post state:")
    print(f"  Title: {final['title']}")
    print(f"  Views: {final['views']}")
    print(f"  Published: {final['published']}")


if __name__ == "__main__":
    print("DataFlow Basic CRUD Example")
    print("=" * 50)

    # Demonstrate all CRUD operations
    post_id = demo_create()
    demo_read(post_id)
    demo_update(post_id)
    demo_list()
    demo_delete(post_id)

    # Demonstrate complex workflow
    demo_complex_workflow()

    print("\n" + "=" * 50)
    print("Example completed successfully!")
    print("\nKey takeaways:")
    print("1. Zero configuration - DataFlow just works")
    print("2. Models defined with simple Python classes")
    print("3. CRUD nodes generated automatically")
    print("4. Data flows naturally between workflow nodes")
    print("5. All operations are async and efficient")
