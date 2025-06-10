"""Example demonstrating the RESTClient node for RESTful API integration."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.api import RESTClientNode


def demonstrate_crud_operations():
    """Demonstrate CRUD operations with RESTClientNode."""
    print("🔄 RESTClientNode CRUD Operations Demo")
    print("=" * 50)

    client = RESTClientNode()

    # Using JSONPlaceholder API for demonstration
    base_url = "https://jsonplaceholder.typicode.com"

    # 1. CREATE - Post a new resource
    print("\n1. CREATE - Creating a new post:")
    create_result = client.create(
        base_url=base_url,
        resource="posts",
        data={
            "title": "My New Post",
            "body": "This is the content of my post",
            "userId": 1,
        },
    )

    if create_result["success"]:
        print(f"   ✅ Status: {create_result['status_code']}")
        print(f"   Created Post ID: {create_result['data'].get('id', 'N/A')}")
        print(f"   Title: {create_result['data'].get('title', 'N/A')}")
        created_id = create_result["data"].get("id", 101)  # JSONPlaceholder returns 101
    else:
        print(f"   ❌ Error: {create_result.get('error', 'Unknown error')}")
        created_id = 101

    # 2. READ - Get a single resource
    print("\n2. READ - Fetching a single post:")
    get_result = client.get(base_url=base_url, resource="posts", resource_id="1")

    if get_result["success"]:
        print(f"   ✅ Status: {get_result['status_code']}")
        print(f"   Post ID: {get_result['data'].get('id', 'N/A')}")
        print(f"   Title: {get_result['data'].get('title', 'N/A')[:50]}...")
    else:
        print(f"   ❌ Error: {get_result.get('error', 'Unknown error')}")

    # 3. LIST - Get collection with pagination
    print("\n3. LIST - Fetching posts with pagination:")
    list_result = client.get(
        base_url=base_url, resource="posts", query_params={"_page": 1, "_limit": 5}
    )

    if list_result["success"]:
        print(f"   ✅ Status: {list_result['status_code']}")
        print(f"   Posts Retrieved: {len(list_result['data'])}")
        for i, post in enumerate(list_result["data"][:3], 1):
            print(f"   Post {i}: {post.get('title', 'N/A')[:40]}...")
    else:
        print(f"   ❌ Error: {list_result.get('error', 'Unknown error')}")

    # 4. UPDATE - Full update of a resource
    print("\n4. UPDATE - Updating a post:")
    update_result = client.update(
        base_url=base_url,
        resource="posts",
        resource_id="1",
        data={
            "id": 1,
            "title": "Updated Post Title",
            "body": "This is the updated content",
            "userId": 1,
        },
    )

    if update_result["success"]:
        print(f"   ✅ Status: {update_result['status_code']}")
        print(f"   Updated Title: {update_result['data'].get('title', 'N/A')}")
    else:
        print(f"   ❌ Error: {update_result.get('error', 'Unknown error')}")

    # 5. PATCH - Partial update
    print("\n5. PATCH - Partially updating a post:")
    patch_result = client.update(
        base_url=base_url,
        resource="posts",
        resource_id="1",
        data={"title": "Partially Updated Title"},
        partial=True,
    )

    if patch_result["success"]:
        print(f"   ✅ Status: {patch_result['status_code']}")
        print(f"   Patched Title: {patch_result['data'].get('title', 'N/A')}")
    else:
        print(f"   ❌ Error: {patch_result.get('error', 'Unknown error')}")

    # 6. DELETE - Remove a resource
    print("\n6. DELETE - Deleting a post:")
    delete_result = client.delete(
        base_url=base_url, resource="posts", resource_id=str(created_id)
    )

    if delete_result["success"]:
        print(f"   ✅ Status: {delete_result['status_code']}")
        print(f"   Message: {delete_result.get('message', 'Deleted successfully')}")
    else:
        print(f"   ❌ Error: {delete_result.get('error', 'Unknown error')}")


def demonstrate_nested_resources():
    """Demonstrate working with nested resources using RESTClientNode."""
    print("\n\n🔗 RESTClientNode Nested Resources Demo")
    print("=" * 50)

    client = RESTClientNode()
    base_url = "https://jsonplaceholder.typicode.com"

    # 1. Get comments for a specific post
    print("\n1. Nested Resource - Post Comments:")
    comments_result = client.get(base_url=base_url, resource="posts/1/comments")

    if comments_result["success"]:
        print(f"   ✅ Status: {comments_result['status_code']}")
        print(f"   Comments Retrieved: {len(comments_result['data'])}")
        for i, comment in enumerate(comments_result["data"][:2], 1):
            print(f"   Comment {i}:")
            print(f"     - Name: {comment.get('name', 'N/A')[:40]}...")
            print(f"     - Email: {comment.get('email', 'N/A')}")

    # 2. Get posts by a specific user
    print("\n2. Filtered Resource - User's Posts:")
    user_posts_result = client.get(
        base_url=base_url, resource="posts", query_params={"userId": 1, "_limit": 3}
    )

    if user_posts_result["success"]:
        print(f"   ✅ Status: {user_posts_result['status_code']}")
        print(f"   Posts by User 1: {len(user_posts_result['data'])}")
        for post in user_posts_result["data"]:
            print(f"   - {post.get('title', 'N/A')[:50]}...")

    # 3. Get albums for a specific user
    print("\n3. Related Resource - User's Albums:")
    albums_result = client.get(
        base_url=base_url, resource="users/1/albums", query_params={"_limit": 3}
    )

    if albums_result["success"]:
        print(f"   ✅ Status: {albums_result['status_code']}")
        print(f"   Albums Retrieved: {len(albums_result['data'])}")
        for album in albums_result["data"]:
            print(f"   - Album: {album.get('title', 'N/A')}")


def demonstrate_advanced_features():
    """Demonstrate advanced REST features with RESTClientNode."""
    print("\n\n🚀 RESTClientNode Advanced Features Demo")
    print("=" * 50)

    client = RESTClientNode()

    # 1. API versioning
    print("\n1. API Versioning:")
    try:
        versioned_result = client.get(
            base_url="https://api.example.com",  # Mock example
            resource="users",
            version="v2",
        )
        print(f"   Success: {versioned_result['success']}")
    except Exception:
        # Expected to fail with mock URL
        print("   API URL would be: https://api.example.com/v2/users")
        print("   Note: Mock URL example (expected to fail)")

    # 2. Authenticated requests
    print("\n2. Authenticated REST Request:")
    auth_result = client.get(
        base_url="https://httpbin.org",
        resource="bearer",
        headers={"Authorization": "Bearer demo-token-12345"},
    )

    if auth_result["success"]:
        print(f"   ✅ Status: {auth_result['status_code']}")
        print(f"   Authenticated: {auth_result['data'].get('authenticated', False)}")

    # 3. Custom headers and metadata
    print("\n3. Custom Headers and Metadata:")
    metadata_result = client.get(
        base_url="https://httpbin.org",
        resource="headers",
        headers={"X-Custom-Header": "CustomValue", "Accept-Language": "en-US"},
    )

    if metadata_result["success"]:
        print(f"   ✅ Status: {metadata_result['status_code']}")
        headers_seen = metadata_result["data"].get("headers", {})
        print(
            f"   Custom Header Received: {headers_seen.get('X-Custom-Header', 'N/A')}"
        )
        print("   Metadata:")
        if "response_time_ms" in metadata_result["metadata"]:
            print(
                f"     - Response Time: {metadata_result['metadata']['response_time_ms']}ms"
            )
        if "rate_limit" in metadata_result["metadata"]:
            rl = metadata_result["metadata"]["rate_limit"]
            print(
                f"     - Rate Limit: {rl.get('remaining', 'N/A')}/{rl.get('limit', 'N/A')}"
            )

    # 4. Error handling
    print("\n4. REST Error Handling:")
    error_result = client.get(
        base_url="https://httpbin.org",
        resource="status/{code}",
        path_params={"code": 404},
    )

    if not error_result["success"]:
        print("   ❌ Expected 404 Error")
        print(f"   Status Code: {error_result.get('status_code', 'N/A')}")
        print(f"   Success: {error_result['success']}")

    # 5. Demonstrate metadata extraction
    print("\n5. Metadata Extraction Demo:")
    github_result = client.get(base_url="https://api.github.com", resource="rate_limit")

    if github_result["success"]:
        print(f"   ✅ Status: {github_result['status_code']}")
        if "rate_limit" in github_result["metadata"]:
            rl = github_result["metadata"]["rate_limit"]
            print("   Rate Limit Info:")
            print(f"     - Limit: {rl.get('limit', 'N/A')}")
            print(f"     - Remaining: {rl.get('remaining', 'N/A')}")
            print(f"     - Reset: {rl.get('reset', 'N/A')}")
        if "links" in github_result["metadata"]:
            print(
                f"   HATEOAS Links: {list(github_result['metadata']['links'].keys())}"
            )
    else:
        print("   Note: GitHub API may require authentication")


def demonstrate_real_world_scenario():
    """Demonstrate a real-world REST API workflow."""
    print("\n\n🌍 Real-World REST Workflow Demo")
    print("=" * 50)
    print("Scenario: Blog Post Management System")

    client = RESTClientNode()
    base_url = "https://jsonplaceholder.typicode.com"

    # Step 1: Get user information
    print("\n1. Fetch User Information:")
    user_result = client.get(base_url=base_url, resource="users", resource_id="1")

    if user_result["success"]:
        user = user_result["data"]
        print(f"   ✅ User: {user.get('name', 'N/A')}")
        print(f"   Email: {user.get('email', 'N/A')}")
        print(f"   Company: {user.get('company', {}).get('name', 'N/A')}")

    # Step 2: Get user's recent posts
    print("\n2. Fetch User's Recent Posts:")
    posts_result = client.get(
        base_url=base_url,
        resource="posts",
        query_params={"userId": 1, "_limit": 3, "_sort": "id", "_order": "desc"},
    )

    if posts_result["success"]:
        print(f"   ✅ Found {len(posts_result['data'])} recent posts")

        # Step 3: Get comments for the most recent post
        if posts_result["data"]:
            latest_post = posts_result["data"][0]
            post_id = latest_post["id"]

            print(f"\n3. Fetch Comments for Post '{latest_post['title'][:40]}...':")
            comments_result = client.get(
                base_url=base_url, resource=f"posts/{post_id}/comments"
            )

            if comments_result["success"]:
                print(f"   ✅ Found {len(comments_result['data'])} comments")

                # Step 4: Create a new comment
                print("\n4. Add New Comment:")
                new_comment_result = client.create(
                    base_url=base_url,
                    resource="comments",
                    data={
                        "postId": post_id,
                        "name": "Great post!",
                        "email": "reader@example.com",
                        "body": "This was very informative. Thanks for sharing!",
                    },
                )

                if new_comment_result["success"]:
                    print("   ✅ Comment added successfully")
                    print(
                        f"   Comment ID: {new_comment_result['data'].get('id', 'N/A')}"
                    )

    # Step 5: Get user's todos
    print("\n5. Check User's TODO List:")
    todos_result = client.get(
        base_url=base_url,
        resource="todos",
        query_params={"userId": 1, "completed": False, "_limit": 3},
    )

    if todos_result["success"]:
        print(f"   ✅ Found {len(todos_result['data'])} incomplete todos")
        for todo in todos_result["data"]:
            print(f"   - [ ] {todo.get('title', 'N/A')}")

    print("\n" + "=" * 50)
    print("✨ RESTClient enables complex multi-resource workflows!")


def main():
    """Run all RESTClient demonstrations."""
    print("🎯 Kailash RESTClient Node Examples")
    print("=" * 50)
    print("Demonstrating RESTful API integration capabilities\n")

    demonstrate_crud_operations()
    demonstrate_nested_resources()
    demonstrate_advanced_features()
    demonstrate_real_world_scenario()

    print("\n\n📚 Key Features Demonstrated:")
    print("✅ Full CRUD operations (Create, Read, Update, Delete)")
    print("✅ Resource-oriented design")
    print("✅ Nested and related resources")
    print("✅ Query parameters and filtering")
    print("✅ API versioning")
    print("✅ Authentication integration")
    print("✅ Error handling with REST semantics")
    print("✅ Real-world workflow patterns")


if __name__ == "__main__":
    main()
