"""
Tests for DataFlow integration base classes.

Verifies:
- DataFlowAwareAgent creation
- DataFlowOperationsMixin functionality
- Agent behavior with/without DataFlow
- Database operation capabilities
"""

from unittest.mock import MagicMock

import pytest


class TestDataFlowOperationsMixin:
    """Test suite for DataFlowOperationsMixin."""

    @pytest.fixture
    def mock_dataflow(self):
        """Create a mock DataFlow instance."""
        mock_db = MagicMock()
        mock_db.list_models.return_value = ["User", "Product"]
        return mock_db

    @pytest.fixture
    def mixin_class(self):
        """Get DataFlowOperationsMixin class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowOperationsMixin,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowOperationsMixin
        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_mixin_connect_dataflow(self, mock_dataflow, mixin_class):
        """
        Verify mixin can connect to DataFlow instance.

        Mixin should establish connection and store reference.
        """
        mixin = mixin_class()
        mixin.connect_dataflow(mock_dataflow)

        # Should have connection
        assert mixin.db_connection is not None
        assert mixin.db_connection.db is mock_dataflow

    def test_mixin_connect_dataflow_type_validation(self, mixin_class):
        """
        Verify mixin validates DataFlow instance type.

        Should reject non-DataFlow objects with clear error.
        """
        mixin = mixin_class()

        # Should raise TypeError for invalid type
        with pytest.raises(TypeError, match="Expected DataFlow instance"):
            mixin.connect_dataflow("not a dataflow instance")

    def test_mixin_query_database_without_connection(self, mixin_class):
        """
        Verify mixin requires connection before database operations.

        Should raise clear error when connection not established.
        """
        mixin = mixin_class()

        # Should raise RuntimeError when no connection
        with pytest.raises(RuntimeError, match="No DataFlow connection"):
            mixin.query_database(table="users")

    def test_mixin_query_database_with_connection(self, mock_dataflow, mixin_class):
        """
        Verify mixin can execute database queries.

        Should successfully query database when connected.
        """
        # Setup mock query results
        mock_results = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        mock_dataflow.query = MagicMock(return_value=mock_results)

        mixin = mixin_class()
        mixin.connect_dataflow(mock_dataflow)

        # Should execute query
        results = mixin.query_database(table="users", filter={"active": True})

        assert results is not None
        assert len(results) == 2

    def test_mixin_multiple_database_operations(self, mock_dataflow, mixin_class):
        """
        Verify mixin supports multiple database operations.

        Should handle create, read, update, delete operations.
        """
        mixin = mixin_class()
        mixin.connect_dataflow(mock_dataflow)

        # Verify connection allows operations
        assert mixin.db_connection is not None
        assert hasattr(mixin, "query_database")


class TestDataFlowAwareAgent:
    """Test suite for DataFlowAwareAgent base class."""

    @pytest.fixture
    def mock_dataflow(self):
        """Create a mock DataFlow instance."""
        mock_db = MagicMock()
        mock_db.list_models.return_value = ["User"]
        return mock_db

    @pytest.fixture
    def agent_class(self):
        """Get DataFlowAwareAgent class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowAwareAgent,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowAwareAgent
        except ImportError:
            pytest.skip("DataFlow integration not available")

    @pytest.fixture
    def agent_config(self):
        """Create agent configuration."""
        from kaizen.core.config import BaseAgentConfig

        return BaseAgentConfig(llm_provider="mock", model="gpt-4")

    def test_dataflow_aware_agent_creation(self, agent_class, agent_config):
        """
        Verify DataFlowAwareAgent can be created.

        Should inherit from BaseAgent and include DataFlow capabilities.
        """
        agent = agent_class(config=agent_config)

        # Should be instance of BaseAgent
        from kaizen.core.base_agent import BaseAgent

        assert isinstance(agent, BaseAgent)

        # Should have DataFlow mixin capabilities
        assert hasattr(agent, "connect_dataflow")
        assert hasattr(agent, "db_connection")

    def test_dataflow_aware_agent_with_db_parameter(
        self, agent_class, agent_config, mock_dataflow
    ):
        """
        Verify DataFlowAwareAgent accepts DataFlow in constructor.

        Should automatically establish connection when db provided.
        """
        agent = agent_class(config=agent_config, db=mock_dataflow)

        # Should have connection established
        assert agent.db_connection is not None
        assert agent.db_connection.db is mock_dataflow

    def test_agent_without_dataflow_instance(self, agent_class, agent_config):
        """
        Verify agent works without DataFlow connection.

        Agent should be fully functional even without database.
        """
        agent = agent_class(config=agent_config)

        # Should exist and work
        assert agent is not None
        assert agent.config is not None
        assert agent.config.llm_provider == "mock"

        # Should not have connection
        assert agent.db_connection is None

    def test_agent_with_dataflow_instance(
        self, agent_class, agent_config, mock_dataflow
    ):
        """
        Verify agent enhanced with DataFlow connection.

        Agent with DataFlow should have database capabilities.
        """
        agent = agent_class(config=agent_config, db=mock_dataflow)

        # Should have connection
        assert agent.db_connection is not None

        # Should have database operations
        assert hasattr(agent, "query_database")

    def test_agent_connect_dataflow_after_creation(
        self, agent_class, agent_config, mock_dataflow
    ):
        """
        Verify agent can connect to DataFlow after creation.

        Should support lazy connection establishment.
        """
        agent = agent_class(config=agent_config)

        # Initially no connection
        assert agent.db_connection is None

        # Connect after creation
        agent.connect_dataflow(mock_dataflow)

        # Now should have connection
        assert agent.db_connection is not None
        assert agent.db_connection.db is mock_dataflow

    def test_agent_database_operations_integration(
        self, agent_class, agent_config, mock_dataflow
    ):
        """
        Verify agent can execute database operations.

        Should integrate BaseAgent with DataFlow operations.
        """
        mock_dataflow.query = MagicMock(return_value=[{"id": 1}])

        agent = agent_class(config=agent_config, db=mock_dataflow)

        # Should execute database operations
        results = agent.query_database(table="users")

        assert results is not None


