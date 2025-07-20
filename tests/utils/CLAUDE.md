# Kailash Python SDK - Test Infrastructure Setup

## Locked-in Port Configuration

This repository uses the following DEDICATED ports for testing infrastructure:

### Core Test Services (LOCKED-IN)
- **PostgreSQL**: `5434` (kailash_sdk_test_postgres) ✅ ACTIVE
- **Redis**: `6380` (kailash_sdk_test_redis) ✅ ACTIVE
- **Ollama**: `11435` (kailash_sdk_test_ollama)
- **MySQL**: `3307` (kailash_sdk_test_mysql)
- **MongoDB**: `27017` (kailash_sdk_test_mongodb)
- **Kubernetes**: `6443` (kailash_sdk_test_kubernetes) 🚀 NEW

## Docker Compose Configuration

### Primary Test Stack (docker-compose.test.yml)
Location: `tests/utils/docker-compose.test.yml`

```bash
# Start all test services
docker-compose -f tests/utils/docker-compose.test.yml up -d

# Check service health
docker-compose -f tests/utils/docker-compose.test.yml ps

# Stop all test services
docker-compose -f tests/utils/docker-compose.test.yml down
```

## Environment Configuration

### Test Environment Variables (PRIMARY)
```bash
# PostgreSQL
export DB_HOST=localhost
export DB_PORT=5434
export DB_NAME=kailash_test
export DB_USER=test_user
export DB_PASSWORD=test_password

# Redis
export REDIS_HOST=localhost
export REDIS_PORT=6380

# Ollama
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11435
export OLLAMA_BASE_URL=http://localhost:11435

# MySQL
export MYSQL_HOST=localhost
export MYSQL_PORT=3307
export MYSQL_DATABASE=kailash_test
export MYSQL_USER=kailash_test
export MYSQL_PASSWORD=test_password

# MongoDB
export MONGO_HOST=localhost
export MONGO_PORT=27017
export MONGO_USER=kailash
export MONGO_PASSWORD=kailash123

# Kubernetes (kind)
export KUBERNETES_HOST=localhost
export KUBERNETES_PORT=6443
export KUBERNETES_API_SERVER=https://localhost:6443
export KUBERNETES_NAMESPACE=default
export KUBECONFIG=/tmp/kailash-k8s-kubeconfig
```

## Testing Strategy (3-Tier Approach)

### Tier 1: Unit Tests
```bash
# Command
pytest tests/unit/ -m "not (integration or e2e or requires_docker)"

# Requirements
- No Docker services needed
- Mocking allowed and encouraged
- Fast execution (< 2 minutes)
- Isolated component testing

# Target: ~1,200 tests across 106 files
```

### Tier 2: Integration Tests
```bash
# Command
pytest tests/integration/ -m "not e2e"

# Requirements
- Real Docker services REQUIRED
- NO MOCKING - use real PostgreSQL, Redis, etc.
- Component interaction testing
- Medium execution time (< 10 minutes)

# Target: ~500 tests across 59 files
```

### Tier 3: E2E Tests
```bash
# Command
pytest tests/e2e/

# Requirements
- All Docker services including Ollama
- NO MOCKING - complete real scenarios
- Full workflow testing
- Longer execution time (< 45 minutes)

# Target: ~144 tests across 42 files
```

## Service Health Verification

### Quick Health Check
```bash
# PostgreSQL
psql "postgresql://test_user:test_password@localhost:5434/kailash_test" -c "SELECT 1;"

# Redis
redis-cli -p 6380 ping

# Ollama
curl http://localhost:11435/api/tags

# MySQL
mysql -h localhost -P 3307 -u kailash_test -ptest_password -e "SELECT 1;"
```

### Comprehensive Health Check
```bash
# Run the built-in health checker
python -c "
import asyncio
from tests.utils.docker_config import ensure_docker_services
result = asyncio.run(ensure_docker_services())
print('All services healthy!' if result else 'Service issues detected!')
"

# Check Kubernetes cluster
./tests/utils/test-env kubernetes status
```

## Development Workflow

### 1. Start Test Environment
```bash
# Start core services (PostgreSQL + Redis)
./tests/utils/test-env up

# For Kubernetes tests, also start kind cluster
./tests/utils/test-env kubernetes setup

# For AI tests, also start Ollama
docker-compose -f tests/utils/docker-compose.test.yml up -d ollama

# Wait for health checks
sleep 30
```

