"""Agent-to-Agent (A2A) communication nodes with shared memory pools.

This module implements multi-agent communication with selective attention mechanisms,
enabling efficient collaboration between AI agents while preventing information overload.

Design Philosophy:
    The A2A system enables decentralized multi-agent collaboration through shared
    memory pools and attention mechanisms. Agents can share insights, coordinate
    tasks, and build collective intelligence without centralized control.
"""

import json
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from kaizen.nodes.ai.llm_agent import LLMAgentNode

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_cycle_aware import CycleAwareNode

# ============================================================================
# ENHANCED A2A COMPONENTS: Agent Cards and Task Management
# ============================================================================


class CapabilityLevel(Enum):
    """Agent capability proficiency levels."""

    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class CollaborationStyle(Enum):
    """Agent collaboration preferences."""

    INDEPENDENT = "independent"  # Prefers solo work
    COOPERATIVE = "cooperative"  # Works well in teams
    LEADER = "leader"  # Takes charge of coordination
    SUPPORT = "support"  # Provides assistance to others


class TaskState(Enum):
    """Task lifecycle states."""

    CREATED = "created"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    ITERATING = "iterating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InsightType(Enum):
    """Types of insights that can be generated."""

    DISCOVERY = "discovery"  # New finding
    ANALYSIS = "analysis"  # Deep analysis result
    RECOMMENDATION = "recommendation"  # Actionable recommendation
    WARNING = "warning"  # Potential issue
    OPPORTUNITY = "opportunity"  # Improvement opportunity
    PATTERN = "pattern"  # Identified pattern
    ANOMALY = "anomaly"  # Unusual finding


@dataclass
class Capability:
    """Detailed capability description."""

    name: str
    domain: str
    level: CapabilityLevel
    description: str
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)

    def matches_requirement(self, requirement: str) -> float:
        """Calculate match score for a requirement (0.0-1.0)."""
        requirement_lower = requirement.lower()

        # Direct name match
        if self.name.lower() in requirement_lower:
            return 0.9

        # Domain match
        if self.domain.lower() in requirement_lower:
            return 0.7

        # Keyword matches
        keyword_matches = sum(
            1 for keyword in self.keywords if keyword.lower() in requirement_lower
        )
        if keyword_matches > 0:
            return min(0.6 + (keyword_matches * 0.1), 0.8)

        # Description similarity
        desc_words = set(self.description.lower().split())
        req_words = set(requirement_lower.split())
        overlap = len(desc_words & req_words)
        if overlap > 0:
            return min(0.3 + (overlap * 0.05), 0.5)

        return 0.0


