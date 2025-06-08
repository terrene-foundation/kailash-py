# Development Workflow Guide

## Complete Development Workflow (Any Task)

### START: Check todos and plan
1. Check `guide/todos/000-master.md` for priorities
2. Mark task as "In Progress"
3. Check relevant ADRs and reference docs

### IMPLEMENT: Write code
4. Use `guide/reference/api-registry.yaml` for exact APIs
5. Follow patterns from `guide/reference/cheatsheet.md`
6. Check `guide/features/` when:
   - Implementing multi-agent coordination (`agent_coordination_patterns.md`)
   - Adding authentication/permissions (`access_control.md`)
   - Integrating external APIs (`api_integration.md`)
   - Using MCP tools (`mcp_ecosystem.md`)
   - Working with cyclic workflows (`cyclic_workflows.md`)
   - Designing new architectural patterns
   - Understanding existing feature implementations
7. Write detailed docstrings following `guide/instructions/documentation-requirements.md`:
   - Include all 8 required sections (design, dependencies, usage, implementation, etc.)
   - Use Google-style format with doctest examples (>>> syntax)
   - Document all parameters, returns, raises, and side effects
8. Write examples FIRST:
   - Create basic example in `examples/{category}_examples/`
   - Create complex example showing advanced usage
   - Validate: `python guide/reference/validate_kailash_code.py your_examples.py`
   - Run examples to ensure they work
9. Implement the actual feature/fix

### TEST: Verify everything works
10. Write tests based on your examples:
    - Break down examples into test components
    - Test edge cases not covered in examples
    - Run new tests: `pytest tests/test_your_module.py`
11. Run ALL examples: `cd examples && python _utils/test_all_examples.py`
12. Run ALL tests: `pytest`
13. Run doctests: `python -m doctest -v src/kailash/**/*.py`
14. Run linting: `black . && isort . && ruff check .`

### DOCUMENT: Update all docs
15. Update `guide/todos/000-master.md` (mark completed, add new tasks)
16. Document mistakes:
    - Create new file in `guide/mistakes/NNN-description.md`
    - Update `guide/mistakes/README.md` index
17. Update reference docs if APIs changed:
    - `guide/reference/api-registry.yaml`
    - `guide/reference/api-validation-schema.json`
    - `guide/reference/cheatsheet.md`
    - `guide/reference/node-catalog.md` (if new nodes added)
    - `guide/reference/pattern-library/` (if new patterns discovered)
    - `guide/reference/templates/` (if new common use cases identified)
18. Update READMEs and Sphinx docs if needed
19. Update CHANGELOG.md

### FINALIZE: Prepare for commit
20. Build Sphinx: `cd docs && python build_docs.py`
21. Review all changes
22. Commit with descriptive message
23. Push to GitHub

## Specific Task Patterns

### Creating Examples
- Location: `examples/{category}_examples/`
- Naming: `{category}_{description}.py`
- Must pass validation and test_all_examples.py

### Writing Tests
- Location: `tests/` (mirror src structure)
- Coverage: Maintain >80%
- Run full test suite before committing

### Adding New Features
- Start with ADR if architectural change
- Update all reference documentation
- Create examples showing usage
- Write comprehensive tests

## Quick Validation Commands
```bash
# Validate a single file
python guide/reference/validate_kailash_code.py myfile.py

# Test all examples
cd examples && python _utils/test_all_examples.py

# Run unit tests
pytest tests/ -v

# Run pre-commit checks
pre-commit run --all-files

# Build documentation
cd docs && python build_docs.py
```
