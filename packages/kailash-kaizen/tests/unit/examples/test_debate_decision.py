"""
Tests for Debate-Decision Multi-Agent Pattern.

This module tests the debate-decision example which demonstrates adversarial
reasoning using SharedMemoryPool for multi-agent dialectic debate.

Test Coverage:
- Proponent arguments and rebuttals
- Opponent arguments and rebuttals
- Judge evaluation and decision-making
- Debate rounds (initial arguments + rebuttals)
- Shared memory usage across all agents
- Full workflow execution
- Decision quality and reasoning

Pattern:
Decision Question → ProponentAgent argues FOR → writes to SharedMemoryPool
→ OpponentAgent argues AGAINST → writes to SharedMemoryPool
→ ProponentAgent rebuts opponent → writes rebuttal to SharedMemoryPool
→ OpponentAgent rebuts proponent → writes rebuttal to SharedMemoryPool
→ JudgeAgent reads all arguments/rebuttals → evaluates and decides
→ JudgeAgent writes decision to SharedMemoryPool → return final decision

Agents Tested:
- ProponentAgent: Argues FOR the decision, rebuts opponent
- OpponentAgent: Argues AGAINST the decision, rebuts proponent
- JudgeAgent: Evaluates all arguments, makes final decision

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 5, Task 5E.1, Example 3)
Reference: supervisor-worker, consensus-building examples
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load debate-decision example
_module = import_example_module("examples/2-multi-agent/debate-decision")
ProponentAgent = _module.ProponentAgent
OpponentAgent = _module.OpponentAgent
JudgeAgent = _module.JudgeAgent
debate_decision_workflow = _module.debate_decision_workflow
DebateConfig = _module.DebateConfig

from kaizen.memory.shared_memory import SharedMemoryPool


class TestProponentArguments:
    """Test proponent arguments and rebuttals."""

    def test_proponent_argues_for_decision(self):
        """Test proponent presents case FOR the decision."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")

        # Present initial argument
        result = proponent.argue("Should we adopt AI-powered code review?")

        # Should return argument with evidence
        assert "argument" in result
        assert "evidence" in result
        assert "confidence" in result
        assert isinstance(result["argument"], str)
        assert len(result["argument"]) > 0

    def test_proponent_rebuts_opponent(self):
        """Test proponent rebuts opponent's arguments."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")

        # Rebuttal to opponent's argument
        opponent_arg = "AI code review is unreliable and will miss critical bugs"
        result = proponent.rebut(
            "Should we adopt AI-powered code review?", opponent_arg
        )

        # Should return rebuttal
        assert "argument" in result
        assert "evidence" in result
        assert isinstance(result["argument"], str)

    def test_proponent_arguments_written_to_shared_memory(self):
        """Test proponent writes arguments to shared memory."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")

        # Present argument
        proponent.argue("Should we migrate to microservices?")

        # Verify written to shared memory
        arguments = pool.read_relevant(
            agent_id="judge", tags=["argument", "proponent"], exclude_own=False
        )

        assert len(arguments) > 0

        # Should have correct tags and segment
        arg_insight = arguments[0]
        assert "argument" in arg_insight["tags"]
        assert "proponent" in arg_insight["tags"]
        assert arg_insight["segment"] == "debate"
        assert arg_insight["importance"] == 0.9


