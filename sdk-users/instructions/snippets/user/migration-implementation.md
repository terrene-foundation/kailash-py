# Migration Implementation Instructions

*After completing repository analysis with trace.md, use this guide for actual migration implementation*

---

You are implementing a repository migration to the Kailash SDK template structure. Follow these steps exactly and show complete outputs at each step. Do not summarize or skip any validation steps.

## 1. CONTEXT LOADING AND ULTRATHINK ACTIVATION

### Essential Context Loading
Load these files before starting (DO NOT proceed until loaded):
- Root `CLAUDE.md` - Core validation rules and critical patterns
- `sdk-users/CLAUDE.md` - Implementation patterns and architectural guidance
- `todos/000-master.md` - Current project state and priorities

**For implementation guidance during development, remember these key resource locations** (use MCP tools to search when needed):
- `sdk-users/developer/` - Core implementation guides and patterns
- `sdk-users/nodes/` - Node selection and usage patterns
- `sdk-users/cheatsheet/` - Copy-paste implementation patterns
- `sdk-users/validation/common-mistakes.md` - Error database with solutions

### Framework Solutions Check (CRITICAL)
Before migrating any component, check for existing framework solutions:
- `sdk-users/apps/dataflow/` - Workflow-native database framework
- `sdk-users/apps/nexus/` - Multi-channel unified platform
- Other frameworks in `sdk-users/apps/` that may provide relevant components

### Critical Understanding Confirmation
After loading the essential files, you MUST confirm you understand:
- **3-tier testing strategy** (`sdk-users/testing/regression-testing-strategy.md` and `sdk-users/testing/test-organization-policy.md`)
  - **Tier 1 requirements**: Fast (<1s), isolated, can use mocks, no external dependencies, no sleep
  - **NO MOCKING policy** for Tier 2/3 tests - this is absolutely critical
  - Real Docker infrastructure requirement - never skip this for integration/E2E tests
- **Todo management system** The todo management system is two-tiered: Repo level todos are in `todos/` and module level todos are in their respective `src/` sub-directories.
- **Available frameworks** in `sdk-users/apps/` that can provide ready-made solutions
- **How to use MCP tools** to search relevant documentation when needed

**Search relevant documentation as needed during implementation using MCP tools instead of loading everything upfront.**

### ULTRATHINK CAP ACTIVATION
Before beginning migration, analyze deeply:

1. **What are the most critical components to migrate first?**
   - Core business logic that everything depends on
   - Components with most external dependencies
   - Areas with highest test coverage (easier validation)

2. **What existing template patterns can accelerate migration?**
   - Which apps from new_project_template are similar?
   - What manifest.yaml patterns apply?
   - Which deployment configs can be reused?

3. **What migration risks must be mitigated?**
   - Data loss or corruption risks
   - Service interruption risks
   - Integration breaking changes
   - Performance degradation risks

4. **How will we validate each migration step?**
   - Existing tests that must continue passing
   - New tests needed for SDK patterns
   - Performance benchmarks to maintain
   - User acceptance criteria

**Document your detailed analysis before proceeding.**

## 2. MIGRATION PLANNING AND ADR

### Create Migration ADR
Create an Architecture Decision Record for the migration in the repository:

**File**: `adr/XXX-kailash-sdk-migration.md`

```markdown
# Migration to Kailash SDK Template Structure

## Status
Proposed

## Context
[Why migration is needed, current limitations, business drivers]

## Decision
### Migration Approach
- Phased migration maintaining service availability
- Component priority order: [list]
- Template patterns to adopt: [list]
- SDK components to integrate: [list]

### Technical Details
- Apps structure: [how to organize]
- Solutions layer: [cross-app orchestration]
- Deployment modernization: [gateway, service discovery]

## Consequences
### Positive
- Multi-app scalability
- Enterprise deployment patterns
- SDK ecosystem benefits

### Negative
- Migration effort required
- Temporary dual maintenance
- Learning curve for team

### Risks
- [Risk 1]: Mitigation strategy
- [Risk 2]: Mitigation strategy

## Migration Phases
1. Structure Alignment
2. Component Migration
3. SDK Integration
4. Deployment Modernization
5. Validation & Cutover
```

**Show me the complete ADR before proceeding.**

### Component Priority Matrix
Based on trace.md analysis, create priority matrix:

| Component | Business Critical | Dependencies | Complexity | Migration Order |
|-----------|------------------|--------------|------------|-----------------|
| [name]    | High/Med/Low     | [list]       | High/Med/Low | 1,2,3...      |

**Show me the complete priority matrix.**

## 3. MIGRATION TODO SYSTEM

Create migration-specific todos:

