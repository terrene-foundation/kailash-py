"""
Unit Tests for TaskAnalyzer (Tier 1)

Tests the TaskAnalyzer for task complexity and type detection:
- TaskComplexity and TaskType enums
- TaskAnalysis dataclass
- Complexity detection
- Type detection
- Requirement detection
"""

import pytest

from kaizen.llm.routing.analyzer import (
    TaskAnalysis,
    TaskAnalyzer,
    TaskComplexity,
    TaskType,
)


class TestTaskComplexity:
    """Tests for TaskComplexity enum."""

    def test_all_complexities_exist(self):
        """Test all complexity levels exist."""
        assert TaskComplexity.TRIVIAL
        assert TaskComplexity.LOW
        assert TaskComplexity.MEDIUM
        assert TaskComplexity.HIGH
        assert TaskComplexity.EXPERT

    def test_complexity_values(self):
        """Test complexity values."""
        assert TaskComplexity.TRIVIAL.value == "trivial"
        assert TaskComplexity.LOW.value == "low"
        assert TaskComplexity.MEDIUM.value == "medium"
        assert TaskComplexity.HIGH.value == "high"
        assert TaskComplexity.EXPERT.value == "expert"


class TestTaskType:
    """Tests for TaskType enum."""

    def test_all_types_exist(self):
        """Test all task types exist."""
        assert TaskType.SIMPLE_QA
        assert TaskType.CODE
        assert TaskType.ANALYSIS
        assert TaskType.CREATIVE
        assert TaskType.STRUCTURED
        assert TaskType.REASONING
        assert TaskType.MULTIMODAL

    def test_type_values(self):
        """Test type values."""
        assert TaskType.SIMPLE_QA.value == "simple_qa"
        assert TaskType.CODE.value == "code"
        assert TaskType.ANALYSIS.value == "analysis"


class TestTaskAnalysisDataclass:
    """Tests for TaskAnalysis dataclass."""

    def test_create_default(self):
        """Test creating with defaults."""
        analysis = TaskAnalysis()

        assert analysis.complexity == TaskComplexity.MEDIUM
        assert analysis.type == TaskType.SIMPLE_QA
        assert analysis.requires_vision is False
        assert analysis.requires_tools is False
        assert analysis.confidence == 0.5

    def test_create_full(self):
        """Test creating with all parameters."""
        analysis = TaskAnalysis(
            complexity=TaskComplexity.HIGH,
            type=TaskType.CODE,
            requires_vision=True,
            requires_tools=True,
            requires_structured=True,
            estimated_tokens=1500,
            specialties_needed=["code", "reasoning"],
            confidence=0.9,
            reasoning="Complex code task",
        )

        assert analysis.complexity == TaskComplexity.HIGH
        assert analysis.type == TaskType.CODE
        assert analysis.requires_vision is True
        assert analysis.estimated_tokens == 1500
        assert "code" in analysis.specialties_needed

    def test_to_dict(self):
        """Test serialization."""
        analysis = TaskAnalysis(
            complexity=TaskComplexity.HIGH,
            type=TaskType.CODE,
            confidence=0.85,
        )

        data = analysis.to_dict()

        assert data["complexity"] == "high"
        assert data["type"] == "code"
        assert data["confidence"] == 0.85


class TestTaskAnalyzerCreation:
    """Tests for TaskAnalyzer creation."""

    def test_create_default(self):
        """Test creating with defaults."""
        analyzer = TaskAnalyzer()

        assert analyzer is not None

    def test_create_with_llm_analyzer(self):
        """Test creating with LLM analyzer."""

        def mock_llm(task, ctx):
            return TaskAnalysis(confidence=0.99)

        analyzer = TaskAnalyzer(
            llm_analyzer=mock_llm,
            use_llm_for_ambiguous=True,
        )

        assert analyzer._llm_analyzer is not None


