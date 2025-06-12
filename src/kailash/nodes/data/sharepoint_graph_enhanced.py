"""Enhanced SharePoint Graph API connector with multiple authentication methods.

This module provides an enhanced SharePointGraphReader that supports multiple
authentication methods beyond just client credentials.
"""

from typing import Any, Dict, Optional, Literal
import os
import base64
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import jwt
import requests
from datetime import datetime, timedelta

from kailash.nodes.data.sharepoint_graph import SharePointGraphReader
from kailash.nodes.base import NodeParameter, register_node
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


@register_node()
class SharePointGraphReaderEnhanced(SharePointGraphReader):
    """Enhanced SharePoint Graph Reader with multiple authentication methods.
    
    Supports:
    - Client Credentials (OAuth2 App-Only)
    - Certificate-based Authentication
    - Username/Password (Resource Owner Password)
    - Managed Identity (for Azure-hosted apps)
    - Device Code Flow (for devices without browsers)
    
    Example:
        ```python
        # Certificate-based auth
        reader = SharePointGraphReaderEnhanced()
        result = reader.execute(
            auth_method="certificate",
            tenant_id="your-tenant-id",
            client_id="your-client-id",
            certificate_path="/path/to/cert.pem",
            certificate_password="cert-password",
            site_url="https://company.sharepoint.com/sites/project",
            operation="list_files"
        )
        
        # Username/password auth
        reader = SharePointGraphReaderEnhanced()
        result = reader.execute(
            auth_method="username_password",
            tenant_id="your-tenant-id",
            client_id="your-client-id",
            username="user@company.com",
            password="user-password",
            site_url="https://company.sharepoint.com/sites/project",
            operation="list_files"
        )
        ```
    """
    
    def get_parameters(self) -> dict[str, NodeParameter]:
        """Extended parameters to support multiple auth methods."""
        params = super().get_parameters()
        
        # Add new authentication parameters
        params.update({
            "auth_method": NodeParameter(
                name="auth_method",
                type=str,
                required=False,
                default="client_credentials",
                description="Authentication method: client_credentials, certificate, username_password, managed_identity, device_code"
            ),
            # Certificate auth params
            "certificate_path": NodeParameter(
                name="certificate_path",
                type=str,
                required=False,
                description="Path to certificate file for certificate authentication"
            ),
            "certificate_password": NodeParameter(
                name="certificate_password",
                type=str,
                required=False,
                description="Password for certificate file (if encrypted)"
            ),
            "certificate_thumbprint": NodeParameter(
                name="certificate_thumbprint",
                type=str,
                required=False,
                description="Certificate thumbprint (alternative to file path)"
            ),
            # Username/password auth params
            "username": NodeParameter(
                name="username",
                type=str,
                required=False,
                description="Username for resource owner password flow"
            ),
            "password": NodeParameter(
                name="password",
                type=str,
                required=False,
                description="Password for resource owner password flow"
            ),
            # Managed identity params
            "use_system_identity": NodeParameter(
                name="use_system_identity",
                type=bool,
                required=False,
                default=True,
                description="Use system-assigned managed identity (vs user-assigned)"
            ),
            "managed_identity_client_id": NodeParameter(
                name="managed_identity_client_id",
                type=str,
                required=False,
                description="Client ID for user-assigned managed identity"
            ),
            # Device code params
            "device_code_callback": NodeParameter(
                name="device_code_callback",
                type=str,
                required=False,
                description="Callback function name for device code display"
            )
        })
        
        return params
    
    def _authenticate(self, tenant_id: str, client_id: str, client_secret: str = None) -> dict[str, Any]:
        """Override to route to appropriate auth method."""
        # This method is called by parent, but we'll override run() to handle routing
        return super()._authenticate(tenant_id, client_id, client_secret)
    
    def _authenticate_certificate(
        self, 
        tenant_id: str, 
        client_id: str,
        certificate_path: Optional[str] = None,
        certificate_password: Optional[str] = None,
        certificate_thumbprint: Optional[str] = None
    ) -> dict[str, Any]:
        """Authenticate using certificate-based authentication."""
        try:
            import msal
        except ImportError:
            raise NodeConfigurationError(
                "MSAL library not installed. Install with: pip install msal"
            )
        
        # Load certificate
        if certificate_path:
            with open(certificate_path, 'rb') as f:
                cert_data = f.read()
            
            # Try to load as PEM or DER
            try:
                if certificate_password:
                    from cryptography.hazmat.primitives.serialization import pkcs12
                    private_key, certificate, _ = pkcs12.load_key_and_certificates(
                        cert_data, 
                        certificate_password.encode() if certificate_password else None
                    )
                else:
                    # Load PEM certificate
                    certificate = x509.load_pem_x509_certificate(cert_data)
                    private_key = serialization.load_pem_private_key(
                        cert_data, 
                        password=None
                    )
            except Exception as e:
                raise NodeConfigurationError(f"Failed to load certificate: {e}")
            
            # Get thumbprint
            thumbprint = base64.urlsafe_b64encode(
                certificate.fingerprint(hashes.SHA1())
            ).decode('utf-8').rstrip('=')
            
            # Create client credential from certificate
            client_credential = {
                "private_key": private_key,
                "thumbprint": thumbprint,
                "public_certificate": certificate.public_bytes(serialization.Encoding.PEM).decode()
            }
        elif certificate_thumbprint:
            # Use provided thumbprint (assumes cert is already registered in Azure AD)
            client_credential = {"thumbprint": certificate_thumbprint}
        else:
            raise NodeConfigurationError(
                "Either certificate_path or certificate_thumbprint must be provided"
            )
        
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_credential,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        if "access_token" not in result:
            error_msg = result.get("error_description", "Unknown authentication error")
            raise NodeExecutionError(f"Certificate authentication failed: {error_msg}")
        
        return {
            "token": result["access_token"],
            "headers": {
                "Authorization": f"Bearer {result['access_token']}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        }
    
    def _authenticate_username_password(
        self,
        tenant_id: str,
        client_id: str,
        username: str,
        password: str
    ) -> dict[str, Any]:
        """Authenticate using username/password (Resource Owner Password Credentials)."""
        try:
            import msal
        except ImportError:
            raise NodeConfigurationError(
                "MSAL library not installed. Install with: pip install msal"
            )
        
        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        
        result = app.acquire_token_by_username_password(
            username=username,
            password=password,
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        if "access_token" not in result:
            error_msg = result.get("error_description", "Unknown authentication error")
            raise NodeExecutionError(f"Username/password authentication failed: {error_msg}")
        
        return {
            "token": result["access_token"],
            "headers": {
                "Authorization": f"Bearer {result['access_token']}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        }
    
    def _authenticate_managed_identity(
        self,
        use_system_identity: bool = True,
        managed_identity_client_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Authenticate using Azure Managed Identity."""
        # Managed Identity endpoint
        msi_endpoint = os.environ.get(
            "MSI_ENDPOINT",
            "http://169.254.169.254/metadata/identity/oauth2/token"
        )
        
        params = {
            "api-version": "2019-08-01",
            "resource": "https://graph.microsoft.com"
        }
        
        headers = {"Metadata": "true"}
        
        # Add secret if using App Service
        msi_secret = os.environ.get("MSI_SECRET")
        if msi_secret:
            headers["X-IDENTITY-HEADER"] = msi_secret
        
        # Use user-assigned identity if specified
        if not use_system_identity and managed_identity_client_id:
            params["client_id"] = managed_identity_client_id
        
        try:
            response = requests.get(msi_endpoint, params=params, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data["access_token"]
            
            return {
                "token": access_token,
                "headers": {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            }
        except Exception as e:
            raise NodeExecutionError(
                f"Managed Identity authentication failed: {e}. "
                "Ensure this code is running in an Azure environment with Managed Identity enabled."
            )
    
    def _authenticate_device_code(
        self,
        tenant_id: str,
        client_id: str,
        device_code_callback: Optional[str] = None
    ) -> dict[str, Any]:
        """Authenticate using device code flow."""
        try:
            import msal
        except ImportError:
            raise NodeConfigurationError(
                "MSAL library not installed. Install with: pip install msal"
            )
        
        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        
        flow = app.initiate_device_flow(scopes=["https://graph.microsoft.com/.default"])
        
        if "user_code" not in flow:
            raise NodeExecutionError("Failed to initiate device flow")
        
        # Display the code to user
        print(f"\nTo authenticate, visit: {flow['verification_uri']}")
        print(f"Enter code: {flow['user_code']}\n")
        
        # If callback provided, call it with the flow info
        if device_code_callback:
            try:
                callback_func = eval(device_code_callback)
                callback_func(flow)
            except:
                pass
        
        # Wait for user to authenticate
        result = app.acquire_token_by_device_flow(flow)
        
        if "access_token" not in result:
            error_msg = result.get("error_description", "Unknown authentication error")
            raise NodeExecutionError(f"Device code authentication failed: {error_msg}")
        
        return {
            "token": result["access_token"],
            "headers": {
                "Authorization": f"Bearer {result['access_token']}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        }
    
    def run(self, **kwargs) -> dict[str, Any]:
        """Execute SharePoint operation with selected authentication method."""
        auth_method = kwargs.get("auth_method", "client_credentials")
        
        # Validate common parameters
        site_url = kwargs.get("site_url")
        if not site_url:
            raise NodeConfigurationError("site_url is required")
        
        # Authenticate based on method
        if auth_method == "client_credentials":
            # Use parent's implementation
            return super().run(**kwargs)
            
        elif auth_method == "certificate":
            tenant_id = kwargs.get("tenant_id")
            client_id = kwargs.get("client_id")
            
            if not all([tenant_id, client_id]):
                raise NodeConfigurationError(
                    "tenant_id and client_id are required for certificate auth"
                )
            
            auth_data = self._authenticate_certificate(
                tenant_id=tenant_id,
                client_id=client_id,
                certificate_path=kwargs.get("certificate_path"),
                certificate_password=kwargs.get("certificate_password"),
                certificate_thumbprint=kwargs.get("certificate_thumbprint")
            )
            
        elif auth_method == "username_password":
            tenant_id = kwargs.get("tenant_id")
            client_id = kwargs.get("client_id")
            username = kwargs.get("username")
            password = kwargs.get("password")
            
            if not all([tenant_id, client_id, username, password]):
                raise NodeConfigurationError(
                    "tenant_id, client_id, username, and password are required"
                )
            
            auth_data = self._authenticate_username_password(
                tenant_id=tenant_id,
                client_id=client_id,
                username=username,
                password=password
            )
            
        elif auth_method == "managed_identity":
            auth_data = self._authenticate_managed_identity(
                use_system_identity=kwargs.get("use_system_identity", True),
                managed_identity_client_id=kwargs.get("managed_identity_client_id")
            )
            
        elif auth_method == "device_code":
            tenant_id = kwargs.get("tenant_id")
            client_id = kwargs.get("client_id")
            
            if not all([tenant_id, client_id]):
                raise NodeConfigurationError(
                    "tenant_id and client_id are required for device code auth"
                )
            
            auth_data = self._authenticate_device_code(
                tenant_id=tenant_id,
                client_id=client_id,
                device_code_callback=kwargs.get("device_code_callback")
            )
            
        else:
            raise NodeConfigurationError(
                f"Invalid auth_method: {auth_method}. "
                "Must be one of: client_credentials, certificate, username_password, "
                "managed_identity, device_code"
            )
        
        # After authentication, proceed with operation using parent's logic
        headers = auth_data["headers"]
        site_data = self._get_site_data(site_url, headers)
        site_id = site_data["id"]
        
        # Get operation and execute
        operation = kwargs.get("operation", "list_files")
        
        if operation == "list_libraries":
            libraries = self._list_libraries(site_id, headers)
            return {
                "site_name": site_data["displayName"],
                "library_count": len(libraries),
                "libraries": [
                    {"name": lib["name"], "id": lib["id"], "web_url": lib.get("webUrl")}
                    for lib in libraries
                ],
            }
        elif operation == "list_files":
            library_name = kwargs.get("library_name", "Documents")
            folder_path = kwargs.get("folder_path", "")
            return self._list_files(site_id, library_name, folder_path, headers)
        elif operation == "download_file":
            if not kwargs.get("file_name"):
                raise NodeConfigurationError(
                    "file_name is required for download_file operation"
                )
            library_name = kwargs.get("library_name", "Documents")
            file_name = kwargs["file_name"]
            folder_path = kwargs.get("folder_path", "")
            local_path = kwargs.get("local_path")
            return self._download_file(
                site_id, library_name, file_name, folder_path, local_path, headers
            )
        elif operation == "search_files":
            if not kwargs.get("search_query"):
                raise NodeConfigurationError(
                    "search_query is required for search_files operation"
                )
            library_name = kwargs.get("library_name", "Documents")
            query = kwargs["search_query"]
            return self._search_files(site_id, library_name, query, headers)
        else:
            raise NodeConfigurationError(
                f"Invalid operation: {operation}. "
                "Must be one of: list_libraries, list_files, download_file, search_files"
            )