"""
JWT Token Generation & OAuth2 Integration

Demonstrates:
- JWT token generation and validation workflows
- OAuth2 authorization code exchange flow
- Security patterns for authentication
- Token management with refresh tokens
- Multi-step authentication workflows

Dependencies:
    pip install dataflow kailash

Environment Variables:
    JWT_SECRET_KEY: Secret key for JWT signing
    OAUTH2_CLIENT_ID: OAuth2 client ID (e.g., Google, GitHub)
    OAUTH2_CLIENT_SECRET: OAuth2 client secret
    OAUTH2_REDIRECT_URI: OAuth2 redirect URI

Usage:
    # Generate JWT tokens for user
    python jwt_oauth2.py jwt alice@example.com

    # Exchange OAuth2 code for tokens
    python jwt_oauth2.py oauth2 authorization_code_123
"""

import asyncio
import sys
from datetime import datetime, timedelta

from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ============================================================================
# Database Models
# ============================================================================

# Create in-memory database for demonstration
db = DataFlow(":memory:")


@db.model
class User:
    """
    User model for authentication.

    Demonstrates:
    - Password hashing (stored as hash, never plaintext)
    - Basic user attributes
    """

    id: str
    email: str
    password_hash: str
    name: str


@db.model
class TokenMetadata:
    """
    Token metadata model for tracking issued tokens.

    Demonstrates:
    - Token type tracking (access vs refresh)
    - Expiration tracking
    - Token lifecycle management
    """

    id: str
    user_id: str
    token_type: str
    expires_at: str
    created_at: str


@db.model
class OAuthUser:
    """
    OAuth user model for external authentication.

    Demonstrates:
    - OAuth provider integration
    - External user ID mapping
    - Access token storage
    """

    id: str
    email: str
    name: str
    oauth_provider: str
    oauth_user_id: str
    access_token: str


@db.model
class Session:
    """
    Session model for user sessions.

    Demonstrates:
    - Session token tracking
    - Expiration management
    - User-session relationship
    """

    id: str
    user_id: str
    token: str
    expires_at: str


# ============================================================================
# Workflow 1: JWT Token Generation and Validation
# ============================================================================


def build_jwt_token_workflow(email: str, name: str) -> WorkflowBuilder:
    """
    Build workflow for JWT token generation and validation.

    Workflow Steps:
    1. Create test user (UserCreateNode)
    2. Authenticate user credentials (PythonCodeNode)
    3. Generate JWT access token (PythonCodeNode)
    4. Generate refresh token (PythonCodeNode)
    5. Store token metadata (TokenMetadataCreateNode x2)

    Args:
        email: User email address
        name: User name

    Returns:
        WorkflowBuilder configured for JWT token generation

    Demonstrates:
        - JWT token generation with expiration
        - Token validation patterns
        - Refresh token handling
        - Security best practices (token storage)
    """
    workflow = WorkflowBuilder()

    # Step 1: Create test user
    workflow.add_node(
        "UserCreateNode",
        "create_user",
        {
            "id": f"user-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "email": email,
            "password_hash": "hashed_password_123",  # In production, use bcrypt/argon2
            "name": name,
        },
    )

    # Step 2: Authenticate user (mock)
    workflow.add_node(
        "PythonCodeNode",
        "authenticate",
        {
            "code": f"""
# Mock user authentication
# In production:
# - Verify password hash with bcrypt.checkpw()
# - Check user account status
# - Rate limit authentication attempts
# - Log authentication events

authenticated = True
user_id = "user-001"
email = "{email}"

print(f"✓ User authenticated")
print(f"  Email: {{email}}")
""",
            "inputs": {},
        },
    )

    # Step 3: Generate JWT tokens
    workflow.add_node(
        "PythonCodeNode",
        "generate_tokens",
        {
            "code": """
import uuid
from datetime import datetime, timedelta

# Mock JWT token generation
# In production, use PyJWT:
# import jwt
# payload = {
#     'user_id': user_id,
#     'email': email,
#     'exp': datetime.utcnow() + timedelta(hours=1)
# }
# access_token = jwt.encode(payload, secret_key, algorithm='HS256')

access_token = f"jwt_access_{uuid.uuid4().hex}"
refresh_token = f"jwt_refresh_{uuid.uuid4().hex}"
access_expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
refresh_expires_at = (datetime.now() + timedelta(days=7)).isoformat()

print(f"✓ JWT tokens generated")
print(f"  Access token expires: {access_expires_at}")
print(f"  Refresh token expires: {refresh_expires_at}")
""",
            "inputs": {"user_id": "{{authenticate.user_id}}"},
        },
    )

    # Step 4: Store access token metadata
    workflow.add_node(
        "TokenMetadataCreateNode",
        "store_access_token",
        {
            "id": "{{generate_tokens.access_token}}",
            "user_id": "{{authenticate.user_id}}",
            "token_type": "access",
            "expires_at": "{{generate_tokens.access_expires_at}}",
            "created_at": datetime.now().isoformat(),
        },
    )

    # Step 5: Store refresh token metadata
    workflow.add_node(
        "TokenMetadataCreateNode",
        "store_refresh_token",
        {
            "id": "{{generate_tokens.refresh_token}}",
            "user_id": "{{authenticate.user_id}}",
            "token_type": "refresh",
            "expires_at": "{{generate_tokens.refresh_expires_at}}",
            "created_at": datetime.now().isoformat(),
        },
    )

    # Connections
    workflow.add_connection("create_user", "id", "authenticate", "trigger")
    workflow.add_connection("authenticate", "user_id", "generate_tokens", "user_id")
    workflow.add_connection(
        "generate_tokens", "access_token", "store_access_token", "id"
    )
    workflow.add_connection(
        "generate_tokens", "refresh_token", "store_refresh_token", "id"
    )

    return workflow


