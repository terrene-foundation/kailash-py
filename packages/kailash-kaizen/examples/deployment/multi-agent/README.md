# Multi-Agent Deployment

Production deployment for coordinating multiple Kaizen agents with shared memory.

## Architecture

This deployment demonstrates:
- Supervisor-Worker pattern
- Shared memory using Redis
- Scalable worker agents
- Inter-agent coordination
- Container networking

## Services

### Redis
- Shared memory store for all agents
- Persistent storage with AOF
- Health checks enabled

### Supervisor Agent
- Coordinates worker agents
- Assigns tasks
- Monitors progress
- 1-2 CPU cores, 512MB-1GB memory

### Worker Agents
- Execute assigned tasks
- Report results to supervisor
- Horizontally scalable (default: 3 replicas)
- 0.5-1 CPU cores, 256MB-512MB memory per worker

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start Services

```bash
docker-compose up -d
```

### 3. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f supervisor
docker-compose logs -f worker
docker-compose logs -f redis
```

### 4. Scale Workers

```bash
docker-compose up -d --scale worker=5
```

### 5. Stop Services

```bash
docker-compose down
```

## Configuration

### Environment Variables

- `KAIZEN_ENV`: Environment (dev/staging/prod)
- `OPENAI_API_KEY`: OpenAI API key
- `REDIS_URL`: Redis connection URL (auto-configured)
- `AGENT_ROLE`: supervisor or worker (auto-set)

### Scaling

Adjust worker count based on workload:

```bash
# 5 workers
docker-compose up -d --scale worker=5

# 10 workers
docker-compose up -d --scale worker=10
```

## Monitoring

### Service Health

```bash
docker-compose ps
```

### Redis Monitoring

```bash
docker-compose exec redis redis-cli INFO
docker-compose exec redis redis-cli MONITOR
```

### Resource Usage

```bash
docker stats
```

## Production Considerations

### High Availability

1. Use Redis Cluster for HA
2. Deploy multiple supervisors with leader election
3. Add load balancer for API access

### Security

1. Enable Redis authentication
2. Use TLS for Redis connections
3. Network isolation with firewall rules
4. Secrets management with Vault

### Performance

1. Monitor Redis memory usage
2. Tune worker count based on CPU/memory
3. Add caching layer for frequent queries
4. Implement request queuing

## Troubleshooting

### Workers Not Connecting

Check Redis health:
```bash
docker-compose exec redis redis-cli ping
```

Check network:
```bash
docker network inspect kaizen-network
```

### Memory Issues

Monitor Redis memory:
```bash
docker-compose exec redis redis-cli INFO memory
```

Increase limits in docker-compose.yml:
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

### Scaling Issues

Check available resources:
```bash
docker system df
docker system prune
```

## Next Steps

- Add API gateway for external access
- Implement message queue (RabbitMQ/Kafka)
- Add PostgreSQL for persistence
- Deploy to Kubernetes for orchestration
- Add Prometheus metrics
- Add Grafana dashboards
