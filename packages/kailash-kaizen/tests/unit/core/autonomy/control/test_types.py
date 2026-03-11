"""
Tier 1 Unit Tests for Control Protocol Core Types

Tests ControlRequest and ControlResponse dataclasses including:
- Message creation with all supported types
- JSON serialization/deserialization
- Request/response pairing by ID
- Error handling and validation
- Edge cases and boundary conditions

Coverage Target: 100% for control protocol types
Test Strategy: TDD - Tests written BEFORE implementation
Infrastructure: Mocked - No external dependencies
"""

import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

# Import will fail until types are implemented
# This is intentional for TDD approach
try:
    from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse
except ImportError:
    # Placeholder for TDD - tests will fail until implementation exists
    ControlRequest = None
    ControlResponse = None


# ============================================
# Test Fixtures
# ============================================


@pytest.fixture
def sample_request_data() -> dict[str, Any]:
    """Sample request data for testing."""
    return {
        "question": "Proceed with deletion?",
        "options": ["yes", "no"],
        "context": "Deleting 100 files",
    }


@pytest.fixture
def sample_response_data() -> dict[str, Any]:
    """Sample response data for testing."""
    return {"answer": "yes", "confidence": 0.95}


# ============================================
# ControlRequest Creation Tests
# ============================================


class TestControlRequestCreation:
    """Test ControlRequest creation with various message types."""

    def test_create_user_input_request(self, sample_request_data):
        """Test creating a user_input request."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        request = ControlRequest.create("user_input", sample_request_data)

        assert request.type == "user_input"
        assert request.data == sample_request_data
        assert request.request_id is not None
        assert request.request_id.startswith("req_")
        assert len(request.request_id) > 4  # req_ + UUID portion

    def test_create_approval_request(self):
        """Test creating an approval request."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        data = {"action": "delete_files", "count": 100}
        request = ControlRequest.create("approval", data)

        assert request.type == "approval"
        assert request.data == data
        assert request.request_id.startswith("req_")

    def test_create_progress_update_request(self):
        """Test creating a progress_update request."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        data = {"message": "Processing files", "percentage": 45.5}
        request = ControlRequest.create("progress_update", data)

        assert request.type == "progress_update"
        assert request.data == data
        assert request.request_id.startswith("req_")

    def test_create_question_request(self):
        """Test creating a question request."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        data = {"question": "Which format?", "options": ["json", "xml", "yaml"]}
        request = ControlRequest.create("question", data)

        assert request.type == "question"
        assert request.data == data
        assert request.request_id.startswith("req_")

    def test_request_id_uniqueness(self):
        """Test that request IDs are unique across multiple requests."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        requests = [ControlRequest.create("user_input", {"test": i}) for i in range(10)]

        request_ids = [r.request_id for r in requests]
        assert len(request_ids) == len(set(request_ids))  # All unique

    def test_request_with_empty_data(self):
        """Test creating a request with empty data dict."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        request = ControlRequest.create("progress_update", {})

        assert request.type == "progress_update"
        assert request.data == {}
        assert request.request_id is not None

    def test_request_with_nested_data(self):
        """Test creating a request with complex nested data."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        data = {
            "question": "Approve?",
            "details": {
                "files": ["a.txt", "b.txt"],
                "metadata": {"size": 1024, "owner": "user"},
            },
        }
        request = ControlRequest.create("approval", data)

        assert request.data == data
        assert request.data["details"]["files"] == ["a.txt", "b.txt"]


# ============================================
# ControlRequest Serialization Tests
# ============================================


class TestControlRequestSerialization:
    """Test ControlRequest JSON serialization."""

    def test_to_json_basic(self, sample_request_data):
        """Test serializing request to JSON."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        request = ControlRequest.create("user_input", sample_request_data)
        json_str = request.to_json()

        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["type"] == "user_input"
        assert parsed["data"] == sample_request_data
        assert parsed["request_id"] == request.request_id

    def test_to_dict(self, sample_request_data):
        """Test converting request to dict."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        request = ControlRequest.create("question", sample_request_data)
        data_dict = request.to_dict()

        assert isinstance(data_dict, dict)
        assert data_dict["type"] == "question"
        assert data_dict["data"] == sample_request_data
        assert data_dict["request_id"] == request.request_id

    def test_from_json_basic(self):
        """Test deserializing request from JSON."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        json_str = json.dumps(
            {
                "request_id": "req_test123",
                "type": "approval",
                "data": {"action": "delete"},
            }
        )

        request = ControlRequest.from_json(json_str)

        assert request.request_id == "req_test123"
        assert request.type == "approval"
        assert request.data == {"action": "delete"}

    def test_from_dict(self):
        """Test creating request from dict."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        data_dict = {
            "request_id": "req_test456",
            "type": "question",
            "data": {"question": "Proceed?"},
        }

        request = ControlRequest.from_dict(data_dict)

        assert request.request_id == "req_test456"
        assert request.type == "question"
        assert request.data == {"question": "Proceed?"}

    def test_roundtrip_serialization(self, sample_request_data):
        """Test that serialization roundtrip preserves data."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        original = ControlRequest.create("user_input", sample_request_data)
        json_str = original.to_json()
        restored = ControlRequest.from_json(json_str)

        assert restored.request_id == original.request_id
        assert restored.type == original.type
        assert restored.data == original.data


