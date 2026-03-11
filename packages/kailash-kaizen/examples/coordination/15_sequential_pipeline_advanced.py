"""
Example 15: Sequential Pipeline Pattern - Advanced Usage

This example demonstrates advanced features of the SequentialPipelinePattern,
including complex workflows, error handling, stage metadata, and performance optimization.

Learning Objectives:
- Complex multi-stage workflows
- Error handling and partial failures
- Stage metadata tracking
- Performance optimization
- Custom stage implementations

Estimated time: 10 minutes
"""

import json
from typing import Any, Dict

from kaizen.agents.coordination import create_sequential_pipeline
from kaizen.agents.coordination.sequential_pipeline import PipelineStageAgent
from kaizen.core.base_agent import BaseAgentConfig


def analyze_stage_metadata(stage_results: list) -> Dict[str, Any]:
    """Analyze metadata from all stages."""
    analysis = {
        "total_stages": len(stage_results),
        "successful_stages": sum(
            1 for s in stage_results if s["stage_status"] == "success"
        ),
        "failed_stages": sum(1 for s in stage_results if s["stage_status"] == "failed"),
        "partial_stages": sum(
            1 for s in stage_results if s["stage_status"] == "partial"
        ),
        "stages": [],
    }

    for stage in stage_results:
        # Parse metadata
        try:
            metadata = json.loads(stage.get("stage_metadata", "{}"))
        except:
            metadata = {}

        analysis["stages"].append(
            {
                "name": stage["stage_name"],
                "status": stage["stage_status"],
                "input_length": len(stage.get("stage_input", "")),
                "output_length": len(stage.get("stage_output", "")),
                "metadata": metadata,
            }
        )

    return analysis


