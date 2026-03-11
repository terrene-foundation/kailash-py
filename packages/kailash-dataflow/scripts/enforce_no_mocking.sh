#!/bin/bash
#
# NO MOCKING Policy Enforcement
#
# Enforces the strict NO MOCKING policy in Tier 2 and Tier 3 tests.
# Tier 1 (unit tests) are allowed to use mocking.
# Tier 2 (integration tests) and Tier 3 (e2e tests) MUST use real infrastructure.
#
# Exit Codes:
#   0 - No mocking violations found
#   1 - Mocking detected in Tier 2/3 tests
#
# Usage:
#   ./scripts/enforce_no_mocking.sh
#   ./scripts/enforce_no_mocking.sh --verbose

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TESTS_DIR="${PROJECT_ROOT}/tests"
VERBOSE=0

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--verbose]"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}=== NO MOCKING Policy Enforcement ===${NC}"
echo ""

# Check if tests directory exists
if [ ! -d "${TESTS_DIR}" ]; then
    echo -e "${RED}ERROR: Tests directory not found: ${TESTS_DIR}${NC}"
    exit 1
fi

# Mocking patterns to detect
declare -a MOCK_PATTERNS=(
    "from unittest.mock import"
    "from unittest import mock"
    "import unittest.mock"
    "import mock"
    "from mock import"
    "@patch"
    "@mock.patch"
    "Mock()"
    "MagicMock()"
    "AsyncMock()"
    "patch.object"
    "patch.dict"
    "mock.Mock"
    "mock.MagicMock"
    "mock.AsyncMock"
    "pytest-mock"
    "mocker.patch"
    "mocker.Mock"
)

# Temporary files
VIOLATIONS_FILE=$(mktemp)
trap "rm -f ${VIOLATIONS_FILE}" EXIT

# Track findings
VIOLATIONS_FOUND=0
TIER2_VIOLATIONS=0
TIER3_VIOLATIONS=0

# Function to check file for mocking
check_file_for_mocking() {
    local file=$1
    local tier=$2
    local violations=0

    for pattern in "${MOCK_PATTERNS[@]}"; do
        if grep -nE "${pattern}" "${file}" >> "${VIOLATIONS_FILE}" 2>/dev/null; then
            if [ ${VERBOSE} -eq 1 ]; then
                echo -e "  ${RED}✗ Found mocking in ${tier}: ${file}${NC}"
            fi
            violations=1
            break
        fi
    done

    echo ${violations}
}

# Check Tier 2 (Integration) tests
echo -e "${BLUE}Checking Tier 2 (Integration) tests...${NC}"

INTEGRATION_DIR="${TESTS_DIR}/integration"
if [ -d "${INTEGRATION_DIR}" ]; then
    INTEGRATION_FILES=$(find "${INTEGRATION_DIR}" -type f -name "test_*.py" -o -name "*_test.py")

    if [ -z "${INTEGRATION_FILES}" ]; then
        echo "No integration tests found"
    else
        FILE_COUNT=$(echo "${INTEGRATION_FILES}" | wc -l | tr -d ' ')
        echo "Scanning ${FILE_COUNT} integration test files..."

        for test_file in ${INTEGRATION_FILES}; do
            if [ ${VERBOSE} -eq 1 ]; then
                echo "Checking: ${test_file}"
            fi

            # Write tier header to violations file
            echo "=== Tier 2 (Integration): ${test_file} ===" >> "${VIOLATIONS_FILE}"

            for pattern in "${MOCK_PATTERNS[@]}"; do
                if matches=$(grep -nE "${pattern}" "${test_file}" 2>/dev/null); then
                    echo "${matches}" >> "${VIOLATIONS_FILE}"
                    TIER2_VIOLATIONS=$((TIER2_VIOLATIONS + 1))
                    VIOLATIONS_FOUND=1

                    if [ ${VERBOSE} -eq 1 ]; then
                        echo -e "  ${RED}✗ Found mocking pattern: ${pattern}${NC}"
                    fi
                fi
            done
        done

        if [ ${TIER2_VIOLATIONS} -eq 0 ]; then
            echo -e "  ${GREEN}✓ No mocking violations in integration tests${NC}"
        else
            echo -e "  ${RED}✗ Found ${TIER2_VIOLATIONS} mocking violations${NC}"
        fi
    fi
