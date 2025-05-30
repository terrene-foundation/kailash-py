# ADR-0017: CI Optimization - Unified Workflow Strategy

## Status
Proposed

## Context
Currently, our CI pipeline runs duplicate tests when:
1. A developer pushes to a feature branch (triggers `ci.yml`)
2. The same developer creates a PR from that branch (triggers `pr-checks.yml`)

This results in:
- Duplicate test runs for the same commit SHA
- Increased CI costs and resource usage
- Slower feedback cycles
- Confusion about which workflow results to trust

### Current Workflow Structure
- `ci.yml`: Runs on push to feature branches
- `pr-checks.yml`: Runs on PR creation/update
- Both workflows test similar things with overlap

## Decision
Implement a unified CI workflow that intelligently determines what tests to run based on the context, eliminating duplicate runs while maintaining code quality standards.

### Implementation Strategy

1. **Single Unified Workflow**
   - Combine logic from `ci.yml` and `pr-checks.yml`
   - Detect whether the event is a push or PR
   - Check if a PR exists for pushed branches
   - Run appropriate test suite based on context

2. **Test Execution Logic**
   ```
   IF event is pull_request:
     Run full test suite (lint, format, tests, security)
   ELSE IF event is push:
     IF PR exists for this branch:
       Skip (PR checks will handle it)
     ELSE:
       Run basic smoke tests only
   ```

3. **Concurrency Control**
   - Use concurrency groups to cancel in-progress runs
   - Group by workflow and ref to prevent parallel runs

## Consequences

### Positive
- **40-50% reduction in CI resource usage**
- **Faster developer feedback** - no waiting for duplicate runs
- **Clearer CI status** - one source of truth per context
- **Cost savings** on GitHub Actions minutes
- **Simplified workflow maintenance** - fewer files to manage

### Negative
- **More complex workflow logic** - single file is harder to understand
- **Potential edge cases** - need careful testing of the detection logic
- **Migration effort** - existing PRs may need updates

### Mitigation Strategies
1. Comprehensive documentation in workflow files
2. Clear output messages about why tests are skipped
3. Gradual rollout with monitoring

## Implementation Details

### Phase 1: Create Unified Workflow
```yaml
name: CI Pipeline

on:
  push:
    branches: [ feat/*, feature/* ]
  pull_request:
    branches: [ main ]

concurrency:
  group: ${{ github.workflow }}-${{ github.head_ref || github.ref }}
  cancel-in-progress: true

jobs:
  determine-context:
    outputs:
      test-level: ${{ steps.determine.outputs.level }}
    steps:
      - id: determine
        uses: actions/github-script@v7
        with:
          script: |
            // Determine test level based on context
            
  run-tests:
    needs: determine-context
    # Run appropriate tests based on level
```

### Phase 2: Update Branch Protection
- Configure status checks to accept unified workflow results
- Update documentation for developers

### Phase 3: Deprecate Old Workflows
- Keep old workflows disabled but available for reference
- Remove after successful migration period

## Alternatives Considered

1. **Keep Separate Workflows with Skip Logic**
   - Pro: Simpler individual workflows
   - Con: Still requires two workflow files, complex skip conditions

2. **Use Workflow Reuse**
   - Pro: DRY principle, shared job definitions
   - Con: Still triggers multiple workflows

3. **Manual PR Labels**
   - Pro: Developer control
   - Con: Requires manual intervention, error-prone

## References
- [GitHub Actions: Prevent duplicate workflow runs](https://github.community/t/how-to-avoid-running-duplicate-workflows/16335)
- [GitHub Actions: Concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency)
- [GitHub Actions: Conditional Jobs](https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution)

## Implementation Checklist
- [ ] Create unified workflow file
- [ ] Test with various scenarios (push only, push then PR, direct PR)
- [ ] Update branch protection rules
- [ ] Update developer documentation
- [ ] Monitor for edge cases
- [ ] Deprecate old workflows after validation period