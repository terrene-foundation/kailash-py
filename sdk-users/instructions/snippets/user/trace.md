# Repository Analysis and Migration Instruction Snippets

These snippets guide Claude Code through systematic analysis of existing repositories and migration to the Kailash SDK template structure.

## 🎯 ULTRATHINK ACTIVATION

Before starting any analysis, put on your ultrathink cap and answer these questions:

1. **What type of application is this likely to be?**
   - Look at root files, dependencies, and structure
   - Identify the primary business domain
   - Note any obvious architectural patterns

2. **What migration challenges are most likely?**
   - Consider the technology stack
   - Think about state management complexity
   - Identify potential breaking changes

3. **What existing Kailash SDK components could replace custom code?**
   - Consider the business logic type
   - Think about common patterns (API, data processing, orchestration)
   - Identify reusable SDK nodes

**Document your initial analysis before proceeding.**

## 🔍 Phase 1: Initial Repository Analysis

### 1.0 Framework-First Check

Before deep analysis, check if this repository already uses any Kailash frameworks:

```
Quick framework check:
1. Search for kailash imports: grep -r "from kailash" . --include="*.py"
2. Check requirements: grep -i kailash requirements.txt pyproject.toml
3. Look for existing SDK patterns: find . -name "*node.py" -o -name "*workflow.py"
4. Check for framework apps: ls -la apps/ 2>/dev/null

If Kailash SDK is already in use, focus analysis on:
- Current SDK version and patterns used
- Gaps between current and ideal template structure
- Existing nodes and workflows to preserve
```

### 1.1 Comprehensive Structure Discovery

Please perform a comprehensive analysis of this repository structure:

1. **Root Level Analysis**
   - List all files and directories at root level
   - Identify entry points (main.py, app.py, server.py, etc.)
   - Check for CLAUDE.md, README.md, or similar documentation
   - Identify build/config files (pyproject.toml, setup.py, requirements.txt)
   - Note any Docker/deployment configurations

2. **Code Organization Pattern**
   - Is code in root, src/, or another structure?
   - Are there multiple applications or a monolith?
   - How are modules/components organized?
   - What's the import structure pattern?

3. **Documentation Audit**
   - List all documentation directories and files
   - Identify documentation patterns (docs/, wiki/, README files)
   - Check for architecture decisions (ADR/, decisions/)
   - Find any AI/Claude-specific instructions

4. **Workflow Analysis**
   - Identify business logic organization
   - Map workflow/process implementations
   - Find state management patterns
   - Locate orchestration/coordination code

5. **Testing Infrastructure**
   - Test directory structure
   - Testing frameworks in use
   - Coverage configuration
   - Test naming patterns

**Provide a structured summary with specific file paths and patterns found.

**VALIDATION**: Show me actual command outputs, not just descriptions. I need to see:
- `ls -la` output for root directory
- `find . -name "main.py" -o -name "app.py" -o -name "server.py"` results
- `cat pyproject.toml | head -20` or `cat requirements.txt | head -20`
- First 50 lines of main entry point file**

### 1.2 Technology Stack Identification

Analyze the technology stack and dependencies:

1. **Core Technologies**
   - Primary language and version
   - Key frameworks (FastAPI, Flask, Django, etc.)
   - Database systems in use
   - Message queues or event systems

2. **Kailash SDK Usage**
   - Check if kailash SDK is already imported
   - Identify any workflow/node patterns
   - Find custom node implementations
   - Note SDK version if present

3. **External Dependencies**
   - List major libraries from requirements/pyproject
   - Identify API integrations
   - Note authentication/security libraries
   - Find monitoring/logging tools

4. **Development Tools**
   - Linting/formatting configuration
   - Pre-commit hooks
   - CI/CD pipeline files
   - Development environment setup

**Create a technology inventory with versions where available.

**VALIDATION**: Run these commands and show output:
```bash
# Python version
python --version

# Key dependencies with versions
pip list | grep -E "(fastapi|flask|django|kailash|pytest|docker)"

# Check for Docker
docker --version 2>/dev/null || echo "Docker not found"

# Check test framework
pytest --version 2>/dev/null || echo "Pytest not found"
```**

### 1.3 Business Logic Mapping

Map the core business logic and data flows:

1. **Entry Points**
   - Main application entry (with file:line references)
   - API endpoints or routes
   - Background job processors
   - Event handlers

2. **Core Business Flows**
   - Trace main user journeys through code
   - Map data transformations
   - Identify decision points
   - Document state transitions

