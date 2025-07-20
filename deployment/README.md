# Kailash SDK Template - Deployment

Enterprise-grade deployment infrastructure for Kailash SDK applications, built with Docker and aligned with the test infrastructure.

## 🚀 Quick Start

### Development Environment

```bash
# Setup development environment
./deployment/scripts/setup.sh

# Or with specific options
./deployment/scripts/setup.sh -e development -c

# Access the application
open http://localhost:8000
```

### Production Environment

```bash
# Setup production environment
./deployment/scripts/setup.sh -e production

# Configure environment variables
cp deployment/docker/.env.example deployment/docker/.env.production
# Edit the file with your production values

# Deploy
./deployment/scripts/setup.sh -e production
```

## 📁 Directory Structure

```
deployment/
├── docker/                     # Docker infrastructure
│   ├── Dockerfile              # Multi-stage production Dockerfile
│   ├── docker-compose.development.yml
│   ├── docker-compose.production.yml
│   ├── .env.example            # Environment configuration template
│   ├── init-scripts/           # Database initialization scripts
│   └── config/                 # Service configurations
├── kubernetes/                 # Kubernetes manifests
│   ├── infrastructure/         # Shared services
│   └── apps/                   # Application deployments
├── helm/                       # Helm charts
│   ├── Chart.yaml              # Main chart
│   └── charts/                 # Sub-charts
└── scripts/                    # Deployment automation
    └── setup.sh                # Main setup script
```

## 🏗️ Architecture

### Services

- **app**: Main Kailash SDK application (with DataFlow + Nexus)
- **postgres**: PostgreSQL database with pgvector extension
- **redis**: Redis cache for DataFlow and application caching
- **ollama**: AI service for embeddings and LLM operations
- **traefik**: Reverse proxy and load balancer (production)
- **prometheus**: Metrics collection and monitoring
- **grafana**: Visualization and dashboards

### Ports

**Development:**
- Application: 8000
- PostgreSQL: 5432
- Redis: 6379
- Ollama: 11434
- Adminer: 8080
- Redis Commander: 8081

**Production:**
- HTTP: 80
- HTTPS: 443
- Grafana: 3000
- Prometheus: 9090
- Traefik Dashboard: 8080

## 🔧 Configuration

### Environment Variables

Copy `.env.example` to `.env.development` or `.env.production` and configure:

```bash
# Database
POSTGRES_PASSWORD=your_secure_password

# Security
SECRET_KEY=your_256_bit_secret_key
ENCRYPTION_KEY=your_256_bit_encryption_key
NEXUS_API_KEY=your_nexus_api_key

# Domain (production only)
DOMAIN=your-domain.com
ACME_EMAIL=admin@your-domain.com

# Monitoring
GRAFANA_ADMIN_PASSWORD=your_grafana_password
```

### Application Configuration

The application uses DataFlow for database operations and Nexus for multi-channel access:

- **API**: `http://localhost:8000/workflows/{workflow_name}/execute`
- **CLI**: `nexus run {workflow_name}`
- **MCP**: Available as tools for AI agents

## 📊 Monitoring

### Metrics

- **Application metrics**: Custom business metrics via Prometheus
- **Infrastructure metrics**: CPU, memory, disk usage
- **Database metrics**: Query performance, connection counts
- **Cache metrics**: Redis hit rates, memory usage

### Dashboards

Pre-configured Grafana dashboards:
- Application overview
- Database performance
- Infrastructure health
- Business metrics

## 🔐 Security

### Container Security

- Non-root user in containers
- Multi-stage builds for minimal attack surface
- Resource limits and quotas
- Network policies (Kubernetes)

### Application Security

- Encrypted configuration
- Secure API keys
- CORS configuration
- Basic authentication for admin interfaces

### Database Security

- Encrypted connections
- Role-based access control
- Audit logging
- pgvector extension for vector operations

## 🚀 Deployment Options

### Docker Compose (Recommended for development)

```bash
# Development
docker-compose -f deployment/docker/docker-compose.development.yml up -d

# Production
docker-compose -f deployment/docker/docker-compose.production.yml up -d
```

### Kubernetes (Recommended for production)

```bash
# Apply manifests
kubectl apply -f deployment/kubernetes/

# Check status
kubectl get pods -n template-app
```

## 🔄 Operations

### Health Checks

```bash
# Application health
curl http://localhost:8000/workflows/get_status/execute

# Database health
docker exec template-postgres pg_isready -U app_user

# Redis health
docker exec template-redis redis-cli ping
```

### Scaling

```bash
# Scale application (Docker Compose)
docker-compose -f deployment/docker/docker-compose.production.yml up -d --scale app=3

# Scale application (Kubernetes)
kubectl scale deployment template-app --replicas=3
```

### Logs

```bash
# Application logs
docker logs -f template-app

# All services logs
docker-compose -f deployment/docker/docker-compose.production.yml logs -f

# Kubernetes logs
kubectl logs -f deployment/template-app
```

## 🧪 Testing

### Integration with Test Infrastructure

This deployment aligns with the test infrastructure in `tests/utils/`:

```bash
# Run tests against Docker environment
cd tests
python utils/setup_local_docker.py
pytest integration/ -v

# Run E2E tests
pytest e2e/ -v
```

### Port Alignment

The deployment uses the same port allocation strategy as the test infrastructure:
- Dynamic port allocation based on project name hash
- Conflict detection and resolution
- Consistent port mapping across environments

## 🛠️ Troubleshooting

### Common Issues

1. **Port conflicts**: Use `--custom-base-port` option in setup script
2. **Memory issues**: Ensure at least 4GB RAM available
3. **Database connection**: Check PostgreSQL logs and connection strings
4. **Model loading**: Ollama models may take time to download

### Debug Commands

```bash
# Check service status
docker-compose -f deployment/docker/docker-compose.development.yml ps

# Check logs
docker-compose -f deployment/docker/docker-compose.development.yml logs service-name

# Interactive debugging
docker exec -it template-app bash

# Database debugging
docker exec -it template-postgres psql -U app_user template_dev
```

## 📖 Additional Resources

- [Kailash SDK Documentation](https://docs.kailash.dev)
- [DataFlow Documentation](https://docs.dataflow.dev)
- [Nexus Documentation](https://docs.nexus.dev)
- [Docker Documentation](https://docs.docker.com)
- [Kubernetes Documentation](https://kubernetes.io/docs)

## 🆘 Support

For deployment issues:
1. Check the troubleshooting section above
2. Review logs for specific error messages
3. Ensure all prerequisites are met
4. Verify alignment with test infrastructure

---

**Enterprise-grade deployment for Kailash SDK Template** 🚀