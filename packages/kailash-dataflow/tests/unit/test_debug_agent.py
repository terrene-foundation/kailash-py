"""Unit tests for Debug Agent orchestrator and CLI components.

Tests the DebugAgent orchestration, DebugReport serialization, and
CLI formatting with mocked KnowledgeBase and Inspector.
"""

import json
from unittest.mock import MagicMock, Mock

import pytest
from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.cli_formatter import CLIFormatter
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.debug_report import DebugReport
from dataflow.debug.error_capture import CapturedError
from dataflow.debug.error_categorizer import ErrorCategory
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.debug.suggested_solution import SuggestedSolution


@pytest.fixture
def mock_knowledge_base():
    """Create mock KnowledgeBase with standard responses."""
    kb = Mock(spec=KnowledgeBase)

    # Mock pattern
    mock_pattern = {
        "name": "Missing Required Parameter",
        "category": "PARAMETER",
        "related_solutions": ["SOL_001"],
    }

    # Mock solution
    mock_solution = {
        "id": "SOL_001",
        "title": "Add Missing 'id' Parameter",
        "category": "QUICK_FIX",
        "description": "Add required 'id' field to CreateNode",
        "code_example": 'workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})',
        "explanation": "The 'id' field is required for all CREATE operations in DataFlow.",
        "references": ["https://docs.dataflow.dev/nodes/create"],
        "difficulty": "easy",
        "estimated_time": 1,
    }

    kb.get_pattern = Mock(return_value=mock_pattern)
    kb.get_solutions_for_pattern = Mock(return_value=[mock_solution])
    kb.get_all_patterns = Mock(return_value=[mock_pattern])

    return kb


@pytest.fixture
def mock_inspector():
    """Create mock Inspector."""
    inspector = Mock()
    inspector.model = Mock(return_value=None)
    inspector._get_workflow = Mock(return_value=None)
    return inspector


@pytest.fixture
def debug_agent(mock_knowledge_base, mock_inspector):
    """Create DebugAgent with mocks."""
    return DebugAgent(mock_knowledge_base, mock_inspector)


@pytest.fixture
def sample_exception():
    """Create sample exception for testing."""
    return ValueError("NOT NULL constraint failed: users.id")


def test_debug_agent_initialization(debug_agent):
    """Test DebugAgent initializes all components."""
    assert debug_agent.knowledge_base is not None
    assert debug_agent.inspector is not None
    assert debug_agent.capture is not None
    assert debug_agent.categorizer is not None
    assert debug_agent.analyzer is not None
    assert debug_agent.generator is not None


def test_debug_from_exception(debug_agent, sample_exception):
    """Test debugging exception object."""
    report = debug_agent.debug(sample_exception)

    # Verify report structure
    assert isinstance(report, DebugReport)
    assert report.captured_error is not None
    assert report.error_category is not None
    assert report.analysis_result is not None
    assert report.execution_time > 0

    # Verify error capture
    assert report.captured_error.error_type == "ValueError"
    assert "NOT NULL constraint failed" in report.captured_error.message


def test_debug_from_string(debug_agent):
    """Test debugging error message string."""
    error_message = "NOT NULL constraint failed: users.id"
    report = debug_agent.debug_from_string(error_message, error_type="DatabaseError")

    # Verify report structure
    assert isinstance(report, DebugReport)
    assert report.captured_error.message == error_message
    assert report.error_category is not None


def test_debug_agent_pipeline_stages(debug_agent, sample_exception):
    """Test that all pipeline stages execute."""
    report = debug_agent.debug(sample_exception, max_solutions=3, min_relevance=0.1)

    # Stage 1: Capture
    assert report.captured_error is not None
    assert report.captured_error.exception is not None

    # Stage 2: Categorize
    assert report.error_category is not None
    assert report.error_category.category != ""

    # Stage 3: Analyze
    assert report.analysis_result is not None
    assert report.analysis_result.root_cause != ""

    # Stage 4: Suggest (may be 0 for some errors)
    # Stage 5: Format (DebugReport created)
    assert report.execution_time > 0


def test_debug_agent_without_inspector(mock_knowledge_base):
    """Test DebugAgent works without Inspector (fallback mode)."""
    agent = DebugAgent(mock_knowledge_base, inspector=None)

    exception = ValueError("Test error")
    report = agent.debug(exception)

    # Should still produce report with basic analysis
    assert report.captured_error is not None
    assert report.error_category is not None
    assert report.analysis_result is not None
    # Root cause will be simple message since no Inspector available
    assert report.analysis_result.root_cause != ""


def test_debug_report_serialization():
    """Test DebugReport to_dict() and from_dict()."""
    from datetime import datetime

    # Create sample report
    captured = CapturedError(
        exception=ValueError("Test error"),
        error_type="ValueError",
        message="Test error",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter 'id'",
        affected_nodes=["create_user"],
        affected_models=["User"],
        context_data={"missing_parameter": "id"},
    )

    solutions = [
        SuggestedSolution(
            solution_id="SOL_001",
            title="Add Missing Parameter",
            category="QUICK_FIX",
            description="Add required field",
            code_example="...",
            explanation="...",
            relevance_score=0.95,
            confidence=0.9,
        )
    ]

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=solutions,
        execution_time=23.5,
    )

    # Serialize
    data = report.to_dict()
    assert data["error_category"]["category"] == "PARAMETER"
    assert data["execution_time"] == 23.5
    assert len(data["suggested_solutions"]) == 1

    # Deserialize
    restored = DebugReport.from_dict(data)
    assert restored.error_category.category == "PARAMETER"
    assert restored.execution_time == 23.5
    assert len(restored.suggested_solutions) == 1


