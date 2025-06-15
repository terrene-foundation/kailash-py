"""Example demonstrating the CredentialManagerNode for enterprise credential management.

This example shows various ways to manage credentials securely across different
sources and validation patterns.
"""

import json
import os
from pathlib import Path

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.nodes.security import CredentialManagerNode
from kailash.workflow import Workflow


def setup_test_credentials():
    """Set up test credentials for demonstration."""
    # Environment variables
    os.environ["OPENAI_API_KEY"] = "sk-test-12345678901234567890"
    os.environ["DB_HOST"] = "localhost"
    os.environ["DB_USER"] = "test_user"
    os.environ["DB_PASSWORD"] = "test_password_123"
    os.environ["DB_NAME"] = "test_database"

    # Create test credential files
    cred_dir = Path(".credentials")
    cred_dir.mkdir(exist_ok=True)

    # API credentials file
    api_creds = {
        "api_key": "file-based-api-key-123456",
        "endpoint": "https://api.example.com",
    }
    with open(cred_dir / "api_service.json", "w") as f:
        json.dump(api_creds, f)

    # OAuth2 credentials file
    oauth_creds = {
        "client_id": "oauth-client-123",
        "client_secret": "oauth-secret-456",
        "token_url": "https://auth.example.com/token",
    }
    with open(cred_dir / "oauth_service.json", "w") as f:
        json.dump(oauth_creds, f)


async def basic_credential_usage():
    """Basic credential management example."""
    print("=== Basic Credential Usage ===\n")

    # Create workflow
    workflow = Workflow(
        workflow_id="cred_example", name="Credential Management Example"
    )

    # Add credential manager for API key
    workflow.add_node(
        "get_api_key",
        CredentialManagerNode,
        credential_name="openai",
        credential_type="api_key",
        validate_on_fetch=True,
    )

    # Add LLM node that uses the credential
    workflow.add_node(
        "llm_process", LLMAgentNode, prompt="Generate a summary", model="gpt-4"
    )

    # Connect nodes - credential manager provides API key
    workflow.connect("get_api_key", "llm_process", {"credentials.api_key": "api_key"})

    # Execute
    result = await workflow.execute()

    # Display results
    cred_result = result["get_api_key"]
    print(f"Credential source: {cred_result['source']}")
    print(f"Validated: {cred_result['validated']}")
    print(f"Masked display: {cred_result['masked_display']}")
    print(f"Metadata: {cred_result['metadata']}")


async def multi_source_credentials():
    """Demonstrate multiple credential sources with fallback."""
    print("\n=== Multi-Source Credentials ===\n")

    workflow = Workflow(
        workflow_id="multi_source", name="Multi-Source Credential Example"
    )

    # Try multiple sources in order
    workflow.add_node(
        "get_db_creds",
        CredentialManagerNode,
        credential_name="db",
        credential_type="database",
        credential_sources=["vault", "aws_secrets", "env", "file"],
        cache_duration_seconds=600,  # Cache for 10 minutes
    )

    # Use credentials in database node
    workflow.add_node("db_query", SQLDatabaseNode, query="SELECT * FROM users LIMIT 5")

    # Connect with credential mapping
    workflow.connect(
        "get_db_creds",
        "db_query",
        {
            "credentials.host": "host",
            "credentials.port": "port",
            "credentials.username": "username",
            "credentials.password": "password",
            "credentials.database": "database",
        },
    )

    result = await workflow.execute()
    print(f"Found credentials in: {result['get_db_creds']['source']}")


async def oauth2_credential_flow():
    """OAuth2 credential management example."""
    print("\n=== OAuth2 Credential Flow ===\n")

    workflow = Workflow(workflow_id="oauth_flow", name="OAuth2 Credential Example")

    # Get OAuth2 credentials
    workflow.add_node(
        "get_oauth_creds",
        CredentialManagerNode,
        credential_name="oauth_service",
        credential_type="oauth2",
        credential_sources=["file", "env"],
        validate_on_fetch=True,
    )

    # Use in HTTP request
    workflow.add_node(
        "api_request", HTTPRequestNode, url="https://api.example.com/data", method="GET"
    )

    # Connect - OAuth credentials for API request
    workflow.connect(
        "get_oauth_creds",
        "api_request",
        {
            "credentials.client_id": "oauth_client_id",
            "credentials.client_secret": "oauth_client_secret",
        },
    )

    result = await workflow.execute()
    oauth_creds = result["get_oauth_creds"]

    print(f"OAuth2 credentials validated: {oauth_creds['validated']}")
    print(f"Masked credentials: {oauth_creds['masked_display']}")


