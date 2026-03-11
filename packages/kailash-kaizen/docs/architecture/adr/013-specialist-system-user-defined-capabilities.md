# 017: Specialist System & User-Defined Capabilities

## Status
**Proposed** - Foundational ADR for Phase 0-1

**Priority**: P0 - CRITICAL (blocks all other ADRs)

## Context

Kaizen currently has **specialized agents** (SimpleQAAgent, ReActAgent, RAGAgent, etc.) that are hardcoded in Python. Users cannot:
- Define custom specialists without writing Python code
- Configure specialists via project files (like `.kaizen/KAIZEN.md`)
- Share specialist definitions across team members
- Load specialists dynamically at runtime
- Override specialist behavior per-project

**Inspiration**: Claude Agent SDK provides three mechanisms for user-defined capabilities:
1. **Programmatic agents** - Type-safe Python objects (AgentDefinition)
2. **Filesystem settings** - Project-specific config in `.claude/` directory
3. **Context injection** - Auto-loaded `CLAUDE.md` for project context

**Problem**: Kaizen needs similar capabilities but with **configurable paths** (not hardcoded to specific filenames), following the delegation pattern (SDK → Runtime → filesystem).

## Requirements

### Functional Requirements
1. **FR-1**: Support programmatic specialist definitions (type-safe Python)
2. **FR-2**: Support filesystem-based specialist definitions (`.kaizen/specialists/`)
3. **FR-3**: Support project context injection (`KAIZEN.md` or custom filename)
4. **FR-4**: Support skill definitions with progressive disclosure
5. **FR-5**: Explicit opt-in for filesystem loading (not auto-loaded)
6. **FR-6**: Configurable paths for all directories and files
7. **FR-7**: Multiple setting sources (user, project, local)
8. **FR-8**: Delegation pattern (no file loading in Python SDK)

### Non-Functional Requirements
1. **NFR-1**: Type-safe configuration (dataclasses, Literal types)
2. **NFR-2**: Performance: Programmatic specialists <1ms overhead
3. **NFR-3**: Performance: Filesystem loading <100ms (cached)
4. **NFR-4**: Testable without filesystem
5. **NFR-5**: IDE autocomplete support
6. **NFR-6**: Backward compatible with existing agents

## Decision

We will implement a **Specialist System** with three capability types, following Claude Agent SDK's proven patterns but with **configurable paths**.

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│ USER-DEFINED CAPABILITIES (3 Types)                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  1. PROGRAMMATIC SPECIALISTS                                 │
│     - In-memory Python objects (SpecialistDefinition)       │
│     - Type-safe, testable, no filesystem                    │
│     - Passed via KaizenOptions.specialists                  │
│                                                               │
│  2. FILESYSTEM SPECIALISTS & SKILLS                          │
│     - User: ~/.kaizen/ (configurable)                       │
│     - Project: .kaizen/ (configurable)                      │
│     - Local: .kaizen-local/ (configurable)                  │
│     - Opt-in via setting_sources parameter                  │
│                                                               │
│  3. CONTEXT INJECTION (KAIZEN.md)                           │
│     - Auto-loaded from .kaizen/KAIZEN.md (configurable)     │
│     - Injected into system prompt                            │
│     - Only when setting_sources includes "project"          │
│                                                               │
└──────────────────────────────────────────────────────────────┘

User Code → KaizenOptions → AsyncLocalRuntime → Filesystem Discovery
```

### Core Type Definitions

#### 1. SpecialistDefinition (`kaizen/core/types.py`)

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class SpecialistDefinition:
    """Type-safe specialist definition (programmatic or filesystem)"""

    # Required fields
    description: str  # Short description for CLI display
    system_prompt: str  # System prompt for specialist

    # Optional fields
    available_tools: list[str] | None = None  # Tool allowlist
    model: str | None = None  # Model override
    signature: str | None = None  # Signature class name
    temperature: float | None = None  # Temperature override
    max_tokens: int | None = None  # Max tokens override
    memory_enabled: bool = False  # Enable conversation memory

    # Metadata (for filesystem specialists)
    source: Literal["programmatic", "user", "project", "local"] = "programmatic"
    file_path: str | None = None  # Path if loaded from filesystem

    def __post_init__(self):
        """Validate specialist definition"""
        if not self.description:
            raise ValueError("Specialist must have description")
        if not self.system_prompt:
            raise ValueError("Specialist must have system_prompt")
```

