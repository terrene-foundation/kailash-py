"""
Simple Self-Organizing Agent Example

This example demonstrates the basic concepts of self-organizing agents:
1. Agent pool management
2. Problem analysis
3. Team formation
4. Solution evaluation

Perfect for understanding the core mechanics before diving into complex examples.
"""

import json
import time

from kailash import Workflow
from kailash.nodes.ai.self_organizing import (
    AgentPoolManagerNode,
    ProblemAnalyzerNode,
    SelfOrganizingAgentNode,
    SolutionEvaluatorNode,
    TeamFormationNode,
)
from kailash.runtime.local import LocalRuntime


def create_simple_agent_pool() -> Workflow:
    """Create a simple workflow with self-organizing components."""
    workflow = Workflow(
        workflow_id="simple_self_organizing", name="Simple Self-Organizing Example"
    )

    # Core components
    workflow.add_node("pool_manager", AgentPoolManagerNode())
    workflow.add_node("problem_analyzer", ProblemAnalyzerNode())
    workflow.add_node("team_formation", TeamFormationNode())
    workflow.add_node("evaluator", SolutionEvaluatorNode())

    # Create 6 simple agents with different specializations
    agent_specs = [
        {
            "id": "data_analyst",
            "capabilities": ["data_analysis", "statistics"],
            "role": "analyst",
        },
        {
            "id": "ml_engineer",
            "capabilities": ["machine_learning", "modeling"],
            "role": "engineer",
        },
        {
            "id": "researcher",
            "capabilities": ["research", "literature_review"],
            "role": "researcher",
        },
        {
            "id": "visualizer",
            "capabilities": ["visualization", "reporting"],
            "role": "designer",
        },
        {
            "id": "domain_expert",
            "capabilities": ["domain_expertise", "validation"],
            "role": "expert",
        },
        {
            "id": "coordinator",
            "capabilities": ["coordination", "synthesis"],
            "role": "coordinator",
        },
    ]

    for spec in agent_specs:
        workflow.add_node(
            spec["id"],
            SelfOrganizingAgentNode(),
            config={
                "agent_id": spec["id"],
                "agent_role": spec["role"],
                "provider": "mock",
                "model": "mock-model",
            },
        )

    return workflow, agent_specs


def demonstrate_pool_management(workflow: Workflow, agent_specs: list[dict]):
    """Demonstrate agent pool management capabilities."""
    print("\n" + "=" * 50)
    print("1. AGENT POOL MANAGEMENT")
    print("=" * 50)

    # Access the pool manager node directly
    pool_manager = workflow._node_instances["pool_manager"]

    # Register all agents
    print("\nRegistering agents...")
    for spec in agent_specs:
        result = pool_manager.execute(
            action="register",
            agent_id=spec["id"],
            capabilities=spec["capabilities"],
            metadata={
                "role": spec["role"],
                "experience": "mid",
                "performance_history": {
                    "success_rate": 0.8 + len(spec["capabilities"]) * 0.05
                },
            },
        )
        print(
            f"  {spec['id']}: {result['status']} (capabilities: {', '.join(spec['capabilities'])})"
        )

    # Show pool metrics
    print("\nPool metrics:")
    metrics_result = pool_manager.execute(action="get_metrics")
    pool_metrics = metrics_result["pool_metrics"]
    print(f"  Total agents: {pool_metrics['total_agents']}")
    print(f"  Available: {pool_metrics['available_agents']}")
    print(f"  Average success rate: {pool_metrics['avg_success_rate']:.2f}")

    print("\nCapability distribution:")
    for capability, count in pool_metrics["capability_distribution"].items():
        print(f"  {capability}: {count} agents")

    return pool_manager


def demonstrate_problem_analysis(workflow: Workflow):
    """Demonstrate problem analysis capabilities."""
    print("\n" + "=" * 50)
    print("2. PROBLEM ANALYSIS")
    print("=" * 50)

    runtime = LocalRuntime()

    # Test different types of problems
    problems = [
        "Analyze customer data using statistics and visualization",
        "Build a machine learning model using data analysis and modeling",
        "Research literature and coordinate team synthesis",
    ]

    for i, problem in enumerate(problems, 1):
        print(f"\nProblem {i}: {problem}")

        analysis_result, _ = runtime.execute(
            workflow,
            parameters={
                "problem_analyzer": {
                    "problem_description": problem,
                    "context": {"urgency": "normal", "domain": "business"},
                }
            },
        )

        analysis = analysis_result["problem_analyzer"]["analysis"]
        print(
            f"  Required capabilities: {', '.join(analysis['required_capabilities'])}"
        )
        print(f"  Complexity score: {analysis['complexity_score']:.2f}")
        print(f"  Estimated agents: {analysis['estimated_agents']}")
        print(f"  Time estimate: {analysis['time_estimate']} minutes")

    return analysis  # Return last analysis for team formation demo


