#!/usr/bin/env node
/**
 * Hook: integration-hygiene
 * Event: PostToolUse
 * Matcher: Edit|Write
 * Purpose: Catch integration-hygiene anti-patterns the moment they land in code.
 *
 *   Detects (WARN, non-blocking):
 *   - Raw SQL strings in non-migration source files (DataFlow bypass)
 *   - MOCK_/FAKE_/DUMMY_/SAMPLE_ frontend constants (hidden stub data)
 *   - Silent-swallow exception handlers (`except: pass`, `catch(e){}`, bare rescue)
 *   - New endpoint handlers with no logger call in the function body
 *   - Raw HTTP client calls (requests./httpx./fetch()) without surrounding log
 *
 * Returns WARN only -- never blocks. Intent is to surface the violation so the
 * agent self-corrects in the same session. Blocking here would break too many
 * legitimate edge cases that the agent rightly ignores.
 *
 * Exit Codes:
 *   0 = success / warn
 *   1 = hook error (e.g. timeout, malformed input)
 */

const fs = require("fs");
const path = require("path");

const TIMEOUT_MS = 3000;
const timeout = setTimeout(() => {
  console.error("[HOOK TIMEOUT] integration-hygiene exceeded 3s limit");
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
  if (process.env.COC_RUNTIME === "codex" && Buffer.byteLength(input) > 2 * 1024 * 1024) {
    fs.writeSync(1, JSON.stringify({ hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: "Hygiene scan skipped: hook input size limit exceeded.",
    } }) + "\n");
    process.exit(0);
  }
});
process.stdin.on("end", () => {
  clearTimeout(timeout);
  try {
    const data = JSON.parse(input);
    const result = process.env.COC_RUNTIME === "codex" ? checkCodexFiles(data) : checkFile(data);
    // Surface advisories to the agent via additionalContext — the delivered
    // PostToolUse field; the prior `validation` sibling was silently dropped
    // (loom #466). Render the message objects to text; emit no context block
    // when there are no advisories.
    const out = { continue: true };
    if (Array.isArray(result.messages) && result.messages.length) {
      out.hookSpecificOutput = {
        hookEventName: "PostToolUse",
        additionalContext: result.messages
          .map((m) => (m && m.message ? `[${m.rule}] ${m.message}` : String(m)))
          .join("\n"),
      };
    }
    console.log(JSON.stringify(out));
    process.exit(0);
  } catch (error) {
    console.error(`[HOOK ERROR] integration-hygiene: ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

// Native Codex apply_patch carries patch text in tool_input.command, not
// file_path. Inspect only bounded, existing in-root targets; never execute or
// interpret shell commands. PostToolUse advisories cannot undo the edit.
const MAX_SCAN_BYTES = 1024 * 1024;
const MAX_SCAN_FILES = 100;
function scanNotice(message) {
  return { severity: "warn", rule: "hook-coverage", message };
}
function isScannableSource(filePath) {
  return [".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".rb"].includes(path.extname(filePath).toLowerCase()) &&
    !/(migrations?\/|tests?\/|__tests__\/|test_|_test\.|\.spec\.|\.test\.)/.test(filePath);
}
function checkCodexFiles(data) {
  const targets = [];
  if (data.tool_name === "apply_patch") {
    const patch = data.tool_input?.command;
    if (typeof patch !== "string" || Buffer.byteLength(patch) > MAX_SCAN_BYTES ||
        !patch.startsWith("*** Begin Patch\n") || !patch.trimEnd().endsWith("*** End Patch")) {
      return { messages: [scanNotice("Hygiene scan skipped: unsupported patch or size limit.")] };
    }
    for (const line of patch.split("\n")) {
      const match = line.match(/^\*\*\* (Add File|Update File|Move to): (.+)$/);
      if (!match) continue;
      if (match[1] === "Move to" && targets.length) targets[targets.length - 1] = match[2];
      else targets.push(match[2]);
      if (targets.length > MAX_SCAN_FILES) {
        return { messages: [scanNotice("Hygiene scan skipped: patch target count limit exceeded.")] };
      }
    }
  } else if (["Edit", "Write"].includes(data.tool_name) && typeof data.tool_input?.file_path === "string") {
    targets.push(data.tool_input.file_path);
  } else {
    return { messages: [scanNotice("Hygiene scan skipped: no supported edit payload; Bash writes are not scanned.")] };
  }
  const messages = [];
  let boundary;
  try {
    boundary = fs.realpathSync(process.env.CLAUDE_PROJECT_DIR || data.cwd || process.cwd());
  } catch {
    return { messages: [scanNotice("Hygiene scan skipped: repository root is unavailable.")] };
  }
  for (const target of new Set(targets)) {
    let fd;
    try {
      const canonical = fs.realpathSync(path.resolve(data.cwd || boundary, target));
      const relative = path.relative(boundary, canonical);
      if (relative === ".." || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
        messages.push(scanNotice("Hygiene scan skipped: target is outside the repository root."));
        continue;
      }
      if (!isScannableSource(canonical)) continue;
      const before = fs.statSync(canonical);
      if (!before.isFile() || before.size > MAX_SCAN_BYTES) {
        messages.push(scanNotice("Hygiene scan skipped: target is not a regular file or exceeds the size limit."));
        continue;
      }
      // Pin the opened file before reading and reject leaf symlinks. Compare
      // identity and canonical path again before reading to detect replacements.
      // This is not an OS sandbox against concurrent hostile ancestor mutation.
      fd = fs.openSync(canonical, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
      const opened = fs.fstatSync(fd);
      if (!opened.isFile() || opened.dev !== before.dev || opened.ino !== before.ino ||
          fs.realpathSync(canonical) !== canonical) {
        messages.push(scanNotice("Hygiene scan skipped: target changed during inspection."));
        continue;
      }
      const buffer = Buffer.alloc(MAX_SCAN_BYTES + 1);
      let used = 0;
      while (used < buffer.length) {
        const count = fs.readSync(fd, buffer, used, buffer.length - used, null);
        if (count === 0) break;
        used += count;
      }
      if (used > MAX_SCAN_BYTES) {
        messages.push(scanNotice("Hygiene scan skipped: file grew past the size limit."));
        continue;
      }
      messages.push(...checkFile(data, { filePath: canonical, content: buffer.toString("utf8", 0, used) }).messages);
    } catch {
      messages.push(scanNotice("Hygiene scan skipped: target was deleted, unreadable, or changed during inspection."));
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
    }
  }
  return { messages };
}

// ---------------------------------------------------------------------------
// Main check dispatcher
// ---------------------------------------------------------------------------

function checkFile(data, loaded) {
  const filePath = loaded ? loaded.filePath : data.tool_input?.file_path || "";
  if (!isScannableSource(filePath)) return { messages: [] };

  let content = "";
  try {
    content = loaded ? loaded.content : fs.readFileSync(filePath, "utf8");
  } catch {
    return { messages: [] }; // file deleted or unreadable; nothing to check
  }

  const messages = [];
  const rel = path.relative(data.cwd || process.cwd(), filePath);

  // 1. Raw SQL strings outside migration files (DataFlow bypass)
  const sqlPattern =
    /["'`](?:\s*)(?:SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE)\s+/i;
  if (
    sqlPattern.test(content) &&
    !/\/(?:db|infrastructure|dialect)\//.test(filePath)
  ) {
    messages.push({
      severity: "warn",
      rule: "framework-first.md § Work-Domain Binding",
      message: `${rel}: raw SQL string detected. DataFlow (@db.model, db.express) is MANDATORY for all DB work. Consult dataflow-specialist.`,
    });
  }

  // 2. Frontend mock-data constants
  const mockPattern = /\b(MOCK|FAKE|DUMMY|SAMPLE)_[A-Z][A-Z0-9_]*\s*[:=]/;
  if (mockPattern.test(content)) {
    messages.push({
      severity: "warn",
      rule: "zero-tolerance.md Rule 2",
      message: `${rel}: mock/fake/dummy constant detected. Frontend mock data is a stub -- remove before ship.`,
    });
  }

  // 3. Silent exception swallows
  const silentSwallowPatterns = [
    { pat: /except\s*:\s*pass\b/, lang: "Python" },
    {
      pat: /except\s+Exception\s*:\s*(?:pass|return\s+None)\b/,
      lang: "Python",
    },
    { pat: /catch\s*\([^)]*\)\s*\{\s*\}/, lang: "JS/TS" },
    { pat: /rescue\s*(?:=>\s*\w+)?\s*$\s*end/m, lang: "Ruby" },
  ];
  for (const { pat, lang } of silentSwallowPatterns) {
    if (pat.test(content)) {
      messages.push({
        severity: "warn",
        rule: "zero-tolerance.md Rule 3",
        message: `${rel}: silent ${lang} exception swallow. BLOCKED per Rule 3 -- log AND act (retry, fall back, re-raise) or re-raise.`,
      });
      break;
    }
  }

  // 4. Endpoint handlers with no logger call anywhere in the file
  const endpointPattern =
    /(?:@(?:router|app|api)\.(?:get|post|put|patch|delete)|@route|def\s+\w+\s*\(\s*request|async\s+def\s+\w+\s*\(\s*req)/;
  const loggerPattern =
    /(?:logger\.(?:info|warn|warning|error|debug|exception)|structlog\.|Rails\.logger|semantic_logger|tracing::)/;
  if (endpointPattern.test(content) && !loggerPattern.test(content)) {
    messages.push({
      severity: "warn",
      rule: "observability.md § Mandatory Log Points",
      message: `${rel}: endpoint handler detected with no logger call. Every endpoint MUST log entry, exit, and error paths.`,
    });
  }

  // 5. Raw HTTP client calls without any log in the file
  const rawHttpPattern =
    /(?:requests\.(?:get|post|put|patch|delete)|httpx\.(?:get|post|put|patch|delete)|\bfetch\s*\(|urllib\.request)/;
  if (rawHttpPattern.test(content) && !loggerPattern.test(content)) {
    messages.push({
      severity: "warn",
      rule: "framework-first.md § Work-Domain Binding + observability.md",
      message: `${rel}: raw HTTP client call detected with no surrounding log. Outbound integrations MUST log intent + result. Consult nexus-specialist.`,
    });
  }

  return { messages };
}
