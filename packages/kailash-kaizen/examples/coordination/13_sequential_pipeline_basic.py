"""
Example 13: Sequential Pipeline Pattern - Basic Usage

This example demonstrates the basic usage of the SequentialPipelinePattern with zero-configuration.
Multiple agents are chained in linear order where each processes the output of the previous agent.

Learning Objectives:
- Zero-config pattern creation
- Linear agent chaining
- Context preservation across stages
- Stage result tracking

Estimated time: 5 minutes
"""

from kaizen.agents.coordination import create_sequential_pipeline
from kaizen.agents.coordination.sequential_pipeline import PipelineStageAgent
from kaizen.core.base_agent import BaseAgentConfig


def main():
    print("=" * 70)
    print("Sequential Pipeline Pattern - Basic Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Create Pattern (Zero-Config!)
    # ==================================================================
    print("Step 1: Creating sequential pipeline pattern...")
    print("-" * 70)

    # Create pattern with default settings
    # - Uses gpt-3.5-turbo (default model)
    # - Uses environment variables if set (KAIZEN_MODEL, etc.)
    pipeline = create_sequential_pipeline()

    print("✓ Pattern created successfully!")
    print("  - Pipeline type: Sequential")
    print(f"  - Stages: {len(pipeline.stages)} (empty, will add)")
    print(f"  - Shared Memory: {pipeline.shared_memory is not None}")
    print()

    # ==================================================================
    # STEP 2: Define Pipeline Stages
    # ==================================================================
    print("Step 2: Defining pipeline stages...")
    print("-" * 70)

    # Create 3-stage data processing pipeline
    # Stage 1: Extract data
    extract_agent = PipelineStageAgent(
        config=BaseAgentConfig(), agent_id="extract_stage"
    )

    # Stage 2: Transform data
    transform_agent = PipelineStageAgent(
        config=BaseAgentConfig(), agent_id="transform_stage"
    )

    # Stage 3: Load data
    load_agent = PipelineStageAgent(config=BaseAgentConfig(), agent_id="load_stage")

    # Add stages to pipeline (order matters!)
    pipeline.add_stage(extract_agent)
    pipeline.add_stage(transform_agent)
    pipeline.add_stage(load_agent)

    print("✓ Pipeline stages defined!")
    print("  - Stage 1: Extract (ID: extract_stage)")
    print("  - Stage 2: Transform (ID: transform_stage)")
    print("  - Stage 3: Load (ID: load_stage)")
    print(f"  - Total stages: {len(pipeline.stages)}")
    print()

    # ==================================================================
    # STEP 3: Validate Pattern
    # ==================================================================
    print("Step 3: Validating pattern initialization...")
    print("-" * 70)

    if pipeline.validate_pattern():
        print("✓ Pattern validation passed!")
        print(f"  - All agents initialized: {len(pipeline.get_agents())} agents")
        print(f"  - Agent IDs: {pipeline.get_agent_ids()}")
        print("  - Shared memory configured: YES")
    else:
        print("✗ Pattern validation failed!")
        return

    print()

    # ==================================================================
    # STEP 4: Execute Pipeline
    # ==================================================================
    print("Step 4: Executing sequential pipeline...")
    print("-" * 70)

    # Define initial input
    initial_input = """
    Customer data to process:
    - Customer ID: 12345
    - Name: John Doe
    - Email: john.doe@example.com
    - Orders: [101, 102, 103]
    - Total spent: $1,250
    """

    context = "ETL workflow for customer data processing"

    print("Initial Input:")
    print(f"  {initial_input.strip()[:100]}...")
    print()

    print(f"Context: {context}")
    print()

    # Execute pipeline
    print("Pipeline execution in progress...")
    print("-" * 70)

    result = pipeline.execute_pipeline(initial_input=initial_input, context=context)

    print("✓ Pipeline execution complete!")
    print()

    # ==================================================================
    # STEP 5: Review Results
    # ==================================================================
    print("Step 5: Reviewing pipeline results...")
    print("-" * 70)

    print("Pipeline Summary:")
    print(f"  - Pipeline ID: {result['pipeline_id']}")
    print(f"  - Total Stages: {result['stage_count']}")
    print(f"  - Status: {result['status']}")
    print()

    print("Final Output:")
    print(f"  {result['final_output'][:200]}...")
    print()

    # Get detailed stage results
    stage_results = pipeline.get_stage_results(result["pipeline_id"])

    print("Stage-by-Stage Results:")
    print("-" * 70)
    for idx, stage in enumerate(stage_results, 1):
        print(f"\nStage {idx}: {stage['stage_name']}")
        print(f"  Status: {stage['stage_status']}")
        print(f"  Input: {stage['stage_input'][:80]}...")
        print(f"  Output: {stage['stage_output'][:80]}...")

    print()

    # ==================================================================
    # STEP 6: Context Preservation Demonstration
    # ==================================================================
    print("Step 6: Demonstrating context preservation...")
    print("-" * 70)

    print("Context Preservation:")
    print(f"  - Original context: '{context}'")
    print("  - Context is passed to ALL stages automatically")
    print("  - Each stage receives:")
    print("    1. Previous stage output (or initial input for first stage)")
    print("    2. Original context")
    print("  - This enables stages to maintain awareness of pipeline purpose")
    print()

    # ==================================================================
    # STEP 7: Cleanup (Optional)
    # ==================================================================
    print("Step 7: Cleanup (optional)...")
    print("-" * 70)

    # Clear shared memory if you want to reuse the pattern
    pipeline.clear_shared_memory()
    print("✓ Shared memory cleared (pattern ready for next execution)")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to create a sequential pipeline pattern (zero-config)")
    print("  ✓ How to define and add pipeline stages")
    print("  ✓ How stages are executed in linear order")
    print("  ✓ How context is preserved across all stages")
    print("  ✓ How to retrieve stage-by-stage results")
    print("  ✓ How to cleanup shared memory for reuse")
    print()
    print("Next steps:")
    print("  → Try example 14: Progressive configuration")
    print("  → Try example 15: Advanced features (complex workflows)")
    print("  → Try example 16: Real-world ETL pipeline")
    print()


if __name__ == "__main__":
    main()
