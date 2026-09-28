#!/usr/bin/env node
/**
 * Native Codex hook adapter. The registration resolves this file from the Git
 * root because Codex starts commands in the session cwd, possibly a subfolder.
 * Resolve repo-relative target paths from this installed wrapper, not from cwd
 * or an inherited project-directory variable. Run the child at that root while
 * preserving the original stdin payload (including the session cwd).
 *
 * COC_RUNTIME and CLAUDE_PROJECT_DIR are adapter-owned. The native child keeps
 * require.main behavior and stdin/stdout/stderr delivery. Exit statuses pass
 * through; missing/non-file targets, spawn errors and signals exit 2. A hook's
 * own exit 1 remains non-blocking except for the Bash validator: unexpected
 * validator exits and its bounded deadline deny the unchecked command.
 * This wrapper cannot
 * enforce anything if it is absent, untrusted, disabled, or never matched.
 * See https://learn.chatgpt.com/docs/hooks (2026-09-28).
 */

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

// Fail-closed exit code for wrapper-level delegation failures. 2 is the
// PreToolUse block contract shared by validate-bash-command.js — the strongest
// fail-closed posture on the git-safety lane.
const FAIL_CLOSED_EXIT = 2;

function failClosed(message) {
  // Synchronous write (fs.writeSync, not process.stderr.write): on a pipe the
  // async stderr write can be dropped when process.exit() terminates before the
  // flush — losing the block diagnostic Codex feeds back to the agent. The exit
  // code (the block itself) is always preserved; this preserves the WHY too.
  try {
    fs.writeSync(2, `[codex-hook-runtime] ${message}\n`);
  } catch {
    // stderr fd unwritable (closed pipe) — the exit-2 block still stands.
  }
  process.exit(FAIL_CLOSED_EXIT);
}

function dispatch() {
  const targetArg = process.argv[2];
  const forwardedArgs = process.argv.slice(3);

  if (!targetArg) {
    failClosed(
      "no target hook path given (usage: node codex-hook-runtime.js <target-hook.js> [args...])",
    );
  }

  const projectRoot = fs.realpathSync(path.resolve(__dirname, "../../.."));
  let resolvedTarget = path.resolve(projectRoot, targetArg);
  // isFile(), not existsSync(): a DIRECTORY (or any non-file) target passes an
  // existence check, but `node <dir>` exits 1 (MODULE_NOT_FOUND) — non-blocking =
  // fail-OPEN on the git-safety lane. Stat and require a regular file so a
  // misconfigured hooks.json entry fails CLOSED (exit 2), not open.
  let targetStat = null;
  try {
    resolvedTarget = fs.realpathSync(resolvedTarget);
    targetStat = fs.statSync(resolvedTarget);
  } catch {
    targetStat = null; // ENOENT etc. → not found → fail closed below (never open)
  }
  if (!targetStat) {
    failClosed(
      `target hook not found: ${targetArg} (resolved ${resolvedTarget})`,
    );
  }
  if (!targetStat.isFile()) {
    // A directory (or socket/fifo) passes an existence check, but `node <dir>`
    // exits 1 (MODULE_NOT_FOUND) — non-blocking = fail-OPEN on the git-safety lane.
    failClosed(
      `target hook is not a regular file: ${targetArg} (resolved ${resolvedTarget})`,
    );
  }

  // Child deadlines are separate from the native 30s registration budget.
  // Native zsh diagnosis (2026-09-28): Node startup took ~4950ms; the same
  // sentinel with isolated empty shell startup took ~693ms. Preserve normal
  // shell initialization and leave outer margin instead of weakening it.
  // A JavaScript timer inside a hook cannot preempt synchronous hook work.
  // Resolve both sides of role classification through the same resolver.
  // Aliases (including a registered symlink to an external file) retain their
  // role. This is identity classification, not a filesystem containment fence;
  // canonicalization does not prevent a subsequent check-to-use path swap.
  const matchingHooks = [
    ["validate-bash-command.js", 4000, true],
    ["integration-hygiene.js", 10000, false],
    ["session-start.js", 20000, false],
  ].filter(([name]) => {
    try {
      return fs.realpathSync(path.join(projectRoot, ".claude/hooks", name)) === resolvedTarget;
    } catch (error) {
      // Generic dispatch is supported even when unrelated known hooks are absent.
      if (error.code === "ENOENT" || error.code === "ENOTDIR") return false;
      throw error;
    }
  });
  // If registrations share one physical file, retain the strictest deadline
  // and the validator role instead of letting a later entry overwrite them.
  const childDeadlineMs = matchingHooks.length
    ? Math.min(...matchingHooks.map(([, deadline]) => deadline))
    : undefined;
  const isValidator = matchingHooks.some(([, , validator]) => validator);

  const result = spawnSync(process.execPath, [resolvedTarget, ...forwardedArgs], {
    cwd: projectRoot,
    timeout: childDeadlineMs,
    // spawnSync otherwise waits indefinitely if a timed-out child ignores
    // SIGTERM. Known bounded hooks must terminate before the outer deadline.
    killSignal: childDeadlineMs === undefined ? undefined : "SIGKILL",
    // Transparent passthrough: the child reads the hook JSON from the wrapper's
    // own stdin and writes stdout/stderr straight back to Codex.
    stdio: "inherit",
    // Pin the root of this installed adapter, even if the parent process has
    // a CLAUDE_PROJECT_DIR belonging to a different checkout.
    env: {
      ...process.env,
      COC_RUNTIME: "codex",
      CLAUDE_PROJECT_DIR: projectRoot,
    },
  });

  if (result.error) {
    if (result.error.code === "ETIMEDOUT") {
      failClosed(`hook child timed out after ${childDeadlineMs}ms`);
    }
    // Spawn itself failed (e.g. node not found on PATH). Fail closed.
    failClosed(`failed to spawn target hook: ${String(result.error)}`);
  }

  if (result.status === null) {
    // Killed by a signal (no exit code). Fail closed rather than assume success.
    failClosed(
      `target hook terminated by signal ${result.signal || "unknown"} with no exit code`,
    );
  }

  if (isValidator &&
      result.status !== 0 && result.status !== 2) {
    failClosed("Bash validation could not complete; command was not validated.");
  }
  // Other hooks retain their native warning and exit semantics.
  process.exit(result.status);
}

// Top-level fail-closed guard: any UNEXPECTED internal throw (e.g. process.cwd()
// raising ENOENT if the working directory is unlinked mid-hook) MUST fail closed
// (exit 2), never surface as an uncaught exception → node exit 1 = fail-OPEN on the
// git-safety lane. This completes the fail-closed contract to cover ANY internal
// error, not only the three wrapper-interceptable modes documented above.
// (process.exit does not throw, so the normal fail-closed / passthrough exits inside
// dispatch() terminate before this catch and are never intercepted by it.)
function main() {
  try {
    dispatch();
  } catch (e) {
    failClosed(`internal wrapper error: ${String(e)}`);
  }
}

main();
