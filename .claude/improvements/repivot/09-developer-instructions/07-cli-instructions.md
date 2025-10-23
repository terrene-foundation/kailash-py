# CLI Team: Developer Instructions

**Team:** CLI Development
**Timeline:** Weeks 9-14 (after templates are designed)
**Estimated Effort:** 60 hours
**Priority:** High (primary interface for IT teams)

---

## Your Responsibilities

Build the kailash CLI - primary interface for IT teams:

1. ✅ `kailash create` - Generate projects from templates
2. ✅ `kailash dev` - Development server with auto-reload
3. ✅ `kailash upgrade` - Upgrade Quick Mode to Full SDK
4. ✅ `kailash marketplace` - Component discovery and installation
5. ✅ `kailash component` - Create new components

**Impact:** This is how users interact with Kailash. First impression matters.

---

## Required Reading

### MUST READ (2.5 hours):

**1. Templates Understanding (1 hour):**
- `../02-implementation/02-new-components/01-templates-specification.md` - You're generating these

**2. CLI Specifications (1.5 hours):**
- `../02-implementation/03-modifications/04-cli-additions.md` - Complete CLI spec (1,254 lines)

---

## Detailed Tasks

### Task 1: kailash create (Weeks 9-10, 20 hours) - HIGHEST PRIORITY

**New file:** `src/kailash/cli/create.py`

**Specification:** `03-modifications/04-cli-additions.md` (lines 10-350)

**What to build:**

**CLI command:**
```bash
kailash create my-saas --template=saas-starter --database=postgresql
```

**Implementation:**
```python
@click.command()
@click.argument('project_name')
@click.option('--template', default='saas-starter')
@click.option('--ai-mode/--no-ai-mode', default=True)
@click.option('--database', type=click.Choice(['postgresql', 'mysql', 'sqlite']))
def create(project_name, template, ai_mode, database):
    # 1. Validate project name
    # 2. Get template directory
    # 3. Load template metadata
    # 4. Copy files with Jinja2 substitution
    # 5. Post-creation setup (git init, venv, pip install)
    # 6. Success message with next steps
```

**Key functionality:**
- Variable substitution (project_name, database_type)
- Conditional file inclusion (AI mode vs minimal)
- Post-creation setup automation
- Helpful error messages

**Testing:**
```python
def test_create_generates_saas_template():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(create, ['test-saas', '--template=saas-starter'])
        assert result.exit_code == 0
        assert Path('test-saas/main.py').exists()

def test_generated_project_runs():
    # ... generate, configure, run, verify
```

---

### Task 2: kailash dev (Week 11, 15 hours)

**New file:** `src/kailash/cli/dev.py`

**Specification:** `03-modifications/04-cli-additions.md` (lines 352-550)

**What to build:**

**CLI command:**
```bash
kailash dev --host=0.0.0.0 --port=8000 --reload
```

**Implementation:**
```python
@click.command()
@click.option('--host', default='0.0.0.0')
@click.option('--port', default=8000)
@click.option('--reload/--no-reload', default=True)
def dev(host, port, reload):
    # 1. Find entry point (main.py or app.py)
    # 2. If reload: use watchdog for auto-reload
    # 3. If no reload: direct subprocess
    # 4. Set environment variables
    # 5. Monitor and restart on file changes
```

**Key functionality:**
- Auto-reload with watchdog
- File change detection
- Process management
- Helpful startup messages

**Testing:**
```python
def test_dev_starts_application():
    # Generate template
    # Run kailash dev
    # Verify server starts
    # Make HTTP request
    # Verify response
```

---

### Task 3: kailash marketplace (Week 12-13, 15 hours)

**New file:** `src/kailash/cli/marketplace.py`

**Specification:** `03-modifications/04-cli-additions.md` (lines 552-900)

**What to build:**

**CLI commands:**
```bash
kailash marketplace search authentication
kailash marketplace install kailash-sso
kailash marketplace list
kailash marketplace update
kailash marketplace outdated
```

**Implementation:**
```python
@click.group()
def marketplace():
    """Component marketplace operations."""

@marketplace.command()
@click.argument('query')
def search(query):
    # 1. Search PyPI for kailash-{query}
    # 2. Format results
    # 3. Display with metadata (downloads, version)
```

**Key functionality:**
- PyPI API integration
- Component discovery
- Installation wrapper (pip install)
- Update checking

**Testing:**
```python
def test_marketplace_search_finds_components():
    # Mock PyPI API
    # Search for "sso"
    # Verify kailash-sso returned
```

---

### Task 4: kailash upgrade (Week 14, 10 hours)

**New file:** `src/kailash/cli/upgrade.py`

**Specification:** `03-modifications/04-cli-additions.md` (lines 902-1200)

**What to build:**

**CLI command:**
```bash
kailash upgrade --analyze    # Analyze without changing
kailash upgrade --to=standard  # Actually upgrade
```

**Implementation:**
```python
@click.command()
@click.option('--to', type=click.Choice(['standard', 'enterprise']))
@click.option('--analyze', is_flag=True)
def upgrade(to, analyze):
    # 1. Detect Quick Mode usage
    # 2. Analyze project complexity
    # 3. Generate recommendation
    # 4. If not --analyze: convert to Full SDK
    # 5. Create backup
    # 6. Generate UPGRADE.md
```

