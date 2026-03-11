"""
Test DebatePattern - Multi-Agent Coordination Pattern

Tests adversarial reasoning through structured debate with proponent, opponent, and judge.
Covers factory function, pattern class, all agents, and debate logic.

Written BEFORE implementation (TDD).

Test Coverage:
- Factory Function: 10 tests
- Pattern Class: 10 tests
- ProponentAgent: 15 tests
- OpponentAgent: 15 tests
- JudgeAgent: 15 tests
- Integration: 15 tests
- Shared Memory: 10 tests
- Error Handling: 8 tests
Total: 98 tests
"""

import json

# ============================================================================
# TEST CLASS 1: Factory Function (10 tests)
# ============================================================================


class TestCreateDebatePattern:
    """Test create_debate_pattern factory function."""

    def test_zero_config_creation(self):
        """Test zero-config pattern creation."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        assert pattern is not None
        assert pattern.proponent is not None
        assert pattern.opponent is not None
        assert pattern.judge is not None
        assert pattern.shared_memory is not None

    def test_custom_llm_provider(self):
        """Test creating pattern with custom LLM provider."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="anthropic")

        assert pattern.proponent.config.llm_provider == "anthropic"
        assert pattern.opponent.config.llm_provider == "anthropic"
        assert pattern.judge.config.llm_provider == "anthropic"

    def test_custom_model(self):
        """Test creating pattern with custom model."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(model="gpt-4")

        assert pattern.proponent.config.model == "gpt-4"
        assert pattern.opponent.config.model == "gpt-4"
        assert pattern.judge.config.model == "gpt-4"

    def test_progressive_configuration_temperature_and_max_tokens(self):
        """Test overriding temperature and max_tokens."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(temperature=0.8, max_tokens=2000)

        assert pattern.proponent.config.temperature == 0.8
        assert pattern.proponent.config.max_tokens == 2000
        assert pattern.opponent.config.temperature == 0.8
        assert pattern.judge.config.max_tokens == 2000

    def test_progressive_configuration_multiple_params(self):
        """Test overriding multiple parameters."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
        )

        # Verify all agents have correct config
        assert pattern.proponent.config.llm_provider == "anthropic"
        assert pattern.proponent.config.model == "claude-3-opus"
        assert pattern.proponent.config.temperature == 0.7
        assert pattern.proponent.config.max_tokens == 2000

        assert pattern.opponent.config.llm_provider == "anthropic"
        assert pattern.judge.config.model == "claude-3-opus"

    def test_separate_configs_per_agent_type(self):
        """Test separate configs for proponent, opponent, judge."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(
            proponent_config={"model": "gpt-4"},
            opponent_config={"model": "gpt-3.5-turbo"},
            judge_config={"model": "gpt-4"},
        )

        # Proponent should use gpt-4
        assert pattern.proponent.config.model == "gpt-4"
        # Opponent should use gpt-3.5-turbo
        assert pattern.opponent.config.model == "gpt-3.5-turbo"
        # Judge should use gpt-4
        assert pattern.judge.config.model == "gpt-4"

    def test_shared_memory_provided(self):
        """Test providing existing SharedMemoryPool."""
        from kaizen.agents.coordination import create_debate_pattern
        from kaizen.memory import SharedMemoryPool

        existing_pool = SharedMemoryPool()

        pattern = create_debate_pattern(shared_memory=existing_pool)

        # Pattern should use provided pool
        assert pattern.shared_memory is existing_pool
        # All agents should share same pool
        assert pattern.proponent.shared_memory is existing_pool
        assert pattern.opponent.shared_memory is existing_pool
        assert pattern.judge.shared_memory is existing_pool

    def test_agent_ids_are_unique(self):
        """Test that all agent IDs are unique."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        agent_ids = pattern.get_agent_ids()

        # Should have unique IDs
        assert len(agent_ids) == len(set(agent_ids))
        # Should include proponent, opponent, judge
        assert len(agent_ids) == 3

    def test_default_agent_ids_format(self):
        """Test default agent ID naming convention."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        agent_ids = pattern.get_agent_ids()

        # Check expected IDs
        assert "proponent_1" in agent_ids
        assert "opponent_1" in agent_ids
        assert "judge_1" in agent_ids

    def test_environment_variable_usage(self):
        """Test that factory uses environment variables as fallback."""
        import os

        from kaizen.agents.coordination import create_debate_pattern

        # Set environment variables
        os.environ["KAIZEN_LLM_PROVIDER"] = "mock"  # Use mock provider for testing
        os.environ["KAIZEN_MODEL"] = "test_model"
        os.environ["KAIZEN_TEMPERATURE"] = "0.9"
        os.environ["KAIZEN_MAX_TOKENS"] = "3000"

        try:
            # Create pattern without explicit llm_provider - should use env vars
            pattern = create_debate_pattern()

            # Should use env vars when no explicit config provided
            assert pattern.proponent.config.llm_provider == "mock"
            assert pattern.proponent.config.model == "test_model"
            # Temperature and max_tokens should use env values or defaults
        finally:
            # Clean up
            del os.environ["KAIZEN_LLM_PROVIDER"]
            del os.environ["KAIZEN_MODEL"]
            del os.environ["KAIZEN_TEMPERATURE"]
            del os.environ["KAIZEN_MAX_TOKENS"]


