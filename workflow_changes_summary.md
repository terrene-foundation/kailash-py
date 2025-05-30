# GitHub Actions Workflow Optimization

## Problem
When creating a PR from a feature branch to main, CI runs were duplicated:
1. `ci.yml` was triggered by the pull_request event
2. `pr-checks.yml` was also triggered by the pull_request event
3. If you had been pushing to the feature branch, `ci.yml` had already run on those commits

## Solution
Remove the `pull_request` trigger from `ci.yml` to eliminate redundancy.

## Changes Made

### 1. Modified `.github/workflows/ci.yml`
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

### 2. Updated `.github/workflows/README.md`
- Removed references to `ci.yml` running on pull requests
- Clarified that only `pr-checks.yml` runs for PR validation

## Benefits

1. **No Duplicate Runs**: Each workflow now has distinct, non-overlapping triggers
2. **Clear Separation of Concerns**:
   - `ci.yml`: Quick tests during feature development (on push)
   - `pr-checks.yml`: Comprehensive validation for PRs
   - `full-test.yml`: Complete test suite on main branch
3. **Resource Optimization**: Saves CI minutes by avoiding redundant runs
4. **Simpler Mental Model**: Each workflow has a single, clear purpose

## New Workflow Flow

1. **During Development** (feature branches):
   - Push to `feat/*` → `ci.yml` runs quick tests (~3-5 min)

2. **When Creating PR**:
   - Open PR to main → `pr-checks.yml` runs comprehensive validation (~5-10 min)
   - No duplicate `ci.yml` run

3. **After Merge**:
   - Push to main → `full-test.yml` runs complete suite (~10-15 min)

## Migration Notes
- Existing PRs will only trigger `pr-checks.yml` after this change
- Feature branch pushes continue to trigger `ci.yml` as before
- No changes needed to developer workflow