# GitHub Actions Workflow Strategy

## Overview

This repository uses a unified CI pipeline that intelligently avoids duplicate test runs while maintaining code quality standards.

## Workflow Files

### 1. `unified-ci.yml` - Unified CI Pipeline (ACTIVE)
- **Purpose**: Smart CI pipeline that eliminates duplicate runs
- **Triggers**:
  - Push to feature branches (`feat/*`, `feature/*`)
  - Pull requests to `main`
  - Manual dispatch
- **Smart Detection**:
  - For pushes: Checks if PR exists, skips if yes
  - For PRs: Always runs full test suite
  - For manual: Always runs full test suite
- **Jobs**:
  - Basic tests (push without PR)
  - Full suite (PRs and manual):
    - Lint and format checks
    - Test matrix (Python 3.11, 3.12)
    - Security scanning
    - Example validation
    - PR summary with bot comments
- **Duration**:
  - Basic: ~2-3 minutes
  - Full: ~5-10 minutes

### 2. `full-test.yml` - Full Test Suite
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

### 3. `local-test.yml` - Local Testing Validation
- **Purpose**: Validate workflows work with `act` for local testing
- **Triggers**:
  - Manual dispatch only
- **Jobs**: Simple validation tests
- **Duration**: ~1 minute

## Workflow Strategy & Optimization

### Unified CI Pipeline Flow

1. **Feature Development** (on `feat/*` branches):
   - Push without PR: Runs basic smoke tests only
   - Push with existing PR: Skips tests (PR will handle)
   - Smart detection prevents duplicate runs

2. **Pull Request** (to `main`):
   - Always runs full test suite
   - Comprehensive validation before merge
   - Bot comments with status summary

3. **Main Branch** (after merge):
   - `full-test.yml` runs complete test suite
   - Generates coverage reports and artifacts
   - Additional integration tests

4. **Nightly**:
   - `full-test.yml` runs daily to catch issues early

### Key Benefits

1. **No Duplicate Runs**: Smart detection prevents running tests twice
2. **40-50% CI Resource Savings**: Tests run only where needed
3. **Faster Feedback**: Basic tests in 2-3 min, full suite in 5-10 min
4. **Single Source of Truth**: One workflow handles all scenarios
5. **Intelligent Context Detection**: Automatically determines what to run

## Optimization History

### Problem Solved
Previously, when creating a PR from a feature branch to main, CI runs were duplicated:
1. `ci.yml` was triggered by the pull_request event
2. `pr-checks.yml` was also triggered by the pull_request event
3. If pushing to the feature branch, `ci.yml` had already run on those commits

### Solution Evolution

**Phase 1**: Removed `pull_request` trigger from `ci.yml` (partial fix)

**Phase 2**: Implemented unified CI pipeline with smart detection:
- Single workflow handles all scenarios
- Detects if PR exists for branch
- Skips duplicate runs automatically
- Provides clear feedback about decisions

This ensures:
- **Zero Duplicate Runs**: Smart detection prevents any redundancy
- **40-50% Resource Savings**: Tests only run where needed
- **Better Developer Experience**: Clear messages about what's running and why

## Manual Workflow Execution

All workflows support `workflow_dispatch` for manual runs:

```bash
# Using GitHub CLI
gh workflow run unified-ci.yml
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

# Run unified CI workflow
act push -W .github/workflows/unified-ci.yml
act pull_request -W .github/workflows/unified-ci.yml

# Run specific jobs
act -j basic-tests -W .github/workflows/unified-ci.yml
act -j lint-and-format -W .github/workflows/unified-ci.yml

# Run with specific event
act workflow_dispatch -W .github/workflows/unified-ci.yml
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

### Transition to Unified CI
- New pushes and PRs will use `unified-ci.yml` automatically
- Existing PRs may need to be rebased to pick up the new workflow
- `ci.yml` and `pr-checks.yml` are deprecated but kept for reference
- No changes needed to developer workflow - just push as usual

### Branch Protection Updates
- Update required status checks to use `unified-ci.yml` jobs:
  - `CI Pipeline / Lint and Format Check`
  - `CI Pipeline / Test Python 3.11`
  - `CI Pipeline / Test Python 3.12`
  - `CI Pipeline / Security Scan`
  - `CI Pipeline / Validate Examples`

### Timeline
1. **Immediate**: Unified workflow active for new pushes/PRs
2. **1 week**: Monitor for issues, adjust as needed
3. **2 weeks**: Remove deprecated workflows if stable
