# Specialist System Guide (ADR-013)

This guide covers the Specialist System, which enables user-defined specialists, skills, and project context files following Claude Code's agent/skill discovery patterns.

## Overview

The Specialist System provides three core capabilities:

1. **Specialists**: Predefined agent personas with specific system prompts, tools, and configurations
2. **Skills**: Knowledge packages that can be dynamically loaded to augment agent capabilities
3. **Context Files**: Project-specific context injected into all agent interactions (e.g., `KAIZEN.md`)

## Quick Start

### Programmatic Specialists

Define specialists in code without filesystem access:

```python
from kaizen.core import KaizenOptions, SpecialistDefinition
from kaizen.runtime.adapters import LocalKaizenAdapter

# Define specialists programmatically
specialists = {
    "code-reviewer": SpecialistDefinition(
        description="Expert code reviewer for Python projects",
        system_prompt="You are a senior code reviewer. Focus on code quality, security, and best practices.",
        available_tools=["Read", "Glob", "Grep"],
        model="gpt-4o",
        temperature=0.2,
    ),
    "data-analyst": SpecialistDefinition(
        description="Data analysis and visualization specialist",
        system_prompt="You analyze data and create actionable insights.",
        temperature=0.5,
    ),
}

# Create options with specialists
options = KaizenOptions(specialists=specialists)

# Create adapter with specialist support
adapter = LocalKaizenAdapter(kaizen_options=options)

# List available specialists
print(adapter.list_specialists())  # ['code-reviewer', 'data-analyst']

# Get specialist-configured adapter
reviewer = adapter.for_specialist("code-reviewer")
```

### Filesystem-Based Specialists

Load specialists from `.kaizen/`, `~/.kaizen/`, and `.kaizen-local/` directories:

```python
from kaizen.core import KaizenOptions
from kaizen.runtime.adapters import LocalKaizenAdapter

# Enable filesystem loading
options = KaizenOptions(
    setting_sources=["user", "project", "local"],  # Load from all sources
    cwd="/path/to/project",  # Project root
)

adapter = LocalKaizenAdapter(kaizen_options=options)

# Specialists are automatically loaded from:
# - ~/.kaizen/specialists/*.md (user)
# - /path/to/project/.kaizen/specialists/*.md (project)
# - /path/to/project/.kaizen-local/specialists/*.md (local)
```

## Specialist Definition

### Markdown Format

Create specialists as markdown files in the `specialists/` directory:

```markdown
# Code Reviewer

**Description**: Expert code reviewer for Python projects
**System Prompt**: You are a senior code reviewer. Focus on:
- Code quality and readability
- Security vulnerabilities
- Performance issues
- Best practices

When reviewing code, always explain your reasoning.
**Available Tools**: Read, Glob, Grep, Edit
**Model**: gpt-4o
**Temperature**: 0.2
**Max Tokens**: 8192
**Memory Enabled**: true
```

### Python Dataclass

```python
from kaizen.core import SpecialistDefinition

specialist = SpecialistDefinition(
    description="Short description for CLI/UI display",
    system_prompt="Full system prompt text...",
    available_tools=["Read", "Glob", "Grep"],  # Optional: limit tools
    model="gpt-4o",  # Optional: override model
    signature="ReviewSignature",  # Optional: DSPy signature
    temperature=0.3,  # Optional: 0.0-2.0
    max_tokens=8192,  # Optional: output limit
    memory_enabled=True,  # Optional: enable memory
    source="programmatic",  # Auto-set based on origin
    file_path=None,  # Auto-set for filesystem specialists
)
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | str | Yes | Short description for display |
| `system_prompt` | str | Yes | Full system prompt text |
| `available_tools` | list[str] | No | Limit available tools |
| `model` | str | No | Override default model |
| `signature` | str | No | DSPy signature class name |
| `temperature` | float | No | LLM temperature (0.0-2.0) |
| `max_tokens` | int | No | Max output tokens |
| `memory_enabled` | bool | No | Enable memory for specialist |
| `source` | str | Auto | Origin: programmatic/user/project/local |
| `file_path` | str | Auto | Path for filesystem specialists |

## Skill Definition

### Directory Structure

Skills are directories containing a `SKILL.md` entry point and optional additional files:

```
.kaizen/skills/python-patterns/
├── SKILL.md           # Required: entry point with metadata
├── patterns.md        # Optional: additional content
├── examples.md        # Optional: more content
└── best-practices.md  # Optional: even more content
```

### SKILL.md Format

```markdown
---
name: python-patterns
description: Common Python design patterns with best practices
---
# Python Patterns Skill

This skill provides guidance on Python design patterns.

