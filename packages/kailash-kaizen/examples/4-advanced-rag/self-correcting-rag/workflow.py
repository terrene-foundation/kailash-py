"""
Self-Correcting RAG Advanced Example

This example demonstrates self-correction in RAG using multi-agent coordination.

Agents:
1. AnswerGeneratorAgent - Generates initial answer from documents
2. ErrorDetectorAgent - Detects errors in generated answer
3. CorrectionStrategyAgent - Selects correction strategy
4. AnswerRefinerAgent - Refines answer based on strategy
5. ValidationAgent - Validates final answer quality

Use Cases:
- Error detection and correction
- Self-critique and refinement
- Factual consistency checking
- Answer validation

Architecture Pattern: Iterative Correction Pipeline with Validation
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class SelfCorrectingRAGConfig:
    """Configuration for self-correcting RAG workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    max_corrections: int = 3
    validation_threshold: float = 0.8
    enable_self_critique: bool = True


# ===== Signatures =====


class AnswerGenerationSignature(Signature):
    """Signature for answer generation."""

    query: str = InputField(description="User query")
    documents: str = InputField(description="Retrieved documents as JSON")

    answer: str = OutputField(description="Generated answer")
    confidence: str = OutputField(description="Confidence score (0-1)")


class ErrorDetectionSignature(Signature):
    """Signature for error detection."""

    query: str = InputField(description="Original query")
    answer: str = InputField(description="Generated answer")
    documents: str = InputField(description="Source documents as JSON")

    has_errors: str = OutputField(description="Whether errors detected (true/false)")
    error_types: str = OutputField(description="Types of errors as JSON")
    error_details: str = OutputField(description="Detailed error analysis")


class CorrectionStrategySignature(Signature):
    """Signature for correction strategy selection."""

    error_analysis: str = InputField(description="Error analysis as JSON")

    strategy: str = OutputField(description="Correction strategy to use")
    reasoning: str = OutputField(description="Reasoning for strategy selection")


class AnswerRefinementSignature(Signature):
    """Signature for answer refinement."""

    query: str = InputField(description="Original query")
    original_answer: str = InputField(description="Answer to refine")
    documents: str = InputField(description="Source documents as JSON")
    strategy: str = InputField(description="Correction strategy")

    refined_answer: str = OutputField(description="Refined answer")
    corrections_made: str = OutputField(description="Corrections made as JSON")


class AnswerValidationSignature(Signature):
    """Signature for answer validation."""

    query: str = InputField(description="Original query")
    answer: str = InputField(description="Answer to validate")
    documents: str = InputField(description="Source documents as JSON")

    is_valid: str = OutputField(description="Whether answer is valid (true/false)")
    validation_score: str = OutputField(description="Validation score (0-1)")
    feedback: str = OutputField(description="Validation feedback")


# ===== Agents =====


