# E2E Business Scenarios

This directory contains end-to-end tests that validate complete business scenarios using real infrastructure.

## Scenario Categories

### Data Processing Pipelines
- ETL workflows with real data sources
- Stream processing scenarios
- Batch processing workflows
- Data quality validation

### AI/ML Workflows
- LLM-powered analysis pipelines
- Embedding generation and search
- Multi-model orchestration
- Real-time inference scenarios

### Enterprise Workflows
- Multi-tenant data processing
- Compliance and audit workflows
- Security policy enforcement
- Performance optimization scenarios

## Test Structure

Each scenario should:
1. Use real infrastructure (PostgreSQL, Redis, Ollama)
2. Process realistic data volumes
3. Validate business outcomes
4. Measure performance metrics
5. Test error conditions

## Running Scenarios

```bash
# All business scenarios
pytest tests/e2e/scenarios/ -m e2e

# AI-specific scenarios
pytest tests/e2e/scenarios/ -m requires_ollama

# Performance scenarios
pytest tests/e2e/scenarios/ -m performance
```
