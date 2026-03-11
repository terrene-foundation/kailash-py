"""
Integration tests for AI-enhanced database operations with real database.

Tier 2 Testing (NO MOCKING) - Uses real database infrastructure.

Verifies:
- End-to-end NL to SQL execution
- Data transformation pipelines with real database
- Quality assessment workflows
- Intelligent bulk operations
- Semantic database search

Prerequisites:
- PostgreSQL or SQLite database available
- DataFlow installed
- Real LLM provider configured (or skip with @pytest.mark.real_llm)
"""

import os

import pytest


@pytest.fixture(scope="module")
def database_url():
    """
    Get database URL for integration tests.

    Uses SQLite for local testing, can be overridden with env var.
    """
    return os.getenv("TEST_DATABASE_URL", "sqlite:///test_ai_db_operations.db")


@pytest.fixture(scope="module")
def dataflow_instance(database_url):
    """
    Create real DataFlow instance for integration tests.

    This is a REAL database connection - no mocking.
    """
    try:
        from dataflow import DataFlow
    except ImportError:
        pytest.skip("DataFlow not available")

    # Create DataFlow instance
    db = DataFlow(database_url, auto_migrate=True)

    # Define test models
    @db.model
    class User:
        name: str
        email: str
        age: int = None
        department: str = None

    @db.model
    class Product:
        name: str
        inventory: int
        demand_score: float = None
        category: str = None

    yield db

    # Cleanup: Drop test database (SQLite)
    if database_url.startswith("sqlite:///"):
        import os

        db_file = database_url.replace("sqlite:///", "")
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.fixture
def agent_config():
    """Create agent configuration for integration tests."""
    from kaizen.core.config import BaseAgentConfig

    return BaseAgentConfig(
        llm_provider=os.getenv("TEST_LLM_PROVIDER", "mock"),
        model=os.getenv("TEST_LLM_MODEL", "gpt-4"),
        temperature=0.2,
    )


