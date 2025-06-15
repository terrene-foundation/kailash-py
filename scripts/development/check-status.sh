#!/bin/bash

# Check SDK Development Environment Status

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "SDK Development Environment Status"
echo "=================================="
echo

cd "$PROJECT_ROOT/docker"

# Check if services are running
if docker compose -f docker-compose.sdk-dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -q "kailash-sdk"; then
    echo "Services Status:"
    docker compose -f docker-compose.sdk-dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    echo

    # Check individual service health
    echo "Health Checks:"

    # PostgreSQL
    if docker exec kailash-sdk-postgres pg_isready -U kailash >/dev/null 2>&1; then
        echo "✓ PostgreSQL is healthy"
    else
        echo "✗ PostgreSQL is not responding"
    fi

    # MongoDB
    if docker exec kailash-sdk-mongodb mongosh --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
        echo "✓ MongoDB is healthy"
    else
        echo "✗ MongoDB is not responding"
    fi

    # Qdrant
    if curl -s http://localhost:6333/health >/dev/null 2>&1; then
        echo "✓ Qdrant is healthy"
    else
        echo "✗ Qdrant is not responding"
    fi

    # Kafka
    if docker exec kailash-sdk-kafka kafka-topics --bootstrap-server localhost:9092 --list >/dev/null 2>&1; then
        echo "✓ Kafka is healthy"
    else
        echo "✗ Kafka is not responding"
    fi

    # Ollama
    if curl -s http://localhost:11434/api/version >/dev/null 2>&1; then
        echo "✓ Ollama is healthy"
    else
        echo "✗ Ollama is not responding"
    fi

    # Mock API
    if curl -s http://localhost:8888/health >/dev/null 2>&1; then
        echo "✓ Mock API is healthy"
    else
        echo "✗ Mock API is not responding"
    fi

    # MCP Server
    if curl -s http://localhost:8765/health >/dev/null 2>&1; then
        echo "✓ MCP Server is healthy"
    else
        echo "✗ MCP Server is not responding"
    fi

    echo
    echo "Data Volumes:"
    docker volume ls | grep kailash_sdk | awk '{print "  " $2}'

else
    echo "SDK Development Environment is not running."
    echo
    echo "To start, run:"
    echo "  ./scripts/start-sdk-dev.sh"
fi
