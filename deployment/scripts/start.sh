#!/bin/bash

# 🚀 Centralized Deployment Quick Start
# Starts the entire MCP platform with service discovery

set -e

echo "🚀 Starting MCP Platform with Centralized Deployment"
echo "=" * 60

# Change to deployment directory
cd "$(dirname "$0")/../docker"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "📋 Starting services..."
echo "  • AI Registry (port 8001)"
echo "  • User Management (port 8002)" 
echo "  • Example App (port 8003)"
echo "  • Enterprise Gateway (port 8000)"
echo "  • PostgreSQL (port 5432)"
echo "  • Redis (port 6379)"
echo "  • Grafana (port 3000)"
echo "  • Prometheus (port 9090)"
echo

# Start all services
docker-compose up -d

echo "⏳ Waiting for services to start..."
sleep 15

# Check service health
echo "🔍 Checking service health..."

services=(
    "http://localhost:8000/health:Enterprise Gateway"
    "http://localhost:8001/health:AI Registry"
    "http://localhost:8002/health:User Management"
    "http://localhost:8003/health:Example App"
)

for service in "${services[@]}"; do
    IFS=':' read -r url name <<< "$service"
    if curl -s "$url" > /dev/null; then
        echo "  ✅ $name - Healthy"
    else
        echo "  ❌ $name - Not responding"
    fi
done

echo
echo "🎯 Service Discovery:"
curl -s http://localhost:8000/api/v1/discovery | python3 -m json.tool

echo
echo "🔧 Available Tools:"
curl -s http://localhost:8000/api/v1/tools | python3 -c "
import sys, json
data = json.load(sys.stdin)
for service, tools in data.items():
    if isinstance(tools, list):
        print(f'  📊 {service}: {len(tools)} tools')
        for tool in tools[:2]:  # Show first 2 tools
            print(f'    • {tool.get(\"name\", \"unknown\")}')
    else:
        print(f'  ❌ {service}: {tools}')
"

echo
echo "🌐 Access Points:"
echo "  • Gateway API:        http://localhost:8000"
echo "  • API Documentation:  http://localhost:8000/docs"
echo "  • Service Discovery:  http://localhost:8000/api/v1/discovery"
echo "  • Unified Tools:      http://localhost:8000/api/v1/tools"
echo "  • Grafana Dashboard:  http://localhost:3000 (admin/admin123)"
echo "  • Prometheus Metrics: http://localhost:9090"
echo
echo "✅ Platform is ready! Try the centralized deployment architecture."

# Optional: Show logs
read -p "Show gateway logs? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📊 Gateway Logs:"
    docker logs mcp-enterprise-gateway --tail 20
fi