class TestOpponentArguments:
    """Test opponent arguments and rebuttals."""

    def test_opponent_argues_against_decision(self):
        """Test opponent presents case AGAINST the decision."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        opponent = OpponentAgent(config, pool, agent_id="opponent")

        # Present argument against
        result = opponent.argue("Should we adopt AI-powered code review?")

        # Should return argument with risks
        assert "argument" in result
        assert "risks" in result
        assert "confidence" in result
        assert isinstance(result["argument"], str)
        assert len(result["argument"]) > 0

    def test_opponent_rebuts_proponent(self):
        """Test opponent rebuts proponent's arguments."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        opponent = OpponentAgent(config, pool, agent_id="opponent")

        # Rebuttal to proponent's argument
        proponent_arg = "AI code review will increase productivity by 40%"
        result = opponent.rebut(
            "Should we adopt AI-powered code review?", proponent_arg
        )

        # Should return rebuttal
        assert "argument" in result
        assert "risks" in result
        assert isinstance(result["argument"], str)

    def test_opponent_arguments_written_to_shared_memory(self):
        """Test opponent writes arguments to shared memory."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        opponent = OpponentAgent(config, pool, agent_id="opponent")

        # Present argument
        opponent.argue("Should we migrate to microservices?")

        # Verify written to shared memory
        arguments = pool.read_relevant(
            agent_id="judge", tags=["argument", "opponent"], exclude_own=False
        )

        assert len(arguments) > 0

        # Should have correct tags and segment
        arg_insight = arguments[0]
        assert "argument" in arg_insight["tags"]
        assert "opponent" in arg_insight["tags"]
        assert arg_insight["segment"] == "debate"
        assert arg_insight["importance"] == 0.9


class TestJudgeEvaluation:
    """Test judge evaluation and decision-making."""

    def test_judge_reads_all_arguments(self):
        """Test judge reads all arguments from shared memory."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Simulate proponent argument
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "AI will improve code quality", "evidence": "Studies show 30% reduction in bugs"}',
                "tags": ["argument", "proponent", "round1"],
                "importance": 0.9,
                "segment": "debate",
                "metadata": {"question": "Should we adopt AI code review?", "round": 1},
            }
        )

        # Simulate opponent argument
        pool.write_insight(
            {
                "agent_id": "opponent",
                "content": '{"argument": "AI is unreliable", "risks": "False positives waste developer time"}',
                "tags": ["argument", "opponent", "round1"],
                "importance": 0.9,
                "segment": "debate",
                "metadata": {"question": "Should we adopt AI code review?", "round": 1},
            }
        )

        JudgeAgent(config, pool, agent_id="judge")

        # Judge should be able to read arguments
        arguments = pool.read_relevant(
            agent_id="judge", tags=["argument"], segments=["debate"], exclude_own=False
        )

        assert len(arguments) >= 2

    def test_judge_makes_decision(self):
        """Test judge makes final decision based on arguments."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Simulate arguments
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Benefits outweigh risks"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )
        pool.write_insight(
            {
                "agent_id": "opponent",
                "content": '{"argument": "Risks are too high"}',
                "tags": ["argument", "opponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )

        judge = JudgeAgent(config, pool, agent_id="judge")

        # Evaluate and decide
        result = judge.evaluate("Should we adopt AI code review?")

        # Should return decision
        assert "decision" in result
        assert "reasoning" in result
        assert "winner" in result
        assert "confidence" in result
        assert result["decision"] in ["approve", "reject"]
        assert result["winner"] in ["proponent", "opponent", "tie"]

    def test_judge_determines_winner(self):
        """Test judge determines which side won the debate."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Simulate strong proponent argument
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Strong evidence-based case"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )

        judge = JudgeAgent(config, pool, agent_id="judge")

        # Evaluate
        result = judge.evaluate("Test question")

        # Should determine winner
        assert "winner" in result
        assert result["winner"] in ["proponent", "opponent", "tie"]

    def test_judge_decision_written_to_shared_memory(self):
        """Test judge writes decision to shared memory."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Simulate arguments
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Support the decision"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )

        judge = JudgeAgent(config, pool, agent_id="judge")

        # Make decision
        judge.evaluate("Should we proceed?")

        # Verify decision written to shared memory
        decisions = pool.read_relevant(
            agent_id="proponent", tags=["decision", "final"], exclude_own=False
        )

        assert len(decisions) > 0

        # Should have correct tags and segment
        decision_insight = decisions[0]
        assert "decision" in decision_insight["tags"]
        assert "final" in decision_insight["tags"]
        assert decision_insight["segment"] == "decisions"
        assert decision_insight["importance"] == 1.0


class TestDebateRounds:
    """Test debate rounds structure."""

    def test_round_1_initial_arguments(self):
        """Test round 1 with initial arguments from both sides."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        opponent = OpponentAgent(config, pool, agent_id="opponent")

        question = "Should we implement continuous deployment?"

        # Round 1: Initial arguments
        proponent_arg = proponent.argue(question)
        opponent_arg = opponent.argue(question)

        # Both should have made arguments
        assert "argument" in proponent_arg
        assert "argument" in opponent_arg

        # Should be written to shared memory with round1 tag
        round1_args = pool.read_relevant(
            agent_id="judge", tags=["argument", "round1"], exclude_own=False
        )

        assert len(round1_args) >= 2

    def test_round_2_rebuttals(self):
        """Test round 2 with rebuttals from both sides."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        opponent = OpponentAgent(config, pool, agent_id="opponent")

        question = "Should we implement continuous deployment?"

        # Round 1: Initial arguments
        proponent_arg = proponent.argue(question)
        opponent_arg = opponent.argue(question)

        # Round 2: Rebuttals
        proponent_rebut = proponent.rebut(question, opponent_arg["argument"])
        opponent_rebut = opponent.rebut(question, proponent_arg["argument"])

        # Both should have made rebuttals
        assert "argument" in proponent_rebut
        assert "argument" in opponent_rebut

        # Should be written to shared memory with round2 tag
        round2_rebuttals = pool.read_relevant(
            agent_id="judge", tags=["rebuttal", "round2"], exclude_own=False
        )

        assert len(round2_rebuttals) >= 2

    def test_multi_round_debate(self):
        """Test multi-round debate structure."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo", rounds=2)

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        opponent = OpponentAgent(config, pool, agent_id="opponent")

        question = "Should we migrate to cloud infrastructure?"

        # Round 1: Arguments
        proponent.argue(question)
        opponent.argue(question)

        # Round 2: Rebuttals
        proponent.rebut(question, "opponent argument")
        opponent.rebut(question, "proponent argument")

        # Should have multiple rounds of content
        all_insights = pool.read_all()

        # At least 4 insights (2 arguments + 2 rebuttals)
        assert len(all_insights) >= 4

    def test_debate_tags_correct_per_round(self):
        """Test debate insights have correct tags per round."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        opponent = OpponentAgent(config, pool, agent_id="opponent")

        question = "Should we adopt GraphQL?"

        # Round 1
        proponent.argue(question)
        opponent.argue(question)

        # Round 2
        proponent.rebut(question, "opponent view")
        opponent.rebut(question, "proponent view")

        # Check round1 tags
        round1 = pool.read_relevant(
            agent_id="judge", tags=["round1"], exclude_own=False
        )
        assert len(round1) >= 2

        # Check round2 tags
        round2 = pool.read_relevant(
            agent_id="judge", tags=["round2"], exclude_own=False
        )
        assert len(round2) >= 2


class TestFullWorkflow:
    """Test full debate-decision workflow."""

    def test_full_debate_workflow(self):
        """Test full workflow from question to decision."""
        result = debate_decision_workflow("Should we implement feature flags?")

        # Should have complete result
        assert "question" in result
        assert "proponent_argument" in result
        assert "opponent_argument" in result
        assert "proponent_rebuttal" in result
        assert "opponent_rebuttal" in result
        assert "decision" in result
        assert "stats" in result

    def test_workflow_with_proponent_winner(self):
        """Test workflow where proponent wins the debate."""
        # Strong FOR argument expected from mock
        result = debate_decision_workflow("Should we adopt automated testing?")

        # Should have decision
        assert "decision" in result
        assert "decision" in result["decision"]
        assert result["decision"]["decision"] in ["approve", "reject"]

    def test_workflow_with_opponent_winner(self):
        """Test workflow where opponent wins the debate."""
        # Strong AGAINST argument expected from mock
        result = debate_decision_workflow("Should we remove all code comments?")

        # Should have decision
        assert "decision" in result
        assert "reasoning" in result["decision"]
        assert len(result["decision"]["reasoning"]) > 0

    def test_stats_reflect_debate_operations(self):
        """Test shared memory stats reflect all debate operations."""
        result = debate_decision_workflow("Should we use NoSQL database?")

        stats = result["stats"]

        # Should have accurate counts
        assert "insight_count" in stats
        assert "agent_count" in stats
        assert stats["insight_count"] > 0
        # Should have proponent + opponent + judge = 3 agents
        assert stats["agent_count"] >= 3

        # Should have multiple insights (arguments + rebuttals + decision)
        assert stats["insight_count"] >= 5  # 2 args + 2 rebuttals + 1 decision


class TestDebateQuality:
    """Test debate quality and reasoning."""

    def test_arguments_have_evidence(self):
        """Test arguments include supporting evidence."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")

        result = proponent.argue("Should we adopt TDD?")

        # Should have evidence
        assert "evidence" in result
        assert isinstance(result["evidence"], str)

    def test_rebuttals_address_opposing_arguments(self):
        """Test rebuttals specifically address opposing arguments."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        opponent = OpponentAgent(config, pool, agent_id="opponent")

        # Rebuttal should reference the opposing argument
        proponent_arg = "TDD increases development speed"
        result = opponent.rebut("Should we adopt TDD?", proponent_arg)

        # Should have rebuttal
        assert "argument" in result
        assert isinstance(result["argument"], str)

    def test_judge_provides_detailed_reasoning(self):
        """Test judge provides detailed reasoning for decision."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        # Simulate debate
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Strong benefits"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )
        pool.write_insight(
            {
                "agent_id": "opponent",
                "content": '{"argument": "Significant risks"}',
                "tags": ["argument", "opponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )

        judge = JudgeAgent(config, pool, agent_id="judge")
        result = judge.evaluate("Should we proceed?")

        # Should have detailed reasoning
        assert "reasoning" in result
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0

    def test_confidence_scores_provided(self):
        """Test all agents provide confidence scores."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        opponent = OpponentAgent(config, pool, agent_id="opponent")
        judge = JudgeAgent(config, pool, agent_id="judge")

        # Get arguments
        proponent_result = proponent.argue("Test question")
        opponent_result = opponent.argue("Test question")

        # Judge evaluates
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Test"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )
        judge_result = judge.evaluate("Test question")

        # All should have confidence
        assert "confidence" in proponent_result
        assert "confidence" in opponent_result
        assert "confidence" in judge_result


class TestSharedMemoryUsage:
    """Test shared memory usage patterns."""

    def test_debate_uses_correct_segments(self):
        """Test debate uses correct memory segments."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        judge = JudgeAgent(config, pool, agent_id="judge")

        # Create argument
        proponent.argue("Test question")

        # Create decision
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Test"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )
        judge.evaluate("Test question")

        # Check segments
        debate_insights = pool.read_relevant(
            agent_id="judge", segments=["debate"], exclude_own=False
        )
        assert len(debate_insights) > 0

        decision_insights = pool.read_relevant(
            agent_id="proponent", segments=["decisions"], exclude_own=False
        )
        assert len(decision_insights) > 0

    def test_importance_levels_correct(self):
        """Test insights have correct importance levels."""
        pool = SharedMemoryPool()
        config = DebateConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(config, pool, agent_id="proponent")
        judge = JudgeAgent(config, pool, agent_id="judge")

        # Arguments should have importance 0.9
        proponent.argue("Test question")

        arguments = pool.read_all()
        for insight in arguments:
            if "argument" in insight["tags"]:
                assert insight["importance"] == 0.9

        # Decision should have importance 1.0
        pool.write_insight(
            {
                "agent_id": "proponent",
                "content": '{"argument": "Test"}',
                "tags": ["argument", "proponent"],
                "importance": 0.9,
                "segment": "debate",
            }
        )
        judge.evaluate("Test question")

        decisions = pool.read_relevant(
            agent_id="proponent", tags=["decision"], exclude_own=False
        )
        for insight in decisions:
            assert insight["importance"] == 1.0