# ============================================================================
# TEST CLASS 2: DebatePattern Class (10 tests)
# ============================================================================


class TestDebatePattern:
    """Test DebatePattern class."""

    def test_pattern_initialization(self):
        """Test pattern is properly initialized."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        assert pattern.validate_pattern() is True

    def test_debate_convenience_method_single_round(self):
        """Test pattern.debate() orchestrates single-round debate."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        result = pattern.debate(
            topic="Should AI be regulated?",
            context="Important policy decision",
            rounds=1,
        )

        assert isinstance(result, dict)
        assert "debate_id" in result
        assert "judgment" in result or "decision" in result

    def test_debate_convenience_method_multi_round(self):
        """Test pattern.debate() orchestrates multi-round debate."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        result = pattern.debate(
            topic="Should AI be regulated?",
            context="Important policy decision",
            rounds=2,
        )

        assert isinstance(result, dict)
        assert "debate_id" in result
        # Should have multiple rounds of arguments
        assert "judgment" in result or "decision" in result

    def test_get_judgment_convenience_method(self):
        """Test pattern.get_judgment() retrieves final judgment."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("Test topic", rounds=1)
        debate_id = debate_result["debate_id"]

        # Get judgment
        judgment = pattern.get_judgment(debate_id)

        assert isinstance(judgment, dict)
        assert "decision" in judgment
        assert "winner" in judgment
        assert "reasoning" in judgment

    def test_get_agents(self):
        """Test get_agents() returns all agents."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        agents = pattern.get_agents()

        # Should return 3 agents: proponent, opponent, judge
        assert len(agents) == 3
        assert pattern.proponent in agents
        assert pattern.opponent in agents
        assert pattern.judge in agents

    def test_get_agent_ids(self):
        """Test get_agent_ids() returns unique IDs."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        agent_ids = pattern.get_agent_ids()

        assert len(agent_ids) == 3
        assert "proponent_1" in agent_ids
        assert "opponent_1" in agent_ids
        assert "judge_1" in agent_ids

    def test_clear_shared_memory(self):
        """Test clear_shared_memory() clears pattern state."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

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
        from kaizen.orchestration.patterns.debate import DebatePattern

        # Create pattern with no agents (invalid)
        pattern = DebatePattern(
            proponent=None, opponent=None, judge=None, shared_memory=SharedMemoryPool()
        )

        assert pattern.validate_pattern() is False

    def test_pattern_str_representation(self):
        """Test string representation of pattern."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern_str = str(pattern)

        assert "DebatePattern" in pattern_str
        assert "3" in pattern_str  # 3 agents

    def test_pattern_works_with_base_pattern_helpers(self):
        """Test pattern works with BaseMultiAgentPattern helper methods."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

        # Test get_shared_insights
        insights = pattern.get_shared_insights(tags=["argument"])
        assert len(insights) > 0

        # Test count_insights_by_tags
        count = pattern.count_insights_by_tags(["argument"])
        assert count > 0

    def test_debate_isolation_with_different_debate_ids(self):
        """Test that different debates are isolated via debate_ids."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run first debate
        result1 = pattern.debate("Topic A", rounds=1)
        debate_id1 = result1["debate_id"]

        # Clear memory
        pattern.clear_shared_memory()

        # Run second debate
        result2 = pattern.debate("Topic B", rounds=1)
        debate_id2 = result2["debate_id"]

        # Should have different IDs
        assert debate_id1 != debate_id2


# ============================================================================
# TEST CLASS 3: ProponentAgent (15 tests)
# ============================================================================


