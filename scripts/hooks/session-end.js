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
const {
  resolveLearningDir,
  ensureLearningDir,
  logObservation: logLearningObservation,
  countObservations,
} = require("./lib/learning-utils");

// Timeout fallback — prevents hanging the Claude Code session
const TIMEOUT_MS = 15000;
const _timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  try {
    const data = JSON.parse(input);
    saveSession(data);
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
  const learningDir = resolveLearningDir(cwd);

  // Ensure directories exist
  [sessionDir].forEach((dir) => {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {}
  });
  ensureLearningDir(cwd);

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

    // Log enriched session_summary observation for learning
    logLearningObservation(
      cwd,
      "session_summary",
      {
        file_counts: sessionData.stats,
        framework: detectFramework(cwd),
        duration_estimate: estimateSessionDuration(session_id, sessionDir),
      },
      {
        session_id,
      },
    );

    // --- Log session accomplishments from .session-notes ---
    try {
      logSessionAccomplishments(cwd, session_id);
    } catch {}

    // --- Log journal decisions created this session ---
    try {
      logDecisionReferences(cwd, session_id, sessionDir);
    } catch {}

    // --- Build learning digest (replaces instinct pipeline) ---
    try {
      buildLearningDigest(cwd, learningDir);
    } catch {}

    // Clean up old sessions (keep last 20)
    cleanupOldSessions(sessionDir, 20);

    return { saved: true, path: sessionFile };
  } catch (error) {
    return { saved: false, error: error.message };
  }
}

// Scans top-level cwd only (not subdirectories) for performance in hooks.
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

// Scans top-level cwd only (not subdirectories) for performance in hooks.
function detectFramework(cwd) {
  try {
    const files = fs.readdirSync(cwd).filter((f) => f.endsWith(".py"));
    for (const file of files.slice(0, 10)) {
      try {
        const content = fs.readFileSync(path.join(cwd, file), "utf8");
        if (/@db\.model/.test(content) || /from dataflow/.test(content))
          return "dataflow";
        if (/from nexus/.test(content) || /Nexus\(/.test(content))
          return "nexus";
        if (/from kaizen/.test(content) || /BaseAgent/.test(content))
          return "kaizen";
        if (/WorkflowBuilder/.test(content)) return "core-sdk";
      } catch {}
    }
    return "core-sdk";
  } catch {
    return "unknown";
  }
}

function estimateSessionDuration(sessionId, sessionDir) {
  try {
    // Check if there's a session start timestamp from the session file
    const sessionFile = path.join(sessionDir, `${sessionId}.json`);
    if (fs.existsSync(sessionFile)) {
      const data = JSON.parse(fs.readFileSync(sessionFile, "utf8"));
      if (data.startedAt) {
        const start = new Date(data.startedAt).getTime();
        const end = Date.now();
        return Math.round((end - start) / 1000); // seconds
      }
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Log session accomplishments from .session-notes file.
 * Parses the "Accomplished" or "Completed" section if it exists.
 */
function logSessionAccomplishments(cwd, sessionId) {
  // Check multiple possible locations for session notes
  const candidates = [
    path.join(cwd, ".session-notes"),
    path.join(cwd, "workspaces"),
  ];

  // Direct .session-notes file
  const notesPath = candidates[0];
  if (fs.existsSync(notesPath)) {
    const stat = fs.statSync(notesPath);
    const ageHours = (Date.now() - stat.mtimeMs) / (1000 * 60 * 60);
    // Only log if modified recently (within last 4 hours = likely this session)
    if (ageHours > 4) return;

    const content = fs.readFileSync(notesPath, "utf8");
    const accomplishments = extractAccomplishments(content);
    if (accomplishments) {
      logLearningObservation(
        cwd,
        "session_accomplishment",
        { accomplishments: accomplishments.substring(0, 1000) },
        { session_id: sessionId },
      );
    }
    return;
  }

  // Check workspace session notes
  const wsDir = candidates[1];
  if (!fs.existsSync(wsDir)) return;

  try {
    const workspaces = fs.readdirSync(wsDir);
    for (const ws of workspaces) {
      const wsNotes = path.join(wsDir, ws, ".session-notes");
      if (!fs.existsSync(wsNotes)) continue;

      const stat = fs.statSync(wsNotes);
      const ageHours = (Date.now() - stat.mtimeMs) / (1000 * 60 * 60);
      if (ageHours > 4) continue;

      const content = fs.readFileSync(wsNotes, "utf8");
      const accomplishments = extractAccomplishments(content);
      if (accomplishments) {
        logLearningObservation(
          cwd,
          "session_accomplishment",
          {
            workspace: ws,
            accomplishments: accomplishments.substring(0, 1000),
          },
          { session_id: sessionId },
        );
      }
    }
  } catch {}
}

/**
 * Extract the "Accomplished" section from session notes markdown.
 */
function extractAccomplishments(content) {
  // Match ## Accomplished, ### Accomplished, or similar headings
  const match = content.match(
    /^#{1,4}\s*(?:Accomplished|Completed|Done|What was done)\s*\n([\s\S]*?)(?=\n#{1,4}\s|\n---|\Z)/im,
  );
  if (match && match[1].trim().length > 0) {
    return match[1].trim();
  }
  return null;
}

/**
 * Log journal entries created during this session as decision references.
 */
function logDecisionReferences(cwd, sessionId, sessionDir) {
  const journalDir = path.join(cwd, "journal");
  if (!fs.existsSync(journalDir)) return;

  // Determine session start time
  let sessionStartMs = Date.now() - 4 * 60 * 60 * 1000; // default: 4 hours ago
  try {
    const sessionFile = path.join(sessionDir, `${sessionId}.json`);
    if (fs.existsSync(sessionFile)) {
      const data = JSON.parse(fs.readFileSync(sessionFile, "utf8"));
      if (data.startedAt) {
        sessionStartMs = new Date(data.startedAt).getTime();
      }
    }
  } catch {}

  try {
    const entries = fs.readdirSync(journalDir).filter((f) => f.endsWith(".md"));
    for (const entry of entries) {
      const entryPath = path.join(journalDir, entry);
      const stat = fs.statSync(entryPath);
      // Only log entries created/modified during this session
      if (stat.mtimeMs < sessionStartMs) continue;

      // Parse type from filename: NNNN-TYPE-topic.md
      const match = entry.match(/^\d+-(\w+)-(.+)\.md$/);
      if (!match) continue;

      logLearningObservation(
        cwd,
        "decision_reference",
        {
          type: match[1], // DECISION, DISCOVERY, TRADE-OFF, etc.
          topic: match[2].replace(/-/g, " "),
          file: entry,
        },
        { session_id: sessionId },
      );
    }
  } catch {}
}

/**
 * Build learning digest from observations.
 * Produces learning-digest.json — a structured summary consumed by /codify.
 * Pure file I/O, no LLM calls. Semantic analysis happens in /codify.
 */
function buildLearningDigest(cwd, learningDir) {
  const observationCount = countObservations(learningDir);
  if (observationCount < 5) return;

  try {
    const digestBuilder = require("../learning/digest-builder");
    digestBuilder.buildDigest(cwd, learningDir);
  } catch {}
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
