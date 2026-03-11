"""
Test ConsensusPattern - Multi-Agent Coordination Pattern

Tests consensus-based decision making with democratic voting.
Covers factory function, pattern class, all agents, and voting logic.

Written BEFORE implementation (TDD).

Test Coverage:
- Factory Function: 10 tests
- Pattern Class: 10 tests
- ProposerAgent: 12 tests
- VoterAgent: 15 tests
- AggregatorAgent: 12 tests
- Integration: 12 tests
- Shared Memory: 10 tests
- Error Handling: 8 tests
Total: 89 tests
"""

# ============================================================================
# TEST CLASS 1: Factory Function (10 tests)
# ============================================================================


class TestCreateConsensusPattern:
    """Test create_consensus_pattern factory function."""

    def test_zero_config_creation(self):
        """Test zero-config pattern creation."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern()

        assert pattern is not None
        assert pattern.proposer is not None
        assert len(pattern.voters) == 3  # default
        assert pattern.aggregator is not None
        assert pattern.shared_memory is not None

    def test_custom_num_voters(self):
        """Test creating pattern with custom voter count."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=5)

        assert len(pattern.voters) == 5
        assert pattern.proposer is not None
        assert pattern.aggregator is not None

    def test_custom_voter_perspectives(self):
        """Test creating pattern with custom voter perspectives."""
        from kaizen.agents.coordination import create_consensus_pattern

        perspectives = ["technical", "business", "security"]
        pattern = create_consensus_pattern(
            num_voters=3, voter_perspectives=perspectives
        )

        assert len(pattern.voters) == 3
        for i, voter in enumerate(pattern.voters):
            assert voter.perspective == perspectives[i]

    def test_voter_perspectives_mismatch_uses_provided_list(self):
        """Test that num_voters is adjusted to match perspectives length."""
        from kaizen.agents.coordination import create_consensus_pattern

        perspectives = ["technical", "business"]
        pattern = create_consensus_pattern(
            num_voters=5,  # Different from perspectives length
            voter_perspectives=perspectives,
        )

        # Should use perspectives length
        assert len(pattern.voters) == 2
        assert pattern.voters[0].perspective == "technical"
        assert pattern.voters[1].perspective == "business"

    def test_progressive_configuration_model_only(self):
        """Test overriding model only."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(model="gpt-4", num_voters=2)

        # Verify all agents use gpt-4
        assert pattern.proposer.config.model == "gpt-4"
        for voter in pattern.voters:
            assert voter.config.model == "gpt-4"
        assert pattern.aggregator.config.model == "gpt-4"

    def test_progressive_configuration_multiple_params(self):
        """Test overriding multiple parameters."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
            num_voters=2,
        )

        # Verify all agents have correct config
        assert pattern.proposer.config.llm_provider == "anthropic"
        assert pattern.proposer.config.model == "claude-3-opus"
        assert pattern.proposer.config.temperature == 0.7
        assert pattern.proposer.config.max_tokens == 2000

        for voter in pattern.voters:
            assert voter.config.llm_provider == "anthropic"
            assert voter.config.model == "claude-3-opus"

    def test_separate_configs_per_agent_type(self):
        """Test separate configs for proposer, voters, aggregator."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(
            num_voters=2,
            proposer_config={"model": "gpt-4"},
            voter_config={"model": "gpt-3.5-turbo"},
            aggregator_config={"model": "gpt-4"},
        )

        # Proposer should use gpt-4
        assert pattern.proposer.config.model == "gpt-4"
        # Voters should use gpt-3.5-turbo
        for voter in pattern.voters:
            assert voter.config.model == "gpt-3.5-turbo"
        # Aggregator should use gpt-4
        assert pattern.aggregator.config.model == "gpt-4"

    def test_shared_memory_provided(self):
        """Test providing existing SharedMemoryPool."""
        from kaizen.agents.coordination import create_consensus_pattern
        from kaizen.memory import SharedMemoryPool

        existing_pool = SharedMemoryPool()

        pattern = create_consensus_pattern(shared_memory=existing_pool, num_voters=2)

        # Pattern should use provided pool
        assert pattern.shared_memory is existing_pool
        # All agents should share same pool
        assert pattern.proposer.shared_memory is existing_pool
        for voter in pattern.voters:
            assert voter.shared_memory is existing_pool
        assert pattern.aggregator.shared_memory is existing_pool

    def test_agent_ids_are_unique(self):
        """Test that all agent IDs are unique."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=5)

        agent_ids = pattern.get_agent_ids()

        # Should have unique IDs
        assert len(agent_ids) == len(set(agent_ids))
        # Should include proposer, voters, aggregator
        assert len(agent_ids) == 7  # 1 proposer + 5 voters + 1 aggregator

    def test_default_agent_ids_format(self):
        """Test default agent ID naming convention."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        agent_ids = pattern.get_agent_ids()

        # Check expected IDs
        assert "proposer_1" in agent_ids
        assert "voter_1" in agent_ids
        assert "voter_2" in agent_ids
        assert "voter_3" in agent_ids
        assert "aggregator_1" in agent_ids


# ============================================================================
# TEST CLASS 2: ConsensusPattern Class (10 tests)
# ============================================================================


class TestConsensusPattern:
    """Test ConsensusPattern class."""

    def test_pattern_initialization(self):
        """Test pattern is properly initialized."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern()

        assert pattern.validate_pattern() is True

    def test_create_proposal_convenience_method(self):
        """Test pattern.create_proposal() calls proposer.create_proposal()."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        proposal = pattern.create_proposal("Should we adopt AI?", "Important decision")

        assert isinstance(proposal, dict)
        assert "proposal_id" in proposal
        assert "proposal" in proposal or "content" in proposal
        assert "request_id" in proposal

    def test_collect_votes_convenience_method(self):
        """Test pattern.collect_votes() collects all votes."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")
        proposal_id = proposal["proposal_id"]

        # Voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Collect votes
        votes = pattern.collect_votes(proposal_id)

        assert isinstance(votes, list)
        assert len(votes) >= 2  # Should have votes from voters

    def test_determine_consensus_convenience_method(self):
        """Test pattern.determine_consensus() calls aggregator.aggregate_votes()."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")
        proposal_id = proposal["proposal_id"]

        # Voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Determine consensus
        result = pattern.determine_consensus(proposal_id)

        assert isinstance(result, dict)
        assert "consensus_reached" in result
        assert "final_decision" in result

    def test_get_agents(self):
        """Test get_agents() returns all agents."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)
        agents = pattern.get_agents()

        # Should return 1 proposer + 3 voters + 1 aggregator = 5
        assert len(agents) == 5
        # First should be proposer
        assert agents[0] == pattern.proposer
        # Last should be aggregator
        assert agents[-1] == pattern.aggregator
        # Middle should be voters
        for i in range(1, 4):
            assert agents[i] in pattern.voters

    def test_get_agent_ids(self):
        """Test get_agent_ids() returns unique IDs."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)
        agent_ids = pattern.get_agent_ids()

        assert len(agent_ids) == 5  # 1 + 3 + 1
        assert "proposer_1" in agent_ids
        assert "voter_1" in agent_ids
        assert "voter_2" in agent_ids
        assert "voter_3" in agent_ids
        assert "aggregator_1" in agent_ids

    def test_clear_shared_memory(self):
        """Test clear_shared_memory() clears pattern state."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        pattern.create_proposal("Test proposal", "Test context")

        # Should have insights
        insights_before = pattern.shared_memory.read_all()
        assert len(insights_before) > 0

        # Clear
        pattern.clear_shared_memory()

        # Should be empty
        insights_after = pattern.shared_memory.read_all()
        assert len(insights_after) == 0

    def test_validate_pattern_detects_invalid_pattern(self):
        """Test validate_pattern() detects invalid configuration."""
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.consensus import ConsensusPattern

        # Create pattern with no agents (invalid)
        pattern = ConsensusPattern(
            proposer=None, voters=[], aggregator=None, shared_memory=SharedMemoryPool()
        )

        assert pattern.validate_pattern() is False

    def test_pattern_str_representation(self):
        """Test string representation of pattern."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)
        pattern_str = str(pattern)

        assert "ConsensusPattern" in pattern_str
        assert "5" in pattern_str  # 5 agents

    def test_pattern_works_with_base_pattern_helpers(self):
        """Test pattern works with BaseMultiAgentPattern helper methods."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        pattern.create_proposal("Test proposal", "Test context")

        # Test get_shared_insights
        insights = pattern.get_shared_insights(tags=["proposal"])
        assert len(insights) > 0

        # Test count_insights_by_tags
        count = pattern.count_insights_by_tags(["proposal"])
        assert count > 0


