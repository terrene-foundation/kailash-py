#!/bin/bash
set -e

# ==============================================================================
# Tier 2 (Integration) Test Runner - Kaizen Gold Standard Testing
# ==============================================================================
#
# Requirements:
# - Speed: <5000ms per test
# - Infrastructure: Real Docker services from tests/utils
# - NO MOCKING: Absolutely forbidden - use real services
# - Focus: Component interactions
# - Location: tests/integration/
#
# CRITICAL Setup Required:
#   ./tests/utils/test-env up && ./tests/utils/test-env status
#
# Usage:
#   ./scripts/test-tier2-integration.sh              # Run all integration tests
#   ./scripts/test-tier2-integration.sh --setup      # Setup infrastructure first
#   ./scripts/test-tier2-integration.sh --check      # Check infrastructure status
#   ./scripts/test-tier2-integration.sh --cleanup    # Cleanup after tests
#   ./scripts/test-tier2-integration.sh --file test  # Specific test file
# ==============================================================================

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$PROJECT_ROOT/tests/integration"
UTILS_DIR="$PROJECT_ROOT/tests/utils"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
SETUP_INFRA=false
CHECK_INFRA=false
CLEANUP_INFRA=false
SPECIFIC_FILE=""
VERBOSE=false
FORCE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --setup)
            SETUP_INFRA=true
            shift
            ;;
        --check)
            CHECK_INFRA=true
            shift
            ;;
        --cleanup)
            CLEANUP_INFRA=true
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
        --force)
            FORCE=true
            shift
            ;;
        --help|-h)
            echo "Tier 2 (Integration) Test Runner"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --setup           Setup infrastructure before running tests"
            echo "  --check           Check infrastructure status only"
            echo "  --cleanup         Cleanup infrastructure after tests"
            echo "  --file FILE       Run specific test file"
            echo "  --verbose, -v     Verbose output"
            echo "  --force           Force run even if infrastructure check fails"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Tier 2 Requirements:"
            echo "  - Maximum duration: 5000ms per test"
            echo "  - Real Docker services required"
            echo "  - NO MOCKING policy enforced"
            echo "  - Infrastructure setup: ./tests/utils/test-env up"
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
echo -e "${BLUE}Tier 2 (Integration) Test Runner - Kaizen Gold Standard Testing${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "${YELLOW}Requirements:${NC}"
echo -e "  ${GREEN}✓${NC} Speed: <5000ms per test"
echo -e "  ${GREEN}✓${NC} Infrastructure: Real Docker services"
echo -e "  ${RED}✗${NC} NO MOCKING: Absolutely forbidden - use real services"
echo -e "  ${GREEN}✓${NC} Focus: Component interactions"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Validate directories exist
if [[ ! -d "$TEST_DIR" ]]; then
    echo -e "${RED}Error: Integration test directory not found: $TEST_DIR${NC}"
    exit 1
fi

if [[ ! -d "$UTILS_DIR" ]]; then
    echo -e "${RED}Error: Test utils directory not found: $UTILS_DIR${NC}"
    echo -e "${RED}Infrastructure setup scripts missing!${NC}"
    exit 1
fi

# Infrastructure check function
check_infrastructure() {
    echo -e "${YELLOW}Checking infrastructure status...${NC}"

    # Check if test-env script exists
    if [[ -f "$UTILS_DIR/test-env" ]]; then
        cd "$UTILS_DIR"
        if ./test-env status; then
            echo -e "${GREEN}✓ Infrastructure is ready${NC}"
            return 0
        else
            echo -e "${RED}✗ Infrastructure is not ready${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}Warning: test-env script not found at $UTILS_DIR/test-env${NC}"
        echo -e "${YELLOW}Checking for Core SDK infrastructure...${NC}"

        # Check parent SDK infrastructure
        PARENT_UTILS=""
        if [[ -f "$PARENT_UTILS/test-env" ]]; then
            cd "$PARENT_UTILS"
            if ./test-env status; then
                echo -e "${GREEN}✓ Core SDK infrastructure is ready${NC}"
                return 0
            else
                echo -e "${RED}✗ Core SDK infrastructure is not ready${NC}"
                return 1
            fi
        else
            echo -e "${RED}✗ No infrastructure setup found${NC}"
            return 1
        fi
    fi
}

# Infrastructure setup function
setup_infrastructure() {
    echo -e "${YELLOW}Setting up infrastructure for integration tests...${NC}"

    # Try local test-env first
    if [[ -f "$UTILS_DIR/test-env" ]]; then
        cd "$UTILS_DIR"
        ./test-env up
    else
        # Fall back to parent SDK infrastructure
        PARENT_UTILS=""
        if [[ -f "$PARENT_UTILS/test-env" ]]; then
            cd "$PARENT_UTILS"
            ./test-env up
        else
            echo -e "${RED}Error: No infrastructure setup script found${NC}"
            echo -e "${RED}Expected locations:${NC}"
            echo -e "${RED}  - $UTILS_DIR/test-env${NC}"
            echo -e "${RED}  - $PARENT_UTILS/test-env${NC}"
            exit 1
        fi
    fi

    # Verify setup worked
    if check_infrastructure; then
        echo -e "${GREEN}✓ Infrastructure setup complete${NC}"
    else
        echo -e "${RED}✗ Infrastructure setup failed${NC}"
        exit 1
    fi
}

# Infrastructure cleanup function
cleanup_infrastructure() {
    echo -e "${YELLOW}Cleaning up infrastructure...${NC}"

    # Try local test-env first
    if [[ -f "$UTILS_DIR/test-env" ]]; then
        cd "$UTILS_DIR"
        ./test-env down
    else
        # Fall back to parent SDK infrastructure
        PARENT_UTILS=""
        if [[ -f "$PARENT_UTILS/test-env" ]]; then
            cd "$PARENT_UTILS"
            ./test-env down
        fi
    fi

    echo -e "${GREEN}✓ Infrastructure cleanup complete${NC}"
}

