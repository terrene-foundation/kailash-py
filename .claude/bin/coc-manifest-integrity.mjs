#!/usr/bin/env node
/**
 * coc-manifest-integrity — the F1-class tripwire for the COC eval-manifest.
 *
 * LOOM ADAPTATION (C2 §3.2): loom adopts the eval ENGINE and EXCLUDES the
 * canon-sync scanner (`canon-sync-readiness-check.mjs`, an F3 concern). The two
 * canon-sync-specific constants below (`CANON_SYNC_ARTIFACT_SET`, check (c);
 * `REQUIRED_STRUCTURAL_ENTRIES`, check (i)) are therefore EMPTY at loom and both
 * checks are inert no-ops until loom authors its own local structural scanners.
 * Every GENERIC drift check — (a) path-resolution, (b) probe artifact_id, (d)
 * structural-coverage invariants, (e)/(f)/(g) orphan-probe/scanner/fixture, (h)
 * bipolar floor, (j) containment — stays fully active over whatever loom's
 * eval-manifest declares. loom's committed eval-manifest is empty (no structural
 * scanners yet), so a clean run reports 0 entries, integrity PASS.
 *
 * The eval-manifest ↔ probe-file ↔ on-disk-artifact triad can silently drift:
 * a probe file registered under the wrong key, a scanner/fixtures/probes path
 * that no longer resolves, a new COC artifact landed on disk with no manifest
 * entry. Each drift makes `coc-eval-all.mjs` report GREEN while the coverage it
 * claims does not exist. This module HARD-FAILS on any such drift so the
 * structural gate cannot pass over a broken manifest.
 *
 * Five checks (all HARD errors — zero-tolerance.md Rule 2, no silent pass):
 *   (a) every non-null `scanner` / `fixturesDir` / `probes` manifest path
 *       resolves on disk (a DECLARED-BUT-MISSING scanner FAILS, never SKIPS);
 *   (b) every probe row's `artifact_id` is a manifest key (a probe file
 *       registered against a phantom key is a coverage lie);
 *   (c) every on-disk canon-sync / eval-harness COC artifact (the enumerated
 *       set below) has a manifest entry (the F1-class "artifact present but
 *       absent from the manifest" gap the two-tier coverage contract blocks);
 *   (d) every `type:tool` entry carries a NON-null `scanner` AND a non-empty
 *       `expected` map — a tool's correctness is proven ONLY by its structural
 *       fixtures (coc-artifact-eval-coverage.md MUST-1 bootstrap note), so a
 *       `type:tool` entry downgraded to `scanner:null` would silently erase all
 *       structural coverage while coc-eval-all still reported GREEN (the
 *       scanner-null disarm — a one-token manifest edit disabling the CI teeth);
 *   (e) every `*.probes.json` on disk under the probes dir is referenced by
 *       some manifest entry — an orphan probe file (present but unregistered)
 *       is a coverage claim nobody runs (fail-open drift the gate must surface);
 *   (f) every `*-readiness-check.mjs` scanner on disk under .claude/bin is
 *       referenced by some manifest entry's `scanner` — an orphan SCANNER
 *       (present but unregistered) means a structural gate exists that nothing
 *       runs. This closes the F1 disarm CLASS that check (d) alone cannot: (d)
 *       and the coc-eval-all coverage floor key on the ATTACKER-CONTROLLED
 *       `type` field, so retyping a `type:tool` entry to a prose type (+ null
 *       scanner) OR deleting the entry both erase structural coverage while the
 *       gate stays green — but both ORPHAN the scanner, which (f) catches
 *       regardless of any entry's declared `type`;
 *   (g) every payload-bearing fixture-case subdir under a structural entry's
 *       `fixturesDir` is a key in that entry's `expected` — an orphan FIXTURE
 *       (present on disk but un-asserted) is coverage nobody runs. Dropping the
 *       negative / violation-detection cases from `expected` (a routine-looking
 *       fixture prune) erases the scanner's whole detection purpose while the
 *       gate stays green — the sibling of the orphan probe/scanner classes, one
 *       field over (`expected` truncation). A HELPER dir (flat, README/.md-only,
 *       no payload subtree — e.g. audit-fixtures/canon-sync/hooks/) is NOT a
 *       fixture case and is excluded.
 *   (h) BIPOLAR detection floor — every entry with a NON-null scanner MUST
 *       assert BOTH a clean-input case (an `expected` case with exit 0) AND a
 *       violation-detection case (an `expected` case with a non-zero exit).
 *       Asserting only one polarity erases half the detection contract while
 *       green: keeping only the exit-0 positives means the scanner never
 *       verifies it FLAGS a violation; keeping only the exit-1 negatives means
 *       it never verifies it stays QUIET on clean input. This closes the
 *       repoint-`fixturesDir`-to-a-positives-only-dir + prune-`expected`
 *       disarm that (a)-(g) miss — (g) only bounds on-disk⊆expected, it never
 *       constrains `expected`'s polarity MIX, and a fresh decoy fixturesDir
 *       satisfies (g) trivially. Type-independent (keyed on scanner presence,
 *       like d2) so a retype-to-prose dodge cannot evade it.
 *   (i) PINNED structural entries — the canon-sync structural tool (its manifest
 *       entry, its `scanner`, AND its `fixturesDir`) is pinned to its canonical
 *       identity. Checks (d)-(h) all PRESUPPOSE the entry exists; deleting the
 *       entry + its scanner file + its fixtures dir in one edit erases the whole
 *       structural tier with `structural_run:0` while the gate stays green
 *       ((a)/(f)/(g) have nothing on-disk left to enumerate). Pinning
 *       {key present, type:tool, exact scanner path, exact fixturesDir path}
 *       makes any deletion — OR a fixturesDir repoint away from the canonical
 *       audit tree (the (h) sibling lever) — a HARD fail.
 *   (j) CONTAINMENT — every declared `scanner` / `fixturesDir` / `probes` path
 *       MUST resolve INSIDE the repo's `.claude/` tree, BOTH lexically (the
 *       manifest string, rejecting `../payload.mjs` / absolute-outside) AND by
 *       REAL path (following symlinks — a symlink AT a lexically-contained path
 *       whose target escapes `.claude/` is the `resolve()`-is-lexical bypass: it
 *       passes the string check yet `execFileSync` would run out-of-tree code).
 *       Both are execution-containment escapes, defeated before the scanner runs.
 *
 * (e)/(f)/(g) together make the manifest a COMPLETE reflection of on-disk
 * coverage — every on-disk probe file, scanner, AND fixture case MUST be
 * declared — so coverage cannot be silently erased by UNDER-declaring it.
 * (h)/(i)/(j) close the residual OVER-mutation levers (`expected` polarity
 * pruning, wholesale entry+file deletion, out-of-tree path repoint) that the
 * under-declaration checks (a)-(g) structurally cannot see.
 *
 * Public API:
 *   checkManifestIntegrity({ manifestPath, repoRoot }) -> { ok, errors[] }
 *
 * Also runnable standalone:
 *   node .claude/bin/coc-manifest-integrity.mjs [--manifest <path>] [--json]
 *
 * Dependencies: Node.js built-ins only. Zero deps.
 */

