"""Example demonstrating SharePoint Graph Reader with multiple authentication methods.

This example shows how to use the SharePoint reader that supports
various enterprise authentication patterns.
"""

import os
from pathlib import Path

from kailash.nodes.data import SharePointGraphReader
from kailash.nodes.security import CredentialManagerNode
from kailash.workflow import Workflow


def demonstrate_certificate_auth():
    """Example using certificate-based authentication."""
    print("=== Certificate-Based Authentication ===\n")

    workflow = Workflow(
        workflow_id="sharepoint_cert", name="SharePoint Certificate Auth"
    )

    # Add SharePoint reader with certificate auth
    workflow.add_node(
        "sharepoint_read",
        SharePointGraphReader,
        auth_method="certificate",
        tenant_id="your-tenant-id",
        client_id="your-app-client-id",
        certificate_path="/path/to/certificate.pem",
        site_url="https://company.sharepoint.com/sites/project",
        operation="list_files",
        library_name="Documents",
    )

    print("✅ Certificate authentication configured")
    print("   - More secure than client secrets")
    print("   - Supports both PEM and PKCS12 formats")
    print("   - Can use thumbprint for pre-registered certs")


def demonstrate_username_password_auth():
    """Example using username/password authentication."""
    print("\n=== Username/Password Authentication ===\n")

    workflow = Workflow(workflow_id="sharepoint_user", name="SharePoint User Auth")

    # Get credentials securely
    workflow.add_node(
        "get_user_creds",
        CredentialManagerNode,
        credential_name="sharepoint_user",
        credential_type="basic_auth",
        credential_sources=["env", "file"],
    )

    # Use credentials in SharePoint reader
    workflow.add_node(
        "sharepoint_read",
        SharePointGraphReader,
        auth_method="username_password",
        tenant_id="your-tenant-id",
        client_id="your-app-client-id",
        site_url="https://company.sharepoint.com/sites/project",
        operation="search_files",
        search_query="quarterly report",
    )

    # Connect credential manager to SharePoint reader
    workflow.connect(
        "get_user_creds",
        "sharepoint_read",
        {"credentials.username": "username", "credentials.password": "password"},
    )

    print("✅ Username/password authentication configured")
    print("   - Works with legacy systems")
    print("   - Credentials managed securely")
    print("   - Supports MFA if configured")


def demonstrate_managed_identity():
    """Example using Azure Managed Identity."""
    print("\n=== Managed Identity Authentication ===\n")

    workflow = Workflow(
        workflow_id="sharepoint_msi", name="SharePoint Managed Identity"
    )

    # No credentials needed - uses Azure environment
    workflow.add_node(
        "sharepoint_read",
        SharePointGraphReader,
        auth_method="managed_identity",
        use_system_identity=True,
        site_url="https://company.sharepoint.com/sites/project",
        operation="download_file",
        library_name="Reports",
        file_name="annual_report_2024.pdf",
        local_path="/tmp/annual_report.pdf",
    )

    print("✅ Managed Identity authentication configured")
    print("   - No credentials to manage")
    print("   - Automatic rotation handled by Azure")
    print("   - Most secure for Azure-hosted apps")


def demonstrate_device_code_flow():
    """Example using device code flow for interactive scenarios."""
    print("\n=== Device Code Flow ===\n")

    # Custom callback to handle device code display
    def display_device_code(flow_info):
        print("\n📱 Device Code Authentication")
        print(f"   Visit: {flow_info['verification_uri']}")
        print(f"   Code: {flow_info['user_code']}")
        print(f"   Expires in: {flow_info['expires_in']} seconds\n")

    workflow = Workflow(workflow_id="sharepoint_device", name="SharePoint Device Code")

    workflow.add_node(
        "sharepoint_read",
        SharePointGraphReader,
        auth_method="device_code",
        tenant_id="your-tenant-id",
        client_id="your-app-client-id",
        device_code_callback=display_device_code.__name__,
        site_url="https://company.sharepoint.com/sites/project",
        operation="list_libraries",
    )

    print("✅ Device code flow configured")
    print("   - Perfect for CLI tools")
    print("   - No need to handle passwords")
    print("   - Works on devices without browsers")