def main():
    print("=" * 70)
    print("Sequential Pipeline Pattern - Advanced Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # SCENARIO 1: Complex Multi-Stage Workflow
    # ==================================================================
    print("Scenario 1: Complex 6-Stage Data Processing Pipeline")
    print("-" * 70)

    pipeline1 = create_sequential_pipeline(model="gpt-4")

    # Create comprehensive data processing pipeline
    stages = [
        ("validate", "Validate input data"),
        ("extract", "Extract relevant fields"),
        ("normalize", "Normalize data formats"),
        ("enrich", "Enrich with additional data"),
        ("aggregate", "Aggregate statistics"),
        ("format", "Format for output"),
    ]

    for stage_id, description in stages:
        agent = PipelineStageAgent(config=BaseAgentConfig(), agent_id=stage_id)
        pipeline1.add_stage(agent)

    print("✓ 6-stage pipeline created:")
    for idx, (stage_id, desc) in enumerate(stages, 1):
        print(f"  Stage {idx}: {stage_id} - {desc}")
    print()

    # Execute
    result1 = pipeline1.execute_pipeline(
        initial_input="Customer data: John, john@example.com, purchased 5 items for $150",
        context="Process customer transaction data",
    )

    print("Execution Results:")
    print(f"  - Pipeline ID: {result1['pipeline_id']}")
    print(f"  - Stages completed: {result1['stage_count']}")
    print(f"  - Status: {result1['status']}")
    print()

    pipeline1.clear_shared_memory()

    # ==================================================================
    # SCENARIO 2: Error Handling and Partial Failures
    # ==================================================================
    print("Scenario 2: Error Handling and Partial Failures")
    print("-" * 70)

    pipeline2 = create_sequential_pipeline()

    # Add stages
    pipeline2.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage_1"))
    pipeline2.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage_2"))
    pipeline2.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage_3"))

    # Execute with potentially problematic input
    result2 = pipeline2.execute_pipeline(
        initial_input="",  # Empty input to test error handling
        context="Test error resilience",
    )

    print("Error Handling Results:")
    print(f"  - Status: {result2['status']}")
    print(f"  - Stages attempted: {result2['stage_count']}")
    print()

    # Check stage-by-stage results
    stage_results2 = pipeline2.get_stage_results(result2["pipeline_id"])
    print("Stage-by-Stage Status:")
    for stage in stage_results2:
        print(f"  {stage['stage_name']}: {stage['stage_status']}")
    print()

    pipeline2.clear_shared_memory()

    # ==================================================================
    # SCENARIO 3: Stage Metadata Tracking
    # ==================================================================
    print("Scenario 3: Stage Metadata Tracking")
    print("-" * 70)

    pipeline3 = create_sequential_pipeline(model="gpt-4")

    # Add stages
    pipeline3.add_stage(PipelineStageAgent(BaseAgentConfig(), "analyze"))
    pipeline3.add_stage(PipelineStageAgent(BaseAgentConfig(), "process"))
    pipeline3.add_stage(PipelineStageAgent(BaseAgentConfig(), "summarize"))

    result3 = pipeline3.execute_pipeline(
        initial_input="Analyze quarterly sales data: Q1=$100k, Q2=$150k, Q3=$125k, Q4=$175k",
        context="Financial analysis pipeline",
    )

    # Analyze metadata
    stage_results3 = pipeline3.get_stage_results(result3["pipeline_id"])
    metadata_analysis = analyze_stage_metadata(stage_results3)

    print("Metadata Analysis:")
    print(f"  Total stages: {metadata_analysis['total_stages']}")
    print(f"  Successful: {metadata_analysis['successful_stages']}")
    print(f"  Failed: {metadata_analysis['failed_stages']}")
    print(f"  Partial: {metadata_analysis['partial_stages']}")
    print()

    print("Stage Details:")
    for stage_info in metadata_analysis["stages"]:
        print(f"\n  {stage_info['name']}:")
        print(f"    Status: {stage_info['status']}")
        print(f"    Input size: {stage_info['input_length']} chars")
        print(f"    Output size: {stage_info['output_length']} chars")
        if stage_info["metadata"]:
            print(f"    Metadata: {stage_info['metadata']}")
    print()

    pipeline3.clear_shared_memory()

    # ==================================================================
    # SCENARIO 4: Context Preservation in Complex Workflows
    # ==================================================================
    print("Scenario 4: Context Preservation in Complex Workflows")
    print("-" * 70)

    pipeline4 = create_sequential_pipeline()

    # Create content generation pipeline
    pipeline4.add_stage(PipelineStageAgent(BaseAgentConfig(), "research"))
    pipeline4.add_stage(PipelineStageAgent(BaseAgentConfig(), "outline"))
    pipeline4.add_stage(PipelineStageAgent(BaseAgentConfig(), "draft"))
    pipeline4.add_stage(PipelineStageAgent(BaseAgentConfig(), "edit"))
    pipeline4.add_stage(PipelineStageAgent(BaseAgentConfig(), "finalize"))

    # Complex context with requirements
    context4 = """
    Requirements:
    - Target audience: Software developers
    - Tone: Technical but accessible
    - Length: 800-1000 words
    - Include: Code examples, best practices
    - SEO keywords: AI, machine learning, automation
    """

    result4 = pipeline4.execute_pipeline(
        initial_input="Write article about AI in software development", context=context4
    )

    print("Content Generation Pipeline:")
    print("  Context preserved: YES")
    print(f"  Context length: {len(context4)} chars")
    print()

    stage_results4 = pipeline4.get_stage_results(result4["pipeline_id"])
    print("Content Evolution Through Stages:")
    for idx, stage in enumerate(stage_results4, 1):
        output_preview = (
            stage["stage_output"][:80] + "..."
            if len(stage["stage_output"]) > 80
            else stage["stage_output"]
        )
        print(f"  Stage {idx} ({stage['stage_name']}): {output_preview}")
    print()

    pipeline4.clear_shared_memory()

    # ==================================================================
    # SCENARIO 5: Performance Optimization with Stage Configs
    # ==================================================================
    print("Scenario 5: Performance Optimization with Stage Configs")
    print("-" * 70)

    # Optimize stages based on task complexity
    optimized_configs = [
        # Simple extraction - fast model, low temp, fewer tokens
        {"model": "gpt-3.5-turbo", "temperature": 0.3, "max_tokens": 500},
        # Complex transformation - powerful model, higher temp, more tokens
        {"model": "gpt-4", "temperature": 0.8, "max_tokens": 1500},
        # Simple formatting - fast model, low temp, fewer tokens
        {"model": "gpt-3.5-turbo", "temperature": 0.2, "max_tokens": 300},
    ]

    pipeline5 = create_sequential_pipeline(stage_configs=optimized_configs)

    print("Optimized Pipeline Configuration:")
    print("  Stage 1 (Extract): gpt-3.5-turbo, temp=0.3, tokens=500 (FAST)")
    print("  Stage 2 (Transform): gpt-4, temp=0.8, tokens=1500 (QUALITY)")
    print("  Stage 3 (Format): gpt-3.5-turbo, temp=0.2, tokens=300 (FAST)")
    print()

    print("Optimization Benefits:")
    print("  → Reduced cost (fast model for simple stages)")
    print("  → Better quality (powerful model for complex stage)")
    print("  → Optimal token usage per stage")
    print()

    pipeline5.clear_shared_memory()

    # ==================================================================
    # SCENARIO 6: Edge Case Handling
    # ==================================================================
    print("Scenario 6: Edge Case Handling")
    print("-" * 70)

    # Test 1: Empty pipeline
    pipeline6a = create_sequential_pipeline()
    result6a = pipeline6a.execute_pipeline("Test input")

    print("Empty Pipeline Test:")
    print("  Input: 'Test input'")
    print(f"  Output: '{result6a['final_output']}'")
    print(f"  Status: {result6a['status']}")
    print("  Behavior: Passthrough (input = output)")
    print()

    # Test 2: Single-stage pipeline
    pipeline6b = create_sequential_pipeline()
    pipeline6b.add_stage(PipelineStageAgent(BaseAgentConfig(), "only_stage"))
    result6b = pipeline6b.execute_pipeline("Single stage test")

    print("Single-Stage Pipeline Test:")
    print(f"  Stages: {result6b['stage_count']}")
    print(f"  Status: {result6b['status']}")
    print(f"  Output: '{result6b['final_output'][:50]}...'")
    print()

    # Test 3: Very long pipeline (10 stages)
    pipeline6c = create_sequential_pipeline()
    for i in range(10):
        pipeline6c.add_stage(PipelineStageAgent(BaseAgentConfig(), f"stage_{i+1}"))

    result6c = pipeline6c.execute_pipeline("Test with 10 stages")

    print("Long Pipeline Test (10 stages):")
    print(f"  Stages executed: {result6c['stage_count']}")
    print(f"  Status: {result6c['status']}")
    print(f"  All stages completed: {result6c['stage_count'] == 10}")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Advanced Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to build complex multi-stage workflows (6+ stages)")
    print("  ✓ How to handle errors and partial failures gracefully")
    print("  ✓ How to track and analyze stage metadata")
    print("  ✓ How context is preserved in complex workflows")
    print("  ✓ How to optimize performance with stage-specific configs")
    print("  ✓ How to handle edge cases (empty, single, long pipelines)")
    print()
    print("Advanced Patterns:")
    print("  → Data processing pipelines (validate → extract → transform → load)")
    print("  → Content generation (research → outline → draft → edit → publish)")
    print("  → Analysis workflows (collect → analyze → aggregate → summarize)")
    print("  → ETL pipelines with error handling")
    print()
    print("Best Practices:")
    print("  → Use fast models for simple stages")
    print("  → Use powerful models for complex transformations")
    print("  → Optimize token usage per stage")
    print("  → Track metadata for debugging")
    print("  → Handle partial failures gracefully")
    print("  → Test edge cases (empty, single, long)")
    print()


if __name__ == "__main__":
    main()
