"""
Unit tests for A2A Agent Cards functionality.
"""

import pytest
from datetime import datetime

from kailash.nodes.ai.a2a import (
    A2AAgentCard,
    Capability,
    CapabilityLevel,
    CollaborationStyle,
    PerformanceMetrics,
    ResourceRequirements,
    create_coding_agent_card,
    create_qa_agent_card,
    create_research_agent_card,
)


class TestCapability:
    """Test the Capability class."""
    
    def test_capability_creation(self):
        """Test creating a capability."""
        cap = Capability(
            name="data_analysis",
            domain="research",
            level=CapabilityLevel.EXPERT,
            description="Expert at analyzing complex datasets",
            keywords=["analysis", "statistics", "patterns"],
            examples=["sales analysis", "trend detection"],
            constraints=["requires structured data"],
        )
        
        assert cap.name == "data_analysis"
        assert cap.domain == "research"
        assert cap.level == CapabilityLevel.EXPERT
        assert len(cap.keywords) == 3
        assert len(cap.examples) == 2
        assert len(cap.constraints) == 1
    
    def test_capability_matching(self):
        """Test capability requirement matching."""
        cap = Capability(
            name="data_analysis",
            domain="research",
            level=CapabilityLevel.EXPERT,
            description="Expert at analyzing complex datasets",
            keywords=["analysis", "statistics", "patterns", "trends"],
        )
        
        # Direct name match
        assert cap.matches_requirement("Need data_analysis expert") >= 0.9
        
        # Domain match
        assert cap.matches_requirement("Research specialist required") >= 0.7
        
        # Keyword matches
        assert cap.matches_requirement("Looking for statistics expert") >= 0.6
        assert cap.matches_requirement("Need patterns and trends analysis") >= 0.7
        
        # Description overlap
        assert cap.matches_requirement("Someone who can work with complex datasets") >= 0.3
        
        # No match
        assert cap.matches_requirement("Need a chef") == 0.0


class TestPerformanceMetrics:
    """Test the PerformanceMetrics class."""
    
    def test_performance_metrics_defaults(self):
        """Test default performance metrics."""
        metrics = PerformanceMetrics()
        
        assert metrics.total_tasks == 0
        assert metrics.successful_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.success_rate == 0.0
        assert metrics.insight_quality_score == 0.0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = PerformanceMetrics(
            total_tasks=100,
            successful_tasks=85,
            failed_tasks=15,
        )
        
        assert metrics.success_rate == 0.85
    
    def test_insight_quality_score(self):
        """Test insight quality score calculation."""
        metrics = PerformanceMetrics(
            insights_generated=100,
            unique_insights=80,
            actionable_insights=60,
            average_insight_quality=0.7,
        )
        
        # 0.7 * 0.4 + (80/100) * 0.3 + (60/100) * 0.3
        # = 0.28 + 0.24 + 0.18 = 0.70
        assert metrics.insight_quality_score == pytest.approx(0.70, rel=0.01)
    
    def test_empty_insights_handling(self):
        """Test handling when no insights generated."""
        metrics = PerformanceMetrics(
            insights_generated=0,
            average_insight_quality=0.8,
        )
        
        assert metrics.insight_quality_score == 0.0


class TestA2AAgentCard:
    """Test the A2AAgentCard class."""
    
    def test_agent_card_creation(self):
        """Test creating an agent card."""
        card = A2AAgentCard(
            agent_id="agent_001",
            agent_name="Research Agent",
            agent_type="research",
            version="1.0.0",
            description="Specialized research agent",
            tags=["research", "analysis"],
        )
        
        assert card.agent_id == "agent_001"
        assert card.agent_name == "Research Agent"
        assert card.agent_type == "research"
        assert card.version == "1.0.0"
        assert len(card.tags) == 2
        assert card.collaboration_style == CollaborationStyle.COOPERATIVE
    
    def test_agent_card_serialization(self):
        """Test agent card to_dict and from_dict."""
        original = create_research_agent_card("agent_001", "Research Bot")
        
        # Serialize
        data = original.to_dict()
        assert data["agent_id"] == "agent_001"
        assert data["agent_name"] == "Research Bot"
        assert len(data["primary_capabilities"]) > 0
        
        # Deserialize
        restored = A2AAgentCard.from_dict(data)
        assert restored.agent_id == original.agent_id
        assert restored.agent_name == original.agent_name
        assert len(restored.primary_capabilities) == len(original.primary_capabilities)
    
    def test_match_score_calculation(self):
        """Test agent matching score calculation."""
        card = create_coding_agent_card("coder_001", "Code Master")
        
        # Strong match
        high_score = card.calculate_match_score([
            "Need code generation",
            "Python implementation required",
            "Must debug complex issues"
        ])
        assert high_score > 0.4  # Reasonable match based on keyword and description overlap
        
        # Weak match
        low_score = card.calculate_match_score([
            "Need market research",
            "Financial analysis",
            "Report writing"
        ])
        assert low_score < 0.3
        
        # No requirements
        neutral_score = card.calculate_match_score([])
        assert neutral_score == 0.5
    
    def test_compatibility_check(self):
        """Test agent compatibility checking."""
        card = A2AAgentCard(
            agent_id="agent_001",
            agent_name="Agent 1",
            agent_type="generic",
            version="1.0.0",
            incompatible_agents=["agent_002", "agent_003"],
        )
        
        assert card.is_compatible_with("agent_004") == True
        assert card.is_compatible_with("agent_002") == False
        assert card.is_compatible_with("agent_003") == False
    
    def test_performance_update(self):
        """Test updating performance metrics."""
        card = create_qa_agent_card("qa_001", "Test Master")
        
        # Initial state
        assert card.performance.total_tasks == 0
        
        # Successful task
        card.update_performance({
            "success": True,
            "response_time_ms": 150,
            "insights": [
                {"key": "bug1", "actionable": True},
                {"key": "bug2", "actionable": True},
                {"key": "observation1", "actionable": False},
            ],
            "quality_score": 0.9,
        })
        
        assert card.performance.total_tasks == 1
        assert card.performance.successful_tasks == 1
        assert card.performance.insights_generated == 3
        assert card.performance.actionable_insights == 2
        assert card.performance.average_response_time_ms == pytest.approx(15.0, rel=0.001)  # 0.1 * 150
        assert card.performance.average_insight_quality == pytest.approx(0.09, rel=0.001)  # 0.1 * 0.9
        
        # Failed task
        card.update_performance({
            "success": False,
        })
        
        assert card.performance.total_tasks == 2
        assert card.performance.successful_tasks == 1
        assert card.performance.failed_tasks == 1