### Master Migration List
Create/Update in repository:
```
todos/migration/000-migration-master.md
├── Phase 1: Structure Alignment
├── Phase 2: Component Migration
├── Phase 3: SDK Integration
├── Phase 4: Deployment
└── Phase 5: Validation
```

### Detailed Migration Tasks
For each component to migrate:
```
todos/migration/active/001-migrate-[component].md
- Current location: [path]
- Target location: apps/[app_name]/
- Dependencies: [list]
- SDK nodes to use: [list]
- Tests to maintain: [list]
- Acceptance criteria: [list]
```

**Show me the todo entries created.**

## 4. STRUCTURE ALIGNMENT IMPLEMENTATION

### Create Template Structure
Execute these commands and show output:

```bash
# Create apps directory structure
mkdir -p apps/{app1,app2,_template}/{src,tests,adr,todos,mistakes}

# Create solutions directory
mkdir -p solutions/{orchestration,shared_services}

# Create deployment structure
mkdir -p deployment/{docker,kubernetes,helm}

# Copy template files
cp new_project_template/apps/_template/* apps/_template/
```

### Create Initial Manifests
For each app, create `manifest.yaml`:

```yaml
name: [app-name]
version: 0.1.0
type: hybrid
description: "[Purpose of this app]"
capabilities:
  api:
    enabled: true
    endpoints:
      - path: /api/v1/[resource]
        method: [GET|POST|PUT|DELETE]
        description: "[What it does]"
  mcp:
    enabled: false
    tools: []
dependencies:
  - kailash>=1.0.0
environment:
  required:
    - DATABASE_URL
  optional:
    - LOG_LEVEL: "INFO"
```

**Show me each manifest created.**

## 5. COMPONENT MIGRATION WITH VALIDATION

For each component (in priority order):

### Pre-Migration Snapshot
```bash
# Document current state
echo "=== Pre-Migration: [component] ==="
# Run existing tests
pytest [current_test_path] -v
# Check current functionality
[specific validation commands]
```

### Migration Steps

#### Step 1: Create App Structure
```bash
# Create component app
mkdir -p apps/[component]/{src/nodes,tests/unit,tests/integration}
touch apps/[component]/__init__.py
```

#### Step 2: Convert to SDK Patterns
Show the conversion for each file:

**Original Code** ([original_path]):
```python
[show current implementation]
```

**SDK Pattern** (apps/[component]/src/nodes/[name]_node.py):
```python
from kailash import Node, NodeParameter
from typing import Dict, Any

class [Name]Node(Node):
    """[Component description]"""

    def __init__(self, name: str):
        # Set parameters before super().__init__
        self.param1 = None
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "param1": NodeParameter(
                type_hint=str,
                required=True,
                description="[What this parameter does]"
            )
        }

    def execute(self, context) -> Dict[str, Any]:
        # Migrate logic here
        param1 = self.param1

        # [Original logic adapted to node pattern]

        return {"result": processed_data}
```

#### Step 3: Create/Migrate Tests

**Unit Test** (apps/[component]/tests/unit/test_[name]_node.py):
```python
import pytest
from apps.[component].src.nodes.[name]_node import [Name]Node

def test_[name]_node_basic():
    """Test basic functionality"""
    node = [Name]Node("test")
    node.param1 = "test_value"

    result = node.execute({})
    assert result["result"] == expected_value
```

**Integration Test** (apps/[component]/tests/integration/test_[name]_integration.py):
```python
# NO MOCKING - use real services
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def test_[name]_workflow_integration():
    """Test with real infrastructure"""
    workflow = WorkflowBuilder("test_workflow")
    workflow.add_node("[Name]Node", "processor", {
        "param1": "real_value"
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["processor"]["result"] == expected_value
```

#### Step 4: Validation Checkpoint
**Run these commands and show COMPLETE output:**

```bash
# 1. Run migrated unit tests
pytest apps/[component]/tests/unit/ -v

# 2. Run migrated integration tests
pytest apps/[component]/tests/integration/ -v

# 3. Run original tests against migrated code
# Update imports to point to new location
pytest [original_tests_updated] -v

# 4. Performance comparison
python scripts/benchmark_migration.py --component [name]
```

**DO NOT proceed to next component if any tests fail.**

### Post-Migration Verification
- [ ] All original tests still pass
- [ ] New SDK tests pass
- [ ] No functionality lost
- [ ] Performance maintained
- [ ] Manifest.yaml validated

## 6. CROSS-APP INTEGRATION

### Solutions Layer Implementation
After migrating core components, implement orchestration:

