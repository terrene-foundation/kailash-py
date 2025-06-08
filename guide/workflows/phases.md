# 5-Phase Development Workflow

This document describes the structured 5-phase workflow for developing features in the Kailash Python SDK. Each phase has specific goals and outputs to ensure quality and knowledge capture.

## Overview

The workflow is designed to:
1. Minimize context switches
2. Capture learning from mistakes
3. Ensure comprehensive documentation
4. Maintain code quality

## Phase 1: Discovery & Planning (PLAN MODE)

### Goals
- Understand the request fully
- Research existing patterns and potential issues
- Create a comprehensive plan

### Steps
1. **Check TODO List**: Review `guide/todos/000-master.md` for context
2. **Research Documentation**:
   - Architecture decisions in `guide/adr/`
   - Similar features in `guide/features/`
   - API patterns in `guide/reference/`
3. **Review Mistakes**: Check `guide/mistakes/consolidated-guide.md` for known pitfalls
4. **Create Plan**: Develop architecture and implementation approach

### Output
- Detailed implementation plan
- List of deliverables
- Identified risks and mitigation strategies

## Phase 2: Implementation & Learning (EDIT MODE)

### Goals
- Build working examples first
- Implement based on proven examples
- Capture all mistakes and learnings

### Steps
1. **Update TODOs**: Mark task as "In Progress"
2. **Create ADR**: If architectural change, document decision
3. **Write Examples**:
   - Start with basic example
   - Debug until it works
   - Create advanced example
   - **Track all mistakes in `guide/sessions/current-mistakes.md`**
4. **Implement Feature**: Based on working examples
5. **Write Tests**: Extract test cases from examples
6. **Run Validation**:
   ```bash
   python guide/reference/validate_kailash_code.py examples/your_example.py
   cd examples && python _utils/test_all_examples.py
   pytest tests/test_your_feature.py
   black . && isort . && ruff check .
   ```

### Output
- Working examples
- Implemented feature
- Test coverage
- Mistake log with all discovered issues

## Phase 3: Mistake Analysis (PLAN MODE)

### Goals
- Analyze all mistakes systematically
- Identify patterns and root causes
- Plan documentation updates

### Steps
1. **Review Mistake Log**: Analyze `guide/sessions/current-mistakes.md`
2. **Identify Patterns**: Group related mistakes
3. **Determine Root Causes**: Understand why mistakes occurred
4. **Plan Updates**: List all documentation that needs updating

### Output
- Categorized mistake analysis
- Root cause identification
- Documentation update plan

## Phase 4: Documentation Updates (EDIT MODE)

### Goals
- Update all relevant documentation
- Ensure learnings are captured
- Prevent future occurrences

### Steps
1. **Update Mistake Logs**:
   - Create new file `guide/mistakes/NNN-description.md` using template
   - Update `guide/mistakes/README.md` index
   - Add to "Common Fixes" in README if very common
2. **Update References**:
   - `guide/reference/api-registry.yaml` for API changes
   - `guide/reference/validation-guide.md` for new rules
   - `guide/reference/pattern-library/` for new patterns
3. **Update Feature Guides**:
   - Add learnings to relevant `guide/features/` docs
   - Create new guides if needed
4. **Update Cheatsheet**: Add to `guide/reference/cheatsheet.md`

### Output
- Updated mistake documentation
- Enhanced reference guides
- Improved feature documentation

## Phase 5: Final Release (EDIT MODE)

### Goals
- Ensure everything is production-ready
- Complete all housekeeping tasks
- Prepare for release

### Steps
1. **Final Validation**:
   ```bash
   pytest  # All tests
   python -m doctest -v src/kailash/**/*.py  # Doctests
   cd docs && python build_docs.py  # Sphinx docs
   ```
2. **Update TODOs**: Mark task as "Completed"
3. **Update CHANGELOG.md**: Document changes
4. **Create Release** (if applicable):
   - Update version numbers
   - Create release notes
   - Build and upload to PyPI
5. **Git Operations**:
   ```bash
   git add -A
   git commit -m "feat: [description]"
   git push origin [branch]
   # Create PR
   ```

### Output
- Validated codebase
- Updated documentation
- Clean git history
- Pull request ready

## Context Management

### When to Clear Context
- Between phases (especially before Phase 3)
- When switching between major tasks
- After completing Phase 5

### What to Keep Loaded
- **Phase 1**: References, ADRs, mistakes
- **Phase 2**: Examples, source code, current-mistakes.md
- **Phase 3**: All mistake logs, documentation structure
- **Phase 4**: Documentation files being updated
- **Phase 5**: Validation tools, release checklist

## Quick Reference Commands

```bash
# Validation
python guide/reference/validate_kailash_code.py [file]
cd examples && python _utils/test_all_examples.py
pytest
black . && isort . && ruff check .

# Documentation
cd docs && python build_docs.py

# Release
python -m build
twine upload dist/*
```
