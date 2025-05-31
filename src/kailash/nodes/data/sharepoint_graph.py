"""SharePoint Graph API connector nodes for the Kailash SDK.

This module provides nodes for connecting to SharePoint using Microsoft Graph API.
It supports modern authentication with MSAL and provides better compatibility
with Azure AD app registrations.

Design purpose:
- Enable seamless integration with SharePoint via Graph API
- Support app-only authentication with client credentials
- Provide operations for file management and search
- Align with database persistence requirements for orchestration

Upstream dependencies:
- Base node classes from kailash.nodes.base
- MSAL library for authentication
- Microsoft Graph API

Downstream consumers:
- Workflows that need to interact with SharePoint
- Orchestration systems reading from MongoDB
- Long-running workflows with state persistence
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
)


@register_node()
class SharePointGraphReader(Node):
    """Node for reading files from SharePoint using Microsoft Graph API.

    This node uses Microsoft Graph API with MSAL authentication, providing
    better compatibility with modern Azure AD app registrations compared
    to the legacy SharePoint REST API.

    Key features:
    1. Modern authentication with MSAL
    2. Support for listing, downloading, and searching files
    3. Folder navigation and library support
    4. Stateless design for orchestration compatibility
    5. JSON-serializable outputs for database persistence

    Usage patterns:
    1. List files in document libraries
    2. Download files to local storage
    3. Search for files by name
    4. Navigate folder structures

    Example::

        reader = SharePointGraphReader()
        result = reader.execute(
            tenant_id="your-tenant-id",
            client_id="your-client-id",
            client_secret="your-secret",
            site_url="https://company.sharepoint.com/sites/project",
            operation="list_files",
            library_name="Documents",
            folder_path="Reports/2024"
        )
    """

    def get_metadata(self) -> NodeMetadata:
        """Get node metadata for discovery and orchestration."""
        return NodeMetadata(
            name="SharePoint Graph Reader",
            description="Read files from SharePoint using Microsoft Graph API",
            tags={"sharepoint", "graph", "reader", "cloud", "microsoft"},
            version="2.0.0",
            author="Kailash SDK",
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for SharePoint Graph operations."""
        return {
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=False,
                description="Azure AD tenant ID",
            ),
            "client_id": NodeParameter(
                name="client_id",
                type=str,
                required=False,
                description="Azure AD app client ID",
            ),
            "client_secret": NodeParameter(
                name="client_secret",
                type=str,
                required=False,
                description="Azure AD app client secret",
            ),
            "site_url": NodeParameter(
                name="site_url",
                type=str,
                required=False,
                description="SharePoint site URL",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="list_files",
                description="Operation: list_files, download_file, search_files, list_libraries",
            ),
            "library_name": NodeParameter(
                name="library_name",
                type=str,
                required=False,
                default="Documents",
                description="Document library name",
            ),
            "folder_path": NodeParameter(
                name="folder_path",
                type=str,
                required=False,
                default="",
                description="Folder path within library",
            ),
            "file_name": NodeParameter(
                name="file_name",
                type=str,
                required=False,
                description="File name for download operation",
            ),
            "local_path": NodeParameter(
                name="local_path",
                type=str,
                required=False,
                description="Local path to save downloaded file",
            ),
            "search_query": NodeParameter(
                name="search_query",
                type=str,
                required=False,
                description="Search query for finding files",
            ),
        }

    def _authenticate(
        self, tenant_id: str, client_id: str, client_secret: str
    ) -> Dict[str, Any]:
        """Authenticate with Microsoft Graph API using MSAL.

        Returns dict with token and headers for stateless operation.
        """
        try:
            import msal
        except ImportError:
            raise NodeConfigurationError(
                "MSAL library not installed. Install with: pip install msal"
            )

        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" not in result:
            error_msg = result.get("error_description", "Unknown authentication error")
            raise NodeExecutionError(f"Authentication failed: {error_msg}")

        return {
            "token": result["access_token"],
            "headers": {
                "Authorization": f"Bearer {result['access_token']}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        }

    def _get_site_data(self, site_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """Get SharePoint site data from Graph API."""
        # Convert SharePoint URL to Graph API site ID format
        site_id = site_url.replace("https://", "").replace(
            ".sharepoint.com", ".sharepoint.com:"
        )
        site_endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}"

        response = requests.get(site_endpoint, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise NodeExecutionError(
                f"Failed to get site data: {response.status_code} - {response.text}"
            )

    def _list_libraries(
        self, site_id: str, headers: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """List all document libraries in the site."""
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        response = requests.get(drives_url, headers=headers)

        if response.status_code == 200:
            return response.json()["value"]
        else:
            raise NodeExecutionError(
                f"Failed to get libraries: {response.status_code} - {response.text}"
            )

    def _get_drive_id(
        self, site_id: str, library_name: str, headers: Dict[str, str]
    ) -> Optional[str]:
        """Get the drive ID for a specific library."""
        libraries = self._list_libraries(site_id, headers)
        for lib in libraries:
            if library_name.lower() in lib["name"].lower():
                return lib["id"]
        return None

    def _list_files(
        self, site_id: str, library_name: str, folder_path: str, headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """List files in a specific library and folder."""
        drive_id = self._get_drive_id(site_id, library_name, headers)
        if not drive_id:
            raise NodeExecutionError(f"Library '{library_name}' not found")

        # Build URL based on folder path
        if folder_path:
            folder_path = folder_path.strip("/")
            files_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}:/children"
        else:
            files_url = (
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
            )

        response = requests.get(files_url, headers=headers)

        if response.status_code == 200:
            items = response.json()["value"]

            files = []
            folders = []

            for item in items:
                if "file" in item:
                    files.append(
                        {
                            "name": item["name"],
                            "id": item["id"],
                            "size": item["size"],
                            "modified": item["lastModifiedDateTime"],
                            "download_url": item.get("@microsoft.graph.downloadUrl"),
                        }
                    )
                elif "folder" in item:
                    folders.append(
                        {
                            "name": item["name"],
                            "id": item["id"],
                            "child_count": item.get("folder", {}).get("childCount", 0),
                        }
                    )

            return {
                "library_name": library_name,
                "folder_path": folder_path,
                "file_count": len(files),
                "folder_count": len(folders),
                "files": files,
                "folders": folders,
            }
        else:
            raise NodeExecutionError(
                f"Failed to list files: {response.status_code} - {response.text}"
            )

    def _download_file(
        self,
        site_id: str,
        library_name: str,
        file_name: str,
        folder_path: str,
        local_path: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Download a file from SharePoint."""
        drive_id = self._get_drive_id(site_id, library_name, headers)
        if not drive_id:
            raise NodeExecutionError(f"Library '{library_name}' not found")

        # Build the file path
        if folder_path:
            folder_path = folder_path.strip("/")
            file_path = f"{folder_path}/{file_name}"
        else:
            file_path = file_name

        # Get file metadata
        file_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{file_path}"
        )
        response = requests.get(file_url, headers=headers)

        if response.status_code != 200:
            raise NodeExecutionError(
                f"File '{file_name}' not found: {response.status_code} - {response.text}"
            )

        file_data = response.json()
        download_url = file_data["@microsoft.graph.downloadUrl"]

        # Download the file
        file_response = requests.get(download_url)

        if file_response.status_code == 200:
            # Determine local path
            if not local_path:
                local_path = file_name

            # Ensure directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            with open(local_path, "wb") as f:
                f.write(file_response.content)

            return {
                "file_name": file_name,
                "file_path": file_path,
                "local_path": local_path,
                "file_size": len(file_response.content),
                "downloaded": True,
            }
        else:
            raise NodeExecutionError(
                f"Failed to download file: {file_response.status_code}"
            )

    def _search_files(
        self, site_id: str, library_name: str, query: str, headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Search for files in a library."""
        drive_id = self._get_drive_id(site_id, library_name, headers)
        if not drive_id:
            raise NodeExecutionError(f"Library '{library_name}' not found")

        search_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/search(q='{query}')"
        response = requests.get(search_url, headers=headers)

        if response.status_code == 200:
            items = response.json()["value"]

            files = []
            for item in items:
                if "file" in item:
                    files.append(
                        {
                            "name": item["name"],
                            "id": item["id"],
                            "size": item["size"],
                            "modified": item["lastModifiedDateTime"],
                            "parent_path": item.get("parentReference", {}).get(
                                "path", ""
                            ),
                        }
                    )

            return {
                "query": query,
                "library_name": library_name,
                "result_count": len(files),
                "files": files,
            }
        else:
            raise NodeExecutionError(
                f"Search failed: {response.status_code} - {response.text}"
            )

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute SharePoint Graph operation.

        This method is stateless and returns JSON-serializable results
        suitable for database persistence and orchestration.
        """
        # Validate required parameters
        tenant_id = kwargs.get("tenant_id")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        site_url = kwargs.get("site_url")

        if not all([tenant_id, client_id, client_secret, site_url]):
            raise NodeValidationError(
                "tenant_id, client_id, client_secret, and site_url are required"
            )

        # Get operation
        operation = kwargs.get("operation", "list_files")
        valid_operations = [
            "list_files",
            "download_file",
            "search_files",
            "list_libraries",
        ]
        if operation not in valid_operations:
            raise NodeValidationError(
                f"Invalid operation '{operation}'. Must be one of: {', '.join(valid_operations)}"
            )

        # Authenticate and get site data
        auth_data = self._authenticate(tenant_id, client_id, client_secret)
        headers = auth_data["headers"]
        site_data = self._get_site_data(site_url, headers)
        site_id = site_data["id"]

        # Execute operation
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
                raise NodeValidationError(
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
                raise NodeValidationError(
                    "search_query is required for search_files operation"
                )

            library_name = kwargs.get("library_name", "Documents")
            query = kwargs["search_query"]

            return self._search_files(site_id, library_name, query, headers)


@register_node()
class SharePointGraphWriter(Node):
    """Node for uploading files to SharePoint using Microsoft Graph API.

    This node handles file uploads to SharePoint document libraries,
    supporting folder structures and metadata.

    Example::

        writer = SharePointGraphWriter()
        result = writer.execute(
            tenant_id="your-tenant-id",
            client_id="your-client-id",
            client_secret="your-secret",
            site_url="https://company.sharepoint.com/sites/project",
            local_path="report.pdf",
            library_name="Documents",
            folder_path="Reports/2024",
            sharepoint_name="Q4_Report_2024.pdf"
        )
    """

    def get_metadata(self) -> NodeMetadata:
        """Get node metadata for discovery and orchestration."""
        return NodeMetadata(
            name="SharePoint Graph Writer",
            description="Upload files to SharePoint using Microsoft Graph API",
            tags={"sharepoint", "graph", "writer", "upload", "microsoft"},
            version="2.0.0",
            author="Kailash SDK",
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters for SharePoint upload operations."""
        return {
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=False,
                description="Azure AD tenant ID",
            ),
            "client_id": NodeParameter(
                name="client_id",
                type=str,
                required=False,
                description="Azure AD app client ID",
            ),
            "client_secret": NodeParameter(
                name="client_secret",
                type=str,
                required=False,
                description="Azure AD app client secret",
            ),
            "site_url": NodeParameter(
                name="site_url",
                type=str,
                required=False,
                description="SharePoint site URL",
            ),
            "local_path": NodeParameter(
                name="local_path",
                type=str,
                required=False,
                description="Local file path to upload",
            ),
            "sharepoint_name": NodeParameter(
                name="sharepoint_name",
                type=str,
                required=False,
                description="Name for file in SharePoint (defaults to local filename)",
            ),
            "library_name": NodeParameter(
                name="library_name",
                type=str,
                required=False,
                default="Documents",
                description="Target document library",
            ),
            "folder_path": NodeParameter(
                name="folder_path",
                type=str,
                required=False,
                default="",
                description="Target folder path within library",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute SharePoint upload operation."""
        # Validate required parameters
        tenant_id = kwargs.get("tenant_id")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        site_url = kwargs.get("site_url")
        local_path = kwargs.get("local_path")

        if not all([tenant_id, client_id, client_secret, site_url, local_path]):
            raise NodeValidationError(
                "tenant_id, client_id, client_secret, site_url, and local_path are required"
            )

        if not os.path.exists(local_path):
            raise NodeValidationError(f"Local file '{local_path}' not found")

        # Reuse authentication logic from reader
        reader = SharePointGraphReader()
        auth_data = reader._authenticate(tenant_id, client_id, client_secret)
        headers = auth_data["headers"]
        site_data = reader._get_site_data(site_url, headers)
        site_id = site_data["id"]

        # Get parameters
        library_name = kwargs.get("library_name", "Documents")
        folder_path = kwargs.get("folder_path", "")
        sharepoint_name = kwargs.get("sharepoint_name") or os.path.basename(local_path)

        # Get drive ID
        drive_id = reader._get_drive_id(site_id, library_name, headers)
        if not drive_id:
            raise NodeExecutionError(f"Library '{library_name}' not found")

        # Build upload path
        if folder_path:
            folder_path = folder_path.strip("/")
            upload_path = f"{folder_path}/{sharepoint_name}"
        else:
            upload_path = sharepoint_name

        # Upload file
        upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{upload_path}:/content"

        with open(local_path, "rb") as file_content:
            upload_headers = {
                "Authorization": headers["Authorization"],
                "Content-Type": "application/octet-stream",
            }

            response = requests.put(
                upload_url, headers=upload_headers, data=file_content.read()
            )

        if response.status_code in [200, 201]:
            result = response.json()
            return {
                "uploaded": True,
                "file_name": sharepoint_name,
                "file_id": result["id"],
                "file_path": upload_path,
                "library_name": library_name,
                "web_url": result.get("webUrl"),
                "size": result["size"],
                "created": result["createdDateTime"],
            }
        else:
            raise NodeExecutionError(
                f"Failed to upload file: {response.status_code} - {response.text}"
            )
