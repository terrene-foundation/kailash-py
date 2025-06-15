"""Example demonstrating the CredentialTestingNode for testing authentication flows.

This example shows how to use the CredentialTestingNode to test various
credential scenarios without requiring actual external services.
"""

import os
import sys
import json

# Add the src directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")))

from kailash.nodes.testing import CredentialTestingNode
from kailash.nodes.api.auth import OAuth2Node, APIKeyNode, BasicAuthNode
from kailash.workflow import Workflow
from kailash.runtime.testing import SecurityTestHelper, CredentialMockData


def demonstrate_credential_testing_basics():
    """Demonstrate basic credential testing scenarios."""
    print("🧪 CredentialTestingNode Basic Demo")
    print("=" * 50)
    
    # Create testing node
    tester = CredentialTestingNode()
    
    # Test different credential types and scenarios
    test_cases = [
        ("OAuth2 - Success", "oauth2", "success", {}),
        ("OAuth2 - Expired", "oauth2", "expired", {}),
        ("OAuth2 - Invalid", "oauth2", "invalid", {}),
        ("API Key - Success", "api_key", "success", {"key_length": 32}),
        ("API Key - Invalid", "api_key", "invalid", {}),
        ("Basic Auth - Success", "basic", "success", {"username": "demo_user", "password": "demo_pass"}),
        ("JWT - Success", "jwt", "success", {"subject": "user123", "name": "Demo User"}),
        ("JWT - Expired", "jwt", "expired", {}),
    ]
    
    for test_name, cred_type, scenario, mock_data in test_cases:
        print(f"\n📝 Test: {test_name}")
        print("-" * 40)
        
        try:
            result = tester.execute(
                credential_type=cred_type,
                scenario=scenario,
                mock_data=mock_data,
                validation_rules={} if cred_type != "api_key" else {"key_length": 32}
            )
            
            print(f"   Valid: {'✅' if result['valid'] else '❌'}")
            
            if result['valid']:
                if 'credentials' in result:
                    print(f"   Credentials: {list(result['credentials'].keys())}")
                if 'headers' in result:
                    print(f"   Headers: {list(result['headers'].keys())}")
                if 'expires_at' in result:
                    print(f"   Expires: {result['expires_at']}")
            else:
                print(f"   Error: {result.get('error', 'Unknown error')}")
                if 'error_details' in result:
                    print(f"   Details: {result['error_details']}")
                    
        except Exception as e:
            print(f"   ❌ Exception: {e}")


def demonstrate_validation_rules():
    """Demonstrate credential validation with custom rules."""
    print("\n\n🔍 Credential Validation Demo")
    print("=" * 50)
    
    tester = CredentialTestingNode()
    
    # OAuth2 validation with scope requirements
    print("\n📝 OAuth2 Scope Validation:")
    print("-" * 40)
    
    oauth_rules = {
        "required_fields": ["access_token", "token_type", "scope"],
        "required_scopes": ["read", "write"],
        "token_format": "mock_"
    }
    
    # Test with sufficient scopes
    result = tester.execute(
        credential_type="oauth2",
        scenario="success",
        mock_data={"scope": "read write admin"},
        validation_rules=oauth_rules
    )
    print(f"✅ With all scopes: Valid = {result['valid']}")
    
    # Test with insufficient scopes
    result = tester.execute(
        credential_type="oauth2",
        scenario="success",
        mock_data={"scope": "read"},
        validation_rules=oauth_rules
    )
    print(f"❌ Missing scopes: Valid = {result['valid']}")
    if not result['valid']:
        print(f"   Error: {result.get('error')}")
    
    # API Key validation with length requirements
    print("\n📝 API Key Length Validation:")
    print("-" * 40)
    
    for key_length in [16, 32, 64]:
        result = tester.execute(
            credential_type="api_key",
            scenario="success",
            validation_rules={"key_length": key_length, "header_name": "X-API-Key"}
        )
        
        if result['valid']:
            actual_length = len(result['credentials']['api_key'])
            print(f"✅ Key length {key_length}: Generated key has {actual_length} chars")


def demonstrate_error_scenarios():
    """Demonstrate various error scenarios."""
    print("\n\n🚨 Error Scenario Testing Demo")
    print("=" * 50)
    
    tester = CredentialTestingNode()
    
    # Network error simulation
    print("\n📝 Network Error Simulation:")
    print("-" * 40)
    
    try:
        result = tester.execute(
            credential_type="oauth2",
            scenario="network_error",
            delay_ms=100  # Simulate 100ms delay before error
        )
    except Exception as e:
        print(f"✅ Network error caught: {e}")
    
    # Rate limit simulation
    print("\n📝 Rate Limit Simulation:")
    print("-" * 40)
    
    result = tester.execute(
        credential_type="api_key",
        scenario="rate_limit"
    )
    
    print(f"   Valid: {result['valid']}")
    print(f"   Error: {result['error']}")
    print(f"   Retry After: {result['error_details']['retry_after']} seconds")
    print(f"   Rate Limit: {result['error_details']['limit']} requests")
    print(f"   Remaining: {result['error_details']['remaining']}")


