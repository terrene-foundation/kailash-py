"""
Unit tests for DataFlowDebugAgent Base Class (Week 10 Task 4.2).

Tests cover:
- DebugAgentSignature creation (2 tests)
- DebugAgent initialization (3 tests)
- ErrorAnalysisEngine.analyze_error() (5 tests)
- DebugAgent.diagnose_error() basic flow (5 tests)

Total: 15 unit tests

Test Philosophy:
- Write tests FIRST (TDD)
- Tests define the interface
- Implementation follows tests
- No mocking in Tier 1 (unit tests) for internal components
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock

import pytest

from dataflow.exceptions import EnhancedDataFlowError
from dataflow.exceptions import ErrorSolution as ExceptionErrorSolution


# Helper function to create test errors
def create_test_error(
    error_code="DF-101",
    message="Test error",
    context=None,
    causes=None,
    solutions=None,
):
    """Create EnhancedDataFlowError for testing."""
    return EnhancedDataFlowError(
        error_code=error_code,
        message=message,
        context=context or {},
        causes=causes or [],
        solutions=solutions or [],
        docs_url="https://docs.dataflow.dev",
    )


# Test 1: DebugAgentSignature - Input Fields
def test_debug_agent_signature_input_fields():
    """Test DebugAgentSignature defines required input fields."""
    from dataflow.debug.signatures import DebugAgentSignature

    signature = DebugAgentSignature()

    # Input fields must exist
    assert hasattr(signature, "error_code")
    assert hasattr(signature, "error_context")
    assert hasattr(signature, "workflow_structure")

    # Verify field descriptions exist
    assert signature.error_code.description == "DataFlow error code (DF-XXX)"
    assert "Error context from ErrorEnhancer" in signature.error_context.description
    assert (
        "Workflow structure from Inspector" in signature.workflow_structure.description
    )


# Test 2: DebugAgentSignature - Output Fields
def test_debug_agent_signature_output_fields():
    """Test DebugAgentSignature defines required output fields."""
    from dataflow.debug.signatures import DebugAgentSignature

    signature = DebugAgentSignature()

    # Output fields must exist
    assert hasattr(signature, "diagnosis")
    assert hasattr(signature, "ranked_solutions")
    assert hasattr(signature, "confidence")
    assert hasattr(signature, "next_steps")

    # Verify field descriptions exist
    assert "Root cause" in signature.diagnosis.description
    assert "ranked by relevance" in signature.ranked_solutions.description
    assert signature.confidence.description == "Confidence score (0.0-1.0)"
    assert "Specific actions" in signature.next_steps.description


# Test 3: DebugAgent - Initialization with Required Components
def test_debug_agent_initialization():
    """Test DebugAgent can be initialized with required components."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    # Mock required components
    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    # Create DebugAgent
    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
        model="gpt-4o-mini",
    )

    # Verify components stored correctly
    assert agent.error_enhancer is error_enhancer
    assert agent.inspector is inspector
    assert agent.knowledge_base is knowledge_base
    assert agent.model == "gpt-4o-mini"