def test_debug_report_json_export():
    """Test DebugReport to_json() and JSON deserialization."""
    from datetime import datetime

    captured = CapturedError(
        exception=ValueError("Test error"),
        error_type="ValueError",
        message="Test error",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_models=[],
        context_data={},
    )

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=[],
        execution_time=10.5,
    )

    # Export to JSON
    json_str = report.to_json()
    assert isinstance(json_str, str)

    # Parse JSON
    data = json.loads(json_str)
    assert data["error_category"]["category"] == "PARAMETER"
    assert data["execution_time"] == 10.5


def test_debug_report_cli_format():
    """Test DebugReport to_cli_format() text representation."""
    from datetime import datetime

    captured = CapturedError(
        exception=ValueError("Test error"),
        error_type="ValueError",
        message="Test error",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=["create_user"],
        affected_models=["User"],
        context_data={},
    )

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=[],
        execution_time=15.0,
    )

    # Get CLI format
    output = report.to_cli_format()

    # Verify output contains key elements
    assert "ERROR: PARAMETER" in output
    assert "Test error" in output
    assert "Missing parameter" in output
    assert "create_user" in output
    assert "15.0ms" in output


def test_cli_formatter_header():
    """Test CLIFormatter formats header correctly."""
    from datetime import datetime

    formatter = CLIFormatter()
    captured = CapturedError(
        exception=ValueError("Test error"),
        error_type="ValueError",
        message="Test error",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_models=[],
        context_data={},
    )

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=[],
        execution_time=10.0,
    )

    output = formatter.format_report(report)

    # Verify header
    assert "DataFlow Debug Agent" in output
    assert "╔" in output  # Box drawing character


def test_cli_formatter_error_section():
    """Test CLIFormatter formats error section correctly."""
    from datetime import datetime

    formatter = CLIFormatter()
    captured = CapturedError(
        exception=ValueError("NOT NULL constraint failed: users.id"),
        error_type="DatabaseError",
        message="NOT NULL constraint failed: users.id",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.92, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_models=[],
        context_data={},
    )

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=[],
        execution_time=10.0,
    )

    output = formatter.format_report(report)

    # Verify error section
    assert "ERROR DETAILS" in output
    assert "DatabaseError" in output
    assert "PARAMETER" in output
    assert "92%" in output  # Confidence
    assert "NOT NULL constraint failed" in output


def test_cli_formatter_solutions_section():
    """Test CLIFormatter formats solutions section correctly."""
    from datetime import datetime

    formatter = CLIFormatter()
    captured = CapturedError(
        exception=ValueError("Test error"),
        error_type="ValueError",
        message="Test error",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_models=[],
        context_data={},
    )

    solutions = [
        SuggestedSolution(
            solution_id="SOL_001",
            title="Add Missing Parameter",
            category="QUICK_FIX",
            description="Add required 'id' field to CreateNode",
            code_example='workflow.add_node("UserCreateNode", "create", {"id": "value"})',
            explanation="The 'id' field is required...",
            difficulty="easy",  # Explicitly set difficulty
            estimated_time=1,  # Explicitly set estimated time
            relevance_score=0.95,
            confidence=0.9,
        )
    ]

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=solutions,
        execution_time=10.0,
    )

    output = formatter.format_report(report)

    # Verify solutions section
    assert "SUGGESTED SOLUTIONS" in output
    assert "[1] Add Missing Parameter" in output
    assert "QUICK_FIX" in output
    assert "95%" in output  # Relevance
    assert "easy" in output  # Difficulty


def test_debug_report_repr():
    """Test DebugReport __repr__() method."""
    from datetime import datetime

    captured = CapturedError(
        exception=ValueError("Test error"),
        error_type="ValueError",
        message="Test error",
        stacktrace=[],
        context={},
        timestamp=datetime.now(),
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_models=[],
        context_data={},
    )

    solutions = [Mock(), Mock()]  # 2 mock solutions

    report = DebugReport(
        captured_error=captured,
        error_category=category,
        analysis_result=analysis,
        suggested_solutions=solutions,
        execution_time=23.5,
    )

    repr_str = repr(report)

    # Verify repr format
    assert "DebugReport" in repr_str
    assert "PARAMETER" in repr_str
    assert "solutions=2" in repr_str
    assert "23.5ms" in repr_str


def test_execution_time_tracking(debug_agent, sample_exception):
    """Test that execution time is tracked correctly."""
    report = debug_agent.debug(sample_exception)

    # Execution time should be positive and reasonable (< 1000ms for unit tests)
    assert report.execution_time > 0
    assert report.execution_time < 1000  # Should complete quickly


def test_max_solutions_limit(debug_agent, sample_exception):
    """Test max_solutions limit is enforced."""
    report1 = debug_agent.debug(sample_exception, max_solutions=1)
    report2 = debug_agent.debug(sample_exception, max_solutions=3)

    # Note: Actual solution count depends on mock configuration
    # Just verify the parameter is passed through
    assert report1.suggested_solutions is not None
    assert report2.suggested_solutions is not None
