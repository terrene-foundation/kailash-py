/**
 * Fixtures for the Dispatch-Freshness Precondition predicate.
 *
 * Run: node --test .claude/audit-fixtures/dispatch-freshness/test.mjs
 *
 * REAL GIT, NOT MOCKS. The predicate IS git process state, so a mocked git would test the mock.
 * Every repo below is a real `git init` with a real commit backdated via GIT_COMMITTER_DATE, and a
 * real `refs/remotes/origin/<trunk>` created with `git update-ref`. The two UNDETERMINED cases are
 * the exception and are labelled where they appear: one is a genuinely corrupt ref (real), one
 * injects a killed-process error because a true timeout cannot be produced deterministically.
 *
 * THE THRESHOLD IS INJECTABLE, and both sides of it are crossed below. A threshold no test can
 * cross is a threshold nobody has checked.
 *
 * MUTATIONS. A passing suite proves nothing until it is shown to FAIL when the thing it guards is
 * removed. Three mutations run against scratch copies (never the real file), each one asserted to
 * have actually CHANGED THE SOURCE first — a mutation that did not alter the file, or that dies on
 * a missing import, reads as a successful mutation while proving nothing. The M0 control runs the
 * UNMUTATED scratch copy and confirms it still behaves like the real module, which is what makes
 * the other three readable at all.
 */

import { strict as assert } from "node:assert";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { after, describe, it } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const LIB_PATH = path.resolve(
  import.meta.dirname,
  "../../hooks/lib/dispatch-freshness.js",
);
const lib = require(LIB_PATH);

const NOW_MS = Date.UTC(2026, 8, 13, 12, 0, 0); // fixed clock: 2026-09-13T12:00:00Z
const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

const tmpRoots = [];
after(() => {
  for (const dir of tmpRoots) {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {}
  }
});

function git(cwd, args, env = {}) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ...env },
  });
}

/**
 * A real repo with one real commit, backdated, and optionally a real remote-tracking trunk ref.
 * @param {{tipAgeMs?:number, trunk?:string|null, corruptRef?:boolean}} opts
 */
function makeRepo(opts = {}) {
  const { tipAgeMs = 0, trunk = "dev", corruptRef = false } = opts;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "disp-fresh-"));
  tmpRoots.push(dir);

  git(dir, ["init", "--quiet", "-b", "work"]);
  git(dir, ["config", "user.email", "t@example.invalid"]);
  git(dir, ["config", "user.name", "T"]);
  fs.writeFileSync(path.join(dir, "f.txt"), "x\n");
  git(dir, ["add", "f.txt"]);

  const stamp = new Date(NOW_MS - tipAgeMs).toISOString();
  git(dir, ["commit", "--quiet", "-m", "base"], {
    GIT_COMMITTER_DATE: stamp,
    GIT_AUTHOR_DATE: stamp,
  });

  const sha = git(dir, ["rev-parse", "HEAD"]).trim();
  if (corruptRef) {
    // A ref pointing at an object that does not exist: git can neither resolve it nor call it
    // absent. This is a REAL unanswerable probe, not a simulated one.
    const refFile = path.join(dir, ".git", "refs", "remotes", "origin");
    fs.mkdirSync(refFile, { recursive: true });
    fs.writeFileSync(path.join(refFile, "dev"), `${"0".repeat(39)}1\n`);
  } else if (trunk) {
    git(dir, ["update-ref", `refs/remotes/origin/${trunk}`, sha]);
  }
  return { dir, sha };
}

function evaluate(cwd, extra = {}) {
  return lib.evaluateDispatchFreshness({
    toolName: "Task",
    cwd,
    nowMs: NOW_MS,
    env: {}, // never inherit the ambient COC_DISPATCH_* overrides
    ...extra,
  });
}

// ---------------------------------------------------------------------------
// The seven behaviours the spec's table requires
// ---------------------------------------------------------------------------

