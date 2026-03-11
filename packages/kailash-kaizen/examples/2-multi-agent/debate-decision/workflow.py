"""
Debate-Decision Multi-Agent Pattern.

This example demonstrates adversarial reasoning for critical decisions using
SharedMemoryPool from Phase 2 (Week 3). ProponentAgent and OpponentAgent engage
in structured debate while JudgeAgent evaluates and makes the final decision.

Agents:
1. ProponentAgent - Argues FOR the decision, rebuts opponent
2. OpponentAgent - Argues AGAINST the decision, rebuts proponent
3. JudgeAgent - Evaluates all arguments, makes final decision

Key Features:
- Adversarial reasoning (dialectic debate)
- Two-round debate (initial arguments + rebuttals)
- Evidence-based arguments
- Objective judge evaluation
- Winner determination
- Transparent decision rationale

Architecture:
    Decision Question
         |
         v
    ProponentAgent (argues FOR)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["argument", "proponent", "round1"]
         |
         v
    OpponentAgent (argues AGAINST)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["argument", "opponent", "round1"]
         |
         v (proponent reads opponent argument)
    ProponentAgent (rebuts opponent)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["rebuttal", "proponent", "round2"]
         |
         v (opponent reads proponent argument)
    OpponentAgent (rebuts proponent)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["rebuttal", "opponent", "round2"]
         |
         v (judge reads all arguments/rebuttals)
    JudgeAgent (evaluates and decides)
         |
         v (writes to SharedMemoryPool)
    SharedMemoryPool ["decision", "final"]
         |
         v
    Final Decision

Debate Structure:
- Round 1: Initial arguments (proponent FOR, opponent AGAINST)
- Round 2: Rebuttals (both sides address opposing arguments)
- Round 3: Evaluation (judge reads all, makes decision)

Use Cases:
- Critical business decisions
- Risk assessment and mitigation
- Strategic planning with devil's advocate
- Technology adoption decisions
- Architecture decision records (ADRs)
- Investment decisions

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 5, Task 5E.1, Example 3)
Reference: supervisor-worker, consensus-building examples
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Signature definitions


class ProponentSignature(Signature):
    """Signature for proponent arguing FOR the decision."""

    question: str = InputField(desc="Decision question")
    opponent_argument: str = InputField(
        desc="Opponent's argument (for rebuttal)", default=""
    )

    argument: str = OutputField(desc="Argument supporting the decision")
    evidence: str = OutputField(desc="Evidence supporting argument")
    confidence: str = OutputField(desc="Confidence score 0-1")


class OpponentSignature(Signature):
    """Signature for opponent arguing AGAINST the decision."""

    question: str = InputField(desc="Decision question")
    proponent_argument: str = InputField(
        desc="Proponent's argument (for rebuttal)", default=""
    )

    argument: str = OutputField(desc="Argument opposing the decision")
    risks: str = OutputField(desc="Risks identified")
    confidence: str = OutputField(desc="Confidence score 0-1")


class JudgeSignature(Signature):
    """Signature for judge evaluation and decision."""

    arguments: str = InputField(desc="JSON list of all arguments and rebuttals")

    decision: str = OutputField(desc="Final decision: approve/reject")
    reasoning: str = OutputField(desc="Detailed reasoning")
    winner: str = OutputField(desc="Which side won: proponent/opponent/tie")
    confidence: str = OutputField(desc="Confidence in decision 0-1")


# Configuration


@dataclass
class DebateConfig:
    """Configuration for debate-decision workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    rounds: int = 2  # Initial argument + rebuttal


# Agent implementations


