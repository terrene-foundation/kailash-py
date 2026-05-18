#!/usr/bin/env node
/*
 * ============================================================================
 *  sync-tier-aware — canonical tier-aware .claude/ enumerator (issue #272)
 * ============================================================================
 *
 *  PURPOSE
 *
 *  Closes the recurring `/tmp/sync-<target>.sh` ad-hoc-script class in
 *  /sync Gate 2. Every prior cycle re-implemented the tier-subscription
 *  filter in hand-written bash; every cycle regressed (the 2026-05-17
 *  cycle's helper leaked 4 categories of inappropriate files into a USE
 *  template before self-reverting). This script IS the structural defense
 *  the coc-sync.md MUST NOT § "Ad-Hoc Bash Sync Scripts That Bypass
 *  Tier-Aware Tooling" clause names — there is now exactly one place
 *  where tier filtering happens, and it ships with regression tests.
 *
 *  CONTRACT (sync-flow.md Gate 2 step 3)
 *
 *    1. Read `repos.<target>.tier_subscriptions` (REQUIRED in v2.21.0+;
 *       missing = manifest defect, halt with non-zero exit).
 *    2. Compute inclusion glob set = union of `tiers.<tier>[]` across
 *       subscribed tiers.
 *    3. Always-include tier-independent runtime infra regardless of
 *       subscriptions: `.claude/hooks/**`, `.claude/hooks/lib/**`,
 *       `.claude/bin/**`, `.claude/.coc-obsoleted`.
 *    4. Apply `exclude:` (universal) + `use_exclude:` (USE-templates only).
 *    5. Apply `use_obsoleted:` as PURGE list (paths to delete from target
 *       even though they are not in the include set).
 *    6. Exclude loom-local config: `*.local.json` (the gitignored
 *       operator-local resolver / repin config — never sync). The
 *       committed `*.local.example.json` schema templates DO ship (they
 *       are the documented schema downstream consumers may follow).
 *    7. Resolve target on-disk path via `bin/lib/loom-links.mjs`
 *       (`use-template.<key>` logical keys). NO positional fallback.
 *
 *  USAGE
 *
 *    node .claude/bin/sync-tier-aware.mjs --target <py|rs|rb|base>
 *        [--template <repo>]   # restrict to one of repos.<target>.templates[]
 *        [--dry-run]           # emit manifest, do not write
 *        [--out <dir>]         # write to this absolute path instead of
 *                              # resolving via loom-links
 *        [--json]              # emit machine-readable JSON manifest on stdout
 *                              # (default: text summary on stdout)
 *
 *  Exit codes: 0 = success; 1 = manifest defect / write failure;
 *              2 = usage error; 3 = resolver not-configured (loom-links).
 *
 *  Node ESM, zero external dependencies (mirrors emit.mjs convention:
 *  regex-based YAML slicing per validateTierCompleteness()).
 * ============================================================================
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolveRepo, LinkError } from "./lib/loom-links.mjs";

// ────────────────────────────────────────────────────────────────
// Filesystem safety primitives (security-reviewer Round-1 CRIT/HIGH)
// ────────────────────────────────────────────────────────────────

/**
 * Resolve `sub` against `base` and assert the result stays inside
 * `base`. Rejects `..` traversal, absolute paths, and `base` itself
 * (a `.` purge entry would delete the whole template repo).
 *
 * Used by both the copy branch (path.join(dir, f.path)) and the purge
 * branch (path.join(dir, use_obsoleted_entry)). Mirrors the structural-
 * confirmation pattern in `git.md` § "git reset --hard verify clean
 * working tree" and `schema-migration.md` Rule 7 — applied here to
 * `fs.rmSync(..., recursive, force)`, the irreversible-op equivalent.
 */
