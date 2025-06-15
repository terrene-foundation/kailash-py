#!/bin/bash

# Setup script for PostgreSQL and MySQL test databases
# This script starts Docker containers for testing database connectivity

echo "🗄️ Setting up test databases for Kailash SQL Node testing..."

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo "❌ Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Function to wait for database to be ready
wait_for_db() {
    local host=$1
    local port=$2
    local timeout=30
    local count=0

    echo "⏳ Waiting for database at $host:$port to be ready..."

    while [ $count -lt $timeout ]; do
        if nc -z $host $port 2>/dev/null; then
            echo "✅ Database is ready!"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done

    echo "❌ Timeout waiting for database at $host:$port"
    return 1
}

# Check Docker availability
check_docker

echo "🐘 Starting PostgreSQL test database..."

# Stop and remove existing PostgreSQL container if it exists
docker stop test-postgres 2>/dev/null || true
docker rm test-postgres 2>/dev/null || true

# Start PostgreSQL container on port 5433 (to avoid conflicts)
docker run --name test-postgres \
    -e POSTGRES_PASSWORD=password \
    -e POSTGRES_DB=test \
    -p 5433:5432 \
    -d postgres:15

# Wait for PostgreSQL to be ready
if wait_for_db localhost 5433; then
    echo "✅ PostgreSQL test database is running"
    echo "   Connection: postgresql://postgres:password@localhost:5433/test"
else
    echo "❌ Failed to start PostgreSQL"
fi

echo ""
echo "🐬 Starting MySQL test database..."

# Stop and remove existing MySQL container if it exists
docker stop test-mysql 2>/dev/null || true
docker rm test-mysql 2>/dev/null || true

# Start MySQL container on port 3307 (to avoid conflicts)
docker run --name test-mysql \
    -e MYSQL_ROOT_PASSWORD=password \
    -e MYSQL_DATABASE=test \
    -e MYSQL_USER=test \
    -e MYSQL_PASSWORD=test \
    -p 3307:3306 \
    -d mysql:8.0

# Wait for MySQL to be ready
if wait_for_db localhost 3307; then
    echo "✅ MySQL test database is running"
    echo "   Connection: mysql://root:password@localhost:3307/test"
else
    echo "❌ Failed to start MySQL"
fi

echo ""
echo "🎉 Database setup complete!"
echo ""
echo "📋 Available test connections:"
echo "   PostgreSQL: postgresql://postgres:password@localhost:5433/test"
echo "   MySQL:      mysql://root:password@localhost:3307/test"
echo ""
echo "🧪 To run database tests:"
echo "   # Run all database tests (including PostgreSQL/MySQL if available)"
echo "   pytest tests/test_nodes/test_sql_database.py -v"
echo ""
echo "   # Run only SQLite tests"
echo "   pytest tests/test_nodes/test_sql_database.py::TestSQLDatabaseNode -v"
echo ""
echo "   # Run only advanced SQLite tests"
echo "   pytest tests/test_nodes/test_sql_database.py::TestSQLAdvancedFeatures -v"
echo ""
echo "   # Run only PostgreSQL/MySQL tests"
echo "   pytest tests/test_nodes/test_sql_database.py::TestSQLRealDatabaseSupport -v"
echo ""
echo "🛑 To stop test databases:"
echo "   ./scripts/teardown-test-databases.sh"
echo ""
echo "   Or manually:"
echo "   docker stop test-postgres test-mysql"
echo "   docker rm test-postgres test-mysql"
