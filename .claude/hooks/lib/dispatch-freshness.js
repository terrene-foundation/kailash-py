#!/usr/bin/env node
/**
 * dispatch-freshness.js — the Dispatch-Freshness Precondition predicate.
 *
 * Answers ONE question, once, before a wave of parallel agents is cut: how stale is the base
 * they will all share?
 *
 * WHY THIS LIVES AT DISPATCH AND NOT INSIDE AN AGENT
 * --------------------------------------------------
 * Measured incident (2026-09-12/13): a 32-lane wave executed against a tree whose tip was dated
 * 2026-08-19 — 25 days and 3,850 commits behind trunk. 53 of its 134 issues (40%) had closed in
 * the interim; ALL 53 closed AFTER the snapshot date and NONE before. ~40% of the wave's output
 * was unactionable, and one lane recommended closing an issue that had closed as COMPLETED three
 * weeks earlier.
 *
 * Every lane measured its own tree CORRECTLY. `git status` was clean, `git log` showed real
 * commits, every file was present — and every file was superseded. Staleness is not a property of
 * any lane; it is a property of the BASE they were all cut from, which is decided once, by the
 * orchestrator, before the first lane exists. A stale tree is indistinguishable from a fresh one
 * by inspection: presence of a file says nothing about its version. So a per-agent reminder cannot
 * work — not because agents ignore it, but because the agent is the wrong OBSERVER.
 *
 * That clean 0/53 split is also the diagnosis: the issue list was perfectly consistent WITH the
 * snapshot, so nothing inside the wave looked wrong. Internal consistency is what stale state
 * feels like from the inside.
 *
 * THE PREDICATE — one command, NO NETWORK
 * ----------------------------------------
 * A remote-tracking ref is only as fresh as the last `git fetch`, so the age of its tip is a
 * direct OFFLINE measure of how stale a lane cut from it would be.
 *
 * We use `git for-each-ref --format=%(committerdate:unix) <ref>` rather than the spec's
 * illustrative `git log -1 --format=%ct <ref>`. Both are offline and report the same number; the
 * difference is state separation, which this predicate needs. `for-each-ref` exits 0 with EMPTY
 * output for a ref that does not exist, so "no trunk ref" (-> SILENT) is distinguishable from
 * "git could not answer" (-> UNDETERMINED). `git log` exits non-zero for both, collapsing the two
 * states this predicate exists to keep apart.
 *
 * DO NOT add a `git fetch` here. A network call in a dispatch-time hook can hang every dispatch,
 * and a guard that makes the common case slow gets disabled — a disabled guard protects nothing.
 * Reading a local ref UNDER-reports (a freshly-fetched but genuinely quiet trunk looks old) and
 * never over-reports, which is the safe direction for something that only advises.
 *
 * THREE STATES, NEVER TWO
 * ------------------------
 * FIRES / SILENT / UNDETERMINED. An unanswerable probe and a current trunk are byte-identical in a
 * "proceed" response — that is precisely how a guard stops guarding without anyone noticing. So a
 * probe that cannot answer says UNDETERMINED out loud and is never folded into "fresh".
 *
 * SILENCE IS DELIBERATE, NOT OMISSION. No `origin/<trunk>` ref at all -> silent, on purpose: a
 * guard that speaks on every dispatch trains the operator to skim past it, and then the one time
 * it matters they skim past that too.
 *
 * ADVISORY ONLY. An old tip is genuinely AMBIGUOUS — a quiet trunk over a holiday and a tree
 * nobody has fetched are the same reading, and only the operator can tell which. Blocking on an
 * ambiguity is a false-positive machine. What makes advisory sufficient here (where it would not
 * be for an end-of-turn check) is TIMING: this fires BEFORE the decision it exists to change.
 *
 * CLONE-SAFE. Pure local git process state. No roster, no signing key, no network, no enrollment.
 * A fresh fork with no `origin/dev` is SILENT, not broken — so this is safe in committed
 * settings.json, unlike the coordination-ENFORCEMENT hooks that must stay operator-local.
 *
 * Spec: the Dispatch-Freshness Precondition (portable spec, 2026-09-13). This file implements it;
 * it is not a copy of any other harness's implementation.
 */

"use strict";

const { execFileSync } = require("node:child_process");

/** The delegation tools. A dispatch is the only moment this predicate is worth paying for. */
const DELEGATION_TOOLS = ["Task", "Agent"];

/** Default staleness threshold: well below the 600h incident, comfortably above a quiet weekend. */
const DEFAULT_THRESHOLD_HOURS = 72;

/**
 * Trunk candidates, in priority order; the FIRST that exists wins.
 * `dev` leads because this repo's integration trunk is `dev` (rules/dev-integration-trunk.md).
 * A fork carrying only `main` resolves to `main` — which is why the list, not a hard-coded ref.
 */
const DEFAULT_TRUNK_CANDIDATES = ["dev", "main", "master"];

/** Bounded so a wedged git cannot hold up a dispatch. Exceeding it is UNDETERMINED, not fresh. */
const PROBE_TIMEOUT_MS = 2000;