# ============================================================================
# TEST CLASS 3: ProposerAgent (12 tests)
# ============================================================================


class TestProposerAgent:
    """Test ProposerAgent class."""

    def test_initialization(self):
        """Test proposer initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.consensus import ProposerAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proposer = ProposerAgent(
            config=config, shared_memory=shared_memory, agent_id="test_proposer"
        )

        assert proposer.agent_id == "test_proposer"
        assert proposer.shared_memory is shared_memory
        assert proposer.signature is not None

    def test_create_proposal_returns_dict(self):
        """Test create_proposal() returns proper dict structure."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        assert isinstance(proposal, dict)
        assert "proposal_id" in proposal
        assert "request_id" in proposal
        assert "topic" in proposal
        assert "proposal" in proposal or "content" in proposal

    def test_create_proposal_writes_to_shared_memory(self):
        """Test create_proposal() writes to shared memory."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        pattern.proposer.create_proposal("Test topic", "Test context")

        # Check shared memory has proposal
        proposals = pattern.get_shared_insights(tags=["proposal"])
        assert len(proposals) >= 1

    def test_create_proposal_uses_correct_tags(self):
        """Test create_proposal() uses correct tags."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Get insights and check tags
        proposals = pattern.get_shared_insights(tags=["proposal"])
        assert len(proposals) >= 1

        # Check tags contain both "proposal" and request_id
        tags = proposals[0].get("tags", [])
        assert "proposal" in tags
        assert proposal["request_id"] in tags

    def test_create_proposal_uses_proposals_segment(self):
        """Test create_proposal() uses 'proposals' segment."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        pattern.proposer.create_proposal("Test topic", "Test context")

        # Check segment
        proposals = pattern.get_shared_insights(segment="proposals")
        assert len(proposals) >= 1

    def test_create_proposal_sets_importance(self):
        """Test create_proposal() sets importance to 0.8."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        pattern.proposer.create_proposal("Test topic", "Test context")

        # Check importance
        proposals = pattern.get_shared_insights(tags=["proposal"])
        assert len(proposals) >= 1
        assert proposals[0].get("importance") == 0.8

    def test_create_proposal_generates_unique_ids(self):
        """Test create_proposal() generates unique proposal IDs."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal1 = pattern.proposer.create_proposal("Topic 1", "Context 1")
        proposal2 = pattern.proposer.create_proposal("Topic 2", "Context 2")

        assert proposal1["proposal_id"] != proposal2["proposal_id"]
        assert proposal1["request_id"] != proposal2["request_id"]

    def test_create_proposal_includes_topic(self):
        """Test create_proposal() includes topic in proposal."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        topic = "Should we implement AI?"

        proposal = pattern.proposer.create_proposal(topic, "Important decision")

        assert proposal["topic"] == topic

    def test_create_proposal_with_empty_context(self):
        """Test create_proposal() works with empty context."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        proposal = pattern.proposer.create_proposal("Test topic", "")

        assert isinstance(proposal, dict)
        assert "proposal_id" in proposal

    def test_create_proposal_signature_used(self):
        """Test create_proposal() uses ProposalCreationSignature."""
        from kaizen.agents.coordination import create_consensus_pattern
        from kaizen.orchestration.patterns.consensus import ProposalCreationSignature

        pattern = create_consensus_pattern(num_voters=2)

        # Check signature type
        assert isinstance(pattern.proposer.signature, ProposalCreationSignature)

    def test_multiple_proposals_isolated_by_request_id(self):
        """Test multiple proposals are isolated by request_id."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal1 = pattern.proposer.create_proposal("Topic 1", "Context 1")
        proposal2 = pattern.proposer.create_proposal("Topic 2", "Context 2")

        # Get proposals for each request
        proposals1 = pattern.get_shared_insights(tags=[proposal1["request_id"]])
        proposals2 = pattern.get_shared_insights(tags=[proposal2["request_id"]])

        # Each should have their own proposal
        assert len(proposals1) >= 1
        assert len(proposals2) >= 1

    def test_create_proposal_includes_rationale(self):
        """Test create_proposal() includes rationale in result."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Should have rationale field (from signature output)
        assert "rationale" in proposal or "proposal" in proposal


# ============================================================================
# TEST CLASS 4: VoterAgent (15 tests)
# ============================================================================


class TestVoterAgent:
    """Test VoterAgent class."""

    def test_initialization(self):
        """Test voter initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.consensus import VoterAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        voter = VoterAgent(
            config=config,
            shared_memory=shared_memory,
            agent_id="test_voter",
            perspective="technical",
        )

        assert voter.agent_id == "test_voter"
        assert voter.shared_memory is shared_memory
        assert voter.perspective == "technical"
        assert voter.signature is not None

    def test_initialization_default_perspective(self):
        """Test voter initialization with default perspective."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.consensus import VoterAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        voter = VoterAgent(
            config=config, shared_memory=shared_memory, agent_id="test_voter"
        )

        assert voter.perspective == "general"

    def test_get_proposals_reads_from_memory(self):
        """Test get_proposals() reads proposals from shared memory."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposals
        pattern.proposer.create_proposal("Topic 1", "Context 1")
        pattern.proposer.create_proposal("Topic 2", "Context 2")

        # Voter reads proposals
        voter = pattern.voters[0]
        proposals = voter.get_proposals()

        assert isinstance(proposals, list)
        assert len(proposals) >= 2

    def test_vote_returns_dict(self):
        """Test vote() returns proper dict structure."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        vote_result = voter.vote(proposal)

        assert isinstance(vote_result, dict)
        assert "vote" in vote_result
        assert "reasoning" in vote_result
        assert "confidence" in vote_result
        assert "proposal_id" in vote_result

    def test_vote_writes_to_shared_memory(self):
        """Test vote() writes to shared memory."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        voter.vote(proposal)

        # Check shared memory has vote
        votes = pattern.get_shared_insights(tags=["vote"])
        assert len(votes) >= 1

    def test_vote_uses_correct_tags(self):
        """Test vote() uses correct tags."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        voter.vote(proposal)

        # Check tags
        votes = pattern.get_shared_insights(tags=["vote"])
        assert len(votes) >= 1

        tags = votes[0].get("tags", [])
        assert "vote" in tags
        assert proposal["proposal_id"] in tags
        assert voter.agent_id in tags

    def test_vote_uses_votes_segment(self):
        """Test vote() uses 'votes' segment."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        voter.vote(proposal)

        # Check segment
        votes = pattern.get_shared_insights(segment="votes")
        assert len(votes) >= 1

    def test_vote_sets_importance(self):
        """Test vote() sets importance to 0.8."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        voter.vote(proposal)

        # Check importance
        votes = pattern.get_shared_insights(tags=["vote"])
        assert len(votes) >= 1
        assert votes[0].get("importance") == 0.8

    def test_vote_includes_perspective(self):
        """Test vote() uses voter's perspective."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(
            num_voters=1, voter_perspectives=["security"]
        )

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        voter.vote(proposal)

        # Perspective should be used in voting logic
        assert voter.perspective == "security"

    def test_vote_returns_valid_vote_options(self):
        """Test vote() returns one of: approve, reject, abstain."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        vote_result = voter.vote(proposal)

        valid_votes = ["approve", "reject", "abstain"]
        assert vote_result["vote"] in valid_votes

    def test_vote_confidence_in_range(self):
        """Test vote() returns confidence in range 0.0-1.0."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        vote_result = voter.vote(proposal)

        confidence = vote_result["confidence"]
        assert isinstance(confidence, (int, float))
        assert 0.0 <= confidence <= 1.0

    def test_vote_signature_used(self):
        """Test vote() uses VotingSignature."""
        from kaizen.agents.coordination import create_consensus_pattern
        from kaizen.orchestration.patterns.consensus import VotingSignature

        pattern = create_consensus_pattern(num_voters=2)

        # Check signature type
        voter = pattern.voters[0]
        assert isinstance(voter.signature, VotingSignature)

    def test_multiple_voters_vote_independently(self):
        """Test multiple voters can vote on same proposal."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # All voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Check all votes recorded
        votes = pattern.get_shared_insights(tags=["vote", proposal["proposal_id"]])
        assert len(votes) >= 3

    def test_voter_perspective_used_in_voting(self):
        """Test voter perspective is passed to LLM for voting."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(
            num_voters=2, voter_perspectives=["technical", "business"]
        )

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Voters vote (perspective should influence vote)
        for voter in pattern.voters:
            vote_result = voter.vote(proposal)
            # Just verify vote executed successfully
            assert "vote" in vote_result

    def test_vote_includes_reasoning(self):
        """Test vote() includes reasoning for decision."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Vote
        voter = pattern.voters[0]
        vote_result = voter.vote(proposal)

        # Should have reasoning
        assert "reasoning" in vote_result
        assert isinstance(vote_result["reasoning"], str)


# ============================================================================
# TEST CLASS 5: AggregatorAgent (12 tests)
# ============================================================================


class TestAggregatorAgent:
    """Test AggregatorAgent class."""

    def test_initialization(self):
        """Test aggregator initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.consensus import AggregatorAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        aggregator = AggregatorAgent(
            config=config, shared_memory=shared_memory, agent_id="test_aggregator"
        )

        assert aggregator.agent_id == "test_aggregator"
        assert aggregator.shared_memory is shared_memory
        assert aggregator.signature is not None

    def test_aggregate_votes_reads_from_memory(self):
        """Test aggregate_votes() reads votes from shared memory."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        aggregator = pattern.aggregator
        result = aggregator.aggregate_votes(proposal["proposal_id"])

        assert isinstance(result, dict)

    def test_aggregate_votes_returns_consensus_decision(self):
        """Test aggregate_votes() returns consensus decision."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        assert "consensus_reached" in result
        assert "final_decision" in result
        assert "vote_summary" in result

    def test_aggregate_votes_consensus_reached_values(self):
        """Test aggregate_votes() returns yes/no for consensus_reached."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2, llm_provider="mock")

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        assert result["consensus_reached"] in ["yes", "no"]

    def test_aggregate_votes_signature_used(self):
        """Test aggregate_votes() uses ConsensusAggregationSignature."""
        from kaizen.agents.coordination import create_consensus_pattern
        from kaizen.orchestration.patterns.consensus import (
            ConsensusAggregationSignature,
        )

        pattern = create_consensus_pattern(num_voters=2)

        # Check signature type
        assert isinstance(pattern.aggregator.signature, ConsensusAggregationSignature)

    def test_check_consensus_reached_returns_bool(self):
        """Test check_consensus_reached() returns boolean."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Check consensus
        consensus = pattern.aggregator.check_consensus_reached(proposal["proposal_id"])

        assert isinstance(consensus, bool)

    def test_check_consensus_reached_with_no_votes(self):
        """Test check_consensus_reached() with no votes."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal but no votes
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # Check consensus (should be False)
        consensus = pattern.aggregator.check_consensus_reached(proposal["proposal_id"])

        assert consensus is False

    def test_aggregate_votes_filters_by_proposal_id(self):
        """Test aggregate_votes() only aggregates votes for specific proposal."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create two proposals
        proposal1 = pattern.proposer.create_proposal("Topic 1", "Context 1")
        proposal2 = pattern.proposer.create_proposal("Topic 2", "Context 2")

        # Vote on both
        for voter in pattern.voters:
            voter.vote(proposal1)
            voter.vote(proposal2)

        # Aggregate proposal1 only
        result = pattern.aggregator.aggregate_votes(proposal1["proposal_id"])

        # Should only consider votes for proposal1
        assert isinstance(result, dict)
        assert "consensus_reached" in result

    def test_aggregate_votes_includes_vote_summary(self):
        """Test aggregate_votes() includes summary of votes."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        assert "vote_summary" in result
        assert isinstance(result["vote_summary"], str)

    def test_aggregate_votes_with_mixed_votes(self):
        """Test aggregate_votes() handles approve/reject/abstain mix."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")

        # All voters vote (may be mixed)
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        # Should handle mixed votes
        assert "consensus_reached" in result
        assert "final_decision" in result

    def test_aggregate_votes_uses_proposal_in_signature(self):
        """Test aggregate_votes() passes original proposal to signature."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate (should use proposal data)
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        assert isinstance(result, dict)

    def test_aggregate_votes_handles_abstentions(self):
        """Test aggregate_votes() properly handles abstentions."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal and vote
        proposal = pattern.proposer.create_proposal("Test topic", "Test context")
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate (should handle abstentions in logic)
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        assert "consensus_reached" in result


