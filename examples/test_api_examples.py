#!/usr/bin/env python3
"""
Test script for API integration examples.

This script validates that the API integration examples work correctly
and demonstrates the functionality of the Kailash SDK's API capabilities.
"""

import sys
import os
import traceback

# Add the src directory to the Python path so we can import kailash
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_rate_limiting_config():
    """Test the rate limiting configuration."""
    print("Testing rate limiting configuration...")
    
    try:
        from kailash.nodes.api.rate_limiting import RateLimitConfig, TokenBucketRateLimiter, SlidingWindowRateLimiter
        
        # Test token bucket configuration
        config = RateLimitConfig(
            max_requests=5,
            time_window=10.0,
            strategy="token_bucket"
        )
        
        limiter = TokenBucketRateLimiter(config)
        
        # Test basic functionality
        assert limiter.can_proceed(), "Token bucket should allow initial request"
        assert limiter.consume(), "Token bucket should consume token"
        
        print("✓ Token bucket rate limiter works")
        
        # Test sliding window configuration
        config = RateLimitConfig(
            max_requests=3,
            time_window=5.0,
            strategy="sliding_window"
        )
        
        limiter = SlidingWindowRateLimiter(config)
        
        # Test basic functionality
        assert limiter.can_proceed(), "Sliding window should allow initial request"
        assert limiter.consume(), "Sliding window should consume token"
        
        print("✓ Sliding window rate limiter works")
        
        return True
        
    except Exception as e:
        print(f"✗ Rate limiting test failed: {e}")
        traceback.print_exc()
        return False


def test_api_nodes():
    """Test the basic API nodes."""
    print("Testing API nodes...")
    
    try:
        from kailash.nodes.api import HTTPRequestNode, RESTClientNode, BasicAuthNode, APIKeyNode
        from kailash.runtime.local import LocalRuntime
        
        # Test HTTPRequestNode - provide required params to avoid validation error
        http_node = HTTPRequestNode(node_id="test_http", url="http://example.com")
        params = http_node.get_parameters()
        output_schema = http_node.get_output_schema()
        
        assert "url" in params, "HTTP node should have url parameter"
        assert "response" in output_schema, "HTTP node should have response output"
        
        print("✓ HTTPRequestNode parameter definition works")
        
        # Test RESTClientNode - provide required params
        rest_node = RESTClientNode(node_id="test_rest", base_url="http://api.example.com", resource="users")
        params = rest_node.get_parameters()
        output_schema = rest_node.get_output_schema()
        
        assert "base_url" in params, "REST node should have base_url parameter"
        assert "resource" in params, "REST node should have resource parameter"
        assert "data" in output_schema, "REST node should have data output"
        
        print("✓ RESTClientNode parameter definition works")
        
        # Test BasicAuthNode - provide required params
        auth_node = BasicAuthNode(node_id="test_auth", username="test", password="test")
        params = auth_node.get_parameters()
        output_schema = auth_node.get_output_schema()
        
        assert "username" in params, "Basic auth should have username parameter"
        assert "password" in params, "Basic auth should have password parameter"
        assert "headers" in output_schema, "Basic auth should have headers output"
        
        print("✓ BasicAuthNode parameter definition works")
        
        # Test APIKeyNode - provide required params
        api_key_node = APIKeyNode(node_id="test_api_key", api_key="test-key")
        params = api_key_node.get_parameters()
        output_schema = api_key_node.get_output_schema()
        
        assert "api_key" in params, "API key node should have api_key parameter"
        assert "location" in params, "API key node should have location parameter"
        assert "headers" in output_schema, "API key node should have headers output"
        
        print("✓ APIKeyNode parameter definition works")
        
        return True
        
    except Exception as e:
        print(f"✗ API nodes test failed: {e}")
        traceback.print_exc()
        return False


def test_rate_limited_wrapper():
    """Test the rate limited wrapper functionality."""
    print("Testing rate limited wrapper...")
    
    try:
        from kailash.nodes.api import HTTPRequestNode, RateLimitConfig, RateLimitedAPINode
        from kailash.runtime.local import LocalRuntime
        
        # Create a basic HTTP node with required params
        http_node = HTTPRequestNode(node_id="base_http", url="http://example.com")
        
        # Create rate limiting config
        rate_config = RateLimitConfig(
            max_requests=2,
            time_window=5.0,
            strategy="token_bucket"
        )
        
        # Wrap with rate limiting
        rate_limited_node = RateLimitedAPINode(
            wrapped_node=http_node,
            rate_limit_config=rate_config,
            node_id="rate_limited"
        )
        
        # Test parameter inheritance
        params = rate_limited_node.get_parameters()
        assert "url" in params, "Rate limited node should inherit url parameter"
        assert "respect_rate_limits" in params, "Rate limited node should have rate limit control"
        
        # Test output schema inheritance
        output_schema = rate_limited_node.get_output_schema()
        assert "response" in output_schema, "Rate limited node should inherit response output"
        assert "rate_limit_metadata" in output_schema, "Rate limited node should add rate limit metadata"
        
        print("✓ Rate limited wrapper works")
        
        return True
        
    except Exception as e:
        print(f"✗ Rate limited wrapper test failed: {e}")
        traceback.print_exc()
        return False


