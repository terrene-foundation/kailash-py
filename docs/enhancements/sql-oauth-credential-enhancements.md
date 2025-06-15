# SQL, OAuth2, and Credential Testing Enhancements

This document describes the enhancements made to SQLDatabaseNode, OAuth2Node, and the new CredentialTestingNode.

## SQLDatabaseNode Serialization Enhancement

### Overview
The SQLDatabaseNode now automatically serializes database-specific types to JSON-compatible formats, eliminating common JSON serialization errors when working with query results.

### Supported Type Conversions
- **Decimal** → float (preserves numeric precision)
- **datetime** → ISO format string (e.g., "2025-06-12T10:30:00")
- **date** → ISO format string (e.g., "2025-06-12")
- **timedelta** → total seconds (numeric representation)
- **UUID** → string representation
- **bytes** → base64 encoded string
- **Nested structures** → Recursively serialized

### Implementation
Added `_serialize_value()` method that handles type conversion before returning results. This ensures all query results can be safely serialized to JSON for APIs, storage, or further processing.

### Example
```python
from kailash.nodes.data import SQLDatabaseNode

# Query returns Decimal and datetime types
sql_node = SQLDatabaseNode(connection_string="sqlite:///example.db")
result = sql_node.execute(
    query="SELECT price, created_at FROM products",
    result_format="dict"
)

# Results are automatically serialized
# price: Decimal("99.99") → 99.99 (float)
# created_at: datetime object → "2025-06-12T10:30:00" (string)
```

## OAuth2Node Enhanced Output

### Overview
The OAuth2Node now provides comprehensive token metadata for better lifecycle management and debugging.

### New Output Fields
- **token_type**: Extracted from response (e.g., "Bearer", "MAC")
- **scope**: Actual granted scopes from the authorization server
- **refresh_token_present**: Boolean indicating if refresh token is available
- **token_expires_at**: ISO format timestamp of token expiration
- **raw_response**: Optional full token response for debugging

### Enhanced Features
- Support for different token types (not just Bearer)
- Precise expiration tracking with ISO timestamps
- Optional raw response inclusion for troubleshooting
- Automatic header formatting based on token type

### Example
```python
from kailash.nodes.api.auth import OAuth2Node

oauth_node = OAuth2Node(
    token_url="https://auth.example.com/token",
    client_id="client_123",
    client_secret="secret_456"
)

result = oauth_node.execute(include_raw_response=True)
# Returns:
# {
#   "headers": {"Authorization": "Bearer access_token_123"},
#   "token_type": "Bearer",
#   "scope": "read write",
#   "refresh_token_present": True,
#   "token_expires_at": "2025-06-12T11:30:00+00:00",
#   "expires_in": 3600,
#   "raw_response": {...}  # Full server response
# }
```

## CredentialTestingNode

### Overview
A new specialized node for testing authentication flows without requiring actual external services. Perfect for unit testing, integration testing, and security validation.

### Features
- **Multiple credential types**: OAuth2, API Key, Basic Auth, JWT
- **Scenario simulation**: Success, expired, invalid, network errors, rate limits
- **Validation rules**: Custom requirements for generated credentials
- **Mock data generation**: Realistic test credentials
- **Error injection**: Controlled error scenarios for testing
- **Metadata tracking**: Test IDs, timestamps, scenario details

### Supported Scenarios
- **success**: Valid credentials with configurable properties
- **expired**: Expired tokens/credentials
- **invalid**: Invalid or malformed credentials
- **network_error**: Simulated connection failures
- **rate_limit**: API rate limiting responses

### Example
```python
from kailash.nodes.testing import CredentialTestingNode

tester = CredentialTestingNode()

# Test OAuth2 token expiration
result = tester.run(
    credential_type="oauth2",
    scenario="expired",
    mock_data={"client_id": "test_client"}
)
# Returns:
# {
#   "valid": False,
#   "expired": True,
#   "error": "Token expired",
#   "error_details": {"error_code": "expired_token", ...}
# }

# Test successful API key with validation
result = tester.run(
    credential_type="api_key",
    scenario="success",
    validation_rules={"key_length": 32}
)
# Returns:
# {
#   "valid": True,
#   "credentials": {"api_key": "sk_test_..."},
#   "headers": {"X-API-Key": "sk_test_..."}
# }
```

## Testing Framework Enhancements

### CredentialMockData Class
Generates realistic mock credentials for different providers:
- OAuth2 configs for generic, GitHub, Google
- API key configs for generic, Stripe, OpenAI
- JWT claims for user, admin, service accounts

### SecurityTestHelper Class
Provides comprehensive security testing utilities:
- Create auth test workflows for different auth types
- Test multiple credential scenarios in batch
- Integration with workflow testing

### Example
```python
from kailash.runtime.testing import SecurityTestHelper

helper = SecurityTestHelper()

# Test all OAuth2 scenarios
results = helper.test_credential_scenarios("oauth2")
# Tests: success, expired, invalid, rate_limit

# Create test workflow
workflow = helper.create_auth_test_workflow("oauth2")
# Creates: credential_test → oauth → http nodes
```

## Benefits

1. **SQLDatabaseNode**: Eliminates JSON serialization errors, enabling seamless integration with APIs and storage systems
2. **OAuth2Node**: Better token lifecycle management with detailed metadata for monitoring and debugging
3. **CredentialTestingNode**: Systematic testing of authentication flows without external dependencies
4. **Overall**: More robust handling of external integrations with comprehensive testing capabilities
