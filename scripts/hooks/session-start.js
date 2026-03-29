#!/usr/bin/env node
/**
 * Hook: session-start
 * Event: SessionStart
 * Purpose: Discover env config, validate model-key pairings, create .env if
 *          missing, inject session notes into Claude context, output model
 *          configuration prominently.
 *
 * Framework-agnostic — works with any Kailash project.
 *
 * Exit Codes:
 *   0 = success (continue)
 *   2 = blocking error (stop tool execution)
 *   other = non-blocking error (warn and continue)
 */

const fs = require("fs");
const path = require("path");
const {
  parseEnvFile,
  discoverModelsAndKeys,
  ensureEnvFile,
  buildCompactSummary,
} = require("./lib/env-utils");
const {
  resolveLearningDir,
  ensureLearningDir,
  logObservation: logLearningObservation,
} = require("./lib/learning-utils");
const {
  detectActiveWorkspace,
  derivePhase,
  getTodoProgress,
  findAllSessionNotes,
} = require("./lib/workspace-utils");
const { checkVersion } = require("./lib/version-utils");

// Timeout fallback — prevents hanging the Claude Code session
const TIMEOUT_MS = 10000;
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
    const result = initializeSession(data);
    const output = { continue: true };
    if (result.sessionNotesContext) {
      output.hookSpecificOutput = {
        hookEventName: "SessionStart",
        additionalContext: result.sessionNotesContext,
      };
    }
    console.log(JSON.stringify(output));
    process.exit(0);
  } catch (error) {
    console.error(`[HOOK ERROR] ${error.message}`);
    console.log(JSON.stringify({ continue: true }));
    process.exit(1);
  }
});

function initializeSession(data) {
  const result = { sessionNotesContext: null };
  const session_id = (data.session_id || "unknown").replace(
    /[^a-zA-Z0-9_-]/g,
    "_",
  );
  const cwd = data.cwd || process.cwd();
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

  // ── .env provision ────────────────────────────────────────────────────
  const envResult = ensureEnvFile(cwd);
  if (envResult.created) {
    console.error(
      `[ENV] Created .env from ${envResult.source}. Please fill in your API keys.`,
    );
  }

  // ── Parse .env ────────────────────────────────────────────────────────
  const envPath = path.join(cwd, ".env");
  const envExists = fs.existsSync(envPath);
  let env = {};
  let discovery = { models: {}, keys: {}, validations: [] };

  if (envExists) {
    env = parseEnvFile(envPath);
    discovery = discoverModelsAndKeys(env);
  }

  // ── Detect framework ──────────────────────────────────────────────────
  const framework = detectFramework(cwd);

  // ── Detect DataFlow pool config ─────────────────────────────────────
  const poolInfo = detectPoolConfig(cwd);
  if (poolInfo.isPostgresql) {
    if (poolInfo.hasPoolOverride) {
      console.error(
        "[DataFlow] Pool size override detected (DATAFLOW_POOL_SIZE). Auto-scaling disabled.",
      );
    } else {
      console.error(
        "[DataFlow] Pool auto-scaling active. Override with DATAFLOW_POOL_SIZE=N if needed.",
      );
    }
  }

  // ── Log observation ───────────────────────────────────────────────────
  try {
    const observationsFile = path.join(learningDir, "observations.jsonl");
    fs.appendFileSync(
      observationsFile,
      JSON.stringify({
        type: "session_start",
        session_id,
        cwd,
        timestamp: new Date().toISOString(),
        envExists,
        framework,
        models: discovery.models,
        keyCount: Object.keys(discovery.keys).length,
        validationFailures: discovery.validations
          .filter((v) => v.status === "MISSING_KEY")
          .map((v) => v.message),
      }) + "\n",
    );
  } catch {}

  // ── Version check (human-facing, stderr only) ─────────────────────────
  try {
    const versionResult = checkVersion(cwd);
    for (const msg of versionResult.messages) {
      console.error(msg);
    }
  } catch {}

  // ── Output workspace status (human-facing, stderr only) ──────────────
  try {
    const ws = detectActiveWorkspace(cwd);
    if (ws) {
      const phase = derivePhase(ws.path, cwd);
      const todos = getTodoProgress(ws.path);
      console.error(
        `[WORKSPACE] ${ws.name} | Phase: ${phase} | Todos: ${todos.active} active / ${todos.completed} done`,
      );
    }
  } catch {}

  // ── Session notes (inject into Claude context + human-facing stderr) ─
  try {
    const allNotes = findAllSessionNotes(cwd);
    if (allNotes.length > 0) {
      for (const note of allNotes) {
        const staleTag = note.stale ? " (STALE)" : "";
        const label = note.workspace ? ` [${note.workspace}]` : " [root]";
        console.error(
          `[SESSION-NOTES]${label} ${note.relativePath}${staleTag} — updated ${note.age}`,
        );
      }

      // Build context for Claude — include all non-stale notes, or latest if all stale
      const contextParts = [];
      for (const note of allNotes) {
        const label = note.workspace ? `[${note.workspace}]` : "[root]";
        const staleMark = note.stale ? " (STALE — may be outdated)" : "";
        contextParts.push(
          `## Session Notes ${label}${staleMark} — updated ${note.age}\n\n${note.content}`,
        );
      }
      if (contextParts.length > 0) {
        result.sessionNotesContext =
          "# Previous Session Notes\n\nRead these to understand where the last session left off.\n\n" +
          contextParts.join("\n\n---\n\n");
      }
    }
  } catch {}

  // ── Package freshness & version consistency check ───────────────────
  try {
    checkPythonPackageFreshness(cwd);
  } catch (e) {
    console.error(`[FRESHNESS] Check failed: ${e.message}`);
  }

  // ── Output model/key summary ──────────────────────────────────────────
  if (envExists) {
    const summary = buildCompactSummary(env, discovery);
    console.error(`[ENV] ${summary}`);

    // Detail each model-key validation
    for (const v of discovery.validations) {
      const icon = v.status === "ok" ? "✓" : "✗";
      console.error(`[ENV]   ${icon} ${v.message}`);
    }

    // Prominent warnings for missing keys
    const failures = discovery.validations.filter(
      (v) => v.status === "MISSING_KEY",
    );
    if (failures.length > 0) {
      console.error(
        `[ENV] WARNING: ${failures.length} model(s) configured without API keys!`,
      );
      console.error(
        "[ENV] LLM operations WILL FAIL. Add missing keys to .env.",
      );
    }
  } else {
    console.error(
      "[ENV] No .env file found. API keys and models not configured.",
    );
  }

  return result;
}

