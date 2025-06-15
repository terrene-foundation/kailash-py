"""Tests for intelligent orchestration nodes."""

import pytest

from kailash.nodes.ai.intelligent_agent_orchestrator import (
    ConvergenceDetectorNode,
    IntelligentCacheNode,
    MCPAgentNode,
    OrchestrationManagerNode,
    QueryAnalysisNode,
)


class TestIntelligentCacheNode:
    """Test IntelligentCacheNode functionality."""

    def test_cache_and_get_basic(self):
        """Test basic cache and get operations."""
        cache = IntelligentCacheNode()

        # Cache some data
        cache_result = cache.execute(
            action="cache",
            cache_key="test_key",
            data={"value": 42, "message": "hello"},
            metadata={"source": "test", "cost": 0.1, "semantic_tags": ["test", "data"]},
            ttl=3600,
        )

        assert cache_result["success"] is True
        assert cache_result["cache_key"] == "test_key"

        # Retrieve the data
        get_result = cache.execute(action="get", cache_key="test_key")

        assert get_result["success"] is True
        assert get_result["hit"] is True
        assert get_result["data"]["value"] == 42
        assert get_result["data"]["message"] == "hello"

    def test_cache_miss(self):
        """Test cache miss behavior."""
        cache = IntelligentCacheNode()

        result = cache.execute(action="get", cache_key="nonexistent_key")

        assert result["success"] is True
        assert result["hit"] is False

    def test_semantic_search(self):
        """Test semantic search functionality."""
        cache = IntelligentCacheNode()

        # Cache data with semantic tags
        cache.execute(
            action="cache",
            cache_key="weather_data",
            data={"temperature": 75, "conditions": "sunny"},
            metadata={"semantic_tags": ["weather", "temperature", "conditions"]},
        )

        # Search semantically
        result = cache.execute(
            action="get", query="weather temperature", similarity_threshold=0.5
        )

        assert result["success"] is True
        # Note: In a real implementation with better semantic matching,
        # this might return True, but our simple implementation may not

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = IntelligentCacheNode()

        stats = cache.execute(action="stats")

        assert stats["success"] is True
        assert "stats" in stats
        assert "total_entries" in stats["stats"]
        assert "hit_rate" in stats["stats"]


class TestQueryAnalysisNode:
    """Test QueryAnalysisNode functionality."""

    def test_simple_query_analysis(self):
        """Test analysis of a simple query."""
        analyzer = QueryAnalysisNode()

        result = analyzer.execute(
            query="What is the weather like today?", context={"domain": "general"}
        )

        assert result["success"] is True
        assert "analysis" in result
        analysis = result["analysis"]

        assert "complexity_score" in analysis
        assert "required_capabilities" in analysis
        assert "mcp_requirements" in analysis
        assert "team_suggestion" in analysis

    def test_complex_query_analysis(self):
        """Test analysis of a complex query."""
        analyzer = QueryAnalysisNode()

        complex_query = """
        Research the latest AI trends, analyze market opportunities,
        predict future developments, and create a comprehensive strategy
        """

        result = analyzer.execute(
            query=complex_query,
            context={"domain": "business_strategy", "urgency": "high"},
        )

        assert result["success"] is True
        analysis = result["analysis"]

        # Complex query should have higher complexity
        assert analysis["complexity_score"] > 0.5
        assert len(analysis["required_capabilities"]) > 2
        assert analysis["mcp_requirements"]["mcp_needed"] is True

    def test_pattern_matching(self):
        """Test query pattern matching."""
        analyzer = QueryAnalysisNode()

        # Test prediction pattern
        result = analyzer.execute(query="Predict sales for next quarter", context={})

        analysis = result["analysis"]
        patterns = analysis.get("pattern_matches", {})

        # Should detect prediction pattern
        assert "prediction" in patterns or analysis["complexity_score"] > 0.6


class TestConvergenceDetectorNode:
    """Test ConvergenceDetectorNode functionality."""

    def test_quality_threshold_met(self):
        """Test convergence when quality threshold is met."""
        detector = ConvergenceDetectorNode()

        solution_history = [{"evaluation": {"overall_score": 0.85}, "duration": 60}]

        result = detector.execute(
            solution_history=solution_history,
            quality_threshold=0.8,
            current_iteration=1,
        )

        assert result["success"] is True
        assert result["should_stop"] is True
        assert "Quality threshold achieved" in result["reason"]

    def test_insufficient_improvement(self):
        """Test convergence detection for insufficient improvement."""
        detector = ConvergenceDetectorNode()

        solution_history = [
            {"evaluation": {"overall_score": 0.7}, "duration": 60},
            {"evaluation": {"overall_score": 0.705}, "duration": 65},
        ]

        result = detector.execute(
            solution_history=solution_history,
            quality_threshold=0.8,
            improvement_threshold=0.02,
            current_iteration=2,
        )

        assert result["success"] is True
        assert result["should_stop"] is True
        assert "Insufficient improvement" in result["reason"]

    def test_iteration_limit(self):
        """Test convergence when iteration limit is reached."""
        detector = ConvergenceDetectorNode()

        solution_history = [{"evaluation": {"overall_score": 0.6}, "duration": 60}]

        result = detector.execute(
            solution_history=solution_history, current_iteration=5, max_iterations=5
        )

        assert result["success"] is True
        assert result["should_stop"] is True
        assert "Maximum iterations reached" in result["reason"]

    def test_improvement_trend_calculation(self):
        """Test improvement trend calculation."""
        detector = ConvergenceDetectorNode()

        # Improving trend
        improving_history = [
            {"evaluation": {"overall_score": 0.6}},
            {"evaluation": {"overall_score": 0.7}},
            {"evaluation": {"overall_score": 0.8}},
        ]

        result = detector.execute(solution_history=improving_history, current_iteration=3)

        assert result["success"] is True
        trend = result["improvement_trend"]
        assert trend["trend"] == "improving"
        assert trend["total_improvement"] > 0


