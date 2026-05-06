#!/usr/bin/env node
/**
 * Hook: validate-prod-deploy
 * Event: PreToolUse
 * Matcher: Bash
 * Purpose: Block direct production deployment commands unless staging has passed.
 *
 * Intercepts Bash commands that touch production Docker containers and
 * requires .staging-passed to exist with the current git HEAD commit.
 *
 * To use this hook, register it in .claude/settings.json under PreToolUse:Bash.
 * See deploy/scripts/ for the stage.sh and deploy.sh that write/read the marker.
 *
 * Exit Codes:
 *   0 = allow (command is safe or staging verified)
 *   2 = block (direct production deploy without staging)
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  // Timeout = allow (fail-open to avoid blocking all Bash commands)
  process.exit(0);
}, TIMEOUT_MS);

async function main() {
  try {
    const input = JSON.parse(fs.readFileSync("/dev/stdin", "utf8"));
    const toolName = input.tool_name;
    const toolInput = input.tool_input || {};
    const command = toolInput.command || "";

    // Only check Bash commands
    if (toolName !== "Bash") {
      clearTimeout(timeout);
      process.exit(0);
      return;
    }

    // Patterns that indicate production deployment
    // Projects should add their own container name patterns below.
    const PROD_PATTERNS = [
      // Generic docker compose prod file patterns
      /docker.*compose.*prod.*up/i,
      /docker.*compose.*prod.*build/i,
      /docker.*compose.*prod.*restart/i,
      /docker.*compose.*-f.*docker-compose\.prod/i,
      // bare docker restart (single container restarts bypass compose)
      /docker\s+restart\s+\S+/,
      // SSH to production server running docker compose
      /ssh\s+.*docker\s+(compose|stack)/i,
    ];

    // Patterns that are always allowed (read-only, logs, status, dev scripts)
    const SAFE_PATTERNS = [
      /docker.*logs/i,
      /docker.*ps/i,
      /docker.*inspect/i,
      /docker.*images/i,
      /docker\s+exec/i,
      /git\s+(pull|log|status|diff)/i,
      /curl/i,
      /cat|grep|head|tail|ls/,
      /deploy\/scripts\/stage\.sh/,
      /deploy\/scripts\/promote\.sh/,
      /deploy\/scripts\/dev\.sh/,
      /docker.*compose.*dev.*up/i,
      /docker.*compose.*staging.*up/i,
    ];

    // Check safe patterns first — if command is clearly safe, allow immediately
    for (const safe of SAFE_PATTERNS) {
      if (safe.test(command)) {
        clearTimeout(timeout);
        process.exit(0);
        return;
      }
    }

    // Check if command matches a production deploy pattern
    let isProductionDeploy = false;
    for (const pattern of PROD_PATTERNS) {
      if (pattern.test(command)) {
        isProductionDeploy = true;
        break;
      }
    }

    if (!isProductionDeploy) {
      clearTimeout(timeout);
      process.exit(0);
      return;
    }

    // Skip-staging escape hatch — allow but warn loudly
    if (command.includes("--skip-staging")) {
      console.error(
        "\n" +
          "[DEPLOY HOOK] WARNING: --skip-staging detected.\n" +
          "[DEPLOY HOOK] Allowing direct production deploy WITHOUT staging verification.\n" +
          "[DEPLOY HOOK] You MUST document the reason in deploy/deployment-config.md.\n",
      );
      clearTimeout(timeout);
      process.exit(0);
      return;
    }

    // Locate repo root by walking up from cwd or script location
    let repoRoot;
    try {
      repoRoot = execSync("git rev-parse --show-toplevel", {
        encoding: "utf8",
        timeout: 3000,
      }).trim();
    } catch {
      // Not in a git repo or git unavailable — fail open
      clearTimeout(timeout);
      process.exit(0);
      return;
    }

    const markerPath = path.join(repoRoot, ".staging-passed");

    // Check that .staging-passed exists
    if (!fs.existsSync(markerPath)) {
      console.error(
        "\n" +
          "╔══════════════════════════════════════════════════════════╗\n" +
          "║  BLOCKED: Production deploy without staging             ║\n" +
          "║                                                          ║\n" +
          "║  Run staging first:                                      ║\n" +
          "║    bash deploy/scripts/promote.sh                        ║\n" +
          "║                                                          ║\n" +
          "║  Or step-by-step on the server:                          ║\n" +
          "║    bash deploy/scripts/stage.sh                          ║\n" +
          "║    bash deploy/scripts/deploy.sh                         ║\n" +
          "║                                                          ║\n" +
          "║  Emergency bypass (document the reason afterward):       ║\n" +
          "║    Add --skip-staging to your command                    ║\n" +
          "╚══════════════════════════════════════════════════════════╝\n",
      );
      clearTimeout(timeout);
      process.exit(2); // Block
      return;
    }

    // Verify that .staging-passed contains the current commit
    const marker = fs.readFileSync(markerPath, "utf8").trim();
    let currentCommit;
    try {
      currentCommit = execSync("git rev-parse HEAD", {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 3000,
      }).trim();
    } catch {
      // Can't determine current commit — fail open rather than block legitimate work
      clearTimeout(timeout);
      process.exit(0);
      return;
    }

    const shortHash = currentCommit.substring(0, 7);
    if (!marker.includes(shortHash)) {
      console.error(
        "\n" +
          "╔══════════════════════════════════════════════════════════╗\n" +
          "║  BLOCKED: Staging marker is stale                        ║\n" +
          "║                                                          ║\n" +
          "║  Code has changed since staging last passed.             ║\n" +
          `║  Current commit: ${shortHash.padEnd(42)}║\n` +
          `║  Staging marker: ${marker.substring(0, 7).padEnd(42)}║\n` +
          "║                                                          ║\n" +
          "║  Re-run staging:                                         ║\n" +
          "║    bash deploy/scripts/promote.sh                        ║\n" +
          "╚══════════════════════════════════════════════════════════╝\n",
      );
      clearTimeout(timeout);
      process.exit(2); // Block
      return;
    }

    // Staging verified and current — allow production deploy
    console.error(
      `[DEPLOY HOOK] Staging verified (${shortHash}). Allowing production deploy.`,
    );
    clearTimeout(timeout);
    process.exit(0);
  } catch (err) {
    // Parse error or unexpected failure — fail open to avoid blocking legitimate work
    clearTimeout(timeout);
    process.exit(0);
  }
}

main();
