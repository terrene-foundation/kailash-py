#!/usr/bin/env python3
"""
Comprehensive API Integration Examples for Kailash SDK

This script demonstrates the complete API integration capabilities of the Kailash SDK:

1. Basic HTTP Requests
   - Simple GET/POST/PUT/DELETE operations
   - Response handling and status codes

2. REST API Integration
   - Resource patterns and path parameters
   - Query parameters and headers
   - Response processing

3. GraphQL API Integration
   - Query execution with variables
   - Mutation support
   - Result flattening

4. Authentication Methods
   - Basic authentication
   - API Key authentication
   - OAuth 2.0 (various flows)

5. Performance Features
   - Rate limiting (token bucket, sliding window)
   - Asynchronous execution
   - Retry mechanisms

6. Error Handling
   - Timeout configuration
   - Retry strategies
   - Error response processing

7. Complex Workflows
   - Multi-API integration
   - Data transformation between calls
   - Conditional execution

This example serves as a comprehensive reference for all API integration
capabilities available in the Kailash SDK.
"""

import asyncio
import json
import logging

# Ensure parent directory is in path
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kailash.nodes.api import (  # Basic HTTP nodes; REST API nodes; GraphQL nodes; Authentication nodes; Rate limiting
    APIKeyNode,
    AsyncHTTPRequestNode,
    AsyncRateLimitedAPINode,
    AsyncRESTClientNode,
    BasicAuthNode,
    GraphQLClientNode,
    HTTPRequestNode,
    RateLimitConfig,
    RateLimitedAPINode,
    RESTClientNode,
)
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

# Kailash SDK imports
from kailash.workflow import Workflow

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def section_header(title):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def example_1_basic_http_requests():
    """Example 1: Basic HTTP request operations."""
    section_header("Example 1: Basic HTTP Requests")

    # Create a workflow with a single HTTP request node
    workflow = Workflow(workflow_id="http_request_example", name="HTTP Request Example")

    # Add an HTTP request node to fetch data from a public API
    workflow.add_node(
        node_id="http_request",
        node_or_type=HTTPRequestNode,
        name="HTTP GET Request",
        url="https://jsonplaceholder.typicode.com/users",
        method="GET",
        response_format="json",
    )

    # Execute the workflow
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow)

    print("\n1. Simple GET request:")
    # Get the results from the workflow execution
    http_results = results["http_request"]

    # Print the results
    print(f"  Status code: {http_results['status_code']}")
    print(f"  Success: {http_results['success']}")
    print(f"  Number of users: {len(http_results['response']['content'])}")
    print(f"  First user: {http_results['response']['content'][0]['name']}")

    print("\n2. GET request with query parameters:")
    # Create a new workflow for this example
    wf2 = Workflow(workflow_id="http_query_example", name="HTTP Query Example")

    # Add a query params node
    wf2.add_node(
        node_id="query_request",
        node_or_type=HTTPRequestNode,
        name="HTTP GET with Query",
        url="https://jsonplaceholder.typicode.com/comments",
        method="GET",
        query_params={"postId": 1},
        response_format="json",
    )

    # Execute the workflow
    query_results, _ = runtime.execute(wf2)
    query_response = query_results["query_request"]

    print(f"  Status code: {query_response['status_code']}")
    print(f"  Number of comments: {len(query_response['response']['content'])}")

    print("\n3. POST request with JSON body:")
    # Create a new workflow for this example
    wf3 = Workflow(workflow_id="http_post_example", name="HTTP POST Example")

    # Add a POST node
    wf3.add_node(
        node_id="post_request",
        node_or_type=HTTPRequestNode,
        name="HTTP POST Request",
        url="https://jsonplaceholder.typicode.com/posts",
        method="POST",
        body={
            "title": "Kailash API Integration",
            "body": "Testing API integration with Kailash SDK",
            "userId": 1,
        },
        headers={"Content-Type": "application/json"},
        response_format="json",
    )

    # Execute the workflow
    post_results, _ = runtime.execute(wf3)
    post_response = post_results["post_request"]

    print(f"  Status code: {post_response['status_code']}")
    print(f"  Created post ID: {post_response['response']['content'].get('id')}")
    print(f"  Post title: {post_response['response']['content'].get('title')}")

    return {
        "get_request": http_results,
        "query_request": query_response,
        "post_request": post_response,
    }