## Singleton Pattern
[Content...]

## Factory Pattern
[Content...]
```

### Python Dataclass

```python
from kaizen.core import SkillDefinition

skill = SkillDefinition(
    name="python-patterns",
    description="Python design patterns with best practices",
    location="/path/to/skill/directory",
    skill_content=None,  # Loaded on demand
    additional_files=None,  # Loaded on demand
    source="project",  # Origin
)

# Check if content is loaded
if not skill.is_loaded:
    skill = adapter.load_skill_content(skill)

# Access additional files
examples = skill.get_file("examples.md")
```

### Progressive Disclosure

Skills use progressive disclosure - only metadata is loaded initially:

```python
# Fast: loads only name, description, location
skills = adapter.list_skills()

# Load full content on demand
skill = adapter.get_skill("python-patterns")
skill = adapter.load_skill_content(skill)

print(skill.skill_content)  # Full SKILL.md content
print(skill.additional_files)  # {"patterns.md": "...", "examples.md": "..."}
```

## Context Files

### KAIZEN.md

Project context is loaded from `KAIZEN.md` (configurable):

```
.kaizen/KAIZEN.md
```

Example content:

```markdown
# Project Context

This is a Python SDK for workflow automation.

## Architecture
- Core workflow engine in `src/workflow/`
- Plugin system in `src/plugins/`
- CLI interface in `src/cli/`

## Coding Standards
- Use type hints for all public APIs
- Follow PEP 8 style guide
- Write tests before implementation
```

### Context Injection

Context is automatically injected into system prompts:

```python
# Adapter loads context file automatically
adapter = LocalKaizenAdapter(kaizen_options=options)

# Context is available
if adapter.context_file:
    print(adapter.context_file.content)

# Get formatted context for system prompt
context_section = adapter.get_context_prompt_section()
# Returns: "## Project Context\n[content]"
```

## Configuration Options

### KaizenOptions

```python
from kaizen.core import KaizenOptions

options = KaizenOptions(
    # Specialist definitions (programmatic)
    specialists={"name": SpecialistDefinition(...)},

    # Filesystem sources to load from
    setting_sources=["user", "project", "local"],  # None = isolated mode

    # Custom directory paths
    user_settings_dir="~/.kaizen/",  # Default
    project_settings_dir=".kaizen/",  # Default
    local_settings_dir=".kaizen-local/",  # Default

    # Custom names
    context_file_name="KAIZEN.md",  # Default
    specialists_dir_name="specialists",  # Default
    skills_dir_name="skills",  # Default
    commands_dir_name="commands",  # Default

    # Runtime settings
    cwd="/path/to/project",  # Working directory
    budget_limit_usd=10.0,  # Budget limit
    audit_enabled=True,  # Enable audit logging
)
```

### Setting Sources

| Source | Directory | Priority |
|--------|-----------|----------|
| `user` | `~/.kaizen/` | Low |
| `project` | `.kaizen/` | Medium |
| `local` | `.kaizen-local/` | High |

Later sources override earlier ones.

### Isolated Mode

When `setting_sources` is `None`, the adapter runs in isolated mode:

- No filesystem access
- Only programmatic specialists available
- No context file loading
- Useful for testing or embedded deployments

```python
# Isolated mode (default)
options = KaizenOptions()  # setting_sources=None
assert options.is_isolated == True

# Non-isolated mode
options = KaizenOptions(setting_sources=["project"])
assert options.is_isolated == False
```

## Using Specialists

### for_specialist() Method

Create a pre-configured adapter for a specific specialist:

```python
# Get adapter configured for specialist
reviewer = adapter.for_specialist("code-reviewer")

# Specialist settings are applied:
# - Model and temperature from specialist definition
# - Tool restrictions from available_tools
# - System prompt includes specialist prompt

# Execute as that specialist
context = ExecutionContext(task="Review the auth module")
result = await reviewer.execute(context)
```

### Shared Resources

Specialist-specific adapters share registries with the parent:

```python
# Parent adapter
adapter = LocalKaizenAdapter(kaizen_options=options)

# Create specialist adapter
reviewer = adapter.for_specialist("code-reviewer")

# Both have access to all specialists
assert len(reviewer.specialist_registry) == len(adapter.specialist_registry)

# Both have same context file
assert reviewer.context_file == adapter.context_file
```

## API Reference

### LocalKaizenAdapter Properties

```python
adapter.kaizen_options         # KaizenOptions or None
adapter.specialist_registry    # SpecialistRegistry or None
adapter.skill_registry         # SkillRegistry or None
adapter.context_file           # ContextFile or None
adapter.available_tools        # List[str] or None (if limited by specialist)
adapter.effective_budget_limit # float or None
adapter.working_directory      # Path
```

### LocalKaizenAdapter Methods

```python
# Specialists
adapter.get_specialist(name) -> SpecialistDefinition | None
adapter.list_specialists() -> list[str]
adapter.for_specialist(name) -> LocalKaizenAdapter | None