function safeJoinUnder(base, sub) {
  const baseAbs = path.resolve(base);
  const targetAbs = path.resolve(baseAbs, sub);
  if (targetAbs === baseAbs) {
    throw new Error(
      `path '${sub}' resolves to the target dir itself (would erase the template)`,
    );
  }
  if (!targetAbs.startsWith(baseAbs + path.sep)) {
    throw new Error(
      `path '${sub}' escapes the target dir (resolves to '${targetAbs}')`,
    );
  }
  return targetAbs;
}

/**
 * Reject manifest-declared `use_obsoleted` entries that would defeat
 * containment at parse time, surfacing the defect before any FS call.
 * Catches absolute paths (POSIX `path.join` discards prior components
 * when an absolute path appears), `.`-equivalents, and `..`-segments.
 */
function rejectUnsafePurgeEntry(entry) {
  if (typeof entry !== "string" || entry.length === 0) {
    return `empty entry`;
  }
  if (path.isAbsolute(entry)) return `absolute path '${entry}'`;
  if (entry === "." || entry === "./") return `'.' entry`;
  const segs = entry.split(/[/\\]/);
  if (segs.some((s) => s === "..")) return `'..' segment in '${entry}'`;
  return null;
}

/**
 * Symlink-safe copy. fs.copyFileSync follows symlinks at destination
 * by default, opening a TOCTOU race where a planted symlink between
 * mkdir and copy redirects the write outside the template. Mirrors
 * emit.mjs::safeWriteFileSync — O_NOFOLLOW refuses to open a symlink
 * target, closing the window. Asymmetry between the two sync paths
 * (emit.mjs strict; sync-tier-aware lax) would itself be institutional
 * drift per `cross-repo.md` MUST-1.
 */
function safeCopyFile(src, dest) {
  const srcData = fs.readFileSync(src);
  const fd = fs.openSync(
    dest,
    fs.constants.O_CREAT |
      fs.constants.O_WRONLY |
      fs.constants.O_TRUNC |
      fs.constants.O_NOFOLLOW,
    0o644,
  );
  try {
    fs.writeFileSync(fd, srcData);
  } finally {
    fs.closeSync(fd);
  }
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");
const MANIFEST_PATH = path.join(REPO, ".claude", "sync-manifest.yaml");
const CLAUDE_DIR = path.join(REPO, ".claude");

// ────────────────────────────────────────────────────────────────
// Always-include (Gate 2 step 3 — tier-independent runtime infra)
// ────────────────────────────────────────────────────────────────
//
// These ship to every USE template regardless of tier_subscriptions.
// Source of truth: `commands/sync.md` Gate 2 step 3 line.
//
// Pinning here (vs computing from manifest) is intentional: these are
// runtime infrastructure paths, not tier-classified content. Adding a
// new always-include path is a deliberate operator decision, not a
// passive manifest edit.
const ALWAYS_INCLUDE = [
  ".claude/hooks/**",
  ".claude/hooks/lib/**",
  ".claude/bin/**",
  ".claude/.coc-obsoleted",
];

// Loom-local config paths (gitignored operator config; NEVER sync).
// The companion `*.local.example.json` schema templates DO ship — they
// are the committed schemas downstream consumers may copy from. See
// `bin/lib/loom-links.mjs` § Disclosure discipline.
const LOOM_LOCAL_PATTERNS = [".claude/bin/*.local.json"];

// ────────────────────────────────────────────────────────────────
// CLI parse
// ────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const args = {
    target: null,
    template: null,
    dryRun: false,
    out: null,
    json: false,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target") args.target = argv[++i];
    else if (a === "--template") args.template = argv[++i];
    else if (a === "--dry-run") args.dryRun = true;
    else if (a === "--out") args.out = argv[++i];
    else if (a === "--json") args.json = true;
    else if (a === "-h" || a === "--help") {
      process.stdout.write(usage());
      process.exit(0);
    } else {
      process.stderr.write(`unknown arg: ${a}\n${usage()}`);
      process.exit(2);
    }
  }
  if (!args.target) {
    process.stderr.write(`--target is required\n${usage()}`);
    process.exit(2);
  }
  return args;
}