const FIRES = "fires";
const SILENT = "silent";
const UNDETERMINED = "undetermined";

const SECONDS_PER_HOUR = 3600;

/**
 * Read the tip committer-date of one remote-tracking ref, offline.
 *
 * @returns {{kind:"measured",tipSeconds:number}
 *          |{kind:"missing"}
 *          |{kind:"undetermined",reason:string}}
 */
function probeRefTipSeconds(ref, opts = {}) {
  const cwd = opts.cwd || process.cwd();
  const timeoutMs = opts.timeoutMs || PROBE_TIMEOUT_MS;
  const exec = opts.execFn || defaultExec;

  let raw;
  try {
    raw = exec(["for-each-ref", "--format=%(committerdate:unix)", ref], {
      cwd,
      timeoutMs,
    });
  } catch (err) {
    // "Not a git repository" is not an unanswerable probe — it is a context with no trunk at all,
    // which is the same nothing-to-say as a missing ref. Everything else (git absent, timeout,
    // unreadable ref, corrupt object) is a probe that COULD NOT ANSWER and must say so.
    const text =
      `${(err && err.stderr) || ""} ${(err && err.message) || ""}`.toLowerCase();
    if (text.includes("not a git repository")) return { kind: "missing" };
    if (err && err.code === "ENOENT")
      return { kind: "undetermined", reason: "git not found" };
    if (err && (err.killed || err.signal === "SIGTERM")) {
      return { kind: "undetermined", reason: `probe exceeded ${timeoutMs}ms` };
    }
    return {
      kind: "undetermined",
      reason: firstLine(text) || "git probe failed",
    };
  }

  const text = String(raw == null ? "" : raw).trim();
  // Exit 0 with empty output is `for-each-ref`'s answer for "that ref does not exist".
  if (text === "") return { kind: "missing" };

  const tipSeconds = Number.parseInt(text.split(/\s+/)[0], 10);
  if (!Number.isFinite(tipSeconds) || tipSeconds <= 0) {
    // Ref resolved but produced no usable date. That is unanswerable, NOT fresh.
    return {
      kind: "undetermined",
      reason: `unparseable committerdate: ${truncate(text, 40)}`,
    };
  }
  return { kind: "measured", tipSeconds };
}