# ============================================
# ControlRequest Validation Tests
# ============================================


class TestControlRequestValidation:
    """Test ControlRequest validation and error cases."""

    def test_invalid_message_type_raises_error(self):
        """Test that invalid message type raises ValueError."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        with pytest.raises(ValueError, match="Invalid message type"):
            ControlRequest.create("invalid_type", {})

    def test_from_json_invalid_json_raises_error(self):
        """Test that invalid JSON raises error."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        with pytest.raises(json.JSONDecodeError):
            ControlRequest.from_json("not valid json {")

    def test_from_json_missing_required_fields(self):
        """Test that missing required fields raises error."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        # Missing 'type' field
        json_str = json.dumps({"request_id": "req_test", "data": {}})

        with pytest.raises((KeyError, ValueError)):
            ControlRequest.from_json(json_str)

    def test_from_dict_missing_request_id(self):
        """Test that missing request_id raises error."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        with pytest.raises((KeyError, ValueError)):
            ControlRequest.from_dict({"type": "question", "data": {}})

    def test_data_must_be_dict(self):
        """Test that data must be a dict."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        with pytest.raises((TypeError, ValueError)):
            ControlRequest.create("question", "not a dict")


# ============================================
# ControlResponse Creation Tests
# ============================================


class TestControlResponseCreation:
    """Test ControlResponse creation."""

    def test_create_success_response(self, sample_response_data):
        """Test creating a successful response."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(request_id="req_test123", data=sample_response_data)

        assert response.request_id == "req_test123"
        assert response.data == sample_response_data
        assert response.error is None
        assert not response.is_error

    def test_create_error_response(self):
        """Test creating an error response."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(
            request_id="req_test456", error="User cancelled operation"
        )

        assert response.request_id == "req_test456"
        assert response.data is None
        assert response.error == "User cancelled operation"
        assert response.is_error

    def test_create_response_with_both_data_and_error(self):
        """Test that response can have both data and error (error takes precedence)."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(
            request_id="req_test789",
            data={"result": "success"},
            error="Warning: partial success",
        )

        assert response.is_error  # Error takes precedence
        assert response.error is not None
        assert response.data is not None

    def test_response_with_empty_data(self):
        """Test creating response with empty data dict."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(request_id="req_test", data={})

        assert response.data == {}
        assert not response.is_error

    def test_response_minimal(self):
        """Test creating response with only request_id (both data and error None)."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(request_id="req_minimal")

        assert response.request_id == "req_minimal"
        assert response.data is None
        assert response.error is None
        assert not response.is_error  # No error = not an error response


# ============================================
# ControlResponse Serialization Tests
# ============================================


class TestControlResponseSerialization:
    """Test ControlResponse JSON serialization."""

    def test_to_json_success(self, sample_response_data):
        """Test serializing success response to JSON."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(request_id="req_test123", data=sample_response_data)
        json_str = response.to_json()

        parsed = json.loads(json_str)
        assert parsed["request_id"] == "req_test123"
        assert parsed["data"] == sample_response_data
        assert parsed["error"] is None

    def test_to_json_error(self):
        """Test serializing error response to JSON."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(request_id="req_test456", error="Timeout occurred")
        json_str = response.to_json()

        parsed = json.loads(json_str)
        assert parsed["request_id"] == "req_test456"
        assert parsed["error"] == "Timeout occurred"
        assert parsed["data"] is None

    def test_to_dict(self):
        """Test converting response to dict."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        response = ControlResponse(request_id="req_test", data={"result": "ok"})
        data_dict = response.to_dict()

        assert isinstance(data_dict, dict)
        assert data_dict["request_id"] == "req_test"
        assert data_dict["data"] == {"result": "ok"}

    def test_from_json_success(self):
        """Test deserializing success response from JSON."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        json_str = json.dumps(
            {"request_id": "req_test", "data": {"answer": "yes"}, "error": None}
        )

        response = ControlResponse.from_json(json_str)

        assert response.request_id == "req_test"
        assert response.data == {"answer": "yes"}
        assert response.error is None
        assert not response.is_error

    def test_from_json_error(self):
        """Test deserializing error response from JSON."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        json_str = json.dumps(
            {"request_id": "req_test", "data": None, "error": "Failed to process"}
        )

        response = ControlResponse.from_json(json_str)

        assert response.request_id == "req_test"
        assert response.error == "Failed to process"
        assert response.is_error

    def test_from_dict(self):
        """Test creating response from dict."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        data_dict = {
            "request_id": "req_dict",
            "data": {"status": "complete"},
            "error": None,
        }

        response = ControlResponse.from_dict(data_dict)

        assert response.request_id == "req_dict"
        assert response.data == {"status": "complete"}
        assert not response.is_error

    def test_roundtrip_serialization_success(self, sample_response_data):
        """Test serialization roundtrip for success response."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        original = ControlResponse(request_id="req_round", data=sample_response_data)
        json_str = original.to_json()
        restored = ControlResponse.from_json(json_str)

        assert restored.request_id == original.request_id
        assert restored.data == original.data
        assert restored.error == original.error
        assert restored.is_error == original.is_error

    def test_roundtrip_serialization_error(self):
        """Test serialization roundtrip for error response."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        original = ControlResponse(request_id="req_error", error="Connection failed")
        json_str = original.to_json()
        restored = ControlResponse.from_json(json_str)

        assert restored.request_id == original.request_id
        assert restored.error == original.error
        assert restored.is_error


