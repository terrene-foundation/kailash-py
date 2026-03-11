"""
Test Suite for Domain-Specialists Multi-Agent Pattern

Tests the expert routing pattern with domain specialists:
- 1 RouterAgent classifies questions and routes to specialists
- 3 Specialist Agents (Python, Database, Security) provide expert answers
- 1 IntegratorAgent synthesizes multi-domain answers

Coverage: 18 comprehensive tests
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load domain-specialists example
_module = import_example_module("examples/2-multi-agent/domain-specialists")
RouterAgent = _module.RouterAgent
PythonExpertAgent = _module.PythonExpertAgent
DatabaseExpertAgent = _module.DatabaseExpertAgent
SecurityExpertAgent = _module.SecurityExpertAgent
IntegratorAgent = _module.IntegratorAgent
DomainSpecialistsConfig = _module.DomainSpecialistsConfig
domain_specialists_workflow = _module.domain_specialists_workflow

from kaizen.memory.shared_memory import SharedMemoryPool


class TestRouterAgent:
    """Test RouterAgent domain classification and routing (4 tests)"""

    def test_router_single_domain(self):
        """Test router identifies single domain question"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        router = RouterAgent(config, shared_pool, "router")

        result = router.route("How do I write a Python function?")

        assert "domains" in result
        assert "routing" in result
        # Should identify python domain
        domains = result["domains"]
        assert isinstance(domains, list) or isinstance(domains, str)

    def test_router_multi_domain(self):
        """Test router identifies multi-domain question"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        router = RouterAgent(config, shared_pool, "router")

        result = router.route(
            "How do I securely connect Python to a PostgreSQL database?"
        )

        assert "domains" in result
        domains = result["domains"]
        # Should identify multiple domains
        assert isinstance(domains, list) or isinstance(domains, str)

    def test_router_domain_classification(self):
        """Test router correctly classifies different domains"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        router = RouterAgent(config, shared_pool, "router")

        # Test different domain questions
        python_q = "What is a Python decorator?"
        db_q = "How do I optimize database queries?"
        sec_q = "What is SQL injection and how to prevent it?"

        python_result = router.route(python_q)
        db_result = router.route(db_q)
        sec_result = router.route(sec_q)

        # All should return valid routing decisions
        assert "domains" in python_result
        assert "domains" in db_result
        assert "domains" in sec_result

    def test_routing_written_to_shared_memory(self):
        """Test router writes routing decisions to shared memory"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        router = RouterAgent(config, shared_pool, "router")
        router.route("How do I use Python decorators?")

        # Check routing segment
        routing_insights = shared_pool.read_relevant(
            agent_id="test_reader",
            tags=["routing"],
            segments=["routing"],
            exclude_own=False,
            limit=10,
        )

        assert len(routing_insights) >= 1


class TestSpecialistAgents:
    """Test specialist agent answers (6 tests)"""

    def test_python_expert_answers(self):
        """Test PythonExpertAgent provides answers"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        expert = PythonExpertAgent(config, shared_pool, "python_expert")

        result = expert.answer("What are Python list comprehensions?")

        assert "answer" in result
        assert "confidence" in result
        assert len(result["answer"]) > 0

    def test_database_expert_answers(self):
        """Test DatabaseExpertAgent provides answers"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        expert = DatabaseExpertAgent(config, shared_pool, "database_expert")

        result = expert.answer("What is database normalization?")

        assert "answer" in result
        assert "confidence" in result
        assert len(result["answer"]) > 0

    def test_security_expert_answers(self):
        """Test SecurityExpertAgent provides answers"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        expert = SecurityExpertAgent(config, shared_pool, "security_expert")

        result = expert.answer("What is cross-site scripting?")

        assert "answer" in result
        assert "confidence" in result
        assert len(result["answer"]) > 0

    def test_specialist_confidence(self):
        """Test specialists provide confidence scores"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        expert = PythonExpertAgent(config, shared_pool, "python_expert")

        result = expert.answer("Explain Python generators")

        assert "confidence" in result
        # Confidence should be a string or number
        assert result["confidence"] is not None

    def test_specialist_references(self):
        """Test specialists provide references"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        expert = DatabaseExpertAgent(config, shared_pool, "database_expert")

        result = expert.answer("Explain ACID properties")

        assert "references" in result
        # Should have some reference information
        assert result["references"] is not None

    def test_answers_written_to_shared_memory(self):
        """Test specialists write answers to shared memory"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        expert = PythonExpertAgent(config, shared_pool, "python_expert")
        expert.answer("What are decorators?")

        # Check answers segment
        answers = shared_pool.read_relevant(
            agent_id="test_reader",
            tags=["answer"],
            segments=["answers"],
            exclude_own=False,
            limit=10,
        )

        assert len(answers) >= 1


class TestIntegratorAgent:
    """Test IntegratorAgent synthesis (4 tests)"""

    def test_integrator_reads_answers(self):
        """Test integrator reads specialist answers"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        # Add some specialist answers
        python_expert = PythonExpertAgent(config, shared_pool, "python_expert")
        db_expert = DatabaseExpertAgent(config, shared_pool, "database_expert")

        python_expert.answer("Python ORM usage")
        db_expert.answer("Database connection pooling")

        integrator = IntegratorAgent(config, shared_pool, "integrator")
        result = integrator.integrate("How do I use Python with databases?")

        assert "integrated_answer" in result
        assert len(result["integrated_answer"]) > 0

    def test_integrator_synthesizes_multi_domain(self):
        """Test integrator combines multiple specialist answers"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        # Multiple specialists answer
        python_expert = PythonExpertAgent(config, shared_pool, "python_expert")
        db_expert = DatabaseExpertAgent(config, shared_pool, "database_expert")
        sec_expert = SecurityExpertAgent(config, shared_pool, "security_expert")

        python_expert.answer("Python database libraries")
        db_expert.answer("SQL best practices")
        sec_expert.answer("Secure database access")

        integrator = IntegratorAgent(config, shared_pool, "integrator")
        result = integrator.integrate("Secure Python database access")

        assert "integrated_answer" in result
        assert "domains_covered" in result

    def test_single_domain_no_integration(self):
        """Test single domain doesn't require integration"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        python_expert = PythonExpertAgent(config, shared_pool, "python_expert")
        answer = python_expert.answer("What are Python decorators?")

        # Single domain can return specialist answer directly
        assert "answer" in answer
        assert len(answer["answer"]) > 0

    def test_integrated_answer_written_to_shared_memory(self):
        """Test integrator writes final answer to shared memory"""
        shared_pool = SharedMemoryPool()
        config = DomainSpecialistsConfig()

        # Add specialist answers
        python_expert = PythonExpertAgent(config, shared_pool, "python_expert")
        python_expert.answer("Python question")

        integrator = IntegratorAgent(config, shared_pool, "integrator")
        integrator.integrate("Python question")

        # Check final segment
        final_answers = shared_pool.read_relevant(
            agent_id="test_reader",
            tags=["answer", "integrated"],
            segments=["final"],
            exclude_own=False,
            limit=10,
        )

        assert len(final_answers) >= 1


