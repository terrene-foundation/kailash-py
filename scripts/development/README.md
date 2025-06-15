# Development Environment Scripts

Scripts for setting up, managing, and monitoring the Kailash SDK development environment.

## 📁 Scripts Overview

| Script | Purpose | Usage |
|--------|---------|-------|
| `setup-environment.sh` | Complete SDK environment setup with Docker | `./setup-environment.sh` |
| `start-development.sh` | Start all development services | `./start-development.sh` |
| `stop-development.sh` | Stop all development services | `./stop-development.sh` |
| `reset-development.sh` | Reset environment (clear data) | `./reset-development.sh` |
| `check-status.sh` | Check environment health status | `./check-status.sh` |
| `setup-databases.sh` | Setup test databases only | `./setup-databases.sh` |

## 🚀 Quick Start

### First Time Setup
```bash
# Run interactive setup (recommended)
./setup-environment.sh

# Choose option 1 for full installation
# This will install Docker if needed and setup all services
```

### Daily Development
```bash
# Start development environment
./start-development.sh

# Check if everything is running
./check-status.sh

# Work on your features...

# Stop when done
./stop-development.sh
```

## 📋 Detailed Script Documentation

### `setup-environment.sh`
**Purpose**: Interactive setup wizard for complete development environment

**Features**:
- Detects OS (macOS, Linux, Windows)
- Installs Docker if not present
- Creates environment configuration
- Starts all required services
- Validates service health

**Menu Options**:
1. **Full Setup** - Install Docker + setup services (recommended)
2. **Check Only** - See what's installed without changes
3. **No Docker** - Show alternative setup guide
4. **Start Services** - Start services if Docker exists
5. **Stop Services** - Stop all services
6. **Reset Services** - Reset with clean data

**Requirements**:
- Admin/sudo access (for Docker installation)
- Internet connection
- 4GB+ available RAM

### `start-development.sh`
**Purpose**: Start all SDK development services

**Services Started**:
- PostgreSQL (localhost:5432)
- MongoDB (localhost:27017)
- Qdrant Vector DB (localhost:6333)
- Kafka (localhost:9092)
- Ollama LLM (localhost:11434)
- Mock API Server (localhost:8888)
- MCP Server (localhost:8765)

**Health Checks**:
- Automatic service health validation
- Service availability confirmation
- Port conflict detection

### `stop-development.sh`
**Purpose**: Gracefully stop all development services

**Features**:
- Preserves data volumes
- Clean shutdown sequence
- Status confirmation

### `reset-development.sh`
**Purpose**: Reset development environment with clean data

**⚠️ WARNING**: This will delete ALL development data including:
- Database contents
- Vector embeddings
- Kafka topics
- File uploads

**Use Cases**:
- Starting fresh after corrupted data
- Testing clean installation scenarios
- Clearing test data before release

### `check-status.sh`
**Purpose**: Comprehensive health check of development environment

**Checks Include**:
- Service running status
- Individual service health endpoints
- Port availability
- Data volume status
- Container resource usage

**Output Example**:
```
SDK Development Environment Status
==================================

Services Status:
kailash-sdk-postgres    Up 2 hours    0.0.0.0:5432->5432/tcp
kailash-sdk-mongodb     Up 2 hours    0.0.0.0:27017->27017/tcp
...

Health Checks:
✓ PostgreSQL is healthy
✓ MongoDB is healthy
✓ Qdrant is healthy
...
```

### `setup-databases.sh`
**Purpose**: Setup only the database components (without full environment)

**Use Cases**:
- CI/CD pipeline database setup
- Minimal development setup
- Database-only testing

**Databases Configured**:
- PostgreSQL with multiple schemas (transactions, compliance, analytics, etc.)
- MongoDB with authentication
- Test data population

## 🔧 Environment Configuration

### Environment Files
The setup creates `.env.sdk-dev` with all service configurations:

