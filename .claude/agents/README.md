# Kailash SDK Focused Subagents

This directory contains focused subagents designed to replace the token-heavy feature-implementation.md workflow with efficient specialists that operate in separate context windows.

## Focused Subagent Architecture

The subagents are designed around the core workflow phases identified in `CLAUDE.md` and `feature-implementation.md`:

### Core Specialists

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **sdk-navigator** | Documentation navigation with file indexes | Finding specific patterns, guides, examples |
| **framework-advisor** | Framework selection and coordination | Choosing between Core SDK, DataFlow, Nexus, MCP |
| **pattern-expert** | Core SDK patterns (workflows, nodes, parameters) | Implementing workflows, debugging pattern issues |
| **gold-standards-validator** | Compliance checking against gold standards | Code validation, catching violations early |
| **testing-specialist** | 3-tier testing strategy with real infrastructure | Understanding testing requirements and strategy |
| **tdd-implementer** | Test-first development methodology | Implementing features with write-test-then-code |
| **documentation-validator** | Documentation validation and testing | Testing code examples, ensuring doc accuracy |
| **ultrathink-analyst** | Deep analysis and failure point identification | Complex features, systemic issues, risk analysis |
| **requirements-analyst** | Requirements breakdown and ADR creation | Systematic analysis, architecture decisions |
| **intermediate-reviewer** | Checkpoint reviews and progress critique | Reviewing todos and implementation milestones |
| **todo-manager** | Task management and project tracking | Creating and managing development task lists |
| **mcp-specialist** | MCP server implementation and integration | Model Context Protocol patterns and debugging |
| **git-release-specialist** | Git workflows, CI validation, and releases | Pre-commit checks, PR creation, version releases |
| **gh-manager** | GitHub project and issue management | Syncing requirements with GitHub Projects, managing sprints |

### Framework Specialists

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **nexus-specialist** | Nexus multi-channel platform implementation | Zero-config deployment, API/CLI/MCP orchestration, **DataFlow integration** |
| **dataflow-specialist** | DataFlow database framework implementation | Database operations, bulk processing, auto node generation, **Nexus integration** |
| **kaizen-specialist** | Kaizen AI framework implementation | Signature-based programming, multi-agent coordination, multi-modal workflows |

### Frontend & Mobile Specialists

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **react-specialist** | React and Next.js frontend implementation | Workflow editors, admin dashboards, AI agent interfaces with React Flow |
| **flutter-specialist** | Flutter cross-platform mobile/desktop apps | Mobile workflow builders, AI agent interfaces, enterprise mobile apps |
| **frontend-developer** | General responsive UI components | Creating pages, converting mockups, implementing React features |

### Infrastructure Specialists

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **deployment-specialist** | Docker and Kubernetes deployment | Production deployments, environment management, service orchestration |

### Critical Integration Guides

**⚠️ IMPORTANT: DataFlow + Nexus Integration**
- See: `sdk-users/guides/dataflow-nexus-integration.md` for tested configurations
- Key settings to prevent blocking: `Nexus(auto_discovery=False)` + `DataFlow(skip_registry=True)`
- Full featured config available with 10-30s startup time
- Both specialists updated with integration warnings

### Design Principles

1. **Navigation over Loading**: Agents use file indexes rather than loading entire contexts
2. **Focused Expertise**: Each agent has a specific, narrow domain of expertise
3. **Reference-Based**: Agents provide specific file paths and references
4. **Workflow-Aligned**: Agents map to the established development workflow phases

## Suggested Usage Sequence

Follow this sequence for efficient feature development:

### Quick Reference: Agents by Phase

| Phase | Agents (in order) | Purpose |
|-------|-------------------|---------|
| **1. Analysis** | ultrathink-analyst → requirements-analyst → sdk-navigator → framework-advisor → (nexus/dataflow/kaizen-specialist) | Deep analysis, requirements, existing patterns, tech selection, framework-specific guidance |
| **2. Planning** | todo-manager → gh-manager → intermediate-reviewer | Task breakdown, GitHub sync, and validation |
| **3. Implementation** | tdd-implementer → pattern-expert → (nexus/dataflow/kaizen/react/flutter-specialist) → intermediate-reviewer → gold-standards-validator | Test-first, implement, framework patterns, review, validate (repeat per component) |
| **4. Testing** | testing-specialist → documentation-validator | Full test coverage, doc accuracy |
| **5. Deployment** | deployment-specialist | Docker/Kubernetes setup, environment management |
| **6. Release** | git-release-specialist | Pre-commit validation, PR creation, version management |
| **7. Final** | intermediate-reviewer | Final critique |