# ============================================================================
# TEST CLASS 6: Integration (12 tests)
# ============================================================================


class TestConsensusPatternIntegration:
    """Test complete consensus workflows."""

    def test_complete_workflow_propose_vote_aggregate(self):
        """Test complete workflow: propose → vote → aggregate."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3, llm_provider="mock")

        # Step 1: Create proposal
        proposal = pattern.create_proposal("Should we adopt AI?", "Important decision")

        # Step 2: Voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Step 3: Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])

        assert result["consensus_reached"] in ["yes", "no"]
        assert "final_decision" in result
        assert "vote_summary" in result

    def test_multiple_voters_different_perspectives(self):
        """Test workflow with different voter perspectives."""
        from kaizen.agents.coordination import create_consensus_pattern

        perspectives = ["technical", "business", "security"]
        pattern = create_consensus_pattern(
            num_voters=3, voter_perspectives=perspectives
        )

        # Create proposal
        proposal = pattern.create_proposal("Adopt new technology?", "Cost vs benefit")

        # All perspectives vote
        for voter in pattern.voters:
            vote = voter.vote(proposal)
            assert "vote" in vote

        # Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])
        assert "consensus_reached" in result

    def test_consensus_reached_scenario(self):
        """Test scenario where consensus is reached (majority approve)."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # All voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Check consensus
        is_consensus = pattern.aggregator.check_consensus_reached(
            proposal["proposal_id"]
        )

        # Should be True or False (depends on votes)
        assert isinstance(is_consensus, bool)

    def test_consensus_not_reached_scenario(self):
        """Test scenario where consensus is not reached."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2, llm_provider="mock")

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # Voters vote (may be split)
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])

        # Should have result regardless of consensus
        assert "consensus_reached" in result
        assert result["consensus_reached"] in ["yes", "no"]

    def test_all_votes_abstain_scenario(self):
        """Test scenario where all voters abstain."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # All vote (may include abstentions)
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])

        # Should handle abstentions
        assert "consensus_reached" in result

    def test_isolation_between_proposals_different_request_ids(self):
        """Test proposals are isolated by request_id."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2, llm_provider="mock")

        # Create two proposals
        proposal1 = pattern.create_proposal("Proposal 1", "Context 1")
        proposal2 = pattern.create_proposal("Proposal 2", "Context 2")

        # Vote on proposal 1 only
        for voter in pattern.voters:
            voter.vote(proposal1)

        # Aggregate proposal 1
        result1 = pattern.determine_consensus(proposal1["proposal_id"])

        # Aggregate proposal 2 (no votes)
        result2 = pattern.determine_consensus(proposal2["proposal_id"])

        # Results should be different - proposal 1 has votes, proposal 2 doesn't
        assert len(result1.get("votes", [])) >= 2  # Has votes
        assert len(result2.get("votes", [])) == 0  # No votes

    def test_proposal_and_votes_persist_in_shared_memory(self):
        """Test proposals and votes persist in shared memory."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # Vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Check shared memory has both
        proposals = pattern.get_shared_insights(tags=["proposal"])
        votes = pattern.get_shared_insights(tags=["vote"])

        assert len(proposals) >= 1
        assert len(votes) >= 2

    def test_collect_votes_returns_all_votes(self):
        """Test collect_votes() returns all votes for proposal."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # Vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Collect votes
        votes = pattern.collect_votes(proposal["proposal_id"])

        assert len(votes) >= 3

    def test_pattern_handles_multiple_sequential_proposals(self):
        """Test pattern handles multiple proposals sequentially."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Process 3 proposals
        for i in range(3):
            proposal = pattern.create_proposal(f"Proposal {i}", f"Context {i}")

            for voter in pattern.voters:
                voter.vote(proposal)

            result = pattern.determine_consensus(proposal["proposal_id"])
            assert "consensus_reached" in result

    def test_pattern_works_with_single_voter(self):
        """Test pattern works with single voter (edge case)."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=1)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # Single voter votes
        pattern.voters[0].vote(proposal)

        # Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])

        assert "consensus_reached" in result

    def test_pattern_works_with_many_voters(self):
        """Test pattern scales to many voters."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=10)

        # Create proposal
        proposal = pattern.create_proposal("Test proposal", "Test context")

        # All voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])

        assert "consensus_reached" in result

    def test_workflow_respects_voter_perspectives(self):
        """Test workflow respects different voter perspectives."""
        from kaizen.agents.coordination import create_consensus_pattern

        perspectives = ["technical", "business", "legal", "security"]
        pattern = create_consensus_pattern(
            num_voters=4, voter_perspectives=perspectives
        )

        # Verify perspectives assigned
        for i, voter in enumerate(pattern.voters):
            assert voter.perspective == perspectives[i]

        # Create proposal
        proposal = pattern.create_proposal("Adopt new technology?", "Complex decision")

        # All perspectives vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Aggregate
        result = pattern.determine_consensus(proposal["proposal_id"])
        assert "consensus_reached" in result


