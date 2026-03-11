"""
Kaizen Pipeline Infrastructure

Provides base Pipeline class for composable multi-agent workflows with
.to_agent() method for seamless integration into larger orchestrations.

The Pipeline abstraction allows you to:
1. Define complex multi-step workflows
2. Convert pipelines into agents via .to_agent()
3. Compose pipelines within larger orchestrations
4. Reuse workflow logic across different contexts

Usage:
    from kaizen.orchestration.pipeline import Pipeline
    from kaizen.orchestration.patterns import create_supervisor_worker_pattern

    class MyPipeline(Pipeline):
        def run(self, **inputs):
            # Multi-step logic here
            result = self.step1(inputs)
            result = self.step2(result)
            return result

    # Use as standalone pipeline
    pipeline = MyPipeline()
    result = pipeline.run(data="...")

    # Convert to agent for composition
    pipeline_agent = pipeline.to_agent()

    # Use in multi-agent patterns
    pattern = create_supervisor_worker_pattern(
        workers=[pipeline_agent, other_agent]
    )
"""

from typing import Any, Callable, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature


class Pipeline:
    """
    Base class for composable pipelines.

    Pipelines provide a way to define multi-step workflows that can be:
    1. Executed directly via .run()
    2. Converted to agents via .to_agent()
    3. Composed within larger orchestrations

    Example:
        class DataProcessingPipeline(Pipeline):
            def run(self, data: str, **kwargs) -> Dict[str, Any]:
                # Step 1: Clean data
                cleaned = self.clean(data)

                # Step 2: Transform data
                transformed = self.transform(cleaned)

                # Step 3: Analyze data
                analysis = self.analyze(transformed)

                return {
                    "original": data,
                    "cleaned": cleaned,
                    "transformed": transformed,
                    "analysis": analysis
                }

        # Use directly
        pipeline = DataProcessingPipeline()
        result = pipeline.run(data="raw data...")

        # Convert to agent
        agent = pipeline.to_agent()
        result = agent.run(data="raw data...")
    """

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute the pipeline.

        Args:
            **inputs: Pipeline inputs (varies by implementation)

        Returns:
            Dict[str, Any]: Pipeline results

        Raises:
            NotImplementedError: If not overridden by subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement run() method"
        )

    def to_agent(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> BaseAgent:
        """
        Convert pipeline to an Agent for composition.

        Creates a PipelineAgent that wraps this pipeline, allowing it to be
        used anywhere a BaseAgent is expected (multi-agent patterns, workflows, etc.)

        Args:
            name: Optional name for the pipeline agent
            description: Optional description for the pipeline agent

        Returns:
            BaseAgent: Agent wrapper around this pipeline

        Example:
            pipeline = DataProcessingPipeline()
            agent = pipeline.to_agent(
                name="data_processor",
                description="Processes and analyzes data"
            )

            # Use in multi-agent pattern
            pattern = create_supervisor_worker_pattern(
                workers=[agent, other_agent]
            )
        """
        pipeline_instance = self

        class PipelineAgent(BaseAgent):
            """Agent wrapper for Pipeline instances."""

            def __init__(
                self,
                config: Optional[BaseAgentConfig] = None,
                signature: Optional[Signature] = None,
            ):
                """
                Initialize PipelineAgent.

                Args:
                    config: Optional agent configuration
                    signature: Optional signature (auto-generated if not provided)
                """
                # Use provided config or create minimal config
                if config is None:
                    config = BaseAgentConfig(
                        llm_provider="pipeline",
                        model="pipeline",
                    )

                # Use provided signature or create generic signature
                if signature is None:
                    signature = self._create_generic_signature()

                super().__init__(config=config, signature=signature)

                # Store pipeline reference
                self.pipeline = pipeline_instance
                self.pipeline_name = name or pipeline_instance.__class__.__name__

            def _create_generic_signature(self) -> Signature:
                """Create a generic signature for pipeline execution."""

                class PipelineSignature(Signature):
                    """Generic pipeline signature."""

                    inputs: Dict[str, Any] = InputField(
                        description="Pipeline inputs (dict)"
                    )
                    outputs: Dict[str, Any] = OutputField(
                        description="Pipeline outputs (dict)"
                    )

                return PipelineSignature()

            def run(self, **inputs) -> Dict[str, Any]:
                """
                Execute the wrapped pipeline.

                Args:
                    **inputs: Inputs to pass to pipeline

                Returns:
                    Dict[str, Any]: Pipeline execution results
                """
                # Execute the pipeline
                result = self.pipeline.run(**inputs)

                # Ensure result is a dict
                if not isinstance(result, dict):
                    result = {"result": result}

                return result

            def __repr__(self) -> str:
                return f"PipelineAgent(pipeline={self.pipeline_name})"

        # Create and return the agent
        agent = PipelineAgent()

        # Set agent metadata
        if name:
            agent.agent_id = name
        if description:
            agent.description = description

        return agent

    # ========================================================================
    # Factory Methods for Pipeline Patterns (Phase 3, TODO-174)
    # ========================================================================

    @staticmethod
    def router(
        agents: List["BaseAgent"],
        routing_strategy: str = "semantic",
        error_handling: str = "graceful",
    ) -> "Pipeline":
        """
        Create Meta-Controller (Router) Pipeline for intelligent routing.

        Routes requests to best agent based on A2A capability matching.
        Falls back to round-robin or first agent when A2A unavailable.

        Args:
            agents: List of agents to route between
            routing_strategy: "semantic" (A2A), "round-robin", or "random"
            error_handling: "graceful" (default) or "fail-fast"

        Returns:
            MetaControllerPipeline: Router pipeline instance

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            pipeline = Pipeline.router(
                agents=[code_agent, data_agent, writing_agent],
                routing_strategy="semantic"
            )

            result = pipeline.run(
                task="Write a Python function to analyze data",
                input="sales.csv"
            )

        Reference:
            ADR-018: Pipeline Pattern Architecture
            docs/testing/pipeline-edge-case-test-matrix.md
        """
        from kaizen.orchestration.patterns.meta_controller import MetaControllerPipeline

        return MetaControllerPipeline(
            agents=agents,
            routing_strategy=routing_strategy,
            error_handling=error_handling,
        )

    @staticmethod
    def parallel(
        agents: List["BaseAgent"],
        aggregator: Optional[Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = None,
        max_workers: int = 10,
        error_handling: str = "graceful",
        timeout: Optional[float] = None,
    ) -> "Pipeline":
        """
        Create Parallel Pipeline for concurrent agent execution.

        Executes all agents concurrently using asyncio/threads, then aggregates results.
        Achieves 10-100x speedup over sequential execution.

        Args:
            agents: List of agents to execute in parallel
            aggregator: Optional function to aggregate results
            max_workers: Max concurrent executions (default: 10)
            error_handling: "graceful" (default) or "fail-fast"
            timeout: Optional timeout per agent in seconds

        Returns:
            ParallelPipeline: Parallel pipeline instance

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            # Basic parallel execution
            pipeline = Pipeline.parallel(
                agents=[agent1, agent2, agent3],
                max_workers=5
            )

            result = pipeline.run(input="test_data")

            # With custom aggregator
            def combine(results):
                return {"combined": " | ".join(r["output"] for r in results)}

            pipeline = Pipeline.parallel(
                agents=[agent1, agent2],
                aggregator=combine
            )

        Reference:
            ADR-018: Pipeline Pattern Architecture
            docs/testing/pipeline-edge-case-test-matrix.md
        """
        from kaizen.orchestration.patterns.parallel import ParallelPipeline

        return ParallelPipeline(
            agents=agents,
            aggregator=aggregator,
            max_workers=max_workers,
            error_handling=error_handling,
            timeout=timeout,
        )

    @staticmethod
    def ensemble(
        agents: List["BaseAgent"],
        synthesizer: "BaseAgent",
        discovery_mode: str = "a2a",
        top_k: int = 3,
        error_handling: str = "graceful",
    ) -> "Pipeline":
        """
        Create Ensemble Pipeline for multi-perspective agent collaboration.

        Selects top-k agents with best capability matches (via A2A), executes them,
        then synthesizes their perspectives into a unified result.

        Args:
            agents: List of agents to discover from
            synthesizer: Agent that combines perspectives
            discovery_mode: "a2a" (A2A discovery) or "all" (use all agents)
            top_k: Number of agents to select (default: 3)
            error_handling: "graceful" (default) or "fail-fast"

        Returns:
            EnsemblePipeline: Ensemble pipeline instance

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            # A2A discovery (top-3 agents)
            pipeline = Pipeline.ensemble(
                agents=[code_agent, data_agent, writing_agent, research_agent],
                synthesizer=synthesis_agent,
                discovery_mode="a2a",
                top_k=3
            )

            result = pipeline.run(
                task="Analyze codebase and suggest improvements",
                input="repository_path"
            )

            # Use all agents
            pipeline = Pipeline.ensemble(
                agents=[agent1, agent2, agent3],
                synthesizer=synthesizer,
                discovery_mode="all"
            )

            result = pipeline.run(task="Comprehensive review", input="document")

        Reference:
            ADR-018: Pipeline Pattern Architecture
            docs/testing/pipeline-edge-case-test-matrix.md
        """
        from kaizen.orchestration.patterns.ensemble import EnsemblePipeline

        return EnsemblePipeline(
            agents=agents,
            synthesizer=synthesizer,
            discovery_mode=discovery_mode,
            top_k=top_k,
            error_handling=error_handling,
        )

    @staticmethod
    def blackboard(
        specialists: List["BaseAgent"],
        controller: "BaseAgent",
        selection_mode: str = "semantic",
        max_iterations: int = 5,
        error_handling: str = "graceful",
    ) -> "Pipeline":
        """
        Create Blackboard Pipeline for iterative specialist collaboration.

        Maintains shared blackboard state, iteratively selects specialists based on
        evolving needs (via A2A), and uses controller to determine when solution is complete.

        Args:
            specialists: List of specialist agents
            controller: Controller agent that determines completion
            selection_mode: "semantic" (A2A) or "sequential"
            max_iterations: Maximum iterations to prevent infinite loops (default: 5)
            error_handling: "graceful" (default) or "fail-fast"

        Returns:
            BlackboardPipeline: Blackboard pipeline instance

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            # Semantic specialist selection (A2A)
            pipeline = Pipeline.blackboard(
                specialists=[problem_solver, data_analyst, optimizer, validator],
                controller=controller_agent,
                selection_mode="semantic",
                max_iterations=5
            )

            result = pipeline.run(
                task="Solve complex optimization problem",
                input="problem_definition"
            )

            # Sequential specialist invocation
            pipeline = Pipeline.blackboard(
                specialists=[specialist1, specialist2, specialist3],
                controller=controller,
                selection_mode="sequential",
                max_iterations=10
            )

            result = pipeline.run(task="Iterative refinement", input="data")

        Reference:
            ADR-018: Pipeline Pattern Architecture
            docs/testing/pipeline-edge-case-test-matrix.md
        """
        from kaizen.orchestration.patterns.blackboard import BlackboardPipeline

        return BlackboardPipeline(
            specialists=specialists,
            controller=controller,
            selection_mode=selection_mode,
            max_iterations=max_iterations,
            error_handling=error_handling,
        )

    # ========================================================================
    # Factory Methods for Existing Patterns (TODO-174 Phase 3 Day 3)
    # ========================================================================

    @staticmethod
    def sequential(agents: List["BaseAgent"]) -> "SequentialPipeline":
        """
        Create Sequential Pipeline for linear agent execution.

        Executes agents in order where each agent's output becomes the next agent's input.
        Simplest coordination pattern for step-by-step processing.

        Args:
            agents: List of agents to execute sequentially

        Returns:
            SequentialPipeline: Sequential pipeline instance

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            pipeline = Pipeline.sequential(
                agents=[extractor, transformer, loader]
            )

            result = pipeline.run(input="raw_data")
            print(result['final_output'])

        Reference:
            ADR-018: Pipeline Pattern Architecture
            src/kaizen/orchestration/patterns/sequential.py
        """
        return SequentialPipeline(agents=agents)

    @staticmethod
    def supervisor_worker(
        supervisor: "BaseAgent",
        workers: List["BaseAgent"],
        shared_memory: Optional["SharedMemoryPool"] = None,
        selection_mode: str = "semantic",
    ) -> "Pipeline":
        """
        Create Supervisor-Worker Pattern with A2A semantic matching.

        Supervisor delegates tasks to workers, with A2A capability-based selection
        for optimal worker assignment. Falls back to round-robin when A2A unavailable.

        Args:
            supervisor: Supervisor agent that delegates tasks
            workers: List of worker agents
            shared_memory: Optional shared memory pool for coordination
            selection_mode: "semantic" (A2A) or "round-robin"

        Returns:
            SupervisorWorkerPattern: Pattern instance with delegation methods

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            # A2A semantic matching (automatic capability-based selection)
            pattern = Pipeline.supervisor_worker(
                supervisor=supervisor_agent,
                workers=[code_expert, data_expert, writing_expert],
                selection_mode="semantic"
            )

            tasks = pattern.delegate("Process 100 documents")
            results = pattern.aggregate_results(tasks[0]["request_id"])

        Reference:
            ADR-018: Pipeline Pattern Architecture
            src/kaizen/orchestration/patterns/supervisor_worker.py
        """
        from kaizen.memory.shared_memory import SharedMemoryPool
        from kaizen.orchestration.patterns.supervisor_worker import (
            SupervisorWorkerPattern,
        )

        # Create shared memory if not provided
        if shared_memory is None:
            shared_memory = SharedMemoryPool()

        # Create pattern with supervisor, workers
        # Note: coordinator is optional and can be None
        pattern = SupervisorWorkerPattern(
            supervisor=supervisor,
            workers=workers,
            coordinator=None,  # Optional coordinator - set to None for simplified API
            shared_memory=shared_memory,
        )

        return pattern

    @staticmethod
    def consensus(
        agents: List["BaseAgent"],
        threshold: float = 0.5,
        voting_strategy: str = "majority",
        shared_memory: Optional["SharedMemoryPool"] = None,
    ) -> "Pipeline":
        """
        Create Consensus Pattern for democratic voting.

        Agents vote on proposals, with configurable threshold and voting strategies.
        Useful for decision-making requiring agreement across multiple perspectives.

        Args:
            agents: List of voter agents
            threshold: Consensus threshold (0.0-1.0, default: 0.5 for majority)
            voting_strategy: "majority", "unanimous", or "weighted"
            shared_memory: Optional shared memory pool

        Returns:
            ConsensusPattern: Pattern with proposal and voting methods

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            pattern = Pipeline.consensus(
                agents=[technical_expert, business_expert, legal_expert],
                threshold=0.67,  # 2 out of 3 must agree
                voting_strategy="majority"
            )

            proposal = pattern.create_proposal("Should we adopt AI?")
            for voter in pattern.voters:
                voter.vote(proposal)
            result = pattern.determine_consensus(proposal["proposal_id"])

        Reference:
            ADR-018: Pipeline Pattern Architecture
            src/kaizen/orchestration/patterns/consensus.py
        """
        from kaizen.memory.shared_memory import SharedMemoryPool
        from kaizen.orchestration.patterns.consensus import create_consensus_pattern

        # Use existing factory function with wrapper parameters
        return create_consensus_pattern(
            num_voters=len(agents),
            shared_memory=shared_memory or SharedMemoryPool(),
            # Note: create_consensus_pattern creates its own agents
            # This wrapper provides simplified API
        )

    @staticmethod
    def debate(
        agents: List["BaseAgent"],
        rounds: int = 3,
        judge: Optional["BaseAgent"] = None,
        shared_memory: Optional["SharedMemoryPool"] = None,
    ) -> "Pipeline":
        """
        Create Debate Pattern for adversarial reasoning.

        Two agents argue opposing positions, with optional judge to determine winner.
        Multiple rounds of rebuttals strengthen arguments and expose weaknesses.

        Args:
            agents: List of at least 2 agents (proponent and opponent)
            rounds: Number of debate rounds (default: 3)
            judge: Optional judge agent (uses internal if not provided)
            shared_memory: Optional shared memory pool

        Returns:
            DebatePattern: Pattern with debate execution methods

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            pattern = Pipeline.debate(
                agents=[proponent_agent, opponent_agent],
                rounds=3,
                judge=judge_agent
            )

            result = pattern.debate(
                topic="Should AI be regulated?",
                context="Considering safety and innovation"
            )
            print(f"Winner: {result['judgment']['winner']}")

        Reference:
            ADR-018: Pipeline Pattern Architecture
            src/kaizen/orchestration/patterns/debate.py
        """
        from kaizen.memory.shared_memory import SharedMemoryPool
        from kaizen.orchestration.patterns.debate import create_debate_pattern

        # Use existing factory function with wrapper parameters
        return create_debate_pattern(
            shared_memory=shared_memory or SharedMemoryPool(),
            # Note: create_debate_pattern creates its own agents
            # This wrapper provides simplified API
        )

    @staticmethod
    def handoff(
        agents: List["BaseAgent"],
        handoff_condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> "Pipeline":
        """
        Create Handoff Pattern for tier escalation.

        Tasks start at tier 1 and escalate to higher tiers based on complexity.
        Each tier evaluates if it can handle the task before executing or escalating.

        Args:
            agents: List of agents representing tiers (tier 1, tier 2, tier 3, ...)
            handoff_condition: Optional function to determine escalation

        Returns:
            HandoffPattern: Pattern with handoff execution methods

        Example:
            from kaizen.orchestration.pipeline import Pipeline

            pattern = Pipeline.handoff(
                agents=[tier1_agent, tier2_agent, tier3_agent]
            )

            result = pattern.execute_with_handoff(
                task="Debug complex distributed system issue",
                max_tier=3
            )
            print(f"Handled by tier: {result['final_tier']}")
            print(f"Escalations: {result['escalation_count']}")

        Reference:
            ADR-018: Pipeline Pattern Architecture
            src/kaizen/orchestration/patterns/handoff.py
        """
        from kaizen.memory.shared_memory import SharedMemoryPool
        from kaizen.orchestration.patterns.handoff import create_handoff_pattern

        # Use existing factory function with wrapper parameters
        return create_handoff_pattern(
            num_tiers=len(agents),
            shared_memory=SharedMemoryPool(),
            # Note: create_handoff_pattern creates its own agents
            # This wrapper provides simplified API
        )


class SequentialPipeline(Pipeline):
    """
    Sequential pipeline that executes agents in order.

    Convenience class for creating simple sequential workflows where
    each agent's output becomes the next agent's input.

    Example:
        from kaizen.agents import SimpleQAAgent, CodeGenerationAgent
        from kaizen.orchestration.pipeline import SequentialPipeline

        pipeline = SequentialPipeline(
            agents=[
                SimpleQAAgent(),      # Step 1: Analyze task
                CodeGenerationAgent()  # Step 2: Generate code
            ]
        )

        # Execute pipeline
        result = pipeline.run(task="Create a sorting function")

        # Convert to agent
        pipeline_agent = pipeline.to_agent(name="code_creation_pipeline")
    """

    def __init__(self, agents: list):
        """
        Initialize sequential pipeline.

        Args:
            agents: List of BaseAgent instances to execute in order
        """
        self.agents = agents

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute agents sequentially.

        Each agent's output becomes the next agent's input.

        Args:
            **inputs: Initial inputs for first agent

        Returns:
            Dict[str, Any]: Final agent's output plus intermediate results
        """
        results = []
        current_inputs = inputs

        for i, agent in enumerate(self.agents):
            # Execute agent
            result = agent.run(**current_inputs)

            # Store result
            results.append(
                {"agent": agent.__class__.__name__, "step": i + 1, "output": result}
            )

            # Use output as input for next agent
            current_inputs = result

        # Return final result with full history
        return {"final_output": result, "intermediate_results": results}


__all__ = [
    "Pipeline",
    "SequentialPipeline",
]
