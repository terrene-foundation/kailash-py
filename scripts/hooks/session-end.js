#!/usr/bin/env node
/**
 * Hook: session-end
 * Event: SessionEnd
 * Purpose: Save session state for future resumption
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
    const result = saveSession(data);
    // SessionEnd hooks don't support hookSpecificOutput in schema
    console.log(JSON.stringify({ continue: true }));
    process.exit(0);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

function saveSession(data) {
  // Sanitize session_id to prevent path traversal
  const session_id = (data.session_id || "").replace(/[^a-zA-Z0-9_-]/g, "_");
  const cwd = data.cwd;
  const homeDir = process.env.HOME || process.env.USERPROFILE;
  const sessionDir = path.join(homeDir, ".claude", "sessions");
  const learningDir = path.join(homeDir, ".claude", "kailash-learning");

  // Ensure directories exist
  [sessionDir, learningDir].forEach((dir) => {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {}
  });

  // Collect session statistics
  const sessionData = {
    session_id,
    cwd,
    endedAt: new Date().toISOString(),
    stats: collectSessionStats(cwd),
  };

  try {
    // Save to session-specific file
    const sessionFile = path.join(sessionDir, `${session_id}.json`);
    fs.writeFileSync(sessionFile, JSON.stringify(sessionData, null, 2));

    // Save as last session for quick resume
    const lastSessionFile = path.join(sessionDir, "last-session.json");
    fs.writeFileSync(lastSessionFile, JSON.stringify(sessionData, null, 2));

    // Log observation for learning
    const observationsFile = path.join(learningDir, "observations.jsonl");
    const observation = {
      type: "session_end",
      session_id,
      cwd,
      timestamp: new Date().toISOString(),
    };
    fs.appendFileSync(observationsFile, JSON.stringify(observation) + "\n");

    // Clean up old sessions (keep last 20)
    cleanupOldSessions(sessionDir, 20);

    return { saved: true, path: sessionFile };
  } catch (error) {
    return { saved: false, error: error.message };
  }
}

function collectSessionStats(cwd) {
  try {
    const stats = {
      pythonFiles: 0,
      testFiles: 0,
      workflowFiles: 0,
    };

    const files = fs.readdirSync(cwd).filter((f) => f.endsWith(".py"));
    stats.pythonFiles = files.length;

    for (const file of files) {
      if (/_test\.py$|test_.*\.py$/.test(file)) {
        stats.testFiles++;
      }
      try {
        const content = fs.readFileSync(path.join(cwd, file), "utf8");
        if (/WorkflowBuilder/.test(content)) {
          stats.workflowFiles++;
        }
      } catch {}
    }

    return stats;
  } catch {
    return {};
  }
}

function cleanupOldSessions(sessionDir, keepCount) {
  try {
    const files = fs
      .readdirSync(sessionDir)
      .filter((f) => f.endsWith(".json") && f !== "last-session.json")
      .map((f) => ({
        name: f,
        path: path.join(sessionDir, f),
        mtime: fs.statSync(path.join(sessionDir, f)).mtime,
      }))
      .sort((a, b) => b.mtime - a.mtime);

    // Remove files beyond keepCount
    for (const file of files.slice(keepCount)) {
      try {
        fs.unlinkSync(file.path);
      } catch {}
    }
  } catch {}
}