class AnswerGeneratorAgent(BaseAgent):
    """Agent for generating initial answer."""

    def __init__(
        self,
        config: SelfCorrectingRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "generator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AnswerGenerationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.correction_config = config

    def generate(self, query: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate initial answer from documents."""
        # Run agent
        result = self.run(query=query, documents=json.dumps(documents))

        # Extract outputs
        answer = result.get("answer", "No answer generated")

        confidence_raw = result.get("confidence", "0.5")
        try:
            confidence = float(confidence_raw)
        except:
            confidence = 0.5

        generation_result = {"answer": answer, "confidence": confidence}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=generation_result,  # Auto-serialized
            tags=["answer_generation", "correction_pipeline"],
            importance=0.9,
            segment="correction_pipeline",
        )

        return generation_result


class ErrorDetectorAgent(BaseAgent):
    """Agent for detecting errors in answer."""

    def __init__(
        self,
        config: SelfCorrectingRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "detector",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ErrorDetectionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.correction_config = config

    def detect(
        self, query: str, answer: str, documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Detect errors in generated answer."""
        # Run agent
        result = self.run(query=query, answer=answer, documents=json.dumps(documents))

        # Extract outputs
        has_errors_raw = result.get("has_errors", "false")
        has_errors = has_errors_raw.lower() in ["true", "yes", "1"]

        # UX Improvement: One-line extraction

        error_types = self.extract_list(result, "error_types", default=[])

        error_details = result.get("error_details", "No error details")

        detection_result = {
            "has_errors": has_errors,
            "error_types": error_types,
            "error_details": error_details,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=detection_result,  # Auto-serialized
            tags=["error_detection", "correction_pipeline"],
            importance=1.0,
            segment="correction_pipeline",
        )

        return detection_result


class CorrectionStrategyAgent(BaseAgent):
    """Agent for selecting correction strategy."""

    def __init__(
        self,
        config: SelfCorrectingRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "strategy",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=CorrectionStrategySignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.correction_config = config

    def select_strategy(self, error_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Select correction strategy based on error analysis."""
        # Run agent
        result = self.run(error_analysis=json.dumps(error_analysis))

        # Extract outputs
        strategy = result.get("strategy", "replace_with_evidence")
        reasoning = result.get("reasoning", "Default correction strategy")

        strategy_result = {"strategy": strategy, "reasoning": reasoning}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=strategy_result,  # Auto-serialized
            tags=["correction_strategy", "correction_pipeline"],
            importance=0.85,
            segment="correction_pipeline",
        )

        return strategy_result


class AnswerRefinerAgent(BaseAgent):
    """Agent for refining answer."""

    def __init__(
        self,
        config: SelfCorrectingRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "refiner",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AnswerRefinementSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.correction_config = config

    def refine(
        self,
        query: str,
        original_answer: str,
        documents: List[Dict[str, Any]],
        strategy: str,
    ) -> Dict[str, Any]:
        """Refine answer based on correction strategy."""
        # Run agent
        result = self.run(
            query=query,
            original_answer=original_answer,
            documents=json.dumps(documents),
            strategy=strategy,
        )

        # Extract outputs
        refined_answer = result.get("refined_answer", original_answer)

        corrections_made_raw = result.get("corrections_made", "[]")
        if isinstance(corrections_made_raw, str):
            try:
                corrections_made = (
                    json.loads(corrections_made_raw) if corrections_made_raw else []
                )
            except:
                corrections_made = [corrections_made_raw]
        else:
            corrections_made = (
                corrections_made_raw if isinstance(corrections_made_raw, list) else []
            )

        refinement_result = {
            "refined_answer": refined_answer,
            "corrections_made": corrections_made,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=refinement_result,  # Auto-serialized
            tags=["answer_refinement", "correction_pipeline"],
            importance=0.95,
            segment="correction_pipeline",
        )

        return refinement_result


class ValidationAgent(BaseAgent):
    """Agent for validating answer."""

    def __init__(
        self,
        config: SelfCorrectingRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "validator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AnswerValidationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.correction_config = config

    def validate(
        self, query: str, answer: str, documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Validate final answer quality."""
        # Run agent
        result = self.run(query=query, answer=answer, documents=json.dumps(documents))

        # Extract outputs
        is_valid_raw = result.get("is_valid", "true")
        is_valid = is_valid_raw.lower() in ["true", "yes", "1"]

        validation_score_raw = result.get("validation_score", "0.8")
        try:
            validation_score = float(validation_score_raw)
        except:
            validation_score = 0.8

        feedback = result.get("feedback", "Validation complete")

        validation_result = {
            "is_valid": is_valid
            or validation_score >= self.correction_config.validation_threshold,
            "validation_score": validation_score,
            "feedback": feedback,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=validation_result,  # Auto-serialized
            tags=["answer_validation", "correction_pipeline"],
            importance=1.0,
            segment="correction_pipeline",
        )

        return validation_result


# ===== Workflow Functions =====


def self_correcting_rag_workflow(
    query: str,
    documents: List[Dict[str, Any]],
    config: Optional[SelfCorrectingRAGConfig] = None,
) -> Dict[str, Any]:
    """
    Execute self-correcting RAG workflow with error detection and refinement.

    Args:
        query: User query
        documents: Retrieved documents
        config: Configuration for self-correcting RAG

    Returns:
        Complete self-correcting RAG result with corrections and validation
    """
    if config is None:
        config = SelfCorrectingRAGConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    generator = AnswerGeneratorAgent(config, shared_pool, "generator")
    detector = ErrorDetectorAgent(config, shared_pool, "detector")
    strategy_agent = CorrectionStrategyAgent(config, shared_pool, "strategy")
    refiner = AnswerRefinerAgent(config, shared_pool, "refiner")
    validator = ValidationAgent(config, shared_pool, "validator")

    # Stage 1: Generate initial answer
    generation = generator.generate(query, documents)
    current_answer = generation["answer"]

    # Track correction history
    corrections = []
    correction_count = 0

    # Iterative correction loop
    while correction_count < config.max_corrections:
        # Stage 2: Detect errors
        error_detection = detector.detect(query, current_answer, documents)

        # If no errors or answer is valid, break
        if not error_detection["has_errors"]:
            break

        # Stage 3: Select correction strategy
        strategy_result = strategy_agent.select_strategy(error_detection)
        strategy = strategy_result["strategy"]

        # Stage 4: Refine answer
        refinement = refiner.refine(query, current_answer, documents, strategy)
        current_answer = refinement["refined_answer"]

        # Track correction
        corrections.append(
            {
                "iteration": correction_count + 1,
                "errors_detected": error_detection["error_types"],
                "strategy": strategy,
                "corrections": refinement["corrections_made"],
            }
        )

        correction_count += 1

    # Stage 5: Validate final answer
    validation = validator.validate(query, current_answer, documents)

    return {
        "query": query,
        "initial_answer": generation["answer"],
        "initial_confidence": generation["confidence"],
        "error_detection": error_detection,
        "corrections": corrections,
        "correction_count": correction_count,
        "final_answer": current_answer,
        "validation": validation,
        "is_valid": validation["is_valid"],
        "validation_score": validation["validation_score"],
    }


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = SelfCorrectingRAGConfig(llm_provider="mock")

    # Single query
    query = "What are transformers in deep learning?"
    documents = [
        {
            "content": "Transformers are neural network architectures that use attention mechanisms"
        }
    ]

    print("=== Self-Correcting RAG Query ===")
    result = self_correcting_rag_workflow(query, documents, config)
    print(f"Query: {result['query']}")
    print(f"Initial Answer: {result['initial_answer'][:100]}...")
    print(f"Initial Confidence: {result['initial_confidence']}")
    print(f"Errors Detected: {result['error_detection']['has_errors']}")
    print(f"Corrections Made: {result['correction_count']}")
    print(f"Final Answer: {result['final_answer'][:100]}...")
    print(f"Validation Score: {result['validation_score']}")
    print(f"Is Valid: {result['is_valid']}")

    # Example with potential errors
    query_with_errors = "What are transformers?"
    documents_with_errors = [
        {"content": "Transformers are vehicles that can transform"}
    ]

    print("\n=== Self-Correcting RAG with Error Detection ===")
    result_with_errors = self_correcting_rag_workflow(
        query_with_errors, documents_with_errors, config
    )
    print(f"Initial Answer: {result_with_errors['initial_answer'][:100]}...")
    print(f"Errors Detected: {result_with_errors['error_detection']['has_errors']}")
    print(f"Error Types: {result_with_errors['error_detection']['error_types']}")
    print(f"Corrections Made: {result_with_errors['correction_count']}")
    print(f"Final Answer: {result_with_errors['final_answer'][:100]}...")
