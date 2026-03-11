"""Unit tests for context analyzer component.

Tests the ContextAnalyzer error analysis engine with mocked Inspector to ensure
accurate context extraction and root cause identification.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.context_analyzer import ContextAnalyzer
from dataflow.debug.error_capture import CapturedError, StackFrame
from dataflow.debug.error_categorizer import ErrorCategory
from dataflow.platform.inspector import Inspector, ModelInfo


@pytest.fixture
def mock_inspector():
    """Create mock Inspector with standard test data."""
    inspector = Mock(spec=Inspector)

    # Mock model info
    mock_model_info = ModelInfo(
        name="User",
        table_name="users",
        schema={
            "id": {"type": "VARCHAR", "nullable": False, "primary_key": True},
            "name": {"type": "VARCHAR", "nullable": False, "primary_key": False},
            "email": {"type": "VARCHAR", "nullable": True, "primary_key": False},
        },
        generated_nodes=["UserCreateNode", "UserReadNode", "UserUpdateNode"],
        parameters={
            "create": {"id": {"required": True, "type": "str"}},
        },
        primary_key="id",
    )

    inspector.model = Mock(return_value=mock_model_info)
    inspector.db = Mock()
    inspector.db._models = {"User": Mock(), "Order": Mock()}

    # Mock workflow
    mock_workflow = Mock()
    mock_workflow.nodes = {"create_user": Mock(), "read_user": Mock()}
    mock_workflow.connections = []
    inspector._get_workflow = Mock(return_value=mock_workflow)

    return inspector


@pytest.fixture
def analyzer(mock_inspector):
    """Create ContextAnalyzer with mock Inspector."""
    return ContextAnalyzer(mock_inspector)


def test_analyze_parameter_error(analyzer, mock_inspector):
    """Test parameter error analysis with Inspector integration."""
    error = CapturedError(
        exception=ValueError("NOT NULL constraint failed: users.id"),
        error_type="ValueError",
        message="NOT NULL constraint failed: users.id",
        stacktrace=[],
        context={"node_id": "UserCreateNode"},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER",
        pattern_id="PARAM_001",
        confidence=0.9,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Verify analysis result
    assert result.root_cause is not None
    assert "UserCreateNode" in result.root_cause
    assert "id" in result.root_cause
    assert "User" in result.affected_models
    assert "UserCreateNode" in result.affected_nodes

    # Verify context data
    assert result.context_data["model_name"] == "User"
    assert result.context_data["missing_parameter"] == "id"
    assert result.context_data["is_primary_key"] is True
    assert result.context_data["field_type"] == "VARCHAR"


def test_analyze_parameter_error_without_node_id(analyzer):
    """Test parameter error analysis when node_id not in context."""
    error = CapturedError(
        exception=ValueError("Missing parameter in node create_user"),
        error_type="ValueError",
        message="Missing parameter 'email' in node 'create_user'",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER",
        pattern_id="PARAM_001",
        confidence=0.8,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Should extract node_id from message
    assert "create_user" in result.root_cause or "email" in result.root_cause


def test_analyze_connection_error(analyzer, mock_inspector):
    """Test connection error analysis with workflow structure."""
    error = CapturedError(
        exception=KeyError("Node 'nonexistent_node' not found"),
        error_type="KeyError",
        message="Connection from nonexistent_node to read_user failed",
        stacktrace=[],
        context={"source_node": "nonexistent_node", "target_node": "read_user"},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="CONNECTION",
        pattern_id="CONN_001",
        confidence=0.85,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Verify analysis result
    assert "nonexistent_node" in result.root_cause
    assert (
        "nonexistent_node" in result.affected_nodes
        or "read_user" in result.affected_nodes
    )
    assert "nonexistent_node → read_user" in result.affected_connections

    # Verify context data
    assert result.context_data["missing_node"] == "nonexistent_node"
    assert "create_user" in result.context_data["available_nodes"]
    assert "read_user" in result.context_data["available_nodes"]


def test_analyze_connection_error_with_similar_nodes(analyzer, mock_inspector):
    """Test connection error analysis finds similar node names."""
    # Add similar node name
    mock_inspector._get_workflow().nodes = {"user_create": Mock(), "user_read": Mock()}

    error = CapturedError(
        exception=KeyError("Node 'usr_create' not found"),
        error_type="KeyError",
        message="Connection from usr_create to user_read failed",
        stacktrace=[],
        context={"source_node": "usr_create", "target_node": "user_read"},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="CONNECTION",
        pattern_id="CONN_001",
        confidence=0.9,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Should suggest similar node name
    assert result.context_data["similar_nodes"]
    assert any("user_create" in suggestion for suggestion in result.suggestions)


def test_analyze_migration_error(analyzer):
    """Test migration error analysis with schema context."""
    error = CapturedError(
        exception=Exception("Table 'userss' does not exist"),
        error_type="OperationalError",
        message="OperationalError: Table 'userss' does not exist",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="MIGRATION",
        pattern_id="MIGR_001",
        confidence=0.85,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Verify analysis result
    assert "userss" in result.root_cause.lower()
    assert "userss" in result.affected_models

    # Should suggest existing table name (fuzzy match)
    assert "user" in result.context_data["existing_tables"]


def test_analyze_configuration_error(analyzer):
    """Test configuration error analysis."""
    error = CapturedError(
        exception=ValueError("Invalid database URL format"),
        error_type="ValueError",
        message="Invalid database URL: missing protocol",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="CONFIGURATION",
        pattern_id="CONF_001",
        confidence=0.9,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Verify analysis result
    assert (
        "configuration" in result.root_cause.lower()
        or "url" in result.root_cause.lower()
    )
    assert any("database URL" in suggestion for suggestion in result.suggestions)


def test_analyze_runtime_error_timeout(analyzer):
    """Test runtime error analysis for timeout."""
    error = CapturedError(
        exception=TimeoutError("Query timeout after 30 seconds"),
        error_type="TimeoutError",
        message="Query timeout after 30 seconds",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="RUNTIME",
        pattern_id="RUNTIME_001",
        confidence=0.95,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Verify analysis result
    assert "timeout" in result.root_cause.lower()
    assert result.context_data["runtime_issue"] == "timeout"
    assert any("timeout" in suggestion.lower() for suggestion in result.suggestions)


def test_analyze_runtime_error_deadlock(analyzer):
    """Test runtime error analysis for deadlock."""
    error = CapturedError(
        exception=Exception("Deadlock detected in transaction"),
        error_type="OperationalError",
        message="Deadlock detected: waiting for lock",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="RUNTIME",
        pattern_id="RUNTIME_002",
        confidence=0.9,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Verify analysis result
    assert "deadlock" in result.root_cause.lower()
    assert result.context_data["runtime_issue"] == "deadlock"


def test_extract_node_id_from_message(analyzer):
    """Test node ID extraction from error message."""
    # Pattern: Node 'node_id'
    node_id = analyzer._extract_node_id_from_message("Error in Node 'create_user'")
    assert node_id == "create_user"

    # Pattern: in node node_id
    node_id = analyzer._extract_node_id_from_message("Error in node read_user")
    assert node_id == "read_user"

    # No match
    node_id = analyzer._extract_node_id_from_message("Generic error")
    assert node_id is None


def test_extract_model_name(analyzer):
    """Test model name extraction from node ID."""
    assert analyzer._extract_model_name("UserCreateNode") == "User"
    assert analyzer._extract_model_name("OrderItemUpdateNode") == "OrderItem"
    assert analyzer._extract_model_name("ProductListNode") == "Product"
    assert analyzer._extract_model_name("invalid_node") is None


def test_extract_parameter_name(analyzer):
    """Test parameter name extraction from error message."""
    # Pattern: parameter 'name'
    param = analyzer._extract_parameter_name("Missing required parameter 'id'")
    assert param == "id"

    # Pattern: NOT NULL constraint
    param = analyzer._extract_parameter_name("NOT NULL constraint failed: users.email")
    assert param == "email"

    # Pattern: field 'name'
    param = analyzer._extract_parameter_name("Invalid field 'name' value")
    assert param == "name"

    # No match
    param = analyzer._extract_parameter_name("Generic error")
    assert param is None


def test_extract_connection_from_message(analyzer):
    """Test connection extraction from error message."""
    # Pattern: from source to target
    source, target = analyzer._extract_connection_from_message(
        "Connection from user_create to user_read failed"
    )
    assert source == "user_create"
    assert target == "user_read"

    # Pattern: source -> target
    source, target = analyzer._extract_connection_from_message(
        "user_create -> user_read"
    )
    assert source == "user_create"
    assert target == "user_read"

    # No match
    source, target = analyzer._extract_connection_from_message("Generic error")
    assert source is None
    assert target is None


def test_find_similar_strings(analyzer):
    """Test fuzzy string matching for typo suggestions."""
    candidates = ["user_create", "user_update", "order_create"]

    # High similarity
    similar = analyzer._find_similar_strings("usr_create", candidates)
    assert len(similar) > 0
    assert similar[0][0] == "user_create"
    assert similar[0][1] > 0.7

    # No similar strings (threshold 0.5)
    similar = analyzer._find_similar_strings("completely_different", candidates)
    assert len(similar) == 0


def test_analyze_unknown_category(analyzer):
    """Test analysis of unknown error category."""
    error = CapturedError(
        exception=Exception("Unknown error"),
        error_type="Exception",
        message="Unknown error xyz123",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="UNKNOWN",
        pattern_id="UNKNOWN",
        confidence=0.0,
        features={},
    )

    result = analyzer.analyze(error, category)

    # Should return unknown result
    assert result.root_cause == "Unknown error - unable to determine root cause"
    assert len(result.affected_nodes) == 0


def test_analysis_result_unknown_factory():
    """Test AnalysisResult.unknown() factory method."""
    result = AnalysisResult.unknown()

    assert result.root_cause == "Unknown error - unable to determine root cause"
    assert result.affected_nodes == []
    assert result.affected_connections == []
    assert result.affected_models == []
    assert result.context_data == {}
    assert len(result.suggestions) > 0


def test_analysis_result_to_dict():
    """Test AnalysisResult serialization."""
    result = AnalysisResult(
        root_cause="Test error",
        affected_nodes=["node1"],
        affected_connections=["node1 → node2"],
        affected_models=["User"],
        context_data={"key": "value"},
        suggestions=["Fix the issue"],
    )

    data = result.to_dict()

    assert data["root_cause"] == "Test error"
    assert data["affected_nodes"] == ["node1"]
    assert data["affected_connections"] == ["node1 → node2"]
    assert data["affected_models"] == ["User"]
    assert data["context_data"] == {"key": "value"}
    assert data["suggestions"] == ["Fix the issue"]


def test_analysis_result_repr():
    """Test AnalysisResult debug representation."""
    result = AnalysisResult(
        root_cause="Test error",
        affected_nodes=["node1", "node2"],
        affected_connections=["conn1"],
        affected_models=["User"],
    )

    repr_str = repr(result)

    assert "Test error" in repr_str
    assert "nodes=2" in repr_str
    assert "connections=1" in repr_str
    assert "models=1" in repr_str