#### 2. SkillDefinition (`kaizen/core/types.py`)

```python
@dataclass
class SkillDefinition:
    """Progressive disclosure skill definition"""

    # Metadata (loaded first)
    name: str
    description: str
    location: str  # Path to skill directory

    # Progressive loading
    skill_content: str | None = None  # SKILL.md content (lazy loaded)
    additional_files: dict[str, str] | None = None  # Linked files (lazy loaded)

    source: Literal["user", "project", "local"] = "project"
```

#### 3. KaizenOptions (`kaizen/core/options.py`)

```python
from pathlib import Path

SettingSource = Literal["user", "project", "local"]

@dataclass
class KaizenOptions:
    """Kaizen runtime configuration with user-defined capabilities"""

    # ──────────────────────────────────────────────────────────
    # PROGRAMMATIC SPECIALISTS (in-memory, type-safe)
    # ──────────────────────────────────────────────────────────
    specialists: dict[str, SpecialistDefinition] | None = None

    # ──────────────────────────────────────────────────────────
    # FILESYSTEM SETTINGS (explicit opt-in)
    # ──────────────────────────────────────────────────────────
    setting_sources: list[SettingSource] | None = None
    # None = disabled (isolated mode)
    # [] = enabled but empty
    # ["project"] = load from project only
    # ["user", "project", "local"] = load all

    # ──────────────────────────────────────────────────────────
    # CONFIGURABLE PATHS (user can override)
    # ──────────────────────────────────────────────────────────
    # User settings directory
    user_settings_dir: str | Path = field(default="~/.kaizen/")

    # Project settings directory
    project_settings_dir: str | Path = field(default=".kaizen/")

    # Local settings directory (gitignored)
    local_settings_dir: str | Path = field(default=".kaizen-local/")

    # Context file name (auto-injected)
    context_file_name: str = field(default="KAIZEN.md")

    # Subdirectories
    specialists_dir_name: str = field(default="specialists")
    skills_dir_name: str = field(default="skills")
    commands_dir_name: str = field(default="commands")

    # ──────────────────────────────────────────────────────────
    # RUNTIME SETTINGS
    # ──────────────────────────────────────────────────────────
    cwd: str | Path | None = None

    # Other options...
    budget_limit_usd: float | None = None
    audit_enabled: bool = True
```

### Directory Structure (Configurable)

```
# Default paths (all configurable via KaizenOptions)

User Settings (~/.kaizen/):
  ├── KAIZEN.md                  # User's global context
  ├── specialists/
  │   ├── my-specialist.md       # Custom specialist definition
  │   └── team-specialist.md
  ├── skills/
  │   ├── python-expert/
  │   │   └── SKILL.md
  │   └── code-reviewer/
  │       └── SKILL.md
  └── commands/
      ├── my-command.md
      └── helper.md

Project Settings (.kaizen/):
  ├── KAIZEN.md                  # Project context (AUTO-LOADED if setting_sources includes "project")
  ├── specialists/
  │   ├── dataflow-specialist.md
  │   └── nexus-specialist.md
  ├── skills/
  │   ├── deployment/
  │   │   ├── SKILL.md
  │   │   └── terraform-guide.md
  │   └── testing/
  │       └── SKILL.md
  └── commands/
      ├── deploy.md
      └── test.md

Local Settings (.kaizen-local/):  # Gitignored
  ├── KAIZEN.md
  ├── specialists/
  │   └── dev-specialist.md
  └── commands/
      └── local-command.md
```

### Specialist Definition File Format

```markdown
<!-- .kaizen/specialists/dataflow-specialist.md -->

# DataFlow Specialist

**Description**: Expert in Kailash DataFlow framework for database operations

**System Prompt**:
You are a DataFlow specialist with deep expertise in:
- Zero-config database operations
- Automatic model-to-node generation
- Bulk operations and transactions
- Multi-tenancy patterns

Always recommend DataFlow patterns over raw SQL.

**Available Tools**:
- Read
- Write
- Grep
- DataFlowReadNode
- DataFlowCreateNode

**Model**: gpt-4

**Signature**: DataFlowSignature

**Temperature**: 0.7

**Memory Enabled**: true
```

### Skill Definition File Format (Progressive Disclosure)