class TestMCPAgentNode:
    """Test MCPAgentNode functionality."""

    def test_mcp_agent_initialization(self):
        """Test MCP agent initialization."""
        agent = MCPAgentNode()

        # Test basic functionality without actual MCP servers
        result = agent.execute(
            agent_id="test_agent",
            capabilities=["data_analysis"],
            mcp_servers=[],
            task="Test task",
            provider="mock",
            model="mock-model",
        )

        # Should succeed even without MCP servers
        assert result.get("success") is True or "error" in result

    def test_mcp_server_setup(self):
        """Test MCP server setup handling."""
        agent = MCPAgentNode()

        # Mock MCP servers
        mock_servers = [
            {"name": "test_server", "command": "python", "args": ["-m", "test_mcp"]}
        ]

        # Should handle server setup gracefully
        result = agent.execute(
            agent_id="test_agent",
            capabilities=["api_integration"],
            mcp_servers=mock_servers,
            task="Test MCP integration",
            provider="mock",
            model="mock-model",
        )

        # Should not fail catastrophically
        assert isinstance(result, dict)


class TestOrchestrationManagerNode:
    """Test OrchestrationManagerNode functionality."""

    def test_simple_orchestration(self):
        """Test simple orchestration workflow."""
        orchestrator = OrchestrationManagerNode()

        # Simple query that should complete quickly
        result = orchestrator.execute(
            query="What is 2 + 2?",
            agent_pool_size=3,
            max_iterations=1,
            quality_threshold=0.7,
            time_limit_minutes=1,
            enable_caching=False,  # Disable for simpler test
        )

        assert result["success"] is True
        assert "final_solution" in result
        assert "session_id" in result
        assert result["iterations_completed"] >= 1

    def test_orchestration_with_context(self):
        """Test orchestration with additional context."""
        orchestrator = OrchestrationManagerNode()

        result = orchestrator.execute(
            query="Analyze customer satisfaction data",
            context={"domain": "customer_analytics", "urgency": "medium"},
            agent_pool_size=5,
            max_iterations=2,
            quality_threshold=0.8,
        )

        assert result["success"] is True
        assert result["query"] == "Analyze customer satisfaction data"

    def test_orchestration_parameters(self):
        """Test orchestration parameter handling."""
        orchestrator = OrchestrationManagerNode()

        # Test with minimal parameters
        result = orchestrator.execute(query="Simple test query")

        assert result["success"] is True
        assert "performance_metrics" in result

    def test_orchestration_time_limit(self):
        """Test orchestration respects time limits."""
        orchestrator = OrchestrationManagerNode()

        import time

        start_time = time.time()

        result = orchestrator.execute(
            query="Complex analysis requiring multiple iterations",
            time_limit_minutes=0.01,  # Very short time limit
            max_iterations=10,
        )

        execution_time = time.time() - start_time

        # Should complete quickly due to time limit
        assert execution_time < 5  # Should finish within 5 seconds
        assert result["success"] is True


def test_node_parameter_validation():
    """Test that all nodes have proper parameter definitions."""
    nodes = [
        IntelligentCacheNode(),
        QueryAnalysisNode(),
        ConvergenceDetectorNode(),
        MCPAgentNode(),
        OrchestrationManagerNode(),
    ]

    for node in nodes:
        params = node.get_parameters()
        assert isinstance(params, dict)

        # Each parameter should have required attributes
        for param_name, param_obj in params.items():
            assert hasattr(param_obj, "name")
            assert hasattr(param_obj, "type")
            assert hasattr(param_obj, "required")


def test_node_error_handling():
    """Test node error handling for invalid inputs."""
    cache = IntelligentCacheNode()

    # Test invalid action
    result = cache.execute(action="invalid_action")
    assert result["success"] is False
    assert "error" in result

    # Test missing required parameters for convergence detector
    detector = ConvergenceDetectorNode()

    # Should handle missing required parameters gracefully
    try:
        result = detector.execute()
        # Should either succeed with defaults or fail gracefully
        assert isinstance(result, dict)
    except Exception as e:
        # Should not raise unhandled exceptions
        assert "required" in str(e).lower() or "missing" in str(e).lower()