```bash
# Key configuration locations
SDK_DEV_MODE=true

# Database URLs
POSTGRES_PASSWORD=kailash123
TRANSACTION_DB=postgresql://kailash:kailash123@localhost:5432/transactions
MONGO_URL=mongodb://kailash:kailash123@localhost:27017/kailash

# Service endpoints
KAFKA_BROKERS=localhost:9092
OLLAMA_HOST=http://localhost:11434
MCP_SERVER_URL=http://localhost:8765
```

### Docker Compose Files
Services are defined in `docker/docker-compose.sdk-dev.yml`

### Data Persistence
Data is stored in Docker volumes:
- `kailash_sdk_postgres_data`
- `kailash_sdk_mongodb_data`
- `kailash_sdk_qdrant_data`
- `kailash_sdk_kafka_data`

## 🌐 Service Access

| Service | URL | Purpose |
|---------|-----|---------|
| PostgreSQL | `localhost:5432` | Main database |
| MongoDB | `localhost:27017` | Document storage |
| MongoDB Express | `http://localhost:8081` | MongoDB web UI |
| Qdrant | `http://localhost:6333` | Vector database |
| Kafka | `localhost:9092` | Message streaming |
| Kafka UI | `http://localhost:8082` | Kafka web UI |
| Ollama | `http://localhost:11434` | Local LLM server |
| Mock API | `http://localhost:8888` | Testing endpoints |
| MCP Server | `http://localhost:8765` | Model Context Protocol |

## 🐛 Troubleshooting

### Common Issues

**Docker not starting**
```bash
# Check Docker status
docker info

# Start Docker Desktop (macOS)
open -a Docker

# Start Docker service (Linux)
sudo systemctl start docker
```

**Port conflicts**
```bash
# Check what's using a port
lsof -i :5432

# Stop conflicting services
brew services stop postgresql
```

**Services unhealthy**
```bash
# Check logs
docker compose -f docker/docker-compose.sdk-dev.yml logs

# Restart specific service
docker compose -f docker/docker-compose.sdk-dev.yml restart postgres
```

**Permission errors**
```bash
# Fix Docker permissions (Linux)
sudo usermod -aG docker $USER
# Then log out and back in
```

### Performance Issues

**Slow startup**
- Increase Docker memory allocation (4GB minimum)
- Close other memory-intensive applications
- Use SSD storage for better I/O

**High CPU usage**
- Limit Docker CPU usage in Docker Desktop settings
- Consider disabling some services for lighter development

### Verification Steps

**Database connectivity**
```bash
# Test PostgreSQL
psql postgresql://kailash:kailash123@localhost:5432/transactions -c "SELECT 1;"

# Test MongoDB
mongosh mongodb://kailash:kailash123@localhost:27017/kailash --eval "db.runCommand('ping')"
```

**Service health**
```bash
# Test all health endpoints
curl http://localhost:8888/health
curl http://localhost:6333/health
curl http://localhost:11434/api/version
```

## 💡 Best Practices

### Development Workflow
1. **Always check status** before starting work: `./check-status.sh`
2. **Start fresh daily** to catch initialization issues
3. **Monitor logs** for service errors: `docker compose logs -f`
4. **Clean shutdown** to prevent data corruption: `./stop-development.sh`

### Resource Management
- Use `./stop-development.sh` when not developing to save resources
- Periodically reset environment to prevent data bloat: `./reset-development.sh`
- Monitor disk usage: `docker system df`

### Backup Important Data
Before reset operations:
```bash
# Export important data
pg_dump postgresql://kailash:kailash123@localhost:5432/transactions > backup.sql
mongodump --uri mongodb://kailash:kailash123@localhost:27017/kailash
```

## 🤝 Contributing

### Adding New Services
1. Update `docker-compose.sdk-dev.yml`
2. Add health check to `check-status.sh`
3. Update service list in `start-development.sh`
4. Document new service in this README

### Modifying Scripts
- Test changes in isolated environment first
- Ensure backward compatibility
- Update documentation
- Add error handling for new failure modes

---

**Dependencies**: Docker, Docker Compose, curl, PostgreSQL client tools
**Tested On**: macOS (Intel/Apple Silicon), Ubuntu 20.04+, Windows 10+ with WSL2
**Last Updated**: Scripts directory reorganization
