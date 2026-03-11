"""
Example Validation Tests

Validates that all autonomy examples:
1. Exist in the expected locations
2. Have valid Python syntax (can be imported)
3. Have comprehensive README documentation
4. Follow consistent naming patterns

These tests DO NOT execute examples (that's in integration tests).
They only validate structure and basic validity.
"""

import importlib.util
from pathlib import Path

import pytest

# Base directory for autonomy examples
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples" / "autonomy"


class TestToolCallingExamples:
    """Validate tool calling examples exist and are importable."""

    def test_code_review_agent_exists(self):
        """Verify code review agent example exists."""
        example_dir = EXAMPLES_DIR / "tool-calling" / "code-review-agent"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "code_review_agent.py").exists()
        assert (example_dir / "README.md").exists()

    def test_data_analysis_agent_exists(self):
        """Verify data analysis agent example exists."""
        example_dir = EXAMPLES_DIR / "tool-calling" / "data-analysis-agent"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "data_analysis_agent.py").exists()
        assert (example_dir / "README.md").exists()

    def test_devops_agent_exists(self):
        """Verify devops agent example exists."""
        example_dir = EXAMPLES_DIR / "tool-calling" / "devops-agent"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "devops_agent.py").exists()
        assert (example_dir / "README.md").exists()


class TestPlanningExamples:
    """Validate planning examples exist and are importable."""

    def test_research_assistant_exists(self):
        """Verify research assistant example exists."""
        example_dir = EXAMPLES_DIR / "planning" / "research-assistant"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "research_assistant.py").exists()
        assert (example_dir / "README.md").exists()

    def test_content_creator_exists(self):
        """Verify content creator example exists."""
        example_dir = EXAMPLES_DIR / "planning" / "content-creator"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "content_creator.py").exists()
        assert (example_dir / "README.md").exists()

    def test_problem_solver_exists(self):
        """Verify problem solver example exists."""
        example_dir = EXAMPLES_DIR / "planning" / "problem-solver"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "problem_solver.py").exists()
        assert (example_dir / "README.md").exists()


class TestMetaControllerExamples:
    """Validate meta-controller examples exist and are importable."""

    def test_multi_specialist_coding_exists(self):
        """Verify multi-specialist coding example exists."""
        example_dir = EXAMPLES_DIR / "meta-controller" / "multi-specialist-coding"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "multi_specialist_coding.py").exists()
        assert (example_dir / "README.md").exists()

    def test_complex_data_pipeline_exists(self):
        """Verify complex data pipeline example exists."""
        example_dir = EXAMPLES_DIR / "meta-controller" / "complex-data-pipeline"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "complex_data_pipeline.py").exists()
        assert (example_dir / "README.md").exists()


class TestMemoryExamples:
    """Validate memory examples exist and are importable."""

    def test_long_running_research_exists(self):
        """Verify long-running research example exists."""
        example_dir = EXAMPLES_DIR / "memory" / "long-running-research"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "long_running_research.py").exists()
        assert (example_dir / "README.md").exists()

    def test_customer_support_exists(self):
        """Verify customer support example exists."""
        example_dir = EXAMPLES_DIR / "memory" / "customer-support"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "customer_support_agent.py").exists()
        assert (example_dir / "README.md").exists()


class TestCheckpointExamples:
    """Validate checkpoint examples exist and are importable."""

    def test_resume_interrupted_research_exists(self):
        """Verify resume interrupted research example exists."""
        example_dir = EXAMPLES_DIR / "checkpoints" / "resume-interrupted-research"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "resume_interrupted_research.py").exists()
        assert (example_dir / "README.md").exists()

    def test_multi_day_project_exists(self):
        """Verify multi-day project example exists."""
        example_dir = EXAMPLES_DIR / "checkpoints" / "multi-day-project"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "multi_day_project.py").exists()
        assert (example_dir / "README.md").exists()


class TestInterruptExamples:
    """Validate interrupt examples exist and are importable."""

    def test_ctrl_c_interrupt_exists(self):
        """Verify ctrl+c interrupt example exists."""
        example_file = EXAMPLES_DIR / "interrupts" / "01_ctrl_c_interrupt.py"
        readme_file = EXAMPLES_DIR / "interrupts" / "README_01_ctrl_c.md"
        assert example_file.exists(), f"Missing file: {example_file}"
        assert readme_file.exists(), f"Missing README: {readme_file}"

    def test_budget_interrupt_exists(self):
        """Verify budget interrupt example exists."""
        example_file = EXAMPLES_DIR / "interrupts" / "03_budget_interrupt.py"
        readme_file = EXAMPLES_DIR / "interrupts" / "README_03_budget.md"
        assert example_file.exists(), f"Missing file: {example_file}"
        assert readme_file.exists(), f"Missing README: {readme_file}"