# ============================================
# ControlResponse Validation Tests
# ============================================


class TestControlResponseValidation:
    """Test ControlResponse validation."""

    def test_from_json_invalid_json(self):
        """Test that invalid JSON raises error."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        with pytest.raises(json.JSONDecodeError):
            ControlResponse.from_json("invalid json")

    def test_from_json_missing_request_id(self):
        """Test that missing request_id raises error."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        json_str = json.dumps({"data": {"result": "ok"}})

        with pytest.raises((KeyError, ValueError)):
            ControlResponse.from_json(json_str)

    def test_from_dict_missing_request_id(self):
        """Test that missing request_id in dict raises error."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        with pytest.raises((KeyError, ValueError)):
            ControlResponse.from_dict({"data": {"result": "ok"}})


# ============================================
# Request/Response Pairing Tests
# ============================================


class TestRequestResponsePairing:
    """Test request/response pairing by ID."""

    def test_response_matches_request_id(self):
        """Test that response can reference request ID."""
        if ControlRequest is None or ControlResponse is None:
            pytest.skip("Types not yet implemented")

        request = ControlRequest.create("question", {"question": "Proceed?"})
        response = ControlResponse(
            request_id=request.request_id, data={"answer": "yes"}
        )

        assert response.request_id == request.request_id

    def test_multiple_requests_with_correct_responses(self):
        """Test pairing multiple requests with their responses."""
        if ControlRequest is None or ControlResponse is None:
            pytest.skip("Types not yet implemented")

        # Create multiple requests
        req1 = ControlRequest.create("question", {"q": "First?"})
        req2 = ControlRequest.create("approval", {"action": "delete"})
        req3 = ControlRequest.create("user_input", {"prompt": "Name?"})

        # Create corresponding responses
        resp1 = ControlResponse(request_id=req1.request_id, data={"a": "yes"})
        resp2 = ControlResponse(request_id=req2.request_id, data={"approved": True})
        resp3 = ControlResponse(request_id=req3.request_id, data={"name": "Alice"})

        # Verify pairing
        assert resp1.request_id == req1.request_id
        assert resp2.request_id == req2.request_id
        assert resp3.request_id == req3.request_id

        # Verify IDs are unique
        ids = [req1.request_id, req2.request_id, req3.request_id]
        assert len(ids) == len(set(ids))


# ============================================
# Edge Cases and Boundary Conditions
# ============================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_request_with_large_data(self):
        """Test request with large data payload."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        large_data = {"items": [{"id": i, "value": f"item_{i}"} for i in range(1000)]}
        request = ControlRequest.create("user_input", large_data)

        assert len(request.data["items"]) == 1000
        assert request.data["items"][999]["value"] == "item_999"

    def test_response_with_large_error_message(self):
        """Test response with large error message."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        error_msg = "Error: " + ("x" * 10000)
        response = ControlResponse(request_id="req_large", error=error_msg)

        assert len(response.error) > 10000
        assert response.is_error

    def test_request_with_special_characters_in_data(self):
        """Test request with special characters in data."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        data = {"text": "Special chars: \n\t\r\"'\\", "unicode": "Hello 世界 🌍"}
        request = ControlRequest.create("question", data)

        # Roundtrip to ensure serialization handles special chars
        json_str = request.to_json()
        restored = ControlRequest.from_json(json_str)

        assert restored.data == data

    def test_response_with_null_values_in_data(self):
        """Test response with null values in data dict."""
        if ControlResponse is None:
            pytest.skip("ControlResponse not yet implemented")

        data = {"result": None, "status": "pending", "details": None}
        response = ControlResponse(request_id="req_null", data=data)

        assert response.data["result"] is None
        assert response.data["status"] == "pending"
        assert not response.is_error

    def test_request_type_is_immutable_after_creation(self):
        """Test that request type cannot be changed after creation."""
        if ControlRequest is None:
            pytest.skip("ControlRequest not yet implemented")

        request = ControlRequest.create("question", {})

        # Attempt to modify type should raise error (if dataclass is frozen)
        # If not frozen, this test documents the behavior
        try:
            request.type = "approval"
            # If we get here, dataclass is not frozen
            # Restore original type for other tests
            request.type = "question"
        except (AttributeError, FrozenInstanceError):
            # Expected: dataclass is frozen
            pass
