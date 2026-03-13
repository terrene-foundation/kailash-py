#!/bin/bash

# Test Coverage Tracker for Kailash Python SDK
# Tracks test file changes and coverage metrics
# Usage: ./test-coverage-tracker.sh [start_date] [end_date]

set -e

# Repository configuration
REPO="terrene-foundation/kailash-py"
REPO_PATH=""

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Default date range (last 30 days if not specified)
if [ -z "$1" ]; then
    START_DATE=$(date -v-30d +%Y-%m-%d)
else
    START_DATE="$1"
fi

if [ -z "$2" ]; then
    END_DATE=$(date +%Y-%m-%d)
else
    END_DATE="$2"
fi

cd "$REPO_PATH"

echo -e "${PURPLE}=== Test Coverage Analysis ===${NC}"
echo -e "Period: ${GREEN}$START_DATE${NC} to ${GREEN}$END_DATE${NC}"
echo ""

# Function to analyze test files
analyze_test_files() {
    local file=$1
    local additions=0
    local deletions=0
    local test_count=0

    # Count test methods (functions starting with test_)
    if [ -f "$file" ]; then
        test_count=$(grep -c "^[[:space:]]*def test_" "$file" 2>/dev/null || echo "0")
    fi

    # Get line changes
    STATS=$(git log --since="$START_DATE" --until="$END_DATE" --numstat --follow -- "$file" 2>/dev/null | awk '{added+=$1; deleted+=$2} END {print added, deleted}')
    if [ -n "$STATS" ]; then
        additions=$(echo "$STATS" | awk '{print $1}')
        deletions=$(echo "$STATS" | awk '{print $2}')
    fi

    echo "$additions $deletions $test_count"
}

# Get all test files changed in the period
echo -e "${BLUE}📊 Test File Analysis${NC}"

TEST_FILES=$(git log \
    --since="$START_DATE" \
    --until="$END_DATE" \
    --pretty=format:"%H" \
    --all | while read commit; do
    git diff-tree --no-commit-id --name-only -r "$commit" | grep -E "(test_.*\.py|.*_test\.py|tests/.*\.py)" || true
done | sort -u)

TOTAL_TEST_FILES=0
TOTAL_ADDITIONS=0
TOTAL_DELETIONS=0
NEW_TEST_FILES=0
MODIFIED_TEST_FILES=0

# Analyze each test file
while IFS= read -r file; do
    if [ -n "$file" ]; then
        TOTAL_TEST_FILES=$((TOTAL_TEST_FILES + 1))

        # Check if file is new
        FILE_CREATED=$(git log --follow --format=%aD --reverse -- "$file" 2>/dev/null | head -1)
        if [ -n "$FILE_CREATED" ]; then
            CREATED_DATE=$(date -j -f "%a, %d %b %Y %H:%M:%S %z" "$FILE_CREATED" +%Y-%m-%d 2>/dev/null || echo "")
            if [[ "$CREATED_DATE" > "$START_DATE" ]] || [[ "$CREATED_DATE" == "$START_DATE" ]]; then
                NEW_TEST_FILES=$((NEW_TEST_FILES + 1))
            else
                MODIFIED_TEST_FILES=$((MODIFIED_TEST_FILES + 1))
            fi
        fi

        # Get changes
        ANALYSIS=$(analyze_test_files "$file")
        ADD=$(echo "$ANALYSIS" | awk '{print $1}')
        DEL=$(echo "$ANALYSIS" | awk '{print $2}')
        TESTS=$(echo "$ANALYSIS" | awk '{print $3}')

        TOTAL_ADDITIONS=$((TOTAL_ADDITIONS + ${ADD:-0}))
        TOTAL_DELETIONS=$((TOTAL_DELETIONS + ${DEL:-0}))
    fi
done <<< "$TEST_FILES"

echo -e "├─ Total test files changed: ${GREEN}$TOTAL_TEST_FILES${NC}"
echo -e "├─ New test files created: ${GREEN}$NEW_TEST_FILES${NC}"
echo -e "├─ Existing files modified: ${GREEN}$MODIFIED_TEST_FILES${NC}"
echo -e "├─ Lines added: ${GREEN}+$TOTAL_ADDITIONS${NC}"
echo -e "├─ Lines removed: ${RED}-$TOTAL_DELETIONS${NC}"
echo -e "└─ Net change: ${YELLOW}$((TOTAL_ADDITIONS - TOTAL_DELETIONS)) lines${NC}"
echo ""

# Test categories
echo -e "${BLUE}🗂️  Test Categories${NC}"

