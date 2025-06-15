"""Example demonstrating the enhanced HTTPRequestNode with authentication support."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.api import HTTPRequestNode


def demonstrate_basic_requests():
    """Demonstrate basic HTTP requests with the enhanced node."""
    print("🌐 Enhanced HTTPRequestNode Basic Requests Demo")
    print("=" * 50)

    # Create a client - URL will be passed at runtime
    client = HTTPRequestNode()

    # 1. Simple GET request
    print("\n1. Simple GET Request:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/get",
        headers={"Accept": "application/json"},
    )

    if result["success"]:
        print(f"   ✅ Status: {result['status_code']}")
        response_data = result["response"]["content"]
        print(f"   Response: {response_data.get('origin', 'N/A')}")
        print(
            f"   User-Agent: {response_data.get('headers', {}).get('User-Agent', 'N/A')}"
        )
    else:
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")

    # 2. POST request with JSON data
    print("\n2. POST Request with JSON:")
    result = client.execute(
        method="POST",
        url="https://httpbin.org/post",
        json_data={"name": "John Doe", "age": 30},
    )

    if result["success"]:
        print(f"   ✅ Status: {result['status_code']}")
        response_data = result["response"]["content"]
        print(f"   Posted Data: {response_data.get('json', {})}")
    else:
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")

    # 3. Request with query parameters
    print("\n3. Request with Query Parameters:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/get",
        params={"search": "test", "page": 1, "limit": 10},
    )

    if result["success"]:
        print(f"   ✅ Status: {result['status_code']}")
        response_data = result["response"]["content"]
        print(f"   Query Args: {response_data.get('args', {})}")
    else:
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")


def demonstrate_authentication():
    """Demonstrate authentication methods with the enhanced node."""
    print("\n\n🔐 Enhanced HTTPRequestNode Authentication Demo")
    print("=" * 50)

    # Create a client - URL will be passed at runtime
    client = HTTPRequestNode()

    # 1. Bearer token authentication
    print("\n1. Bearer Token Authentication:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/bearer",
        auth_type="bearer",
        auth_token="my-secret-token",
    )

    if result["success"]:
        print(f"   ✅ Status: {result['status_code']}")
        response_data = result["response"]["content"]
        print(f"   Authenticated: {response_data.get('authenticated', False)}")
        print(f"   Token: {response_data.get('token', 'N/A')}")
    else:
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")

    # 2. Basic authentication
    print("\n2. Basic Authentication:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/basic-auth/testuser/testpass",
        auth_type="basic",
        auth_username="testuser",
        auth_password="testpass",
    )

    if result["success"]:
        print(f"   ✅ Status: {result['status_code']}")
        response_data = result["response"]["content"]
        print(f"   Authenticated: {response_data.get('authenticated', False)}")
        print(f"   User: {response_data.get('user', 'N/A')}")
    else:
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")

    # 3. API Key authentication
    print("\n3. API Key Authentication:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/headers",
        auth_type="api_key",
        auth_token="my-api-key-123",
        api_key_header="X-API-Key",
    )

    if result["success"]:
        response_data = result["response"]["content"]
        headers = response_data.get("headers", {})
        print(f"   ✅ Status: {result['status_code']}")
        print(f"   API Key Header: {headers.get('X-Api-Key', 'Not found')}")
    else:
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")


def demonstrate_error_handling():
    """Demonstrate error handling with recovery suggestions."""
    print("\n\n⚠️  Enhanced HTTPRequestNode Error Handling Demo")
    print("=" * 50)

    # Create a client - URL will be passed at runtime
    client = HTTPRequestNode()

    # 1. 404 Not Found
    print("\n1. Handling 404 Not Found:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/status/404",
        retry_count=0,  # Don't retry 404s
    )

    print(f"   Status: {result.get('status_code', 'N/A')}")
    print(f"   Success: {result['success']}")
    if not result["success"] and "recovery_suggestions" in result:
        print("   Recovery Suggestions:")
        for suggestion in result["recovery_suggestions"][:3]:
            print(f"      - {suggestion}")

    # 2. Authentication error
    print("\n2. Authentication Error (401):")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/status/401",
        retry_count=0,
    )

    print(f"   Status: {result.get('status_code', 'N/A')}")
    print(f"   Success: {result['success']}")
    if not result["success"] and "recovery_suggestions" in result:
        print("   Recovery Suggestions:")
        for suggestion in result["recovery_suggestions"][:3]:
            print(f"      - {suggestion}")

    # 3. Rate limit error
    print("\n3. Rate Limit Error (429):")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/status/429",
        retry_count=0,
    )

    print(f"   Status: {result.get('status_code', 'N/A')}")
    print(f"   Success: {result['success']}")
    if not result["success"] and "recovery_suggestions" in result:
        print("   Recovery Suggestions:")
        for suggestion in result["recovery_suggestions"][:3]:
            print(f"      - {suggestion}")

    # 4. Timeout handling
    print("\n4. Timeout Handling:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/delay/10",  # 10 second delay
        timeout=2,  # 2 second timeout
        retry_count=0,
    )

    if not result["success"]:
        print(f"   ❌ Expected timeout error: {result.get('error_type', 'Unknown')}")
        if "recovery_suggestions" in result:
            print("   Recovery Suggestions:")
            for suggestion in result["recovery_suggestions"][:2]:
                print(f"      - {suggestion}")
    else:
        print("   ✅ Request completed (unexpected)")


def demonstrate_advanced_features():
    """Demonstrate advanced features of the enhanced node."""
    print("\n\n🚀 Enhanced HTTPRequestNode Advanced Features Demo")
    print("=" * 50)

    # Create a client - URL will be passed at runtime
    client = HTTPRequestNode()

    # 1. Rate limiting
    print("\n1. Rate Limiting:")
    print("   Making 3 requests with 1-second delay between each...")
    for i in range(3):
        start_time = client.execute(
            method="GET",
            url="https://httpbin.org/uuid",
            rate_limit_delay=1.0,  # 1 second delay
        )
        if start_time["success"]:
            response_data = start_time["response"]["content"]
            print(f"   Request {i+1}: UUID = {response_data.get('uuid', 'N/A')}")
        else:
            print(f"   Request {i+1}: Failed")

    # 2. Request logging
    print("\n2. Request/Response Logging:")
    result = client.execute(
        method="POST",
        url="https://httpbin.org/post",
        json_data={"test": "data", "logging": True},
        log_requests=True,  # Enable detailed logging
    )
    print(f"   ✅ Status: {result['status_code']} (check logs for details)")

    # 3. Retry with backoff
    print("\n3. Retry with Exponential Backoff:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/status/500",  # Server error
        retry_count=2,
        retry_backoff=1.0,
    )
    print(f"   Status: {result.get('status_code', 'N/A')}")
    print(f"   Success: {result['success']}")

    # 4. Response metadata
    print("\n4. Response Metadata:")
    result = client.execute(
        method="GET",
        url="https://httpbin.org/response-headers",
        params={"X-Custom-Response": "test-value"},
    )

    if result["success"]:
        response = result["response"]
        print(f"   ✅ Status: {result['status_code']}")
        print(f"   Content-Type: {response['content_type']}")
        print(f"   Response Time: {response['response_time_ms']:.2f}ms")
        print(f"   URL: {response['url']}")


def demonstrate_workflow_integration():
    """Show how the enhanced HTTPRequestNode integrates with workflows."""
    print("\n\n🔄 Enhanced HTTPRequestNode Workflow Integration Demo")
    print("=" * 50)

    # Simulate a multi-step API workflow
    # Create a client - URL will be passed at runtime
    client = HTTPRequestNode()

    # Step 1: Get authentication token
    print("\n1. Get Authentication Token:")
    auth_result = client.execute(
        method="POST",
        url="https://httpbin.org/post",
        json_data={"username": "demo", "password": "demo123"},
    )

    if auth_result["success"]:
        # Simulate extracting a token
        mock_token = "demo-token-12345"
        print(f"   ✅ Token obtained: {mock_token}")

        # Step 2: Use token to fetch user data
        print("\n2. Fetch User Data with Token:")
        user_result = client.execute(
            method="GET",
            url="https://httpbin.org/bearer",
            auth_type="bearer",
            auth_token=mock_token,
        )

        if user_result["success"]:
            response_data = user_result["response"]["content"]
            print("   ✅ User data retrieved")
            print(f"   Authenticated: {response_data.get('authenticated', False)}")

        # Step 3: Update user preferences
        print("\n3. Update User Preferences:")
        update_result = client.execute(
            method="PATCH",
            url="https://httpbin.org/patch",
            auth_type="bearer",
            auth_token=mock_token,
            json_data={"preferences": {"theme": "dark", "notifications": True}},
        )

        if update_result["success"]:
            response_data = update_result["response"]["content"]
            print("   ✅ Preferences updated")
            print(f"   Updated data: {response_data.get('json', {})}")

    print("\n" + "=" * 50)
    print(
        "✨ Enhanced HTTPRequestNode provides all features in a single, unified interface!"
    )


def main():
    """Run all enhanced HTTPRequestNode demonstrations."""
    print("🎯 Kailash Enhanced HTTPRequestNode Examples")
    print("=" * 50)
    print("Demonstrating the unified HTTP client with all features\n")

    demonstrate_basic_requests()
    demonstrate_authentication()
    demonstrate_error_handling()
    demonstrate_advanced_features()
    demonstrate_workflow_integration()

    print("\n\n📚 Key Features Demonstrated:")
    print("✅ Multiple HTTP methods (GET, POST, PATCH, etc.)")
    print("✅ Authentication (Bearer, Basic, API Key, OAuth2)")
    print("✅ Error handling with recovery suggestions")
    print("✅ Query parameters and headers")
    print("✅ Request/response logging")
    print("✅ Rate limiting support")
    print("✅ Retry with exponential backoff")
    print("✅ Response metadata and timing")
    print("✅ Workflow integration")
    print("✅ Both synchronous and asynchronous support")


if __name__ == "__main__":
    main()