### 2. Run Tests Systematically
```bash
# Phase 1: Unit Tests (no Docker needed)
pytest tests/unit/ -v --tb=short --maxfail=5

# Phase 2: Integration Tests (requires PostgreSQL + Redis)
pytest tests/integration/ -v --tb=short --maxfail=5

# Phase 3: E2E Tests (requires all services)
pytest tests/e2e/ -v --tb=short --maxfail=5
```

### 3. Cleanup
```bash
# Stop Docker services but keep volumes
./tests/utils/test-env down

# Stop Kubernetes cluster
./tests/utils/test-env kubernetes stop

# Full cleanup (removes volumes)
./tests/utils/test-env clean
```

## Ollama Configuration

### Required Models for Testing
```bash
# Download essential models
curl -X POST http://localhost:11435/api/pull -d '{"name": "llama3.2:1b"}'
curl -X POST http://localhost:11435/api/pull -d '{"name": "nomic-embed-text"}'

# Verify models
curl http://localhost:11435/api/tags
```

### Models Used in Tests
- **llama3.2:1b**: Fast, small LLM for testing (recommended)
- **nomic-embed-text**: Embedding generation
- **llama2**: Fallback option (larger, slower)

## Repository-Specific Configuration

### Container Names (LOCKED-IN)
- `kailash_sdk_test_postgres`
- `kailash_sdk_test_redis`
- `kailash_sdk_test_ollama`
- `kailash_sdk_test_mysql`
- `kailash_sdk_test_mongodb`
- `kailash-test-control-plane` (kind cluster)

### Network Name
- `kailash_sdk_test_network`

### Volume Names
- `kailash_sdk_postgres_data`
- `kailash_sdk_redis_data`
- `kailash_sdk_ollama_models`
- `kailash_sdk_mysql_data`
- `kailash_sdk_mongodb_data`

## Port Conflict Resolution

### If Ports Are In Use
1. **Check what's using our ports**:
   ```bash
   lsof -i :5434  # PostgreSQL
   lsof -i :6380  # Redis
   lsof -i :11435 # Ollama
   ```

2. **Stop our containers if needed**:
   ```bash
   docker stop kailash_sdk_test_postgres kailash_sdk_test_redis kailash_sdk_test_ollama
   ```

3. **Remove containers if needed**:
   ```bash
   docker rm kailash_sdk_test_postgres kailash_sdk_test_redis kailash_sdk_test_ollama
   ```

### Emergency Port Changes
If we must change ports, update these files:
- `tests/utils/docker_config.py`
- `tests/utils/docker-compose.test.yml`
- This `CLAUDE.md` file

## Data Management

### Initialization Scripts
- PostgreSQL: Loads from `tests/utils/test_data/` if available
- Other services: Clean start

### Persistence Strategy
- **Development**: Keep volumes for faster restarts
- **CI/CD**: Clean volumes for consistent testing
- **Debugging**: Persistent volumes for data inspection

## Testing Policy Compliance

### Unit Tests (tests/unit/)
- ✅ Mocking allowed
- ✅ Fast execution required
- ✅ No Docker dependencies
- ✅ Isolated component testing

### Integration Tests (tests/integration/)
- ❌ NO MOCKING - Real services only
- ✅ Use real PostgreSQL, Redis, MySQL
- ✅ Test component interactions
- ✅ Use docker_config.py configurations

### E2E Tests (tests/e2e/)
- ❌ NO MOCKING - Complete real scenarios
- ✅ Use all Docker services
- ✅ Test full user workflows
- ✅ Include AI/Ollama testing

## Troubleshooting

### Common Issues
1. **Container won't start**: Check port conflicts
2. **Tests fail**: Verify service health first
3. **Slow tests**: Check if Ollama models are downloaded
4. **Connection refused**: Wait for health checks to pass

### Debug Commands
```bash
# Check container logs
docker logs kailash_sdk_test_postgres
docker logs kailash_sdk_test_redis
docker logs kailash_sdk_test_ollama

# Enter containers for debugging
docker exec -it kailash_sdk_test_postgres psql -U test_user -d kailash_test
docker exec -it kailash_sdk_test_redis redis-cli
```

---

**Repository**: kailash_python_sdk
**Last Updated**: 2025-06-30
**Docker Network**: kailash_sdk_test_network
**Status**: LOCKED-IN ✅
