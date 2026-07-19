#!/usr/bin/env node
/*
 * Helper module for value-prioritization-ablation.test.mjs. Exports
 * `loadScenarios` and `makeFixtureSetup` so the unit-test layer
 * (tests/value-prioritization-probe-schema.test.mjs) can verify the
 * path-traversal defense-in-depth gates without invoking the runner's
 * top-level execution path (which would re-spawn the paid CC ablation
 * subprocess on import — the dynamic-`import()` lesson from PR #98).
 *
 * The runner imports these from here too. Single-source-of-truth for
 * (a) the scenarios.json schema validator (LAYER 1 path-traversal
 * gate), (b) the fixture-setup composer (LAYER 2 resolve-anchor
 * gate). Per security-reviewer MED-1 (PR #98 review): both layers
 * required for defense-in-depth.
 */

import fs from "node:fs";
import path from "node:path";

const RULE_BLOCK_RE = /<!-- VP_RULE_START -->[\s\S]*?<!-- VP_RULE_END -->\s*/;

export function loadScenarios(fixturesDir, fixtureName = "value-prioritization-ablation") {
  const p = path.join(fixturesDir, fixtureName, "scenarios.json");
  const raw = fs.readFileSync(p, "utf8");
  const parsed = JSON.parse(raw);
  // S1-S6 (anchor source d / literal-quote regression baseline) + S7-S10
  // (anchor sources a/b/c/e per F-1.5 / issue #86) + S11-S16 (anchor source
  // f per F-2.0 / issue #100 — Failure-A reproduction) + S17-S23 (anchor
  // source g per F-3.0 — caveat 3 + 5 isolation) + S24-S26 (anchor source h
  // per F-3.1 — MUST-6 verbatim-citation discipline; retests S18+S22
  // failure modes with the new clause in scope) = 26 expected. Keep a band
  // rather than an exact equality so the runner doesn't fight a single-
  // scenario dev edit.
  if (
    !Array.isArray(parsed.scenarios) ||
    parsed.scenarios.length < 6 ||
    parsed.scenarios.length > 30
  ) {
    throw new Error(
      `expected 6-30 scenarios at ${p}, got ${parsed.scenarios?.length ?? "non-array"}`,
    );
  }
  for (const s of parsed.scenarios) {
    // Always-required: id / axis / high_value_candidate / low_value_candidate / prompt.
    for (const k of [
      "id",
      "axis",
      "high_value_candidate",
      "low_value_candidate",
      "prompt",
    ]) {
      if (typeof s[k] !== "string" || !s[k]) {
        throw new Error(
          `scenario ${s.id ?? "?"}: missing or empty field "${k}"`,
        );
      }
    }
    // user_anchor_quote is REQUIRED for source-(d) scenarios (the literal
    // quote IS the anchor) and OPTIONAL for source-(a/b/c/e) scenarios
    // (the anchor is materialized into the fixture root via `materialize`).
    const sourceLetter = s.anchor_source ?? "d";
    if (sourceLetter === "d") {
      if (typeof s.user_anchor_quote !== "string" || !s.user_anchor_quote) {
        throw new Error(
          `scenario ${s.id}: anchor_source=d requires user_anchor_quote`,
        );
      }
    }
    // materialize is OPTIONAL; when present, MUST be array of {path, content}.
    if (s.materialize !== undefined) {
      if (!Array.isArray(s.materialize)) {
        throw new Error(`scenario ${s.id}: materialize must be an array`);
      }
      for (const f of s.materialize) {
        if (typeof f.path !== "string" || !f.path) {
          throw new Error(`scenario ${s.id}: materialize entry missing path`);
        }
        if (typeof f.content !== "string") {
          throw new Error(
            `scenario ${s.id}: materialize entry "${f.path}" missing string content`,
          );
        }
        // mode is OPTIONAL; defaults to "overwrite" (legacy behavior).
        // "append" preserves existing file content (e.g., harness baseline
        // CLAUDE.md with VP_RULE_START/END markers — F-3.0 S23 caveat 5
        // requires splice, not overwrite). When mode=append, the baseline
        // file MUST exist at materialize time or the runner errors loudly.
        if (f.mode !== undefined && f.mode !== "overwrite" && f.mode !== "append") {
          throw new Error(
            `scenario ${s.id}: materialize entry "${f.path}" has invalid mode "${f.mode}" (allowed: "overwrite", "append")`,
          );
        }
        // Defense-in-depth (LAYER 1): static rejection of obvious traversal.
        // Materialized files MUST land inside the fixture root, not somewhere
        // on the host fs.
        // Reject:
        //   - absolute paths           ("/etc/passwd")
        //   - leading parent ref       ("../foo")
        //   - mid-path parent ref      ("foo/../bar")
        //   - Windows separator        ("..\\..\\windows")  — not used by node
        //                                fs on POSIX, but catches authoring
        //                                mistakes that would resolve oddly if
        //                                the runner ever ran on Windows
        //   - URL-encoded traversal    ("%2e%2e/", "%2E%2E\\")  — node fs
        //                                does NOT decode %xx, but a fixture
        //                                consumer that did would see a
        //                                traversal escape; reject at the
        //                                authoring boundary
        //   - NUL byte                 ("foo\x00bar") — path-truncation
        //                                attack on legacy fs APIs
        // Layer 2 (the resolve-anchor check) runs in makeFixtureSetup and is
        // the load-bearing gate; this layer fails authoring loud at startup.
        if (/[\\\x00]/.test(f.path) || /%2e%2e|%2E%2E|%5c|%5C/.test(f.path)) {
          throw new Error(
            `scenario ${s.id}: materialize path "${f.path}" contains rejected character (backslash / NUL / URL-encoded traversal)`,
          );
        }
        const norm = path.posix.normalize(f.path);
        if (norm.startsWith("/") || norm.startsWith("..") || norm.includes("/../")) {
          throw new Error(
            `scenario ${s.id}: materialize path "${f.path}" escapes fixture root`,
          );
        }
      }
    }
  }
  return parsed.scenarios;
}