describe("dispatch-freshness predicate", () => {
  it("FIRES when the trunk tip is 30 days old", () => {
    const { dir } = makeRepo({ tipAgeMs: 30 * DAY });
    const r = evaluate(dir);
    assert.equal(r.state, lib.FIRES);
    assert.equal(r.ref, "refs/remotes/origin/dev");
    assert.ok(Math.abs(r.ageDays - 30) < 0.05, `ageDays=${r.ageDays}`);
  });

  it("is SILENT when the trunk tip is fresh", () => {
    const { dir } = makeRepo({ tipAgeMs: 2 * HOUR });
    assert.equal(evaluate(dir).state, lib.SILENT);
  });

  it("is SILENT for a non-dispatch tool call, however stale the tree", () => {
    const { dir } = makeRepo({ tipAgeMs: 300 * DAY });
    for (const toolName of ["Bash", "Read", "Grep", "Edit", ""]) {
      assert.equal(evaluate(dir, { toolName }).state, lib.SILENT, `tool=${toolName}`);
    }
    // Control: the SAME repo fires for a real dispatch, so the silence above is the GATE and not
    // a repo that simply cannot produce a finding.
    assert.equal(evaluate(dir, { toolName: "Task" }).state, lib.FIRES);
    assert.equal(evaluate(dir, { toolName: "Agent" }).state, lib.FIRES);
  });

  it("is SILENT when no origin trunk ref exists at all", () => {
    const { dir } = makeRepo({ tipAgeMs: 300 * DAY, trunk: null });
    const r = evaluate(dir);
    assert.equal(r.state, lib.SILENT);
    assert.match(r.reason, /no origin trunk ref/);
  });

  it("reports UNDETERMINED — never silent, never stale — when the probe cannot answer", () => {
    // (a) REAL corrupt ref.
    const { dir } = makeRepo({ corruptRef: true });
    const real = evaluate(dir);
    assert.equal(real.state, lib.UNDETERMINED, `got ${real.state} (${real.reason})`);
    assert.ok(real.reason && real.reason.length > 0);

    // (b) Injected timeout. A true timeout is not deterministic, so the killed-process shape is
    // injected rather than raced for.
    const timedOut = evaluate(dir, {
      execFn: () => {
        const e = new Error("spawn timeout");
        e.killed = true;
        e.signal = "SIGTERM";
        throw e;
      },
    });
    assert.equal(timedOut.state, lib.UNDETERMINED);
    assert.match(timedOut.reason, /exceeded/);
  });

  it("crosses the threshold in BOTH directions (5d tip vs 3d and 10d thresholds)", () => {
    const { dir } = makeRepo({ tipAgeMs: 5 * DAY });
    assert.equal(evaluate(dir, { thresholdHours: 72 }).state, lib.FIRES); // 3 days
    assert.equal(evaluate(dir, { thresholdHours: 240 }).state, lib.SILENT); // 10 days
  });

  it("honours COC_DISPATCH_FRESHNESS_HOURS and COC_DISPATCH_TRUNK", () => {
    const { dir } = makeRepo({ tipAgeMs: 5 * DAY, trunk: "main" });
    // Default candidate order would find `main` anyway; pin it explicitly and confirm the ref used.
    const r = evaluate(dir, { env: { COC_DISPATCH_TRUNK: "main", COC_DISPATCH_FRESHNESS_HOURS: "1" } });
    assert.equal(r.state, lib.FIRES);
    assert.equal(r.ref, "refs/remotes/origin/main");
    assert.equal(r.thresholdHours, 1);

    const quiet = evaluate(dir, { env: { COC_DISPATCH_TRUNK: "main", COC_DISPATCH_FRESHNESS_HOURS: "999" } });
    assert.equal(quiet.state, lib.SILENT);
  });

  it("prefers dev over main when both exist (this repo's integration trunk)", () => {
    const { dir, sha } = makeRepo({ tipAgeMs: 30 * DAY });
    git(dir, ["update-ref", "refs/remotes/origin/main", sha]);
    assert.equal(evaluate(dir).ref, "refs/remotes/origin/dev");
  });
});

// ---------------------------------------------------------------------------
// The message — the fourth element is the one most likely to be dropped
// ---------------------------------------------------------------------------

describe("advisory message", () => {
  it("states ref, tip date, age, the fetch remedy, the explicit out, and the tracker warning", () => {
    const { dir } = makeRepo({ tipAgeMs: 25 * DAY });
    const text = lib.renderAdvisory(evaluate(dir));
    assert.match(text, /refs\/remotes\/origin\/dev/); // 1: the ref
    assert.match(text, /2026-08-19/); // 1: the tip DATE
    assert.match(text, /25\.0 days/); // 1: the age
    assert.match(text, /git fetch origin/); // 2: the remedy
    assert.match(text, /quiet/i); // 3: the explicit out
    assert.match(text, /tracker|issue list/i); // 4: re-derive the issue list
    assert.match(text, /stale TOGETHER/); // 4: and WHY it is coupled
  });

  it("says UNDETERMINED out loud rather than reading as a clean proceed", () => {
    const text = lib.renderAdvisory({
      state: lib.UNDETERMINED,
      ref: "refs/remotes/origin/dev",
      reason: "git not found",
      thresholdHours: 72,
    });
    assert.match(text, /UNDETERMINED/);
    assert.match(text, /NOT a clean reading/);
    assert.match(text, /tracker|issue list/i);
  });
});

