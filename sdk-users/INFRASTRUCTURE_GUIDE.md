# Kailash SDK Infrastructure Guide

This guide explains how to set up and use the SDK development infrastructure for running examples and tests.

## Quick Start

### 1. Automatic Setup (Recommended)

Run the setup script which will install Docker if needed and start all services:

```bash
./scripts/setup-sdk-environment.sh
```

Choose option 1 for full installation.

### 2. Manual Setup

If you already have Docker installed:

```bash
# Start all services
cd docker
docker compose -f docker-compose.sdk-dev.yml up -d

# Check health
curl http://localhost:8889/health
```

## Services Overview

| Service | Port | Description | Web UI |
|---------|------|-------------|---------|
| PostgreSQL | 5432 | 6 databases for examples | - |
| MongoDB | 27017 | Document storage | http://localhost:8081 |
| Qdrant | 6333 | Vector database | http://localhost:6333/dashboard |
| Kafka | 9092 | Streaming platform | http://localhost:8082 |
| Ollama | 11434 | Local LLM | - |
| Mock API | 8888 | REST endpoints | - |
| MCP Server | 8765 | AI Registry tools | - |

## Database Details

### PostgreSQL Databases
- `transactions` - Financial transaction data
- `compliance` - Compliance reports
- `analytics` - Analytics and metrics
- `crm` - Customer relationship data
- `marketing` - Marketing campaigns
- `reports` - Generated reports

### MongoDB Collections
- `documents` - Unstructured documents
- `events` - Event stream data
- `workflows` - Workflow definitions
- `logs` - Application logs
- `api_responses` - API response cache

## Environment Configuration

The setup creates `/sdk-users/.env.sdk-dev` with all connection strings:

```bash
# Use in your examples
source sdk-users/.env.sdk-dev

# Or set SDK development mode
export SDK_DEV_MODE=true
```

## Running Examples

### With Infrastructure

```bash
# Ensure services are running
docker compose -f docker/docker-compose.sdk-dev.yml ps

# Run examples
python examples/workflow_examples/financial_data_processor_refactored.py
```

### Without Docker (Limited Mode)

```bash
export NO_DOCKER=true
python examples/workflow_examples/financial_processor_minimal.py
```

## Common Operations

### View Logs
```bash
# All services
docker compose -f docker/docker-compose.sdk-dev.yml logs

# Specific service
docker compose -f docker/docker-compose.sdk-dev.yml logs kafka
```

### Access Databases

**PostgreSQL:**
```bash
docker exec -it kailash-sdk-postgres psql -U kailash -d transactions
```

**MongoDB:**
```bash
docker exec -it kailash-sdk-mongodb mongosh -u kailash -p kailash123
```

### Reset Data
```bash
# Stop and remove all data
docker compose -f docker/docker-compose.sdk-dev.yml down -v

# Restart fresh
docker compose -f docker/docker-compose.sdk-dev.yml up -d
```

## Troubleshooting

### Port Conflicts
If you get port binding errors:
```bash
# Check what's using the port
lsof -i :5432  # PostgreSQL
lsof -i :27017 # MongoDB

# Use different ports in .env.sdk-dev
POSTGRES_PORT=5433
```

### Service Not Starting
```bash
# Check service logs
docker compose -f docker/docker-compose.sdk-dev.yml logs [service-name]

# Restart specific service
docker compose -f docker/docker-compose.sdk-dev.yml restart [service-name]
```

### Ollama Model Download
First run downloads a small model (llama3.2:1b):
```bash
# Check download progress
docker logs kailash-sdk-ollama -f

# Manually pull models
docker exec -it kailash-sdk-ollama ollama pull llama3.2:1b
```

## Integration with Tests

Tests automatically use SDK infrastructure when available:

```bash
# Run all tests with infrastructure
SDK_DEV_MODE=true pytest tests/

# Run specific infrastructure tests
pytest tests/integration/ -m "requires_infrastructure"
```

## Mock API Endpoints

The mock API server provides these endpoints for examples:

- `GET /health` - Health check
- `GET /transactions/pending` - Pending transactions
- `POST /alerts` - Create fraud alert
- `POST /send` - Send notification
- `POST /enrichment` - Enrich lead data
- `POST /webhook` - Generic webhook

## Data Persistence

All data is persisted in named Docker volumes:
- `kailash_sdk_postgres_data`
- `kailash_sdk_mongo_data`
- `kailash_sdk_qdrant_data`
- `kailash_sdk_kafka_data`
- `kailash_sdk_ollama_models`

To backup:
```bash
# Backup PostgreSQL
docker exec kailash-sdk-postgres pg_dumpall -U kailash > backup.sql

# Backup MongoDB
docker exec kailash-sdk-mongodb mongodump --out /backup
```

## Production Considerations

This infrastructure is for **development only**. For production:
- Use managed database services
- Configure proper authentication
- Set up monitoring and backups
- Use production-grade message queues
- Deploy behind load balancers

## Getting Help

- Check service logs: `docker compose logs [service]`
- Health status: `curl http://localhost:8889/health`
- Reset everything: `./scripts/setup-sdk-environment.sh` (option 6)
- See alternative setup: [INFRASTRUCTURE_NO_DOCKER.md](INFRASTRUCTURE_NO_DOCKER.md)
