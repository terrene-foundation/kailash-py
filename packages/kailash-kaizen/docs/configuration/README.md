# Configuration Guide

## Environment Variables

### Required
- `KAIZEN_ENV` - Environment name (dev/staging/prod)
- `LOG_LEVEL` - Logging level (DEBUG/INFO/WARNING/ERROR)

### LLM Provider API Keys (at least one required)
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `PERPLEXITY_API_KEY` - Perplexity AI API key (web search with citations)
- `GOOGLE_API_KEY` or `GEMINI_API_KEY` - Google Gemini API key
- `AZURE_AI_INFERENCE_ENDPOINT` + `AZURE_AI_INFERENCE_API_KEY` - Azure AI Foundry

### Optional
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `MAX_WORKERS` - Number of worker threads (default: 4)
- `TIMEOUT` - Request timeout in seconds (default: 30)
- `KAIZEN_DEFAULT_PROVIDER` - Override auto-detection (openai/anthropic/perplexity/google/ollama/docker)
- `KAIZEN_PERPLEXITY_MODEL` - Default Perplexity model (default: sonar)

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
