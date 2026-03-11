# Docker Deployment Guide

## Building the Image

```bash
# Build production image
docker build -t kaizen:latest .

# Build with specific version
docker build -t kaizen:v1.0.0 .

# Multi-platform build
docker buildx build --platform linux/amd/64,linux/arm64 -t kaizen:latest .
```

## Running Locally

```bash
# Run with environment variables
docker run -d \
  -p 8080:8080 \
  -p 9090:9090 \
  -e OPENAI_API_KEY=your-key \
  -e KAIZEN_ENV=development \
  kaizen:latest

# Run with env file
docker run -d --env-file .env kaizen:latest
```

## Docker Compose

See `examples/deployment/` for complete Docker Compose examples.
