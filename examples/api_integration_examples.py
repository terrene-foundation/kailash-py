#!/usr/bin/env python3
"""
API Integration Examples for Kailash SDK

This module demonstrates various API integration patterns using the Kailash SDK's
built-in API nodes. It covers common scenarios like REST APIs, GraphQL APIs,
authentication, rate limiting, and error handling.

Examples included:
1. Basic REST API calls with different authentication methods
2. GraphQL API integration
3. Rate limiting for API calls
4. OAuth 2.0 authentication flow
5. Complex workflow with multiple API integrations
6. Error handling and retry strategies
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any

# Kailash SDK imports
from kailash.workflow import Workflow
from kailash.nodes.api import (
    HTTPRequestNode,
    AsyncHTTPRequestNode,
    RESTClientNode,
    AsyncRESTClientNode,
    GraphQLClientNode,
    AsyncGraphQLClientNode,
    BasicAuthNode,
    OAuth2Node,
    APIKeyNode,
    RateLimitConfig,
    RateLimitedAPINode,
    AsyncRateLimitedAPINode,
)
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.transform import FilterRowsNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def example_1_basic_rest_api():
    """Example 1: Basic REST API calls with different authentication methods."""
    print("\n" + "="*60)
    print("Example 1: Basic REST API Integration")
    print("="*60)
    
    # Create a workflow
    workflow = Workflow(name="basic_rest_api_example")
    
    # Add a basic HTTP request node
    http_node = HTTPRequestNode(node_id="fetch_user")
    
    # Add a REST client node with API key authentication
    api_key_auth = APIKeyNode(node_id="api_key_auth")
    rest_node = RESTClientNode(node_id="fetch_posts")
    
    # Add nodes to workflow
    workflow.add_node(http_node)
    workflow.add_node(api_key_auth)
    workflow.add_node(rest_node)
    
    # Create connections
    workflow.connect(
        "api_key_auth", "fetch_posts",
        {"headers": "headers"}
    )
    
    # Execute the workflow
    runtime = LocalRuntime()
    
    try:
        # First, demonstrate basic HTTP request
        print("\n1. Basic HTTP GET request to JSONPlaceholder API:")
        http_result = runtime.execute_node(
            http_node,
            url="https://jsonplaceholder.typicode.com/users/1",
            method="GET"
        )
        
        user_data = http_result["response"]["content"]
        print(f"   User: {user_data.get('name')} ({user_data.get('email')})")
        print(f"   Status: {http_result['status_code']}")
        
        # Demonstrate API key authentication
        print("\n2. API Key authentication setup:")
        auth_result = runtime.execute_node(
            api_key_auth,
            api_key="your-api-key-here",
            location="header",
            param_name="X-API-Key"
        )
        print(f"   Auth headers: {auth_result['headers']}")
        
        # Demonstrate REST client with resource patterns
        print("\n3. REST client with resource patterns:")
        rest_result = runtime.execute_node(
            rest_node,
            base_url="https://jsonplaceholder.typicode.com",
            resource="posts/{id}",
            path_params={"id": 1},
            method="GET",
            headers=auth_result["headers"]
        )
        
        post_data = rest_result["data"]
        print(f"   Post title: {post_data.get('title')}")
        print(f"   Success: {rest_result['success']}")
        
    except Exception as e:
        print(f"Error in example 1: {e}")


def example_2_graphql_integration():
    """Example 2: GraphQL API integration."""
    print("\n" + "="*60)
    print("Example 2: GraphQL API Integration")
    print("="*60)
    
    # Create GraphQL client
    graphql_node = GraphQLClientNode(node_id="graphql_query")
    
    runtime = LocalRuntime()
    
    try:
        # Example GraphQL query (using a public GraphQL API)
        query = """
        query GetCountries($first: Int!) {
            countries(first: $first) {
                name
                code
                capital
                currency
            }
        }
        """
        
        print("\n1. GraphQL query to Countries API:")
        result = runtime.execute_node(
            graphql_node,
            endpoint="https://countries.trevorblades.com/",
            query=query,
            variables={"first": 3},
            flatten_response=True
        )
        
        if result["success"]:
            countries = result["data"]
            print(f"   Retrieved {len(countries)} countries:")
            for country in countries:
                print(f"   - {country['name']} ({country['code']})")
        else:
            print(f"   GraphQL errors: {result['errors']}")
        
    except Exception as e:
        print(f"Error in example 2: {e}")


def example_3_rate_limiting():
    """Example 3: Rate limiting for API calls."""
    print("\n" + "="*60)
    print("Example 3: Rate Limiting")
    print("="*60)
    
    # Create rate limit configuration
    rate_config = RateLimitConfig(
        max_requests=3,           # 3 requests
        time_window=10.0,         # per 10 seconds
        strategy="token_bucket",  # using token bucket algorithm
        burst_limit=5,            # allow burst of up to 5 requests
        backoff_factor=1.5        # increase wait time by 1.5x on each retry
    )
    
    # Create a basic HTTP node
    http_node = HTTPRequestNode(node_id="api_call")
    
    # Wrap it with rate limiting
    rate_limited_node = RateLimitedAPINode(
        wrapped_node=http_node,
        rate_limit_config=rate_config,
        node_id="rate_limited_api"
    )
    
    runtime = LocalRuntime()
    
    print(f"\n1. Rate limiting config: {rate_config.max_requests} requests per {rate_config.time_window}s")
    print("2. Making rapid API calls to demonstrate rate limiting:")
    
    try:
        for i in range(6):  # Try to make 6 requests (more than limit)
            print(f"\n   Request {i+1}:")
            start_time = time.time()
            
            result = runtime.execute_node(
                rate_limited_node,
                url="https://jsonplaceholder.typicode.com/posts/1",
                method="GET"
            )
            
            end_time = time.time()
            metadata = result.get("rate_limit_metadata", {})
            
            print(f"     Status: {result['status_code']}")
            print(f"     Attempts: {metadata.get('attempts', 1)}")
            print(f"     Wait time: {metadata.get('total_wait_time', 0):.2f}s")
            print(f"     Total time: {end_time - start_time:.2f}s")
            
    except Exception as e:
        print(f"Error in example 3: {e}")


def example_4_oauth2_authentication():
    """Example 4: OAuth 2.0 authentication flow."""
    print("\n" + "="*60)
    print("Example 4: OAuth 2.0 Authentication")
    print("="*60)
    
    # Create OAuth2 node for client credentials flow
    oauth_node = OAuth2Node(node_id="oauth_auth")
    
    runtime = LocalRuntime()
    
    print("\n1. OAuth 2.0 Client Credentials Flow (simulated):")
    
    try:
        # Note: This is a demonstration with mock credentials
        # In a real scenario, you would use actual OAuth provider credentials
        print("   Setting up OAuth client with mock credentials...")
        print("   Grant type: client_credentials")
        print("   Client ID: demo-client-id")
        print("   Scope: api:read api:write")
        
        # For demonstration purposes, we'll show the configuration
        # In a real implementation, this would make an actual OAuth request
        config_demo = {
            "token_url": "https://your-oauth-provider.com/oauth/token",
            "client_id": "demo-client-id",
            "client_secret": "demo-client-secret",
            "grant_type": "client_credentials",
            "scope": "api:read api:write"
        }
        
        print(f"   Configuration: {json.dumps(config_demo, indent=4)}")
        print("   Note: This example shows the OAuth setup. In practice, this would")
        print("         make a real request to get an access token.")
        
    except Exception as e:
        print(f"Error in example 4: {e}")


def example_5_complex_api_workflow():
    """Example 5: Complex workflow with multiple API integrations."""
    print("\n" + "="*60)
    print("Example 5: Complex Multi-API Workflow")
    print("="*60)
    
    # Create a workflow that:
    # 1. Fetches user data from one API
    # 2. Uses that data to query another API
    # 3. Processes and combines the results
    
    workflow = Workflow(name="complex_api_workflow")
    
    # Add nodes
    user_api = RESTClientNode(node_id="fetch_user")
    posts_api = RESTClientNode(node_id="fetch_posts")
    filter_node = FilterRowsNode(node_id="filter_posts")
    
    workflow.add_node(user_api)
    workflow.add_node(posts_api)
    workflow.add_node(filter_node)
    
    # Connect nodes
    workflow.connect(
        "fetch_user", "fetch_posts",
        {"data": "user_data"}
    )
    workflow.connect(
        "fetch_posts", "filter_posts",
        {"data": "posts_data"}
    )
    
    runtime = LocalRuntime()
    
    print("\n1. Multi-step API workflow:")
    print("   Step 1: Fetch user information")
    print("   Step 2: Fetch user's posts")
    print("   Step 3: Filter and process posts")
    
    try:
        # Execute step by step for demonstration
        print("\n2. Executing workflow steps:")
        
        # Step 1: Get user
        user_result = runtime.execute_node(
            user_api,
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{id}",
            path_params={"id": 1},
            method="GET"
        )
        
        user = user_result["data"]
        print(f"   User: {user['name']} ({user['email']})")
        
        # Step 2: Get user's posts
        posts_result = runtime.execute_node(
            posts_api,
            base_url="https://jsonplaceholder.typicode.com",
            resource="users/{userId}/posts",
            path_params={"userId": user["id"]},
            method="GET"
        )
        
        posts = posts_result["data"]
        print(f"   Found {len(posts)} posts by {user['name']}")
        
        # Show first post title
        if posts:
            print(f"   First post: '{posts[0]['title']}'")
        
    except Exception as e:
        print(f"Error in example 5: {e}")


async def example_6_async_api_calls():
    """Example 6: Asynchronous API calls for better performance."""
    print("\n" + "="*60)
    print("Example 6: Asynchronous API Integration")
    print("="*60)
    
    # Create async API nodes
    async_http = AsyncHTTPRequestNode(node_id="async_http")
    async_rest = AsyncRESTClientNode(node_id="async_rest")
    
    # Create rate limiting for async calls
    rate_config = RateLimitConfig(
        max_requests=5,
        time_window=5.0,
        strategy="sliding_window"
    )
    
    rate_limited_async = AsyncRateLimitedAPINode(
        wrapped_node=async_rest,
        rate_limit_config=rate_config,
        node_id="rate_limited_async"
    )
    
    runtime = AsyncLocalRuntime()
    
    print("\n1. Making concurrent API calls asynchronously:")
    
    try:
        # Create multiple concurrent requests
        tasks = []
        urls = [
            "https://jsonplaceholder.typicode.com/posts/1",
            "https://jsonplaceholder.typicode.com/posts/2",
            "https://jsonplaceholder.typicode.com/posts/3",
            "https://jsonplaceholder.typicode.com/posts/4",
            "https://jsonplaceholder.typicode.com/posts/5"
        ]
        
        start_time = time.time()
        
        for i, url in enumerate(urls):
            task = runtime.execute_node_async(
                rate_limited_async,
                base_url="https://jsonplaceholder.typicode.com",
                resource="posts/{id}",
                path_params={"id": i + 1},
                method="GET"
            )
            tasks.append(task)
        
        # Wait for all requests to complete
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        
        print(f"   Completed {len(results)} requests in {end_time - start_time:.2f} seconds")
        
        # Show results
        for i, result in enumerate(results):
            post = result["data"]
            metadata = result.get("rate_limit_metadata", {})
            print(f"   Post {i+1}: '{post['title'][:50]}...' (wait: {metadata.get('total_wait_time', 0):.2f}s)")
        
    except Exception as e:
        print(f"Error in example 6: {e}")


def example_7_error_handling():
    """Example 7: Error handling and retry strategies."""
    print("\n" + "="*60)
    print("Example 7: Error Handling and Retry Strategies")
    print("="*60)
    
    # Create HTTP node with retry configuration
    http_node = HTTPRequestNode(node_id="retry_example")
    
    runtime = LocalRuntime()
    
    print("\n1. Testing retry behavior with failing requests:")
    
    try:
        # Test with a URL that will likely fail
        print("   Attempting request to non-existent endpoint...")
        
        result = runtime.execute_node(
            http_node,
            url="https://jsonplaceholder.typicode.com/nonexistent",
            method="GET",
            retry_count=3,
            retry_backoff=0.5,
            timeout=5
        )
        
        print(f"   Status: {result['status_code']}")
        print(f"   Success: {result['success']}")
        
        if not result["success"]:
            response_content = result["response"]["content"]
            print(f"   Error response: {response_content}")
        
    except Exception as e:
        print(f"   Expected error occurred: {type(e).__name__}: {e}")
    
    print("\n2. Testing successful request after configuration:")
    try:
        # Test with a valid endpoint
        result = runtime.execute_node(
            http_node,
            url="https://jsonplaceholder.typicode.com/posts/1",
            method="GET",
            retry_count=3,
            retry_backoff=0.5
        )
        
        print(f"   Status: {result['status_code']}")
        print(f"   Success: {result['success']}")
        print(f"   Response time: {result['response']['response_time_ms']:.2f}ms")
        
    except Exception as e:
        print(f"Error in successful request: {e}")


def run_all_examples():
    """Run all API integration examples."""
    print("Kailash SDK - API Integration Examples")
    print("=====================================")
    print("This script demonstrates various API integration patterns")
    print("available in the Kailash SDK.")
    
    # Run synchronous examples
    example_1_basic_rest_api()
    example_2_graphql_integration()
    example_3_rate_limiting()
    example_4_oauth2_authentication()
    example_5_complex_api_workflow()
    example_7_error_handling()
    
    # Run async example
    print("\nRunning async example...")
    try:
        asyncio.run(example_6_async_api_calls())
    except Exception as e:
        print(f"Error in async example: {e}")
    
    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60)
    print("\nKey takeaways:")
    print("- The Kailash SDK provides comprehensive API integration capabilities")
    print("- Support for REST, GraphQL, and custom HTTP requests")
    print("- Multiple authentication methods (Basic, OAuth2, API Key)")
    print("- Built-in rate limiting with different strategies")
    print("- Both synchronous and asynchronous execution")
    print("- Robust error handling and retry mechanisms")


if __name__ == "__main__":
    run_all_examples()