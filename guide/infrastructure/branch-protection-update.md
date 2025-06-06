# Branch Protection Update Guide

## Current Issue
The branch protection is expecting old job names that no longer exist when using the optimized workflow with local runners.

## Required Changes

### Go to Repository Settings
1. Navigate to: https://github.com/terrene-foundation/kailash-py/settings
2. Click on "Branches" in the left sidebar
3. Find the rule for `main` branch (or create one if it doesn't exist)

### Update Required Status Checks

#### Remove These Old Checks:
- ❌ `Test Python 3.11`
- ❌ `Test Python 3.12`

#### Add These New Checks:
When using **GitHub-hosted runners**:
- ✅ `CI Pipeline / Lint and Format Check`
- ✅ `CI Pipeline / Test Python 3.11`
- ✅ `CI Pipeline / Test Python 3.12`
- ✅ `CI Pipeline / Security Scan`
- ✅ `CI Pipeline / Validate Examples`

When using **self-hosted runners** (your local Mac):
- ✅ `CI Pipeline / All Checks (Parallel)`
- ✅ `CI Pipeline / Security Scan`

### Recommended Minimal Set
Since you're using both GitHub and self-hosted runners, use these checks that always run:
- ✅ `CI Pipeline / Security Scan`
- ✅ `CI Pipeline / Determine Test Context`

Or disable "Require status checks to pass before merging" temporarily to merge this PR, then re-enable with the correct job names.

## Steps to Update

1. **Go to Settings → Branches**
2. **Edit the protection rule for `main`**
3. **Under "Require status checks to pass before merging":**
   - Search for and remove old job names
   - Add the new job names listed above
4. **Save changes**

## Alternative: Temporary Disable
If you need to merge immediately:
1. Temporarily disable "Require status checks to pass before merging"
2. Merge the PR
3. Re-enable with the correct job names

## Verifying Job Names
To see the exact job names from your latest workflow run:
```bash
gh run view 15467066747 --json jobs | jq -r '.jobs[] | .name'
```

This will show you the actual job names that GitHub sees.
