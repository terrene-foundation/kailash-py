#!/usr/bin/env node
/**
 * Hook: user-prompt-rules-reminder
 * Event: UserPromptSubmit
 * Purpose: Inject critical rules into conversation on EVERY user message.
 *          This is the PRIMARY mechanism that survives context compression,
 *          because it runs fresh on every turn (independent of memory).
 *
 * Framework-agnostic — works with any Kailash project.
 *
 * Exit Codes:
 *   0 = success (continue)
 */

const fs = require("fs");
const path = require("path");
const {
  parseEnvFile,
  discoverModelsAndKeys,
  buildCompactSummary,
  ensureEnvFile,
} = require("./lib/env-utils");

const TIMEOUT_MS = 3000;
const timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(0);
}, TIMEOUT_MS);

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  clearTimeout(timeout);
  try {
    const data = JSON.parse(input);
    const result = buildReminder(data);
    console.log(JSON.stringify(result));
    process.exit(0);
  } catch {
    console.log(JSON.stringify({ continue: true }));
    process.exit(0);
  }
});

function buildReminder(data) {
  const cwd = data.cwd || process.cwd();
  const userMessage = (data.tool_input?.user_message || "").toLowerCase();

  // ── Always inject env summary (brief, 1-2 lines) ─────────────────
  const envPath = path.join(cwd, ".env");
  let envSummary = "No .env found";
  let failures = [];

  if (fs.existsSync(envPath)) {
    const env = parseEnvFile(envPath);
    const discovery = discoverModelsAndKeys(env);
    envSummary = buildCompactSummary(env, discovery);
    failures = discovery.validations.filter((v) => v.status === "MISSING_KEY");
  } else {
    // Try to create .env
    ensureEnvFile(cwd);
  }

  // ── Build the reminder lines ──────────────────────────────────────
  const lines = [];

  // Line 1: Always show model/key status (compressed, 1 line)
  lines.push(`[ENV] ${envSummary}`);

  // Line 2: If there are failures, highlight them
  if (failures.length > 0) {
    lines.push(
      `[ENV] CRITICAL: ${failures.length} model(s) missing API keys — LLM calls will fail!`,
    );
  }

  // Line 3: Core behavioral rules (always present, survives compression)
  lines.push(
    "[RULES] Never hardcode models/keys. " +
      "Create missing records (god-mode). " +
      "Implement gaps, don't document them. " +
      "Follow up on failures. " +
      "No stubs/TODOs/simulated data in production code.",
  );

  // ── Contextual reminders based on user message content ────────────
  const llmKeywords = [
    "model",
    "llm",
    "agent",
    "gpt",
    "claude",
    "gemini",
    "openai",
    "anthropic",
    "api key",
    "shadow agent",
    "objective",
  ];
  const e2eKeywords = [
    "e2e",
    "test",
    "playwright",
    "validate",
    "red-team",
    "persona",
    "rbac",
    "login",
  ];

  const mentionsLLM = llmKeywords.some((kw) => userMessage.includes(kw));
  const mentionsE2E = e2eKeywords.some((kw) => userMessage.includes(kw));

  if (mentionsLLM) {
    lines.push(
      "[REMINDER] Read model name from .env (OPENAI_PROD_MODEL or equivalent). " +
        "Read API key from .env. NEVER hardcode.",
    );
  }

  if (mentionsE2E) {
    lines.push(
      "[REMINDER] God-mode E2E: Create ALL missing records. " +
        "Adapt to data changes. Assume correct role. " +
        "If endpoint missing, implement it.",
    );
  }

  return {
    continue: true,
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      suppressOutput: false,
      message: lines.join("\n"),
    },
  };
}
