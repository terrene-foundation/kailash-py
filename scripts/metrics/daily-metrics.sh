#!/bin/bash

# Daily Metrics Tracker for Kailash Python SDK
# Tracks today's metrics and compares with yesterday
# Usage: ./daily-metrics.sh

set -e

# Repository configuration
REPO="terrene-foundation/kailash-py"
REPO_PATH=""

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Dates
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d)

echo -e "${BLUE}=== Daily Metrics Report ===${NC}"
echo -e "Date: ${YELLOW}$TODAY${NC}"
echo ""

# Function to get PR count for a specific date
get_pr_count() {
    local date=$1
    gh pr list \
        --repo "$REPO" \
        --state merged \
        --search "merged:${date}..${date}" \
        --json number \
        --limit 100 | jq 'length' 2>/dev/null || echo "0"
}

# Function to get issue count for a specific date
get_issue_count() {
    local date=$1
    gh issue list \
        --repo "$REPO" \
        --state closed \
        --search "closed:${date}..${date}" \
        --json number \
        --limit 100 | jq 'length' 2>/dev/null || echo "0"
}

# Today's metrics
echo -e "${BLUE}Today's Activity:${NC}"

# PRs merged today
TODAY_PRS=$(get_pr_count "$TODAY")
echo -e "- Pull Requests Merged: ${GREEN}$TODAY_PRS${NC}"

# Issues closed today
TODAY_ISSUES=$(get_issue_count "$TODAY")
echo -e "- Issues Closed: ${GREEN}$TODAY_ISSUES${NC}"

# Commits today
cd "$REPO_PATH"
TODAY_COMMITS=$(git log --since="$TODAY 00:00:00" --until="$TODAY 23:59:59" --oneline | wc -l | tr -d ' ')
echo -e "- Commits: ${GREEN}$TODAY_COMMITS${NC}"

# Active contributors today
TODAY_CONTRIBUTORS=$(git log --since="$TODAY 00:00:00" --until="$TODAY 23:59:59" --format="%an" | sort -u | wc -l | tr -d ' ')
echo -e "- Active Contributors: ${GREEN}$TODAY_CONTRIBUTORS${NC}"

echo ""

# Comparison with yesterday
echo -e "${BLUE}Comparison with Yesterday:${NC}"

YESTERDAY_PRS=$(get_pr_count "$YESTERDAY")
YESTERDAY_ISSUES=$(get_issue_count "$YESTERDAY")
YESTERDAY_COMMITS=$(git log --since="$YESTERDAY 00:00:00" --until="$YESTERDAY 23:59:59" --oneline | wc -l | tr -d ' ')

# Calculate differences
PR_DIFF=$((TODAY_PRS - YESTERDAY_PRS))
ISSUE_DIFF=$((TODAY_ISSUES - YESTERDAY_ISSUES))
COMMIT_DIFF=$((TODAY_COMMITS - YESTERDAY_COMMITS))

# Display with appropriate colors
display_diff() {
    local name=$1
    local today=$2
    local yesterday=$3
    local diff=$4

    if [ $diff -gt 0 ]; then
        echo -e "- $name: $today (${GREEN}+$diff${NC} from yesterday's $yesterday)"
    elif [ $diff -lt 0 ]; then
        echo -e "- $name: $today (${RED}$diff${NC} from yesterday's $yesterday)"
    else
        echo -e "- $name: $today (${YELLOW}same as yesterday${NC})"
    fi
}

display_diff "Pull Requests" "$TODAY_PRS" "$YESTERDAY_PRS" "$PR_DIFF"
display_diff "Issues Closed" "$TODAY_ISSUES" "$YESTERDAY_ISSUES" "$ISSUE_DIFF"
display_diff "Commits" "$TODAY_COMMITS" "$YESTERDAY_COMMITS" "$COMMIT_DIFF"

echo ""

# Recent activity details
echo -e "${BLUE}Recent Activity Details:${NC}"

# Last 5 commits
echo "Last 5 commits today:"
git log --since="$TODAY 00:00:00" --until="$TODAY 23:59:59" --oneline --format="  - %h: %s (%an)" | head -5

echo ""

# Files changed today
FILES_CHANGED=$(git log --since="$TODAY 00:00:00" --until="$TODAY 23:59:59" --name-only --pretty=format: | sort -u | grep -v "^$" | wc -l | tr -d ' ')
echo -e "Files changed today: ${GREEN}$FILES_CHANGED${NC}"

# Test files changed
TEST_FILES=$(git log --since="$TODAY 00:00:00" --until="$TODAY 23:59:59" --name-only --pretty=format: | grep -E "(test_.*\.py|.*_test\.py|tests/.*\.py)" | sort -u | wc -l | tr -d ' ')
echo -e "Test files changed: ${GREEN}$TEST_FILES${NC}"

# Documentation files changed
DOC_FILES=$(git log --since="$TODAY 00:00:00" --until="$TODAY 23:59:59" --name-only --pretty=format: | grep -E "\.(md|rst|txt)$|docs/|guide/" | sort -u | wc -l | tr -d ' ')
echo -e "Documentation files changed: ${GREEN}$DOC_FILES${NC}"

# Save daily metrics to log file
LOG_DIR="$REPO_PATH/scripts/metrics/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_metrics.csv"

# Create header if file doesn't exist
if [ ! -f "$LOG_FILE" ]; then
    echo "date,prs_merged,issues_closed,commits,contributors,files_changed,test_files,doc_files" > "$LOG_FILE"
fi

# Append today's metrics
echo "$TODAY,$TODAY_PRS,$TODAY_ISSUES,$TODAY_COMMITS,$TODAY_CONTRIBUTORS,$FILES_CHANGED,$TEST_FILES,$DOC_FILES" >> "$LOG_FILE"

echo ""
echo -e "${GREEN}Metrics saved to: $LOG_FILE${NC}"