### Phase 1: Analysis & Planning (Sequential)
```
1. > Use the ultrathink-analyst subagent to analyze requirements and identify failure points for [feature]
2. > Use the requirements-analyst subagent to create systematic breakdown and ADR for [feature]
3. > Use the sdk-navigator subagent to find existing patterns similar to [feature]
4. > Use the framework-advisor subagent to recommend Core SDK vs DataFlow vs Nexus vs Kaizen for [feature]
   - If DataFlow recommended: > Use the dataflow-specialist subagent for implementation details
   - If Nexus recommended: > Use the nexus-specialist subagent for implementation details
   - If Kaizen recommended: > Use the kaizen-specialist subagent for implementation details
   - If React frontend needed: > Use the react-specialist subagent for UI implementation details
   - If Flutter mobile needed: > Use the flutter-specialist subagent for mobile implementation details

OR chain all Phase 1 agents:
> Use the ultrathink-analyst, requirements-analyst, sdk-navigator, and framework-advisor subagents to perform complete analysis and planning for [feature]
```

### Phase 2: Task Planning & Review
```
1. > Use the todo-manager subagent to create detailed task breakdown based on requirements
2. > Use the gh-manager subagent to sync tasks with GitHub Projects and create issues
3. > Use the intermediate-reviewer subagent to review todo completeness and feasibility

OR chain Phase 2:
> Use the todo-manager, gh-manager, and intermediate-reviewer subagents to create, sync, and validate task breakdown
```

### Phase 3: Implementation (Iterative per component)
```
For each component:
1. > Use the tdd-implementer subagent to write tests first for [component]
2. > Use the pattern-expert subagent to implement [component] following SDK patterns
   - For DataFlow components: > Use the dataflow-specialist subagent for database patterns
   - For Nexus components: > Use the nexus-specialist subagent for multi-channel patterns
   - For Kaizen components: > Use the kaizen-specialist subagent for AI agent patterns
   - For React components: > Use the react-specialist subagent for frontend patterns
   - For Flutter components: > Use the flutter-specialist subagent for mobile patterns
3. > Use the gold-standards-validator subagent to ensure [component] compliance
4. > Use the intermediate-reviewer subagent to review [component] implementation

OR chain Phase 3 for a component:
> Use the tdd-implementer, pattern-expert, gold-standards-validator, and appropriate framework specialists to implement and validate [component]

POST Phase 3:
> Use the intermediate-reviewer subagent to ensure that the implementation meets all requirements and standards
```

### Phase 4: Testing & Documentation
```
1. > Use the testing-specialist subagent to verify 3-tier test coverage
2. > Use the documentation-validator subagent to test all code examples in documentation
3. > Use the todo-manager subagent to ensure all todos are complete and update the todo system accordingly

OR chain Phase 4:
> Use the testing-specialist, documentation-validator, and todo-manager subagents to ensure complete test coverage and documentation accuracy
```

### Phase 5: Deployment Setup
```
1. > Use the deployment-specialist subagent to set up Docker Compose for local development
2. > Use the deployment-specialist subagent to configure Kubernetes for production deployment
3. > Use the deployment-specialist subagent to set up environment management and secrets

OR chain Phase 5:
> Use the deployment-specialist subagent to handle complete deployment setup from development to production
```

### Phase 6: Release & Git Management
```
1. > Use the git-release-specialist subagent to run pre-commit validation (black, isort, ruff)
2. > Use the git-release-specialist subagent to create feature branch and PR workflow
3. > Use the git-release-specialist subagent to handle version management and release procedures (if applicable)

OR chain Phase 6:
> Use the git-release-specialist subagent to validate code quality, create PR, and manage release workflow
```

### Phase 7: Final Review
```
> Use the intermediate-reviewer subagent to perform final critique of complete implementation
```

### Quick Debugging Sequence
```
When facing issues:
1. > Use the sdk-navigator subagent to find solutions in common-mistakes.md
2. > Use the pattern-expert subagent to debug specific pattern issues
3. > Use the testing-specialist subagent to understand test failures
   - For DataFlow issues: > Use the dataflow-specialist subagent for database-specific debugging
   - For Nexus issues: > Use the nexus-specialist subagent for multi-channel debugging
   - For Kaizen issues: > Use the kaizen-specialist subagent for AI agent debugging
   - For React issues: > Use the react-specialist subagent for frontend debugging
   - For Flutter issues: > Use the flutter-specialist subagent for mobile debugging
   - For deployment issues: > Use the deployment-specialist subagent for Docker/Kubernetes debugging

OR for comprehensive debugging:
> Use the sdk-navigator, pattern-expert, testing-specialist, and appropriate framework specialists to diagnose and fix [issue]
```

