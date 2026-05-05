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
 * Severity: block (per `hooks/lib/instruct-and-wait.js`).
 * Genuine safety block — direct production deploys without staging verification
 * are unrecoverable in the worst case (broken prod, no rollback marker). The
 * --skip-staging escape hatch + deploy/scripts/promote.sh are the documented
 * paths around the block.
 *
 * Output shape: routes through instructAndWait so the agent receives the
 * canonical WHAT HAPPENED / WHY / REPORT TO USER / THEN structure (loom
 * 2026-05-05 hook redesign) instead of just stderr boxes the user sees but
 * the agent has to interpret without context.
 *
 * Exit Codes:
 *   0 = allow (command is safe or staging verified)
 *   2 = block (direct production deploy without staging)
 */

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { instructAndWait } = require("./lib/instruct-and-wait");

const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  // Timeout = allow (fail-open to avoid blocking all Bash commands)
  process.exit(0);
}, TIMEOUT_MS);

function emitBlock({ what, why, report, wait, summary }) {
  const out = instructAndWait({
    hookEvent: "PreToolUse",
    severity: "block",
    what_happened: what,
    why,
    agent_must_report: report,
    agent_must_wait: wait,
    user_summary: summary,
  });
  console.log(JSON.stringify(out.json));
  process.exit(out.exitCode);
}

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

    // Skip-staging escape hatch — allow but warn loudly to stderr (user-visible)
    if (command.includes("--skip-staging")) {
      process.stderr.write(
        "[DEPLOY HOOK] WARNING: --skip-staging detected. " +
          "Allowing direct production deploy WITHOUT staging verification. " +
          "Document the reason in deploy/deployment-config.md.\n",
      );
      clearTimeout(timeout);
      process.exit(0);
      return;
    }

    // Locate repo root by walking up from cwd or script location
    let repoRoot;
    try {
      repoRoot = execFileSync("git", ["rev-parse", "--show-toplevel"], {
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

    // Block 1: .staging-passed marker missing
    if (!fs.existsSync(markerPath)) {
      clearTimeout(timeout);
      emitBlock({
        what: `Production deploy attempted without staging verification: ${command.slice(0, 120)}`,
        why: "deploy/deployment-config.md — .staging-passed marker is the deploy gate; no marker = no proof staging passed for the current commit",
        report: [
          "Quote the exact deploy command that was attempted",
          "Run staging first: `bash deploy/scripts/promote.sh` (which runs stage + deploy together) — OR step-by-step: `bash deploy/scripts/stage.sh` then `bash deploy/scripts/deploy.sh`",
          "Emergency bypass (document the reason afterward in deploy/deployment-config.md): add `--skip-staging` to the command",
          "Confirm whether the user explicitly authorized direct prod deploy IN THIS CONVERSATION",
        ],
        wait: "Do not retry the deploy command. Run staging first OR get explicit user authorization for --skip-staging.",
        summary: "production deploy blocked — staging not passed",
      });
      return;
    }

    // Verify that .staging-passed contains the current commit
    const marker = fs.readFileSync(markerPath, "utf8").trim();
    let currentCommit;
    try {
      currentCommit = execFileSync("git", ["rev-parse", "HEAD"], {
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
      const markerHash = marker.substring(0, 7);
      clearTimeout(timeout);
      emitBlock({
        what: `Production deploy attempted with stale staging marker: ${command.slice(0, 80)}`,
        why: `deploy/deployment-config.md — current commit ${shortHash} does not match staging marker ${markerHash}; code has changed since staging last passed`,
        report: [
          `Current commit: ${shortHash}`,
          `Staging marker:  ${markerHash}`,
          "Re-run staging against the current commit: `bash deploy/scripts/promote.sh`",
          "OR step-by-step on the server: `bash deploy/scripts/stage.sh` then `bash deploy/scripts/deploy.sh`",
          "Confirm the marker mismatch is not a sync/branch issue (e.g., wrong git branch checked out at deploy time)",
        ],
        wait: "Do not retry the deploy. Re-run staging or investigate the marker mismatch.",
        summary: `production deploy blocked — stale staging marker (${markerHash} vs ${shortHash})`,
      });
      return;
    }

    // Staging verified and current — allow production deploy
    process.stderr.write(
      `[DEPLOY HOOK] Staging verified (${shortHash}). Allowing production deploy.\n`,
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
