# Infrastructure Integration Tests

This directory contains integration tests that verify infrastructure components work correctly with the Kailash SDK.

## Test Categories

### Docker Infrastructure
- Database connection tests
- Cache service tests
- Message queue tests
- Service health checks

### Connection Management
- Connection pool tests
- Circuit breaker tests
- Retry mechanism tests
- Failover tests

### Service Discovery
- Service registration tests
- Health check tests
- Load balancing tests

## Running Tests

```bash
# All infrastructure tests
pytest tests/integration/infrastructure/ -m integration

# Database-specific tests
pytest tests/integration/infrastructure/ -m requires_postgres

# Cache-specific tests
pytest tests/integration/infrastructure/ -m requires_redis
```