# Skills
adapter.get_skill(name) -> SkillDefinition | None
adapter.list_skills() -> list[str]
adapter.load_skill_content(skill) -> SkillDefinition

# Context
adapter.get_context_prompt_section() -> str | None
```

### SpecialistRegistry

```python
from kaizen.runtime import SpecialistRegistry

registry = SpecialistRegistry()
registry.register("name", specialist, overwrite=True) -> bool
registry.get("name") -> SpecialistDefinition | None
registry.remove("name") -> bool
registry.list() -> list[str]
registry.clear() -> int  # Returns count cleared
registry.merge(other_registry, overwrite=True) -> int  # Returns count merged
len(registry)  # Number of specialists
```

### SkillRegistry

```python
from kaizen.runtime import SkillRegistry

registry = SkillRegistry()
registry.register(skill) -> bool
registry.get("name") -> SkillDefinition | None
registry.remove("name") -> bool
registry.list() -> list[str]
registry.clear() -> int
registry.merge(other_registry, overwrite=True) -> int
len(registry)
```

### SpecialistLoader

```python
from kaizen.runtime import SpecialistLoader

loader = SpecialistLoader(options)
specialists = loader.load_specialists() -> SpecialistRegistry
skills = loader.load_skills() -> SkillRegistry
context = loader.load_context_file() -> ContextFile | None
specialists, skills, context = loader.load_all()
skill = loader.load_skill_content(skill) -> SkillDefinition
```

## Directory Structure

Recommended project layout:

```
project/
├── .kaizen/                    # Project settings (committed)
│   ├── KAIZEN.md               # Project context
│   ├── specialists/            # Specialist definitions
│   │   ├── code-reviewer.md
│   │   └── data-analyst.md
│   ├── skills/                 # Knowledge packages
│   │   ├── python-patterns/
│   │   │   ├── SKILL.md
│   │   │   └── examples.md
│   │   └── testing/
│   │       ├── SKILL.md
│   │       └── pytest-tips.md
│   └── commands/               # Custom commands (future)
│
├── .kaizen-local/              # Local overrides (not committed)
│   ├── specialists/
│   │   └── custom-helper.md
│   └── KAIZEN.md              # Local context overrides
│
├── ~/.kaizen/                  # User-level settings
│   ├── specialists/
│   │   └── global-helper.md
│   └── KAIZEN.md              # User-level context
```

## Best Practices

### Specialist Design

1. **Clear Descriptions**: Write concise descriptions for CLI display
2. **Focused Prompts**: Create specific, task-oriented system prompts
3. **Tool Restrictions**: Limit tools to those actually needed
4. **Temperature Tuning**: Lower for deterministic tasks, higher for creative

### Skill Organization

1. **Single Responsibility**: One skill per knowledge domain
2. **Progressive Content**: Put summary in SKILL.md, details in additional files
3. **Clear Frontmatter**: Include name and description in YAML

### Context Files

1. **Project Overview**: Start with high-level architecture
2. **Coding Standards**: Include team conventions
3. **Key Patterns**: Document important patterns
4. **Keep Updated**: Maintain as project evolves

## Troubleshooting

### Specialist Not Loading

```python
# Check if source is enabled
assert "project" in options.setting_sources

# Verify path resolution
print(options.get_specialists_dir("project"))

# Check file exists and has required fields
# Required: **Description** and **System Prompt**
```

### Skill Not Loading

```python
# Skills require SKILL.md file
skill_dir / "SKILL.md"

# Check for description (either in frontmatter or first paragraph)
```

### Context Not Injected

```python
# Verify context file exists
context_path = options.get_context_file("project")
print(context_path, context_path.exists())

# Check isolated mode
assert not options.is_isolated
```

## Migration from Claude Code

The Specialist System uses similar patterns to Claude Code's agent/skill discovery:

| Claude Code | Kaizen |
|-------------|--------|
| `.claude/agents/` | `.kaizen/specialists/` |
| `.claude/skills/` | `.kaizen/skills/` |
| `CLAUDE.md` | `KAIZEN.md` |
| `~/.claude/` | `~/.kaizen/` |
| `.claude-local/` | `.kaizen-local/` |

The markdown format and directory structure are designed to be familiar while supporting Kaizen-specific features like DSPy signatures and memory integration.
