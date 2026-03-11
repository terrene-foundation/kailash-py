"""
Domain-Specialists Multi-Agent Pattern.

This example demonstrates expert routing based on domain expertise using
SharedMemoryPool from Phase 2 (Week 3). A router analyzes questions, routes
to appropriate domain experts, and an integrator synthesizes multi-domain answers.

Agents:
1. RouterAgent - Routes questions to appropriate specialist(s)
2. PythonExpertAgent - Python programming expertise
3. DatabaseExpertAgent - Database design and queries
4. SecurityExpertAgent - Security and authentication
5. IntegratorAgent - Synthesizes multi-domain answers

Key Features:
- Intelligent domain classification
- Multi-domain question handling
- Expert-level domain answers
- Confidence scoring
- Reference documentation
- Answer integration across domains

Architecture:
    Question
         |
         v
    RouterAgent (analyzes domain)
         |
         v (single domain)
    Specialist (Python/Database/Security)
         |
         v (writes answer to SharedMemoryPool)
    SharedMemoryPool ["answer", domain_name]
         |
         v (multi-domain path)
    Multiple Specialists
         |
         v (all write answers)
    IntegratorAgent (reads + synthesizes)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["answer", "integrated"]
         |
         v
    Final Answer

Use Cases:
- Technical Q&A systems
- Expert routing systems
- Multi-domain problem solving
- Knowledge base queries

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 5, Task 5E.1)
Reference: Expert systems and domain routing patterns
"""

import json
import uuid
from typing import Any, Dict

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Signature definitions


class RoutingSignature(Signature):
    """Signature for router domain classification."""

    question: str = InputField(desc="User question to classify")

    domains: str = OutputField(desc="Identified domains (JSON list)", default="[]")
    routing: str = OutputField(desc="Routing decision", default="")


class ExpertiseSignature(Signature):
    """Signature for specialist expert answers."""

    question: str = InputField(desc="Domain-specific question")

    answer: str = OutputField(desc="Expert answer", default="")
    confidence: str = OutputField(desc="Confidence 0-1", default="0.8")
    references: str = OutputField(desc="References/documentation", default="")


class IntegrationSignature(Signature):
    """Signature for integrator synthesis."""

    answers: str = InputField(desc="JSON list of specialist answers")
    question: str = InputField(desc="Original question")

    integrated_answer: str = OutputField(desc="Synthesized answer", default="")
    domains_covered: str = OutputField(desc="Domains included", default="")


# Configuration


