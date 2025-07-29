# Kailash SDK Focused Subagents

This directory contains focused subagents designed to replace the token-heavy feature-implementation.md workflow with efficient specialists that operate in separate context windows.

## Focused Subagent Architecture

The subagents are designed around the core workflow phases identified in `CLAUDE.md` and `feature-implementation.md`:

### Core Specialists

| Agent | Purpose | When to Use |
|-------|---------|-------------|

| **sdk-navigator** | Documentation navigation with file indexes | Finding specific patterns, guides, examples |
| **framework-advisor** | DataFlow, Nexus, MCP selection & implementation | Choosing between Core SDK and App Framework |
| **pattern-expert** | Core SDK patterns (workflows, nodes, parameters) | Implementing workflows, debugging pattern issues |
| **gold-standards-validator** | Compliance checking against gold standards | Code validation, catching violations early |
| **testing-specialist** | 3-tier testing strategy with real infrastructure | Understanding testing requirements and strategy |
| **tdd-implementer** | Test-first development methodology | Implementing features with write-test-then-code |
| **documentation-validator** | Docu| **ultrathink-analyst** | Deep analysis and failure point identification | Complex features, systemic issues, risk analysis |

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
| **1. Analysis** | ultrathink-analyst → requirements-analyst → sdk-navigator → framework-advisor | Deep analysis, requirements, existing patterns, tech selection |
| **2. Planning** | todo-manager → intermediate-reviewer | Task breakdown and validation |
| **3. Implementation** | tdd-implementer → pattern-expert → intermediate-reviewer → gold-standards-validator | Test-first, implement, review, validate (repeat per component) |
| **4. Testing** | testing-specialist → documentation-validator | Full test coverage, doc accuracy |
| **5. Final** | intermediate-reviewer | Final critique |

### Phase 1: Analysis & Planning (Sequential)
```
1. > Use the ultrathink-analyst subagent to analyze requirements and identify failure points for [feature]
2. > Use the requirements-analyst subagent to create systematic breakdown and ADR for [feature]
3. > Use the sdk-navigator subagent to find existing patterns similar to [feature]
4. > Use the framework-advisor subagent to recommend Core SDK vs DataFlow vs Nexus for [feature]

OR chain all Phase 1 agents:
> Use the ultrathink-analyst, requirements-analyst, sdk-navigator, and framework-advisor subagents to perform complete analysis and planning for [feature]
```

### Phase 2: Task Planning & Review
```
1. > Use the todo-manager subagent to create detailed task breakdown based on requirements
2. > Use the intermediate-reviewer subagent to review todo completeness and feasibility

OR chain Phase 2:
> Use the todo-manager and intermediate-reviewer subagents to create and validate task breakdown
```

### Phase 3: Implementation (Iterative per component)
```
For each component:
1. > Use the tdd-implementer subagent to write tests first for [component]
2. > Use the pattern-expert subagent to implement [component] following SDK patterns
3. > Use the gold-standards-validator subagent to ensure [component] compliance
4. > Use the intermediate-reviewer subagent to review [component] implementation

OR chain Phase 3 for a component:
> Use the tdd-implementer, pattern-expert, and gold-standards-validator subagents to implement and validate [component]

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

### Phase 5: Final Review
```
> Use the intermediate-reviewer subagent to perform final critique of complete implementation
```

### Quick Debugging Sequence
```
When facing issues:
1. > Use the sdk-navigator subagent to find solutions in common-mistakes.md
2. > Use the pattern-expert subagent to debug specific pattern issues
3. > Use the testing-specialist subagent to understand test failures

OR for comprehensive debugging:
> Use the sdk-navigator, pattern-expert, and testing-specialist subagents to diagnose and fix [issue]
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
- **src/kailash/mcp_server/**: Production MCP server implementation

### Gold Standards
- **sdk-users/7-gold-standards/**: All compliance standards
- **sdk-users/2-core-concepts/validation/common-mistakes.md**: Error solutions

This focused architecture maintains the essential workflow while dramatically reducing token usage through targeted, navigation-based agents that guide users to the right documentation at the right time.