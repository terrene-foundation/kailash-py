#!/bin/bash

# Weekly Summary Report for Kailash Python SDK
# Generates a comprehensive weekly report with trends
# Usage: ./weekly-summary.sh [week_offset]
# Example: ./weekly-summary.sh 0  # This week
#          ./weekly-summary.sh 1  # Last week

set -e

# Repository configuration
REPO="terrene-foundation/kailash-py"
REPO_PATH=""

# Week offset (0 = this week, 1 = last week, etc.)
WEEK_OFFSET=${1:-0}

# Calculate date range
if [ $(uname) = "Darwin" ]; then
    # macOS
    WEEK_START=$(date -v-${WEEK_OFFSET}w -v-sun +%Y-%m-%d)
    WEEK_END=$(date -v-${WEEK_OFFSET}w -v+sat +%Y-%m-%d)
else
    # Linux
    WEEK_START=$(date -d "last sunday - $WEEK_OFFSET weeks" +%Y-%m-%d)
    WEEK_END=$(date -d "last saturday - $((WEEK_OFFSET - 1)) weeks" +%Y-%m-%d)
fi

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${PURPLE}╔════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║       WEEKLY METRICS SUMMARY           ║${NC}"
echo -e "${PURPLE}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "Repository: ${YELLOW}$REPO${NC}"
echo -e "Week: ${GREEN}$WEEK_START${NC} to ${GREEN}$WEEK_END${NC}"
echo ""

# Run the main metrics script for the week
METRICS_OUTPUT=$("$REPO_PATH/scripts/metrics/github-metrics.sh" "$WEEK_START" "$WEEK_END" --json 2>/dev/null || echo "{}")

# Extract key metrics
if [ -n "$METRICS_OUTPUT" ] && [ "$METRICS_OUTPUT" != "{}" ]; then
    FEATURES=$(echo "$METRICS_OUTPUT" | jq -r '.metrics.features_completed // 0' 2>/dev/null || echo "0")
    ISSUES=$(echo "$METRICS_OUTPUT" | jq -r '.metrics.issues_resolved // 0' 2>/dev/null || echo "0")
    TEST_FILES=$(echo "$METRICS_OUTPUT" | jq -r '.metrics.tests.files_modified // 0' 2>/dev/null || echo "0")
    DOC_FILES=$(echo "$METRICS_OUTPUT" | jq -r '.metrics.documentation.files_modified // 0' 2>/dev/null || echo "0")
else
    FEATURES=0
    ISSUES=0
    TEST_FILES=0
    DOC_FILES=0
fi

# Get additional weekly stats
cd "$REPO_PATH"

# Total commits
TOTAL_COMMITS=$(git log --since="$WEEK_START" --until="$WEEK_END" --oneline | wc -l | tr -d ' ')

# Active contributors
CONTRIBUTORS=$(git log --since="$WEEK_START" --until="$WEEK_END" --format="%an" | sort -u)
CONTRIBUTOR_COUNT=$(echo "$CONTRIBUTORS" | grep -v "^$" | wc -l | tr -d ' ')

# Top contributors by commit count
echo -e "${BLUE}📊 Week Overview${NC}"
echo -e "├─ Features Completed: ${GREEN}$FEATURES${NC}"
echo -e "├─ Issues Resolved: ${GREEN}$ISSUES${NC}"
echo -e "├─ Total Commits: ${GREEN}$TOTAL_COMMITS${NC}"
echo -e "├─ Active Contributors: ${GREEN}$CONTRIBUTOR_COUNT${NC}"
echo -e "├─ Test Files Modified: ${GREEN}$TEST_FILES${NC}"
echo -e "└─ Documentation Updated: ${GREEN}$DOC_FILES${NC}"
echo ""

# Daily breakdown
echo -e "${BLUE}📅 Daily Activity${NC}"
for i in {0..6}; do
    if [ $(uname) = "Darwin" ]; then
        DAY=$(date -v-${WEEK_OFFSET}w -v-sun -v+${i}d +%Y-%m-%d)
        DAY_NAME=$(date -v-${WEEK_OFFSET}w -v-sun -v+${i}d +%A)
    else
        DAY=$(date -d "$WEEK_START + $i days" +%Y-%m-%d)
        DAY_NAME=$(date -d "$WEEK_START + $i days" +%A)
    fi

    DAY_COMMITS=$(git log --since="$DAY 00:00:00" --until="$DAY 23:59:59" --oneline 2>/dev/null | wc -l | tr -d ' ')

    # Create visual bar
    BAR=""
    for j in $(seq 1 $((DAY_COMMITS / 2))); do
        BAR="${BAR}█"
    done

    printf "%-10s [%-3s] %s\n" "$DAY_NAME" "$DAY_COMMITS" "$BAR"
done
echo ""

# Top contributors
echo -e "${BLUE}👥 Top Contributors${NC}"
git log --since="$WEEK_START" --until="$WEEK_END" --format="%an" | sort | uniq -c | sort -rn | head -5 | while read count author; do
    echo -e "   ${GREEN}$count${NC} commits - $author"