class DomainSpecialistsConfig(BaseAgentConfig):
    """Configuration for domain specialists pattern."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    routing_segment: str = "routing"
    answers_segment: str = "answers"
    final_segment: str = "final"


# Agent implementations


class RouterAgent(BaseAgent):
    """
    RouterAgent: Routes questions to appropriate domain specialists.

    Responsibilities:
    - Analyze question to identify domain(s)
    - Classify as single-domain or multi-domain
    - Route to appropriate specialist(s)
    - Write routing decisions to shared memory

    Shared Memory Behavior:
    - Writes routing with tags: ["routing"]
    - Segment: "routing"
    - Importance: 0.7
    - Metadata: domains, question_id
    """

    def __init__(
        self,
        config: DomainSpecialistsConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize RouterAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this router
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=RoutingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config
        self.domain_keywords = {
            "python": [
                "python",
                "decorator",
                "function",
                "class",
                "module",
                "import",
                "list",
                "dict",
            ],
            "database": [
                "database",
                "sql",
                "query",
                "table",
                "index",
                "postgres",
                "mysql",
                "orm",
            ],
            "security": [
                "security",
                "authentication",
                "authorization",
                "encrypt",
                "hash",
                "xss",
                "injection",
            ],
        }

    def route(self, question: str) -> Dict[str, Any]:
        """
        Route question to appropriate specialists.

        Args:
            question: User question to route

        Returns:
            Routing decision with domains
        """
        question_id = f"q_{uuid.uuid4().hex[:8]}"

        # Simple keyword-based classification (in production, use LLM)
        domains = []
        question_lower = question.lower()

        for domain, keywords in self.domain_keywords.items():
            if any(keyword in question_lower for keyword in keywords):
                domains.append(domain)

        # If no domains matched, default to python
        if not domains:
            domains = ["python"]

        # Execute routing via base agent
        result = self.run(question=question, session_id=f"route_{question_id}")

        # Parse domains from result if available
        domains_from_llm = result.get("domains", "[]")
        if isinstance(domains_from_llm, str):
            try:
                parsed_domains = json.loads(domains_from_llm)
                if parsed_domains:
                    domains = parsed_domains
            except json.JSONDecodeError:
                pass

        routing_decision = f"Route to: {', '.join(domains)}"

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content={
                "question": question,
                "domains": domains,
                "question_id": question_id,
            },
            tags=["routing"],
            importance=0.7,
            segment=self.config.routing_segment,
            metadata={
                "question_id": question_id,
                "domains": domains,
                "routing_decision": routing_decision,
            },
        )

        return {
            "question_id": question_id,
            "domains": domains,
            "routing": routing_decision,
        }


class PythonExpertAgent(BaseAgent):
    """
    PythonExpertAgent: Provides Python programming expertise.

    Responsibilities:
    - Answer Python-related questions
    - Provide confidence scores
    - Include references to documentation
    - Write answers to shared memory

    Shared Memory Behavior:
    - Writes answers with tags: ["answer", "python"]
    - Segment: "answers"
    - Importance: 0.9
    - Metadata: question_id, confidence
    """

    def __init__(
        self,
        config: DomainSpecialistsConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize PythonExpertAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this expert
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=ExpertiseSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config
        self.domain = "python"

    def answer(self, question: str) -> Dict[str, Any]:
        """
        Provide expert Python answer.

        Args:
            question: Python question

        Returns:
            Expert answer with confidence and references
        """
        question_id = f"python_{uuid.uuid4().hex[:8]}"

        # Execute via base agent
        result = self.run(question=question, session_id=f"answer_{question_id}")

        answer_text = result.get("answer", f"Python answer for: {question}")
        confidence = result.get("confidence", "0.8")
        references = result.get("references", "https://docs.python.org/")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=answer_text,
            tags=["answer", "python"],
            importance=0.9,
            segment=self.config.answers_segment,
            metadata={
                "question_id": question_id,
                "domain": self.domain,
                "confidence": confidence,
                "references": references,
            },
        )

        return {
            "answer": answer_text,
            "confidence": confidence,
            "references": references,
            "domain": self.domain,
        }


class DatabaseExpertAgent(BaseAgent):
    """
    DatabaseExpertAgent: Provides database design and query expertise.

    Responsibilities:
    - Answer database-related questions
    - Provide confidence scores
    - Include references to documentation
    - Write answers to shared memory

    Shared Memory Behavior:
    - Writes answers with tags: ["answer", "database"]
    - Segment: "answers"
    - Importance: 0.9
    - Metadata: question_id, confidence
    """

    def __init__(
        self,
        config: DomainSpecialistsConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize DatabaseExpertAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this expert
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=ExpertiseSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config
        self.domain = "database"

    def answer(self, question: str) -> Dict[str, Any]:
        """
        Provide expert database answer.

        Args:
            question: Database question

        Returns:
            Expert answer with confidence and references
        """
        question_id = f"database_{uuid.uuid4().hex[:8]}"

        # Execute via base agent
        result = self.run(question=question, session_id=f"answer_{question_id}")

        answer_text = result.get("answer", f"Database answer for: {question}")
        confidence = result.get("confidence", "0.8")
        references = result.get("references", "https://postgresql.org/docs/")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=answer_text,
            tags=["answer", "database"],
            importance=0.9,
            segment=self.config.answers_segment,
            metadata={
                "question_id": question_id,
                "domain": self.domain,
                "confidence": confidence,
                "references": references,
            },
        )

        return {
            "answer": answer_text,
            "confidence": confidence,
            "references": references,
            "domain": self.domain,
        }


class SecurityExpertAgent(BaseAgent):
    """
    SecurityExpertAgent: Provides security and authentication expertise.

    Responsibilities:
    - Answer security-related questions
    - Provide confidence scores
    - Include references to security standards
    - Write answers to shared memory

    Shared Memory Behavior:
    - Writes answers with tags: ["answer", "security"]
    - Segment: "answers"
    - Importance: 0.9
    - Metadata: question_id, confidence
    """

    def __init__(
        self,
        config: DomainSpecialistsConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize SecurityExpertAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this expert
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=ExpertiseSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config
        self.domain = "security"

    def answer(self, question: str) -> Dict[str, Any]:
        """
        Provide expert security answer.

        Args:
            question: Security question

        Returns:
            Expert answer with confidence and references
        """
        question_id = f"security_{uuid.uuid4().hex[:8]}"

        # Execute via base agent
        result = self.run(question=question, session_id=f"answer_{question_id}")

        answer_text = result.get("answer", f"Security answer for: {question}")
        confidence = result.get("confidence", "0.8")
        references = result.get("references", "https://owasp.org/")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=answer_text,
            tags=["answer", "security"],
            importance=0.9,
            segment=self.config.answers_segment,
            metadata={
                "question_id": question_id,
                "domain": self.domain,
                "confidence": confidence,
                "references": references,
            },
        )

        return {
            "answer": answer_text,
            "confidence": confidence,
            "references": references,
            "domain": self.domain,
        }


class IntegratorAgent(BaseAgent):
    """
    IntegratorAgent: Synthesizes multi-domain answers.

    Responsibilities:
    - Read answers from multiple specialists
    - Synthesize cohesive multi-domain answer
    - Identify domains covered
    - Write integrated answer to shared memory

    Shared Memory Behavior:
    - Reads answers with tags: ["answer"]
    - Writes integrated with tags: ["answer", "integrated"]
    - Segment: "final"
    - Importance: 1.0 (highest)
    """

    def __init__(
        self,
        config: DomainSpecialistsConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize IntegratorAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this integrator
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=IntegrationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def integrate(self, question: str) -> Dict[str, Any]:
        """
        Integrate multiple specialist answers.

        Args:
            question: Original question

        Returns:
            Integrated answer with domains covered
        """
        # Read all specialist answers
        specialist_answers = []
        if self.shared_memory:
            answers = self.shared_memory.read_relevant(
                agent_id=self.agent_id,
                tags=["answer"],
                segments=[self.config.answers_segment],
                exclude_own=True,
                limit=50,
            )

            for answer_insight in answers:
                metadata = answer_insight.get("metadata", {})
                specialist_answers.append(
                    {
                        "answer": answer_insight.get("content", ""),
                        "domain": metadata.get("domain", "unknown"),
                        "confidence": metadata.get("confidence", "0.8"),
                    }
                )

        # If no answers, return empty
        if not specialist_answers:
            return {
                "integrated_answer": f"No specialist answers found for: {question}",
                "domains_covered": [],
                "status": "no_answers",
            }

        # Execute integration via base agent
        result = self.run(
            answers=json.dumps(specialist_answers),
            question=question,
            session_id=f"integrate_{uuid.uuid4().hex[:8]}",
        )

        integrated_answer = result.get("integrated_answer", "")
        if not integrated_answer:
            # Fallback: concatenate specialist answers
            integrated_answer = "\n\n".join(
                [f"[{a['domain']}]: {a['answer']}" for a in specialist_answers]
            )

        domains_covered = [a["domain"] for a in specialist_answers]

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content=integrated_answer,
            tags=["answer", "integrated"],
            importance=1.0,
            segment=self.config.final_segment,
            metadata={
                "domains_covered": domains_covered,
                "specialist_count": len(specialist_answers),
            },
        )

        return {
            "integrated_answer": integrated_answer,
            "domains_covered": domains_covered,
            "specialist_answers": specialist_answers,
        }


# Workflow function


def domain_specialists_workflow(question: str) -> Dict[str, Any]:
    """
    Run domain-specialists multi-agent workflow.

    This workflow demonstrates expert routing based on domain expertise:
    1. RouterAgent analyzes question and identifies domain(s)
    2. Router routes to appropriate specialist(s)
    3. Specialists provide expert answers
    4. Answers written to SharedMemoryPool
    5. If multi-domain, IntegratorAgent synthesizes answer
    6. Return final answer with statistics

    Args:
        question: User question to answer

    Returns:
        Dictionary containing:
        - question: Original question
        - routing: Routing decision
        - specialist_answers: Individual specialist answers
        - integrated_answer: Synthesized answer (if multi-domain)
        - answer: Final answer (specialist or integrated)
        - stats: Shared memory statistics
        - status: success/error
    """
    # Setup shared memory pool
    shared_pool = SharedMemoryPool()
    config = DomainSpecialistsConfig()

    # Create agents
    router = RouterAgent(config, shared_pool, agent_id="router")

    python_expert = PythonExpertAgent(config, shared_pool, agent_id="python_expert")
    database_expert = DatabaseExpertAgent(
        config, shared_pool, agent_id="database_expert"
    )
    security_expert = SecurityExpertAgent(
        config, shared_pool, agent_id="security_expert"
    )

    integrator = IntegratorAgent(config, shared_pool, agent_id="integrator")

    experts = {
        "python": python_expert,
        "database": database_expert,
        "security": security_expert,
    }

    print(f"\n{'='*60}")
    print(f"Domain-Specialists Pattern: {question}")
    print(f"{'='*60}\n")

    # Step 1: Router classifies and routes
    print("Step 1: Router analyzing question...")
    routing = router.route(question)
    domains = routing["domains"]
    print(f"  - Identified domains: {domains}")
    print(f"  - Routing: {routing['routing']}")

    # Step 2: Specialists provide answers
    print("\nStep 2: Specialists answering...")
    specialist_answers = []

    for domain in domains:
        if domain in experts:
            expert = experts[domain]
            answer = expert.answer(question)
            specialist_answers.append(answer)
            print(
                f"  - {domain.capitalize()} Expert: Answered (confidence: {answer['confidence']})"
            )

    # Step 3: Integration (if multi-domain)
    integrated_answer = None
    final_answer = None

    if len(specialist_answers) > 1:
        print("\nStep 3: Integrator synthesizing multi-domain answer...")
        integration = integrator.integrate(question)
        integrated_answer = integration["integrated_answer"]
        final_answer = integrated_answer
        print(f"  - Integrated {len(specialist_answers)} specialist answers")
        print(f"  - Domains covered: {integration['domains_covered']}")
    elif len(specialist_answers) == 1:
        print("\nStep 3: Single domain - using specialist answer directly")
        final_answer = specialist_answers[0]["answer"]
    else:
        print("\nStep 3: No specialist answers available")
        final_answer = "Unable to answer question - no specialists available"

    # Show shared memory stats
    stats = shared_pool.get_stats()
    print(f"\n{'='*60}")
    print("Shared Memory Statistics:")
    print(f"{'='*60}")
    print(f"  - Total insights: {stats['insight_count']}")
    print(f"  - Agents involved: {stats['agent_count']}")
    print(f"  - Tag distribution: {stats['tag_distribution']}")
    print(f"  - Segment distribution: {stats['segment_distribution']}")
    print(f"{'='*60}\n")

    return {
        "question": question,
        "routing": routing,
        "specialist_answers": specialist_answers,
        "integrated_answer": integrated_answer,
        "answer": final_answer,
        "stats": stats,
        "status": "success" if final_answer else "error",
    }


# Main execution
if __name__ == "__main__":
    # Run example workflows

    # Single domain question
    print("Example 1: Single Domain Question")
    result1 = domain_specialists_workflow(
        "What are Python decorators and how do I use them?"
    )
    print(f"\nFinal Answer: {result1['answer'][:200]}...\n")

    # Multi-domain question
    print("\n" + "=" * 60)
    print("Example 2: Multi-Domain Question")
    result2 = domain_specialists_workflow(
        "How do I securely connect a Python application to a PostgreSQL database?"
    )
    print(f"\nFinal Answer: {result2['answer'][:200]}...\n")

    # All domains question
    print("\n" + "=" * 60)
    print("Example 3: All Domains Question")
    result3 = domain_specialists_workflow(
        "Best practices for secure Python database applications with authentication?"
    )
    print(f"\nFinal Answer: {result3['answer'][:200]}...\n")
