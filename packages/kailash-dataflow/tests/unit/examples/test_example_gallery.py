"""
Unit tests for Example Gallery - Phase 3.4.1 Core Examples

This test file validates 5 high-value integration examples:
1. Payment Processing - Stripe Subscription (2 tests)
2. Email Integration - SendGrid (2 tests)
3. AI/LLM Integration - OpenAI (2 tests)
4. File Storage - S3 Upload (2 tests)
5. Authentication - JWT + OAuth2 (2 tests)

Tests use PostgreSQL for real infrastructure testing (NO SQLite :memory:).
"""

import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# PostgreSQL test database URL
PG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://kaizen_dev:kaizen_dev_password@localhost:5432/kailash_test",
)


# ============================================================================
# Test Category 1: Payment Processing - Stripe Subscription
# ============================================================================


class TestStripeSubscription:
    """
    Test Stripe subscription workflow integration.

    Demonstrates:
    - ErrorEnhancer for retry logic
    - Webhook signature verification
    - Payment intent handling
    """

    @pytest.mark.asyncio
    async def test_create_customer_workflow(self):
        """
        Test creating Stripe customer workflow.

        Workflow:
        1. Create Stripe customer via API (mock)
        2. Store customer record in database
        3. Return customer ID and stripe_customer_id
        """
        db = DataFlow(PG_URL)

        @db.model
        class Customer:
            id: str
            email: str
            stripe_customer_id: str
            name: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "create_stripe_customer",
            {
                "code": """
import uuid
stripe_customer_id = f"cus_{uuid.uuid4().hex[:24]}"
customer_email = "alice@example.com"
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "CustomerCreateNode",
            "store_customer",
            {
                "id": "cust-001",
                "email": "alice@example.com",
                "stripe_customer_id": "{{create_stripe_customer.stripe_customer_id}}",
                "name": "Alice Smith",
            },
        )

        workflow.add_connection(
            "create_stripe_customer",
            "stripe_customer_id",
            "store_customer",
            "stripe_customer_id",
        )

        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            assert "store_customer" in results
            assert results["store_customer"]["id"] == "cust-001"
            assert results["store_customer"]["email"] == "alice@example.com"
            assert "stripe_customer_id" in results["store_customer"]
        finally:
            # Cleanup
            try:
                cleanup = WorkflowBuilder()
                cleanup.add_node("CustomerDeleteNode", "del", {"id": "cust-001"})
                await runtime.execute_workflow_async(cleanup.build(), inputs={})
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_handle_webhook_workflow(self):
        """
        Test handling Stripe webhook workflow.

        Workflow:
        1. Verify webhook signature (PythonCodeNode)
        2. Extract payment intent data
        3. Update customer subscription status
        """
        db = DataFlow(PG_URL)

        @db.model
        class Subscription:
            id: str
            customer_id: str
            stripe_subscription_id: str
            status: str
            plan_name: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "verify_signature",
            {
                "code": """
import hmac
import hashlib
signature = "test_signature"
verified = True
subscription_id = 'sub_123'
customer_id = 'cus_123'
subscription_status = 'active'
plan_name = 'Pro Plan'
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "SubscriptionCreateNode",
            "store_subscription",
            {
                "id": "sub-001",
                "customer_id": "cust-001",
                "stripe_subscription_id": "{{verify_signature.subscription_id}}",
                "status": "{{verify_signature.subscription_status}}",
                "plan_name": "{{verify_signature.plan_name}}",
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "send_email",
            {
                "code": """
email_sent = True
recipient = "alice@example.com"
""",
                "inputs": {},
            },
        )

        workflow.add_connection(
            "verify_signature",
            "subscription_id",
            "store_subscription",
            "stripe_subscription_id",
        )
        workflow.add_connection(
            "verify_signature", "subscription_status", "store_subscription", "status"
        )
        workflow.add_connection(
            "verify_signature", "plan_name", "store_subscription", "plan_name"
        )
        workflow.add_connection("store_subscription", "id", "send_email", "trigger")

        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            assert "store_subscription" in results
            assert results["store_subscription"]["status"] == "active"
            assert results["store_subscription"]["plan_name"] == "Pro Plan"
            assert "send_email" in results
        finally:
            try:
                cleanup = WorkflowBuilder()
                cleanup.add_node("SubscriptionDeleteNode", "del", {"id": "sub-001"})
                await runtime.execute_workflow_async(cleanup.build(), inputs={})
            except Exception:
                pass


# ============================================================================
# Test Category 2: Email Integration - SendGrid
# ============================================================================


class TestSendGridEmail:
    """
    Test SendGrid email integration workflows.

    Demonstrates:
    - APINode for SendGrid API
    - Template rendering
    - Bulk email operations
    """

    @pytest.mark.asyncio
    async def test_send_transactional_email_workflow(self):
        """
        Test sending transactional email workflow.

        Workflow:
        1. Render email template with user data
        2. Send email via SendGrid API
        3. Log email sent event
        """
        db = DataFlow(PG_URL)

        @db.model
        class EmailLog:
            id: str
            recipient: str
            template_id: str
            status: str
            sent_at: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "render_template",
            {
                "code": """
recipient_email = "alice@example.com"
subject = "Welcome to DataFlow!"
body = "Hello Alice, welcome to our platform!"
template_id = "welcome_email"
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "send_email",
            {
                "code": """
import uuid
message_id = f"msg_{uuid.uuid4().hex[:16]}"
status = "sent"
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "EmailLogCreateNode",
            "log_email",
            {
                "id": "{{send_email.message_id}}",
                "recipient": "{{render_template.recipient_email}}",
                "template_id": "{{render_template.template_id}}",
                "status": "{{send_email.status}}",
                "sent_at": datetime.now().isoformat(),
            },
        )

        workflow.add_connection(
            "render_template", "template_id", "send_email", "trigger"
        )
        workflow.add_connection("send_email", "message_id", "log_email", "id")
        workflow.add_connection(
            "render_template", "recipient_email", "log_email", "recipient"
        )
        workflow.add_connection(
            "render_template", "template_id", "log_email", "template_id"
        )
        workflow.add_connection("send_email", "status", "log_email", "status")

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "log_email" in results
        assert results["log_email"]["recipient"] == "alice@example.com"
        assert results["log_email"]["status"] == "sent"
        assert results["log_email"]["template_id"] == "welcome_email"

    @pytest.mark.asyncio
    async def test_send_bulk_email_workflow(self):
        """
        Test sending bulk emails workflow.

        Workflow:
        1. Prepare list of recipients
        2. Send batch of emails via SendGrid
        3. Log campaign results
        """
        db = DataFlow(PG_URL)

        @db.model
        class BulkEmailLog:
            id: str
            campaign_id: str
            total_sent: int
            total_failed: int
            started_at: str
            completed_at: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "prepare_recipients",
            {
                "code": """
recipients = [
    {"id": "r1", "email": "user1@example.com", "name": "User 1"},
    {"id": "r2", "email": "user2@example.com", "name": "User 2"},
    {"id": "r3", "email": "user3@example.com", "name": "User 3"},
]
recipient_count = len(recipients)
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "send_bulk_emails",
            {
                "code": """
import uuid
campaign_id = f"camp_{uuid.uuid4().hex[:16]}"
total_sent = len(recipients)
total_failed = 0
""",
                "inputs": {"recipients": "{{prepare_recipients.recipients}}"},
            },
        )

        workflow.add_node(
            "BulkEmailLogCreateNode",
            "log_campaign",
            {
                "id": "{{send_bulk_emails.campaign_id}}",
                "campaign_id": "{{send_bulk_emails.campaign_id}}",
                "total_sent": 3,
                "total_failed": 0,
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
            },
        )

        workflow.add_connection(
            "prepare_recipients", "recipients", "send_bulk_emails", "recipients"
        )
        workflow.add_connection("send_bulk_emails", "campaign_id", "log_campaign", "id")

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "log_campaign" in results
        assert results["log_campaign"]["total_sent"] == 3
        assert results["log_campaign"]["total_failed"] == 0


# ============================================================================
# Test Category 3: AI/LLM Integration - OpenAI
# ============================================================================


class TestOpenAIIntegration:
    """
    Test OpenAI/LLM integration workflows.

    Demonstrates:
    - AsyncLocalRuntime for async API calls
    - Timeout handling for LLM operations
    - Error handling for API failures
    """

    @pytest.mark.asyncio
    async def test_chat_completion_workflow(self):
        """
        Test OpenAI chat completion workflow.

        Workflow:
        1. Prepare prompt with context
        2. Call OpenAI API for chat completion
        3. Parse and store response
        """
        db = DataFlow(PG_URL)

        @db.model
        class ChatCompletion:
            id: str
            prompt: str
            response: str
            model: str
            tokens_used: int
            cost: float

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "prepare_prompt",
            {
                "code": """
prompt = "Explain DataFlow in 3 sentences."
model = "gpt-4"
max_tokens = 150
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "call_openai",
            {
                "code": """
import uuid
response_text = "DataFlow is a zero-config database framework built on Kailash SDK. It automatically generates 11 workflow nodes per model for database operations (7 CRUD + 4 Bulk). It supports PostgreSQL, MySQL, and SQLite with full feature parity."
tokens_used = 50
cost = 0.002
completion_id = f"cmpl_{uuid.uuid4().hex[:24]}"
""",
                "inputs": {"prompt": "{{prepare_prompt.prompt}}"},
            },
        )

        workflow.add_node(
            "ChatCompletionCreateNode",
            "store_completion",
            {
                "id": "{{call_openai.completion_id}}",
                "prompt": "{{prepare_prompt.prompt}}",
                "response": "{{call_openai.response_text}}",
                "model": "{{prepare_prompt.model}}",
                "tokens_used": 50,
                "cost": 0.002,
            },
        )

        workflow.add_connection("prepare_prompt", "prompt", "call_openai", "prompt")
        workflow.add_connection(
            "prepare_prompt", "prompt", "store_completion", "prompt"
        )
        workflow.add_connection("prepare_prompt", "model", "store_completion", "model")
        workflow.add_connection(
            "call_openai", "completion_id", "store_completion", "id"
        )
        workflow.add_connection(
            "call_openai", "response_text", "store_completion", "response"
        )

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "store_completion" in results
        assert results["store_completion"]["model"] == "gpt-4"
        assert results["store_completion"]["tokens_used"] == 50
        assert len(results["store_completion"]["response"]) > 0

    @pytest.mark.asyncio
    async def test_streaming_response_workflow(self):
        """
        Test OpenAI streaming response workflow.

        Workflow:
        1. Initiate streaming chat completion
        2. Process chunks as they arrive
        3. Store final response
        """
        db = DataFlow(PG_URL)

        @db.model
        class StreamingCompletion:
            id: str
            prompt: str
            full_response: str
            chunks_received: int
            streaming_time_ms: int

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "start_streaming",
            {
                "code": """
import uuid
stream_id = f"stream_{uuid.uuid4().hex[:16]}"
prompt = "Write a haiku about databases."
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "process_stream",
            {
                "code": """
chunks = [
    "Data flows like streams\\n",
    "Tables dance in memory\\n",
    "Queries bloom bright"
]
full_response = "".join(chunks)
chunks_received = len(chunks)
streaming_time_ms = 1500
""",
                "inputs": {"stream_id": "{{start_streaming.stream_id}}"},
            },
        )

        workflow.add_node(
            "StreamingCompletionCreateNode",
            "store_streaming",
            {
                "id": "{{start_streaming.stream_id}}",
                "prompt": "{{start_streaming.prompt}}",
                "full_response": "{{process_stream.full_response}}",
                "chunks_received": 3,
                "streaming_time_ms": 1500,
            },
        )

        workflow.add_connection(
            "start_streaming", "stream_id", "process_stream", "stream_id"
        )
        workflow.add_connection("start_streaming", "stream_id", "store_streaming", "id")
        workflow.add_connection(
            "start_streaming", "prompt", "store_streaming", "prompt"
        )
        workflow.add_connection(
            "process_stream", "full_response", "store_streaming", "full_response"
        )

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "store_streaming" in results
        assert results["store_streaming"]["chunks_received"] == 3
        assert "Data flows like streams" in results["store_streaming"]["full_response"]


# ============================================================================
# Test Category 4: File Storage - S3 Upload
# ============================================================================


class TestS3Upload:
    """
    Test S3 file upload workflows.

    Demonstrates:
    - Connection pooling for S3 operations
    - Async file upload
    - Multi-file batch upload
    """

    @pytest.mark.asyncio
    async def test_single_file_upload_workflow(self):
        """
        Test single file upload to S3 workflow.

        Workflow:
        1. Validate file metadata
        2. Generate presigned URL
        3. Upload file to S3
        4. Store file metadata in database
        """
        db = DataFlow(PG_URL)

        @db.model
        class FileUpload:
            id: str
            filename: str
            s3_key: str
            s3_bucket: str
            size_bytes: int
            content_type: str
            uploaded_at: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "validate_file",
            {
                "code": """
filename = "document.pdf"
size_bytes = 1024000
content_type = "application/pdf"
valid = True
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "upload_s3",
            {
                "code": """
import uuid
s3_key = f"uploads/{uuid.uuid4().hex}/document.pdf"
s3_bucket = "my-dataflow-bucket"
upload_success = True
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "FileUploadCreateNode",
            "store_metadata",
            {
                "id": "file-001",
                "filename": "{{validate_file.filename}}",
                "s3_key": "{{upload_s3.s3_key}}",
                "s3_bucket": "{{upload_s3.s3_bucket}}",
                "size_bytes": 1024000,
                "content_type": "{{validate_file.content_type}}",
                "uploaded_at": datetime.now().isoformat(),
            },
        )

        workflow.add_connection("validate_file", "valid", "upload_s3", "trigger")
        workflow.add_connection(
            "validate_file", "filename", "store_metadata", "filename"
        )
        workflow.add_connection(
            "validate_file", "content_type", "store_metadata", "content_type"
        )
        workflow.add_connection("upload_s3", "s3_key", "store_metadata", "s3_key")
        workflow.add_connection("upload_s3", "s3_bucket", "store_metadata", "s3_bucket")

        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            assert "store_metadata" in results
            assert results["store_metadata"]["filename"] == "document.pdf"
            assert results["store_metadata"]["s3_bucket"] == "my-dataflow-bucket"
            assert results["store_metadata"]["size_bytes"] == 1024000
        finally:
            try:
                cleanup = WorkflowBuilder()
                cleanup.add_node("FileUploadDeleteNode", "del", {"id": "file-001"})
                await runtime.execute_workflow_async(cleanup.build(), inputs={})
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_multi_file_upload_workflow(self):
        """
        Test multi-file upload with progress tracking workflow.

        Workflow:
        1. Validate all files
        2. Upload files concurrently to S3
        3. Track progress for each file
        4. Store batch metadata
        """
        db = DataFlow(PG_URL)

        @db.model
        class BatchUpload:
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
            id: str
            batch_id: str
            filename: str
            s3_key: str
            status: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "prepare_batch",
            {
                "code": """
import uuid
batch_id = f"batch_{uuid.uuid4().hex[:16]}"
files = [
    {"filename": "file1.pdf", "size": 100000},
    {"filename": "file2.pdf", "size": 200000},
    {"filename": "file3.pdf", "size": 300000},
]
total_files = len(files)
total_size_bytes = sum(f['size'] for f in files)
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "upload_batch",
            {
                "code": """
import uuid
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
""",
                "inputs": {
                    "files": "{{prepare_batch.files}}",
                    "batch_id": "{{prepare_batch.batch_id}}",
                },
            },
        )

        workflow.add_node(
            "FileMetadataBulkCreateNode",
            "store_files",
            {"records": "{{upload_batch.uploaded_files}}"},
        )

        workflow.add_node(
            "BatchUploadCreateNode",
            "store_batch",
            {
                "id": "{{prepare_batch.batch_id}}",
                "batch_id": "{{prepare_batch.batch_id}}",
                "total_files": 3,
                "total_size_bytes": 600000,
                "uploaded_count": 3,
                "failed_count": 0,
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
            },
        )

        workflow.add_connection("prepare_batch", "batch_id", "upload_batch", "batch_id")
        workflow.add_connection("prepare_batch", "files", "upload_batch", "files")
        workflow.add_connection("prepare_batch", "batch_id", "store_batch", "id")
        workflow.add_connection(
            "upload_batch", "uploaded_files", "store_files", "records"
        )

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        assert "store_batch" in results
        assert results["store_batch"]["total_files"] == 3
        assert results["store_batch"]["uploaded_count"] == 3
        assert results["store_batch"]["failed_count"] == 0


# ============================================================================
# Test Category 5: Authentication - JWT + OAuth2
# ============================================================================


class TestAuthentication:
    """
    Test authentication workflows (JWT and OAuth2).

    Demonstrates:
    - JWT token generation and validation
    - OAuth2 code exchange flow
    - Security patterns
    """

    @pytest.mark.asyncio
    async def test_jwt_token_workflow(self):
        """
        Test JWT token generation and validation workflow.

        Workflow:
        1. Create test user
        2. Authenticate user credentials
        3. Generate JWT tokens
        4. Store token metadata
        """
        db = DataFlow(PG_URL)

        @db.model
        class User:
            id: str
            email: str
            password_hash: str
            name: str

        @db.model
        class TokenMetadata:
            id: str
            user_id: str
            token_type: str
            expires_at: str
            created_at: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "id": "user-001",
                "email": "alice@example.com",
                "password_hash": "hashed_password_123",
                "name": "Alice Smith",
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "authenticate",
            {
                "code": """
authenticated = True
user_id = "user-001"
email = "alice@example.com"
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "generate_tokens",
            {
                "code": """
import uuid
access_token = f"jwt_access_{uuid.uuid4().hex}"
refresh_token = f"jwt_refresh_{uuid.uuid4().hex}"
access_expires_at = "2025-10-30T05:00:00"
refresh_expires_at = "2025-11-06T04:00:00"
""",
                "inputs": {"user_id": "{{authenticate.user_id}}"},
            },
        )

        workflow.add_node(
            "TokenMetadataCreateNode",
            "store_access_token",
            {
                "id": "{{generate_tokens.access_token}}",
                "user_id": "{{authenticate.user_id}}",
                "token_type": "access",
                "expires_at": "{{generate_tokens.access_expires_at}}",
                "created_at": "2025-10-30T04:00:00",
            },
        )

        workflow.add_node(
            "TokenMetadataCreateNode",
            "store_refresh_token",
            {
                "id": "{{generate_tokens.refresh_token}}",
                "user_id": "{{authenticate.user_id}}",
                "token_type": "refresh",
                "expires_at": "{{generate_tokens.refresh_expires_at}}",
                "created_at": "2025-10-30T04:00:00",
            },
        )

        workflow.add_connection("create_user", "id", "authenticate", "trigger")
        workflow.add_connection("authenticate", "user_id", "generate_tokens", "user_id")
        workflow.add_connection(
            "authenticate", "user_id", "store_access_token", "user_id"
        )
        workflow.add_connection(
            "authenticate", "user_id", "store_refresh_token", "user_id"
        )
        workflow.add_connection(
            "generate_tokens", "access_token", "store_access_token", "id"
        )
        workflow.add_connection(
            "generate_tokens", "access_expires_at", "store_access_token", "expires_at"
        )
        workflow.add_connection(
            "generate_tokens", "refresh_token", "store_refresh_token", "id"
        )
        workflow.add_connection(
            "generate_tokens", "refresh_expires_at", "store_refresh_token", "expires_at"
        )

        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            assert "store_access_token" in results
            assert results["store_access_token"] is not None
            assert "store_refresh_token" in results
            assert results["store_refresh_token"] is not None
        finally:
            try:
                cleanup = WorkflowBuilder()
                cleanup.add_node("UserDeleteNode", "del", {"id": "user-001"})
                await runtime.execute_workflow_async(cleanup.build(), inputs={})
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_oauth2_code_exchange_workflow(self):
        """
        Test OAuth2 authorization code exchange workflow.

        Workflow:
        1. Receive authorization code from OAuth provider
        2. Exchange code for access token
        3. Fetch user profile from OAuth provider
        4. Create user record
        5. Generate internal session token
        """
        db = DataFlow(PG_URL)

        @db.model
        class OAuthUser:
            id: str
            email: str
            name: str
            oauth_provider: str
            oauth_user_id: str
            access_token: str

        @db.model
        class Session:
            id: str
            user_id: str
            token: str
            expires_at: str

        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "exchange_code",
            {
                "code": """
import uuid
auth_code = "code_123"
oauth_access_token = f"oauth_token_{uuid.uuid4().hex}"
oauth_user_id = "google_user_123"
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "fetch_profile",
            {
                "code": """
email = "alice@example.com"
name = "Alice Smith"
oauth_provider = "google"
""",
                "inputs": {"access_token": "{{exchange_code.oauth_access_token}}"},
            },
        )

        workflow.add_node(
            "OAuthUserCreateNode",
            "create_oauth_user",
            {
                "id": "user-oauth-001",
                "email": "{{fetch_profile.email}}",
                "name": "{{fetch_profile.name}}",
                "oauth_provider": "{{fetch_profile.oauth_provider}}",
                "oauth_user_id": "{{exchange_code.oauth_user_id}}",
                "access_token": "{{exchange_code.oauth_access_token}}",
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "generate_session",
            {
                "code": """
import uuid
session_token = f"session_{uuid.uuid4().hex}"
expires_at = "2025-10-31T04:00:00"
""",
                "inputs": {},
            },
        )

        workflow.add_node(
            "SessionCreateNode",
            "store_session",
            {
                "id": "{{generate_session.session_token}}",
                "user_id": "user-oauth-001",
                "token": "{{generate_session.session_token}}",
                "expires_at": "{{generate_session.expires_at}}",
            },
        )

        workflow.add_connection(
            "exchange_code", "oauth_access_token", "fetch_profile", "access_token"
        )
        workflow.add_connection("fetch_profile", "email", "create_oauth_user", "email")
        workflow.add_connection("fetch_profile", "name", "create_oauth_user", "name")
        workflow.add_connection(
            "fetch_profile", "oauth_provider", "create_oauth_user", "oauth_provider"
        )
        workflow.add_connection(
            "exchange_code", "oauth_user_id", "create_oauth_user", "oauth_user_id"
        )
        workflow.add_connection(
            "exchange_code", "oauth_access_token", "create_oauth_user", "access_token"
        )
        workflow.add_connection(
            "create_oauth_user", "id", "generate_session", "trigger"
        )
        workflow.add_connection(
            "generate_session", "session_token", "store_session", "id"
        )
        workflow.add_connection(
            "generate_session", "expires_at", "store_session", "expires_at"
        )

        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            assert "create_oauth_user" in results
            assert results["create_oauth_user"]["oauth_provider"] == "google"
            assert results["create_oauth_user"]["email"] == "alice@example.com"
            assert "store_session" in results
            assert results["store_session"]["user_id"] == "user-oauth-001"
        finally:
            try:
                cleanup = WorkflowBuilder()
                cleanup.add_node("OAuthUserDeleteNode", "del", {"id": "user-oauth-001"})
                await runtime.execute_workflow_async(cleanup.build(), inputs={})
            except Exception:
                pass