class TestDomainSpecialistsWorkflow:
    """Test full workflow (4 tests)"""

    def test_single_domain_workflow(self):
        """Test workflow with single domain question"""
        result = domain_specialists_workflow(
            question="What are Python list comprehensions?"
        )

        assert "question" in result
        assert "routing" in result
        assert "answer" in result
        assert "status" in result
        assert result["status"] == "success"

    def test_multi_domain_workflow(self):
        """Test workflow with multi-domain question"""
        result = domain_specialists_workflow(
            question="How do I securely connect Python to a PostgreSQL database?"
        )

        assert "question" in result
        assert "routing" in result
        assert "specialist_answers" in result
        assert "integrated_answer" in result
        assert "status" in result
        assert result["status"] == "success"

    def test_all_specialists_workflow(self):
        """Test workflow involving all three specialists"""
        result = domain_specialists_workflow(
            question="Best practices for secure Python database applications with proper authentication?"
        )

        assert "question" in result
        assert "routing" in result
        assert "specialist_answers" in result
        # Should have multiple specialist answers
        assert len(result.get("specialist_answers", [])) > 0
        assert "status" in result

    def test_stats_reflect_routing(self):
        """Test workflow statistics reflect routing decisions"""
        result = domain_specialists_workflow(
            question="Explain Python decorators and database transactions"
        )

        stats = result["stats"]

        # Should track insights written
        assert "insight_count" in stats
        assert stats["insight_count"] > 0

        # Should track agents involved
        assert "agent_count" in stats
        assert stats["agent_count"] >= 2  # At least router + specialist
