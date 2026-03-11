"""
Unit tests for Inspector ErrorEnhancer Integration (Task 2.4).

Tests cover:
- diagnose_error(): Diagnose DataFlow errors with Inspector suggestions
- _suggest_inspector_commands(): Generate command suggestions based on error type
- _suggest_error_actions(): Generate recommended actions
- ErrorDiagnosis dataclass and show() method
"""

import pytest
from dataflow.exceptions import EnhancedDataFlowError, ErrorSolution
from dataflow.platform.inspector import ErrorDiagnosis, Inspector


@pytest.mark.unit
class TestErrorDiagnosis:
    """Tests for ErrorDiagnosis dataclass."""

    def test_error_diagnosis_creation(self):
        """Test creating ErrorDiagnosis instance."""
        diagnosis = ErrorDiagnosis(
            error_code="DF-101",
            error_type="ParameterError",
            affected_component="user_create",
            inspector_commands=["inspector.node('user_create')"],
            context_hints={"node_id": "user_create", "parameter_name": "data"},
            recommended_actions=["Verify all required parameters are provided"],
        )

        assert diagnosis.error_code == "DF-101"
        assert diagnosis.error_type == "ParameterError"
        assert diagnosis.affected_component == "user_create"
        assert len(diagnosis.inspector_commands) == 1
        assert len(diagnosis.context_hints) == 2
        assert len(diagnosis.recommended_actions) == 1

    def test_error_diagnosis_show_with_color(self):
        """Test ErrorDiagnosis show() with color."""
        diagnosis = ErrorDiagnosis(
            error_code="DF-101",
            error_type="ParameterError",
            affected_component="user_create",
            inspector_commands=["inspector.node('user_create')"],
            context_hints={"node_id": "user_create"},
            recommended_actions=["Check parameters"],
        )

        output = diagnosis.show(color=True)

        # Check for ANSI color codes
        assert "\033[" in output
        assert "Error Diagnosis: DF-101" in output
        assert "ParameterError" in output
        assert "user_create" in output

    def test_error_diagnosis_show_without_color(self):
        """Test ErrorDiagnosis show() without color."""
        diagnosis = ErrorDiagnosis(
            error_code="DF-102",
            error_type="ConnectionError",
            affected_component=None,
            inspector_commands=["inspector.validate_connections()"],
            context_hints={},
            recommended_actions=["Verify connections"],
        )

        output = diagnosis.show(color=False)

        # No ANSI color codes
        assert "\033[" not in output
        assert "Error Diagnosis: DF-102" in output
        assert "ConnectionError" in output

    def test_error_diagnosis_empty_sections(self):
        """Test ErrorDiagnosis with empty sections."""
        diagnosis = ErrorDiagnosis(
            error_code="UNKNOWN",
            error_type="Exception",
            affected_component=None,
            inspector_commands=[],
            context_hints={},
            recommended_actions=[],
        )

        output = diagnosis.show(color=False)

        # Should still display basic info
        assert "Error Diagnosis: UNKNOWN" in output
        assert "Exception" in output


