"""
Basic Planning Agent Example

This example demonstrates the Planning Agent's three-phase workflow:
1. Plan: Generate detailed execution plan
2. Validate: Check plan feasibility
3. Execute: Execute validated plan step-by-step

Pattern: "Plan Before You Act"
Differs from ReAct (interleaved) and CoT (linear reasoning)

Requirements:
- OpenAI API key in .env file (or use Ollama with llm_provider="ollama")

Run with:
    python examples/1-single-agent/planning-agent/basic_planning.py
"""

import os

from dotenv import load_dotenv
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

# Load environment variables
load_dotenv()


def main():
    """Demonstrate Planning Agent with a research task"""

    print("=" * 80)
    print("Planning Agent - Basic Example")
    print("=" * 80)
    print()

    # Configuration (uses environment variables by default)
    llm_provider = os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    model = os.getenv("KAIZEN_MODEL", "gpt-4" if llm_provider == "openai" else "llama2")

    config = PlanningConfig(
        llm_provider=llm_provider,
        model=model,
        temperature=0.3,  # Low temperature for consistent planning
        max_plan_steps=5,  # Limit plan to 5 steps
        validation_mode="strict",  # Strict validation before execution
        enable_replanning=True,  # Enable replanning on validation failure
    )

    print(f"Using LLM Provider: {llm_provider}")
    print(f"Using Model: {model}")
    print()

    # Create Planning Agent
    agent = PlanningAgent(config=config)

    # Task: Create a research report
    task = "Create a comprehensive research report on AI ethics"

    # Additional context
    context = {
        "max_sources": 5,
        "report_length": "2000 words",
        "audience": "general public",
        "focus_areas": ["privacy", "bias", "transparency"],
    }

    print(f"Task: {task}")
    print(f"Context: {context}")
    print()

    # Execute Planning Agent
    print("Executing Planning Agent (Plan → Validate → Execute)...")
    print()

    result = agent.run(task=task, context=context)

    # Display results

    # 1. Plan
    print("=" * 80)
    print("PHASE 1: PLAN")
    print("=" * 80)
    print()

    if "plan" in result and result["plan"]:
        print(f"Generated {len(result['plan'])} steps:")
        print()
        for step in result["plan"]:
            print(f"Step {step.get('step', '?')}: {step.get('action', 'N/A')}")
            print(f"  Description: {step.get('description', 'N/A')}")
            print()
    else:
        print("No plan generated (or plan is empty)")
        print()

    # 2. Validation
    print("=" * 80)
    print("PHASE 2: VALIDATION")
    print("=" * 80)
    print()

    if "validation_result" in result:
        validation = result["validation_result"]
        print(f"Status: {validation.get('status', 'N/A')}")
        if "reason" in validation:
            print(f"Reason: {validation['reason']}")
        if "warnings" in validation and validation["warnings"]:
            print("Warnings:")
            for warning in validation["warnings"]:
                print(f"  - {warning}")
    else:
        print("No validation result")
    print()

    # 3. Execution
    print("=" * 80)
    print("PHASE 3: EXECUTION")
    print("=" * 80)
    print()

    if "execution_results" in result and result["execution_results"]:
        print(f"Executed {len(result['execution_results'])} steps:")
        print()
        for exec_result in result["execution_results"]:
            step_num = exec_result.get("step", "?")
            status = exec_result.get("status", "N/A")
            print(f"Step {step_num}: {status}")
            if "output" in exec_result:
                print(f"  Output: {exec_result['output'][:100]}...")
            if "error" in exec_result:
                print(f"  Error: {exec_result['error']}")
            print()
    else:
        print("No execution results")
        print()

    # 4. Final Result
    print("=" * 80)
    print("FINAL RESULT")
    print("=" * 80)
    print()

    if "final_result" in result and result["final_result"]:
        print(result["final_result"])
    else:
        print("No final result generated")

    print()

    # Error handling
    if "error" in result:
        print("=" * 80)
        print("ERROR")
        print("=" * 80)
        print(f"Error Code: {result['error']}")
        print()

    print("=" * 80)
    print("Planning Agent Example Complete")
    print("=" * 80)


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY not set in .env")
        print("Set OPENAI_API_KEY or use llm_provider='ollama' for local inference")
        print()

    main()