/**
 * Check version consistency across pyproject.toml and __init__.py for all packages.
 * Also check COC sync freshness for USE repos.
 */
function checkPythonPackageFreshness(cwd) {
  // Check all packages for version consistency
  const packageDirs = [
    {
      name: "kailash",
      pyproject: "pyproject.toml",
      init: "src/kailash/__init__.py",
    },
  ];

  // Also check packages/ subdirectories
  const packagesDir = path.join(cwd, "packages");
  if (fs.existsSync(packagesDir)) {
    try {
      const subDirs = fs.readdirSync(packagesDir);
      for (const sub of subDirs) {
        const subPath = path.join(packagesDir, sub);
        const pyproject = path.join(subPath, "pyproject.toml");
        if (fs.existsSync(pyproject)) {
          // Find the __init__.py
          const srcDir = path.join(subPath, "src");
          if (fs.existsSync(srcDir)) {
            try {
              const srcSubs = fs.readdirSync(srcDir);
              for (const s of srcSubs) {
                const initPath = path.join(srcDir, s, "__init__.py");
                if (fs.existsSync(initPath)) {
                  packageDirs.push({
                    name: sub,
                    pyproject: path.join("packages", sub, "pyproject.toml"),
                    init: path.join("packages", sub, "src", s, "__init__.py"),
                  });
                }
              }
            } catch {}
          }
        }
      }
    } catch {}
  }

  let mismatches = 0;
  for (const pkg of packageDirs) {
    try {
      const pyprojectPath = path.join(cwd, pkg.pyproject);
      const initPath = path.join(cwd, pkg.init);

      if (!fs.existsSync(pyprojectPath) || !fs.existsSync(initPath)) continue;

      const pyproject = fs.readFileSync(pyprojectPath, "utf8");
      const init = fs.readFileSync(initPath, "utf8");

      const pyVersionMatch = pyproject.match(/version\s*=\s*"([^"]+)"/);
      const initVersionMatch = init.match(/__version__\s*=\s*"([^"]+)"/);

      if (pyVersionMatch && initVersionMatch) {
        if (pyVersionMatch[1] !== initVersionMatch[1]) {
          console.error(
            `[FRESHNESS] VERSION MISMATCH in ${pkg.name}: ` +
              `pyproject.toml=${pyVersionMatch[1]}, __init__.py=${initVersionMatch[1]}. ` +
              `Update __init__.py before release!`,
          );
          mismatches++;
        }
      } else if (pyVersionMatch && !initVersionMatch) {
        console.error(
          `[FRESHNESS] ${pkg.name}: __init__.py missing __version__. ` +
            `Add __version__ = "${pyVersionMatch[1]}" to ${pkg.init}`,
        );
        mismatches++;
      }
    } catch {}
  }

  if (mismatches === 0) {
    console.error(`[FRESHNESS] All package versions consistent`);
  } else {
    console.error(
      `[FRESHNESS] ${mismatches} version mismatch(es) found — FIX BEFORE RELEASE`,
    );
  }

  // Check COC sync freshness (for USE repos that have a sync marker)
  const markerPath = path.join(cwd, ".claude", ".coc-sync-marker");
  if (fs.existsSync(markerPath)) {
    try {
      const marker = JSON.parse(fs.readFileSync(markerPath, "utf8").trim());
      if (marker.synced_at) {
        const daysSince =
          (Date.now() - new Date(marker.synced_at).getTime()) /
          (1000 * 60 * 60 * 24);
        if (daysSince > 7) {
          console.error(
            `[COC-SYNC] WARNING: COC sync is ${Math.floor(daysSince)} days old. ` +
              `Run COC sync to get latest agents, skills, and rules.`,
          );
        } else {
          console.error(`[COC-SYNC] Last synced: ${marker.synced_at}`);
        }
      }
    } catch {}
  }
}

function detectFramework(cwd) {
  try {
    const files = fs.readdirSync(cwd);
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
    return "core-sdk";
  } catch {
    return "unknown";
  }
}

function detectPoolConfig(cwd) {
  const result = { isPostgresql: false, hasPoolOverride: false };
  try {
    const envPath = path.join(cwd, ".env");
    if (!fs.existsSync(envPath)) return result;
    const content = fs.readFileSync(envPath, "utf8");
    const lines = content.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const eqIndex = trimmed.indexOf("=");
      const key = trimmed.slice(0, eqIndex).trim();
      const value = trimmed
        .slice(eqIndex + 1)
        .trim()
        .replace(/^["']|["']$/g, "");
      if (
        (key === "DATABASE_URL" || key === "DATAFLOW_DATABASE_URL") &&
        (/postgresql/i.test(value) || /postgres/i.test(value))
      ) {
        result.isPostgresql = true;
      }
      if (key === "DATAFLOW_POOL_SIZE" && value.length > 0) {
        result.hasPoolOverride = true;
      }
    }
  } catch {}
  return result;
}