def example_2_rest_api_integration():
    """Example 2: REST API integration with resource patterns."""
    section_header("Example 2: REST API Integration")

    # Execute the workflow
    runtime = LocalRuntime()

    print("\n1. REST API call with path parameters:")
    results = runtime.execute_node(
        RESTClientNode(
            name="REST API Client",
            node_id="rest_client",
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{id}",
            method="GET",
            path_params={"id": 3},
        )
    )

    # Print the results
    user = results["data"]
    print(f"  User: {user['name']} ({user['email']})")
    print(f"  Company: {user['company']['name']}")

    print("\n2. REST API call with query parameters:")
    results = runtime.execute_node(
        RESTClientNode(
            name="REST API Client",
            node_id="rest_client_query",
            base_url="https://jsonplaceholder.typicode.com",
            resource="posts",
            method="GET",
            query_params={"userId": 3},
        )
    )

    # Print the results
    posts = results["data"]
    print(f"  Retrieved {len(posts)} posts by user ID 3")
    if posts:
        print(f"  First post title: {posts[0]['title']}")

    print("\n3. Complex REST example - Get user's posts and their comments:")

    # First get a user
    user_result = runtime.execute_node(
        RESTClientNode(
            name="REST API Client",
            node_id="rest_client_user",
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{id}",
            method="GET",
            path_params={"id": 2},
        )
    )
    user = user_result["data"]

    # Get user's posts
    posts_result = runtime.execute_node(
        RESTClientNode(
            name="REST API Client",
            node_id="rest_client_posts",
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{id}/posts",
            method="GET",
            path_params={"id": user["id"]},
        )
    )
    posts = posts_result["data"]

    # Get comments for first post
    if posts:
        comments_result = runtime.execute_node(
            RESTClientNode(
                name="REST API Client",
                node_id="rest_client_comments",
                base_url="https://jsonplaceholder.typicode.com",
                resource="posts/{id}/comments",
                method="GET",
                path_params={"id": posts[0]["id"]},
            )
        )
        comments = comments_result["data"]

        print(f"  User: {user['name']} ({user['email']})")
        print(f"  Found {len(posts)} posts")
        print(f"  First post title: {posts[0]['title']}")
        print(f"  Comment count for first post: {len(comments)}")
        print(f"  First comment by: {comments[0]['name']} ({comments[0]['email']})")

    return {
        "user": user_result,
        "posts": posts_result,
        "comments": comments_result if posts else None,
    }


def example_3_graphql_api_integration():
    """Example 3: GraphQL API integration."""
    section_header("Example 3: GraphQL API Integration")

    # Execute the workflow
    runtime = LocalRuntime()

    print("\n1. Basic GraphQL query:")
    results = runtime.execute_node(
        GraphQLClientNode(
            name="GraphQL Client",
            node_id="graphql_client",
            endpoint="https://api.spacex.land/graphql/",
            query="""
            query {
              company {
                name
                founder
                founded
                employees
              }
              rockets(limit: 3) {
                name
                first_flight
                success_rate_pct
              }
            }
            """,
        )
    )

    # Print the results
    data = results["data"]
    company = data["company"]
    rockets = data["rockets"]

    print(f"  Company: {company['name']}")
    print(f"  Founded: {company['founded']} by {company['founder']}")
    print(f"  Employees: {company['employees']}")
    print("\n  Rockets:")
    for rocket in rockets:
        print(
            f"    - {rocket['name']} (First flight: {rocket['first_flight']}, "
            f"Success rate: {rocket['success_rate_pct']}%)"
        )

    print("\n2. GraphQL query with variables:")

    # Another example using the Countries API with variables
    results = runtime.execute_node(
        GraphQLClientNode(
            name="GraphQL Client",
            node_id="graphql_countries",
            endpoint="https://countries.trevorblades.com/",
            query="""
            query GetCountries($limit: Int!) {
              countries(first: $limit) {
                name
                code
                capital
                currency
              }
            }
            """,
            variables={"limit": 5},
        )
    )

    countries = results["data"]["countries"]
    print(f"  Retrieved {len(countries)} countries:")
    for country in countries:
        print(
            f"    - {country['name']} ({country['code']}): Capital: {country['capital']}, Currency: {country['currency']}"
        )

    return results


