#!/usr/bin/env node
/**
 * Hooks Validation Script for CI
 *
 * Validates all hook scripts meet quality standards:
 * - Uses correct exit codes (0=continue, 2=block)
 * - Handles JSON input/output
 * - Has timeout handling
 * - No external dependencies beyond Node.js stdlib
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const HOOKS_DIR = path.join(process.cwd(), 'scripts', 'hooks');
const SETTINGS_PATH = path.join(process.cwd(), '.claude', 'settings.json');

/**
 * Validate single hook script
 */
function validateHookScript(filePath) {
  const errors = [];
  const warnings = [];
  const fileName = path.basename(filePath);

  try {
    const content = fs.readFileSync(filePath, 'utf8');

    // Check shebang
    if (!content.startsWith('#!/usr/bin/env node')) {
      warnings.push('Missing or non-standard shebang');
    }

    // Check for JSON handling
    if (!content.includes('JSON.parse') && !content.includes('JSON.stringify')) {
      warnings.push('No JSON parsing/serialization found');
    }

    // Check for exit codes - detect both literal and dynamic patterns
    const hasExitCodes =
      content.includes('process.exit(0)') ||
      content.includes('process.exit(2)') ||
      content.includes('process.exit(1)') ||
      /process\.exit\s*\(\s*\w+\s*\)/.test(content) ||  // Dynamic: process.exit(variable)
      /process\.exit\s*\(\s*\w+\.\w+\s*\)/.test(content);  // Dynamic: process.exit(obj.prop)

    if (!hasExitCodes) {
      warnings.push('No exit codes found (expected process.exit with 0, 1, 2, or variable)');
    }

    // Check for stdin handling
    if (!content.includes('process.stdin')) {
      warnings.push('No stdin handling (hooks receive JSON via stdin)');
    }

    // Check for require statements (dependencies)
    const requires = content.match(/require\(['"]([\w-]+)['"]\)/g) || [];
    const nonStdlib = requires.filter(r => {
      const mod = r.match(/require\(['"](.+)['"]\)/)[1];
      // Node.js stdlib modules
      const stdlib = ['fs', 'path', 'os', 'child_process', 'crypto', 'util', 'stream', 'events', 'http', 'https', 'url', 'querystring', 'buffer'];
      return !stdlib.includes(mod) && !mod.startsWith('.');
    });

    if (nonStdlib.length > 0) {
      warnings.push(`External dependencies: ${nonStdlib.join(', ')}`);
    }

    // Check for error handling
    if (!content.includes('try') && !content.includes('catch')) {
      warnings.push('No try/catch error handling');
    }

    // Check for timeout handling (for PreToolUse hooks only)
    // Looking for setTimeout, Promise.race with timeout, or explicit timeout variable
    const hasTimeoutHandling =
      content.includes('setTimeout') ||
      content.includes('Promise.race') ||
      /timeout\s*[:=]\s*\d+/.test(content) ||
      content.includes('AbortController');

    // Only warn for actual PreToolUse hooks (validate-* scripts), not PreCompact or other hooks
    const isPreToolUseHook = fileName.startsWith('validate-') && !fileName.includes('compact');
    if (isPreToolUseHook && !hasTimeoutHandling) {
      warnings.push('PreToolUse hook should have timeout handling');
    }

    return {
      file: fileName,
      errors,
      warnings,
      valid: errors.length === 0
    };
  } catch (error) {
    return {
      file: fileName,
      errors: [`Read error: ${error.message}`],
      warnings: [],
      valid: false
    };
  }
}

/**
 * Validate settings.json hooks configuration
 */
function validateHooksConfig() {
  const errors = [];
  const warnings = [];
  let hookCount = 0;

  try {
    if (!fs.existsSync(SETTINGS_PATH)) {
      errors.push('Missing .claude/settings.json');
      return { errors, warnings, valid: false };
    }

    const settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8'));

    if (!settings.hooks) {
      errors.push('No hooks configuration in settings.json');
      return { errors, warnings, valid: false };
    }

    // Validate each hook type
    const validTypes = ['PreToolUse', 'PostToolUse', 'Notification', 'Stop', 'SessionStart', 'SessionEnd', 'PreCompact'];

    Object.keys(settings.hooks).forEach(hookType => {
      if (!validTypes.includes(hookType)) {
        warnings.push(`Unknown hook type: ${hookType}`);
      }

      const hookConfigs = settings.hooks[hookType];
      if (!Array.isArray(hookConfigs)) {
        errors.push(`${hookType} hooks should be an array`);
        return;
      }

      hookConfigs.forEach((config, configIndex) => {
        // Handle nested hooks format: { matcher: "...", hooks: [...] }
        if (config.hooks && Array.isArray(config.hooks)) {
          config.hooks.forEach((hook, hookIndex) => {
            hookCount++;

            // Check command field
            if (!hook.command) {
              errors.push(`${hookType}[${configIndex}].hooks[${hookIndex}]: missing command field`);
            } else {
              // Check that script exists
              const scriptPath = hook.command;
              if (scriptPath && !fs.existsSync(path.join(process.cwd(), scriptPath))) {
                warnings.push(`${hookType}: script not found: ${scriptPath}`);
              }
            }
          });

          // Validate matcher (can be string pattern or object)
          if (config.matcher !== undefined && typeof config.matcher !== 'string' && typeof config.matcher !== 'object') {
            warnings.push(`${hookType}[${configIndex}]: matcher should be string or object`);
          }
        }
        // Handle flat format: { command: "...", matcher: {...} }
        else if (config.command) {
          hookCount++;

          // Check that script exists
          const scriptPath = config.command.includes(' ') ? config.command.split(' ')[1] : config.command;
          if (scriptPath && !fs.existsSync(path.join(process.cwd(), scriptPath))) {
            warnings.push(`${hookType}: script not found: ${scriptPath}`);
          }
        }
        else {
          errors.push(`${hookType}[${configIndex}]: invalid hook format (missing command or hooks array)`);
        }
      });
    });

    return {
      errors,
      warnings,
      valid: errors.length === 0,
      hookCount
    };
  } catch (error) {
    return {
      errors: [`Parse error: ${error.message}`],
      warnings: [],
      valid: false
    };
  }
}

/**
 * Test hook execution
 */
function testHookExecution(hookPath, testInput) {
  return new Promise((resolve) => {
    const child = spawn('node', [hookPath], {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, 5000);

    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    child.on('close', (code) => {
      clearTimeout(timeout);
      resolve({
        exitCode: code,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        timedOut
      });
    });

    child.stdin.write(JSON.stringify(testInput));
    child.stdin.end();
  });
}

/**
 * Validate all hooks
 */
async function validateAllHooks() {
  const results = {
    config: validateHooksConfig(),
    scripts: [],
    total: 0,
    valid: 0,
    invalid: 0
  };

  if (fs.existsSync(HOOKS_DIR)) {
    const files = fs.readdirSync(HOOKS_DIR).filter(f => f.endsWith('.js'));
    results.total = files.length;

    for (const file of files) {
      const result = validateHookScript(path.join(HOOKS_DIR, file));
      results.scripts.push(result);

      if (result.valid) {
        results.valid++;
      } else {
        results.invalid++;
      }
    }
  }

  return results;
}

/**
 * Main execution
 */
async function main() {
  console.log('Validating hooks...\n');

  const results = await validateAllHooks();

  // Output config validation
  console.log('Configuration (.claude/settings.json):');
  const configStatus = results.config.valid ? '✓' : '✗';
  console.log(`${configStatus} ${results.config.hookCount || 0} hooks configured`);

  results.config.errors.forEach(err => {
    console.log(`    ERROR: ${err}`);
  });
  results.config.warnings.forEach(warn => {
    console.log(`    WARN: ${warn}`);
  });

  // Output script validation
  console.log('\nScripts (scripts/hooks/):');
  results.scripts.forEach(script => {
    const status = script.valid ? '✓' : '✗';
    console.log(`${status} ${script.file}`);

    script.errors.forEach(err => {
      console.log(`    ERROR: ${err}`);
    });
    script.warnings.forEach(warn => {
      console.log(`    WARN: ${warn}`);
    });
  });

  console.log(`\nSummary: ${results.valid}/${results.total} scripts valid`);
  console.log(`Config: ${results.config.valid ? 'valid' : 'invalid'}`);

  // Exit with error if any invalid
  const hasErrors = !results.config.valid || results.invalid > 0;
  process.exit(hasErrors ? 1 : 0);
}

if (require.main === module) {
  main();
}

module.exports = { validateHookScript, validateHooksConfig, validateAllHooks };