@pytest.mark.unit
class TestDiagnoseError:
    """Tests for diagnose_error() method."""

    def test_diagnose_enhanced_dataflow_error(self, memory_dataflow):
        """Test diagnosing EnhancedDataFlowError."""
        db = memory_dataflow

        # Create model
        @db.model
        class TestModel:
            id: str
            name: str

        # Create inspector
        inspector = Inspector(db)

        # Create enhanced error
        error = EnhancedDataFlowError(
            error_code="DF-101",
            message="Missing required parameter",
            context={"node_id": "test_create", "parameter_name": "data"},
            causes=["Parameter not provided in node definition"],
            solutions=[
                ErrorSolution(
                    priority=1,
                    description="Add missing parameter",
                    code_template="node.add_parameter('data', value)",
                )
            ],
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Check diagnosis
        assert isinstance(diagnosis, ErrorDiagnosis)
        assert diagnosis.error_code == "DF-101"
        assert diagnosis.error_type == "EnhancedDataFlowError"
        assert diagnosis.affected_component == "test_create"
        assert len(diagnosis.inspector_commands) > 0
        assert len(diagnosis.recommended_actions) > 0

    def test_diagnose_standard_exception(self, memory_dataflow):
        """Test diagnosing standard Python exception."""
        db = memory_dataflow
        inspector = Inspector(db)

        # Create standard error
        error = KeyError("missing_key")

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Check diagnosis
        assert isinstance(diagnosis, ErrorDiagnosis)
        assert diagnosis.error_code == "UNKNOWN"
        assert diagnosis.error_type == "KeyError"
        assert len(diagnosis.inspector_commands) > 0  # Should suggest general commands

    def test_diagnose_parameter_error(self, memory_dataflow):
        """Test diagnosing parameter-related error."""
        db = memory_dataflow
        inspector = Inspector(db)

        # Create parameter error
        error = EnhancedDataFlowError(
            error_code="DF-PARAM-001",
            message="Parameter type mismatch",
            context={"node_id": "user_create", "parameter_name": "age"},
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Should suggest commands and actions (flexible check)
        assert len(diagnosis.inspector_commands) > 0
        assert len(diagnosis.recommended_actions) > 0

    def test_diagnose_connection_error(self, memory_dataflow):
        """Test diagnosing connection-related error."""
        db = memory_dataflow
        inspector = Inspector(db)

        # Create connection error
        error = EnhancedDataFlowError(
            error_code="DF-CONN-001",
            message="Broken connection detected",
            context={"node_id": "user_read"},
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Should suggest commands and actions (flexible check)
        assert len(diagnosis.inspector_commands) > 0
        assert len(diagnosis.recommended_actions) > 0

    def test_diagnose_model_error(self, memory_dataflow):
        """Test diagnosing model-related error."""
        db = memory_dataflow

        @db.model
        class ErrorTestModel:
            id: str
            name: str

        inspector = Inspector(db)

        # Create model error
        error = EnhancedDataFlowError(
            error_code="DF-MODEL-001",
            message="Model schema mismatch",
            context={"model_name": "ErrorTestModel"},
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Should suggest model-related commands
        assert any("model" in cmd.lower() for cmd in diagnosis.inspector_commands)
        assert any(
            "schema" in action.lower() or "model" in action.lower()
            for action in diagnosis.recommended_actions
        )

    def test_diagnose_workflow_error(self, memory_dataflow):
        """Test diagnosing workflow-related error."""
        db = memory_dataflow
        inspector = Inspector(db)

        # Create workflow error
        error = EnhancedDataFlowError(
            error_code="DF-WORKFLOW-001",
            message="Workflow validation failed",
            context={"workflow_id": "main_workflow"},
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Should suggest workflow-related commands
        assert any("workflow" in cmd.lower() for cmd in diagnosis.inspector_commands)

    def test_diagnose_migration_error(self, memory_dataflow):
        """Test diagnosing migration-related error."""
        db = memory_dataflow

        @db.model
        class MigrationTestModel:
            id: str
            name: str

        inspector = Inspector(db)

        # Create migration error
        error = EnhancedDataFlowError(
            error_code="DF-MIGRATION-001",
            message="Migration failed",
            context={"model_name": "MigrationTestModel"},
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # Should suggest migration-related commands
        assert any("migration" in cmd.lower() for cmd in diagnosis.inspector_commands)


@pytest.mark.unit
class TestSuggestInspectorCommands:
    """Tests for _suggest_inspector_commands() method."""

    def test_suggest_commands_for_parameter_error(self, memory_dataflow):
        """Test command suggestions for parameter errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        commands = inspector._suggest_inspector_commands(
            error_code="DF-PARAM-001",
            error_type="ParameterError",
            context={"node_id": "user_create", "parameter_name": "data"},
        )

        # Should include node inspection and parameter tracing
        assert len(commands) > 0
        assert any("node" in cmd for cmd in commands)
        assert any(
            "trace_parameter" in cmd or "validate_connections" in cmd
            for cmd in commands
        )

    def test_suggest_commands_for_connection_error(self, memory_dataflow):
        """Test command suggestions for connection errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        commands = inspector._suggest_inspector_commands(
            error_code="DF-CONNECTION-001",
            error_type="ConnectionError",
            context={"node_id": "user_read"},
        )

        # Should include connection analysis commands
        assert len(commands) > 0
        assert any("connection" in cmd.lower() for cmd in commands)

    def test_suggest_commands_for_model_error(self, memory_dataflow):
        """Test command suggestions for model errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        commands = inspector._suggest_inspector_commands(
            error_code="DF-MODEL-001",
            error_type="ModelError",
            context={"model_name": "User"},
        )

        # Should include model introspection commands
        assert len(commands) > 0
        assert any("model" in cmd.lower() for cmd in commands)

    def test_suggest_commands_with_no_context(self, memory_dataflow):
        """Test command suggestions with minimal context."""
        db = memory_dataflow
        inspector = Inspector(db)

        commands = inspector._suggest_inspector_commands(
            error_code="UNKNOWN", error_type="Exception", context={}
        )

        # Should suggest general debugging commands
        assert len(commands) > 0
        assert any(
            "workflow" in cmd.lower() or "validate" in cmd.lower() for cmd in commands
        )


@pytest.mark.unit
class TestSuggestErrorActions:
    """Tests for _suggest_error_actions() method."""

    def test_suggest_actions_for_parameter_error(self, memory_dataflow):
        """Test action suggestions for parameter errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        actions = inspector._suggest_error_actions(
            error_code="DF-PARAMETER-001",
            error_type="ParameterError",
            context={"parameter_name": "data"},
        )

        # Should include parameter validation actions
        assert len(actions) > 0
        assert any("parameter" in action.lower() for action in actions)

    def test_suggest_actions_for_connection_error(self, memory_dataflow):
        """Test action suggestions for connection errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        actions = inspector._suggest_error_actions(
            error_code="DF-CONNECTION-001",
            error_type="ConnectionError",
            context={},
        )

        # Should include connection verification actions
        assert len(actions) > 0
        assert any("connection" in action.lower() for action in actions)

    def test_suggest_actions_for_model_error(self, memory_dataflow):
        """Test action suggestions for model errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        actions = inspector._suggest_error_actions(
            error_code="DF-MODEL-001", error_type="ModelError", context={}
        )

        # Should include model schema actions
        assert len(actions) > 0
        assert any(
            "schema" in action.lower() or "model" in action.lower()
            for action in actions
        )

    def test_suggest_actions_with_no_specific_error(self, memory_dataflow):
        """Test action suggestions for unknown errors."""
        db = memory_dataflow
        inspector = Inspector(db)

        actions = inspector._suggest_error_actions(
            error_code="UNKNOWN", error_type="Exception", context={}
        )

        # Should include default actions
        assert len(actions) > 0
        assert any(
            "Inspector" in action or "documentation" in action.lower()
            for action in actions
        )


@pytest.mark.unit
class TestErrorIntegrationWorkflow:
    """Integration tests for error diagnosis workflow."""

    def test_complete_error_diagnosis_workflow(self, memory_dataflow):
        """Test complete workflow from error to diagnosis to fix."""
        db = memory_dataflow

        @db.model
        class WorkflowTestModel:
            id: str
            name: str

        inspector = Inspector(db)

        # 1. Simulate an error
        error = EnhancedDataFlowError(
            error_code="DF-101",
            message="Missing required parameter 'data'",
            context={"node_id": "test_create", "parameter_name": "data"},
            causes=["Parameter not provided"],
            solutions=[
                ErrorSolution(
                    priority=1, description="Add parameter", code_template="add_param"
                )
            ],
        )

        # 2. Diagnose error
        diagnosis = inspector.diagnose_error(error)

        # 3. Verify diagnosis provides useful information
        assert diagnosis.error_code == "DF-101"
        assert diagnosis.affected_component == "test_create"
        assert len(diagnosis.inspector_commands) > 0
        assert len(diagnosis.recommended_actions) > 0

        # 4. Display diagnosis
        output = diagnosis.show(color=False)
        assert "DF-101" in output
        assert "test_create" in output
        assert "Inspector Commands" in output or "$ " in output

    def test_error_diagnosis_show_output_formatting(self, memory_dataflow):
        """Test formatted output of error diagnosis."""
        db = memory_dataflow
        inspector = Inspector(db)

        error = EnhancedDataFlowError(
            error_code="DF-TEST-001",
            message="Test error",
            context={"node_id": "test_node", "detail": "Additional context"},
        )

        diagnosis = inspector.diagnose_error(error)
        output = diagnosis.show(color=False)

        # Verify all sections are present
        assert "Error Diagnosis:" in output
        assert "DF-TEST-001" in output
        assert "test_node" in output
        assert "Recommended" in output  # Recommended Commands or Actions