class TestBaseClassInheritance:
    """Test inheritance and class hierarchy."""

    @pytest.fixture
    def agent_class(self):
        """Get DataFlowAwareAgent class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowAwareAgent,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowAwareAgent
        except ImportError:
            pytest.skip("DataFlow integration not available")

    @pytest.fixture
    def mixin_class(self):
        """Get DataFlowOperationsMixin class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowOperationsMixin,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowOperationsMixin
        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_aware_agent_inherits_base_agent(self, agent_class):
        """
        Verify DataFlowAwareAgent inherits from BaseAgent.

        Should have all BaseAgent capabilities.
        """
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="gpt-4")
        agent = agent_class(config=config)

        # Should be BaseAgent instance
        assert isinstance(agent, BaseAgent)

        # Should have BaseAgent attributes
        assert hasattr(agent, "config")
        assert hasattr(agent, "execute")

    def test_aware_agent_includes_mixin(self, agent_class, mixin_class):
        """
        Verify DataFlowAwareAgent includes DataFlowOperationsMixin.

        Should have all mixin capabilities.
        """
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="gpt-4")
        agent = agent_class(config=config)

        # Should have mixin methods
        assert hasattr(agent, "connect_dataflow")
        assert hasattr(agent, "query_database")
        assert hasattr(agent, "db_connection")

    def test_mixin_can_be_added_to_custom_agents(self, mixin_class):
        """
        Verify DataFlowOperationsMixin can be added to custom agents.

        Should support composition pattern.
        """
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        # Create custom agent with mixin
        class CustomDatabaseAgent(BaseAgent, mixin_class):
            def __init__(self, config, db=None):
                super().__init__(config)
                if db is not None:
                    self.connect_dataflow(db)

        config = BaseAgentConfig(llm_provider="mock", model="gpt-4")
        agent = CustomDatabaseAgent(config=config)

        # Should have both BaseAgent and mixin capabilities
        assert isinstance(agent, BaseAgent)
        assert hasattr(agent, "connect_dataflow")


class TestIntegrationPatterns:
    """Test common integration usage patterns."""

    @pytest.fixture
    def mock_dataflow(self):
        """Create a mock DataFlow instance."""
        mock_db = MagicMock()
        mock_db.list_models.return_value = ["User", "Product"]
        mock_db.query = MagicMock(return_value=[])
        return mock_db

    @pytest.fixture
    def agent_class(self):
        """Get DataFlowAwareAgent class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowAwareAgent,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowAwareAgent
        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_pattern_agent_with_embedded_dataflow(self, agent_class, mock_dataflow):
        """
        Test pattern: Agent with embedded DataFlow instance.

        Common pattern for single-agent database applications.
        """
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="gpt-4")

        # Create agent with DataFlow
        agent = agent_class(config=config, db=mock_dataflow)

        # Should work seamlessly
        assert agent.db_connection is not None

    def test_pattern_multiple_agents_shared_database(self, agent_class, mock_dataflow):
        """
        Test pattern: Multiple agents sharing database.

        Common pattern for multi-agent coordination.
        """
        from kaizen.core.config import BaseAgentConfig

        # Create multiple agents with shared DataFlow
        agent1 = agent_class(
            config=BaseAgentConfig(llm_provider="mock", model="gpt-4"), db=mock_dataflow
        )

        agent2 = agent_class(
            config=BaseAgentConfig(llm_provider="mock", model="gpt-4"), db=mock_dataflow
        )

        # Both should share database
        assert agent1.db_connection.db is agent2.db_connection.db

    def test_pattern_lazy_dataflow_connection(self, agent_class, mock_dataflow):
        """
        Test pattern: Lazy DataFlow connection.

        Common pattern for conditional database usage.
        """
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="gpt-4")

        # Create agent without DataFlow
        agent = agent_class(config=config)
        assert agent.db_connection is None

        # Connect later when needed
        agent.connect_dataflow(mock_dataflow)
        assert agent.db_connection is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
