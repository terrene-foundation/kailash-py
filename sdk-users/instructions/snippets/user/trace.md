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
   ├── deployment/            ← Production ready?
   ├── docs/                  ← Documentation structure
   ├── data/                  ← Data organization
   ├── tests/                 ← Test infrastructure
   └── scripts/               ← Automation tools
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

**FIRST: Create Migration ADR**
Before any planning, create an Architecture Decision Record:
```
File: adr/XXX-kailash-sdk-migration.md
- Context: Why migrate? Current limitations?
- Decision: Migration approach and rationale
- Consequences: Benefits, risks, impacts
- Alternatives: Other options considered
```

1. **Phase 1: Structure Alignment**
   - Create apps/ directory structure
   - Move core logic to appropriate apps
   - Add manifest.yaml to each app
   - Set up basic Docker infrastructure

2. **Phase 2: SDK Integration**
   - Convert orchestration to WorkflowBuilder
   - Implement key workflows as nodes
   - Replace custom patterns with SDK nodes
   - Add CLAUDE.md with SDK patterns

3. **Phase 3: Documentation Migration**
   - Implement two-level documentation
   - Move decisions to ADR structure
   - Update all cross-references

4. **Phase 4: Deployment Modernization**
   - Implement gateway pattern
   - Add Docker/Kubernetes configs
   - Set up service discovery
   - Create deployment automation

5. **Phase 5: Testing & Validation**
   - Achieve 80%+ test coverage
   - Validate all migrations work
   - Performance testing
   - Documentation review

For each phase, list:
- Specific tasks with file paths
- Dependencies and blockers
- Risk mitigation strategies
- Validation criteria

### 3.2 Detailed Migration Steps

For the highest priority component/workflow to migrate:

1. **Current State Analysis**
   - Trace complete code path (all files involved)
   - List all dependencies
   - Document current behavior
   - Identify test cases

2. **Target Design**
   - Design as SDK workflow
   - Identify required nodes
   - Plan state management
   - Design error handling

3. **Migration Steps**
   Step 1: Create app structure

   Step 2: Extract and refactor code
   - Move files with git mv
   - Update imports
   - Refactor to node pattern
   - Add SDK integration

   Step 3: Create workflow

   Step 4: Update tests
   - Migrate existing tests
   - Add SDK-specific tests
   - Ensure coverage maintained

   Step 5: Integration
   - Update entry points
   - Add to gateway config
   - Test end-to-end

4. **Validation Checklist**
   - [ ] All tests pass
   - [ ] No functionality lost
   - [ ] Performance maintained
   - [ ] Documentation updated
   - [ ] Manifest.yaml correct

## 🔧 Phase 4: Implementation Patterns

### 4.1 Node Conversion Pattern

Convert this function/class to a Kailash SDK node:

Given: [paste current code]

1. **Analyze Current Code**
   - Input parameters
   - Processing logic
   - Output format
   - External dependencies

2. **Design Node Structure**

3. **Integration Pattern**
   - Show workflow integration
   - Data path connections
   - Error handling approach
   - Testing strategy

4. **Migration Commands**
   ```bash
   # Move to correct location
   git mv [old_path] apps/[app_name]/src/nodes/[name]_node.py

   # Update imports across codebase
   # Show specific import changes needed
   ```

### 4.2 Manifest Creation

Create manifest.yaml for this application component:

1. **Analyze Capabilities**
   - List all API endpoints
   - Identify background tasks
   - Find integration points
   - Note data sources

2. **Generate Manifest**
   ```yaml
   name: [app-name]
   version: 0.1.0
   type: hybrid  # api|mcp|hybrid
   capabilities:
     api:
       enabled: true
       endpoints:
         - path: /api/v1/[resource]
           method: [GET|POST|PUT|DELETE]
           description: "[endpoint purpose]"
     mcp:
       enabled: true
       tools:
         - name: [tool_name]
           description: "[tool purpose]"
     background:
       workers:
         - name: [worker_name]
           schedule: "cron expression or interval"

   dependencies:
     - kailash>=1.0.0
     - [other deps]

   environment:
     required:
       - ENV_VAR_NAME
     optional:
       - OPTIONAL_VAR: default_value
   ```

3. **Validation**
   - Check all endpoints covered
   - Verify dependencies complete
   - Test environment variables
   - Validate with gateway

### 4.3 Documentation Migration

Migrate existing documentation to template structure:

1. **Inventory Current Docs**
   ```
   find . -name "*.md" -o -name "*.rst" -o -name "*.txt" | grep -E "(doc|wiki|guide)"
   ```

2. **Categorize Content**
   - Architecture decisions → /adr/
   - API documentation → /docs/api/
   - User guides → /docs/user-guides/
   - Development guides → /docs/development/
   - Deployment guides → /deployment/docs/

3. **Create CLAUDE.md**
   Structure with sections:
   - Project Overview (2-3 sentences)
   - Critical Patterns (Must-follow rules)
   - Quick Start (Under 5 minutes)
   - Navigation Guide (Where to find what)
   - Project-Specific Instructions
   - Common Tasks (with file:line references)

4. **Update Cross-References**

5. **Add SDK References**
   Link to relevant SDK docs:
   - Node selection → sdk-users/nodes/node-selection-guide.md
   - Patterns → sdk-users/cheatsheet/
   - Workflows → sdk-users/workflows/

## 🧪 Phase 5: Validation Instructions

### 5.1 Migration Validation


Validate the migration for [component/workflow name]:

1. **Functional Testing**

2. **Performance Comparison**
   - Measure latency before/after
   - Check memory usage
   - Monitor CPU utilization
   - Validate throughput

3. **Integration Testing**
   - Test with gateway
   - Verify service discovery
   - Check cross-app communication
   - Validate error handling

4. **Documentation Check**
   - All links work
   - Code examples run
   - Manifest validates
   - CLAUDE.md complete

**Report any regressions or issues found.**

### 5.2 Final Checklist

Complete pre-production checklist:

Repository Structure:
- [ ] All code in apps/ or solutions/
- [ ] Each app has manifest.yaml
- [ ] CLAUDE.md at root with project patterns
- [ ] Two-level documentation structure
- [ ] SDK-users/ has relevant guides

Code Quality:
- [ ] All workflows use SDK patterns
- [ ] Nodes follow naming convention
- [ ] No custom orchestration code
- [ ] Error handling standardized
- [ ] Logging consistent

Testing:
- [ ] 80%+ test coverage
- [ ] All tests passing
- [ ] Performance benchmarks met
- [ ] Integration tests complete

Documentation:
- [ ] Architecture decisions recorded
- [ ] API documentation current
- [ ] Deployment guide complete
- [ ] Troubleshooting guide exists

Deployment:
- [ ] Docker files created
- [ ] Kubernetes manifests ready
- [ ] Gateway configuration complete
- [ ] Environment management setup

**For any unchecked items, provide remediation steps.**

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
