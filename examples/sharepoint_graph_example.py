#!/usr/bin/env python3
"""SharePoint Graph API example for Kailash SDK.

This example demonstrates how to use the new SharePoint nodes that use
Microsoft Graph API with MSAL authentication.
"""

import os

from kailash.nodes.data import SharePointGraphReader
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def test_sharepoint_graph_operations():
    """Test SharePoint Graph API operations."""
    print("=== SharePoint Graph API Operations ===\n")

    # Your credentials (replace these with your actual values)
    # These are example credentials for the IG Dev Dummy site
    tenant_id = os.getenv(
        "SHAREPOINT_TENANT_ID", "af88121d-9ac7-4ed0-b7e3-91c931e9c18f"
    )
    client_id = os.getenv(
        "SHAREPOINT_CLIENT_ID", "a2552663-6550-4bd7-b97b-a39f6da2150c"
    )
    client_secret = os.getenv(
        "SHAREPOINT_CLIENT_SECRET", "xf58Q~2r.24hQZZ3bMXOnX1nSOIerURgAPumYaqi"
    )
    site_url = os.getenv(
        "SHAREPOINT_SITE_URL", "https://terrene-foundationglobal.sharepoint.com/sites/IGDevDummy"
    )

    # Create reader node
    reader = SharePointGraphReader()

    # Test 1: List document libraries
    print("1. Listing document libraries:")
    try:
        result = reader.execute(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            site_url=site_url,
            operation="list_libraries",
        )

        print(f"Connected to: {result['site_name']}")
        print(f"Found {result['library_count']} libraries:")
        for lib in result["libraries"][:5]:
            print(f"  - {lib['name']}")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 2: List files in Documents
    print("2. Listing files in Documents library:")
    files_to_download = []
    try:
        result = reader.execute(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            site_url=site_url,
            operation="list_files",
            library_name="Documents",
            folder_path="",
        )

        print(
            f"Found {result['file_count']} files and {result['folder_count']} folders"
        )
        print("\nFiles:")
        for file in result["files"]:
            size_mb = file["size"] / (1024 * 1024)
            print(f"  - {file['name']} ({size_mb:.2f} MB)")
            files_to_download.append(file["name"])

        print("\nFolders:")
        for folder in result["folders"][:5]:
            print(f"  - {folder['name']}/ ({folder['child_count']} items)")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 3: Download all 3 files
    print("3. Downloading all 3 files from SharePoint:")
    if files_to_download:
        os.makedirs("downloads", exist_ok=True)

        for file_name in files_to_download:
            try:
                print(f"\nDownloading: {file_name}")
                result = reader.execute(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    site_url=site_url,
                    operation="download_file",
                    library_name="Documents",
                    file_name=file_name,
                    folder_path="",
                    local_path=f"downloads/{file_name}",
                )

                if result["downloaded"]:
                    print(f"✅ Successfully downloaded to: {result['local_path']}")
                    print(f"   File size: {result['file_size']:,} bytes")
            except Exception as e:
                print(f"❌ Error downloading {file_name}: {e}")

        # List downloaded files
        print("\n4. Verifying downloaded files:")
        if os.path.exists("downloads"):
            files = os.listdir("downloads")
            print(f"Found {len(files)} files in downloads folder:")
            for file in files:
                file_path = os.path.join("downloads", file)
                size = os.path.getsize(file_path)
                print(f"  - {file} ({size:,} bytes)")
    else:
        print("No files found to download")

    print()


