# Documentation Reorganization

**Location:** `sdk-users/` directory restructure
**Estimated Effort:** 30 hours
**Risk:** Low (creating new structure, keeping old for reference)

---

## Current Documentation Structure

```
sdk-users/
├── 1-quickstart/           # Getting started
├── 2-core-concepts/        # Nodes, workflows, patterns
├── 3-development/          # Development guides
├── 4-features/             # Advanced features
├── 5-enterprise/           # Enterprise patterns
├── 6-reference/            # API reference
├── 7-gold-standards/       # Best practices
├── examples/               # Code examples
└── apps/                   # Framework docs (DataFlow, Nexus, Kaizen)

Total: ~250,000 lines
Categories: 17
Skills: 246
```

**Problem for IT teams:**
- Overwhelming (too much information)
- Developer-focused (assumes coding knowledge)
- No clear "where to start" for AI-assisted development

**Problem for developers:**
- Mixed with IT team content
- Hard to find advanced topics
- No separation of skill levels

---

## New Documentation Structure

### Two Parallel Documentation Trees

```
sdk-users/
├── docs-it-teams/          # NEW: For IT teams + AI assistants
│   ├── getting-started/
│   │   ├── 5-minute-quickstart.md
│   │   ├── your-first-app.md
│   │   └── using-claude-code.md
│   │
│   ├── templates/
│   │   ├── saas-starter-guide.md
│   │   ├── internal-tools-guide.md
│   │   └── customization-patterns.md
│   │
│   ├── quick-mode/
│   │   ├── quickstart.md
│   │   ├── models.md
│   │   ├── workflows.md
│   │   ├── deployment.md
│   │   └── upgrade.md
│   │
│   ├── patterns/            # 10 Golden Patterns
│   │   ├── 01-dataflow-model.md
│   │   ├── 02-create-workflow.md
│   │   ├── 03-deploy-nexus.md
│   │   ├── 04-external-api.md
│   │   ├── 05-authentication.md
│   │   ├── 06-multi-tenancy.md
│   │   ├── 07-background-jobs.md
│   │   ├── 08-file-processing.md
│   │   ├── 09-error-handling.md
│   │   └── 10-conditional-logic.md
│   │
│   ├── dataflow/
│   │   ├── quickstart.md
│   │   ├── common-errors.md
│   │   └── field-helpers.md
│   │
│   ├── nexus/
│   │   ├── presets-guide.md
│   │   └── deployment.md
│   │
│   ├── marketplace/
│   │   ├── using-components.md
│   │   ├── component-catalog.md
│   │   └── popular-components.md
│   │
│   ├── ai-features/
│   │   ├── using-kaizen-components.md
│   │   └── document-processing.md
│   │
│   └── troubleshooting/
│       ├── common-errors.md
│       ├── getting-help.md
│       └── faq.md
│
├── docs-developers/        # NEW: For software developers
│   ├── architecture/
│   │   ├── core-sdk-internals.md
│   │   ├── workflow-engine.md
│   │   └── runtime-system.md
│   │
│   ├── advanced/
│   │   ├── custom-nodes.md
│   │   ├── custom-runtimes.md
│   │   └── cyclic-workflows.md
│   │
│   ├── frameworks/
│   │   ├── dataflow-deep-dive.md
│   │   ├── nexus-internals.md
│   │   └── kaizen-architecture.md
│   │
│   ├── contributing/
│   │   ├── development-setup.md
│   │   ├── testing-guide.md
│   │   └── pull-request-process.md
│   │
│   ├── performance/
│   │   ├── optimization-guide.md
│   │   └── benchmarking.md
│   │
│   └── reference/
│       ├── complete-api-reference.md
│       ├── node-catalog.md
│       └── error-reference.md
│
└── [existing docs kept for reference]
    ├── 1-quickstart/
    ├── 2-core-concepts/
    └── ...
```

---

## Documentation Philosophy