3. **Data Models**
   - Database schemas or models
   - API contracts/schemas
   - Internal data structures
   - Configuration formats

4. **Integration Points**
   - External API calls
   - Database operations
   - File system interactions
   - Third-party service integrations

**Provide a flow diagram in text format showing key paths through the system.

### 1.4 Testing Infrastructure Deep Dive

Analyze the testing setup to understand migration complexity:

```
1. **Test Structure Analysis**
   ```bash
   # Show test directory structure
   find . -type d -name "test*" | head -20

   # Count test files by type
   echo "Unit tests:" && find . -name "test_*.py" -path "*/unit/*" | wc -l
   echo "Integration tests:" && find . -name "test_*.py" -path "*/integration/*" | wc -l
   echo "E2E tests:" && find . -name "test_*.py" -path "*/e2e/*" | wc -l
   ```

2. **Test Quality Assessment**
   - Check for mocking patterns: `grep -r "mock\|Mock\|patch" tests/ --include="*.py" | head -10`
   - Look for fixtures: `grep -r "@fixture\|@pytest.fixture" tests/ --include="*.py" | head -10`
   - Find Docker usage: `grep -r "docker\|container" tests/ --include="*.py" | head -10`

3. **Current Coverage**
   ```bash
   # Check if coverage report exists
   find . -name ".coverage" -o -name "htmlcov" -o -name "coverage.xml" | head -5

   # Look for coverage config
   grep -A5 "\[coverage\|coverage:" pyproject.toml setup.cfg .coveragerc 2>/dev/null
   ```

**Important**: Understanding current testing approach is CRITICAL for migration success.
Tests will need to be reorganized into the 3-tier structure:
- Tier 1 (Unit): Fast, can use mocks
- Tier 2 (Integration): NO MOCKING, real Docker services
- Tier 3 (E2E): NO MOCKING, complete user flows**

## 🎯 Phase 2: Gap Analysis

### 2.1 Template Alignment Assessment

Compare this repository against the ideal Kailash SDK template structure:

1. **Structural Gaps**
   Compare current structure to ideal:
   ```
   ideal_structure/
   ├── CLAUDE.md              ← Check if exists
   ├── README.md              ← Check content/format
   ├── pyproject.toml         ← Modern Python config?
   ├── src/                   ← Code organization
   ├── apps/                  ← Multi-app architecture?
   ├── solutions/             ← Cross-app orchestration?
   ├── sdk-users/             ← SDK documentation?
   ├── deployment/            ← Production ready?
   ├── docs/                  ← Documentation structure
   ├── data/                  ← Data organization
   ├── tests/                 ← Test infrastructure
   ├── scripts/               ← Automation tools
   └── todos/                 ← Task tracking system?
   ```

2. **Pattern Gaps**
   - Missing manifest.yaml files for apps
   - Lack of two-level documentation (root + app)
   - No service discovery setup
   - Missing ADR/todos/mistakes structure
   - Absence of template sync capability

3. **SDK Integration Gaps**
   - Not using WorkflowBuilder patterns
   - Custom orchestration instead of SDK nodes
   - Missing node naming conventions
   - Manual state management

4. **Deployment Gaps**
   - No unified gateway
   - Missing Docker/Kubernetes configs
   - Lack of environment management
   - No automated deployment

**For each gap, rate priority (High/Medium/Low) and complexity (Simple/Moderate/Complex).

**Create a Gap Summary Table**:
| Gap Category | Specific Gap | Priority | Complexity | Estimated Effort |
|--------------|--------------|----------|------------|------------------|
| Structure    | No apps/ dir | High     | Simple     | 1-2 days        |
| Pattern      | No manifest.yaml | High  | Simple     | 1 day           |
| Testing      | No 3-tier structure | Medium | Complex | 1 week       |

### 2.3 Migration Risk Assessment

Identify critical risks before migration:

```
1. **Data/State Risks**
   - Stateful components that need careful migration
   - Database schemas that might need evolution
   - Cache/session data that could be lost

2. **Integration Risks**
   - External API dependencies
   - Service-to-service communications
   - Authentication/authorization flows

3. **Performance Risks**
   - Current bottlenecks that might worsen
   - Additional overhead from SDK patterns
   - Network latency from service separation

4. **Operational Risks**
   - Deployment complexity increase
   - Monitoring/logging gaps
   - Team knowledge gaps