UNIT_TESTS=$(echo "$TEST_FILES" | grep -E "test_[^/]+\.py$" | grep -v "integration" | wc -l | tr -d ' ')
INTEGRATION_TESTS=$(echo "$TEST_FILES" | grep -E "integration|test_.*integration.*\.py" | wc -l | tr -d ' ')
NODE_TESTS=$(echo "$TEST_FILES" | grep "test_nodes/" | wc -l | tr -d ' ')
WORKFLOW_TESTS=$(echo "$TEST_FILES" | grep "test_workflow/" | wc -l | tr -d ' ')
API_TESTS=$(echo "$TEST_FILES" | grep "test_api/" | wc -l | tr -d ' ')

echo -e "├─ Unit tests: ${GREEN}$UNIT_TESTS${NC}"
echo -e "├─ Integration tests: ${GREEN}$INTEGRATION_TESTS${NC}"
echo -e "├─ Node tests: ${GREEN}$NODE_TESTS${NC}"
echo -e "├─ Workflow tests: ${GREEN}$WORKFLOW_TESTS${NC}"
echo -e "└─ API tests: ${GREEN}$API_TESTS${NC}"
echo ""

# Test commits analysis
echo -e "${BLUE}📝 Test-Related Commits${NC}"

TEST_COMMITS=$(git log --since="$START_DATE" --until="$END_DATE" --grep="test" -i --oneline)
TEST_COMMIT_COUNT=$(echo "$TEST_COMMITS" | grep -v "^$" | wc -l | tr -d ' ')
FIX_COMMITS=$(echo "$TEST_COMMITS" | grep -i "fix.*test" | wc -l | tr -d ' ')
ADD_COMMITS=$(echo "$TEST_COMMITS" | grep -iE "add.*test|new.*test" | wc -l | tr -d ' ')

echo -e "├─ Total test commits: ${GREEN}$TEST_COMMIT_COUNT${NC}"
echo -e "├─ Test additions: ${GREEN}$ADD_COMMITS${NC}"
echo -e "└─ Test fixes: ${YELLOW}$FIX_COMMITS${NC}"
echo ""

# Top test contributors
echo -e "${BLUE}👥 Top Test Contributors${NC}"
git log --since="$START_DATE" --until="$END_DATE" --format="%an" -- "tests/" "test_*.py" 2>/dev/null | sort | uniq -c | sort -rn | head -5 | while read count author; do
    echo -e "   ${GREEN}$count${NC} commits - $author"
done
echo ""

# Recent test files
echo -e "${BLUE}📄 Recently Modified Test Files${NC}"
echo "$TEST_FILES" | grep -v "^$" | head -10 | while read file; do
    if [ -f "$file" ]; then
        TEST_COUNT=$(grep -c "^[[:space:]]*def test_" "$file" 2>/dev/null || echo "0")
        echo -e "   $file (${GREEN}$TEST_COUNT tests${NC})"
    else
        echo -e "   $file (${RED}deleted${NC})"
    fi
done

if [ $(echo "$TEST_FILES" | grep -v "^$" | wc -l) -gt 10 ]; then
    echo "   ... and $(($(echo "$TEST_FILES" | grep -v "^$" | wc -l) - 10)) more files"
fi
echo ""

# Coverage trend (if pytest-cov is available)
if command -v pytest &> /dev/null && [ -f "pytest.ini" ]; then
    echo -e "${BLUE}📈 Coverage Check${NC}"
    echo "Running coverage analysis..."

    # Try to run coverage
    if pytest --cov=src/kailash --cov-report=term-missing --no-header -q 2>/dev/null | grep "TOTAL"; then
        echo "Coverage report generated successfully"
    else
        echo "Coverage analysis not available"
    fi
    echo ""
fi

# Summary report
REPORT_DIR="$REPO_PATH/scripts/metrics/reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/test_coverage_${START_DATE}_to_${END_DATE}.json"

cat > "$REPORT_FILE" << EOF
{
  "period": {
    "start": "$START_DATE",
    "end": "$END_DATE"
  },
  "summary": {
    "total_test_files_changed": $TOTAL_TEST_FILES,
    "new_test_files": $NEW_TEST_FILES,
    "modified_test_files": $MODIFIED_TEST_FILES,
    "lines_added": $TOTAL_ADDITIONS,
    "lines_removed": $TOTAL_DELETIONS,
    "net_change": $((TOTAL_ADDITIONS - TOTAL_DELETIONS))
  },
  "categories": {
    "unit_tests": $UNIT_TESTS,
    "integration_tests": $INTEGRATION_TESTS,
    "node_tests": $NODE_TESTS,
    "workflow_tests": $WORKFLOW_TESTS,
    "api_tests": $API_TESTS
  },
  "commits": {
    "total_test_commits": $TEST_COMMIT_COUNT,
    "test_additions": $ADD_COMMITS,
    "test_fixes": $FIX_COMMITS
  }
}
EOF

echo -e "${GREEN}Report saved to: $REPORT_FILE${NC}"