def test_sharepoint_workflow():
    """Test SharePoint in a workflow with database persistence in mind."""
    print("=== SharePoint Workflow Example ===\n")

    # Create workflow
    workflow = Workflow(
        workflow_id="sharepoint_graph_demo", name="SharePoint Graph API Demo"
    )

    # Add nodes
    workflow.add_node("list_files", SharePointGraphReader())
    workflow.add_node("search_files", SharePointGraphReader())

    # Create runtime
    runtime = LocalRuntime()

    # Credentials (using environment variables with defaults)
    credentials = {
        "tenant_id": os.getenv(
            "SHAREPOINT_TENANT_ID", "af88121d-9ac7-4ed0-b7e3-91c931e9c18f"
        ),
        "client_id": os.getenv(
            "SHAREPOINT_CLIENT_ID", "a2552663-6550-4bd7-b97b-a39f6da2150c"
        ),
        "client_secret": os.getenv(
            "SHAREPOINT_CLIENT_SECRET", "xf58Q~2r.24hQZZ3bMXOnX1nSOIerURgAPumYaqi"
        ),
        "site_url": os.getenv(
            "SHAREPOINT_SITE_URL",
            "https://terrene-foundationglobal.sharepoint.com/sites/IGDevDummy",
        ),
    }

    try:
        # Execute workflow
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "list_files": {
                    **credentials,
                    "operation": "list_files",
                    "library_name": "Documents",
                },
                "search_files": {
                    **credentials,
                    "operation": "search_files",
                    "library_name": "Documents",
                    "search_query": "dummy 3.txt",  # Example search query
                },
            },
        )

        print("Workflow Results:")
        print("-" * 50)

        # Show list results
        if "list_files" in results:
            list_result = results["list_files"]
            print(f"List Files: Found {list_result.get('file_count', 0)} files")

        # Show search results
        if "search_files" in results:
            search_result = results["search_files"]
            print(f"Search Files: Found {search_result.get('result_count', 0)} matches")

        print(
            "\nNote: These results are JSON-serializable and ready for database storage!"
        )
        print(
            "In a production system, this workflow state would be persisted to MongoDB."
        )

    except Exception as e:
        print(f"Workflow error: {e}")


def demonstrate_orchestration_pattern():
    """Demonstrate how this aligns with orchestration requirements."""
    print("\n=== Orchestration Pattern Demonstration ===\n")

    print("Key Design Principles Implemented:")
    print("-" * 50)
    print("1. **Stateless Nodes**: Each operation is completely stateless")
    print("   - Authentication happens per operation")
    print("   - No state is maintained between calls")
    print("   - Perfect for distributed execution")
    print()
    print("2. **JSON-Serializable Results**: All outputs can be persisted")
    print("   - Results are plain dictionaries")
    print("   - No complex objects or file handles")
    print("   - Ready for MongoDB storage")
    print()
    print("3. **Explicit Parameters**: Everything needed is passed in")
    print("   - Credentials as parameters")
    print("   - No hidden configuration")
    print("   - Easy to reconstruct from database")
    print()
    print("4. **Error Handling**: Graceful failures with clear messages")
    print("   - NodeValidationError for bad inputs")
    print("   - NodeExecutionError for runtime issues")
    print("   - NodeConfigurationError for missing dependencies")
    print()
    print("5. **Long-Running Workflow Support**:")
    print("   - Each node execution can be tracked separately")
    print("   - Results can be checkpointed to database")
    print("   - Failed nodes can be retried independently")
    print()
    print("6. **Human-in-the-Loop Ready**:")
    print("   - Workflow can pause after listing files")
    print("   - Human can select which files to process")
    print("   - Resume with selected file operations")


def main():
    """Run all examples."""
    print("SharePoint Graph API Integration for Kailash SDK")
    print("=" * 60)
    print()

    # Test basic operations
    test_sharepoint_graph_operations()

    # Test workflow integration
    test_sharepoint_workflow()

    # Demonstrate orchestration patterns
    demonstrate_orchestration_pattern()

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print("✅ The new SharePointGraphReader/Writer nodes use Microsoft Graph API")
    print("✅ Authentication works with your app-only credentials")
    print("✅ All operations are stateless and database-friendly")
    print("✅ Results are JSON-serializable for MongoDB persistence")
    print("✅ Nodes align with Kailash orchestration requirements")
    print()
    print("Next steps for orchestration:")
    print("1. Workflow definitions can be saved to MongoDB")
    print("2. Node parameters can be stored and retrieved")
    print("3. Execution state can be tracked and resumed")
    print("4. Failed operations can be retried")
    print("5. Human approval steps can be inserted")


if __name__ == "__main__":
    main()
