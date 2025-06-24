#!/bin/bash
# Start Docker services using docker-compose

set -e

echo "🐳 Starting Docker test infrastructure..."

# Change to infrastructure directory
cd "$(dirname "$0")/../infrastructure"

# Start services
echo "Starting PostgreSQL, MySQL, Redis, and Ollama..."
docker-compose -f docker-compose.test.yml up -d postgres mysql redis ollama

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 10

# Check PostgreSQL
echo -n "Checking PostgreSQL... "
if docker exec kailash_test_postgres pg_isready -U test_user -d kailash_test >/dev/null 2>&1; then
    echo "✅"
else
    echo "❌"
fi

# Check MySQL
echo -n "Checking MySQL... "
if docker exec kailash_test_mysql mysqladmin ping -h localhost >/dev/null 2>&1; then
    echo "✅"
else
    echo "❌"
fi

# Check Redis
echo -n "Checking Redis... "
if docker exec kailash_test_redis redis-cli ping >/dev/null 2>&1; then
    echo "✅"
else
    echo "❌"
fi

# Check Ollama
echo -n "Checking Ollama... "
if curl -s http://localhost:11435/api/tags >/dev/null 2>&1; then
    echo "✅"
else
    echo "❌"
fi

# Pull Ollama model
echo "Pulling Ollama test model (this may take a few minutes)..."
docker exec kailash_test_ollama ollama pull llama3.2:1b || echo "⚠️  Failed to pull model"

# Export environment variables
echo ""
echo "📝 Add these to your environment:"
echo "export POSTGRES_TEST_URL=postgresql://test_user:test_password@localhost:5434/kailash_test"
echo "export MYSQL_TEST_URL=mysql://kailash_test:test_password@localhost:3307/kailash_test"
echo "export REDIS_TEST_URL=redis://localhost:6380"
echo "export OLLAMA_TEST_URL=http://localhost:11435"
echo "export TEST_DOCKER_AVAILABLE=true"

echo ""
echo "✅ Docker services are ready!"
echo ""
echo "To run the previously skipped tests:"
echo "  pytest tests/unit/ -v -k 'postgres or mysql or docker'"
echo ""
echo "To stop services:"
echo "  cd tests/infrastructure && docker-compose -f docker-compose.test.yml down"