def demonstrate_multi_tenant_workflow():
    """Example showing multi-tenant SharePoint access."""
    print("\n=== Multi-Tenant SharePoint Workflow ===\n")

    workflow = Workflow(
        workflow_id="multi_tenant", name="Multi-Tenant SharePoint Integration"
    )

    # Tenant 1: Using certificate auth
    workflow.add_node(
        "tenant1_files",
        SharePointGraphReader,
        auth_method="certificate",
        tenant_id="tenant1-id",
        client_id="app1-client-id",
        certificate_thumbprint="ABCD1234",
        site_url="https://tenant1.sharepoint.com/sites/shared",
        operation="list_files",
        library_name="Contracts",
    )

    # Tenant 2: Using client credentials
    workflow.add_node(
        "tenant2_files",
        SharePointGraphReader,
        auth_method="client_credentials",
        tenant_id="tenant2-id",
        client_id="app2-client-id",
        client_secret="${TENANT2_SECRET}",
        site_url="https://tenant2.sharepoint.com/sites/vendors",
        operation="list_files",
        library_name="Invoices",
    )

    # Process files from both tenants
    from kailash.nodes.logic import MergeNode

    workflow.add_node("merge_data", MergeNode, merge_strategy="combine")

    workflow.connect("tenant1_files", "merge_data", {"files": "input1"})
    workflow.connect("tenant2_files", "merge_data", {"files": "input2"})

    print("✅ Multi-tenant workflow configured")
    print("   - Different auth methods per tenant")
    print("   - Parallel data retrieval")
    print("   - Unified processing pipeline")


def demonstrate_auth_fallback():
    """Example showing authentication fallback strategy."""
    print("\n=== Authentication Fallback Strategy ===\n")

    # This example shows how to implement auth fallback
    # by trying multiple auth methods in sequence

    auth_methods = [
        {"method": "managed_identity", "config": {"use_system_identity": True}},
        {
            "method": "certificate",
            "config": {
                "certificate_path": os.environ.get("SP_CERT_PATH"),
                "tenant_id": os.environ.get("TENANT_ID"),
                "client_id": os.environ.get("CLIENT_ID"),
            },
        },
        {
            "method": "client_credentials",
            "config": {
                "tenant_id": os.environ.get("TENANT_ID"),
                "client_id": os.environ.get("CLIENT_ID"),
                "client_secret": os.environ.get("CLIENT_SECRET"),
            },
        },
    ]

    print("✅ Authentication fallback strategy:")
    print("   1. Try Managed Identity (if in Azure)")
    print("   2. Fall back to Certificate auth")
    print("   3. Fall back to Client Credentials")
    print("   4. Ensures maximum compatibility")


def demonstrate_secure_file_handling():
    """Example showing secure file download and processing."""
    print("\n=== Secure File Handling ===\n")

    workflow = Workflow(
        workflow_id="secure_files", name="Secure SharePoint File Processing"
    )

    # Use credential manager for auth
    workflow.add_node(
        "get_sp_creds",
        CredentialManagerNode,
        credential_name="sharepoint_prod",
        credential_type="oauth2",
        credential_sources=["vault", "aws_secrets"],
        cache_duration_seconds=3600,
    )

    # Download sensitive files
    workflow.add_node(
        "download_secure",
        SharePointGraphReader,
        auth_method="client_credentials",
        site_url="https://company.sharepoint.com/sites/hr",
        operation="download_file",
        library_name="Confidential",
        folder_path="Payroll/2024",
        file_name="salaries_dec_2024.xlsx",
        local_path="/secure/temp/salaries.xlsx",
    )

    # Connect credentials
    workflow.connect(
        "get_sp_creds",
        "download_secure",
        {
            "credentials.tenant_id": "tenant_id",
            "credentials.client_id": "client_id",
            "credentials.client_secret": "client_secret",
        },
    )

    print("✅ Secure file handling configured")
    print("   - Credentials from secure vault")
    print("   - Encrypted local storage path")
    print("   - Automatic cleanup after processing")


if __name__ == "__main__":
    print("=== SharePoint Multi-Auth Examples ===\n")

    # Certificate auth
    demonstrate_certificate_auth()

    # Username/password auth
    demonstrate_username_password_auth()

    # Managed identity
    demonstrate_managed_identity()

    # Device code flow
    demonstrate_device_code_flow()

    # Multi-tenant
    demonstrate_multi_tenant_workflow()

    # Auth fallback
    demonstrate_auth_fallback()

    # Secure file handling
    demonstrate_secure_file_handling()

    print("\n✅ All authentication methods demonstrated!")
    print("   Choose the right method based on:")
    print("   - Security requirements")
    print("   - Infrastructure (Azure vs on-prem)")
    print("   - User interaction needs")
    print("   - Legacy system compatibility")