```python
# solutions/orchestration/main_workflow.py
from kailash.workflow.builder import WorkflowBuilder

def create_main_workflow():
    """Orchestrate multiple app components"""
    workflow = WorkflowBuilder("main_orchestration")

    # Add nodes from different apps
    workflow.add_node("apps.app1.nodes.Component1Node", "comp1", {})
    workflow.add_node("apps.app2.nodes.Component2Node", "comp2", {})

    # Connect them
    workflow.add_connection("comp1", "result", "comp2", "input")

    return workflow
```

### Gateway Integration
Update deployment configuration:

```yaml
# deployment/docker/docker-compose.yml
services:
  gateway:
    build: ./gateway
    environment:
      - AUTO_DISCOVER=true
      - APPS_PATH=/apps
    volumes:
      - ../../apps:/apps:ro
    ports:
      - "8000:8000"
```

## 7. DEPLOYMENT MIGRATION

### Docker Migration
Create Dockerfiles for each app:

```dockerfile
# apps/[app]/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy only this app
COPY ./src /app/src
COPY ./manifest.yaml /app/

# Install dependencies
RUN pip install kailash>=1.0.0

# Run with Nexus if API/MCP enabled
CMD ["python", "-m", "nexus", "start", "--manifest", "manifest.yaml"]
```

### Service Discovery Setup
Ensure each app's manifest enables discovery:
- Declare all endpoints
- Set proper capability flags
- Include health check endpoints

## 8. VALIDATION AND CUTOVER

### Comprehensive Test Suite
Run complete validation in order:

```bash
# 1. All unit tests (Tier 1)
pytest apps/*/tests/unit/ -v

# 2. All integration tests (Tier 2)
./tests/utils/test-env up && ./tests/utils/test-env status
pytest apps/*/tests/integration/ -v

# 3. End-to-end tests (Tier 3)
pytest tests/e2e/ -v

# 4. Performance benchmarks
python scripts/benchmark_all.py --compare-before-after

# 5. Documentation validation
python scripts/validate_docs.py --check-examples
```

**Show COMPLETE output for each tier.**

### Migration Validation Checklist
- [ ] All components migrated to apps/
- [ ] All manifests created and valid
- [ ] Solutions layer orchestrates properly
- [ ] Gateway discovers all services
- [ ] All tests passing (100%)
- [ ] Performance maintained or improved
- [ ] Documentation updated
- [ ] Deployment configs working

### Cutover Plan
1. **Parallel Run Phase**
   - Run old and new systems together
   - Compare outputs
   - Monitor performance

2. **Gradual Migration**
   - Route percentage of traffic to new system
   - Monitor errors and performance
   - Increase percentage gradually

3. **Full Cutover**
   - Switch all traffic to new system
   - Keep old system available for rollback
   - Monitor closely for 24-48 hours

## 9. POST-MIGRATION TASKS

### Documentation Updates
Update all documentation to reflect new structure:

1. **Update CLAUDE.md**
   - Add migration-specific patterns
   - Update navigation to new structure
   - Include common migration issues

2. **Update README.md**
   - New setup instructions
   - Updated architecture diagram
   - Migration notes

3. **Create Migration Guide**
   ```
   docs/migration/kailash-sdk-migration.md
   ├── Why we migrated
   ├── What changed
   ├── How to work with new structure
   └── Troubleshooting
   ```

### Team Training
Create training materials:
- Quick start guide for new structure
- Common tasks in new system
- Troubleshooting guide
- Best practices

### Template Sync Setup
Enable ongoing updates:

```bash
# Add template remote
git remote add template https://github.com/your-org/new_project_template
git fetch template

# Create sync branch
git checkout -b template-sync template/main

# Document sync process
cat > docs/template-sync.md << EOF
# Template Sync Process

1. Fetch latest template
2. Merge carefully preserving customizations
3. Test thoroughly
4. Create PR for review
EOF
```

## 10. ULTRATHINK MIGRATION CRITIQUE

Put on your ultrathink cap. Review the entire migration:

1. **Did we maintain all functionality?**
   - Compare feature parity
   - Check performance metrics
   - Verify user workflows

2. **Is the new structure actually better?**
   - Easier to develop?
   - Easier to deploy?
   - Easier to maintain?

3. **What problems did migration introduce?**
   - New complexity?
   - Performance issues?
   - Team confusion?

4. **What would you do differently?**
   - Better migration order?
   - Different patterns?
   - Additional tooling?

**Document critique in `docs/critiques/migration-retrospective.md`**

---

## Migration Success Criteria

Before declaring migration complete:

1. **All tests passing** (show output)
2. **Performance maintained** (show benchmarks)
3. **Zero functionality lost** (show comparison)
4. **Team trained** (show materials)
5. **Documentation complete** (show updates)
6. **Production validated** (show metrics)

**Do not declare complete until ALL criteria are met with evidence.**