def demonstrate_team_formation(
    workflow: Workflow, pool_manager, problem_analysis: dict
):
    """Demonstrate team formation strategies."""
    print("\n" + "=" * 50)
    print("3. TEAM FORMATION")
    print("=" * 50)

    runtime = LocalRuntime()

    # For this demo, use a custom problem that matches our agent capabilities
    demo_problem_analysis = {
        "required_capabilities": ["data_analysis", "machine_learning", "visualization"],
        "complexity_score": 0.7,
        "estimated_agents": 3,
        "time_estimate": 60,
    }

    # Get all agents from the pool
    all_agents_result = pool_manager.execute(action="list")
    all_agents = all_agents_result.get("agents", [])

    # Filter agents that have at least one matching capability
    available_agents = []
    for agent in all_agents:
        agent_caps = set(agent.get("capabilities", []))
        required_caps = set(demo_problem_analysis["required_capabilities"])
        if agent_caps & required_caps:  # Has at least one matching capability
            available_agents.append(agent)

    print(f"\nAvailable agents: {len(available_agents)}")
    for agent in available_agents:
        print(
            f"  {agent['id']}: {', '.join(agent['capabilities'])} (perf: {agent['performance']:.2f})"
        )

    # Test different formation strategies
    strategies = ["capability_matching", "swarm_based", "market_based"]

    teams = {}
    for strategy in strategies:
        print(f"\n--- {strategy.upper()} STRATEGY ---")

        formation_result, _ = runtime.execute(
            workflow,
            parameters={
                "team_formation": {
                    "problem_analysis": demo_problem_analysis,
                    "available_agents": available_agents,
                    "formation_strategy": strategy,
                    "constraints": {"min_team_size": 2, "max_team_size": 4},
                }
            },
        )

        # Debug what's in the result
        team_formation_data = formation_result.get("team_formation", {})
        if "team" not in team_formation_data:
            print(
                f"  WARNING: No team found in result. Keys: {list(team_formation_data.keys())}"
            )
            print(f"  Full result: {team_formation_data}")
            continue

        team = team_formation_data["team"]
        metrics = team_formation_data.get(
            "team_metrics", {"fitness_score": 0.0, "capability_coverage": 0.0}
        )

        print(f"Team size: {len(team)}")
        print(f"Fitness score: {metrics['fitness_score']:.2f}")
        print(f"Capability coverage: {metrics['capability_coverage']:.0%}")
        print("Team members:")
        for member in team:
            print(f"  - {member['id']}: {', '.join(member['capabilities'])}")

        teams[strategy] = team

    return teams, demo_problem_analysis


def demonstrate_collaboration(
    workflow: Workflow, teams: dict[str, list], problem_analysis: dict = None
):
    """Demonstrate agent collaboration."""
    print("\n" + "=" * 50)
    print("4. AGENT COLLABORATION")
    print("=" * 50)

    runtime = LocalRuntime()

    # Use the best team (capability_matching)
    team = teams["capability_matching"]
    task = "Analyze customer data to identify improvement opportunities"

    print(f"\nTask: {task}")
    print(f"Team: {', '.join(agent['id'] for agent in team)}")

    # Each agent works on the task
    solutions = []
    for agent in team:
        print(f"\n{agent['id']} working...")

        result, _ = runtime.execute(
            workflow,
            parameters={
                agent["id"]: {
                    "capabilities": agent["capabilities"],
                    "team_context": {
                        "team_id": "demo_team",
                        "team_goal": task,
                        "other_members": [
                            a["id"] for a in team if a["id"] != agent["id"]
                        ],
                    },
                    "task": task,
                    "messages": [{"role": "user", "content": task}],
                }
            },
        )

        if result[agent["id"]].get("success"):
            response = result[agent["id"]].get("response", {}).get("content", "")
            solutions.append(
                {
                    "agent": agent["id"],
                    "contribution": response,
                    "capabilities": agent["capabilities"],
                }
            )
            print(f"  ✓ Contribution: {response[:100]}...")
        else:
            print("  ✗ Failed")

    # Synthesize solutions
    integrated_solution = {
        "task": task,
        "team_size": len(team),
        "contributions": len(solutions),
        "approach": "Collaborative analysis using capability-matched team",
        "confidence": 0.85,
        "findings": [
            f"Combined insights from {len(solutions)} specialized agents",
            f"Leveraged capabilities: {', '.join(set(cap for sol in solutions for cap in sol['capabilities']))}",
            "Multi-perspective analysis completed",
        ],
    }

    print("\nIntegrated solution:")
    print(f"  Confidence: {integrated_solution['confidence']:.2f}")
    print(f"  Contributors: {integrated_solution['contributions']}")
    print("  Key findings:")
    for finding in integrated_solution["findings"]:
        print(f"    - {finding}")

    return integrated_solution


