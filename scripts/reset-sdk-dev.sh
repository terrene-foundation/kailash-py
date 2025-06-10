#!/bin/bash

# Reset SDK Development Environment (removes all data)

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "WARNING: This will remove all SDK development data!"
read -p "Are you sure? (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Resetting SDK Development Environment..."
    
    cd "$PROJECT_ROOT/docker"
    
    # Stop services and remove volumes
    docker compose -f docker-compose.sdk-dev.yml down -v
    
    echo "✓ Environment reset complete"
    echo
    echo "To start fresh, run:"
    echo "  ./scripts/start-sdk-dev.sh"
else
    echo "Reset cancelled"
fi