## Coordination Through Root CLAUDE.md

Since subagents cannot invoke other subagents, coordination happens at the main Claude Code level through the root `CLAUDE.md` file, which:

1. **Loads automatically** when Claude Code starts
2. **Contains the 18-step enterprise workflow** for guidance
3. **References subagents** for specific phases
4. **Maintains the multi-step strategy** that users follow

## File References

### Primary Workflow Sources
- **Root CLAUDE.md**: 18-step enterprise workflow, core patterns
- **feature-implementation.md**: 4-phase detailed implementation process
- **sdk-users/CLAUDE.md**: Essential SDK patterns navigation

### Framework Documentation
- **sdk-users/apps/dataflow/**: Zero-config database patterns and guides
- **sdk-users/apps/nexus/**: Multi-channel platform patterns and guides
- **sdk-users/apps/kaizen/**: Signature-based AI framework patterns and guides
- **src/kailash/mcp_server/**: Production MCP server implementation

### Frontend & Mobile Documentation
- **docs/guides/frontend_guidance.md**: React/Vue integration patterns
- **React Flow Templates**: Official workflow editor templates

### Infrastructure Documentation
- **Docker Compose**: Multi-service orchestration patterns
- **Kubernetes**: Production deployment patterns

### Gold Standards
- **sdk-users/7-gold-standards/**: All compliance standards
- **sdk-users/2-core-concepts/validation/common-mistakes.md**: Error solutions

This focused architecture maintains the essential workflow while dramatically reducing token usage through targeted, navigation-based agents that guide users to the right documentation at the right time.

## Framework-Specific Workflows

### DataFlow Database Applications
```
1. > Use the framework-advisor subagent to confirm DataFlow is appropriate
2. > Use the dataflow-specialist subagent for:
   - Model definition patterns
   - Auto-generated node usage
   - Bulk operations
   - Migration control (auto_migrate settings)
   - PostgreSQL-only execution limitations
```

### Nexus Multi-Channel Platforms
```
1. > Use the framework-advisor subagent to confirm Nexus is appropriate
2. > Use the nexus-specialist subagent for:
   - Zero-config initialization
   - Workflow registration patterns
   - Multi-channel parameter consistency
   - Progressive enterprise enhancement
   - Session management
```

### Kaizen AI Agent Applications
```
1. > Use the framework-advisor subagent to confirm Kaizen is appropriate
2. > Use the kaizen-specialist subagent for:
   - Signature-based programming patterns
   - BaseAgent implementation
   - Multi-agent coordination
   - Multi-modal processing (vision/audio)
   - A2A protocol integration
```

### React Frontend Applications
```
1. > Use the react-specialist subagent for:
   - React 19 and Next.js 15 App Router patterns
   - React Flow workflow editors
   - @tanstack/react-query API integration
   - Shadcn UI component implementation
   - Modular architecture (index.tsx + elements/)
```

### Flutter Mobile Applications
```
1. > Use the flutter-specialist subagent for:
   - Flutter 3.27+ Material Design 3 patterns
   - Riverpod state management
   - Responsive design (mobile/tablet/desktop)
   - Kailash SDK API integration
   - Cross-platform deployment
```

### Combined Framework Applications
```
For DataFlow + Nexus integration:
1. > Use the framework-advisor subagent for architecture guidance
2. > Use the dataflow-specialist subagent for database layer
3. > Use the nexus-specialist subagent for platform deployment
4. > Use the pattern-expert subagent for workflow connections

For Full-Stack Application (Backend + Frontend):
1. > Use the framework-advisor subagent for architecture guidance
2. > Use appropriate backend specialists (dataflow/nexus/kaizen)
3. > Use appropriate frontend specialists (react/flutter)
4. > Use the deployment-specialist subagent for infrastructure setup
5. > Use the pattern-expert subagent for integration patterns
```

## GitHub Project Management Workflow

### Syncing Requirements with GitHub
```
1. > Use the requirements-analyst subagent to create systematic breakdown
2. > Use the todo-manager subagent to create detailed task breakdown
3. > Use the gh-manager subagent to:
   - Sync tasks with GitHub Projects
   - Create issues with proper labels
   - Link issues to project milestones
   - Track sprint progress
```

## Production Deployment Workflow

### Setting Up Production Infrastructure
```
1. > Use the deployment-specialist subagent to:
   - Create Docker Compose configuration for local development
   - Set up Kubernetes deployments for production
   - Configure environment management (.env files, secrets)
   - Implement health checks and monitoring
   - Set up horizontal pod autoscaling
   - Configure CI/CD pipelines
```
