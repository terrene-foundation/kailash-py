# CLI Additions

**New Files:** `src/kailash/cli/` module (completely new)
**Estimated Effort:** 60 hours
**Risk:** Low (all new code, doesn't affect existing)

---

## CLI Architecture

### Current State

**Existing CLI (if any):**
- Limited or no CLI commands
- Users interact via Python API only

**New CLI:**
```
kailash
├── create       # Create project from template
├── dev          # Run development server
├── upgrade      # Upgrade Quick Mode → Full SDK
├── marketplace  # Component marketplace commands
│   ├── search
│   ├── install
│   ├── list
│   └── update
└── component    # Create new component (for developers)
    └── create
```

### Implementation Structure

```
src/kailash/cli/
├── __init__.py          # CLI entry point
├── __main__.py          # python -m kailash support
├── create.py            # Template creation
├── dev.py               # Development server
├── upgrade.py           # Upgrade to Full SDK
├── marketplace.py       # Marketplace commands
├── component.py         # Component development
└── utils.py             # Shared utilities
```

---

## Command 1: kailash create

**Purpose:** Create new project from template

**Signature:**
```bash
kailash create [PROJECT_NAME] [OPTIONS]

Options:
  --template TEXT       Template to use (default: saas-starter)
                       Choices: saas-starter, internal-tools, api-gateway
  --ai-mode            Enable AI-optimized mode (default: True)
  --database TEXT      Database type (default: postgresql)
                       Choices: postgresql, mysql, sqlite
  --no-git             Don't initialize git repository
  --no-venv            Don't create virtual environment
  --help               Show help message
```

### Implementation

```python
# src/kailash/cli/create.py

import click
from pathlib import Path
from typing import Optional
import shutil
import os

@click.command()
@click.argument('project_name')
@click.option(
    '--template',
    default='saas-starter',
    type=click.Choice(['saas-starter', 'internal-tools', 'api-gateway']),
    help='Template to use'
)
@click.option(
    '--ai-mode/--no-ai-mode',
    default=True,
    help='Enable AI-optimized mode with embedded instructions'
)
@click.option(
    '--database',
    default='postgresql',
    type=click.Choice(['postgresql', 'mysql', 'sqlite']),
    help='Database type'
)
@click.option('--no-git', is_flag=True, help="Don't initialize git repository")
@click.option('--no-venv', is_flag=True, help="Don't create virtual environment")
def create(
    project_name: str,
    template: str,
    ai_mode: bool,
    database: str,
    no_git: bool,
    no_venv: bool
):
    """Create a new Kailash project from a template.

    Examples:

        # Create SaaS project with defaults
        kailash create my-saas

        # Create with SQLite (for testing)
        kailash create my-app --template=saas-starter --database=sqlite

        # Create API gateway
        kailash create my-gateway --template=api-gateway

        # Create without AI mode (minimal comments)
        kailash create my-app --no-ai-mode
    """
    click.echo(f"🚀 Creating Kailash project: {project_name}")
    click.echo(f"   Template: {template}")
    click.echo(f"   Database: {database}")
    click.echo(f"   AI Mode: {'enabled' if ai_mode else 'disabled'}")
    click.echo()

    # Validate project name
    if not _is_valid_project_name(project_name):
        click.echo(f"❌ Invalid project name: {project_name}")
        click.echo(f"   Use lowercase letters, numbers, hyphens only")
        return

    # Check if directory exists
    project_dir = Path(project_name)
    if project_dir.exists():
        click.echo(f"❌ Directory '{project_name}' already exists")
        click.echo(f"   Choose a different name or remove existing directory")
        return

    try:
        # Get template directory
        template_dir = _get_template_dir(template)

        if not template_dir.exists():
            click.echo(f"❌ Template '{template}' not found")
            click.echo(f"   Available templates: {', '.join(_list_templates())}")
            return

        # Load template metadata
        metadata = _load_template_metadata(template_dir)

        # Collect template variables
        variables = {
            'project_name': project_name,
            'database_type': database,
            'ai_mode': ai_mode,
        }

        # Prompt for additional variables (if any)
        if metadata.get('variables'):
            variables.update(_prompt_for_variables(metadata['variables']))

        # Copy template with variable substitution
        _copy_template(template_dir, project_dir, variables, ai_mode)

        # Post-creation setup
        _setup_project(project_dir, no_git, no_venv)

        # Success!
        click.echo()
        click.echo("✅ Project created successfully!")
        click.echo()
        click.echo("Next steps:")
        click.echo(f"  cd {project_name}")
        click.echo(f"  cp .env.example .env  # Add your configuration")
        click.echo(f"  # Edit .env: Set DATABASE_URL, API keys")
        click.echo(f"  kailash dev           # Start development server")
        click.echo()
        click.echo(f"📖 See {project_name}/CUSTOMIZE.md for customization guide")
        click.echo(f"📖 See {project_name}/README.md for getting started")

    except Exception as e:
        click.echo(f"❌ Error creating project: {e}")
        # Clean up partial creation
        if project_dir.exists():
            shutil.rmtree(project_dir)
        raise


def _is_valid_project_name(name: str) -> bool:
    """Validate project name."""
    import re
    # Lowercase, numbers, hyphens only
    pattern = r'^[a-z][a-z0-9-]*$'
    return re.match(pattern, name) is not None


def _get_template_dir(template: str) -> Path:
    """Get template directory path."""
    # Templates are in SDK: kailash/templates/{template}/
    import kailash
    kailash_root = Path(kailash.__file__).parent.parent
    return kailash_root / 'templates' / template


def _list_templates() -> list:
    """List available templates."""
    templates_dir = _get_template_dir('.').parent
    return [d.name for d in templates_dir.iterdir() if d.is_dir()]


def _load_template_metadata(template_dir: Path) -> dict:
    """Load template.json metadata."""
    metadata_file = template_dir / 'template.json'
    if not metadata_file.exists():
        return {}

    import json
    return json.loads(metadata_file.read_text())


def _copy_template(
    template_dir: Path,
    project_dir: Path,
    variables: dict,
    ai_mode: bool
):
    """Copy template files with variable substitution."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(template_dir))

    # Get all files
    for file_path in template_dir.rglob('*'):
        if file_path.is_file():
            relative_path = file_path.relative_to(template_dir)

            # Skip excluded files
            if _should_exclude(relative_path):
                continue

            # Skip AI instructions if ai_mode=False
            if not ai_mode and _is_ai_instruction(file_path):
                continue

            # Render template with variables
            if file_path.suffix in ['.py', '.md', '.txt', '.json', '.toml', '.yaml']:
                try:
                    template = env.get_template(str(relative_path))
                    content = template.render(**variables)
                except Exception as e:
                    # If not a Jinja2 template, copy as-is
                    content = file_path.read_text()
            else:
                content = file_path.read_bytes()

            # Write to project directory
            dest_path = project_dir / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, str):
                dest_path.write_text(content)
            else:
                dest_path.write_bytes(content)


def _setup_project(project_dir: Path, no_git: bool, no_venv: bool):
    """Post-creation setup."""

    # Initialize git
    if not no_git:
        click.echo("📦 Initializing git repository...")
        os.system(f"cd {project_dir} && git init -q")
        os.system(f"cd {project_dir} && git add .")
        os.system(f'cd {project_dir} && git commit -q -m "Initial commit from kailash template"')

    # Create virtual environment
    if not no_venv:
        click.echo("🐍 Creating virtual environment...")
        os.system(f"cd {project_dir} && python -m venv .venv")

        # Install dependencies
        click.echo("📥 Installing dependencies...")
        os.system(f"cd {project_dir} && .venv/bin/pip install -q -r requirements.txt")

    # Create .ai-mode marker (if ai_mode enabled)
    # This is used by SDK to detect AI-optimized projects
    (project_dir / '.ai-mode').write_text('true')

    click.echo("✅ Setup complete!")
```

---

## Command 2: kailash dev

**Purpose:** Run development server with auto-reload

**Signature:**
```bash
kailash dev [OPTIONS]

Options:
  --host TEXT        Host to bind (default: 0.0.0.0)
  --port INTEGER     Port to use (default: 8000)
  --reload/--no-reload   Auto-reload on file changes (default: True)
  --help             Show help message
```

### Implementation

```python
# src/kailash/cli/dev.py

import click
import subprocess
import sys
from pathlib import Path

@click.command()
@click.option('--host', default='0.0.0.0', help='Host to bind')
@click.option('--port', default=8000, help='Port to use')
@click.option('--reload/--no-reload', default=True, help='Auto-reload on changes')
def dev(host: str, port: int, reload: bool):
    """Run development server with auto-reload.

    Automatically detects and runs:
    - Quick Mode apps (if using kailash.quick)
    - Full SDK apps (if using Nexus directly)

    Examples:

        # Run with defaults
        kailash dev

        # Run on different port
        kailash dev --port 9000

        # Disable auto-reload
        kailash dev --no-reload
    """
    click.echo(f"🚀 Starting Kailash development server...")
    click.echo(f"   Host: {host}")
    click.echo(f"   Port: {port}")
    click.echo(f"   Auto-reload: {'enabled' if reload else 'disabled'}")
    click.echo()

    # Find entry point (main.py, app.py, or first .py file)
    entry_point = _find_entry_point()

    if not entry_point:
        click.echo("❌ No entry point found")
        click.echo("   Create main.py or app.py in current directory")
        return

    click.echo(f"📂 Entry point: {entry_point}")
    click.echo()

    # Run with auto-reload (using watchdog)
    if reload:
        _run_with_reload(entry_point, host, port)
    else:
        _run_without_reload(entry_point, host, port)


def _find_entry_point() -> Optional[Path]:
    """Find main entry point file."""
    candidates = ['main.py', 'app.py', 'server.py']

    for candidate in candidates:
        if Path(candidate).exists():
            return Path(candidate)

    # Fallback: First .py file
    py_files = list(Path('.').glob('*.py'))
    return py_files[0] if py_files else None


def _run_with_reload(entry_point: Path, host: str, port: int):
    """Run with auto-reload using watchdog."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        import threading
    except ImportError:
        click.echo("⚠️  Auto-reload requires 'watchdog' package")
        click.echo("   Install: pip install watchdog")
        click.echo("   Running without auto-reload...")
        _run_without_reload(entry_point, host, port)
        return

    # File change handler
    class ReloadHandler(FileSystemEventHandler):
        def __init__(self, restart_callback):
            self.restart_callback = restart_callback

        def on_modified(self, event):
            if event.src_path.endswith('.py'):
                click.echo(f"🔄 File changed: {event.src_path}")
                self.restart_callback()

    # Process management
    process = None

    def start_process():
        nonlocal process
        if process:
            process.terminate()
            process.wait()

        click.echo("▶️  Starting server...")
        process = subprocess.Popen(
            [sys.executable, str(entry_point)],
            env={**os.environ, "KAILASH_HOST": host, "KAILASH_PORT": str(port)}
        )

    # Start initial process
    start_process()

    # Watch for changes
    observer = Observer()
    observer.schedule(ReloadHandler(start_process), path='.', recursive=True)
    observer.start()

    try:
        click.echo("👀 Watching for file changes... (Ctrl+C to stop)")
        observer.join()
    except KeyboardInterrupt:
        click.echo("\n⏹️  Stopping server...")
        observer.stop()
        if process:
            process.terminate()


def _run_without_reload(entry_point: Path, host: str, port: int):
    """Run without auto-reload."""
    os.environ["KAILASH_HOST"] = host
    os.environ["KAILASH_PORT"] = str(port)

    subprocess.run([sys.executable, str(entry_point)])
```

**Usage:**
```bash
# In project directory
kailash dev

# Output:
# 🚀 Starting Kailash development server...
#    Host: 0.0.0.0
#    Port: 8000
#    Auto-reload: enabled
# 📂 Entry point: main.py
# ▶️  Starting server...
# ✅ Nexus started at http://0.0.0.0:8000
# 👀 Watching for file changes... (Ctrl+C to stop)

# Change file...
# 🔄 File changed: workflows/users.py
# ▶️  Starting server...
# ✅ Nexus restarted
```

---

## Command 2: kailash upgrade

**Purpose:** Upgrade Quick Mode project to Full SDK

**Signature:**
```bash
kailash upgrade [OPTIONS]

Options:
  --to TEXT          Target mode (default: standard)
                     Choices: standard, enterprise
  --analyze          Analyze project without upgrading
  --force            Force upgrade without confirmation
  --backup/--no-backup   Create backup (default: True)
  --help             Show help message
```

### Implementation

```python
# src/kailash/cli/upgrade.py

import click
from pathlib import Path
import shutil
import ast

@click.command()
@click.option(
    '--to',
    'target',
    default='standard',
    type=click.Choice(['standard', 'enterprise']),
    help='Target mode'
)
@click.option('--analyze', is_flag=True, help='Analyze without upgrading')
@click.option('--force', is_flag=True, help='Skip confirmation')
@click.option('--backup/--no-backup', default=True, help='Create backup')
def upgrade(target: str, analyze: bool, force: bool, backup: bool):
    """Upgrade Quick Mode project to Full SDK.

    Analyzes your Quick Mode code and converts to standard Kailash SDK.

    Examples:

        # Analyze project (no changes)
        kailash upgrade --analyze

        # Upgrade to standard SDK
        kailash upgrade --to=standard

        # Upgrade to enterprise mode (all features)
        kailash upgrade --to=enterprise
    """
    click.echo("🔍 Analyzing project...")

    # Detect Quick Mode usage
    analysis = _analyze_project()

    if not analysis['is_quick_mode']:
        click.echo("ℹ️  This project is not using Quick Mode")
        click.echo("   No upgrade needed")
        return

    # Display analysis
    _display_analysis(analysis)

    if analyze:
        # Just show analysis, don't upgrade
        click.echo()
        click.echo("💡 To upgrade, run: kailash upgrade --to=standard")
        return

    # Confirm upgrade
    if not force:
        click.echo()
        click.confirm('Continue with upgrade?', abort=True)

    # Create backup
    if backup:
        click.echo()
        click.echo("💾 Creating backup...")
        _create_backup()

    # Perform upgrade
    click.echo()
    click.echo(f"🔄 Upgrading to {target} mode...")

    try:
        if target == 'standard':
            _upgrade_to_standard(analysis)
        elif target == 'enterprise':
            _upgrade_to_enterprise(analysis)

        click.echo()
        click.echo("✅ Upgrade complete!")
        click.echo()
        click.echo("Next steps:")
        click.echo("  1. Review generated code in workflows/")
        click.echo("  2. Test: kailash dev")
        click.echo("  3. Commit changes")
        click.echo()
        click.echo(f"📖 See UPGRADE.md for details")
        click.echo(f"💾 Backup saved in .kailash/backup/")

    except Exception as e:
        click.echo(f"❌ Upgrade failed: {e}")
        click.echo()
        click.echo("Restoring from backup...")
        _restore_backup()
        raise


def _analyze_project() -> dict:
    """Analyze project structure and Quick Mode usage."""

    analysis = {
        'is_quick_mode': False,
        'quick_mode_files': [],
        'models': [],
        'workflows': [],
        'complexity': 'low',
        'upgrade_recommendation': None
    }

    # Check for .ai-mode marker
    if Path('.ai-mode').exists():
        analysis['is_quick_mode'] = True

    # Scan Python files for Quick Mode imports
    for py_file in Path('.').rglob('*.py'):
        if _file_uses_quick_mode(py_file):
            analysis['is_quick_mode'] = True
            analysis['quick_mode_files'].append(str(py_file))

            # Extract models and workflows
            file_analysis = _analyze_file(py_file)
            analysis['models'].extend(file_analysis['models'])
            analysis['workflows'].extend(file_analysis['workflows'])

    # Assess complexity
    if len(analysis['workflows']) > 10:
        analysis['complexity'] = 'high'
    elif len(analysis['workflows']) > 5:
        analysis['complexity'] = 'medium'

    # Generate recommendation
    analysis['upgrade_recommendation'] = _generate_recommendation(analysis)

    return analysis


def _file_uses_quick_mode(file_path: Path) -> bool:
    """Check if file imports kailash.quick."""
    try:
        content = file_path.read_text()
        return 'from kailash.quick import' in content
    except:
        return False


def _analyze_file(file_path: Path) -> dict:
    """Analyze Python file for models and workflows."""
    try:
        content = file_path.read_text()
        tree = ast.parse(content)

        models = []
        workflows = []

        for node in ast.walk(tree):
            # Find @db.model decorated classes
            if isinstance(node, ast.ClassDef):
                if any(d.id == 'model' for d in node.decorator_list if hasattr(d, 'id')):
                    models.append(node.name)

            # Find @app.post/get/workflow decorated functions
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if hasattr(decorator, 'func'):
                        if hasattr(decorator.func, 'attr'):
                            if decorator.func.attr in ['post', 'get', 'workflow']:
                                workflows.append(node.name)

        return {'models': models, 'workflows': workflows}
    except:
        return {'models': [], 'workflows': []}


def _display_analysis(analysis: dict):
    """Display project analysis."""
    click.echo()
    click.echo("📊 Project Analysis")
    click.echo("=" * 40)
    click.echo(f"Mode: Quick Mode")
    click.echo(f"Files using Quick Mode: {len(analysis['quick_mode_files'])}")
    click.echo(f"Models: {len(analysis['models'])}")
    click.echo(f"Workflows: {len(analysis['workflows'])}")
    click.echo(f"Complexity: {analysis['complexity']}")
    click.echo()
    click.echo("Upgrade Benefits:")
    click.echo("  ✅ Full workflow control")
    click.echo("  ✅ Advanced error handling")
    click.echo("  ✅ Custom middleware")
    click.echo("  ✅ Performance optimization")
    click.echo()
    click.echo("Upgrade Costs:")
    click.echo("  ⚠️  More code to maintain")
    click.echo("  ⚠️  Steeper learning curve")
    click.echo("  ⚠️  Must understand WorkflowBuilder")
    click.echo()
    click.echo(f"Recommendation: {analysis['upgrade_recommendation']}")


def _generate_recommendation(analysis: dict) -> str:
    """Generate upgrade recommendation."""
    if analysis['complexity'] == 'low':
        return "Stay in Quick Mode (project is simple, no complex workflows)"
    elif analysis['complexity'] == 'medium':
        return "Consider upgrade if you need advanced features"
    else:
        return "Upgrade recommended (complex workflows benefit from Full SDK)"


def _upgrade_to_standard(analysis: dict):
    """Convert Quick Mode to Standard SDK.

    Generates:
    - main.py (Nexus initialization)
    - workflows/ directory (converted from Quick Mode)
    - models/ directory (DataFlow models, unchanged)
    - UPGRADE.md (documentation of changes)
    """
    # Implementation: Code generation from Quick Mode to Full SDK
    # This is complex - parses Quick Mode code, generates Full SDK equivalent

    # 1. Convert Quick Mode imports to Full SDK imports
    # 2. Convert @app.post decorators to workflow functions
    # 3. Convert db.users.create() to WorkflowBuilder
    # 4. Generate main.py with Nexus setup
    # 5. Generate UPGRADE.md documentation

    pass


def _create_backup():
    """Create backup of current state."""
    backup_dir = Path('.kailash/backup')
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Copy all Python files
    for py_file in Path('.').glob('*.py'):
        shutil.copy(py_file, backup_dir / py_file.name)

    click.echo(f"✅ Backup created in .kailash/backup/")


def _restore_backup():
    """Restore from backup."""
    backup_dir = Path('.kailash/backup')

    if not backup_dir.exists():
        click.echo("❌ No backup found")
        return

    for backup_file in backup_dir.glob('*.py'):
        shutil.copy(backup_file, backup_file.name)

    click.echo("✅ Restored from backup")
```

---

## Command 3: kailash marketplace

**Purpose:** Component marketplace operations

**Signature:**
```bash
kailash marketplace [COMMAND] [OPTIONS]

Commands:
  search [QUERY]      Search for components
  install [PACKAGE]   Install component
  list                List installed components
  update [PACKAGE]    Update component
  outdated            Show outdated components

Options:
  --help              Show help message
```

### Implementation

```python
# src/kailash/cli/marketplace.py

import click
import subprocess
import requests

@click.group()
def marketplace():
    """Component marketplace operations."""
    pass


@marketplace.command()
@click.argument('query')
def search(query: str):
    """Search for components in marketplace.

    Examples:

        kailash marketplace search authentication
        kailash marketplace search payment
        kailash marketplace search dataflow
    """
    click.echo(f"🔍 Searching for '{query}'...")
    click.echo()

    # Search PyPI for kailash-{query}
    components = _search_pypi(query)

    if not components:
        click.echo(f"No components found matching '{query}'")
        click.echo()
        click.echo("💡 Try broader search terms:")
        click.echo("   - auth (instead of authentication)")
        click.echo("   - pay (instead of payment)")
        return

    # Display results
    for component in components:
        _display_component(component)
        click.echo()

    click.echo(f"Found {len(components)} component(s)")
    click.echo()
    click.echo("To install: kailash marketplace install [package-name]")


@marketplace.command()
@click.argument('package')
def install(package: str):
    """Install a component.

    Examples:

        kailash marketplace install kailash-sso
        kailash marketplace install kailash-rbac
    """
    click.echo(f"📦 Installing {package}...")

    try:
        # Use pip to install
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package],
            check=True
        )

        click.echo(f"✅ {package} installed successfully!")
        click.echo()
        click.echo("Next steps:")
        click.echo(f"  1. Import: from {package.replace('-', '_')} import ...")
        click.echo(f"  2. See docs: https://docs.kailash.dev/components/{package}")

    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Installation failed: {e}")


@marketplace.command()
def list():
    """List installed Kailash components."""
    click.echo("📦 Installed Kailash components:")
    click.echo()

    # Get installed packages
    installed = _get_installed_kailash_packages()

    if not installed:
        click.echo("   No components installed")
        click.echo()
        click.echo("💡 Install components:")
        click.echo("   kailash marketplace search [query]")
        return

    for package in installed:
        click.echo(f"   ✅ {package['name']} ({package['version']})")

    click.echo()
    click.echo(f"Total: {len(installed)} component(s)")


@marketplace.command()
@click.argument('package', required=False)
def update(package: Optional[str]):
    """Update component(s).

    Examples:

        # Update specific component
        kailash marketplace update kailash-sso

        # Update all components
        kailash marketplace update
    """
    if package:
        # Update specific package
        click.echo(f"⬆️  Updating {package}...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', package], check=True)
        click.echo(f"✅ {package} updated!")
    else:
        # Update all Kailash components
        click.echo("⬆️  Updating all Kailash components...")

        installed = _get_installed_kailash_packages()

        for package_info in installed:
            package = package_info['name']
            click.echo(f"   Updating {package}...")
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', package],
                check=True,
                capture_output=True
            )

        click.echo(f"✅ Updated {len(installed)} component(s)!")


@marketplace.command()
def outdated():
    """Show outdated components."""
    click.echo("🔍 Checking for updates...")
    click.echo()

    installed = _get_installed_kailash_packages()

    outdated_components = []

    for package_info in installed:
        latest_version = _get_latest_version(package_info['name'])

        if latest_version and latest_version != package_info['version']:
            outdated_components.append({
                **package_info,
                'latest_version': latest_version
            })

    if not outdated_components:
        click.echo("✅ All components up to date!")
        return

    click.echo(f"Found {len(outdated_components)} outdated component(s):")
    click.echo()

    for component in outdated_components:
        click.echo(f"📦 {component['name']}")
        click.echo(f"   Installed: {component['version']}")
        click.echo(f"   Available: {component['latest_version']}")
        click.echo()

    click.echo("To update: kailash marketplace update")


# Helper functions

def _search_pypi(query: str) -> list:
    """Search PyPI for kailash-* packages."""
    results = []

    # Try exact match first
    try:
        response = requests.get(f"https://pypi.org/pypi/kailash-{query}/json")
        if response.status_code == 200:
            data = response.json()
            results.append(_format_component_info(data))
    except:
        pass

    # Then try general search
    # ... (PyPI search API)

    return results


def _format_component_info(pypi_data: dict) -> dict:
    """Format PyPI data to component info."""
    info = pypi_data['info']
    return {
        'name': info['name'],
        'version': info['version'],
        'description': info['summary'],
        'author': info['author'],
        'license': info['license'],
        'downloads': info.get('downloads', {}).get('last_month', 0)
    }


def _display_component(component: dict):
    """Display component information."""
    click.echo(f"📦 {component['name']} (v{component['version']})")
    click.echo(f"   {component['description']}")
    click.echo(f"   Author: {component['author']}")
    click.echo(f"   Downloads: {component['downloads']:,}/month")


def _get_installed_kailash_packages() -> list:
    """Get list of installed kailash-* packages."""
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'list', '--format=json'],
        capture_output=True,
        text=True
    )

    import json
    packages = json.loads(result.stdout)

    # Filter for kailash-* packages
    kailash_packages = [
        {'name': pkg['name'], 'version': pkg['version']}
        for pkg in packages
        if pkg['name'].startswith('kailash-')
    ]

    return kailash_packages


def _get_latest_version(package: str) -> Optional[str]:
    """Get latest version from PyPI."""
    try:
        response = requests.get(f"https://pypi.org/pypi/{package}/json")
        if response.status_code == 200:
            data = response.json()
            return data['info']['version']
    except:
        return None
```

---

## Command 4: kailash component create

**Purpose:** Create new component (for developers contributing to marketplace)

**Signature:**
```bash
kailash component create [PACKAGE_NAME] [OPTIONS]

Options:
  --author TEXT      Author name
  --email TEXT       Author email
  --license TEXT     License (default: MIT)
  --help             Show help message
```

### Implementation

```python
# src/kailash/cli/component.py

import click
from pathlib import Path

@click.group()
def component():
    """Component development tools."""
    pass


@component.command()
@click.argument('package_name')
@click.option('--author', prompt='Author name', help='Component author')
@click.option('--email', prompt='Author email', help='Author email')
@click.option('--license', default='MIT', help='License type')
def create(package_name: str, author: str, email: str, license: str):
    """Create new component from template.

    Examples:

        kailash component create kailash-mycomponent
    """
    click.echo(f"📦 Creating component: {package_name}")

    # Validate package name
    if not package_name.startswith('kailash-'):
        click.echo("⚠️  Component names should start with 'kailash-'")
        package_name = f"kailash-{package_name}"
        click.echo(f"   Using: {package_name}")

    # Get component template
    template_dir = _get_component_template()

    # Variables for template rendering
    variables = {
        'package_name': package_name,
        'module_name': package_name.replace('-', '_'),
        'author': author,
        'email': email,
        'license': license,
        'year': datetime.now().year
    }

    # Copy template with substitution
    project_dir = Path(package_name)
    _copy_template(template_dir, project_dir, variables)

    click.echo()
    click.echo("✅ Component created!")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  cd {package_name}")
    click.echo(f"  # Implement your component in src/{variables['module_name']}/")
    click.echo(f"  # Add tests in tests/")
    click.echo(f"  # Update README.md and CLAUDE.md")
    click.echo(f"  # When ready: python -m build && twine upload dist/*")
```

---

## CLI Entry Point

```python
# src/kailash/cli/__init__.py

import click

@click.group()
def cli():
    """Kailash SDK command-line interface."""
    pass

# Register commands
from .create import create
from .dev import dev
from .upgrade import upgrade
from .marketplace import marketplace
from .component import component

cli.add_command(create)
cli.add_command(dev)
cli.add_command(upgrade)
cli.add_command(marketplace)
cli.add_command(component)

if __name__ == '__main__':
    cli()
```

```python
# src/kailash/cli/__main__.py

from . import cli

if __name__ == '__main__':
    cli()
```

**Installation:**
```toml
# pyproject.toml

[project.scripts]
kailash = "kailash.cli:cli"
```

**Usage:**
```bash
# After pip install kailash
kailash --help

# Output:
# Usage: kailash [OPTIONS] COMMAND [ARGS]...
#
# Kailash SDK command-line interface.
#
# Commands:
#   create       Create new project from template
#   dev          Run development server
#   upgrade      Upgrade Quick Mode to Full SDK
#   marketplace  Component marketplace operations
#   component    Component development tools
```

---

## Testing

### CLI Tests

```python
# tests/cli/test_create_command.py

from click.testing import CliRunner
from kailash.cli.create import create

def test_create_command_generates_project():
    """Test that create command generates project structure."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(create, [
            'test-project',
            '--template=saas-starter',
            '--database=sqlite'
        ])

        assert result.exit_code == 0
        assert Path('test-project').exists()
        assert Path('test-project/main.py').exists()
        assert Path('test-project/CUSTOMIZE.md').exists()

def test_create_validates_project_name():
    """Test that create validates project name."""
    runner = CliRunner()

    result = runner.invoke(create, ['Invalid Name'])  # Spaces not allowed

    assert result.exit_code != 0
    assert 'Invalid project name' in result.output
```

---

## Documentation

### CLI Reference

**Location:** `sdk-users/docs-it-teams/cli-reference.md`

```markdown
# Kailash CLI Reference

## kailash create

Create new project from template.

```bash
kailash create my-saas --template=saas-starter
```

[... detailed docs for each command ...]

## Quick Reference

| Command | Purpose |
|---------|---------|
| `kailash create` | Create from template |
| `kailash dev` | Run dev server |
| `kailash upgrade` | Upgrade to Full SDK |
| `kailash marketplace search` | Find components |
| `kailash marketplace install` | Install component |
```

---

## Implementation Timeline

**Week 1-2:** Implement `kailash create` command
**Week 3:** Implement `kailash dev` command
**Week 4:** Implement `kailash marketplace` commands
**Week 5:** Implement `kailash upgrade` command
**Week 6:** Testing and documentation

---

## Key Takeaways

**CLI is the primary interface for IT teams:**
- `kailash create` gets them started quickly
- `kailash dev` provides fast iteration
- `kailash marketplace` enables component discovery
- `kailash upgrade` provides growth path

**Success criteria:**
- 80% of template projects use `kailash dev`
- 60% discover components via `kailash marketplace search`
- 30% eventually run `kailash upgrade`

**Implementation is straightforward:**
- All new code (no modifications to existing)
- Uses Click library (familiar to Python developers)
- Wraps existing SDK functionality

---

**Next:** See `05-documentation-reorganization.md` for docs structure
