#!/bin/bash
#
# Stub Registry Validator
#
# Ensures STUB_IMPLEMENTATIONS_REGISTRY.md is synchronized with actual code.
# Validates that:
#   1. All listed stubs exist in code
#   2. All stubs in code are listed in registry
#   3. Registry format is correct
#
# Exit Codes:
#   0 - Registry is valid and synchronized
#   1 - Registry validation failed or mismatches found
#
# Usage:
#   ./scripts/validate_stub_registry.sh

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${PROJECT_ROOT}/src"
REGISTRY_FILE="${PROJECT_ROOT}/STUB_IMPLEMENTATIONS_REGISTRY.md"

# Color output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Stub Registry Validator ===${NC}"
echo ""

# Check if registry file exists
if [ ! -f "${REGISTRY_FILE}" ]; then
    echo -e "${YELLOW}WARNING: Registry file not found: ${REGISTRY_FILE}${NC}"
    echo ""
    echo "Creating stub registry template..."

    cat > "${REGISTRY_FILE}" << 'EOF'
# Stub Implementations Registry

This file tracks intentional stub implementations that are allowed in production code.
All stubs must be documented here with justification and planned completion date.

## Registry Format

Each stub entry must include:
- **File**: Full path to file containing stub
- **Line**: Line number(s) of stub implementation
- **Function/Class**: Name of stubbed function or class
- **Reason**: Why this stub is necessary
- **Planned Completion**: Target date for real implementation
- **Tracking Issue**: Link to GitHub issue/task

## Active Stubs

<!-- Add stub entries below in this format:

### Stub: FunctionName
- **File**: `src/module/file.py`
- **Line**: 123-145
- **Function/Class**: `ClassName.method_name`
- **Reason**: Feature not yet implemented, blocked by dependency X
- **Planned Completion**: 2025-01-15
- **Tracking Issue**: #123

-->

## Completed Stubs

<!-- Move completed stubs here for audit trail -->

EOF

    echo -e "${GREEN}✓ Created registry template: ${REGISTRY_FILE}${NC}"
    echo ""
    echo "Registry is empty. Add stub entries as needed."
    exit 0
fi

echo "Registry file: ${REGISTRY_FILE}"
echo "Source directory: ${SRC_DIR}"
echo ""

# Validation flags
VALIDATION_ERRORS=0
WARNINGS=0

# Temporary files
REGISTRY_STUBS=$(mktemp)
CODE_STUBS=$(mktemp)
trap "rm -f ${REGISTRY_STUBS} ${CODE_STUBS}" EXIT

# Extract stub entries from registry
# Look for File: entries in the registry
echo -e "${BLUE}Step 1: Extracting stub entries from registry...${NC}"
if grep -E "^- \*\*File\*\*:" "${REGISTRY_FILE}" | sed 's/.*`\(.*\)`.*/\1/' > "${REGISTRY_STUBS}"; then
    REGISTRY_COUNT=$(wc -l < "${REGISTRY_STUBS}" | tr -d ' ')
    echo "Found ${REGISTRY_COUNT} stub entries in registry"
else
    REGISTRY_COUNT=0
    echo "No stub entries found in registry"
fi

# Search for stub patterns in code
echo ""
echo -e "${BLUE}Step 2: Searching for stubs in code...${NC}"

# Stub patterns to detect
declare -a STUB_PATTERNS=(
    "# STUB implementation"
    "# stub:"
    "# placeholder:"
    "pass  # stub"
    "return {}  # stub"
    "return \[\]  # stub"
    "return None  # stub"
)

# Find all Python files, excluding tests
find "${SRC_DIR}" -type f -name "*.py" \
    ! -path "*/tests/*" \
    ! -path "*/test_*" \
    ! -name "*_test.py" \
    ! -path "*/__pycache__/*" \
    ! -path "*/.pytest_cache/*" \
    > "${CODE_STUBS}"

CODE_FILES_COUNT=$(wc -l < "${CODE_STUBS}" | tr -d ' ')
echo "Scanning ${CODE_FILES_COUNT} source files..."

# Check each file for stub patterns
STUBS_IN_CODE=0
declare -a FOUND_STUBS=()

while IFS= read -r file; do
    for pattern in "${STUB_PATTERNS[@]}"; do
        if grep -qiE "${pattern}" "${file}" 2>/dev/null; then
            STUBS_IN_CODE=$((STUBS_IN_CODE + 1))
            RELATIVE_PATH="${file#${PROJECT_ROOT}/}"
            FOUND_STUBS+=("${RELATIVE_PATH}")
            break  # Only count file once
        fi
    done
