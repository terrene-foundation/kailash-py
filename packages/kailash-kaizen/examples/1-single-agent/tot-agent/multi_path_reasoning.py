"""
Tree-of-Thoughts Agent Example: Multi-Path Reasoning

Demonstrates parallel path exploration and selection pattern.

Pattern: Generate N paths → Evaluate → Select Best → Execute

Use Case: Strategic decision-making with multiple perspectives
"""

from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig


def main():
    """
    Example: Strategic decision with multiple reasoning paths.

    The ToT agent will:
    1. Generate: Create N different reasoning paths
    2. Evaluate: Score each path independently
    3. Select: Choose the path with highest score
    4. Execute: Execute only the best path
    """

    print("=" * 80)
    print("Tree-of-Thoughts Agent Example: Multi-Path Decision Making")
    print("=" * 80)

    # Configuration
    config = ToTAgentConfig(
        llm_provider="openai",  # or "ollama" for local
        model="gpt-4",  # or "llama3.2" for Ollama
        temperature=0.9,  # Higher temperature for diversity
        num_paths=5,
        max_paths=20,
        evaluation_criteria="quality",  # quality, speed, or creativity
        parallel_execution=True,
    )

    # Create agent
    agent = ToTAgent(config=config)

    # Task: Strategic decision requiring multiple perspectives
    task = """
    A startup has $500K in seed funding and needs to decide on the best
    go-to-market strategy. Options include:

    A) Enterprise B2B sales (high value, long sales cycle)
    B) Consumer B2C freemium model (viral growth, monetization challenge)
    C) Platform/marketplace approach (network effects, chicken-egg problem)
    D) Vertical integration (control but capital-intensive)

    Consider:
    - Market size and competition
    - Time to revenue
    - Resource requirements
    - Scalability potential
    - Risk factors

    Recommend the best strategy with detailed reasoning.
    """

    print("\n📝 Task:")
    print(task)

    # Execute with ToT pattern
    print(f"\n🌳 Generating {config.num_paths} reasoning paths...\n")
    result = agent.run(task=task)

    # Display results
    print("\n" + "=" * 80)
    print("Results")
    print("=" * 80)

    print(f"\n🔍 Path Exploration ({len(result['paths'])} paths generated):\n")
    for i, evaluation in enumerate(result["evaluations"], 1):
        score = evaluation.get("score", 0.0)
        path = evaluation.get("path", {})
        reasoning_preview = path.get("reasoning", "")[:100]

        print(f"   Path {i}:")
        print(f"   Score: {score:.2f} {'⭐' * int(score * 5)}")
        print(f"   Preview: {reasoning_preview}...")
        print()

    # Best path details
    best_path = result["best_path"]
    print("\n🏆 Best Path Selected:")
    print(f"   Score: {best_path.get('score', 0.0):.2f}")
    print(f"   Reasoning: {best_path.get('reasoning', 'See details below')}")

    print("\n✅ Final Recommendation:")
    print("-" * 80)
    print(result["final_result"])
    print("-" * 80)

    # Summary
    print("\n📊 Summary:")
    print(f"   - Paths Explored: {len(result['paths'])}")
    print(f"   - Best Score: {best_path.get('score', 0.0):.2f}")
    print(f"   - Evaluation Criteria: {config.evaluation_criteria}")
    print(f"   - Temperature: {config.temperature} (higher = more diverse)")
    print(
        f"   - Parallel Execution: {'Enabled' if config.parallel_execution else 'Disabled'}"
    )

    # Score distribution
    scores = [eval.get("score", 0.0) for eval in result["evaluations"]]
    print("\n📈 Score Distribution:")
    print(f"   - Min: {min(scores):.2f}")
    print(f"   - Max: {max(scores):.2f}")
    print(f"   - Avg: {sum(scores) / len(scores):.2f}")
    print(f"   - Range: {max(scores) - min(scores):.2f}")


if __name__ == "__main__":
    # Note: Set OPENAI_API_KEY in .env before running
    # Or use Ollama locally: llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"

    main()
