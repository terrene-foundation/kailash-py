# Agent Orchestration Rules

## Scope
These rules govern when and how specialized agents MUST be used.

## MANDATORY Delegations

### Rule 1: Code Review After ANY Change
After completing ANY file modification (Edit, Write), you MUST:
1. Delegate to **intermediate-reviewer** for code review
2. Wait for review completion before proceeding
3. Address any findings before moving to next task

**Enforced by**: PostToolUse hook reminder
**Exception**: User explicitly says "skip review"

### Rule 2: Security Review Before ANY Commit
Before executing ANY git commit command, you MUST:
1. Delegate to **security-reviewer** for security audit
2. Address all CRITICAL findings
3. Document any HIGH findings for tracking

**Enforced by**: PreToolUse hook on git commit
**Exception**: NONE - security review is always required

### Rule 3: Framework Specialist for Framework Work
When working with Kailash frameworks, you MUST consult:
- **dataflow-specialist**: For any database or DataFlow work
- **nexus-specialist**: For any API or deployment work
- **kaizen-specialist**: For any AI agent work
- **mcp-specialist**: For any MCP integration work

**Applies when**:
- Creating new workflows
- Modifying database models
- Setting up API endpoints
- Building AI agents

**Enforced by**: Framework detection in session-start hook

### Rule 4: Analysis Chain for Complex Features
For features requiring design decisions, follow this chain:
1. **deep-analyst** → Identify failure points
2. **requirements-analyst** → Break down requirements
3. **framework-advisor** → Choose implementation approach
4. Then appropriate specialist for implementation

**Applies when**:
- New feature spanning multiple files
- Unclear requirements
- Multiple valid approaches exist

### Rule 5: Parallel Execution for Independent Operations
When multiple independent operations are needed, you MUST:
1. Launch agents in parallel using Task tool
2. Wait for all to complete
3. Aggregate results

**Example independent operations**:
- Reading multiple unrelated files
- Running multiple search queries
- Validating separate components

## Examples

### Correct: Sequential with Review
```
✅ User asks for code change
   → Agent implements change
   → Agent delegates to intermediate-reviewer
   → Agent addresses review findings
   → Only then moves to next task
```

### Incorrect: Skipping Review
```
❌ User asks for code change
   → Agent implements change
   → Agent moves to next task (skipped review!)
```

## PROHIBITED Actions

### MUST NOT: Skip Code Review
Code review is mandatory after changes. Skipping requires explicit user approval.

### MUST NOT: Commit Without Security Review
Security review before commits is non-negotiable.

### MUST NOT: Framework Work Without Specialist
Never use raw SQL when DataFlow patterns exist.
Never build custom API when Nexus patterns exist.
Never build custom agents when Kaizen patterns exist.

### MUST NOT: Sequential When Parallel Possible
If operations are independent, run them in parallel.

## Quality Gates

### Checkpoint 1: After Planning
- [ ] Requirements understood
- [ ] Approach validated
- [ ] Framework selected

### Checkpoint 2: After Implementation
- [ ] Code review completed
- [ ] Tests written
- [ ] Patterns validated

### Checkpoint 3: Before Commit
- [ ] Security review passed
- [ ] All tests pass
- [ ] Documentation updated

### Checkpoint 4: Before Push
- [ ] PR description complete
- [ ] CI checks configured
- [ ] Ready for human review
