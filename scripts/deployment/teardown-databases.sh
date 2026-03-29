#!/bin/bash

# Teardown script for PostgreSQL and MySQL test databases
# This script stops and removes Docker containers used for testing database connectivity

echo "🧹 Tearing down test databases..."

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo "❌ Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Function to stop and remove container if it exists
remove_container() {
    local container_name=$1
    local display_name=$2

    echo "🛑 Stopping $display_name container..."

    if docker stop "$container_name" 2>/dev/null; then
        echo "✅ $display_name container stopped"
    else
        echo "ℹ️  $display_name container was not running"
    fi

    if docker rm "$container_name" 2>/dev/null; then
        echo "🗑️  $display_name container removed"
    else
        echo "ℹ️  $display_name container was already removed"
    fi
}

# Check Docker availability
check_docker

# Remove PostgreSQL test container
remove_container "test-postgres" "PostgreSQL"

echo ""

# Remove MySQL test container
remove_container "test-mysql" "MySQL"

echo ""
echo "🎉 Test database teardown complete!"
echo ""
echo "📋 Containers removed:"
echo "   ❌ test-postgres (PostgreSQL)"
echo "   ❌ test-mysql (MySQL)"
echo ""
echo "💡 To set up test databases again:"
echo "   ./scripts/setup-test-databases.sh"
echo ""
echo "🧪 To run database tests with SQLite only:"
echo "   pytest tests/test_nodes/test_sql_database.py::TestSQLDatabaseNode -v"
echo "   pytest tests/test_nodes/test_sql_database.py::TestSQLAdvancedFeatures -v"
