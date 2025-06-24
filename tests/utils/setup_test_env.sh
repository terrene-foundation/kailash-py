#!/bin/bash
# Setup test environment with real services

set -e

echo "🚀 Setting up Kailash SDK test environment..."

# Start Docker services
echo "📦 Starting Docker services..."
cd docker
docker-compose -f docker-compose.sdk-dev.yml up -d postgres ollama

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until docker exec kailash-sdk-postgres pg_isready -U kailash; do
  echo "Waiting for PostgreSQL..."
  sleep 2
done

# Create test database
echo "🗄️ Creating test database..."
docker exec kailash-sdk-postgres psql -U kailash -c "CREATE DATABASE test_db;" || echo "Database test_db already exists"

# Create pgvector extension
echo "🔧 Setting up pgvector extension..."
docker exec kailash-sdk-postgres psql -U kailash -d test_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Create test tables
echo "📊 Creating test tables..."
docker exec kailash-sdk-postgres psql -U kailash -d test_db <<EOF
-- Create users table for async SQL tests
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert test data
INSERT INTO users (name, email) VALUES
    ('User 1', 'user1@test.com'),
    ('User 2', 'user2@test.com'),
    ('User 3', 'user3@test.com')
ON CONFLICT DO NOTHING;

-- Create embeddings table for vector tests
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(384),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS embeddings_embedding_idx
ON embeddings USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
EOF

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
until curl -f http://localhost:11434/api/version > /dev/null 2>&1; do
  echo "Waiting for Ollama..."
  sleep 2
done

# Pull required model
echo "🤖 Pulling Ollama model..."
docker exec kailash-sdk-ollama ollama pull llama3.2:1b || echo "Model might already be pulled"

cd ..

echo "✅ Test environment is ready!"
echo ""
echo "Database connection strings:"
echo "  PostgreSQL: postgresql://kailash:kailash123@localhost:5432/test_db"
echo "  Ollama: http://localhost:11434"
echo ""
echo "To run tests: pytest tests/test_nodes/test_async_database_integration.py"
echo "To stop services: cd docker && docker-compose -f docker-compose.sdk-dev.yml down"
