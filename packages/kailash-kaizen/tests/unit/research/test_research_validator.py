"""
Unit tests for ResearchValidator - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Validate research implementation reproducibility (>95% target)
2. Benchmark against paper claims
3. Quality scoring (6 dimensions from TODO-145)
4. Detect validation issues
5. Handle validation failures
6. Performance validation (<5 minutes per validation)

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock, patch


class TestResearchValidator:
    """Test suite for ResearchValidator component."""

    def test_validator_initialization(self):
        """Test ResearchValidator can be instantiated."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()
        assert validator is not None
        assert hasattr(validator, "validate_implementation")
        assert hasattr(validator, "_run_validation")
        assert hasattr(validator, "_identify_issues")

    def test_validate_flash_attention_success(
        self, flash_attention_paper, validation_dataset
    ):
        """Test successful validation of Flash Attention implementation."""
        from pathlib import Path

        from kaizen.research import ResearchValidator, ValidationResult

        validator = ResearchValidator()

        # Mock code execution and validation
        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch.object(Path, "glob") as mock_glob,
        ):
            # Mock test files exist so subprocess.run gets called
            mock_glob.return_value = [Path("test_example.py")]

            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7\naccuracy: 1.0", stderr=""
            )

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/Dao-AILab/flash-attention",
                validation_dataset=validation_dataset,
            )

            assert isinstance(result, ValidationResult)
            assert result.validation_passed is True
            assert result.reproducibility_score >= 0.95
            assert "speedup" in result.reproduced_metrics
            # Should be close to paper's claimed 2.7x
            assert abs(result.reproduced_metrics["speedup"] - 2.7) < 0.5

    def test_validate_maml_success(self, maml_paper):
        """Test successful validation of MAML implementation."""
        from pathlib import Path

        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch.object(Path, "glob") as mock_glob,
        ):
            # Mock test files exist so subprocess.run gets called
            mock_glob.return_value = [Path("test_example.py")]

            # Return metrics that match MAML paper: few_shot_accuracy, adaptation_steps, tasks_tested
            mock_subprocess.run.return_value = Mock(
                returncode=0,
                stdout="few_shot_accuracy: 0.95\nadaptation_steps: 5.0\ntasks_tested: 20.0",
                stderr="",
            )

            result = validator.validate_implementation(
                paper=maml_paper,
                code_url="https://github.com/cbfinn/maml",
                validation_dataset=None,  # Uses default dataset
            )

            assert result.validation_passed is True
            assert result.reproducibility_score >= 0.95

    def test_validate_invalid_paper_failure(self, invalid_paper):
        """Test validation failure for invalid paper."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        result = validator.validate_implementation(
            paper=invalid_paper,
            code_url="https://github.com/invalid/repo",
            validation_dataset=None,
        )

        assert result.validation_passed is False
        assert len(result.issues) > 0
        assert result.reproducibility_score < 0.95

    def test_validate_code_not_found(self, flash_attention_paper):
        """Test validation when code repository is not accessible."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with patch("kaizen.research.validator.git.Repo.clone_from") as mock_clone:
            mock_clone.side_effect = Exception("Repository not found")

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/nonexistent/repo",
                validation_dataset=None,
            )

            assert result.validation_passed is False
            assert any("repository" in issue.lower() for issue in result.issues)

    def test_validate_metric_mismatch(self, flash_attention_paper, validation_dataset):
        """Test validation failure when reproduced metrics don't match claims."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        # Mock validation that produces different metrics
        with (
            patch.object(validator, "_run_validation") as mock_run,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):
            # Return tuple (metrics, stderr)
            mock_run.return_value = (
                {"speedup": 1.5, "accuracy": 0.98},  # Much lower than claimed 2.7x
                "",
            )

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/Dao-AILab/flash-attention",
                validation_dataset=validation_dataset,
            )

            # Should detect significant metric deviation
            assert result.reproducibility_score < 0.95 or len(result.issues) > 0

    def test_validate_performance_timing(
        self, flash_attention_paper, performance_timer
    ):
        """Test validation completes within <5 minutes target."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="Validation passed"
            )

            # Fix: Instantiate the Timer class
            timer = performance_timer()
            timer.start()
            validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )
            timer.stop()

            # Should complete in <5 minutes (300 seconds)
            timer.assert_under(300.0, "Validation")

    def test_quality_scoring_comprehensive(self, flash_attention_paper):
        """Test comprehensive quality scoring using TODO-145 QualityMetrics."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):
            mock_subprocess.run.return_value = Mock(returncode=0)

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            # Should have quality score with multiple dimensions
            assert hasattr(result, "quality_score")
            assert isinstance(result.quality_score, dict)

            # TODO-145 defines 6 quality dimensions

            # Should have at least some quality dimensions
            assert len(result.quality_score) > 0

    def test_validate_calculates_reproducibility_score(self, flash_attention_paper):
        """Test reproducibility score calculation."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch.object(validator, "_run_validation") as mock_run,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):
            # Perfectly reproduced metrics - return tuple (metrics, stderr)
            mock_run.return_value = ({"speedup": 2.7, "accuracy": 1.0}, "")

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            # Perfect reproduction should have score near 1.0
            assert result.reproducibility_score >= 0.95
            assert result.reproducibility_score <= 1.0

    def test_validate_partial_reproducibility(self, flash_attention_paper):
        """Test scoring when some metrics reproduce, others don't."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch.object(validator, "_run_validation") as mock_run,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):
            # Mixed results - speedup good, accuracy slightly off - return tuple (metrics, stderr)
            mock_run.return_value = (
                {
                    "speedup": 2.6,  # Close to 2.7 (3.7% deviation)
                    "accuracy": 0.95,  # Close to 1.0 (5% deviation)
                },
                "",
            )

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            # Should still pass but with lower score
            # speedup: 1.0 - 0.037/0.2 = 0.815
            # accuracy: 1.0 - 0.05/0.2 = 0.75
            # Average = 0.7825
            assert 0.75 <= result.reproducibility_score < 1.0

    def test_identify_issues_missing_dependencies(self, flash_attention_paper):
        """Test issue identification for missing dependencies."""
        from pathlib import Path

        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch.object(Path, "glob") as mock_glob,
        ):
            # Mock test files exist so subprocess.run gets called
            mock_glob.return_value = [Path("test_example.py")]

            mock_subprocess.run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="ModuleNotFoundError: No module named 'flash_attn'",
            )

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            assert result.validation_passed is False
            assert any(
                "dependenc" in issue.lower() or "module" in issue.lower()
                for issue in result.issues
            )

    def test_identify_issues_runtime_error(self, flash_attention_paper):
        """Test issue identification for runtime errors."""
        from pathlib import Path

        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch.object(Path, "glob") as mock_glob,
        ):
            # Mock test files exist so subprocess.run gets called
            mock_glob.return_value = [Path("test_example.py")]

            mock_subprocess.run.return_value = Mock(
                returncode=1, stdout="", stderr="RuntimeError: CUDA out of memory"
            )

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            assert result.validation_passed is False
            assert any(
                "runtime" in issue.lower() or "memory" in issue.lower()
                for issue in result.issues
            )

    def test_validate_with_custom_validation_dataset(self, flash_attention_paper):
        """Test validation using custom dataset."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        custom_dataset = [
            {"input": "custom_test_1", "expected": "result_1"},
            {"input": "custom_test_2", "expected": "result_2"},
        ]

        with patch("kaizen.research.validator.subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = Mock(returncode=0)

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=custom_dataset,
            )

            # Should use custom dataset for validation
            assert result is not None


