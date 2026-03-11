"""
Integration tests for string ID type coercion fix with real DataFlow models and database.

This test module validates that the fix for the critical string ID bug works
end-to-end with real DataFlow models, generated nodes, and database operations.

Bug Fix: Type-aware ID conversion based on model field annotations
"""

import os
import tempfile
import time

import pytest

# DataFlow and Kailash imports
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestStringIdTypeCoercionIntegration:
    """Integration tests for string ID type coercion fix with real DataFlow models."""

    def setup_method(self):
        """Setup test database and DataFlow instance for each test."""
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.database_url = f"sqlite:///{self.temp_db.name}"

        # Initialize DataFlow with test database and auto_migrate enabled
        self.db = DataFlow(database_url=self.database_url, auto_migrate=True)
        self.runtime = LocalRuntime()

    def teardown_method(self):
        """Cleanup temporary database file."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_string_id_model_crud_operations(self):
        """Test all CRUD operations work correctly with string ID models."""

        # Define a model with string ID
        @self.db.model
        class SessionModel:
            id: str
            user_id: str
            state: str = "active"

        # Test data
        session_id = "session-uuid-12345-abcdef"
        user_id = "user-uuid-67890-ghijkl"

        # Test CREATE operation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionModelCreateNode",
            "create_session",
            {"id": session_id, "user_id": user_id, "state": "active"},
        )

        # Execute create workflow
        results, run_id = self.runtime.execute(workflow.build())

        assert results["create_session"] is not None
        assert results["create_session"]["id"] == session_id
        assert results["create_session"]["user_id"] == user_id

        # Test READ operation with string ID
        workflow = WorkflowBuilder()
        workflow.add_node("SessionModelReadNode", "read_session", {"id": session_id})

        results, run_id = self.runtime.execute(workflow.build())

        assert results["read_session"] is not None
        assert results["read_session"]["id"] == session_id
        assert results["read_session"]["user_id"] == user_id
        assert results["read_session"]["state"] == "active"

        # Test UPDATE operation with string ID (THE FIX)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionModelUpdateNode",
            "update_session",
            {"id": session_id, "updates": {"state": "expired"}},
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["update_session"] is not None
        assert results["update_session"]["id"] == session_id

        # Verify update worked by reading again
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionModelReadNode", "read_session_updated", {"id": session_id}
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["read_session_updated"]["state"] == "expired"

        # Test DELETE operation with string ID
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionModelDeleteNode", "delete_session", {"id": session_id}
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["delete_session"] is not None
        assert results["delete_session"]["id"] == session_id

    def test_integer_id_model_backward_compatibility(self):
        """Test that integer ID models still work correctly (backward compatibility)."""

        # Define a model with integer ID (auto-generated, not explicitly defined)
        @self.db.model
        class UserModel:
            # No explicit id field - DataFlow auto-generates integer ID
            name: str
            email: str

        # Test data with string that should convert to int
        user_id_str = "123"  # String that should be converted to int
        user_id_int = 123
        name = "Test User"
        email = f"test_{int(time.time())}@example.com"  # Unique email

        # Test CREATE operation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserModelCreateNode",
            "create_user",
            {
                # Don't pass ID for integer models - it's auto-generated
                "name": name,
                "email": email,
            },
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["create_user"] is not None
        # Get the auto-generated ID for use in subsequent operations
        created_id = results["create_user"]["id"]
        assert isinstance(created_id, int)  # Should be an integer for int ID models

        # Test READ operation with string ID that should convert to int
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserModelReadNode",
            "read_user",
            {"id": str(created_id)},  # Pass the created ID as string
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["read_user"] is not None
        assert results["read_user"]["id"] == created_id  # Should match the created ID
        assert results["read_user"]["name"] == name

        # Test UPDATE operation with string ID that should convert to int
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserModelUpdateNode",
            "update_user",
            {
                "id": str(created_id),  # Pass the created ID as string
                "updates": {"name": "Updated User"},
            },
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["update_user"] is not None
        assert results["update_user"]["id"] == created_id  # Should match the created ID

    def test_uuid_string_id_operations(self):
        """Test operations work correctly with UUID string IDs."""
        import uuid

        # Define a model with string ID for UUIDs
        @self.db.model
        class DocumentModel:
            id: str
            title: str
            content: str

        # Test data with real UUID
        doc_id = str(uuid.uuid4())
        title = "Test Document"
        content = "This is test content"

        # Test CREATE operation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "DocumentModelCreateNode",
            "create_doc",
            {"id": doc_id, "title": title, "content": content},
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["create_doc"] is not None
        assert results["create_doc"]["id"] == doc_id

        # Test UPDATE operation with UUID string ID (should preserve UUID)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "DocumentModelUpdateNode",
            "update_doc",
            {
                "id": doc_id,  # UUID string should be preserved, not converted to int
                "updates": {"title": "Updated Document"},
            },
        )

        results, run_id = self.runtime.execute(workflow.build())

        assert results["update_doc"] is not None
        assert results["update_doc"]["id"] == doc_id  # UUID should be preserved

        # Verify update worked
        workflow = WorkflowBuilder()
        workflow.add_node("DocumentModelReadNode", "read_doc", {"id": doc_id})

        results, run_id = self.runtime.execute(workflow.build())

        assert results["read_doc"]["title"] == "Updated Document"
        assert results["read_doc"]["id"] == doc_id
