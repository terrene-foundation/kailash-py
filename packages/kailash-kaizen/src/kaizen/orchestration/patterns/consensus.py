"""
ConsensusPattern - Multi-Agent Coordination Pattern

Production-ready consensus-based decision making pattern with democratic voting.
Provides zero-config factory function with progressive configuration support.

Pattern Components:
- ProposerAgent: Creates proposals for voting
- VoterAgent: Evaluates proposals and casts votes (with perspectives)
- AggregatorAgent: Tallies votes and determines consensus
- ConsensusPattern: Pattern container with convenience methods

Usage:
    # Zero-config
    from kaizen.orchestration.patterns import create_consensus_pattern

    pattern = create_consensus_pattern()
    proposal = pattern.create_proposal("Should we adopt AI?", "Important decision")
    for voter in pattern.voters:
        voter.vote(proposal)
    result = pattern.determine_consensus(proposal["proposal_id"])

    # Progressive configuration
    pattern = create_consensus_pattern(
        num_voters=5,
        voter_perspectives=["technical", "business", "security", "legal", "ops"],
        model="gpt-4",
        temperature=0.7
    )

Architecture:
    User Request → ProposerAgent (creates proposal)
                → SharedMemoryPool (writes proposal)
                → VoterAgents (read & vote)
                → SharedMemoryPool (write votes)
                → AggregatorAgent (tallies & determines consensus)
                → Final Decision

Author: Kaizen Framework Team
Created: 2025-10-04 (Phase 3, Multi-Agent Patterns)
Reference: examples/2-multi-agent/consensus-voting/ (when created)
"""

import json
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from kaizen.tools.registry import ToolRegistry

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.patterns.base_pattern import BaseMultiAgentPattern
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Signature Definitions
# ============================================================================


class ProposalCreationSignature(Signature):
    """Signature for proposal creation."""

    topic: str = InputField(desc="Topic for proposal")
    context: str = InputField(desc="Additional context", default="")

    proposal: str = OutputField(desc="Detailed proposal")
    rationale: str = OutputField(desc="Reasoning for proposal", default="")


class VotingSignature(Signature):
    """Signature for voting on proposals."""

    proposal: str = InputField(desc="Proposal to evaluate")
    voter_perspective: str = InputField(
        desc="Voter's perspective/role", default="general"
    )

    vote: str = OutputField(desc="Vote: approve/reject/abstain", default="abstain")
    reasoning: str = OutputField(desc="Vote reasoning", default="")
    confidence: float = OutputField(desc="Confidence level 0.0-1.0", default=0.5)


class ConsensusAggregationSignature(Signature):
    """Signature for consensus aggregation."""

    votes: str = InputField(desc="All votes (JSON list)")
    proposal: str = InputField(desc="Original proposal")

    consensus_reached: str = OutputField(desc="Consensus: yes/no", default="no")
    final_decision: str = OutputField(desc="Final decision", default="")
    vote_summary: str = OutputField(desc="Summary of votes", default="")


# ============================================================================
# Agent Implementations
# ============================================================================