# Test 4: DebugAgent - Default Model
def test_debug_agent_default_model():
    """Test DebugAgent uses gpt-4o-mini as default model."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
        # model not provided
    )

    # Default model should be gpt-4o-mini (fast, cost-effective)
    assert agent.model == "gpt-4o-mini"


# Test 5: DebugAgent - Extends KaizenNode
def test_debug_agent_extends_kaizen_node():
    """Test DebugAgent extends Kaizen KaizenNode (BaseAgent)."""
    from kaizen.nodes.base import KaizenNode

    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
    )

    # DebugAgent must extend KaizenNode
    assert isinstance(agent, KaizenNode)


# Test 6: ErrorAnalysisEngine - Extract Error Code
def test_error_analysis_engine_extract_error_code():
    """Test ErrorAnalysisEngine extracts error code from EnhancedDataFlowError."""
    from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine

    error_enhancer = Mock()
    engine = ErrorAnalysisEngine(error_enhancer)

    # Create test error
    error = create_test_error(
        error_code="DF-101",
        message="Missing required parameter",
        context={"node_id": "create_user", "parameter": "id"},
        causes=["Cause 1", "Cause 2"],
        solutions=[
            ExceptionErrorSolution(
                priority=1,
                description="Solution 1",
                code_template="...",
                auto_fixable=False,
            )
        ],
    )

    # Analyze error
    analysis = engine.analyze_error(error)

    # Verify error code extracted
    assert analysis.error_code == "DF-101"


# Test 7: ErrorAnalysisEngine - Extract Category from Error Code
def test_error_analysis_engine_extract_category():
    """Test ErrorAnalysisEngine extracts category from error code."""
    from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine

    error_enhancer = Mock()
    engine = ErrorAnalysisEngine(error_enhancer)

    # Test different error categories
    test_cases = [
        ("DF-101", "parameter"),
        ("DF-201", "connection"),
        ("DF-301", "migration"),
        ("DF-401", "configuration"),
        ("DF-501", "runtime"),
        ("DF-601", "model"),
        ("DF-701", "node"),
        ("DF-801", "workflow"),
        ("DF-901", "validation"),
    ]

    for error_code, expected_category in test_cases:
        error = create_test_error(error_code=error_code, message="Test error")
        analysis = engine.analyze_error(error)
        assert (
            analysis.category == expected_category
        ), f"Error code {error_code} should map to category {expected_category}"


# Test 8: ErrorAnalysisEngine - Extract Context
def test_error_analysis_engine_extract_context():
    """Test ErrorAnalysisEngine extracts error context."""
    from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine

    error_enhancer = Mock()
    engine = ErrorAnalysisEngine(error_enhancer)

    context = {
        "node_id": "create_user",
        "parameter": "id",
        "expected_type": "str",
        "actual_value": None,
    }

    error = create_test_error(
        error_code="DF-101",
        message="Missing required parameter",
        context=context,
        causes=["Parameter not provided"],
    )

    analysis = engine.analyze_error(error)

    # Verify context extracted correctly
    assert analysis.context == context
    assert analysis.context["node_id"] == "create_user"
    assert analysis.context["parameter"] == "id"


# Test 9: ErrorAnalysisEngine - Extract Causes and Solutions
def test_error_analysis_engine_extract_causes_and_solutions():
    """Test ErrorAnalysisEngine extracts causes and solutions."""
    from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine

    error_enhancer = Mock()
    engine = ErrorAnalysisEngine(error_enhancer)

    causes = [
        "Parameter not provided in workflow",
        "Missing connection to parameter",
        "Typo in parameter name",
    ]

    solutions = [
        ExceptionErrorSolution(
            priority=1,
            description="Add missing parameter",
            code_template='workflow.add_node(..., {"id": "value"})',
            auto_fixable=False,
        ),
        ExceptionErrorSolution(
            priority=2,
            description="Add connection",
            code_template="workflow.add_connection(...)",
            auto_fixable=False,
        ),
    ]

    error = create_test_error(
        error_code="DF-101",
        message="Missing required parameter",
        causes=causes,
        solutions=solutions,
    )

    analysis = engine.analyze_error(error)

    # Verify causes and solutions extracted
    assert len(analysis.causes) == 3
    assert analysis.causes[0] == "Parameter not provided in workflow"

    assert len(analysis.solutions) == 2
    assert analysis.solutions[0].description == "Add missing parameter"
    assert analysis.solutions[0].priority == 1


# Test 10: ErrorAnalysisEngine - Extract Severity
def test_error_analysis_engine_extract_severity():
    """Test ErrorAnalysisEngine extracts severity (all errors default to 'error')."""
    from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine

    error_enhancer = Mock()
    engine = ErrorAnalysisEngine(error_enhancer)

    # Test error severity (all DataFlow errors default to "error")
    error = create_test_error(error_code="DF-101", message="Missing parameter")
    analysis = engine.analyze_error(error)
    assert analysis.severity == "error"

    # Validation errors also default to "error" severity
    validation_error = create_test_error(
        error_code="DF-901", message="Validation error"
    )
    validation_analysis = engine.analyze_error(validation_error)
    assert validation_analysis.severity == "error"


# Test 11: DebugAgent - diagnose_error() Creates ErrorAnalysis
def test_debug_agent_diagnose_error_creates_error_analysis():
    """Test DebugAgent.diagnose_error() creates ErrorAnalysis."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
    )

    # Create test error
    error = create_test_error(
        error_code="DF-101",
        message="Missing parameter",
        context={"node_id": "create_user", "parameter": "id"},
        causes=["Cause 1"],
        solutions=[
            ExceptionErrorSolution(
                priority=1,
                description="Solution 1",
                code_template="...",
                auto_fixable=False,
            )
        ],
    )

    # Mock workflow
    workflow = Mock()

    # Diagnose error
    diagnosis = agent.diagnose_error(error, workflow)

    # Verify diagnosis returned
    assert diagnosis is not None
    assert hasattr(diagnosis, "diagnosis")
    assert hasattr(diagnosis, "ranked_solutions")
    assert hasattr(diagnosis, "confidence")
    assert hasattr(diagnosis, "next_steps")