async def jwt_token_example(email: str, name: str):
    """
    Execute JWT token generation workflow.

    Args:
        email: User email address
        name: User name

    Returns:
        Dictionary with token generation results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_jwt_token_workflow(email, name)

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ JWT tokens generated successfully (run_id: {run_id})")
        print(f"  User ID: {results['store_access_token']['user_id']}")
        print()
        print("Access Token:")
        print(f"  Type: {results['store_access_token']['token_type']}")
        print(f"  Expires: {results['store_access_token']['expires_at']}")
        print()
        print("Refresh Token:")
        print(f"  Type: {results['store_refresh_token']['token_type']}")
        print(f"  Expires: {results['store_refresh_token']['expires_at']}")

        return results

    except Exception as e:
        print(f"✗ Error generating JWT tokens: {e}")
        raise


# ============================================================================
# Workflow 2: OAuth2 Authorization Code Exchange
# ============================================================================


def build_oauth2_workflow() -> WorkflowBuilder:
    """
    Build workflow for OAuth2 authorization code exchange.

    Workflow Steps:
    1. Exchange authorization code for access token (PythonCodeNode)
    2. Fetch user profile from OAuth provider (PythonCodeNode)
    3. Check if user exists (OAuthUserListNode)
    4. Create or update user record (OAuthUserCreateNode)
    5. Generate internal JWT token (PythonCodeNode)
    6. Store session (SessionCreateNode)

    Returns:
        WorkflowBuilder configured for OAuth2 flow

    Demonstrates:
        - OAuth2 code exchange flow
        - External API integration (Google, GitHub, etc.)
        - User profile synchronization
        - Token generation after OAuth
        - Multi-step authentication workflow
    """
    workflow = WorkflowBuilder()

    # Step 1: Exchange authorization code for access token
    workflow.add_node(
        "PythonCodeNode",
        "exchange_code",
        {
            "code": """
import uuid

# Mock OAuth2 code exchange
# In production, use requests library:
# response = requests.post(
#     'https://oauth2.googleapis.com/token',
#     data={
#         'code': auth_code,
#         'client_id': client_id,
#         'client_secret': client_secret,
#         'redirect_uri': redirect_uri,
#         'grant_type': 'authorization_code'
#     }
# )
# oauth_access_token = response.json()['access_token']

auth_code = "code_123"
oauth_access_token = f"oauth_token_{uuid.uuid4().hex}"
oauth_user_id = "google_user_123"

print(f"✓ OAuth2 code exchanged for token")
print(f"  Provider user ID: {oauth_user_id}")
""",
            "inputs": {},
        },
    )

    # Step 2: Fetch user profile from OAuth provider
    workflow.add_node(
        "PythonCodeNode",
        "fetch_profile",
        {
            "code": """
# Mock OAuth profile fetch
# In production, use OAuth provider's API:
# response = requests.get(
#     'https://www.googleapis.com/oauth2/v2/userinfo',
#     headers={'Authorization': f'Bearer {access_token}'}
# )
# profile = response.json()

email = "alice@example.com"
name = "Alice Smith"
oauth_provider = "google"

