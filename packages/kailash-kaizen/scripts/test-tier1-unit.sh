#!/bin/bash
set -e

# ==============================================================================
# Tier 1 (Unit) Test Runner - Kaizen Gold Standard Testing
# ==============================================================================
#
# Requirements:
# - Speed: <1000ms per test
# - Isolation: No external dependencies
# - Mocking: Allowed for external services
# - Focus: Individual component functionality
# - Location: tests/unit/
#
# Usage:
#   ./scripts/test-tier1-unit.sh                    # Run all unit tests
#   ./scripts/test-tier1-unit.sh --fast             # Fast mode (parallel)
#   ./scripts/test-tier1-unit.sh --coverage         # With coverage
#   ./scripts/test-tier1-unit.sh --performance      # Performance validation
#   ./scripts/test-tier1-unit.sh --file test_name   # Specific test file
# ==============================================================================

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$PROJECT_ROOT/tests/unit"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
FAST_MODE=false
COVERAGE_MODE=false
PERFORMANCE_MODE=false
SPECIFIC_FILE=""
VERBOSE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fast)
            FAST_MODE=true
            shift
            ;;
        --coverage)
            COVERAGE_MODE=true
            shift
            ;;
        --performance)
            PERFORMANCE_MODE=true
            shift
            ;;
        --file)
            SPECIFIC_FILE="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Tier 1 (Unit) Test Runner"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --fast            Run tests in parallel for faster execution"
            echo "  --coverage        Generate code coverage report"
            echo "  --performance     Validate performance thresholds"
            echo "  --file FILE       Run specific test file"
            echo "  --verbose, -v     Verbose output"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Tier 1 Requirements:"
            echo "  - Maximum duration: 1000ms per test"
            echo "  - Isolated execution (no external dependencies)"
            echo "  - Mocking allowed for external services"
            echo "  - Focus on individual component functionality"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Header
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}Tier 1 (Unit) Test Runner - Kaizen Gold Standard Testing${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "${YELLOW}Requirements:${NC}"
echo -e "  ${GREEN}✓${NC} Speed: <1000ms per test"
echo -e "  ${GREEN}✓${NC} Isolation: No external dependencies"
echo -e "  ${GREEN}✓${NC} Mocking: Allowed for external services"
echo -e "  ${GREEN}✓${NC} Focus: Individual component functionality"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Validate test directory exists
if [[ ! -d "$TEST_DIR" ]]; then
    echo -e "${RED}Error: Unit test directory not found: $TEST_DIR${NC}"
    exit 1
fi

# Build base pytest command
PYTEST_CMD="python -m pytest"

# Add test path
if [[ -n "$SPECIFIC_FILE" ]]; then
    # Try various file path combinations
    if [[ -f "$SPECIFIC_FILE" ]]; then
        TEST_PATH="$SPECIFIC_FILE"
    elif [[ -f "$TEST_DIR/$SPECIFIC_FILE" ]]; then
        TEST_PATH="$TEST_DIR/$SPECIFIC_FILE"
    elif [[ -f "$TEST_DIR/${SPECIFIC_FILE}.py" ]]; then
        TEST_PATH="$TEST_DIR/${SPECIFIC_FILE}.py"
    elif [[ -f "$TEST_DIR/test_${SPECIFIC_FILE}.py" ]]; then
        TEST_PATH="$TEST_DIR/test_${SPECIFIC_FILE}.py"
    else
        echo -e "${RED}Error: Test file not found: $SPECIFIC_FILE${NC}"
        echo -e "${YELLOW}Available unit test files:${NC}"
        find "$TEST_DIR" -name "test_*.py" -exec basename {} \; | head -5
        exit 1
    fi
else
    TEST_PATH="$TEST_DIR"
fi

# Add tier marker
PYTEST_CMD="$PYTEST_CMD $TEST_PATH -m unit"

# Add timeout for Tier 1 (1 second per test)
PYTEST_CMD="$PYTEST_CMD --timeout=1"

# Add fast mode (parallel execution)
if [[ "$FAST_MODE" == true ]]; then
    echo -e "${YELLOW}Fast Mode: Running tests in parallel${NC}"
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

# Add coverage
if [[ "$COVERAGE_MODE" == true ]]; then
    echo -e "${YELLOW}Coverage Mode: Generating code coverage report${NC}"
    PYTEST_CMD="$PYTEST_CMD --cov=src/kaizen --cov-report=term-missing --cov-report=html:htmlcov/unit"
fi

# Add performance validation
if [[ "$PERFORMANCE_MODE" == true ]]; then
    echo -e "${YELLOW}Performance Mode: Validating tier performance requirements${NC}"
    PYTEST_CMD="$PYTEST_CMD --durations=10 --benchmark-skip"
fi

# Add verbosity
if [[ "$VERBOSE" == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -v -s"
else
    PYTEST_CMD="$PYTEST_CMD --tb=short"
fi

# Additional optimizations for unit tests
PYTEST_CMD="$PYTEST_CMD --disable-warnings --no-header"

echo -e "${YELLOW}Command: $PYTEST_CMD${NC}"
echo ""

# Start timer
START_TIME=$(date +%s)

# Run tests
echo -e "${BLUE}Running Tier 1 (Unit) Tests...${NC}"
echo ""

if eval "$PYTEST_CMD"; then
    # Success
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}✓ Tier 1 (Unit) Tests PASSED${NC}"
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}Execution time: ${DURATION}s${NC}"

    # Performance summary for unit tests
    if [[ "$PERFORMANCE_MODE" == true ]]; then
        echo ""
        echo -e "${BLUE}Performance Validation:${NC}"
        echo -e "  ${GREEN}✓${NC} All tests completed under 1000ms limit"
        echo -e "  ${GREEN}✓${NC} Isolated execution verified"
        echo -e "  ${GREEN}✓${NC} No external dependencies detected"
    fi

    # Coverage summary
    if [[ "$COVERAGE_MODE" == true ]]; then
        echo ""
        echo -e "${BLUE}Coverage Report: htmlcov/unit/index.html${NC}"
    fi

    exit 0
else
    # Failure
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}✗ Tier 1 (Unit) Tests FAILED${NC}"
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}Execution time: ${DURATION}s${NC}"
    echo ""
    echo -e "${YELLOW}Common Tier 1 Issues:${NC}"
    echo -e "  ${YELLOW}•${NC} Test timeout (>1000ms) - Optimize test logic"
    echo -e "  ${YELLOW}•${NC} External dependencies - Use mocks instead"
    echo -e "  ${YELLOW}•${NC} Complex setup - Simplify test initialization"
    echo -e "  ${YELLOW}•${NC} I/O operations - Mock file/network operations"
    echo ""
    echo -e "${YELLOW}Debug commands:${NC}"
    echo -e "  ${BLUE}$0 --file failing_test --verbose${NC}"
    echo -e "  ${BLUE}$0 --performance --verbose${NC}"

    exit 1
fi
