"""
Tests for customer-service enterprise workflow example.

This test suite validates:
1. Individual agent behavior (TicketTriageAgent, KnowledgeSearchAgent, ResponseGeneratorAgent, TicketRouterAgent)
2. Workflow integration and multi-agent collaboration
3. Shared memory usage for customer service pipeline
4. Real-world customer service automation scenarios

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load customer-service example
_customer_service_module = import_example_module(
    "examples/3-enterprise-workflows/customer-service"
)
TicketTriageAgent = _customer_service_module.TicketTriageAgent
KnowledgeSearchAgent = _customer_service_module.KnowledgeSearchAgent
ResponseGeneratorAgent = _customer_service_module.ResponseGeneratorAgent
TicketRouterAgent = _customer_service_module.TicketRouterAgent
CustomerServiceConfig = _customer_service_module.CustomerServiceConfig
batch_ticket_processing = _customer_service_module.batch_ticket_processing
customer_service_workflow = _customer_service_module.customer_service_workflow


class TestCustomerServiceAgents:
    """Test individual agent behavior."""

    def test_ticket_triage_agent_triages_tickets(self):
        """Test TicketTriageAgent triages support tickets."""

        config = CustomerServiceConfig(llm_provider="mock")
        agent = TicketTriageAgent(config)

        ticket = {
            "ticket_id": "T123",
            "subject": "Cannot login to account",
            "description": "Getting error message when trying to log in",
            "customer_email": "test@example.com",
        }

        result = agent.triage(ticket)

        assert result is not None
        assert "priority" in result
        assert "category" in result
        assert "urgency" in result

    def test_knowledge_search_agent_searches_knowledge(self):
        """Test KnowledgeSearchAgent searches knowledge base."""

        config = CustomerServiceConfig(llm_provider="mock")
        agent = KnowledgeSearchAgent(config)

        query = "How to reset password"

        result = agent.search_knowledge(query)

        assert result is not None
        assert "articles" in result
        assert "solutions" in result

    def test_response_generator_agent_generates_response(self):
        """Test ResponseGeneratorAgent generates customer response."""

        config = CustomerServiceConfig(llm_provider="mock")
        agent = ResponseGeneratorAgent(config)

        ticket = {"subject": "Login issue"}
        knowledge = {"articles": ["Reset password guide"]}

        result = agent.generate_response(ticket, knowledge)

        assert result is not None
        assert "response" in result
        assert "tone" in result

    def test_ticket_router_agent_routes_tickets(self):
        """Test TicketRouterAgent routes tickets to appropriate agents."""

        config = CustomerServiceConfig(llm_provider="mock")
        agent = TicketRouterAgent(config)

        triage_result = {
            "priority": "high",
            "category": "technical",
            "urgency": "immediate",
        }

        result = agent.route(triage_result)

        assert result is not None
        assert "routing_decision" in result
        assert "assigned_team" in result


class TestCustomerServiceWorkflow:
    """Test complete customer service workflow."""

    def test_single_ticket_processing(self):
        """Test processing a single customer ticket."""

        config = CustomerServiceConfig(llm_provider="mock")

        ticket = {
            "ticket_id": "T123",
            "subject": "Cannot login",
            "description": "Getting error when logging in",
            "customer_email": "test@example.com",
        }

        result = customer_service_workflow(ticket, config)

        assert result is not None
        assert "triage" in result
        assert "knowledge" in result
        assert "response" in result
        assert "routing" in result

    def test_batch_ticket_processing(self):
        """Test processing multiple tickets."""

        config = CustomerServiceConfig(llm_provider="mock")

        tickets = [
            {
                "ticket_id": "T1",
                "subject": "Login issue",
                "description": "Cannot login",
            },
            {
                "ticket_id": "T2",
                "subject": "Payment failed",
                "description": "Card declined",
            },
            {
                "ticket_id": "T3",
                "subject": "Feature request",
                "description": "Need new feature",
            },
        ]

        results = batch_ticket_processing(tickets, config)

        assert results is not None
        assert len(results) == 3
        assert all("response" in r for r in results)

    def test_priority_ticket_handling(self):
        """Test handling of high-priority tickets."""

        config = CustomerServiceConfig(llm_provider="mock")

        ticket = {
            "ticket_id": "T999",
            "subject": "URGENT: System down",
            "description": "Critical system outage",
            "priority": "critical",
        }

        result = customer_service_workflow(ticket, config)

        assert result is not None


class TestSharedMemoryIntegration:
    """Test shared memory usage in customer service pipeline."""

    def test_triage_writes_to_shared_memory(self):
        """Test TicketTriageAgent writes triage results to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = CustomerServiceConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = TicketTriageAgent(config, shared_pool, "triage")

        ticket = {"ticket_id": "T123", "subject": "Test"}
        agent.triage(ticket)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="search", tags=["triage"], segments=["pipeline"]
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "triage"

    def test_knowledge_search_reads_from_shared_memory(self):
        """Test KnowledgeSearchAgent reads triage from shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = CustomerServiceConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        triage_agent = TicketTriageAgent(config, shared_pool, "triage")
        KnowledgeSearchAgent(config, shared_pool, "search")

        # Triage writes
        ticket = {"ticket_id": "T123", "subject": "Test"}
        triage_agent.triage(ticket)

        # Search reads
        insights = shared_pool.read_relevant(
            agent_id="search", tags=["triage"], segments=["pipeline"]
        )

        assert len(insights) > 0

    def test_pipeline_coordination_via_shared_memory(self):
        """Test full pipeline coordination via shared memory."""

        config = CustomerServiceConfig(llm_provider="mock")

        ticket = {"ticket_id": "T123", "subject": "Test ticket"}

        result = customer_service_workflow(ticket, config)

        # All stages should complete
        assert "triage" in result
        assert "knowledge" in result
        assert "response" in result
        assert "routing" in result


class TestEnterpriseFeatures:
    """Test enterprise-specific features."""

    def test_multi_category_tickets(self):
        """Test handling tickets from multiple categories."""

        config = CustomerServiceConfig(llm_provider="mock")
        agent = TicketTriageAgent(config)

        tickets = [
            {"subject": "Technical issue"},
            {"subject": "Billing question"},
            {"subject": "Feature request"},
            {"subject": "Account access"},
        ]

        for ticket in tickets:
            result = agent.triage(ticket)
            assert "category" in result

    def test_priority_levels(self):
        """Test priority level assignment."""

        config = CustomerServiceConfig(llm_provider="mock")
        agent = TicketTriageAgent(config)

        ticket = {"subject": "URGENT: Critical issue"}

        result = agent.triage(ticket)

        assert "priority" in result

    def test_automated_response_generation(self):
        """Test automated response generation."""

        config = CustomerServiceConfig(llm_provider="mock", auto_response=True)

        agent = ResponseGeneratorAgent(config)
        ticket = {"subject": "How to reset password"}
        knowledge = {"articles": ["Password reset guide"]}

        result = agent.generate_response(ticket, knowledge)

        assert "response" in result

    def test_error_handling_missing_ticket(self):
        """Test error handling for missing ticket data."""

        config = CustomerServiceConfig(llm_provider="mock")

        # Empty ticket
        ticket = {}

        result = customer_service_workflow(ticket, config)

        # Should handle gracefully
        assert result is not None


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = CustomerServiceConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.auto_response is True

    def test_custom_config(self):
        """Test custom configuration."""

        config = CustomerServiceConfig(
            llm_provider="openai",
            model="gpt-4",
            auto_response=True,
            knowledge_base_enabled=True,
            max_articles=5,
            response_tone="professional",
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.auto_response is True
        assert config.knowledge_base_enabled is True

    def test_routing_config(self):
        """Test routing configuration."""

        config = CustomerServiceConfig(
            llm_provider="mock", routing_enabled=True, escalation_threshold="high"
        )

        assert config.routing_enabled is True
        assert config.escalation_threshold == "high"
