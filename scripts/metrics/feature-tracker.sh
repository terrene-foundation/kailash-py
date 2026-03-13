#!/bin/bash

# Feature Development Tracker for Kailash Python SDK
# Tracks feature PRs, branches, and development lifecycle
# Usage: ./feature-tracker.sh [start_date] [end_date]

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
CYAN='\033[0;36m'
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

echo -e "${PURPLE}=== Feature Development Tracker ===${NC}"
echo -e "Repository: ${YELLOW}$REPO${NC}"
echo -e "Period: ${GREEN}$START_DATE${NC} to ${GREEN}$END_DATE${NC}"
echo ""

# Get feature PRs
echo -e "${BLUE}🚀 Feature Pull Requests${NC}"

FEATURE_PRS=$(gh pr list \
    --repo "$REPO" \
    --state all \
    --search "created:${START_DATE}..${END_DATE}" \
    --json number,title,state,mergedAt,createdAt,author,labels,additions,deletions \
    --limit 1000)

# Filter and analyze feature PRs
TOTAL_FEATURES=0
MERGED_FEATURES=0
OPEN_FEATURES=0
CLOSED_FEATURES=0
TOTAL_ADDITIONS=0
TOTAL_DELETIONS=0

echo "$FEATURE_PRS" | jq -c '.[]' 2>/dev/null | while read pr; do
    TITLE=$(echo "$pr" | jq -r '.title')
    STATE=$(echo "$pr" | jq -r '.state')

    # Check if it's a feature PR
    if [[ "$TITLE" =~ ^feat:|^feature: ]] || echo "$pr" | grep -q '"name":"feature"' || echo "$pr" | grep -q '"name":"enhancement"'; then
        TOTAL_FEATURES=$((TOTAL_FEATURES + 1))

        if [ "$STATE" = "MERGED" ]; then
            MERGED_FEATURES=$((MERGED_FEATURES + 1))
        elif [ "$STATE" = "OPEN" ]; then
            OPEN_FEATURES=$((OPEN_FEATURES + 1))
        else
            CLOSED_FEATURES=$((CLOSED_FEATURES + 1))
        fi

        # Track size
        ADD=$(echo "$pr" | jq -r '.additions // 0')
        DEL=$(echo "$pr" | jq -r '.deletions // 0')
        TOTAL_ADDITIONS=$((TOTAL_ADDITIONS + ADD))
        TOTAL_DELETIONS=$((TOTAL_DELETIONS + DEL))
    fi
done

echo -e "├─ Total feature PRs: ${GREEN}$TOTAL_FEATURES${NC}"
echo -e "├─ Merged: ${GREEN}$MERGED_FEATURES${NC}"
echo -e "├─ Still open: ${YELLOW}$OPEN_FEATURES${NC}"
echo -e "├─ Closed without merge: ${RED}$CLOSED_FEATURES${NC}"
echo -e "├─ Total additions: ${GREEN}+$TOTAL_ADDITIONS${NC}"
echo -e "└─ Total deletions: ${RED}-$TOTAL_DELETIONS${NC}"
echo ""

# Feature branches analysis
echo -e "${BLUE}🌿 Feature Branches${NC}"

cd "$REPO_PATH"

# Get all branches that start with feat/ or feature/
FEATURE_BRANCHES=$(git branch -r | grep -E "origin/(feat|feature)/" | sed 's/origin\///')
ACTIVE_BRANCHES=0
STALE_BRANCHES=0

if [ -n "$FEATURE_BRANCHES" ]; then
    echo "$FEATURE_BRANCHES" | while read branch; do
        # Get last commit date
        LAST_COMMIT=$(git log -1 --format="%ai" "origin/$branch" 2>/dev/null || echo "")
        if [ -n "$LAST_COMMIT" ]; then
            LAST_COMMIT_DATE=$(echo "$LAST_COMMIT" | cut -d' ' -f1)

            # Check if branch is active (committed to in last 7 days)
            SEVEN_DAYS_AGO=$(date -v-7d +%Y-%m-%d)
            if [[ "$LAST_COMMIT_DATE" > "$SEVEN_DAYS_AGO" ]]; then
                ACTIVE_BRANCHES=$((ACTIVE_BRANCHES + 1))
                echo -e "   ${GREEN}✓${NC} $branch (last commit: $LAST_COMMIT_DATE)"
            else
                STALE_BRANCHES=$((STALE_BRANCHES + 1))
                echo -e "   ${YELLOW}⚠${NC} $branch (stale - last commit: $LAST_COMMIT_DATE)"
            fi
        fi
    done
fi

echo ""
echo -e "Active branches: ${GREEN}$ACTIVE_BRANCHES${NC}"
echo -e "Stale branches: ${YELLOW}$STALE_BRANCHES${NC}"
echo ""

