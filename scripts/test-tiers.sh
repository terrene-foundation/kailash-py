#!/bin/bash
# Test tier execution script for Kailash SDK
# This script helps developers run the correct test tier

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default to tier 1
TIER=${1:-1}

echo -e "${GREEN}🧪 Kailash SDK Test Runner${NC}"
echo "================================"

case $TIER in
  1)
    echo -e "${YELLOW}Running Tier 1 (Unit Tests)${NC}"
    echo "Fast, isolated tests with no external dependencies"
    echo ""
    pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker or requires_postgres or requires_mysql or requires_ollama)" -v --tb=short --maxfail=5
    ;;

  2)
    echo -e "${YELLOW}Running Tier 2 (Integration Tests)${NC}"
    echo "Component interaction tests (may require Docker services)"
    echo ""

    # Check if Docker services are available
    if [ -n "$POSTGRES_TEST_URL" ] || [ -n "$MYSQL_TEST_URL" ] || [ -n "$OLLAMA_TEST_URL" ]; then
      echo "✅ External services configured"
    else
      echo "⚠️  No external services configured. Some tests may be skipped."
      echo "   To run all integration tests, set:"
      echo "   export POSTGRES_TEST_URL='postgresql://test_user:test_password@localhost:5434/kailash_test'"
      echo "   export MYSQL_TEST_URL='mysql+pymysql://root:test_password@localhost:3307/kailash_test'"
      echo "   export OLLAMA_TEST_URL='http://localhost:11435'"
    fi
    echo ""
    pytest tests/integration/ -m "integration" -v --tb=short
    ;;

  3)
    echo -e "${YELLOW}Running Tier 3 (E2E Tests)${NC}"
    echo "Full end-to-end scenarios with Docker infrastructure"
    echo ""
    pytest tests/e2e/ -m "e2e" -v --tb=short
    ;;

  all)
    echo -e "${YELLOW}Running All Tests${NC}"
    echo "Complete test suite (may take 45-60 minutes)"
    echo ""
    pytest -v
    ;;

  fast)
    echo -e "${YELLOW}Running Fast Tests Only${NC}"
    echo "All tests except those marked as slow"
    echo ""
    pytest -m "not slow" -v --maxfail=10
    ;;

  critical)
    echo -e "${YELLOW}Running Critical Path Tests${NC}"
    echo "Core functionality that must never break"
    echo ""
    pytest -m "critical" -v --maxfail=1
    ;;

  *)
    echo -e "${RED}Invalid tier: $TIER${NC}"
    echo ""
    echo "Usage: $0 [tier]"
    echo ""
    echo "Tiers:"
    echo "  1    - Unit tests (default, fast, no external deps)"
    echo "  2    - Integration tests (component interactions)"
    echo "  3    - E2E tests (full scenarios)"
    echo "  all  - All tests"
    echo "  fast - All non-slow tests"
    echo "  critical - Critical path only"
    exit 1
    ;;
esac

echo ""
echo "✅ Test run complete!"
