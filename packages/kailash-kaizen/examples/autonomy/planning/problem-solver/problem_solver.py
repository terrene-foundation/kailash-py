"""
Problem Solver - Multi-path problem solving with Tree-of-Thoughts Agent.

This example demonstrates:
1. Multi-path exploration (5 alternative solutions)
2. Path evaluation and comparison
3. Best solution selection based on scores
4. Decision rationale logging
5. Hooks integration for path comparison

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+

Usage:
    python problem_solver.py "optimize database query performance"

    The agent will:
    - Generate 5 alternative solution paths
    - Evaluate each path independently
    - Compare paths by quality score
    - Select and execute best path
    - Provide detailed rationale
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import MemoryTransport
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookManager, HookResult


class PathComparisonHook:
    """Custom hook for comparing solution paths."""

    def __init__(self, comparison_log_path: Path):
        self.comparison_log_path = comparison_log_path
        self.comparison_log_path.parent.mkdir(parents=True, exist_ok=True)

    async def post_agent_loop(self, context: HookContext) -> HookResult:
        """Log path comparison results."""
        import json

        # Extract paths and evaluations from context
        paths = context.data.get("paths", [])
        evaluations = context.data.get("evaluations", [])
        best_path = context.data.get("best_path", {})

        comparison = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": context.agent_id,
            "trace_id": context.trace_id,
            "num_paths": len(paths),
            "evaluations": [
                {
                    "path_id": i + 1,
                    "score": eval.get("score", 0.0) if isinstance(eval, dict) else 0.0,
                    "selected": (
                        i == best_path.get("path_id", -1) - 1
                        if isinstance(best_path, dict)
                        else False
                    ),
                }
                for i, eval in enumerate(evaluations)
            ],
            "best_score": (
                best_path.get("score", 0.0) if isinstance(best_path, dict) else 0.0
            ),
        }

        with open(self.comparison_log_path, "a") as f:
            json.dump(comparison, f)
            f.write("\n")

        print(
            f"📊 Path Comparison: {len(paths)} paths evaluated, best score: {comparison['best_score']:.2f}"
        )
        return HookResult(success=True)


class ProblemSolver:
    """Problem solver with multi-path exploration pattern."""

    def __init__(
        self,
        config: ToTAgentConfig,
        control_protocol: ControlProtocol = None,
        enable_comparison_logging: bool = True,
    ):
        """
        Initialize problem solver.

        Args:
            config: Tree-of-Thoughts agent configuration
            control_protocol: Optional control protocol for progress reporting
            enable_comparison_logging: Enable path comparison logging
        """
        self.config = config
        self.control_protocol = control_protocol

        # Setup hooks for path comparison
        self.hook_manager = None
        if enable_comparison_logging:
            self.hook_manager = HookManager()
            comparison_hook = PathComparisonHook(Path("./path_comparison.jsonl"))
            self.hook_manager.register(
                HookEvent.POST_AGENT_LOOP, comparison_hook.post_agent_loop
            )

        # Create ToT agent
        self.agent = ToTAgent(
            llm_provider=config.llm_provider,
            model=config.model,
            temperature=config.temperature,
            num_paths=config.num_paths,
            evaluation_criteria=config.evaluation_criteria,
            parallel_execution=config.parallel_execution,
        )

        print("\n" + "=" * 60)
        print("🤖 PROBLEM SOLVER INITIALIZED")
        print("=" * 60)
        print(f"🔧 LLM: {config.llm_provider}/{config.model}")
        print(f"🌳 Number of Paths: {config.num_paths}")
        print(f"📊 Evaluation Criteria: {config.evaluation_criteria}")
        print(f"⚡ Parallel Execution: {config.parallel_execution}")
        print(f"📝 Comparison Logging: {enable_comparison_logging}")
        print("=" * 60 + "\n")

    async def solve_problem(self, problem: str, context: Dict = None) -> Dict:
        """
        Solve problem using multi-path exploration.

        Args:
            problem: Problem description
            context: Optional problem context (constraints, requirements)

        Returns:
            Dict with paths, evaluations, best path, and final result
        """
        print(f"\n🎯 Solving problem: {problem}\n")

        # Build problem context
        problem_context = context or {}
        problem_context["problem"] = problem

        # Report progress
        if self.control_protocol:
            await self.control_protocol.report_progress(
                message="Generating solution paths", percentage=10
            )

        try:
            # Execute ToT agent (generate → evaluate → select → execute)
            result = self.agent.run(task=problem, context=problem_context)

            # Display all paths
            paths = result.get("paths", [])
            print("\n" + "=" * 60)
            print(f"🌳 SOLUTION PATHS ({len(paths)} alternatives)")
            print("=" * 60)

            for i, path in enumerate(paths, 1):
                if isinstance(path, dict):
                    print(
                        f"\nPath {i}: {path.get('name', path.get('title', f'Path {i}'))}"
                    )
                    description = path.get("description", path.get("approach", ""))
                    if description:
                        print(
                            f"  {description[:100]}..."
                            if len(description) > 100
                            else f"  {description}"
                        )
                else:
                    print(f"\nPath {i}: {str(path)[:100]}...")

            print("=" * 60 + "\n")

            # Report progress
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message="Evaluating solution paths", percentage=50
                )

            # Display evaluations
            evaluations = result.get("evaluations", [])
            print("=" * 60)
            print("📊 PATH EVALUATIONS")
            print("=" * 60)

            # Sort evaluations by score
            sorted_evals = sorted(
                enumerate(evaluations, 1),
                key=lambda x: x[1].get("score", 0.0) if isinstance(x[1], dict) else 0.0,
                reverse=True,
            )

            for i, (path_num, evaluation) in enumerate(sorted_evals):
                if isinstance(evaluation, dict):
                    score = evaluation.get("score", 0.0)
                    is_best = i == 0
                    marker = "🏆" if is_best else "  "
                    print(f"\n{marker} Path {path_num}: Score {score:.2f}")

                    pros = evaluation.get("pros", [])
                    if pros:
                        print("  Pros:")
                        for pro in pros[:3]:  # Show first 3
                            print(f"    + {pro}")

                    cons = evaluation.get("cons", [])
                    if cons:
                        print("  Cons:")
                        for con in cons[:3]:  # Show first 3
                            print(f"    - {con}")
                else:
                    print(f"\n  Path {path_num}: {evaluation}")

            print("=" * 60 + "\n")

            # Display best path
            best_path = result.get("best_path", {})
            print("=" * 60)
            print("🏆 SELECTED BEST PATH")
            print("=" * 60)
            if isinstance(best_path, dict):
                print(f"Path ID: {best_path.get('path_id', 'N/A')}")
                print(f"Score: {best_path.get('score', 0.0):.2f}")
                print("\nRationale:")
                rationale = best_path.get("rationale", "No rationale provided")
                print(f"  {rationale}")
            else:
                print(best_path)
            print("=" * 60 + "\n")

            # Report progress
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message="Executing best path", percentage=75
                )

            # Display final result
            print("=" * 60)
            print("✅ SOLUTION")
            print("=" * 60)
            final_result = result.get("final_result", "")
            print(final_result)
            print("=" * 60 + "\n")

            # Report completion
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message="Problem solved", percentage=100
                )

            return result

        except Exception as e:
            print(f"\n❌ Error during problem solving: {e}\n")
            if self.control_protocol:
                await self.control_protocol.report_progress(
                    message=f"Problem solving failed: {e}", percentage=0
                )
            raise

    def export_solution(self, result: Dict, output_dir: Path):
        """
        Export solution analysis to file.

        Args:
            result: Solution result with paths and evaluations
            output_dir: Output directory
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = output_dir / f"solution_analysis_{timestamp}.md"

        # Build markdown report
        paths = result.get("paths", [])
        evaluations = result.get("evaluations", [])
        best_path = result.get("best_path", {})
        final_result = result.get("final_result", "")

        content = f"""# Problem Solution Analysis

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Summary

- **Paths Explored**: {len(paths)}
- **Best Path Score**: {best_path.get('score', 0.0) if isinstance(best_path, dict) else 'N/A'}
- **Evaluation Criteria**: {self.config.evaluation_criteria}

## Solution Paths

"""

        # Add all paths
        for i, path in enumerate(paths, 1):
            if isinstance(path, dict):
                content += f"### Path {i}: {path.get('name', f'Path {i}')}\n\n"
                content += f"{path.get('description', path.get('approach', 'No description'))}\n\n"
            else:
                content += f"### Path {i}\n\n{path}\n\n"

        content += "## Path Evaluations\n\n"

        # Add evaluations
        for i, evaluation in enumerate(evaluations, 1):
            if isinstance(evaluation, dict):
                score = evaluation.get("score", 0.0)
                content += f"### Path {i}: Score {score:.2f}\n\n"

                pros = evaluation.get("pros", [])
                if pros:
                    content += "**Pros:**\n"
                    for pro in pros:
                        content += f"- {pro}\n"
                    content += "\n"

                cons = evaluation.get("cons", [])
                if cons:
                    content += "**Cons:**\n"
                    for con in cons:
                        content += f"- {con}\n"
                    content += "\n"

        content += "## Selected Solution\n\n"
        content += f"{final_result}\n"

        file_path.write_text(content, encoding="utf-8")

        print("\n" + "=" * 60)
        print("💾 SOLUTION EXPORTED")
        print("=" * 60)
        print(f"✅ Analysis: {file_path}")
        print("=" * 60 + "\n")


