# Kaizen Module Structure

## Overview

This document explains the module organization in the Kailash Kaizen framework, particularly the relationship between `kaizen.coordination` and `kaizen.orchestration`.

## Module Hierarchy

### Orchestration (Primary Implementation)

The primary implementation of coordination patterns and teams resides in the orchestration module:

```
kaizen/orchestration/
├── core/
│   ├── patterns.py      # Actual implementation of coordination patterns
│   └── teams.py         # Actual implementation of agent teams
└── patterns/            # Multi-agent orchestration patterns
    ├── __init__.py
    ├── base_pattern.py
    ├── supervisor_worker.py
    ├── consensus.py
    ├── debate.py
    ├── handoff.py
    ├── sequential.py
    ├── ensemble.py
    ├── blackboard.py
    ├── meta_controller.py
    └── parallel.py
```

**Key Classes in `orchestration/core/patterns.py`:**
- `CoordinationPattern` - Base class for coordination patterns
- `DebateCoordinationPattern` - Debate coordination with enterprise features
- `ConsensusCoordinationPattern` - Consensus building with iterative refinement
- `HierarchicalCoordinationPattern` - Supervisor-worker hierarchical coordination
- `TeamCoordinationPattern` - Enhanced team coordination with role-based collaboration
- `CoordinationPatternRegistry` - Registry for managing coordination patterns
- `get_global_pattern_registry()` - Global registry accessor

**Key Classes in `orchestration/core/teams.py`:**
- `AgentTeam` - Multi-agent team with coordination capabilities
- `TeamCoordinator` - Coordinator for agent teams

### Coordination (Compatibility Layer)

The coordination module provides backward compatibility by re-exporting from orchestration:

```
kaizen/coordination/
├── __init__.py          # Main coordination module exports
├── patterns.py          # Re-exports from orchestration.core.patterns
└── teams.py             # Re-exports from orchestration.core.teams
```

## Import Paths

### Recommended (Direct)

Import directly from the orchestration module for new code:

```python
from kaizen.orchestration.core.patterns import (
    CoordinationPattern,
    DebateCoordinationPattern,
    ConsensusCoordinationPattern,
    HierarchicalCoordinationPattern,
    TeamCoordinationPattern,
    CoordinationPatternRegistry,
    get_global_pattern_registry,
)

from kaizen.orchestration.core.teams import (
    AgentTeam,
    TeamCoordinator,
)
```

### Backward Compatible (Via Coordination)

For backward compatibility, you can also import via the coordination module:

```python
from kaizen.coordination.patterns import (
    CoordinationPattern,
    DebateCoordinationPattern,
    ConsensusCoordinationPattern,
    HierarchicalCoordinationPattern,
    TeamCoordinationPattern,
    CoordinationPatternRegistry,
    get_global_pattern_registry,
)

from kaizen.coordination.teams import (
    AgentTeam,
    TeamCoordinator,
)
```

### Via Top-Level Coordination Module

The top-level coordination module also exports all classes:

```python
from kaizen.coordination import (
    AgentTeam,
    TeamCoordinator,
    CoordinationPattern,
    DebateCoordinationPattern,
    ConsensusCoordinationPattern,
    HierarchicalCoordinationPattern,
    TeamCoordinationPattern,
    CoordinationPatternRegistry,
    get_global_pattern_registry,
)
```

## Architecture Rationale

### Why Two Module Paths?

1. **Separation of Concerns**: The orchestration module contains the actual implementation and handles multi-agent workflows, patterns, and execution.

2. **Backward Compatibility**: The coordination module existed as a public API before the implementation was moved to orchestration. The compatibility layer ensures existing code continues to work.

3. **Clear Intent**: Having both paths allows:
   - **orchestration.core** - For developers working on the framework internals
   - **coordination** - For users consuming the framework API

### Implementation Details

The compatibility layer is implemented using simple re-exports:

**`kaizen/coordination/patterns.py`:**
```python
from kaizen.orchestration.core.patterns import (
    ConsensusCoordinationPattern,
    CoordinationPattern,
    CoordinationPatternRegistry,
    # ... other classes
)
```

**`kaizen/coordination/teams.py`:**
```python
from kaizen.orchestration.core.teams import (
    AgentTeam,
    TeamCoordinator,
)
```

This ensures:
- No code duplication
- Single source of truth
- Automatic synchronization of changes
- Minimal maintenance overhead

## Migration Guide

If you're maintaining code that uses the old import paths:

### No Action Required

Existing code will continue to work thanks to the compatibility layer:

```python
# This continues to work
from kaizen.coordination.patterns import DebateCoordinationPattern
```

### Optional: Modernize Imports

For new code or when refactoring, consider using direct imports:

```python
# Modern, direct import
from kaizen.orchestration.core.patterns import DebateCoordinationPattern
```

## Troubleshooting

### ModuleNotFoundError: No module named 'kaizen.coordination.patterns'

This error indicates that the compatibility layer files are missing. Ensure both files exist:

1. `/path/to/kaizen/coordination/patterns.py`
2. `/path/to/kaizen/coordination/teams.py`

If you've installed the package, you may need to reinstall it:

```bash
cd /path/to/kailash-kaizen
pip install -e .
```

Or for production:

```bash
pip install --upgrade kailash-kaizen
```

### Import Performance

The re-export mechanism has negligible performance impact (< 1ms) as it's a simple import statement that gets cached by Python's import system.

## Related Documentation

- [Orchestration Patterns](../patterns/README.md)
- [Multi-Agent Coordination](../guides/multi-agent-coordination.md)
- [Agent Teams](../guides/agent-teams.md)

## Changelog

### 2024-12-17: Module Structure Clarification

- Added compatibility layer in `kaizen/coordination/patterns.py`
- Added compatibility layer in `kaizen/coordination/teams.py`
- Documented module hierarchy and import paths
- Fixed 4 failing tests in `test_kaizen_multi_agent_coordination.py`
