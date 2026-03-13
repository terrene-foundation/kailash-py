#!/bin/bash

# GitHub Metrics Tracking Script for Kailash Python SDK
# Usage: ./github-metrics.sh [start_date] [end_date]
# Example: ./github-metrics.sh "2024-01-01" "2024-01-31"

set -e

# Repository configuration
REPO="terrene-foundation/kailash-py"
REPO_PATH=""

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default date range (last 7 days if not specified)
if [ -z "$1" ]; then
    START_DATE=$(date -v-7d +%Y-%m-%d)
else
    START_DATE="$1"
fi

if [ -z "$2" ]; then
    END_DATE=$(date +%Y-%m-%d)
else
    END_DATE="$2"
fi

echo -e "${BLUE}=== GitHub Metrics Report ===${NC}"
echo -e "Repository: ${YELLOW}$REPO${NC}"
echo -e "Period: ${GREEN}$START_DATE${NC} to ${GREEN}$END_DATE${NC}"
echo ""

# Function to format JSON output
format_json() {
    if command -v jq &> /dev/null; then
        jq -r "$1"
    else
        cat
    fi
}

# 1. Features Completed (PRs with feat: prefix or feature labels)
echo -e "${BLUE}1. Features Completed${NC}"
echo "   Analyzing merged pull requests..."

# Get merged PRs in date range
MERGED_PRS=$(gh pr list \
    --repo "$REPO" \
    --state merged \
    --search "merged:${START_DATE}..${END_DATE}" \
    --json number,title,mergedAt,author,labels \
    --limit 1000)

# Count feature PRs
FEATURE_COUNT=0
FEATURE_DETAILS=""

if [ -n "$MERGED_PRS" ] && [ "$MERGED_PRS" != "[]" ]; then
    while IFS= read -r pr; do
        TITLE=$(echo "$pr" | format_json '.title')
        NUMBER=$(echo "$pr" | format_json '.number')
        AUTHOR=$(echo "$pr" | format_json '.author.login')
        MERGED_AT=$(echo "$pr" | format_json '.mergedAt')

        # Check if PR is a feature (feat: prefix or feature label)
        if [[ "$TITLE" =~ ^feat:|^feature: ]] || echo "$pr" | grep -q '"name":"feature"'; then
            FEATURE_COUNT=$((FEATURE_COUNT + 1))
            FEATURE_DETAILS="${FEATURE_DETAILS}   - PR #${NUMBER}: ${TITLE} (by @${AUTHOR})\n"
        fi
    done < <(echo "$MERGED_PRS" | jq -c '.[]' 2>/dev/null || echo "$MERGED_PRS")
fi

echo -e "   ${GREEN}Total Features: $FEATURE_COUNT${NC}"
if [ -n "$FEATURE_DETAILS" ]; then
    echo -e "$FEATURE_DETAILS"
fi
echo ""

# 2. Issues Resolved
echo -e "${BLUE}2. Issues Resolved${NC}"
echo "   Analyzing closed issues..."

# Get closed issues in date range
CLOSED_ISSUES=$(gh issue list \
    --repo "$REPO" \
    --state closed \
    --search "closed:${START_DATE}..${END_DATE}" \
    --json number,title,closedAt,author,labels \
    --limit 1000)

ISSUE_COUNT=0
ISSUE_DETAILS=""

if [ -n "$CLOSED_ISSUES" ] && [ "$CLOSED_ISSUES" != "[]" ]; then
    ISSUE_COUNT=$(echo "$CLOSED_ISSUES" | jq 'length' 2>/dev/null || echo "0")

    # Get top 5 issues
    ISSUE_DETAILS=$(echo "$CLOSED_ISSUES" | jq -r '.[0:5] | .[] | "   - Issue #\(.number): \(.title) (by @\(.author.login))"' 2>/dev/null || echo "")
fi

echo -e "   ${GREEN}Total Issues Resolved: $ISSUE_COUNT${NC}"
if [ -n "$ISSUE_DETAILS" ]; then
    echo "$ISSUE_DETAILS"
    if [ "$ISSUE_COUNT" -gt 5 ]; then
        echo "   ... and $((ISSUE_COUNT - 5)) more"
    fi
fi
echo ""

# 3. Tests Written
echo -e "${BLUE}3. Tests Written${NC}"
echo "   Analyzing test file changes..."

cd "$REPO_PATH"

# Get commits in date range
TEST_STATS=$(git log \
    --since="$START_DATE" \
    --until="$END_DATE" \
    --pretty=format:"%H" \
    --all | while read commit; do
    git diff-tree --no-commit-id --name-only -r "$commit" | grep -E "(test_.*\.py|.*_test\.py|tests/.*\.py)" || true
done | sort | uniq)

TEST_FILES_COUNT=$(echo "$TEST_STATS" | grep -v "^$" | wc -l | tr -d ' ')
TEST_COMMITS=$(git log --since="$START_DATE" --until="$END_DATE" --grep="test" -i --oneline | wc -l | tr -d ' ')

# Get test line changes
TEST_ADDITIONS=0
TEST_DELETIONS=0

while IFS= read -r file; do
    if [ -n "$file" ]; then
        STATS=$(git log --since="$START_DATE" --until="$END_DATE" --numstat --follow -- "$file" 2>/dev/null | awk '{added+=$1; deleted+=$2} END {print added, deleted}')
        if [ -n "$STATS" ]; then
            ADD=$(echo "$STATS" | awk '{print $1}')
            DEL=$(echo "$STATS" | awk '{print $2}')
            TEST_ADDITIONS=$((TEST_ADDITIONS + ${ADD:-0}))
            TEST_DELETIONS=$((TEST_DELETIONS + ${DEL:-0}))
        fi
    fi
