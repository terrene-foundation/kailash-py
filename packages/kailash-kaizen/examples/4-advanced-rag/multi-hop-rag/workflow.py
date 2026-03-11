"""
Multi-Hop RAG Advanced Example

This example demonstrates multi-hop reasoning in RAG using multi-agent coordination.

Agents:
1. QuestionDecomposerAgent - Decomposes complex query into sub-questions
2. SubQuestionRetrieverAgent - Retrieves information for each sub-question
3. AnswerAggregatorAgent - Aggregates sub-answers
4. ReasoningChainAgent - Builds reasoning chain from sub-questions/answers
5. FinalAnswerAgent - Synthesizes final answer from reasoning chain

Use Cases:
- Multi-step question answering
- Complex reasoning chains
- Sequential information gathering
- Dependency-aware retrieval

Architecture Pattern: Sequential Multi-Hop Pipeline with Reasoning Chains
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class MultiHopRAGConfig:
    """Configuration for multi-hop RAG workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    max_hops: int = 3
    max_sub_questions: int = 5
    enable_chain_tracking: bool = True


# ===== Signatures =====


class QuestionDecompositionSignature(Signature):
    """Signature for question decomposition."""

    query: str = InputField(description="Complex query to decompose")

    sub_questions: str = OutputField(description="Sub-questions as JSON")
    reasoning_steps: str = OutputField(description="Reasoning steps as JSON")


class SubQuestionRetrievalSignature(Signature):
    """Signature for sub-question retrieval."""

    sub_question: str = InputField(description="Sub-question to retrieve for")

    documents: str = OutputField(description="Retrieved documents as JSON")
    sub_answer: str = OutputField(description="Answer to sub-question")


class AnswerAggregationSignature(Signature):
    """Signature for answer aggregation."""

    sub_answers: str = InputField(description="Sub-answers to aggregate as JSON")

    aggregated_context: str = OutputField(description="Aggregated context")
    key_findings: str = OutputField(description="Key findings as JSON")


class ReasoningChainSignature(Signature):
    """Signature for reasoning chain construction."""

    query: str = InputField(description="Original query")
    sub_questions: str = InputField(description="Sub-questions as JSON")
    sub_answers: str = InputField(description="Sub-answers as JSON")

    reasoning_chain: str = OutputField(description="Reasoning chain")
    chain_steps: str = OutputField(description="Chain steps as JSON")


class FinalAnswerSignature(Signature):
    """Signature for final answer synthesis."""

    query: str = InputField(description="Original query")
    reasoning_chain: str = InputField(description="Reasoning chain as JSON")

    final_answer: str = OutputField(description="Final synthesized answer")
    supporting_evidence: str = OutputField(description="Supporting evidence as JSON")


# ===== Agents =====


