"""
Unit tests for A2A Task Management functionality.
"""

import pytest
from datetime import datetime

from kailash.nodes.ai.a2a import (
    A2ATask,
    Insight,
    InsightType,
    TaskIteration,
    TaskPriority,
    TaskState,
    TaskValidator,
    create_implementation_task,
    create_research_task,
    create_validation_task,
)


class TestA2ATask:
    """Test the A2ATask class."""
    
    def test_task_creation(self):
        """Test creating a task."""
        task = A2ATask(
            name="Test Task",
            description="A test task",
            requirements=["requirement1", "requirement2"],
            priority=TaskPriority.HIGH,
        )
        
        assert task.name == "Test Task"
        assert task.description == "A test task"
        assert len(task.requirements) == 2
        assert task.priority == TaskPriority.HIGH
        assert task.state == TaskState.CREATED
        assert task.task_id is not None
    
    def test_task_state_transitions(self):
        """Test valid task state transitions."""
        task = A2ATask(name="Test")
        
        # Valid transitions
        assert task.transition_to(TaskState.ASSIGNED) == True
        assert task.state == TaskState.ASSIGNED
        assert task.assigned_at is not None
        
        assert task.transition_to(TaskState.IN_PROGRESS) == True
        assert task.state == TaskState.IN_PROGRESS
        assert task.started_at is not None
        
        assert task.transition_to(TaskState.AWAITING_REVIEW) == True
        assert task.state == TaskState.AWAITING_REVIEW
        
        assert task.transition_to(TaskState.COMPLETED) == True
        assert task.state == TaskState.COMPLETED
        assert task.completed_at is not None
    
    def test_invalid_state_transitions(self):
        """Test invalid task state transitions."""
        task = A2ATask(name="Test")
        
        # Cannot go directly from CREATED to IN_PROGRESS
        assert task.transition_to(TaskState.IN_PROGRESS) == False
        assert task.state == TaskState.CREATED
        
        # Cannot go from COMPLETED to anything
        task.state = TaskState.COMPLETED
        assert task.transition_to(TaskState.IN_PROGRESS) == False
        assert task.state == TaskState.COMPLETED
    
    def test_add_insight(self):
        """Test adding insights to a task."""
        task = A2ATask(name="Test")
        
        insight = Insight(
            content="Test insight",
            confidence=0.8,
            novelty_score=0.7,
            actionability_score=0.9,
            impact_score=0.6,
        )
        
        task.add_insight(insight)
        
        assert len(task.insights) == 1
        assert task.insights[0].content == "Test insight"
        assert task.current_quality_score > 0
    
    def test_quality_score_calculation(self):
        """Test task quality score calculation."""
        task = A2ATask(name="Test", target_quality_score=0.8)
        
        # Add high-quality insights
        for i in range(3):
            insight = Insight(
                content=f"Insight {i}",
                confidence=0.9,
                novelty_score=0.8,
                actionability_score=0.85,
                impact_score=0.7,
            )
            task.add_insight(insight)
        
        # Should have high quality score
        assert task.current_quality_score > 0.7
        
        # Add duplicate insight (affects uniqueness)
        duplicate = Insight(
            content="Insight 0",  # Same content as first
            confidence=0.9,
            novelty_score=0.8,
            actionability_score=0.85,
            impact_score=0.7,
        )
        task.add_insight(duplicate)
        
        # Quality should decrease slightly due to reduced uniqueness
        prev_score = task.current_quality_score
        task._update_quality_score()
        assert task.current_quality_score <= prev_score
    
    def test_task_iteration(self):
        """Test task iteration functionality."""
        task = A2ATask(name="Test", max_iterations=3)
        task.state = TaskState.AWAITING_REVIEW
        task.target_quality_score = 0.9
        task.current_quality_score = 0.6
        
        # Should need iteration
        assert task.needs_iteration == True
        
        # Start iteration
        iteration = task.start_iteration(
            reason="Quality below target",
            adjustments=["Increase depth", "Add more sources"]
        )
        
        assert task.current_iteration == 1
        assert task.state == TaskState.ITERATING
        assert len(task.iterations) == 1
        
        # Complete iteration
        new_insights = [
            Insight(content="Better insight 1", confidence=0.9),
            Insight(content="Better insight 2", confidence=0.85),
        ]
        
        task.complete_iteration(
            insights=new_insights,
            agents_involved=["agent1", "agent2"],
            consensus_score=0.8
        )
        
        assert task.state == TaskState.IN_PROGRESS
        assert len(task.insights) == 2
        assert task.iterations[0].completed_at is not None
    
    def test_task_duration(self):
        """Test task duration calculation."""
        task = A2ATask(name="Test")
        
        # No duration if not started
        assert task.duration is None
        
        # Start task
        task.started_at = datetime.now()
        
        # Should have duration
        import time
        time.sleep(0.1)
        assert task.duration > 0
        
        # Complete task
        task.completed_at = datetime.now()
        final_duration = task.duration
        
        # Duration should be fixed after completion
        time.sleep(0.1)
        assert task.duration == final_duration
    
    def test_task_serialization(self):
        """Test task to_dict and from_dict."""
        original = A2ATask(
            name="Test Task",
            description="Description",
            requirements=["req1", "req2"],
            priority=TaskPriority.HIGH,
        )
        
        # Add some insights
        original.add_insight(Insight(content="Insight 1"))
        original.add_insight(Insight(content="Insight 2"))
        
        # Serialize
        data = original.to_dict()
        assert data["name"] == "Test Task"
        assert data["priority"] == "high"
        assert len(data["insights"]) == 2
        
        # Deserialize
        restored = A2ATask.from_dict(data)
        assert restored.name == original.name
        assert restored.task_id == original.task_id
        assert len(restored.insights) == 2
    
    def test_legacy_task_compatibility(self):
        """Test backward compatibility with dictionary tasks."""
        legacy_data = {
            "title": "Legacy Task",
            "description": "Old format task",
            "requirements": ["skill1", "skill2"],
        }
        
        task = A2ATask.from_dict(legacy_data)
        assert task.name == "Legacy Task"
        assert task.description == "Old format task"
        assert len(task.requirements) == 2
        assert task.context == legacy_data


