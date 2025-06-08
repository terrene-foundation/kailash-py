#!/bin/bash

# Example usage of GitHub metrics scripts
# This script demonstrates various use cases

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=== GitHub Metrics Examples ===${NC}"
echo ""

# Example 1: Check this week's progress
echo -e "${YELLOW}Example 1: This Week's Progress${NC}"
echo "Command: ./weekly-summary.sh 0"
echo "This shows current week's activity including daily breakdown"
echo ""

# Example 2: Compare two specific weeks
echo -e "${YELLOW}Example 2: Sprint Comparison${NC}"
echo "Sprint 1 (Jan 1-14):"
echo "  ./github-metrics.sh '2024-01-01' '2024-01-14'"
echo "Sprint 2 (Jan 15-28):"
echo "  ./github-metrics.sh '2024-01-15' '2024-01-28'"
echo ""

# Example 3: Monthly test coverage report
echo -e "${YELLOW}Example 3: Monthly Test Coverage${NC}"
echo "Command: ./test-coverage-tracker.sh '2024-01-01' '2024-01-31'"
echo "Shows test file changes, categories, and contributors"
echo ""

# Example 4: Feature development over a quarter
echo -e "${YELLOW}Example 4: Quarterly Feature Report${NC}"
echo "Command: ./feature-tracker.sh '2024-01-01' '2024-03-31'"
echo "Tracks feature PRs, velocity, and categories"
echo ""

# Example 5: Daily standup metrics
echo -e "${YELLOW}Example 5: Daily Standup Metrics${NC}"
echo "Add to your shell aliases:"
echo "  alias standup='cd $SCRIPT_DIR && ./daily-metrics.sh'"
echo ""

# Example 6: Generate reports for specific dates
echo -e "${YELLOW}Example 6: Historical Analysis${NC}"
cat << 'EOF'
# Last 7 days
for i in {0..6}; do
    DATE=$(date -v-${i}d +%Y-%m-%d)
    echo "Metrics for $DATE:"
    ./github-metrics.sh "$DATE" "$DATE"
done
EOF
echo ""

# Example 7: Team performance dashboard
echo -e "${YELLOW}Example 7: Team Performance Dashboard${NC}"
cat << 'EOF'
#!/bin/bash
# team-dashboard.sh
echo "=== Team Performance Dashboard ==="

# This week's summary
./weekly-summary.sh 0 > this_week.txt

# Test coverage
./test-coverage-tracker.sh > test_report.txt

# Feature velocity
./feature-tracker.sh > feature_report.txt

# Combine into dashboard
echo "Dashboard generated with:"
echo "- Weekly summary: this_week.txt"
echo "- Test report: test_report.txt"
echo "- Feature report: feature_report.txt"
EOF
echo ""

# Example 8: Automated reporting
echo -e "${YELLOW}Example 8: Automated Weekly Reports${NC}"
cat << 'EOF'
# Add to crontab:
# Every Monday at 9 AM - Weekly report for last week
0 9 * * 1 cd /path/to/metrics && ./weekly-summary.sh 1

# Every day at 5 PM - Daily summary
0 17 * * * cd /path/to/metrics && ./daily-metrics.sh

# First of month - Monthly feature report
0 10 1 * * cd /path/to/metrics && ./feature-tracker.sh
EOF
echo ""

# Example 9: JSON export for further processing
echo -e "${YELLOW}Example 9: JSON Export for Analysis${NC}"
cat << 'EOF'
# Export metrics to JSON
./github-metrics.sh "2024-01-01" "2024-01-31" --json

# Process with jq
cat metrics_2024-01-01_to_2024-01-31.json | jq '.metrics.features_completed'

# Generate CSV from multiple periods
for month in {1..12}; do
    START=$(printf "2024-%02d-01" $month)
    END=$(date -v+1m -v-1d -j -f "%Y-%m-%d" "$START" +%Y-%m-%d)
    ./github-metrics.sh "$START" "$END" --json
done
EOF
echo ""

# Example 10: Custom date ranges
echo -e "${YELLOW}Example 10: Custom Date Ranges${NC}"
echo "Last 30 days:"
echo "  ./github-metrics.sh \$(date -v-30d +%Y-%m-%d) \$(date +%Y-%m-%d)"
echo ""
echo "Year to date:"
echo "  ./github-metrics.sh '2024-01-01' \$(date +%Y-%m-%d)"
echo ""
echo "Specific sprint (2 weeks):"
echo "  ./github-metrics.sh \$(date -v-14d +%Y-%m-%d) \$(date +%Y-%m-%d)"
echo ""

echo -e "${GREEN}Run any of these examples by copying the commands above!${NC}"