For each risk, specify:
- Impact (High/Medium/Low)
- Likelihood (High/Medium/Low)
- Mitigation strategy
```**

### 2.2 Code Quality Assessment

Evaluate code organization for SDK compatibility:

1. **Modularity Check**
   - Are components properly separated?
   - Can workflows be extracted to nodes?
   - Is business logic mixed with infrastructure?
   - Are there clear interfaces between modules?

2. **SDK Readiness**
   - Which parts can become WorkflowNodes?
   - What needs PythonCodeNode wrapping?
   - Are there reusable patterns for nodes?
   - Can orchestration use SDK patterns?

3. **Testability**
   - Current test coverage percentage
   - Unit vs integration test balance
   - Mock usage vs real implementations
   - Test data management approach

4. **Documentation Quality**
   - Code comments coverage
   - API documentation completeness
   - Architecture documentation currency
   - Operational runbooks existence

Identify the top refactoring priorities for SDK migration.

## 🚀 Phase 3: Migration Planning

### 3.1 Create Migration Roadmap

Design a phased migration plan to the template structure:

**FIRST: Set Up Migration Todo System**
Create a comprehensive todo tracking system for the migration:

```
1. **Create Migration Todo Structure**
   mkdir -p todos/migration/{active,completed,backlog}

2. **Create Master Migration List** (todos/migration/000-migration-master.md):
   # Migration Master Todo List

   ## Phase 1: Analysis & Planning
   - [ ] Complete repository analysis
   - [ ] Create migration ADR
   - [ ] Identify component priorities
   - [ ] Set up migration infrastructure

   ## Phase 2: Structure Alignment
   - [ ] Create apps/ directory structure
   - [ ] Create manifest.yaml templates
   - [ ] Set up Docker infrastructure

   ## Phase 3: Component Migration
   - [ ] Migrate [Component 1]
   - [ ] Migrate [Component 2]
   - [ ] Migrate [Component N]

   ## Phase 4: Testing & Validation
   - [ ] Migrate test suite to 3-tier
   - [ ] Achieve 80%+ coverage
   - [ ] Performance validation

   ## Phase 5: Deployment & Cutover
   - [ ] Update deployment configs
   - [ ] Parallel run validation
   - [ ] Final cutover

3. **Create Detailed Todo Templates**:
   For each component, create: todos/migration/active/XXX-migrate-[component].md
   ```
   # Migrate [Component Name]

   ## Acceptance Criteria
   - [ ] All functionality preserved
   - [ ] Tests passing (unit/integration/e2e)
   - [ ] Performance maintained
   - [ ] Documentation updated

   ## Subtasks
   - [ ] Analyze current implementation
   - [ ] Design SDK node structure
   - [ ] Create app directory
   - [ ] Implement node(s)
   - [ ] Migrate tests
   - [ ] Update imports
   - [ ] Validate functionality

   ## Risks
   - [Risk 1]: [Mitigation]
   - [Risk 2]: [Mitigation]

   ## Dependencies
   - Requires: [Component X] migrated first
   - Blocks: [Component Y] migration
   ```

4. **Plan Todo Management Process**:
   Define how todos will be managed during implementation:
   - Components move from backlog → active → completed
   - Each completed todo gets date prefix when moved
   - Master list updated after each component
   - Status dashboard tracks overall progress

**SECOND: Plan Migration ADR**
Plan to create Architecture Decision Record during implementation:
- Context: Why migrate? Current limitations?
- Decision: Migration approach and rationale
- Consequences: Benefits, risks, impacts
- Alternatives: Other options considered

### 3.2 Define Migration Phases

Based on analysis, define the migration phases:

1. **Phase 1: Structure Alignment**
   - Plan apps/ directory structure
   - Identify which code moves where
   - Define manifest.yaml requirements
   - Plan Docker infrastructure needs

2. **Phase 2: SDK Integration**
   - Map current code to SDK patterns
   - Identify WorkflowBuilder opportunities
   - List custom patterns to replace
   - Plan CLAUDE.md content

3. **Phase 3: Documentation Migration**
   - Map current docs to new structure
   - Plan ADR organization
   - List cross-references to update

4. **Phase 4: Deployment Modernization**
   - Define gateway requirements
   - Plan Docker/Kubernetes setup
   - Design service discovery approach
   - List deployment automation needs

5. **Phase 5: Testing & Validation**
   - Define coverage targets
   - Plan validation approach
   - List performance benchmarks
   - Define acceptance criteria

For each phase, document:
- Specific tasks to complete
- Dependencies and prerequisites
- Risk mitigation strategies
- Success criteria

### 3.3 Component Migration Planning