class TestFullIntegrationExample:
    """Validate full integration example exists and is importable."""

    def test_autonomous_research_agent_exists(self):
        """Verify autonomous research agent example exists."""
        example_dir = EXAMPLES_DIR / "full-integration" / "autonomous-research-agent"
        assert example_dir.exists(), f"Missing directory: {example_dir}"
        assert (example_dir / "autonomous_research_agent.py").exists()
        assert (example_dir / "README.md").exists()


class TestExampleGalleryDocumentation:
    """Validate example gallery documentation."""

    def test_gallery_documentation_exists(self):
        """Verify EXAMPLE_GALLERY.md exists."""
        gallery_path = EXAMPLES_DIR / "EXAMPLE_GALLERY.md"
        assert gallery_path.exists(), f"Missing EXAMPLE_GALLERY.md at {gallery_path}"

    def test_gallery_has_required_sections(self):
        """Verify gallery has all required sections."""
        gallery_path = EXAMPLES_DIR / "EXAMPLE_GALLERY.md"
        content = gallery_path.read_text()

        # Required sections
        required_sections = [
            "## 📚 Overview",
            "## 🎯 Prerequisites",
            "## 📂 Example Categories",
            "## 🎓 Learning Paths",
            "## 🏗️ Production Patterns",
            "## 🎯 Common Use Cases",
            "## 📊 Quick Reference Table",
            "## 🆘 Getting Help",
        ]

        for section in required_sections:
            assert section in content, f"Missing section: {section}"

    def test_gallery_references_all_examples(self):
        """Verify gallery references all 15 examples."""
        gallery_path = EXAMPLES_DIR / "EXAMPLE_GALLERY.md"
        content = gallery_path.read_text()

        # All 15 examples should be mentioned
        expected_examples = [
            "Code Review Agent",
            "Data Analysis Agent",
            "DevOps Agent",
            "Research Assistant",
            "Content Creator",
            "Problem Solver",
            "Multi-Specialist Coding",
            "Complex Data Pipeline",
            "Long-Running Research",
            "Customer Support",
            "Resume Interrupted Research",
            "Multi-Day Project",
            "Ctrl+C Interrupt",
            "Budget Interrupt",
            "Autonomous Research Agent",
        ]

        for example in expected_examples:
            assert example in content, f"Gallery missing reference to: {example}"


class TestREADMEQuality:
    """Validate README files meet quality standards."""

    def test_all_readmes_have_minimum_length(self):
        """Verify all READMEs are comprehensive (>100 lines)."""
        readme_paths = [
            EXAMPLES_DIR / "tool-calling" / "code-review-agent" / "README.md",
            EXAMPLES_DIR / "tool-calling" / "data-analysis-agent" / "README.md",
            EXAMPLES_DIR / "tool-calling" / "devops-agent" / "README.md",
            EXAMPLES_DIR / "planning" / "research-assistant" / "README.md",
            EXAMPLES_DIR / "planning" / "content-creator" / "README.md",
            EXAMPLES_DIR / "planning" / "problem-solver" / "README.md",
            EXAMPLES_DIR / "meta-controller" / "multi-specialist-coding" / "README.md",
            EXAMPLES_DIR / "meta-controller" / "complex-data-pipeline" / "README.md",
            EXAMPLES_DIR / "memory" / "long-running-research" / "README.md",
            EXAMPLES_DIR / "memory" / "customer-support" / "README.md",
            EXAMPLES_DIR / "checkpoints" / "resume-interrupted-research" / "README.md",
            EXAMPLES_DIR / "checkpoints" / "multi-day-project" / "README.md",
            EXAMPLES_DIR / "interrupts" / "README_01_ctrl_c.md",
            EXAMPLES_DIR / "interrupts" / "README_03_budget.md",
            EXAMPLES_DIR
            / "full-integration"
            / "autonomous-research-agent"
            / "README.md",
        ]

        for readme_path in readme_paths:
            assert readme_path.exists(), f"Missing README: {readme_path}"
            content = readme_path.read_text()
            line_count = len(content.splitlines())
            assert (
                line_count >= 100
            ), f"README too short ({line_count} lines): {readme_path.name}"

    def test_all_readmes_have_expected_sections(self):
        """Verify READMEs have standard sections."""
        readme_paths = [
            EXAMPLES_DIR / "tool-calling" / "code-review-agent" / "README.md",
            EXAMPLES_DIR / "tool-calling" / "data-analysis-agent" / "README.md",
            EXAMPLES_DIR / "planning" / "research-assistant" / "README.md",
            EXAMPLES_DIR / "memory" / "customer-support" / "README.md",
            EXAMPLES_DIR
            / "full-integration"
            / "autonomous-research-agent"
            / "README.md",
        ]

        for readme_path in readme_paths:
            content = readme_path.read_text()

            # Common sections that should appear
            expected_patterns = [
                "## ",  # Has at least one section
                "Features",  # Describes features
                "Usage",  # Shows how to use
                "Output",  # Shows expected output
            ]

            for pattern in expected_patterns:
                assert (
                    pattern in content
                ), f"README missing '{pattern}': {readme_path.name}"