function defaultExec(args, { cwd, timeoutMs }) {
  return execFileSync("git", args, {
    cwd,
    timeout: timeoutMs,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
}

function firstLine(s) {
  return String(s || "")
    .trim()
    .split("\n")[0]
    .trim();
}

function truncate(s, n) {
  const t = String(s);
  return t.length <= n ? t : `${t.slice(0, n)}…`;
}

/**
 * Evaluate the precondition for one dispatch.
 *
 * Every input that varies is injectable, because a threshold no test can cross is a threshold
 * nobody has checked.
 *
 * @returns {{state:string, ref?:string, ageHours?:number, ageDays?:number,
 *            tipSeconds?:number, thresholdHours:number, reason?:string}}
 */
function evaluateDispatchFreshness(opts = {}) {
  const toolName = opts.toolName;

  // The dispatch-tool gate. This predicate is about the base a WAVE is cut from; paying for a git
  // probe on every Read/Bash/Grep would be noise with a cost.
  if (!DELEGATION_TOOLS.includes(toolName)) {
    return {
      state: SILENT,
      thresholdHours: resolveThreshold(opts),
      reason: "not a dispatch",
    };
  }

  const thresholdHours = resolveThreshold(opts);
  const nowMs = Number.isFinite(opts.nowMs) ? opts.nowMs : Date.now();
  const candidates = opts.trunkCandidates || resolveTrunkCandidates(opts);

  const probeOpts = {
    cwd: opts.cwd,
    timeoutMs: opts.timeoutMs,
    execFn: opts.execFn,
  };

  let firstUndetermined = null;
  for (const trunk of candidates) {
    const ref = `refs/remotes/origin/${trunk}`;
    const result = probeRefTipSeconds(ref, probeOpts);

    if (result.kind === "undetermined") {
      // Hold it: a later candidate may resolve cleanly. Only if NONE does is this UNDETERMINED —
      // but it must never silently degrade to "fresh" just because a later ref was missing.
      if (!firstUndetermined)
        firstUndetermined = { ref, reason: result.reason };
      continue;
    }
    if (result.kind === "missing") continue;

    const ageHours = (nowMs / 1000 - result.tipSeconds) / SECONDS_PER_HOUR;
    const base = {
      ref,
      tipSeconds: result.tipSeconds,
      ageHours,
      ageDays: ageHours / 24,
      thresholdHours,
    };
    return ageHours > thresholdHours
      ? { state: FIRES, ...base }
      : { state: SILENT, ...base };
  }

  if (firstUndetermined) {
    return {
      state: UNDETERMINED,
      ref: firstUndetermined.ref,
      reason: firstUndetermined.reason,
      thresholdHours,
    };
  }

  // No trunk ref at all — a fresh clone, or a repo that tracks no origin. Deliberately silent.
  return { state: SILENT, thresholdHours, reason: "no origin trunk ref" };
}

function resolveThreshold(opts) {
  if (Number.isFinite(opts.thresholdHours)) return opts.thresholdHours;
  const env = (opts.env || process.env || {}).COC_DISPATCH_FRESHNESS_HOURS;
  const parsed = Number.parseFloat(env);
  return Number.isFinite(parsed) && parsed > 0
    ? parsed
    : DEFAULT_THRESHOLD_HOURS;
}

function resolveTrunkCandidates(opts) {
  const env = (opts.env || process.env || {}).COC_DISPATCH_TRUNK;
  if (env && String(env).trim()) return [String(env).trim()];
  return DEFAULT_TRUNK_CANDIDATES;
}

/**
 * Build the structured finding for `instruct-and-wait.js::emit()`.
 *
 * Returns FIELDS, not prose, so the hook owns presentation and the predicate stays
 * unit-testable without spawning a process. The four `agent_must_report` items are the
 * spec's four message requirements, in order.
 *
 * SEVERITY IS `pre-action`, NOT `halt-and-report`. This fires at PreToolUse: the dispatch
 * has NOT happened and is NOT blocked. `instruct-and-wait.js` renders every non-block head
 * as the ACTION'S FATE (loom#1715 H-1), so `halt-and-report` here would state "the action
 * ALREADY RAN" of a wave that has not been cut — false, and it removes the decision the
 * advisory exists to prompt. `pre-action` is the register built for exactly this moment.
 */
function buildFinding(result) {
  if (result.state === UNDETERMINED) {
    return {
      severity: "pre-action",
      what_happened:
        `The dispatch-freshness probe could NOT answer for \`${result.ref}\` ` +
        `(${result.reason}). The age of the base this wave would be cut from is UNKNOWN.`,
      why:
        "An unanswerable probe and a current trunk are byte-identical in a proceed " +
        "response — that is precisely how a guard stops guarding without anyone noticing. " +
        "So this is reported rather than assumed fresh.",
      agent_must_report: [
        `State that the freshness probe was UNANSWERABLE for \`${result.ref}\`, and why.`,
        "Establish the base's age by hand before cutting a wave: " +
          "`git fetch origin && git log -1 --format=%ci refs/remotes/origin/<trunk>`.",
        "Re-derive any issue list or tracker snapshot feeding this wave — the tree and " +
          "the tracker go stale together.",
      ],
      agent_must_wait:
        "Do not cut a wave of lanes until the base's age has been established.",
      user_summary: `dispatch-freshness: UNDETERMINED for ${result.ref} — ${result.reason}`,
    };
  }

  const days = result.ageDays.toFixed(1);
  const tipIso = new Date(result.tipSeconds * 1000).toISOString().replace("T", " ").slice(0, 19);
  const thresholdDays = (result.thresholdHours / 24).toFixed(1);

  return {
    severity: "pre-action",
    what_happened:
      `About to dispatch, but \`${result.ref}\` points at a commit dated ` +
      `**${tipIso} UTC** — ${days} days old (threshold ${thresholdDays}d).\n\n` +
      "A remote-tracking ref is only as fresh as the last fetch, so every lane cut from " +
      "it inherits this staleness — and no lane can detect it, because each measures its " +
      "own tree correctly.",
    why:
      "Measured 2026-09-13: a 32-lane wave ran against a tree 25 days and 3,850 commits " +
      "stale. 53 of its 134 issues (40%) had closed in the interim — all after the " +
      "snapshot date, none before. One lane recommended closing an issue that had closed " +
      "as COMPLETED three weeks earlier.",
    agent_must_report: [
      `State the measured age: \`${result.ref}\` tip is ${tipIso} UTC, ${days} days old.`,
      "Run `git fetch origin` and re-check BEFORE dispatching, so the wave is cut from a " +
        "current base.",
      "If the trunk is genuinely quiet and this age is correct, say so explicitly — an old " +
        "tip and an unfetched ref are the same reading from here.",
      "Re-derive any issue list or tracker snapshot feeding this wave. The tree and the " +
        "tracker go stale TOGETHER, which is what made the 0/53 closure split read as " +
        "internal consistency rather than as a warning.",
    ],
    agent_must_wait:
      "Do not cut a wave of lanes from a trunk ref older than the threshold without " +
      "fetching first, or stating why the age is correct.",
    user_summary:
      `dispatch-freshness: ${result.ref} tip is ${days}d old (${tipIso} UTC) — ` +
      "fetch before cutting lanes",
  };
}

module.exports = {
  DELEGATION_TOOLS,
  DEFAULT_THRESHOLD_HOURS,
  DEFAULT_TRUNK_CANDIDATES,
  PROBE_TIMEOUT_MS,
  FIRES,
  SILENT,
  UNDETERMINED,
  probeRefTipSeconds,
  evaluateDispatchFreshness,
  buildFinding,
};