**This is complex:** Converts Quick Mode code to Full SDK code

**Consider:** Phase 2 feature (defer if time constrained)

---

## Subagent Workflow for CLI Team

### Week 9: Planning

```bash
# Day 1
> Use the requirements-analyst subagent to break down CLI requirements into create, dev, upgrade, and marketplace commands

> Use the sdk-navigator subagent to check if any CLI infrastructure exists in current SDK

# Day 2
> Use the todo-manager subagent to create detailed task breakdown for CLI development prioritizing kailash create as most critical

> Use the ultrathink-analyst subagent to analyze CLI UX and identify potential user confusion points
```

### Weeks 10-11: Implementation (create + dev)

```bash
# kailash create
> Use the pattern-expert subagent to implement template generation with Jinja2 variable substitution following Python CLI best practices

# kailash dev
> Use the pattern-expert subagent to implement development server with hot reload using watchdog library

# After each command
> Use the testing-specialist subagent to write comprehensive CLI tests using Click's CliRunner

> Use the intermediate-reviewer subagent to review CLI command implementation for UX and error handling
```

### Weeks 12-13: Implementation (marketplace)

```bash
> Use the pattern-expert subagent to implement marketplace commands with PyPI API integration

> Use the testing-specialist subagent to test marketplace commands with mock PyPI responses and real package installations

> Use the gold-standards-validator subagent to ensure CLI follows Python CLI best practices and Kailash standards
```

### Week 14: Polish and Integration

```bash
> Use the documentation-validator subagent to create comprehensive CLI reference documentation

> Use the git-release-specialist subagent to create PR for CLI implementation with tests and docs

> Use the intermediate-reviewer subagent to perform final review of complete CLI before merge
```

---

## Testing Protocol

### CLI Testing with Click

```python
# tests/cli/test_create.py

from click.testing import CliRunner
from kailash.cli.create import create

def test_create_command_basic():
    """Test basic template creation."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(create, ['my-app', '--template=saas-starter'])

        # Verify exit code
        assert result.exit_code == 0

        # Verify files created
        assert Path('my-app/main.py').exists()
        assert Path('my-app/CUSTOMIZE.md').exists()

        # Verify output message
        assert '✅ Project created successfully!' in result.output

def test_create_validates_project_name():
    """Test project name validation."""
    runner = CliRunner()

    result = runner.invoke(create, ['Invalid Name'])  # Spaces not allowed

    assert result.exit_code != 0
    assert 'Invalid project name' in result.output

def test_create_with_all_options():
    """Test create with all options."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(create, [
            'my-saas',
            '--template=saas-starter',
            '--database=postgresql',
            '--ai-mode',
            '--no-git',
            '--no-venv'
        ])

        assert result.exit_code == 0
        assert Path('my-saas').exists()
        assert not Path('my-saas/.git').exists()  # --no-git
        assert not Path('my-saas/.venv').exists()  # --no-venv
```

---

## Integration Testing

**Test complete user flow:**
```python
# tests/integration/test_cli_complete_flow.py

def test_complete_user_flow():
    """Test complete CLI flow from create to deploy."""

    runner = CliRunner()

    with runner.isolated_filesystem():
        # 1. Create project
        result = runner.invoke(create, ['my-saas', '--template=saas-starter'])
        assert result.exit_code == 0

        # 2. Configure
        env_file = Path('my-saas/.env')
        env_file.write_text("DATABASE_URL=sqlite:///test.db")

        # 3. Start dev server (background)
        # ... (test kailash dev starts successfully)

        # 4. Test app works
        response = requests.get('http://localhost:8000/health')
        assert response.status_code == 200
```

---

## Success Criteria

**CLI succeeds if:**
- [ ] kailash create works 100% of time (no failures)
- [ ] Generated projects run successfully (95%+ success rate)
- [ ] kailash dev provides fast iteration (auto-reload works)
- [ ] Marketplace commands make discovery easy
- [ ] Error messages are clear and actionable
- [ ] UX is intuitive (doesn't require docs to use)

**Measure by:**
- CLI usage telemetry (which commands used most)
- User feedback ("CLI is easy to use" in surveys)
- Support tickets (should be low for CLI issues)

---

## Dependencies

**From Templates Team:**
- Template designs (Week 4)
- template.json format
- Variable substitution needs

**From Core SDK Team:**
- Telemetry integration (Week 11)
- Track CLI command usage

**From Marketplace:**
- Component list for search
- PyPI integration approach

---

## Timeline

**Week 9:** Planning + tests (10 hours)
**Week 10:** kailash create (15 hours)
**Week 11:** kailash dev (15 hours)
**Week 12-13:** kailash marketplace (15 hours)
**Week 14:** Integration, docs, polish (5 hours)

**Total: 60 hours over 6 weeks**

**Team:** 1 developer at 10 hours/week

---

**The CLI is the front door to Kailash for IT teams. Make it welcoming, intuitive, and helpful.**
