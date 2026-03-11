# Kaizen v1.0.0-beta.1 Feedback Guide

Thank you for participating in the Kaizen v1.0.0-beta.1 beta program! Your feedback is invaluable in shaping the final release.

## How to Provide Feedback

### Option 1: GitHub Issues (Preferred)
Use our structured issue templates:
- [Beta Feedback](https://github.com/terrene-foundation/kailash-py/issues/new?template=beta-feedback.yml)
- [Bug Report](https://github.com/terrene-foundation/kailash-py/issues/new?template=bug-report.yml)

### Option 2: Structured Feedback Form
Copy and fill out this template, then submit as a GitHub issue:

```markdown
## Beta Feedback: [Your Title]

### Feedback Type
- [ ] Bug Report
- [ ] Feature Request
- [ ] Performance Issue
- [ ] Documentation Issue
- [ ] API Usability
- [ ] Integration Issue

### Component
- [ ] Unified Agent API
- [ ] Native Tools (file, bash, search)
- [ ] Claude Code Parity Tools (todo, planning, process)
- [ ] Runtime Adapters
- [ ] Memory System
- [ ] Multi-LLM Routing
- [ ] Specialist System
- [ ] Streaming
- [ ] Other: ___________

### Description
[Detailed description of your feedback]

### Code Sample (if applicable)
```python
# Your code here
```

### Environment
- Kaizen Version: 1.0.0b1
- Python Version:
- OS:
- LLM Provider:

### Impact/Severity
- [ ] Critical - Blocks usage entirely
- [ ] High - Major functionality affected
- [ ] Medium - Some functionality affected
- [ ] Low - Minor inconvenience
- [ ] Enhancement - Nice to have
```

## What We're Looking For

### 1. Unified Agent API Feedback
- Is the progressive configuration intuitive?
- Are the capability presets useful?
- Is the 2-line quickstart working smoothly?

```python
from kaizen import Agent

# We want to know: Is this intuitive?
agent = Agent()
result = await agent.run("your task")
```

### 2. Native Tools Feedback
- Are the 19 native tools sufficient for your use case?
- Any tools you're missing?
- Performance issues?

### 3. Claude Code Parity
- Do the new tools (TodoWrite, NotebookEdit, AskUserQuestion, etc.) work as expected?
- Any differences from Claude Code behavior you've noticed?

### 4. Runtime and Memory
- Is LocalKaizenAdapter's TAOD loop working correctly?
- Are memory providers functioning as expected?

### 5. Multi-LLM Routing
- Is LLM routing behaving as expected?
- Any issues with provider fallback?

## Priority Areas

For this beta, we're especially interested in:

1. **Breaking Issues**: Anything that prevents basic usage
2. **API Usability**: Confusing or unintuitive APIs
3. **Performance**: Slowdowns or memory issues
4. **Missing Features**: Critical gaps in functionality
5. **Documentation**: Missing or unclear documentation

## Known Limitations

### Python Version
- Requires Python 3.11+
- Python 3.13 not yet tested

### Optional Dependencies
- `[azure]` optional dependency updated for security
- Token counting requires `[tokens]` extra

## Beta Timeline

| Phase | Date | Focus |
|-------|------|-------|
| Beta Start | 2026-01-24 | Initial release |
| Feedback Collection | 2026-01-24 to 2026-02-07 | 2 weeks |
| Bug Fixes | 2026-02-07 to 2026-02-21 | Address critical issues |
| RC1 | 2026-02-21 | Release candidate |
| GA | 2026-03-01 | Final release |

## Contact

- **GitHub Issues**: https://github.com/terrene-foundation/kailash-py/issues
- **Discussions**: https://github.com/terrene-foundation/kailash-py/discussions
- **Documentation**: https://docs.kailash.com/kaizen

Thank you for helping make Kaizen better!
