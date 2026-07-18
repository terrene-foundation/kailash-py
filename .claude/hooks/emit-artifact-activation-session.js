#!/usr/bin/env node
/**
 * emit-artifact-activation-session.js — loom#1209 (W1-b, activation-event PRODUCER, loom lane).
 *
 * PRODUCER of the ArtifactActivationEvent stream at the **session-start** lifecycle moment
 * (CLI-neutral; CC SessionStart ≈ Gemini `@hooks.session_start` ≈ Codex `session-init`). It
 * emits the two artifact types the pre-tool-use tool stream CANNOT observe:
 *
 *   - RULE (availability)  → the ALWAYS-ON rules loaded/active this session. observation_tier
 *                            = "availability": a rule being LOADED is observable at the hook
 *                            layer; a rule being APPLIED to a decision is a SEMANTIC act the hook
 *                            layer does NOT see (no tool call fires when an agent follows a rule).
 *                            So this event honestly attests availability at SESSION grain, NOT
 *                            per-application "firing". (The G2 residual for rules.) Path-scoped
 *                            rules inject later, on first matching-path touch — not observable
 *                            at session-start; documented in the G2 finding.
 *   - HOOK (self-report)   → this producer reports its OWN firing (one event/session), the clean,
 *                            low-noise demonstration that hook-firing is emittable + names the
 *                            hook via the shared recordHookFiring helper. Comprehensive per-hook
 *                            coverage = each hook opting into recordHookFiring (the G2 residual
 *                            for hooks: reliable-by-construction, wiring is opt-in).
 *
 * Severity: NEVER blocks. `{continue:true}` on every path (observability emitter, fail-open).
 * NO F101-2 DEPENDENCY — writes only to the artifact-activation staging sink.
 *
 * Origin: loom#1209.
 */

"use strict";

const TIMEOUT_MS = 5000;
// Armed inside main() ONLY — NOT at module top-level — so require()-ing this module for its
// exported pure functions (ruleScopeOf/enumerateAlwaysOnRules) in tests does not schedule a
// ref'd timer that hangs the test process. Mirrors emit-artifact-activation.js's discipline.
let fallback = null;

const fs = require("fs");
const path = require("path");
const PROJECT_DIR = process.env.CLAUDE_PROJECT_DIR || process.cwd();

const { readStdinBounded } = require("./lib/read-stdin-bounded.js");

const HOOK_NAME = "emit-artifact-activation-session";

function passthrough() {
  clearTimeout(fallback);
  try {
    process.stdout.write(JSON.stringify({ continue: true }) + "\n");
  } catch {}
  process.exit(0);
}

function resolveMainCheckoutSafely(repoDir) {
  try {
    const { resolveMainCheckout } = require(
      path.join(__dirname, "lib", "state-resolver.js"),
    );
    return resolveMainCheckout(repoDir);
  } catch {
    return repoDir;
  }
}

/**
 * Determine whether a rule file is ALWAYS-ON (loaded every session) vs PATH-SCOPED (injected
 * only on first matching-path touch, per rules/paths frontmatter). A rule is path-scoped iff its
 * YAML frontmatter carries a `paths:` key OR `scope: path-scoped`. Everything else is always-on.
 * Pure function of file text — testable, no IO in the classifier.
 *
 * @returns {"always-on" | "path-scoped"}
 */
function ruleScopeOf(fileText) {
  const text = typeof fileText === "string" ? fileText : "";
  // Extract the leading `--- … ---` frontmatter block, if any.
  const m = /^---\n([\s\S]*?)\n---/.exec(text);
  if (!m) return "always-on";
  const fm = m[1];
  if (/^\s*paths\s*:/m.test(fm)) return "path-scoped";
  if (/^\s*scope\s*:\s*path-scoped\s*$/m.test(fm)) return "path-scoped";
  return "always-on";
}

/**
 * Enumerate the always-on rule ids under `.claude/rules/`. The rule id is the basename without
 * `.md` (matching how detect-violations / the rule corpus reference rules). Best-effort: a
 * missing/unreadable rules dir yields []. Recurses one level into subdirs (e.g. rules/local/).
 */
function enumerateAlwaysOnRules(repoDir) {
  const rulesDir = path.join(repoDir, ".claude", "rules");
  const out = [];
  function walk(dir, depth) {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (depth < 1) walk(full, depth + 1);
      } else if (e.isFile() && e.name.endsWith(".md")) {
        let txt = "";
        try {
          txt = fs.readFileSync(full, "utf8");
        } catch {
          continue;
        }
        if (ruleScopeOf(txt) === "always-on") {
          out.push(e.name.replace(/\.md$/, ""));
        }
      }
    }
  }
  walk(rulesDir, 0);
  return out;
}

async function main() {
  fallback = setTimeout(() => {
    try {
      process.stdout.write(JSON.stringify({ continue: true }) + "\n");
    } catch {}
    process.exit(1);
  }, TIMEOUT_MS);
  try {
    const payload = await readStdinBounded().catch(() => ({}));
    const session = (payload && payload.session_id) || "unknown-session";
    const mainCheckout = resolveMainCheckoutSafely(PROJECT_DIR);
    const nowIso = new Date().toISOString();

    let ledger;
    try {
      ledger = require(
        path.join(__dirname, "lib", "artifact-activation-ledger.js"),
      );
    } catch {
      passthrough();
      return;
    }

    // (1) HOOK self-report — this producer's own firing (one event/session).
    try {
      ledger.recordHookFiring({
        repoDir: mainCheckout,
        hookName: HOOK_NAME,
        sessionId: session,
        lifecycleMoment: "session-start",
        nowIso,
      });
    } catch {}

    // (2) RULE availability — every always-on rule loaded this session.
    try {
      const rules = enumerateAlwaysOnRules(mainCheckout);
      for (const ruleId of rules) {
        ledger.emitArtifactActivation({
          repoDir: mainCheckout,
          artifactType: "rule",
          artifactId: ruleId,
          agentId: null, // session-grain availability — no dispatching agent
          sessionId: session,
          lifecycleMoment: "session-start",
          observationTier: "availability",
          nowIso,
        });
      }
    } catch {}

    passthrough();
  } catch {
    passthrough();
  }
}

if (require.main === module) {
  main();
}

module.exports = { ruleScopeOf, enumerateAlwaysOnRules };
