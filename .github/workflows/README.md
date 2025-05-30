# GitHub Actions Workflow Strategy

## Overview

This repository uses a strategic workflow configuration to optimize CI/CD performance and avoid duplicate runs.

## Workflow Files

### 1. `ci.yml` - CI Quick Tests
- **Purpose**: Fast feedback for feature development
- **Triggers**:
  - Push to feature branches (`feat/*`, `feature/*`)
  - Manual dispatch
- **Jobs**: Basic tests and linting
- **Duration**: ~3-5 minutes
- **Note**: Does NOT run on pull requests (to avoid duplication with pr-checks.yml)

### 2. `pr-checks.yml` - Pull Request Validation
- **Purpose**: Comprehensive validation for PRs
- **Triggers**:
  - Pull requests to `main` (opened, synchronized, reopened)
- **Jobs**:
  - Lint and format checks
  - Test matrix (Python 3.11, 3.12)
  - Security scanning
  - Example validation
  - PR summary report
- **Duration**: ~5-10 minutes

### 3. `full-test.yml` - Full Test Suite
- **Purpose**: Complete test coverage and artifact generation
- **Triggers**:
  - Push to `main` branch
  - Daily schedule (2 AM UTC)
  - Manual dispatch
- **Jobs**:
  - Full test matrix with coverage
  - Example execution tests
  - Coverage report uploads
- **Duration**: ~10-15 minutes

### 4. `local-test.yml` - Local Testing Validation
- **Purpose**: Validate workflows work with `act` for local testing
- **Triggers**:
  - Manual dispatch only
- **Jobs**: Simple validation tests
- **Duration**: ~1 minute

## Workflow Strategy & Optimization

### Development Flow

1. **Feature Development** (on `feat/*` branches):
   - `ci.yml` runs on every push for quick feedback
   - No duplicate runs on feature branches

2. **Pull Request** (to `main`):
   - Only `pr-checks.yml` runs comprehensive validation
   - No duplicate runs from feature branch pushes
   - `ci.yml` does NOT run to avoid redundancy

3. **Main Branch** (after merge):
   - `full-test.yml` runs complete test suite
   - Generates coverage reports and artifacts
   - No duplicate with PR checks

4. **Nightly**:
   - `full-test.yml` runs daily to catch issues early

### Key Benefits

1. **No Duplicate Runs**: Each workflow has distinct triggers
2. **Fast Feedback**: Quick CI on feature branches (~3-5 min)
3. **Comprehensive PR Validation**: All checks before merge
4. **Main Branch Protection**: Full suite only on main
5. **Resource Optimization**: Appropriate test depth for each stage

## Optimization History

### Problem Solved
Previously, when creating a PR from a feature branch to main, CI runs were duplicated:
1. `ci.yml` was triggered by the pull_request event
2. `pr-checks.yml` was also triggered by the pull_request event
3. If pushing to the feature branch, `ci.yml` had already run on those commits

### Solution Implemented
Removed the `pull_request` trigger from `ci.yml` to eliminate redundancy:

```yaml
# Before:
on:
  push:
    branches: [ feat/*, feature/* ]
  pull_request:
    branches: [ main ]
  workflow_dispatch:

# After:
on:
  push:
    branches: [ feat/*, feature/* ]
  workflow_dispatch:
```

This ensures:
- **No Duplicate Runs**: Each workflow now has distinct, non-overlapping triggers
- **Clear Separation of Concerns**: Each workflow has a single, clear purpose
- **Resource Optimization**: Saves CI minutes by avoiding redundant runs

## Manual Workflow Execution

All workflows support `workflow_dispatch` for manual runs:

```bash
# Using GitHub CLI
gh workflow run ci.yml
gh workflow run pr-checks.yml
gh workflow run full-test.yml
gh workflow run local-test.yml

# Check status
gh run list
```

## Local Testing with act

Test workflows locally before pushing:

```bash
# List available workflows
act -l

# Run specific workflow
act -j basic-test -W .github/workflows/ci.yml
act -j lint-and-format -W .github/workflows/pr-checks.yml

# Run with specific event
act pull_request -W .github/workflows/pr-checks.yml
```

## Coverage Requirements

- **Target**: 80% code coverage
- **Current**: ~54% (focusing on critical paths)
- **Reports**: Available in Codecov and as artifacts

## Optimization Tips

1. Use `[skip ci]` in commit messages to skip CI runs
2. Use manual dispatch for experimental changes
3. Check workflow status before pushing to avoid queuing

## Troubleshooting

### Duplicate Runs
If you see duplicate runs:
1. Check branch protection rules
2. Verify workflow triggers don't overlap
3. Review recent workflow file changes

### Failed Workflows
1. Check the workflow logs in Actions tab
2. Run locally with `act` to debug
3. Verify all dependencies are installed

### Rate Limiting
- Codecov uploads may be rate-limited without token
- Configure `CODECOV_TOKEN` in repository secrets

## Migration Notes
- Existing PRs will only trigger `pr-checks.yml` after the optimization
- Feature branch pushes continue to trigger `ci.yml` as before
- No changes needed to developer workflow