else
    echo -e "${YELLOW}Integration tests directory not found: ${INTEGRATION_DIR}${NC}"
fi

echo ""

# Check Tier 3 (E2E) tests
echo -e "${BLUE}Checking Tier 3 (E2E) tests...${NC}"

E2E_DIR="${TESTS_DIR}/e2e"
if [ -d "${E2E_DIR}" ]; then
    E2E_FILES=$(find "${E2E_DIR}" -type f -name "test_*.py" -o -name "*_test.py")

    if [ -z "${E2E_FILES}" ]; then
        echo "No e2e tests found"
    else
        FILE_COUNT=$(echo "${E2E_FILES}" | wc -l | tr -d ' ')
        echo "Scanning ${FILE_COUNT} e2e test files..."

        for test_file in ${E2E_FILES}; do
            if [ ${VERBOSE} -eq 1 ]; then
                echo "Checking: ${test_file}"
            fi

            # Write tier header to violations file
            echo "=== Tier 3 (E2E): ${test_file} ===" >> "${VIOLATIONS_FILE}"

            for pattern in "${MOCK_PATTERNS[@]}"; do
                if matches=$(grep -nE "${pattern}" "${test_file}" 2>/dev/null); then
                    echo "${matches}" >> "${VIOLATIONS_FILE}"
                    TIER3_VIOLATIONS=$((TIER3_VIOLATIONS + 1))
                    VIOLATIONS_FOUND=1

                    if [ ${VERBOSE} -eq 1 ]; then
                        echo -e "  ${RED}✗ Found mocking pattern: ${pattern}${NC}"
                    fi
                fi
            done
        done

        if [ ${TIER3_VIOLATIONS} -eq 0 ]; then
            echo -e "  ${GREEN}✓ No mocking violations in e2e tests${NC}"
        else
            echo -e "  ${RED}✗ Found ${TIER3_VIOLATIONS} mocking violations${NC}"
        fi
    fi
else
    echo -e "${YELLOW}E2E tests directory not found: ${E2E_DIR}${NC}"
fi

echo ""

# Check Tier 1 (Unit) tests - informational only
echo -e "${BLUE}Checking Tier 1 (Unit) tests (informational only)...${NC}"

UNIT_DIR="${TESTS_DIR}/unit"
if [ -d "${UNIT_DIR}" ]; then
    UNIT_MOCKS=$(find "${UNIT_DIR}" -type f \( -name "test_*.py" -o -name "*_test.py" \) -exec grep -l "mock" {} \; | wc -l | tr -d ' ')
    echo -e "  ${GREEN}ℹ Unit tests with mocking: ${UNIT_MOCKS} (allowed)${NC}"
else
    echo -e "${YELLOW}Unit tests directory not found: ${UNIT_DIR}${NC}"
fi

# Final report
echo ""
echo -e "${GREEN}=== Enforcement Summary ===${NC}"
echo ""
echo "Tier 2 (Integration) violations: ${TIER2_VIOLATIONS}"
echo "Tier 3 (E2E) violations: ${TIER3_VIOLATIONS}"
echo "Total violations: $((TIER2_VIOLATIONS + TIER3_VIOLATIONS))"
echo ""

if [ ${VIOLATIONS_FOUND} -eq 1 ]; then
    echo -e "${RED}✗ NO MOCKING POLICY VIOLATION DETECTED${NC}"
    echo ""
    echo "Violations found:"
    cat "${VIOLATIONS_FILE}"
    echo ""
    echo -e "${YELLOW}Action Required:${NC}"
    echo "1. Remove all mock/stub usage from Tier 2 (integration) tests"
    echo "2. Remove all mock/stub usage from Tier 3 (e2e) tests"
    echo "3. Use real infrastructure (Docker services) for testing"
    echo "4. Refer to testing strategy: .claude/skills/12-testing-strategies/"
    echo ""
    echo -e "${RED}NO MOCKING in Tiers 2-3 is MANDATORY${NC}"
    exit 1
else
    echo -e "${GREEN}✓ NO MOCKING POLICY COMPLIANCE VERIFIED${NC}"
    echo ""
    echo "All Tier 2 and Tier 3 tests use real infrastructure."
    echo "NO MOCKING policy is being followed correctly."
    exit 0
fi