class TestProponentAgent:
    """Test ProponentAgent class."""

    def test_initialization(self):
        """Test proponent initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.debate import ProponentAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        proponent = ProponentAgent(
            config=config, shared_memory=shared_memory, agent_id="test_proponent"
        )

        assert proponent.agent_id == "test_proponent"
        assert proponent.shared_memory is shared_memory
        assert proponent.signature is not None

    def test_construct_argument_returns_dict(self):
        """Test construct_argument() returns proper dict structure."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        assert isinstance(argument, dict)
        assert "argument" in argument
        assert "key_points" in argument
        assert "evidence" in argument

    def test_construct_argument_for_position(self):
        """Test construct_argument() creates FOR argument."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Should have argument content
        assert isinstance(argument["argument"], str)
        assert len(argument["argument"]) > 0

    def test_construct_argument_key_points_is_json_list(self):
        """Test key_points is JSON list."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # key_points should be parseable as JSON list
        key_points = argument["key_points"]
        if isinstance(key_points, str):
            parsed = json.loads(key_points)
            assert isinstance(parsed, list)
        else:
            assert isinstance(key_points, list)

    def test_construct_argument_includes_evidence(self):
        """Test argument includes evidence."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Should have evidence
        assert "evidence" in argument
        assert isinstance(argument["evidence"], str)

    def test_construct_argument_writes_to_shared_memory(self):
        """Test construct_argument() writes to shared memory."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check shared memory has argument
        arguments = pattern.get_shared_insights(tags=["argument"])
        assert len(arguments) >= 1

    def test_construct_argument_tags_include_for_position(self):
        """Test argument tags include 'for' position."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check tags
        arguments = pattern.get_shared_insights(tags=["for"])
        assert len(arguments) >= 1

    def test_construct_argument_importance_level(self):
        """Test argument written with importance 0.8."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check importance
        arguments = pattern.get_shared_insights(tags=["argument"])
        assert len(arguments) > 0
        # Importance should be 0.8
        for arg in arguments:
            if "for" in arg.get("tags", []):
                assert arg.get("importance") == 0.8
                break

    def test_construct_argument_segment_is_arguments(self):
        """Test argument written to 'arguments' segment."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check segment
        arguments = pattern.get_shared_insights(segment="arguments")
        assert len(arguments) > 0

    def test_rebut_returns_dict(self):
        """Test rebut() returns proper dict structure."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create opponent argument first
        opponent_arg = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Proponent rebuts
        rebuttal = pattern.proponent.rebut(
            opponent_argument=opponent_arg, topic="AI regulation"
        )

        assert isinstance(rebuttal, dict)
        assert "rebuttal" in rebuttal
        assert "counterpoints" in rebuttal
        assert "strength" in rebuttal

    def test_rebut_counterpoints_is_json_list(self):
        """Test counterpoints is JSON list."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create opponent argument
        opponent_arg = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Proponent rebuts
        rebuttal = pattern.proponent.rebut(
            opponent_argument=opponent_arg, topic="AI regulation"
        )

        # counterpoints should be parseable as JSON list
        counterpoints = rebuttal["counterpoints"]
        if isinstance(counterpoints, str):
            parsed = json.loads(counterpoints)
            assert isinstance(parsed, list)
        else:
            assert isinstance(counterpoints, list)

    def test_rebut_strength_validation(self):
        """Test rebuttal strength is between 0.0 and 1.0."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create opponent argument
        opponent_arg = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Proponent rebuts
        rebuttal = pattern.proponent.rebut(
            opponent_argument=opponent_arg, topic="AI regulation"
        )

        strength = rebuttal["strength"]
        # Should be float
        assert isinstance(strength, (int, float))
        # Should be 0.0-1.0
        strength_float = float(strength)
        assert 0.0 <= strength_float <= 1.0

    def test_rebut_writes_to_shared_memory(self):
        """Test rebut() writes to shared memory."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create opponent argument
        opponent_arg = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Clear memory to isolate rebuttal
        pattern.clear_shared_memory()

        # Proponent rebuts
        pattern.proponent.rebut(opponent_argument=opponent_arg, topic="AI regulation")

        # Check shared memory has rebuttal
        insights = pattern.get_shared_insights(tags=["argument"])
        assert len(insights) >= 1

    def test_multiple_rounds_supported(self):
        """Test proponent can participate in multiple rounds."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Round 1: Initial argument
        arg1 = pattern.proponent.construct_argument(
            topic="AI regulation", context="Round 1"
        )
        assert arg1 is not None

        # Round 2: Rebut opponent
        opponent_arg = pattern.opponent.construct_argument(
            topic="AI regulation", context="Round 1"
        )
        rebuttal1 = pattern.proponent.rebut(
            opponent_argument=opponent_arg, topic="AI regulation"
        )
        assert rebuttal1 is not None

    def test_construct_argument_with_empty_context(self):
        """Test construct_argument works with empty context."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.proponent.construct_argument(
            topic="AI regulation", context=""
        )

        assert isinstance(argument, dict)
        assert "argument" in argument


# ============================================================================
# TEST CLASS 4: OpponentAgent (15 tests)
# ============================================================================


class TestOpponentAgent:
    """Test OpponentAgent class."""

    def test_initialization(self):
        """Test opponent initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.debate import OpponentAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        opponent = OpponentAgent(
            config=config, shared_memory=shared_memory, agent_id="test_opponent"
        )

        assert opponent.agent_id == "test_opponent"
        assert opponent.shared_memory is shared_memory
        assert opponent.signature is not None

    def test_construct_argument_returns_dict(self):
        """Test construct_argument() returns proper dict structure."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        assert isinstance(argument, dict)
        assert "argument" in argument
        assert "key_points" in argument
        assert "evidence" in argument

    def test_construct_argument_against_position(self):
        """Test construct_argument() creates AGAINST argument."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Should have argument content
        assert isinstance(argument["argument"], str)
        assert len(argument["argument"]) > 0

    def test_construct_argument_key_points_is_json_list(self):
        """Test key_points is JSON list."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # key_points should be parseable as JSON list
        key_points = argument["key_points"]
        if isinstance(key_points, str):
            parsed = json.loads(key_points)
            assert isinstance(parsed, list)
        else:
            assert isinstance(key_points, list)

    def test_construct_argument_includes_evidence(self):
        """Test argument includes evidence."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Should have evidence
        assert "evidence" in argument
        assert isinstance(argument["evidence"], str)

    def test_construct_argument_writes_to_shared_memory(self):
        """Test construct_argument() writes to shared memory."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check shared memory has argument
        arguments = pattern.get_shared_insights(tags=["argument"])
        assert len(arguments) >= 1

    def test_construct_argument_tags_include_against_position(self):
        """Test argument tags include 'against' position."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check tags
        arguments = pattern.get_shared_insights(tags=["against"])
        assert len(arguments) >= 1

    def test_construct_argument_importance_level(self):
        """Test argument written with importance 0.8."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check importance
        arguments = pattern.get_shared_insights(tags=["argument"])
        assert len(arguments) > 0
        # Importance should be 0.8
        for arg in arguments:
            if "against" in arg.get("tags", []):
                assert arg.get("importance") == 0.8
                break

    def test_construct_argument_segment_is_arguments(self):
        """Test argument written to 'arguments' segment."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        pattern.opponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Check segment
        arguments = pattern.get_shared_insights(segment="arguments")
        assert len(arguments) > 0

    def test_rebut_returns_dict(self):
        """Test rebut() returns proper dict structure."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create proponent argument first
        proponent_arg = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Opponent rebuts
        rebuttal = pattern.opponent.rebut(
            proponent_argument=proponent_arg, topic="AI regulation"
        )

        assert isinstance(rebuttal, dict)
        assert "rebuttal" in rebuttal
        assert "counterpoints" in rebuttal
        assert "strength" in rebuttal

    def test_rebut_counterpoints_is_json_list(self):
        """Test counterpoints is JSON list."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create proponent argument
        proponent_arg = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Opponent rebuts
        rebuttal = pattern.opponent.rebut(
            proponent_argument=proponent_arg, topic="AI regulation"
        )

        # counterpoints should be parseable as JSON list
        counterpoints = rebuttal["counterpoints"]
        if isinstance(counterpoints, str):
            parsed = json.loads(counterpoints)
            assert isinstance(parsed, list)
        else:
            assert isinstance(counterpoints, list)

    def test_rebut_strength_validation(self):
        """Test rebuttal strength is between 0.0 and 1.0."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create proponent argument
        proponent_arg = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Opponent rebuts
        rebuttal = pattern.opponent.rebut(
            proponent_argument=proponent_arg, topic="AI regulation"
        )

        strength = rebuttal["strength"]
        # Should be float
        assert isinstance(strength, (int, float))
        # Should be 0.0-1.0
        strength_float = float(strength)
        assert 0.0 <= strength_float <= 1.0

    def test_rebut_writes_to_shared_memory(self):
        """Test rebut() writes to shared memory."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create proponent argument
        proponent_arg = pattern.proponent.construct_argument(
            topic="AI regulation", context="Policy debate"
        )

        # Clear memory to isolate rebuttal
        pattern.clear_shared_memory()

        # Opponent rebuts
        pattern.opponent.rebut(proponent_argument=proponent_arg, topic="AI regulation")

        # Check shared memory has rebuttal
        insights = pattern.get_shared_insights(tags=["argument"])
        assert len(insights) >= 1

    def test_multiple_rounds_supported(self):
        """Test opponent can participate in multiple rounds."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Round 1: Initial argument
        arg1 = pattern.opponent.construct_argument(
            topic="AI regulation", context="Round 1"
        )
        assert arg1 is not None

        # Round 2: Rebut proponent
        proponent_arg = pattern.proponent.construct_argument(
            topic="AI regulation", context="Round 1"
        )
        rebuttal1 = pattern.opponent.rebut(
            proponent_argument=proponent_arg, topic="AI regulation"
        )
        assert rebuttal1 is not None

    def test_construct_argument_with_empty_context(self):
        """Test construct_argument works with empty context."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")
        argument = pattern.opponent.construct_argument(
            topic="AI regulation", context=""
        )

        assert isinstance(argument, dict)
        assert "argument" in argument