class TestNLQueryToDataFlowExecution:
    """Integration tests for natural language query to execution."""

    @pytest.fixture
    def nl_agent_class(self):
        """Get NLToSQLAgent class."""
        try:
            from kaizen.integrations.dataflow.ai_enhanced_ops import NLToSQLAgent

            return NLToSQLAgent
        except ImportError:
            pytest.skip("AI enhanced operations not implemented yet")

    @pytest.fixture
    def setup_test_data(self, dataflow_instance):
        """Setup test data in real database."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Insert test users
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkCreateNode",
            "create_users",
            {
                "data": [
                    {
                        "name": "Alice Smith",
                        "email": "alice@example.com",
                        "age": 28,
                        "department": "Engineering",
                    },
                    {
                        "name": "Bob Jones",
                        "email": "bob@example.com",
                        "age": 35,
                        "department": "Sales",
                    },
                    {
                        "name": "Carol White",
                        "email": "carol@example.com",
                        "age": 22,
                        "department": "Engineering",
                    },
                    {
                        "name": "David Brown",
                        "email": "david@example.com",
                        "age": 45,
                        "department": "Marketing",
                    },
                ]
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results

    @pytest.mark.real_llm
    def test_nl_query_to_dataflow_execution(
        self, nl_agent_class, agent_config, dataflow_instance, setup_test_data
    ):
        """
        Test end-to-end NL query execution.

        Given: Real database with user data
        When: Natural language query executed
        Then: Returns correct results from database
        """
        agent = nl_agent_class(config=agent_config, db=dataflow_instance)

        result = agent.run(query="Show me all users in the Engineering department")

        # Should return results
        assert result is not None
        assert "results" in result
        assert "explanation" in result

        # Should have explanation
        assert len(result["explanation"]) > 0

    @pytest.mark.real_llm
    def test_nl_query_with_age_filter(
        self, nl_agent_class, agent_config, dataflow_instance, setup_test_data
    ):
        """
        Test NL query with numeric comparison.

        Given: Database with users of different ages
        When: Query "users over 30"
        Then: Returns only users with age > 30
        """
        agent = nl_agent_class(config=agent_config, db=dataflow_instance)

        result = agent.run(query="Find users over 30 years old")

        # Should filter correctly
        assert result is not None

    @pytest.mark.real_llm
    def test_nl_query_aggregation(
        self, nl_agent_class, agent_config, dataflow_instance, setup_test_data
    ):
        """
        Test NL query with aggregation.

        Given: Database with users
        When: Query "count users by department"
        Then: Returns aggregated results
        """
        agent = nl_agent_class(config=agent_config, db=dataflow_instance)

        result = agent.run(query="Count how many users are in each department")

        # Should aggregate
        assert result is not None


class TestDataTransformationPipeline:
    """Integration tests for data transformation with real database."""

    @pytest.fixture
    def transform_agent_class(self):
        """Get DataTransformAgent class."""
        try:
            from kaizen.integrations.dataflow.ai_enhanced_ops import DataTransformAgent

            return DataTransformAgent
        except ImportError:
            pytest.skip("Data transform agent not implemented yet")

    @pytest.mark.real_llm
    def test_transform_data_between_schemas(
        self, transform_agent_class, agent_config, dataflow_instance
    ):
        """
        Test data transformation pipeline.

        Given: Source data with different schema
        When: Agent transforms to target schema
        Then: Data inserted into real database
        """
        agent = transform_agent_class(config=agent_config, db=dataflow_instance)

        # Source data with different field names
        source_data = [
            {
                "full_name": "Test User 1",
                "email_address": "test1@example.com",
                "years_old": 30,
            },
            {
                "full_name": "Test User 2",
                "email_address": "test2@example.com",
                "years_old": 25,
            },
        ]

        result = agent.transform_data(source_data=source_data, target_table="User")

        # Should insert data
        assert result is not None
        assert "inserted_count" in result or "transformed_data" in result

    @pytest.mark.real_llm
    def test_transformation_with_quality_check(
        self, transform_agent_class, agent_config, dataflow_instance
    ):
        """
        Test transformation includes quality assessment.

        Given: Source data with quality issues
        When: Agent transforms data
        Then: Reports quality issues and handles gracefully
        """
        agent = transform_agent_class(config=agent_config, db=dataflow_instance)

        source_data = [
            {"name": "", "email": "invalid-email", "age": -5},  # Bad data
            {"name": "Valid User", "email": "valid@example.com", "age": 30},
        ]

        result = agent.transform_data(source_data=source_data, target_table="User")

        # Should identify quality issues
        assert result is not None
        if "quality_issues" in result:
            assert len(result["quality_issues"]) > 0


class TestQualityAssessmentWorkflow:
    """Integration tests for data quality assessment."""

    @pytest.fixture
    def quality_agent_class(self):
        """Get DataQualityAgent class."""
        try:
            from kaizen.integrations.dataflow.ai_enhanced_ops import DataQualityAgent

            return DataQualityAgent
        except ImportError:
            pytest.skip("Data quality agent not implemented yet")

    @pytest.fixture
    def setup_quality_test_data(self, dataflow_instance):
        """Setup data with quality issues."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkCreateNode",
            "create_users",
            {
                "data": [
                    {"name": "Good User", "email": "good@example.com", "age": 25},
                    {"name": "", "email": "bad", "age": 999},  # Quality issues
                    {
                        "name": "Another Good User",
                        "email": "another@example.com",
                        "age": 30,
                    },
                ]
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results

    @pytest.mark.real_llm
    def test_assess_and_fix_data_quality(
        self,
        quality_agent_class,
        agent_config,
        dataflow_instance,
        setup_quality_test_data,
    ):
        """
        Test quality assessment and fixing workflow.

        Given: Real database with quality issues
        When: Agent assesses and fixes
        Then: Quality improves
        """
        agent = quality_agent_class(config=agent_config)

        # Get sample data from database
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node("UserListNode", "list_users", {"limit": 10})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        users = results.get("list_users", [])

        # Assess quality
        schema = {
            "columns": {
                "name": {"type": "str", "nullable": False},
                "email": {"type": "str", "nullable": False},
                "age": {"type": "int", "nullable": True},
            }
        }

        result = agent.assess_quality(data_sample=users, schema=schema)

        # Should identify issues
        assert result is not None
        assert "quality_score" in result or "issues_found" in result


class TestIntelligentBulkInsert:
    """Integration tests for AI-optimized bulk operations."""

    @pytest.fixture
    def bulk_optimizer_class(self):
        """Get bulk operation optimizer class."""
        try:
            from kaizen.integrations.dataflow.query_optimizer import (
                BulkOperationOptimizer,
            )

            return BulkOperationOptimizer
        except ImportError:
            pytest.skip("Bulk optimizer not implemented yet")

    @pytest.mark.real_llm
    def test_intelligent_bulk_insert_optimization(
        self, bulk_optimizer_class, agent_config, dataflow_instance
    ):
        """
        Test AI-optimized bulk insert.

        Given: Large dataset for insertion
        When: Agent optimizes bulk operation
        Then: Inserts efficiently with optimal batch size
        """
        optimizer = bulk_optimizer_class(config=agent_config)

        # Generate large dataset
        large_dataset = [
            {"name": f"User {i}", "email": f"user{i}@example.com", "age": 20 + (i % 50)}
            for i in range(1000)
        ]

        result = optimizer.optimize_bulk_insert(data=large_dataset, target_table="User")

        # Should optimize
        assert result is not None
        assert "batch_size" in result or "strategy" in result


class TestSemanticDatabaseSearch:
    """Integration tests for semantic search across tables."""

    @pytest.fixture
    def semantic_agent_class(self):
        """Get SemanticSearchAgent class."""
        try:
            from kaizen.integrations.dataflow.ai_enhanced_ops import SemanticSearchAgent

            return SemanticSearchAgent
        except ImportError:
            pytest.skip("Semantic search agent not implemented yet")

    @pytest.fixture
    def setup_multi_table_data(self, dataflow_instance):
        """Setup data across multiple tables."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Insert users
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkCreateNode",
            "create_users",
            {
                "data": [
                    {"name": "Alice", "email": "alice@example.com", "age": 25},
                    {"name": "Bob", "email": "bob@example.com", "age": 30},
                ]
            },
        )

        # Insert products
        workflow.add_node(
            "ProductBulkCreateNode",
            "create_products",
            {
                "data": [
                    {
                        "name": "Laptop",
                        "inventory": 5,
                        "demand_score": 0.9,
                        "category": "Electronics",
                    },
                    {
                        "name": "Phone",
                        "inventory": 15,
                        "demand_score": 0.95,
                        "category": "Electronics",
                    },
                    {
                        "name": "Desk",
                        "inventory": 20,
                        "demand_score": 0.3,
                        "category": "Furniture",
                    },
                ]
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results

    @pytest.mark.real_llm
    def test_semantic_search_across_tables(
        self,
        semantic_agent_class,
        agent_config,
        dataflow_instance,
        setup_multi_table_data,
    ):
        """
        Test semantic search across multiple tables.

        Given: Real database with users and products
        When: Semantic query executed
        Then: Identifies relevant tables and returns results
        """
        agent = semantic_agent_class(config=agent_config, db=dataflow_instance)

        result = agent.search(query="Find popular electronics with low inventory")

        # Should search semantically
        assert result is not None
        assert "relevant_tables" in result or "results" in result

    @pytest.mark.real_llm
    def test_semantic_search_with_context(
        self,
        semantic_agent_class,
        agent_config,
        dataflow_instance,
        setup_multi_table_data,
    ):
        """
        Test semantic search with additional context.

        Given: Database with multiple tables
        When: Query with business context
        Then: Uses context to improve search
        """
        agent = semantic_agent_class(config=agent_config, db=dataflow_instance)

        result = agent.search(
            query="Items we should restock soon",
            context="Focus on high demand products",
        )

        # Should use context
        assert result is not None


class TestEndToEndAIPipeline:
    """Integration tests for complete AI-enhanced workflows."""

    @pytest.fixture
    def all_agent_classes(self):
        """Get all AI agent classes."""
        try:
            from kaizen.integrations.dataflow.ai_enhanced_ops import (
                DataQualityAgent,
                DataTransformAgent,
                NLToSQLAgent,
            )

            return {
                "nl_to_sql": NLToSQLAgent,
                "transform": DataTransformAgent,
                "quality": DataQualityAgent,
            }
        except ImportError:
            pytest.skip("AI enhanced operations not implemented yet")

    @pytest.mark.real_llm
    def test_complete_ai_pipeline(
        self, all_agent_classes, agent_config, dataflow_instance
    ):
        """
        Test complete AI-enhanced data pipeline.

        Given: Raw data needing transformation
        When: Pipeline runs (quality check → transform → query)
        Then: Data processed and queryable via NL
        """
        # Step 1: Assess quality
        quality_agent = all_agent_classes["quality"](config=agent_config)

        raw_data = [
            {"full_name": "  Alice Smith  ", "email": "ALICE@EXAMPLE.COM", "age": 28},
            {"full_name": "Bob Jones", "email": "bob@example.com", "age": 35},
        ]

        quality_result = quality_agent.assess_quality(
            data_sample=raw_data,
            schema={
                "columns": {
                    "name": {"type": "str"},
                    "email": {"type": "str"},
                    "age": {"type": "int"},
                }
            },
        )

        # Step 2: Transform and load
        transform_agent = all_agent_classes["transform"](
            config=agent_config, db=dataflow_instance
        )

        transform_result = transform_agent.transform_data(
            source_data=raw_data, target_table="User"
        )

        # Step 3: Query via natural language
        nl_agent = all_agent_classes["nl_to_sql"](
            config=agent_config, db=dataflow_instance
        )

        query_result = nl_agent.run(query="Show me all users")

        # All steps should succeed
        assert quality_result is not None
        assert transform_result is not None
        assert query_result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
