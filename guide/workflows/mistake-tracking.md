# Mistake Tracking Guide

This guide explains how to track, analyze, and learn from mistakes during development.

## Why Track Mistakes?

1. **Prevent Recurrence**: Document solutions to avoid repeating errors
2. **Improve Documentation**: Update guides based on real issues
3. **Build Knowledge**: Create a searchable database of solutions
4. **Help Future Developers**: Share learnings with the team

## Tracking Process

### 1. Create Session Mistake File

At the start of Phase 2 (Implementation), create:
```bash
touch guide/sessions/current-mistakes.md
```

Use this template:
```markdown
# Current Session Mistakes - [Date]

## Session Context
- Task: [What you're working on]
- Phase: Implementation & Learning
- Start Time: [Timestamp]

## Mistakes Log

### Mistake 1: [Descriptive Title]
- **Time**: [When it occurred]
- **What happened**: [Describe the error/issue]
- **Error message**:
  ```
  [Paste actual error]
  ```
- **Root cause**: [Why it happened]
- **Solution**: [How you fixed it]
- **Prevention**: [How to avoid in future]
- **Docs to update**:
  - [ ] guide/mistakes/000-master.md
  - [ ] guide/reference/[relevant-doc].md
  - [ ] guide/features/[relevant-feature].md

### Mistake 2: [Title]
[Same structure...]
```

### 2. Log Mistakes in Real-Time

As you encounter issues:
1. **Don't fix and forget** - Document immediately
2. **Include full context** - Error messages, code snippets
3. **Note your debugging process** - What you tried
4. **Document the solution** - What actually worked

### 3. Categories of Mistakes to Track

#### API/Integration Issues
- Wrong method names or signatures
- Incorrect parameter passing
- Missing imports

#### Node Implementation Issues
- Config vs runtime parameter confusion
- Missing required methods
- Async/sync mismatches

#### Workflow Issues
- Connection problems
- Validation errors
- Cycle-related issues

#### Testing Issues
- Flaky tests
- Mock configuration
- Assertion problems

#### Documentation Issues
- Outdated examples
- Missing information
- Incorrect instructions

## Analysis Process (Phase 3)

### 1. Review All Mistakes
Open `guide/sessions/current-mistakes.md` and:
- Count total mistakes
- Group by category
- Identify patterns

### 2. Pattern Recognition
Look for:
- **Repeated mistakes**: Same issue multiple times
- **Related mistakes**: Different symptoms, same root cause
- **Category clusters**: Many issues in one area

### 3. Root Cause Analysis
For each pattern, determine:
- **Why it keeps happening**: Missing docs? Confusing API?
- **Impact level**: How much time lost?
- **Prevention strategy**: What would stop this?

### 4. Create Update Plan
List all documentation updates needed:
```markdown
## Documentation Update Plan

### High Priority (Frequent/Critical)
1. Update guide/reference/validation-guide.md
   - Add section on [specific issue]
   - Include examples of correct usage

2. Update guide/mistakes/consolidated-guide.md
   - Add to "Common Pitfalls" section
   - Include quick fix

### Medium Priority (Occasional)
1. Update guide/features/[feature].md
   - Clarify [confusing section]
   - Add troubleshooting guide

### Low Priority (Rare/Minor)
1. Update examples/
   - Fix outdated example
   - Add comment explaining pitfall
```

## Documentation Updates (Phase 4)

### 1. Create Individual Mistake File
Create a new file `guide/mistakes/NNN-short-description.md`:
- Use next sequential number (check README.md)
- Follow the template in `0000-template.md`
- Include all sections: Problem, Symptoms, Example, etc.

Example: `062-state-mutation-error.md`

### 2. Update Mistakes Registry
Add entry to `guide/mistakes/README.md`:
- Add to appropriate category section
- Update error message quick reference if applicable
- If it's a very common pattern, consider adding to "Common Fixes" section
- Increment statistics if needed

### 3. Update Feature Documentation
Enhance relevant guides in `guide/features/`:
- Add "Common Issues" sections
- Include troubleshooting guides
- Update examples with warnings
- Link to the new mistake file

## Best Practices

### DO:
- ✅ Log mistakes immediately
- ✅ Include full error messages
- ✅ Document your thought process
- ✅ Test solutions thoroughly
- ✅ Update docs in same session

### DON'T:
- ❌ Don't wait to document
- ❌ Don't skip "minor" issues
- ❌ Don't assume you'll remember
- ❌ Don't fix without understanding
- ❌ Don't update docs without examples

## Example Mistake Entry

```markdown
### Mistake 12: AsyncNode not used for MCP client
- **Time**: 14:32
- **What happened**: Created MCP client node inheriting from Node instead of AsyncNode
- **Error message**:
  ```
  RuntimeError: unhandled errors in a TaskGroup
  ```
- **Root cause**: LocalRuntime expects async_run() for async operations, but Node doesn't support it
- **Solution**: Changed to inherit from AsyncNode and implemented async_run() instead of run()
- **Prevention**: Always use AsyncNode for any node doing async operations (MCP, API calls, etc.)
- **Docs to update**:
  - [x] guide/mistakes/000-master.md - Added as issue #57
  - [x] guide/features/mcp_ecosystem.md - Added async pattern section
  - [x] guide/reference/node-catalog.md - Noted async requirement
```

## Session Cleanup

After Phase 4:
1. Archive session file: `mv current-mistakes.md session-[date]-mistakes.md`
2. Create summary in `guide/sessions/session-[date]-summary.md`
3. Clear for next session

## Quick Reference Card

```
Mistake Detected
       ↓
Log in current-mistakes.md
       ↓
Continue Implementation
       ↓
Phase 3: Analyze Patterns
       ↓
Phase 4: Update Docs
       ↓
Better SDK for Everyone!
```