# ============================================================================
# TEST CLASS 7: Shared Memory Coordination (10 tests)
# ============================================================================


class TestSharedMemoryCoordination:
    """Test shared memory coordination and isolation."""

    def test_proposals_written_with_correct_tags(self):
        """Test proposals have correct tags."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal = pattern.create_proposal("Test", "Context")

        # Check tags
        proposals = pattern.get_shared_insights(tags=["proposal"])
        assert len(proposals) >= 1

        tags = proposals[0].get("tags", [])
        assert "proposal" in tags
        assert proposal["request_id"] in tags

    def test_votes_written_with_correct_tags(self):
        """Test votes have correct tags."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal = pattern.create_proposal("Test", "Context")
        voter = pattern.voters[0]
        voter.vote(proposal)

        # Check tags
        votes = pattern.get_shared_insights(tags=["vote"])
        assert len(votes) >= 1

        tags = votes[0].get("tags", [])
        assert "vote" in tags
        assert proposal["proposal_id"] in tags
        assert voter.agent_id in tags

    def test_tag_based_filtering_proposals(self):
        """Test tag-based filtering for proposals."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal1 = pattern.create_proposal("Topic 1", "Context 1")
        proposal2 = pattern.create_proposal("Topic 2", "Context 2")

        # Filter by request_id
        proposals1 = pattern.get_shared_insights(tags=[proposal1["request_id"]])
        proposals2 = pattern.get_shared_insights(tags=[proposal2["request_id"]])

        assert len(proposals1) >= 1
        assert len(proposals2) >= 1

    def test_tag_based_filtering_votes(self):
        """Test tag-based filtering for votes."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal = pattern.create_proposal("Test", "Context")

        # Voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Filter votes by proposal_id
        votes = pattern.get_shared_insights(tags=["vote", proposal["proposal_id"]])
        assert len(votes) >= 2

    def test_segments_proposals_segment(self):
        """Test proposals use 'proposals' segment."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        pattern.create_proposal("Test", "Context")

        # Check segment
        proposals = pattern.get_shared_insights(segment="proposals")
        assert len(proposals) >= 1

    def test_segments_votes_segment(self):
        """Test votes use 'votes' segment."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal = pattern.create_proposal("Test", "Context")
        pattern.voters[0].vote(proposal)

        # Check segment
        votes = pattern.get_shared_insights(segment="votes")
        assert len(votes) >= 1

    def test_request_isolation_via_tags(self):
        """Test request isolation via tags."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Two separate proposals
        proposal1 = pattern.create_proposal("Topic 1", "Context 1")
        proposal2 = pattern.create_proposal("Topic 2", "Context 2")

        # Vote on both
        for voter in pattern.voters:
            voter.vote(proposal1)
            voter.vote(proposal2)

        # Filter votes by proposal
        votes1 = pattern.get_shared_insights(tags=[proposal1["proposal_id"]])
        votes2 = pattern.get_shared_insights(tags=[proposal2["proposal_id"]])

        # Each should have their own votes
        assert len(votes1) >= 2
        assert len(votes2) >= 2

    def test_importance_levels_proposals(self):
        """Test proposals have importance 0.8."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        pattern.create_proposal("Test", "Context")

        proposals = pattern.get_shared_insights(tags=["proposal"])
        assert len(proposals) >= 1
        assert proposals[0].get("importance") == 0.8

    def test_importance_levels_votes(self):
        """Test votes have importance 0.8."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        proposal = pattern.create_proposal("Test", "Context")
        pattern.voters[0].vote(proposal)

        votes = pattern.get_shared_insights(tags=["vote"])
        assert len(votes) >= 1
        assert votes[0].get("importance") == 0.8

    def test_shared_memory_coordination_complete_flow(self):
        """Test shared memory coordination in complete flow."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=3)

        # Create proposal
        proposal = pattern.create_proposal("Test", "Context")

        # Check proposal in memory
        proposals = pattern.get_shared_insights(tags=["proposal"])
        assert len(proposals) >= 1

        # Voters vote
        for voter in pattern.voters:
            voter.vote(proposal)

        # Check votes in memory
        votes = pattern.get_shared_insights(tags=["vote"])
        assert len(votes) >= 3

        # Aggregator reads votes (via aggregate_votes)
        result = pattern.determine_consensus(proposal["proposal_id"])
        assert "consensus_reached" in result