class TestInsight:
    """Test the Insight class."""
    
    def test_insight_creation(self):
        """Test creating an insight."""
        insight = Insight(
            content="Test insight",
            insight_type=InsightType.DISCOVERY,
            confidence=0.8,
            novelty_score=0.7,
            actionability_score=0.9,
            impact_score=0.6,
            generated_by="agent1",
            keywords=["test", "discovery"],
        )
        
        assert insight.content == "Test insight"
        assert insight.insight_type == InsightType.DISCOVERY
        assert insight.confidence == 0.8
        assert len(insight.keywords) == 2
    
    def test_insight_quality_score(self):
        """Test insight quality score calculation."""
        insight = Insight(
            confidence=0.8,
            novelty_score=0.7,
            actionability_score=0.9,
            impact_score=0.6,
        )
        
        # Quality = 0.8*0.3 + 0.7*0.3 + 0.9*0.3 + 0.6*0.1
        # = 0.24 + 0.21 + 0.27 + 0.06 = 0.78
        assert insight.quality_score == pytest.approx(0.78, rel=0.01)
    
    def test_insight_relationships(self):
        """Test insight relationship tracking."""
        insight1 = Insight(content="Base insight")
        insight2 = Insight(
            content="Derived insight",
            builds_on=[insight1.insight_id],
        )
        insight3 = Insight(
            content="Contradictory insight",
            contradicts=[insight1.insight_id],
        )
        
        assert len(insight2.builds_on) == 1
        assert insight1.insight_id in insight2.builds_on
        assert len(insight3.contradicts) == 1
        assert insight1.insight_id in insight3.contradicts


class TestTaskValidator:
    """Test the TaskValidator class."""
    
    def test_validate_for_assignment(self):
        """Test task validation for assignment."""
        # Valid task
        task = A2ATask(
            name="Valid Task",
            description="Has all required fields",
            requirements=["req1"],
            state=TaskState.CREATED,
        )
        
        is_valid, issues = TaskValidator.validate_for_assignment(task)
        assert is_valid == True
        assert len(issues) == 0
        
        # Invalid task - no name
        task_no_name = A2ATask(
            description="Missing name",
            requirements=["req1"],
        )
        
        is_valid, issues = TaskValidator.validate_for_assignment(task_no_name)
        assert is_valid == False
        assert "name" in issues[0]
        
        # Invalid task - wrong state
        task_wrong_state = A2ATask(
            name="Task",
            description="Wrong state",
            requirements=["req1"],
            state=TaskState.IN_PROGRESS,
        )
        
        is_valid, issues = TaskValidator.validate_for_assignment(task_wrong_state)
        assert is_valid == False
        assert "CREATED state" in issues[0]
    
    def test_validate_for_completion(self):
        """Test task validation for completion."""
        # Valid task
        task = A2ATask(
            name="Task",
            state=TaskState.AWAITING_REVIEW,
            target_quality_score=0.8,
        )
        
        # Add insights to meet quality
        for i in range(3):
            task.add_insight(Insight(
                content=f"Insight {i}",
                confidence=0.9,
                novelty_score=0.8,
                actionability_score=0.85,
            ))
        
        is_valid, issues = TaskValidator.validate_for_completion(task)
        assert is_valid == True
        assert len(issues) == 0
        
        # Invalid - no insights
        task_no_insights = A2ATask(
            name="Task",
            state=TaskState.AWAITING_REVIEW,
        )
        
        is_valid, issues = TaskValidator.validate_for_completion(task_no_insights)
        assert is_valid == False
        assert "at least one insight" in issues[0]


class TestTaskFactoryFunctions:
    """Test the task factory functions."""
    
    def test_create_research_task(self):
        """Test creating a research task."""
        task = create_research_task(
            name="Research AI impacts",
            description="Study AI impact on productivity",
            requirements=["literature review", "data analysis"],
            priority=TaskPriority.HIGH,
        )
        
        assert task.name == "Research AI impacts"
        assert task.priority == TaskPriority.HIGH
        assert "research" in task.tags
        assert task.target_quality_score == 0.85
        assert task.max_iterations == 3
    
    def test_create_implementation_task(self):
        """Test creating an implementation task."""
        task = create_implementation_task(
            name="Implement feature X",
            description="Add new feature",
            requirements=["python", "api design"],
        )
        
        assert task.priority == TaskPriority.HIGH  # Default for implementation
        assert "implementation" in task.tags
        assert task.target_quality_score == 0.90
        assert task.max_iterations == 2
    
    def test_create_validation_task(self):
        """Test creating a validation task."""
        parent_id = "parent-123"
        task = create_validation_task(
            name="Validate feature X",
            description="Test the implementation",
            requirements=["testing", "qa"],
            parent_task_id=parent_id,
        )
        
        assert task.parent_task_id == parent_id
        assert task.priority == TaskPriority.HIGH
        assert "validation" in task.tags
        assert task.target_quality_score == 0.95
        assert task.max_iterations == 1