function usage() {
  return (
    "Usage: sync-tier-aware.mjs --target <py|rs|rb|base>\n" +
    "       [--template <repo>] [--dry-run] [--out <dir>] [--json]\n"
  );
}

// ────────────────────────────────────────────────────────────────
// Manifest parsing — regex-scoped section parse, mirroring
// emit.mjs::validateTierCompleteness() (no YAML dep).
// ────────────────────────────────────────────────────────────────
function loadManifest() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    fail(1, `sync-manifest.yaml not found at ${rel(MANIFEST_PATH)}`);
  }
  return fs.readFileSync(MANIFEST_PATH, "utf8");
}

/**
 * Slice a top-level YAML block: from the line AFTER `^<key>:` to the
 * next column-0 key. Mirrors emit.mjs::validateTierCompleteness sliceBlock.
 */
function sliceBlock(text, key) {
  const re = new RegExp(`^${key}:\\s*$`, "m");
  const start = text.search(re);
  if (start === -1) return "";
  const bodyStart = text.indexOf("\n", start);
  if (bodyStart === -1) return "";
  const after = text.slice(bodyStart + 1);
  const nextRel = after.search(/^[A-Za-z_][\w-]*:\s*$/m);
  return after.slice(0, nextRel === -1 ? undefined : nextRel);
}

/** Extract a list of `- <glob>` entries from a YAML block body. */
function parseList(blockBody) {
  const out = [];
  const re = /^\s*-\s*(\S.*?)\s*(?:#.*)?$/gm;
  let m;
  while ((m = re.exec(blockBody)) !== null) {
    let v = m[1];
    // Strip surrounding quotes if any
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    out.push(v);
  }
  return out;
}

/**
 * Parse `tiers:` block into { tier_name: [glob, ...] }. The block is
 * nested 2-space (tier key) → 4-space (- glob). Inner-key lookahead
 * also stops at the next `tiers`-block sibling at the same indent.
 */
function parseTiers(manifestText) {
  const tiersBlock = sliceBlock(manifestText, "tiers");
  const tiers = {};
  // Split tiers by their headers: `^  <tier>:\s*$`
  const tierHeaderRe = /^  ([a-z_][\w-]*):\s*$/gm;
  const headers = [];
  let m;
  while ((m = tierHeaderRe.exec(tiersBlock)) !== null) {
    headers.push({ name: m[1], start: m.index, headerEnd: m.index + m[0].length });
  }
  for (let i = 0; i < headers.length; i++) {
    const startBody = headers[i].headerEnd + 1;
    const endBody = i + 1 < headers.length ? headers[i + 1].start : tiersBlock.length;
    const body = tiersBlock.slice(startBody, endBody);
    // Only `- <glob>` lines at any indent within this tier body.
    tiers[headers[i].name] = parseList(body);
  }
  return tiers;
}

/**
 * Parse `repos:` block into { name: { tier_subscriptions:[], templates:[{repo,clis,baseline_files}], variant, build } }.
 */
function parseRepos(manifestText) {
  const reposBlock = sliceBlock(manifestText, "repos");
  const repos = {};
  // Repo headers: `^  <name>:\s*$`
  const headerRe = /^  ([a-z][\w-]*):\s*$/gm;
  const headers = [];
  let m;
  while ((m = headerRe.exec(reposBlock)) !== null) {
    headers.push({ name: m[1], start: m.index, headerEnd: m.index + m[0].length });
  }
  for (let i = 0; i < headers.length; i++) {
    const startBody = headers[i].headerEnd + 1;
    const endBody = i + 1 < headers.length ? headers[i + 1].start : reposBlock.length;
    const body = reposBlock.slice(startBody, endBody);
    // tier_subscriptions: inline array `[cc, co, coc]` OR `[]`
    const tsMatch = body.match(/^\s*tier_subscriptions:\s*\[([^\]]*)\]\s*$/m);
    const tier_subscriptions =
      tsMatch === null
        ? null
        : tsMatch[1]
            .split(",")
            .map((s) => s.trim())
            .filter((s) => s.length > 0);
    // variant: <name>
    const variantMatch = body.match(/^\s*variant:\s*(\S+)\s*$/m);
    const variant = variantMatch ? variantMatch[1] : null;
    // build: <name|null>
    const buildMatch = body.match(/^\s*build:\s*(\S+)\s*$/m);
    const build =
      buildMatch && buildMatch[1] !== "null" ? buildMatch[1] : null;
    // templates: list of { repo, clis, baseline_files }
    const templates = parseTemplates(body);
    repos[headers[i].name] = {
      tier_subscriptions,
      templates,
      variant,
      build,
    };
  }
  return repos;
}

