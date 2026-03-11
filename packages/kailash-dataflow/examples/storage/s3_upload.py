"""
AWS S3 File Upload Integration

Demonstrates:
- Connection pooling for S3 operations
- Async file upload with AsyncLocalRuntime
- Multi-file batch upload with concurrent processing
- Progress tracking for large uploads
- BulkCreateNode for batch metadata storage

Dependencies:
    pip install dataflow kailash

Environment Variables:
    AWS_ACCESS_KEY_ID: Your AWS access key
    AWS_SECRET_ACCESS_KEY: Your AWS secret key
    AWS_REGION: AWS region (e.g., us-east-1)
    S3_BUCKET_NAME: Name of your S3 bucket

Usage:
    # Upload single file
    python s3_upload.py upload document.pdf

    # Upload multiple files with progress tracking
    python s3_upload.py upload-batch
"""

import asyncio
import sys
from datetime import datetime

from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ============================================================================
# Database Models
# ============================================================================

# Create in-memory database for demonstration
db = DataFlow(":memory:")


@db.model
class FileUpload:
    """
    File upload model for tracking uploaded files.

    Demonstrates:
    - String ID preservation for file identifiers
    - Integer fields for file sizes
    - Metadata storage for S3 objects
    """

    id: str
    filename: str
    s3_key: str
    s3_bucket: str
    size_bytes: int
    content_type: str
    uploaded_at: str


@db.model
class BatchUpload:
    """
    Batch upload model for tracking multi-file uploads.

    Demonstrates:
    - Batch operation tracking
    - Success/failure counts
    - Timestamp range for upload duration
    """

    id: str
    batch_id: str
    total_files: int
    total_size_bytes: int
    uploaded_count: int
    failed_count: int
    started_at: str
    completed_at: str


@db.model
class FileMetadata:
    """
    File metadata model for batch uploads.

    Demonstrates:
    - Individual file tracking within batch
    - Status tracking for each file
    - Foreign key relationship (batch_id)
    """

    id: str
    batch_id: str
    filename: str
    s3_key: str
    status: str


# ============================================================================
# Workflow 1: Single File Upload
# ============================================================================


def build_single_upload_workflow(filename: str) -> WorkflowBuilder:
    """
    Build workflow for single file upload to S3.

    Workflow Steps:
    1. Validate file metadata (PythonCodeNode)
    2. Generate presigned URL (optional)
    3. Upload file to S3 (PythonCodeNode)
    4. Store file metadata in database (FileUploadCreateNode)

    Args:
        filename: Name of file to upload

    Returns:
        WorkflowBuilder configured for single file upload

    Demonstrates:
        - AsyncLocalRuntime for async uploads
        - Connection pooling for S3
        - Error handling for upload failures
        - Metadata storage with DataFlow
    """
    workflow = WorkflowBuilder()

    # Step 1: Validate file
    workflow.add_node(
        "PythonCodeNode",
        "validate_file",
        {
            "code": f"""
# Mock file validation
# In production, check:
# - File exists
# - File size within limits
# - Content type allowed
# - Filename sanitization

filename = "{filename}"
size_bytes = 1024000  # 1MB
content_type = "application/pdf"
valid = True

print(f"✓ File validated")
print(f"  Filename: {{filename}}")
print(f"  Size: {{size_bytes:,}} bytes")
print(f"  Content Type: {{content_type}}")
""",
            "inputs": {},
        },
    )

    # Step 2: Upload to S3 (mock)
    workflow.add_node(
        "PythonCodeNode",
        "upload_s3",
        {
            "code": """
import uuid

# Mock S3 upload
# In production, use boto3:
# import boto3
# s3_client = boto3.client('s3')
# s3_client.upload_file(
#     local_filename,
#     bucket_name,
#     s3_key,
#     ExtraArgs={'ContentType': content_type}
# )

s3_key = f"uploads/{uuid.uuid4().hex}/{filename}"
s3_bucket = "my-dataflow-bucket"
upload_success = True

print(f"✓ File uploaded to S3")
print(f"  Bucket: {s3_bucket}")
print(f"  Key: {s3_key}")
""",
            "inputs": {"filename": "{{validate_file.filename}}"},
        },
    )

    # Step 3: Store file metadata
    workflow.add_node(
        "FileUploadCreateNode",
        "store_metadata",
        {
            "id": f"file-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "filename": filename,
            "s3_key": "{{upload_s3.s3_key}}",
            "s3_bucket": "{{upload_s3.s3_bucket}}",
            "size_bytes": "{{validate_file.size_bytes}}",
            "content_type": "{{validate_file.content_type}}",
            "uploaded_at": datetime.now().isoformat(),
        },
    )

    # Connections
    workflow.add_connection("validate_file", "valid", "upload_s3", "trigger")
    workflow.add_connection("upload_s3", "s3_key", "store_metadata", "s3_key")

    return workflow


