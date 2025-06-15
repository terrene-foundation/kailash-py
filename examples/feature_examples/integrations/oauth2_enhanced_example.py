"""Example demonstrating OAuth2Node enhanced token output.

This example shows the enhanced OAuth2Node output that includes additional
metadata for better token lifecycle management and debugging.
"""

import os
import sys
import time
from datetime import datetime, timezone

# Add the src directory to Python path
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
    ),
)

from kailash.nodes.api.auth import OAuth2Node
from kailash.nodes.api.http import HTTPRequestNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def demonstrate_oauth2_enhanced_output():
    """Demonstrate the enhanced OAuth2 token output."""
    print("🔐 OAuth2Node Enhanced Output Demo")
    print("=" * 50)

    # Note: This example uses a mock token endpoint for demonstration
    # In production, use actual OAuth2 provider endpoints

    # Create OAuth2Node with mock configuration
    oauth_node = OAuth2Node(
        token_url="https://oauth2.example.com/token",  # Mock endpoint
        client_id="demo_client_id",
        client_secret="demo_client_secret",
        grant_type="client_credentials",
        scope="read write admin",
    )

    print("\n📝 OAuth2 Configuration:")
    print("   Token URL: https://oauth2.example.com/token")
    print("   Client ID: demo_client_id")
    print("   Grant Type: client_credentials")
    print("   Scope: read write admin")

    # Since we're using a mock endpoint, we'll simulate the response
    # In real usage, the node would make an actual HTTP request
    print("\n⚠️  Note: Using simulated responses for demonstration")

    # Simulate different token scenarios
    scenarios = [
        {
            "name": "Standard Token Response",
            "mock_response": {
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.mock_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read write",
                "refresh_token": "refresh_token_12345",
            },
        },
        {
            "name": "Token Without Refresh",
            "mock_response": {
                "access_token": "simple_access_token_67890",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": "read",
            },
        },
        {
            "name": "Custom Token Type",
            "mock_response": {
                "access_token": "custom_token_abc123",
                "token_type": "MAC",
                "expires_in": 1800,
                "scope": "admin",
                "custom_field": "custom_value",
            },
        },
    ]

    for scenario in scenarios:
        print(f"\n\n🔄 Scenario: {scenario['name']}")
        print("-" * 40)

        # Simulate token response
        oauth_node.token_data = scenario["mock_response"]
        oauth_node.token_expires_at = (
            time.time() + scenario["mock_response"]["expires_in"]
        )

        # Get enhanced output (without include_raw_response)
        result = oauth_node.execute(include_raw_response=False)

        print("\n📊 Standard Output:")
        print(f"   Headers: {result['headers']}")
        print(f"   Auth Type: {result['auth_type']}")
        print(f"   Token Type: {result['token_type']}")
        print(f"   Expires In: {result['expires_in']} seconds")
        print(f"   Scope: {result['scope']}")
        print(f"   Refresh Token Present: {result['refresh_token_present']}")
        print(f"   Token Expires At: {result['token_expires_at']}")

        # Get enhanced output with raw response
        result_with_raw = oauth_node.execute(include_raw_response=True)

        print("\n📊 Output with Raw Response:")
        if "raw_response" in result_with_raw:
            print(
                f"   Raw Response Keys: {list(result_with_raw['raw_response'].keys())}"
            )
            if "custom_field" in result_with_raw["raw_response"]:
                print(
                    f"   Custom Field: {result_with_raw['raw_response']['custom_field']}"
                )

    # Demonstrate token expiration handling
    print("\n\n🕐 Token Expiration Demonstration:")
    print("-" * 40)

    # Set token to expire in 5 seconds
    oauth_node.token_data = {
        "access_token": "expiring_token_123",
        "token_type": "Bearer",
        "expires_in": 5,
        "scope": "read",
    }
    oauth_node.token_expires_at = time.time() + 5

    # Check token before expiration
    result = oauth_node.execute()
    print(f"\n✅ Token valid - Expires in: {result['expires_in']} seconds")
    print(f"   Expiration time: {result['token_expires_at']}")

    # Wait for token to expire
    print("\n⏳ Waiting 6 seconds for token to expire...")
    time.sleep(6)

    # Check token after expiration (auto_refresh is True by default)
    # In real usage, this would trigger a token refresh
    result = oauth_node.execute()
    print(f"\n🔄 After expiration - Expires in: {result['expires_in']} seconds")
    print("   (In production, this would trigger automatic token refresh)")