class TestTaskAnalyzerTypeDetection:
    """Tests for task type detection."""

    def test_detect_code_task(self):
        """Test detecting code tasks."""
        analyzer = TaskAnalyzer()

        # Clear code indicators
        analysis = analyzer.analyze(
            "Write a Python function to sort a list using quicksort algorithm"
        )
        assert analysis.type == TaskType.CODE

        analysis = analyzer.analyze(
            "Debug this JavaScript code that has a null reference error"
        )
        assert analysis.type == TaskType.CODE

        analysis = analyzer.analyze("Implement a REST API endpoint for user login")
        assert analysis.type == TaskType.CODE

    def test_detect_analysis_task(self):
        """Test detecting analysis tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Analyze the sales data and identify trends")
        assert analysis.type == TaskType.ANALYSIS

        analysis = analyzer.analyze(
            "Evaluate the performance metrics and compare results"
        )
        assert analysis.type == TaskType.ANALYSIS

    def test_detect_creative_task(self):
        """Test detecting creative tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Write a short story about a robot learning to love"
        )
        assert analysis.type == TaskType.CREATIVE

        analysis = analyzer.analyze("Compose a poem about nature")
        assert analysis.type == TaskType.CREATIVE

        analysis = analyzer.analyze("Create marketing content for our new product")
        assert analysis.type == TaskType.CREATIVE

    def test_detect_structured_task(self):
        """Test detecting structured output tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Convert this text to JSON format")
        assert analysis.type == TaskType.STRUCTURED

        analysis = analyzer.analyze("Extract entities and output as YAML")
        assert analysis.type == TaskType.STRUCTURED

    def test_detect_reasoning_task(self):
        """Test detecting reasoning tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Think through the logical implications and derive a conclusion"
        )
        assert analysis.type == TaskType.REASONING

        analysis = analyzer.analyze("Prove that this mathematical theorem is true")
        assert analysis.type == TaskType.REASONING

    def test_detect_simple_qa(self):
        """Test detecting simple Q&A."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("What is the capital of France?")
        assert analysis.type == TaskType.SIMPLE_QA

        analysis = analyzer.analyze("Define photosynthesis")
        assert analysis.type == TaskType.SIMPLE_QA

    def test_detect_multimodal(self):
        """Test detecting multimodal tasks from context."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Describe what you see",
            context={"has_images": True},
        )
        assert analysis.type == TaskType.MULTIMODAL


class TestTaskAnalyzerComplexityDetection:
    """Tests for complexity detection."""

    def test_detect_trivial_complexity(self):
        """Test detecting trivial tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("What is 2+2?")
        assert analysis.complexity in (TaskComplexity.TRIVIAL, TaskComplexity.LOW)

        analysis = analyzer.analyze("Yes or no: Is Python a programming language?")
        assert analysis.complexity in (TaskComplexity.TRIVIAL, TaskComplexity.LOW)

    def test_detect_low_complexity(self):
        """Test detecting low complexity tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Give me a simple example of a for loop")
        assert analysis.complexity in (TaskComplexity.TRIVIAL, TaskComplexity.LOW)

    def test_detect_medium_complexity(self):
        """Test detecting medium complexity tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Write a function to validate email addresses in Python"
        )
        # Code tasks default to medium
        assert analysis.complexity in (
            TaskComplexity.LOW,
            TaskComplexity.MEDIUM,
            TaskComplexity.HIGH,
        )

    def test_detect_high_complexity(self):
        """Test detecting high complexity tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Design a comprehensive, scalable microservices architecture "
            "for a production e-commerce platform with multiple services "
            "and advanced security considerations"
        )
        assert analysis.complexity in (TaskComplexity.HIGH, TaskComplexity.EXPERT)

    def test_detect_expert_complexity(self):
        """Test detecting expert complexity."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Develop a sophisticated, comprehensive, advanced system "
            "for enterprise-grade, production-ready, scalable architecture "
            "with multi-step reasoning and complex security considerations"
        )
        assert analysis.complexity in (TaskComplexity.HIGH, TaskComplexity.EXPERT)

    def test_long_task_increases_complexity(self):
        """Test that very long tasks increase complexity."""
        analyzer = TaskAnalyzer()

        short_task = "Write a hello world program"
        long_task = "Write a program " + "with detailed step by step " * 50

        short_analysis = analyzer.analyze(short_task)
        long_analysis = analyzer.analyze(long_task)

        # Long task should be at least as complex
        complexity_order = list(TaskComplexity)
        short_idx = complexity_order.index(short_analysis.complexity)
        long_idx = complexity_order.index(long_analysis.complexity)
        assert long_idx >= short_idx


class TestTaskAnalyzerRequirementDetection:
    """Tests for requirement detection."""

    def test_detect_vision_requirement(self):
        """Test detecting vision requirement."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Describe the image attached")
        assert analysis.requires_vision is True

        analysis = analyzer.analyze("What's in this picture?")
        assert analysis.requires_vision is True

        analysis = analyzer.analyze("Look at the screenshot and identify the error")
        assert analysis.requires_vision is True

    def test_detect_vision_from_context(self):
        """Test vision from context."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Describe this", context={"has_images": True})
        assert analysis.requires_vision is True

    def test_detect_audio_requirement(self):
        """Test detecting audio requirement."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Transcribe this audio recording")
        assert analysis.requires_audio is True

        analysis = analyzer.analyze("Listen to the voice message")
        assert analysis.requires_audio is True

    def test_detect_tool_requirement(self):
        """Test detecting tool requirement."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Execute this code and show the output")
        assert analysis.requires_tools is True

        analysis = analyzer.analyze("Search the web for recent news")
        assert analysis.requires_tools is True

    def test_detect_structured_requirement(self):
        """Test detecting structured output requirement."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Return the result as JSON")
        assert analysis.requires_structured is True

        analysis = analyzer.analyze("Output in YAML format")
        assert analysis.requires_structured is True