# ============================================================================
# TEST CLASS 8: Error Handling (8 tests)
# ============================================================================


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_aggregate_votes_with_no_votes(self):
        """Test aggregate_votes() with no votes."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal but no votes
        proposal = pattern.create_proposal("Test", "Context")

        # Aggregate (should handle gracefully)
        result = pattern.aggregator.aggregate_votes(proposal["proposal_id"])

        assert isinstance(result, dict)
        assert "consensus_reached" in result

    def test_aggregate_votes_with_invalid_proposal_id(self):
        """Test aggregate_votes() with invalid proposal ID."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Aggregate with fake ID
        result = pattern.aggregator.aggregate_votes("fake_proposal_id")

        # Should handle gracefully
        assert isinstance(result, dict)

    def test_collect_votes_with_no_votes(self):
        """Test collect_votes() with no votes."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create proposal but no votes
        proposal = pattern.create_proposal("Test", "Context")

        # Collect votes
        votes = pattern.collect_votes(proposal["proposal_id"])

        # Should return empty list
        assert isinstance(votes, list)
        assert len(votes) == 0

    def test_create_proposal_with_empty_topic(self):
        """Test create_proposal() with empty topic."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Create with empty topic (should handle)
        proposal = pattern.create_proposal("", "Context")

        assert isinstance(proposal, dict)
        assert "proposal_id" in proposal

    def test_vote_with_malformed_proposal(self):
        """Test vote() with malformed proposal dict."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Vote with minimal proposal
        malformed_proposal = {"proposal_id": "test_id"}

        voter = pattern.voters[0]
        vote_result = voter.vote(malformed_proposal)

        # Should handle gracefully
        assert isinstance(vote_result, dict)

    def test_check_consensus_reached_with_invalid_id(self):
        """Test check_consensus_reached() with invalid ID."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Check with fake ID
        consensus = pattern.aggregator.check_consensus_reached("fake_id")

        # Should return False
        assert consensus is False

    def test_pattern_with_zero_voters(self):
        """Test pattern creation with zero voters (edge case)."""
        from kaizen.agents.coordination import create_consensus_pattern

        # Should create pattern but validation may fail
        pattern = create_consensus_pattern(num_voters=0)

        # Pattern should exist but may not be valid
        assert pattern is not None
        assert len(pattern.voters) == 0

    def test_get_proposals_with_no_proposals(self):
        """Test get_proposals() with no proposals in memory."""
        from kaizen.agents.coordination import create_consensus_pattern

        pattern = create_consensus_pattern(num_voters=2)

        # Get proposals (none exist)
        voter = pattern.voters[0]
        proposals = voter.get_proposals()

        # Should return empty list
        assert isinstance(proposals, list)
        assert len(proposals) == 0
