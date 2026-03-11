"""
Tests for BaseAgent shared memory integration.

This module tests how BaseAgent integrates with SharedMemoryPool to enable
multi-agent collaboration through shared insights. Tests cover:
- Agent initialization with shared_memory parameter
- Agent ID generation (default vs custom)
- Reading shared insights before execution
- Writing insights after execution
- Multi-agent collaboration scenarios
- Backward compatibility (agents without shared_memory)
- Combined individual + shared memory

Test Coverage:
- Agent with shared_memory reads insights
- Agent with shared_memory writes insights
- Multiple agents collaborate via shared pool
- Agent reads insights from other agents (exclude_own)
- Agent without shared_memory works (backward compat)
- Combined: individual memory + shared memory
- Agent ID generation (default vs custom)
- Insight filtering in multi-agent scenario
- Sequential multi-agent workflow
- Parallel multi-agent workflow

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 2: Shared Memory, Task 2M.3)
"""


class TestBaseAgentSharedMemoryInitialization:
    """Test BaseAgent initialization with shared memory."""

    def test_agent_accepts_shared_memory_parameter(self):
        """Test that BaseAgent accepts shared_memory parameter."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        # Should not raise
        agent = BaseAgent(config=config, shared_memory=pool)

        assert agent.shared_memory is pool

    def test_agent_without_shared_memory_is_none(self):
        """Test that shared_memory defaults to None."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        assert agent.shared_memory is None

    def test_agent_id_auto_generated_if_not_provided(self):
        """Test that agent_id is auto-generated if not provided."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        # Should have an auto-generated agent_id
        assert hasattr(agent, "agent_id")
        assert agent.agent_id is not None
        assert isinstance(agent.agent_id, str)
        assert len(agent.agent_id) > 0

    def test_agent_id_custom_if_provided(self):
        """Test that custom agent_id is preserved."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, agent_id="my_custom_agent")

        assert agent.agent_id == "my_custom_agent"

    def test_different_agents_have_different_ids(self):
        """Test that different agents get different auto-generated IDs."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig()
        agent1 = BaseAgent(config=config)
        agent2 = BaseAgent(config=config)

        assert agent1.agent_id != agent2.agent_id


class TestBaseAgentReadsSharedInsights:
    """Test that BaseAgent reads shared insights before execution."""

    def test_agent_reads_shared_insights_during_run(self):
        """Test that agent receives shared insights via _shared_insights input."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        # Add insights to pool
        pool.write_insight(
            {
                "agent_id": "other_agent",
                "content": "Important finding",
                "tags": ["important"],
                "importance": 0.9,
                "segment": "analysis",
            }
        )

        # Create agent with shared memory
        agent = BaseAgent(config=config, shared_memory=pool, agent_id="test_agent")

        # Create mock strategy that captures inputs
        class CapturingStrategy:
            def __init__(self):
                self.captured_inputs = None

            async def execute(self, agent, inputs):
                self.captured_inputs = inputs
                return {"result": "test"}

        strategy = CapturingStrategy()
        agent.strategy = strategy

        # Run agent
        agent.run(prompt="test")

        # Strategy should have received _shared_insights
        assert strategy.captured_inputs is not None
        assert "_shared_insights" in strategy.captured_inputs
        assert len(strategy.captured_inputs["_shared_insights"]) == 1

    def test_agent_excludes_own_insights_by_default(self):
        """Test that agent excludes its own insights when reading."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        # Add insights from different agents
        pool.write_insight(
            {
                "agent_id": "test_agent",
                "content": "My own insight",
                "tags": ["test"],
                "importance": 0.9,
                "segment": "test",
            }
        )
        pool.write_insight(
            {
                "agent_id": "other_agent",
                "content": "Other's insight",
                "tags": ["test"],
                "importance": 0.8,
                "segment": "test",
            }
        )

        # Create agent
        agent = BaseAgent(config=config, shared_memory=pool, agent_id="test_agent")

        # Capture inputs
        class CapturingStrategy:
            def __init__(self):
                self.captured_inputs = None

            async def execute(self, agent, inputs):
                self.captured_inputs = inputs
                return {"result": "test"}

        strategy = CapturingStrategy()
        agent.strategy = strategy

        # Run
        agent.run(prompt="test")

        # Should only see other agent's insight
        insights = strategy.captured_inputs["_shared_insights"]
        assert len(insights) == 1
        assert insights[0]["content"] == "Other's insight"

    def test_agent_reads_top_10_insights_by_default(self):
        """Test that agent reads top 10 most relevant insights by default."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        # Add 20 insights
        for i in range(20):
            pool.write_insight(
                {
                    "agent_id": "other_agent",
                    "content": f"Insight {i}",
                    "tags": ["test"],
                    "importance": 0.5 + (i * 0.01),  # Varying importance
                    "segment": "test",
                }
            )

        agent = BaseAgent(config=config, shared_memory=pool, agent_id="test_agent")

        # Capture
        class CapturingStrategy:
            def __init__(self):
                self.captured_inputs = None

            async def execute(self, agent, inputs):
                self.captured_inputs = inputs
                return {"result": "test"}

        strategy = CapturingStrategy()
        agent.strategy = strategy

        agent.run(prompt="test")

        # Should get top 10 (limit=10)
        insights = strategy.captured_inputs["_shared_insights"]
        assert len(insights) <= 10