def demonstrate_evaluation(workflow: Workflow, solution: dict, problem_analysis: dict):
    """Demonstrate solution evaluation."""
    print("\n" + "=" * 50)
    print("5. SOLUTION EVALUATION")
    print("=" * 50)

    runtime = LocalRuntime()

    # Evaluate the solution
    evaluation_result, _ = runtime.execute(
        workflow,
        parameters={
            "evaluator": {
                "solution": solution,
                "problem_requirements": {
                    "quality_threshold": 0.8,
                    "required_outputs": ["analysis", "recommendations"],
                    "time_estimate": problem_analysis["time_estimate"],
                },
                "team_performance": {"collaboration_score": 0.9, "time_taken": 45},
                "iteration_count": 1,
            }
        },
    )

    evaluation = evaluation_result["evaluator"]

    print(f"Overall quality score: {evaluation['overall_score']:.2f}")
    print(f"Meets threshold: {'Yes' if evaluation['meets_threshold'] else 'No'}")
    print(f"Needs iteration: {'Yes' if evaluation['needs_iteration'] else 'No'}")

    print("\nQuality breakdown:")
    for aspect, score in evaluation["quality_scores"].items():
        print(f"  {aspect}: {score:.2f}")

    print("\nFeedback:")
    feedback = evaluation["feedback"]
    if feedback["strengths"]:
        print("  Strengths:")
        for strength in feedback["strengths"]:
            print(f"    + {strength}")

    if feedback["weaknesses"]:
        print("  Weaknesses:")
        for weakness in feedback["weaknesses"]:
            print(f"    - {weakness}")

    if feedback["suggestions"]:
        print("  Suggestions:")
        for suggestion in feedback["suggestions"]:
            print(f"    → {suggestion}")

    return evaluation


def main():
    """Run the simple self-organizing agent example."""
    print("SIMPLE SELF-ORGANIZING AGENT EXAMPLE")
    print("Demonstrating core concepts step by step")

    # Create the system
    workflow, agent_specs = create_simple_agent_pool()

    # Step 1: Pool Management
    pool_manager = demonstrate_pool_management(workflow, agent_specs)

    # Step 2: Problem Analysis
    problem_analysis = demonstrate_problem_analysis(workflow)

    # Step 3: Team Formation
    teams, demo_problem_analysis = demonstrate_team_formation(
        workflow, pool_manager, problem_analysis
    )

    # Step 4: Collaboration
    solution = demonstrate_collaboration(workflow, teams, demo_problem_analysis)

    # Step 5: Evaluation
    evaluation = demonstrate_evaluation(workflow, solution, problem_analysis)

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    print("\n✓ Successfully demonstrated self-organizing agents")
    print("✓ Formed teams using multiple strategies")
    print(f"✓ Achieved {evaluation['overall_score']:.0%} solution quality")
    print(
        f"✓ {'Met' if evaluation['meets_threshold'] else 'Did not meet'} quality threshold"
    )

    # Save results
    results = {
        "timestamp": time.time(),
        "problem_analysis": problem_analysis,
        "teams": {
            strategy: [
                {"id": agent["id"], "capabilities": agent["capabilities"]}
                for agent in team
            ]
            for strategy, team in teams.items()
        },
        "solution": solution,
        "evaluation": evaluation,
    }

    # Create output directory if it doesn't exist
    import os

    output_dir = "examples/outputs"
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, "self_organizing_simple_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
