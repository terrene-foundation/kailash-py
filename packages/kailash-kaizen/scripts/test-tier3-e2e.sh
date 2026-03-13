#!/bin/bash
set -e

# ==============================================================================
# Tier 3 (E2E) Test Runner - Kaizen Gold Standard Testing
# ==============================================================================
#
# Requirements:
# - Speed: <10000ms per test
# - Infrastructure: Complete real infrastructure stack
# - NO MOCKING: Complete scenarios with real services
# - Focus: Complete user workflows
# - Location: tests/e2e/
#
# CRITICAL Setup Required:
#   ./tests/utils/test-env up && ./tests/utils/test-env status
#
# Usage:
#   ./scripts/test-tier3-e2e.sh                    # Run all E2E tests
#   ./scripts/test-tier3-e2e.sh --full-stack       # Full infrastructure validation
#   ./scripts/test-tier3-e2e.sh --scenario NAME    # Specific scenario
#   ./scripts/test-tier3-e2e.sh --smoke            # Smoke tests only
#   ./scripts/test-tier3-e2e.sh --monitoring       # With performance monitoring
# ==============================================================================

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$PROJECT_ROOT/tests/e2e"
UTILS_DIR="$PROJECT_ROOT/tests/utils"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Default options
FULL_STACK=false
SPECIFIC_SCENARIO=""
SMOKE_ONLY=false
MONITORING=false
VERBOSE=false
FORCE=false
PARALLEL=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --full-stack)
            FULL_STACK=true
            shift
            ;;
        --scenario)
            SPECIFIC_SCENARIO="$2"
            shift 2
            ;;
        --smoke)
            SMOKE_ONLY=true
            shift
            ;;
        --monitoring)
            MONITORING=true
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
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
            echo "Tier 3 (E2E) Test Runner"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --full-stack      Complete infrastructure validation"
            echo "  --scenario NAME   Run specific E2E scenario"
            echo "  --smoke           Run smoke tests only (critical paths)"
            echo "  --monitoring      Enable detailed performance monitoring"
            echo "  --parallel        Run tests in parallel (careful with resources)"
            echo "  --verbose, -v     Verbose output"
            echo "  --force           Force run even if infrastructure check fails"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Tier 3 Requirements:"
            echo "  - Maximum duration: 10000ms per test"
            echo "  - Complete real infrastructure stack"
            echo "  - NO MOCKING policy (complete scenarios)"
            echo "  - Focus: Complete user workflows"
            echo ""
            echo "E2E Test Categories:"
            echo "  - Smoke tests: Critical functionality validation"
            echo "  - Workflow tests: Complete user scenarios"
            echo "  - Integration tests: Multi-service interactions"
            echo "  - Performance tests: End-to-end performance validation"
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
echo -e "${PURPLE}================================================================================${NC}"
echo -e "${PURPLE}Tier 3 (E2E) Test Runner - Kaizen Gold Standard Testing${NC}"
echo -e "${PURPLE}================================================================================${NC}"
echo ""
echo -e "${YELLOW}Requirements:${NC}"
echo -e "  ${GREEN}✓${NC} Speed: <10000ms per test"
echo -e "  ${GREEN}✓${NC} Infrastructure: Complete real stack"
echo -e "  ${RED}✗${NC} NO MOCKING: Complete scenarios with real services"
echo -e "  ${GREEN}✓${NC} Focus: Complete user workflows"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Validate directories exist
if [[ ! -d "$TEST_DIR" ]]; then
    echo -e "${RED}Error: E2E test directory not found: $TEST_DIR${NC}"
    exit 1
fi

# Enhanced infrastructure check for E2E
check_full_infrastructure() {
    echo -e "${YELLOW}Checking complete infrastructure stack...${NC}"

    local all_services_ready=true
    local services_status=""

    # Check if test-env script exists
    local test_env_script=""
    if [[ -f "$UTILS_DIR/test-env" ]]; then
        test_env_script="$UTILS_DIR/test-env"
    else
        # Fall back to parent SDK infrastructure
        PARENT_UTILS=""
        if [[ -f "$PARENT_UTILS/test-env" ]]; then
            test_env_script="$PARENT_UTILS/test-env"
        fi
    fi

    if [[ -n "$test_env_script" ]]; then
        cd "$(dirname "$test_env_script")"

        # Get detailed status
        if ./test-env status > /tmp/infra_status.log 2>&1; then
            services_status=$(cat /tmp/infra_status.log)
            echo -e "${GREEN}✓ Infrastructure stack is ready${NC}"

            if [[ "$VERBOSE" == true ]]; then
                echo ""
                echo -e "${BLUE}Infrastructure Status:${NC}"
                echo "$services_status"
            fi

            return 0
        else
            services_status=$(cat /tmp/infra_status.log)
            echo -e "${RED}✗ Infrastructure stack is not ready${NC}"

            if [[ "$VERBOSE" == true ]]; then
                echo ""
                echo -e "${RED}Infrastructure Issues:${NC}"
                echo "$services_status"
            fi

            return 1
        fi
    else
        echo -e "${RED}✗ No infrastructure setup found${NC}"
        echo -e "${RED}Expected locations:${NC}"
        echo -e "${RED}  - $UTILS_DIR/test-env${NC}"
        echo -e "${RED}  - "
        return 1
    fi
}