async def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python problem_solver.py 'problem description'")
        print("\nExamples:")
        print("  python problem_solver.py 'optimize database query performance'")
        print("  python problem_solver.py 'design scalable microservices architecture'")
        sys.exit(1)

    problem = sys.argv[1]

    # Optional: Parse additional context
    context = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            key, value = arg.split("=", 1)
            context[key] = value.strip('"')

    # Create control protocol for progress reporting
    transport = MemoryTransport()
    await transport.connect()
    control_protocol = ControlProtocol(transport)

    # Create problem solver with Ollama (FREE)
    config = ToTAgentConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.9,  # HIGH temperature for diverse paths
        num_paths=5,
        evaluation_criteria="quality",  # quality, speed, creativity
        parallel_execution=True,
    )

    solver = ProblemSolver(
        config=config,
        control_protocol=control_protocol,
        enable_comparison_logging=True,
    )

    try:
        # Solve problem
        result = await solver.solve_problem(problem, context=context)

        # Export solution
        output_dir = Path("./solution_output")
        solver.export_solution(result, output_dir)

        # Show statistics
        print("\n" + "=" * 60)
        print("📈 PROBLEM SOLVING STATISTICS")
        print("=" * 60)
        print(f"Paths Explored: {len(result.get('paths', []))}")
        print(f"Best Path Score: {result.get('best_path', {}).get('score', 0.0):.2f}")
        print(f"Evaluation Criteria: {config.evaluation_criteria}")
        print("💰 Cost: $0.00 (using Ollama local inference)")
        print("=" * 60 + "\n")

    except KeyboardInterrupt:
        print("\n⚠️  Problem solving interrupted by user\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during problem solving: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