class QuestionDecomposerAgent(BaseAgent):
    """Agent for decomposing complex queries."""

    def __init__(
        self,
        config: MultiHopRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "decomposer",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=QuestionDecompositionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.multi_hop_config = config

    def decompose(self, query: str) -> Dict[str, Any]:
        """Decompose complex query into sub-questions."""
        # Run agent
        result = self.run(query=query)

        # Extract outputs
        sub_questions_raw = result.get("sub_questions", "[]")
        if isinstance(sub_questions_raw, str):
            try:
                sub_questions = (
                    json.loads(sub_questions_raw) if sub_questions_raw else []
                )
            except:
                sub_questions = [sub_questions_raw]
        else:
            sub_questions = (
                sub_questions_raw if isinstance(sub_questions_raw, list) else []
            )

        # Limit to max_sub_questions
        sub_questions = sub_questions[: self.multi_hop_config.max_sub_questions]

        # UX Improvement: One-line extraction

        reasoning_steps = self.extract_list(result, "reasoning_steps", default=[])

        decomposition_result = {
            "sub_questions": sub_questions,
            "reasoning_steps": reasoning_steps,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=decomposition_result,  # Auto-serialized
            tags=["question_decomposition", "multi_hop_pipeline"],
            importance=0.9,
            segment="multi_hop_pipeline",
        )

        return decomposition_result


class SubQuestionRetrieverAgent(BaseAgent):
    """Agent for retrieving information for sub-questions."""

    def __init__(
        self,
        config: MultiHopRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "retriever",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=SubQuestionRetrievalSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.multi_hop_config = config

    def retrieve(self, sub_question: str) -> Dict[str, Any]:
        """Retrieve information for sub-question."""
        # Run agent
        result = self.run(sub_question=sub_question)

        # Extract outputs
        documents_raw = result.get("documents", "[]")
        if isinstance(documents_raw, str):
            try:
                documents = json.loads(documents_raw) if documents_raw else []
            except:
                documents = [{"content": documents_raw}]
        else:
            documents = documents_raw if isinstance(documents_raw, list) else []

        sub_answer = result.get("sub_answer", "No answer found")

        retrieval_result = {
            "sub_question": sub_question,
            "documents": documents,
            "sub_answer": sub_answer,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=retrieval_result,  # Auto-serialized
            tags=["sub_question_retrieval", "multi_hop_pipeline"],
            importance=0.85,
            segment="multi_hop_pipeline",
        )

        return retrieval_result


class AnswerAggregatorAgent(BaseAgent):
    """Agent for aggregating sub-answers."""

    def __init__(
        self,
        config: MultiHopRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "aggregator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AnswerAggregationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.multi_hop_config = config

    def aggregate(self, sub_answers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate sub-answers."""
        # Run agent
        result = self.run(sub_answers=json.dumps(sub_answers))

        # Extract outputs
        aggregated_context = result.get("aggregated_context", "No context aggregated")

        key_findings_raw = result.get("key_findings", "[]")
        if isinstance(key_findings_raw, str):
            try:
                key_findings = json.loads(key_findings_raw) if key_findings_raw else []
            except:
                key_findings = [key_findings_raw]
        else:
            key_findings = (
                key_findings_raw if isinstance(key_findings_raw, list) else []
            )

        aggregation_result = {
            "aggregated_context": aggregated_context,
            "key_findings": key_findings,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=aggregation_result,  # Auto-serialized
            tags=["answer_aggregation", "multi_hop_pipeline"],
            importance=0.9,
            segment="multi_hop_pipeline",
        )

        return aggregation_result


class ReasoningChainAgent(BaseAgent):
    """Agent for building reasoning chains."""

    def __init__(
        self,
        config: MultiHopRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "chain",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ReasoningChainSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.multi_hop_config = config

    def build_chain(
        self, query: str, sub_questions: List[str], sub_answers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build reasoning chain from sub-questions and answers."""
        # Run agent
        result = self.run(
            query=query,
            sub_questions=json.dumps(sub_questions),
            sub_answers=json.dumps(sub_answers),
        )

        # Extract outputs
        reasoning_chain = result.get("reasoning_chain", "No reasoning chain built")

        # UX Improvement: One-line extraction

        chain_steps = self.extract_list(result, "chain_steps", default=[])

        chain_result = {"reasoning_chain": reasoning_chain, "chain_steps": chain_steps}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=chain_result,  # Auto-serialized
            tags=["reasoning_chain", "multi_hop_pipeline"],
            importance=1.0,
            segment="multi_hop_pipeline",
        )

        return chain_result


class FinalAnswerAgent(BaseAgent):
    """Agent for synthesizing final answer."""

    def __init__(
        self,
        config: MultiHopRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "final",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=FinalAnswerSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.multi_hop_config = config

    def synthesize(self, query: str, reasoning_chain: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize final answer from reasoning chain."""
        # Run agent
        result = self.run(query=query, reasoning_chain=json.dumps(reasoning_chain))

        # Extract outputs
        final_answer = result.get("final_answer", "No final answer generated")

        supporting_evidence_raw = result.get("supporting_evidence", "[]")
        if isinstance(supporting_evidence_raw, str):
            try:
                supporting_evidence = (
                    json.loads(supporting_evidence_raw)
                    if supporting_evidence_raw
                    else []
                )
            except:
                supporting_evidence = [supporting_evidence_raw]
        else:
            supporting_evidence = (
                supporting_evidence_raw
                if isinstance(supporting_evidence_raw, list)
                else []
            )

        synthesis_result = {
            "final_answer": final_answer,
            "supporting_evidence": supporting_evidence,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=synthesis_result,  # Auto-serialized
            tags=["final_answer", "multi_hop_pipeline"],
            importance=1.0,
            segment="multi_hop_pipeline",
        )

        return synthesis_result


# ===== Workflow Functions =====


def multi_hop_rag_workflow(
    query: str,
    config: Optional[MultiHopRAGConfig] = None,
    documents_corpus: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Execute multi-hop RAG workflow with sequential reasoning.

    Args:
        query: Complex user query
        config: Configuration for multi-hop RAG
        documents_corpus: Optional document corpus (for testing)

    Returns:
        Complete multi-hop RAG result with sub-questions, answers, reasoning chain, and final answer
    """
    if config is None:
        config = MultiHopRAGConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    decomposer = QuestionDecomposerAgent(config, shared_pool, "decomposer")
    retriever = SubQuestionRetrieverAgent(config, shared_pool, "retriever")
    aggregator = AnswerAggregatorAgent(config, shared_pool, "aggregator")
    chain_agent = ReasoningChainAgent(config, shared_pool, "chain")
    final_agent = FinalAnswerAgent(config, shared_pool, "final")

    # Stage 1: Decompose query into sub-questions
    decomposition = decomposer.decompose(query)
    sub_questions = decomposition["sub_questions"]

    # Stage 2: Retrieve and answer each sub-question (multi-hop)
    sub_answers = []
    for i, sub_question in enumerate(sub_questions):
        if i >= config.max_hops:
            break

        retrieval = retriever.retrieve(sub_question)
        sub_answers.append(
            {
                "question": sub_question,
                "answer": retrieval["sub_answer"],
                "documents": retrieval["documents"],
                "hop": i + 1,
            }
        )

    # Track actual hops taken
    hops = len(sub_answers)

    # Stage 3: Aggregate sub-answers
    aggregation = aggregator.aggregate(sub_answers)

    # Stage 4: Build reasoning chain
    reasoning_chain = chain_agent.build_chain(query, sub_questions, sub_answers)

    # Stage 5: Synthesize final answer
    final_synthesis = final_agent.synthesize(query, reasoning_chain)

    return {
        "query": query,
        "sub_questions": sub_questions,
        "reasoning_steps": decomposition["reasoning_steps"],
        "sub_answers": sub_answers,
        "hops": hops,
        "aggregated_context": aggregation["aggregated_context"],
        "key_findings": aggregation["key_findings"],
        "reasoning_chain": reasoning_chain["reasoning_chain"],
        "chain_steps": reasoning_chain["chain_steps"],
        "final_answer": final_synthesis["final_answer"],
        "supporting_evidence": final_synthesis["supporting_evidence"],
    }


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = MultiHopRAGConfig(llm_provider="mock")

    # Complex multi-hop query
    query = "How do transformers improve upon RNNs in terms of parallelization and long-range dependencies?"

    print("=== Multi-Hop RAG Query ===")
    result = multi_hop_rag_workflow(query, config)
    print(f"Query: {result['query']}")
    print(f"Sub-Questions: {len(result['sub_questions'])}")
    for i, sq in enumerate(result["sub_questions"], 1):
        print(f"  {i}. {sq}")
    print(f"Hops: {result['hops']}")
    print(f"Key Findings: {len(result['key_findings'])}")
    print(f"Final Answer: {result['final_answer'][:100]}...")

    # Another example
    query2 = "Compare the computational complexity of transformers and RNNs for sequence processing"

    print("\n=== Multi-Hop RAG Query 2 ===")
    result2 = multi_hop_rag_workflow(query2, config)
    print(f"Query: {result2['query']}")
    print(f"Sub-Questions: {len(result2['sub_questions'])}")
    print(f"Hops: {result2['hops']}")
    print(f"Chain Steps: {len(result2['chain_steps'])}")
