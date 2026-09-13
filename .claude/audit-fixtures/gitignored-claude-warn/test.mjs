/**
 * Fixtures for gitignored-claude-warn — the three-way discrimination its exit-code read depends on.
 *
 * Run: node --test .claude/audit-fixtures/gitignored-claude-warn/test.mjs
 *
 * WHAT BROKE. The hook ran `git check-ignore -v` and read exit 0 as "this path is gitignored".
 * Under `-v`, git reports a NEGATION match (`!pattern`) as a match and exits 0 — so exit 0 stops
 * meaning "ignored" and starts meaning "some pattern mentioned this path, in either direction".
 * This repo un-ignores `.claude/audit-fixtures/**` with exactly such a negation, so every new
 * UNTRACKED fixture was warned as "transient, will not be tracked" while being perfectly
 * trackable. Caught when the hook fired on a fixture being added to a tree that already tracked
 * 1,909 of them.
 *
 * WHY REAL REPOS. The predicate is git's pattern engine, including negation precedence and the
 * index lookup. A mock encodes the author's belief about `check-ignore`, which is the thing that
 * was wrong in the first place.
 *
 * The THIRD row is the one that matters and the one a naive suite omits: a genuinely-ignored path
 * must still warn. Without it, deleting the hook's body entirely would pass.
 */

import { strict as assert } from "node:assert";
import { execFileSync, spawnSync } from "node:child_process";
import { after, describe, it } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const HOOK = path.resolve(
  import.meta.dirname,
  "../../hooks/gitignored-claude-warn.js",
);

const tmpRoots = [];
after(() => {
  for (const d of tmpRoots) {
    try {
      fs.rmSync(d, { recursive: true, force: true });
    } catch {}
  }
});

/**
 * A real repo mirroring THIS repo's actual .gitignore shape.
 *
 * The shape matters and a plausible-looking one does not reproduce the bug. An earlier draft used
 * a blanket `.claude/**` plus `!.claude/audit-fixtures/**`; under git's "cannot re-include a file
 * whose parent directory is excluded" rule the negation is inert there, the path stays genuinely
 * ignored, and `check-ignore` returns 0 for the RIGHT reason — so the fixture passed on the buggy
 * hook and proved nothing. The real file (lines 251-259) ignores SPECIFIC subpaths and carries `!`
 * negations matching paths nothing ignored in the first place. That is the reproducing condition:
 * a negation that MATCHES a path which is NOT ignored.
 */
function makeRepo() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gciw-"));
  tmpRoots.push(dir);
  const git = (args) =>
    execFileSync("git", args, { cwd: dir, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });

  git(["init", "--quiet", "-b", "main"]);
  git(["config", "user.email", "t@example.invalid"]);
  git(["config", "user.name", "T"]);
  fs.writeFileSync(
    path.join(dir, ".gitignore"),
    [
      ".claude/learning/",
      ".claude/settings.local.json",
      "!.claude/hooks/lib/",
      "!.claude/bin/**",
      "!.claude/audit-fixtures/**",
      "",
    ].join("\n"),
  );
  fs.mkdirSync(path.join(dir, ".claude/audit-fixtures/demo"), { recursive: true });
  fs.mkdirSync(path.join(dir, ".claude/hooks/lib"), { recursive: true });
  fs.mkdirSync(path.join(dir, ".claude/bin"), { recursive: true });
  fs.mkdirSync(path.join(dir, ".claude/learning"), { recursive: true });

  git(["add", ".gitignore"]);
  git(["commit", "--quiet", "-m", "init"]);
  return dir;
}

/** Drive the hook exactly as the harness does: JSON on stdin, JSON on stdout. */
function runHook(cwd, filePath) {
  const payload = JSON.stringify({
    tool_name: "Write",
    cwd,
    tool_input: { file_path: path.join(cwd, filePath) },
  });
  const r = spawnSync(process.execPath, [HOOK], {
    input: payload,
    cwd,
    encoding: "utf8",
    timeout: 10000,
    env: { ...process.env, CLAUDE_PROJECT_DIR: cwd },
  });
  assert.equal(r.status, 0, `hook must always exit 0, got ${r.status}: ${r.stderr}`);
  let out = {};
  try {
    out = JSON.parse(r.stdout || "{}");
  } catch {
    assert.fail(`hook emitted non-JSON: ${r.stdout}`);
  }
  return out.hookSpecificOutput?.additionalContext || "";
}

describe("gitignored-claude-warn — negation must not read as ignored", () => {
  it("is SILENT for an UNTRACKED file under a '!' negation (the regression)", () => {
    const dir = makeRepo();
    const rel = ".claude/audit-fixtures/demo/new-fixture.mjs";
    fs.writeFileSync(path.join(dir, rel), "// new, untracked\n");

    // Pin the git behaviour this hook depends on, so the test explains itself when git changes:
    // `-v` exits 0 on the negation (the bug), bare check-ignore exits 1 (the truth).
    const withV = spawnSync("git", ["check-ignore", "-v", rel], { cwd: dir });
    const bare = spawnSync("git", ["check-ignore", rel], { cwd: dir });
    assert.equal(withV.status, 0, "-v is expected to exit 0 on a negation match");
    assert.equal(bare.status, 1, "bare check-ignore is expected to exit 1 — not ignored");

    assert.equal(
      runHook(dir, rel),
      "",
      "a trackable fixture must NOT be warned as transient",
    );
  });

  it("is SILENT for an untracked file under a second negated subtree", () => {
    const dir = makeRepo();
    const rel = ".claude/bin/new-tool.mjs";
    fs.writeFileSync(path.join(dir, rel), "// new tool\n");
    // A `**` negation, like the fixtures one: `-v` MATCHES it and exits 0, so this pole
    // discriminates. A directory-form negation (`!.claude/hooks/lib/`) does NOT match a file
    // beneath it under `-v`, so a test built on one passes with and without the fix -- measured,
    // and the reason this case was rewritten.
    const withV = spawnSync("git", ["check-ignore", "-v", rel], { cwd: dir });
    const bare = spawnSync("git", ["check-ignore", rel], { cwd: dir });
    assert.equal(withV.status, 0, "precondition: -v matches the negation");
    assert.equal(bare.status, 1, "precondition: this path is NOT ignored");
    assert.equal(runHook(dir, rel), "");
  });

  it("STILL WARNS for a genuinely ignored .claude path", () => {
    // The control. Without this the hook could be gutted entirely and the suite would pass.
    const dir = makeRepo();
    const rel = ".claude/learning/notes.md";
    fs.writeFileSync(path.join(dir, rel), "# transient\n");

    const bare = spawnSync("git", ["check-ignore", rel], { cwd: dir });
    assert.equal(bare.status, 0, "precondition: this path really is ignored");

    const msg = runHook(dir, rel);
    assert.notEqual(msg, "", "a genuinely gitignored .claude file MUST still warn");
    assert.match(msg, /gitignored|transient/i);
  });

  it("is SILENT outside .claude/ and outside a git repo", () => {
    const dir = makeRepo();
    fs.writeFileSync(path.join(dir, "README.md"), "x\n");
    assert.equal(runHook(dir, "README.md"), "");

    const bare = fs.mkdtempSync(path.join(os.tmpdir(), "gciw-nogit-"));
    tmpRoots.push(bare);
    fs.mkdirSync(path.join(bare, ".claude"), { recursive: true });
    fs.writeFileSync(path.join(bare, ".claude/x.md"), "x\n");
    assert.equal(runHook(bare, ".claude/x.md"), "", "exit 128 must be silent, not a crash");
  });
});
