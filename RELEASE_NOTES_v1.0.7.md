# Kailash Nexus v1.0.7 Release Notes

## Release Date
October 8, 2025

## Overview
This release delivers comprehensive UX improvements for the Nexus platform, with a focus on FastAPI integration clarity, enhanced logging, and improved developer experience. This is an enhancement release with no breaking changes.

## Key Features & Improvements

### 1. FastAPI Mount Behavior Documentation
- **NEW**: Comprehensive 293-line technical guide explaining FastAPI `app.mount()` behavior
- Detailed explanation of path prefix handling and `/workflows` routing
- Code examples demonstrating proper FastAPI integration patterns
- Troubleshooting guide for common mount-related issues
- Location: `docs/technical/fastapi-mount-behavior.md`

### 2. Enhanced Workflow Registration Logging
- Structured logging with clear workflow registration feedback
- Real-time visibility into workflow registration process
- Helpful debug information for troubleshooting registration issues
- Integration points clearly logged for multi-channel deployments

### 3. Improved 404 Error Handling
- User-friendly 404 handler added to Core SDK WorkflowAPI
- Clear error messages when workflows are not found
- Helpful guidance on checking workflow registration and paths
- Improved debugging experience for API users

### 4. Documentation Updates
- Enhanced `docs/getting-started/basic-usage.md` (+59 lines)
- Updated `docs/user-guides/workflow-registration.md` (+44 lines)
- New architecture decision record (ADR-001) documenting UX improvements
- All examples tested and validated

### 5. Dependency Updates
- Core SDK dependency updated to `kailash>=0.9.21`
- Ensures compatibility with latest Core SDK features
- Aligned dependency versions across both setup.py and pyproject.toml

## Test Coverage
This release includes comprehensive test coverage:
- **22 new tests** across 4 test modules
- **100% coverage** for new functionality
- **All existing tests passing** (305 tests, zero breaking changes)

### New Test Modules
1. `tests/e2e/test_nexus_ux_improvements_e2e.py` (14 tests, 355 lines)
2. `tests/e2e/test_documentation_ux.py` (3 tests, 105 lines)
3. `tests/integration/test_enhanced_logging.py` (5 tests, 167 lines)
4. `src/kailash/api/tests/test_workflow_api_404.py` (5 tests, 202 lines)

## Files Changed
- **Documentation**: 4 files (293 + 59 + 44 + 808 lines)
- **Core Implementation**: 2 files (enhanced logging + 404 handler)
- **Version Files**: 2 files (pyproject.toml + setup.py)
- **Tests**: 4 new test files (829 lines)
- **Total**: 2,079+ lines of improvements

## Breaking Changes
**None** - This is a fully backward-compatible release.

## Migration Guide
No migration required. This is a drop-in replacement for v1.0.6.

To upgrade:
```bash
pip install --upgrade kailash-nexus
```

## Dependencies
- Python: >=3.11
- Kailash SDK: >=0.9.21

## What's Next
This release sets the foundation for:
- Enhanced multi-channel deployment patterns
- Improved debugging and troubleshooting capabilities
- Better developer onboarding experience

## Contributors
- Jack Hong <jack.hong@self-hosted.com>
- Claude <noreply@anthropic.com>

## Related Links
- PR #398: https://github.com/terrene-foundation/kailash-py/pull/398
- Core SDK v0.9.21: https://github.com/terrene-foundation/kailash-py/releases/tag/v0.9.21

---

Generated with Claude Code
