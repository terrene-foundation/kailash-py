"""
Simple Q&A Agent with Kaizen Signature-Based Programming

Demonstrates foundational agent patterns with structured input/output,
comprehensive error handling, and enterprise-grade monitoring using
the Kaizen framework built on Core SDK.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Kaizen Framework imports - signature-based programming
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
class QAConfig:
    """
    Configuration for Q&A Agent

    Supports auto-detection of providers (OpenAI with gpt-5-nano or Ollama)
    or explicit provider configuration.
    """

    llm_provider: Optional[str] = None  # Auto-detect if None
    model: Optional[str] = None  # Provider-specific default if None
    temperature: float = 0.1
    max_tokens: int = 300
    timeout: int = 30
    retry_attempts: int = 3
    min_confidence_threshold: float = 0.5
    provider_config: Dict[str, Any] = field(default_factory=dict)


class QASignature(Signature):
    """Answer questions accurately and concisely with confidence scoring."""

    # Inputs - DSPy-inspired field syntax
    question: str = InputField(desc="The question to answer")
    context: str = InputField(desc="Additional context if available", default="")

    # Outputs - structured response
    answer: str = OutputField(desc="Clear, accurate answer")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0")
    reasoning: str = OutputField(desc="Brief explanation of reasoning")


class SimpleQAAgent:
    """
    Simple Q&A Agent with Kaizen signature-based programming.

    Demonstrates:
    - Structured input/output with Kaizen signatures
    - Comprehensive error handling
    - Performance monitoring
    - Enterprise-grade logging
    - <100ms framework init, <200ms agent creation targets
    """

    def __init__(self, config: QAConfig):
        self.config = config
        self.kaizen_framework = None
        self.agent = None
        self._initialize_framework()

    def _initialize_framework(self):
        """Initialize the Kaizen framework with signature-based agent."""
        logger.info("Initializing Kaizen Q&A agent")
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
            )

            self.kaizen_framework = kaizen.Kaizen(config=framework_config)

            framework_init_time = (time.time() - start_time) * 1000
            logger.info(f"Kaizen framework initialized in {framework_init_time:.1f}ms")

            # Create signature for structured Q&A
            agent_start_time = time.time()
            signature = QASignature(
                name="qa_signature",
                description="Answer questions accurately and concisely with confidence scoring.",
            )

            # Configure agent with signature-based programming and provider config
            agent_config = self.config.provider_config.copy()
            agent_config.update(
                {
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                    "timeout": self.config.timeout,
                    "enable_monitoring": True,
                    "enterprise_features": True,
                }
            )

            # Create agent using Kaizen framework
            self.agent = self.kaizen_framework.create_agent(
                agent_id="qa_agent", config=agent_config, signature=signature
            )

            agent_creation_time = (time.time() - agent_start_time) * 1000
            total_init_time = (time.time() - start_time) * 1000

            logger.info(f"Agent created in {agent_creation_time:.1f}ms")
            logger.info(f"Total initialization in {total_init_time:.1f}ms")

            # Validate performance targets
            if framework_init_time > 100:
                logger.warning(
                    f"Framework init time {framework_init_time:.1f}ms exceeds <100ms target"
                )
            if agent_creation_time > 200:
                logger.warning(
                    f"Agent creation time {agent_creation_time:.1f}ms exceeds <200ms target"
                )

        except Exception as e:
            logger.error(f"Failed to initialize Kaizen framework: {e}")
            raise

    def ask(self, question: str, context: str = "") -> Dict[str, Any]:
        """
        Process a question and return structured answer using Kaizen signature.

        Args:
            question: The question to answer
            context: Optional additional context

        Returns:
            Dict containing answer, confidence, reasoning, and metadata
        """
        start_time = time.time()

        # Input validation
        if not question or not question.strip():
            return self._error_response(
                "Please provide a clear question for me to answer.",
                "INVALID_INPUT",
                "Empty or invalid input received",
            )

        logger.info(f"Processing question: {question[:100]}...")

        try:
            # Prepare input for signature-based execution
            signature_input = {
                "question": question.strip(),
                "context": context.strip() if context else "",
            }

            # Execute using Kaizen agent with signature
            logger.info("Executing Kaizen Q&A agent")

            # Use agent's execute method (supports both signature and direct execution)
            if self.agent.has_signature:
                result = self.agent.execute(**signature_input)
            else:
                # Fallback to direct execution
                result = self.agent.execute(
                    question + (f"\nContext: {context}" if context else "")
                )

            # Extract structured results based on signature
            if isinstance(result, dict) and all(
                key in result for key in ["answer", "confidence", "reasoning"]
            ):
                # Structured result from signature-based execution
                answer = result["answer"]
                confidence = float(result.get("confidence", 0.8))
                reasoning = result["reasoning"]
            else:
                # Parse from LLM response - extract the actual answer content
                if isinstance(result, dict) and "content" in result:
                    # LLM provider response format
                    answer = result["content"]
                    confidence = float(result.get("confidence", 0.7))
                    reasoning = result.get("reasoning", "Direct LLM response")
                elif isinstance(result, dict):
                    # Handle other dict formats
                    text_response = str(
                        result.get("response", result.get("output", str(result)))
                    )
                    answer = text_response
                    confidence = 0.7
                    reasoning = "Parsed from LLM response"
                else:
                    # String response
                    answer = str(result)
                    confidence = 0.7
                    reasoning = "Direct string response from LLM"

            # Apply confidence threshold
            if confidence < self.config.min_confidence_threshold:
                logger.warning(
                    f"Low confidence ({confidence:.2f}) below threshold ({self.config.min_confidence_threshold})"
                )

            # Calculate execution metrics
            execution_time = (time.time() - start_time) * 1000

            response = {
                "answer": answer,
                "confidence": confidence,
                "reasoning": reasoning,
                "metadata": {
                    "execution_time_ms": round(execution_time, 1),
                    "agent_id": self.agent.agent_id,
                    "model_used": self.config.model,
                    "timestamp": time.time(),
                    "signature_used": self.agent.has_signature,
                    "framework": "kaizen",
                },
            }

            logger.info(
                f"Question processed in {execution_time:.1f}ms (confidence: {confidence:.2f})"
            )
            return response

        except TimeoutError as e:
            logger.error(f"Timeout processing question: {e}")
            return self._error_response(
                "Request timed out. The LLM provider took too long to respond.",
                "TIMEOUT_ERROR",
                f"Timeout after {self.config.timeout}s: {str(e)}\n\n"
                "Try: Increase timeout in QAConfig or check network connectivity",
            )
        except ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return self._error_response(
                "Could not connect to LLM provider.",
                "CONNECTION_ERROR",
                f"Connection failed: {str(e)}\n\n"
                "Please check:\n"
                "  1. Internet connectivity for OpenAI\n"
                "  2. Ollama is running (for local models): ollama serve\n"
                "  3. Provider configuration is correct",
            )
        except ValueError as e:
            logger.error(f"Invalid configuration: {e}")
            return self._error_response(
                "Configuration error in LLM setup.",
                "CONFIG_ERROR",
                f"Invalid config: {str(e)}\n\n"
                "Please verify provider and model settings",
            )
        except Exception as e:
            logger.error(f"Unexpected error processing question: {e}", exc_info=True)
            error_type = type(e).__name__
            return self._error_response(
                "I encountered an unexpected error processing your question.",
                "PROCESSING_ERROR",
                f"{error_type}: {str(e)}\n\n"
                "If this persists, please check:\n"
                "  1. LLM provider is accessible\n"
                "  2. API credentials are valid\n"
                "  3. Model name is correct\n"
                "  4. Review logs for more details",
            )

    def _error_response(
        self, message: str, error_code: str, details: str
    ) -> Dict[str, Any]:
        """Generate standardized error response."""
        return {
            "answer": message,
            "confidence": 0.0,
            "reasoning": details,
            "metadata": {
                "error_code": error_code,
                "timestamp": time.time(),
                "execution_time_ms": 0,
                "agent_id": getattr(self.agent, "agent_id", "unknown"),
                "model_used": self.config.model,
                "signature_used": getattr(self.agent, "has_signature", False),
                "framework": "kaizen",
            },
        }

    def batch_ask(
        self, questions: list[str], context: str = ""
    ) -> list[Dict[str, Any]]:
        """
        Process multiple questions in batch using Kaizen optimizations.

        Args:
            questions: List of questions to process
            context: Shared context for all questions

        Returns:
            List of response dictionaries with batch metadata
        """
        logger.info(f"Processing batch of {len(questions)} questions using Kaizen")
        start_time = time.time()

        results = []
        for i, question in enumerate(questions):
            logger.info(f"Processing question {i+1}/{len(questions)}")
            result = self.ask(question, context)

            # Add batch-specific metadata
            result["metadata"]["batch_index"] = i
            result["metadata"]["batch_size"] = len(questions)

            results.append(result)

        batch_time = (time.time() - start_time) * 1000
        avg_time_per_question = batch_time / len(questions) if questions else 0

        logger.info(f"Batch processing completed in {batch_time:.1f}ms")
        logger.info(f"Average time per question: {avg_time_per_question:.1f}ms")

        # Add batch summary metadata to all results
        for result in results:
            result["metadata"]["batch_total_time_ms"] = round(batch_time, 1)
            result["metadata"]["batch_avg_time_per_question_ms"] = round(
                avg_time_per_question, 1
            )

        return results


def main():
    """
    Example usage of Kaizen Simple Q&A Agent.

    Demonstrates:
    - Auto-detection of LLM providers (OpenAI gpt-5-nano or Ollama)
    - Real LLM integration (no mocks)
    - Error handling with informative messages
    - Signature-based programming
    """
    print("=== Kaizen Simple Q&A Agent Testing ===\n")
    print("This example demonstrates Kaizen framework with REAL LLM integration.")
    print("Provider auto-detection will select:")
    print("  1. OpenAI (gpt-4o-mini) if OPENAI_API_KEY is set, or")
    print("  2. Ollama (llama3.2) if Ollama is running locally")
    print()

    # Initialize agent with auto-detected provider (Layer 1: Simple)
    try:
        config = QAConfig(
            temperature=0.1,  # Low temperature for factual answers
            min_confidence_threshold=0.7,
            # provider auto-detected, no explicit config needed
        )

        print("Initializing Kaizen Q&A agent...")
        agent = SimpleQAAgent(config)

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

    # Test cases with REAL LLM calls (no mocks)
    test_questions = [
        {
            "question": "What is machine learning?",
            "context": "Explain for a general audience",
            "expected_confidence": "> 0.8",
        },
        {
            "question": "How do neural networks work?",
            "context": "Technical explanation with mathematical concepts",
            "expected_confidence": "> 0.7",
        },
        {
            "question": "",  # Edge case: empty question
            "context": "",
            "expected_confidence": "= 0.0",
        },
    ]

    for i, test in enumerate(test_questions, 1):
        print(f"Test {i}: {test['question'] or '(empty question)'}")
        print(f"Expected confidence: {test['expected_confidence']}")

        result = agent.ask(test["question"], test["context"])

        print(f"Answer: {result['answer']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Reasoning: {result['reasoning']}")
        print(f"Execution time: {result['metadata']['execution_time_ms']}ms")
        print(f"Framework: {result['metadata']['framework']}")
        print(f"Signature used: {result['metadata']['signature_used']}")
        print("-" * 60)

    # Batch processing test
    print("\n=== Kaizen Batch Processing Test ===")
    batch_questions = [
        "What is artificial intelligence?",
        "How does deep learning differ from machine learning?",
        "What are the main applications of AI in healthcare?",
    ]

    batch_results = agent.batch_ask(
        batch_questions, "Provide concise, accurate answers"
    )

    for i, result in enumerate(batch_results, 1):
        print(
            f"Q{i}: {result['answer'][:100]}... (confidence: {result['confidence']:.2f})"
        )

    # Performance summary
    if batch_results:
        avg_time = batch_results[0]["metadata"]["batch_avg_time_per_question_ms"]
        total_time = batch_results[0]["metadata"]["batch_total_time_ms"]
        print("\nBatch Performance Summary:")
        print(f"Total batch time: {total_time}ms")
        print(f"Average per question: {avg_time}ms")
        print(f"Questions processed: {len(batch_results)}")

    # Framework audit trail
    if hasattr(agent.kaizen_framework, "get_audit_trail"):
        audit_trail = agent.kaizen_framework.get_audit_trail(limit=5)
        if audit_trail:
            print("\n=== Enterprise Audit Trail (last 5 entries) ===")
            for entry in audit_trail[-5:]:
                print(
                    f"Action: {entry.get('action', 'unknown')} at {entry.get('timestamp', 'unknown')}"
                )


def performance_benchmark():
    """Run performance benchmarks to validate targets."""
    print("=== Kaizen Performance Benchmark ===\n")

    config = QAConfig(llm_provider="mock", model="gpt-3.5-turbo", temperature=0.0)

    # Benchmark framework initialization
    framework_times = []
    agent_creation_times = []

    for i in range(5):
        print(f"Benchmark run {i+1}/5...")

        start_time = time.time()
        framework_config = kaizen.KaizenConfig(
            signature_programming_enabled=True, optimization_enabled=True
        )
        framework = kaizen.Kaizen(config=framework_config)
        framework_time = (time.time() - start_time) * 1000
        framework_times.append(framework_time)

        agent_start = time.time()
        signature = QASignature(
            name=f"benchmark_signature_{i}", description="Benchmark Q&A signature"
        )
        agent = framework.create_agent(
            agent_id=f"benchmark_agent_{i}",
            config={"model": "gpt-3.5-turbo"},
            signature=signature,
        )
        agent_time = (time.time() - agent_start) * 1000
        agent_creation_times.append(agent_time)

        framework.cleanup()

    avg_framework_time = sum(framework_times) / len(framework_times)
    avg_agent_time = sum(agent_creation_times) / len(agent_creation_times)

    print("\nPerformance Results:")
    print(f"Framework init time: {avg_framework_time:.1f}ms (target: <100ms)")
    print(f"Agent creation time: {avg_agent_time:.1f}ms (target: <200ms)")

    # Validate targets
    framework_pass = avg_framework_time < 100
    agent_pass = avg_agent_time < 200

    print(f"Framework target: {'PASS' if framework_pass else 'FAIL'}")
    print(f"Agent target: {'PASS' if agent_pass else 'FAIL'}")

    return framework_pass and agent_pass


if __name__ == "__main__":
    main()
    print("\n" + "=" * 60 + "\n")
    performance_benchmark()
