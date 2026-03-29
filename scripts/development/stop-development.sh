#!/bin/bash

# Stop SDK Development Environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Stopping SDK Development Environment..."

cd "$PROJECT_ROOT/docker"

# Stop services (preserve data)
docker compose -f docker-compose.sdk-dev.yml down

echo "✓ Services stopped (data preserved)"
echo
echo "To completely reset (remove all data), run:"
echo "  ./scripts/reset-sdk-dev.sh"