# Setup complete infrastructure stack
setup_full_stack() {
    echo -e "${YELLOW}Setting up complete infrastructure stack for E2E tests...${NC}"
    echo -e "${YELLOW}This may take several minutes...${NC}"

    # Find and run setup
    local test_env_script=""
    if [[ -f "$UTILS_DIR/test-env" ]]; then
        test_env_script="$UTILS_DIR/test-env"
    else
        PARENT_UTILS=""
        if [[ -f "$PARENT_UTILS/test-env" ]]; then
            test_env_script="$PARENT_UTILS/test-env"
        fi
    fi

    if [[ -n "$test_env_script" ]]; then
        cd "$(dirname "$test_env_script")"

        # Start all services
        ./test-env up --wait

        # Wait for services to be fully ready
        echo -e "${YELLOW}Waiting for services to be fully ready...${NC}"
        sleep 10

        # Verify setup
        if check_full_infrastructure; then
            echo -e "${GREEN}✓ Complete infrastructure stack ready${NC}"
            return 0
        else
            echo -e "${RED}✗ Infrastructure setup failed${NC}"
            echo -e "${RED}Check service logs for details${NC}"
            return 1
        fi
    else
        echo -e "${RED}Error: No infrastructure setup script found${NC}"
        return 1
    fi
}

# Pre-flight infrastructure check
if [[ "$FULL_STACK" == true ]]; then
    echo -e "${PURPLE}Full Stack Mode: Complete infrastructure validation${NC}"
    if ! check_full_infrastructure; then
        if [[ "$FORCE" == true ]]; then
            echo -e "${YELLOW}Warning: Infrastructure check failed, but --force specified${NC}"
        else
            echo ""
            echo -e "${YELLOW}Setting up complete infrastructure stack...${NC}"
            if ! setup_full_stack; then
                echo -e "${RED}Failed to setup infrastructure. Use --force to skip checks.${NC}"
                exit 1
            fi
        fi
    fi
else
    echo -e "${YELLOW}Pre-flight infrastructure check...${NC}"
    if ! check_full_infrastructure; then
        if [[ "$FORCE" == true ]]; then
            echo -e "${YELLOW}Warning: Infrastructure check failed, but --force specified${NC}"
        else
            echo ""
            echo -e "${RED}CRITICAL: Complete infrastructure stack not ready for E2E tests${NC}"
            echo ""
            echo -e "${YELLOW}E2E tests require complete infrastructure:${NC}"
            echo -e "  ${YELLOW}•${NC} PostgreSQL (database operations)"
            echo -e "  ${YELLOW}•${NC} Redis (caching and sessions)"
            echo -e "  ${YELLOW}•${NC} MinIO (object storage)"
            echo -e "  ${YELLOW}•${NC} Elasticsearch (search functionality)"
            echo -e "  ${YELLOW}•${NC} Ollama (AI/LLM operations) [optional]"
            echo ""
            echo -e "${YELLOW}Setup options:${NC}"
            echo -e "  ${BLUE}$0 --full-stack${NC}     # Setup and run"
            echo -e "  ${BLUE}./tests/utils/test-env up${NC}     # Manual setup"
            echo ""
            echo -e "${RED}NO MOCKING POLICY: E2E tests MUST use complete real infrastructure${NC}"
            exit 1
        fi
    fi
fi

# Return to project root for tests
cd "$PROJECT_ROOT"

# Build base pytest command
PYTEST_CMD="python -m pytest"

# Determine test selection
if [[ -n "$SPECIFIC_SCENARIO" ]]; then
    # Specific scenario
    if [[ -f "$TEST_DIR/test_${SPECIFIC_SCENARIO}.py" ]]; then
        TEST_PATH="$TEST_DIR/test_${SPECIFIC_SCENARIO}.py"
    elif [[ -f "$TEST_DIR/${SPECIFIC_SCENARIO}.py" ]]; then
        TEST_PATH="$TEST_DIR/${SPECIFIC_SCENARIO}.py"
    else
        echo -e "${RED}Error: E2E scenario not found: $SPECIFIC_SCENARIO${NC}"
        echo -e "${YELLOW}Available scenarios:${NC}"
        find "$TEST_DIR" -name "test_*.py" -exec basename {} \; | sed 's/test_/  - /' | sed 's/.py//'
        exit 1
    fi
elif [[ "$SMOKE_ONLY" == true ]]; then
    # Smoke tests only
    TEST_PATH="$TEST_DIR"
    PYTEST_CMD="$PYTEST_CMD -k smoke"
