#!/usr/bin/env node
/**
 * Hook: validate-workflow
 * Event: PostToolUse
 * Matcher: Edit|Write
 * Purpose: Enforce Kailash SDK patterns in Python files
 *
 * Exit Codes:
 *   0 = success (continue)
 *   2 = blocking error (stop tool execution)
 *   other = non-blocking error (warn and continue)
 */

const fs = require('fs');
const path = require('path');

// Timeout handling for PostToolUse hooks (5 second limit)
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.error('[HOOK TIMEOUT] validate-workflow exceeded 5s limit');
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
    const result = validateWorkflowPatterns(data);
    console.log(JSON.stringify({
      continue: result.continue,
      hookSpecificOutput: {
        hookEventName: 'PostToolUse',
        validation: result.messages
      }
    }));
    process.exit(result.exitCode);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

function validateWorkflowPatterns(data) {
  const filePath = data.tool_input?.file_path || '';
  const messages = [];

  // Only check Python files
  if (!filePath.endsWith('.py')) {
    return { continue: true, exitCode: 0, messages: ['Not a Python file'] };
  }

  let content;
  try {
    content = fs.readFileSync(filePath, 'utf8');
  } catch (e) {
    return { continue: true, exitCode: 0, messages: ['Could not read file'] };
  }

  // Check 1: Anti-pattern workflow.execute(runtime)
  if (/workflow\s*\.\s*execute\s*\(\s*runtime/.test(content)) {
    messages.push('WARNING: Found workflow.execute(runtime). Use runtime.execute(workflow.build()) instead.');
  }

  // Check 2: Missing .build() call
  if (/runtime\s*\.\s*execute\s*\(\s*workflow\s*[^.]/.test(content)) {
    messages.push('WARNING: Missing .build() call. Use runtime.execute(workflow.build())');
  }

  // Check 3: Relative imports in kailash code
  if (/from\s+['"]\./.test(content) && /kailash|dataflow|nexus|kaizen/.test(filePath.toLowerCase())) {
    messages.push('WARNING: Relative imports detected. Use absolute imports for Kailash code.');
  }

  // Check 4: Mocking in test files (NO MOCKING in Tier 2-3)
  if (/_test\.py$|test_.*\.py$/.test(filePath)) {
    const mockPatterns = [
      { pattern: /@patch\(/, name: '@patch decorator' },
      { pattern: /MagicMock/, name: 'MagicMock' },
      { pattern: /unittest\.mock/, name: 'unittest.mock' },
      { pattern: /from\s+mock\s+import/, name: 'mock import' },
      { pattern: /\.mock\s*=/, name: 'mock assignment' },
    ];

    for (const { pattern, name } of mockPatterns) {
      if (pattern.test(content)) {
        messages.push(`WARNING: ${name} detected. Remember: NO MOCKING in Tier 2-3 tests.`);
      }
    }
  }

  // Check 5: DataFlow primary key naming
  if (/@db\.model/.test(content) || /class.*Model/.test(content)) {
    // Check if there's a primary key that's not named 'id'
    if (/primary_key\s*=\s*True/.test(content) && !/id\s*[:=]/.test(content)) {
      messages.push('WARNING: DataFlow models should have primary key named "id".');
    }
  }

  // Check 6: Environment variable loading
  if (/kailash/.test(filePath.toLowerCase()) && !/load_dotenv/.test(content) && /os\.environ/.test(content)) {
    messages.push('WARNING: Using os.environ without load_dotenv(). Add "from dotenv import load_dotenv; load_dotenv()"');
  }

  return {
    continue: true, // Always continue, just warn
    exitCode: 0,
    messages: messages.length > 0 ? messages : ['All Kailash patterns validated']
  };
}
