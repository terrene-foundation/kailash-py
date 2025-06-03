# Workflow Procedures - Kailash Python SDK

## Development Workflow

### 1. Starting a New Feature

1. **Check Requirements**
   - Review PRD in `guide/prd/`
   - Check existing ADRs in `guide/adr/`
   - Review current todos in `guide/todos/000-master.md`

2. **Plan Implementation**
   - Create/update ADR if needed
   - Update todo list with tasks
   - Identify affected components

3. **Reference Documentation**
   - Check `guide/reference/api-registry.yaml` for APIs
   - Review `guide/reference/validation-guide.md`
   - Use patterns from `guide/reference/cheatsheet.md`

### 2. Implementation Process

```bash
# 1. Create feature branch
git checkout -b feature/your-feature-name

# 2. Make changes following coding standards
# - Check guide/reference/ for API specs
# - Follow patterns in examples/

# 3. Validate your code
python guide/reference/validate_kailash_code.py your_file.py

# 4. Run tests
pytest tests/

# 5. Update documentation
# - Update api-registry.yaml if APIs changed
# - Update examples if needed
# - Update CHANGELOG.md

# 6. Commit with conventional commits
git add .
git commit -m "feat: add new feature description"
```

### 3. Testing Workflow

1. **Write Tests First** (when possible)
   ```python
   # tests/test_your_feature.py
   def test_new_feature_behavior():
       # Test implementation
       pass
   ```

2. **Run Tests Iteratively**
   ```bash
   # Run specific test during development
   pytest tests/test_your_feature.py -v
   
   # Run all tests before committing
   pytest
   ```

3. **Validate Examples**
   ```bash
   cd examples
   python _utils/test_all_examples.py
   ```

## Task Management

### Todo System Structure

We use a two-file system for better context management:

1. **Master File** (`guide/todos/000-master.md`)
   - Active tasks only
   - Current priorities
   - Keep under 300 lines

2. **Archive File** (`guide/todos/completed-archive.md`)
   - Historical record
   - Completed tasks
   - Session summaries

### Todo File Format

```markdown
# Project Status Overview
- **API Development**: 90% complete - Final testing phase
- **Documentation**: 85% complete - Updating examples
- **Testing**: 95% complete - Integration tests remaining

## 🔥 URGENT PRIORITY - Current Client Needs
- **Fix Critical Bug in HTTP Node**
  - Description: Connection timeout not respected
  - Status: In Progress
  - Priority: Critical
  - Branch: fix/http-timeout

## High Priority - Active Tasks
- **Complete LLM Reference Documentation**
  - Description: Create api-registry.yaml
  - Status: In Progress
  - Priority: High
  - Details: Need to document all node types

## Medium Priority Tasks
- **Optimize Workflow Execution**
  - Description: Improve performance for large graphs
  - Status: To Do
  - Priority: Medium
  - Estimate: 2-3 days

## Recent Achievements
- ✅ Created validation system for LLM code generation
- ✅ Implemented comprehensive error handling
- ✅ Added pre-commit hooks
- [Full history in completed-archive.md]
```

### Task Lifecycle

1. **Creating Tasks**
   - Add to appropriate priority section
   - Include clear description
   - Set initial status: "To Do"

2. **Working on Tasks**
   - Update status to "In Progress"
   - Add implementation notes
   - Link to branch/PR if applicable

3. **Completing Tasks**
   - Update status to "Completed"
   - Move to Recent Achievements
   - Archive in next session

4. **Archiving Tasks**
   - Move completed tasks to archive file
   - Summarize session achievements
   - Keep master file focused

## Code Review Process

### Self-Review Checklist

Before requesting review:

- [ ] Code follows naming conventions
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Examples work correctly
- [ ] No hardcoded values/secrets
- [ ] Commits are logical and well-described

### Review Guidelines

1. **Check API Consistency**
   - Method names follow conventions
   - Parameters match documentation
   - Return values are as expected

2. **Verify Documentation**
   - Docstrings are complete
   - Examples are accurate
   - API registry is updated

3. **Test Coverage**
   - New code has tests
   - Edge cases are covered
   - Integration tests pass

## Release Workflow

### 1. Pre-Release Checklist

- [ ] All tests passing
- [ ] Documentation built successfully
- [ ] CHANGELOG.md updated
- [ ] Version bumped in setup.py
- [ ] API registry reflects all changes
- [ ] Examples tested and working

### 2. Release Process

```bash
# 1. Ensure on main branch
git checkout main
git pull origin main

# 2. Run full test suite
pytest
cd examples && python _utils/test_all_examples.py

# 3. Build documentation
cd docs && python build_docs.py

# 4. Create release commit
git add .
git commit -m "chore: release v0.1.4"

# 5. Tag release
git tag -a v0.1.4 -m "Release version 0.1.4"

# 6. Push to repository
git push origin main --tags

# 7. Build and upload to PyPI
python setup.py sdist bdist_wheel
twine upload dist/*
```

### 3. Post-Release

1. **Update Documentation**
   - Verify docs are deployed
   - Check PyPI page is correct
   - Update README if needed

2. **Archive Completed Work**
   - Move completed todos to archive
   - Create new development cycle entry
   - Reset master todo file

3. **Plan Next Cycle**
   - Review backlog
   - Set priorities
   - Update roadmap

## Maintenance Procedures

### Weekly Tasks

1. **Dependency Updates**
   ```bash
   pip list --outdated
   pip-upgrade --skip-package-installation
   ```

2. **Security Checks**
   ```bash
   safety check
   bandit -r src/
   ```

3. **Documentation Review**
   - Check for outdated information
   - Verify all links work
   - Update examples if needed

### Monthly Tasks

1. **Performance Analysis**
   - Run performance benchmarks
   - Profile slow operations
   - Optimize if needed

2. **Code Quality Review**
   - Check code coverage trends
   - Review complexity metrics
   - Refactor problem areas

3. **User Feedback Review**
   - Check GitHub issues
   - Review feature requests
   - Update roadmap

## Troubleshooting Procedures

### Common Issues

1. **Import Errors**
   - Check `guide/reference/api-registry.yaml`
   - Verify correct import paths
   - Ensure package is installed: `pip install -e .`

2. **Test Failures**
   - Check `guide/mistakes/000-master.md`
   - Verify test environment
   - Check for missing dependencies

3. **Documentation Build Errors**
   - Verify Sphinx is installed
   - Check for syntax errors in .rst files
   - Ensure all referenced files exist

### Debug Workflow

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use debugger
import pdb; pdb.set_trace()

# Or use IPython debugger
from IPython import embed; embed()
```

## Git Workflow

### Branch Naming
- Features: `feature/description`
- Fixes: `fix/description`
- Documentation: `docs/description`
- Refactoring: `refactor/description`

### Commit Messages
Follow conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `test:` Test only
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

### Example Workflow
```bash
# Start new feature
git checkout -b feature/add-graphql-node

# Make changes and commit
git add src/kailash/nodes/api/graphql.py
git commit -m "feat: add GraphQL node for API queries"

git add tests/test_nodes/test_graphql.py  
git commit -m "test: add tests for GraphQL node"

git add docs/api/nodes.rst
git commit -m "docs: document GraphQL node usage"

# Push and create PR
git push origin feature/add-graphql-node
```