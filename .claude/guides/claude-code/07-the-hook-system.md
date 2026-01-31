# Guide 07: The Hook System

## Introduction

Hooks are **automatic enforcement scripts** that run at specific points in Claude's tool usage. Unlike skills (knowledge) or agents (judgment), hooks provide **deterministic enforcement** that doesn't require AI decision-making.

By the end of this guide, you will understand:
- What hooks are and why they exist
- Every hook event type and when it fires
- All configured hooks and what they do
- How hooks block, warn, or transform
- How to interpret hook messages

---

## Part 1: What Are Hooks?

### The Problem Hooks Solve

Some quality controls shouldn't depend on AI judgment:

| Control | Without Hooks | With Hooks |
|---------|---------------|------------|
| Block `rm -rf /` | Claude might forget | Always blocked |
| Format code after edit | Claude might skip | Always formatted |
| Log session data | Claude might omit | Always logged |
| Check for secrets | Claude might miss | Always checked |

### The Solution: Deterministic Automation

Hooks run **automatically** at specific events:

```
┌──────────────────────────────────────────────────────────────┐
│                     CLAUDE ACTION                             │
│                  "Run rm -rf /tmp/*"                          │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    PRE-TOOL-USE HOOK                          │
│                                                               │
│   validate-bash-command.js runs BEFORE tool executes          │
│                                                               │
│   Checks: Is this command dangerous?                          │
│   Result: Not matched as dangerous → Continue                 │
│                                                               │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     TOOL EXECUTES                             │
│                  Command runs successfully                    │
└──────────────────────────────────────────────────────────────┘
```

### Hooks vs. Other Components

| Aspect | Hooks | Rules | Agents |
|--------|-------|-------|--------|
| **Execution** | Automatic | Claude reads | Claude delegates |
| **Judgment** | None (deterministic) | Requires interpretation | Deep analysis |
| **Speed** | Milliseconds | Depends on context | Seconds |
| **Blocking** | Can block actions | Cannot block | Cannot block |
| **Token Usage** | Zero | Minimal | Significant |

---

## Part 2: Hook Event Types

### When Hooks Fire

Claude Code supports six hook events:

```
SESSION LIFECYCLE
─────────────────────────────────────────────────────────────
    SessionStart                                SessionEnd
         │                                           │
         ▼                                           ▼
    ┌─────────┐                                 ┌─────────┐
    │ Session │◄──────── Work happens ─────────►│ Session │
    │ begins  │                                 │  ends   │
    └─────────┘                                 └─────────┘

TOOL LIFECYCLE (repeats for each tool use)
─────────────────────────────────────────────────────────────
    PreToolUse                                 PostToolUse
         │                                           │
         ▼                                           ▼
    ┌─────────┐      ┌──────────────┐         ┌─────────┐
    │ Before  │─────►│ Tool Executes │────────►│  After  │
    │  tool   │      └──────────────┘         │  tool   │
    └─────────┘                               └─────────┘

CONTEXT MANAGEMENT
─────────────────────────────────────────────────────────────
    PreCompact                                    Stop
         │                                           │
         ▼                                           ▼
    ┌─────────┐                                 ┌─────────┐
    │ Before  │                                 │ Session │
    │ cleanup │                                 │ stopped │
    └─────────┘                                 └─────────┘
```

### Event Details

| Event | When It Fires | Common Uses |
|-------|---------------|-------------|
| **SessionStart** | Claude Code starts | Load context, check environment |
| **SessionEnd** | Claude Code exits normally | Save state, cleanup |
| **PreToolUse** | Before any tool runs | Block dangerous commands, validate input |
| **PostToolUse** | After any tool runs | Format code, validate output |
| **PreCompact** | Before context cleanup | Save important state |
| **Stop** | Session terminated | Emergency cleanup |

---

## Part 3: Configured Hooks

### Hook Configuration File

Hooks are configured in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [...],
    "PostToolUse": [...],
    "SessionStart": [...],
    "SessionEnd": [...],
    "PreCompact": [...],
    "Stop": [...]
  }
}
```

### Current Hook Configuration

```
PreToolUse
├── validate-bash-command.js
│   ├── Matcher: Bash tool only
│   ├── Timeout: 10 seconds
│   └── Purpose: Block dangerous commands

