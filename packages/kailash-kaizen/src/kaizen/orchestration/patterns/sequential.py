"""
SequentialPipelinePattern - Multi-Agent Coordination Pattern

Sequential pipeline coordination where each agent processes the output
of the previous agent in linear order.

Pattern Components:
- PipelineStageAgent: Processes input from previous stage
- StageProcessingSignature: Signature for stage processing
- SequentialPipelinePattern: Pattern container with convenience methods
- create_sequential_pipeline: Factory function with zero-config support

Usage:
    # Zero-config
    from kaizen.orchestration.patterns import create_sequential_pipeline

    pipeline = create_sequential_pipeline()

    # Add stages
    pipeline.add_stage(ExtractAgent())
    pipeline.add_stage(TransformAgent())
    pipeline.add_stage(LoadAgent())

    # Execute pipeline
    result = pipeline.execute_pipeline(
        initial_input="Process this data",
        context="ETL workflow for customer data"
    )

    # Get all stage results
    stage_results = pipeline.get_stage_results(result['pipeline_id'])

Architecture:
    Input → [Stage 1] → [Stage 2] → [Stage 3] → ... → [Stage N] → Final Output
            Extract      Transform     Load            Process

Author: Kaizen Framework Team
Created: 2025-10-04 (Sequential Pipeline Pattern)
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.patterns.base_pattern import BaseMultiAgentPattern
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Signature Definitions
# ============================================================================


class StageProcessingSignature(Signature):
    """Signature for pipeline stage processing."""

    stage_input: str = InputField(desc="Input from previous stage (or initial input)")
    stage_name: str = InputField(desc="Name of current stage")
    context: str = InputField(desc="Additional context (optional)", default="")

    stage_output: str = OutputField(desc="Output for next stage")
    stage_metadata: str = OutputField(desc="Stage metadata (JSON)", default="{}")
    stage_status: str = OutputField(
        desc="Stage status: success/partial/failed", default="success"
    )


# ============================================================================
# Agent Implementations
# ============================================================================


class PipelineStageAgent(BaseAgent):
    """
    PipelineStageAgent: Processes input from previous stage.

    Responsibilities:
    - Process input from previous stage (or initial input)
    - Produce output for next stage
    - Write stage results to shared memory
    - Support custom stage logic via inheritance

    Shared Memory Behavior:
    - Writes stage results with tags: ["pipeline", "stage", pipeline_id, stage_name]
    - Segment: "pipeline_stages"
    - Importance: 0.8
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        stage_name: str,
        pipeline_id: Optional[str] = None,
        stage_index: Optional[int] = None,
    ):
        """
        Initialize PipelineStageAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this agent
            stage_name: Name of this stage (e.g., "extract", "transform")
            pipeline_id: Pipeline identifier (optional, for tracking)
            stage_index: Stage index in pipeline (optional, for ordering)
        """
        super().__init__(
            config=config,
            signature=StageProcessingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.stage_name = stage_name
        self.pipeline_id = pipeline_id
        self.stage_index = stage_index

    def process_stage(
        self, stage_input: str, context: str = "", pipeline_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process stage input and produce output.

        Args:
            stage_input: Input from previous stage (or initial input)
            context: Additional context
            pipeline_id: Pipeline identifier for tracking

        Returns:
            Dict with stage_output, stage_metadata, stage_status
        """
        # Update pipeline_id if provided
        if pipeline_id:
            self.pipeline_id = pipeline_id

        # Execute stage processing via base agent
        result = self.run(
            stage_input=stage_input, stage_name=self.stage_name, context=context
        )

        # Extract stage output (handle different response formats)
        stage_output = result.get("stage_output", "")
        if not stage_output:
            # Fallback to common field names
            stage_output = result.get("output", result.get("response", ""))

        # Extract metadata
        stage_metadata_str = result.get("stage_metadata", "{}")
        try:
            stage_metadata = (
                json.loads(stage_metadata_str)
                if isinstance(stage_metadata_str, str)
                else stage_metadata_str
            )
        except json.JSONDecodeError:
            stage_metadata = {}

        # Extract status
        stage_status = result.get("stage_status", "success")
        if not stage_status or stage_status not in ["success", "partial", "failed"]:
            # Check for error indicators
            if result.get("error") or result.get("success") is False:
                stage_status = "failed"
            else:
                stage_status = "success"

        # Build stage result
        stage_result = {
            "pipeline_id": self.pipeline_id or "unknown",
            "stage_index": self.stage_index if self.stage_index is not None else 0,
            "stage_name": self.stage_name,
            "stage_input": stage_input,
            "stage_output": stage_output,
            "stage_metadata": stage_metadata,
            "stage_status": stage_status,
            "context": context,
        }

        # Write to shared memory
        if self.shared_memory and self.pipeline_id:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(stage_result),
                    "tags": ["pipeline", "stage", self.pipeline_id, self.stage_name],
                    "importance": 0.8,
                    "segment": "pipeline_stages",
                    "metadata": {
                        "pipeline_id": self.pipeline_id,
                        "stage_index": self.stage_index,
                        "stage_name": self.stage_name,
                        "stage_status": stage_status,
                    },
                }
            )

        return stage_result


# ============================================================================
# Pattern Container
# ============================================================================


@dataclass
class SequentialPipelinePattern(BaseMultiAgentPattern):
    """
    SequentialPipelinePattern: Container for sequential pipeline coordination.

    Provides convenience methods for common operations:
    - add_stage(): Add stage to pipeline
    - execute_pipeline(): Execute all stages in order
    - get_stage_results(): Retrieve all stage results

    Attributes:
        stages: List of PipelineStageAgent instances
        shared_memory: SharedMemoryPool for coordination
    """

    stages: List[PipelineStageAgent] = field(default_factory=list)

    def add_stage(self, agent: PipelineStageAgent) -> None:
        """
        Add a stage to the pipeline.

        Stages execute in the order they are added.

        Args:
            agent: PipelineStageAgent to add

        Example:
            >>> pipeline.add_stage(ExtractAgent())
            >>> pipeline.add_stage(TransformAgent())
        """
        # Set stage index
        agent.stage_index = len(self.stages)
        self.stages.append(agent)

    def execute_pipeline(self, initial_input: str, context: str = "") -> Dict[str, Any]:
        """
        Execute pipeline with all stages in order.

        Each stage receives the output of the previous stage.
        Context is preserved and passed to all stages.

        Args:
            initial_input: Initial input to first stage
            context: Additional context (passed to all stages)

        Returns:
            Dict with pipeline_id, final_output, stage_count, status

        Example:
            >>> result = pipeline.execute_pipeline(
            ...     initial_input="Process this data",
            ...     context="ETL workflow"
            ... )
            >>> print(result['final_output'])
        """
        # Generate pipeline ID
        pipeline_id = f"pipeline_{uuid.uuid4().hex[:8]}"

        # Handle empty pipeline
        if len(self.stages) == 0:
            return {
                "pipeline_id": pipeline_id,
                "final_output": initial_input,  # Pass through
                "stage_count": 0,
                "status": "success",
            }

        # Execute stages in order
        current_input = initial_input
        final_status = "success"

        for i, stage in enumerate(self.stages):
            # Update stage metadata
            stage.pipeline_id = pipeline_id
            stage.stage_index = i

            try:
                # Process stage
                stage_result = stage.process_stage(
                    stage_input=current_input, context=context, pipeline_id=pipeline_id
                )

                # Update status if stage failed
                if stage_result["stage_status"] in ["partial", "failed"]:
                    final_status = stage_result["stage_status"]

                # Pass output to next stage
                current_input = stage_result["stage_output"]

            except Exception as e:
                # Handle stage failure
                final_status = "failed"
                # Continue to next stage with error message
                current_input = f"Error in stage {stage.stage_name}: {str(e)}"

        # Return final result
        return {
            "pipeline_id": pipeline_id,
            "final_output": current_input,
            "stage_count": len(self.stages),
            "status": final_status,
            "context": context,
        }

    def get_stage_results(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all stage results for a pipeline.

        Args:
            pipeline_id: Pipeline identifier

        Returns:
            List of stage result dicts (ordered by stage_index)

        Example:
            >>> result = pipeline.execute_pipeline("Input", "")
            >>> stage_results = pipeline.get_stage_results(result['pipeline_id'])
            >>> for stage in stage_results:
            ...     print(f"{stage['stage_name']}: {stage['stage_status']}")
        """
        if not self.shared_memory:
            return []

        # Read stage results from shared memory
        stage_insights = self.shared_memory.read_relevant(
            agent_id="_pattern_",
            tags=["pipeline", pipeline_id],
            exclude_own=False,
            segments=["pipeline_stages"],
            limit=1000,
        )

        # Parse stage results
        stage_results = []
        for insight in stage_insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    stage_data = json.loads(content)
                    # Verify it's for this pipeline
                    if stage_data.get("pipeline_id") == pipeline_id:
                        stage_results.append(stage_data)
                except json.JSONDecodeError:
                    continue
            else:
                # Verify it's for this pipeline
                if content.get("pipeline_id") == pipeline_id:
                    stage_results.append(content)

        # Sort by stage_index
        stage_results.sort(key=lambda x: x.get("stage_index", 0))

        return stage_results

    def get_agents(self) -> List[BaseAgent]:
        """
        Get all agents in this pattern.

        Returns:
            List of agent instances (all stages)
        """
        return self.stages

    def get_agent_ids(self) -> List[str]:
        """
        Get all agent IDs in this pattern.

        Returns:
            List of agent ID strings
        """
        return [stage.agent_id for stage in self.stages]


# ============================================================================
# Factory Function
# ============================================================================


def create_sequential_pipeline(
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    stage_configs: Optional[List[Dict[str, Any]]] = None,
    stages: Optional[List[PipelineStageAgent]] = None,
) -> SequentialPipelinePattern:
    """
    Create sequential pipeline pattern with zero-config defaults.

    Progressive Configuration Levels:
    - Level 1 (Zero-config): Uses environment variables or defaults
    - Level 2 (Basic params): Override model, temperature, etc.
    - Level 3 (Stage configs): Different config per stage
    - Level 4 (Custom stages): Provide pre-built stages

    Zero-Config Usage:
        >>> pipeline = create_sequential_pipeline()
        >>> pipeline.add_stage(ExtractAgent(...))
        >>> result = pipeline.execute_pipeline("Input", "")

    Progressive Configuration:
        >>> pipeline = create_sequential_pipeline(
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )

    Stage Configs:
        >>> pipeline = create_sequential_pipeline(
        ...     stage_configs=[
        ...         {'model': 'gpt-4', 'temperature': 0.1},
        ...         {'model': 'gpt-3.5-turbo', 'temperature': 0.7}
        ...     ]
        ... )

    Custom Stages:
        >>> pipeline = create_sequential_pipeline(
        ...     stages=[stage1, stage2, stage3]
        ... )

    Args:
        llm_provider: LLM provider (default: from env or "openai")
        model: Model name (default: from env or "gpt-3.5-turbo")
        temperature: Temperature (default: 0.7)
        max_tokens: Max tokens (default: 1000)
        shared_memory: Existing SharedMemoryPool (default: creates new)
        stage_configs: List of stage configs (default: None)
        stages: Pre-built stages (default: None, empty pipeline)

    Returns:
        SequentialPipelinePattern: Pattern ready to use

    Raises:
        ValueError: If stage_configs is not a list
        TypeError: If stages contains non-PipelineStageAgent instances
    """
    # Validate inputs
    if stage_configs is not None and not isinstance(stage_configs, list):
        raise ValueError("stage_configs must be a list of config dicts")

    if stages is not None and not isinstance(stages, list):
        raise TypeError("stages must be a list of PipelineStageAgent instances")

    # Create shared memory if not provided
    if shared_memory is None:
        shared_memory = SharedMemoryPool()

    # If stages provided, use them directly
    if stages is not None:
        # Verify all are PipelineStageAgent instances
        for stage in stages:
            if not isinstance(stage, PipelineStageAgent):
                raise TypeError(
                    f"All stages must be PipelineStageAgent instances, got {type(stage)}"
                )

        # Create pattern with provided stages
        pattern = SequentialPipelinePattern(
            stages=list(stages), shared_memory=shared_memory  # Copy list
        )

        # Update stage indices
        for i, stage in enumerate(pattern.stages):
            stage.stage_index = i
            stage.shared_memory = shared_memory

        return pattern

    # Otherwise, create empty pattern (stages added via add_stage())
    # stage_configs would be used if we auto-create stages, but spec says
    # stages are added manually via add_stage() or provided via stages parameter

    pattern = SequentialPipelinePattern(stages=[], shared_memory=shared_memory)

    return pattern
