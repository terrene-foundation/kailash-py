#!/usr/bin/env node
/**
 * Hook: session-start
 * Event: SessionStart
 * Purpose: Load previous session state, initialize logging, check environment
 *
 * Exit Codes:
 *   0 = success (continue)
 *   2 = blocking error (stop tool execution)
 *   other = non-blocking error (warn and continue)
 */

const fs = require("fs");
const path = require("path");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  try {
    const data = JSON.parse(input);
    const result = initializeSession(data);
    // SessionStart hooks don't support hookSpecificOutput in schema
    // Only PreToolUse, UserPromptSubmit, PostToolUse have hookSpecificOutput
    console.log(JSON.stringify({ continue: true }));
    process.exit(0);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

function initializeSession(data) {
  const session_id = data.session_id || "unknown";
  const cwd = data.cwd || process.cwd();
  const homeDir = process.env.HOME || process.env.USERPROFILE;
  const sessionDir = path.join(homeDir, ".claude", "sessions");
  const learningDir = path.join(homeDir, ".claude", "kailash-learning");

  // Ensure directories exist
  [sessionDir, learningDir].forEach((dir) => {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {}
  });

  // Load previous session if exists
  let previousSession = null;
  const sessionFile = path.join(sessionDir, `${session_id}.json`);
  const lastSessionFile = path.join(sessionDir, "last-session.json");

  try {
    if (fs.existsSync(sessionFile)) {
      previousSession = JSON.parse(fs.readFileSync(sessionFile, "utf8"));
    } else if (fs.existsSync(lastSessionFile)) {
      previousSession = JSON.parse(fs.readFileSync(lastSessionFile, "utf8"));
    }
  } catch {}

  // Check for .env file
  let envExists = false;
  try {
    const envPath = path.join(cwd, ".env");
    envExists = fs.existsSync(envPath);
  } catch {}

  // Detect framework in use
  const framework = detectFramework(cwd);

  // Initialize observations file for learning
  const observationsFile = path.join(learningDir, "observations.jsonl");
  const observation = {
    type: "session_start",
    session_id,
    cwd,
    timestamp: new Date().toISOString(),
    envExists,
    framework,
  };

  try {
    fs.appendFileSync(observationsFile, JSON.stringify(observation) + "\n");
  } catch {}

  const warnings = [];
  if (!envExists) {
    warnings.push("No .env file found. Ensure environment variables are set.");
  }

  return {
    session_id,
    cwd,
    previousSession: previousSession ? "loaded" : "none",
    envExists,
    framework,
    warnings,
    message: warnings.length > 0 ? `WARNING: ${warnings.join(" ")}` : "Ready",
  };
}

function detectFramework(cwd) {
  try {
    const files = fs.readdirSync(cwd);
    const fileList = files.join(" ").toLowerCase();

    // Check file contents for more accurate detection
    for (const file of files.filter((f) => f.endsWith(".py")).slice(0, 10)) {
      try {
        const content = fs.readFileSync(path.join(cwd, file), "utf8");
        if (/@db\.model/.test(content) || /from dataflow/.test(content))
          return "dataflow";
        if (/from nexus/.test(content) || /Nexus\(/.test(content))
          return "nexus";
        if (/from kaizen/.test(content) || /BaseAgent/.test(content))
          return "kaizen";
      } catch {}
    }

    // Fallback to filename detection
    if (fileList.includes("dataflow")) return "dataflow";
    if (fileList.includes("nexus")) return "nexus";
    if (fileList.includes("kaizen")) return "kaizen";

    return "core-sdk";
  } catch {
    return "unknown";
  }
}
