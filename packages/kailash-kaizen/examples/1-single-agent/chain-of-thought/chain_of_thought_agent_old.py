"""
Chain-of-Thought Reasoning Agent with Kaizen Signature-Based Programming

Demonstrates advanced Chain-of-Thought (CoT) reasoning patterns for complex problem
decomposition using the Kaizen framework built on Core SDK. This agent breaks down
complex problems into step-by-step reasoning chains, enabling transparent and
verifiable problem-solving processes.

Performance Targets:
- Framework initialization: <100ms
- Agent creation: <200ms
- Reasoning execution: <1000ms
- Enterprise features: audit trails, monitoring
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Kaizen Framework imports - signature-based programming (Option 3: DSPy-inspired)
import kaizen
from kaizen.config import ConfigurationError, get_default_model_config
from kaizen.signatures import InputField, OutputField, Signature

# Configure logging for execution tracing
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class CoTConfig:
    """
    Configuration for Chain-of-Thought Agent

    Supports auto-detection of providers (OpenAI with gpt-5-nano or Ollama)
    or explicit provider configuration.
    """

    llm_provider: Optional[str] = None  # Auto-detect if None
    model: Optional[str] = None  # Provider-specific default if None
    temperature: float = 0.1
    max_tokens: int = 1500
    timeout: int = 45
    retry_attempts: int = 3
    reasoning_steps: int = 5
    confidence_threshold: float = 0.7
    enable_verification: bool = True
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ChainOfThoughtSignature(Signature):
    """
    Chain-of-Thought signature for structured step-by-step reasoning.

    Enables transparent problem decomposition with explicit reasoning chains,
    intermediate steps, and confidence scoring for enterprise applications.
    """

    # Input fields - Option 3: DSPy-inspired syntax
    problem: str = InputField(desc="Complex problem requiring step-by-step reasoning")
    context: str = InputField(desc="Additional context or constraints", default="")

    # Output fields - structured reasoning chain
    step1: str = OutputField(desc="First reasoning step: Problem understanding")
    step2: str = OutputField(
        desc="Second reasoning step: Data identification and organization"
    )
    step3: str = OutputField(
        desc="Third reasoning step: Systematic calculation or analysis"
    )
    step4: str = OutputField(desc="Fourth reasoning step: Solution verification")
    step5: str = OutputField(desc="Fifth reasoning step: Final answer formulation")
    final_answer: str = OutputField(desc="Complete, verified solution to the problem")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0 for the solution")


class ChainOfThoughtAgent:
    """
    Chain-of-Thought Agent with Kaizen signature-based programming.

    Demonstrates:
    - Structured step-by-step reasoning with Kaizen signatures
    - Mathematical problem solving with verification
    - Enterprise audit trails and monitoring
    - Performance optimization targets
    - Comprehensive error handling
    """

    def __init__(self, config: CoTConfig):
        self.config = config
        self.kaizen_framework = None
        self.agent = None
        self.performance_metrics = {
            "framework_init_time": 0,
            "agent_creation_time": 0,
            "total_executions": 0,
            "successful_executions": 0,
            "average_execution_time": 0,
        }
        self._initialize_framework()

    def _initialize_framework(self):
        """Initialize the Kaizen framework with Chain-of-Thought agent."""
        logger.info("Initializing Kaizen Chain-of-Thought agent")
        start_time = time.time()

        try:
            # Auto-detect provider or use explicit configuration
            if not self.config.provider_config:
                try:
                    logger.info("Auto-detecting LLM provider...")
                    self.config.provider_config = get_default_model_config()
                    logger.info(
                        f"Using provider: {self.config.provider_config['provider']} "
                        f"with model: {self.config.provider_config['model']}"
                    )
                except ConfigurationError as e:
                    logger.error(f"Provider auto-detection failed: {e}")
                    raise RuntimeError(
                        f"Failed to configure LLM provider: {e}\n\n"
                        "Please ensure either:\n"
                        "  1. OPENAI_API_KEY is set for OpenAI (gpt-5-nano), or\n"
                        "  2. Ollama is installed and running for local models"
                    )

            # Initialize Kaizen framework with enterprise features
            framework_config = kaizen.KaizenConfig(
                signature_programming_enabled=True,
                optimization_enabled=True,
                monitoring_enabled=True,
                debug=False,
                audit_trail_enabled=True,
                multi_agent_enabled=False,  # Single agent example
                compliance_mode="enterprise",
                security_level="standard",
            )

            self.kaizen_framework = kaizen.Kaizen(config=framework_config)

            framework_init_time = (time.time() - start_time) * 1000
            self.performance_metrics["framework_init_time"] = framework_init_time
            logger.info(f"Kaizen framework initialized in {framework_init_time:.1f}ms")

            # Validate performance target: <100ms framework initialization
            if framework_init_time > 100:
                logger.warning(
                    f"Framework initialization exceeded 100ms target: {framework_init_time:.1f}ms"
                )

            # Create signature for structured Chain-of-Thought reasoning (Option 3)
            agent_start_time = time.time()
            signature = ChainOfThoughtSignature()

            # Configure agent with CoT-specific parameters and provider config
            agent_config = self.config.provider_config.copy()
            agent_config.update(
                {
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                    "timeout": self.config.timeout,
                    "signature": signature,
                    "generation_config": {
                        "reasoning_pattern": "chain_of_thought",
                        "step_verification": self.config.enable_verification,
                        "confidence_tracking": True,
                    },
                }
            )

            # Create Kaizen agent with signature-based programming
            self.agent = self.kaizen_framework.create_agent(
                agent_id="chain_of_thought_processor",
                config=agent_config,
                signature=signature,
            )

            agent_creation_time = (time.time() - agent_start_time) * 1000
            self.performance_metrics["agent_creation_time"] = agent_creation_time
            logger.info(
                f"Chain-of-Thought agent created in {agent_creation_time:.1f}ms"
            )

            # Validate performance target: <200ms agent creation
            if agent_creation_time > 200:
                logger.warning(
                    f"Agent creation exceeded 200ms target: {agent_creation_time:.1f}ms"
                )

            total_init_time = (time.time() - start_time) * 1000
            logger.info(f"Total initialization completed in {total_init_time:.1f}ms")

        except Exception as e:
            logger.error(f"Failed to initialize Chain-of-Thought agent: {e}")
            raise

    def solve_problem(self, problem: str, context: str = "") -> Dict[str, Any]:
        """
        Solve a complex problem using Chain-of-Thought reasoning.

        Args:
            problem: Complex problem requiring step-by-step reasoning
            context: Additional context or constraints

        Returns:
            Dict containing reasoning steps, final answer, and metadata

        Examples:
            >>> agent = ChainOfThoughtAgent(CoTConfig())
            >>> result = agent.solve_problem(
            ...     "If a train travels 60 mph for 3 hours, then speeds up to 80 mph for 2 more hours, what total distance did it travel?"
            ... )
            >>> print(result['final_answer'])
        """
        execution_start_time = time.time()
        logger.info(
            f"Starting Chain-of-Thought reasoning for problem: {problem[:50]}..."
        )

        try:
            # Prepare inputs for signature-based execution
            inputs = {"problem": problem, "context": context}

            # Execute using agent's signature (Option 3)
            result = self.agent.execute(**inputs)

            execution_time = (time.time() - execution_start_time) * 1000

            # Extract structured outputs from REAL LLM response
            reasoning_result = self._extract_reasoning_steps_from_result(
                result, execution_time
            )

            # Update performance metrics
            self._update_metrics(execution_time, success=True)

            # Add audit trail entry
            audit_entry = {
                "action": "chain_of_thought_reasoning",
                "problem": problem[:100],  # Truncate for logging
                "execution_time_ms": execution_time,
                "success": True,
                "confidence": reasoning_result["confidence"],
                "timestamp": time.time(),
            }
            if hasattr(self.kaizen_framework, "audit_trail"):
                self.kaizen_framework.audit_trail.add_entry(audit_entry)

            logger.info(
                f"Chain-of-Thought reasoning completed in {execution_time:.1f}ms"
            )
            logger.info(f"Final answer: {reasoning_result['final_answer']}")
            logger.info(f"Confidence: {reasoning_result['confidence']:.2f}")

            return reasoning_result

        except Exception as e:
            execution_time = (time.time() - execution_start_time) * 1000
            self._update_metrics(execution_time, success=False)

            logger.error(f"Chain-of-Thought reasoning failed: {e}")

            # Return error result
            return {
                "final_answer": "Unable to solve the problem due to an error",
                "confidence": 0.0,
                "error": str(e),
                "execution_time_ms": execution_time,
                "success": False,
            }

    def _extract_reasoning_steps_from_result(
        self, result: Dict[str, Any], execution_time: float
    ) -> Dict[str, Any]:
        """
        Extract and structure Chain-of-Thought reasoning steps from agent execution result (Option 3).

        Args:
            result: Result from agent.execute() with signature outputs
            execution_time: Time taken for execution

        Returns:
            Structured reasoning result with steps and final answer
        """
        try:
            # With Option 3 signatures, result is already structured with output fields
            if isinstance(result, dict):
                return {
                    "step1": result.get("step1", "Step 1 not provided"),
                    "step2": result.get("step2", "Step 2 not provided"),
                    "step3": result.get("step3", "Step 3 not provided"),
                    "step4": result.get("step4", "Step 4 not provided"),
                    "step5": result.get("step5", "Step 5 not provided"),
                    "final_answer": result.get("final_answer", "No answer provided"),
                    "confidence": float(result.get("confidence", 0.7)),
                    "execution_time_ms": execution_time,
                    "reasoning_pattern": "chain_of_thought",
                    "success": True,
                }

            # Fallback for unexpected result format
            logger.warning(f"Unexpected result format: {type(result)}")
            return {
                "final_answer": str(result),
                "confidence": 0.6,
                "execution_time_ms": execution_time,
                "success": True,
                "note": "Results not in expected structure",
            }

        except Exception as e:
            logger.error(f"Error extracting reasoning steps: {e}")
            return {
                "final_answer": f"Error processing result: {str(e)}",
                "confidence": 0.0,
                "execution_time_ms": execution_time,
                "success": False,
                "error": str(e),
            }

    def _update_metrics(self, execution_time: float, success: bool):
        """Update performance metrics."""
        self.performance_metrics["total_executions"] += 1
        if success:
            self.performance_metrics["successful_executions"] += 1

        # Update average execution time
        current_avg = self.performance_metrics["average_execution_time"]
        total_count = self.performance_metrics["total_executions"]
        self.performance_metrics["average_execution_time"] = (
            current_avg * (total_count - 1) + execution_time
        ) / total_count

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        success_rate = 0
        if self.performance_metrics["total_executions"] > 0:
            success_rate = (
                self.performance_metrics["successful_executions"]
                / self.performance_metrics["total_executions"]
            )

        return {
            **self.performance_metrics,
            "success_rate": success_rate,
            "framework_target_met": self.performance_metrics["framework_init_time"]
            < 100,
            "agent_target_met": self.performance_metrics["agent_creation_time"] < 200,
            "average_execution_target_met": self.performance_metrics[
                "average_execution_time"
            ]
            < 1000,
        }

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get audit trail for enterprise compliance."""
        return self.kaizen_framework.get_audit_trail(limit=50)

    def cleanup(self):
        """Clean up resources and generate final report."""
        if self.kaizen_framework:
            logger.info("Generating final performance report")
            metrics = self.get_performance_metrics()

            logger.info("Performance Summary:")
            logger.info(
                f"  Framework Init: {metrics['framework_init_time']:.1f}ms (Target: <100ms)"
            )
            logger.info(
                f"  Agent Creation: {metrics['agent_creation_time']:.1f}ms (Target: <200ms)"
            )
            logger.info(
                f"  Average Execution: {metrics['average_execution_time']:.1f}ms (Target: <1000ms)"
            )
            logger.info(f"  Success Rate: {metrics['success_rate']:.1%}")

            self.kaizen_framework.cleanup()


