# Kailash Python SDK - LLM Instructions

## 🚨 CRITICAL: Check These First!

### 1. TODO LIST - ALWAYS CHECK FIRST
**`guide/todos/000-master.md`** - Current tasks and priorities
- Check what's in progress
- See urgent priorities
- Understand project status

### 2. API Reference
**STOP!** Before generating ANY code:
1. Open `guide/reference/api-registry.yaml` for exact APIs
2. Check `guide/reference/validation-guide.md` for rules
3. Never guess method names or parameters

## Quick Links
- **TODO LIST (CRITICAL)**: `guide/todos/000-master.md` ← CHECK FIRST!
- **API Reference**: `guide/reference/api-registry.yaml`
- **Common Patterns**: `guide/reference/cheatsheet.md`
- **Validation**: `guide/reference/validate_kailash_code.py`
- **Mistakes Log**: `guide/mistakes/000-master.md`
- **Project Structure**: `guide/prd/0000-project_structure.md`

## Core Rules (MEMORIZE THESE)
1. **ALL node classes end with "Node"**: `CSVReaderNode` ✓, `CSVReader` ✗
2. **ALL methods use snake_case**: `add_node()` ✓, `addNode()` ✗
3. **ALL config keys use underscores**: `file_path` ✓, `filePath` ✗
4. **Workflow execution patterns**: `runtime.execute(workflow)` ✓, `workflow.execute(runtime)` ✗
5. **Parameter order is STRICT**: Check exact signatures in api-registry.yaml
6. **Docstring examples use doctest format**: `>>> code` ✓, `:: code` ✗

## 📋 TODO Management System (CRITICAL)

The todo system in `guide/todos/` is the central task tracking system:

### File Structure:
- **`000-master.md`** - ACTIVE TODO LIST (Always check first!)
  - Current tasks and priorities
  - Tasks in progress
  - Urgent client needs
  - Recent achievements

- **`completed-archive.md`** - Historical record
  - All completed tasks from past sessions
  - Detailed implementation notes
  - Session summaries and statistics

- **Numbered files** (001-xxx.md) - Session-specific logs
  - How todos were approached and resolved
  - Challenges faced and solutions found
  - Lessons learned for future reference

### When to Update:
- **Start of session**: Check 000-master.md for priorities
- **Starting a task**: Mark as "In Progress"
- **Completing a task**: Mark as "Completed" immediately
- **Finding new tasks**: Add to appropriate priority level
- **End of session**: Move completed tasks to archive

## Project Context
The Kailash Python SDK enables AI Business Coaches (ABCs) to create workflows using a node-based architecture. It provides a Python-friendly interface while maintaining compatibility with Kailash's container-node system.

## Primary Workflows

### 1. Development Workflow (Any Task)
# START: Check todos and plan
1. Check guide/todos/000-master.md for priorities
2. Mark task as "In Progress"
3. Check relevant ADRs and reference docs

# IMPLEMENT: Write code
4. Use guide/reference/api-registry.yaml for exact APIs
5. Follow patterns from guide/reference/cheatsheet.md
6. Write examples FIRST:
   - Create basic example in examples/{category}_examples/
   - Create complex example showing advanced usage
   - Validate: python guide/reference/validate_kailash_code.py your_examples.py
   - Run examples to ensure they work
7. Implement the actual feature/fix

# TEST: Verify everything works
8. Write tests based on your examples:
   - Break down examples into test components
   - Test edge cases not covered in examples
   - Run new tests: pytest tests/test_your_module.py
9. Run ALL examples: cd examples && python _utils/test_all_examples.py
10. Run ALL tests: pytest
11. Run doctests: python -m doctest -v src/kailash/**/*.py
12. Run linting: black . && isort . && ruff check .

# DOCUMENT: Update all docs
13. Update guide/todos/000-master.md (mark completed, add new tasks)
14. Document mistakes in guide/mistakes/000-master.md
15. Update reference docs if APIs changed:
    - guide/reference/api-registry.yaml
    - guide/reference/api-validation-schema.json
    - guide/reference/cheatsheet.md
16. Update READMEs and Sphinx docs if needed
17. Update CHANGELOG.md

# FINALIZE: Prepare for commit
18. Build Sphinx: cd docs && python build_docs.py
19. Review all changes
20. Commit with descriptive message
21. Push to GitHub

### 2. Specific Task Patterns

#### Creating Examples
- Location: `examples/{category}_examples/`
- Naming: `{category}_{description}.py`
- Must pass validation and test_all_examples.py

#### Writing Tests
- Location: `tests/` (mirror src structure)
- Coverage: Maintain >80%
- Run full test suite before committing

#### Adding New Features
- Start with ADR if architectural change
- Update all reference documentation
- Create examples showing usage
- Write comprehensive tests

## Common Task Checklists

### □ Adding a New Node
- [ ] Name ends with "Node" (e.g., `MyCustomNode`)
- [ ] Inherits from `Node` or `AsyncNode`
- [ ] Has `get_parameters()` and `run()` methods (required)
- [ ] Has `get_output_schema()` method (optional, for output validation)
- [ ] Update `guide/reference/api-registry.yaml`
- [ ] Create example in `examples/node_examples/`
- [ ] Write unit tests
- [ ] Update docs

### □ Creating a Workflow Example
- [ ] Import from correct paths (check api-registry.yaml)
- [ ] Use exact method names (snake_case)
- [ ] Include all required parameters
- [ ] Validate with `validate_kailash_code.py`
- [ ] Test with `test_all_examples.py`

### □ Updating API
- [ ] Update `guide/reference/api-registry.yaml`
- [ ] Update `guide/reference/api-validation-schema.json`
- [ ] Update examples in `guide/reference/cheatsheet.md`
- [ ] Run validation tests
- [ ] Update CHANGELOG.md

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

## Directory Structure
```
kailash_python_sdk/
├── src/kailash/          # Source code
├── tests/                # Unit tests
├── examples/             # Example code
├── docs/                 # Sphinx documentation
├── guide/                # Development guides
│   ├── todos/           # TODO TRACKING (CHECK FIRST!)
│   │   ├── 000-master.md      # Active tasks
│   │   ├── completed-archive.md # Historical record
│   │   └── 001-xxx.md         # Session logs
│   ├── reference/        # LLM reference docs
│   ├── instructions/     # Detailed instructions
│   ├── adr/             # Architecture decisions
│   ├── prd/             # Product requirements
│   └── mistakes/        # Common mistakes log
```

## Important Reminders
- **Do only what's asked** - nothing more, nothing less
- **Never create unnecessary files** - prefer editing existing ones
- **Always validate generated code** before submitting
- **Follow the Development Workflow** above for all tasks
- **All key references are in Quick Links** at the top

## Need More Detail?

For deep dives into specific topics, see `guide/instructions/`:
- Coding conventions → `coding-standards.md`
- Documentation formats → `documentation-requirements.md`
- Testing patterns → `testing-guidelines.md`
- Development process → `workflow-procedures.md`
- Release & maintenance → `maintenance-procedures.md`