# Feature development timeline
echo -e "${BLUE}📅 Feature Development Timeline${NC}"

# Get merged features with timeline
echo "$FEATURE_PRS" | jq -r --arg start "$START_DATE" --arg end "$END_DATE" '
    .[] |
    select(.state == "MERGED") |
    select(.title | test("^(feat|feature):"; "i")) |
    {
        number,
        title: (.title | .[0:60] + if length > 60 then "..." else "" end),
        created: .createdAt[0:10],
        merged: .mergedAt[0:10],
        author: .author.login,
        days: (((.mergedAt | fromdateiso8601) - (.createdAt | fromdateiso8601)) / 86400 | floor)
    } |
    "PR #\(.number): \(.title)\n   Created: \(.created) → Merged: \(.merged) (\(.days) days) by @\(.author)"
' 2>/dev/null | head -10

echo ""

# Feature categories (based on PR labels and titles)
echo -e "${BLUE}📊 Feature Categories${NC}"

API_FEATURES=$(echo "$FEATURE_PRS" | jq '[.[] | select(.title | test("api|endpoint|rest"; "i"))] | length' 2>/dev/null || echo 0)
UI_FEATURES=$(echo "$FEATURE_PRS" | jq '[.[] | select(.title | test("ui|frontend|studio"; "i"))] | length' 2>/dev/null || echo 0)
NODE_FEATURES=$(echo "$FEATURE_PRS" | jq '[.[] | select(.title | test("node|component"; "i"))] | length' 2>/dev/null || echo 0)
WORKFLOW_FEATURES=$(echo "$FEATURE_PRS" | jq '[.[] | select(.title | test("workflow|flow"; "i"))] | length' 2>/dev/null || echo 0)
INTEGRATION_FEATURES=$(echo "$FEATURE_PRS" | jq '[.[] | select(.title | test("integration|mcp|agent"; "i"))] | length' 2>/dev/null || echo 0)

echo -e "├─ API/Backend: ${GREEN}$API_FEATURES${NC}"
echo -e "├─ UI/Frontend: ${GREEN}$UI_FEATURES${NC}"
echo -e "├─ Nodes/Components: ${GREEN}$NODE_FEATURES${NC}"
echo -e "├─ Workflow Engine: ${GREEN}$WORKFLOW_FEATURES${NC}"
echo -e "└─ Integrations: ${GREEN}$INTEGRATION_FEATURES${NC}"
echo ""

# Feature velocity
echo -e "${BLUE}⚡ Feature Velocity${NC}"

# Calculate weekly velocity
WEEKS=$(( ($(date -j -f "%Y-%m-%d" "$END_DATE" +%s) - $(date -j -f "%Y-%m-%d" "$START_DATE" +%s)) / 604800 + 1 ))
AVG_FEATURES_PER_WEEK=$(echo "scale=1; $MERGED_FEATURES / $WEEKS" | bc 2>/dev/null || echo "0")

echo -e "Period: $WEEKS weeks"
echo -e "Average features merged per week: ${GREEN}$AVG_FEATURES_PER_WEEK${NC}"
echo ""

# Top feature contributors
echo -e "${BLUE}👥 Top Feature Contributors${NC}"
echo "$FEATURE_PRS" | jq -r '.[] | select(.state == "MERGED") | select(.title | test("^(feat|feature):"; "i")) | .author.login' 2>/dev/null | sort | uniq -c | sort -rn | head -5 | while read count author; do
    echo -e "   ${GREEN}$count${NC} features - $author"
done
echo ""

# Generate feature report
REPORT_DIR="$REPO_PATH/scripts/metrics/reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/feature_report_${START_DATE}_to_${END_DATE}.json"

cat > "$REPORT_FILE" << EOF
{
  "period": {
    "start": "$START_DATE",
    "end": "$END_DATE"
  },
  "summary": {
    "total_feature_prs": $TOTAL_FEATURES,
    "merged": $MERGED_FEATURES,
    "open": $OPEN_FEATURES,
    "closed_without_merge": $CLOSED_FEATURES,
    "total_additions": $TOTAL_ADDITIONS,
    "total_deletions": $TOTAL_DELETIONS
  },
  "categories": {
    "api_backend": $API_FEATURES,
    "ui_frontend": $UI_FEATURES,
    "nodes_components": $NODE_FEATURES,
    "workflow_engine": $WORKFLOW_FEATURES,
    "integrations": $INTEGRATION_FEATURES
  },
  "velocity": {
    "weeks": $WEEKS,
    "average_per_week": $AVG_FEATURES_PER_WEEK
  },
  "branches": {
    "active": $ACTIVE_BRANCHES,
    "stale": $STALE_BRANCHES
  }
}
EOF

echo -e "${GREEN}Report saved to: $REPORT_FILE${NC}"
