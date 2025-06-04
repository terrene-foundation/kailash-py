"""
Self-Organizing Agent Patterns

This example demonstrates advanced self-organization patterns:
1. Emergent Specialization - Agents develop expertise over time
2. Dynamic Coalition Formation - Temporary teams for specific goals
3. Adaptive Topology - Team structure adapts to problem type
4. Swarm Intelligence - Collective problem solving
5. Market-Based Coordination - Economic mechanisms for task allocation

Each pattern shows different approaches to autonomous agent organization.
"""

import json
import random
import time
from collections import defaultdict, deque
from typing import Any, Dict, List

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.runtime import LocalRuntime


@register_node()
class EmergentSpecializationNode(Node):
    """
    Demonstrates how agents develop specializations based on success patterns.
    Agents that repeatedly succeed at certain tasks become experts in those areas.
    """

    def __init__(self):
        super().__init__()
        self.agent_performance_history = defaultdict(lambda: defaultdict(list))
        self.specialization_thresholds = {
            "emerging": 0.7,
            "specialized": 0.8,
            "expert": 0.9,
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "agent_id": NodeParameter(
                name="agent_id", type=str, required=True, description="ID of the agent"
            ),
            "task_type": NodeParameter(
                name="task_type",
                type=str,
                required=True,
                description="Type of task performed",
            ),
            "performance_score": NodeParameter(
                name="performance_score",
                type=float,
                required=True,
                description="Performance score (0-1)",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context about the task",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Track performance and identify emerging specializations."""
        agent_id = kwargs["agent_id"]
        task_type = kwargs["task_type"]
        score = kwargs["performance_score"]
        context = kwargs.get("context", {})

        # Record performance
        self.agent_performance_history[agent_id][task_type].append(
            {"score": score, "timestamp": time.time(), "context": context}
        )

        # Calculate specialization level
        performances = self.agent_performance_history[agent_id][task_type]
        if len(performances) >= 3:  # Need minimum history
            recent_scores = [p["score"] for p in performances[-5:]]  # Last 5 attempts
            avg_performance = sum(recent_scores) / len(recent_scores)

            # Determine specialization level
            if avg_performance >= self.specialization_thresholds["expert"]:
                level = "expert"
            elif avg_performance >= self.specialization_thresholds["specialized"]:
                level = "specialized"
            elif avg_performance >= self.specialization_thresholds["emerging"]:
                level = "emerging"
            else:
                level = "learning"

            # Check for improvement trend
            if len(recent_scores) >= 3:
                trend = (
                    "improving" if recent_scores[-1] > recent_scores[0] else "stable"
                )
            else:
                trend = "unknown"

            specialization = {
                "task_type": task_type,
                "level": level,
                "performance": avg_performance,
                "trend": trend,
                "experience": len(performances),
            }
        else:
            specialization = {
                "task_type": task_type,
                "level": "novice",
                "performance": score,
                "trend": "unknown",
                "experience": len(performances),
            }

        # Get all specializations for this agent
        all_specializations = {}
        for t_type, history in self.agent_performance_history[agent_id].items():
            if len(history) >= 3:
                scores = [p["score"] for p in history[-5:]]
                avg = sum(scores) / len(scores)
                if avg >= self.specialization_thresholds["emerging"]:
                    all_specializations[t_type] = avg

        return {
            "success": True,
            "agent_id": agent_id,
            "current_specialization": specialization,
            "all_specializations": all_specializations,
            "recommended_focus": (
                max(all_specializations.items(), key=lambda x: x[1])[0]
                if all_specializations
                else task_type
            ),
        }


@register_node()
class DynamicCoalitionNode(Node):
    """
    Demonstrates dynamic coalition formation where agents temporarily
    form groups based on shared interests or complementary capabilities.
    """

    def __init__(self):
        super().__init__()
        self.active_coalitions = {}
        self.coalition_history = deque(maxlen=50)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="form",
                description="Action: 'form', 'join', 'evaluate', 'dissolve'",
            ),
            "objective": NodeParameter(
                name="objective",
                type=dict,
                required=False,
                description="Coalition objective",
            ),
            "available_agents": NodeParameter(
                name="available_agents",
                type=list,
                required=False,
                default=[],
                description="Available agents for coalition",
            ),
            "coalition_id": NodeParameter(
                name="coalition_id",
                type=str,
                required=False,
                description="ID of existing coalition",
            ),
            "agent_proposal": NodeParameter(
                name="agent_proposal",
                type=dict,
                required=False,
                description="Agent's proposal for joining",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Manage dynamic coalition formation."""
        action = kwargs.get("action", "form")

        if action == "form":
            return self._form_coalition(kwargs)
        elif action == "join":
            return self._join_coalition(kwargs)
        elif action == "evaluate":
            return self._evaluate_coalitions()
        elif action == "dissolve":
            return self._dissolve_coalition(kwargs)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _form_coalition(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Form new coalitions based on objectives."""
        objective = kwargs.get("objective", {})
        available_agents = kwargs.get("available_agents", [])

        coalition_id = f"coalition_{len(self.active_coalitions) + 1}_{int(time.time())}"

        # Agents form coalitions based on shared interests
        coalitions = []

        # Strategy 1: Capability-based coalitions
        capability_groups = defaultdict(list)
        for agent in available_agents:
            for cap in agent.get("capabilities", []):
                if cap in objective.get("required_capabilities", []):
                    capability_groups[cap].append(agent)

        # Form coalitions for each major capability
        for capability, agents in capability_groups.items():
            if len(agents) >= 2:  # Minimum coalition size
                coalition = {
                    "id": f"{coalition_id}_{capability}",
                    "type": "capability_based",
                    "focus": capability,
                    "members": agents[:4],  # Max 4 per coalition
                    "objective": objective,
                    "formed_at": time.time(),
                    "performance": 0.0,
                }
                coalitions.append(coalition)
                self.active_coalitions[coalition["id"]] = coalition

        # Strategy 2: Interest-based coalitions (based on agent metadata)
        interest_groups = defaultdict(list)
        for agent in available_agents:
            interests = agent.get("metadata", {}).get("interests", [])
            for interest in interests:
                interest_groups[interest].append(agent)

        for interest, agents in interest_groups.items():
            if len(agents) >= 3:
                coalition = {
                    "id": f"{coalition_id}_{interest}",
                    "type": "interest_based",
                    "focus": interest,
                    "members": agents[:5],
                    "objective": objective,
                    "formed_at": time.time(),
                    "performance": 0.0,
                }
                coalitions.append(coalition)
                self.active_coalitions[coalition["id"]] = coalition

        return {
            "success": True,
            "coalitions_formed": len(coalitions),
            "coalitions": coalitions,
            "total_active": len(self.active_coalitions),
        }

    def _join_coalition(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent requests to join coalitions."""
        coalition_id = kwargs.get("coalition_id")
        agent_proposal = kwargs.get("agent_proposal", {})

        if coalition_id not in self.active_coalitions:
            return {"success": False, "error": "Coalition not found"}

        coalition = self.active_coalitions[coalition_id]

        # Evaluate if agent can join
        agent_capabilities = set(agent_proposal.get("capabilities", []))
        coalition_focus = coalition["focus"]

        # Check capability match
        if coalition_focus in agent_capabilities:
            # Add to coalition if space available
            if len(coalition["members"]) < 6:  # Max coalition size
                coalition["members"].append(agent_proposal)
                return {
                    "success": True,
                    "coalition_id": coalition_id,
                    "action": "joined",
                    "coalition_size": len(coalition["members"]),
                }
            else:
                return {"success": False, "error": "Coalition at capacity"}
        else:
            return {"success": False, "error": "Capability mismatch"}

    def _evaluate_coalitions(self) -> Dict[str, Any]:
        """Evaluate performance of active coalitions."""
        evaluations = {}

        for coalition_id, coalition in self.active_coalitions.items():
            # Mock performance evaluation
            age = time.time() - coalition["formed_at"]
            size_factor = len(coalition["members"]) / 5.0  # Optimal size is 5

            # Performance decreases over time without activity
            time_factor = max(0.5, 1.0 - age / 3600)  # Decay over 1 hour

            performance = min(1.0, size_factor * time_factor)
            coalition["performance"] = performance

            evaluations[coalition_id] = {
                "performance": performance,
                "size": len(coalition["members"]),
                "age_minutes": age / 60,
                "recommendation": "maintain" if performance > 0.7 else "reform",
            }

        return {
            "success": True,
            "evaluations": evaluations,
            "active_coalitions": len(self.active_coalitions),
        }

    def _dissolve_coalition(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Dissolve a coalition."""
        coalition_id = kwargs.get("coalition_id")

        if coalition_id not in self.active_coalitions:
            return {"success": False, "error": "Coalition not found"}

        # Move to history
        coalition = self.active_coalitions.pop(coalition_id)
        coalition["dissolved_at"] = time.time()
        coalition["duration"] = coalition["dissolved_at"] - coalition["formed_at"]
        self.coalition_history.append(coalition)

        return {
            "success": True,
            "coalition_id": coalition_id,
            "duration_minutes": coalition["duration"] / 60,
            "final_performance": coalition["performance"],
        }


@register_node()
class AdaptiveTopologyNode(Node):
    """
    Demonstrates adaptive team topology where team structure
    changes based on problem characteristics and performance.
    """

    def __init__(self):
        super().__init__()
        self.topology_templates = {
            "star": {
                "description": "Central coordinator with spokes",
                "best_for": ["coordination", "synthesis", "reporting"],
                "max_size": 7,
            },
            "mesh": {
                "description": "Full connectivity between all members",
                "best_for": ["brainstorming", "innovation", "exploration"],
                "max_size": 5,
            },
            "hierarchy": {
                "description": "Multi-level structure with clear roles",
                "best_for": ["complex_projects", "specialization", "quality_control"],
                "max_size": 12,
            },
            "pipeline": {
                "description": "Sequential processing chain",
                "best_for": ["data_processing", "manufacturing", "sequential_tasks"],
                "max_size": 8,
            },
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "problem_type": NodeParameter(
                name="problem_type",
                type=str,
                required=True,
                description="Type of problem to solve",
            ),
            "team_members": NodeParameter(
                name="team_members",
                type=list,
                required=True,
                description="List of team members",
            ),
            "performance_history": NodeParameter(
                name="performance_history",
                type=list,
                required=False,
                default=[],
                description="Previous performance with different topologies",
            ),
            "constraints": NodeParameter(
                name="constraints",
                type=dict,
                required=False,
                default={},
                description="Constraints for topology design",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Design adaptive topology for team."""
        problem_type = kwargs["problem_type"]
        team_members = kwargs["team_members"]
        performance_history = kwargs.get("performance_history", [])
        kwargs.get("constraints", {})

        # Select best topology based on problem type
        topology_scores = {}
        for topology_name, template in self.topology_templates.items():
            score = 0

            # Score based on problem type match
            if any(keyword in problem_type.lower() for keyword in template["best_for"]):
                score += 0.6

            # Score based on team size suitability
            team_size = len(team_members)
            if team_size <= template["max_size"]:
                size_ratio = team_size / template["max_size"]
                score += 0.3 * size_ratio

            # Score based on historical performance
            if performance_history:
                historical_scores = [
                    h["performance"]
                    for h in performance_history
                    if h.get("topology") == topology_name
                ]
                if historical_scores:
                    avg_historical = sum(historical_scores) / len(historical_scores)
                    score += 0.1 * avg_historical

            topology_scores[topology_name] = score

        # Select best topology
        best_topology = max(topology_scores.items(), key=lambda x: x[1])[0]

        # Create topology structure
        if best_topology == "star":
            structure = self._create_star_topology(team_members)
        elif best_topology == "mesh":
            structure = self._create_mesh_topology(team_members)
        elif best_topology == "hierarchy":
            structure = self._create_hierarchy_topology(team_members)
        elif best_topology == "pipeline":
            structure = self._create_pipeline_topology(team_members)
        else:
            structure = self._create_mesh_topology(team_members)  # Default

        # Generate communication channels
        channels = self._derive_communication_channels(structure, best_topology)

        return {
            "success": True,
            "topology": best_topology,
            "structure": structure,
            "communication_channels": channels,
            "topology_scores": topology_scores,
            "reasoning": f"Selected {best_topology} topology for {problem_type} with {len(team_members)} members",
        }

    def _create_star_topology(self, members: List[Dict]) -> Dict[str, Any]:
        """Create star topology with central coordinator."""
        # Select coordinator (highest performance or coordination capability)
        coordinator = max(
            members,
            key=lambda m: (
                m.get("performance", 0.8)
                + (0.2 if "coordination" in m.get("capabilities", []) else 0)
            ),
        )

        spokes = [m for m in members if m != coordinator]

        return {
            "type": "star",
            "coordinator": coordinator,
            "spokes": spokes,
            "roles": {
                coordinator["id"]: "coordinator",
                **{spoke["id"]: "specialist" for spoke in spokes},
            },
        }

    def _create_mesh_topology(self, members: List[Dict]) -> Dict[str, Any]:
        """Create mesh topology with full connectivity."""
        return {
            "type": "mesh",
            "members": members,
            "roles": {member["id"]: "collaborator" for member in members},
        }

    def _create_hierarchy_topology(self, members: List[Dict]) -> Dict[str, Any]:
        """Create hierarchical topology."""
        # Sort by performance for hierarchy levels
        sorted_members = sorted(
            members, key=lambda m: m.get("performance", 0.8), reverse=True
        )

        # Create 3 levels max
        if len(sorted_members) <= 3:
            levels = [sorted_members]
        elif len(sorted_members) <= 8:
            levels = [sorted_members[:2], sorted_members[2:]]  # Leaders  # Specialists
        else:
            levels = [
                sorted_members[:2],  # Top level
                sorted_members[2:5],  # Middle level
                sorted_members[5:],  # Workers
            ]

        return {
            "type": "hierarchy",
            "levels": levels,
            "roles": (
                {
                    **{m["id"]: "leader" for m in levels[0]},
                    **{m["id"]: "manager" for m in levels[1] if len(levels) > 1},
                    **{m["id"]: "specialist" for m in levels[-1] if len(levels) > 1},
                }
                if len(levels) > 1
                else {m["id"]: "leader" for m in levels[0]}
            ),
        }

    def _create_pipeline_topology(self, members: List[Dict]) -> Dict[str, Any]:
        """Create pipeline topology for sequential processing."""
        # Order members by capabilities that suggest sequence
        capability_order = [
            "data_collection",
            "data_cleaning",
            "analysis",
            "modeling",
            "validation",
            "reporting",
        ]

        ordered_members = []
        remaining_members = members.copy()

        # Order by capability sequence
        for cap in capability_order:
            for member in remaining_members[:]:
                if cap in member.get("capabilities", []):
                    ordered_members.append(member)
                    remaining_members.remove(member)
                    break

        # Add remaining members
        ordered_members.extend(remaining_members)

        return {
            "type": "pipeline",
            "sequence": ordered_members,
            "roles": {
                member["id"]: f"stage_{i+1}" for i, member in enumerate(ordered_members)
            },
        }

    def _derive_communication_channels(
        self, structure: Dict, topology: str
    ) -> List[Dict]:
        """Generate communication channels based on topology."""
        channels = []

        if topology == "star":
            coordinator_id = structure["coordinator"]["id"]
            for spoke in structure["spokes"]:
                channels.append(
                    {
                        "from": coordinator_id,
                        "to": spoke["id"],
                        "type": "bidirectional",
                        "purpose": "coordination",
                    }
                )

        elif topology == "mesh":
            members = structure["members"]
            for i, member1 in enumerate(members):
                for member2 in members[i + 1 :]:
                    channels.append(
                        {
                            "from": member1["id"],
                            "to": member2["id"],
                            "type": "bidirectional",
                            "purpose": "collaboration",
                        }
                    )

        elif topology == "hierarchy":
            levels = structure["levels"]
            for i in range(len(levels) - 1):
                for upper in levels[i]:
                    for lower in levels[i + 1]:
                        channels.append(
                            {
                                "from": upper["id"],
                                "to": lower["id"],
                                "type": "hierarchical",
                                "purpose": "supervision",
                            }
                        )

        elif topology == "pipeline":
            sequence = structure["sequence"]
            for i in range(len(sequence) - 1):
                channels.append(
                    {
                        "from": sequence[i]["id"],
                        "to": sequence[i + 1]["id"],
                        "type": "sequential",
                        "purpose": "data_flow",
                    }
                )

        return channels


def demonstrate_emergent_specialization():
    """Demonstrate how agents develop specializations over time."""
    print("\n" + "=" * 60)
    print("1. EMERGENT SPECIALIZATION PATTERN")
    print("=" * 60)

    workflow = Workflow(workflow_id="emergent_spec", name="Emergent Specialization")
    workflow.add_node("specialization_tracker", EmergentSpecializationNode())

    LocalRuntime()
    tracker = workflow._node_instances["specialization_tracker"]

    # Simulate agent performing tasks over time
    agent_id = "adaptive_agent_001"
    task_types = ["data_analysis", "machine_learning", "visualization", "research"]

    print(f"\nSimulating {agent_id} learning over 20 tasks...")

    for task_num in range(1, 21):
        # Agent has natural affinity for some tasks
        task_type = random.choice(task_types)

        # Simulate improving performance over time
        base_performance = {
            "data_analysis": 0.7,
            "machine_learning": 0.9,  # Agent is naturally good at ML
            "visualization": 0.6,
            "research": 0.5,
        }

        # Performance improves with experience
        improvement = min(0.2, task_num * 0.01)
        performance = min(
            1.0, base_performance[task_type] + improvement + random.uniform(-0.1, 0.1)
        )

        result = tracker.run(
            agent_id=agent_id,
            task_type=task_type,
            performance_score=performance,
            context={"task_number": task_num},
        )

        if task_num % 5 == 0:  # Report every 5 tasks
            print(f"\nAfter task {task_num}:")
            if result["all_specializations"]:
                print("  Emerging specializations:")
                for spec, score in result["all_specializations"].items():
                    print(f"    {spec}: {score:.2f}")
            print(f"  Recommended focus: {result['recommended_focus']}")

    print("\nFinal specialization analysis:")
    final_result = tracker.run(
        agent_id=agent_id, task_type="assessment", performance_score=0.8
    )

    print(
        f"Agent developed expertise in: {', '.join(final_result['all_specializations'].keys())}"
    )
    print(f"Top specialization: {final_result['recommended_focus']}")


def demonstrate_dynamic_coalitions():
    """Demonstrate dynamic coalition formation."""
    print("\n" + "=" * 60)
    print("2. DYNAMIC COALITION FORMATION")
    print("=" * 60)

    workflow = Workflow(workflow_id="coalitions", name="Dynamic Coalitions")
    workflow.add_node("coalition_manager", DynamicCoalitionNode())

    LocalRuntime()
    manager = workflow._node_instances["coalition_manager"]

    # Create diverse agents
    agents = [
        {
            "id": "data_scientist_1",
            "capabilities": ["data_analysis", "statistics"],
            "metadata": {"interests": ["healthcare", "research"]},
        },
        {
            "id": "data_scientist_2",
            "capabilities": ["data_analysis", "machine_learning"],
            "metadata": {"interests": ["finance", "automation"]},
        },
        {
            "id": "ml_engineer_1",
            "capabilities": ["machine_learning", "deep_learning"],
            "metadata": {"interests": ["computer_vision", "nlp"]},
        },
        {
            "id": "ml_engineer_2",
            "capabilities": ["machine_learning", "optimization"],
            "metadata": {"interests": ["finance", "trading"]},
        },
        {
            "id": "domain_expert_1",
            "capabilities": ["healthcare", "validation"],
            "metadata": {"interests": ["healthcare", "clinical_research"]},
        },
        {
            "id": "domain_expert_2",
            "capabilities": ["finance", "risk_analysis"],
            "metadata": {"interests": ["finance", "compliance"]},
        },
        {
            "id": "researcher_1",
            "capabilities": ["research", "literature_review"],
            "metadata": {"interests": ["healthcare", "methodology"]},
        },
        {
            "id": "engineer_1",
            "capabilities": ["software_engineering", "deployment"],
            "metadata": {"interests": ["automation", "scalability"]},
        },
    ]

    # Define objective
    objective = {
        "goal": "Develop predictive healthcare model",
        "required_capabilities": [
            "data_analysis",
            "machine_learning",
            "healthcare",
            "research",
        ],
        "deadline": 7,  # days
        "priority": "high",
    }

    print(f"\nObjective: {objective['goal']}")
    print(f"Required capabilities: {', '.join(objective['required_capabilities'])}")
    print(f"Available agents: {len(agents)}")

    # Form coalitions
    formation_result = manager.run(
        action="form", objective=objective, available_agents=agents
    )

    print(f"\nCoalitions formed: {formation_result['coalitions_formed']}")
    for coalition in formation_result["coalitions"]:
        print(f"\n{coalition['id']} ({coalition['type']}):")
        print(f"  Focus: {coalition['focus']}")
        print(f"  Members: {', '.join(m['id'] for m in coalition['members'])}")

    # Evaluate coalitions
    time.sleep(1)  # Simulate passage of time
    evaluation_result = manager.run(action="evaluate")

    print("\nCoalition performance evaluation:")
    for coalition_id, eval_data in evaluation_result["evaluations"].items():
        print(f"  {coalition_id}:")
        print(f"    Performance: {eval_data['performance']:.2f}")
        print(f"    Size: {eval_data['size']}")
        print(f"    Recommendation: {eval_data['recommendation']}")


def demonstrate_adaptive_topology():
    """Demonstrate adaptive team topology."""
    print("\n" + "=" * 60)
    print("3. ADAPTIVE TOPOLOGY PATTERN")
    print("=" * 60)

    workflow = Workflow(workflow_id="topology", name="Adaptive Topology")
    workflow.add_node("topology_designer", AdaptiveTopologyNode())

    LocalRuntime()
    designer = workflow._node_instances["topology_designer"]

    # Test different problem types
    problem_scenarios = [
        {
            "type": "brainstorming session for new product features",
            "members": [
                {"id": "designer", "capabilities": ["ui_design"], "performance": 0.9},
                {"id": "engineer", "capabilities": ["development"], "performance": 0.8},
                {
                    "id": "marketer",
                    "capabilities": ["market_research"],
                    "performance": 0.85,
                },
                {"id": "pm", "capabilities": ["coordination"], "performance": 0.9},
            ],
        },
        {
            "type": "complex data processing pipeline implementation",
            "members": [
                {
                    "id": "data_architect",
                    "capabilities": ["database_design"],
                    "performance": 0.95,
                },
                {
                    "id": "etl_engineer",
                    "capabilities": ["data_processing"],
                    "performance": 0.8,
                },
                {
                    "id": "data_scientist",
                    "capabilities": ["analysis"],
                    "performance": 0.9,
                },
                {
                    "id": "ml_engineer",
                    "capabilities": ["modeling"],
                    "performance": 0.85,
                },
                {"id": "devops", "capabilities": ["deployment"], "performance": 0.8},
                {"id": "qa", "capabilities": ["testing"], "performance": 0.85},
            ],
        },
        {
            "type": "research project coordination and reporting",
            "members": [
                {
                    "id": "research_lead",
                    "capabilities": ["coordination", "research"],
                    "performance": 0.95,
                },
                {
                    "id": "statistician",
                    "capabilities": ["statistics"],
                    "performance": 0.9,
                },
                {
                    "id": "domain_expert",
                    "capabilities": ["validation"],
                    "performance": 0.85,
                },
                {
                    "id": "junior_researcher",
                    "capabilities": ["research"],
                    "performance": 0.7,
                },
                {"id": "writer", "capabilities": ["documentation"], "performance": 0.8},
            ],
        },
    ]

    for i, scenario in enumerate(problem_scenarios, 1):
        print(f"\nScenario {i}: {scenario['type']}")
        print(f"Team size: {len(scenario['members'])}")

        result = designer.run(
            problem_type=scenario["type"],
            team_members=scenario["members"],
            performance_history=[],
            constraints={},
        )

        print(f"Selected topology: {result['topology']}")
        print(f"Reasoning: {result['reasoning']}")
        print(f"Communication channels: {len(result['communication_channels'])}")

        # Show structure details
        structure = result["structure"]
        if result["topology"] == "star":
            print(f"  Coordinator: {structure['coordinator']['id']}")
            print(f"  Specialists: {', '.join(s['id'] for s in structure['spokes'])}")
        elif result["topology"] == "hierarchy":
            print("  Hierarchy levels:")
            for level_idx, level in enumerate(structure["levels"]):
                print(f"    Level {level_idx + 1}: {', '.join(m['id'] for m in level)}")
        elif result["topology"] == "pipeline":
            print(
                f"  Pipeline sequence: {' → '.join(m['id'] for m in structure['sequence'])}"
            )
        else:  # mesh
            print(
                f"  All members collaborate: {', '.join(m['id'] for m in structure['members'])}"
            )


def main():
    """Run all self-organizing pattern demonstrations."""
    print("SELF-ORGANIZING AGENT PATTERNS")
    print("Demonstrating advanced autonomous organization patterns")

    # Pattern 1: Emergent Specialization
    demonstrate_emergent_specialization()

    # Pattern 2: Dynamic Coalitions
    demonstrate_dynamic_coalitions()

    # Pattern 3: Adaptive Topology
    demonstrate_adaptive_topology()

    print("\n" + "=" * 60)
    print("PATTERN SUMMARY")
    print("=" * 60)

    print("\n✓ Emergent Specialization: Agents develop expertise through experience")
    print("✓ Dynamic Coalitions: Temporary teams form based on shared interests")
    print("✓ Adaptive Topology: Team structure adapts to problem characteristics")

    print("\nThese patterns enable:")
    print("- Autonomous skill development")
    print("- Flexible team formation")
    print("- Context-aware organization")
    print("- Emergent behavior and intelligence")

    # Save pattern results
    results = {
        "timestamp": time.time(),
        "patterns_demonstrated": [
            "emergent_specialization",
            "dynamic_coalitions",
            "adaptive_topology",
        ],
        "key_insights": [
            "Agents can develop specializations through performance tracking",
            "Coalitions form naturally around shared capabilities and interests",
            "Team topology should adapt to problem characteristics",
            "Self-organization emerges from simple rules and interactions",
        ],
    }

    with open("examples/outputs/self_organizing_patterns_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(
        "\nPattern results saved to: examples/outputs/self_organizing_patterns_results.json"
    )


if __name__ == "__main__":
    main()