def main():
    """
    Demonstration of Chain-of-Thought reasoning with REAL LLM integration.

    Demonstrates:
    - Auto-detection of LLM providers (OpenAI gpt-5-nano or Ollama)
    - Real LLM integration (no mocks)
    - Signature-based CoT reasoning
    - Performance monitoring
    """
    print("Chain-of-Thought Reasoning Agent - Kaizen Framework Demo")
    print("=" * 60)
    print("\nThis example demonstrates Kaizen framework with REAL LLM integration.")
    print("Provider auto-detection will select:")
    print("  1. OpenAI (gpt-4o-mini) if OPENAI_API_KEY is set, or")
    print("  2. Ollama (llama3.2) if Ollama is running locally")
    print()

    # Initialize agent with auto-detected provider (Layer 1: Simple)
    try:
        config = CoTConfig(
            temperature=0.1,  # Low temperature for structured reasoning
            reasoning_steps=5,
            enable_verification=True,
            # provider auto-detected, no explicit config needed
        )

        print("Initializing Kaizen Chain-of-Thought agent...")
        agent = ChainOfThoughtAgent(config)

        # Validate initialization
        provider = agent.config.provider_config.get("provider", "unknown")
        model = agent.config.provider_config.get("model", "unknown")
        print(f"✓ Provider: {provider}")
        print(f"✓ Model: {model}")
        print(f"✓ Signature enabled: {agent.agent.has_signature}")
        print("✓ Framework: Kaizen")
        print()

    except RuntimeError as e:
        print(f"✗ Failed to initialize agent: {e}")
        print("\nPlease configure an LLM provider to run this example.")
        return

    try:
        # Mathematical reasoning demonstration
        train_problem = (
            "If a train travels 60 mph for 3 hours, then speeds up to 80 mph for 2 more hours, "
            "what total distance did it travel?"
        )

        print(f"\nProblem: {train_problem}")
        print("-" * 60)

        result = agent.solve_problem(train_problem)

        print("\nReasoning Steps:")
        for i in range(1, 6):
            step_key = f"step{i}"
            if step_key in result:
                print(f"  Step {i}: {result[step_key]}")

        print(f"\nFinal Answer: {result['final_answer']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Execution Time: {result['execution_time_ms']:.1f}ms")

        # Performance validation
        print("\nPerformance Metrics:")
        metrics = agent.get_performance_metrics()
        print(
            f"  Framework Init: {metrics['framework_init_time']:.1f}ms ({'✓' if metrics['framework_target_met'] else '✗'} <100ms)"
        )
        print(
            f"  Agent Creation: {metrics['agent_creation_time']:.1f}ms ({'✓' if metrics['agent_target_met'] else '✗'} <200ms)"
        )
        print(
            f"  Average Execution: {metrics['average_execution_time']:.1f}ms ({'✓' if metrics['average_execution_target_met'] else '✗'} <1000ms)"
        )

        print("\nEnterprise Features:")
        audit_entries = agent.get_audit_trail()
        print(f"  Audit Trail Entries: {len(audit_entries)}")
        if audit_entries:
            latest = audit_entries[-1]
            print(f"  Latest Action: {latest.get('action', 'N/A')}")
            print(f"  Success: {latest.get('success', 'N/A')}")

    finally:
        agent.cleanup()

    print("\nDemo completed successfully!")


if __name__ == "__main__":
    main()