### For IT Teams

**Principles:**
1. **Outcome-focused** - "How to build X" not "How X works"
2. **Copy-paste ready** - Working examples, not theory
3. **AI-optimized** - Embedded in code, not separate files
4. **Progressive** - Start simple, link to advanced

**Example structure:**
```markdown
# Building Your First SaaS App (5 Minutes)

## What You'll Build

A working multi-tenant SaaS with:
- User authentication
- Database models
- API endpoints
- Admin dashboard

## Prerequisites

- Python 3.10+
- PostgreSQL (or use SQLite for testing)
- 5 minutes

## Step 1: Create Project (1 minute)

```bash
kailash create my-saas --template=saas-starter
cd my-saas
```

## Step 2: Configure (2 minutes)

```bash
cp .env.example .env
# Edit .env:
#   DATABASE_URL=postgresql://localhost/mydb
```

## Step 3: Run (1 minute)

```bash
kailash dev
```

## Step 4: Test (1 minute)

Open browser: http://localhost:8000/docs

**That's it! You have a working SaaS.**

## Next Steps

- [Customize models](customization-patterns.md#adding-models)
- [Add workflows](customization-patterns.md#adding-workflows)
- [Deploy to production](deployment.md)

## Using Claude Code

This template is optimized for Claude Code. To customize:

1. Describe what you want in plain English
2. Claude Code modifies the files
3. Test with `kailash dev`

Example:
> "Add a 'Product' model with name, price, and description fields"

Claude Code will:
- Add model in models/product.py
- Generate CRUD workflows
- Update main.py to register workflows
```

**Key differences from developer docs:**
- Starts with outcome ("What you'll build")
- Time estimates (5 minutes, not hours)
- No theory (just do this)
- AI assistant guidance prominent

### For Developers

**Principles:**
1. **Architecture-focused** - "How X works" not just "How to use X"
2. **Comprehensive** - Cover edge cases, internals
3. **Reference quality** - Technical accuracy paramount
4. **Contribution-ready** - Enable developers to extend SDK

**Example structure:**
```markdown
# WorkflowBuilder Internals

## Architecture

WorkflowBuilder constructs directed acyclic graphs (DAGs) representing workflow execution plans.

### Node Registration

When you call `add_node()`:

```python
def add_node(self, node_class: str, node_id: str, parameters: dict):
    # 1. Validate node_class exists in registry
    # 2. Create NodeInstance
    # 3. Add to internal graph structure
    # 4. Return self for chaining
```

Internally:
- Graph representation: adjacency list
- Node storage: Dict[str, NodeInstance]
- Connection validation: Ensures valid source/target ports

### Build Process

When you call `build()`:

```python
def build(self) -> Workflow:
    # 1. Validate graph (no cycles, no disconnected nodes)
    # 2. Topological sort (determine execution order)
    # 3. Create Workflow object
    # 4. Return immutable workflow
```

[... detailed technical content ...]

## Extending WorkflowBuilder

To add custom functionality:

```python
class CustomWorkflowBuilder(WorkflowBuilder):
    def add_monitored_node(self, ...):
        # Add node with automatic monitoring
        pass
```

[... advanced developer content ...]
```

**Key differences from IT team docs:**
- Starts with internals
- Technical depth (algorithms, data structures)
- Assumes coding knowledge
- Enables extension and contribution

---

## AI Context Engineering

### Detection System

**Auto-detect user type from project:**