function parseTemplates(repoBody) {
  // Each template entry begins with `^\s*-\s*repo:\s*<repo>\s*$`.
  // We parse repo, clis, baseline_files per entry.
  const out = [];
  const entryRe = /^\s*-\s*repo:\s*(\S+)\s*$/gm;
  const entries = [];
  let m;
  while ((m = entryRe.exec(repoBody)) !== null) {
    entries.push({ repo: m[1], start: m.index + m[0].length });
  }
  for (let i = 0; i < entries.length; i++) {
    const end = i + 1 < entries.length ? entries[i + 1].start : repoBody.length;
    const body = repoBody.slice(entries[i].start, end);
    const clisMatch = body.match(/^\s*clis:\s*\[([^\]]*)\]\s*$/m);
    const clis = clisMatch
      ? clisMatch[1]
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0)
      : [];
    const baseMatch = body.match(/^\s*baseline_files:\s*\[([^\]]*)\]\s*$/m);
    const baseline_files = baseMatch
      ? baseMatch[1]
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0)
      : [];
    out.push({ repo: entries[i].repo, clis, baseline_files });
  }
  return out;
}

// ────────────────────────────────────────────────────────────────
// Glob matching — minimal subset supporting `**`, `*`, exact paths.
// Sufficient for the manifest's glob vocabulary (no `?`, no `[...]`).
// ────────────────────────────────────────────────────────────────
function globToRegex(glob) {
  // Anchor at start AND end. Escape regex metachars except `*`.
  // `**` → match anything including `/`.
  // `*`  → match anything except `/`.
  let re = "";
  let i = 0;
  while (i < glob.length) {
    const c = glob[i];
    if (c === "*") {
      if (glob[i + 1] === "*") {
        re += ".*";
        i += 2;
        // Skip a following slash so `**/x` matches both `x` and `a/b/x`.
        if (glob[i] === "/") i += 1;
      } else {
        re += "[^/]*";
        i += 1;
      }
    } else if (/[.+?^${}()|[\]\\]/.test(c)) {
      re += "\\" + c;
      i += 1;
    } else {
      re += c;
      i += 1;
    }
  }
  return new RegExp("^" + re + "$");
}

function matchesAny(relpath, globs) {
  for (const g of globs) {
    if (globToRegex(g).test(relpath)) return true;
  }
  return false;
}

// ────────────────────────────────────────────────────────────────
// Walk loom/.claude/ — emit every file relative to repo root.
// ────────────────────────────────────────────────────────────────
function walkClaudeDir() {
  const out = [];
  const stack = [CLAUDE_DIR];
  while (stack.length > 0) {
    const dir = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      const abs = path.join(dir, e.name);
      if (e.isDirectory()) {
        stack.push(abs);
      } else if (e.isFile()) {
        // Path relative to REPO (matches manifest glob shape).
        out.push(path.relative(REPO, abs).split(path.sep).join("/"));
      }
    }
  }
  return out.sort();
}