# Handle specific operations
if [[ "$CHECK_INFRA" == true ]]; then
    check_infrastructure
    exit $?
fi

if [[ "$SETUP_INFRA" == true ]]; then
    setup_infrastructure
    exit 0
fi

if [[ "$CLEANUP_INFRA" == true ]]; then
    cleanup_infrastructure
    exit 0
fi

# Pre-flight infrastructure check
echo -e "${YELLOW}Pre-flight infrastructure check...${NC}"
if ! check_infrastructure; then
    if [[ "$FORCE" == true ]]; then
        echo -e "${YELLOW}Warning: Infrastructure check failed, but --force specified. Continuing...${NC}"
    else
        echo ""
        echo -e "${RED}CRITICAL: Infrastructure not ready for Tier 2 tests${NC}"
        echo ""
        echo -e "${YELLOW}Required setup:${NC}"
        echo -e "  ${BLUE}./tests/utils/test-env up${NC}"
        echo -e "  ${BLUE}./tests/utils/test-env status${NC}"
        echo ""
        echo -e "${YELLOW}Or run with infrastructure setup:${NC}"
        echo -e "  ${BLUE}$0 --setup${NC}"
        echo ""
        echo -e "${YELLOW}Required services for Tier 2 tests:${NC}"
        echo -e "  ${YELLOW}•${NC} PostgreSQL (database integration)"
        echo -e "  ${YELLOW}•${NC} Redis (caching and session tests)"
        echo -e "  ${YELLOW}•${NC} MinIO (object storage tests)"
        echo -e "  ${YELLOW}•${NC} Elasticsearch (search functionality)"
        echo ""
        echo -e "${RED}NO MOCKING POLICY: Tier 2 tests MUST use real infrastructure${NC}"
        exit 1
    fi
fi

# Return to project root for tests
cd "$PROJECT_ROOT"

# Build base pytest command
PYTEST_CMD="python -m pytest"

# Add test path
if [[ -n "$SPECIFIC_FILE" ]]; then
    if [[ -f "$TEST_DIR/$SPECIFIC_FILE" ]]; then
        TEST_PATH="$TEST_DIR/$SPECIFIC_FILE"
    elif [[ -f "$TEST_DIR/test_$SPECIFIC_FILE.py" ]]; then
        TEST_PATH="$TEST_DIR/test_$SPECIFIC_FILE.py"
    else
        echo -e "${RED}Error: Test file not found: $SPECIFIC_FILE${NC}"
        exit 1
    fi
else
    TEST_PATH="$TEST_DIR"
fi

# Add tier marker
PYTEST_CMD="$PYTEST_CMD $TEST_PATH -m integration"

# Add timeout for Tier 2 (5 seconds per test)
PYTEST_CMD="$PYTEST_CMD --timeout=5"

# Add infrastructure requirement markers
PYTEST_CMD="$PYTEST_CMD --strict-markers"

# Add verbosity
if [[ "$VERBOSE" == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -v -s"
else
    PYTEST_CMD="$PYTEST_CMD --tb=short"
fi

# NO MOCKING validation
PYTEST_CMD="$PYTEST_CMD --disable-warnings"

echo -e "${YELLOW}Command: $PYTEST_CMD${NC}"
echo ""

# Start timer
START_TIME=$(date +%s)

# Run tests
echo -e "${BLUE}Running Tier 2 (Integration) Tests...${NC}"
echo -e "${RED}NO MOCKING POLICY ENFORCED - Using real infrastructure only${NC}"
echo ""

if eval "$PYTEST_CMD"; then
    # Success
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}✓ Tier 2 (Integration) Tests PASSED${NC}"
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}Execution time: ${DURATION}s${NC}"
    echo -e "${GREEN}Infrastructure: Real services used (NO MOCKING)${NC}"

    # Cleanup option
    echo ""
    echo -e "${YELLOW}Cleanup infrastructure?${NC}"
    echo -e "  ${BLUE}$0 --cleanup${NC}"

    exit 0
else
    # Failure
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}✗ Tier 2 (Integration) Tests FAILED${NC}"
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}Execution time: ${DURATION}s${NC}"
    echo ""
    echo -e "${YELLOW}Common Tier 2 Issues:${NC}"
    echo -e "  ${YELLOW}•${NC} Infrastructure not available (PostgreSQL, Redis, etc.)"
    echo -e "  ${YELLOW}•${NC} Test timeout (>5000ms) - Check service connections"
    echo -e "  ${YELLOW}•${NC} Connection failures - Verify service health"
    echo -e "  ${YELLOW}•${NC} Mocking detected - Remove mocks, use real services"
    echo ""
    echo -e "${YELLOW}Debug commands:${NC}"
    echo -e "  ${BLUE}$0 --check${NC}                 # Check infrastructure status"
    echo -e "  ${BLUE}$0 --setup${NC}                 # Setup infrastructure"
    echo -e "  ${BLUE}$0 --file failing_test --verbose${NC}"
    echo ""
    echo -e "${YELLOW}Infrastructure debug:${NC}"
    if [[ -f "$UTILS_DIR/test-env" ]]; then
        echo -e "  ${BLUE}cd $UTILS_DIR && ./test-env status${NC}"
        echo -e "  ${BLUE}cd $UTILS_DIR && ./test-env logs${NC}"
    else
        PARENT_UTILS=""
        echo -e "  ${BLUE}cd $PARENT_UTILS && ./test-env status${NC}"
        echo -e "  ${BLUE}cd $PARENT_UTILS && ./test-env logs${NC}"
    fi

    exit 1
fi
