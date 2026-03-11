"""
Memory E2E tests for Kaizen AI Framework.

Tests the 3-tier memory architecture with real infrastructure:
- Hot tier (in-memory cache with LRU eviction)
- Warm tier (Redis persistence - optional)
- Cold tier (PostgreSQL via DataFlow)

Test Coverage:
- Tests 22-23: Hot tier operations and eviction
- Test 24: Warm tier with Redis (skip if unavailable)
- Test 25: Cold tier with PostgreSQL
- Tests 26-28: Persistence across restarts, tier promotion/demotion

All tests use NO MOCKING policy with real infrastructure.
"""