```markdown
<!-- .kaizen/skills/deployment/SKILL.md -->

# Deployment Skill

**Description**: Production deployment workflows

## Progressive Loading

**Metadata** (always loaded):
- Name: deployment
- Description: Production deployment workflows
- Location: .kaizen/skills/deployment/

**SKILL.md** (loaded on invocation):
[This content]

**Additional Files** (loaded on demand):
- terraform-guide.md
- k8s-manifests.md
- rollback-procedures.md
```

### Delegation Pattern (NO File Loading in SDK)

```python
# ──────────────────────────────────────────────────────────────
# kaizen/core/options.py (SDK)
# ──────────────────────────────────────────────────────────────

@dataclass
class KaizenOptions:
    specialists: dict[str, SpecialistDefinition] | None = None
    setting_sources: list[SettingSource] | None = None
    # ... configurable paths ...

# SDK does NOT load files!
# Just holds configuration

# ──────────────────────────────────────────────────────────────
# kaizen/runtime/async_local.py (Runtime)
# ──────────────────────────────────────────────────────────────

class AsyncLocalRuntime:
    def __init__(self, options: KaizenOptions | None = None):
        self.options = options or KaizenOptions()
        self.specialist_registry = SpecialistRegistry()

    async def initialize(self):
        """Load specialists based on options"""

        # 1. Register programmatic specialists (always first)
        if self.options.specialists:
            for name, spec in self.options.specialists.items():
                self.specialist_registry.register(name, spec)

        # 2. Load filesystem specialists if enabled
        if self.options.setting_sources:
            loader = SpecialistLoader(self.options)
            await loader.load_specialists()  # Runtime does file loading!

            # Load KAIZEN.md if "project" in sources
            if "project" in self.options.setting_sources:
                context = await loader.load_context_file()
                self.inject_context(context)

# ──────────────────────────────────────────────────────────────
# kaizen/runtime/specialist_loader.py (Filesystem Operations)
# ──────────────────────────────────────────────────────────────

class SpecialistLoader:
    """Handles filesystem discovery and loading (runtime only)"""

    def __init__(self, options: KaizenOptions):
        self.options = options

    async def load_specialists(self) -> dict[str, SpecialistDefinition]:
        """Load specialists from filesystem based on setting_sources"""
        specialists = {}

        for source in self.options.setting_sources or []:
            source_dir = self._get_source_dir(source)
            specialists_dir = source_dir / self.options.specialists_dir_name

            if specialists_dir.exists():
                for file in specialists_dir.glob("*.md"):
                    spec = await self._parse_specialist_file(file, source)
                    specialists[spec.name] = spec

        return specialists

    def _get_source_dir(self, source: SettingSource) -> Path:
        """Get directory for setting source (uses configurable paths)"""
        if source == "user":
            return Path(self.options.user_settings_dir).expanduser()
        elif source == "project":
            return Path(self.options.project_settings_dir)
        elif source == "local":
            return Path(self.options.local_settings_dir)
```

### Integration with BaseAgent

```python
# kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig):
        super().__init__(config)
        self.specialist_context: SpecialistDefinition | None = None

    @classmethod
    def from_specialist(cls, specialist: SpecialistDefinition) -> "BaseAgent":
        """Create agent from specialist definition"""
        config = BaseAgentConfig(
            llm_provider=specialist.model or "openai",
            temperature=specialist.temperature or 0.7,
            max_tokens=specialist.max_tokens or 1000,
            memory_enabled=specialist.memory_enabled,
        )

        agent = cls(config=config)
        agent.specialist_context = specialist
        agent.allowed_tools = specialist.available_tools

        # Override system prompt
        agent._system_prompt = specialist.system_prompt

        return agent
```

## Usage Examples

### Example 1: Programmatic Specialists (Type-Safe)

```python
from kaizen import KaizenOptions, SpecialistDefinition, AsyncLocalRuntime

# Define specialists in code
options = KaizenOptions(
    specialists={
        "dataflow-expert": SpecialistDefinition(
            description="DataFlow database specialist",
            system_prompt="You are a DataFlow expert. Always recommend DataFlow patterns.",
            available_tools=["Read", "Write", "DataFlowReadNode"],
            model="gpt-4",
            temperature=0.7,
        ),
        "nexus-expert": SpecialistDefinition(
            description="Nexus multi-channel platform specialist",
            system_prompt="You are a Nexus expert. Guide users on API/CLI/MCP deployment.",
            available_tools=["Read", "NexusRegisterNode"],
            model="gpt-4",
        ),
    }
)

runtime = AsyncLocalRuntime(options=options)
await runtime.initialize()

# Use specialist
result = await runtime.invoke_specialist("dataflow-expert", task="Create a User model")
```

