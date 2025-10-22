# Configuration Guide

## Environment Variables

### Required
- `KAIZEN_ENV` - Environment name (dev/staging/prod)
- `LOG_LEVEL` - Logging level (DEBUG/INFO/WARNING/ERROR)
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key

### Optional
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `MAX_WORKERS` - Number of worker threads (default: 4)
- `TIMEOUT` - Request timeout in seconds (default: 30)

## Configuration Files

### Development
File: `config/dev.env`
- Mock providers enabled
- Debug logging
- Relaxed rate limits

### Staging
File: `config/staging.env`
- Real providers with dev keys
- INFO logging
- Production-like settings

### Production
File: `config/prod.env`
- Real providers with prod keys
- WARNING logging
- Strict security settings

## Validation

```bash
# Validate configuration
python scripts/validate_env.py --env prod
```
