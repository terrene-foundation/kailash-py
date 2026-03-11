"""
Example 14: Sequential Pipeline Pattern - Progressive Configuration

This example demonstrates progressive configuration of the SequentialPipelinePattern,
showing how to override specific parameters while keeping others as defaults.

Learning Objectives:
- Progressive configuration (override specific params)
- Different models for different stages
- Environment variable usage
- Pre-built stages configuration

Estimated time: 5 minutes
"""

import os

from kaizen.agents.coordination import create_sequential_pipeline
from kaizen.agents.coordination.sequential_pipeline import PipelineStageAgent
from kaizen.core.base_agent import BaseAgentConfig


def example_1_custom_model():
    """Example 1: Custom model for all stages."""
    print("Example 1: Custom Model for All Stages")
    print("-" * 70)

    # Use GPT-4 instead of default gpt-3.5-turbo
    pipeline = create_sequential_pipeline(model="gpt-4", temperature=0.7)

    # Add stages
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage_1"))
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage_2"))

    print("✓ Pipeline created with custom model")
    print("  Model: gpt-4")
    print("  Temperature: 0.7")
    print(f"  Stages: {len(pipeline.stages)}")
    print()


def example_2_stage_specific_configs():
    """Example 2: Different configs for different stages."""
    print("Example 2: Stage-Specific Configurations")
    print("-" * 70)

    # Different config for each stage
    pipeline = create_sequential_pipeline(
        stage_configs=[
            {
                "model": "gpt-3.5-turbo",
                "temperature": 0.5,  # Lower temp for extraction
                "max_tokens": 500,
            },
            {
                "model": "gpt-4",
                "temperature": 0.8,  # Higher temp for transformation
                "max_tokens": 1000,
            },
            {
                "model": "gpt-3.5-turbo",
                "temperature": 0.3,  # Very low temp for loading
                "max_tokens": 300,
            },
        ]
    )

    print("✓ Pipeline created with stage-specific configs")
    print("  Stage 1: gpt-3.5-turbo (temp=0.5, tokens=500)")
    print("  Stage 2: gpt-4 (temp=0.8, tokens=1000)")
    print("  Stage 3: gpt-3.5-turbo (temp=0.3, tokens=300)")
    print(f"  Total stages: {len(pipeline.stages)}")
    print()


def example_3_environment_variables():
    """Example 3: Using environment variables."""
    print("Example 3: Environment Variables")
    print("-" * 70)

    # Set environment variables
    os.environ["KAIZEN_MODEL"] = "gpt-4"
    os.environ["KAIZEN_TEMPERATURE"] = "0.6"
    os.environ["KAIZEN_LLM_PROVIDER"] = "openai"

    # Create pipeline - will use environment variables
    pipeline = create_sequential_pipeline()
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "env_stage"))

    print("✓ Pipeline created using environment variables")
    print(f"  KAIZEN_MODEL: {os.environ.get('KAIZEN_MODEL')}")
    print(f"  KAIZEN_TEMPERATURE: {os.environ.get('KAIZEN_TEMPERATURE')}")
    print(f"  KAIZEN_LLM_PROVIDER: {os.environ.get('KAIZEN_LLM_PROVIDER')}")
    print()

    # Cleanup
    del os.environ["KAIZEN_MODEL"]
    del os.environ["KAIZEN_TEMPERATURE"]
    del os.environ["KAIZEN_LLM_PROVIDER"]


def example_4_pre_built_stages():
    """Example 4: Using pre-built stages."""
    print("Example 4: Pre-Built Stages")
    print("-" * 70)

    # Create custom stages first
    extract = PipelineStageAgent(
        config=BaseAgentConfig(model="gpt-3.5-turbo", temperature=0.5),
        agent_id="extract",
    )

    transform = PipelineStageAgent(
        config=BaseAgentConfig(model="gpt-4", temperature=0.8), agent_id="transform"
    )

    load = PipelineStageAgent(
        config=BaseAgentConfig(model="gpt-3.5-turbo", temperature=0.3), agent_id="load"
    )

    # Create pipeline with pre-built stages
    pipeline = create_sequential_pipeline(stages=[extract, transform, load])

    print("✓ Pipeline created with pre-built stages")
    print("  Stages provided: 3")
    print(f"  Stages in pipeline: {len(pipeline.stages)}")
    print(f"  Agent IDs: {pipeline.get_agent_ids()}")
    print()