done < "${CODE_STUBS}"

echo "Found ${STUBS_IN_CODE} files with stub patterns in code"

# Cross-reference validation
echo ""
echo -e "${BLUE}Step 3: Cross-referencing registry with code...${NC}"

# Check if stubs in registry actually exist in code
if [ ${REGISTRY_COUNT} -gt 0 ]; then
    echo "Validating registry entries exist in code..."

    while IFS= read -r registered_file; do
        FULL_PATH="${PROJECT_ROOT}/${registered_file}"

        if [ ! -f "${FULL_PATH}" ]; then
            echo -e "  ${RED}✗ File not found: ${registered_file}${NC}"
            VALIDATION_ERRORS=$((VALIDATION_ERRORS + 1))
        else
            # Check if file actually contains stub patterns
            CONTAINS_STUB=0
            for pattern in "${STUB_PATTERNS[@]}"; do
                if grep -qiE "${pattern}" "${FULL_PATH}" 2>/dev/null; then
                    CONTAINS_STUB=1
                    break
                fi
            done

            if [ ${CONTAINS_STUB} -eq 0 ]; then
                echo -e "  ${YELLOW}⚠ No stub found in registered file: ${registered_file}${NC}"
                WARNINGS=$((WARNINGS + 1))
            else
                echo -e "  ${GREEN}✓ Verified: ${registered_file}${NC}"
            fi
        fi
    done < "${REGISTRY_STUBS}"
fi

# Check if stubs in code are registered
if [ ${STUBS_IN_CODE} -gt 0 ]; then
    echo ""
    echo "Checking for unregistered stubs..."

    for stub_file in "${FOUND_STUBS[@]}"; do
        if ! grep -qF "${stub_file}" "${REGISTRY_FILE}"; then
            echo -e "  ${RED}✗ Unregistered stub: ${stub_file}${NC}"
            VALIDATION_ERRORS=$((VALIDATION_ERRORS + 1))
        fi
    done
fi

# Validate registry format
echo ""
echo -e "${BLUE}Step 4: Validating registry format...${NC}"

# Check for required sections
if ! grep -q "## Active Stubs" "${REGISTRY_FILE}"; then
    echo -e "  ${RED}✗ Missing required section: ## Active Stubs${NC}"
    VALIDATION_ERRORS=$((VALIDATION_ERRORS + 1))
fi

if ! grep -q "## Completed Stubs" "${REGISTRY_FILE}"; then
    echo -e "  ${YELLOW}⚠ Missing recommended section: ## Completed Stubs${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# Check for stub entries with proper format
STUB_ENTRIES=$(grep -c "^### Stub:" "${REGISTRY_FILE}" || echo "0")
echo "Found ${STUB_ENTRIES} properly formatted stub entries"

if [ ${STUB_ENTRIES} -ne ${REGISTRY_COUNT} ] && [ ${REGISTRY_COUNT} -gt 0 ]; then
    echo -e "  ${YELLOW}⚠ Stub count mismatch: ${STUB_ENTRIES} formatted entries vs ${REGISTRY_COUNT} file references${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# Final report
echo ""
echo -e "${GREEN}=== Validation Summary ===${NC}"
echo ""
echo "Registry entries: ${REGISTRY_COUNT}"
echo "Stubs in code: ${STUBS_IN_CODE}"
echo "Validation errors: ${VALIDATION_ERRORS}"
echo "Warnings: ${WARNINGS}"
echo ""

if [ ${VALIDATION_ERRORS} -gt 0 ]; then
    echo -e "${RED}✗ VALIDATION FAILED${NC}"
    echo ""
    echo "Action required:"
    echo "1. Register all stub implementations in ${REGISTRY_FILE}"
    echo "2. Remove or fix stale registry entries"
    echo "3. Ensure all stubs have proper documentation"
    exit 1
elif [ ${WARNINGS} -gt 0 ]; then
    echo -e "${YELLOW}⚠ VALIDATION PASSED WITH WARNINGS${NC}"
    echo ""
    echo "Consider addressing warnings for better registry maintenance."
    exit 0
else
    echo -e "${GREEN}✓ VALIDATION PASSED${NC}"
    echo ""
    echo "Registry is synchronized with code."
    exit 0
fi
