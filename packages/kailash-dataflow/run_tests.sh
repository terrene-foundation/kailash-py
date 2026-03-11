#!/bin/bash
# Run DataFlow tests using the test environment

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}DataFlow Test Runner${NC}"
echo "===================="

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from packages/kailash-dataflow directory${NC}"
    exit 1
fi

# Navigate to project root for test-env
cd ../../../

# Check if test environment script exists
if [ ! -f "./test-env" ]; then
    echo -e "${RED}Error: test-env script not found in project root${NC}"
    exit 1
fi

# Setup test environment
echo -e "${YELLOW}Setting up test environment...${NC}"
./test-env setup

# Start services
echo -e "${YELLOW}Starting test services...${NC}"
./test-env up

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
sleep 5

# Check service status
./test-env status

# Navigate back to DataFlow directory
cd packages/kailash-dataflow

# Run tests based on tier
TIER=${1:-all}

case $TIER in
    unit)
        echo -e "${YELLOW}Running unit tests...${NC}"
        pytest tests/unit -v
        ;;
    integration)
        echo -e "${YELLOW}Running integration tests...${NC}"
        pytest tests/integration -v --tb=short
        ;;
    e2e)
        echo -e "${YELLOW}Running E2E tests...${NC}"
        pytest tests/e2e -v --tb=short
        ;;
    all)
        echo -e "${YELLOW}Running all tests...${NC}"

        echo -e "\n${YELLOW}Unit Tests:${NC}"
        pytest tests/unit -v || true

        echo -e "\n${YELLOW}Integration Tests:${NC}"
        pytest tests/integration -v --tb=short || true

        echo -e "\n${YELLOW}E2E Tests:${NC}"
        pytest tests/e2e -v --tb=short || true
        ;;
    *)
        echo -e "${RED}Invalid tier: $TIER${NC}"
        echo "Usage: ./run_tests.sh [unit|integration|e2e|all]"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Test run complete!${NC}"

# Optional: Stop services
read -p "Stop test services? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd ../../../
    ./test-env down
fi
