#!/bin/bash
#
# Stub Detection Script
#
# Prevents stub implementations from being merged into production code.
# This script searches for common stub patterns and exits with error if found.
#
# Exit Codes:
#   0 - No stubs found
#   1 - Stubs detected or script error
#
# Usage:
#   ./scripts/detect_stubs.sh
#   ./scripts/detect_stubs.sh --verbose

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${PROJECT_ROOT}/src"
VERBOSE=0

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
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

# Stub detection patterns
# These patterns indicate stub/placeholder implementations
declare -a STUB_PATTERNS=(
    "STUB implementation"
    "return.*simulated"
    "mock.*data.*return"
    "placeholder.*implementation"
    "TODO.*implement"
    "FIXME.*stub"
    "NotImplementedError.*stub"
    "raise NotImplementedError"
    "pass  # stub"
    "pass  # placeholder"
    "return {}  # stub"
    "return \[\]  # stub"
    "return None  # stub"
)

# Exclusion patterns - files/directories to skip
declare -a EXCLUDE_PATTERNS=(
    "*/tests/*"
    "*/test_*"
    "*_test.py"
    "*/docs/*"
    "*/examples/*"
    "*/__pycache__/*"
    "*.pyc"
    "*/.pytest_cache/*"
    "*/venv/*"
    "*/env/*"
    "*/.git/*"
)

# Build grep exclude arguments
GREP_EXCLUDE_ARGS=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    GREP_EXCLUDE_ARGS="${GREP_EXCLUDE_ARGS} --exclude-dir='${pattern}' --exclude='${pattern}'"
done

echo -e "${GREEN}=== Stub Detection Script ===${NC}"
echo "Scanning: ${SRC_DIR}"
echo ""

# Check if source directory exists
if [ ! -d "${SRC_DIR}" ]; then
    echo -e "${RED}ERROR: Source directory not found: ${SRC_DIR}${NC}"
    exit 1
fi

# Track findings
STUBS_FOUND=0
TEMP_FILE=$(mktemp)
trap "rm -f ${TEMP_FILE}" EXIT

# Search for each stub pattern
for pattern in "${STUB_PATTERNS[@]}"; do
    if [ ${VERBOSE} -eq 1 ]; then
        echo "Searching for pattern: ${pattern}"
    fi

    # Use grep to find matches
    # -r: recursive
    # -n: line numbers
    # -i: case insensitive
    # --color=always: colored output
    # -E: extended regex

    # Build exclude arguments dynamically
    EXCLUDE_ARGS=""
    for exclude in "${EXCLUDE_PATTERNS[@]}"; do
        EXCLUDE_ARGS="${EXCLUDE_ARGS} --exclude=${exclude}"
    done

    # Search for pattern
    if grep -rniE "${pattern}" "${SRC_DIR}" \
        --exclude-dir=tests \
        --exclude-dir=test \
        --exclude-dir=__pycache__ \
        --exclude-dir=.pytest_cache \
        --exclude-dir=docs \
        --exclude-dir=examples \
        --exclude='test_*.py' \
        --exclude='*_test.py' \
        --exclude='*.pyc' \
        --color=always \
        >> "${TEMP_FILE}" 2>/dev/null; then
        STUBS_FOUND=$((STUBS_FOUND + 1))
    fi
done

# Check results
if [ -s "${TEMP_FILE}" ]; then
    echo -e "${RED}✗ STUB IMPLEMENTATIONS DETECTED${NC}"
    echo ""
    echo "The following stub implementations were found in production code:"
    echo ""
    cat "${TEMP_FILE}"
    echo ""
    echo -e "${YELLOW}Action Required:${NC}"
    echo "1. Replace stub implementations with real code"
    echo "2. If this is intentional, add to STUB_IMPLEMENTATIONS_REGISTRY.md"
    echo "3. Remove stub patterns from production code"
    echo ""
    echo -e "${RED}Total patterns matched: ${STUBS_FOUND}${NC}"
    exit 1
else
    echo -e "${GREEN}✓ No stub implementations detected${NC}"
    echo ""
    echo "All checks passed. Production code is stub-free."
    exit 0
fi