def example_4_authentication_methods():
    """Example 4: Various authentication methods."""
    section_header("Example 4: Authentication Methods")

    # Execute the workflow
    runtime = LocalRuntime()

    print("\n1. API Key Authentication:")
    api_key_result = runtime.execute_node(
        APIKeyNode(
            name="API Key Auth",
            node_id="api_key_auth",
            api_key="your-api-key-here",
            location="header",
            param_name="X-API-Key",
        )
    )

    print(f"  API Key Headers: {api_key_result['headers']}")

    print("\n2. Basic Authentication:")
    basic_auth_result = runtime.execute_node(
        BasicAuthNode(
            name="Basic Auth",
            node_id="basic_auth",
            username="demo_user",
            password="demo_password",
        )
    )

    print(f"  Basic Auth Headers: {basic_auth_result['headers']}")

    print("\n3. OAuth 2.0 Authentication (Client Credentials Flow):")
    print("  Setting up OAuth client with mock credentials...")
    print("  Grant type: client_credentials")
    print("  Client ID: demo-client-id")
    print("  Scope: api:read api:write")

    # For demonstration purposes, we'll show the configuration
    oauth_config = {
        "token_url": "https://your-oauth-provider.com/oauth/token",
        "client_id": "demo-client-id",
        "client_secret": "demo-client-secret",
        "grant_type": "client_credentials",
        "scope": "api:read api:write",
    }

    print(f"  Configuration: {json.dumps(oauth_config, indent=2)}")
    print("  Note: This example shows the OAuth setup. In practice, this would")
    print("        make a real request to get an access token.")

    print("\n4. Using authentication with API request:")
    # For demo purposes, we'll use the API Key with a REST request
    rest_result = runtime.execute_node(
        RESTClientNode(
            name="REST Client with Auth",
            node_id="rest_client_auth",
            base_url="https://jsonplaceholder.typicode.com",
            resource="posts/1",
            method="GET",
            headers=api_key_result["headers"],
        )
    )

    print(f"  Request with Auth - Status: {rest_result['success']}")
    print(f"  Post title: {rest_result['data']['title']}")

    return {
        "api_key": api_key_result,
        "basic_auth": basic_auth_result,
        "rest_with_auth": rest_result,
    }


def example_5_rate_limiting():
    """Example 5: Rate limiting for API calls."""
    section_header("Example 5: Rate Limiting")

    # Create rate limit configuration
    rate_config = RateLimitConfig(
        max_requests=3,  # 3 requests
        time_window=10.0,  # per 10 seconds
        strategy="token_bucket",  # using token bucket algorithm
        burst_limit=5,  # allow burst of up to 5 requests
        backoff_factor=1.5,  # increase wait time by 1.5x on each retry
    )

    # Execute the workflow
    runtime = LocalRuntime()

    print(
        f"\n1. Rate limiting config: {rate_config.max_requests} requests per {rate_config.time_window}s"
    )
    print("2. Making rapid API calls to demonstrate rate limiting:")

    results = []

    for i in range(6):  # Try to make 6 requests (more than limit)
        print(f"\n   Request {i+1}:")
        start_time = time.time()

        # For each request, create a fresh RateLimitedAPINode with the same config
        http_node = HTTPRequestNode(
            name="HTTP Client",
            url="https://jsonplaceholder.typicode.com/posts/1",
            method="GET",
        )
        rate_limited_node = RateLimitedAPINode(
            wrapped_node=http_node,
            rate_limit_config=rate_config,
            name="Rate Limited API",
            node_id=f"rate_limited_api_{i}",
        )

        result = runtime.execute_node(rate_limited_node)

        end_time = time.time()
        results.append(result)

        metadata = result.get("rate_limit_metadata", {})

        print(f"     Status: {result['status_code']}")
        print(f"     Attempts: {metadata.get('attempts', 1)}")
        print(f"     Wait time: {metadata.get('total_wait_time', 0):.2f}s")
        print(f"     Total time: {end_time - start_time:.2f}s")

    print("\n3. Rate limiting strategies available:")
    print("   - token_bucket: Classic token bucket algorithm")
    print("   - sliding_window: More precise control for high-volume APIs")
    print("   - fixed_window: Simple implementation for basic rate limits")

    return results