// ────────────────────────────────────────────────────────────────
// Glob normalization — manifest tier globs are repo-root-relative
// but typically authored WITHOUT the leading `.claude/` prefix
// (e.g. `rules/git.md`, `agents/management/coc-sync.md`). The walk
// emits `.claude/rules/git.md`. We probe both shapes.
// ────────────────────────────────────────────────────────────────
function matchesManifestGlob(relpath, manifestGlob) {
  // Strip leading `.claude/` from the candidate so a bare manifest
  // glob like `rules/git.md` matches; also keep the full path for
  // globs authored WITH the prefix (always-include set).
  const stripped = relpath.startsWith(".claude/")
    ? relpath.slice(".claude/".length)
    : relpath;
  return (
    globToRegex(manifestGlob).test(relpath) ||
    globToRegex(manifestGlob).test(stripped)
  );
}

function matchesAnyManifestGlob(relpath, globs) {
  for (const g of globs) {
    if (matchesManifestGlob(relpath, g)) return true;
  }
  return false;
}

// ────────────────────────────────────────────────────────────────
// Inclusion computation
// ────────────────────────────────────────────────────────────────
function buildPlan(manifest, target, templateFilter) {
  const tiersMap = parseTiers(manifest);
  const repos = parseRepos(manifest);
  const repo = repos[target];
  if (!repo) {
    fail(
      1,
      `manifest defect: repos.${target} not declared in sync-manifest.yaml. ` +
        `Available: ${Object.keys(repos).join(", ")}`,
    );
  }
  if (repo.tier_subscriptions === null) {
    fail(
      1,
      `manifest defect: repos.${target}.tier_subscriptions missing ` +
        `(REQUIRED in v2.21.0+; halt per commands/sync.md Gate 2 step 3)`,
    );
  }

  const exclude = parseList(sliceBlock(manifest, "exclude"));
  const useExclude = parseList(sliceBlock(manifest, "use_exclude"));
  const useObsoleted = parseList(sliceBlock(manifest, "use_obsoleted"));

  // Reject unsafe purge entries at plan-build time (CRIT-1 defense).
  // An absolute / `.` / `..` entry would cause fs.rmSync to escape the
  // template dir; halt before any FS mutation.
  for (const entry of useObsoleted) {
    const defect = rejectUnsafePurgeEntry(entry);
    if (defect !== null) {
      fail(
        1,
        `manifest defect: use_obsoleted entry ${defect} ` +
          `— sync-tier-aware refuses to apply this purge list ` +
          `(would escape target dir)`,
      );
    }
  }

  // Compose inclusion globs from subscribed tiers.
  const inclusionGlobs = [];
  for (const tier of repo.tier_subscriptions) {
    const g = tiersMap[tier];
    if (!g) {
      fail(
        1,
        `manifest defect: tiers.${tier} not declared but ` +
          `repos.${target}.tier_subscriptions references it`,
      );
    }
    inclusionGlobs.push(...g);
  }

  const templates =
    templateFilter === null
      ? repo.templates
      : repo.templates.filter((t) => t.repo === templateFilter);
  if (templateFilter !== null && templates.length === 0) {
    fail(
      2,
      `--template ${templateFilter} not found under repos.${target}. ` +
        `Available: ${repo.templates.map((t) => t.repo).join(", ")}`,
    );
  }

  const allFiles = walkClaudeDir();

  // Per-file disposition.
  const files = [];
  for (const f of allFiles) {
    const disposition = classifyFile(
      f,
      inclusionGlobs,
      exclude,
      useExclude,
    );
    files.push({ path: f, ...disposition });
  }

  return {
    target,
    variant: repo.variant,
    tier_subscriptions: repo.tier_subscriptions,
    templates: templates.map((t) => t.repo),
    files,
    purge: useObsoleted.slice(),
  };
}