class ProponentAgent(BaseAgent):
    """
    ProponentAgent: Argues FOR the decision, rebuts opponent.

    Responsibilities:
    - Receive decision question
    - Present compelling case FOR the decision
    - Provide evidence supporting the position
    - Read opponent's arguments from shared memory
    - Rebut opponent's case with counter-arguments
    - Maintain confidence scores

    Shared Memory Behavior:
    - Writes arguments with tags: ["argument", "proponent", "round1"]
    - Writes rebuttals with tags: ["rebuttal", "proponent", "round2"]
    - Reads opponent arguments with tags: ["argument", "opponent"]
    - Importance: 0.9 for arguments and rebuttals
    - Segment: "debate"
    """

    def __init__(
        self, config: DebateConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize ProponentAgent.

        Args:
            config: Debate workflow configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=ProponentSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def argue(self, question: str) -> Dict[str, Any]:
        """
        Present case FOR the decision.

        Args:
            question: Decision question to argue for

        Returns:
            Dictionary containing argument, evidence, and confidence
        """
        # Execute argument generation via base agent
        result = self.run(
            question=question,
            opponent_argument="",
            session_id=f"argue_{uuid.uuid4().hex[:8]}",
        )

        # Extract argument details
        argument = result.get("argument", "I support this decision")
        evidence = result.get("evidence", "Based on analysis")
        confidence = result.get("confidence", "0.8")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content={
                "argument": argument,
                "evidence": evidence,
                "confidence": confidence,
            },
            tags=["argument", "proponent", "round1"],
            importance=0.9,
            segment="debate",
            metadata={"question": question, "round": 1, "type": "initial_argument"},
        )

        return {"argument": argument, "evidence": evidence, "confidence": confidence}

    def rebut(self, question: str, opponent_argument: str) -> Dict[str, Any]:
        """
        Rebut opponent's argument.

        Args:
            question: Decision question
            opponent_argument: Opponent's argument to rebut

        Returns:
            Dictionary containing rebuttal, evidence, and confidence
        """
        # Execute rebuttal generation via base agent
        result = self.run(
            question=question,
            opponent_argument=opponent_argument,
            session_id=f"rebut_{uuid.uuid4().hex[:8]}",
        )

        # Extract rebuttal details
        argument = result.get("argument", "I address the opponent's concerns")
        evidence = result.get("evidence", "Additional evidence")
        confidence = result.get("confidence", "0.8")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content={
                "rebuttal": argument,
                "evidence": evidence,
                "confidence": confidence,
                "responding_to": opponent_argument,
            },
            tags=["rebuttal", "proponent", "round2"],
            importance=0.9,
            segment="debate",
            metadata={"question": question, "round": 2, "type": "rebuttal"},
        )

        return {"argument": argument, "evidence": evidence, "confidence": confidence}


class OpponentAgent(BaseAgent):
    """
    OpponentAgent: Argues AGAINST the decision, rebuts proponent.

    Responsibilities:
    - Receive decision question
    - Present compelling case AGAINST the decision
    - Identify risks and concerns
    - Read proponent's arguments from shared memory
    - Rebut proponent's case with counter-arguments
    - Maintain confidence scores

    Shared Memory Behavior:
    - Writes arguments with tags: ["argument", "opponent", "round1"]
    - Writes rebuttals with tags: ["rebuttal", "opponent", "round2"]
    - Reads proponent arguments with tags: ["argument", "proponent"]
    - Importance: 0.9 for arguments and rebuttals
    - Segment: "debate"
    """

    def __init__(
        self, config: DebateConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize OpponentAgent.

        Args:
            config: Debate workflow configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=OpponentSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def argue(self, question: str) -> Dict[str, Any]:
        """
        Present case AGAINST the decision.

        Args:
            question: Decision question to argue against

        Returns:
            Dictionary containing argument, risks, and confidence
        """
        # Execute argument generation via base agent
        result = self.run(
            question=question,
            proponent_argument="",
            session_id=f"argue_{uuid.uuid4().hex[:8]}",
        )

        # Extract argument details
        argument = result.get("argument", "I oppose this decision")
        risks = result.get("risks", "Several risks identified")
        confidence = result.get("confidence", "0.8")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content={"argument": argument, "risks": risks, "confidence": confidence},
            tags=["argument", "opponent", "round1"],
            importance=0.9,
            segment="debate",
            metadata={"question": question, "round": 1, "type": "initial_argument"},
        )

        return {"argument": argument, "risks": risks, "confidence": confidence}

    def rebut(self, question: str, proponent_argument: str) -> Dict[str, Any]:
        """
        Rebut proponent's argument.

        Args:
            question: Decision question
            proponent_argument: Proponent's argument to rebut

        Returns:
            Dictionary containing rebuttal, risks, and confidence
        """
        # Execute rebuttal generation via base agent
        result = self.run(
            question=question,
            proponent_argument=proponent_argument,
            session_id=f"rebut_{uuid.uuid4().hex[:8]}",
        )

        # Extract rebuttal details
        argument = result.get("argument", "The proponent overlooks key issues")
        risks = result.get("risks", "Additional risks")
        confidence = result.get("confidence", "0.8")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content={
                "rebuttal": argument,
                "risks": risks,
                "confidence": confidence,
                "responding_to": proponent_argument,
            },
            tags=["rebuttal", "opponent", "round2"],
            importance=0.9,
            segment="debate",
            metadata={"question": question, "round": 2, "type": "rebuttal"},
        )

        return {"argument": argument, "risks": risks, "confidence": confidence}


