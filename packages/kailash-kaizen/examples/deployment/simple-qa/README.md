# Simple QA Agent Deployment

Production deployment example for a simple question-answering agent using Kaizen.

## Overview

This deployment demonstrates:
- Containerized Kaizen agent
- Environment-based configuration
- Health checks and monitoring
- Resource limits
- Production logging

## Quick Start

### 1. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. Build and Start

```bash
docker-compose up -d
```

### 3. View Logs

```bash
docker-compose logs -f qa-agent
```

### 4. Stop

```bash
docker-compose down
```

## Configuration

### Environment Variables

- `KAIZEN_ENV`: Environment name (dev/staging/prod)
- `LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `OPENAI_API_KEY`: OpenAI API key for GPT models
- `QA_MODEL`: Model to use (default: gpt-4)
- `QA_TEMPERATURE`: Temperature for responses (0.0-1.0)
- `QA_MAX_TOKENS`: Maximum tokens per response
- `QA_MIN_CONFIDENCE`: Minimum confidence threshold

### Resource Limits

The container is configured with:
- CPU: 1-2 cores
- Memory: 512MB-1GB
- Health checks every 30 seconds

## Monitoring

### Health Checks

The service includes health checks that verify:
- Python runtime is available
- Container is responding

Check health status:

```bash
docker-compose ps
```

### Logs

Logs are configured with rotation:
- Maximum size: 10MB per file
- Maximum files: 3
- Format: JSON

View logs:

```bash
docker-compose logs qa-agent
```

## Production Considerations

### Security

1. Never commit `.env` with real secrets
2. Use environment variables in production
3. Enable SSL/TLS for external access
4. Implement rate limiting

### Scaling

For higher load:

```bash
docker-compose up -d --scale qa-agent=3
```

### Performance

- Adjust CPU/memory limits based on usage
- Monitor response times
- Tune model temperature for accuracy vs speed

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker-compose logs qa-agent
```

Common issues:
- Missing API key
- Invalid configuration
- Resource constraints

### Health Check Failing

Increase health check timeout:
```yaml
healthcheck:
  timeout: 30s
```

### Out of Memory

Increase memory limit:
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

## Next Steps

- Add Redis for caching
- Add PostgreSQL for persistence
- Implement API endpoint
- Add monitoring with Prometheus
- Deploy to Kubernetes

See other deployment examples:
- `multi-agent/`: Multiple coordinating agents
- `rag-agent/`: RAG with vector database
- `mcp-integration/`: MCP server deployment
