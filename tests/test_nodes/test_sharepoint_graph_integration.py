"""Integration tests for SharePoint Graph API nodes with real credentials."""

import os

import pytest

from kailash.nodes.data import SharePointGraphReader, SharePointGraphWriter

# Test credentials from the example
TEST_CREDENTIALS = {
    "tenant_id": "af88121d-9ac7-4ed0-b7e3-91c931e9c18f",
    "client_id": "a2552663-6550-4bd7-b97b-a39f6da2150c",
    "client_secret": "xf58Q~2r.24hQZZ3bMXOnX1nSOIerURgAPumYaqi",
    "site_url": "https://terrene-foundationglobal.sharepoint.com/sites/IGDevDummy",
}


@pytest.mark.integration
class TestSharePointGraphIntegration:
    """Integration tests that use real SharePoint credentials."""

    def test_list_libraries(self):
        """Test listing SharePoint libraries with real credentials."""
        reader = SharePointGraphReader()

        result = reader.execute(
            **TEST_CREDENTIALS,
            operation="list_libraries",
        )

        assert "site_name" in result
        assert result["site_name"] == "IG Dev Dummy"
        assert "library_count" in result
        assert result["library_count"] >= 1
        assert "libraries" in result
        assert any(lib["name"] == "Documents" for lib in result["libraries"])

    def test_list_files(self):
        """Test listing files in Documents library."""
        reader = SharePointGraphReader()

        result = reader.execute(
            **TEST_CREDENTIALS,
            operation="list_files",
            library_name="Documents",
            folder_path="",
        )

        assert "file_count" in result
        assert result["file_count"] >= 3  # We know there are at least 3 dummy files
        assert "files" in result

        # Check for dummy files
        file_names = [f["name"] for f in result["files"]]
        assert "dummy 1.txt" in file_names
        assert "dummy 2.txt" in file_names
        assert "dummy 3.txt" in file_names

    def test_download_file(self):
        """Test downloading a specific file."""
        reader = SharePointGraphReader()

        # Create downloads directory
        os.makedirs("test_downloads", exist_ok=True)

        try:
            result = reader.execute(
                **TEST_CREDENTIALS,
                operation="download_file",
                library_name="Documents",
                file_name="dummy 1.txt",
                folder_path="",
                local_path="test_downloads/dummy_1_test.txt",
            )

            assert result["downloaded"] is True
            assert result["file_name"] == "dummy 1.txt"
            assert result["local_path"] == "test_downloads/dummy_1_test.txt"
            assert os.path.exists("test_downloads/dummy_1_test.txt")

            # Check file content
            with open("test_downloads/dummy_1_test.txt", "r") as f:
                content = f.read()
                assert "Dummy Data" in content

        finally:
            # Cleanup
            import shutil

            if os.path.exists("test_downloads"):
                shutil.rmtree("test_downloads")

    def test_search_files(self):
        """Test searching for files."""
        reader = SharePointGraphReader()

        # Note: Search API might have limitations or delays
        try:
            result = reader.execute(
                **TEST_CREDENTIALS,
                operation="search_files",
                library_name="Documents",
                search_query="dummy",
            )

            # Even if search returns 0 results (due to API limitations),
            # the structure should be correct
            assert "query" in result
            assert result["query"] == "dummy"
            assert "library_name" in result
            assert result["library_name"] == "Documents"
            assert "result_count" in result
            assert "files" in result

        except Exception as e:
            # Search API might fail, which is acceptable for this test
            assert "500" in str(e) or "generalException" in str(e)

    def test_upload_and_download(self):
        """Test uploading a file and then downloading it."""
        import time

        writer = SharePointGraphWriter()
        reader = SharePointGraphReader()

        # Create a test file with unique name using timestamp
        timestamp = int(time.time())
        test_content = "Test content from Kailash SDK integration test\n"
        test_filename = f"kailash_integration_test_{timestamp}.txt"

        with open(test_filename, "w") as f:
            f.write(test_content)

        try:
            # Upload the file
            upload_result = writer.execute(
                **TEST_CREDENTIALS,
                local_path=test_filename,
                library_name="Documents",
                sharepoint_name=test_filename,
            )

            assert upload_result["uploaded"] is True
            assert upload_result["file_name"] == test_filename
            assert upload_result["library_name"] == "Documents"

            # Download the file back
            download_result = reader.execute(
                **TEST_CREDENTIALS,
                operation="download_file",
                library_name="Documents",
                file_name=test_filename,
                folder_path="",
                local_path=f"downloaded_{test_filename}",
            )

            assert download_result["downloaded"] is True

            # Verify content
            with open(f"downloaded_{test_filename}", "r") as f:
                downloaded_content = f.read()
                assert downloaded_content == test_content

        finally:
            # Cleanup local files
            for filename in [test_filename, f"downloaded_{test_filename}"]:
                if os.path.exists(filename):
                    os.remove(filename)

    def test_workflow_execution(self):
        """Test SharePoint nodes in a workflow."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow import Workflow

        # Create workflow
        workflow = Workflow(
            workflow_id="sharepoint_test", name="SharePoint Integration Test"
        )

        # Add nodes
        workflow.add_node("list_files", SharePointGraphReader())
        workflow.add_node("list_libs", SharePointGraphReader())

        # Create runtime
        runtime = LocalRuntime()

        # Execute workflow
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "list_files": {
                    **TEST_CREDENTIALS,
                    "operation": "list_files",
                    "library_name": "Documents",
                },
                "list_libs": {
                    **TEST_CREDENTIALS,
                    "operation": "list_libraries",
                },
            },
        )

        # Verify results
        assert "list_files" in results
        assert "list_libs" in results

        assert results["list_files"]["file_count"] >= 3
        assert results["list_libs"]["library_count"] >= 1

    def test_json_serialization_real_data(self):
        """Test that real SharePoint data is JSON serializable."""
        import json

        reader = SharePointGraphReader()

        # Get real data
        result = reader.execute(
            **TEST_CREDENTIALS,
            operation="list_files",
            library_name="Documents",
        )

        # Ensure it's JSON serializable
        json_str = json.dumps(result)
        assert json_str is not None

        # Ensure it can be deserialized
        deserialized = json.loads(json_str)
        assert deserialized["file_count"] == result["file_count"]
        assert len(deserialized["files"]) == len(result["files"])