```python
# src/kailash/utils/context_detection.py (NEW FILE)

def detect_user_context() -> str:
    """Detect if project is IT-team or developer context.

    Returns:
        "it-team" | "developer" | "unknown"
    """
    # Check for .ai-mode marker
    if Path('.ai-mode').exists():
        return "it-team"

    # Check for Quick Mode imports
    if _uses_quick_mode():
        return "it-team"

    # Check for template origin
    if Path('CUSTOMIZE.md').exists():  # Templates have this
        return "it-team"

    # Check for advanced SDK usage
    if _uses_advanced_features():
        return "developer"

    return "unknown"


def _uses_quick_mode() -> bool:
    """Check if any Python file imports kailash.quick."""
    for py_file in Path('.').glob('*.py'):
        try:
            content = py_file.read_text()
            if 'from kailash.quick import' in content:
                return True
        except:
            continue
    return False


def _uses_advanced_features() -> bool:
    """Check for advanced SDK features."""
    advanced_imports = [
        'from kailash.workflow.cycle_builder',
        'from kailash.runtime.parallel',
        'from kailash.middleware',
        'CustomNode',  # Custom node development
    ]

    for py_file in Path('.').glob('*.py'):
        try:
            content = py_file.read_text()
            if any(imp in content for imp in advanced_imports):
                return True
        except:
            continue

    return False
```

### Context-Aware Skills (Update .claude/skills/)

**For IT team projects:**
```python
# In .claude/context/skills.json (auto-generated)

{
  "context": "it-team",
  "skills": [
    # Only 10 Golden Patterns
    "golden-pattern-1-dataflow-model",
    "golden-pattern-2-create-workflow",
    "golden-pattern-3-deploy-nexus",
    "golden-pattern-4-external-api",
    "golden-pattern-5-authentication",
    "golden-pattern-6-multi-tenancy",
    "golden-pattern-7-background-jobs",
    "golden-pattern-8-file-processing",
    "golden-pattern-9-error-handling",
    "golden-pattern-10-conditional-logic"
  ],
  "docs_path": "sdk-users/docs-it-teams/",
  "full_docs_available": true,
  "note": "For advanced use cases, see sdk-users/docs-developers/"
}
```

**For developer projects:**
```python
# In .claude/context/skills.json

{
  "context": "developer",
  "skills": "all",  # All 246 skills available
  "docs_path": "sdk-users/docs-developers/",
  "it_team_docs_available": true
}
```

**Claude Code behavior:**
- Reads `.claude/context/skills.json` (if exists)
- If "it-team" → Use 10 Golden Patterns only
- If "developer" → Use all 246 skills
- If "unknown" → Ask user preference

---

## Migration of Existing Content

### What to Keep (Reference)

**Keep in original location:**
- All existing documentation (for reference)
- API reference (comprehensive)
- Historical guides (may be useful)

**Mark as deprecated:**
```markdown
# At top of old docs

> ⚠️  **Documentation Reorganized**
>
> This documentation has been reorganized:
> - **IT Teams:** See [docs-it-teams/](../docs-it-teams/)
> - **Developers:** See [docs-developers/](../docs-developers/)
>
> This file is kept for reference but may be outdated.
```

### What to Rewrite

**IT Team Docs (New):**
- Quick starts (5-minute focus)
- 10 Golden Patterns (copy-paste ready)
- Troubleshooting (common errors with fixes)

**Developer Docs (Curated from existing):**
- Architecture guides (from existing advanced docs)
- API reference (from existing reference docs)
- Contribution guide (from contributor docs)

**Not duplicated:**
- Don't copy everything twice
- Link between docs where appropriate
- IT team docs can link to developer docs for deep dives

---

## Documentation Standards

### IT Team Documentation

**Format:**
```markdown
# [Action] ([Time Estimate])

Brief description of what you'll achieve.

## What You'll Build

Concrete outcome description.

## Prerequisites

- Requirement 1
- Requirement 2

## Steps

### Step 1: [Action] ([Time])

[copy-paste code block]

**What this does:** Brief explanation

### Step 2: [Action] ([Time])

[copy-paste code block]

## Testing

How to verify it works.

## Troubleshooting

### Issue: [Common problem]

**Solution:** [Fix]

## Next Steps

- [Link to next guide]
- [Link to related pattern]

## Using Claude Code

How to use Claude Code for this task.
```

