"""
PEV Agent Example: Iterative Refinement with Verification

Demonstrates the Plan-Execute-Verify-Refine pattern for iterative improvement.

Pattern: Plan → Execute → Verify → Refine (loop until verified or max iterations)

Use Case: Generate Python code with automatic verification and refinement
"""

from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig


def main():
    """
    Example: Generate Python code with iterative refinement.

    The PEV agent will:
    1. Plan: Create execution plan for code generation
    2. Execute: Generate the code
    3. Verify: Check code quality
    4. Refine: Improve code based on verification feedback
    (Repeat until code passes verification)
    """

    print("=" * 80)
    print("PEV Agent Example: Iterative Code Refinement")
    print("=" * 80)

    # Configuration
    config = PEVAgentConfig(
        llm_provider="openai",  # or "ollama" for local
        model="gpt-4",  # or "llama3.2" for Ollama
        temperature=0.7,
        max_iterations=5,
        verification_strictness="medium",  # strict, medium, or lenient
        enable_error_recovery=True,
    )

    # Create agent
    agent = PEVAgent(config=config)

    # Task: Generate Python function with verification
    task = """
    Generate a Python function that:
    1. Accepts a list of numbers
    2. Filters out negative numbers
    3. Returns the sum of positive numbers
    4. Includes error handling for empty lists and non-numeric values
    5. Has proper docstring and type hints

    The function should be production-ready and well-tested.
    """

    print("\n📝 Task:")
    print(task)

    # Execute with PEV pattern
    print("\n🔄 Executing PEV cycle...\n")
    result = agent.run(task=task)

    # Display results
    print("\n" + "=" * 80)
    print("Results")
    print("=" * 80)

    print("\n📋 Initial Plan:")
    print(result.get("plan", "No plan available"))

    print(f"\n🔍 Verification Status: {result['verification'].get('passed', False)}")
    print(f"   Issues: {len(result['verification'].get('issues', []))}")
    for issue in result["verification"].get("issues", []):
        print(f"   - {issue}")

    print(f"\n🔧 Refinements Made: {len(result['refinements'])}")
    for i, refinement in enumerate(result["refinements"], 1):
        print(f"   {i}. {refinement}")

    print("\n✅ Final Result:")
    print("-" * 80)
    print(result["final_result"])
    print("-" * 80)

    # Summary
    print("\n📊 Summary:")
    print(f"   - Iterations: {len(result['refinements'])}/{config.max_iterations}")
    print(
        f"   - Verification: {'✓ Passed' if result['verification'].get('passed') else '✗ Failed'}"
    )
    print(
        f"   - Error Recovery: {'Enabled' if config.enable_error_recovery else 'Disabled'}"
    )
    print(f"   - Strictness: {config.verification_strictness}")


if __name__ == "__main__":
    # Note: Set OPENAI_API_KEY in .env before running
    # Or use Ollama locally: llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"

    main()