def example_6_error_handling():
    """Example 6: Error handling and retry strategies."""
    section_header("Example 6: Error Handling and Retry Strategies")

    # Execute the workflow
    runtime = LocalRuntime()

    print("\n1. Handling a 404 error:")
    not_found_result = runtime.execute_node(
        HTTPRequestNode(
            name="HTTP Client 404",
            node_id="http_client_404",
            url="https://jsonplaceholder.typicode.com/nonexistent",
            method="GET",
        )
    )

    print(f"  Status code: {not_found_result['status_code']}")
    print(f"  Success flag: {not_found_result['success']}")
    print(f"  Response contains error: {not_found_result['response']['content'] != ''}")

    print("\n2. Configuring automatic retries:")
    retry_result = runtime.execute_node(
        HTTPRequestNode(
            name="HTTP Client Retry",
            node_id="http_client_retry",
            url="https://jsonplaceholder.typicode.com/nonexistent",
            method="GET",
            retry_count=3,
            retry_backoff=0.5,
        )
    )

    print(f"  Status code after retries: {retry_result['status_code']}")
    print(f"  Success flag: {retry_result['success']}")

    print("\n3. Handling timeouts:")
    # Using a delay endpoint
    timeout_result = runtime.execute_node(
        HTTPRequestNode(
            name="HTTP Client Timeout",
            node_id="http_client_timeout",
            url="https://httpbin.org/delay/3",
            method="GET",
            timeout=1,  # 1 second timeout for a 3 second response
        )
    )

    print(f"  Request timed out: {timeout_result.get('timeout', False)}")
    print(f"  Success flag: {timeout_result.get('success', False)}")

    return {
        "not_found": not_found_result,
        "retry": retry_result,
        "timeout": timeout_result,
    }


def example_7_complex_workflow():
    """Example 7: Complex multi-API workflow."""
    section_header("Example 7: Complex Multi-API Workflow")

    # Execute the workflow
    runtime = LocalRuntime()

    print("\n1. Multi-step API workflow:")
    print("   Step 1: Fetch user information")
    print("   Step 2: Fetch user's posts")
    print("   Step 3: Fetch comments for first post")

    # For demonstration, we'll execute step by step

    # Step 1: Get user
    user_result = runtime.execute_node(
        RESTClientNode(
            name="REST Client - User",
            node_id="user_api",
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{id}",
            path_params={"id": 1},
            method="GET",
        )
    )

    user = user_result["data"]
    print(f"\n2. User: {user['name']} ({user['email']})")

    # Step 2: Get user's posts
    posts_result = runtime.execute_node(
        RESTClientNode(
            name="REST Client - Posts",
            node_id="posts_api",
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{userId}/posts",
            path_params={"userId": user["id"]},
            method="GET",
        )
    )

    posts = posts_result["data"]
    print(f"3. Found {len(posts)} posts by {user['name']}")

    # Step 3: Get comments for first post
    if posts:
        comments_result = runtime.execute_node(
            RESTClientNode(
                name="REST Client - Comments",
                node_id="comments_api",
                base_url="https://jsonplaceholder.typicode.com",
                resource="posts/{postId}/comments",
                path_params={"postId": posts[0]["id"]},
                method="GET",
            )
        )

        comments = comments_result["data"]
        print(f"4. First post: '{posts[0]['title']}'")
        print(f"5. Comments on first post: {len(comments)}")
        print(f"6. Sample comment: '{comments[0]['name']}' by {comments[0]['email']}")

    return {
        "user": user_result,
        "posts": posts_result,
        "comments": comments_result if posts else None,
    }