# Test 12: DebugAgent - diagnose_error() Returns Diagnosis Object
def test_debug_agent_diagnose_error_returns_diagnosis():
    """Test DebugAgent.diagnose_error() returns Diagnosis with correct structure."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import Diagnosis, KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
    )

    error = create_test_error(
        error_code="DF-101",
        message="Missing parameter 'id'",
        context={"node_id": "create_user", "parameter": "id"},
        causes=["Parameter not provided"],
        solutions=[
            ExceptionErrorSolution(
                priority=1,
                description="Add id parameter",
                code_template="...",
                auto_fixable=False,
            )
        ],
    )

    workflow = Mock()

    diagnosis = agent.diagnose_error(error, workflow)

    # Verify Diagnosis structure
    assert isinstance(diagnosis, Diagnosis)
    assert isinstance(diagnosis.diagnosis, str)
    assert isinstance(diagnosis.ranked_solutions, list)
    assert isinstance(diagnosis.confidence, float)
    assert isinstance(diagnosis.next_steps, list)


# Test 13: DebugAgent - diagnose_error() Ranks Solutions
def test_debug_agent_diagnose_error_ranks_solutions():
    """Test DebugAgent.diagnose_error() ranks solutions (top 3)."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
    )

    # Error with 5 solutions (should rank top 3)
    solutions = [
        ExceptionErrorSolution(
            priority=i,
            description=f"Solution {i}",
            code_template="...",
            auto_fixable=False,
        )
        for i in range(1, 6)
    ]

    error = create_test_error(
        error_code="DF-101",
        message="Missing parameter",
        causes=["Cause"],
        solutions=solutions,
    )

    workflow = Mock()

    diagnosis = agent.diagnose_error(error, workflow)

    # Verify only top 3 solutions returned
    assert len(diagnosis.ranked_solutions) <= 3


# Test 14: DebugAgent - diagnose_error() Confidence Score Range
def test_debug_agent_diagnose_error_confidence_range():
    """Test DebugAgent.diagnose_error() returns confidence in 0.0-1.0 range."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
    )

    error = create_test_error(
        error_code="DF-101",
        message="Missing parameter",
        causes=["Cause"],
        solutions=[
            ExceptionErrorSolution(
                priority=1,
                description="Solution",
                code_template="...",
                auto_fixable=False,
            )
        ],
    )

    workflow = Mock()

    diagnosis = agent.diagnose_error(error, workflow)

    # Verify confidence in valid range
    assert 0.0 <= diagnosis.confidence <= 1.0


# Test 15: DebugAgent - diagnose_error() Generates Next Steps
def test_debug_agent_diagnose_error_generates_next_steps():
    """Test DebugAgent.diagnose_error() generates actionable next steps."""
    from dataflow.debug.agent import DebugAgent
    from dataflow.debug.data_structures import KnowledgeBase

    error_enhancer = Mock()
    inspector = Mock()
    knowledge_base = KnowledgeBase()

    agent = DebugAgent(
        error_enhancer=error_enhancer,
        inspector=inspector,
        knowledge_base=knowledge_base,
    )

    error = create_test_error(
        error_code="DF-101",
        message="Missing parameter 'id'",
        context={"node_id": "create_user", "parameter": "id"},
        causes=["Parameter not provided"],
        solutions=[
            ExceptionErrorSolution(
                priority=1,
                description="Add id parameter",
                code_template='workflow.add_node(..., {"id": "value"})',
                auto_fixable=False,
            )
        ],
    )

    workflow = Mock()

    diagnosis = agent.diagnose_error(error, workflow)

    # Verify next steps generated
    assert len(diagnosis.next_steps) > 0
    assert all(isinstance(step, str) for step in diagnosis.next_steps)
