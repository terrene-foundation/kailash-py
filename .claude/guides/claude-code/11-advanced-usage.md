# Guide 11: Advanced Usage

## Introduction

This guide covers **power user features** for those who want deeper control over the setup. These techniques go beyond daily workflows into customization, optimization, and expert-level usage.

By the end of this guide, you will know how to:
- Explicitly control agent delegation
- Chain multiple agents for complex tasks
- Customize hooks and rules
- Optimize context usage
- Extend the setup with new components

---

## Part 1: Explicit Agent Control

### Requesting Specific Agents

Instead of relying on automatic delegation, request specific agents:

```
> Use the deep-analyst to evaluate the architectural risks of adding real-time notifications
```

```
> Use the dataflow-specialist to review my model design for potential performance issues
```

```
> Use the security-reviewer to audit only the authentication module
```

### Chaining Agents Manually

For complex analysis, chain agents in sequence:

```
> For this feature, I want you to:
> 1. Use deep-analyst for risk assessment
> 2. Use requirements-analyst for breakdown
> 3. Use framework-advisor for technology selection
> 4. Use the appropriate specialist for implementation guidance
```

### Parallel Agent Execution

Request parallel agent work for independent tasks:

```
> In parallel:
> - Use testing-specialist to review test coverage
> - Use security-reviewer to audit security
> - Use intermediate-reviewer to check code quality
```

Claude launches all three agents simultaneously.

### Agent Bypass (Use Carefully)

Skip automatic delegation when you know best:

```
> Skip the deep-analyst, I've already analyzed this. Just implement:
> [Your implementation details]
```

Note: Bypassing agents removes safety checks.

---

## Part 2: Advanced Context Management

### Selective Skill Loading

Load only what you need:

```
> /db

# Now Claude has DataFlow context
# Other contexts not loaded
```

### Unloading Context

Clear context when switching domains:

```
> /clear

# Context cleared, starting fresh
```

### Context Stacking

Layer contexts for complex tasks:

```
> /sdk
> /db
> /test

# Claude now has Core SDK + DataFlow + Testing
# Use for implementing tested DataFlow features
```

### Minimal Context Mode

For simple tasks, avoid loading heavy context:

```
> Just fix this typo, don't load any extra context

[Claude fixes without loading skills]
```

---

## Part 3: Hook Customization

### Adding a Custom Hook

Create a new hook script:

```javascript
// scripts/hooks/my-custom-hook.js
#!/usr/bin/env node

const fs = require('fs');

let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  const data = JSON.parse(input);

  // Your custom validation
  if (data.tool_input?.file_path?.includes('.env')) {
    console.log(JSON.stringify({
      continue: false,
      hookSpecificOutput: {
        message: 'Blocked: Cannot edit .env files'
      }
    }));
    process.exit(2);
  }

  console.log(JSON.stringify({ continue: true }));
  process.exit(0);
});
```

Register in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "scripts/hooks/my-custom-hook.js",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### Disabling a Hook Temporarily