// ---------------------------------------------------------------------------
// Mutations — M0 control first, then three that MUST red the suite
// ---------------------------------------------------------------------------

const SOURCE = fs.readFileSync(LIB_PATH, "utf8");

/** Copy the lib to a scratch file, apply `transform`, assert it CHANGED, and load it. */
function loadMutant(name, transform) {
  const mutated = transform(SOURCE);
  assert.notEqual(
    mutated,
    SOURCE,
    `mutation '${name}' did not change the source — it proves nothing`,
  );
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `disp-fresh-mut-${name}-`));
  tmpRoots.push(dir);
  const file = path.join(dir, "dispatch-freshness.js");
  fs.writeFileSync(file, mutated);
  return require(file);
}

function evalWith(mod, cwd, extra = {}) {
  return mod.evaluateDispatchFreshness({
    toolName: "Task",
    cwd,
    nowMs: NOW_MS,
    env: {},
    ...extra,
  });
}

describe("mutation battery", () => {
  it("M0 CONTROL: the unmutated scratch copy behaves like the real module", () => {
    // Without this, a mutant that merely dies on a missing import reads as a successful mutation.
    const m0 = loadMutant("m0", (s) => `${s}\n// M0 control: behaviour-neutral edit.\n`);
    const stale = makeRepo({ tipAgeMs: 30 * DAY }).dir;
    const fresh = makeRepo({ tipAgeMs: 1 * HOUR }).dir;
    const corrupt = makeRepo({ corruptRef: true }).dir;

    assert.equal(evalWith(m0, stale).state, m0.FIRES);
    assert.equal(evalWith(m0, fresh).state, m0.SILENT);
    assert.equal(evalWith(m0, corrupt).state, m0.UNDETERMINED);
    assert.equal(evalWith(m0, stale, { toolName: "Bash" }).state, m0.SILENT);
  });

  it("M1 invert the age comparison -> firing cases go SILENT", () => {
    // Target the comparison itself, not the whole return statement: the auto-formatter wraps that
    // return across three lines, and a whitespace-sensitive mutation silently stops applying.
    // Caught on the first run by loadMutant's did-it-change-the-source assertion.
    const m = loadMutant("m1", (s) =>
      s.replace("ageHours > thresholdHours", "ageHours <= thresholdHours"),
    );
    const stale = makeRepo({ tipAgeMs: 30 * DAY }).dir;
    assert.equal(evaluate(stale).state, lib.FIRES, "precondition: real module fires");
    assert.equal(evalWith(m, stale).state, m.SILENT, "M1 must silence the firing case");
  });

  it("M2 collapse UNDETERMINED into fresh -> the third-state case goes SILENT", () => {
    const m = loadMutant("m2", (s) =>
      s.replace(
        /if \(firstUndetermined\) \{[\s\S]*?\n  \}/,
        "if (firstUndetermined) {\n    return { state: SILENT, thresholdHours };\n  }",
      ),
    );
    const corrupt = makeRepo({ corruptRef: true }).dir;
    assert.equal(evaluate(corrupt).state, lib.UNDETERMINED, "precondition: real module reports it");
    assert.equal(evalWith(m, corrupt).state, m.SILENT, "M2 must hide the third state");
  });

  it("M3 remove the dispatch-tool gate -> a non-dispatch call FIRES", () => {
    const m = loadMutant("m3", (s) =>
      s.replace("if (!DELEGATION_TOOLS.includes(toolName)) {", "if (false) {"),
    );
    const stale = makeRepo({ tipAgeMs: 30 * DAY }).dir;
    assert.equal(evaluate(stale, { toolName: "Bash" }).state, lib.SILENT, "precondition: gated");
    assert.equal(evalWith(m, stale, { toolName: "Bash" }).state, m.FIRES, "M3 must ungate it");
  });
});