// Fixture setup. Two responsibilities:
//   1. Materialize per-scenario external resources declared via
//      scenario.materialize[] (BRIEF.md, briefs/<topic>.md, journal/<NNNN-
//      DECISION-...>.md, specs/<domain>.md). These are the user-anchored
//      sources (a/b/c/e) per rules/value-prioritization.md MUST-1's closed
//      allowlist; the agent reads them at runtime via cwd. Source (d)
//      scenarios have no `materialize` and inline the literal user quote
//      directly in the prompt.
//   2. For the "without-rule" variant, strip the rule body wrapped in
//      <!-- VP_RULE_START --> / <!-- VP_RULE_END --> markers from the base
//      fixture's CLAUDE.md so the agent's context is identical EXCEPT for
//      the rule's MUST clauses.
export function makeFixtureSetup(scenario, variant) {
  return (dst, fsArg, pathArg) => {
    // (1) Materialize scenario-declared files.
    if (Array.isArray(scenario.materialize)) {
      // Resolve dst once so the per-entry anchor check is cheap. Append
      // path.sep so a fixture path like "dst-evil" doesn't accidentally
      // pass startsWith("dst").
      const dstAnchor = pathArg.resolve(dst) + pathArg.sep;
      for (const f of scenario.materialize) {
        const target = pathArg.join(dst, f.path);
        // Defense-in-depth (LAYER 2 — load-bearing): regardless of what the
        // validator did, refuse to write outside dst. Catches anything the
        // static validator missed (decode quirks, separator confusion on
        // exotic filesystems, future fixture-author errors).
        const resolvedTarget = pathArg.resolve(target);
        if (!resolvedTarget.startsWith(dstAnchor)) {
          throw new Error(
            `setupFn: materialize path "${f.path}" resolves outside fixture root (${resolvedTarget} not in ${dstAnchor})`,
          );
        }
        fsArg.mkdirSync(pathArg.dirname(target), { recursive: true });
        const mode = f.mode === "append" ? "append" : "overwrite";
        if (mode === "append") {
          // append mode requires the baseline file to exist (otherwise the
          // splice contract is silently broken — the without-rule rule-strip
          // step downstream would fail because the baseline content + markers
          // are missing). Refuse loudly.
          if (!fsArg.existsSync(target)) {
            throw new Error(
              `setupFn: materialize path "${f.path}" requested mode=append but baseline file does not exist at ${target}`,
            );
          }
          fsArg.appendFileSync(target, f.content);
        } else {
          fsArg.writeFileSync(target, f.content);
        }
      }
    }
    // (2) Strip rule block for without-rule variant.
    if (variant === "without-rule") {
      const claudePath = pathArg.join(dst, "CLAUDE.md");
      const before = fsArg.readFileSync(claudePath, "utf8");
      if (!RULE_BLOCK_RE.test(before)) {
        throw new Error(
          `setupFn: VP_RULE_{START,END} markers missing from ${claudePath}; ` +
            `cannot strip rule for without-rule variant`,
        );
      }
      const after = before.replace(RULE_BLOCK_RE, "");
      fsArg.writeFileSync(claudePath, after);
    }
  };
}
