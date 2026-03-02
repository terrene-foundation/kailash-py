#!/usr/bin/env node
/**
 * Hook: validate-workflow
 * Event: PostToolUse
 * Matcher: Edit|Write
 * Purpose: Enforce Kailash Rust SDK patterns, detect hardcoded models/keys in
 *          code files (Rust, TypeScript, JavaScript).
 *
 *   - Rust files:   BLOCK (exit 2) when a hardcoded model has no matching key
 *   - JS/TS files:  WARN only (exit 0)
 *
 * Rust-first -- validates cargo/Rust patterns for the Kailash crate workspace.
 *
 * Exit Codes:
 *   0 = success / warn-only
 *   2 = blocking error (Rust model without key)
 *   other = non-blocking error
 */

const fs = require("fs");
const path = require("path");
const { parseEnvFile, getModelProvider } = require("./lib/env-utils");
const {
  logObservation: logLearningObservation,
} = require("./lib/learning-utils");

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

  const rustExts = [".rs"];
  const jsExts = [".ts", ".tsx", ".js", ".jsx"];
  const configExts = [".yaml", ".yml", ".json", ".env", ".sh", ".toml"];

  const isRust = rustExts.includes(ext);
  const isJs = jsExts.includes(ext);
  const isConfig = configExts.includes(ext);

  if (!isRust && !isJs && !isConfig) {
    return {
      continue: true,
      exitCode: 0,
      messages: ["Not a code or config file -- skipped"],
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

  // -- Kailash Rust-specific checks (.rs only) ----------------------------
  if (isRust) {
    checkRustPatterns(content, filePath, messages);
  }

  // -- Hardcoded model detection (code files only -- configs may list models intentionally)
  if (isRust || isJs) {
    const modelResult = checkHardcodedModels(content, filePath, env, isRust);
    messages.push(...modelResult.messages);
    if (modelResult.block) shouldBlock = true;
  }

  // -- Hardcoded API key detection (all file types including configs) -----
  checkHardcodedKeys(content, filePath, messages);

  // -- Stub/TODO/simulation detection (code files only) -------------------
  if (isRust || isJs) {
    checkStubsAndSimulations(content, filePath, messages);
  }

  if (messages.length === 0) {
    messages.push("All patterns validated");
  }

  // --- Observation logging (Phase 2: enriched learning) ---
  try {
    logFileObservations(content, filePath, cwd, messages);
  } catch {}

  return {
    continue: !shouldBlock,
    exitCode: shouldBlock ? 2 : 0,
    messages,
  };
}

// =====================================================================
// Kailash SDK pattern checks (Rust only)
// =====================================================================

function checkRustPatterns(content, filePath, messages) {
  // Anti-pattern: workflow.execute(runtime) -- wrong direction
  if (/workflow\s*\.\s*execute\s*\(\s*(&\s*)?runtime/.test(content)) {
    messages.push(
      "WARNING: workflow.execute(runtime) found. Use runtime.execute(workflow).",
    );
  }

  // Check for todo!() macro in production code (not tests)
  // For Rust files with inline #[cfg(test)] modules, only check the
  // production portion of the file (before #[cfg(test)]).
  if (!isTestFile(filePath)) {
    const lines = content.split("\n");
    const cfgTestLine = findCfgTestLine(lines);
    const prodContent =
      cfgTestLine > 0 ? lines.slice(0, cfgTestLine - 1).join("\n") : content;

    if (/\btodo!\s*\(/.test(prodContent)) {
      messages.push(
        "WARNING: todo!() macro found in production code. Implement fully.",
      );
    }
    if (/\bunimplemented!\s*\(/.test(prodContent)) {
      messages.push(
        "WARNING: unimplemented!() macro found in production code. Implement fully.",
      );
    }
    if (/\bpanic!\s*\(/.test(prodContent)) {
      messages.push(
        "WARNING: panic!() macro found. Consider returning Result<> instead.",
      );
    }
  }

  // Check for unsafe blocks -- flag for review
  if (/\bunsafe\s*\{/.test(content)) {
    messages.push(
      "REVIEW: unsafe block detected. Ensure this is necessary and document the safety invariant.",
    );
  }

  // Check for raw SQL strings instead of sqlx macros
  if (
    /r#?"(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s/i.test(content) ||
    /"\s*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s/i.test(content)
  ) {
    // Only flag if not already using sqlx::query! or sqlx::query_as!
    if (!/sqlx::query(?:_as)?!/.test(content)) {
      messages.push(
        "WARNING: Raw SQL string detected. Prefer sqlx::query!() or sqlx::query_as!() macros for compile-time checked queries.",
      );
    }
  }

  // Check for format!() in SQL context (SQL injection risk)
  if (
    /format!\s*\(\s*"(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s/i.test(
      content,
    )
  ) {
    messages.push(
      "CRITICAL: format!() with SQL detected -- potential SQL injection. Use sqlx parameterized queries.",
    );
  }

  // Mocking in test files -- check for inappropriate mocking in integration/e2e tests
  if (isTestFile(filePath)) {
    // Check if this looks like an integration or e2e test (tier 2-3)
    const isIntegrationTest =
      filePath.includes("/integration/") ||
      filePath.includes("/e2e/") ||
      filePath.includes("_integration") ||
      filePath.includes("_e2e");

    if (isIntegrationTest) {
      const mockPatterns = [
        [/\bmockall\b/, "mockall"],
        [/\b#\[automock\]/, "#[automock]"],
        [/\bmock!\s*\(/, "mock!()"],
        [/MockContext/, "MockContext"],
      ];
      for (const [pat, name] of mockPatterns) {
        if (pat.test(content)) {
          messages.push(
            `WARNING: ${name} detected in integration/e2e test. NO MOCKING in Tier 2-3 tests.`,
          );
        }
      }
    }
  }

  // Check for std::env::var without dotenv loading
  if (
    /std::env::var/.test(content) &&
    !/dotenv/.test(content) &&
    !/dotenvy/.test(content) &&
    !isTestFile(filePath)
  ) {
    messages.push(
      "WARNING: std::env::var() used without dotenv/dotenvy. Ensure .env is loaded.",
    );
  }

  // Check for hardcoded secret patterns in Rust
  if (
    /let\s+\w*(secret|password|token|key)\w*\s*=\s*"[^"]{8,}"/.test(content) &&
    !isTestFile(filePath)
  ) {
    messages.push(
      "CRITICAL: Possible hardcoded secret in Rust code. Use std::env::var() or dotenvy.",
    );
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
  // Rust/JS: model = "gpt-4" or model: "gpt-4" -- hyphen+suffix optional for standalone models
  new RegExp(
    `model\\s*[=:]\\s*["'\`]((?:${MODEL_PREFIXES})(?:-[^"'\`]+)?)["'\`]`,
    "gi",
  ),
  // Struct/JSON: "model": "gpt-4" or 'model': 'gpt-4'
  new RegExp(
    `["'\`]model(?:_name)?["'\`]\\s*:\\s*["'\`]((?:${MODEL_PREFIXES})(?:-[^"'\`]+)?)["'\`]`,
    "gi",
  ),
];

function checkHardcodedModels(content, filePath, env, isRust) {
  const messages = [];
  let block = false;
  const lines = content.split("\n");

  // For Rust files: find the line where #[cfg(test)] starts.
  // Everything after that line is test code and should only warn, never block.
  const cfgTestLine = isRust ? findCfgTestLine(lines) : -1;

  // For Rust files: build a set of lines that are inside doc comments
  // (/// or //! blocks, including their code examples).
  const docCommentLines = isRust ? buildDocCommentLines(lines) : new Set();

  for (const pattern of MODEL_PATTERNS) {
    // Reset lastIndex for global regex
    pattern.lastIndex = 0;
    let match;

    while ((match = pattern.exec(content)) !== null) {
      const modelName = match[1];
      const lineNum = content.substring(0, match.index).split("\n").length;
      const line = lines[lineNum - 1]?.trim() || "";

      // Skip comments (Rust // and /* */, JS //)
      if (
        line.startsWith("//") ||
        line.startsWith("*") ||
        line.startsWith("/*") ||
        line.startsWith("///") ||
        line.startsWith("//!")
      ) {
        continue;
      }

      // Skip lines inside doc comment blocks (Rust only)
      if (docCommentLines.has(lineNum)) {
        continue;
      }

      // Skip or downgrade matches inside #[cfg(test)] regions (Rust only)
      const inTestRegion = isRust && cfgTestLine > 0 && lineNum >= cfgTestLine;

      // Check if the model has a corresponding API key
      const info = getModelProvider(modelName);
      const hasKey = info
        ? info.keys.some((k) => env[k] && env[k].length > 5)
        : true; // unknown provider = don't block

      if (inTestRegion || isTestFile(filePath)) {
        // Test code: warn only, never block
        messages.push(
          `WARNING: Hardcoded model "${modelName}" in test code at ${path.basename(filePath)}:${lineNum}. ` +
            `Consider reading from env in integration tests.`,
        );
      } else if (isRust && !hasKey && info) {
        messages.push(
          `BLOCKED: Hardcoded model "${modelName}" at line ${lineNum} -- ` +
            `${info.keys.join(" or ")} not found in .env. ` +
            `Use std::env::var("OPENAI_PROD_MODEL") or dotenvy equivalent.`,
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

function checkHardcodedKeys(content, filePath, messages) {
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

  // For Rust files: skip #[cfg(test)] regions -- test keys are not real secrets
  const isRust = filePath && filePath.endsWith(".rs");
  let prodContent = content;
  if (isRust || isTestFile(filePath || "")) {
    const lines = content.split("\n");
    const cfgTestLine = isRust ? findCfgTestLine(lines) : -1;
    if (isTestFile(filePath || "")) {
      return; // Skip key detection entirely for test files
    }
    if (cfgTestLine > 0) {
      prodContent = lines.slice(0, cfgTestLine - 1).join("\n");
    }
  }

  const seen = new Set();
  for (const [pattern, name] of keyPatterns) {
    if (pattern.test(prodContent) && !seen.has(name)) {
      seen.add(name);
      messages.push(
        `CRITICAL: Hardcoded ${name} detected! Use std::env::var() or process.env.`,
      );
    }
  }
}

// =====================================================================
// Stub / TODO / Simulation detection
// =====================================================================

/**
 * Detect stubs, TODOs, placeholders, naive fallbacks, and simulated services.
 * Warn-only (never blocks) -- these are code-quality indicators.
 */
function checkStubsAndSimulations(content, filePath, messages) {
  // Skip test files -- stubs in tests are intentional fixture data
  if (isTestFile(filePath)) {
    return;
  }

  const lines = content.split("\n");

  // For Rust files: skip #[cfg(test)] regions (test code within source files)
  const cfgTestLine = filePath.endsWith(".rs") ? findCfgTestLine(lines) : -1;

  const stubPatterns = [
    // Explicit markers
    [/\bTODO\b/i, "TODO marker"],
    [/\bFIXME\b/i, "FIXME marker"],
    [/\bHACK\b/i, "HACK marker"],
    [/\bSTUB\b/i, "STUB marker"],
    [/\bXXX\b/, "XXX marker"],
    // Rust stubs
    [/\btodo!\s*\(/, "todo!() (unimplemented)"],
    [/\bunimplemented!\s*\(/, "unimplemented!() macro"],
    [
      /\bpanic!\s*\(\s*"not\s+(yet\s+)?implement/i,
      "panic with not-implemented message",
    ],
    // Simulated/mock data in production code
    [
      /\b(simulated?|fake|dummy|placeholder)\s*(data|response|result|value)/i,
      "simulated data",
    ],
    // JS-specific naive silent fallbacks
    [/catch\s*\([^)]*\)\s*\{\s*\}/, "empty catch block (silent fallback)"],
  ];

  const found = new Set();
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip #[cfg(test)] regions in Rust files
    if (cfgTestLine > 0 && i + 1 >= cfgTestLine) {
      break; // All remaining lines are test code
    }

    // Skip comments
    if (
      trimmed.startsWith("//") ||
      trimmed.startsWith("*") ||
      trimmed.startsWith("/*") ||
      trimmed.startsWith("///") ||
      trimmed.startsWith("//!")
    ) {
      continue;
    }

    for (const [pattern, label] of stubPatterns) {
      if (pattern.test(line) && !found.has(label)) {
        found.add(label);
        messages.push(
          `WARNING: ${label} at ${path.basename(filePath)}:${i + 1}. ` +
            `Implement fully -- don't leave stubs in production code.`,
        );
      }
    }
  }
}

// =====================================================================
// Observation logging for the learning system
// =====================================================================

/**
 * Detect patterns in the file content and log enriched observations.
 * Runs after validation; overhead is <5ms (fs.appendFileSync of JSONL lines).
 */
function logFileObservations(content, filePath, cwd, messages) {
  const basename = path.basename(filePath);

  // WorkflowBuilder / runtime.execute() → workflow_pattern
  if (
    /WorkflowBuilder/.test(content) ||
    /runtime\s*\.\s*execute/.test(content)
  ) {
    logLearningObservation(cwd, "workflow_pattern", {
      pattern_type: /WorkflowBuilder/.test(content)
        ? "workflow_builder"
        : "runtime_execute",
      file: basename,
    });
  }

  // add_node() calls → node_usage
  const nodeMatches = content.match(/add_node\s*\(\s*["'](\w+)["']/g);
  if (nodeMatches && nodeMatches.length > 0) {
    const nodeTypes = [
      ...new Set(
        nodeMatches
          .map((m) => {
            const match = m.match(/add_node\s*\(\s*["'](\w+)["']/);
            return match ? match[1] : null;
          })
          .filter(Boolean),
      ),
    ];
    logLearningObservation(cwd, "node_usage", {
      node_types: nodeTypes,
      file: basename,
    });
  }

  // @db.model → dataflow_model
  const modelMatches = content.match(/@db\.model[\s\S]*?class\s+(\w+)/g);
  if (modelMatches) {
    for (const m of modelMatches) {
      const nameMatch = m.match(/class\s+(\w+)/);
      if (nameMatch) {
        logLearningObservation(cwd, "dataflow_model", {
          model_name: nameMatch[1],
          file: basename,
        });
      }
    }
  }

  // Stubs/TODOs detected → error_occurrence (stub_detected)
  if (
    messages.some((m) =>
      /TODO marker|FIXME marker|STUB marker|todo!\(\)|unimplemented!\(\)/.test(
        m,
      ),
    )
  ) {
    logLearningObservation(cwd, "error_occurrence", {
      error_type: "stub_detected",
      file: basename,
    });
  }

  // Hardcoded model name detected → error_occurrence (hardcoded_model)
  if (messages.some((m) => /Hardcoded model/.test(m))) {
    logLearningObservation(cwd, "error_occurrence", {
      error_type: "hardcoded_model",
      file: basename,
    });
  }
}

// =====================================================================
// Helpers
// =====================================================================

/**
 * Find the 1-based line number where `#[cfg(test)]` appears in a Rust file.
 * Returns -1 if not found. Everything after this line is considered test code.
 */
function findCfgTestLine(lines) {
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*#\[cfg\(test\)\]/.test(lines[i])) {
      return i + 1; // 1-based
    }
  }
  return -1;
}

/**
 * Build a set of 1-based line numbers that fall inside Rust doc comment blocks
 * (lines prefixed with `///` or `//!`). This catches code examples inside docs
 * that might contain model names as illustrative content.
 */
function buildDocCommentLines(lines) {
  const docLines = new Set();
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed.startsWith("///") || trimmed.startsWith("//!")) {
      docLines.add(i + 1); // 1-based
    }
  }
  return docLines;
}

function isTestFile(filePath) {
  const basename = path.basename(filePath).toLowerCase();
  return (
    /^test_|_test\.|\.test\.|\.spec\.|__tests__/.test(basename) ||
    filePath.includes("__tests__") ||
    filePath.includes("/tests/") ||
    filePath.includes("/test/") ||
    // Rust test convention: files in tests/ directory or #[cfg(test)] modules
    (filePath.endsWith(".rs") && basename.startsWith("test_"))
  );
}
