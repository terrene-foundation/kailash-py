#!/bin/bash
#
# Quick Validation Script for DataFlow
#
# This script provides fast feedback during development by running
# only the most critical tests that protect core functionality.
#
# Target execution time: < 30 seconds
#
# Usage: ./tests/regression/quick_validation.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TIMEOUT=30

echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}DataFlow Quick Validation${NC}"
echo -e "${BLUE}===========================================${NC}"
echo "Started at: $(date)"
echo "Project root: $PROJECT_ROOT"
echo "Timeout: ${TIMEOUT} seconds"
echo

cd "$PROJECT_ROOT"

# Function to run a command with timeout and capture output
run_with_timeout() {
    local cmd="$1"
    local description="$2"
    local start_time=$(date +%s)

    echo -e "${YELLOW}Running: $description${NC}"
    echo "Command: $cmd"

    if timeout $TIMEOUT bash -c "$cmd"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo -e "${GREEN}✅ PASS${NC} ($duration seconds)"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo -e "${RED}❌ FAIL${NC} ($duration seconds)"
        return 1
    fi
}

# Test counter
TOTAL_TESTS=0
PASSED_TESTS=0

# Test 1: Core functionality validation
echo -e "\n${BLUE}Test 1: Core Functionality Validation${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
if run_with_timeout "python tests/regression/validate_core_functionality.py" "Core functionality validation"; then
    PASSED_TESTS=$((PASSED_TESTS + 1))
fi

# Test 2: Basic example execution
echo -e "\n${BLUE}Test 2: Basic Example Execution${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
if run_with_timeout "python examples/01_basic_crud.py" "Basic CRUD example"; then
    PASSED_TESTS=$((PASSED_TESTS + 1))
fi

# Test 3: Essential unit tests
echo -e "\n${BLUE}Test 3: Essential Unit Tests${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
if run_with_timeout "python -m pytest tests/unit/test_engine_migration_integration.py::TestBasicDataFlowOperations -v --tb=short" "Essential unit tests"; then
    PASSED_TESTS=$((PASSED_TESTS + 1))
fi

# Test 4: Gateway integration (if test exists)
echo -e "\n${BLUE}Test 4: Gateway Integration${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
if run_with_timeout "python -m pytest tests/unit/test_gateway_integration.py::TestBasicGatewayOperations -v --tb=short" "Gateway integration tests"; then
    PASSED_TESTS=$((PASSED_TESTS + 1))
fi

# Test 5: Memory database integration
echo -e "\n${BLUE}Test 5: Memory Database Integration${NC}"
TOTAL_TESTS=$((TOTAL_TESTS + 1))
if [ -f "tests/integration/dataflow_alpha/test_real_database_operations.py" ]; then
    if run_with_timeout "python -m pytest tests/integration/dataflow_alpha/test_real_database_operations.py::test_memory_database_basic_crud -v --tb=short" "Memory database integration"; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
    fi
else
    echo -e "${YELLOW}⚠️  SKIP${NC} (test file not found)"
    # Don't count as failed since it's optional
fi

# Summary
echo
echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}QUICK VALIDATION SUMMARY${NC}"
echo -e "${BLUE}===========================================${NC}"
echo "Completed at: $(date)"
echo "Tests passed: $PASSED_TESTS/$TOTAL_TESTS"

if [ $PASSED_TESTS -eq $TOTAL_TESTS ]; then
    echo -e "${GREEN}🎉 ALL QUICK VALIDATION TESTS PASSED${NC}"
    echo -e "${GREEN}Safe to continue development${NC}"
    exit 0
elif [ $PASSED_TESTS -ge 3 ]; then
    echo -e "${YELLOW}⚠️  SOME TESTS FAILED${NC}"
    echo -e "${YELLOW}Core functionality may be at risk${NC}"
    echo -e "${YELLOW}Review failures and proceed with caution${NC}"
    exit 1
else
    echo -e "${RED}🚨 CRITICAL FAILURES DETECTED${NC}"
    echo -e "${RED}Core functionality is broken!${NC}"
    echo -e "${RED}STOP ALL DEVELOPMENT - Fix immediately${NC}"
    exit 2
fi
