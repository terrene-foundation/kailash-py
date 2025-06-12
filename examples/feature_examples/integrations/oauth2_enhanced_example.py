"""Example demonstrating the enhanced OAuth2Node features.

This example shows how to use the OAuth2Node with its enhanced features including:
- Structured token output for easier consumption
- Automatic token refresh with configurable buffer
- Token health monitoring
- Better error handling with suggestions
"""

import json
import time
from typing import Dict, Any

from kailash import setup_logging
from kailash.nodes.api import OAuth2Node, HTTPRequestNode
from kailash.workflow import Workflow


def create_oauth2_workflow() -> Workflow:
    """Create a workflow demonstrating enhanced OAuth2 features."""
    workflow = Workflow(name="oauth2_enhanced_workflow")
    
    # Add OAuth2 node with enhanced features
    workflow.add_node(
        "oauth_auth",
        OAuth2Node(
            # Basic OAuth configuration
            token_url="https://oauth.example.com/token",
            client_id="your-client-id",
            client_secret="your-client-secret",
            grant_type="client_credentials",
            scope="read:data write:data",
            
            # Enhanced features
            refresh_buffer_seconds=300,  # Refresh 5 minutes before expiry
            validate_token_response=True,  # Validate token structure
            include_token_metadata=True,  # Include structured token output
            auto_refresh=True,  # Automatically refresh expired tokens
        )
    )
    
    # Add HTTP request node to use the token
    workflow.add_node(
        "api_call",
        HTTPRequestNode(
            url="https://api.example.com/data",
            method="GET",
        )
    )
    
    # Connect nodes - pass headers from OAuth to HTTP
    workflow.connect("oauth_auth", "api_call", mapping={"headers": "headers"})
    
    return workflow


def demonstrate_token_structure():
    """Demonstrate the structured token output."""
    print("\n=== OAuth2 Enhanced Token Structure ===")
    
    # Create a mock OAuth2Node for demonstration
    oauth_node = OAuth2Node(
        token_url="https://oauth.example.com/token",
        client_id="demo-client",
        include_token_metadata=True,
    )
    
    # Mock response for demonstration
    mock_result = {
        "headers": {"Authorization": "Bearer abc123..."},
        "auth_type": "oauth2",
        "expires_in": 3300,  # 55 minutes
        "token_type": "Bearer",
        "scope": "read:data write:data",
        "refresh_token_present": True,
        "token_expires_at": "2025-01-12T15:30:00Z",
        "token": {
            "access_token": "abc123...",
            "token_type": "Bearer",
            "expires_in": 3300,
            "expires_at": "2025-01-12T15:30:00Z",
            "issued_at": "2025-01-12T14:35:00Z",
            "scope": "read:data write:data",
            "is_valid": True,
            "has_refresh_token": True,
            "refresh_token_hint": "...7890",
            "headers": {"Authorization": "Bearer abc123..."}
        },
        "metadata": {
            "health": {
                "status": "healthy",
                "expires_in_seconds": 3300,
                "expires_in_minutes": 55.0,
                "expires_in_human": "55 minutes",
                "should_refresh": False,
                "health_percentage": 91.7
            },
            "grant_type": "client_credentials",
            "token_endpoint": "https://oauth.example.com/token",
            "scopes_requested": ["read:data", "write:data"],
            "scopes_granted": ["read:data", "write:data"],
            "token_size_bytes": 256,
            "response_fields": ["access_token", "token_type", "expires_in", "scope"],
            "last_request_duration_ms": 243
        }
    }
    
    print(json.dumps(mock_result, indent=2))
    
    # Show how to use the structured output
    print("\n=== Using Structured Token Output ===")
    print(f"Token is valid: {mock_result['token']['is_valid']}")
    print(f"Health status: {mock_result['metadata']['health']['status']}")
    print(f"Expires in: {mock_result['metadata']['health']['expires_in_human']}")
    print(f"Should refresh: {mock_result['metadata']['health']['should_refresh']}")
    print(f"Ready-to-use headers: {mock_result['token']['headers']}")


def demonstrate_auto_refresh():
    """Demonstrate automatic token refresh behavior."""
    print("\n=== OAuth2 Auto-Refresh Behavior ===")
    
    # Show different health statuses based on expiration
    scenarios = [
        {"expires_in": 7200, "expected": "healthy", "description": "2 hours remaining"},
        {"expires_in": 600, "expected": "warning", "description": "10 minutes remaining"},
        {"expires_in": 250, "expected": "needs_refresh", "description": "Within refresh buffer (5 min)"},
        {"expires_in": 30, "expected": "critical", "description": "30 seconds remaining"},
        {"expires_in": 0, "expected": "expired", "description": "Token expired"},
    ]
    
    for scenario in scenarios:
        print(f"\nScenario: {scenario['description']}")
        print(f"  Expires in: {scenario['expires_in']} seconds")
        print(f"  Health status: {scenario['expected']}")
        print(f"  Auto-refresh will trigger: {'Yes' if scenario['expires_in'] <= 300 else 'No'}")


def demonstrate_error_handling():
    """Demonstrate enhanced error messages with suggestions."""
    print("\n=== OAuth2 Enhanced Error Handling ===")
    
    error_scenarios = [
        {
            "error": "401 Unauthorized",
            "suggestions": [
                "- Verify your client_id and client_secret are correct",
                "- Check if your credentials have the required permissions"
            ]
        },
        {
            "error": "400 Bad Request",
            "suggestions": [
                "- Verify the grant_type is supported by your OAuth server",
                "- Check if all required parameters are provided"
            ]
        },
        {
            "error": "Connection timeout",
            "suggestions": [
                "- Verify the token_url is correct and accessible",
                "- Check your network connection and firewall settings"
            ]
        }
    ]
    
    for scenario in error_scenarios:
        print(f"\nError: {scenario['error']}")
        print("Suggestions:")
        for suggestion in scenario['suggestions']:
            print(f"  {suggestion}")


def main():
    """Run the OAuth2 enhanced features demonstration."""
    setup_logging()
    
    print("OAuth2Node Enhanced Features Demonstration")
    print("=" * 50)
    
    # Demonstrate token structure
    demonstrate_token_structure()
    
    # Demonstrate auto-refresh behavior
    demonstrate_auto_refresh()
    
    # Demonstrate error handling
    demonstrate_error_handling()
    
    # Note about actual usage
    print("\n=== Actual Usage Example ===")
    print("""
# Create OAuth2 node with enhanced features
oauth_node = OAuth2Node(
    token_url="https://auth.example.com/token",
    client_id="my-client-id",
    client_secret="my-secret",
    grant_type="client_credentials",
    
    # Enhanced features
    refresh_buffer_seconds=300,  # Refresh 5 minutes before expiry
    validate_token_response=True,  # Validate token structure
    include_token_metadata=True,  # Get structured output
)

# Get token with structured output
result = oauth_node.run()

# Access token health
if result["metadata"]["health"]["status"] == "healthy":
    headers = result["headers"]
    # Use headers in API requests
    
# Monitor token health
print(f"Token expires in: {result['metadata']['health']['expires_in_human']}")
print(f"Should refresh: {result['metadata']['health']['should_refresh']}")
""")


if __name__ == "__main__":
    main()