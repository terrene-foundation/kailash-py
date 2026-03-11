"""Unit tests for IterativeLLMAgent test-driven convergence.

Tests the test-driven convergence functionality in isolation with mocks.
Following testing policy: Unit tests must be fast (<1s), use mocks, no external dependencies.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from kaizen.nodes.ai.iterative_llm_agent import (
    ConvergenceMode,
    IterationState,
    IterativeLLMAgentNode,
)


class TestIterativeLLMAgentConvergence:
    """Test IterativeLLMAgent convergence modes."""

    def test_convergence_mode_enum(self):
        """Test ConvergenceMode enum values."""
        assert ConvergenceMode.SATISFACTION.value == "satisfaction"
        assert ConvergenceMode.TEST_DRIVEN.value == "test_driven"
        assert ConvergenceMode.HYBRID.value == "hybrid"

    def test_get_parameters_includes_new_params(self):
        """Test that new parameters are included."""
        agent = IterativeLLMAgentNode()
        params = agent.get_parameters()

        # Check new parameters exist
        assert "convergence_mode" in params
        assert params["convergence_mode"].default == "satisfaction"
        assert params["convergence_mode"].type == str

        assert "enable_auto_validation" in params
        assert params["enable_auto_validation"].default is True

        assert "validation_strategy" in params
        assert isinstance(params["validation_strategy"].default, dict)

    @patch.object(IterativeLLMAgentNode, "_discover_mcp_tools")
    def test_auto_inject_validation_tools_test_driven(self, mock_discover):
        """Test validation tools are auto-injected in test-driven mode."""
        agent = IterativeLLMAgentNode()

        # Mock parent class methods
        with patch.object(agent, "_phase_discovery") as mock_discovery:
            with patch.object(agent, "_phase_planning") as mock_planning:
                with patch.object(agent, "_phase_execution") as mock_execution:
                    with patch.object(
                        agent, "_phase_convergence_with_mode"
                    ) as mock_convergence:
                        with patch.object(agent, "_phase_synthesis") as mock_synthesis:
                            # Set up mocks
                            mock_discovery.return_value = {"new_tools": []}
                            mock_planning.return_value = {"execution_steps": []}
                            mock_execution.return_value = {"tool_outputs": {}}
                            mock_convergence.return_value = {
                                "should_stop": True,
                                "reason": "test",
                            }
                            mock_synthesis.return_value = "Final result"

                            # Run with test-driven mode
                            result = agent.execute(
                                messages=[{"role": "user", "content": "test"}],
                                convergence_mode="test_driven",
                                enable_auto_validation=True,
                                max_iterations=1,
                            )

                            # Verify validation tools were added
                            assert result["success"] is True
                            # Check that internal validation server was added
                            call_kwargs = mock_discovery.call_args[0][0]
                            mcp_servers = call_kwargs.get("mcp_servers", [])
                            assert any(
                                isinstance(s, dict) and s.get("type") == "internal"
                                for s in mcp_servers
                            )

    def test_phase_convergence_with_mode_satisfaction(self):
        """Test convergence mode routing for satisfaction mode."""
        agent = IterativeLLMAgentNode()

        # Create test iteration state
        iteration_state = IterationState(
            iteration=1,
            phase="convergence",
            start_time=0,
            execution_results={"tool_outputs": {}},
        )

        # Mock the satisfaction convergence method
        with patch.object(agent, "_phase_convergence") as mock_satisfaction:
            mock_satisfaction.return_value = {
                "should_stop": True,
                "reason": "satisfaction",
                "confidence": 0.85,
            }

            result = agent._phase_convergence_with_mode(
                kwargs={},
                iteration_state=iteration_state,
                previous_iterations=[],
                convergence_criteria={},
                global_discoveries={},
                mode=ConvergenceMode.SATISFACTION,
            )

            # Verify satisfaction method was called
            mock_satisfaction.assert_called_once()
            assert result["reason"] == "satisfaction"

    def test_phase_convergence_with_mode_test_driven(self):
        """Test convergence mode routing for test-driven mode."""
        agent = IterativeLLMAgentNode()

        # Create test iteration state
        iteration_state = IterationState(
            iteration=1,
            phase="convergence",
            start_time=0,
            execution_results={"tool_outputs": {}},
        )

        # Mock the test-driven convergence method
        with patch.object(agent, "_phase_convergence_test_driven") as mock_test_driven:
            mock_test_driven.return_value = {
                "should_stop": True,
                "reason": "test_driven_success",
                "confidence": 0.95,
                "validation_results": {},
            }

            result = agent._phase_convergence_with_mode(
                kwargs={},
                iteration_state=iteration_state,
                previous_iterations=[],
                convergence_criteria={},
                global_discoveries={},
                mode=ConvergenceMode.TEST_DRIVEN,
            )

            # Verify test-driven method was called
            mock_test_driven.assert_called_once()
            assert result["reason"] == "test_driven_success"

    def test_extract_validation_results(self):
        """Test extraction of validation results from execution outputs."""
        agent = IterativeLLMAgentNode()

        # Create iteration state with validation outputs
        iteration_state = IterationState(
            iteration=1,
            phase="execution",
            start_time=0,
            execution_results={
                "tool_outputs": {
                    "validate_code": {
                        "validated": True,
                        "validation_results": [
                            {"test_name": "syntax", "passed": True, "level": "syntax"}
                        ],
                    },
                    "test_runner": {
                        "test_results": [{"name": "test1", "passed": True}]
                    },
                    "other_tool": {"data": "not validation"},
                }
            },
        )

        results = agent._extract_validation_results(iteration_state)

        # Should extract results from both validation tools
        assert len(results) == 2  # 1 from validate_code + 1 from test_runner
        assert any(r.get("test_name") == "syntax" for r in results)
        assert any(r.get("name") == "test1" for r in results)

    def test_analyze_test_results_all_pass(self):
        """Test analyzing test results when all pass."""
        agent = IterativeLLMAgentNode()

        validation_results = [
            {"test_name": "python_syntax", "level": "syntax", "passed": True},
            {"test_name": "import_validation", "level": "imports", "passed": True},
            {"test_name": "code_execution", "level": "semantic", "passed": True},
        ]

        test_requirements = {
            "syntax_valid": True,
            "imports_resolve": True,
            "executes_without_error": True,
            "unit_tests_pass": False,  # Not required
        }

        status = agent._analyze_test_results(validation_results, test_requirements)

        # All required tests should pass
        assert status["syntax_valid"]["passed"] is True
        assert status["imports_resolve"]["passed"] is True
        assert status["executes_without_error"]["passed"] is True
        assert status["unit_tests_pass"]["skipped"] is True

    def test_analyze_test_results_with_failures(self):
        """Test analyzing test results with failures."""
        agent = IterativeLLMAgentNode()

        validation_results = [
            {
                "test_name": "python_syntax",
                "level": "syntax",
                "passed": False,
                "error": "SyntaxError",
            },
            {"test_name": "import_validation", "level": "imports", "passed": True},
        ]

        test_requirements = {
            "syntax_valid": True,
            "imports_resolve": True,
            "executes_without_error": True,
        }

        status = agent._analyze_test_results(validation_results, test_requirements)

        # Syntax should fail
        assert status["syntax_valid"]["passed"] is False
        assert status["syntax_valid"]["error"] == "SyntaxError"

        # Imports should pass
        assert status["imports_resolve"]["passed"] is True

        # Execution not found
        assert status["executes_without_error"]["passed"] is False
        assert status["executes_without_error"]["missing"] is True

    def test_generate_fix_recommendations(self):
        """Test generation of fix recommendations."""
        agent = IterativeLLMAgentNode()

        test_status = {
            "syntax_valid": {"passed": False, "error": "SyntaxError: invalid syntax"},
            "imports_resolve": {
                "passed": False,
                "details": [{"unresolved_list": ["numpy"]}],
            },
            "executes_without_error": {"passed": True},
        }

        failed_tests = ["syntax_valid", "imports_resolve"]
        iteration_state = IterationState(
            iteration=1,
            phase="convergence",
            start_time=0,
            discoveries={"new_tools": []},
        )

        recommendations = agent._generate_fix_recommendations(
            test_status, failed_tests, iteration_state
        )

        # Should have syntax and import recommendations
        assert any("syntax errors" in r for r in recommendations)
        assert any("imports" in r for r in recommendations)
        # Should suggest discovering more tools since none found
        assert any("discovering more tools" in r for r in recommendations)

    def test_phase_convergence_test_driven_success(self):
        """Test test-driven convergence when all tests pass."""
        agent = IterativeLLMAgentNode()

        # Create iteration state with successful validation
        iteration_state = IterationState(
            iteration=1,
            phase="convergence",
            start_time=0,
            execution_results={
                "tool_outputs": {
                    "validate_code": {
                        "validation_results": [
                            {"test_name": "syntax", "level": "syntax", "passed": True},
                            {
                                "test_name": "execution",
                                "level": "semantic",
                                "passed": True,
                            },
                        ]
                    }
                }
            },
        )

        convergence_criteria = {
            "test_requirements": {"syntax_valid": True, "executes_without_error": True}
        }

        result = agent._phase_convergence_test_driven(
            kwargs={},
            iteration_state=iteration_state,
            previous_iterations=[],
            convergence_criteria=convergence_criteria,
            global_discoveries={},
        )

        # Should converge successfully
        assert result["should_stop"] is True
        assert "All 2 required tests passed" in result["reason"]
        assert result["confidence"] == 0.95

    def test_phase_convergence_test_driven_failure(self):
        """Test test-driven convergence when tests fail."""
        agent = IterativeLLMAgentNode()

        # Create iteration state with failed validation
        iteration_state = IterationState(
            iteration=1,
            phase="convergence",
            start_time=0,
            execution_results={
                "tool_outputs": {
                    "validate_code": {
                        "validation_results": [
                            {
                                "test_name": "syntax",
                                "level": "syntax",
                                "passed": False,
                                "error": "SyntaxError",
                            }
                        ]
                    }
                }
            },
        )

        convergence_criteria = {
            "test_requirements": {"syntax_valid": True, "executes_without_error": True}
        }

        result = agent._phase_convergence_test_driven(
            kwargs={},
            iteration_state=iteration_state,
            previous_iterations=[],
            convergence_criteria=convergence_criteria,
            global_discoveries={},
        )

        # Should not converge
        assert result["should_stop"] is False
        assert "2 required tests failed" in result["reason"]
        assert len(result["recommendations"]) > 0

    @patch("kailash.nodes.validation.CodeValidationNode")
    def test_perform_implicit_validation(self, mock_validation_class):
        """Test implicit validation of generated code."""
        agent = IterativeLLMAgentNode()

        # Mock validation node
        mock_validator = MagicMock()
        mock_validation_class.return_value = mock_validator
        mock_validator.execute.return_value = {
            "validation_results": [
                {"test_name": "syntax", "level": "syntax", "passed": True}
            ]
        }

        # Create iteration state with code output
        iteration_state = IterationState(
            iteration=1,
            phase="execution",
            start_time=0,
            execution_results={
                "tool_outputs": {
                    "generate_code": {"code": "def hello():\n    return 'world'"}
                }
            },
        )

        test_requirements = {"syntax_valid": True}
        validation_strategy = {}

        results = agent._perform_implicit_validation(
            iteration_state, test_requirements, validation_strategy
        )

        # Should validate the discovered code
        assert len(results) == 1
        assert results[0]["test_name"] == "syntax"
        mock_validator.execute.assert_called_once()

    def test_phase_convergence_hybrid(self):
        """Test hybrid convergence mode."""
        agent = IterativeLLMAgentNode()

        iteration_state = IterationState(
            iteration=1, phase="convergence", start_time=0, execution_results={}
        )

        # Mock both convergence methods
        with patch.object(agent, "_phase_convergence_test_driven") as mock_test:
            with patch.object(agent, "_phase_convergence") as mock_satisfaction:
                mock_test.return_value = {
                    "should_stop": True,
                    "confidence": 0.9,
                    "validation_results": {},
                    "recommendations": ["test recommendation"],
                }
                mock_satisfaction.return_value = {
                    "should_stop": False,
                    "confidence": 0.7,
                    "criteria_met": {},
                    "recommendations": ["satisfaction recommendation"],
                }

                convergence_criteria = {
                    "hybrid_config": {
                        "test_weight": 0.6,
                        "satisfaction_weight": 0.4,
                        "require_both": False,
                    },
                    "hybrid_threshold": 0.8,
                }

                result = agent._phase_convergence_hybrid(
                    kwargs={},
                    iteration_state=iteration_state,
                    previous_iterations=[],
                    convergence_criteria=convergence_criteria,
                    global_discoveries={},
                )

                # Should calculate weighted confidence
                expected_confidence = 0.9 * 0.6 + 0.7 * 0.4  # 0.82
                assert result["confidence"] == pytest.approx(expected_confidence, 0.01)
                assert result["should_stop"] is True  # > 0.8 threshold
                assert len(result["recommendations"]) == 2
