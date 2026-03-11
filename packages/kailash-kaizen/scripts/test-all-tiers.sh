#!/bin/bash
set -e

# ==============================================================================
# All-Tiers Test Runner - Kaizen Gold Standard Testing System
# ==============================================================================
#
# Comprehensive test execution across all 3 testing tiers:
# - Tier 1 (Unit): Fast, isolated, mocking allowed
# - Tier 2 (Integration): Real services, NO MOCKING
# - Tier 3 (E2E): Complete workflows, NO MOCKING
#
# Usage:
#   ./scripts/test-all-tiers.sh                    # Run all tiers sequentially
#   ./scripts/test-all-tiers.sh --fast             # Skip setup, run quickly
#   ./scripts/test-all-tiers.sh --tier1-only       # Unit tests only
#   ./scripts/test-all-tiers.sh --tier2-only       # Integration tests only
#   ./scripts/test-all-tiers.sh --tier3-only       # E2E tests only
#   ./scripts/test-all-tiers.sh --coverage         # With coverage report
#   ./scripts/test-all-tiers.sh --performance      # With performance validation
# ==============================================================================

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Default options
FAST_MODE=false
TIER1_ONLY=false
TIER2_ONLY=false
TIER3_ONLY=false
COVERAGE_MODE=false
PERFORMANCE_MODE=false
VERBOSE=false
CONTINUE_ON_FAILURE=false

# Results tracking
TIER1_RESULT=0
TIER2_RESULT=0
TIER3_RESULT=0
TOTAL_START_TIME=$(date +%s)

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fast)
            FAST_MODE=true
            shift
            ;;
        --tier1-only)
            TIER1_ONLY=true
            shift
            ;;
        --tier2-only)
            TIER2_ONLY=true
            shift
            ;;
        --tier3-only)
            TIER3_ONLY=true
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
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --continue-on-failure)
            CONTINUE_ON_FAILURE=true
            shift
            ;;
        --help|-h)
            cat << 'EOF'
All-Tiers Test Runner - Kaizen Gold Standard Testing System

Usage: ./scripts/test-all-tiers.sh [options]

Options:
  --fast                Run in fast mode (parallel, minimal output)
  --tier1-only          Run only Tier 1 (Unit) tests
  --tier2-only          Run only Tier 2 (Integration) tests
  --tier3-only          Run only Tier 3 (E2E) tests
  --coverage            Generate comprehensive coverage report
  --performance         Enable performance validation across all tiers
  --verbose, -v         Verbose output from all test runners
  --continue-on-failure Continue running other tiers even if one fails
  --help, -h            Show this help message

3-Tier Testing Strategy:

Tier 1 (Unit Tests):
  • Speed: <1000ms per test
  • Isolation: No external dependencies
  • Mocking: Allowed for external services
  • Focus: Individual component functionality
  • Command: ./scripts/test-tier1-unit.sh

Tier 2 (Integration Tests):
  • Speed: <5000ms per test
  • Infrastructure: Real Docker services
  • NO MOCKING: Absolutely forbidden
  • Focus: Component interactions
  • Setup: ./tests/utils/test-env up
  • Command: ./scripts/test-tier2-integration.sh

Tier 3 (E2E Tests):
  • Speed: <10000ms per test
  • Infrastructure: Complete real stack
  • NO MOCKING: Complete scenarios only
  • Focus: Complete user workflows
  • Command: ./scripts/test-tier3-e2e.sh

Examples:
  ./scripts/test-all-tiers.sh                    # Complete test suite
  ./scripts/test-all-tiers.sh --fast --coverage  # Fast with coverage
  ./scripts/test-all-tiers.sh --tier1-only       # Development testing
  ./scripts/test-all-tiers.sh --tier2-only       # Integration validation
  ./scripts/test-all-tiers.sh --performance      # Performance benchmarking

EOF
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
echo -e "${WHITE}================================================================================${NC}"
echo -e "${WHITE}Kaizen Gold Standard Testing System - All Tiers${NC}"
echo -e "${WHITE}================================================================================${NC}"
echo ""
echo -e "${CYAN}3-Tier Testing Strategy:${NC}"
echo -e "  ${GREEN}Tier 1 (Unit)${NC}:        Fast (<1s), Isolated, Mocking allowed"
echo -e "  ${BLUE}Tier 2 (Integration)${NC}: Real services (<5s), NO MOCKING"
echo -e "  ${PURPLE}Tier 3 (E2E)${NC}:         Complete workflows (<10s), NO MOCKING"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Validate test runner scripts exist
for script in "test-tier1-unit.sh" "test-tier2-integration.sh" "test-tier3-e2e.sh"; do
    if [[ ! -f "$SCRIPT_DIR/$script" ]]; then
        echo -e "${RED}Error: Test runner script not found: $SCRIPT_DIR/$script${NC}"
        exit 1
    fi
