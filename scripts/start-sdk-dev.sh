#!/bin/bash

# Start SDK Development Environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Starting SDK Development Environment..."

cd "$PROJECT_ROOT/docker"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker first."
    exit 1
fi

# Start services
docker compose -f docker-compose.sdk-dev.yml up -d

# Wait for services
echo "Waiting for services to be ready..."
sleep 10

# Check health
if curl -s http://localhost:8889/health >/dev/null 2>&1; then
    echo "✓ All services are healthy"
    echo
    echo "Services available at:"
    echo "  PostgreSQL:      localhost:5432"
    echo "  MongoDB:         localhost:27017 (UI: http://localhost:8081)"
    echo "  Qdrant:          http://localhost:6333"
    echo "  Kafka:           localhost:9092 (UI: http://localhost:8082)"
    echo "  Ollama:          http://localhost:11434"
    echo "  Mock API:        http://localhost:8888"
    echo "  MCP Server:      http://localhost:8765"
else
    echo "⚠ Some services may still be starting. Check logs with:"
    echo "  docker compose -f docker/docker-compose.sdk-dev.yml logs"
fi