**Example:**
```markdown
# Add Authentication to Your App (15 minutes)

Add user login and registration to your application.

## What You'll Build

- User login (email/password)
- User registration
- JWT token authentication
- Protected endpoints

## Prerequisites

- Existing Kailash project
- 15 minutes

## Steps

### Step 1: Install kailash-sso (2 minutes)

```bash
pip install kailash-sso
```

**What this does:** Adds authentication component to your project

[... etc ...]
```

### Developer Documentation

**Format:**
```markdown
# [Component/Concept Name]

## Overview

Technical overview of the component.

## Architecture

Detailed architecture explanation with diagrams.

## API Reference

### Class: [ClassName]

```python
class ClassName:
    def method(self, param: Type) -> ReturnType:
        """Docstring"""
```

**Parameters:**
- `param` (Type): Description

**Returns:**
- ReturnType: Description

**Raises:**
- Exception: When

## Implementation Details

How it works internally.

## Advanced Usage

Complex scenarios and edge cases.

## Performance Considerations

Optimization tips and benchmarks.

## Contributing

How to extend or contribute.
```

---

## .claude/skills/ Reorganization

### Current Structure (246 Skills)

```
.claude/skills/
├── 01-core-sdk/          (14 skills)
├── 02-dataflow/          (12 skills)
├── 03-nexus/             (8 skills)
├── 04-kaizen/            (15 skills)
├── 05-mcp/               (10 skills)
├── 06-cheatsheets/       (20 skills)
├── 07-development-guides/ (45 skills)
├── 08-nodes-reference/   (30 skills)
├── 09-workflow-patterns/ (25 skills)
├── 10-deployment-git/    (8 skills)
├── 11-frontend-integration/ (6 skills)
├── 12-testing-strategies/ (12 skills)
├── 13-architecture-decisions/ (8 skills)
├── 14-code-templates/    (7 skills)
├── 15-error-troubleshooting/ (10 skills)
├── 16-validation-patterns/ (8 skills)
└── 17-gold-standards/    (8 skills)

Total: 246 skills
```

### New Structure (Context-Aware)

```
.claude/skills/
├── it-team/              # NEW: 10 Golden Patterns for IT teams
│   ├── 01-dataflow-model.md
│   ├── 02-create-workflow.md
│   ├── 03-deploy-nexus.md
│   ├── 04-external-api.md
│   ├── 05-authentication.md
│   ├── 06-multi-tenancy.md
│   ├── 07-background-jobs.md
│   ├── 08-file-processing.md
│   ├── 09-error-handling.md
│   └── 10-conditional-logic.md
│
├── developer/            # Existing 246 skills (reorganized)
│   ├── core-sdk/
│   ├── dataflow/
│   ├── nexus/
│   └── ...
│
└── context-detection.md  # How to choose it-team vs developer
```

### Auto-Selection Logic

**In CLAUDE.md (root):**
```python
"""
## 🎯 Context-Aware Skill Loading

The SDK automatically detects your context and loads appropriate skills:

IT Team Context (10 Golden Patterns):
- Detected by: .ai-mode file, Quick Mode imports, template origin
- Skills: 10 essential patterns
- Docs: sdk-users/docs-it-teams/
- Optimization: 90% token reduction

Developer Context (Full SDK):
- Detected by: Advanced features, custom nodes, Full SDK imports
- Skills: All 246 skills
- Docs: sdk-users/docs-developers/
- Optimization: Comprehensive coverage

To manually set context:
- Create .ai-mode file for IT team mode
- Delete .ai-mode file for developer mode

Or set environment variable:
export KAILASH_CONTEXT=it-team  # or developer
"""
```

---

## Documentation Generation

### Automated from Code