Edit `.claude/settings.json` and comment out the hook (JSON doesn't support comments, so remove the entry temporarily).

### Hook Debugging

Add logging to hooks:

```javascript
console.error(`[DEBUG] Input: ${JSON.stringify(data)}`);
```

Check stderr for debug output.

---

## Part 4: Rule Customization

### Adding Project-Specific Rules

Create a new rule file:

```markdown
# .claude/rules/project-specific.md

## MUST Rules

### Always Use Project Logger
All logging MUST use the project's custom logger:

```python
# Correct
from myproject.logger import log
log.info("Message")

# Incorrect
print("Message")  # NO
import logging    # Use project logger instead
```
```

### Rule Priority Override

When rules conflict, specify priority in the rule file:

```markdown
## Priority
This rule takes precedence over patterns.md for logging concerns.
```

### Temporary Rule Exceptions

Document exceptions in your request:

```
> I need to use print statements for debugging. This is a temporary exception to the logging rule. I'll remove them before commit.
```

---

## Part 5: Custom Skills

### Creating a New Skill

Create a skill directory:

```
.claude/skills/99-my-custom-skill/
├── SKILL.md
├── pattern-1.md
└── pattern-2.md
```

Write the SKILL.md:

```markdown
---
name: my-custom-skill
description: "Custom patterns for [your domain]. Use when [trigger conditions]."
---

# My Custom Skill

## Quick Patterns

[Your most common patterns]

## Reference Documentation

- **[pattern-1](pattern-1.md)** - Description

## When to Use

- [Use case 1]
- [Use case 2]

## Support

For help, invoke:
- `pattern-expert` - General patterns
```

### Linking Skills to Commands

Create a command:

```markdown
# .claude/commands/mycmd.md

---
name: mycmd
description: "Load my custom patterns"
---

# My Custom Quick Reference

Load the 99-my-custom-skill skill for [domain] patterns.

## Quick Patterns

[Subset of patterns]

## Usage Examples

```
/mycmd
```
Then ask about [domain] features.
```

---

## Part 6: Custom Agents

### Creating a Specialist Agent

```markdown
# .claude/agents/my-specialist.md

---
name: my-specialist
description: Short description under 120 chars. Use for [trigger].
tools: Read, Write, Edit, Bash, Grep, Glob
model: opus
---

# My Specialist

You are a specialist in [domain].

## Responsibilities

1. [Primary responsibility]
2. [Secondary responsibility]

## Rules

1. [Critical rule]
2. [Important guideline]

## Process

1. [Step 1]
2. [Step 2]
3. [Verification]

## Skill References

- **[my-custom-skill](../skills/99-my-custom-skill/SKILL.md)**

## Related Agents

- **pattern-expert**: Hand off for general patterns
```

### Agent Invocation

After creating, use:

```
> Use the my-specialist to help with [task]
```

---

## Part 7: Optimization Techniques

### Reduce Token Usage

**Do:**
```
> /db
> Create user model
```

**Don't:**
```
> I want to create a database model for users with all the DataFlow patterns
> and I want to make sure it follows all the best practices...
[Loads unnecessary context]
```

### Batch Operations

**Do:**
```
> Fix all the lint errors in src/
```

**Don't:**
```
> Fix the lint error in src/file1.py
> Fix the lint error in src/file2.py
> Fix the lint error in src/file3.py
[Multiple roundtrips]
```

### Parallel Reads

**Do:**
```
> Read src/models/user.py, src/models/product.py, and src/models/order.py
```

Claude reads all three in parallel.

### Cache Awareness

After reading a file once, Claude remembers it for the session:

```
> Read src/config.py

[File read]

> What's the DATABASE_URL in that config?

[Claude answers from memory, no re-read needed]
```

---

## Part 8: Multi-Project Setup

### Project-Specific Overrides

Each project can have its own `.claude/` directory:

```
~/projects/
├── project-a/
│   └── .claude/
│       └── rules/         # Project A specific rules
│           └── custom.md
├── project-b/
│   └── .claude/
│       └── skills/        # Project B specific skills
│           └── 99-b-specific/
```

### Shared Base Setup

For shared setup across projects, use symlinks:

```bash
# In each project
ln -s ~/shared-claude-setup/.claude/skills .claude/skills
```

### Environment Detection

The session-start hook detects frameworks:

```javascript
// scripts/hooks/session-start.js
const hasDataFlow = fs.existsSync('dataflow.py') || hasImport('dataflow');
const hasNexus = fs.existsSync('nexus.py') || hasImport('nexus');
```

Customize for your projects.

---

## Part 9: Advanced Learning

### Manual Instinct Creation

Create instincts directly:

```json
// ~/.claude/kailash-learning/instincts/personal/my-instinct.json
{
  "id": "instinct_my_pattern",
  "pattern": "my_special_pattern",
  "description": "Always do X when Y",
  "confidence": 0.95,
  "evidence": {
    "observation_count": 100,
    "success_rate": 0.98,
    "manual": true
  }
}
```

### Inherited Instincts

Share instincts across team:

```bash
# Export
cp ~/.claude/kailash-learning/instincts/personal/*.json ./team-instincts/

# Import (other team member)
cp ./team-instincts/*.json ~/.claude/kailash-learning/instincts/inherited/
```

### Evolution Tuning

Adjust thresholds:

```bash
node scripts/learning/instinct-evolver.js --skill-threshold 0.80 --command-threshold 0.85
```

---

## Part 10: Integration with External Tools

### IDE Integration

Claude Code can run from VS Code terminal:

```
# In VS Code integrated terminal
claude
```

### CI/CD Integration

Use Claude Code in CI for code review:

```yaml
# .github/workflows/review.yml
- name: Claude Review
  run: |
    echo "Review the changes in this PR" | claude --non-interactive
```

### Pre-Commit Hooks

Integrate with git pre-commit:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: claude-security
        name: Claude Security Review
        entry: scripts/claude-security-check.sh
        language: script
```

---

## Part 11: Key Takeaways

### Summary

1. **Explicit agent control** - Request specific agents when needed

2. **Context management** - Load selectively, clear when switching

3. **Customization** - Add hooks, rules, skills, agents

4. **Optimization** - Reduce tokens, batch operations, parallel reads

5. **Multi-project** - Per-project overrides with shared base

6. **Advanced learning** - Manual instincts, team sharing

### Power User Checklist

- [ ] Created at least one custom hook
- [ ] Added project-specific rules
- [ ] Built a custom skill for your domain
- [ ] Optimized context loading patterns
- [ ] Set up learning checkpoints
- [ ] Integrated with CI/CD

---

## What's Next?

When things go wrong, the troubleshooting guide helps you diagnose and fix issues.

**Next: [12 - Troubleshooting](12-troubleshooting.md)**

---

## Navigation

- **Previous**: [10 - Daily Workflows](10-daily-workflows.md)
- **Next**: [12 - Troubleshooting](12-troubleshooting.md)
- **Home**: [README.md](README.md)