async def example_8_async_execution():
    """Example 8: Asynchronous API execution for performance."""
    section_header("Example 8: Asynchronous API Execution")

    # Create rate limiting for async calls
    rate_config = RateLimitConfig(
        max_requests=5, time_window=5.0, strategy="sliding_window"
    )

    # Execute the workflow
    runtime = AsyncLocalRuntime()

    print("\n1. Making concurrent API calls asynchronously:")

    # Start timing
    start_time = time.time()

    # Create multiple concurrent requests
    tasks = []

    # Prepare URLs for HTTP requests
    urls = [
        "https://jsonplaceholder.typicode.com/posts/1",
        "https://jsonplaceholder.typicode.com/posts/2",
        "https://jsonplaceholder.typicode.com/posts/3",
        "https://jsonplaceholder.typicode.com/posts/4",
        "https://jsonplaceholder.typicode.com/posts/5",
    ]

    # Create tasks for HTTP requests
    for i, url in enumerate(urls):
        task = runtime.execute_node_async(
            AsyncHTTPRequestNode(
                name=f"Async HTTP Client {i+1}",
                node_id=f"async_http_{i+1}",
                url=url,
                method="GET",
            )
        )
        tasks.append(task)

    # Create tasks for REST requests with rate limiting
    for i in range(1, 6):
        # Create a fresh node for each request
        async_rest = AsyncRESTClientNode(
            name=f"Async REST Client {i}",
            base_url="https://jsonplaceholder.typicode.com",
            resource="posts/{id}",
            path_params={"id": i},
            method="GET",
        )

        rate_limited_async = AsyncRateLimitedAPINode(
            wrapped_node=async_rest,
            rate_limit_config=rate_config,
            name=f"Rate Limited Async API {i}",
            node_id=f"rate_limited_async_{i}",
        )

        task = runtime.execute_node_async(rate_limited_async)
        tasks.append(task)

    # Wait for all requests to complete
    results = await asyncio.gather(*tasks)

    # End timing
    end_time = time.time()

    print(f"  Completed {len(results)} requests in {end_time - start_time:.2f} seconds")
    print(
        f"  Average time per request: {(end_time - start_time) / len(results):.2f} seconds"
    )

    # Show first few results
    print("\n2. Sample results:")
    for i, result in enumerate(results[:3]):
        if "response" in result:  # HTTP request
            print(f"  HTTP Result {i+1}: Status {result['status_code']}")
        else:  # REST request
            print(f"  REST Result {i+1}: Title '{result['data']['title'][:30]}...'")

    print("\n3. Benefits of async execution:")
    print("  - Significantly faster execution for multiple API calls")
    print("  - Reduced total execution time by running requests concurrently")
    print("  - Maintains rate limiting to avoid overwhelming APIs")
    print("  - Better resource utilization during I/O-bound operations")

    return results


def main():
    """Execute API integration examples."""
    print("Kailash SDK - API Integration Examples")
    print("==================================================")

    try:
        # Only run the fixed example for now
        example_1_basic_http_requests()

        print("\n" + "=" * 70)
        print(" Example completed successfully!")
        print("=" * 70)

        print("\nKey takeaways:")
        print("- The Kailash SDK provides comprehensive API integration capabilities")
        print("- Support for HTTP, REST, and GraphQL requests")
        print("- Multiple authentication methods (Basic, OAuth2, API Key)")
        print("- Both synchronous and asynchronous execution")

    except Exception as e:
        logger.error(f"Error running examples: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