@dataclass
class PerformanceMetrics:
    """Agent performance tracking."""

    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0

    average_response_time_ms: float = 0.0
    average_insight_quality: float = 0.0
    average_confidence_score: float = 0.0

    insights_generated: int = 0
    unique_insights: int = 0
    actionable_insights: int = 0

    collaboration_score: float = 0.0
    reliability_score: float = 0.0

    last_active: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate task success rate."""
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks

    @property
    def insight_quality_score(self) -> float:
        """Calculate overall insight quality score."""
        if self.insights_generated == 0:
            return 0.0

        uniqueness = self.unique_insights / self.insights_generated
        actionability = self.actionable_insights / self.insights_generated

        return (
            self.average_insight_quality * 0.4 + uniqueness * 0.3 + actionability * 0.3
        )


@dataclass
class ResourceRequirements:
    """Agent resource constraints and requirements."""

    min_memory_mb: int = 512
    max_memory_mb: int = 4096

    min_tokens: int = 100
    max_tokens: int = 4000

    requires_gpu: bool = False
    requires_internet: bool = True

    estimated_cost_per_task: float = 0.0
    max_concurrent_tasks: int = 5

    supported_models: List[str] = field(default_factory=list)
    required_apis: List[str] = field(default_factory=list)


@dataclass
class A2AAgentCard:
    """
    Enhanced agent card for rich capability description.

    Provides comprehensive agent metadata for optimal matching,
    team formation, and performance tracking.
    """

    # Identity
    agent_id: str
    agent_name: str
    agent_type: str
    version: str

    # Capabilities
    primary_capabilities: List[Capability] = field(default_factory=list)
    secondary_capabilities: List[Capability] = field(default_factory=list)
    emerging_capabilities: List[Capability] = field(default_factory=list)

    # Collaboration
    collaboration_style: CollaborationStyle = CollaborationStyle.COOPERATIVE
    preferred_team_size: int = 3
    compatible_agents: List[str] = field(default_factory=list)
    incompatible_agents: List[str] = field(default_factory=list)

    # Performance
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)

    # Resources
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Specializations
    specializations: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "version": self.version,
            "primary_capabilities": [
                {
                    "name": cap.name,
                    "domain": cap.domain,
                    "level": cap.level.value,
                    "description": cap.description,
                    "keywords": cap.keywords,
                }
                for cap in self.primary_capabilities
            ],
            "secondary_capabilities": [
                {
                    "name": cap.name,
                    "domain": cap.domain,
                    "level": cap.level.value,
                    "description": cap.description,
                }
                for cap in self.secondary_capabilities
            ],
            "collaboration_style": self.collaboration_style.value,
            "performance": {
                "success_rate": self.performance.success_rate,
                "insight_quality_score": self.performance.insight_quality_score,
                "average_response_time_ms": self.performance.average_response_time_ms,
                "reliability_score": self.performance.reliability_score,
            },
            "resources": {
                "max_tokens": self.resources.max_tokens,
                "requires_gpu": self.resources.requires_gpu,
                "estimated_cost_per_task": self.resources.estimated_cost_per_task,
            },
            "tags": self.tags,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2AAgentCard":
        """Create from dictionary."""
        # Convert capability dictionaries back to objects
        primary_caps = [
            Capability(
                name=cap["name"],
                domain=cap["domain"],
                level=CapabilityLevel(cap["level"]),
                description=cap.get("description", ""),
                keywords=cap.get("keywords", []),
            )
            for cap in data.get("primary_capabilities", [])
        ]

        secondary_caps = [
            Capability(
                name=cap["name"],
                domain=cap["domain"],
                level=CapabilityLevel(cap["level"]),
                description=cap.get("description", ""),
            )
            for cap in data.get("secondary_capabilities", [])
        ]

        # Create performance metrics
        perf_data = data.get("performance", {})
        performance = PerformanceMetrics()
        if perf_data:
            performance.average_insight_quality = perf_data.get(
                "insight_quality_score", 0.0
            )
            performance.average_response_time_ms = perf_data.get(
                "average_response_time_ms", 0.0
            )
            performance.reliability_score = perf_data.get("reliability_score", 0.0)

        # Create resource requirements
        res_data = data.get("resources", {})
        resources = ResourceRequirements()
        if res_data:
            resources.max_tokens = res_data.get("max_tokens", 4000)
            resources.requires_gpu = res_data.get("requires_gpu", False)
            resources.estimated_cost_per_task = res_data.get(
                "estimated_cost_per_task", 0.0
            )

        return cls(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            agent_type=data["agent_type"],
            version=data.get("version", "1.0.0"),
            primary_capabilities=primary_caps,
            secondary_capabilities=secondary_caps,
            collaboration_style=CollaborationStyle(
                data.get("collaboration_style", "cooperative")
            ),
            performance=performance,
            resources=resources,
            tags=data.get("tags", []),
            description=data.get("description", ""),
        )

    def calculate_match_score(self, requirements: List[str]) -> float:
        """
        Calculate how well this agent matches given requirements.

        Returns a score between 0.0 and 1.0.
        """
        if not requirements:
            return 0.5  # Neutral score for no requirements

        total_score = 0.0

        for requirement in requirements:
            # Check primary capabilities (highest weight)
            primary_scores = [
                cap.matches_requirement(requirement) * 1.0
                for cap in self.primary_capabilities
            ]

            # Check secondary capabilities (medium weight)
            secondary_scores = [
                cap.matches_requirement(requirement) * 0.7
                for cap in self.secondary_capabilities
            ]

            # Check emerging capabilities (lower weight)
            emerging_scores = [
                cap.matches_requirement(requirement) * 0.4
                for cap in self.emerging_capabilities
            ]

            # Take the best match for this requirement
            all_scores = primary_scores + secondary_scores + emerging_scores
            best_score = max(all_scores) if all_scores else 0.0
            total_score += best_score

        # Average across all requirements
        avg_score = total_score / len(requirements)

        # Apply performance modifier
        performance_modifier = (
            self.performance.success_rate * 0.3
            + self.performance.insight_quality_score * 0.7
        )

        # Weighted final score
        final_score = avg_score * 0.7 + performance_modifier * 0.3

        return min(max(final_score, 0.0), 1.0)

    def is_compatible_with(self, other_agent_id: str) -> bool:
        """Check if compatible with another agent."""
        if other_agent_id in self.incompatible_agents:
            return False

        # Could add more sophisticated compatibility logic here
        return True

    def update_performance(self, task_result: Dict[str, Any]) -> None:
        """Update performance metrics based on task result."""
        self.performance.total_tasks += 1

        if task_result.get("success", False):
            self.performance.successful_tasks += 1
        else:
            self.performance.failed_tasks += 1

        # Update response time
        if "response_time_ms" in task_result:
            # Simple moving average
            alpha = 0.1  # Learning rate
            self.performance.average_response_time_ms = (
                alpha * task_result["response_time_ms"]
                + (1 - alpha) * self.performance.average_response_time_ms
            )

        # Update insight metrics
        if "insights" in task_result:
            insights = task_result["insights"]
            self.performance.insights_generated += len(insights)

            # Track unique insights (simple heuristic)
            unique_count = len(
                set(insight.get("key", str(i)) for i, insight in enumerate(insights))
            )
            self.performance.unique_insights += unique_count

            # Track actionable insights
            actionable_count = sum(
                1 for insight in insights if insight.get("actionable", False)
            )
            self.performance.actionable_insights += actionable_count

        # Update quality score
        if "quality_score" in task_result:
            alpha = 0.1
            self.performance.average_insight_quality = (
                alpha * task_result["quality_score"]
                + (1 - alpha) * self.performance.average_insight_quality
            )

        self.performance.last_active = datetime.now()
        self.updated_at = datetime.now()


@dataclass
class Insight:
    """Individual insight from task execution."""

    insight_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    insight_type: InsightType = InsightType.ANALYSIS
    confidence: float = 0.0

    # Quality metrics
    novelty_score: float = 0.0  # How new/unique is this insight
    actionability_score: float = 0.0  # How actionable is it
    impact_score: float = 0.0  # Potential impact if acted upon

    # Metadata
    generated_by: str = ""  # Agent ID
    generated_at: datetime = field(default_factory=datetime.now)

    # Related insights
    builds_on: List[str] = field(default_factory=list)  # IDs of insights this builds on
    contradicts: List[str] = field(
        default_factory=list
    )  # IDs of insights this contradicts

    # Supporting data
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    @property
    def quality_score(self) -> float:
        """Calculate overall quality score."""
        return (
            self.confidence * 0.3
            + self.novelty_score * 0.3
            + self.actionability_score * 0.3
            + self.impact_score * 0.1
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "insight_id": self.insight_id,
            "content": self.content,
            "type": self.insight_type.value,
            "confidence": self.confidence,
            "quality_score": self.quality_score,
            "novelty_score": self.novelty_score,
            "actionability_score": self.actionability_score,
            "impact_score": self.impact_score,
            "generated_by": self.generated_by,
            "generated_at": self.generated_at.isoformat(),
            "keywords": self.keywords,
        }


@dataclass
class TaskIteration:
    """Record of a single task iteration."""

    iteration_number: int
    started_at: datetime
    completed_at: Optional[datetime] = None

    # What changed
    adjustments_made: List[str] = field(default_factory=list)
    reason_for_iteration: str = ""

    # Results
    insights_generated: List[Insight] = field(default_factory=list)
    quality_improvement: float = 0.0  # Change in quality from previous iteration

    # Agent involvement
    agents_involved: List[str] = field(default_factory=list)
    consensus_score: float = 0.0


@dataclass
class A2ATask:
    """
    Structured task with full lifecycle management.

    Replaces dictionary-based tasks with rich objects that track
    state transitions, insight collection, and quality metrics.
    """

    # Identity
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""

    # State management
    state: TaskState = TaskState.CREATED
    priority: TaskPriority = TaskPriority.MEDIUM

    # Assignment
    assigned_to: List[str] = field(default_factory=list)  # Agent IDs
    delegated_by: Optional[str] = None  # Coordinator ID

    # Requirements
    requirements: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)

    # Timeline
    created_at: datetime = field(default_factory=datetime.now)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None

    # Insights - Primary deliverable
    insights: List[Insight] = field(default_factory=list)

    # Iterations
    iterations: List[TaskIteration] = field(default_factory=list)
    max_iterations: int = 3
    current_iteration: int = 0

    # Quality tracking
    target_quality_score: float = 0.85
    current_quality_score: float = 0.0

    # Context and memory
    context: Dict[str, Any] = field(default_factory=dict)
    memory_keys: List[str] = field(default_factory=list)  # Shared memory references

    # Results
    final_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    # Metadata
    tags: List[str] = field(default_factory=list)
    parent_task_id: Optional[str] = None
    subtask_ids: List[str] = field(default_factory=list)

    def transition_to(self, new_state: TaskState) -> bool:
        """
        Transition task to new state with validation.

        Returns True if transition is valid, False otherwise.
        """
        valid_transitions = {
            TaskState.CREATED: [TaskState.ASSIGNED, TaskState.CANCELLED],
            TaskState.ASSIGNED: [TaskState.IN_PROGRESS, TaskState.CANCELLED],
            TaskState.IN_PROGRESS: [
                TaskState.AWAITING_REVIEW,
                TaskState.FAILED,
                TaskState.CANCELLED,
            ],
            TaskState.AWAITING_REVIEW: [
                TaskState.ITERATING,
                TaskState.COMPLETED,
                TaskState.FAILED,
            ],
            TaskState.ITERATING: [
                TaskState.IN_PROGRESS,
                TaskState.FAILED,
                TaskState.CANCELLED,
            ],
            TaskState.COMPLETED: [],  # Terminal state
            TaskState.FAILED: [TaskState.IN_PROGRESS],  # Can retry
            TaskState.CANCELLED: [],  # Terminal state
        }

        if new_state not in valid_transitions.get(self.state, []):
            return False

        # Update timestamps
        if new_state == TaskState.ASSIGNED:
            self.assigned_at = datetime.now()
        elif new_state == TaskState.IN_PROGRESS:
            if not self.started_at:
                self.started_at = datetime.now()
        elif new_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
            self.completed_at = datetime.now()

        self.state = new_state
        return True

    def add_insight(self, insight: Insight) -> None:
        """Add an insight to the task."""
        self.insights.append(insight)
        self._update_quality_score()

    def start_iteration(self, reason: str, adjustments: List[str]) -> TaskIteration:
        """Start a new iteration of the task."""
        self.current_iteration += 1

        iteration = TaskIteration(
            iteration_number=self.current_iteration,
            started_at=datetime.now(),
            reason_for_iteration=reason,
            adjustments_made=adjustments,
        )

        self.iterations.append(iteration)
        self.transition_to(TaskState.ITERATING)

        return iteration

    def complete_iteration(
        self,
        insights: List[Insight],
        agents_involved: List[str],
        consensus_score: float = 0.0,
    ) -> None:
        """Complete the current iteration."""
        if not self.iterations:
            return

        current = self.iterations[-1]
        current.completed_at = datetime.now()
        current.insights_generated = insights
        current.agents_involved = agents_involved
        current.consensus_score = consensus_score

        # Calculate quality improvement
        prev_quality = self.current_quality_score
        self.insights.extend(insights)
        self._update_quality_score()
        current.quality_improvement = self.current_quality_score - prev_quality

        # Transition back to in_progress
        self.transition_to(TaskState.IN_PROGRESS)

    def _update_quality_score(self) -> None:
        """Update overall task quality score based on insights."""
        if not self.insights:
            self.current_quality_score = 0.0
            return

        # Average quality of all insights
        avg_quality = sum(i.quality_score for i in self.insights) / len(self.insights)

        # Bonus for unique insights
        unique_content = len(set(i.content for i in self.insights))
        uniqueness_bonus = min(unique_content / len(self.insights), 1.0) * 0.1

        # Bonus for actionable insights
        actionable_count = sum(1 for i in self.insights if i.actionability_score > 0.7)
        actionability_bonus = (actionable_count / len(self.insights)) * 0.1

        self.current_quality_score = min(
            avg_quality + uniqueness_bonus + actionability_bonus, 1.0
        )

    @property
    def is_complete(self) -> bool:
        """Check if task is in a terminal state."""
        return self.state in [
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        ]

    @property
    def needs_iteration(self) -> bool:
        """Check if task needs another iteration."""
        return (
            self.current_quality_score < self.target_quality_score
            and self.current_iteration < self.max_iterations
            and self.state == TaskState.AWAITING_REVIEW
        )

    @property
    def duration(self) -> Optional[float]:
        """Get task duration in seconds."""
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "priority": self.priority.value,
            "assigned_to": self.assigned_to,
            "requirements": self.requirements,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "insights": [i.to_dict() for i in self.insights],
            "iterations": len(self.iterations),
            "current_quality_score": self.current_quality_score,
            "target_quality_score": self.target_quality_score,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2ATask":
        """Create task from dictionary (backward compatibility)."""
        # Support old dictionary format
        if "task_id" not in data:
            # Legacy format
            return cls(
                name=data.get("title", "Unnamed Task"),
                description=data.get("description", ""),
                requirements=data.get("requirements", []),
                context=data,
            )

        # New format
        task = cls(
            task_id=data["task_id"],
            name=data["name"],
            description=data.get("description", ""),
            state=TaskState(data.get("state", "created")),
            priority=TaskPriority(data.get("priority", "medium")),
            requirements=data.get("requirements", []),
        )

        # Restore insights if present
        if "insights" in data:
            for insight_data in data["insights"]:
                insight = Insight(
                    insight_id=insight_data.get("insight_id", str(uuid.uuid4())),
                    content=insight_data.get("content", ""),
                    confidence=insight_data.get("confidence", 0.0),
                )
                task.insights.append(insight)

        return task


class TaskValidator:
    """Validates task readiness and quality."""

    @staticmethod
    def validate_for_assignment(task: A2ATask) -> Tuple[bool, List[str]]:
        """
        Validate task is ready for assignment.

        Returns (is_valid, list_of_issues).
        """
        issues = []

        if not task.name:
            issues.append("Task must have a name")

        if not task.description:
            issues.append("Task must have a description")

        if not task.requirements:
            issues.append("Task must have at least one requirement")

        if task.state != TaskState.CREATED:
            issues.append(f"Task must be in CREATED state, not {task.state.value}")

        return len(issues) == 0, issues

    @staticmethod
    def validate_for_completion(task: A2ATask) -> Tuple[bool, List[str]]:
        """
        Validate task is ready for completion.

        Returns (is_valid, list_of_issues).
        """
        issues = []

        if not task.insights:
            issues.append("Task must have at least one insight")

        if task.current_quality_score < task.target_quality_score:
            issues.append(
                f"Quality score {task.current_quality_score:.2f} "
                f"below target {task.target_quality_score:.2f}"
            )

        if task.state != TaskState.AWAITING_REVIEW:
            issues.append(
                f"Task must be in AWAITING_REVIEW state, not {task.state.value}"
            )

        # Check success criteria
        # This would need more sophisticated checking in practice
        if task.success_criteria:
            issues.append("Success criteria validation not yet implemented")

        return len(issues) == 0, issues


# Factory functions for common agent types


def create_research_agent_card(agent_id: str, agent_name: str) -> A2AAgentCard:
    """Create a card for a research-focused agent."""
    return A2AAgentCard(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_type="research",
        version="1.0.0",
        primary_capabilities=[
            Capability(
                name="information_retrieval",
                domain="research",
                level=CapabilityLevel.EXPERT,
                description="Expert at finding and synthesizing information from multiple sources",
                keywords=["search", "retrieval", "synthesis", "analysis"],
                examples=[
                    "literature review",
                    "market research",
                    "competitive analysis",
                ],
            ),
            Capability(
                name="data_analysis",
                domain="research",
                level=CapabilityLevel.ADVANCED,
                description="Analyzes complex datasets to extract insights",
                keywords=["statistics", "patterns", "trends", "visualization"],
            ),
        ],
        secondary_capabilities=[
            Capability(
                name="report_generation",
                domain="documentation",
                level=CapabilityLevel.ADVANCED,
                description="Creates comprehensive research reports",
                keywords=["writing", "documentation", "summaries"],
            ),
        ],
        collaboration_style=CollaborationStyle.COOPERATIVE,
        description="Specialized in comprehensive research and information synthesis",
        tags=["research", "analysis", "documentation"],
    )


def create_coding_agent_card(agent_id: str, agent_name: str) -> A2AAgentCard:
    """Create a card for a coding-focused agent."""
    return A2AAgentCard(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_type="coding",
        version="1.0.0",
        primary_capabilities=[
            Capability(
                name="code_generation",
                domain="software_development",
                level=CapabilityLevel.EXPERT,
                description="Generates high-quality code in multiple languages",
                keywords=["python", "javascript", "java", "implementation"],
                examples=["API implementation", "algorithm design", "refactoring"],
            ),
            Capability(
                name="debugging",
                domain="software_development",
                level=CapabilityLevel.ADVANCED,
                description="Identifies and fixes bugs in complex codebases",
                keywords=["troubleshooting", "error", "fix", "debug"],
            ),
        ],
        secondary_capabilities=[
            Capability(
                name="code_review",
                domain="software_development",
                level=CapabilityLevel.ADVANCED,
                description="Reviews code for quality, security, and best practices",
                keywords=["review", "quality", "standards", "security"],
            ),
        ],
        collaboration_style=CollaborationStyle.INDEPENDENT,
        description="Expert software developer focused on code quality and implementation",
        tags=["coding", "development", "debugging"],
    )


def create_qa_agent_card(agent_id: str, agent_name: str) -> A2AAgentCard:
    """Create a card for a QA/testing-focused agent."""
    return A2AAgentCard(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_type="qa_testing",
        version="1.0.0",
        primary_capabilities=[
            Capability(
                name="test_design",
                domain="quality_assurance",
                level=CapabilityLevel.EXPERT,
                description="Designs comprehensive test scenarios and edge cases",
                keywords=["testing", "scenarios", "edge cases", "coverage"],
                examples=["integration tests", "security tests", "performance tests"],
            ),
            Capability(
                name="bug_detection",
                domain="quality_assurance",
                level=CapabilityLevel.EXPERT,
                description="Identifies defects and quality issues systematically",
                keywords=["bugs", "defects", "issues", "validation"],
            ),
        ],
        collaboration_style=CollaborationStyle.SUPPORT,
        description="Quality assurance specialist focused on comprehensive testing",
        tags=["qa", "testing", "quality", "validation"],
    )


def create_research_task(
    name: str,
    description: str,
    requirements: List[str],
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> A2ATask:
    """Create a research-oriented task."""
    return A2ATask(
        name=name,
        description=description,
        requirements=requirements,
        priority=priority,
        tags=["research", "analysis"],
        target_quality_score=0.85,
        max_iterations=3,
    )


def create_implementation_task(
    name: str,
    description: str,
    requirements: List[str],
    priority: TaskPriority = TaskPriority.HIGH,
) -> A2ATask:
    """Create an implementation-oriented task."""
    return A2ATask(
        name=name,
        description=description,
        requirements=requirements,
        priority=priority,
        tags=["implementation", "coding"],
        target_quality_score=0.90,
        max_iterations=2,
    )


def create_validation_task(
    name: str,
    description: str,
    requirements: List[str],
    parent_task_id: str,
) -> A2ATask:
    """Create a validation/testing task."""
    return A2ATask(
        name=name,
        description=description,
        requirements=requirements,
        priority=TaskPriority.HIGH,
        parent_task_id=parent_task_id,
        tags=["validation", "testing"],
        target_quality_score=0.95,
        max_iterations=1,
    )


# ============================================================================
# END OF ENHANCED A2A COMPONENTS
# ============================================================================


@register_node()
class SharedMemoryPoolNode(Node):
    """
    Central memory pool that multiple agents can read from and write to.

    This node implements a sophisticated shared memory system with selective attention
    mechanisms, enabling efficient multi-agent collaboration while preventing information
    overload through intelligent filtering and segmentation.

    Design Philosophy:
        The SharedMemoryPoolNode acts as a cognitive workspace where agents can share
        discoveries, insights, and intermediate results. It implements attention-based
        filtering inspired by human selective attention, allowing agents to focus on
        relevant information without being overwhelmed by the full memory pool.

    Upstream Dependencies:
        - A2AAgentNode: Primary writer of memories with insights and discoveries
        - A2ACoordinatorNode: Writes coordination messages and task assignments
        - Any custom agent nodes that need to share information

    Downstream Consumers:
        - A2AAgentNode: Reads relevant memories to enhance context
        - A2ACoordinatorNode: Monitors agent progress through memory queries
        - SolutionEvaluatorNode: Aggregates insights for evaluation
        - Any analysis or visualization nodes needing shared context

    Configuration:
        This node is typically configured at workflow initialization and doesn't
        require runtime configuration. Memory segmentation and size limits can
        be adjusted through class attributes.

    Implementation Details:
        - Uses segmented memory pools for different types of information
        - Implements tag-based indexing for fast retrieval
        - Supports importance-weighted attention filtering
        - Maintains agent subscription patterns for targeted delivery
        - Automatically manages memory size through FIFO eviction

    Error Handling:
        - Returns empty results for invalid queries rather than failing
        - Handles missing segments gracefully
        - Validates importance scores to [0, 1] range

    Side Effects:
        - Maintains internal memory state across workflow execution
        - Memory persists for the lifetime of the node instance
        - Does not persist to disk or external storage

    Examples:
        >>> # Create a shared memory pool
        >>> memory_pool = SharedMemoryPoolNode()
        >>>
        >>> # Write memory from an agent
        >>> result = memory_pool.execute(
        ...     action="write",
        ...     agent_id="researcher_001",
        ...     content="Found correlation between X and Y",
        ...     tags=["research", "correlation", "data"],
        ...     importance=0.8,
        ...     segment="findings"
        ... )
        >>> assert result["success"] == True
        >>> assert result["memory_id"] is not None
        >>>
        >>> # Read with attention filter
        >>> memories = memory_pool.execute(
        ...     action="read",
        ...     agent_id="analyst_001",
        ...     attention_filter={
        ...         "tags": ["correlation"],
        ...         "importance_threshold": 0.7,
        ...         "window_size": 5
        ...     }
        ... )
        >>> assert len(memories["memories"]) > 0
        >>>
        >>> # Subscribe to specific segments
        >>> memory_pool.execute(
        ...     action="subscribe",
        ...     agent_id="monitor_001",
        ...     segments=["findings", "alerts"]
        ... )
        >>>
        >>> # Semantic query across all memories
        >>> results = memory_pool.execute(
        ...     action="query",
        ...     query="correlation analysis",
        ...     top_k=3
        ... )
    """

    def __init__(self, name=None, **kwargs):
        # Accept name parameter and pass all kwargs to parent
        if name:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.memory_segments = defaultdict(deque)
        self.agent_subscriptions = defaultdict(set)
        self.attention_indices = defaultdict(lambda: defaultdict(list))
        self.memory_id_counter = 0
        self.max_segment_size = 1000

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="read",
                description="Action to perform: 'write', 'read', 'subscribe', 'query'",
            ),
            "agent_id": NodeParameter(
                name="agent_id",
                type=str,
                required=False,
                default="system",
                description="ID of the agent performing the action",
            ),
            "content": NodeParameter(
                name="content",
                type=Any,
                required=False,
                description="Content to write to memory (for write action)",
            ),
            "tags": NodeParameter(
                name="tags",
                type=list,
                required=False,
                default=[],
                description="Tags to categorize the memory",
            ),
            "importance": NodeParameter(
                name="importance",
                type=float,
                required=False,
                default=0.5,
                description="Importance score (0.0 to 1.0)",
            ),
            "segment": NodeParameter(
                name="segment",
                type=str,
                required=False,
                default="general",
                description="Memory segment to write to",
            ),
            "attention_filter": NodeParameter(
                name="attention_filter",
                type=dict,
                required=False,
                default={},
                description="Filter criteria for reading memories",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context for the memory",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Search query for semantic memory search",
            ),
            "segments": NodeParameter(
                name="segments",
                type=list,
                required=False,
                default=["general"],
                description="Memory segments to subscribe to",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute memory pool operations.

        This method routes requests to appropriate handlers based on the action
        parameter, supporting write, read, subscribe, and query operations.

        Args:
            **kwargs: Operation parameters including:
                action (str): Operation type ('write', 'read', 'subscribe', 'query')
                Additional parameters specific to each action

        Returns:
            Dict[str, Any]: Operation results with 'success' status and action-specific data

        Raises:
            No exceptions raised - errors returned in response dict

        Side Effects:
            Modifies internal memory state for write operations
            Updates subscription lists for subscribe operations
        """
        action = kwargs.get("action")

        if action == "write":
            return self._write_memory(kwargs)
        elif action == "read":
            return self._read_with_attention(kwargs)
        elif action == "subscribe":
            return self._subscribe_agent(kwargs)
        elif action == "query":
            return self._semantic_query(kwargs)
        elif action == "metrics":
            return self._get_metrics()
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _write_memory(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Write information to shared pool with metadata."""
        self.memory_id_counter += 1
        memory_item = {
            "id": f"mem_{self.memory_id_counter}",
            "content": kwargs["content"],
            "agent_id": kwargs["agent_id"],
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "tags": kwargs.get("tags", []),
            "importance": kwargs.get("importance", 0.5),
            "context": kwargs.get("context", {}),
            "access_count": 0,
        }

        # Store in appropriate segment
        segment = kwargs.get("segment", "general")
        self.memory_segments[segment].append(memory_item)

        # Maintain segment size limit
        if len(self.memory_segments[segment]) > self.max_segment_size:
            self.memory_segments[segment].popleft()

        # Update attention indices
        self._update_attention_indices(memory_item, segment)

        # Get relevant agents
        relevant_agents = self._get_relevant_agents(memory_item, segment)

        return {
            "success": True,
            "memory_id": memory_item["id"],
            "segment": segment,
            "notified_agents": list(relevant_agents),
            "timestamp": memory_item["timestamp"],
        }

    def _read_with_attention(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Read relevant memories based on attention filter."""
        agent_id = kwargs["agent_id"]
        attention_filter = kwargs.get("attention_filter", {})

        relevant_memories = []

        # Apply attention mechanism
        for segment, memories in self.memory_segments.items():
            if self._matches_attention_filter(segment, attention_filter):
                for memory in memories:
                    relevance_score = self._calculate_relevance(
                        memory, attention_filter, agent_id
                    )
                    if relevance_score > attention_filter.get("threshold", 0.3):
                        memory["access_count"] += 1
                        relevant_memories.append(
                            {
                                **memory,
                                "relevance_score": relevance_score,
                                "segment": segment,
                            }
                        )

        # Sort by relevance and recency
        relevant_memories.sort(
            key=lambda x: (x["relevance_score"], x["timestamp"]), reverse=True
        )

        # Limit to attention window
        window_size = attention_filter.get("window_size", 10)
        selected_memories = relevant_memories[:window_size]

        return {
            "success": True,
            "memories": selected_memories,
            "total_available": len(relevant_memories),
            "segments_scanned": list(self.memory_segments.keys()),
            "agent_id": agent_id,
        }

    def _subscribe_agent(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Subscribe an agent to specific memory segments or tags."""
        agent_id = kwargs["agent_id"]
        segments = kwargs.get("segments", ["general"])
        tags = kwargs.get("tags", [])

        for segment in segments:
            self.agent_subscriptions[segment].add(agent_id)

        # Store subscription preferences
        if not hasattr(self, "agent_preferences"):
            self.agent_preferences = {}

        self.agent_preferences[agent_id] = {
            "segments": segments,
            "tags": tags,
            "attention_filter": kwargs.get("attention_filter", {}),
        }

        return {
            "success": True,
            "agent_id": agent_id,
            "subscribed_segments": segments,
            "subscribed_tags": tags,
        }

    def _semantic_query(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Perform semantic search across memories."""
        query = kwargs.get("query", "")
        kwargs["agent_id"]

        # Simple keyword matching for now (can be enhanced with embeddings)
        matching_memories = []
        query_lower = query.lower()

        for segment, memories in self.memory_segments.items():
            for memory in memories:
                content_str = str(memory.get("content", "")).lower()
                if query_lower in content_str:
                    score = content_str.count(query_lower) / len(content_str.split())
                    matching_memories.append(
                        {**memory, "match_score": score, "segment": segment}
                    )

        # Sort by match score
        matching_memories.sort(key=lambda x: x["match_score"], reverse=True)

        return {
            "success": True,
            "query": query,
            "results": matching_memories[:10],
            "total_matches": len(matching_memories),
        }

    def _update_attention_indices(self, memory_item: Dict[str, Any], segment: str):
        """Update indices for efficient attention-based retrieval."""
        # Index by tags
        for tag in memory_item.get("tags", []):
            self.attention_indices["tags"][tag].append(memory_item["id"])

        # Index by agent
        agent_id = memory_item["agent_id"]
        self.attention_indices["agents"][agent_id].append(memory_item["id"])

        # Index by importance level
        importance = memory_item["importance"]
        if importance >= 0.8:
            self.attention_indices["importance"]["high"].append(memory_item["id"])
        elif importance >= 0.5:
            self.attention_indices["importance"]["medium"].append(memory_item["id"])
        else:
            self.attention_indices["importance"]["low"].append(memory_item["id"])

    def _matches_attention_filter(
        self, segment: str, attention_filter: Dict[str, Any]
    ) -> bool:
        """Check if a segment matches the attention filter."""
        # Check segment filter
        if "segments" in attention_filter:
            if segment not in attention_filter["segments"]:
                return False

        return True

    def _calculate_relevance(
        self, memory: Dict[str, Any], attention_filter: Dict[str, Any], agent_id: str
    ) -> float:
        """Calculate relevance score for a memory item."""
        score = 0.0
        weights = attention_filter.get(
            "weights", {"tags": 0.3, "importance": 0.3, "recency": 0.2, "agent": 0.2}
        )

        # Tag matching
        if "tags" in attention_filter:
            filter_tags = set(attention_filter["tags"])
            memory_tags = set(memory.get("tags", []))
            if filter_tags & memory_tags:
                score += (
                    weights.get("tags", 0.3)
                    * len(filter_tags & memory_tags)
                    / len(filter_tags)
                )

        # Importance threshold
        importance_threshold = attention_filter.get("importance_threshold", 0.0)
        if memory.get("importance", 0) >= importance_threshold:
            score += weights.get("importance", 0.3) * memory["importance"]

        # Recency
        current_time = time.time()
        age_seconds = current_time - memory["timestamp"]
        recency_window = attention_filter.get("recency_window", 3600)  # 1 hour default
        if age_seconds < recency_window:
            recency_score = 1.0 - (age_seconds / recency_window)
            score += weights.get("recency", 0.2) * recency_score

        # Agent affinity
        if "preferred_agents" in attention_filter:
            if memory["agent_id"] in attention_filter["preferred_agents"]:
                score += weights.get("agent", 0.2)

        return min(score, 1.0)

    def _get_relevant_agents(
        self, memory_item: Dict[str, Any], segment: str
    ) -> Set[str]:
        """Get agents that should be notified about this memory."""
        relevant_agents = set()

        # Agents subscribed to this segment
        relevant_agents.update(self.agent_subscriptions.get(segment, set()))

        # Agents with matching tag subscriptions
        if hasattr(self, "agent_preferences"):
            for agent_id, prefs in self.agent_preferences.items():
                if any(
                    tag in memory_item.get("tags", []) for tag in prefs.get("tags", [])
                ):
                    relevant_agents.add(agent_id)

        # Remove the writing agent
        relevant_agents.discard(memory_item["agent_id"])

        return relevant_agents

    def _get_metrics(self) -> Dict[str, Any]:
        """Get memory pool metrics."""
        total_memories = sum(
            len(memories) for memories in self.memory_segments.values()
        )

        return {
            "success": True,
            "total_memories": total_memories,
            "segments": list(self.memory_segments.keys()),
            "segment_sizes": {
                segment: len(memories)
                for segment, memories in self.memory_segments.items()
            },
            "total_agents": len(self.agent_subscriptions),
            "memory_id_counter": self.memory_id_counter,
        }


@register_node()
class A2AAgentNode(LLMAgentNode):
    """
    Enhanced LLM agent with agent-to-agent communication capabilities.

    This node extends the standard LLMAgentNode with sophisticated A2A communication
    features, enabling agents to share insights through a shared memory pool, enhance
    their context with relevant information from other agents, and collaborate
    effectively on complex tasks.

    Design Philosophy:
        A2AAgentNode represents an intelligent agent that can both contribute to and
        benefit from collective intelligence. It automatically extracts insights from
        its responses and shares them with other agents while selectively attending
        to relevant information from the shared memory pool. This creates an emergent
        collaborative intelligence system.

    Upstream Dependencies:
        - QueryAnalysisNode: Provides analyzed queries and context
        - TeamFormationNode: Assigns roles and capabilities to agents
        - A2ACoordinatorNode: Delegates tasks and coordinates activities
        - SharedMemoryPoolNode: Provides access to shared memories

    Downstream Consumers:
        - SharedMemoryPoolNode: Receives insights and discoveries
        - A2ACoordinatorNode: Reports progress and results
        - SolutionEvaluatorNode: Provides solutions for evaluation
        - Other A2AAgentNodes: Indirect consumers through shared memory

    Configuration:
        Inherits all configuration from LLMAgentNode plus A2A-specific parameters
        for memory pool integration, attention filtering, and collaboration modes.

    Implementation Details:
        - Automatically extracts insights from LLM responses
        - Enhances prompts with relevant context from shared memory
        - Supports multiple collaboration modes (cooperative, competitive, hierarchical)
        - Tracks conversation context and shares key discoveries
        - Implements attention filtering to prevent information overload

    Error Handling:
        - Gracefully handles missing memory pool connections
        - Falls back to standard LLM behavior if A2A features fail
        - Validates insight extraction to prevent malformed memories

    Side Effects:
        - Writes insights to SharedMemoryPoolNode after each interaction
        - Maintains conversation history for context
        - May influence other agents through shared memories

    Examples:
        >>> # Create an A2A agent with specific expertise
        >>> agent = A2AAgentNode()
        >>>
        >>> # Execute with A2A features
        >>> result = agent.execute(
        ...     agent_id="researcher_001",
        ...     agent_role="research_specialist",
        ...     provider="openai",
        ...     model="gpt-4",
        ...     messages=[{
        ...         "role": "user",
        ...         "content": "Analyze the impact of AI on productivity"
        ...     }],
        ...     memory_pool=memory_pool_instance,
        ...     attention_filter={
        ...         "tags": ["productivity", "AI", "research"],
        ...         "importance_threshold": 0.7
        ...     },
        ...     collaboration_mode="cooperative"
        ... )
        >>> assert result["success"] == True
        >>> assert "insights_generated" in result["a2a_metadata"]
        >>>
        >>> # Agent automatically shares insights
        >>> insights = result["a2a_metadata"]["insights_generated"]
        >>> assert len(insights) > 0
        >>> assert all("content" in i for i in insights)
    """

    def __init__(self, name=None, **kwargs):
        # Accept name parameter and pass all kwargs to parent
        if name:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.local_memory = deque(maxlen=100)
        self.communication_log = deque(maxlen=50)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        # Inherit all LLMAgentNode parameters
        params = super().get_parameters()

        # Add A2A-specific parameters
        params.update(
            {
                "agent_id": NodeParameter(
                    name="agent_id",
                    type=str,
                    required=False,
                    default=f"agent_{uuid.uuid4().hex[:8]}",
                    description="Unique identifier for this agent",
                ),
                "agent_role": NodeParameter(
                    name="agent_role",
                    type=str,
                    required=False,
                    default="general",
                    description="Role of the agent (researcher, analyst, coordinator, etc.)",
                ),
                "memory_pool": NodeParameter(
                    name="memory_pool",
                    type=Node,
                    required=False,
                    description="Reference to SharedMemoryPoolNode",
                ),
                "attention_filter": NodeParameter(
                    name="attention_filter",
                    type=dict,
                    required=False,
                    default={},
                    description="Criteria for filtering relevant information from shared memory",
                ),
                "communication_config": NodeParameter(
                    name="communication_config",
                    type=dict,
                    required=False,
                    default={"mode": "direct", "protocol": "json-rpc"},
                    description="A2A communication settings",
                ),
                "collaboration_mode": NodeParameter(
                    name="collaboration_mode",
                    type=str,
                    required=False,
                    default="cooperative",
                    description="How agent collaborates: cooperative, competitive, hierarchical",
                ),
                "peer_agents": NodeParameter(
                    name="peer_agents",
                    type=list,
                    required=False,
                    default=[],
                    description="List of peer agent IDs for direct communication",
                ),
            }
        )
        return params

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the A2A agent with enhanced communication capabilities.

        This method extends the base LLMAgentNode execution by:
        1. Reading relevant context from the shared memory pool
        2. Enhancing the prompt with shared discoveries
        3. Executing the LLM call with enriched context
        4. Extracting insights from the response
        5. Sharing valuable insights back to the memory pool

        Args:
            **kwargs: All LLMAgentNode parameters plus:
                agent_id (str): Unique identifier for this agent
                agent_role (str): Agent's role in the team
                memory_pool (SharedMemoryPoolNode): Shared memory instance
                attention_filter (dict): Criteria for filtering memories
                collaboration_mode (str): How agent collaborates

        Returns:
            Dict[str, Any]: LLMAgentNode response plus:
                a2a_metadata: Information about A2A interactions including
                    insights_generated, shared_context_used, collaboration_stats

        Side Effects:
            Writes insights to shared memory pool if available
            Updates internal conversation history
        """
        # Extract A2A specific parameters
        agent_id = kwargs.get("agent_id")
        agent_role = kwargs.get("agent_role", "general")
        memory_pool = kwargs.get("memory_pool")
        attention_filter = kwargs.get("attention_filter", {})

        # Read from shared memory if available
        shared_context = []
        if memory_pool:
            memory_result = memory_pool.execute(
                action="read", agent_id=agent_id, attention_filter=attention_filter
            )
            if memory_result.get("success"):
                shared_context = memory_result.get("memories", [])

        # Store provider and model for use in summarization
        self._current_provider = kwargs.get("provider", "mock")
        self._current_model = kwargs.get("model", "mock-model")

        # Enhance messages with shared context
        messages = kwargs.get("messages", [])
        if shared_context:
            context_summary = self._summarize_shared_context(shared_context)
            enhanced_system_prompt = f"""You are agent {agent_id} with role: {agent_role}.

Relevant shared context from other agents:
{context_summary}

{kwargs.get('system_prompt', '')}"""
            kwargs["system_prompt"] = enhanced_system_prompt

        # Execute LLM agent
        result = super().run(**kwargs)

        # If successful, write insights to shared memory
        if result.get("success") and memory_pool:
            response_content = result.get("response", {}).get("content", "")

            # Use LLM to extract insights if provider supports it
            use_llm_extraction = kwargs.get("use_llm_insight_extraction", True)
            provider = kwargs.get("provider", "mock")

            if use_llm_extraction and provider not in ["mock"]:
                # Use LLM to extract and analyze insights
                insights = self._extract_insights_with_llm(
                    response_content, agent_role, agent_id, kwargs
                )
            else:
                # Fallback to rule-based extraction
                insights = self._extract_insights(response_content, agent_role)

            # Track insight statistics
            insight_stats = {
                "total": len(insights),
                "high_importance": sum(1 for i in insights if i["importance"] >= 0.8),
                "by_type": {},
                "extraction_method": (
                    "llm"
                    if use_llm_extraction and provider not in ["mock"]
                    else "rule-based"
                ),
            }

            for insight in insights:
                # Update type statistics
                insight_type = insight.get("metadata", {}).get(
                    "insight_type", "general"
                )
                insight_stats["by_type"][insight_type] = (
                    insight_stats["by_type"].get(insight_type, 0) + 1
                )

                # Write to memory pool with enhanced context
                memory_pool.execute(
                    action="write",
                    agent_id=agent_id,
                    content=insight["content"],
                    tags=insight.get("tags", [agent_role]),
                    importance=insight.get("importance", 0.6),
                    segment=insight.get("segment", agent_role),
                    context={
                        "source_message": messages[-1] if messages else None,
                        "agent_role": agent_role,
                        "insight_metadata": insight.get("metadata", {}),
                        "timestamp": kwargs.get("timestamp", time.time()),
                    },
                )

            # Store insights in local memory for agent's own reference
            for insight in insights:
                self.local_memory.append(
                    {
                        "type": "insight",
                        "content": insight["content"],
                        "importance": insight["importance"],
                        "timestamp": time.time(),
                    }
                )

        # Add A2A metadata to result
        result["a2a_metadata"] = {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "shared_context_used": len(shared_context),
            "insights_generated": len(insights) if "insights" in locals() else 0,
            "insight_statistics": insight_stats if "insight_stats" in locals() else {},
            "memory_pool_active": memory_pool is not None,
            "local_memory_size": len(self.local_memory),
        }

        return result

    def _summarize_shared_context(self, shared_context: List[Dict[str, Any]]) -> str:
        """Summarize shared context for inclusion in prompt."""
        if not shared_context:
            return "No relevant shared context available."

        # For small context, use simple formatting
        if len(shared_context) <= 3:
            summary_parts = []
            for memory in shared_context:
                agent_id = memory.get("agent_id", "unknown")
                content = memory.get("content", "")
                importance = memory.get("importance", 0)
                tags = ", ".join(memory.get("tags", []))

                summary_parts.append(
                    f"- Agent {agent_id} ({importance:.1f} importance, tags: {tags}): {content}"
                )
            return "\n".join(summary_parts)

        # For larger context, use LLM to create intelligent summary
        return self._summarize_with_llm(shared_context)

    def _summarize_with_llm(self, shared_context: List[Dict[str, Any]]) -> str:
        """Use LLM to create an intelligent summary of shared context."""

        # Prepare context for summarization
        context_items = []
        for memory in shared_context[:10]:  # Process up to 10 most relevant
            context_items.append(
                {
                    "agent": memory.get("agent_id", "unknown"),
                    "content": memory.get("content", ""),
                    "importance": memory.get("importance", 0),
                    "tags": memory.get("tags", []),
                    "type": memory.get("context", {})
                    .get("insight_metadata", {})
                    .get("insight_type", "general"),
                }
            )

        # Create summarization prompt
        summarization_prompt = f"""Summarize the following shared insights from other agents into a concise, actionable briefing.

Shared Context Items:
{json.dumps(context_items, indent=2)}

Create a summary that:
1. Groups related insights by theme
2. Highlights the most important findings (importance >= 0.8)
3. Identifies consensus points where multiple agents agree
4. Notes any contradictions or disagreements
5. Extracts key metrics and data points
6. Suggests areas needing further investigation

Format the summary as a brief paragraph (max 200 words) that another agent can quickly understand and act upon.
Focus on actionable intelligence rather than just listing what each agent said."""

        try:
            # Use the current agent's LLM configuration for summarization
            provider = getattr(self, "_current_provider", "mock")
            model = getattr(self, "_current_model", "mock-model")

            if provider not in ["mock"]:
                summary_kwargs = {
                    "provider": provider,
                    "model": model,
                    "temperature": 0.3,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert at synthesizing information from multiple sources into clear, actionable summaries.",
                        },
                        {"role": "user", "content": summarization_prompt},
                    ],
                    "max_tokens": 300,
                }

                result = super().run(**summary_kwargs)

                if result.get("success"):
                    summary = result.get("response", {}).get("content", "")
                    if summary:
                        return f"Shared Context Summary:\n{summary}"
        except Exception:
            pass

        # Fallback to simple summary
        summary_parts = []
        for memory in shared_context[:5]:
            agent_id = memory.get("agent_id", "unknown")
            content = memory.get("content", "")[:100] + "..."
            importance = memory.get("importance", 0)

            summary_parts.append(f"- {agent_id} [{importance:.1f}]: {content}")

        return "Recent insights:\n" + "\n".join(summary_parts)

    def _extract_insights(self, response: str, agent_role: str) -> List[Dict[str, Any]]:
        """Extract important insights from agent response using advanced NLP techniques."""
        insights = []

        # Enhanced keyword patterns for different types of insights
        insight_patterns = {
            "findings": {
                "keywords": [
                    "found",
                    "discovered",
                    "identified",
                    "revealed",
                    "uncovered",
                    "detected",
                    "observed",
                    "noted",
                    "recognized",
                ],
                "importance": 0.8,
                "tags": ["finding", "discovery"],
            },
            "conclusions": {
                "keywords": [
                    "conclude",
                    "therefore",
                    "thus",
                    "hence",
                    "consequently",
                    "as a result",
                    "in summary",
                    "overall",
                    "in conclusion",
                ],
                "importance": 0.9,
                "tags": ["conclusion", "summary"],
            },
            "comparisons": {
                "keywords": [
                    "compared to",
                    "versus",
                    "vs",
                    "better than",
                    "worse than",
                    "improvement",
                    "decline",
                    "increase",
                    "decrease",
                    "change",
                ],
                "importance": 0.7,
                "tags": ["comparison", "analysis"],
            },
            "recommendations": {
                "keywords": [
                    "recommend",
                    "suggest",
                    "should",
                    "advise",
                    "propose",
                    "best practice",
                    "optimal",
                    "ideal",
                ],
                "importance": 0.85,
                "tags": ["recommendation", "advice"],
            },
            "problems": {
                "keywords": [
                    "issue",
                    "problem",
                    "challenge",
                    "limitation",
                    "constraint",
                    "difficulty",
                    "obstacle",
                    "concern",
                    "risk",
                ],
                "importance": 0.75,
                "tags": ["problem", "challenge"],
            },
            "metrics": {
                "keywords": [
                    "percent",
                    "%",
                    "score",
                    "rating",
                    "benchmark",
                    "metric",
                    "measurement",
                    "performance",
                    "efficiency",
                ],
                "importance": 0.65,
                "tags": ["metric", "measurement"],
            },
        }

        # Process response by sentences for better context
        import re

        sentences = re.split(r"[.!?]+", response)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 20:
                continue

            # Calculate importance based on multiple factors
            importance = 0.5  # Base importance
            matched_tags = set([agent_role])
            insight_type = None

            # Check for insight patterns
            sentence_lower = sentence.lower()
            for pattern_type, pattern_info in insight_patterns.items():
                if any(
                    keyword in sentence_lower for keyword in pattern_info["keywords"]
                ):
                    importance = max(importance, pattern_info["importance"])
                    matched_tags.update(pattern_info["tags"])
                    insight_type = pattern_type
                    break

            # Extract entities and add as tags
            # Simple entity extraction - numbers, capitalized words, technical terms
            numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", sentence)
            if numbers:
                matched_tags.add("quantitative")
                importance += 0.1

            # Extract technical terms (words with specific patterns)
            tech_terms = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", sentence)
            if tech_terms:
                matched_tags.update(
                    [term.lower() for term in tech_terms[:2]]
                )  # Limit tags

            # Boost importance for sentences with multiple capital letters (proper nouns)
            capital_words = re.findall(r"\b[A-Z][A-Za-z]+\b", sentence)
            if len(capital_words) > 2:
                importance += 0.05

            # Check for structured data (JSON, lists, etc.)
            if any(char in sentence for char in ["{", "[", ":", "-"]):
                matched_tags.add("structured")
                importance += 0.05

            # Determine segment based on insight type and role
            segment = f"{agent_role}_{insight_type}" if insight_type else agent_role

            # Create insight with rich metadata
            insight = {
                "content": sentence,
                "importance": min(importance, 1.0),  # Cap at 1.0
                "tags": list(matched_tags),
                "segment": segment,
                "metadata": {
                    "length": len(sentence),
                    "has_numbers": bool(numbers),
                    "insight_type": insight_type or "general",
                    "extracted_entities": tech_terms[:3] if tech_terms else [],
                },
            }

            insights.append(insight)

        # Sort by importance and return top insights
        insights.sort(key=lambda x: x["importance"], reverse=True)

        # Dynamic limit based on response quality
        # If we have many high-quality insights, return more
        high_quality_count = sum(1 for i in insights if i["importance"] >= 0.7)
        limit = min(5 if high_quality_count > 3 else 3, len(insights))

        return insights[:limit]

    def _extract_insights_with_llm(
        self,
        response: str,
        agent_role: str,
        agent_id: str,
        original_kwargs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Multi-stage LLM pipeline for high-quality insight extraction.

        This enhanced method implements a 6-stage pipeline as per the A2A enhancement plan:
        1. Primary extraction with structured output
        2. Novelty detection against memory pool
        3. Quality enhancement and validation
        4. Cross-model validation for reliability (if enabled)
        5. Impact scoring and ranking
        6. Meta-insight synthesis
        """

        # Stage 1: Primary LLM extraction with structured output
        primary_insights = self._stage1_primary_extraction(
            response, agent_role, original_kwargs
        )

        if not primary_insights:
            # Fallback to rule-based extraction
            return self._extract_insights(response, agent_role)

        # Stage 2: Novelty detection against memory pool
        memory_pool = original_kwargs.get("memory_pool")
        if memory_pool:
            primary_insights = self._stage2_novelty_detection(
                primary_insights, agent_id, memory_pool
            )

        # Stage 3: Quality enhancement and validation
        enhanced_insights = self._stage3_quality_enhancement(
            primary_insights, agent_role, original_kwargs
        )

        # Stage 4: Cross-model validation (optional, based on settings)
        if original_kwargs.get("enable_cross_validation", False):
            enhanced_insights = self._stage4_cross_model_validation(
                enhanced_insights, original_kwargs
            )

        # Stage 5: Impact scoring and ranking
        scored_insights = self._stage5_impact_scoring(
            enhanced_insights, agent_role, original_kwargs
        )

        # Stage 6: Meta-insight synthesis (if multiple high-quality insights)
        if len(scored_insights) >= 3:
            meta_insights = self._stage6_meta_insight_synthesis(
                scored_insights, agent_role, original_kwargs
            )
            scored_insights.extend(meta_insights)

        # Sort by quality and return top insights
        scored_insights.sort(
            key=lambda x: x.get("quality_score", x.get("importance", 0.5)), reverse=True
        )

        return scored_insights[:5]  # Return top 5 insights

    def _stage1_primary_extraction(
        self, response: str, agent_role: str, kwargs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 1: Primary LLM extraction with structured output."""
        insight_extraction_prompt = f"""You are an AI insight extraction specialist. Analyze the following response and extract the most important insights.

Agent Role: {agent_role}
Original Response:
{response}

Extract 3-5 key insights from this response. For each insight:
1. Summarize the core finding or conclusion (max 100 words)
2. Assign a confidence score (0.0-1.0) based on evidence strength
3. Categorize the insight type: discovery, analysis, recommendation, warning, opportunity, pattern, or anomaly
4. Extract key entities mentioned (products, technologies, metrics, etc.)
5. Identify the actionability level (0.0-1.0) - how easy is it to act on this insight?
6. Note any prerequisites or dependencies

Output your analysis as a JSON array with this structure:
[
  {{
    "content": "The core insight summarized concisely",
    "confidence": 0.85,
    "type": "discovery",
    "entities": ["Entity1", "Entity2"],
    "actionability": 0.7,
    "prerequisites": ["Need access to X", "Requires Y"],
    "evidence": "Brief supporting evidence from the text",
    "keywords": ["keyword1", "keyword2"]
  }}
]

Focus on insights that would be valuable for other agents to know. Ensure the JSON is valid."""

        try:
            extraction_kwargs = {
                "provider": kwargs.get("provider", "ollama"),
                "model": kwargs.get("model", "mistral"),
                "temperature": 0.3,  # Lower temperature for more focused extraction
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing text and extracting structured insights. Always respond with valid JSON.",
                    },
                    {"role": "user", "content": insight_extraction_prompt},
                ],
                "max_tokens": kwargs.get("max_tokens", 1000),
            }

            extraction_result = super().run(**extraction_kwargs)

            if extraction_result.get("success"):
                extracted_content = extraction_result.get("response", {}).get(
                    "content", ""
                )

                # Parse JSON response
                import json
                import re

                json_match = re.search(r"\[.*?\]", extracted_content, re.DOTALL)
                if json_match:
                    try:
                        extracted_insights = json.loads(json_match.group())

                        # Convert to enhanced format
                        insights = []
                        for item in extracted_insights[:5]:
                            insight = {
                                "content": item.get("content", ""),
                                "confidence": item.get("confidence", 0.5),
                                "insight_type": InsightType(
                                    item.get("type", "analysis").upper()
                                    if item.get("type", "").upper()
                                    in [e.value.upper() for e in InsightType]
                                    else "ANALYSIS"
                                ),
                                "entities": item.get("entities", []),
                                "actionability_score": item.get("actionability", 0.5),
                                "prerequisites": item.get("prerequisites", []),
                                "evidence": item.get("evidence", ""),
                                "keywords": item.get("keywords", []),
                                "stage": "primary_extraction",
                            }
                            insights.append(insight)

                        return insights
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception:
            pass

        return []

    def _stage2_novelty_detection(
        self, insights: List[Dict[str, Any]], agent_id: str, memory_pool: Any
    ) -> List[Dict[str, Any]]:
        """Stage 2: Novelty detection against memory pool."""
        for insight in insights:
            # Search for similar insights in memory
            similar_memories = memory_pool.execute(
                action="read",
                agent_id=agent_id,
                attention_filter={
                    "tags": insight.get("keywords", []),
                    "window_size": 50,  # Check last 50 memories
                },
            ).get("memories", [])

            # Calculate novelty score
            novelty_score = 1.0
            for memory in similar_memories:
                # Simple similarity check (could be enhanced with embeddings)
                memory_content = memory.get("content", "").lower()
                insight_content = insight["content"].lower()

                # Check for significant overlap
                common_words = set(memory_content.split()) & set(
                    insight_content.split()
                )
                if len(common_words) > len(insight_content.split()) * 0.5:
                    novelty_score *= 0.7  # Reduce novelty if similar exists

            insight["novelty_score"] = max(novelty_score, 0.1)
            insight["similar_insights_count"] = len(similar_memories)

        return insights

    def _stage3_quality_enhancement(
        self, insights: List[Dict[str, Any]], agent_role: str, kwargs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 3: Quality enhancement and validation."""
        if not insights:
            return insights

        # Create a consolidated prompt for quality enhancement
        insights_text = "\n".join(
            [
                f"{i+1}. {insight['content']} (Confidence: {insight['confidence']:.2f})"
                for i, insight in enumerate(insights)
            ]
        )

        enhancement_prompt = f"""As a quality assurance specialist, enhance these insights:

Agent Role: {agent_role}
Raw Insights:
{insights_text}

For each insight:
1. Clarify any ambiguous statements
2. Add specific metrics or quantities where possible
3. Identify potential impacts (business, technical, strategic)
4. Suggest follow-up actions
5. Rate the overall quality (0.0-1.0)

Respond with a JSON array matching the input order:
[
  {{
    "enhanced_content": "Clearer, more specific version of the insight",
    "impact": "Description of potential impact",
    "follow_up_actions": ["Action 1", "Action 2"],
    "quality_score": 0.85
  }}
]"""

        try:
            enhancement_kwargs = {
                "provider": kwargs.get("provider", "ollama"),
                "model": kwargs.get("model", "mistral"),
                "temperature": 0.2,  # Even lower for enhancement
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at enhancing and clarifying insights. Always respond with valid JSON.",
                    },
                    {"role": "user", "content": enhancement_prompt},
                ],
                "max_tokens": 800,
            }

            enhancement_result = super().run(**enhancement_kwargs)

            if enhancement_result.get("success"):
                enhanced_content = enhancement_result.get("response", {}).get(
                    "content", ""
                )

                import json
                import re

                json_match = re.search(r"\[.*?\]", enhanced_content, re.DOTALL)
                if json_match:
                    try:
                        enhancements = json.loads(json_match.group())

                        # Merge enhancements with original insights
                        for i, enhancement in enumerate(enhancements[: len(insights)]):
                            if enhancement.get("enhanced_content"):
                                insights[i]["content"] = enhancement["enhanced_content"]
                            insights[i]["impact_score"] = enhancement.get(
                                "quality_score", 0.5
                            )
                            insights[i]["impact_description"] = enhancement.get(
                                "impact", ""
                            )
                            insights[i]["follow_up_actions"] = enhancement.get(
                                "follow_up_actions", []
                            )
                            insights[i]["stage"] = "quality_enhanced"
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception:
            pass

        return insights

    def _stage4_cross_model_validation(
        self, insights: List[Dict[str, Any]], kwargs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 4: Cross-model validation for reliability (optional)."""
        # This would validate insights using a different model
        # For now, we'll simulate by adjusting confidence based on consistency

        alternate_model = kwargs.get("validation_model", kwargs.get("model"))
        if alternate_model == kwargs.get("model"):
            # Same model, skip validation
            return insights

        # In a real implementation, we would re-validate with alternate model
        # For now, apply a validation factor
        for insight in insights:
            insight["cross_validated"] = True
            insight["confidence"] *= 0.95  # Slight confidence adjustment

        return insights

    def _stage5_impact_scoring(
        self, insights: List[Dict[str, Any]], agent_role: str, kwargs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 5: Impact scoring and ranking."""
        for insight in insights:
            # Calculate comprehensive quality score
            confidence = insight.get("confidence", 0.5)
            novelty = insight.get("novelty_score", 0.5)
            actionability = insight.get("actionability_score", 0.5)
            impact = insight.get("impact_score", 0.5)

            # Weighted quality score
            quality_score = (
                confidence * 0.3 + novelty * 0.3 + actionability * 0.3 + impact * 0.1
            )

            # Convert to final format
            insight_obj = Insight(
                content=insight["content"],
                insight_type=insight.get("insight_type", InsightType.ANALYSIS),
                confidence=confidence,
                novelty_score=novelty,
                actionability_score=actionability,
                impact_score=impact,
                generated_by=kwargs.get("agent_id", ""),
                keywords=insight.get("keywords", []),
                evidence=(
                    [{"text": insight.get("evidence", "")}]
                    if insight.get("evidence")
                    else []
                ),
            )

            # Add to format expected by memory pool
            formatted_insight = {
                "content": insight_obj.content,
                "importance": quality_score,
                "quality_score": quality_score,
                "tags": insight.get("keywords", []) + [agent_role],
                "segment": f"{agent_role}_{insight_obj.insight_type.value}",
                "metadata": {
                    "insight_type": insight_obj.insight_type.value,
                    "extracted_entities": insight.get("entities", []),
                    "evidence": insight.get("evidence", ""),
                    "llm_extracted": True,
                    "multi_stage_pipeline": True,
                    "stages_completed": insight.get("stage", "unknown"),
                    "novelty_score": novelty,
                    "actionability_score": actionability,
                    "impact_score": impact,
                    "quality_score": quality_score,
                },
            }

            # Copy over the insight object for reference
            formatted_insight["insight_object"] = insight_obj

            insights[insights.index(insight)] = formatted_insight

        return insights

    def _stage6_meta_insight_synthesis(
        self, insights: List[Dict[str, Any]], agent_role: str, kwargs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 6: Meta-insight synthesis from multiple insights."""
        if len(insights) < 3:
            return []

        # Create synthesis prompt
        insights_summary = "\n".join(
            [
                f"- {insight['content']} (Quality: {insight.get('quality_score', 0.5):.2f})"
                for insight in insights[:5]
            ]
        )

        synthesis_prompt = f"""Analyze these insights collectively to identify meta-patterns:

Agent Role: {agent_role}
Individual Insights:
{insights_summary}

Identify:
1. Common themes or patterns across insights
2. Potential synergies or connections
3. Contradictions or tensions
4. Emergent conclusions from the collective insights

Provide 1-2 meta-insights that capture higher-level understanding.

Respond with JSON:
[
  {{
    "meta_insight": "Higher-level insight derived from patterns",
    "supporting_insights": [1, 2, 3],
    "insight_type": "pattern",
    "confidence": 0.8
  }}
]"""

        try:
            synthesis_kwargs = {
                "provider": kwargs.get("provider", "ollama"),
                "model": kwargs.get("model", "mistral"),
                "temperature": 0.4,  # Slightly higher for creative synthesis
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at identifying patterns and synthesizing meta-insights.",
                    },
                    {"role": "user", "content": synthesis_prompt},
                ],
                "max_tokens": 500,
            }

            synthesis_result = super().run(**synthesis_kwargs)

            if synthesis_result.get("success"):
                synthetic_content = synthesis_result.get("response", {}).get(
                    "content", ""
                )

                import json
                import re

                json_match = re.search(r"\[.*?\]", synthetic_content, re.DOTALL)
                if json_match:
                    try:
                        meta_insights_data = json.loads(json_match.group())

                        meta_insights = []
                        for meta in meta_insights_data[:2]:  # Max 2 meta-insights
                            meta_insight = Insight(
                                content=meta.get("meta_insight", ""),
                                insight_type=InsightType.PATTERN,
                                confidence=meta.get("confidence", 0.7),
                                novelty_score=0.9,  # Meta-insights are typically novel
                                actionability_score=0.6,  # May be less directly actionable
                                impact_score=0.8,  # But high impact
                                generated_by=kwargs.get("agent_id", ""),
                                keywords=["meta-insight", "synthesis", agent_role],
                            )

                            # Track which insights it builds on
                            supporting_indices = meta.get("supporting_insights", [])
                            if supporting_indices:
                                meta_insight.builds_on = [
                                    insights[i - 1]
                                    .get("insight_object", Insight())
                                    .insight_id
                                    for i in supporting_indices
                                    if 0 < i <= len(insights)
                                ]

                            formatted_meta = {
                                "content": meta_insight.content,
                                "importance": meta_insight.quality_score,
                                "quality_score": meta_insight.quality_score,
                                "tags": ["meta-insight", "synthesis"] + [agent_role],
                                "segment": f"{agent_role}_meta_pattern",
                                "metadata": {
                                    "insight_type": "meta_pattern",
                                    "is_meta_insight": True,
                                    "supporting_insights": supporting_indices,
                                    "llm_extracted": True,
                                    "multi_stage_pipeline": True,
                                    "stage": "meta_synthesis",
                                },
                                "insight_object": meta_insight,
                            }

                            meta_insights.append(formatted_meta)

                        return meta_insights
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception:
            pass

        return []


@register_node()
class A2ACoordinatorNode(CycleAwareNode):
    """
    Coordinates communication and task delegation between A2A agents.

    This node acts as a central orchestrator for multi-agent systems, managing task
    distribution, consensus building, and workflow coordination. It implements various
    coordination strategies to optimize agent utilization and ensure effective
    collaboration across heterogeneous agent teams.

    Design Philosophy:
        The A2ACoordinatorNode serves as a decentralized coordination mechanism that
        enables agents to self-organize without requiring a fixed hierarchy. It provides
        flexible coordination patterns (delegation, broadcast, consensus, workflow)
        that can be composed to create sophisticated multi-agent behaviors.

    Upstream Dependencies:
        - ProblemAnalyzerNode: Provides decomposed tasks and requirements
        - TeamFormationNode: Supplies formed teams and agent assignments
        - QueryAnalysisNode: Delivers analyzed queries needing coordination
        - OrchestrationManagerNode: High-level orchestration directives

    Downstream Consumers:
        - A2AAgentNode: Receives task assignments and coordination messages
        - SharedMemoryPoolNode: Stores coordination decisions and progress
        - SolutionEvaluatorNode: Evaluates coordinated solution components
        - ConvergenceDetectorNode: Monitors coordination effectiveness

    Configuration:
        The coordinator adapts its behavior based on the coordination strategy
        selected and the characteristics of available agents. No static configuration
        is required, but runtime parameters control coordination behavior.

    Implementation Details:
        - Maintains registry of active agents with capabilities and status
        - Implements multiple delegation strategies (best_match, round_robin, auction)
        - Tracks task assignments and agent performance metrics
        - Supports both synchronous and asynchronous coordination patterns
        - Manages consensus voting with configurable thresholds

    Error Handling:
        - Handles agent failures with automatic reassignment
        - Validates task requirements before delegation
        - Falls back to broadcast when specific agents unavailable
        - Returns partial results if consensus cannot be reached

    Side Effects:
        - Maintains internal agent registry across calls
        - Updates agent performance metrics after task completion
        - May modify task priorities based on agent availability

    Examples:
        >>> # Create coordinator
        >>> coordinator = A2ACoordinatorNode()
        >>>
        >>> # Register agents
        >>> coordinator.execute(
        ...     action="register",
        ...     agent_info={
        ...         "id": "analyst_001",
        ...         "skills": ["data_analysis", "statistics"],
        ...         "role": "analyst"
        ...     }
        ... )
        >>>
        >>> # Delegate task with best match strategy
        >>> result = coordinator.execute(
        ...     action="delegate",
        ...     task={
        ...         "type": "analysis",
        ...         "description": "Analyze sales data",
        ...         "required_skills": ["data_analysis"],
        ...         "priority": "high"
        ...     },
        ...     available_agents=[
        ...         {"id": "analyst_001", "skills": ["data_analysis"]},
        ...         {"id": "researcher_001", "skills": ["research"]}
        ...     ],
        ...     coordination_strategy="best_match"
        ... )
        >>> assert result["success"] == True
        >>> assert result["assigned_agent"] == "analyst_001"
        >>>
        >>> # Build consensus among agents
        >>> consensus_result = coordinator.execute(
        ...     action="consensus",
        ...     proposal="Implement new feature X",
        ...     voting_agents=["agent1", "agent2", "agent3"],
        ...     consensus_threshold=0.66
        ... )
    """

    def __init__(self, name=None, **kwargs):
        # Accept name parameter and pass all kwargs to parent
        if name:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.registered_agents = {}
        self.task_queue = deque()
        self.consensus_sessions = {}

        # Enhanced features
        self.agent_cards: Dict[str, A2AAgentCard] = {}
        self.active_tasks: Dict[str, A2ATask] = {}
        self.completed_tasks: List[A2ATask] = []
        self.task_history_limit = 100  # Keep last 100 completed tasks

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="coordinate",
                description="Action: 'register', 'register_with_card', 'delegate', 'broadcast', 'consensus', 'coordinate', 'create_task', 'update_task_state', 'get_task_insights', 'match_agents_to_task'",
            ),
            "agent_info": NodeParameter(
                name="agent_info",
                type=dict,
                required=False,
                description="Information about agent (for registration)",
            ),
            "agent_id": NodeParameter(
                name="agent_id",
                type=str,
                required=False,
                description="Unique identifier for an agent (for register_with_card, update_task_state)",
            ),
            "agent_card": NodeParameter(
                name="agent_card",
                type=dict,
                required=False,
                description="Rich capability card for agent registration (for register_with_card action)",
            ),
            "task": NodeParameter(
                name="task",
                type=dict,
                required=False,
                description="Task to delegate or coordinate",
            ),
            "task_id": NodeParameter(
                name="task_id",
                type=str,
                required=False,
                description="ID of an existing task (for update_task_state, get_task_insights, delegate)",
            ),
            "message": NodeParameter(
                name="message",
                type=dict,
                required=False,
                description="Message to broadcast",
            ),
            "consensus_proposal": NodeParameter(
                name="consensus_proposal",
                type=dict,
                required=False,
                description="Proposal for consensus",
            ),
            "available_agents": NodeParameter(
                name="available_agents",
                type=list,
                required=False,
                default=[],
                description="List of available agents",
            ),
            "coordination_strategy": NodeParameter(
                name="coordination_strategy",
                type=str,
                required=False,
                default="best_match",
                description="Strategy: 'best_match', 'round_robin', 'broadcast', 'auction'",
            ),
            "task_type": NodeParameter(
                name="task_type",
                type=str,
                required=False,
                default="research",
                description="Type of task to create: 'research', 'implementation', 'validation'",
            ),
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="",
                description="Name of the task",
            ),
            "description": NodeParameter(
                name="description",
                type=str,
                required=False,
                default="",
                description="Description of the task",
            ),
            "requirements": NodeParameter(
                name="requirements",
                type=list,
                required=False,
                default=[],
                description="List of requirements for the task",
            ),
            "priority": NodeParameter(
                name="priority",
                type=str,
                required=False,
                default="medium",
                description="Task priority: 'low', 'medium', 'high', 'critical'",
            ),
            "new_state": NodeParameter(
                name="new_state",
                type=str,
                required=False,
                description="New state for task transition",
            ),
            "insights": NodeParameter(
                name="insights",
                type=list,
                required=False,
                default=[],
                description="List of insights to add to task",
            ),
            "min_quality": NodeParameter(
                name="min_quality",
                type=float,
                required=False,
                default=0.0,
                description="Minimum quality score for insight filtering",
            ),
            "insight_type": NodeParameter(
                name="insight_type",
                type=str,
                required=False,
                description="Type of insights to filter",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute coordination action with cycle awareness.

        Routes coordination requests to appropriate handlers based on action
        parameter. Tracks coordination history and agent performance across
        iterations for cycle-aware optimization.

        Args:
            context: Execution context with cycle information
            **kwargs: Action-specific parameters including:
                action (str): Type of coordination action
                agent_info (dict): Agent registration details
                task (dict): Task to delegate
                available_agents (list): Agents available for tasks
                coordination_strategy (str): Delegation strategy

        Returns:
            Dict[str, Any]: Action results with cycle metadata including:
                success (bool): Whether action succeeded
                cycle_info (dict): Iteration and history information
                Additional action-specific fields

        Raises:
            None - errors returned in result dictionary

        Side Effects:
            Updates internal agent registry
            Modifies coordination history
            Updates agent performance metrics

        Examples:
            >>> coordinator = A2ACoordinatorNode()
            >>> result = coordinator.execute(context,
            ...     action=\"delegate\",
            ...     task={\"type\": \"analysis\", \"required_skills\": [\"data\"]},
            ...     coordination_strategy=\"best_match\"
            ... )
            >>> assert result[\"success\"] == True
        """
        context = kwargs.get("context", {})
        action = kwargs.get("action")

        # Get cycle information using CycleAwareNode helpers
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)
        prev_state = self.get_previous_state(context)

        # Initialize cycle-aware coordination state
        if is_first:
            self.log_cycle_info(context, f"Starting coordination with action: {action}")
            coordination_history = []
            agent_performance_history = {}
        else:
            coordination_history = prev_state.get("coordination_history", [])
            agent_performance_history = prev_state.get("agent_performance", {})

        # Execute the coordination action - enhanced actions first
        if action == "register_with_card":
            result = self._register_agent_with_card(kwargs, context)
        elif action == "create_task":
            result = self._create_structured_task(kwargs)
        elif action == "update_task_state":
            result = self._update_task_state(kwargs)
        elif action == "get_task_insights":
            result = self._get_task_insights(kwargs)
        elif action == "match_agents_to_task":
            result = self._match_agents_to_task(kwargs)
        # Original actions with enhancement support
        elif action == "register":
            result = self._register_agent(kwargs, context)
        elif action == "delegate":
            # Check if we should use enhanced delegation
            if self.agent_cards or kwargs.get("task_id") in self.active_tasks:
                result = self._enhanced_delegate_task(
                    kwargs, context, coordination_history, agent_performance_history
                )
            else:
                result = self._delegate_task(
                    kwargs, context, coordination_history, agent_performance_history
                )
        elif action == "broadcast":
            result = self._broadcast_message(kwargs, context)
        elif action == "consensus":
            result = self._manage_consensus(kwargs, context, coordination_history)
        elif action == "coordinate":
            result = self._coordinate_workflow(kwargs, context, iteration)
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}

        # Track coordination history for cycle learning
        coordination_event = {
            "iteration": iteration,
            "action": action,
            "success": result.get("success", False),
            "timestamp": time.time(),
            "details": {k: v for k, v in result.items() if k not in ["success"]},
        }
        coordination_history.append(coordination_event)

        # Update agent performance tracking
        if action == "delegate" and result.get("success"):
            agent_id = result.get("delegated_to")
            if agent_id:
                if agent_id not in agent_performance_history:
                    agent_performance_history[agent_id] = {
                        "assignments": 0,
                        "success_rate": 1.0,
                    }
                agent_performance_history[agent_id]["assignments"] += 1

        # Add cycle-aware metadata to result
        result.update(
            {
                "cycle_info": {
                    "iteration": iteration,
                    "coordination_history_length": len(coordination_history),
                    "active_agents": len(self.registered_agents),
                    "performance_tracked_agents": len(agent_performance_history),
                }
            }
        )

        # Log progress
        if iteration % 5 == 0:  # Log every 5 iterations
            self.log_cycle_info(
                context,
                f"Coordination stats: {len(coordination_history)} events, {len(self.registered_agents)} agents",
            )

        # Persist state for next iteration
        return {
            **result,
            **self.set_cycle_state(
                {
                    "coordination_history": coordination_history[
                        -50:
                    ],  # Keep last 50 events
                    "agent_performance": agent_performance_history,
                }
            ),
        }

    def _register_agent(
        self, kwargs: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Register an agent with the coordinator."""
        agent_info = kwargs.get("agent_info", {})
        agent_id = agent_info.get("id")

        if not agent_id:
            return {"success": False, "error": "Agent ID required"}

        # Create base registration
        self.registered_agents[agent_id] = {
            "id": agent_id,
            "skills": agent_info.get("skills", []),
            "role": agent_info.get("role", "general"),
            "status": "available",
            "registered_at": time.time(),
            "task_count": 0,
            "success_rate": 1.0,
        }

        # Create default agent card if not exists
        if agent_id not in self.agent_cards:
            self.agent_cards[agent_id] = self._create_default_agent_card(
                agent_id, agent_info.get("skills", [])
            )

        return {
            "success": True,
            "agent_id": agent_id,
            "registered_agents": list(self.registered_agents.keys()),
        }

    def _delegate_task(
        self,
        kwargs: Dict[str, Any],
        context: Dict[str, Any],
        coordination_history: List[Dict],
        agent_performance: Dict,
    ) -> Dict[str, Any]:
        """Delegate task to most suitable agent with cycle-aware optimization."""
        task = kwargs.get("task", {})
        available_agents = kwargs.get("available_agents", [])
        strategy = kwargs.get("coordination_strategy", "best_match")

        if not available_agents:
            available_agents = [
                agent
                for agent in self.registered_agents.values()
                if agent["status"] == "available"
            ]

        if not available_agents:
            return {"success": False, "error": "No available agents"}

        # Use cycle-aware agent selection based on performance history
        iteration = self.get_iteration(context)

        # Select agent based on strategy with cycle learning
        if strategy == "best_match":
            selected_agent = self._find_best_match_cycle_aware(
                task, available_agents, agent_performance, iteration
            )
        elif strategy == "round_robin":
            # Cycle-aware round-robin based on iteration
            agent_index = iteration % len(available_agents)
            selected_agent = available_agents[agent_index]
        elif strategy == "auction":
            selected_agent = self._run_auction_cycle_aware(
                task, available_agents, agent_performance
            )
        else:
            selected_agent = available_agents[0]

        if not selected_agent:
            return {"success": False, "error": "No suitable agent found"}

        # Update agent status
        agent_id = selected_agent.get("id")
        if agent_id in self.registered_agents:
            self.registered_agents[agent_id]["status"] = "busy"
            self.registered_agents[agent_id]["task_count"] += 1

        return {
            "success": True,
            "delegated_to": agent_id,
            "task": task,
            "strategy": strategy,
            "agent_performance_score": agent_performance.get(agent_id, {}).get(
                "success_rate", 1.0
            ),
            "iteration": iteration,
        }

    def _broadcast_message(
        self, kwargs: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Broadcast message to relevant agents."""
        message = kwargs.get("message", {})
        target_roles = message.get("target_roles", [])
        target_skills = message.get("target_skills", [])

        recipients = []
        for agent in self.registered_agents.values():
            # Check role match
            if target_roles and agent["role"] not in target_roles:
                continue

            # Check skills match
            if target_skills:
                if not any(skill in agent["skills"] for skill in target_skills):
                    continue

            recipients.append(agent["id"])

        return {
            "success": True,
            "recipients": recipients,
            "message": message,
            "broadcast_time": time.time(),
        }

    def _manage_consensus(
        self,
        kwargs: Dict[str, Any],
        context: Dict[str, Any],
        coordination_history: List[Dict],
    ) -> Dict[str, Any]:
        """Manage consensus building among agents."""
        proposal = kwargs.get("consensus_proposal", {})
        session_id = proposal.get("session_id", str(uuid.uuid4()))

        if session_id not in self.consensus_sessions:
            self.consensus_sessions[session_id] = {
                "proposal": proposal,
                "votes": {},
                "started_at": time.time(),
                "status": "open",
            }

        session = self.consensus_sessions[session_id]

        # Handle vote
        if "vote" in kwargs:
            agent_id = kwargs.get("agent_id")
            vote = kwargs.get("vote")
            session["votes"][agent_id] = vote

        # Check if consensus reached
        total_agents = len(self.registered_agents)
        votes_cast = len(session["votes"])

        if votes_cast >= total_agents * 0.5:  # Simple majority
            yes_votes = sum(1 for v in session["votes"].values() if v)
            consensus_reached = yes_votes > votes_cast / 2

            session["status"] = "completed"
            session["result"] = "approved" if consensus_reached else "rejected"

            return {
                "success": True,
                "session_id": session_id,
                "consensus_reached": consensus_reached,
                "result": session["result"],
                "votes": session["votes"],
            }

        return {
            "success": True,
            "session_id": session_id,
            "status": session["status"],
            "votes_cast": votes_cast,
            "votes_needed": int(total_agents * 0.5),
        }

    def _coordinate_workflow(
        self, kwargs: Dict[str, Any], context: Dict[str, Any], iteration: int
    ) -> Dict[str, Any]:
        """Coordinate a multi-agent workflow."""
        workflow_spec = kwargs.get("task", {})
        steps = workflow_spec.get("steps", [])

        coordination_plan = []
        for step in steps:
            required_skills = step.get("required_skills", [])
            available_agents = [
                agent
                for agent in self.registered_agents.values()
                if any(skill in agent["skills"] for skill in required_skills)
            ]

            if available_agents:
                selected_agent = self._find_best_match(step, available_agents)
                coordination_plan.append(
                    {
                        "step": step["name"],
                        "assigned_to": selected_agent["id"],
                        "skills_matched": [
                            s for s in required_skills if s in selected_agent["skills"]
                        ],
                    }
                )
            else:
                coordination_plan.append(
                    {
                        "step": step["name"],
                        "assigned_to": None,
                        "error": "No agent with required skills",
                    }
                )

        return {
            "success": True,
            "workflow": workflow_spec.get("name", "unnamed"),
            "coordination_plan": coordination_plan,
            "total_steps": len(steps),
            "assigned_steps": sum(1 for p in coordination_plan if p.get("assigned_to")),
        }

    def _find_best_match(
        self, task: Dict[str, Any], agents: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find best matching agent for task."""
        required_skills = task.get("required_skills", [])
        if not required_skills:
            return agents[0] if agents else None

        best_agent = None
        best_score = 0

        for agent in agents:
            agent_skills = set(agent.get("skills", []))
            required_set = set(required_skills)

            # Calculate match score
            matches = agent_skills & required_set
            score = len(matches) / len(required_set) if required_set else 0

            # Consider success rate
            success_rate = agent.get("success_rate", 1.0)
            score *= success_rate

            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent

    def _run_auction(
        self, task: Dict[str, Any], agents: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Run auction-based task assignment."""
        # Simplified auction - agents bid based on their capability
        bids = []

        for agent in agents:
            # Calculate bid based on skill match and availability
            required_skills = set(task.get("required_skills", []))
            agent_skills = set(agent.get("skills", []))

            skill_match = (
                len(required_skills & agent_skills) / len(required_skills)
                if required_skills
                else 1.0
            )
            workload = 1.0 - (agent.get("task_count", 0) / 10.0)  # Lower bid if busy

            bid_value = skill_match * workload * agent.get("success_rate", 1.0)

            bids.append({"agent": agent, "bid": bid_value})

        # Select highest bidder
        if bids:
            bids.sort(key=lambda x: x["bid"], reverse=True)
            return bids[0]["agent"]

        return None

    def _find_best_match_cycle_aware(
        self,
        task: Dict[str, Any],
        agents: List[Dict[str, Any]],
        agent_performance: Dict[str, Dict],
        iteration: int,
    ) -> Optional[Dict[str, Any]]:
        """Find best matching agent using cycle-aware performance data."""
        required_skills = task.get("required_skills", [])
        if not required_skills:
            # When no specific skills required, prefer agents with better historical performance
            if agent_performance:
                best_agent = None
                best_score = 0
                for agent in agents:
                    agent_id = agent.get("id")
                    perf = agent_performance.get(
                        agent_id, {"success_rate": 1.0, "assignments": 0}
                    )
                    # Balance experience and success rate
                    experience_factor = min(
                        perf["assignments"] / 10.0, 1.0
                    )  # Max at 10 assignments
                    score = perf["success_rate"] * (0.7 + 0.3 * experience_factor)
                    if score > best_score:
                        best_score = score
                        best_agent = agent
                return best_agent or (agents[0] if agents else None)
            return agents[0] if agents else None

        best_agent = None
        best_score = 0

        for agent in agents:
            agent_id = agent.get("id")
            agent_skills = set(agent.get("skills", []))
            required_set = set(required_skills)

            # Calculate skill match score
            matches = agent_skills & required_set
            skill_score = len(matches) / len(required_set) if required_set else 0

            # Get performance history
            perf = agent_performance.get(
                agent_id, {"success_rate": 1.0, "assignments": 0}
            )
            performance_score = perf["success_rate"]

            # Experience bonus (agents with more assignments get slight preference)
            experience_bonus = min(perf["assignments"] * 0.05, 0.2)  # Max 20% bonus

            # Cycle adaptation: prefer different agents in different iterations to explore
            diversity_factor = 1.0
            if iteration > 0 and agent_performance:
                recent_assignments = sum(
                    1 for p in agent_performance.values() if p["assignments"] > 0
                )
                if recent_assignments > 0:
                    agent_usage_ratio = perf["assignments"] / recent_assignments
                    if agent_usage_ratio > 0.5:  # Over-used agent
                        diversity_factor = 0.8  # Slight penalty

            # Combined score
            final_score = (
                skill_score * performance_score * diversity_factor
            ) + experience_bonus

            if final_score > best_score:
                best_score = final_score
                best_agent = agent

        return best_agent

    def _run_auction_cycle_aware(
        self,
        task: Dict[str, Any],
        agents: List[Dict[str, Any]],
        agent_performance: Dict[str, Dict],
    ) -> Optional[Dict[str, Any]]:
        """Run auction-based task assignment with cycle-aware bidding."""
        bids = []

        for agent in agents:
            agent_id = agent.get("id")

            # Calculate bid based on skill match and availability (original logic)
            required_skills = set(task.get("required_skills", []))
            agent_skills = set(agent.get("skills", []))

            skill_match = (
                len(required_skills & agent_skills) / len(required_skills)
                if required_skills
                else 1.0
            )
            workload = 1.0 - (agent.get("task_count", 0) / 10.0)  # Lower bid if busy

            # Enhance with performance history
            perf = agent_performance.get(
                agent_id, {"success_rate": 1.0, "assignments": 0}
            )
            performance_factor = perf["success_rate"]

            # Experience factor (slight preference for experienced agents)
            experience_factor = min(
                1.0 + (perf["assignments"] * 0.02), 1.2
            )  # Max 20% boost

            bid_value = skill_match * workload * performance_factor * experience_factor

            bids.append({"agent": agent, "bid": bid_value})

        # Select highest bidder
        if bids:
            bids.sort(key=lambda x: x["bid"], reverse=True)
            return bids[0]["agent"]

        return None

    # Enhanced methods to be added to A2ACoordinatorNode

    # =========================================================================
    # ENHANCED METHODS FOR AGENT CARDS AND TASK MANAGEMENT
    # =========================================================================

    def _register_agent_with_card(
        self, kwargs: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Register an agent with a rich capability card."""
        agent_id = kwargs.get("agent_id")
        card_data = kwargs.get("agent_card")

        if not agent_id or not card_data:
            return {"success": False, "error": "agent_id and agent_card required"}

        # Create or update agent card
        if isinstance(card_data, dict):
            card = A2AAgentCard.from_dict(card_data)
        else:
            card = card_data

        self.agent_cards[agent_id] = card

        # Also register with base system for compatibility
        capabilities = [cap.name for cap in card.primary_capabilities]
        self._register_agent(
            {
                "agent_info": {
                    "id": agent_id,
                    "skills": capabilities,
                    "role": card.agent_type,
                }
            },
            context,
        )

        return {
            "success": True,
            "agent_id": agent_id,
            "capabilities_registered": len(capabilities),
            "card_version": card.version,
        }

    def _create_structured_task(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a structured task with lifecycle management."""
        task_type = kwargs.get("task_type", "research")
        name = kwargs.get("name", "")
        description = kwargs.get("description", "")
        requirements = kwargs.get("requirements", [])
        priority = kwargs.get("priority", "medium")

        # Create appropriate task type
        if task_type == "research":
            task = create_research_task(
                name=name,
                description=description,
                requirements=requirements,
                priority=TaskPriority(priority),
            )
        elif task_type == "implementation":
            task = create_implementation_task(
                name=name,
                description=description,
                requirements=requirements,
                priority=TaskPriority(priority),
            )
        elif task_type == "validation":
            parent_id = kwargs.get("parent_task_id")
            task = create_validation_task(
                name=name,
                description=description,
                requirements=requirements,
                parent_task_id=parent_id,
            )
        else:
            # Generic task
            task = A2ATask(
                name=name,
                description=description,
                requirements=requirements,
                priority=TaskPriority(priority),
            )

        # Add any additional context
        if "context" in kwargs:
            task.context.update(kwargs["context"])

        # Store task
        self.active_tasks[task.task_id] = task

        return {"success": True, "task_id": task.task_id, "task": task.to_dict()}

    def _enhanced_delegate_task(
        self,
        kwargs: Dict[str, Any],
        context: Dict[str, Any],
        coordination_history: List[Dict],
        agent_performance_history: Dict[str, Dict],
    ) -> Dict[str, Any]:
        """Enhanced delegation using agent cards for better matching."""
        task_id = kwargs.get("task_id")
        task_dict = kwargs.get("task", {})

        # Check if this is a structured task
        if task_id and task_id in self.active_tasks:
            task = self.active_tasks[task_id]

            # Validate task is ready
            is_valid, issues = TaskValidator.validate_for_assignment(task)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Task not ready for assignment: {', '.join(issues)}",
                }

            # Find best agents using cards
            best_agents = self._find_best_agents_for_task(task)

            if not best_agents:
                # Fall back to base delegation
                return self._delegate_task(
                    kwargs, context, coordination_history, agent_performance_history
                )

            # Assign to best agents
            task.assigned_to = [agent_id for agent_id, _ in best_agents[:3]]
            task.transition_to(TaskState.ASSIGNED)
            task.assigned_at = datetime.now()

            # Use first agent for delegation
            return {
                "success": True,
                "delegated_to": task.assigned_to[0],
                "task_id": task.task_id,
                "match_score": best_agents[0][1],
                "state": task.state.value,
            }

        # Not a structured task, but we can still use agent cards for better matching
        if self.agent_cards and task_dict.get("required_skills"):
            # Try to match using agent cards
            required_skills = task_dict.get("required_skills", [])

            # Find agents that match the requirements
            matching_agents = []
            for agent_id, agent_info in self.registered_agents.items():
                if agent_info["status"] == "available" and agent_id in self.agent_cards:
                    card = self.agent_cards[agent_id]
                    # Check if any capability matches the required skills
                    all_capabilities = list(card.primary_capabilities) + list(
                        card.secondary_capabilities
                    )
                    for cap in all_capabilities:
                        cap_keywords = getattr(cap, "keywords", [])
                        for req in required_skills:
                            if req.lower() in cap.name.lower() or any(
                                req.lower() in kw.lower() for kw in cap_keywords
                            ):
                                matching_agents.append(agent_id)
                                break
                        else:
                            continue
                        break

            if matching_agents:
                # Override available_agents with matched agents, adding card capabilities as skills
                enhanced_agents = []
                for agent_id in matching_agents:
                    agent_copy = dict(self.registered_agents[agent_id])
                    # Add card capabilities as skills for matching
                    if agent_id in self.agent_cards:
                        card = self.agent_cards[agent_id]
                        card_skills = [cap.name for cap in card.primary_capabilities]
                        # Merge original skills with card capabilities
                        agent_copy["skills"] = list(
                            set(agent_copy.get("skills", []) + card_skills)
                        )
                    enhanced_agents.append(agent_copy)
                kwargs["available_agents"] = enhanced_agents

        # Use base delegation which will use the available_agents if provided
        return self._delegate_task(
            kwargs, context, coordination_history, agent_performance_history
        )

    def _find_best_agents_for_task(self, task: A2ATask) -> List[Tuple[str, float]]:
        """Find best agents for a task using agent cards."""
        matches = []

        for agent_id, card in self.agent_cards.items():
            # Skip if incompatible
            if task.delegated_by and not card.is_compatible_with(task.delegated_by):
                continue

            # Calculate match score
            score = card.calculate_match_score(task.requirements)

            # Apply collaboration style bonus
            if len(task.assigned_to) > 0:
                if card.collaboration_style == CollaborationStyle.COOPERATIVE:
                    score *= 1.1
                elif card.collaboration_style == CollaborationStyle.INDEPENDENT:
                    score *= 0.9

            # Apply performance history bonus
            if card.performance.total_tasks > 10:
                score *= 0.8 + 0.2 * card.performance.success_rate

            matches.append((agent_id, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches

    def _update_task_state(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Update task state and handle transitions."""
        task_id = kwargs.get("task_id")
        new_state = kwargs.get("new_state")
        insights = kwargs.get("insights", [])
        agent_id = kwargs.get("agent_id")

        if task_id not in self.active_tasks:
            return {"success": False, "error": f"Task {task_id} not found"}

        task = self.active_tasks[task_id]

        # Handle state transition
        if new_state:
            success = task.transition_to(TaskState(new_state))
            if not success:
                return {
                    "success": False,
                    "error": f"Invalid transition from {task.state.value} to {new_state}",
                }

        # Add insights if provided
        for insight_data in insights:
            if isinstance(insight_data, dict):
                insight = Insight(
                    content=insight_data.get("content", ""),
                    insight_type=InsightType(insight_data.get("type", "analysis")),
                    confidence=insight_data.get("confidence", 0.0),
                    novelty_score=insight_data.get("novelty_score", 0.0),
                    actionability_score=insight_data.get("actionability_score", 0.0),
                    impact_score=insight_data.get("impact_score", 0.0),
                    generated_by=agent_id or "",
                    keywords=insight_data.get("keywords", []),
                )
            else:
                insight = insight_data

            task.add_insight(insight)

        # Update agent performance if we have cards
        if agent_id and agent_id in self.agent_cards:
            card = self.agent_cards[agent_id]
            card.update_performance(
                {
                    "success": task.state != TaskState.FAILED,
                    "insights": insights,
                    "quality_score": task.current_quality_score,
                }
            )

        # Check if task needs iteration
        if task.state == TaskState.AWAITING_REVIEW and task.needs_iteration:
            return {
                "success": True,
                "task_state": task.state.value,
                "needs_iteration": True,
                "current_quality": task.current_quality_score,
                "target_quality": task.target_quality_score,
                "iteration": task.current_iteration + 1,
            }

        # Move completed tasks to history
        if task.is_complete:
            self.completed_tasks.append(task)
            # Limit history size
            if len(self.completed_tasks) > self.task_history_limit:
                self.completed_tasks = self.completed_tasks[-self.task_history_limit :]
            del self.active_tasks[task_id]

        return {
            "success": True,
            "task_state": task.state.value,
            "quality_score": task.current_quality_score,
            "insights_count": len(task.insights),
        }

    def _get_task_insights(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get insights from a task."""
        task_id = kwargs.get("task_id")
        min_quality = kwargs.get("min_quality", 0.0)
        insight_type = kwargs.get("insight_type")

        # Check active tasks
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
        # Check completed tasks
        else:
            task = next((t for t in self.completed_tasks if t.task_id == task_id), None)

        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        # Filter insights
        insights = task.insights

        if min_quality > 0:
            insights = [i for i in insights if i.quality_score >= min_quality]

        if insight_type:
            type_filter = InsightType(insight_type)
            insights = [i for i in insights if i.insight_type == type_filter]

        return {
            "success": True,
            "task_id": task_id,
            "task_state": task.state.value,
            "insights": [i.to_dict() for i in insights],
            "total_insights": len(task.insights),
            "filtered_insights": len(insights),
        }

    def _match_agents_to_task(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Match agents to task requirements without delegation."""
        task_id = kwargs.get("task_id")
        requirements = kwargs.get("requirements", [])

        # Get task if ID provided
        if task_id and task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            requirements = task.requirements
        elif not requirements:
            return {
                "success": False,
                "error": "Either task_id or requirements must be provided",
            }

        # Create temporary task for matching if needed
        if not task_id:
            task = A2ATask(requirements=requirements)

        # Find matches
        matches = self._find_best_agents_for_task(task)

        # Format results
        agent_matches = []
        for agent_id, score in matches[:10]:  # Top 10 matches
            card = self.agent_cards[agent_id]
            agent_matches.append(
                {
                    "agent_id": agent_id,
                    "agent_name": card.agent_name,
                    "match_score": score,
                    "primary_capabilities": [
                        cap.name for cap in card.primary_capabilities
                    ],
                    "performance": {
                        "success_rate": card.performance.success_rate,
                        "insight_quality": card.performance.insight_quality_score,
                    },
                    "collaboration_style": card.collaboration_style.value,
                }
            )

        return {
            "success": True,
            "requirements": requirements,
            "matched_agents": agent_matches,
            "total_agents": len(self.agent_cards),
        }

    def _create_default_agent_card(
        self, agent_id: str, capabilities: List[str]
    ) -> A2AAgentCard:
        """Create a basic agent card from capability list."""
        # Guess agent type from capabilities
        if any("research" in cap.lower() for cap in capabilities):
            return create_research_agent_card(agent_id, agent_id)
        elif any(
            "code" in cap.lower() or "implement" in cap.lower() for cap in capabilities
        ):
            return create_coding_agent_card(agent_id, agent_id)
        elif any("test" in cap.lower() or "qa" in cap.lower() for cap in capabilities):
            return create_qa_agent_card(agent_id, agent_id)
        else:
            # Generic card
            return A2AAgentCard(
                agent_id=agent_id,
                agent_name=agent_id,
                agent_type="generic",
                version="1.0.0",
                primary_capabilities=[
                    Capability(
                        name=cap,
                        domain="general",
                        level=CapabilityLevel.INTERMEDIATE,
                        description=f"Capable of {cap}",
                        keywords=[cap.lower()],
                    )
                    for cap in capabilities[:3]  # Limit to 3 primary
                ],
                description=f"Agent with capabilities: {', '.join(capabilities)}",
            )