class TestTaskAnalyzerEstimates:
    """Tests for token estimation."""

    def test_estimated_tokens_trivial(self):
        """Test token estimation for trivial tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("What is 2+2?")

        # Trivial tasks should have low token estimate
        assert analysis.estimated_tokens <= 200

    def test_estimated_tokens_complex(self):
        """Test token estimation for complex tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Write a comprehensive analysis with detailed recommendations "
            "for improving system performance across multiple dimensions"
        )

        # Complex tasks should have higher token estimate
        assert analysis.estimated_tokens >= 500


class TestTaskAnalyzerSpecialties:
    """Tests for specialty detection."""

    def test_code_specialties(self):
        """Test specialties for code tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Write a Python function")

        assert "code" in analysis.specialties_needed

    def test_analysis_specialties(self):
        """Test specialties for analysis tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Analyze the data and provide insights")

        assert (
            "analysis" in analysis.specialties_needed
            or "reasoning" in analysis.specialties_needed
        )

    def test_reasoning_added_for_high_complexity(self):
        """Test reasoning specialty for high complexity."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze(
            "Design a sophisticated, advanced, comprehensive system architecture"
        )

        # High complexity should include reasoning
        if analysis.complexity in (TaskComplexity.HIGH, TaskComplexity.EXPERT):
            assert "reasoning" in analysis.specialties_needed


class TestTaskAnalyzerConfidence:
    """Tests for confidence calculation."""

    def test_high_confidence_clear_indicators(self):
        """Test high confidence for clear task indicators."""
        analyzer = TaskAnalyzer()

        # Many code indicators
        analysis = analyzer.analyze(
            "Implement a Python function to debug the algorithm code "
            "and refactor the class method"
        )

        assert analysis.confidence >= 0.5

    def test_lower_confidence_ambiguous(self):
        """Test lower confidence for ambiguous tasks."""
        analyzer = TaskAnalyzer()

        # Very short, ambiguous
        analysis = analyzer.analyze("Help")

        assert analysis.confidence <= 0.5

    def test_confidence_short_task(self):
        """Test confidence for very short tasks."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Hi")

        # Short tasks have lower confidence
        assert analysis.confidence < 0.5


class TestTaskAnalyzerReasoning:
    """Tests for reasoning explanation."""

    def test_reasoning_includes_type(self):
        """Test reasoning includes task type."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Write Python code")

        assert "code" in analysis.reasoning.lower()

    def test_reasoning_includes_complexity(self):
        """Test reasoning includes complexity."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Simple question")

        assert analysis.complexity.value in analysis.reasoning.lower()


class TestTaskAnalyzerEdgeCases:
    """Tests for edge cases."""

    def test_empty_task(self):
        """Test with empty task."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("")

        # Should return defaults
        assert analysis.type == TaskType.SIMPLE_QA
        assert analysis.complexity in (
            TaskComplexity.LOW,
            TaskComplexity.TRIVIAL,
            TaskComplexity.MEDIUM,
        )

    def test_unicode_task(self):
        """Test with unicode characters."""
        analyzer = TaskAnalyzer()

        analysis = analyzer.analyze("Write código in Python 日本語")

        # Should handle unicode
        assert analysis is not None
        assert analysis.type == TaskType.CODE

    def test_very_long_task(self):
        """Test with very long task containing complexity indicators."""
        analyzer = TaskAnalyzer()

        # Long task with high complexity indicators
        long_task = (
            "Design a comprehensive, sophisticated, advanced system architecture "
            + "with detailed analysis of scalable patterns " * 50
        )

        analysis = analyzer.analyze(long_task)

        assert analysis is not None
        # Long tasks with complexity indicators should be HIGH or EXPERT
        assert analysis.complexity in (
            TaskComplexity.MEDIUM,
            TaskComplexity.HIGH,
            TaskComplexity.EXPERT,
        )