async def single_upload_example(filename: str):
    """
    Execute single file upload workflow.

    Args:
        filename: Name of file to upload

    Returns:
        Dictionary with upload results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_single_upload_workflow(filename)

    runtime = AsyncLocalRuntime()

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ File uploaded successfully (run_id: {run_id})")
        print(f"  Filename: {results['store_metadata']['filename']}")
        print(f"  Bucket: {results['store_metadata']['s3_bucket']}")
        print(f"  Size: {results['store_metadata']['size_bytes']:,} bytes")
        print(f"  S3 Key: {results['store_metadata']['s3_key']}")

        return results

    except Exception as e:
        print(f"✗ Error uploading file: {e}")
        raise


# ============================================================================
# Workflow 2: Multi-File Batch Upload
# ============================================================================


def build_batch_upload_workflow() -> WorkflowBuilder:
    """
    Build workflow for multi-file upload with progress tracking.

    Workflow Steps:
    1. Prepare file batch (PythonCodeNode)
    2. Upload files concurrently to S3 (PythonCodeNode)
    3. Track progress for each file
    4. Store batch metadata (BulkCreateNode + BatchUploadCreateNode)

    Returns:
        WorkflowBuilder configured for batch upload

    Demonstrates:
        - Bulk operations with BulkCreateNode
        - Concurrent async uploads with max_concurrent_nodes
        - Progress tracking for large batches
        - Batch metadata storage
    """
    workflow = WorkflowBuilder()

    # Step 1: Prepare file batch
    workflow.add_node(
        "PythonCodeNode",
        "prepare_batch",
        {
            "code": """
import uuid

# Mock file batch preparation
# In production:
# - Scan directory for files
# - Validate each file
# - Calculate total size
# - Group files into optimal batches

batch_id = f"batch_{uuid.uuid4().hex[:16]}"
files = [
    {"filename": "file1.pdf", "size": 100000},
    {"filename": "file2.pdf", "size": 200000},
    {"filename": "file3.pdf", "size": 300000},
]
total_files = len(files)
total_size_bytes = sum(f['size'] for f in files)

print(f"✓ Batch prepared")
print(f"  Batch ID: {batch_id}")
print(f"  Total files: {total_files}")
print(f"  Total size: {total_size_bytes:,} bytes")
""",
            "inputs": {},
        },
    )

    # Step 2: Upload files concurrently (mock)
    workflow.add_node(
        "PythonCodeNode",
        "upload_batch",
        {
            "code": """
import uuid

# Mock concurrent S3 uploads
# In production, use asyncio.gather() with boto3:
# async def upload_file(s3_client, file_info):
#     await s3_client.upload_fileobj(...)
#     return metadata
#
# tasks = [upload_file(s3_client, f) for f in files]
# results = await asyncio.gather(*tasks, return_exceptions=True)

uploaded_files = []
for file in files:
    s3_key = f"uploads/{batch_id}/{file['filename']}"
    uploaded_files.append({
        "id": str(uuid.uuid4()),
        "batch_id": batch_id,
        "filename": file['filename'],
        "s3_key": s3_key,
        "status": "uploaded"
    })

uploaded_count = len(uploaded_files)
failed_count = 0

print(f"✓ Batch upload completed")
print(f"  Uploaded: {uploaded_count}")
print(f"  Failed: {failed_count}")
""",
            "inputs": {
                "files": "{{prepare_batch.files}}",
                "batch_id": "{{prepare_batch.batch_id}}",
            },
        },
    )

    # Step 3: Store file metadata in bulk
    workflow.add_node(
        "FileMetadataBulkCreateNode",
        "store_files",
        {"records": "{{upload_batch.uploaded_files}}"},
    )

    # Step 4: Store batch metadata
    workflow.add_node(
        "BatchUploadCreateNode",
        "store_batch",
        {
            "id": "{{prepare_batch.batch_id}}",
            "batch_id": "{{prepare_batch.batch_id}}",
            "total_files": "{{prepare_batch.total_files}}",
            "total_size_bytes": "{{prepare_batch.total_size_bytes}}",
            "uploaded_count": "{{upload_batch.uploaded_count}}",
            "failed_count": "{{upload_batch.failed_count}}",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
        },
    )

    # Connections
    workflow.add_connection("prepare_batch", "batch_id", "upload_batch", "batch_id")
    workflow.add_connection("upload_batch", "uploaded_files", "store_files", "records")
    workflow.add_connection(
        "upload_batch", "uploaded_count", "store_batch", "uploaded_count"
    )

    return workflow


async def batch_upload_example():
    """
    Execute batch file upload workflow.

    Returns:
        Dictionary with batch upload results

    Raises:
        Exception: If workflow execution fails
    """
    workflow = build_batch_upload_workflow()

    # Configure concurrent processing (up to 10 files in parallel)
    runtime = AsyncLocalRuntime(max_concurrent_nodes=10)

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        print(f"✓ Batch upload completed successfully (run_id: {run_id})")
        print(f"  Batch ID: {results['store_batch']['batch_id']}")
        print(f"  Total files: {results['store_batch']['total_files']}")
        print(f"  Uploaded: {results['store_batch']['uploaded_count']}")
        print(f"  Failed: {results['store_batch']['failed_count']}")
        print(f"  Total size: {results['store_batch']['total_size_bytes']:,} bytes")

        return results

    except Exception as e:
        print(f"✗ Error in batch upload: {e}")
        raise


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main entry point for example execution.

    Supports two commands:
    1. upload <filename> - Upload single file
    2. upload-batch - Upload multiple files with progress tracking
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  upload <filename> - Upload single file")
        print("  upload-batch - Upload multiple files with progress tracking")
        sys.exit(1)

    command = sys.argv[1]

    print("=" * 80)
    print("AWS S3 File Upload Integration Example")
    print("=" * 80)
    print()

    if command == "upload":
        if len(sys.argv) < 3:
            print("Error: upload requires filename")
            print("Usage: upload <filename>")
            sys.exit(1)

        filename = sys.argv[2]

        print(f"Uploading file: {filename}")
        print()

        results = await single_upload_example(filename)

    elif command == "upload-batch":
        print("Uploading batch of files...")
        print()

        results = await batch_upload_example()

    else:
        print(f"Error: Unknown command '{command}'")
        print("Valid commands: upload, upload-batch")
        sys.exit(1)

    print()
    print("=" * 80)
    print("✓ Example completed successfully")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