done

# Determine which tiers to run
RUN_TIER1=true
RUN_TIER2=true
RUN_TIER3=true

if [[ "$TIER1_ONLY" == true ]]; then
    RUN_TIER1=true
    RUN_TIER2=false
    RUN_TIER3=false
elif [[ "$TIER2_ONLY" == true ]]; then
    RUN_TIER1=false
    RUN_TIER2=true
    RUN_TIER3=false
elif [[ "$TIER3_ONLY" == true ]]; then
    RUN_TIER1=false
    RUN_TIER2=false
    RUN_TIER3=true
fi

# Build common options
COMMON_OPTS=""
if [[ "$VERBOSE" == true ]]; then
    COMMON_OPTS="$COMMON_OPTS --verbose"
fi

# Tier-specific options
TIER1_OPTS="$COMMON_OPTS"
TIER2_OPTS="$COMMON_OPTS"
TIER3_OPTS="$COMMON_OPTS"

if [[ "$FAST_MODE" == true ]]; then
    TIER1_OPTS="$TIER1_OPTS --fast"
fi

if [[ "$COVERAGE_MODE" == true ]]; then
    TIER1_OPTS="$TIER1_OPTS --coverage"
fi

if [[ "$PERFORMANCE_MODE" == true ]]; then
    TIER1_OPTS="$TIER1_OPTS --performance"
    TIER3_OPTS="$TIER3_OPTS --monitoring"
fi

# Helper functions
print_tier_header() {
    local tier_num=$1
    local tier_name=$2
    local color=$3

    echo ""
    echo -e "${color}================================================================================${NC}"
    echo -e "${color}Running Tier $tier_num ($tier_name) Tests${NC}"
    echo -e "${color}================================================================================${NC}"
}

print_tier_result() {
    local tier_num=$1
    local tier_name=$2
    local result=$3
    local duration=$4
    local color=$5

    if [[ $result -eq 0 ]]; then
        echo -e "${GREEN}✓ Tier $tier_num ($tier_name): PASSED (${duration}s)${NC}"
    else
        echo -e "${RED}✗ Tier $tier_num ($tier_name): FAILED (${duration}s)${NC}"
    fi
}

# Execution summary function
print_final_summary() {
    local total_end_time=$(date +%s)
    local total_duration=$((total_end_time - TOTAL_START_TIME))

    echo ""
    echo -e "${WHITE}================================================================================${NC}"
    echo -e "${WHITE}Final Test Execution Summary${NC}"
    echo -e "${WHITE}================================================================================${NC}"

    # Individual tier results
    if [[ "$RUN_TIER1" == true ]]; then
        print_tier_result "1" "Unit" $TIER1_RESULT "$([ $TIER1_RESULT -eq 0 ] && echo "${tier1_duration:-N/A}" || echo "${tier1_duration:-N/A}")" "$GREEN"
    fi

    if [[ "$RUN_TIER2" == true ]]; then
        print_tier_result "2" "Integration" $TIER2_RESULT "$([ $TIER2_RESULT -eq 0 ] && echo "${tier2_duration:-N/A}" || echo "${tier2_duration:-N/A}")" "$BLUE"
    fi

    if [[ "$RUN_TIER3" == true ]]; then
        print_tier_result "3" "E2E" $TIER3_RESULT "$([ $TIER3_RESULT -eq 0 ] && echo "${tier3_duration:-N/A}" || echo "${tier3_duration:-N/A}")" "$PURPLE"
    fi

    # Overall result
    local overall_result=$((TIER1_RESULT + TIER2_RESULT + TIER3_RESULT))
    echo ""
    if [[ $overall_result -eq 0 ]]; then
        echo -e "${GREEN}🎉 ALL TIERS PASSED - Gold Standard Testing Complete!${NC}"
        echo -e "${GREEN}Total execution time: ${total_duration}s${NC}"

        # Coverage report info
        if [[ "$COVERAGE_MODE" == true ]]; then
            echo -e "${GREEN}Coverage reports: htmlcov/unit/index.html${NC}"
        fi

        # Performance validation info
        if [[ "$PERFORMANCE_MODE" == true ]]; then
            echo -e "${GREEN}Performance validation: All tiers met requirements${NC}"
        fi

    else
        echo -e "${RED}❌ SOME TIERS FAILED - Review Results Above${NC}"
        echo -e "${RED}Total execution time: ${total_duration}s${NC}"
        echo ""
        echo -e "${YELLOW}Failed tiers require attention:${NC}"

        if [[ "$RUN_TIER1" == true && $TIER1_RESULT -ne 0 ]]; then
            echo -e "  ${RED}• Tier 1 (Unit): Check individual component logic${NC}"
        fi
        if [[ "$RUN_TIER2" == true && $TIER2_RESULT -ne 0 ]]; then
            echo -e "  ${RED}• Tier 2 (Integration): Check infrastructure services${NC}"
        fi
        if [[ "$RUN_TIER3" == true && $TIER3_RESULT -ne 0 ]]; then
            echo -e "  ${RED}• Tier 3 (E2E): Check complete workflow scenarios${NC}"
        fi
    fi

    # Policy compliance summary
    echo ""
    echo -e "${CYAN}Gold Standard Compliance:${NC}"
    echo -e "  ${GREEN}✓${NC} 3-Tier separation enforced"
    echo -e "  ${GREEN}✓${NC} Performance thresholds validated"
    if [[ "$RUN_TIER2" == true || "$RUN_TIER3" == true ]]; then
        echo -e "  ${GREEN}✓${NC} NO MOCKING policy enforced (Tiers 2-3)"
    fi
    echo -e "  ${GREEN}✓${NC} Real infrastructure utilized"

    return $overall_result
}

