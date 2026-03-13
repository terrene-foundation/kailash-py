# GitHub Metrics Tracking Scripts

This directory contains comprehensive scripts for tracking GitHub metrics for the Kailash Python SDK repository.

## 📊 Available Scripts

### 1. `github-metrics.sh` - Comprehensive Metrics Report
Tracks features completed, issues resolved, tests written, and documentation updated.

**Usage:**
```bash
# Last 7 days (default)
./github-metrics.sh

# Specific date range
./github-metrics.sh "2024-01-01" "2024-01-31"

# Export to JSON
./github-metrics.sh "2024-01-01" "2024-01-31" --json
```

**Output:**
- Features completed (PRs with feat: prefix or feature labels)
- Issues resolved (closed issues)
- Test files modified with line changes
- Documentation files updated
- Summary statistics

### 2. `daily-metrics.sh` - Daily Activity Tracker
Tracks today's metrics and compares with yesterday.

**Usage:**
```bash
# Run daily report
./daily-metrics.sh
```

**Features:**
- Today's PRs, issues, commits, and contributors
- Comparison with yesterday's metrics
- Recent commit details
- Files changed breakdown
- Automatic CSV logging in `logs/daily_metrics.csv`

### 3. `weekly-summary.sh` - Weekly Summary Report
Generates comprehensive weekly reports with trends.

**Usage:**
```bash
# This week
./weekly-summary.sh 0

# Last week
./weekly-summary.sh 1

# Two weeks ago
./weekly-summary.sh 2
```

**Features:**
- Week overview with key metrics
- Daily activity breakdown with visual bars
- Top contributors
- Activity by file type
- Recent PRs and issues
- Week-over-week comparison
- Generates markdown report in `reports/`

### 4. `test-coverage-tracker.sh` - Test Coverage Analysis
Specialized script for tracking test development.

**Usage:**
```bash
# Last 30 days (default)
./test-coverage-tracker.sh

# Specific period
./test-coverage-tracker.sh "2024-01-01" "2024-01-31"
```

**Features:**
- Test file analysis (new vs modified)
- Test categories (unit, integration, node, workflow, API)
- Test commit analysis
- Top test contributors
- Coverage check (if pytest-cov available)
- JSON report generation

### 5. `feature-tracker.sh` - Feature Development Tracker
Tracks feature PRs, branches, and development lifecycle.

**Usage:**
```bash
# Last 30 days (default)
./feature-tracker.sh

# Specific period
./feature-tracker.sh "2024-01-01" "2024-01-31"
```

**Features:**
- Feature PR analysis (merged, open, closed)
- Feature branch status (active vs stale)
- Development timeline
- Feature categories
- Feature velocity metrics
- Top feature contributors

## 📁 Directory Structure

```
scripts/metrics/
├── github-metrics.sh      # Main comprehensive metrics
├── daily-metrics.sh       # Daily tracking
├── weekly-summary.sh      # Weekly reports
├── test-coverage-tracker.sh # Test analysis
├── feature-tracker.sh     # Feature tracking
├── README.md             # This file
├── logs/                 # Daily metric logs
│   └── daily_metrics.csv
└── reports/              # Generated reports
    ├── weekly_report_*.md
    ├── test_coverage_*.json
    └── feature_report_*.json
```

## 🚀 Quick Start

1. **Set up GitHub CLI** (if not already installed):
```bash
brew install gh
gh auth login
```

2. **Run your first report**:
```bash
cd 
./github-metrics.sh
```

3. **Set up daily tracking** (add to crontab):
```bash
# Add to crontab for daily 9 AM reports
0 9 * * * 
```

4. **Generate weekly summary** (run on Mondays):
```bash
# Add to crontab for weekly Monday reports
0 10 * * 1 
```

## 📈 Example Outputs

### Daily Metrics Example:
```
=== Daily Metrics Report ===
Date: 2024-01-15

Today's Activity:
- Pull Requests Merged: 3
- Issues Closed: 5
- Commits: 12
- Active Contributors: 4

Comparison with Yesterday:
- Pull Requests: 3 (+1 from yesterday's 2)
- Issues Closed: 5 (+2 from yesterday's 3)
- Commits: 12 (-3 from yesterday's 15)
```

### Feature Tracker Example:
```
=== Feature Development Tracker ===
🚀 Feature Pull Requests
├─ Total feature PRs: 15
├─ Merged: 12
├─ Still open: 2
├─ Closed without merge: 1
├─ Total additions: +2,345
└─ Total deletions: -567
```

## 🔧 Requirements

- **GitHub CLI** (`gh`) - For PR and issue queries
- **Git** - For repository analysis
- **jq** - For JSON processing (optional but recommended)
- **bc** - For calculations (usually pre-installed)
- **macOS** or Linux with bash 4+

## 💡 Tips

1. **Performance**: For large repositories, consider using date ranges to limit data
2. **Automation**: Use cron jobs for regular tracking
3. **Reporting**: JSON exports can be used for further analysis or dashboards
4. **Customization**: Scripts use variables at the top for easy customization

## 🐛 Troubleshooting

### Common Issues:

1. **"command not found: gh"**
   - Install GitHub CLI: `brew install gh`

2. **"command not found: jq"**
   - Install jq: `brew install jq`

3. **Permission denied**
   - Make scripts executable: `chmod +x *.sh`

4. **No data returned**
   - Check GitHub authentication: `gh auth status`
   - Verify repository access: `gh repo view terrene-foundation/kailash-py`

## 📝 Customization

To track additional metrics, you can extend the scripts:

1. Add new metric functions in the scripts
2. Update the JSON export sections
3. Modify the output formatting
4. Add new categories or filters

## 🤝 Contributing

To add new metrics or improve existing ones:

1. Follow the existing script patterns
2. Use consistent color coding
3. Include JSON export options
4. Update this README with new features
