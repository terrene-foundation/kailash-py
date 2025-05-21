"""
Example demonstrating the API integration capabilities of the Kailash SDK.

This example shows how to use the various API integration nodes:
- HTTPRequestNode for basic HTTP requests
- RESTClientNode for REST API integration
- GraphQLClientNode for GraphQL API calls
- Authentication nodes (BasicAuth, OAuth2, APIKey)
- Async versions of all nodes

The example uses public APIs for demonstration.
"""

import asyncio
import logging
from pprint import pprint

from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.nodes.api import (
    HTTPRequestNode, AsyncHTTPRequestNode,
    RESTClientNode, AsyncRESTClientNode,
    GraphQLClientNode, AsyncGraphQLClientNode,
    APIKeyNode
)
from kailash.nodes.transform import DataFilterNode


def basic_http_request_example():
    """Example using the basic HTTPRequestNode."""
    print("\n=== Basic HTTP Request Example ===")
    
    # Create a workflow with a single HTTP request node
    workflow = Workflow(name="http_request_example")
    
    # Add an HTTP request node to fetch data from a public API
    http_node = HTTPRequestNode(
        id="http_request",
        name="HTTP GET Request",
        url="https://jsonplaceholder.typicode.com/users",
        method="GET",
        response_format="json"
    )
    workflow.add_node(http_node, "http_request")
    
    # Execute the workflow
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow)
    
    # Print the results
    print(f"Status code: {results['http_request']['status_code']}")
    print(f"Success: {results['http_request']['success']}")
    print(f"Number of users: {len(results['http_request']['response']['content'])}")
    print(f"First user: {results['http_request']['response']['content'][0]['name']}")
    
    return results


def rest_api_example():
    """Example using the RESTClientNode."""
    print("\n=== REST API Example ===")
    
    # Create a workflow
    workflow = Workflow(name="rest_api_example")
    
    # Add a REST client node to fetch a specific user
    rest_node = RESTClientNode(
        id="get_user",
        name="Get User",
        base_url="https://jsonplaceholder.typicode.com",
        resource="users/{id}",
        method="GET",
        path_params={"id": 3}
    )
    workflow.add_node(rest_node, "get_user")
    
    # Add a REST client node to fetch user's posts
    posts_node = RESTClientNode(
        id="get_posts",
        name="Get User Posts",
        base_url="https://jsonplaceholder.typicode.com",
        resource="users/{id}/posts",
        method="GET"
    )
    workflow.add_node(posts_node, "get_posts")
    
    # Connect the nodes - pass user ID from first node to second
    workflow.connect(
        "get_user", 
        "get_posts",
        {"data.id": "path_params.id"}
    )
    
    # Execute the workflow
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow)
    
    # Print the results
    user = results["get_user"]["data"]
    posts = results["get_posts"]["data"]
    
    print(f"User: {user['name']} ({user['email']})")
    print(f"Number of posts: {len(posts)}")
    print(f"First post title: {posts[0]['title']}")
    
    return results


def graphql_api_example():
    """Example using the GraphQLClientNode."""
    print("\n=== GraphQL API Example ===")
    
    # Create a workflow
    workflow = Workflow(name="graphql_api_example")
    
    # Add a GraphQL client node to query the SpaceX API
    graphql_node = GraphQLClientNode(
        id="spacex_query",
        name="SpaceX GraphQL Query",
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
        """
    )
    workflow.add_node(graphql_node, "spacex_query")
    
    # Execute the workflow
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow)
    
    # Print the results
    data = results["spacex_query"]["data"]
    company = data["company"]
    rockets = data["rockets"]
    
    print(f"Company: {company['name']}")
    print(f"Founded: {company['founded']} by {company['founder']}")
    print(f"Employees: {company['employees']}")
    print("\nRockets:")
    for rocket in rockets:
        print(f"  - {rocket['name']} (First flight: {rocket['first_flight']}, "
              f"Success rate: {rocket['success_rate_pct']}%)")
    
    return results


def api_key_auth_example():
    """Example using APIKeyNode with a REST client."""
    print("\n=== API Key Authentication Example ===")
    
    # Create a workflow
    workflow = Workflow(name="api_key_auth_example")
    
    # Add an API key node (using a dummy key for public API that doesn't need auth)
    api_key_node = APIKeyNode(
        id="api_key",
        name="API Key",
        api_key="YOUR_API_KEY",
        location="header",
        param_name="X-API-Key"
    )
    workflow.add_node(api_key_node, "api_key")
    
    # Add a REST client node that uses the API key
    rest_node = RESTClientNode(
        id="weather_api",
        name="Weather API",
        base_url="https://jsonplaceholder.typicode.com",  # Using placeholder as example
        resource="todos",
        method="GET",
    )
    workflow.add_node(rest_node, "weather_api")
    
    # Connect the auth node to the REST node
    workflow.connect(
        "api_key", 
        "weather_api",
        {"headers": "headers"}
    )
    
    # Execute the workflow
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow)
    
    # Print the results
    data = results["weather_api"]["data"]
    print(f"Received {len(data)} todos")
    print(f"First todo: {data[0]['title']}")
    print(f"Auth headers used: {results['api_key']['headers']}")
    
    return results


async def async_api_example():
    """Example using asynchronous API nodes."""
    print("\n=== Asynchronous API Example ===")
    
    # Create a workflow
    workflow = Workflow(name="async_api_example")
    
    # Add multiple async HTTP request nodes
    users_node = AsyncHTTPRequestNode(
        id="get_users",
        name="Get Users",
        url="https://jsonplaceholder.typicode.com/users",
        method="GET"
    )
    workflow.add_node(users_node, "get_users")
    
    posts_node = AsyncHTTPRequestNode(
        id="get_posts",
        name="Get Posts",
        url="https://jsonplaceholder.typicode.com/posts",
        method="GET"
    )
    workflow.add_node(posts_node, "get_posts")
    
    comments_node = AsyncHTTPRequestNode(
        id="get_comments",
        name="Get Comments",
        url="https://jsonplaceholder.typicode.com/comments",
        method="GET"
    )
    workflow.add_node(comments_node, "get_comments")
    
    # Execute the workflow asynchronously
    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_async(workflow)
    
    # Print the results
    print(f"Users: {len(results['get_users']['response']['content'])}")
    print(f"Posts: {len(results['get_posts']['response']['content'])}")
    print(f"Comments: {len(results['get_comments']['response']['content'])}")
    
    return results


def main():
    """Run all examples."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Run the examples
        basic_http_request_example()
        rest_api_example()
        graphql_api_example()
        api_key_auth_example()
        
        # Run the async example using asyncio
        asyncio.run(async_api_example())
        
        print("\nAll examples completed successfully!")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        raise


if __name__ == "__main__":
    main()