done
echo ""

# Activity by file type
echo -e "${BLUE}📁 Activity by File Type${NC}"
FILES_CHANGED=$(git log --since="$WEEK_START" --until="$WEEK_END" --name-only --pretty=format: | grep -v "^$")

PY_FILES=$(echo "$FILES_CHANGED" | grep "\.py$" | wc -l | tr -d ' ')
MD_FILES=$(echo "$FILES_CHANGED" | grep "\.md$" | wc -l | tr -d ' ')
YML_FILES=$(echo "$FILES_CHANGED" | grep -E "\.(yml|yaml)$" | wc -l | tr -d ' ')
JSON_FILES=$(echo "$FILES_CHANGED" | grep "\.json$" | wc -l | tr -d ' ')
OTHER_FILES=$(echo "$FILES_CHANGED" | grep -vE "\.(py|md|yml|yaml|json)$" | wc -l | tr -d ' ')

echo -e "├─ Python files: ${GREEN}$PY_FILES${NC}"
echo -e "├─ Markdown files: ${GREEN}$MD_FILES${NC}"
echo -e "├─ YAML files: ${GREEN}$YML_FILES${NC}"
echo -e "├─ JSON files: ${GREEN}$JSON_FILES${NC}"
echo -e "└─ Other files: ${GREEN}$OTHER_FILES${NC}"
echo ""

# Recent PRs and Issues
echo -e "${BLUE}🔄 Recent Pull Requests${NC}"
gh pr list \
    --repo "$REPO" \
    --state merged \
    --search "merged:${WEEK_START}..${WEEK_END}" \
    --json number,title,author \
    --limit 5 | jq -r '.[] | "   PR #\(.number): \(.title) (@\(.author.login))"' 2>/dev/null || echo "   No PRs found"
echo ""

echo -e "${BLUE}✅ Recent Issues Closed${NC}"
gh issue list \
    --repo "$REPO" \
    --state closed \
    --search "closed:${WEEK_START}..${WEEK_END}" \
    --json number,title,author \
    --limit 5 | jq -r '.[] | "   Issue #\(.number): \(.title) (@\(.author.login))"' 2>/dev/null || echo "   No issues found"
echo ""

# Week-over-week comparison
if [ $WEEK_OFFSET -gt 0 ]; then
    echo -e "${BLUE}📈 Week-over-Week Comparison${NC}"

    # Previous week dates
    PREV_WEEK_OFFSET=$((WEEK_OFFSET + 1))
    if [ $(uname) = "Darwin" ]; then
        PREV_WEEK_START=$(date -v-${PREV_WEEK_OFFSET}w -v-sun +%Y-%m-%d)
        PREV_WEEK_END=$(date -v-${PREV_WEEK_OFFSET}w -v+sat +%Y-%m-%d)
    else
        PREV_WEEK_START=$(date -d "last sunday - $PREV_WEEK_OFFSET weeks" +%Y-%m-%d)
        PREV_WEEK_END=$(date -d "last saturday - $((PREV_WEEK_OFFSET - 1)) weeks" +%Y-%m-%d)
    fi

    PREV_COMMITS=$(git log --since="$PREV_WEEK_START" --until="$PREV_WEEK_END" --oneline | wc -l | tr -d ' ')
    COMMIT_CHANGE=$((TOTAL_COMMITS - PREV_COMMITS))

    if [ $COMMIT_CHANGE -gt 0 ]; then
        echo -e "Commits: $TOTAL_COMMITS (${GREEN}+$COMMIT_CHANGE${NC} from previous week)"
    elif [ $COMMIT_CHANGE -lt 0 ]; then
        echo -e "Commits: $TOTAL_COMMITS (${RED}$COMMIT_CHANGE${NC} from previous week)"
    else
        echo -e "Commits: $TOTAL_COMMITS (${YELLOW}same as previous week${NC})"
    fi
fi

# Generate report file
REPORT_DIR="$REPO_PATH/scripts/metrics/reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/weekly_report_${WEEK_START}.md"

cat > "$REPORT_FILE" << EOF
# Weekly Metrics Report

**Repository:** $REPO
**Period:** $WEEK_START to $WEEK_END

## Summary

- **Features Completed:** $FEATURES
- **Issues Resolved:** $ISSUES
- **Total Commits:** $TOTAL_COMMITS
- **Active Contributors:** $CONTRIBUTOR_COUNT
- **Test Files Modified:** $TEST_FILES
- **Documentation Updated:** $DOC_FILES

## File Type Breakdown

- Python files: $PY_FILES
- Markdown files: $MD_FILES
- YAML files: $YML_FILES
- JSON files: $JSON_FILES
- Other files: $OTHER_FILES

## Contributors

$CONTRIBUTORS

---
*Generated on $(date)*
EOF

echo ""
echo -e "${GREEN}📄 Report saved to: $REPORT_FILE${NC}"
