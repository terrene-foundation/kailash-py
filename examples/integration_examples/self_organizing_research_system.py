"""
Self-Organizing Research System Example

Demonstrates a complete self-organizing agent pool system where:
1. Agents autonomously form teams based on problem requirements
2. Teams collaborate to solve complex research problems
3. Solutions are evaluated and refined iteratively
4. No central orchestration - agents self-organize

This example shows how to build a research system that can tackle
any research question by automatically assembling the right team.
"""

import json
import time
from typing import Dict, List, Optional

from kailash import Workflow
from kailash.nodes.ai.a2a import SharedMemoryPoolNode
from kailash.nodes.ai.self_organizing import (
    AgentPoolManagerNode,
    ProblemAnalyzerNode,
    SelfOrganizingAgentNode,
    SolutionEvaluatorNode,
    TeamFormationNode,
)
from kailash.runtime import LocalRuntime


class SelfOrganizingResearchSystem:
    """A research system where agents self-organize to solve problems."""

    def __init__(self, num_agents: int = 20):
        self.workflow = Workflow(
            workflow_id="self_organizing_research",
            name="Self-Organizing Research System",
            description="Autonomous agent teams solving research problems",
        )

        self.num_agents = num_agents
        self.agent_specializations = [
            # Data specialists
            {
                "capabilities": ["data_collection", "web_scraping", "api_integration"],
                "role": "data_collector",
            },
            {
                "capabilities": ["data_cleaning", "data_validation", "preprocessing"],
                "role": "data_engineer",
            },
            {
                "capabilities": ["database_design", "sql", "data_warehousing"],
                "role": "data_architect",
            },
            # Analysis specialists
            {
                "capabilities": [
                    "statistical_analysis",
                    "hypothesis_testing",
                    "a_b_testing",
                ],
                "role": "statistician",
            },
            {
                "capabilities": [
                    "exploratory_analysis",
                    "data_visualization",
                    "insights",
                ],
                "role": "data_analyst",
            },
            {
                "capabilities": [
                    "time_series_analysis",
                    "forecasting",
                    "trend_analysis",
                ],
                "role": "time_series_expert",
            },
            # ML/AI specialists
            {
                "capabilities": [
                    "machine_learning",
                    "model_selection",
                    "hyperparameter_tuning",
                ],
                "role": "ml_engineer",
            },
            {
                "capabilities": ["deep_learning", "neural_networks", "computer_vision"],
                "role": "dl_specialist",
            },
            {
                "capabilities": ["nlp", "text_analysis", "sentiment_analysis"],
                "role": "nlp_expert",
            },
            # Domain specialists
            {
                "capabilities": ["finance", "risk_analysis", "portfolio_optimization"],
                "role": "finance_expert",
            },
            {
                "capabilities": [
                    "healthcare",
                    "clinical_research",
                    "medical_statistics",
                ],
                "role": "healthcare_expert",
            },
            {
                "capabilities": ["marketing", "customer_analytics", "segmentation"],
                "role": "marketing_expert",
            },
            # Research specialists
            {
                "capabilities": [
                    "literature_review",
                    "research_methodology",
                    "citation_analysis",
                ],
                "role": "research_methodologist",
            },
            {
                "capabilities": [
                    "scientific_writing",
                    "report_generation",
                    "documentation",
                ],
                "role": "technical_writer",
            },
            {
                "capabilities": ["peer_review", "quality_assurance", "validation"],
                "role": "reviewer",
            },
            # Technical specialists
            {
                "capabilities": [
                    "optimization",
                    "algorithm_design",
                    "computational_efficiency",
                ],
                "role": "algorithm_specialist",
            },
            {
                "capabilities": [
                    "distributed_computing",
                    "parallel_processing",
                    "scalability",
                ],
                "role": "systems_architect",
            },
            {
                "capabilities": ["security", "privacy", "compliance"],
                "role": "security_expert",
            },
            # Communication specialists
            {
                "capabilities": ["visualization", "dashboard_design", "storytelling"],
                "role": "visualization_expert",
            },
            {
                "capabilities": [
                    "presentation",
                    "executive_summary",
                    "stakeholder_communication",
                ],
                "role": "communicator",
            },
        ]

        self._setup_infrastructure()
        self._create_agent_pool()
        self._setup_workflow_connections()

    def _setup_infrastructure(self):
        """Set up core infrastructure components."""
        # Agent Pool Manager
        self.workflow.add_node("agent_pool_manager", AgentPoolManagerNode())

        # Problem Analyzer
        self.workflow.add_node(
            "problem_analyzer",
            ProblemAnalyzerNode(),
            config={
                "analysis_depth": "comprehensive",
                "decomposition_strategy": "hierarchical",
            },
        )

        # Team Formation Engine
        self.workflow.add_node(
            "team_formation_engine",
            TeamFormationNode(),
            config={
                "formation_strategy": "capability_matching",
                "optimization_rounds": 3,
                "diversity_weight": 0.3,
            },
        )

        # Shared Memory Pools
        self.workflow.add_node("problem_memory", SharedMemoryPoolNode())

        self.workflow.add_node("solution_memory", SharedMemoryPoolNode())

        self.workflow.add_node("collaboration_memory", SharedMemoryPoolNode())

        # Solution Evaluator
        self.workflow.add_node("solution_evaluator", SolutionEvaluatorNode())

    def _create_agent_pool(self):
        """Create a diverse pool of specialized agents."""
        agent_pool_manager = self.workflow._node_instances["agent_pool_manager"]

        for i in range(self.num_agents):
            # Select specialization (cycle through available specializations)
            spec = self.agent_specializations[i % len(self.agent_specializations)]

            # Create agent
            agent_id = f"agent_{spec['role']}_{i:03d}"

            self.workflow.add_node(
                agent_id,
                SelfOrganizingAgentNode(),
                config={
                    "agent_id": agent_id,
                    "agent_role": spec["role"],
                    "provider": "mock",  # Use mock for example
                    "model": "mock-model",
                    "system_prompt": f"You are a {spec['role']} specialist.",
                    "collaboration_preference": "cooperative",
                    "autonomy_level": 0.8,
                },
            )

            # Register with pool manager
            result = agent_pool_manager.run(
                action="register",
                agent_id=agent_id,
                capabilities=spec["capabilities"],
                metadata={
                    "role": spec["role"],
                    "experience_level": ["junior", "mid", "senior"][i % 3],
                    "performance_history": {
                        "success_rate": 0.75 + (i % 4) * 0.05,
                        "avg_contribution_score": 0.7 + (i % 3) * 0.1,
                    },
                },
            )

            print(f"Registered {agent_id}: {result['status']}")

    def _setup_workflow_connections(self):
        """Connect workflow components."""
        # All agents can access all memory pools
        memory_pools = ["problem_memory", "solution_memory", "collaboration_memory"]

        for node_id in self.workflow._node_instances:
            if node_id.startswith("agent_"):
                for memory_id in memory_pools:
                    self.workflow.connect(node_id, memory_id)

    def solve_research_problem(self, problem_description: str) -> Dict:
        """Solve a research problem using self-organizing agents."""
        runtime = LocalRuntime()
        results = {
            "problem": problem_description,
            "start_time": time.time(),
            "iterations": [],
            "final_solution": None,
            "team_evolution": [],
        }

        print(f"\n{'='*60}")
        print(f"SOLVING: {problem_description}")
        print(f"{'='*60}\n")

        # Step 1: Analyze the problem
        print("1. Analyzing problem requirements...")
        analysis_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "problem_analyzer": {
                    "problem_description": problem_description,
                    "context": {
                        "urgency": "normal",
                        "domain": "research",
                        "expected_deliverables": [
                            "analysis",
                            "recommendations",
                            "visualizations",
                        ],
                    },
                }
            },
        )

        problem_analysis = analysis_result["problem_analyzer"]["analysis"]
        print(
            f"   - Required capabilities: {', '.join(problem_analysis['required_capabilities'])}"
        )
        print(f"   - Complexity score: {problem_analysis['complexity_score']:.2f}")
        print(f"   - Estimated agents needed: {problem_analysis['estimated_agents']}")

        # Write problem to shared memory
        problem_memory = self.workflow._node_instances["problem_memory"]
        problem_memory.run(
            action="write",
            agent_id="system",
            content=problem_analysis,
            tags=["problem", "requirements", "initial"],
            importance=1.0,
            segment="problem_definition",
        )

        # Step 2: Find available agents
        print("\n2. Finding available agents...")
        agent_pool_manager = self.workflow._node_instances["agent_pool_manager"]

        available_agents_result = agent_pool_manager.run(
            action="find_by_capability",
            required_capabilities=problem_analysis["required_capabilities"],
            min_performance=0.7,
        )

        available_agents = available_agents_result["agents"]
        print(f"   - Found {len(available_agents)} qualified agents")

        # Iterative solution process
        iteration = 0
        max_iterations = 3
        solution_quality = 0
        current_team = []

        while (
            iteration < max_iterations
            and solution_quality < problem_analysis["quality_threshold"]
        ):
            iteration += 1
            print(f"\n{'='*60}")
            print(f"ITERATION {iteration}")
            print(f"{'='*60}")

            iteration_data = {"iteration": iteration, "start_time": time.time()}

            # Step 3: Form or reform team
            print(f"\n3. {'Forming' if iteration == 1 else 'Reforming'} team...")

            # Use different strategies for different iterations
            strategies = ["capability_matching", "swarm_based", "market_based"]
            strategy = strategies[min(iteration - 1, len(strategies) - 1)]

            formation_result, _ = runtime.execute(
                self.workflow,
                parameters={
                    "team_formation_engine": {
                        "problem_analysis": problem_analysis,
                        "available_agents": available_agents,
                        "formation_strategy": strategy,
                        "constraints": {
                            "min_team_size": 3,
                            "max_team_size": 8,
                            "budget": 100,
                        },
                    }
                },
            )

            current_team = formation_result["team_formation_engine"]["team"]
            team_metrics = formation_result["team_formation_engine"]["team_metrics"]

            print(f"   - Strategy: {strategy}")
            print(f"   - Team size: {len(current_team)}")
            print(f"   - Team fitness: {team_metrics['fitness_score']:.2f}")
            print(
                f"   - Capability coverage: {team_metrics['capability_coverage']:.2f}"
            )

            # Record team composition
            results["team_evolution"].append(
                {
                    "iteration": iteration,
                    "team_size": len(current_team),
                    "members": [agent["id"] for agent in current_team],
                    "fitness": team_metrics["fitness_score"],
                }
            )

            # Step 4: Execute collaborative problem solving
            print(f"\n4. Team collaborating on solution...")

            # Update agent statuses
            for agent in current_team:
                agent_pool_manager.run(
                    action="update_status", agent_id=agent["id"], status="busy"
                )

            # Agents work on different aspects based on problem decomposition
            team_solutions = []

            for i, phase in enumerate(problem_analysis["decomposition"]):
                print(f"\n   Phase {i+1}: {phase['phase']}")

                # Select agents for this phase
                phase_agents = self._select_agents_for_phase(
                    current_team, phase, problem_analysis
                )

                # Execute phase
                for agent in phase_agents:
                    agent_node = self.workflow._node_instances[agent["id"]]

                    # Create task based on phase
                    task = f"Work on {phase['phase']} for: {problem_description}"

                    # Agent reads from memory
                    memories = problem_memory.run(
                        action="read",
                        agent_id=agent["id"],
                        attention_filter={
                            "tags": phase.get("subtasks", [{}])[0].get(
                                "capabilities", []
                            ),
                            "importance_threshold": 0.5,
                            "window_size": 10,
                        },
                    )

                    # Execute agent task
                    agent_result, _ = runtime.execute(
                        self.workflow,
                        parameters={
                            agent["id"]: {
                                "capabilities": agent["capabilities"],
                                "team_context": {
                                    "team_id": f"team_iter_{iteration}",
                                    "team_goal": problem_description,
                                    "other_members": [
                                        a["id"]
                                        for a in current_team
                                        if a["id"] != agent["id"]
                                    ],
                                },
                                "task": task,
                                "messages": [{"role": "user", "content": task}],
                                "memory_pool": self.workflow._node_instances[
                                    "solution_memory"
                                ],
                            }
                        },
                    )

                    if agent_result[agent["id"]].get("success"):
                        # Write solution fragment to memory
                        solution_memory = self.workflow._node_instances[
                            "solution_memory"
                        ]
                        solution_memory.run(
                            action="write",
                            agent_id=agent["id"],
                            content={
                                "phase": phase["phase"],
                                "contribution": agent_result[agent["id"]]
                                .get("response", {})
                                .get("content", ""),
                                "agent_role": agent.get("metadata", {}).get(
                                    "role", "unknown"
                                ),
                            },
                            tags=["solution", phase["phase"], agent["id"]],
                            importance=0.8,
                            segment="solutions",
                        )

                        team_solutions.append(
                            {
                                "agent": agent["id"],
                                "phase": phase["phase"],
                                "success": True,
                            }
                        )

                    print(
                        f"      - {agent['id']}: {'✓' if agent_result[agent['id']].get('success') else '✗'}"
                    )

            # Step 5: Synthesize team solutions
            print(f"\n5. Synthesizing team solutions...")

            # Read all solution fragments
            all_solutions = self.workflow._node_instances["solution_memory"].run(
                action="read",
                agent_id="synthesizer",
                attention_filter={
                    "tags": ["solution"],
                    "importance_threshold": 0.5,
                    "window_size": 50,
                },
            )

            # Create integrated solution
            integrated_solution = {
                "iteration": iteration,
                "team_size": len(current_team),
                "contributions": len(all_solutions["memories"]),
                "phases_completed": list(
                    set(
                        m["content"]["phase"]
                        for m in all_solutions["memories"]
                        if "phase" in m.get("content", {})
                    )
                ),
                "confidence": 0.7 + iteration * 0.1,  # Increases with iterations
                "approach": f"Collaborative analysis using {strategy} team formation",
                "findings": [
                    f"Analyzed problem from {len(set(m['agent_id'] for m in all_solutions['memories']))} perspectives",
                    f"Completed {len(team_solutions)} solution components",
                    f"Achieved {team_metrics['capability_coverage']:.0%} capability coverage",
                ],
            }

            # Step 6: Evaluate solution
            print(f"\n6. Evaluating solution quality...")

            evaluation_result, _ = runtime.execute(
                self.workflow,
                parameters={
                    "solution_evaluator": {
                        "solution": integrated_solution,
                        "problem_requirements": {
                            "quality_threshold": problem_analysis["quality_threshold"],
                            "required_outputs": ["analysis", "recommendations"],
                            "time_estimate": problem_analysis["time_estimate"],
                        },
                        "team_performance": {
                            "collaboration_score": len(team_solutions)
                            / max(len(current_team), 1),
                            "time_taken": time.time() - iteration_data["start_time"],
                        },
                        "iteration_count": iteration,
                    }
                },
            )

            evaluation = evaluation_result["solution_evaluator"]
            solution_quality = evaluation["overall_score"]

            print(f"   - Overall quality score: {solution_quality:.2f}")
            print(
                f"   - Meets threshold: {'Yes' if evaluation['meets_threshold'] else 'No'}"
            )
            print(f"   - Quality breakdown:")
            for aspect, score in evaluation["quality_scores"].items():
                print(f"     - {aspect}: {score:.2f}")

            # Update agent performance
            for agent in current_team:
                agent_pool_manager.run(
                    action="update_status",
                    agent_id=agent["id"],
                    status="available",
                    performance_update={
                        "task_completed": True,
                        "success": solution_quality > 0.7,
                        "contribution_score": solution_quality,
                    },
                )

            # Record iteration results
            iteration_data.update(
                {
                    "solution": integrated_solution,
                    "evaluation": evaluation,
                    "duration": time.time() - iteration_data["start_time"],
                }
            )
            results["iterations"].append(iteration_data)

            # Check if we should continue
            if evaluation["meets_threshold"]:
                print(f"\n✓ Solution meets quality threshold!")
                results["final_solution"] = integrated_solution
                break
            elif evaluation["needs_iteration"]:
                print(f"\n→ Solution needs improvement. Recommendations:")
                for action in evaluation["recommended_actions"]:
                    print(f"   - {action}")

                # Write feedback to memory for next iteration
                self.workflow._node_instances["collaboration_memory"].run(
                    action="write",
                    agent_id="evaluator",
                    content={
                        "iteration": iteration,
                        "feedback": evaluation["feedback"],
                        "recommendations": evaluation["recommended_actions"],
                    },
                    tags=["feedback", "iteration", "improvement"],
                    importance=0.9,
                    segment="feedback",
                )

        # Final summary
        results["end_time"] = time.time()
        results["total_duration"] = results["end_time"] - results["start_time"]
        results["final_quality"] = solution_quality

        return results

    def _select_agents_for_phase(
        self, team: List[Dict], phase: Dict, problem_analysis: Dict
    ) -> List[Dict]:
        """Select best agents for a specific phase."""
        phase_agents = []

        # Get required capabilities for this phase
        required_caps = set()
        for subtask in phase.get("subtasks", []):
            required_caps.update(subtask.get("capabilities", []))

        # Select agents with matching capabilities
        for agent in team:
            agent_caps = set(agent.get("capabilities", []))
            if agent_caps & required_caps:
                phase_agents.append(agent)

        # If no specific match, use top performers
        if not phase_agents:
            phase_agents = sorted(
                team, key=lambda a: a.get("performance", 0.8), reverse=True
            )[:3]

        return phase_agents

    def display_results(self, results: Dict):
        """Display comprehensive results."""
        print(f"\n{'='*60}")
        print("FINAL RESULTS")
        print(f"{'='*60}")

        print(f"\nProblem: {results['problem']}")
        print(f"Total Duration: {results['total_duration']:.1f} seconds")
        print(f"Iterations: {len(results['iterations'])}")
        print(f"Final Quality Score: {results['final_quality']:.2f}")

        print("\nTeam Evolution:")
        for team in results["team_evolution"]:
            print(
                f"  Iteration {team['iteration']}: {team['team_size']} agents (fitness: {team['fitness']:.2f})"
            )

        print("\nIteration Summary:")
        for iteration in results["iterations"]:
            print(f"\n  Iteration {iteration['iteration']}:")
            print(f"    - Duration: {iteration['duration']:.1f}s")
            print(f"    - Quality: {iteration['evaluation']['overall_score']:.2f}")
            print(f"    - Contributions: {iteration['solution']['contributions']}")

        if results["final_solution"]:
            print("\nFinal Solution:")
            print(f"  Approach: {results['final_solution']['approach']}")
            print(f"  Confidence: {results['final_solution']['confidence']:.2f}")
            print(f"  Key Findings:")
            for finding in results["final_solution"]["findings"]:
                print(f"    - {finding}")


def main():
    """Run the self-organizing research system example."""
    print("=" * 60)
    print("SELF-ORGANIZING RESEARCH SYSTEM")
    print("=" * 60)

    # Create system with 20 diverse agents
    system = SelfOrganizingResearchSystem(num_agents=20)

    # Example research problems of varying complexity
    research_problems = [
        # Simple problem
        "Analyze sales data to identify top-performing products",
        # Medium complexity
        "Predict customer churn using historical transaction data and develop retention strategies",
        # Complex problem
        "Design a comprehensive climate change impact assessment model incorporating economic, social, and environmental factors for urban planning",
    ]

    # Solve each problem
    for i, problem in enumerate(research_problems, 1):
        print(f"\n{'#'*60}")
        print(f"PROBLEM {i}/{len(research_problems)}")
        print(f"{'#'*60}")

        results = system.solve_research_problem(problem)
        system.display_results(results)

        # Save results
        output_file = f"self_organizing_results_{i}.json"
        with open(f"examples/outputs/{output_file}", "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to: examples/outputs/{output_file}")

        if i < len(research_problems):
            print("\nPress Enter to continue to next problem...")
            input()


if __name__ == "__main__":
    main()
