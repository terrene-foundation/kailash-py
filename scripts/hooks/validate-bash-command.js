#!/usr/bin/env node
/**
 * Hook: validate-bash-command
 * Event: PreToolUse
 * Matcher: Bash
 * Purpose: Block dangerous commands, suggest tmux for long-running
 *
 * Exit Codes:
 *   0 = success (continue)
 *   2 = blocking error (stop tool execution)
 *   other = non-blocking error (warn and continue)
 */

const fs = require('fs');

// Timeout handling for PreToolUse hooks (5 second limit)
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.error('[HOOK TIMEOUT] validate-bash-command exceeded 5s limit');
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  clearTimeout(timeout);
  try {
    const data = JSON.parse(input);
    const result = validateBashCommand(data);
    console.log(JSON.stringify({
      continue: result.continue,
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        validation: result.message
      }
    }));
    process.exit(result.exitCode);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

function validateBashCommand(data) {
  const command = data.tool_input?.command || '';

  // BLOCK: Dangerous commands
  const dangerousPatterns = [
    { pattern: /rm\s+-rf\s+\/(?!\w)/, message: 'Blocked: rm -rf / (system destruction)' },
    { pattern: />\s*\/dev\/sd/, message: 'Blocked: Writing to block device' },
    { pattern: /mkfs\./, message: 'Blocked: Filesystem formatting' },
    { pattern: /dd\s+if=.*of=\/dev\/sd/, message: 'Blocked: dd to disk' },
    { pattern: /:\(\)\{\s*:\|:&\s*\};:/, message: 'Blocked: Fork bomb' },
    { pattern: /chmod\s+-R\s+777\s+\//, message: 'Blocked: chmod 777 on root' },
    { pattern: /curl.*\|\s*(ba)?sh/, message: 'WARNING: Piping curl to shell is dangerous' },
  ];

  for (const { pattern, message } of dangerousPatterns) {
    if (pattern.test(command)) {
      if (message.startsWith('Blocked')) {
        return { continue: false, exitCode: 2, message };
      }
      return { continue: true, exitCode: 0, message };
    }
  }

  // WARN: Long-running commands outside tmux/background
  const longRunningPatterns = [
    /npm\s+run\s+(dev|start|serve)/,
    /yarn\s+(dev|start|serve)/,
    /python\s+-m\s+http\.server/,
    /uvicorn/,
    /flask\s+run/,
    /node\s+.*server/,
    /docker\s+compose\s+up(?!\s+-d)/,
  ];

  const inTmux = process.env.TMUX || process.env.TERM_PROGRAM === 'tmux';
  const isBackground = /&\s*$/.test(command) || /--background/.test(command) || /-d\s/.test(command);

  for (const pattern of longRunningPatterns) {
    if (pattern.test(command) && !inTmux && !isBackground) {
      return {
        continue: true,
        exitCode: 0,
        message: 'WARNING: Long-running command. Consider using run_in_background or tmux.'
      };
    }
  }

  // WARN: Git push - reminder for security review
  if (/git\s+push/.test(command)) {
    return {
      continue: true,
      exitCode: 0,
      message: 'REMINDER: Did you run security-reviewer before pushing?'
    };
  }

  // WARN: Git commit - reminder for review
  if (/git\s+commit/.test(command)) {
    return {
      continue: true,
      exitCode: 0,
      message: 'REMINDER: Code review completed? Consider delegating to intermediate-reviewer.'
    };
  }

  return { continue: true, exitCode: 0, message: 'Validated' };
}
