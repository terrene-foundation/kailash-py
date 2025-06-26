"""End-to-end tests for Kailash SDK.

E2E tests verify complete workflows and user scenarios with real infrastructure.
No mocking allowed - use real Docker services and external APIs.

Test organization:
- tests/e2e/workflows/ - Complete workflow scenarios
- tests/e2e/user_flows/ - Real user journey tests
- tests/e2e/performance/ - Performance and load tests
- tests/e2e/integration/ - Cross-system integration tests

Requirements:
- Real Docker services (PostgreSQL, Redis, Ollama)
- Real external APIs and services
- Comprehensive business scenarios
- Performance validation
- Proper pytest markers: @pytest.mark.e2e, @pytest.mark.requires_docker
"""