PostToolUse
├── validate-workflow.js
│   ├── Matcher: Edit or Write tools
│   ├── Timeout: 15 seconds
│   └── Purpose: Check SDK patterns
│
└── auto-format.js
    ├── Matcher: Edit or Write tools
    ├── Timeout: 30 seconds
    └── Purpose: Format code

SessionStart
└── session-start.js
    └── Purpose: Initialize session context

SessionEnd
└── session-end.js
    └── Purpose: Persist session state

PreCompact
└── pre-compact.js
    └── Purpose: Save state before cleanup

Stop
└── stop.js
    ├── Timeout: 5 seconds
    └── Purpose: Handle termination
```

---

## Part 4: Individual Hook Details

### validate-bash-command.js

**Event**: PreToolUse (Bash only)
**Purpose**: Block dangerous commands, warn about risky operations

**What it blocks (exit code 2)**:
```
❌ rm -rf /           → "Blocked: rm -rf / (system destruction)"
❌ > /dev/sda         → "Blocked: Writing to block device"
❌ mkfs.ext4 ...      → "Blocked: Filesystem formatting"
❌ dd if=... of=/dev  → "Blocked: dd to disk"
❌ :(){ :|:& };:      → "Blocked: Fork bomb"
❌ chmod -R 777 /     → "Blocked: chmod 777 on root"
```

**What it warns about (exit code 0 with message)**:
```
⚠️ curl ... | sh     → "WARNING: Piping curl to shell is dangerous"
⚠️ npm run dev       → "WARNING: Long-running command. Use run_in_background."
⚠️ docker compose up → "WARNING: Long-running command..."
⚠️ git push          → "REMINDER: Did you run security-reviewer before pushing?"
⚠️ git commit        → "REMINDER: Code review completed?"
```

### validate-workflow.js

**Event**: PostToolUse (Edit or Write)
**Purpose**: Check SDK pattern compliance

**What it checks**:
```
✓ workflow.build() called before execute
✓ Absolute imports used (not relative)
✓ Primary key named 'id' in DataFlow models
✓ No manual timestamp setting
✓ Correct runtime.execute() pattern
```

**Example warning**:
```
WARNING: Using relative import '../workflow'. Use absolute import instead.
WARNING: Detected workflow.execute(runtime). Use runtime.execute(workflow.build()).
```

### auto-format.js

**Event**: PostToolUse (Edit or Write)
**Purpose**: Automatically format code

**What it does**:
```
Python files  → black formatting
JavaScript    → prettier (if configured)
TypeScript    → prettier (if configured)
JSON          → json formatting
```

### session-start.js

**Event**: SessionStart
**Purpose**: Initialize session context

**What it does**:
1. Detects active frameworks (DataFlow, Nexus, Kaizen)
2. Checks environment setup (.env files, dependencies)
3. Logs session start observation
4. Sets up session state

### session-end.js

**Event**: SessionEnd
**Purpose**: Persist session state

**What it does**:
1. Saves session observations
2. Persists learning state
3. Cleanup temporary resources
4. Log session end

### pre-compact.js

**Event**: PreCompact
**Purpose**: Save state before context cleanup

**What it does**:
1. Saves important observations
2. Checkpoints learning state
3. Preserves critical context

### stop.js

**Event**: Stop
**Purpose**: Handle session termination

**What it does**:
1. Emergency state save
2. Resource cleanup
3. Graceful shutdown

---

## Part 5: Hook Input/Output Format

### Hook Input

Hooks receive JSON input via stdin:

```json
{
  "session_id": "abc123",
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm run dev"
  },
  "cwd": "/path/to/project"
}
```

### Hook Output

Hooks output JSON to stdout:

```json
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "validation": "Validated"
  }
}
```

### Exit Codes

| Exit Code | Meaning | Effect |
|-----------|---------|--------|
| 0 | Success | Continue execution |
| 2 | Blocking error | Stop tool execution |
| Other | Non-blocking error | Warn and continue |

---

## Part 6: How Hooks Affect Your Workflow

### Transparent Enforcement

Most of the time, you won't notice hooks running:

```
You: "Create a Python file for user model"
Claude: [Uses Write tool]
         ↓
    [validate-workflow.js checks patterns]
    [auto-format.js formats code]
         ↓
    "Created user_model.py with DataFlow model"
