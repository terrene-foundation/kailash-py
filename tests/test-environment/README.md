# Kailash SDK Test Environment

A comprehensive, production-grade test environment for the Kailash SDK that provides all required services in Docker containers. This eliminates the need for manual setup and ensures consistent testing across all environments.

## 🚀 Quick Start

```bash
# Initial setup (downloads models, initializes databases)
./tests/utils/test-env setup

# Start all services
./tests/utils/test-env up

# Run tier 2 tests
./tests/utils/test-env test tier2

# Check service status
./tests/utils/test-env status

# Note: test-env script is located in tests/utils/ with a symlink in project root
```

## 📦 Included Services

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL 15 | 5434 | Primary database with pgvector, admin schema |
| MySQL 8.0 | 3307 | Multi-database testing |
| Redis 7 | 6380 | Caching, session management |
| Ollama | 11435 | Local LLM for testing (no API costs) |
| MongoDB 6 | 27017 | Document store testing |
| Qdrant | 6333 | Vector database for embeddings |
| MinIO | 9000/9001 | S3-compatible storage |
| Kafka | 9092 | Event streaming |
| Elasticsearch | 9200 | Search and analytics |
| Jaeger | 16686/4317 | Distributed tracing (UI/OTLP) for AI agents |
| Kubernetes (kind) | 6443 | K8s testing with NodePort 30080/30443 |
| OAuth2 Mock | 8080 | Authentication testing |
| Adminer | 8090 | Database management UI |
| Health Dashboard | 8091 | Service status monitoring |

## 🛠️ Commands

### Service Management
```bash
./tests/utils/test-env up       # Start all services
./tests/utils/test-env down     # Stop all services
./tests/utils/test-env restart  # Restart all services
./tests/utils/test-env status   # Show service status
./tests/utils/test-env logs     # View service logs
./tests/utils/test-env logs -f  # Follow service logs
```

### Running Tests
```bash
./tests/utils/test-env test tier1              # Run unit tests
./tests/utils/test-env test tier2              # Run integration tests
./tests/utils/test-env test tier3              # Run e2e tests
./tests/utils/test-env test all                # Run all tests
./tests/utils/test-env test tests/specific.py  # Run specific test file
```

### Maintenance
```bash
./tests/utils/test-env setup   # Initial setup with model downloads
./tests/utils/test-env clean   # Remove all data and volumes (⚠️ destructive)
```

## 🔧 Configuration

### Environment Variables
The test environment automatically sets these when running tests:
```bash
POSTGRES_TEST_URL=postgresql://test_user:test_password@localhost:5434/kailash_test
MYSQL_TEST_URL=mysql://kailash_test:test_password@localhost:3307/kailash_test
REDIS_TEST_URL=redis://localhost:6380
OLLAMA_TEST_URL=http://localhost:11435
MONGODB_URL=mongodb://kailash:kailash123@localhost:27017
QDRANT_URL=http://localhost:6333
JAEGER_ENDPOINT=http://localhost:4317
JAEGER_UI=http://localhost:16686
MINIO_ENDPOINT=localhost:9000
TEST_DOCKER_AVAILABLE=true
```

### Pre-configured Data
- Admin schema with users, roles, and permissions
- Sample products and orders for data node testing
- Test metrics data for time series analysis
- Vector embeddings table for RAG testing

### Available Ollama Models
The setup script pulls `llama3.2:1b` by default. To add more models:
```bash
docker exec kailash_sdk_test_ollama ollama pull <model-name>
```

## 📊 Monitoring

### Health Dashboard
Access the health check dashboard at http://localhost:8091 to monitor all services.

### Database Management
Use Adminer at http://localhost:8090 to manage databases:
- Server: `test-postgres` or `test-mysql`
- Username: `test_user` / `kailash_test`
- Password: `test_password`

### MinIO Console
Access object storage at http://localhost:9001:
- Username: `test_admin`
- Password: `test_password_123`

## 🧪 Writing Tests

### Using Docker Services in Tests
```python
from tests.utils.docker_config import (
    get_postgres_connection_string,
    ensure_docker_services
)

@pytest.mark.integration
@pytest.mark.requires_docker
async def test_with_real_database():
    # Ensure services are running
    if not await ensure_docker_services():
        pytest.skip("Docker services not available")

    # Use real connection string
    db_config = {
        "connection_string": get_postgres_connection_string()
    }
```

### Test Organization
- **Tier 1 (Unit)**: No Docker dependencies, mocked external services
- **Tier 2 (Integration)**: Real Docker services, component interaction
- **Tier 3 (E2E)**: Full end-to-end scenarios with all services

## 🔍 Troubleshooting

### Services Won't Start
```bash
# Check Docker is running
docker info

# Check port conflicts
lsof -i :5434  # PostgreSQL
lsof -i :6380  # Redis
# etc...

# Clean restart
./test-env clean
./test-env setup
```

### Database Connection Issues
```bash
# Check service health
./test-env status

# View service logs
./test-env logs test-postgres
./test-env logs test-mysql
```

### Ollama Model Issues
```bash
# List available models
docker exec kailash_sdk_test_ollama ollama list

# Pull a model manually
docker exec kailash_sdk_test_ollama ollama pull llama3.2:1b
```

### Clean Slate
```bash
# Remove everything and start fresh
./test-env clean
./test-env setup
```

## 🏗️ Architecture

### Directory Structure
```
tests/test-environment/
├── docker-compose.yml       # Service definitions
├── init-scripts/           # Database initialization
│   ├── 01-create-extensions.sql
│   ├── 02-admin-schema.sql
│   └── 03-sample-data.sql
├── healthcheck/            # Health monitoring
│   ├── index.html
│   └── nginx.conf
└── README.md              # This file
```

### Project Name
All containers use the project name `kailash_sdk` for consistency across the SDK and all app frameworks.

### Network
All services run on the `kailash_test_network` bridge network for inter-service communication.

### Container Names
All containers are prefixed with `kailash_sdk_test_`:
- `kailash_sdk_test_postgres`
- `kailash_sdk_test_redis`
- `kailash_sdk_test_mysql`
- `kailash_sdk_test_mongodb`
- `kailash_sdk_test_ollama`
- `kailash_sdk_test_kafka`
- `kailash_sdk_test_zookeeper`
- `kailash_sdk_test_elasticsearch`
- `kailash_sdk_test_qdrant`
- `kailash_sdk_test_minio`
- `kailash_sdk_test_kubernetes`
- `kailash_sdk_test_jaeger`
- `kailash_sdk_test_oauth2`
- `kailash_sdk_test_adminer`
- `kailash_sdk_test_healthcheck`

### Volumes
Persistent volumes with `kailash_sdk_` prefix ensure data survives container restarts:
- `kailash_sdk_postgres_test_data`
- `kailash_sdk_mysql_test_data`
- `kailash_sdk_mongodb_test_data`
- `kailash_sdk_ollama_models`
- `kailash_sdk_qdrant_test_data`
- `kailash_sdk_minio_test_data`
- `kailash_sdk_elasticsearch_data`
- `kailash_sdk_kubernetes_data`
- `kailash_sdk_kubernetes_config`

## 🤝 Contributing

When adding new services:
1. Update `docker-compose.yml`
2. Add health checks in `test-env` script
3. Update this README
4. Add any initialization scripts to `init-scripts/`

## 📝 Notes

- All services use test-specific ports to avoid conflicts
- Passwords are intentionally simple for test environments
- The setup is designed for local testing only, not production
- Model downloads may take time on first setup
- Some services may take 30-60 seconds to fully initialize