function classifyFile(relpath, inclusionGlobs, exclude, useExclude) {
  // 1. Always-include — wins over everything except loom-local.
  const alwaysInc = matchesAny(relpath, ALWAYS_INCLUDE);
  // 2. Loom-local — universal skip (gitignored operator config).
  if (matchesAny(relpath, LOOM_LOCAL_PATTERNS)) {
    return { action: "skip", reason: "loom_local" };
  }
  if (alwaysInc) {
    return { action: "copy", reason: "always_include" };
  }
  // 3. exclude (universal).
  if (matchesAnyManifestGlob(relpath, exclude)) {
    return { action: "skip", reason: "exclude" };
  }
  // 4. use_exclude (USE-template only — this tool emits to USE templates).
  if (matchesAnyManifestGlob(relpath, useExclude)) {
    return { action: "skip", reason: "use_exclude" };
  }
  // 5. Tier inclusion.
  if (matchesAnyManifestGlob(relpath, inclusionGlobs)) {
    return { action: "copy", reason: "tier_match" };
  }
  return { action: "skip", reason: "no_tier_match" };
}

// ────────────────────────────────────────────────────────────────
// Target path resolution — loom-links resolver, never positional.
// ────────────────────────────────────────────────────────────────
function resolveTemplateDir(repo, outOverride) {
  if (outOverride !== null) return outOverride;
  // Logical key: `use-template.<short-key>`. Strip `kailash-coc-` /
  // `coc-` prefixes to derive the short key. The operator's
  // `.local.json` declares these.
  const shortKey = repo
    .replace(/^kailash-coc-/, "")
    .replace(/^coc-/, "");
  const key = `use-template.${shortKey}`;
  const r = resolveRepo(key, { require: false });
  if (r.skipped) {
    fail(
      3,
      `loom-links resolver: ${r.reason}\n` +
        `(declare 'use-template.${shortKey}' in loom-links.local.json, ` +
        `or pass --out <dir> to override)`,
    );
  }
  if (r.kind !== "path") {
    fail(
      3,
      `loom-links: '${key}' is a ${r.kind}, expected path linkage`,
    );
  }
  return r.value;
}

// ────────────────────────────────────────────────────────────────
// Execution — copy + purge
// ────────────────────────────────────────────────────────────────
function executePlan(plan, outOverride, dryRun) {
  // Two-pass execution (MED-3 defense): resolve EVERY template path
  // BEFORE any FS mutation. A missing resolver entry halts the whole
  // run rather than leaving partial state across templates 1..N-1 when
  // template N fails.
  const resolvedDirs = plan.templates.map((tmpl) =>
    resolveTemplateDir(tmpl, outOverride),
  );

  const results = [];
  for (let i = 0; i < plan.templates.length; i++) {
    const tmpl = plan.templates[i];
    const dir = resolvedDirs[i];
    const result = {
      template: tmpl,
      // HIGH-2 / MED-A defense: results carry the BASENAME, not the
      // resolved absolute path. emitText AND --json both consume this
      // shape; both branches stay disclosure-clean. The absolute `dir`
      // remains local to executePlan (closed over below) for FS ops —
      // never escapes the function as serialized output.
      target_basename: path.basename(dir),
      copied: [],
      purged: [],
      skipped: {
        loom_local: 0,
        exclude: 0,
        use_exclude: 0,
        no_tier_match: 0,
      },
    };
    for (const f of plan.files) {
      if (f.action === "skip") {
        result.skipped[f.reason] = (result.skipped[f.reason] || 0) + 1;
        continue;
      }
      const src = path.join(REPO, f.path);
      // CRIT-2 defense: containment check on dest. f.path comes from
      // walkClaudeDir() which cannot produce `..` segments today, but
      // a future manifest-driven enumeration would inherit the gap.
      let dest;
      try {
        dest = safeJoinUnder(dir, f.path);
      } catch (e) {
        fail(1, `copy refused: ${e.message}`);
      }
      if (!dryRun) {
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        // HIGH-1 defense: O_NOFOLLOW refuses symlink targets at dest.
        safeCopyFile(src, dest);
      }
      result.copied.push({
        src: f.path,
        dest: path.relative(dir, dest),
        reason: f.reason,
      });
    }
    // Purge use_obsoleted at target (only if path exists at target).
    // CRIT-1 defense: containment check rejects `..` / absolute /
    // `.` entries that escape the template dir. Pre-validated at
    // plan-build time (rejectUnsafePurgeEntry); this is the runtime
    // belt to the parse-time braces.
    for (const p of plan.purge) {
      let targetAbs;
      try {
        targetAbs = safeJoinUnder(dir, p);
      } catch (e) {
        fail(1, `purge refused: ${e.message}`);
      }
      if (fs.existsSync(targetAbs)) {
        if (!dryRun) {
          const stat = fs.lstatSync(targetAbs);
          if (stat.isDirectory()) fs.rmSync(targetAbs, { recursive: true, force: true });
          else fs.unlinkSync(targetAbs);
        }
        result.purged.push({ path: p });
      }
    }
    results.push(result);
  }
  return results;
}

