#!/usr/bin/env node
/**
 * Hook: validate-workflow
 * Event: PostToolUse
 * Matcher: Edit|Write
 * Purpose: Enforce Kailash SDK patterns, detect hardcoded models/keys in ALL
 *          code files (Python, TypeScript, JavaScript).
 *
 *   - Python files:  BLOCK (exit 2) when a hardcoded model has no matching key
 *   - JS/TS files:   WARN only (exit 0)
 *
 * Framework-agnostic — works with any Kailash project.
 *
 * Exit Codes:
 *   0 = success / warn-only
 *   2 = blocking error (Python model without key)
 *   other = non-blocking error
 */

const fs = require("fs");
const path = require("path");
const { parseEnvFile, getModelProvider } = require("./lib/env-utils");

const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.error("[HOOK TIMEOUT] validate-workflow exceeded 5s limit");
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  clearTimeout(timeout);
  try {
    const data = JSON.parse(input);
    const result = validateFile(data);
    console.log(
      JSON.stringify({
        continue: result.continue,
        hookSpecificOutput: {
          hookEventName: "PostToolUse",
          validation: result.messages,
        },
      }),
    );
    process.exit(result.exitCode);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

// =====================================================================
// Main dispatcher
// =====================================================================

function validateFile(data) {
  const filePath = data.tool_input?.file_path || "";
  const cwd = data.cwd || process.cwd();

  const ext = path.extname(filePath).toLowerCase();

  const pythonExts = [".py"];
  const jsExts = [".ts", ".tsx", ".js", ".jsx"];
  const configExts = [".yaml", ".yml", ".json", ".env", ".sh", ".toml"];

  const isPython = pythonExts.includes(ext);
  const isJs = jsExts.includes(ext);
  const isConfig = configExts.includes(ext);

  if (!isPython && !isJs && !isConfig) {
    return {
      continue: true,
      exitCode: 0,
      messages: ["Not a code or config file — skipped"],
    };
  }

  let content;
  try {
    content = fs.readFileSync(filePath, "utf8");
  } catch {
    return { continue: true, exitCode: 0, messages: ["Could not read file"] };
  }

  // Load .env once for key-validation
  const envPath = path.join(cwd, ".env");
  const env = fs.existsSync(envPath) ? parseEnvFile(envPath) : {};

  const messages = [];
  let shouldBlock = false;

  // ── Kailash-specific checks (Python only) ──────────────────────────
  if (isPython) {
    checkKailashPatterns(content, filePath, messages);
  }

  // ── Hardcoded model detection (code files only — configs may list models intentionally)
  if (isPython || isJs) {
    const modelResult = checkHardcodedModels(content, filePath, env, isPython);
    messages.push(...modelResult.messages);
    if (modelResult.block) shouldBlock = true;
  }

  // ── Hardcoded API key detection (all file types including configs) ─
  checkHardcodedKeys(content, messages);

  // ── Stub/TODO/simulation detection (code files only) ──────────────
  if (isPython || isJs) {
    checkStubsAndSimulations(content, filePath, messages);
  }

  if (messages.length === 0) {
    messages.push("All patterns validated");
  }

  return {
    continue: !shouldBlock,
    exitCode: shouldBlock ? 2 : 0,
    messages,
  };
}

// =====================================================================
// Kailash SDK pattern checks (Python only)
// =====================================================================

function checkKailashPatterns(content, filePath, messages) {
  // Anti-pattern: workflow.execute(runtime)
  if (/workflow\s*\.\s*execute\s*\(\s*runtime/.test(content)) {
    messages.push(
      "WARNING: workflow.execute(runtime) found. Use runtime.execute(workflow.build()).",
    );
  }

  // Missing .build()
  if (/runtime\s*\.\s*execute\s*\(\s*workflow\s*[^.]/.test(content)) {
    messages.push(
      "WARNING: Missing .build(). Use runtime.execute(workflow.build()).",
    );
  }

  // Relative imports in kailash code (Python: `from .module import X`)
  if (
    /from\s+\./.test(content) &&
    /kailash|dataflow|nexus|kaizen/.test(filePath.toLowerCase())
  ) {
    messages.push("WARNING: Relative imports detected. Use absolute imports.");
  }

  // Mocking in test files
  if (/_test\.py$|test_.*\.py$/.test(filePath)) {
    const mocks = [
      [/@patch\(/, "@patch"],
      [/MagicMock/, "MagicMock"],
      [/unittest\.mock/, "unittest.mock"],
      [/from\s+mock\s+import/, "mock import"],
      [/mocker\.patch/, "mocker.patch (pytest-mock)"],
      [/\bAsyncMock\b/, "AsyncMock"],
      [/create_autospec/, "create_autospec"],
    ];
    for (const [pat, name] of mocks) {
      if (pat.test(content)) {
        messages.push(
          `WARNING: ${name} detected. NO MOCKING in Tier 2-3 tests.`,
        );
      }
    }
  }

  // SQL injection patterns (f-string or concatenation in SQL)
  if (
    /f["'](?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s/i.test(content) ||
    /(?:SELECT|INSERT|UPDATE|DELETE)\s.*["']\s*\+\s*\w/.test(content)
  ) {
    messages.push(
      "CRITICAL: Possible SQL injection — use parameterized queries or ORM.",
    );
  }

  // eval/exec on variables (skip test files)
  if (!/_test\.py$|test_.*\.py$/.test(filePath)) {
    if (/\beval\s*\(/.test(content) && !/\bast\.literal_eval\b/.test(content)) {
      messages.push("CRITICAL: eval() detected — potential code injection.");
    }
    if (/\bexec\s*\(/.test(content)) {
      messages.push("CRITICAL: exec() detected — potential code injection.");
    }
    if (/subprocess.*shell\s*=\s*True/.test(content)) {
      messages.push(
        "CRITICAL: subprocess with shell=True — potential command injection.",
      );
    }
  }

  // DataFlow primary key naming
  if (
    /@db\.model/.test(content) &&
    /primary_key\s*=\s*True/.test(content) &&
    !/id\s*[:=]/.test(content)
  ) {
    messages.push('WARNING: DataFlow primary key should be named "id".');
  }

  // os.environ without load_dotenv
  if (!/load_dotenv/.test(content) && /os\.environ/.test(content)) {
    messages.push("WARNING: os.environ used without load_dotenv().");
  }
}

// =====================================================================
// Hardcoded model name detection
// =====================================================================

/**
 * Regex patterns that match hardcoded model strings in code.
 * Each returns the captured model name in group 1.
 */
const MODEL_PREFIXES =
  "gpt|claude|gemini|deepseek|mistral|mixtral|command|o[134]|chatgpt|dall-e|whisper|tts|text-embedding|embed|rerank|hume|sonar|pplx|codestral|pixtral|palm";
const MODEL_PATTERNS = [
  // Python/JS: model="gpt-4" or model='gpt-4' or model=`gpt-4` — hyphen+suffix optional for standalone models (o1, o3, whisper)
  new RegExp(
    `model\\s*[=:]\\s*["'\`]((?:${MODEL_PREFIXES})(?:-[^"'\`]+)?)["'\`]`,
    "gi",
  ),
  // Dict/JSON: "model": "gpt-4" or 'model': 'gpt-4'
  new RegExp(
    `["'\`]model(?:_name)?["'\`]\\s*:\\s*["'\`]((?:${MODEL_PREFIXES})(?:-[^"'\`]+)?)["'\`]`,
    "gi",
  ),
];

function checkHardcodedModels(content, filePath, env, isPython) {
  const messages = [];
  let block = false;
  const lines = content.split("\n");

  for (const pattern of MODEL_PATTERNS) {
    // Reset lastIndex for global regex
    pattern.lastIndex = 0;
    let match;

    while ((match = pattern.exec(content)) !== null) {
      const modelName = match[1];
      const lineNum = content.substring(0, match.index).split("\n").length;
      const line = lines[lineNum - 1]?.trim() || "";

      // Skip comments, docstrings, and block comments
      if (
        line.startsWith("#") ||
        line.startsWith("//") ||
        line.startsWith("*") ||
        line.startsWith("/*") ||
        line.startsWith('"""') ||
        line.startsWith("'''")
      ) {
        continue;
      }

      // Check if the model has a corresponding API key
      const info = getModelProvider(modelName);
      const hasKey = info
        ? info.keys.some((k) => env[k] && env[k].length > 5)
        : true; // unknown provider = don't block

      if (isPython && !hasKey && info) {
        messages.push(
          `BLOCKED: Hardcoded model "${modelName}" at line ${lineNum} — ` +
            `${info.keys.join(" or ")} not found in .env. ` +
            `Use os.environ.get("OPENAI_PROD_MODEL") or equivalent.`,
        );
        block = true;
      } else {
        messages.push(
          `WARNING: Hardcoded model "${modelName}" at ${path.basename(filePath)}:${lineNum}. ` +
            `Prefer reading from .env.`,
        );
      }
    }
  }

  return { messages, block };
}

// =====================================================================
// Hardcoded API key detection
// =====================================================================

function checkHardcodedKeys(content, messages) {
  // Order matters: more specific prefixes first (sk-ant- before sk-)
  // Patterns match with or without quotes to catch keys in YAML, .env, shell scripts
  const keyPatterns = [
    [/["'`]?sk-ant-[a-zA-Z0-9_-]{20,}["'`]?/, "Anthropic API key"],
    [/["'`]?ant-api[a-zA-Z0-9_-]{20,}["'`]?/, "Anthropic API key"],
    [/["'`]?sk-proj-[a-zA-Z0-9_-]{20,}["'`]?/, "OpenAI API key"],
    [/["'`]?sk-[a-zA-Z0-9_-]{20,}["'`]?/, "OpenAI API key"],
    [/["'`]?pplx-[a-zA-Z0-9_-]{20,}["'`]?/, "Perplexity API key"],
    [/["'`]?AIzaSy[a-zA-Z0-9_-]{30,}["'`]?/, "Google API key"],
    [/["'`]?AKIA[0-9A-Z]{16}["'`]?/, "AWS Access Key"],
    [/["'`]?ghp_[a-zA-Z0-9]{36,}["'`]?/, "GitHub Personal Access Token"],
    [/["'`]?gho_[a-zA-Z0-9]{36,}["'`]?/, "GitHub OAuth Token"],
    [/["'`]?github_pat_[a-zA-Z0-9_]{22,}["'`]?/, "GitHub Fine-grained Token"],
    [/["'`]?sk_live_[a-zA-Z0-9]{20,}["'`]?/, "Stripe Live Key"],
    [/["'`]?sk_test_[a-zA-Z0-9]{20,}["'`]?/, "Stripe Test Key"],
    [/["'`]?xoxb-[a-zA-Z0-9-]{20,}["'`]?/, "Slack Bot Token"],
  ];

  const seen = new Set();
  for (const [pattern, name] of keyPatterns) {
    if (pattern.test(content) && !seen.has(name)) {
      seen.add(name);
      messages.push(
        `CRITICAL: Hardcoded ${name} detected! Use os.environ.get() or process.env.`,
      );
    }
  }
}

// =====================================================================
// Stub / TODO / Simulation detection
// =====================================================================

/**
 * Detect stubs, TODOs, placeholders, naive fallbacks, and simulated services.
 * Warn-only (never blocks) — these are code-quality indicators.
 */
function checkStubsAndSimulations(content, filePath, messages) {
  // Skip test files — stubs in tests are intentional fixture data
  const basename = path.basename(filePath).toLowerCase();
  if (
    /^test_|_test\.|\.test\.|\.spec\.|__tests__/.test(basename) ||
    filePath.includes("__tests__") ||
    filePath.includes("/tests/")
  ) {
    return;
  }

  const lines = content.split("\n");
  const stubPatterns = [
    // Explicit markers
    [/\bTODO\b/i, "TODO marker"],
    [/\bFIXME\b/i, "FIXME marker"],
    [/\bHACK\b/i, "HACK marker"],
    [/\bSTUB\b/i, "STUB marker"],
    [/\bXXX\b/, "XXX marker"],
    // Python stubs
    [/\braise\s+NotImplementedError\b/, "NotImplementedError (unimplemented)"],
    [
      /\bpass\s*#\s*(stub|placeholder|todo|not\s*impl)/i,
      "pass with stub comment",
    ],
    [
      /\breturn\s+None\s*#\s*(stub|placeholder|todo|not\s*impl)/i,
      "return None stub",
    ],
    // Simulated/mock data in production code
    [
      /\b(simulated?|fake|dummy|placeholder)\s*(data|response|result|value)/i,
      "simulated data",
    ],
    [/\breturn\s*\{\s*\}\s*#\s*(stub|placeholder|todo)/i, "empty return stub"],
    // Naive silent fallbacks
    [/except\s*:\s*\n\s*pass\b/, "bare except:pass (silent fallback)"],
    [/catch\s*\([^)]*\)\s*\{\s*\}/, "empty catch block (silent fallback)"],
  ];

  const found = new Set();
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    // Skip comments
    if (
      trimmed.startsWith("#") ||
      trimmed.startsWith("//") ||
      trimmed.startsWith("*") ||
      trimmed.startsWith("/*")
    ) {
      continue;
    }

    for (const [pattern, label] of stubPatterns) {
      if (pattern.test(line) && !found.has(label)) {
        found.add(label);
        messages.push(
          `WARNING: ${label} at ${path.basename(filePath)}:${i + 1}. ` +
            `Implement fully — don't leave stubs in production code.`,
        );
      }
    }
  }
}