def demonstrate_credential_validation():
    """Show credential validation patterns."""
    print("\n=== Credential Validation Patterns ===\n")

    # Create manager with strict validation
    manager = CredentialManagerNode(
        credential_name="api_service",
        credential_type="api_key",
        validate_on_fetch=True,
        name="strict_validator",
    )

    # Test various credential formats
    test_cases = [
        ("valid_api_key", "sk-proj-12345678901234567890abcdef"),
        ("too_short", "sk-123"),
        ("invalid_chars", "sk-test-!!!invalid!!!"),
        (
            "valid_oauth",
            {"client_id": "oauth123456", "client_secret": "secret123456789012345"},
        ),
    ]

    for name, cred in test_cases:
        # Simulate credential validation
        if isinstance(cred, str):
            test_cred = {"api_key": cred}
        else:
            test_cred = cred

        # Check validation (internal method demonstration)
        is_valid = manager._validate_credential(test_cred)
        print(f"{name}: {'✅ Valid' if is_valid else '❌ Invalid'}")


def demonstrate_secure_logging():
    """Show secure credential logging."""
    print("\n=== Secure Credential Logging ===\n")

    manager = CredentialManagerNode(
        credential_name="test",
        credential_type="database",
        mask_in_logs=True,
        name="secure_logger",
    )

    # Demonstrate masking
    sensitive_values = [
        ("api_key", "sk-proj-verysecretkey123456"),
        ("password", "MyP@ssw0rd123!"),
        ("token", "ghp_1234567890abcdef"),
        ("short", "abc123"),
        ("client_secret", "oauth-secret-very-long-value-123456"),
    ]

    print("Credential masking examples:")
    for name, value in sensitive_values:
        masked = manager._mask_value(value)
        print(f"  {name}: {value[:10]}... → {masked}")


async def enterprise_credential_workflow():
    """Complex enterprise credential management workflow."""
    print("\n=== Enterprise Credential Workflow ===\n")

    workflow = Workflow(
        workflow_id="enterprise", name="Enterprise Multi-Service Integration"
    )

    # Service 1: Database credentials
    workflow.add_node(
        "db_creds",
        CredentialManagerNode,
        credential_name="postgres_prod",
        credential_type="database",
        credential_sources=["vault", "env"],
        cache_duration_seconds=3600,
    )

    # Service 2: API credentials
    workflow.add_node(
        "api_creds",
        CredentialManagerNode,
        credential_name="external_api",
        credential_type="api_key",
        credential_sources=["aws_secrets", "file"],
        validate_on_fetch=True,
    )

    # Service 3: OAuth2 credentials
    workflow.add_node(
        "oauth_creds",
        CredentialManagerNode,
        credential_name="analytics_service",
        credential_type="oauth2",
        credential_sources=["azure_keyvault", "env", "file"],
    )

    # Use all credentials in various services
    workflow.add_node("db_query", SQLDatabaseNode, query="SELECT * FROM metrics")
    workflow.add_node("api_call", HTTPRequestNode, url="https://api.external.com/data")
    workflow.add_node(
        "analytics", HTTPRequestNode, url="https://analytics.service.com/report"
    )

    # Connect credential managers to services
    workflow.connect(
        "db_creds",
        "db_query",
        {
            "credentials.host": "host",
            "credentials.username": "username",
            "credentials.password": "password",
        },
    )

    workflow.connect(
        "api_creds", "api_call", {"credentials.api_key": "headers.X-API-Key"}
    )

    workflow.connect(
        "oauth_creds",
        "analytics",
        {
            "credentials.client_id": "oauth_client_id",
            "credentials.client_secret": "oauth_client_secret",
        },
    )

    print("✅ Enterprise workflow configured with secure credential management")
    print("   - Credentials cached appropriately")
    print("   - Multiple fallback sources configured")
    print("   - Validation enabled where needed")
    print("   - All sensitive data masked in logs")


if __name__ == "__main__":
    print("=== Credential Manager Node Examples ===\n")

    # Set up test environment
    setup_test_credentials()

    # Run examples
    import asyncio

    # Basic usage
    # asyncio.run(basic_credential_usage())
    # Multi-source
    # asyncio.run(multi_source_credentials())
    # OAuth2 flow
    # asyncio.run(oauth2_credential_flow())
    # Validation patterns
    demonstrate_credential_validation()

    # Secure logging
    demonstrate_secure_logging()

    # Enterprise workflow
    # asyncio.run(enterprise_credential_workflow())

    print("\n✅ Credential management examples completed!")
    print("   Remember to never commit real credentials to version control!")