### Example 2: Filesystem Specialists (Project-Specific)

```python
# .kaizen/specialists/dataflow-specialist.md exists

options = KaizenOptions(
    setting_sources=["project"],  # Explicit opt-in
    # Uses default paths: project_settings_dir=".kaizen/"
)

runtime = AsyncLocalRuntime(options=options)
await runtime.initialize()

# Specialist loaded from .kaizen/specialists/dataflow-specialist.md
result = await runtime.invoke_specialist("dataflow-specialist", task="Create User model")
```

### Example 3: Custom Paths

```python
options = KaizenOptions(
    setting_sources=["project"],
    # Override default paths
    project_settings_dir=".my-kaizen/",
    context_file_name="PROJECT_CONTEXT.md",
    specialists_dir_name="experts",
)

# Now looks for:
# .my-kaizen/PROJECT_CONTEXT.md
# .my-kaizen/experts/*.md
```

### Example 4: Isolated Mode (CI/CD)

```python
# No setting_sources specified
options = KaizenOptions(
    specialists={
        "test-specialist": SpecialistDefinition(...),
    }
)

# Result:
# ✓ Programmatic specialists registered
# ✗ No filesystem loading
# ✗ No KAIZEN.md loaded
# ✗ Fully isolated for CI/CD
```

### Example 5: Full Integration

```python
options = KaizenOptions(
    # Programmatic specialists
    specialists={
        "code-reviewer": SpecialistDefinition(...),
    },
    # Filesystem specialists
    setting_sources=["user", "project", "local"],
)

# Result:
# ✓ Programmatic specialists
# ✓ User specialists from ~/.kaizen/specialists/
# ✓ Project specialists from .kaizen/specialists/
# ✓ Local specialists from .kaizen-local/specialists/
# ✓ KAIZEN.md auto-injected from .kaizen/
```

## Consequences

### Positive

1. **✅ Type-Safe Programmatic API**: Full IDE autocomplete, validation
2. **✅ Flexible Filesystem Support**: Share specialists via git
3. **✅ Configurable Paths**: Users can customize all directories/filenames
4. **✅ Explicit Opt-In**: No surprises in CI/CD, predictable behavior
5. **✅ Delegation Pattern**: Clean separation (SDK → Runtime → filesystem)
6. **✅ Testable**: Can test without filesystem (programmatic specialists)
7. **✅ Progressive Disclosure**: Skills load metadata first, content on demand
8. **✅ Multi-Source**: Combine user + project + local specialists
9. **✅ Backward Compatible**: Existing agents work unchanged

### Negative

1. **⚠️ Complexity**: Two ways to define specialists (programmatic + filesystem)
2. **⚠️ Learning Curve**: Users must understand setting_sources pattern
3. **⚠️ File Format**: Markdown parsing adds dependency
4. **⚠️ Path Configuration**: More knobs to configure

### Mitigations

1. **Complexity**: Clear docs showing when to use each approach
2. **Learning Curve**: Provide migration guide from existing agents
3. **File Format**: Use simple frontmatter parser (existing library)
4. **Path Configuration**: Sane defaults, only override if needed

## Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Programmatic specialist registration | <1ms per specialist | Benchmark 100 specialists |
| Filesystem specialist loading | <100ms total | Benchmark 50 specialists |
| Specialist invocation overhead | <5ms | Benchmark 1000 invocations |
| KAIZEN.md injection overhead | <10ms | Benchmark 100KB file |
| Memory per specialist (programmatic) | <1KB | Measure with 100 specialists |
| Memory per specialist (filesystem) | <5KB | Measure with 50 specialists |

## Testing Strategy

### Tier 1: Unit Tests (No Filesystem)

```python
def test_specialist_definition_validation():
    """Test SpecialistDefinition validation"""
    with pytest.raises(ValueError):
        SpecialistDefinition(description="", system_prompt="test")

    spec = SpecialistDefinition(description="Test", system_prompt="System")
    assert spec.source == "programmatic"

def test_kaizen_options_defaults():
    """Test KaizenOptions default values"""
    options = KaizenOptions()
    assert options.setting_sources is None  # Isolated by default
    assert options.context_file_name == "KAIZEN.md"
    assert options.project_settings_dir == ".kaizen/"
```