class TestFactoryFunctions:
    """Test the agent card factory functions."""
    
    def test_create_research_agent(self):
        """Test creating a research agent card."""
        card = create_research_agent_card("res_001", "Research Bot")
        
        assert card.agent_id == "res_001"
        assert card.agent_name == "Research Bot"
        assert card.agent_type == "research"
        assert card.collaboration_style == CollaborationStyle.COOPERATIVE
        assert len(card.primary_capabilities) >= 2
        assert any(cap.name == "information_retrieval" for cap in card.primary_capabilities)
        assert "research" in card.tags
    
    def test_create_coding_agent(self):
        """Test creating a coding agent card."""
        card = create_coding_agent_card("code_001", "Code Master")
        
        assert card.agent_id == "code_001"
        assert card.agent_name == "Code Master"
        assert card.agent_type == "coding"
        assert card.collaboration_style == CollaborationStyle.INDEPENDENT
        assert len(card.primary_capabilities) >= 2
        assert any(cap.name == "code_generation" for cap in card.primary_capabilities)
        assert "coding" in card.tags
    
    def test_create_qa_agent(self):
        """Test creating a QA agent card."""
        card = create_qa_agent_card("qa_001", "Test Expert")
        
        assert card.agent_id == "qa_001"
        assert card.agent_name == "Test Expert"
        assert card.agent_type == "qa_testing"
        assert card.collaboration_style == CollaborationStyle.SUPPORT
        assert len(card.primary_capabilities) >= 2
        assert any(cap.name == "test_design" for cap in card.primary_capabilities)
        assert "qa" in card.tags


class TestMatchScoreEdgeCases:
    """Test edge cases in match score calculation."""
    
    def test_performance_modifier_impact(self):
        """Test how performance history affects match scores."""
        card = create_research_agent_card("res_001", "Researcher")
        
        # Set up good performance history
        card.performance.total_tasks = 50
        card.performance.successful_tasks = 45  # 90% success rate
        card.performance.average_insight_quality = 0.8
        card.performance.insights_generated = 200
        card.performance.unique_insights = 180
        card.performance.actionable_insights = 150
        
        # Same requirements, but now with performance history
        score_with_history = card.calculate_match_score([
            "Need research and analysis"
        ])
        
        # Create identical card without history
        fresh_card = create_research_agent_card("res_002", "Researcher")
        score_without_history = fresh_card.calculate_match_score([
            "Need research and analysis"
        ])
        
        # Score with good history should be higher
        assert score_with_history > score_without_history
    
    def test_collaboration_style_in_teams(self):
        """Test how collaboration style affects matching."""
        coop_agent = A2AAgentCard(
            agent_id="coop_001",
            agent_name="Cooperative Agent",
            agent_type="generic",
            version="1.0.0",
            collaboration_style=CollaborationStyle.COOPERATIVE,
        )
        
        solo_agent = A2AAgentCard(
            agent_id="solo_001",
            agent_name="Solo Agent",
            agent_type="generic",
            version="1.0.0",
            collaboration_style=CollaborationStyle.INDEPENDENT,
        )
        
        # In team context, cooperative agents should be preferred
        # This would be tested in the coordinator tests
        assert coop_agent.collaboration_style == CollaborationStyle.COOPERATIVE
        assert solo_agent.collaboration_style == CollaborationStyle.INDEPENDENT