**Generate API reference from docstrings:**
```python
# scripts/generate_api_docs.py

from kailash.workflow.builder import WorkflowBuilder
import inspect

def generate_api_docs():
    """Generate API reference from code."""

    # Extract docstrings
    classes = [WorkflowBuilder, LocalRuntime, DataFlow, Nexus]

    for cls in classes:
        # Generate markdown from docstrings
        doc = f"# {cls.__name__}\n\n"
        doc += cls.__doc__ or "No description"
        doc += "\n\n## Methods\n\n"

        for name, method in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith('_'):
                doc += f"### {name}\n\n"
                doc += method.__doc__ or "No description"
                doc += "\n\n"

        # Write to file
        output_path = f"sdk-users/docs-developers/reference/{cls.__name__.lower()}.md"
        Path(output_path).write_text(doc)

# Run on every release
```

### AI Assistant Generation

**Generate CLAUDE.md for each component:**
```python
# scripts/generate_claude_md.py

def generate_claude_md_for_component(component_name: str):
    """Generate CLAUDE.md for component."""

    template = f"""
# Claude Code Instructions for {component_name}

## Quick Usage

```python
pip install {component_name}

from {component_name.replace('-', '_')} import [MainClass]
```

## AI Instructions

When user asks for [feature]:
1. Install {component_name}
2. Configure with minimal parameters
3. Use pre-built workflows

DO NOT build [feature] from scratch when {component_name} exists.

## Common Patterns

[Auto-generated from examples/]

## Common Mistakes

[Auto-generated from tests/]
"""

    return template
```

---

## Implementation Plan

### Week 1-2: Structure Creation

**Create directories:**
```bash
mkdir -p sdk-users/docs-it-teams/{getting-started,templates,quick-mode,patterns,dataflow,nexus,marketplace,ai-features,troubleshooting}
mkdir -p sdk-users/docs-developers/{architecture,advanced,frameworks,contributing,performance,reference}
```

**Migrate content:**
- Extract IT team relevant content from existing docs
- Rewrite in outcome-focused format
- Add time estimates and concrete examples

### Week 3-4: Golden Patterns Documentation

**Create 10 pattern docs:**
- Each pattern: 1000-2000 words
- Copy-paste ready code
- Common mistakes sections
- AI instructions embedded

### Week 5: Developer Docs Curation

**Extract from existing:**
- Architecture guides
- Advanced features
- Contribution guide
- API reference (auto-generate)

### Week 6: .claude/skills/ Reorganization

**Create it-team/ directory:**
- 10 skills (one per Golden Pattern)
- Context detection logic
- Update CLAUDE.md with auto-selection

---

## Documentation Metrics

### Success Metrics

**1. Documentation Discoverability**
- Target: 90% of users find answers in <5 minutes
- Measure: "Did you find what you needed?" survey
- Current: Unknown (likely low for IT teams)

**2. Context-Appropriate Content**
- Target: 80% of IT teams use IT team docs (not developer docs)
- Measure: Analytics on doc page views
- Segmented by user type

**3. AI Assistant Effectiveness**
- Target: 90% of Claude Code responses reference correct docs
- Measure: Token consumption, response quality
- With Golden Patterns vs full skills

**4. Time to Answer**
- Target: <2 minutes to find pattern
- Current: 5-30 minutes searching 246 skills
- With 10 patterns: Expected <2 minutes

---

## Key Takeaways

**Documentation reorganization is critical for dual-market strategy:**
- IT teams get focused, outcome-oriented docs
- Developers get comprehensive, technical docs
- AI assistants load appropriate context (90% token savings)

**Success depends on:**
- Clear separation (IT teams vs developers)
- Quality of IT team docs (must be excellent)
- AI context detection (automatic, not manual)
- Maintenance (keep both trees updated)

**Implementation is straightforward:**
- Create new directories
- Rewrite existing content in new formats
- Add context detection
- Update .claude/skills/ auto-selection

**Impact: High value, medium effort (30 hours)**

---

**This completes the modifications section. Next: Integration and migration plans.**
