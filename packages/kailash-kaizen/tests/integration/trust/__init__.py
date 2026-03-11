"""
Integration tests for EATP trust module.

EATP Phase 2 Week 8: Integration & E2E Testing

This test suite validates the complete EATP (Enterprise Agent Trust Protocol)
implementation through end-to-end integration tests. These tests use REAL
EATP components with NO MOCKING to ensure production behavior.

Test Suites:
- test_multi_agent_workflow.py: Multi-agent orchestration with trust verification
- test_trust_chain_verification.py: Trust chain creation and propagation
- test_secure_messaging.py: Encrypted messaging and replay protection
- test_policy_enforcement.py: Policy evaluation and enforcement
- test_health_monitoring.py: Health-aware agent selection

Test Intent:
The tests validate that EATP components work together correctly to provide:
1. Secure task delegation between supervisor and worker agents
2. Trust context propagation with capability reduction
3. Cryptographic message signing and verification
4. Policy-based access control for agent actions
5. Health-aware agent selection for reliability

Running Tests:
    # Run all integration tests
    pytest tests/integration/trust/ -v

    # Run specific test suite
    pytest tests/integration/trust/test_multi_agent_workflow.py -v

    # Run with real LLM providers (for AI-related tests)
    USE_REAL_PROVIDERS=true pytest tests/integration/trust/ -v
"""