class TestBaseAgentWritesSharedInsights:
    """Test that BaseAgent writes insights after execution."""

    def test_agent_writes_insight_when_result_has_write_insight(self):
        """Test that agent writes insight when result contains _write_insight key."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        agent = BaseAgent(config=config, shared_memory=pool, agent_id="test_agent")

        # Create strategy that returns _write_insight
        class InsightWritingStrategy:
            async def execute(self, agent, inputs):
                return {
                    "response": "Test response",
                    "_write_insight": "Important finding discovered",
                    "_insight_tags": ["discovery", "important"],
                    "_insight_importance": 0.9,
                    "_insight_segment": "analysis",
                }

        agent.strategy = InsightWritingStrategy()

        # Run
        agent.run(prompt="test")

        # Check pool has insight
        insights = pool.read_all()
        assert len(insights) == 1
        assert insights[0]["agent_id"] == "test_agent"
        assert insights[0]["content"] == "Important finding discovered"
        assert insights[0]["tags"] == ["discovery", "important"]
        assert insights[0]["importance"] == 0.9
        assert insights[0]["segment"] == "analysis"

    def test_agent_does_not_write_without_write_insight_key(self):
        """Test that agent doesn't write insight if result has no _write_insight."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        agent = BaseAgent(config=config, shared_memory=pool, agent_id="test_agent")

        # Strategy that doesn't return _write_insight
        class NormalStrategy:
            async def execute(self, agent, inputs):
                return {"response": "Normal response"}

        agent.strategy = NormalStrategy()

        agent.run(prompt="test")

        # Pool should be empty
        assert len(pool.read_all()) == 0

    def test_insight_uses_default_values_if_not_provided(self):
        """Test that insight uses defaults for optional fields."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        agent = BaseAgent(config=config, shared_memory=pool, agent_id="test_agent")

        # Strategy that only provides minimal insight
        class MinimalInsightStrategy:
            async def execute(self, agent, inputs):
                return {"response": "Test", "_write_insight": "Minimal insight"}

        agent.strategy = MinimalInsightStrategy()

        agent.run(prompt="test")

        # Should use defaults
        insights = pool.read_all()
        assert len(insights) == 1
        assert insights[0]["tags"] == []
        assert insights[0]["importance"] == 0.5
        assert insights[0]["segment"] == "execution"


class TestMultiAgentCollaboration:
    """Test multi-agent collaboration via shared memory."""

    def test_two_agents_collaborate_sequentially(self):
        """Test sequential collaboration: Agent1 writes, Agent2 reads."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        # Agent 1: Analyzer
        agent1 = BaseAgent(config=config, shared_memory=pool, agent_id="analyzer")

        class AnalyzerStrategy:
            async def execute(self, agent, inputs):
                return {
                    "response": "Analysis complete",
                    "_write_insight": "High-priority customer issue detected",
                    "_insight_tags": ["customer", "urgent"],
                    "_insight_importance": 0.9,
                    "_insight_segment": "analysis",
                }

        agent1.strategy = AnalyzerStrategy()

        # Agent 2: Responder
        agent2 = BaseAgent(config=config, shared_memory=pool, agent_id="responder")

        class ResponderStrategy:
            def __init__(self):
                self.captured_insights = None

            async def execute(self, agent, inputs):
                self.captured_insights = inputs.get("_shared_insights", [])
                return {
                    "response": "Response prepared",
                    "_write_insight": "Response strategy formulated",
                    "_insight_tags": ["response", "customer"],
                    "_insight_importance": 0.8,
                    "_insight_segment": "planning",
                }

        responder_strategy = ResponderStrategy()
        agent2.strategy = responder_strategy

        # Execute: Agent1 analyzes, Agent2 responds
        agent1.run(prompt="Analyze customer complaint")
        agent2.run(prompt="Generate response")

        # Agent2 should have seen Agent1's insight
        assert responder_strategy.captured_insights is not None
        assert len(responder_strategy.captured_insights) == 1
        assert (
            responder_strategy.captured_insights[0]["content"]
            == "High-priority customer issue detected"
        )

        # Pool should have 2 insights
        all_insights = pool.read_all()
        assert len(all_insights) == 2

    def test_three_agents_collaborate(self):
        """Test three agents collaborating in sequence."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        pool = SharedMemoryPool()

        # Create 3 agents
        agents = []
        strategies = []
        for i in range(3):
            agent = BaseAgent(config=config, shared_memory=pool, agent_id=f"agent_{i}")

            class TestStrategy:
                def __init__(self, agent_num):
                    self.agent_num = agent_num
                    self.captured_insights = None

                async def execute(self, agent, inputs):
                    self.captured_insights = inputs.get("_shared_insights", [])
                    return {
                        "response": f"Agent {self.agent_num} response",
                        "_write_insight": f"Insight from agent {self.agent_num}",
                        "_insight_tags": ["collaboration"],
                        "_insight_importance": 0.7 + (self.agent_num * 0.1),
                        "_insight_segment": "test",
                    }

            strategy = TestStrategy(i)
            agent.strategy = strategy
            agents.append(agent)
            strategies.append(strategy)

        # Execute all agents
        for agent in agents:
            agent.run(prompt="test")

        # Agent 0: sees 0 insights (first)
        assert len(strategies[0].captured_insights) == 0

        # Agent 1: sees 1 insight (from agent 0)
        assert len(strategies[1].captured_insights) == 1

        # Agent 2: sees 2 insights (from agent 0 and 1)
        assert len(strategies[2].captured_insights) == 2

        # Pool has 3 total insights
        assert len(pool.read_all()) == 3


class TestBackwardCompatibility:
    """Test that agents without shared memory still work."""

    def test_agent_without_shared_memory_works_normally(self):
        """Test that agent without shared_memory parameter works normally."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config)  # No shared_memory

        # Should work normally
        class NormalStrategy:
            async def execute(self, agent, inputs):
                return {"response": "Normal execution"}

        agent.strategy = NormalStrategy()

        result = agent.run(prompt="test")

        assert result["response"] == "Normal execution"

    def test_agent_without_shared_memory_does_not_receive_shared_insights(self):
        """Test that agent without shared_memory doesn't receive _shared_insights."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config)

        class CapturingStrategy:
            def __init__(self):
                self.captured_inputs = None

            async def execute(self, agent, inputs):
                self.captured_inputs = inputs
                return {"response": "test"}

        strategy = CapturingStrategy()
        agent.strategy = strategy

        agent.run(prompt="test")

        # Should NOT have _shared_insights
        assert "_shared_insights" not in strategy.captured_inputs


class TestCombinedIndividualAndSharedMemory:
    """Test agents using both individual and shared memory."""

    def test_agent_with_both_memory_types(self):
        """Test agent with both individual memory and shared memory."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()
        individual_memory = BufferMemory()
        shared_memory = SharedMemoryPool()

        agent = BaseAgent(
            config=config,
            memory=individual_memory,
            shared_memory=shared_memory,
            agent_id="test_agent",
        )

        # Strategy that checks for both memory types
        class DualMemoryStrategy:
            def __init__(self):
                self.has_individual_memory = False
                self.has_shared_memory = False

            async def execute(self, agent, inputs):
                self.has_individual_memory = "_memory_context" in inputs
                self.has_shared_memory = "_shared_insights" in inputs
                return {"response": "test"}

        strategy = DualMemoryStrategy()
        agent.strategy = strategy

        # Run with session_id (for individual memory)
        agent.run(prompt="test", session_id="session1")

        # Both should be available
        assert strategy.has_individual_memory is True
        assert strategy.has_shared_memory is True

    def test_individual_memory_persists_per_session_shared_memory_global(self):
        """Test that individual memory is per-session but shared memory is global."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.memory.buffer import BufferMemory
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = BaseAgentConfig()

        # Two agents with separate individual memory but same shared memory
        memory1 = BufferMemory()
        memory2 = BufferMemory()
        shared = SharedMemoryPool()

        agent1 = BaseAgent(
            config=config, memory=memory1, shared_memory=shared, agent_id="agent1"
        )
        agent2 = BaseAgent(
            config=config, memory=memory2, shared_memory=shared, agent_id="agent2"
        )

        # Simple strategy
        class SimpleStrategy:
            async def execute(self, agent, inputs):
                return {
                    "response": f"Response from {agent.agent_id}",
                    "_write_insight": f"Insight from {agent.agent_id}",
                    "_insight_tags": ["test"],
                    "_insight_importance": 0.5,
                    "_insight_segment": "test",
                }

        agent1.strategy = SimpleStrategy()
        agent2.strategy = SimpleStrategy()

        # Agent1: session1
        agent1.run(prompt="test1", session_id="session1")

        # Agent2: session2 (different session)
        agent2.run(prompt="test2", session_id="session2")

        # Individual memory: each has 1 turn in their own session
        context1 = memory1.load_context("session1")
        context2 = memory2.load_context("session2")
        assert len(context1["turns"]) == 1
        assert len(context2["turns"]) == 1

        # Shared memory: both insights are global
        all_insights = shared.read_all()
        assert len(all_insights) == 2