def example_5_custom_shared_memory():
    """Example 5: Using custom shared memory."""
    print("Example 5: Custom Shared Memory")
    print("-" * 70)

    from kaizen.memory import SharedMemoryPool

    # Create custom shared memory
    shared_memory = SharedMemoryPool()

    # Create pipeline with custom shared memory
    pipeline = create_sequential_pipeline(shared_memory=shared_memory)
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "custom_memory_stage"))

    print("✓ Pipeline created with custom shared memory")
    print("  Shared memory instance provided: YES")
    print(
        f"  All stages share same memory: {all(s.shared_memory is shared_memory for s in pipeline.stages)}"
    )
    print()


def example_6_complete_workflow():
    """Example 6: Complete workflow with custom config."""
    print("Example 6: Complete Workflow with Custom Config")
    print("-" * 70)

    # Create pipeline with optimal config
    pipeline = create_sequential_pipeline(
        model="gpt-4", temperature=0.7, max_tokens=1500
    )

    # Add stages for content generation pipeline
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "research"))
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "draft"))
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "edit"))
    pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "publish"))

    print("Content Generation Pipeline:")
    print("  Stage 1: Research")
    print("  Stage 2: Draft")
    print("  Stage 3: Edit")
    print("  Stage 4: Publish")
    print()

    # Execute pipeline
    result = pipeline.execute_pipeline(
        initial_input="Write an article about AI safety",
        context="Technical blog post for developers",
    )

    print("Pipeline Execution:")
    print(f"  - Pipeline ID: {result['pipeline_id']}")
    print(f"  - Stages executed: {result['stage_count']}")
    print(f"  - Status: {result['status']}")
    print()

    print("Final Output:")
    print(f"  {result['final_output'][:150]}...")
    print()

    # Get stage results
    stage_results = pipeline.get_stage_results(result["pipeline_id"])

    print("Stage Progress:")
    for stage in stage_results:
        print(f"  ✓ {stage['stage_name']}: {stage['stage_status']}")
    print()


def main():
    print("=" * 70)
    print("Sequential Pipeline Pattern - Progressive Configuration Examples")
    print("=" * 70)
    print()

    # Run all examples
    example_1_custom_model()
    example_2_stage_specific_configs()
    example_3_environment_variables()
    example_4_pre_built_stages()
    example_5_custom_shared_memory()
    example_6_complete_workflow()

    # Summary
    print("=" * 70)
    print("Configuration Examples Complete!")
    print("=" * 70)
    print()
    print("Configuration Options Summary:")
    print()
    print("Basic Parameters:")
    print("  - llm_provider: str (default: 'openai' or KAIZEN_LLM_PROVIDER)")
    print("  - model: str (default: 'gpt-3.5-turbo' or KAIZEN_MODEL)")
    print("  - temperature: float (default: 0.7 or KAIZEN_TEMPERATURE)")
    print("  - max_tokens: int (default: 1000 or KAIZEN_MAX_TOKENS)")
    print()
    print("Advanced Parameters:")
    print("  - shared_memory: SharedMemoryPool (default: creates new)")
    print("  - stage_configs: List[Dict[str, Any]] (default: uses basic params)")
    print("  - stages: List[PipelineStageAgent] (default: empty, add via add_stage)")
    print()
    print("Configuration Levels:")
    print()
    print("  Level 1: Zero-config")
    print("    pipeline = create_sequential_pipeline()")
    print()
    print("  Level 2: Basic parameters")
    print("    pipeline = create_sequential_pipeline(model='gpt-4', temperature=0.7)")
    print()
    print("  Level 3: Stage-specific configs")
    print("    pipeline = create_sequential_pipeline(stage_configs=[{...}, {...}])")
    print()
    print("  Level 4: Pre-built stages")
    print("    pipeline = create_sequential_pipeline(stages=[stage1, stage2])")
    print()
    print("Environment Variables (used if not overridden):")
    print("  - KAIZEN_LLM_PROVIDER")
    print("  - KAIZEN_MODEL")
    print("  - KAIZEN_TEMPERATURE")
    print("  - KAIZEN_MAX_TOKENS")
    print()
    print("Recommended Configurations:")
    print()
    print("  Cost-Optimized:")
    print("    model='gpt-3.5-turbo', temperature=0.5")
    print()
    print("  Quality-Optimized:")
    print("    model='gpt-4', temperature=0.7")
    print()
    print("  Balanced (Mixed Stages):")
    print("    stage_configs with mix of gpt-3.5-turbo and gpt-4")
    print()


if __name__ == "__main__":
    main()
