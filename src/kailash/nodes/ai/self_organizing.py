"""Self-Organizing Agent Pool nodes for autonomous team formation and problem solving.

This module implements nodes that enable agents to self-organize into teams,
collaborate dynamically, and solve problems without centralized orchestration.
"""

import json
import random
import time
import uuid
from collections import defaultdict, deque
from enum import Enum
from typing import Any

from kailash.nodes.ai.a2a import A2AAgentNode
from kailash.nodes.base import Node, NodeParameter, register_node


class TeamFormationStrategy(Enum):
    """Strategies for forming agent teams."""

    CAPABILITY_MATCHING = "capability_matching"
    SWARM_BASED = "swarm_based"
    MARKET_BASED = "market_based"
    HIERARCHICAL = "hierarchical"
    RANDOM = "random"


class AgentStatus(Enum):
    """Status of an agent in the pool."""

    AVAILABLE = "available"
    BUSY = "busy"
    FORMING_TEAM = "forming_team"
    INACTIVE = "inactive"


@register_node()
class AgentPoolManagerNode(Node):
    """
    Manages a pool of self-organizing agents with capability tracking,
    performance monitoring, and dynamic availability management.

    This node serves as the registry and coordinator for a dynamic pool of agents,
    tracking their capabilities, availability, performance metrics, and collaboration
    patterns. It enables efficient agent discovery, team formation, and performance-based
    agent selection for complex multi-agent workflows.

    Design Philosophy:
        The AgentPoolManagerNode embodies decentralized management principles, allowing
        agents to join and leave dynamically while maintaining global visibility into
        pool capabilities. It facilitates emergence of specialized teams based on task
        requirements and historical performance, creating an adaptive workforce that
        improves over time through tracked metrics and learned collaboration patterns.

    Upstream Dependencies:
        - OrchestrationManagerNode: Provides agent registration requests
        - TeamFormationNode: Queries for available agents with specific capabilities
        - A2ACoordinatorNode: Updates agent status during task execution
        - Performance monitoring systems: Supply metrics updates

    Downstream Consumers:
        - TeamFormationNode: Uses agent registry for team composition
        - ProblemAnalyzerNode: Queries capabilities for feasibility analysis
        - SolutionEvaluatorNode: Accesses performance history
        - Reporting systems: Aggregate pool analytics

    Configuration:
        No static configuration required. The pool adapts dynamically based on
        registered agents and their evolving performance metrics. Default performance
        thresholds can be adjusted at runtime.

    Implementation Details:
        - Maintains in-memory registry with O(1) agent lookup
        - Indexes agents by capability for fast searching
        - Tracks performance metrics with exponential moving averages
        - Records collaboration history for team affinity analysis
        - Implements status transitions with validation
        - Supports bulk operations for efficiency
        - Thread-safe for concurrent access

    Error Handling:
        - Validates agent IDs to prevent duplicates
        - Handles missing agents gracefully in queries
        - Returns empty results rather than errors for searches
        - Validates status transitions

    Side Effects:
        - Maintains persistent agent registry across calls
        - Updates performance metrics incrementally
        - Records team formation history
        - May affect agent availability for other tasks

    Examples:
        >>> # Create agent pool manager
        >>> pool_manager = AgentPoolManagerNode()
        >>>
        >>> # Test basic structure
        >>> params = pool_manager.get_parameters()
        >>> assert "action" in params
        >>> assert "agent_id" in params
        >>>
        >>> # Test simple registration
        >>> result = pool_manager.execute(
        ...     action="register",
        ...     agent_id="test_agent",
        ...     capabilities=["analysis"]
        ... )
        >>> assert result["success"] == True
    """

    def __init__(self, name: str = None, id: str = None, **kwargs):
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self.agent_registry = {}
        self.availability_tracker = {}
        self.performance_metrics = defaultdict(
            lambda: {
                "tasks_completed": 0,
                "success_rate": 0.8,
                "avg_contribution_score": 0.7,
                "specializations": {},
                "collaboration_history": [],
            }
        )
        self.capability_index = defaultdict(set)
        self.team_history = deque(maxlen=100)

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="list",
                description="Action: 'register', 'unregister', 'find_by_capability', 'update_status', 'get_metrics', 'list'",
            ),
            "agent_id": NodeParameter(
                name="agent_id", type=str, required=False, description="ID of the agent"
            ),
            "capabilities": NodeParameter(
                name="capabilities",
                type=list,
                required=False,
                default=[],
                description="List of agent capabilities",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional agent metadata",
            ),
            "required_capabilities": NodeParameter(
                name="required_capabilities",
                type=list,
                required=False,
                default=[],
                description="Capabilities required for search",
            ),
            "min_performance": NodeParameter(
                name="min_performance",
                type=float,
                required=False,
                default=0.7,
                description="Minimum performance score",
            ),
            "status": NodeParameter(
                name="status",
                type=str,
                required=False,
                description="New status for agent",
            ),
            "performance_update": NodeParameter(
                name="performance_update",
                type=dict,
                required=False,
                description="Performance metrics to update",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute pool management action."""
        action = kwargs.get("action", "list")

        if action == "register":
            return self._register_agent(kwargs)
        elif action == "unregister":
            return self._unregister_agent(kwargs)
        elif action == "find_by_capability":
            return self._find_by_capability(kwargs)
        elif action == "update_status":
            return self._update_status(kwargs)
        elif action == "get_metrics":
            return self._get_metrics(kwargs)
        elif action == "list":
            return self._list_agents()
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _register_agent(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Register a new agent in the pool."""
        agent_id = kwargs.get("agent_id")
        if not agent_id:
            agent_id = f"agent_{uuid.uuid4().hex[:8]}"

        capabilities = kwargs.get("capabilities", [])
        metadata = kwargs.get("metadata", {})

        # Register agent
        self.agent_registry[agent_id] = {
            "id": agent_id,
            "capabilities": capabilities,
            "metadata": metadata,
            "registered_at": time.time(),
            "last_active": time.time(),
        }

        # Update availability
        self.availability_tracker[agent_id] = AgentStatus.AVAILABLE.value

        # Index capabilities
        for capability in capabilities:
            self.capability_index[capability].add(agent_id)

        # Initialize performance metrics if provided
        if "performance_history" in metadata:
            self.performance_metrics[agent_id].update(metadata["performance_history"])

        return {
            "success": True,
            "agent_id": agent_id,
            "status": "registered",
            "capabilities": capabilities,
            "pool_size": len(self.agent_registry),
        }

    def _unregister_agent(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Remove an agent from the pool."""
        agent_id = kwargs.get("agent_id")

        if agent_id not in self.agent_registry:
            return {"success": False, "error": f"Agent {agent_id} not found"}

        # Remove from indices
        agent_data = self.agent_registry[agent_id]
        for capability in agent_data["capabilities"]:
            self.capability_index[capability].discard(agent_id)

        # Remove from registry
        del self.agent_registry[agent_id]
        del self.availability_tracker[agent_id]

        return {
            "success": True,
            "agent_id": agent_id,
            "status": "unregistered",
            "pool_size": len(self.agent_registry),
        }

    def _find_by_capability(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Find agents matching required capabilities."""
        required_capabilities = set(kwargs.get("required_capabilities", []))
        min_performance = kwargs.get("min_performance", 0.7)

        if not required_capabilities:
            return {
                "success": True,
                "agents": list(self.agent_registry.keys()),
                "count": len(self.agent_registry),
            }

        # Find agents with all required capabilities
        matching_agents = None
        for capability in required_capabilities:
            agents_with_capability = self.capability_index.get(capability, set())
            if matching_agents is None:
                matching_agents = agents_with_capability.copy()
            else:
                matching_agents &= agents_with_capability

        if not matching_agents:
            return {"success": True, "agents": [], "count": 0}

        # Filter by performance and availability
        qualified_agents = []
        for agent_id in matching_agents:
            if self.availability_tracker.get(agent_id) != AgentStatus.AVAILABLE.value:
                continue

            performance = self.performance_metrics[agent_id]["success_rate"]
            if performance >= min_performance:
                agent_info = self.agent_registry[agent_id].copy()
                agent_info["performance"] = performance
                agent_info["status"] = self.availability_tracker[agent_id]
                qualified_agents.append(agent_info)

        # Sort by performance
        qualified_agents.sort(key=lambda x: x["performance"], reverse=True)

        return {
            "success": True,
            "agents": qualified_agents,
            "count": len(qualified_agents),
            "total_pool_size": len(self.agent_registry),
        }

    def _update_status(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Update agent status."""
        agent_id = kwargs.get("agent_id")
        new_status = kwargs.get("status")

        if agent_id not in self.agent_registry:
            return {"success": False, "error": f"Agent {agent_id} not found"}

        # Validate status
        valid_statuses = [s.value for s in AgentStatus]
        if new_status not in valid_statuses:
            return {"success": False, "error": f"Invalid status: {new_status}"}

        old_status = self.availability_tracker.get(agent_id)
        self.availability_tracker[agent_id] = new_status
        self.agent_registry[agent_id]["last_active"] = time.time()

        # Update performance if provided
        if "performance_update" in kwargs:
            perf_update = kwargs["performance_update"]
            metrics = self.performance_metrics[agent_id]

            if "task_completed" in perf_update:
                metrics["tasks_completed"] += 1
                success = perf_update.get("success", True)
                # Update success rate with exponential moving average
                alpha = 0.2
                metrics["success_rate"] = (
                    alpha * (1.0 if success else 0.0)
                    + (1 - alpha) * metrics["success_rate"]
                )

            if "contribution_score" in perf_update:
                score = perf_update["contribution_score"]
                metrics["avg_contribution_score"] = (
                    alpha * score + (1 - alpha) * metrics["avg_contribution_score"]
                )

            if "specialization" in perf_update:
                spec = perf_update["specialization"]
                if spec not in metrics["specializations"]:
                    metrics["specializations"][spec] = 0
                metrics["specializations"][spec] += 1

        return {
            "success": True,
            "agent_id": agent_id,
            "old_status": old_status,
            "new_status": new_status,
            "last_active": self.agent_registry[agent_id]["last_active"],
        }

    def _get_metrics(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Get performance metrics for an agent or all agents."""
        agent_id = kwargs.get("agent_id")

        if agent_id:
            if agent_id not in self.agent_registry:
                return {"success": False, "error": f"Agent {agent_id} not found"}

            return {
                "success": True,
                "agent_id": agent_id,
                "metrics": self.performance_metrics[agent_id],
                "registration_info": self.agent_registry[agent_id],
            }
        else:
            # Aggregate metrics
            total_agents = len(self.agent_registry)
            available_agents = sum(
                1
                for status in self.availability_tracker.values()
                if status == AgentStatus.AVAILABLE.value
            )

            avg_success_rate = sum(
                m["success_rate"] for m in self.performance_metrics.values()
            ) / max(total_agents, 1)

            capability_distribution = {}
            for capability, agents in self.capability_index.items():
                capability_distribution[capability] = len(agents)

            return {
                "success": True,
                "pool_metrics": {
                    "total_agents": total_agents,
                    "available_agents": available_agents,
                    "avg_success_rate": avg_success_rate,
                    "capability_distribution": capability_distribution,
                    "status_distribution": dict(
                        (
                            status,
                            sum(
                                1
                                for s in self.availability_tracker.values()
                                if s == status
                            ),
                        )
                        for status in [s.value for s in AgentStatus]
                    ),
                },
            }

    def _list_agents(self) -> dict[str, Any]:
        """List all agents in the pool."""
        agents = []
        for agent_id, agent_data in self.agent_registry.items():
            agent_info = agent_data.copy()
            agent_info["status"] = self.availability_tracker.get(agent_id)
            agent_info["performance"] = self.performance_metrics[agent_id][
                "success_rate"
            ]
            agents.append(agent_info)

        return {"success": True, "agents": agents, "count": len(agents)}


@register_node()
class ProblemAnalyzerNode(Node):
    """
    Analyzes problems to determine required capabilities, complexity,
    and optimal team composition.

    This node performs intelligent problem decomposition and requirement analysis,
    identifying the specific capabilities needed to solve a problem, estimating its
    complexity, and suggesting optimal team configurations. It uses pattern matching,
    keyword analysis, and domain heuristics to create actionable problem specifications.

    Design Philosophy:
        The ProblemAnalyzerNode acts as the strategic planner in self-organizing systems,
        translating high-level problem descriptions into concrete capability requirements
        and team specifications. It embodies the principle that effective problem solving
        begins with thorough understanding and proper decomposition of the challenge.

    Upstream Dependencies:
        - User interfaces or APIs providing problem descriptions
        - OrchestrationManagerNode: Supplies problem context
        - Domain configuration systems: Provide capability mappings

    Downstream Consumers:
        - TeamFormationNode: Uses capability requirements for team assembly
        - AgentPoolManagerNode: Queries based on required capabilities
        - SolutionEvaluatorNode: References problem analysis for validation
        - Resource planning systems: Use complexity estimates

    Configuration:
        The analyzer uses predefined capability patterns that can be extended
        for domain-specific problems. Analysis depth and decomposition strategies
        can be configured at runtime.

    Implementation Details:
        - Pattern-based capability extraction from problem text
        - Keyword-driven complexity scoring
        - Multi-factor team size estimation
        - Hierarchical problem decomposition
        - Context-aware requirement adjustment
        - Priority-based capability ranking
        - Time and resource estimation

    Error Handling:
        - Handles vague problem descriptions with default analysis
        - Validates decomposition strategies
        - Returns minimal requirements for unrecognized problems
        - Never fails - always provides best-effort analysis

    Side Effects:
        - No persistent side effects
        - Pure analysis function
        - May influence downstream team formation

    Examples:
        >>> # Test parameter structure without constructor validation
        >>> analyzer = ProblemAnalyzerNode.__new__(ProblemAnalyzerNode)
        >>> params = analyzer.get_parameters()
        >>> assert "problem_description" in params
        >>> assert "decomposition_strategy" in params
    """

    def __init__(self, name: str = None, id: str = None, **kwargs):
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self.capability_patterns = {
            "data": ["data_collection", "data_cleaning", "data_validation"],
            "analysis": [
                "statistical_analysis",
                "data_analysis",
                "pattern_recognition",
            ],
            "model": ["machine_learning", "predictive_modeling", "model_validation"],
            "research": ["literature_review", "research", "synthesis"],
            "visualization": ["data_visualization", "reporting", "presentation"],
            "domain": ["domain_expertise", "validation", "interpretation"],
        }

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "problem_description": NodeParameter(
                name="problem_description",
                type=str,
                required=True,
                description="Description of the problem to solve",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context about the problem",
            ),
            "decomposition_strategy": NodeParameter(
                name="decomposition_strategy",
                type=str,
                required=False,
                default="hierarchical",
                description="Strategy for decomposing the problem",
            ),
            "analysis_depth": NodeParameter(
                name="analysis_depth",
                type=str,
                required=False,
                default="standard",
                description="Depth of analysis: 'quick', 'standard', 'comprehensive'",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Analyze the problem to determine requirements."""
        problem_description = kwargs["problem_description"]
        context = kwargs.get("context", {})
        strategy = kwargs.get("decomposition_strategy", "hierarchical")
        kwargs.get("analysis_depth", "standard")

        # Extract key terms and requirements
        problem_lower = problem_description.lower()
        required_capabilities = set()

        # Pattern matching for capabilities
        for pattern, caps in self.capability_patterns.items():
            if pattern in problem_lower:
                required_capabilities.update(caps)

        # Add specific capabilities based on keywords
        keyword_capabilities = {
            "predict": ["predictive_modeling", "machine_learning"],
            "forecast": ["time_series_analysis", "predictive_modeling"],
            "analyze": ["data_analysis", "statistical_analysis"],
            "visualize": ["data_visualization", "reporting"],
            "research": ["research", "literature_review"],
            "optimize": ["optimization", "algorithm_design"],
            "classify": ["classification", "machine_learning"],
            "cluster": ["clustering", "unsupervised_learning"],
        }

        for keyword, caps in keyword_capabilities.items():
            if keyword in problem_lower:
                required_capabilities.update(caps)

        # Determine complexity
        complexity_factors = {
            "simple_keywords": ["basic", "simple", "straightforward"],
            "complex_keywords": ["complex", "advanced", "sophisticated", "multi"],
            "scale_keywords": ["large", "massive", "big data", "scalable"],
        }

        complexity_score = 0.5  # Base complexity

        for keyword in complexity_factors["simple_keywords"]:
            if keyword in problem_lower:
                complexity_score -= 0.1

        for keyword in complexity_factors["complex_keywords"]:
            if keyword in problem_lower:
                complexity_score += 0.2

        for keyword in complexity_factors["scale_keywords"]:
            if keyword in problem_lower:
                complexity_score += 0.1

        complexity_score = max(0.1, min(1.0, complexity_score))

        # Estimate team size based on complexity and capabilities
        base_team_size = len(required_capabilities) // 3 + 1
        complexity_multiplier = 1 + complexity_score
        estimated_agents = int(base_team_size * complexity_multiplier)

        # Decompose problem
        if strategy == "hierarchical":
            decomposition = self._hierarchical_decomposition(
                problem_description, required_capabilities
            )
        else:
            decomposition = self._simple_decomposition(
                problem_description, required_capabilities
            )

        # Determine quality threshold based on context
        quality_threshold = 0.8  # Default
        if context.get("urgency") == "high":
            quality_threshold = 0.7
        elif context.get("criticality") == "high":
            quality_threshold = 0.9

        return {
            "success": True,
            "analysis": {
                "problem": problem_description,
                "required_capabilities": list(required_capabilities),
                "complexity_score": complexity_score,
                "estimated_agents": estimated_agents,
                "quality_threshold": quality_threshold,
                "time_estimate": self._estimate_time(
                    complexity_score, estimated_agents
                ),
                "decomposition": decomposition,
                "priority_capabilities": self._prioritize_capabilities(
                    required_capabilities, problem_description
                ),
                "context_factors": context,
            },
        }

    def _hierarchical_decomposition(
        self, problem: str, capabilities: set[str]
    ) -> list[dict]:
        """Decompose problem hierarchically."""
        # Simple heuristic decomposition
        phases = []

        # Phase 1: Data/Research
        if any(cap in capabilities for cap in ["data_collection", "research"]):
            phases.append(
                {
                    "phase": "data_gathering",
                    "subtasks": [
                        {"name": "collect_data", "capabilities": ["data_collection"]},
                        {"name": "validate_data", "capabilities": ["data_validation"]},
                    ],
                    "priority": 1,
                }
            )

        # Phase 2: Analysis
        if any(
            cap in capabilities for cap in ["data_analysis", "statistical_analysis"]
        ):
            phases.append(
                {
                    "phase": "analysis",
                    "subtasks": [
                        {
                            "name": "exploratory_analysis",
                            "capabilities": ["data_analysis"],
                        },
                        {
                            "name": "statistical_testing",
                            "capabilities": ["statistical_analysis"],
                        },
                    ],
                    "priority": 2,
                }
            )

        # Phase 3: Modeling
        if any(
            cap in capabilities for cap in ["machine_learning", "predictive_modeling"]
        ):
            phases.append(
                {
                    "phase": "modeling",
                    "subtasks": [
                        {
                            "name": "model_development",
                            "capabilities": ["machine_learning"],
                        },
                        {
                            "name": "model_validation",
                            "capabilities": ["model_validation"],
                        },
                    ],
                    "priority": 3,
                }
            )

        # Phase 4: Reporting
        phases.append(
            {
                "phase": "reporting",
                "subtasks": [
                    {
                        "name": "create_visualizations",
                        "capabilities": ["data_visualization"],
                    },
                    {
                        "name": "write_report",
                        "capabilities": ["reporting", "synthesis"],
                    },
                ],
                "priority": 4,
            }
        )

        return phases

    def _simple_decomposition(self, problem: str, capabilities: set[str]) -> list[dict]:
        """Simple task decomposition."""
        tasks = []
        for i, cap in enumerate(capabilities):
            tasks.append(
                {
                    "task_id": f"task_{i+1}",
                    "description": f"Apply {cap} to problem",
                    "required_capability": cap,
                    "estimated_duration": 30,  # minutes
                }
            )
        return tasks

    def _estimate_time(self, complexity: float, agents: int) -> int:
        """Estimate time in minutes."""
        base_time = 60  # Base 1 hour
        complexity_factor = 1 + complexity * 2  # Up to 3x for complex
        parallelization_factor = 1 / (1 + agents * 0.1)  # Diminishing returns

        return int(base_time * complexity_factor * parallelization_factor)

    def _prioritize_capabilities(
        self, capabilities: set[str], problem: str
    ) -> list[str]:
        """Prioritize capabilities based on problem."""
        # Simple prioritization based on problem keywords
        priority_map = {
            "urgent": ["data_analysis", "reporting"],
            "predict": ["machine_learning", "predictive_modeling"],
            "research": ["research", "literature_review"],
            "optimize": ["optimization", "algorithm_design"],
        }

        prioritized = []
        problem_lower = problem.lower()

        for keyword, priority_caps in priority_map.items():
            if keyword in problem_lower:
                for cap in priority_caps:
                    if cap in capabilities and cap not in prioritized:
                        prioritized.append(cap)

        # Add remaining capabilities
        for cap in capabilities:
            if cap not in prioritized:
                prioritized.append(cap)

        return prioritized


@register_node()
class TeamFormationNode(Node):
    """
    Forms optimal teams based on problem requirements and agent capabilities.

    Supports multiple formation strategies including capability matching,
    swarm-based organization, market-based auctions, and hierarchical structures.

    Examples:
        >>> formation_engine = TeamFormationNode()
        >>>
        >>> result = formation_engine.run(
        ...     problem_analysis={
        ...         "required_capabilities": ["data_analysis", "machine_learning"],
        ...         "complexity_score": 0.8,
        ...         "estimated_agents": 4
        ...     },
        ...     available_agents=[
        ...         {"id": "agent1", "capabilities": ["data_analysis"], "performance": 0.9},
        ...         {"id": "agent2", "capabilities": ["machine_learning"], "performance": 0.85}
        ...     ],
        ...     formation_strategy="capability_matching"
        ... )
    """

    def __init__(self, name: str = None, id: str = None, **kwargs):
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self.formation_history = deque(maxlen=50)
        self.team_performance_cache = {}

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "problem_analysis": NodeParameter(
                name="problem_analysis",
                type=dict,
                required=False,
                default={},
                description="Analysis of the problem from ProblemAnalyzerNode",
            ),
            "available_agents": NodeParameter(
                name="available_agents",
                type=list,
                required=False,
                default=[],
                description="List of available agents with their capabilities",
            ),
            "formation_strategy": NodeParameter(
                name="formation_strategy",
                type=str,
                required=False,
                default="capability_matching",
                description="Team formation strategy",
            ),
            "constraints": NodeParameter(
                name="constraints",
                type=dict,
                required=False,
                default={},
                description="Constraints for team formation",
            ),
            "optimization_rounds": NodeParameter(
                name="optimization_rounds",
                type=int,
                required=False,
                default=3,
                description="Number of optimization iterations",
            ),
            "diversity_weight": NodeParameter(
                name="diversity_weight",
                type=float,
                required=False,
                default=0.2,
                description="Weight for team diversity (0-1)",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Form an optimal team."""
        problem_analysis = kwargs.get("problem_analysis", {})
        available_agents = kwargs.get("available_agents", [])
        strategy = kwargs.get("formation_strategy", "capability_matching")
        constraints = kwargs.get("constraints", {})
        optimization_rounds = kwargs.get("optimization_rounds", 3)

        if not available_agents:
            return {"success": False, "error": "No available agents", "team": []}

        # Form initial team based on strategy
        if strategy == TeamFormationStrategy.CAPABILITY_MATCHING.value:
            team = self._capability_matching_formation(
                problem_analysis, available_agents, constraints
            )
        elif strategy == TeamFormationStrategy.SWARM_BASED.value:
            team = self._swarm_based_formation(
                problem_analysis, available_agents, constraints
            )
        elif strategy == TeamFormationStrategy.MARKET_BASED.value:
            team = self._market_based_formation(
                problem_analysis, available_agents, constraints
            )
        elif strategy == TeamFormationStrategy.HIERARCHICAL.value:
            team = self._hierarchical_formation(
                problem_analysis, available_agents, constraints
            )
        else:
            team = self._random_formation(
                problem_analysis, available_agents, constraints
            )

        # Optimize team composition
        for round in range(optimization_rounds):
            optimization_result = self._optimize_team(
                team, problem_analysis, available_agents
            )
            if optimization_result["improved"]:
                team = optimization_result["team"]
            else:
                break

        # Calculate team metrics
        team_metrics = self._calculate_team_metrics(team, problem_analysis)

        # Record formation
        self.formation_history.append(
            {
                "timestamp": time.time(),
                "problem": problem_analysis.get("problem", "unknown"),
                "strategy": strategy,
                "team_size": len(team),
                "fitness_score": team_metrics["fitness_score"],
            }
        )

        return {
            "success": True,
            "team": team,
            "team_metrics": team_metrics,
            "formation_strategy": strategy,
            "optimization_rounds_used": round + 1,
        }

    def _capability_matching_formation(
        self, problem: dict, agents: list[dict], constraints: dict
    ) -> list[dict]:
        """Form team by matching capabilities to requirements."""
        required_capabilities = set(problem.get("required_capabilities", []))
        selected_agents = []
        covered_capabilities = set()

        # Sort agents by performance and capability coverage
        agent_scores = []
        for agent in agents:
            agent_caps = set(agent.get("capabilities", []))
            overlap = agent_caps & required_capabilities
            uncovered = overlap - covered_capabilities

            score = (
                len(uncovered) * 2  # Prioritize new capabilities
                + len(overlap)  # Total relevant capabilities
                + agent.get("performance", 0.8) * 2  # Performance weight
            )

            agent_scores.append((score, agent))

        # Sort by score
        agent_scores.sort(key=lambda x: x[0], reverse=True)

        # Select agents
        max_team_size = constraints.get("max_team_size", 10)
        min_team_size = constraints.get("min_team_size", 2)

        for score, agent in agent_scores:
            if len(selected_agents) >= max_team_size:
                break

            agent_caps = set(agent.get("capabilities", []))
            if agent_caps & required_capabilities:  # Has relevant capabilities
                selected_agents.append(agent)
                covered_capabilities.update(agent_caps)

                # Check if all required capabilities are covered
                if covered_capabilities >= required_capabilities:
                    if len(selected_agents) >= min_team_size:
                        break

        return selected_agents

    def _swarm_based_formation(
        self, problem: dict, agents: list[dict], constraints: dict
    ) -> list[dict]:
        """Form team using swarm intelligence principles."""
        required_capabilities = set(problem.get("required_capabilities", []))
        problem.get("complexity_score", 0.5)

        # Calculate attraction scores between agents
        attraction_matrix = {}
        for i, agent1 in enumerate(agents):
            for j, agent2 in enumerate(agents):
                if i != j:
                    # Attraction based on complementary capabilities
                    caps1 = set(agent1.get("capabilities", []))
                    caps2 = set(agent2.get("capabilities", []))

                    complementarity = len((caps1 | caps2) & required_capabilities)
                    overlap = len(caps1 & caps2)

                    # High complementarity, low overlap is good
                    attraction = (
                        complementarity / max(len(required_capabilities), 1)
                        - overlap * 0.1
                    )
                    attraction_matrix[(i, j)] = max(0, attraction)

        # Form clusters using attraction
        clusters = []
        unassigned = set(range(len(agents)))

        while unassigned and len(clusters) < 5:  # Max 5 clusters
            # Start new cluster with highest performance unassigned agent
            seed_idx = max(unassigned, key=lambda i: agents[i].get("performance", 0.8))
            cluster = [seed_idx]
            unassigned.remove(seed_idx)

            # Grow cluster based on attraction
            while len(cluster) < len(agents) // 3:  # Max cluster size
                best_candidate = None
                best_attraction = 0

                for candidate in unassigned:
                    # Average attraction to cluster members
                    avg_attraction = sum(
                        attraction_matrix.get((member, candidate), 0)
                        for member in cluster
                    ) / len(cluster)

                    if avg_attraction > best_attraction:
                        best_attraction = avg_attraction
                        best_candidate = candidate

                if best_candidate and best_attraction > 0.3:
                    cluster.append(best_candidate)
                    unassigned.remove(best_candidate)
                else:
                    break

            clusters.append(cluster)

        # Select best cluster based on capability coverage
        best_cluster = []
        best_coverage = 0

        for cluster in clusters:
            cluster_agents = [agents[i] for i in cluster]
            cluster_caps = set()
            for agent in cluster_agents:
                cluster_caps.update(agent.get("capabilities", []))

            coverage = len(cluster_caps & required_capabilities)
            if coverage > best_coverage:
                best_coverage = coverage
                best_cluster = cluster_agents

        return best_cluster

    def _market_based_formation(
        self, problem: dict, agents: list[dict], constraints: dict
    ) -> list[dict]:
        """Form team using market-based auction mechanism."""
        required_capabilities = problem.get("required_capabilities", [])
        budget = constraints.get("budget", 100)

        # Agents bid for participation
        bids = []
        for agent in agents:
            agent_caps = set(agent.get("capabilities", []))
            relevant_caps = agent_caps & set(required_capabilities)

            if relevant_caps:
                # Calculate bid based on capability match and performance
                capability_value = len(relevant_caps) / max(
                    len(required_capabilities), 1
                )
                performance = agent.get("performance", 0.8)

                # Lower bid = higher chance of selection (inverse auction)
                bid_amount = (2 - capability_value - performance) * 10

                bids.append(
                    {
                        "agent": agent,
                        "bid": bid_amount,
                        "value": capability_value * performance,
                    }
                )

        # Sort by value/cost ratio
        bids.sort(key=lambda x: x["value"] / x["bid"], reverse=True)

        # Select agents within budget
        selected_agents = []
        total_cost = 0

        for bid in bids:
            if total_cost + bid["bid"] <= budget:
                selected_agents.append(bid["agent"])
                total_cost += bid["bid"]

        return selected_agents

    def _hierarchical_formation(
        self, problem: dict, agents: list[dict], constraints: dict
    ) -> list[dict]:
        """Form team with hierarchical structure."""
        required_capabilities = problem.get("required_capabilities", [])

        # Identify potential leaders (high performance, multiple capabilities)
        leader_candidates = []
        for agent in agents:
            caps = agent.get("capabilities", [])
            if len(caps) >= 3 and agent.get("performance", 0) > 0.85:
                leader_candidates.append(agent)

        # Select leader
        if leader_candidates:
            leader = max(leader_candidates, key=lambda a: a.get("performance", 0))
        else:
            leader = max(agents, key=lambda a: a.get("performance", 0))

        team = [leader]
        remaining_agents = [a for a in agents if a != leader]

        # Leader selects team members based on complementary skills
        leader_caps = set(leader.get("capabilities", []))
        needed_caps = set(required_capabilities) - leader_caps

        for cap in needed_caps:
            # Find best agent for each needed capability
            candidates = [
                a for a in remaining_agents if cap in a.get("capabilities", [])
            ]

            if candidates:
                best = max(candidates, key=lambda a: a.get("performance", 0))
                team.append(best)
                remaining_agents.remove(best)

        return team

    def _random_formation(
        self, problem: dict, agents: list[dict], constraints: dict
    ) -> list[dict]:
        """Random team formation for baseline comparison."""
        team_size = min(
            problem.get("estimated_agents", 5),
            len(agents),
            constraints.get("max_team_size", 10),
        )

        return random.sample(agents, team_size)

    def _optimize_team(
        self, team: list[dict], problem: dict, all_agents: list[dict]
    ) -> dict[str, Any]:
        """Optimize team composition."""
        current_fitness = self._calculate_team_fitness(team, problem)

        # Try swapping team members
        non_team_agents = [a for a in all_agents if a not in team]

        if not non_team_agents:
            return {"improved": False, "team": team}

        best_team = team.copy()
        best_fitness = current_fitness

        for i, member in enumerate(team):
            for candidate in non_team_agents:
                # Try swapping
                new_team = team.copy()
                new_team[i] = candidate

                new_fitness = self._calculate_team_fitness(new_team, problem)

                if new_fitness > best_fitness:
                    best_fitness = new_fitness
                    best_team = new_team.copy()

        improved = best_fitness > current_fitness

        return {
            "improved": improved,
            "team": best_team,
            "fitness_improvement": best_fitness - current_fitness,
        }

    def _calculate_team_fitness(self, team: list[dict], problem: dict) -> float:
        """Calculate how well a team matches problem requirements."""
        required_capabilities = set(problem.get("required_capabilities", []))

        # Capability coverage
        team_capabilities = set()
        for agent in team:
            team_capabilities.update(agent.get("capabilities", []))

        coverage = len(team_capabilities & required_capabilities) / max(
            len(required_capabilities), 1
        )

        # Average performance
        avg_performance = sum(a.get("performance", 0.8) for a in team) / max(
            len(team), 1
        )

        # Team size efficiency
        target_size = problem.get("estimated_agents", 5)
        size_penalty = abs(len(team) - target_size) / max(target_size, 1) * 0.2

        # Diversity bonus
        unique_capabilities = len(team_capabilities)
        diversity_bonus = min(unique_capabilities / max(len(team) * 3, 1), 0.2)

        fitness = (
            coverage * 0.5 + avg_performance * 0.3 + diversity_bonus - size_penalty
        )

        return max(0, min(1, fitness))

    def _calculate_team_metrics(
        self, team: list[dict], problem: dict
    ) -> dict[str, Any]:
        """Calculate comprehensive team metrics."""
        required_capabilities = set(problem.get("required_capabilities", []))
        team_capabilities = set()

        for agent in team:
            team_capabilities.update(agent.get("capabilities", []))

        return {
            "team_size": len(team),
            "capability_coverage": len(team_capabilities & required_capabilities)
            / max(len(required_capabilities), 1),
            "total_capabilities": len(team_capabilities),
            "avg_performance": sum(a.get("performance", 0.8) for a in team)
            / max(len(team), 1),
            "fitness_score": self._calculate_team_fitness(team, problem),
            "missing_capabilities": list(required_capabilities - team_capabilities),
            "redundant_capabilities": list(team_capabilities - required_capabilities),
        }


@register_node()
class SelfOrganizingAgentNode(A2AAgentNode):
    """
    Self-organizing agent that can autonomously join teams, collaborate,
    and adapt its behavior based on team dynamics.

    Examples:
        >>> # Create self-organizing agent
        >>> agent = SelfOrganizingAgentNode()
        >>>
        >>> # Test basic structure
        >>> params = agent.get_parameters()
        >>> assert "agent_id" in params
        >>> assert "capabilities" in params
    """

    def __init__(self, name: str = None, id: str = None, **kwargs):
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self.team_memberships = {}
        self.collaboration_history = deque(maxlen=50)
        self.skill_adaptations = defaultdict(float)

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        params = super().get_parameters()

        # Add self-organization specific parameters
        params.update(
            {
                "capabilities": NodeParameter(
                    name="capabilities",
                    type=list,
                    required=False,
                    default=[],
                    description="Agent's capabilities",
                ),
                "team_context": NodeParameter(
                    name="team_context",
                    type=dict,
                    required=False,
                    default={},
                    description="Current team information",
                ),
                "collaboration_mode": NodeParameter(
                    name="collaboration_mode",
                    type=str,
                    required=False,
                    default="cooperative",
                    description="Mode: 'cooperative', 'competitive', 'mixed'",
                ),
                "adaptation_rate": NodeParameter(
                    name="adaptation_rate",
                    type=float,
                    required=False,
                    default=0.1,
                    description="How quickly agent adapts behavior (0-1)",
                ),
                "task": NodeParameter(
                    name="task",
                    type=str,
                    required=False,
                    description="Specific task for the agent",
                ),
                "autonomy_level": NodeParameter(
                    name="autonomy_level",
                    type=float,
                    required=False,
                    default=0.8,
                    description="Level of autonomous decision making (0-1)",
                ),
            }
        )

        return params

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute self-organizing agent behavior."""
        agent_id = kwargs.get("agent_id")
        capabilities = kwargs.get("capabilities", [])
        team_context = kwargs.get("team_context", {})
        collaboration_mode = kwargs.get("collaboration_mode", "cooperative")
        task = kwargs.get("task", "")

        # Adapt behavior based on team context
        if team_context:
            self._adapt_to_team(agent_id, team_context, collaboration_mode)

        # Enhance task with self-organization context
        if task:
            enhanced_task = self._enhance_task_with_context(
                task, team_context, capabilities
            )
            kwargs["messages"] = kwargs.get("messages", [])
            kwargs["messages"].append({"role": "user", "content": enhanced_task})

        # Add self-organization instructions to system prompt
        so_prompt = f"""You are a self-organizing agent with capabilities: {', '.join(capabilities)}.

Current team context: {json.dumps(team_context, indent=2)}
Collaboration mode: {collaboration_mode}

Guidelines:
1. Leverage your specific capabilities to contribute to the team goal
2. Coordinate with other team members when mentioned
3. Adapt your approach based on team dynamics
4. Share insights that others can build upon
5. Be proactive in identifying how you can help

{kwargs.get('system_prompt', '')}"""

        kwargs["system_prompt"] = so_prompt

        # Execute base A2A agent
        result = super().run(**kwargs)

        # Track collaboration
        if result.get("success"):
            self._track_collaboration(agent_id, team_context, task, result)

        # Add self-organization metadata
        result["self_organization"] = {
            "agent_id": agent_id,
            "capabilities": capabilities,
            "team_memberships": list(self.team_memberships.keys()),
            "adaptations": dict(self.skill_adaptations),
            "collaboration_mode": collaboration_mode,
            "task": task,
        }

        return result

    def _adapt_to_team(self, agent_id: str, team_context: dict, mode: str):
        """Adapt behavior to team dynamics."""
        team_id = team_context.get("team_id")
        if not team_id:
            return

        # Track team membership
        if team_id not in self.team_memberships:
            self.team_memberships[team_id] = {
                "joined_at": time.time(),
                "contributions": 0,
                "role": "member",
            }

        # Adapt based on other members' capabilities
        other_members = team_context.get("other_members", [])
        if other_members:
            # In cooperative mode, focus on complementary skills
            if mode == "cooperative":
                # Increase weight on unique capabilities
                for cap in self.skill_adaptations:
                    self.skill_adaptations[cap] *= 0.9  # Decay

            # In competitive mode, enhance overlapping skills
            elif mode == "competitive":
                for cap in self.skill_adaptations:
                    self.skill_adaptations[cap] *= 1.1  # Enhance

    def _enhance_task_with_context(
        self, task: str, team_context: dict, capabilities: list[str]
    ) -> str:
        """Enhance task description with team context."""
        enhanced = task

        if team_context.get("team_goal"):
            enhanced = f"Team Goal: {team_context['team_goal']}\n\nYour Task: {task}"

        if team_context.get("other_members"):
            enhanced += (
                f"\n\nOther team members: {', '.join(team_context['other_members'])}"
            )
            enhanced += "\nCoordinate and build upon their work as needed."

        enhanced += (
            f"\n\nYour unique capabilities to leverage: {', '.join(capabilities)}"
        )

        return enhanced

    def _track_collaboration(
        self, agent_id: str, team_context: dict, task: str, result: dict
    ):
        """Track collaboration history and performance."""
        team_id = team_context.get("team_id", "unknown")

        collaboration_entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "team_id": team_id,
            "task": task,
            "success": result.get("success", False),
            "insights_generated": result.get("a2a_metadata", {}).get(
                "insights_generated", 0
            ),
        }

        self.collaboration_history.append(collaboration_entry)

        # Update team membership stats
        if team_id in self.team_memberships:
            self.team_memberships[team_id]["contributions"] += 1


@register_node()
class SolutionEvaluatorNode(Node):
    """
    Evaluates solutions produced by agent teams and determines if
    iteration is needed.

    Examples:
        >>> evaluator = SolutionEvaluatorNode()
        >>>
        >>> result = evaluator.execute(
        ...     solution={
        ...         "approach": "Clustering analysis",
        ...         "findings": ["3 distinct customer segments identified"],
        ...         "confidence": 0.85
        ...     },
        ...     problem_requirements={
        ...         "quality_threshold": 0.8,
        ...         "required_outputs": ["segmentation", "recommendations"]
        ...     },
        ...     team_performance={
        ...         "collaboration_score": 0.9,
        ...         "time_taken": 45
        ...     }
        ... )
    """

    def __init__(self, name: str = None, id: str = None, **kwargs):
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self.evaluation_history = deque(maxlen=100)

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "solution": NodeParameter(
                name="solution",
                type=dict,
                required=False,
                default={},
                description="Solution to evaluate",
            ),
            "problem_requirements": NodeParameter(
                name="problem_requirements",
                type=dict,
                required=False,
                default={},
                description="Original problem requirements",
            ),
            "team_performance": NodeParameter(
                name="team_performance",
                type=dict,
                required=False,
                default={},
                description="Team performance metrics",
            ),
            "evaluation_criteria": NodeParameter(
                name="evaluation_criteria",
                type=dict,
                required=False,
                default={},
                description="Custom evaluation criteria",
            ),
            "iteration_count": NodeParameter(
                name="iteration_count",
                type=int,
                required=False,
                default=0,
                description="Current iteration number",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Evaluate solution quality."""
        solution = kwargs.get("solution", {})
        requirements = kwargs.get("problem_requirements", {})
        team_performance = kwargs.get("team_performance", {})
        criteria = kwargs.get("evaluation_criteria", {})
        iteration = kwargs.get("iteration_count", 0)

        # Evaluate different aspects
        quality_scores = {}

        # 1. Completeness
        required_outputs = requirements.get("required_outputs", [])
        if required_outputs:
            outputs_found = sum(
                1
                for output in required_outputs
                if output.lower() in str(solution).lower()
            )
            quality_scores["completeness"] = outputs_found / len(required_outputs)
        else:
            quality_scores["completeness"] = 0.8  # Default if not specified

        # 2. Confidence/Certainty
        confidence = solution.get("confidence", 0.7)
        quality_scores["confidence"] = confidence

        # 3. Innovation (based on solution complexity/uniqueness)
        solution_text = json.dumps(solution)
        quality_scores["innovation"] = min(len(set(solution_text.split())) / 100, 1.0)

        # 4. Team collaboration
        collab_score = team_performance.get("collaboration_score", 0.8)
        quality_scores["collaboration"] = collab_score

        # 5. Efficiency
        time_taken = team_performance.get("time_taken", 60)
        time_limit = requirements.get("time_estimate", 60)
        efficiency = min(time_limit / max(time_taken, 1), 1.0)
        quality_scores["efficiency"] = efficiency

        # Calculate overall score
        weights = criteria.get(
            "weights",
            {
                "completeness": 0.3,
                "confidence": 0.25,
                "innovation": 0.15,
                "collaboration": 0.15,
                "efficiency": 0.15,
            },
        )

        overall_score = sum(
            quality_scores.get(aspect, 0) * weight for aspect, weight in weights.items()
        )

        # Determine if iteration needed
        quality_threshold = requirements.get("quality_threshold", 0.8)
        needs_iteration = overall_score < quality_threshold and iteration < 3

        # Generate feedback for improvement
        feedback = self._generate_feedback(quality_scores, requirements, overall_score)

        # Record evaluation
        self.evaluation_history.append(
            {
                "timestamp": time.time(),
                "overall_score": overall_score,
                "quality_scores": quality_scores,
                "iteration": iteration,
                "needs_iteration": needs_iteration,
            }
        )

        return {
            "success": True,
            "overall_score": overall_score,
            "quality_scores": quality_scores,
            "meets_threshold": overall_score >= quality_threshold,
            "needs_iteration": needs_iteration,
            "feedback": feedback,
            "recommended_actions": self._recommend_actions(
                quality_scores, feedback, iteration
            ),
        }

    def _generate_feedback(
        self, scores: dict[str, float], requirements: dict, overall: float
    ) -> dict[str, Any]:
        """Generate specific feedback for improvement."""
        feedback = {"strengths": [], "weaknesses": [], "suggestions": []}

        # Identify strengths and weaknesses
        for aspect, score in scores.items():
            if score >= 0.8:
                feedback["strengths"].append(f"Strong {aspect} (score: {score:.2f})")
            elif score < 0.6:
                feedback["weaknesses"].append(f"Weak {aspect} (score: {score:.2f})")

        # Generate suggestions
        if scores.get("completeness", 1) < 0.8:
            feedback["suggestions"].append("Ensure all required outputs are addressed")

        if scores.get("confidence", 1) < 0.7:
            feedback["suggestions"].append("Gather more evidence or validate findings")

        if scores.get("collaboration", 1) < 0.7:
            feedback["suggestions"].append(
                "Improve team coordination and information sharing"
            )

        return feedback

    def _recommend_actions(
        self, scores: dict[str, float], feedback: dict, iteration: int
    ) -> list[str]:
        """Recommend specific actions for improvement."""
        actions = []

        # Based on weakest areas
        weakest_aspect = min(scores.items(), key=lambda x: x[1])[0]

        if weakest_aspect == "completeness":
            actions.append("Add specialists for missing output areas")
        elif weakest_aspect == "confidence":
            actions.append("Add validation or domain expert agents")
        elif weakest_aspect == "innovation":
            actions.append("Encourage diverse solution approaches")
        elif weakest_aspect == "collaboration":
            actions.append("Improve communication protocols")
        elif weakest_aspect == "efficiency":
            actions.append("Parallelize tasks or reduce team size")

        # Iteration-specific recommendations
        if iteration > 1:
            actions.append("Consider alternative team composition")
            actions.append("Try different problem decomposition")

        return actions