def demonstrate_security_test_helper():
    """Demonstrate the SecurityTestHelper for comprehensive testing."""
    print("\n\n🛡️ SecurityTestHelper Demo")
    print("=" * 50)
    
    helper = SecurityTestHelper()
    
    # Test all credential scenarios for OAuth2
    print("\n📝 Testing All OAuth2 Scenarios:")
    print("-" * 40)
    
    results = helper.test_credential_scenarios("oauth2")
    
    for scenario, result in results.items():
        status = "✅ Success" if result["success"] else "❌ Failed"
        print(f"   {scenario}: {status}")
        if not result["success"] and "error" in result:
            print(f"      Error: {result['error']}")
    
    # Create test workflows for different auth types
    print("\n📝 Creating Test Workflows:")
    print("-" * 40)
    
    for auth_type in ["oauth2", "api_key", "basic"]:
        workflow = helper.create_auth_test_workflow(auth_type)
        print(f"✅ Created {auth_type} test workflow with {len(workflow.nodes)} nodes")
        print(f"   Nodes: {list(workflow.nodes.keys())}")


def demonstrate_workflow_integration():
    """Demonstrate credential testing in a complete workflow."""
    print("\n\n🔄 Workflow Integration Demo")
    print("=" * 50)
    
    # Create a workflow that tests credential flow
    workflow = Workflow(workflow_id="credential_test_workflow", name="Credential Test Workflow")
    
    # Add credential testing node
    workflow.add_node(
        "test_creds",
        CredentialTestingNode(),
        credential_type="oauth2",
        scenario="success",
        mock_data={"scope": "api.read api.write"},
        ttl_seconds=3600
    )
    
    # Add OAuth2 node that would use the credentials
    workflow.add_node(
        "oauth",
        OAuth2Node(),
        token_url="https://api.example.com/token",
        client_id="test_client",
        client_secret="test_secret"
    )
    
    # In a real test, you might connect these nodes
    # workflow.connect("test_creds", "oauth", {"credentials": "mock_data"})
    
    print("✅ Created credential testing workflow")
    print(f"   Nodes: {list(workflow.nodes.keys())}")
    print("\n📊 Workflow Purpose:")
    print("   1. Generate mock OAuth2 credentials")
    print("   2. Validate credentials meet requirements")
    print("   3. Test token lifecycle (expiration, refresh)")
    print("   4. Simulate error conditions")


def demonstrate_mock_data_generation():
    """Demonstrate mock credential data generation."""
    print("\n\n🎭 Mock Data Generation Demo")
    print("=" * 50)
    
    mock_gen = CredentialMockData()
    
    # Generate OAuth2 configs for different providers
    print("\n📝 OAuth2 Provider Configurations:")
    print("-" * 40)
    
    for provider in ["generic", "github", "google"]:
        config = mock_gen.generate_oauth2_config(provider)
        print(f"\n{provider.upper()}:")
        print(f"   Token URL: {config['token_url']}")
        print(f"   Client ID: {config['client_id']}")
        print(f"   Scope: {config['scope']}")
        print(f"   Grant Type: {config['grant_type']}")
    
    # Generate API key configs
    print("\n\n📝 API Key Service Configurations:")
    print("-" * 40)
    
    for service in ["generic", "stripe", "openai"]:
        config = mock_gen.generate_api_key_config(service)
        print(f"\n{service.upper()}:")
        print(f"   API Key: {config['api_key'][:20]}...")
        print(f"   Header: {config['header_name']}")
        print(f"   Prefix: {config['prefix'] or 'None'}")
    
    # Generate JWT claims
    print("\n\n📝 JWT Claims for Different Users:")
    print("-" * 40)
    
    for user_type in ["user", "admin", "service"]:
        claims = mock_gen.generate_jwt_claims(user_type)
        print(f"\n{user_type.upper()}:")
        print(f"   Subject: {claims['sub']}")
        print(f"   Name: {claims.get('name', 'N/A')}")
        print(f"   Roles: {claims.get('roles', claims.get('scope', 'N/A'))}")
        print(f"   Expires: {claims['exp']} (timestamp)")


def main():
    """Run all credential testing demonstrations."""
    try:
        # Basic testing
        demonstrate_credential_testing_basics()
        
        # Validation rules
        demonstrate_validation_rules()
        
        # Error scenarios
        demonstrate_error_scenarios()
        
        # Security test helper
        demonstrate_security_test_helper()
        
        # Workflow integration
        demonstrate_workflow_integration()
        
        # Mock data generation
        demonstrate_mock_data_generation()
        
        print("\n\n✅ All credential testing demonstrations completed!")
        
        # Summary
        print("\n📋 CredentialTestingNode Features Summary:")
        print("-" * 50)
        print("✅ Multiple credential types: OAuth2, API Key, Basic, JWT")
        print("✅ Scenario simulation: Success, expired, invalid, errors")
        print("✅ Validation rules: Custom requirements for credentials")
        print("✅ Error injection: Network errors, rate limits")
        print("✅ Mock data generation: Realistic test credentials")
        print("✅ Security testing: Comprehensive auth flow validation")
        print("✅ Workflow integration: Test auth in complete workflows")
        
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()