// ────────────────────────────────────────────────────────────────
// Reporting
// ────────────────────────────────────────────────────────────────
function emitText(plan, results, dryRun) {
  const mode = dryRun ? "DRY RUN" : "WRITE";
  const lines = [];
  lines.push(
    `# sync-tier-aware ${mode} — target=${plan.target} ` +
      `variant=${plan.variant ?? "—"} ` +
      `tiers=[${plan.tier_subscriptions.join(",")}]`,
  );
  for (const r of results) {
    // HIGH-2 defense: result carries target_basename (set in
    // executePlan); the absolute path never escapes the function.
    // Per `bin/lib/loom-links.mjs` § Disclosure discipline.
    lines.push("");
    lines.push(`## template: ${r.template}`);
    lines.push(`   target_dir: ${r.target_basename}/`);
    lines.push(`   copied:  ${r.copied.length}`);
    lines.push(`   purged:  ${r.purged.length}`);
    lines.push(
      `   skipped: loom_local=${r.skipped.loom_local || 0} ` +
        `exclude=${r.skipped.exclude || 0} ` +
        `use_exclude=${r.skipped.use_exclude || 0} ` +
        `no_tier_match=${r.skipped.no_tier_match || 0}`,
    );
  }
  return lines.join("\n") + "\n";
}

// ────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────
function rel(p) {
  try {
    return path.relative(process.cwd(), p) || p;
  } catch {
    return p;
  }
}

function fail(code, msg) {
  process.stderr.write(`sync-tier-aware: ${msg}\n`);
  process.exit(code);
}

// ────────────────────────────────────────────────────────────────
// Main
// ────────────────────────────────────────────────────────────────
function main() {
  const args = parseArgs(process.argv);
  const manifest = loadManifest();
  const plan = buildPlan(manifest, args.target, args.template);
  const results = executePlan(plan, args.out, args.dryRun);
  if (args.json) {
    const out = { plan, results, dry_run: args.dryRun };
    process.stdout.write(JSON.stringify(out, null, 2) + "\n");
  } else {
    process.stdout.write(emitText(plan, results, args.dryRun));
  }
}

// Run only when invoked directly (not when imported by tests).
// Use realpathSync to resolve symlinks (macOS /var/folders → /private/var/folders).
function _isInvokedDirectly() {
  if (!process.argv[1]) return false;
  try {
    return (
      fs.realpathSync(process.argv[1]) ===
      fs.realpathSync(fileURLToPath(import.meta.url))
    );
  } catch {
    return false;
  }
}
if (_isInvokedDirectly()) {
  try {
    main();
  } catch (e) {
    if (e instanceof LinkError) {
      fail(3, `loom-links: ${e.subtype}: ${e.message}`);
    }
    fail(1, `${e.message || e}`);
  }
}

// ────────────────────────────────────────────────────────────────
// Exports (for regression tests)
// ────────────────────────────────────────────────────────────────
export {
  parseArgs,
  parseTiers,
  parseRepos,
  parseList,
  sliceBlock,
  globToRegex,
  matchesAny,
  matchesManifestGlob,
  matchesAnyManifestGlob,
  classifyFile,
  buildPlan,
  safeJoinUnder,
  rejectUnsafePurgeEntry,
  ALWAYS_INCLUDE,
  LOOM_LOCAL_PATTERNS,
};