def demonstrate_oauth2_workflow():
    """Demonstrate OAuth2 in a workflow context."""
    print("\n\n🔄 OAuth2 Workflow Demo")
    print("=" * 50)

    # Create workflow
    workflow = Workflow(workflow_id="oauth2_api_workflow", name="OAuth2 API Workflow")

    # Add OAuth2 node
    workflow.add_node(
        "oauth",
        OAuth2Node(
            token_url="https://api.example.com/oauth/token",
            client_id="workflow_client",
            client_secret="workflow_secret",
            grant_type="client_credentials",
            scope="api.read api.write",
        ),
    )

    # Add HTTP request node that uses the OAuth token
    workflow.add_node(
        "api_request", HTTPRequestNode(url="https://api.example.com/data", method="GET")
    )

    # Connect OAuth headers to HTTP request
    workflow.connect("oauth", "api_request", {"headers": "headers"})

    print("✅ Created OAuth2 workflow")
    print(f"   Nodes: {list(workflow.nodes.keys())}")
    print("   Connections: oauth → api_request (headers)")

    # Workflow visualization
    print("\n📊 Workflow Structure:")
    print("   [OAuth2Node] → headers → [HTTPRequestNode]")
    print("        ↓                          ↓")
    print("   Token + Metadata          API Response")


def demonstrate_token_lifecycle():
    """Demonstrate complete token lifecycle management."""
    print("\n\n🔄 Token Lifecycle Management Demo")
    print("=" * 50)

    # Simulate token lifecycle events
    lifecycle_events = [
        ("Initial Token Request", "success", 3600),
        ("Token Refresh (Before Expiry)", "refresh", 3600),
        ("Token Refresh (After Expiry)", "expired_refresh", 3600),
        ("Invalid Refresh Token", "invalid_refresh", 0),
        ("Rate Limited", "rate_limit", 0),
    ]

    for event_name, event_type, new_expiry in lifecycle_events:
        print(f"\n📌 Event: {event_name}")
        print("-" * 30)

        if event_type == "success":
            print("✅ Successfully obtained new access token")
            print(f"   Token: eyJ0eXAiOiJKV1QiL...{event_type}")
            print("   Type: Bearer")
            print(f"   Expires in: {new_expiry} seconds")
            print(f"   Expiry: {(datetime.now(timezone.utc).timestamp() + new_expiry)}")

        elif event_type == "refresh":
            print("🔄 Refreshing token before expiration")
            print("   Using refresh_token to get new access_token")
            print(f"   New token expires in: {new_expiry} seconds")

        elif event_type == "expired_refresh":
            print("⏰ Token expired, attempting refresh")
            print("   Current token is expired")
            print("   Using refresh_token to get new access_token")
            print(f"   New token expires in: {new_expiry} seconds")

        elif event_type == "invalid_refresh":
            print("❌ Refresh token is invalid or expired")
            print("   Need to re-authenticate with credentials")
            print("   Falling back to client_credentials grant")

        elif event_type == "rate_limit":
            print("🚫 Rate limit exceeded")
            print("   Retry after: 60 seconds")
            print("   Consider implementing exponential backoff")


def main():
    """Run all OAuth2 demonstrations."""
    try:
        # Demonstrate enhanced output
        demonstrate_oauth2_enhanced_output()

        # Demonstrate workflow usage
        demonstrate_oauth2_workflow()

        # Demonstrate token lifecycle
        demonstrate_token_lifecycle()

        print("\n\n✅ All OAuth2 demonstrations completed!")

        # Summary of enhancements
        print("\n📋 OAuth2Node Enhancement Summary:")
        print("-" * 50)
        print("✅ token_type: Extracted from response (Bearer, MAC, etc.)")
        print("✅ scope: Actual granted scopes from server")
        print("✅ refresh_token_present: Boolean flag for refresh capability")
        print("✅ token_expires_at: ISO format timestamp for precise expiry")
        print("✅ raw_response: Optional full response for debugging")
        print("✅ Auto-refresh: Automatic token renewal on expiration")
        print("✅ Enhanced headers: Support for different token types")

    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