```

### When Hooks Block

When a hook blocks, you'll see a clear message:

```
You: "Run rm -rf /"
Claude: [Tries Bash tool]
         ↓
    [validate-bash-command.js BLOCKS]
         ↓
    "I cannot execute that command. The hook blocked it because:
     Blocked: rm -rf / (system destruction)"
```

### When Hooks Warn

Warnings appear in Claude's context:

```
You: "Commit this code"
Claude: [Uses git commit]
         ↓
    [validate-bash-command.js warns]
         ↓
    "Committed. Note: The validation hook reminds us to ensure
     code review was completed before committing."
```

---

## Part 7: Understanding Hook Messages

### Message Types

| Prefix | Meaning | Action Needed |
|--------|---------|---------------|
| **Blocked** | Action prevented | Request was stopped |
| **WARNING** | Risky operation | Proceed with caution |
| **REMINDER** | Best practice hint | Consider the suggestion |
| **Validated** | All checks passed | No action needed |

### Common Messages You'll See

```
Blocked: rm -rf / (system destruction)
└── Your command was blocked for safety

WARNING: Long-running command. Consider using run_in_background or tmux.
└── Consider running in background

REMINDER: Did you run security-reviewer before pushing?
└── Consider security review

WARNING: Using relative import. Use absolute import instead.
└── Fix your import statement

Validated
└── All checks passed
```

---

## Part 8: Hook Timeouts

### Why Timeouts Matter

Hooks must complete quickly or they'll block Claude:

| Hook | Timeout | Why |
|------|---------|-----|
| `validate-bash-command.js` | 10s | Pre-execution must be fast |
| `validate-workflow.js` | 15s | File analysis takes longer |
| `auto-format.js` | 30s | Formatting large files |
| `stop.js` | 5s | Emergency cleanup |

### Timeout Handling

If a hook times out:

```javascript
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.error('[HOOK TIMEOUT] Hook exceeded time limit');
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);
```

The session continues, but a warning is logged.

---

## Part 9: Writing Custom Hooks

### Hook Script Template

```javascript
#!/usr/bin/env node
/**
 * Hook: my-custom-hook
 * Event: PreToolUse|PostToolUse|SessionStart|etc.
 * Matcher: ToolName (for Pre/PostToolUse)
 * Purpose: What this hook does
 */

const fs = require('fs');

// Timeout handling
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.error('[HOOK TIMEOUT] my-custom-hook exceeded limit');
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

// Read input
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  clearTimeout(timeout);
  try {
    const data = JSON.parse(input);
    const result = processHook(data);
    console.log(JSON.stringify({
      continue: result.continue,
      hookSpecificOutput: {
        hookEventName: process.env.HOOK_EVENT_NAME,
        message: result.message
      }
    }));
    process.exit(result.exitCode);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

function processHook(data) {
  // Your hook logic here
  return { continue: true, exitCode: 0, message: 'Validated' };
}
```

### Adding to Configuration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "scripts/hooks/my-custom-hook.js",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

---

## Part 10: Key Takeaways

### Summary

1. **Hooks enforce rules automatically** - No AI judgment required

2. **Six event types** - SessionStart, SessionEnd, PreToolUse, PostToolUse, PreCompact, Stop

3. **Eight hooks configured** - For validation, formatting, and lifecycle management

4. **Exit codes matter** - 0 = continue, 2 = block, other = warn

5. **Timeouts prevent hangs** - Each hook has a time limit

6. **Messages inform you** - Blocked, WARNING, REMINDER, Validated

### Quick Reference

| Hook | Event | Purpose |
|------|-------|---------|
| `validate-bash-command.js` | PreToolUse | Block dangerous commands |
| `validate-workflow.js` | PostToolUse | Check SDK patterns |
| `auto-format.js` | PostToolUse | Format code |
| `session-start.js` | SessionStart | Initialize session |
| `session-end.js` | SessionEnd | Save state |
| `pre-compact.js` | PreCompact | Save before cleanup |
| `stop.js` | Stop | Handle termination |

---

## What's Next?

Hooks enforce patterns, but where do the rules come from? The next guide explains the rule system.

**Next: [08 - The Rule System](08-the-rule-system.md)**

---

## Navigation

- **Previous**: [06 - The Skill System](06-the-skill-system.md)
- **Next**: [08 - The Rule System](08-the-rule-system.md)
- **Home**: [README.md](README.md)