done <<< "$TEST_STATS"

echo -e "   ${GREEN}Test Files Modified: $TEST_FILES_COUNT${NC}"
echo -e "   ${GREEN}Test-related Commits: $TEST_COMMITS${NC}"
echo -e "   ${GREEN}Lines Added: +$TEST_ADDITIONS${NC}"
echo -e "   ${RED}Lines Removed: -$TEST_DELETIONS${NC}"
echo -e "   ${YELLOW}Net Change: $((TEST_ADDITIONS - TEST_DELETIONS)) lines${NC}"

# Show top 5 test files
if [ "$TEST_FILES_COUNT" -gt 0 ]; then
    echo "   Top modified test files:"
    echo "$TEST_STATS" | grep -v "^$" | head -5 | while read file; do
        echo "   - $file"
    done
fi
echo ""

# 4. Documentation Updated
echo -e "${BLUE}4. Documentation Updated${NC}"
echo "   Analyzing documentation changes..."

# Get documentation file changes
DOC_STATS=$(git log \
    --since="$START_DATE" \
    --until="$END_DATE" \
    --pretty=format:"%H" \
    --all | while read commit; do
    git diff-tree --no-commit-id --name-only -r "$commit" | grep -E "\.(md|rst|txt)$|docs/|guide/|README" || true
done | sort | uniq)

DOC_FILES_COUNT=$(echo "$DOC_STATS" | grep -v "^$" | wc -l | tr -d ' ')
DOC_COMMITS=$(git log --since="$START_DATE" --until="$END_DATE" --grep="doc" -i --oneline | wc -l | tr -d ' ')

# Get documentation line changes
DOC_ADDITIONS=0
DOC_DELETIONS=0

while IFS= read -r file; do
    if [ -n "$file" ]; then
        STATS=$(git log --since="$START_DATE" --until="$END_DATE" --numstat --follow -- "$file" 2>/dev/null | awk '{added+=$1; deleted+=$2} END {print added, deleted}')
        if [ -n "$STATS" ]; then
            ADD=$(echo "$STATS" | awk '{print $1}')
            DEL=$(echo "$STATS" | awk '{print $2}')
            DOC_ADDITIONS=$((DOC_ADDITIONS + ${ADD:-0}))
            DOC_DELETIONS=$((DOC_DELETIONS + ${DEL:-0}))
        fi
    fi
done <<< "$DOC_STATS"

echo -e "   ${GREEN}Documentation Files Modified: $DOC_FILES_COUNT${NC}"
echo -e "   ${GREEN}Documentation Commits: $DOC_COMMITS${NC}"
echo -e "   ${GREEN}Lines Added: +$DOC_ADDITIONS${NC}"
echo -e "   ${RED}Lines Removed: -$DOC_DELETIONS${NC}"
echo -e "   ${YELLOW}Net Change: $((DOC_ADDITIONS - DOC_DELETIONS)) lines${NC}"

# Show top 5 documentation files
if [ "$DOC_FILES_COUNT" -gt 0 ]; then
    echo "   Top modified documentation files:"
    echo "$DOC_STATS" | grep -v "^$" | head -5 | while read file; do
        echo "   - $file"
    done
fi
echo ""

# Summary
echo -e "${BLUE}=== Summary ===${NC}"
echo -e "Period: $START_DATE to $END_DATE"
echo -e "- Features Completed: ${GREEN}$FEATURE_COUNT${NC}"
echo -e "- Issues Resolved: ${GREEN}$ISSUE_COUNT${NC}"
echo -e "- Test Files Modified: ${GREEN}$TEST_FILES_COUNT${NC} (${YELLOW}+$((TEST_ADDITIONS - TEST_DELETIONS)) lines${NC})"
echo -e "- Documentation Files Modified: ${GREEN}$DOC_FILES_COUNT${NC} (${YELLOW}+$((DOC_ADDITIONS - DOC_DELETIONS)) lines${NC})"

# Export results to JSON if requested
if [ "$3" == "--json" ]; then
    OUTPUT_FILE="metrics_${START_DATE}_to_${END_DATE}.json"
    cat > "$OUTPUT_FILE" << EOF
{
  "repository": "$REPO",
  "period": {
    "start": "$START_DATE",
    "end": "$END_DATE"
  },
  "metrics": {
    "features_completed": $FEATURE_COUNT,
    "issues_resolved": $ISSUE_COUNT,
    "tests": {
      "files_modified": $TEST_FILES_COUNT,
      "commits": $TEST_COMMITS,
      "lines_added": $TEST_ADDITIONS,
      "lines_removed": $TEST_DELETIONS,
      "net_change": $((TEST_ADDITIONS - TEST_DELETIONS))
    },
    "documentation": {
      "files_modified": $DOC_FILES_COUNT,
      "commits": $DOC_COMMITS,
      "lines_added": $DOC_ADDITIONS,
      "lines_removed": $DOC_DELETIONS,
      "net_change": $((DOC_ADDITIONS - DOC_DELETIONS))
    }
  }
}
EOF
    echo ""
    echo -e "${GREEN}Results exported to: $OUTPUT_FILE${NC}"
fi