print(f"✓ OAuth profile fetched")
print(f"  Email: {email}")
print(f"  Name: {name}")
print(f"  Provider: {oauth_provider}")
""",
            "inputs": {"access_token": "{{exchange_code.oauth_access_token}}"},
        },
    )

    # Step 3: Check if user exists
    workflow.add_node(
        "OAuthUserListNode",
        "check_user",
        {"filters": {"email": "{{fetch_profile.email}}"}, "limit": 1},
    )

    # Step 4: Create user if not exists
    workflow.add_node(
        "OAuthUserCreateNode",
        "create_oauth_user",
        {
            "id": f"user-oauth-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "email": "{{fetch_profile.email}}",
            "name": "{{fetch_profile.name}}",
            "oauth_provider": "{{fetch_profile.oauth_provider}}",
            "oauth_user_id": "{{exchange_code.oauth_user_id}}",
            "access_token": "{{exchange_code.oauth_access_token}}",
        },
    )

    # Step 5: Generate internal session token
    workflow.add_node(
        "PythonCodeNode",
        "generate_session",
        {
            "code": """
import uuid
from datetime import datetime, timedelta

# Generate internal JWT token for session
# This is separate from OAuth provider's token
session_token = f"session_{uuid.uuid4().hex}"
expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

print(f"✓ Session token generated")
print(f"  Token: {session_token[:20]}...")
print(f"  Expires: {expires_at}")
""",
            "inputs": {},
        },
    )

    # Step 6: Store session
    workflow.add_node(
        "SessionCreateNode",
        "store_session",
        {
            "id": "{{generate_session.session_token}}",
            "user_id": f"user-oauth-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "token": "{{generate_session.session_token}}",
            "expires_at": "{{generate_session.expires_at}}",
        },
    )

    # Connections
    workflow.add_connection(
        "exchange_code", "oauth_access_token", "fetch_profile", "access_token"
    )
    workflow.add_connection("fetch_profile", "email", "check_user", "trigger")
    workflow.add_connection("check_user", "records", "create_oauth_user", "trigger")
    workflow.add_connection("create_oauth_user", "id", "generate_session", "trigger")
    workflow.add_connection(
        "generate_session", "session_token", "store_session", "token"
    )

    return workflow


async def oauth2_example():
    """
    Execute OAuth2 authorization code exchange workflow.

    Returns:
        Dictionary with OAuth2 results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_oauth2_workflow()

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ OAuth2 authentication successful (run_id: {run_id})")
        print()
        print("OAuth User:")
        print(f"  Provider: {results['create_oauth_user']['oauth_provider']}")
        print(f"  Email: {results['create_oauth_user']['email']}")
        print(f"  Name: {results['create_oauth_user']['name']}")
        print()
        print("Session:")
        print(f"  User ID: {results['store_session']['user_id']}")
        print(f"  Expires: {results['store_session']['expires_at']}")

        return results

    except Exception as e:
        print(f"✗ Error in OAuth2 flow: {e}")
        raise


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main entry point for example execution.

    Supports two commands:
    1. jwt <email> [name] - Generate JWT tokens for user
    2. oauth2 <auth_code> - Exchange OAuth2 code for tokens
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  jwt <email> [name] - Generate JWT tokens for user")
        print("  oauth2 <auth_code> - Exchange OAuth2 code for tokens")
        sys.exit(1)

    command = sys.argv[1]

    print("=" * 80)
    print("JWT Token Generation & OAuth2 Integration Example")
    print("=" * 80)
    print()

    if command == "jwt":
        if len(sys.argv) < 3:
            print("Error: jwt requires email")
            print("Usage: jwt <email> [name]")
            sys.exit(1)

        email = sys.argv[2]
        name = (
            " ".join(sys.argv[3:]) if len(sys.argv) > 3 else email.split("@")[0].title()
        )

        print(f"Generating JWT tokens for: {name} <{email}>")
        print()

        results = await jwt_token_example(email, name)

    elif command == "oauth2":
        if len(sys.argv) < 3:
            print("Error: oauth2 requires authorization code")
            print("Usage: oauth2 <auth_code>")
            sys.exit(1)

        auth_code = sys.argv[2]

        print(f"Processing OAuth2 authorization code: {auth_code}")
        print()

        results = await oauth2_example()

    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: jwt, oauth2")
        sys.exit(1)

    print()
    print("=" * 80)
    print("✓ Example completed successfully")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