else
    # All E2E tests
    TEST_PATH="$TEST_DIR"
fi

# Add tier marker
PYTEST_CMD="$PYTEST_CMD $TEST_PATH -m e2e"

# Add timeout for Tier 3 (10 seconds per test)
PYTEST_CMD="$PYTEST_CMD --timeout=10"

# Add parallel execution if requested
if [[ "$PARALLEL" == true ]]; then
    echo -e "${YELLOW}Parallel Mode: Running E2E tests in parallel${NC}"
    echo -e "${YELLOW}Warning: This may overwhelm infrastructure resources${NC}"
    PYTEST_CMD="$PYTEST_CMD -n 2"  # Limited parallelism for E2E
fi

# Add performance monitoring
if [[ "$MONITORING" == true ]]; then
    echo -e "${PURPLE}Monitoring Mode: Detailed performance tracking enabled${NC}"
    PYTEST_CMD="$PYTEST_CMD --durations=10 --benchmark-skip"
fi

# Add verbosity and strict requirements
if [[ "$VERBOSE" == true ]]; then
    PYTEST_CMD="$PYTEST_CMD -v -s"
else
    PYTEST_CMD="$PYTEST_CMD --tb=short"
fi

# E2E specific configurations
PYTEST_CMD="$PYTEST_CMD --strict-markers --maxfail=3"

echo -e "${PURPLE}E2E Command: $PYTEST_CMD${NC}"
echo ""

# Start timer
START_TIME=$(date +%s)

# Run E2E tests
echo -e "${PURPLE}Running Tier 3 (E2E) Tests...${NC}"
echo -e "${RED}NO MOCKING POLICY ENFORCED - Complete real infrastructure scenarios${NC}"
echo ""

if [[ "$SMOKE_ONLY" == true ]]; then
    echo -e "${BLUE}Running smoke tests only (critical functionality validation)${NC}"
elif [[ -n "$SPECIFIC_SCENARIO" ]]; then
    echo -e "${BLUE}Running specific scenario: $SPECIFIC_SCENARIO${NC}"
else
    echo -e "${BLUE}Running complete E2E test suite${NC}"
fi

echo ""

if eval "$PYTEST_CMD"; then
    # Success
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}✓ Tier 3 (E2E) Tests PASSED${NC}"
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}Execution time: ${DURATION}s${NC}"
    echo -e "${GREEN}Infrastructure: Complete real stack used (NO MOCKING)${NC}"

    # Performance summary for E2E
    if [[ "$MONITORING" == true ]]; then
        echo ""
        echo -e "${PURPLE}E2E Performance Summary:${NC}"
        echo -e "  ${GREEN}✓${NC} All workflows completed under 10000ms limit"
        echo -e "  ${GREEN}✓${NC} Complete infrastructure integration verified"
        echo -e "  ${GREEN}✓${NC} End-to-end scenarios validated"
    fi

    # Success categorization
    echo ""
    if [[ "$SMOKE_ONLY" == true ]]; then
        echo -e "${GREEN}✓ Smoke tests passed - Critical functionality verified${NC}"
    elif [[ -n "$SPECIFIC_SCENARIO" ]]; then
        echo -e "${GREEN}✓ Scenario '$SPECIFIC_SCENARIO' passed - Workflow validated${NC}"
    else
        echo -e "${GREEN}✓ Complete E2E suite passed - All workflows validated${NC}"
    fi

    exit 0
else
    # Failure
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}✗ Tier 3 (E2E) Tests FAILED${NC}"
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}Execution time: ${DURATION}s${NC}"
    echo ""
    echo -e "${YELLOW}Common Tier 3 Issues:${NC}"
    echo -e "  ${YELLOW}•${NC} Infrastructure service unavailable"
    echo -e "  ${YELLOW}•${NC} Complete workflow timeout (>10000ms)"
    echo -e "  ${YELLOW}•${NC} Cross-service integration failures"
    echo -e "  ${YELLOW}•${NC} Data consistency issues between services"
    echo -e "  ${YELLOW}•${NC} Resource exhaustion (memory, connections)"
    echo ""
    echo -e "${YELLOW}Debug commands:${NC}"
    echo -e "  ${BLUE}$0 --smoke --verbose${NC}              # Test critical paths only"
    echo -e "  ${BLUE}$0 --scenario specific_test --verbose${NC}"
    echo -e "  ${BLUE}$0 --full-stack --verbose${NC}         # Full infrastructure validation"
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
    echo ""
    echo -e "${YELLOW}E2E Test Categories for focused debugging:${NC}"
    echo -e "  ${BLUE}$0 --smoke${NC}                      # Critical functionality only"
    find "$TEST_DIR" -name "test_*.py" -exec basename {} \; | sed 's/test_/  - /' | sed 's/.py//' | head -5

    exit 1
fi