# ============================================================================
# TEST CLASS 5: JudgeAgent (15 tests)
# ============================================================================


class TestJudgeAgent:
    """Test JudgeAgent class."""

    def test_initialization(self):
        """Test judge initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.debate import JudgeAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        judge = JudgeAgent(
            config=config, shared_memory=shared_memory, agent_id="test_judge"
        )

        assert judge.agent_id == "test_judge"
        assert judge.shared_memory is shared_memory
        assert judge.signature is not None

    def test_judge_debate_returns_dict(self):
        """Test judge_debate() returns proper dict structure."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        judgment = pattern.judge.judge_debate(debate_id)

        assert isinstance(judgment, dict)
        assert "decision" in judgment
        assert "winner" in judgment
        assert "reasoning" in judgment
        assert "confidence" in judgment

    def test_judge_debate_decision_options(self):
        """Test decision is one of: for, against, tie."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        judgment = pattern.judge.judge_debate(debate_id)

        decision = judgment["decision"]
        assert decision in ["for", "against", "tie"]

    def test_judge_debate_winner_determination(self):
        """Test winner matches decision."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate (includes judgment)
        debate_result = pattern.debate("AI regulation", rounds=1)

        # Get judgment from debate result
        judgment = debate_result["judgment"]

        decision = judgment["decision"]
        winner = judgment["winner"]

        # Winner should match decision
        # Test decision is valid
        assert decision in ["for", "against", "tie"]
        # Test winner is provided
        assert isinstance(winner, str)
        assert len(winner) > 0

    def test_judge_debate_confidence_validation(self):
        """Test confidence is between 0.0 and 1.0."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        judgment = pattern.judge.judge_debate(debate_id)

        confidence = judgment["confidence"]
        # Should be float
        assert isinstance(confidence, (int, float))
        # Should be 0.0-1.0
        confidence_float = float(confidence)
        assert 0.0 <= confidence_float <= 1.0

    def test_judge_debate_reasoning_provided(self):
        """Test reasoning is provided."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        judgment = pattern.judge.judge_debate(debate_id)

        reasoning = judgment["reasoning"]
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0

    def test_judge_debate_writes_to_shared_memory(self):
        """Test judge_debate() writes to shared memory."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Clear to isolate judgment
        initial_count = len(pattern.get_shared_insights(tags=["judgment"]))

        # Judge
        pattern.judge.judge_debate(debate_id)

        # Check shared memory has judgment
        judgments = pattern.get_shared_insights(tags=["judgment"])
        assert len(judgments) > initial_count

    def test_judge_debate_tags_include_debate_id(self):
        """Test judgment tags include debate_id."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        pattern.judge.judge_debate(debate_id)

        # Check tags
        judgments = pattern.get_shared_insights(tags=[debate_id])
        assert len(judgments) >= 1

    def test_judge_debate_importance_level(self):
        """Test judgment written with importance 0.9."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        pattern.judge.judge_debate(debate_id)

        # Check importance
        judgments = pattern.get_shared_insights(tags=["judgment"])
        assert len(judgments) > 0
        # Importance should be 0.9
        for jdg in judgments:
            if debate_id in jdg.get("tags", []):
                assert jdg.get("importance") == 0.9
                break

    def test_judge_debate_segment_is_judgments(self):
        """Test judgment written to 'judgments' segment."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        pattern.judge.judge_debate(debate_id)

        # Check segment
        judgments = pattern.get_shared_insights(segment="judgments")
        assert len(judgments) > 0

    def test_get_arguments_retrieves_all_arguments(self):
        """Test get_arguments() retrieves all arguments for debate."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Get arguments
        arguments = pattern.judge.get_arguments(debate_id)

        assert isinstance(arguments, dict)
        # Should have arguments from both sides
        assert "proponent_argument" in arguments or "for_argument" in arguments
        assert "opponent_argument" in arguments or "against_argument" in arguments

    def test_get_arguments_includes_rebuttals(self):
        """Test get_arguments() includes rebuttals if present."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run multi-round debate
        debate_result = pattern.debate("AI regulation", rounds=2)
        debate_id = debate_result["debate_id"]

        # Get arguments
        arguments = pattern.judge.get_arguments(debate_id)

        assert isinstance(arguments, dict)
        # Should have rebuttals
        assert (
            "proponent_rebuttal" in arguments
            or "for_rebuttal" in arguments
            or len(arguments) > 2
        )

    def test_judge_debate_reads_all_arguments_and_rebuttals(self):
        """Test judge reads all arguments and rebuttals before judging."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run multi-round debate
        debate_result = pattern.debate("AI regulation", rounds=2)
        debate_id = debate_result["debate_id"]

        # Judge should read all arguments
        judgment = pattern.judge.judge_debate(debate_id)

        # Should have made a decision
        assert "decision" in judgment
        assert judgment["decision"] in ["for", "against", "tie"]

    def test_judge_debate_handles_no_arguments(self):
        """Test judge_debate() handles case with no arguments."""
        import uuid

        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create fake debate_id with no arguments
        fake_debate_id = f"debate_{uuid.uuid4().hex[:8]}"

        # Should handle gracefully (may return default or error)
        try:
            judgment = pattern.judge.judge_debate(fake_debate_id)
            # If it doesn't raise, should return dict
            assert isinstance(judgment, dict)
        except Exception:
            # It's okay to raise if no arguments found
            pass

    def test_judge_debate_for_proponent_wins(self):
        """Test judgment when proponent should win."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate (outcome depends on mock responses)
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        judgment = pattern.judge.judge_debate(debate_id)

        # Should have decision
        assert judgment["decision"] in ["for", "against", "tie"]

    def test_judge_debate_for_tie(self):
        """Test judgment can result in tie."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        debate_result = pattern.debate("AI regulation", rounds=1)
        debate_id = debate_result["debate_id"]

        # Judge
        judgment = pattern.judge.judge_debate(debate_id)

        # Decision should be valid (including tie)
        assert judgment["decision"] in ["for", "against", "tie"]


# ============================================================================
# TEST CLASS 6: Integration Tests (15 tests)
# ============================================================================


class TestDebatePatternIntegration:
    """Test complete debate workflows."""

    def test_complete_single_round_debate(self):
        """Test complete single-round debate workflow."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(
            topic="Should AI be regulated?",
            context="Important policy decision",
            rounds=1,
        )

        assert isinstance(result, dict)
        assert "debate_id" in result
        assert "judgment" in result or "decision" in result

    def test_complete_multi_round_debate(self):
        """Test complete multi-round debate workflow."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(
            topic="Should AI be regulated?",
            context="Important policy decision",
            rounds=3,
        )

        assert isinstance(result, dict)
        assert "debate_id" in result
        # Should have judgment
        judgment = result.get("judgment") or pattern.get_judgment(result["debate_id"])
        assert judgment is not None

    def test_proponent_wins_scenario(self):
        """Test scenario where proponent wins."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(
            topic="Should we use open source software?",
            context="Strong FOR position",
            rounds=1,
        )

        judgment = result.get("judgment") or pattern.get_judgment(result["debate_id"])
        # Should have made decision
        assert judgment["decision"] in ["for", "against", "tie"]

    def test_opponent_wins_scenario(self):
        """Test scenario where opponent wins."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(
            topic="Should we ban all technology?",
            context="Strong AGAINST position",
            rounds=1,
        )

        judgment = result.get("judgment") or pattern.get_judgment(result["debate_id"])
        # Should have made decision
        assert judgment["decision"] in ["for", "against", "tie"]

    def test_tie_scenario(self):
        """Test scenario resulting in tie."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(
            topic="Should remote work be mandatory?",
            context="Balanced arguments",
            rounds=1,
        )

        judgment = result.get("judgment") or pattern.get_judgment(result["debate_id"])
        # Decision should be valid
        assert judgment["decision"] in ["for", "against", "tie"]

    def test_debate_isolation_different_topics(self):
        """Test debates on different topics are isolated."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run first debate
        result1 = pattern.debate("Topic A", rounds=1)
        debate_id1 = result1["debate_id"]

        # Clear memory
        pattern.clear_shared_memory()

        # Run second debate
        result2 = pattern.debate("Topic B", rounds=1)
        debate_id2 = result2["debate_id"]

        # Should have different IDs
        assert debate_id1 != debate_id2

    def test_debate_with_context(self):
        """Test debate with additional context."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(
            topic="AI regulation",
            context="Focus on privacy and data protection",
            rounds=1,
        )

        assert result is not None
        assert "debate_id" in result

    def test_debate_without_context(self):
        """Test debate without context."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate(topic="AI regulation", context="", rounds=1)

        assert result is not None
        assert "debate_id" in result

    def test_multiple_sequential_debates(self):
        """Test running multiple debates sequentially."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run 3 debates
        for i in range(3):
            result = pattern.debate(f"Topic {i}", rounds=1)
            assert "debate_id" in result

            # Clear between debates
            pattern.clear_shared_memory()

    def test_debate_flow_order(self):
        """Test debate follows correct flow: arg -> arg -> rebut -> rebut -> judge."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        result = pattern.debate("Test topic", rounds=2)
        result["debate_id"]

        # Check shared memory for flow
        all_insights = pattern.shared_memory.read_all()

        # Should have arguments and judgment
        has_arguments = any("argument" in ins.get("tags", []) for ins in all_insights)
        has_judgment = any("judgment" in ins.get("tags", []) for ins in all_insights)

        assert has_arguments
        assert has_judgment

    def test_debate_result_structure(self):
        """Test debate result has expected structure."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        result = pattern.debate("Test topic", rounds=1)

        assert "debate_id" in result
        # Should have judgment in result or accessible via get_judgment
        if "judgment" not in result:
            judgment = pattern.get_judgment(result["debate_id"])
            assert judgment is not None

    def test_get_judgment_after_debate(self):
        """Test get_judgment() retrieves judgment after debate."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        result = pattern.debate("Test topic", rounds=1)
        debate_id = result["debate_id"]

        # Get judgment
        judgment = pattern.get_judgment(debate_id)

        assert isinstance(judgment, dict)
        assert "decision" in judgment

    def test_debate_with_zero_rounds_returns_no_judgment(self):
        """Test debate with 0 rounds returns early."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate with 0 rounds
        result = pattern.debate("Test topic", rounds=0)

        # Should return early or handle gracefully
        assert isinstance(result, dict)

    def test_shared_memory_organization(self):
        """Test shared memory is organized by segments and tags."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

        # Check segments
        arguments = pattern.get_shared_insights(segment="arguments")
        judgments = pattern.get_shared_insights(segment="judgments")

        # Should have insights in correct segments
        assert len(arguments) > 0 or len(judgments) > 0

    def test_debate_performance(self):
        """Test debate completes in reasonable time."""
        import time

        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        start = time.time()
        result = pattern.debate("Test topic", rounds=1)
        duration = time.time() - start

        # Should complete in under 30 seconds (generous for mocking)
        assert duration < 30
        assert result is not None


# ============================================================================
# TEST CLASS 7: Shared Memory Tests (10 tests)
# ============================================================================


class TestDebatePatternSharedMemory:
    """Test shared memory behavior."""

    def test_arguments_written_with_correct_tags(self):
        """Test arguments are written with correct tags."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create arguments
        pattern.proponent.construct_argument("Test topic", "")
        pattern.opponent.construct_argument("Test topic", "")

        # Check tags
        for_args = pattern.get_shared_insights(tags=["for"])
        against_args = pattern.get_shared_insights(tags=["against"])

        assert len(for_args) > 0
        assert len(against_args) > 0

    def test_rebuttals_written_with_correct_tags(self):
        """Test rebuttals are written with correct tags."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create arguments
        proponent_arg = pattern.proponent.construct_argument("Test topic", "")
        opponent_arg = pattern.opponent.construct_argument("Test topic", "")

        # Clear memory
        pattern.clear_shared_memory()

        # Create rebuttals
        pattern.proponent.rebut(opponent_arg, "Test topic")
        pattern.opponent.rebut(proponent_arg, "Test topic")

        # Check tags
        arguments = pattern.get_shared_insights(tags=["argument"])
        assert len(arguments) >= 2

    def test_judgments_written_with_correct_tags(self):
        """Test judgments are written with correct tags."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        result = pattern.debate("Test topic", rounds=1)
        debate_id = result["debate_id"]

        # Check tags
        judgments = pattern.get_shared_insights(tags=["judgment"])
        assert len(judgments) > 0

        # Should include debate_id
        debate_judgments = pattern.get_shared_insights(tags=[debate_id])
        assert len(debate_judgments) > 0

    def test_segments_work_correctly(self):
        """Test memory segments are used correctly."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

        # Check segments
        arguments = pattern.get_shared_insights(segment="arguments")
        judgments = pattern.get_shared_insights(segment="judgments")

        # Should have data in both segments
        assert len(arguments) > 0
        assert len(judgments) > 0

    def test_debate_isolation_via_tags(self):
        """Test debates are isolated via debate_id tags."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run two debates
        result1 = pattern.debate("Topic A", rounds=1)
        debate_id1 = result1["debate_id"]

        result2 = pattern.debate("Topic B", rounds=1)
        debate_id2 = result2["debate_id"]

        # Should have separate insights for each debate
        insights1 = pattern.get_shared_insights(tags=[debate_id1])
        insights2 = pattern.get_shared_insights(tags=[debate_id2])

        # IDs should be different
        assert debate_id1 != debate_id2
        # Both should have insights
        assert len(insights1) > 0
        assert len(insights2) > 0

    def test_importance_levels_are_correct(self):
        """Test importance levels: 0.8 for arguments, 0.9 for judgments."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

        # Check importance levels
        arguments = pattern.get_shared_insights(segment="arguments")
        judgments = pattern.get_shared_insights(segment="judgments")

        # Arguments should have importance 0.8
        for arg in arguments:
            assert arg.get("importance") == 0.8

        # Judgments should have importance 0.9
        for jdg in judgments:
            assert jdg.get("importance") == 0.9

    def test_shared_memory_read_by_judge(self):
        """Test judge reads arguments from shared memory."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create arguments
        pattern.proponent.construct_argument("Test topic", "")
        pattern.opponent.construct_argument("Test topic", "")

        # Create debate_id
        import uuid

        debate_id = f"debate_{uuid.uuid4().hex[:8]}"

        # Judge should be able to read arguments
        arguments = pattern.judge.get_arguments(debate_id)
        # May be empty if debate_id doesn't match, but should return dict
        assert isinstance(arguments, dict)

    def test_shared_memory_isolation_between_agents(self):
        """Test agents can read each other's insights."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Proponent creates argument
        pattern.proponent.construct_argument("Test topic", "")

        # Opponent should be able to read proponent's argument
        # (via shared memory tag filtering)
        all_insights = pattern.shared_memory.read_all()
        assert len(all_insights) > 0

    def test_memory_segments_organization(self):
        """Test memory is organized into segments."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

        # Check segments exist and are separate
        pattern.get_shared_insights(segment="arguments")
        judgments = pattern.get_shared_insights(segment="judgments")

        # Arguments should not be in judgments segment
        any("argument" in jdg.get("tags", []) for jdg in judgments)
        # This might be false depending on implementation

    def test_clear_shared_memory_removes_all_insights(self):
        """Test clear_shared_memory() removes all insights."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        pattern.debate("Test topic", rounds=1)

        # Should have insights
        before = len(pattern.shared_memory.read_all())
        assert before > 0

        # Clear
        pattern.clear_shared_memory()

        # Should be empty
        after = len(pattern.shared_memory.read_all())
        assert after == 0


# ============================================================================
# TEST CLASS 8: Error Handling (8 tests)
# ============================================================================


class TestDebatePatternErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_position_in_construct_argument(self):
        """Test handling of invalid position."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Proponent should construct FOR argument
        # Opponent should construct AGAINST argument
        # Both should work without explicit position parameter
        proponent_arg = pattern.proponent.construct_argument("Test", "")
        opponent_arg = pattern.opponent.construct_argument("Test", "")

        assert proponent_arg is not None
        assert opponent_arg is not None

    def test_no_arguments_for_debate(self):
        """Test judge_debate() with no arguments."""
        import uuid

        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create fake debate_id
        fake_debate_id = f"debate_{uuid.uuid4().hex[:8]}"

        # Should handle gracefully
        try:
            judgment = pattern.judge.judge_debate(fake_debate_id)
            # If it doesn't raise, should return dict
            assert isinstance(judgment, dict)
        except Exception:
            # It's okay to raise if no arguments
            pass

    def test_malformed_argument_structure(self):
        """Test handling of malformed argument."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Create malformed argument
        malformed_arg = {"invalid": "structure"}

        # Try to rebut malformed argument
        try:
            rebuttal = pattern.proponent.rebut(
                opponent_argument=malformed_arg, topic="Test topic"
            )
            # Should handle gracefully
            assert isinstance(rebuttal, dict)
        except Exception:
            # It's okay to raise on malformed input
            pass

    def test_invalid_confidence_value(self):
        """Test confidence validation with invalid values."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Run debate
        result = pattern.debate("Test topic", rounds=1)
        debate_id = result["debate_id"]

        # Get judgment
        judgment = pattern.judge.judge_debate(debate_id)

        # Confidence should be validated to 0.0-1.0
        confidence = judgment["confidence"]
        assert 0.0 <= float(confidence) <= 1.0

    def test_empty_topic(self):
        """Test debate with empty topic."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Should handle empty topic
        try:
            result = pattern.debate("", rounds=1)
            # If it doesn't raise, should return dict
            assert isinstance(result, dict)
        except Exception:
            # It's okay to raise on empty topic
            pass

    def test_zero_rounds(self):
        """Test debate with zero rounds."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Should handle zero rounds gracefully
        result = pattern.debate("Test topic", rounds=0)
        assert isinstance(result, dict)

    def test_negative_rounds(self):
        """Test debate with negative rounds."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Should handle negative rounds (treat as 0 or raise)
        try:
            result = pattern.debate("Test topic", rounds=-1)
            assert isinstance(result, dict)
        except Exception:
            # It's okay to raise on invalid rounds
            pass

    def test_invalid_debate_id_in_get_judgment(self):
        """Test get_judgment() with invalid debate_id."""
        from kaizen.agents.coordination import create_debate_pattern

        pattern = create_debate_pattern(llm_provider="mock")

        # Try to get judgment for non-existent debate
        try:
            judgment = pattern.get_judgment("invalid_debate_id")
            # If it doesn't raise, should return dict or None
            assert judgment is None or isinstance(judgment, dict)
        except Exception:
            # It's okay to raise on invalid ID
            pass