def test_basic_auth_functionality():
    """Test basic authentication functionality."""
    print("Testing basic authentication functionality...")
    
    try:
        from kailash.nodes.api import BasicAuthNode
        from kailash.runtime.local import LocalRuntime
        
        # Create node with required params
        auth_node = BasicAuthNode(node_id="test_basic_auth", username="testuser", password="testpass")
        runtime = LocalRuntime()
        
        # Test auth header generation
        result = runtime.execute_node(
            auth_node,
            username="testuser",
            password="testpass"
        )
        
        assert result["auth_type"] == "basic", "Auth type should be basic"
        assert "Authorization" in result["headers"], "Should have Authorization header"
        assert result["headers"]["Authorization"].startswith("Basic "), "Should be Basic auth header"
        
        print("✓ Basic authentication works")
        
        return True
        
    except Exception as e:
        print(f"✗ Basic authentication test failed: {e}")
        traceback.print_exc()
        return False


def test_api_key_functionality():
    """Test API key authentication functionality."""
    print("Testing API key authentication functionality...")
    
    try:
        from kailash.nodes.api import APIKeyNode
        from kailash.runtime.local import LocalRuntime
        
        # Create node with required params
        api_key_node = APIKeyNode(node_id="test_api_key", api_key="test-api-key-123")
        runtime = LocalRuntime()
        
        # Test header-based API key
        result = runtime.execute_node(
            api_key_node,
            api_key="test-api-key-123",
            location="header",
            param_name="X-API-Key"
        )
        
        assert result["auth_type"] == "api_key", "Auth type should be api_key"
        assert "X-API-Key" in result["headers"], "Should have API key header"
        assert result["headers"]["X-API-Key"] == "test-api-key-123", "API key should match"
        
        # Test query parameter API key
        result = runtime.execute_node(
            api_key_node,
            api_key="test-query-key",
            location="query",
            param_name="apikey"
        )
        
        assert "apikey" in result["query_params"], "Should have API key query param"
        assert result["query_params"]["apikey"] == "test-query-key", "Query API key should match"
        
        print("✓ API key authentication works")
        
        return True
        
    except Exception as e:
        print(f"✗ API key authentication test failed: {e}")
        traceback.print_exc()
        return False


def test_mock_api_examples():
    """Test the mock API examples functionality."""
    print("Testing mock API examples...")
    
    try:
        # Import the HMI example modules
        sys.path.insert(0, os.path.dirname(__file__))
        from hmi_style_api_example import HMIDoctorSearchNode, MockHMIConfig
        from kailash.runtime.local import LocalRuntime
        
        # Test HMI doctor search node with required params
        config = MockHMIConfig()
        doctor_search = HMIDoctorSearchNode(
            node_id="test_doctor_search",
            api_key="test-key",
            base_url="http://test.com",
            specialty="cardiology"
        )
        runtime = LocalRuntime()
        
        # Test parameter definitions
        params = doctor_search.get_parameters()
        assert "specialty" in params, "Should have specialty parameter"
        assert "api_key" in params, "Should have api_key parameter"
        
        # Test output schema
        output_schema = doctor_search.get_output_schema()
        assert "doctors" in output_schema, "Should have doctors output"
        assert "search_metadata" in output_schema, "Should have search_metadata output"
        
        print("✓ HMI doctor search node structure works")
        
        return True
        
    except Exception as e:
        print(f"✗ Mock API examples test failed: {e}")
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all API integration tests."""
    print("Kailash SDK - API Integration Tests")
    print("===================================")
    
    tests = [
        test_rate_limiting_config,
        test_api_nodes,
        test_rate_limited_wrapper,
        test_basic_auth_functionality,
        test_api_key_functionality,
        test_mock_api_examples,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        print(f"\n{test.__name__}:")
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Test Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    if failed == 0:
        print("🎉 All tests passed! API integration is working correctly.")
    else:
        print(f"⚠️  {failed} test(s) failed. Please check the implementation.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)