import { existsSync, readdirSync, readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, isAbsolute, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

// The enumerated must-be-registered COC artifact set (check (c)): each on-disk
// member MUST have a manifest entry under `key`.
//
// LOOM ADAPTATION (C2 §3.2): EMPTY at loom. The BUILD-repo set enumerated the
// canon-sync + eval-harness artifacts (canon-incorporation.md, sync-from-canon,
// the canon-sync scanner, the test-harness-probe pair, …). loom adopts the eval
// ENGINE only and EXCLUDES `canon-sync-readiness-check.mjs` — the canon-sync /
// canon-incorporation contract (F3) is a SEPARATE decision, not this harness.
// loom carries some of those artifacts on disk (e.g. `sync-from-canon.md`,
// `test-harness-probe.md`) for DISTRIBUTION to targets, but does NOT run the
// eval harness over them and declares NO eval-manifest entries for them — so an
// enumerated set here would false-FAIL check (c) on every distributed-but-not-
// evaluated artifact. loom pins none; when loom later declares its own local
// structural scanners it adds their must-register artifacts here. Check (c) is a
// no-op with an empty set — the generic drift checks (a)/(b)/(d)–(h)/(j) remain
// fully active over whatever loom's eval-manifest declares.
const CANON_SYNC_ARTIFACT_SET = [];

// Structural tools whose ENTRY + scanner + fixturesDir are pinned to their
// canonical identity (check (i)). Checks (d)-(h) all presuppose the entry
// exists; without this pin, deleting {entry, scanner file, fixtures dir} in one
// edit erases the whole structural tier (structural_run:0) while the gate stays
// green, and repointing `fixturesDir` to a decoy dir dodges the (h) polarity
// floor via a fresh fixtures tree. Pinning the triple makes both HARD fails.
//
// LOOM ADAPTATION (C2 §3.2): EMPTY at loom. The BUILD-repo pin was `canon-sync`
// — the one structural tool this harness excludes at loom (its scanner
// `canon-sync-readiness-check.mjs` belongs to the SEPARATE F3 canon-incorporation
// decision, deliberately NOT adopted here). loom has NO structural scanners yet,
// so there is no entry to pin; check (i) is a no-op with an empty list. When loom
// authors a local structural scanner it pins {key, type, scanner, fixturesDir}
// here to lock the entry against deletion / decoy-repoint — the disarm class the
// under-declaration checks (a)-(g) structurally cannot see.
const REQUIRED_STRUCTURAL_ENTRIES = [];

/**
 * @param {{manifestPath: string, repoRoot: string}} opts
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function checkManifestIntegrity({ manifestPath, repoRoot }) {
  const errors = [];
  const rel = (p) => (isAbsolute(p) ? p : resolve(repoRoot, p));
  const claudeRoot = resolve(repoRoot, ".claude");
  // Real (symlink-resolved) .claude root — the containment baseline the (j)
  // realpath check compares against, so a repo whose own path has a symlink
  // component (macOS /tmp -> /private/tmp, a symlinked home) is handled correctly.
  let realClaudeRoot = claudeRoot;
  try {
    realClaudeRoot = realpathSync(claudeRoot);
  } catch {
    /* .claude absent (fresh repo) — the per-path realpath below simply won't run */
  }

  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch (e) {
    return { ok: false, errors: [`manifest not readable/parseable at ${manifestPath}: ${e.message}`] };
  }

  const keys = new Set(Object.keys(manifest).filter((k) => !k.startsWith("_")));

  // (a) every non-null scanner/fixturesDir/probes path resolves on disk.
  for (const key of keys) {
    const spec = manifest[key];
    if (!spec || typeof spec !== "object") {
      errors.push(`entry '${key}' is not an object`);
      continue;
    }
    for (const field of ["scanner", "fixturesDir", "probes"]) {
      const val = spec[field];
      if (val == null) continue;
      const p = rel(val);
      // (j) containment — the resolved path MUST stay inside the .claude/ tree.
      // Reject `../payload.mjs` / absolute-outside before any stat, so an
      // out-of-tree scanner cannot reach coc-eval-core's execFileSync.
      const norm = resolve(p);
      if (norm !== claudeRoot && !norm.startsWith(claudeRoot + sep)) {
        errors.push(`entry '${key}'.${field} resolves outside the .claude/ tree: ${val} (a scanner/fixtures/probes path MUST be contained within .claude/ — an out-of-tree path is an execution/containment escape)`);
        continue;
      }
      const ok = field === "fixturesDir" ? existsSync(p) && statSync(p).isDirectory() : existsSync(p);
      if (!ok) {
        errors.push(`entry '${key}'.${field} does not resolve on disk: ${val} (declared-but-missing = FAIL, never SKIP)`);
        continue;
      }
      // (j cont'd) SYMLINK containment — the lexical check above rejects `../` in
      // the manifest STRING, but resolve() does not follow symlinks. A symlink AT
      // a lexically-contained path whose target escapes .claude/ would pass the
      // lexical check yet reach an out-of-tree file — and execFileSync on a
      // symlinked scanner is arbitrary out-of-tree code execution. Re-check the
      // REAL (symlink-resolved) path stays inside .claude/.
      try {
        const realP = realpathSync(p);
        if (realP !== realClaudeRoot && !realP.startsWith(realClaudeRoot + sep)) {
          errors.push(`entry '${key}'.${field} is a symlink whose real target escapes the .claude/ tree: ${val} -> ${realP} (symlink containment escape — a symlinked scanner would execFileSync out-of-tree code)`);
        }
      } catch (e) {
        errors.push(`entry '${key}'.${field} realpath check failed: ${val} (${e.message})`);
      }
    }
  }

  // (b) every probe row's artifact_id is a manifest key.
  const probeFiles = new Set();
  for (const key of keys) {
    const pf = manifest[key] && manifest[key].probes;
    if (pf) probeFiles.add(pf);
  }
  for (const pf of probeFiles) {
    const p = rel(pf);
    if (!existsSync(p)) continue; // already flagged by (a)
    let rows;
    try {
      rows = JSON.parse(readFileSync(p, "utf8"));
    } catch (e) {
      errors.push(`probe file ${pf} is not parseable JSON: ${e.message}`);
      continue;
    }
    if (!Array.isArray(rows)) {
      errors.push(`probe file ${pf} is not a JSON array of probe rows`);
      continue;
    }
    rows.forEach((row, i) => {
      const aid = row && row.artifact_id;
      if (!aid) {
        errors.push(`probe file ${pf} row ${i} is missing artifact_id`);
      } else if (!keys.has(aid)) {
        errors.push(`probe file ${pf} row ${i} artifact_id '${aid}' is not a manifest key`);
      }
    });
  }

  // (c) every on-disk canon-sync/eval-harness COC artifact has a manifest entry.
  for (const [artPath, expectedKey] of CANON_SYNC_ARTIFACT_SET) {
    if (!existsSync(rel(artPath))) continue; // not present in this repo — not a gap
    if (!keys.has(expectedKey)) {
      errors.push(`on-disk COC artifact ${artPath} has no manifest entry (expected key '${expectedKey}')`);
    }
  }

  // (d) structural-coverage invariants, keyed to close the disarm CLASS rather
  // than a single vector (the attacker controls both `type` and `expected` in
  // the manifest they read):
  //   (d1) a `type:tool` entry MUST carry a non-null scanner — a tool's only
  //        eval coverage is its structural fixtures (coc-artifact-eval-coverage.md
  //        MUST-1 bootstrap note).
  //   (d2) ANY entry with a non-null scanner MUST carry a non-empty `expected`
  //        map — TYPE-INDEPENDENT. A registered scanner that runs zero fixtures
  //        passes vacuously, erasing structural coverage while green. Keying d2
  //        on `type` (not scanner presence) would let a retype-to-prose-type +
  //        null-expected edit keep the scanner "registered" (so check (f) stays
  //        quiet) yet run 0 fixtures. A genuine probe-only entry has scanner:null
  //        and is exempt.
  for (const key of keys) {
    const spec = manifest[key];
    if (!spec || typeof spec !== "object") continue;
    if (spec.type === "tool" && spec.scanner == null) {
      errors.push(`entry '${key}' is type:tool but has a null scanner — a tool MUST carry a structural fixture set (a null scanner silently erases structural coverage while coc-eval-all stays green)`);
    }
    if (spec.scanner != null && (!spec.expected || typeof spec.expected !== "object" || Object.keys(spec.expected).length === 0)) {
      errors.push(`entry '${key}' has a scanner but an empty 'expected' map — a registered scanner that runs zero fixtures is vacuous coverage (zero fixtures = zero coverage, regardless of the entry's declared type)`);
    }
    // (h) bipolar detection floor — an entry with a scanner and a non-empty
    // `expected` MUST assert BOTH a clean-input case (exit 0) AND a
    // violation-detection case (a non-zero exit). One-polarity coverage erases
    // half the detection contract while green (header (h)); keyed on scanner
    // presence (type-independent, like d2) so a retype dodge cannot evade it.
    if (spec.scanner != null && spec.expected && typeof spec.expected === "object" && Object.keys(spec.expected).length > 0) {
      const exits = Object.values(spec.expected)
        .map((c) => (c && typeof c === "object" ? c.exit : undefined))
        .filter((e) => typeof e === "number");
      const hasClean = exits.some((e) => e === 0);
      const hasDetection = exits.some((e) => e !== 0);
      if (!hasClean || !hasDetection) {
        errors.push(
          `entry '${key}' has a scanner but its 'expected' map is not BIPOLAR — it MUST assert BOTH a clean-input case (exit 0)${hasClean ? "" : " [MISSING]"} AND a violation-detection case (exit != 0)${hasDetection ? "" : " [MISSING]"}; a single-polarity fixture set (e.g. positives-only after a fixturesDir repoint + expected prune) erases half the detection contract while the gate stays green`,
        );
      }
    }
  }

  // (i) pinned structural entries — the canon-sync structural tool's ENTRY +
  // scanner + fixturesDir are pinned to their canonical identity. Deleting the
  // entry (+ its scanner file + fixtures dir) erases the whole structural tier
  // with structural_run:0 while the gate stays green — checks (d)-(h) all
  // presuppose the entry EXISTS. Pinning the triple makes deletion OR a
  // fixturesDir repoint (the (h)-sibling lever) a HARD fail.
  for (const req of REQUIRED_STRUCTURAL_ENTRIES) {
    const spec = manifest[req.key];
    if (!spec || typeof spec !== "object") {
      errors.push(`required structural entry '${req.key}' is missing from the manifest — deleting a pinned structural tool erases its entire coverage tier (structural_run:0) while the gate stays green`);
      continue;
    }
    if (spec.type !== req.type) {
      errors.push(`required structural entry '${req.key}' must be type:'${req.type}', got '${spec.type}' — a retype dodges the type:tool-keyed structural checks`);
    }
    if (spec.scanner !== req.scanner) {
      errors.push(`required structural entry '${req.key}'.scanner is pinned to '${req.scanner}' (got ${JSON.stringify(spec.scanner)}) — a repoint or null disarms the structural gate`);
    }
    if (spec.fixturesDir !== req.fixturesDir) {
      errors.push(`required structural entry '${req.key}'.fixturesDir is pinned to '${req.fixturesDir}' (got ${JSON.stringify(spec.fixturesDir)}) — a repoint to a decoy fixtures dir erases detection coverage via a fresh tree`);
    }
    // (i cont'd) DETECTION-CLASS pin-lock — every violation-detection case
    // (exit != 0) in a required entry's `expected` MUST pin a non-empty
    // `critical_failures` list. coc-eval-core then asserts the fixture ACTUALLY
    // fails those named critical checks, binding the fixture to its detection
    // CLASS. Without this, a fixture-content swap (same exit + grade, a DIFFERENT
    // failing check) erases a named detection class's coverage at exit 0; dropping
    // the pin here would be the manifest-only way to unbind it.
    if (spec.expected && typeof spec.expected === "object") {
      for (const [caseName, c] of Object.entries(spec.expected)) {
        if (c && typeof c === "object" && typeof c.exit === "number" && c.exit !== 0) {
          if (!Array.isArray(c.critical_failures) || c.critical_failures.length === 0) {
            errors.push(`required structural entry '${req.key}'.expected['${caseName}'] is a violation case (exit ${c.exit}) but pins no non-empty 'critical_failures' — the fixture is not bound to a named detection class (a content swap to a different failing check would pass silently)`);
          }
        }
      }
    }
  }

  // (e) every *.probes.json on disk is referenced by some manifest entry — an
  // orphan probe file (present but unregistered) is a coverage claim nobody runs.
  const probesDir = rel(join(".claude", "test-harness", "probes"));
  if (existsSync(probesDir) && statSync(probesDir).isDirectory()) {
    const registered = new Set([...probeFiles].map((pf) => resolve(rel(pf))));
    for (const fname of readdirSync(probesDir)) {
      if (!fname.endsWith(".probes.json")) continue;
      if (!registered.has(resolve(join(probesDir, fname)))) {
        errors.push(`orphan probe file .claude/test-harness/probes/${fname} is not referenced by any manifest entry (present-but-unregistered = a coverage claim nobody runs)`);
      }
    }
  }

  // (f) every *-readiness-check.mjs scanner on disk is referenced by some
  // manifest entry's `scanner` — an orphan scanner (present but unregistered)
  // is a structural gate nothing runs. Closes the F1 retype/delete disarm CLASS:
  // check (d) + the coverage floor key on the attacker-controlled `type`, so a
  // retype-to-prose-type OR a deleted entry erases structural coverage while
  // staying green — but both ORPHAN the scanner, caught here type-independently.
  const binDir = rel(join(".claude", "bin"));
  if (existsSync(binDir) && statSync(binDir).isDirectory()) {
    const registeredScanners = new Set();
    for (const key of keys) {
      const sc = manifest[key] && manifest[key].scanner;
      if (sc) registeredScanners.add(resolve(rel(sc)));
    }
    for (const fname of readdirSync(binDir)) {
      if (!fname.endsWith("-readiness-check.mjs")) continue;
      if (!registeredScanners.has(resolve(join(binDir, fname)))) {
        errors.push(`orphan scanner .claude/bin/${fname} is not referenced by any manifest entry's scanner (present-but-unregistered = a structural gate nothing runs; a manifest edit that retypes or deletes its entry disarms the gate)`);
      }
    }
  }

  // (g) fixture-set completeness — every payload-bearing fixture-case subdir on
  // disk is asserted in `expected`. Closes the `expected`-truncation disarm:
  // dropping the negative cases from `expected` leaves the scanner running only
  // the fixtures it passes, erasing its detection coverage while green. A helper
  // dir (flat, README/.md-only, no payload subtree) is excluded — the
  // discriminator is "contains a subdirectory OR a non-.md file".
  for (const key of keys) {
    const spec = manifest[key];
    if (!spec || typeof spec !== "object") continue;
    if (spec.scanner == null || spec.fixturesDir == null) continue;
    const fdir = rel(spec.fixturesDir);
    if (!existsSync(fdir) || !statSync(fdir).isDirectory()) continue; // (a) flags a missing fixturesDir
    const declared = new Set(Object.keys(spec.expected || {}));
    let subdirs;
    try {
      subdirs = readdirSync(fdir, { withFileTypes: true });
    } catch (e) {
      errors.push(`fixturesDir ${spec.fixturesDir} for entry '${key}' is not readable: ${e.message}`);
      continue;
    }
    for (const sub of subdirs) {
      if (!sub.isDirectory()) continue; // only case dirs can be fixture cases
      // Guard the nested read (EACCES / TOCTOU) so a transient failure surfaces
      // as a clean FAIL, not an uncaught throw — mirroring check (b)'s try/catch.
      let children;
      try {
        children = readdirSync(join(fdir, sub.name), { withFileTypes: true });
      } catch (e) {
        errors.push(`fixture case dir '${sub.name}' under ${spec.fixturesDir} is not readable: ${e.message}`);
        continue;
      }
      const isFixtureCase = children.some((c) => c.isDirectory() || !c.name.toLowerCase().endsWith(".md"));
      if (isFixtureCase && !declared.has(sub.name)) {
        errors.push(`fixture case '${sub.name}' under ${spec.fixturesDir} is present on disk but NOT asserted in entry '${key}'.expected — an un-asserted fixture is coverage nobody runs (dropping a violation-detection case erases the scanner's detection coverage while the gate stays green)`);
      }
    }
  }

  return { ok: errors.length === 0, errors };
}

// --------------------------------------------------------------------------
// Standalone CLI
// --------------------------------------------------------------------------
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const repoRoot = resolve(__dirname, "..", "..");
  const args = process.argv.slice(2);
  const jsonMode = args.includes("--json");
  let manifestPath = join(repoRoot, ".claude", "test-harness", "eval-manifest.json");
  const mi = args.indexOf("--manifest");
  if (mi !== -1 && args[mi + 1]) {
    manifestPath = isAbsolute(args[mi + 1]) ? args[mi + 1] : resolve(process.cwd(), args[mi + 1]);
  }
  const result = checkManifestIntegrity({ manifestPath, repoRoot });
  if (jsonMode) {
    console.log(JSON.stringify({ case: "manifest-integrity", ...result }, null, 2));
  } else if (result.ok) {
    console.log("manifest-integrity: PASS — manifest ↔ probes ↔ on-disk artifacts consistent");
  } else {
    console.log("manifest-integrity: FAIL");
    for (const e of result.errors) console.log(`  - ${e}`);
  }
  process.exit(result.ok ? 0 : 1);
}