class ProposerAgent(BaseAgent):
    """
    ProposerAgent: Creates proposals for voting.

    Responsibilities:
    - Create detailed proposals from topics
    - Provide rationale for proposals
    - Write proposals to shared memory
    - Generate unique proposal IDs

    Shared Memory Behavior:
    - Writes proposals with tags: ["proposal", request_id]
    - Segment: "proposals"
    - Importance: 0.8
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize ProposerAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        super().__init__(
            config=config,
            signature=ProposalCreationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
            mcp_servers=mcp_servers,
        )
        self.tool_registry = tool_registry

    def create_proposal(self, topic: str, context: str = "") -> Dict[str, Any]:
        """
        Create a proposal for voting.

        Args:
            topic: Topic for proposal
            context: Additional context

        Returns:
            Proposal dict with proposal_id, request_id, topic, proposal, rationale
        """
        # Generate IDs
        proposal_id = f"proposal_{uuid.uuid4().hex[:8]}"
        request_id = f"request_{uuid.uuid4().hex[:8]}"

        # Execute proposal creation via base agent
        result = self.run(
            topic=topic, context=context, session_id=f"create_{proposal_id}"
        )

        # Build proposal dict
        proposal_data = {
            "proposal_id": proposal_id,
            "request_id": request_id,
            "topic": topic,
            "context": context,
            "proposal": result.get("proposal", ""),
            "rationale": result.get("rationale", ""),
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(proposal_data),
                    "tags": ["proposal", request_id],
                    "importance": 0.8,
                    "segment": "proposals",
                    "metadata": {
                        "proposal_id": proposal_id,
                        "request_id": request_id,
                        "topic": topic,
                    },
                }
            )

        return proposal_data


class VoterAgent(BaseAgent):
    """
    VoterAgent: Evaluates proposals and casts votes.

    Responsibilities:
    - Read proposals from shared memory
    - Evaluate proposals from specific perspective
    - Cast votes (approve/reject/abstain)
    - Provide reasoning and confidence
    - Write votes to shared memory

    Shared Memory Behavior:
    - Reads proposals with tags: ["proposal"]
    - Writes votes with tags: ["vote", proposal_id, agent_id]
    - Segment: "votes"
    - Importance: 0.8
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        perspective: str = "general",
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize VoterAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
            perspective: Voter's perspective/role (e.g., "technical", "business")
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        super().__init__(
            config=config,
            signature=VotingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
            mcp_servers=mcp_servers,
        )
        self.perspective = perspective
        self.tool_registry = tool_registry

    def get_proposals(self) -> List[Dict[str, Any]]:
        """
        Get all proposals from shared memory.

        Returns:
            List of proposal dicts
        """
        if not self.shared_memory:
            return []

        # Read proposals
        insights = self.shared_memory.read_relevant(
            agent_id=self.agent_id, tags=["proposal"], exclude_own=True, limit=50
        )

        proposals = []
        for insight in insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    proposal = json.loads(content)
                    proposals.append(proposal)
                except json.JSONDecodeError:
                    continue
            else:
                proposals.append(content)

        return proposals

    def vote(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Vote on a proposal.

        Args:
            proposal: Proposal dict to vote on

        Returns:
            Vote dict with vote, reasoning, confidence, proposal_id
        """
        proposal_id = proposal.get("proposal_id", "unknown")
        proposal_text = proposal.get("proposal", "")
        topic = proposal.get("topic", "")

        # Execute vote via base agent
        result = self.run(
            proposal=f"{topic}: {proposal_text}",
            voter_perspective=self.perspective,
            session_id=f"vote_{proposal_id}_{self.agent_id}",
        )

        # Extract vote data
        vote = result.get("vote", "abstain")
        reasoning = result.get("reasoning", "")
        confidence = result.get("confidence", 0.5)

        # Validate vote
        valid_votes = ["approve", "reject", "abstain"]
        if vote not in valid_votes:
            vote = "abstain"

        # Validate confidence
        try:
            confidence = float(confidence)
            if confidence < 0.0:
                confidence = 0.0
            elif confidence > 1.0:
                confidence = 1.0
        except (ValueError, TypeError):
            confidence = 0.5

        # Build vote dict
        vote_data = {
            "proposal_id": proposal_id,
            "voter_id": self.agent_id,
            "perspective": self.perspective,
            "vote": vote,
            "reasoning": reasoning,
            "confidence": confidence,
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(vote_data),
                    "tags": ["vote", proposal_id, self.agent_id],
                    "importance": 0.8,
                    "segment": "votes",
                    "metadata": {
                        "proposal_id": proposal_id,
                        "vote": vote,
                        "voter_id": self.agent_id,
                    },
                }
            )

        return vote_data


class AggregatorAgent(BaseAgent):
    """
    AggregatorAgent: Tallies votes and determines consensus.

    Responsibilities:
    - Read votes from shared memory
    - Tally votes by proposal
    - Determine if consensus reached (>50% approve)
    - Provide vote summary
    - Return final decision

    Shared Memory Behavior:
    - Reads votes with tags: ["vote", proposal_id]
    - Does NOT write to shared memory (read-only)
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize AggregatorAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        super().__init__(
            config=config,
            signature=ConsensusAggregationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
            mcp_servers=mcp_servers,
        )
        self.tool_registry = tool_registry

    def aggregate_votes(self, proposal_id: str) -> Dict[str, Any]:
        """
        Aggregate votes for a proposal and determine consensus.

        Args:
            proposal_id: Proposal identifier

        Returns:
            Dict with consensus_reached, final_decision, vote_summary
        """
        # Read votes from shared memory
        votes = []
        if self.shared_memory:
            vote_insights = self.shared_memory.read_relevant(
                agent_id=self.agent_id,
                tags=["vote", proposal_id],
                exclude_own=True,
                limit=100,
            )

            for insight in vote_insights:
                content = insight.get("content", "{}")
                if isinstance(content, str):
                    try:
                        vote = json.loads(content)
                        # Double-check vote is for this proposal
                        if vote.get("proposal_id") == proposal_id:
                            votes.append(vote)
                    except json.JSONDecodeError:
                        continue
                else:
                    # Double-check vote is for this proposal
                    if content.get("proposal_id") == proposal_id:
                        votes.append(content)

        # Get proposal
        proposal_text = ""
        if self.shared_memory:
            proposal_insights = self.shared_memory.read_relevant(
                agent_id=self.agent_id, tags=["proposal"], exclude_own=True, limit=50
            )
            for insight in proposal_insights:
                try:
                    content = insight.get("content", "{}")
                    if isinstance(content, str):
                        proposal_data = json.loads(content)
                    else:
                        proposal_data = content

                    if proposal_data.get("proposal_id") == proposal_id:
                        proposal_text = proposal_data.get("proposal", "")
                        break
                except (json.JSONDecodeError, KeyError):
                    continue

        # Execute aggregation via base agent
        result = self.run(
            votes=json.dumps(votes),
            proposal=proposal_text,
            session_id=f"aggregate_{proposal_id}",
        )

        # Ensure proper types for return values
        vote_summary = result.get("vote_summary", "")
        if not isinstance(vote_summary, str):
            vote_summary = str(vote_summary) if vote_summary else ""

        return {
            "consensus_reached": result.get("consensus_reached", "no"),
            "final_decision": result.get("final_decision", ""),
            "vote_summary": vote_summary,
            "votes": votes,
        }

    def check_consensus_reached(self, proposal_id: str) -> bool:
        """
        Check if consensus reached for a proposal.

        Args:
            proposal_id: Proposal identifier

        Returns:
            True if consensus reached, False otherwise
        """
        # Read votes
        votes = []
        if self.shared_memory:
            vote_insights = self.shared_memory.read_relevant(
                agent_id=self.agent_id,
                tags=["vote", proposal_id],
                exclude_own=True,
                limit=100,
            )

            for insight in vote_insights:
                content = insight.get("content", "{}")
                if isinstance(content, str):
                    try:
                        vote = json.loads(content)
                        votes.append(vote)
                    except json.JSONDecodeError:
                        continue

        # No votes = no consensus
        if len(votes) == 0:
            return False

        # Count approvals (simple majority >50%)
        approvals = sum(1 for v in votes if v.get("vote") == "approve")
        total = len(votes)

        return approvals > (total / 2)


# ============================================================================
# Pattern Container
# ============================================================================


@dataclass
class ConsensusPattern(BaseMultiAgentPattern):
    """
    ConsensusPattern: Container for consensus-based decision making.

    Provides convenience methods for common operations:
    - create_proposal(): Create proposal for voting
    - collect_votes(): Collect all votes for proposal
    - determine_consensus(): Determine consensus decision

    Attributes:
        proposer: ProposerAgent instance
        voters: List of VoterAgent instances
        aggregator: AggregatorAgent instance
        shared_memory: SharedMemoryPool for coordination
    """

    proposer: ProposerAgent
    voters: List[VoterAgent]
    aggregator: AggregatorAgent

    def create_proposal(self, topic: str, context: str = "") -> Dict[str, Any]:
        """
        Convenience method: Create proposal.

        Args:
            topic: Topic for proposal
            context: Additional context

        Returns:
            Proposal dict
        """
        return self.proposer.create_proposal(topic, context)

    def collect_votes(self, proposal_id: str) -> List[Dict[str, Any]]:
        """
        Convenience method: Collect all votes for proposal.

        Args:
            proposal_id: Proposal identifier

        Returns:
            List of vote dicts
        """
        if not self.shared_memory:
            return []

        vote_insights = self.shared_memory.read_relevant(
            agent_id="_pattern_",
            tags=["vote", proposal_id],
            exclude_own=False,
            limit=100,
        )

        votes = []
        for insight in vote_insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    vote = json.loads(content)
                    votes.append(vote)
                except json.JSONDecodeError:
                    continue
            else:
                votes.append(content)

        return votes

    def determine_consensus(self, proposal_id: str) -> Dict[str, Any]:
        """
        Convenience method: Determine consensus.

        Args:
            proposal_id: Proposal identifier

        Returns:
            Consensus result dict
        """
        return self.aggregator.aggregate_votes(proposal_id)

    def get_agents(self) -> List[BaseAgent]:
        """
        Get all agents in this pattern.

        Returns:
            List of agent instances (filters out None agents)
        """
        agents = []
        if self.proposer:
            agents.append(self.proposer)
        agents.extend(self.voters)
        if self.aggregator:
            agents.append(self.aggregator)
        return agents

    def get_agent_ids(self) -> List[str]:
        """
        Get all agent IDs in this pattern.

        Returns:
            List of agent ID strings
        """
        return [agent.agent_id for agent in self.get_agents() if agent is not None]

    async def execute_async(self, topic: str, context: str = "") -> Dict[str, Any]:
        """
        Execute consensus pattern asynchronously using AsyncLocalRuntime.

        This method provides async execution for Docker/FastAPI environments.
        For synchronous execution in CLI/scripts, use the create_proposal(),
        vote(), and determine_consensus() methods directly.

        Args:
            topic: Topic for proposal
            context: Additional context

        Returns:
            Dict with consensus_reached, final_decision, vote_summary, and votes

        Example:
            >>> pattern = create_consensus_pattern()
            >>> result = await pattern.execute_async("Should we adopt AI?")
            >>> print(result['final_decision'])
        """
        # Create proposal
        proposal = self.create_proposal(topic, context)
        proposal_id = proposal.get("proposal_id")

        # Collect votes from all voters
        for voter in self.voters:
            voter.vote(proposal)

        # Determine consensus
        return self.determine_consensus(proposal_id)


# ============================================================================
# Factory Function
# ============================================================================


def create_consensus_pattern(
    num_voters: int = 3,
    voter_perspectives: Optional[List[str]] = None,
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    proposer_config: Optional[Dict[str, Any]] = None,
    voter_config: Optional[Dict[str, Any]] = None,
    aggregator_config: Optional[Dict[str, Any]] = None,
) -> ConsensusPattern:
    """
    Create consensus pattern with zero-config defaults.

    Zero-Config Usage:
        >>> pattern = create_consensus_pattern()
        >>> proposal = pattern.create_proposal("Should we adopt AI?")
        >>> for voter in pattern.voters:
        ...     voter.vote(proposal)
        >>> result = pattern.determine_consensus(proposal["proposal_id"])

    Progressive Configuration:
        >>> pattern = create_consensus_pattern(
        ...     num_voters=5,
        ...     voter_perspectives=["technical", "business", "security", "legal", "ops"],
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )

    Separate Agent Configs:
        >>> pattern = create_consensus_pattern(
        ...     num_voters=3,
        ...     proposer_config={'model': 'gpt-4'},
        ...     voter_config={'model': 'gpt-3.5-turbo'}
        ... )

    Args:
        num_voters: Number of voter agents (default: 3)
        voter_perspectives: List of perspectives for voters (default: ["general"] * num_voters)
        llm_provider: LLM provider (default: from env or "openai")
        model: Model name (default: from env or "gpt-3.5-turbo")
        temperature: Temperature (default: 0.7)
        max_tokens: Max tokens (default: 1000)
        shared_memory: Existing SharedMemoryPool (default: creates new)
        proposer_config: Override proposer config
        voter_config: Override voter config
        aggregator_config: Override aggregator config

    Returns:
        ConsensusPattern: Pattern ready to use
    """
    # Create shared memory if not provided
    if shared_memory is None:
        shared_memory = SharedMemoryPool()

    # Build base config from parameters (or use defaults)
    base_config_dict = {
        "llm_provider": llm_provider or os.getenv("KAIZEN_LLM_PROVIDER", "openai"),
        "model": model or os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo"),
        "temperature": temperature if temperature is not None else 0.7,
        "max_tokens": max_tokens if max_tokens is not None else 1000,
    }

    # Build proposer config
    proposer_cfg_dict = {**base_config_dict}
    if proposer_config:
        proposer_cfg_dict.update(proposer_config)
    proposer_cfg = BaseAgentConfig(**proposer_cfg_dict)

    # Build voter config
    voter_cfg_dict = {**base_config_dict}
    if voter_config:
        voter_cfg_dict.update(voter_config)
    voter_cfg = BaseAgentConfig(**voter_cfg_dict)

    # Build aggregator config
    aggregator_cfg_dict = {**base_config_dict}
    if aggregator_config:
        aggregator_cfg_dict.update(aggregator_config)
    aggregator_cfg = BaseAgentConfig(**aggregator_cfg_dict)

    # Determine voter perspectives
    if voter_perspectives:
        # Use provided perspectives (overrides num_voters)
        num_voters = len(voter_perspectives)
        perspectives = voter_perspectives
    else:
        # Use default perspective for all voters
        perspectives = ["general"] * num_voters

    # Create proposer
    proposer = ProposerAgent(
        config=proposer_cfg, shared_memory=shared_memory, agent_id="proposer_1"
    )

    # Create voters
    voters = [
        VoterAgent(
            config=voter_cfg,
            shared_memory=shared_memory,
            agent_id=f"voter_{i+1}",
            perspective=perspectives[i],
        )
        for i in range(num_voters)
    ]

    # Create aggregator
    aggregator = AggregatorAgent(
        config=aggregator_cfg, shared_memory=shared_memory, agent_id="aggregator_1"
    )

    return ConsensusPattern(
        proposer=proposer,
        voters=voters,
        aggregator=aggregator,
        shared_memory=shared_memory,
    )
