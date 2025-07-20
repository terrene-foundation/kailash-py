#!/bin/bash

# 🛑 Stop MCP Platform
# Gracefully stops all services in the centralized deployment

set -e

echo "🛑 Stopping MCP Platform"
echo "=" * 40

# Change to deployment directory
cd "$(dirname "$0")/../docker"

# Stop all services
echo "📋 Stopping services..."
docker-compose down

echo "🧹 Cleaning up..."
echo "  • Containers stopped"
echo "  • Network removed"
echo "  • Volumes preserved"

echo
echo "✅ Platform stopped successfully"
echo
echo "💡 To restart: ./deployment/scripts/start.sh"
echo "💡 To remove data: docker-compose down -v"