class JudgeAgent(BaseAgent):
    """
    JudgeAgent: Evaluates all arguments and makes final decision.

    Responsibilities:
    - Read all arguments from shared memory (both sides)
    - Read all rebuttals from shared memory (both sides)
    - Analyze strength of each position
    - Evaluate evidence quality
    - Determine which side presented better case
    - Make final decision (approve/reject)
    - Provide detailed reasoning
    - Write decision to shared memory

    Decision Criteria:
    - Strength of arguments
    - Quality of evidence
    - Effectiveness of rebuttals
    - Risk/benefit balance
    - Overall persuasiveness

    Shared Memory Behavior:
    - Reads arguments with tags: ["argument"], segment: "debate"
    - Reads rebuttals with tags: ["rebuttal"], segment: "debate"
    - Writes decision with tags: ["decision", "final"]
    - Importance: 1.0 for final decision
    - Segment: "decisions"
    """

    def __init__(
        self, config: DebateConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize JudgeAgent.

        Args:
            config: Debate workflow configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,
            signature=JudgeSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def evaluate(self, question: str) -> Dict[str, Any]:
        """
        Read all arguments and make decision.

        Args:
            question: Decision question being evaluated

        Returns:
            Dictionary containing decision, reasoning, winner, and confidence
        """
        if not self.shared_memory:
            return {
                "decision": "approve",
                "reasoning": "No shared memory available",
                "winner": "tie",
                "confidence": "0.5",
            }

        # Read all arguments from shared memory
        arguments = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["argument"],
            segments=["debate"],
            exclude_own=False,
            limit=10,
        )

        # Read all rebuttals from shared memory
        rebuttals = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["rebuttal"],
            segments=["debate"],
            exclude_own=False,
            limit=10,
        )

        # Combine all debate content
        all_content = arguments + rebuttals

        # Format for judge evaluation
        formatted_arguments = []
        for insight in all_content:
            formatted_arguments.append(
                {
                    "agent": insight.get("agent_id"),
                    "content": insight.get("content"),
                    "tags": insight.get("tags", []),
                    "metadata": insight.get("metadata", {}),
                }
            )

        # Execute evaluation via base agent
        result = self.run(
            arguments=json.dumps(formatted_arguments),
            session_id=f"evaluate_{uuid.uuid4().hex[:8]}",
        )

        # Extract decision details with proper defaults for mock provider
        decision = result.get("decision", "approve")
        # Validate decision is one of allowed values
        if decision not in ["approve", "reject"]:
            decision = "approve"

        reasoning = result.get("reasoning", "Based on evaluation of all arguments")
        winner = result.get("winner", "tie")
        # Validate winner
        if winner not in ["proponent", "opponent", "tie"]:
            winner = "tie"

        confidence = result.get("confidence", "0.75")

        # UX Improvement: Concise shared memory write
        self.write_to_memory(
            content={
                "decision": decision,
                "reasoning": reasoning,
                "winner": winner,
                "confidence": confidence,
                "arguments_considered": len(formatted_arguments),
            },
            tags=["decision", "final"],
            importance=1.0,
            segment="decisions",
            metadata={"question": question, "decision": decision, "winner": winner},
        )

        return {
            "decision": decision,
            "reasoning": reasoning,
            "winner": winner,
            "confidence": confidence,
        }