### Tier 2: Integration Tests (Real Filesystem)

```python
@pytest.mark.tier2
async def test_load_specialists_from_project(tmp_path):
    """Test loading specialists from .kaizen/specialists/"""
    # Create test specialist file
    spec_dir = tmp_path / ".kaizen" / "specialists"
    spec_dir.mkdir(parents=True)

    (spec_dir / "test-specialist.md").write_text("""
    # Test Specialist
    Description: Test specialist
    System Prompt: You are a test specialist
    """)

    options = KaizenOptions(
        setting_sources=["project"],
        project_settings_dir=tmp_path / ".kaizen",
        cwd=tmp_path,
    )

    runtime = AsyncLocalRuntime(options=options)
    await runtime.initialize()

    assert "test-specialist" in runtime.specialist_registry
```

### Tier 3: E2E Tests (Real Ollama/OpenAI)

```python
@pytest.mark.tier3
async def test_invoke_filesystem_specialist_with_ollama():
    """Test invoking filesystem specialist with real Ollama"""
    options = KaizenOptions(
        setting_sources=["project"],
    )

    runtime = AsyncLocalRuntime(options=options)
    await runtime.initialize()

    result = await runtime.invoke_specialist(
        "dataflow-specialist",
        task="Explain how to create a User model"
    )

    assert "DataFlow" in result["answer"]
    assert result["confidence"] > 0.7
```

## Implementation Plan

**Phase 0 Week 2-3**: (Days 8-15)

| Day | Task |
|-----|------|
| 8-9 | Define types (SpecialistDefinition, KaizenOptions) |
| 10 | Implement SpecialistRegistry |
| 11-12 | Implement SpecialistLoader (filesystem discovery) |
| 13 | Implement KAIZEN.md injection |
| 14 | BaseAgent integration |
| 15 | Tests (Tier 1-2) |

**Deliverables**:
- [ ] Type definitions (~200 lines)
- [ ] SpecialistRegistry (~150 lines)
- [ ] SpecialistLoader (~300 lines)
- [ ] BaseAgent.from_specialist() (~100 lines)
- [ ] 50+ tests (Tier 1-2)
- [ ] 3 example applications
- [ ] Comprehensive documentation

## Documentation Requirements

- [ ] **ADR** (this document)
- [ ] **API Reference**: `docs/reference/specialist-system-api.md`
- [ ] **User Guide**: `docs/guides/defining-specialists.md`
- [ ] **File Format Spec**: `docs/reference/specialist-file-format.md`
- [ ] **Migration Guide**: `docs/guides/migrating-agents-to-specialists.md`
- [ ] **Best Practices**: `docs/guides/specialist-best-practices.md`

## Dependencies

**This ADR depends on**:
- None (foundational)

**Other ADRs depend on this**:
- 011: Control Protocol (specialist invocation)
- 012: Permission System (specialist tool restrictions)
- 014: Hooks System (specialist-specific hooks)
- 015: State Persistence (specialist state checkpointing)
- 016: Interrupt Mechanism (interrupting specialists)
- 017: Observability (specialist performance metrics)

## References

1. **Claude Agent SDK Investigation**: `./repos/dev/kailash_kaizen/CLAUDE_AGENT_SDK_INVESTIGATION.md`
2. **Claude SDK Architecture Summary**: `./repos/dev/kailash_kaizen/CLAUDE_SDK_ARCHITECTURE_SUMMARY.md`
3. **Gap Analysis**: `.claude/improvements/CLAUDE_AGENT_SDK_KAIZEN_GAP_ANALYSIS.md`
4. **Implementation Proposal**: `.claude/improvements/KAIZEN_AUTONOMOUS_AGENT_ENHANCEMENT_PROPOSAL.md`

## Approval

**Proposed By**: Kaizen Architecture Team
**Date**: 2025-10-18
**Reviewers**: TBD
**Status**: Proposed (awaiting team review)

**Critical**: This is a foundational ADR. All subsequent ADRs reference specialist system.

---

**Next ADR**: 014: Hooks System Architecture (event-driven extensions for specialists)