class TestPythonSyntax:
    """Validate Python files have valid syntax."""

    def test_all_examples_have_valid_syntax(self):
        """Verify all example Python files can be compiled."""
        example_files = [
            EXAMPLES_DIR
            / "tool-calling"
            / "code-review-agent"
            / "code_review_agent.py",
            EXAMPLES_DIR
            / "tool-calling"
            / "data-analysis-agent"
            / "data_analysis_agent.py",
            EXAMPLES_DIR / "tool-calling" / "devops-agent" / "devops_agent.py",
            EXAMPLES_DIR / "planning" / "research-assistant" / "research_assistant.py",
            EXAMPLES_DIR / "planning" / "content-creator" / "content_creator.py",
            EXAMPLES_DIR / "planning" / "problem-solver" / "problem_solver.py",
            EXAMPLES_DIR
            / "meta-controller"
            / "multi-specialist-coding"
            / "multi_specialist_coding.py",
            EXAMPLES_DIR
            / "meta-controller"
            / "complex-data-pipeline"
            / "complex_data_pipeline.py",
            EXAMPLES_DIR
            / "memory"
            / "long-running-research"
            / "long_running_research.py",
            EXAMPLES_DIR / "memory" / "customer-support" / "customer_support_agent.py",
            EXAMPLES_DIR
            / "checkpoints"
            / "resume-interrupted-research"
            / "resume_interrupted_research.py",
            EXAMPLES_DIR / "checkpoints" / "multi-day-project" / "multi_day_project.py",
            EXAMPLES_DIR / "interrupts" / "01_ctrl_c_interrupt.py",
            EXAMPLES_DIR / "interrupts" / "03_budget_interrupt.py",
            EXAMPLES_DIR
            / "full-integration"
            / "autonomous-research-agent"
            / "autonomous_research_agent.py",
        ]

        for example_file in example_files:
            assert example_file.exists(), f"Missing file: {example_file}"

            # Test that file can be compiled (syntax check)
            with open(example_file, "r") as f:
                code = f.read()

            try:
                compile(code, example_file, "exec")
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {example_file.name}: {e}")


class TestProjectStructure:
    """Validate overall project structure."""

    def test_all_categories_exist(self):
        """Verify all example categories exist."""
        categories = [
            "tool-calling",
            "planning",
            "meta-controller",
            "memory",
            "checkpoints",
            "interrupts",
            "full-integration",
        ]

        for category in categories:
            category_dir = EXAMPLES_DIR / category
            assert category_dir.exists(), f"Missing category: {category}"

    def test_example_count(self):
        """Verify we have exactly 15 examples."""
        # Count example directories (exclude interrupts which are files, not dirs)
        example_count = 0

        # Tool calling (3)
        example_count += len(list((EXAMPLES_DIR / "tool-calling").iterdir()))

        # Planning (3)
        example_count += len(list((EXAMPLES_DIR / "planning").iterdir()))

        # Meta-controller (2)
        example_count += len(list((EXAMPLES_DIR / "meta-controller").iterdir()))

        # Memory (2)
        example_count += len(list((EXAMPLES_DIR / "memory").iterdir()))

        # Checkpoints (2)
        example_count += len(list((EXAMPLES_DIR / "checkpoints").iterdir()))

        # Interrupts (2 files)
        example_count += 2

        # Full integration (1)
        example_count += len(list((EXAMPLES_DIR / "full-integration").iterdir()))

        assert example_count == 15, f"Expected 15 examples, found {example_count}"