# Workflow function


def debate_decision_workflow(question: str, rounds: int = 2) -> Dict[str, Any]:
    """
    Run debate-decision multi-agent workflow.

    This workflow demonstrates adversarial reasoning for critical decisions:
    1. ProponentAgent presents case FOR the decision
    2. OpponentAgent presents case AGAINST the decision
    3. ProponentAgent rebuts opponent's case
    4. OpponentAgent rebuts proponent's case
    5. JudgeAgent reads all arguments/rebuttals
    6. JudgeAgent evaluates and makes final decision

    Args:
        question: Decision question to debate
        rounds: Number of debate rounds (default: 2)

    Returns:
        Dictionary containing:
        - question: Original decision question
        - proponent_argument: Proponent's initial argument
        - opponent_argument: Opponent's initial argument
        - proponent_rebuttal: Proponent's rebuttal
        - opponent_rebuttal: Opponent's rebuttal
        - decision: Judge's final decision
        - stats: Shared memory statistics
    """
    # Setup shared memory pool
    shared_pool = SharedMemoryPool()
    config = DebateConfig(rounds=rounds)

    # Create agents
    proponent = ProponentAgent(config, shared_pool, agent_id="proponent")
    opponent = OpponentAgent(config, shared_pool, agent_id="opponent")
    judge = JudgeAgent(config, shared_pool, agent_id="judge")

    print(f"\n{'='*60}")
    print(f"Debate-Decision Pattern: {question}")
    print(f"{'='*60}\n")

    # Round 1: Initial Arguments
    print("Round 1: Initial Arguments")
    print("-" * 60)

    print("  Proponent presenting case FOR...")
    proponent_arg = proponent.argue(question)
    print(f"  - Argument: {proponent_arg['argument'][:80]}...")
    print(f"  - Evidence: {proponent_arg['evidence'][:80]}...")
    print(f"  - Confidence: {proponent_arg['confidence']}")

    print("\n  Opponent presenting case AGAINST...")
    opponent_arg = opponent.argue(question)
    print(f"  - Argument: {opponent_arg['argument'][:80]}...")
    print(f"  - Risks: {opponent_arg['risks'][:80]}...")
    print(f"  - Confidence: {opponent_arg['confidence']}")

    # Round 2: Rebuttals
    print("\nRound 2: Rebuttals")
    print("-" * 60)

    print("  Proponent rebutting opponent's case...")
    proponent_rebut = proponent.rebut(question, opponent_arg["argument"])
    print(f"  - Rebuttal: {proponent_rebut['argument'][:80]}...")
    print(f"  - Evidence: {proponent_rebut['evidence'][:80]}...")

    print("\n  Opponent rebutting proponent's case...")
    opponent_rebut = opponent.rebut(question, proponent_arg["argument"])
    print(f"  - Rebuttal: {opponent_rebut['argument'][:80]}...")
    print(f"  - Risks: {opponent_rebut['risks'][:80]}...")

    # Round 3: Evaluation
    print("\nRound 3: Judge Evaluation")
    print("-" * 60)

    print("  Judge evaluating all arguments...")
    decision = judge.evaluate(question)
    print(f"  - Decision: {decision['decision']}")
    print(f"  - Winner: {decision['winner']}")
    print(f"  - Reasoning: {decision['reasoning'][:100]}...")
    print(f"  - Confidence: {decision['confidence']}")

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
        "proponent_argument": proponent_arg,
        "opponent_argument": opponent_arg,
        "proponent_rebuttal": proponent_rebut,
        "opponent_rebuttal": opponent_rebut,
        "decision": decision,
        "stats": stats,
    }


# Main execution
if __name__ == "__main__":
    # Run example workflow
    result = debate_decision_workflow(
        "Should we migrate our monolithic application to microservices architecture?"
    )

    print("\nWorkflow Complete!")
    print(f"Question: {result['question']}")
    print(f"Decision: {result['decision']['decision']}")
    print(f"Winner: {result['decision']['winner']}")
    print(f"Confidence: {result['decision']['confidence']}")
