#!/bin/bash
#
# Full Regression Test Suite for DataFlow
#
# This script runs comprehensive validation before releases to ensure
# that all critical functionality remains intact and no regressions
# have been introduced.
#
# Target execution time: < 10 minutes
#
# Usage: ./tests/regression/full_regression_suite.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$SCRIPT_DIR/regression_$(date +%Y%m%d_%H%M%S).log"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}DataFlow Full Regression Test Suite${NC}"
echo -e "${BLUE}================================================${NC}"
echo "Started at: $(date)"
echo "Project root: $PROJECT_ROOT"
echo "Log file: $LOG_FILE"
echo

cd "$PROJECT_ROOT"

# Initialize counters
TOTAL_STAGES=0
PASSED_STAGES=0
FAILED_STAGES=()

# Function to run a test stage
run_stage() {
    local stage_name="$1"
    local stage_cmd="$2"
    local timeout="${3:-300}"  # Default 5 minutes
    local required="${4:-true}"

    TOTAL_STAGES=$((TOTAL_STAGES + 1))

    echo -e "\n${CYAN}Stage $TOTAL_STAGES: $stage_name${NC}"
    echo "Command: $stage_cmd"
    echo "Timeout: ${timeout}s"

    local start_time=$(date +%s)

    if timeout $timeout bash -c "$stage_cmd" 2>&1 | tee -a "$LOG_FILE"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo -e "${GREEN}✅ PASS${NC} ($duration seconds)"
        PASSED_STAGES=$((PASSED_STAGES + 1))
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo -e "${RED}❌ FAIL${NC} ($duration seconds)"
        FAILED_STAGES+=("$stage_name")

        if [ "$required" = "true" ]; then
            echo -e "${RED}CRITICAL FAILURE - Aborting regression suite${NC}"
            exit 1
        fi
        return 1
    fi
}

# Stage 1: Core Functionality Validation (CRITICAL)
run_stage \
    "Core Functionality Validation" \
    "python tests/regression/validate_core_functionality.py" \
    60 \
    true

# Stage 2: Basic Examples (CRITICAL)
run_stage \
    "Basic Examples Execution" \
    "python examples/01_basic_crud.py" \
    120 \
    true

# Stage 3: Performance Benchmarks
run_stage \
    "Performance Benchmarks" \
    "python tests/regression/performance_benchmark.py" \
    180 \
    false

# Stage 4: Essential Unit Tests (CRITICAL)
run_stage \
    "Essential Unit Tests" \
    "python -m pytest tests/unit/test_engine_migration_integration.py tests/unit/test_gateway_integration.py tests/unit/test_legacy_api_compatibility.py -v --tb=short" \
    300 \
    true

# Stage 5: Core Unit Test Suite
run_stage \
    "Core Unit Test Suite" \
    "python -m pytest tests/unit/ -x -q --tb=line" \
    600 \
    false

# Stage 6: Integration Tests (Database Operations)
if [ -d "tests/integration/dataflow_alpha" ]; then
    run_stage \
        "DataFlow Alpha Integration Tests" \
        "python -m pytest tests/integration/dataflow_alpha/ -v --tb=short" \
        300 \
        false
fi

# Stage 7: Critical Integration Tests
run_stage \
    "Critical Integration Tests" \
    "python -m pytest tests/integration/test_dataflow_crud_integration.py tests/integration/test_database_operations.py -v --tb=short" \
    300 \
    false

# Stage 8: E2E Smoke Tests
if [ -d "tests/e2e/dataflow" ]; then
    run_stage \
        "E2E Smoke Tests" \
        "python -m pytest tests/e2e/dataflow_alpha/test_complete_user_journey.py::test_basic_user_journey -v --tb=short" \
        180 \
        false
fi

# Stage 9: Documentation Examples
run_stage \
    "Documentation Examples Validation" \
    "python -m pytest tests/e2e/test_documentation_examples.py -v --tb=short" \
    240 \
    false

# Stage 10: Backward Compatibility
if [ -f "test_backward_compatibility.py" ]; then
    run_stage \
        "Backward Compatibility Check" \
        "python test_backward_compatibility.py" \
        120 \
        false
fi

# Stage 11: Package Installation Test
run_stage \
    "Package Installation Validation" \
    "python -c 'import dataflow; db = dataflow.DataFlow(); print(\"Package import successful\")'" \
    30 \
    true

# Stage 12: Memory Leak Check (if available)
if command -v valgrind >/dev/null 2>&1; then
    run_stage \
        "Memory Leak Detection" \
        "valgrind --tool=memcheck --leak-check=full --error-exitcode=1 python tests/regression/validate_core_functionality.py" \
        600 \
        false
fi

# Generate summary report
echo
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}REGRESSION TEST SUITE SUMMARY${NC}"
echo -e "${BLUE}================================================${NC}"
echo "Completed at: $(date)"
echo "Total stages: $TOTAL_STAGES"
echo "Passed stages: $PASSED_STAGES"
echo "Failed stages: $((TOTAL_STAGES - PASSED_STAGES))"
echo "Success rate: $(( PASSED_STAGES * 100 / TOTAL_STAGES ))%"
echo "Log file: $LOG_FILE"

if [ ${#FAILED_STAGES[@]} -gt 0 ]; then
    echo
    echo -e "${YELLOW}Failed stages:${NC}"
    for stage in "${FAILED_STAGES[@]}"; do
        echo "  - $stage"
    done
fi

# Determine overall result
if [ $PASSED_STAGES -eq $TOTAL_STAGES ]; then
    echo
    echo -e "${GREEN}🎉 ALL REGRESSION TESTS PASSED${NC}"
    echo -e "${GREEN}DataFlow is ready for release${NC}"
    exit 0
elif [ $PASSED_STAGES -ge $((TOTAL_STAGES * 80 / 100)) ]; then
    echo
    echo -e "${YELLOW}⚠️  MOST TESTS PASSED${NC}"
    echo -e "${YELLOW}Review failed stages before release${NC}"
    exit 1
else
    echo
    echo -e "${RED}🚨 SIGNIFICANT REGRESSIONS DETECTED${NC}"
    echo -e "${RED}DO NOT RELEASE - Fix issues first${NC}"
    exit 2
fi
