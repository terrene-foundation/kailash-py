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
const { execFileSync } = require("child_process");
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
const {
  computeOpenPrState,
  formatOpenPrBlock,
} = require("./lib/open-pr-surface");
const {
  migrateMonolithToSplit,
  regenerateAggregate,
} = require("./lib/session-notes-layout");
const { ensureCanonicalDriver } = require("./lib/coc-ledger-driver");
const { resolveIdentity } = require("./lib/operator-id");

// Timeout fallback — prevents hanging the Claude Code session
const TIMEOUT_MS = 10000;
const _timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
const { readPosture, isPendingWithinGrace } = require("./lib/state-io");

process.stdin.on("end", () => {
  try {
    const data = JSON.parse(input);
    const result = initializeSession(data);

    // Trust-posture gate (mitigates red-team H4 / Phase 1 of trust-posture rollout)
    let trustGate = "";
    try {
      const posture = readPosture(data.cwd);
      const lines = [];
      lines.push(
        `\n## Trust Posture: ${posture.posture}` +
          (posture._fail_closed
            ? " (FAIL-CLOSED — state was missing/corrupt)"
            : "") +
          (posture._fresh ? " (fresh repo)" : ""),
      );
      lines.push(`since: ${posture.since}`);
      // loom#875 — only surface entries still WITHIN their grace window; a
      // grace-expired entry must not drive the trust-gate banner (it would
      // render a nonsensical "day N of 7" for N > 7 and nag forever).
      const pv = (posture.pending_verification || []).filter(
        (e) => e && e.rule_id && isPendingWithinGrace(e),
      );
      if (pv.length) {
        lines.push("\n⚠️ TRUST GATE — Verification Pending:");
        for (const e of pv) {
          const days = Math.floor(
            (Date.now() - new Date(e.since).getTime()) / 86400000,
          );
          lines.push(
            `  - ${e.rule_id} (day ${days + 1} of ${e.grace_period_days}). ` +
              `Violation within grace = EMERGENCY DOWNGRADE. ` +
              `Include \`[ack: ${e.rule_id}]\` in your first response.`,
          );
        }
      }
      trustGate = lines.join("\n");
    } catch {
      // If readPosture itself fails, surface a quiet warning — don't block session
      trustGate =
        "\n## Trust Posture: UNREADABLE — manual /posture init required";
    }

    // Open-PR session-start surface (orphan-PR guard, issue #574). Fail-open:
    // computeOpenPrState never throws; a null/undefined state degrades to no
    // block (undefined) or a "could-not-verify" warning (null). Gated on a
    // github.com remote so a local-only repo gets no false warning. Prepended
    // ABOVE the session notes so the live queue outranks any note's claim.
    let openPrBlock = null;
    try {
      openPrBlock = formatOpenPrBlock(computeOpenPrState(data.cwd));
    } catch {
      openPrBlock = null; // belt-and-suspenders: never block session start
    }

    const output = { continue: true };
    const ctxParts = [];
    if (openPrBlock) ctxParts.push(openPrBlock);
    if (result.sessionNotesContext) ctxParts.push(result.sessionNotesContext);
    if (trustGate) ctxParts.push(trustGate);
    if (ctxParts.length) {
      output.hookSpecificOutput = {
        hookEventName: "SessionStart",
        additionalContext: ctxParts.join("\n\n"),
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

  // ── Python virtual environment check ───────────────────────────────────
  const hasPyproject = fs.existsSync(path.join(cwd, "pyproject.toml"));
  if (hasPyproject) {
    const venvPython = path.join(cwd, ".venv", "bin", "python");
    const hasVenv = fs.existsSync(venvPython);
    if (!hasVenv) {
      console.error(
        "[VENV] ⚠ WARNING: No .venv found in project root. Using global Python is BLOCKED.",
      );
      console.error(
        "[VENV]   Fix: run `uv venv && uv sync` before any Python work.",
      );
      console.error(
        "[VENV]   See rules/python-environment.md for the full policy.",
      );
    } else {
      // Check if venv is stale (pyproject.toml newer than .venv)
      try {
        const pyprojectMtime = fs.statSync(
          path.join(cwd, "pyproject.toml"),
        ).mtimeMs;
        const venvMtime = fs.statSync(venvPython).mtimeMs;
        if (pyprojectMtime > venvMtime) {
          console.error(
            "[VENV] pyproject.toml changed since last uv sync. Run `uv sync` to update.",
          );
        }
      } catch {}
    }
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

  // ── Session-notes coherence: zero-touch migrate + aggregate (C5, #743) ─
  // Migrate a legacy monolith into the per-operator split ONCE (idempotent —
  // no-op when already split or no monolith present) and regenerate the
  // read-only by-name aggregate. EVERY path is wrapped so a failure NEVER
  // blocks session start (C5.2 fail-open; cc-artifacts.md Rule 7). Runs BEFORE
  // the notes surface below so the dashboard reflects current on-disk truth.
  try {
    const identity = resolveIdentity(cwd, {});
    if (identity) {
      const mig = migrateMonolithToSplit(cwd, identity);
      if (mig && mig.ok && mig.migrated) {
        console.error(
          "[SESSION-NOTES] Migrated legacy .session-notes → per-operator split (.session-notes.d/); original preserved as .session-notes.migrated.",
        );
      }
    }
    // Regenerate the aggregate regardless (belt: reflects any fragment change).
    // The writer self-refuses if the target is not gitignored (C2.2), so an
    // errored/absent-gitignore state is a silent no-op here, never a throw.
    regenerateAggregate(cwd);
  } catch (e) {
    console.error(`[SESSION-NOTES] Coherence pass skipped: ${e.message}`);
  }

  // ── Ledger merge-driver self-heal (G1, journal/0418) ─────────────────────
  // If this repo opts into the coc-ledger 3-way merge driver (.gitattributes)
  // but this clone's local registration is missing or NON-CANONICAL (the
  // loom#741 bare-path form that fails `Permission denied` and silently falls
  // back to the default line-merge, clobbering .session-notes.shared.md rows),
  // register the canonical driver in LOCAL git config. Idempotent + fail-open;
  // a not-referenced / already-canonical repo writes nothing. Closes the silent
  // multi-operator clobber window without a manual `loom doctor --fix`.
  try {
    const drv = ensureCanonicalDriver({ repoRoot: cwd });
    if (drv && drv.action === "registered") {
      console.error(
        "[MERGE-DRIVER] Registered canonical coc-ledger 3-way merge driver" +
          (drv.before
            ? ` (was non-canonical: ${drv.before})`
            : " (was unregistered)") +
          " — protects .session-notes.shared.md from clobber (journal/0418 G1).",
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

      // Build pointer-only context for Claude (full notes loaded on demand).
      // Prior behavior injected full note content, ballooning to 10KB+ per session.
      const pointerParts = [];
      for (const note of allNotes) {
        const label = note.workspace ? `[${note.workspace}]` : "[root]";
        const staleMark = note.stale ? " STALE" : "";
        pointerParts.push(
          `- ${label} ${note.relativePath} (updated ${note.age}${staleMark})`,
        );
      }
      if (pointerParts.length > 0) {
        result.sessionNotesContext =
          "# Previous Session Notes\n\nRead these files if continuing prior work:\n\n" +
          pointerParts.join("\n");
      }
    }
  } catch {}

  // ── Package freshness & version consistency check ───────────────────
  try {
    checkPythonPackageFreshness(cwd);
  } catch (e) {
    console.error(`[FRESHNESS] Check failed: ${e.message}`);
  }

  // ── Release drift check (unreleased packages) ────────────────────────
  try {
    checkReleaseDrift(cwd);
  } catch (e) {
    console.error(`[RELEASE-DRIFT] Check failed: ${e.message}`);
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
 * Resolve a package's __version__ when __init__.py re-exports it from a sibling
 * module instead of assigning a literal (`from kailash_ml._version import __version__`).
 *
 * The module name is PARSED from the import statement — never assumed to be
 * `_version` — so a package using any other version-module name resolves too.
 * Handles absolute (`from <pkg>.<mod> import ...`), relative (`from .<mod> ...`),
 * and parent-relative (`from ..<mod> ...`) forms.
 *
 * Returns { version, file } or null when no re-exported literal resolves.
 */
function resolveReexportedVersion(initPath, initContent) {
  const initDir = path.dirname(initPath);
  const pkgName = path.basename(initDir);

  // `from <module> import <names>` — names captured up to EOL/comment.
  const importRe = /^[ \t]*from[ \t]+([.\w]+)[ \t]+import[ \t]+([^\n#]+)/gm;
  let m;
  while ((m = importRe.exec(initContent)) !== null) {
    const moduleRef = m[1];
    const names = m[2];
    // __version__ must appear as a whole imported name, not a substring.
    if (!/(^|[\s,(])__version__([\s,)]|$)/.test(names)) continue;

    const leadingDots = (moduleRef.match(/^\.+/) || [""])[0].length;
    let rel = moduleRef.slice(leadingDots);
    let baseDir = initDir;

    if (leadingDots === 0) {
      // Absolute: only resolvable when rooted at this package.
      if (!rel.startsWith(pkgName + ".")) continue;
      rel = rel.slice(pkgName.length + 1);
    } else {
      // `.mod` = sibling; `..mod` = parent package, etc.
      for (let i = 1; i < leadingDots; i++) baseDir = path.dirname(baseDir);
    }
    if (!rel) continue;

    const stem = path.join(baseDir, ...rel.split("."));
    for (const candidate of [stem + ".py", path.join(stem, "__init__.py")]) {
      if (!fs.existsSync(candidate)) continue;
      const lit = fs
        .readFileSync(candidate, "utf8")
        .match(/^[ \t]*__version__\s*=\s*["']([^"']+)["']/m);
      if (lit) return { version: lit[1], file: candidate };
    }
  }
  return null;
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

      // __version__ may be a literal in __init__.py OR re-exported from a
      // sibling module. Both are valid single-source-of-truth layouts; only
      // "neither resolves" is a real finding.
      let initVersion = null;
      let initVersionSource = pkg.init;
      const initLiteral = init.match(/__version__\s*=\s*"([^"]+)"/);
      if (initLiteral) {
        initVersion = initLiteral[1];
      } else {
        const reexported = resolveReexportedVersion(initPath, init);
        if (reexported) {
          initVersion = reexported.version;
          initVersionSource = path.relative(cwd, reexported.file);
        }
      }

      if (pyVersionMatch && initVersion) {
        if (pyVersionMatch[1] !== initVersion) {
          console.error(
            `[FRESHNESS] VERSION MISMATCH in ${pkg.name}: ` +
              `pyproject.toml=${pyVersionMatch[1]}, ${initVersionSource}=${initVersion}. ` +
              `Update ${initVersionSource} before release!`,
          );
          mismatches++;
        }
      } else if (pyVersionMatch && !initVersion) {
        console.error(
          `[FRESHNESS] ${pkg.name}: no __version__ resolvable from ${pkg.init} ` +
            `(no literal, no re-export). ` +
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

  // Check SDK dependency pin freshness (for repos that depend on kailash packages)
  checkSdkPinFreshness(cwd);

  // Check COC sync freshness (for USE repos that have a sync marker)
  const markerPath = path.join(cwd, ".claude", ".coc-sync-marker");
  if (fs.existsSync(markerPath)) {
    try {
      const marker = JSON.parse(fs.readFileSync(markerPath, "utf8").trim());
      if (marker.synced_at) {
        const daysSince =
          (Date.now() - new Date(marker.synced_at).getTime()) /
          (1000 * 60 * 60 * 24);
        if (!isFinite(daysSince)) {
          console.error(
            `[COC-SYNC] WARNING: Invalid sync timestamp in marker file`,
          );
        } else if (daysSince > 7) {
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

/**
 * Check if kailash SDK dependency pins in pyproject.toml are installed in .venv.
 * Warns if pins exist but .venv packages are missing or at a different version.
 * Also enforces uv sync (not pip install) for dependency management.
 */
function checkSdkPinFreshness(cwd) {
  const pyprojectPath = path.join(cwd, "pyproject.toml");
  if (!fs.existsSync(pyprojectPath)) return;

  try {
    const content = fs.readFileSync(pyprojectPath, "utf8");

    // Extract kailash-* dependency pins from pyproject.toml
    // Matches: kailash>=1.2.3, kailash-dataflow>=1.0.0, and the extras form
    // kailash-dataflow[security,monitoring,api]>=2.0.12 (the bracket is
    // consumed but NOT captured, so pin.name stays the bare dist name).
    //
    // The (?:^|\n) line-start anchor is DELIBERATE: dropping it would also
    // match `kailash-dataflow>=2.0.3` inside the prose comment above
    // [tool.uv.sources], inventing a pin that does not exist. Every kailash-*
    // package pinned in a one-liner extra (`dataflow = ["kailash-dataflow>=..."]`)
    // is also pinned line-anchored in the [all] array, so the anchor costs
    // no coverage here.
    const pinRegex =
      /(?:^|\n)\s*"?(kailash(?:-[\w]+)?)(?:\[[^\]]*\])?"?\s*>=\s*([\d.]+)/g;
    const pinsByName = new Map();
    let match;
    while ((match = pinRegex.exec(content)) !== null) {
      const [name, version] = [match[1], match[2]];
      // A package pinned in more than one place (bare + extras form): keep the
      // WEAKEST pin, so a stale pin anywhere in the manifest still surfaces.
      const seen = pinsByName.get(name);
      if (!seen || isOlderThan(version, seen.version)) {
        pinsByName.set(name, { name, version });
      }
    }
    const pins = [...pinsByName.values()];

    if (pins.length === 0) return; // Not a kailash downstream repo

    // Check pins against BUILD repo's actual versions
    checkPinsAgainstBuild(cwd, pins);

    // Check if .venv exists
    const venvPython = path.join(cwd, ".venv", "bin", "python");
    if (!fs.existsSync(venvPython)) {
      console.error(
        `[SDK-PINS] ${pins.length} kailash packages pinned but no .venv found. Run: uv venv && uv sync`,
      );
      return;
    }

    // Enumerate installed packages via importlib.metadata — works in ANY venv,
    // including uv's default which ships NO pip (`python -m pip` there fails
    // with "No module named pip" on a perfectly healthy interpreter).
    // Emits the [{name, version}] shape the pip path produced, PLUS a `broken`
    // field for the pinned packages.
    //
    // WHY the `broken` probe: metadata presence is NOT evidence of usability.
    // `.dist-info` survives a broken editable install, so a package whose
    // `.pth` points at a moved/deleted source tree still enumerates at its
    // recorded version while `import <pkg>` raises ModuleNotFoundError and its
    // test suite cannot run. Reporting that as healthy hides a condition that
    // silently invalidates test results.
    //
    // Two MECHANICAL signals, no module execution:
    //   1. an editable-pointer `.pth` whose target directory does not exist
    //      (names the stale path, which is the actionable part)
    //   2. no top-level module resolves via find_spec
    // find_spec RESOLVES without importing: 0.02s vs 5.1s for real imports of
    // these packages, and real imports also dump ~60 lines of library INFO
    // logging into session start. Limitation: this catches "module cannot be
    // located" (the ModuleNotFoundError class) — NOT a module that locates but
    // raises during execution. Scoped to the pinned packages only; probing all
    // ~288 distributions costs 5.1s, probing the 7 pinned costs 0.44s.
    const PROBE_INSTALLED = [
      "import json,sys,pathlib,importlib.util",
      "from importlib.metadata import distributions",
      "wanted={a.lower().replace('-','_') for a in sys.argv[1:]}",
      "def pth_targets(d):",
      "    out=[]",
      "    for f in (d.files or []):",
      "        if not str(f).endswith('.pth'): continue",
      "        try: raw=pathlib.Path(d.locate_file(f)).read_text()",
      "        except Exception: continue",
      "        for line in raw.splitlines():",
      "            line=line.strip()",
      "            if not line or line.startswith(('import ','#')): continue",
      "            out.append((line, pathlib.Path(line).is_dir()))",
      "    return out",
      "def top_levels(d,targets):",
      "    tl=d.read_text('top_level.txt')",
      "    if tl: return sorted({x.strip() for x in tl.split() if x.strip()})",
      "    names=set()",
      "    for path,ok in targets:",
      "        if not ok: continue",
      "        for child in pathlib.Path(path).iterdir():",
      "            if (child/'__init__.py').is_file(): names.add(child.name)",
      "    return sorted(names)",
      "out=[]",
      "for d in distributions():",
      "    n=(d.metadata or {}).get('Name')",
      "    v=d.version",
      "    if not n or not v: continue",
      "    e={'name':n,'version':v}",
      "    if n.lower().replace('-','_') in wanted:",
      "        try:",
      "            targets=pth_targets(d)",
      "            broken=[p for p,ok in targets if not ok]",
      "            if broken: e['broken']='stale editable pointer -> '+broken[0]",
      "            else:",
      "                tls=top_levels(d,targets)",
      "                if tls and not any(importlib.util.find_spec(m) for m in tls):",
      "                    e['broken']='module does not resolve: '+', '.join(tls)",
      "        except Exception as ex: e['probe_error']=f'{type(ex).__name__}: {ex}'",
      "    out.append(e)",
      "json.dump(out,sys.stdout)",
    ].join("\n");

    let stale = 0;
    const brokenInstalls = [];
    try {
      const installed = execFileSync(
        venvPython,
        ["-c", PROBE_INSTALLED, ...pins.map((p) => p.name)],
        // MUST stay below this hook's own TIMEOUT_MS (10s) so a hung probe is
        // killed here and the hook still reports, rather than the whole hook
        // hitting its fallback. Measured probe cost is ~0.44s (7 pinned pkgs).
        { encoding: "utf8", timeout: 5000, stdio: ["pipe", "pipe", "pipe"] },
      );
      const packages = JSON.parse(installed);
      const pkgMap = {};
      for (const p of packages) {
        const key = p.name.toLowerCase().replace(/-/g, "_");
        // FIRST-wins, not last: distributions() yields in sys.path order, so the
        // first entry for a name is the one Python actually imports. A venv can
        // legitimately carry two .dist-info dirs for one name at DIFFERENT
        // versions (stale editable + newer install); last-wins would report the
        // shadowed one. (`pip list` deduped for us; this enumeration does not.)
        if (!(key in pkgMap)) pkgMap[key] = p;
      }

      for (const pin of pins) {
        const normalized = pin.name.toLowerCase().replace(/-/g, "_");
        const entry = pkgMap[normalized];
        if (!entry) {
          console.error(
            `[SDK-PINS] ${pin.name}>=${pin.version} pinned but NOT installed. Run: uv sync`,
          );
          stale++;
          continue;
        }
        if (entry.probe_error) {
          // Surface rather than swallow; treat as unknown-health, not healthy.
          console.error(
            `[SDK-PINS] ${pin.name}: health probe failed (${entry.probe_error}); usability UNKNOWN.`,
          );
        }
        if (entry.broken) {
          // Metadata present but unusable — MUST NOT count toward the healthy
          // tally; this package's tests cannot execute.
          brokenInstalls.push({
            name: pin.name,
            version: entry.version,
            reason: entry.broken,
          });
          continue;
        }
        const installed_ver = entry.version;
        if (
          installed_ver !== pin.version &&
          isOlderThan(installed_ver, pin.version)
        ) {
          console.error(
            `[SDK-PINS] ${pin.name}: installed ${installed_ver} < pinned ${pin.version}. Run: uv sync`,
          );
          stale++;
        }
      }
    } catch (e) {
      // Surface the ACTUAL error rather than a guessed cause. Do NOT advise
      // recreating the venv: this path no longer implies a broken interpreter
      // (the old `python -m pip` probe failed on every pip-less uv venv), so
      // "uv venv && uv sync" would destroy a working environment for a
      // cause that may not exist.
      // Prefer the child's own stderr and keep only its last non-empty line:
      // e.message embeds the whole -c script, and for a Python failure the
      // last line is the actual exception. Keeps session start readable.
      const detail =
        String(e.stderr || e.message || "")
          .trim()
          .split("\n")
          .filter((l) => l.trim())
          .pop() || "unknown error";
      console.error(
        `[SDK-PINS] Could not enumerate installed packages: ${detail}. ` +
          `Verify the interpreter with \`.venv/bin/python -V\` before changing anything.`,
      );
      return;
    }

    // Healthy = pinned, installed, at/above pin, AND actually usable. Broken
    // installs are excluded from this tally so the count never asserts health
    // for a package that cannot be imported.
    const healthy = pins.length - stale - brokenInstalls.length;
    if (stale === 0 && healthy > 0) {
      // Distinct from the STALE-pin check above: that compares pins against the
      // SDK source, this compares the .venv's INSTALLED versions against the pins.
      console.error(
        `[SDK-PINS] ${healthy} kailash packages installed at or above their pin`,
      );
    } else if (stale > 0) {
      console.error(
        `[SDK-PINS] ${stale} stale pin(s). MUST run: uv sync (not pip install)`,
      );
    }

    if (brokenInstalls.length > 0) {
      console.error(
        `[SDK-PINS] ⚠ ${brokenInstalls.length} package(s) have install metadata but FAIL to import ` +
          `— their test suites cannot run:`,
      );
      for (const b of brokenInstalls) {
        console.error(
          `[SDK-PINS]   ${b.name} (metadata ${b.version}): ${b.reason}`,
        );
      }
      console.error(
        `[SDK-PINS]   Cause is usually a stale editable-install pointer after a repo move. ` +
          `Fix: uv venv --clear && uv sync`,
      );
    }
  } catch {}
}

/**
 * Compare pyproject.toml pins against the current SDK package versions.
 *
 * Two sources, in priority order:
 *   1. `packages/<pkg>/pyproject.toml::version` — the LIVE version, used
 *      whenever that file exists. In this monorepo the SDK packages sit right
 *      next to the root pyproject, so this is ground truth.
 *   2. `.claude/VERSION::upstream.sdk_packages` — a /sync-time SNAPSHOT
 *      (Gate 2 step 8), used only for packages not present locally (the
 *      downstream-consumer case, which has no packages/ tree).
 *
 * The snapshot is written once per /sync and goes stale between syncs, so it
 * MUST NOT override a locally-present package's real version — doing so
 * reports every number wrong and hides packages the snapshot never listed.
 *
 * A mismatch means the pyproject.toml pin was not bumped alongside the SDK.
 */
function checkPinsAgainstBuild(cwd, pins) {
  const sdkVersions = {};

  // Source 2 (fallback): the /sync-time snapshot, loaded first so live
  // package versions below overwrite it.
  const versionPath = path.join(cwd, ".claude", "VERSION");
  if (fs.existsSync(versionPath)) {
    try {
      const version = JSON.parse(fs.readFileSync(versionPath, "utf8"));
      const sdkPackages = (version.upstream || {}).sdk_packages;
      for (const [name, ver] of Object.entries(sdkPackages || {})) {
        sdkVersions[name.toLowerCase().replace(/-/g, "_")] = ver;
      }
    } catch (e) {
      console.error(
        `[SDK-PINS] .claude/VERSION unreadable (${e.message}); using local packages/ only.`,
      );
    }
  }

  // Source 1 (preferred): the live version in each local package manifest.
  for (const pin of pins) {
    const baseName = pin.name.replace(/\[.*\]/, "");
    const localManifest = path.join(
      cwd,
      "packages",
      baseName,
      "pyproject.toml",
    );
    if (!fs.existsSync(localManifest)) continue;
    try {
      const localVer = fs
        .readFileSync(localManifest, "utf8")
        .match(/^version\s*=\s*"([^"]+)"/m);
      if (localVer) {
        sdkVersions[baseName.toLowerCase().replace(/-/g, "_")] = localVer[1];
      }
    } catch (e) {
      console.error(
        `[SDK-PINS] ${baseName}: could not read ${path.relative(cwd, localManifest)} (${e.message}).`,
      );
    }
  }

  if (Object.keys(sdkVersions).length === 0) return;

  let staleCount = 0;
  const staleList = [];

  for (const pin of pins) {
    const baseName = pin.name.replace(/\[.*\]/, "");
    const normalized = baseName.toLowerCase().replace(/-/g, "_");
    const sdkVer = sdkVersions[normalized];

    if (!sdkVer) continue;

    if (isOlderThan(pin.version, sdkVer)) {
      staleList.push(
        `${baseName}: pinned >=${pin.version}, current SDK is ${sdkVer}`,
      );
      staleCount++;
    }
  }

  if (staleCount > 0) {
    console.error(
      `[SDK-PINS] ⚠ ${staleCount} STALE pin(s) — pyproject.toml is behind the current SDK version ` +
        `(source: packages/<pkg>/pyproject.toml, falling back to .claude/VERSION):`,
    );
    for (const msg of staleList) {
      console.error(`[SDK-PINS]   ${msg}`);
    }
    console.error(
      `[SDK-PINS]   Fix: update pyproject.toml pins to match current SDK, then run \`uv sync\``,
    );
  }
}

/**
 * Simple version comparison: is a older than b?
 */
function isOlderThan(a, b) {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) < (pb[i] || 0)) return true;
    if ((pa[i] || 0) > (pb[i] || 0)) return false;
  }
  return false;
}

/**
 * Check for packages with commits since their last release tag.
 * Silent when no packages / no matching tags / all released.
 * See .claude/hooks/lib/release-drift.js for detection logic.
 */
function checkReleaseDrift(cwd) {
  const { detectUnreleasedPackages } = require("./lib/release-drift");
  const unreleased = detectUnreleasedPackages(cwd);
  if (unreleased.length === 0) return;

  console.error(
    `[RELEASE-DRIFT] ⚠ ${unreleased.length} package(s) have commits since last release:`,
  );
  for (const pkg of unreleased) {
    console.error(
      `[RELEASE-DRIFT]   ${pkg.name} (${pkg.path}): ${pkg.commits_since_tag} commit(s) since ${pkg.last_tag} — pyproject at v${pkg.current_version}`,
    );
  }
  console.error(`[RELEASE-DRIFT]   Run /release when ready to publish.`);
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