For each component identified in the priority matrix:

1. **Component Analysis**
   - Document current file locations
   - List all dependencies (internal and external)
   - Map current behavior and test cases
   - Identify integration points

2. **Target Architecture Design**
   - Define target app structure
   - Map to appropriate SDK nodes
   - Plan state management approach
   - Design error handling strategy

3. **Migration Task List**
   - List files to move/refactor
   - Define import updates needed
   - Plan test migration approach
   - Identify validation steps

4. **Risk Assessment**
   - Breaking changes to consumers
   - Performance impact concerns
   - Data migration requirements
   - Rollback strategy needed

## 🎯 Phase 4: Migration Readiness Assessment

### 4.1 Pre-Migration Validation Plan

Define validation approach for the migration:

1. **Testing Strategy**
   - Map existing tests to 3-tier structure
   - Identify gaps in test coverage
   - Plan new tests needed for SDK patterns
   - Define performance benchmarks

2. **Acceptance Criteria**
   - No functionality regression
   - Performance maintained or improved
   - All existing integrations work
   - Zero data loss

3. **Rollback Planning**
   - Define rollback triggers
   - Plan data backup strategy
   - Document rollback procedures
   - Test rollback approach

4. **Communication Plan**
   - Stakeholder notifications
   - Team training needs
   - Documentation requirements
   - Support procedures

### 4.2 Resource Planning

Plan resources needed for migration:

1. **Team Requirements**
   - Developer skills needed
   - Training requirements
   - Time allocation per phase
   - External support needs

2. **Infrastructure Needs**
   - Development environments
   - Testing infrastructure
   - Staging environment
   - Production readiness

3. **Tool Requirements**
   - Migration scripts needed
   - Testing tools required
   - Monitoring setup
   - Documentation tools

4. **Budget Considerations**
   - Development effort
   - Infrastructure costs
   - Training expenses
   - Contingency planning

## 🚀 HANDOVER TO IMPLEMENTATION

### Analysis Complete - Ready for Migration?

Once you've completed all analysis phases, create a Migration Readiness Report:

```markdown
# Migration Readiness Report

## Repository Overview
- **Name**: [repository name]
- **Type**: [API service, data processor, web app, etc.]
- **Size**: [LOC, number of modules, complexity]
- **Current State**: [monolith, microservices, hybrid]

## Key Findings
1. **Critical Components**: [list top 5-10 components]
2. **Major Risks**: [top 3 risks with mitigation strategies]
3. **Quick Wins**: [easy migrations that provide immediate value]
4. **Complex Migrations**: [components requiring significant effort]

## Migration Recommendation
- **Approach**: [Big Bang / Phased / Hybrid]
- **Timeline**: [estimated weeks/months]
- **Team Size**: [recommended team size]
- **Priority Order**: [numbered list of components]

## Pre-Migration Checklist
- [ ] All tests currently passing
- [ ] Documentation is current
- [ ] Team understands Kailash SDK patterns
- [ ] Docker infrastructure available
- [ ] Backup/rollback plan defined

## Next Steps
**Ready to proceed with migration implementation.**
Use migration-implementation.md for detailed implementation guidance.
```

### Handover to migration-implementation.md

After completing analysis and creating the readiness report:

```
**HANDOVER COMMAND**:
"I've completed the repository analysis using trace.md. Here's the Migration Readiness Report: [paste report]. I'm now ready to begin implementation following migration-implementation.md. Should I proceed with Phase 1: Structure Alignment?"
```

The migration-implementation.md guide will take over with:
1. ULTRATHINK activation for migration
2. ADR creation for migration decisions
3. Component-by-component migration with validation
4. 3-tier test implementation
5. Continuous validation at each step

### Critical Handover Information

Ensure these are documented for migration-implementation.md:

1. **Component Dependency Graph**
   ```
   Component A → Component B → Component C
           ↓                      ↑
   Component D ←─────────────────┘
   ```

2. **Test Migration Mapping**
   ```
   Current Test → Target Tier → SDK Pattern
   test_api.py → Tier 2 → WorkflowNode integration test
   test_unit.py → Tier 1 → Node unit test
   test_full.py → Tier 3 → E2E workflow test
   ```

3. **Risk Mitigation Timeline**
   ```
   Week 1: Address Risk A (data migration)
   Week 2: Address Risk B (API compatibility)
   Week 3: Address Risk C (performance validation)
   ```

---
*These snippets provide thorough analysis. The migration-implementation.md guide provides step-by-step implementation with continuous validation.*