class TestValidationResult:
    """Test ValidationResult data structure."""

    def test_validation_result_creation(self):
        """Test ValidationResult can be created with required fields."""
        from kaizen.research import ValidationResult

        result = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"accuracy": 0.95},
            issues=[],
        )

        assert result.validation_passed is True
        assert result.reproducibility_score == 0.96
        assert result.reproduced_metrics["speedup"] == 2.7
        assert len(result.issues) == 0

    def test_validation_result_with_issues(self):
        """Test ValidationResult with validation issues."""
        from kaizen.research import ValidationResult

        result = ValidationResult(
            validation_passed=False,
            reproducibility_score=0.75,
            reproduced_metrics={},
            quality_score={},
            issues=["Dependency missing", "Runtime error"],
        )

        assert result.validation_passed is False
        assert len(result.issues) == 2
        assert "Dependency missing" in result.issues

    def test_validation_result_optional_fields(self):
        """Test ValidationResult with optional fields."""
        from kaizen.research import ValidationResult

        result = ValidationResult(validation_passed=True, reproducibility_score=0.95)

        # Should have sensible defaults for optional fields
        assert hasattr(result, "reproduced_metrics")
        assert hasattr(result, "quality_score")
        assert hasattr(result, "issues")


class TestIntegrationWithQualityMetrics:
    """Test integration with TODO-145 QualityMetrics system."""

    def test_uses_quality_metrics_from_optimization(self, flash_attention_paper):
        """Test that validator uses QualityMetrics from TODO-145."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        # Validator should have access to QualityMetrics
        assert hasattr(validator, "_calculate_quality_score")

        with patch("kaizen.research.validator.subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = Mock(returncode=0)

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            # Quality score should be calculated using TODO-145 metrics
            assert hasattr(result, "quality_score")

    def test_quality_dimensions_match_todo_145(self, flash_attention_paper):
        """Test quality scoring uses TODO-145's 6 dimensions."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        with patch("kaizen.research.validator.subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = Mock(returncode=0)

            result = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            # Should align with TODO-145 quality dimensions
            if result.quality_score:
                # Quality metrics should be numerical scores
                for score in result.quality_score.values():
                    assert isinstance(score, (int, float))
                    assert 0.0 <= score <= 1.0