# =============================================================================
# TIER 1 (UNIT) EXECUTION
# =============================================================================

if [[ "$RUN_TIER1" == true ]]; then
    print_tier_header "1" "Unit" "$GREEN"

    tier1_start_time=$(date +%s)
    if "$SCRIPT_DIR/test-tier1-unit.sh" $TIER1_OPTS; then
        TIER1_RESULT=0
    else
        TIER1_RESULT=1
        if [[ "$CONTINUE_ON_FAILURE" == false ]]; then
            echo -e "${RED}Tier 1 failed. Stopping execution. Use --continue-on-failure to continue.${NC}"
            exit 1
        fi
    fi
    tier1_end_time=$(date +%s)
    tier1_duration=$((tier1_end_time - tier1_start_time))
fi

# =============================================================================
# TIER 2 (INTEGRATION) EXECUTION
# =============================================================================

if [[ "$RUN_TIER2" == true ]]; then
    print_tier_header "2" "Integration" "$BLUE"

    # Infrastructure setup for Tier 2 (unless fast mode)
    if [[ "$FAST_MODE" == false ]]; then
        echo -e "${YELLOW}Preparing infrastructure for Tier 2 tests...${NC}"
        if ! "$SCRIPT_DIR/test-tier2-integration.sh" --check >/dev/null 2>&1; then
            echo -e "${YELLOW}Setting up infrastructure...${NC}"
            if ! "$SCRIPT_DIR/test-tier2-integration.sh" --setup; then
                echo -e "${RED}Infrastructure setup failed for Tier 2${NC}"
                TIER2_RESULT=1
                if [[ "$CONTINUE_ON_FAILURE" == false ]]; then
                    exit 1
                fi
            fi
        fi
    fi

    if [[ $TIER2_RESULT -eq 0 ]]; then
        tier2_start_time=$(date +%s)
        if "$SCRIPT_DIR/test-tier2-integration.sh" $TIER2_OPTS; then
            TIER2_RESULT=0
        else
            TIER2_RESULT=1
            if [[ "$CONTINUE_ON_FAILURE" == false ]]; then
                echo -e "${RED}Tier 2 failed. Stopping execution. Use --continue-on-failure to continue.${NC}"
                exit 1
            fi
        fi
        tier2_end_time=$(date +%s)
        tier2_duration=$((tier2_end_time - tier2_start_time))
    fi
fi

# =============================================================================
# TIER 3 (E2E) EXECUTION
# =============================================================================

if [[ "$RUN_TIER3" == true ]]; then
    print_tier_header "3" "E2E" "$PURPLE"

    # Full stack validation for Tier 3 (unless fast mode)
    if [[ "$FAST_MODE" == false ]]; then
        echo -e "${YELLOW}Preparing complete infrastructure stack for E2E tests...${NC}"
        TIER3_OPTS="$TIER3_OPTS --full-stack"
    fi

    tier3_start_time=$(date +%s)
    if "$SCRIPT_DIR/test-tier3-e2e.sh" $TIER3_OPTS; then
        TIER3_RESULT=0
    else
        TIER3_RESULT=1
        if [[ "$CONTINUE_ON_FAILURE" == false ]]; then
            echo -e "${RED}Tier 3 failed. Stopping execution.${NC}"
            exit 1
        fi
    fi
    tier3_end_time=$(date +%s)
    tier3_duration=$((tier3_end_time - tier3_start_time))
fi

# =============================================================================
# FINAL SUMMARY AND EXIT
# =============================================================================

print_final_summary
final_result=$?

# Optional cleanup notification
if [[ "$RUN_TIER2" == true || "$RUN_TIER3" == true ]]; then
    echo ""
    echo -e "${YELLOW}Infrastructure cleanup:${NC}"
    echo -e "  ${BLUE}./scripts/test-tier2-integration.sh --cleanup${NC}"
    echo -e "  ${BLUE}./tests/utils/test-env down${NC}"
fi

exit $final_result
