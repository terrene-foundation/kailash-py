#!/usr/bin/env node
/**
 * coc-manifest-integrity — the F1-class tripwire for the COC eval-manifest.
 *
 * CLASS-DERIVED PIN SETS (loom#1393). Checks (c) and (i) assert a proposition
 * that DIFFERS per repo class, and this file is `BUILD_ONLY_ALWAYS_INCLUDE`
 * (sync-tier-aware.mjs:602) — shipped VERBATIM to every `coc-build` consumer.
 * Their two backing sets are therefore resolved from `.claude/VERSION::type` via
 * the ONE shared class predicate (`lib/manifest-source.mjs::readRepoClass`), not
 * hardcoded; see § CLASS-DERIVED PIN SETS below for the split and for why an
 * UNDECLARED set emits a loud, actionable WARN rather than silently degrading to
 * an empty one. (It is NOT a hard fail: a hard fail would red-CI a
 * never-surveyed consumer whose harness works — the `security.md`
 * secure-default WARN path. An UNRESOLVABLE class still fails CLOSED.)
 *
 * At loom (`coc-source`) the (c) must-register set is empty by declaration —
 * loom EXCLUDES the canon-sync scanner (`canon-sync-readiness-check.mjs`, an F3
 * concern) — while the (i) pin set carries loom's OWN structural scanner,
 * `detection-binding-check` (added 2026-07-28; see IN_CODE_PIN_SETS below). Every
 * GENERIC drift check — (a) path-resolution, (b) probe artifact_id, (d)
 * structural-coverage invariants, (e)/(f)/(g) orphan-probe/scanner/fixture, (h)
 * bipolar floor, (j) containment, (k) declared-empty — stays fully active over
 * whatever loom's eval-manifest declares. loom's committed eval-manifest now has
 * ONE structural entry and therefore carries NO `_declared_empty` declaration
 * (check (k) HARD-FAILS a stale one alongside real entries); a clean run reports
 * 1 entry, integrity PASS, and coc-eval-all prints ALL STRUCTURAL PASS with
 * `coverage_asserted: true`.
 *
 * The eval-manifest ↔ probe-file ↔ on-disk-artifact triad can silently drift:
 * a probe file registered under the wrong key, a scanner/fixtures/probes path
 * that no longer resolves, a new COC artifact landed on disk with no manifest
 * entry. Each drift makes `coc-eval-all.mjs` report GREEN while the coverage it
 * claims does not exist. This module HARD-FAILS on any such drift so the
 * structural gate cannot pass over a broken manifest.
 *
 * Eleven checks, (a) through (k) — all HARD errors (zero-tolerance.md Rule 2,
 * no silent pass). (The header said "Five" while listing ten; corrected with
 * (k) in loom#1368 part 2.)
 *   (a) every non-null `scanner` / `fixturesDir` / `probes` manifest path
 *       resolves on disk (a DECLARED-BUT-MISSING scanner FAILS, never SKIPS);
 *   (b) every probe row's `artifact_id` is a manifest key (a probe file
 *       registered against a phantom key is a coverage lie);
 *   (c) every on-disk must-register COC artifact (the CLASS-DERIVED set — see
 *       § CLASS-DERIVED PIN SETS) has a manifest entry (the F1-class "artifact
 *       present but absent from the manifest" gap the two-tier coverage
 *       contract blocks);
 *   (d) every `type:tool` entry carries a NON-null `scanner` AND a non-empty
 *       `expected` map — a tool's correctness is proven ONLY by its structural
 *       fixtures (coc-artifact-eval-coverage.md MUST-1 bootstrap note), so a
 *       `type:tool` entry downgraded to `scanner:null` would silently erase all
 *       structural coverage while coc-eval-all still reported GREEN (the
 *       scanner-null disarm — a one-token manifest edit disabling the CI teeth);
 *   (e) every probe file on disk under the probes dir — `*.probes.json` AND
 *       `*.probes.jsonl` — is referenced by some manifest entry OR declared in
 *       `_deferred_probes`; an orphan probe file (present, unregistered,
 *       undeclared) is a coverage claim nobody runs (fail-open drift the gate
 *       must surface). BOTH extensions are enumerated because matching only
 *       `.probes.json` made a rename to `.probes.jsonl` a silent bypass, in
 *       active use at loom as an escape hatch (loom#1368 part 2C). A staged
 *       probe file that is knowingly not yet registered is legal but must be
 *       DECLARED per-file with {reason, graduation} — legal, loud, and time-
 *       bounded, instead of invisible; a deferral whose file is gone is STALE
 *       and fails, so it cannot pre-clear the next staged file at that path;
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
 *   (i) PINNED structural entries — each pinned structural tool (its manifest
 *       entry, its `scanner`, AND its `fixturesDir`) is locked to its canonical
 *       identity; the pin set is CLASS-DERIVED (see § CLASS-DERIVED PIN SETS),
 *       and an UNDECLARED set on a class loom does not declare in code emits a
 *       loud, actionable WARN — never a SILENT empty pass. An EMPTY-but-present
 *       stanza takes the same WARN path (adoption is decided on CONTENT, not on
 *       the stanza's presence). PARTIAL adoption (one set real, its sibling
 *       empty) is a KNOWN GAP, filed rather than warned: a repo may legitimately
 *       pin structural entries and have nothing that must be registered, and
 *       there is no per-set way to SAY so, so warning on emptiness alone
 *       false-fires on that legitimate shape — see the note at
 *       `resolveDeclaredPinSets`.
 *       Checks (d)-(h) all PRESUPPOSE the entry exists; deleting the
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
 *   (k) DECLARED-EMPTY vs SILENTLY-EMPTIED (loom#1368 part 2) — a manifest with
 *       ZERO eval entries verifies NOTHING, so exit 0 over it is defensible ONLY
 *       when zero is the DECLARED intent. A zero-entry manifest MUST carry a
 *       top-level `_declared_empty: { reason, graduation }` (both non-empty
 *       strings); without it the manifest is UNCONFIGURED or silently-emptied
 *       — indistinguishable from drift — and HARD-FAILS. The converse is also a
 *       HARD fail: a `_declared_empty` alongside real entries is a STALE
 *       declaration that would silently re-authorize a future zero-entry run.
 *       This is the manifest half of the vacuous-gate fix; the loud NO-COVERAGE
 *       banner is the coc-eval-all half.
 *
 * (e)/(f)/(g) together make the manifest a COMPLETE reflection of on-disk
 * coverage — every on-disk probe file, scanner, AND fixture case MUST be
 * declared — so coverage cannot be silently erased by UNDER-declaring it.
 * (h)/(i)/(j) close the residual OVER-mutation levers (`expected` polarity
 * pruning, wholesale entry+file deletion, out-of-tree path repoint) that the
 * under-declaration checks (a)-(g) structurally cannot see. (k) closes the
 * floor beneath them all: erasing EVERY entry at once leaves nothing for
 * (a)-(j) to check, so the zero-entry state itself must be declared.
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
// The ONE class predicate (`security.md` § Enforcement-Surface Parity — a second
// hand-rolled `.claude/VERSION` reader would agree with itself while disagreeing
// with production). Ships to every consumer class via sync-tier-aware.mjs's
// ALWAYS_INCLUDE (`.claude/bin/lib/manifest-source.mjs`), so this import resolves
// on BUILD exactly as it does at loom.
import {
  KNOWN_REPO_CLASSES,
  MANIFEST_OWNER_CLASS,
  readRepoClass,
} from "./lib/manifest-source.mjs";

// ────────────────────────────────────────────────────────────────
// CLASS-DERIVED PIN SETS (loom#1393)
// ────────────────────────────────────────────────────────────────
//
// Check (c) enumerates the must-be-registered COC artifacts (each on-disk member
// MUST have a manifest entry under `key`). Check (i) pins a structural tool's
// {entry, type, scanner, fixturesDir} to its canonical identity — checks (d)-(h)
// all PRESUPPOSE the entry exists, so without the pin, deleting {entry, scanner
// file, fixtures dir} in one edit erases the whole structural tier
// (structural_run:0) while the gate stays green, and repointing `fixturesDir` to
// a decoy dir dodges the (h) polarity floor via a fresh fixtures tree.
//
// Both sets were a flat `[]` until loom#1393. That was correct AT loom and WRONG
// everywhere else: this file is `BUILD_ONLY_ALWAYS_INCLUDE`
// (sync-tier-aware.mjs:602), so the loom value was shipped verbatim to every
// `coc-build` repo, where both checks iterated an empty list, could never fire,
// and the harness still reported green. For an ASSERTION an empty set is not a
// neutral default — it is a VACUOUS PASS, indistinguishable from a real check,
// the exact shape `lib/manifest-source.mjs`'s D4 disposition rejects.
//
// WHY THE BUILD SET IS NOT ENUMERATED HERE. loom cannot know a BUILD repo's
// scanner and fixture paths: they are that repo's data, they differ between
// BUILD repos, and loom holds no copy of them. Hardcoding a class -> set table
// for a class whose members loom cannot see would repeat the SAME category error
// one level up — a loom-side guess shipped verbatim as though it were the
// consumer's truth. So the split is by WHO OWNS THE DATA:
//
//   coc-source (loom)   the set is loom's OWN -> declared IN CODE below.
//   every other class   the set is that repo's own data -> declared in ITS OWN
//                       eval-manifest (`_must_register_artifacts`,
//                       `_required_structural_entries`). loom ships the ENGINE
//                       that ENFORCES the declaration, never its content.
//
// UNDECLARED IS NOT EMPTY. A repo routed to the manifest-declared branch that
// declares NEITHER pins NOR an explicit `_declared_no_pins` has not adopted the
// contract yet. It does NOT silently pass — it emits a LOUD, one-time,
// ACTIONABLE warning naming the missing stanza and the exact wiring to add.
//
// WHY A WARN HERE AND A HARD FAIL EVERYWHERE ELSE (`security.md` § "Secure-
// Default For A New Security Feature"). That rule's contract is: fail CLOSED,
// OR — where backward-compat genuinely forbids on-by-default — emit a loud
// one-time WARN naming the OFF protection and its wiring. A silent no-op is the
// only BLOCKED option. This clause lands in a file that ships to `coc-build`
// repos NOBODY HAS SURVEYED: a repo already carrying a working eval-manifest
// without the new stanzas would be converted from green to hard-fail on its next
// sync — a regression shipped to a consumer sight-unseen. That is the exact
// backward-compat case the WARN path exists for, so the UN-ADOPTED state warns.
//
// EVERY OTHER SHAPE STAYS FAIL-CLOSED, because none of them is a backward-compat
// case — each requires the repo to have ALREADY adopted the contract, or to be
// broken independently:
//   · class UNRESOLVABLE            — a repo with no valid `.claude/VERSION` is
//                                     already broken for emit (manifest-source
//                                     throws on it); nothing regresses.
//   · `_declared_no_pins` malformed / short / EXPIRED / alongside real pins
//   · a declared pin VIOLATED       — entry deleted, retyped, scanner or
//                                     fixturesDir repointed, partial triple
// So the ratchet has teeth the moment a repo declares anything at all.
//
// RESIDUAL, stated rather than glossed: while a repo stays un-adopted, (c)/(i)
// assert nothing there — loudly, not silently. Deleting a pin declaration also
// drops back to the WARN. Closing that needs a per-repo survey (loom#1393
// established the BUILD ground truth does not exist at kailash-py; kailash-rs
// was NOT read and is not covered by the authorization).

// The manifest's canonical repo-relative location, named in the un-adopted WARN
// so the remediation says WHICH file to edit (the runtime `manifestPath` may be
// a `--manifest` override or a temp path).
const MANIFEST_REL_LABEL = ".claude/test-harness/eval-manifest.json";

/**
 * The PATH-BEARING fields of an eval-manifest ENTRY — the fields check (a)
 * below resolves on disk, and the ONE notion of "this manifest value names a
 * file/directory".
 *
 * EXPORTED because loom#1549 ask 3's delivery-side gate
 * (`sync-tier-aware.mjs::declaredReferentBreaks`) must adjudicate exactly the
 * references THIS checker will later demand resolve at the target. Two
 * hand-maintained field lists would drift, and the drift is silent in the worst
 * direction: a new path-bearing field would be enforced HERE (at the target,
 * after delivery) while the delivery gate never looked at it — which is the
 * #1549 shape one field over. Importing the constant makes the delivery gate
 * learn any new field by construction.
 *
 * `fixturesDir` is the one DIRECTORY member; the other two name files. The
 * split matters to the consumer (a directory survives while it still holds an
 * unpurged file), so it is recorded here beside the list rather than
 * re-derived there.
 */
export const MANIFEST_PATH_FIELDS = Object.freeze(["scanner", "fixturesDir", "probes"]);
export const MANIFEST_DIR_FIELDS = Object.freeze(["fixturesDir"]);

// Positive allowlist (`cc-artifacts.md` Rule 10): repo class -> the pin sets
// loom declares IN CODE. A class ABSENT from this table is NOT bucketed into
// "empty" — it routes to the manifest-declared branch, which WARNS loudly when
// un-adopted and fails closed on every malformed or violated declaration.
const IN_CODE_PIN_SETS = Object.freeze({
  // loom adopts the eval ENGINE and EXCLUDES the canon-sync scanner
  // (`canon-sync-readiness-check.mjs` belongs to the SEPARATE F3
  // canon-incorporation decision).
  //
  // (c) mustRegisterArtifacts stays EMPTY. loom carries some canon-sync artifacts
  // on disk (`sync-from-canon.md`, `test-harness-probe.md`) for DISTRIBUTION to
  // targets while declaring no eval entries for them, so an enumerated (c) set
  // would false-FAIL on every distributed-but-not-evaluated artifact.
  //
  // (i) requiredStructuralEntries is NO LONGER EMPTY as of 2026-07-28.
  // `detection-binding-check` is loom's FIRST local structural scanner — the
  // detector for `coc-artifact-eval-coverage.md` MUST-4, whose own mandate
  // (every enforcement rule names a RESOLVING scanner + fixtures + probe
  // binding) had no enforcement until it landed. Pinning the triple {key, type,
  // scanner, fixturesDir} is what makes deleting the entry, retyping it to a
  // prose type, or repointing `fixturesDir` at a decoy tree a HARD fail:
  // checks (d)-(h) all PRESUPPOSE the entry exists, and the scanner is NOT named
  // `*-readiness-check.mjs`, so check (f)'s orphan sweep would not catch its
  // deletion either. This pin is the only thing standing between a one-line
  // manifest edit and the silent removal of loom's whole structural tier.
  //
  // The manifest's `_declared_empty` declaration was REMOVED in the same change,
  // per its own stated graduation condition; check (k) HARD-FAILS a stale
  // declaration carried alongside a real structural entry.
  [MANIFEST_OWNER_CLASS]: Object.freeze({
    mustRegisterArtifacts: Object.freeze([]),
    requiredStructuralEntries: Object.freeze([
      Object.freeze({
        key: "detection-binding-check",
        type: "tool",
        scanner: ".claude/bin/detection-binding-check.mjs",
        fixturesDir: ".claude/audit-fixtures/detection-binding-check",
      }),
    ]),
  }),
});

/**
 * Resolve the (c)/(i) pin sets for THIS repo's class (loom#1393).
 *
 * @returns {{class: string, source: string, mustRegisterArtifacts: Array,
 *            requiredStructuralEntries: Array} | null}
 *   `null` when the sets cannot be resolved. The explaining error has ALREADY
 *   been pushed onto `errors`, and the caller MUST skip (c)/(i) rather than run
 *   them over an invented empty set — running them would print the same vacuous
 *   PASS this whole section exists to prevent. The UN-ADOPTED state is the one
 *   exception: it returns empty sets and pushes a LOUD warning (see § CLASS-
 *   DERIVED PIN SETS for why that one case warns instead of failing).
 */
function resolvePinSets(manifest, repoRoot, errors, warnings) {
  const { type, error } = readRepoClass(repoRoot);
  if (error) {
    errors.push(
      `repo class UNRESOLVED — ${error}. Checks (c) (must-register artifacts) and (i) (pinned structural entries) assert a DIFFERENT proposition per class (${MANIFEST_OWNER_CLASS}: loom's own in-code set; every other class: the set declared in this repo's OWN eval-manifest), so they fail CLOSED rather than guess. Defaulting to an empty set would make BOTH checks vacuous — a PASS indistinguishable from a real check. Repair .claude/VERSION::type (known classes: ${KNOWN_REPO_CLASSES.join(", ")}).`,
    );
    return null;
  }
  if (Object.hasOwn(IN_CODE_PIN_SETS, type)) {
    // A manifest-declared pin on a class whose sets come from CODE would be
    // SILENTLY IGNORED — an author adding one would believe it took effect while
    // the in-code set governed. Say so rather than drop it (zero-tolerance.md
    // Rule 3).
    for (const stanza of [
      "_must_register_artifacts",
      "_required_structural_entries",
      "_declared_no_pins",
    ]) {
      if (manifest[stanza] != null) {
        errors.push(
          `manifest declares '${stanza}' but this repo's class is "${type}", whose (c)/(i) pin sets are declared IN CODE — the declaration would be SILENTLY IGNORED. Remove the stanza, or change the in-code set for this class.`,
        );
      }
    }
    return { class: type, source: "in-code", ...IN_CODE_PIN_SETS[type] };
  }
  return resolveDeclaredPinSets(manifest, type, errors, warnings);
}

/**
 * The manifest-declared branch: for every class loom does NOT declare in code,
 * the pins are the REPO'S OWN declaration. An ABSENT declaration is the
 * UN-ADOPTED state and emits a loud actionable WARN; every malformed or
 * VIOLATED declaration is a HARD FAIL.
 */
function resolveDeclaredPinSets(manifest, klass, errors, warnings) {
  const rawArtifacts = manifest._must_register_artifacts;
  const rawEntries = manifest._required_structural_entries;
  const noPins = manifest._declared_no_pins;
  const declaredAny = rawArtifacts != null || rawEntries != null;

  if (noPins != null) {
    // The CONTRADICTION arm, mirroring check (k)'s stale-`_declared_empty`
    // ratchet: once real pins exist the "no pins" declaration is stale and MUST
    // go, so it cannot lie dormant and re-authorize a future un-pinning.
    if (declaredAny) {
      errors.push(
        `manifest carries a '_declared_no_pins' declaration AND declares pins ('_must_register_artifacts' / '_required_structural_entries') — the declaration is STALE and MUST be removed now that pins exist (leaving it would silently re-authorize a future un-pinned run)`,
      );
      return null;
    }
    validateDeclaration("'_declared_no_pins'", noPins, errors);
    return {
      class: klass,
      source: "declared-none",
      mustRegisterArtifacts: [],
      requiredStructuralEntries: [],
    };
  }

  if (!declaredAny) {
    // UN-ADOPTED. Loud, one-time, ACTIONABLE — never silent, and deliberately
    // not terminal (see § CLASS-DERIVED PIN SETS: this is the `security.md`
    // secure-default WARN path, because a hard fail here would convert a
    // never-surveyed BUILD repo's working harness into a red CI on next sync).
    warnings.push(
      `checks (c) and (i) ASSERT NOTHING in this repo: its class is "${klass}", whose pin sets come from THIS manifest, and it declares none. ` +
        `loom ships the integrity ENGINE but cannot know a "${klass}" repo's scanner/fixture paths, so the pins are this repo's to declare. ` +
        `Until then a deleted/retyped/repointed structural entry is NOT caught by (i), and an unregistered must-register artifact is NOT caught by (c). ` +
        `TO WIRE IT, add ONE of these to ${MANIFEST_REL_LABEL}: ` +
        `(1) the pins — "_required_structural_entries": { "<manifest-key>": { "type": "tool", "scanner": ".claude/bin/<name>-readiness-check.mjs", "fixturesDir": ".claude/audit-fixtures/<name>" } } ` +
        `and/or "_must_register_artifacts": { "<repo-relative-artifact-path>": "<expected-manifest-key>" }; ` +
        `or (2) an explicit no-pins declaration — "_declared_no_pins": { "reason": "<why this repo pins no structural entry>", "graduation": "<what ends this declaration>", "expires": "<YYYY-MM-DD>" }. ` +
        `Once EITHER is present the checks become enforcing and every violation is a HARD fail.`,
    );
    return {
      class: klass,
      source: "un-adopted",
      mustRegisterArtifacts: [],
      requiredStructuralEntries: [],
    };
  }

  const mustRegisterArtifacts = [];
  if (rawArtifacts != null) {
    if (typeof rawArtifacts !== "object" || Array.isArray(rawArtifacts)) {
      errors.push(
        `'_must_register_artifacts' must be an object mapping a repo-relative artifact path to its expected manifest key, got ${Array.isArray(rawArtifacts) ? "an array" : typeof rawArtifacts}`,
      );
      return null;
    }
    for (const [artPath, expectedKey] of Object.entries(rawArtifacts)) {
      if (typeof expectedKey !== "string" || expectedKey.trim() === "") {
        errors.push(
          `'_must_register_artifacts'['${artPath}'] must map to a non-empty manifest key string, got ${JSON.stringify(expectedKey)}`,
        );
        continue;
      }
      mustRegisterArtifacts.push([artPath, expectedKey]);
    }
  }

  const requiredStructuralEntries = [];
  if (rawEntries != null) {
    if (typeof rawEntries !== "object" || Array.isArray(rawEntries)) {
      errors.push(
        `'_required_structural_entries' must be an object mapping a manifest key to its pinned { type, scanner, fixturesDir } triple, got ${Array.isArray(rawEntries) ? "an array" : typeof rawEntries}`,
      );
      return null;
    }
    for (const [key, pin] of Object.entries(rawEntries)) {
      if (!pin || typeof pin !== "object" || Array.isArray(pin)) {
        errors.push(
          `'_required_structural_entries'['${key}'] must be an object pinning { type, scanner, fixturesDir }, got ${Array.isArray(pin) ? "an array" : typeof pin}`,
        );
        continue;
      }
      // All THREE fields are mandatory: a partial pin leaves the unpinned field
      // free to be repointed, which is the (h)-sibling decoy lever (i) exists to
      // close.
      const missing = ["type", "scanner", "fixturesDir"].filter(
        (f) => typeof pin[f] !== "string" || pin[f].trim() === "",
      );
      if (missing.length > 0) {
        errors.push(
          `'_required_structural_entries'['${key}'] is missing non-empty string field(s): ${missing.join(", ")} — a PARTIAL pin leaves the unpinned field free to be repointed, which is the decoy lever check (i) exists to close`,
        );
        continue;
      }
      requiredStructuralEntries.push({
        key,
        type: pin.type,
        scanner: pin.scanner,
        fixturesDir: pin.fixturesDir,
      });
    }
  }

  // ADOPTION IS DECIDED ON CONTENT, NOT ON THE STANZA'S PRESENCE.
  //
  // `declaredAny` above keys on `!= null`, which is correct for the
  // `_declared_no_pins` CONTRADICTION arm (a stanza that EXISTS is what makes a
  // "no pins" declaration stale, empty or not) but wrong as an adoption test:
  // `{}` is `!= null`, so an empty stanza counted as ADOPTED and returned here
  // silently while contributing ZERO pins. Measured: key ABSENT → warn=1, key
  // present as `{}` → warn=0. A two-character edit was therefore STRICTLY
  // QUIETER than deleting the key, and it bought identical (zero) enforcement
  // with no reason, no graduation, and — unlike `_declared_no_pins` — NO EXPIRY,
  // so it never aged out. That defeats the very ratchet this file builds, and
  // reproduces the failure mode § CLASS-DERIVED PIN SETS names in its own words:
  // "for an ASSERTION an empty set is not a neutral default — it is a VACUOUS
  // PASS, indistinguishable from a real check."
  //
  // The WARN's own remediation text invited it: "TO WIRE IT, add ONE of these"
  // followed by "Once EITHER is present the checks become enforcing" — false for
  // `{}`. A reader silencing the warning by scaffolding the key was following
  // the instruction.
  //
  // WARN rather than hard-fail, deliberately: this is the same
  // `security.md` secure-default path the un-adopted branch takes, and a hard
  // fail here would red-CI a consumer whose harness works. The point is that the
  // state is no longer SILENT.
  const noneResolved =
    mustRegisterArtifacts.length === 0 && requiredStructuralEntries.length === 0;
  if (noneResolved) {
    warnings.push(
      `checks (c) and (i) ASSERT NOTHING in this repo: its class is "${klass}" and its pin stanza(s) are PRESENT BUT EMPTY, which is not adoption — an empty pin set asserts nothing while silencing the un-adopted warning. ` +
        `Either declare real pins, or state the exemption explicitly with "_declared_no_pins": { "reason": …, "graduation": …, "expires": "<YYYY-MM-DD>" } — which, unlike an empty stanza, EXPIRES and so cannot become a permanent silent disarm.`,
    );
  }
  // PARTIAL adoption (one pin set real, its sibling empty) is deliberately NOT
  // warned here. It is a real gap — one adoption bit governs two INDEPENDENT
  // sets, so declaring either silences the other's notice — but warning on it
  // unconditionally is WRONG: a repo may legitimately pin structural entries and
  // have NOTHING that must be registered, and there is no per-set way to SAY so.
  // A first attempt warned on emptiness alone and false-fired on exactly that
  // legitimate shape (audit fixture `08-coc-build-pin-intact-clean`, which is the
  // clean anti-vacuity control proving case 09 fails from the disarm rather than
  // because a BUILD tree cannot pass — a "clean" control that warns is no longer
  // a control). Closing it properly needs a per-SET declaration, i.e. new
  // manifest schema, which is its own shard. Filed rather than half-built.

  return {
    class: klass,
    source: "manifest-declared",
    mustRegisterArtifacts,
    requiredStructuralEntries,
  };
}

// Minimum substantive length for a declaration's prose fields. A declaration is
// a standing exemption from a coverage gate, so `{"reason":"x","graduation":"y"}`
// — which satisfied a bare non-empty check — is not one. The floor is crude by
// design: it blocks the token placeholder without pretending to judge content,
// which is the reviewer's job (R1 MEDIUM-3).
const DECLARATION_MIN_TEXT = 30;

/**
 * Validate a coverage-gap declaration (`_declared_empty`, or one `_deferred_probes`
 * entry). Both carry the same contract: a substantive reason, a substantive
 * graduation condition, and an EXPIRY. Without the expiry a declaration is green
 * forever — the exact "delete entries, add a two-field declaration, done" bypass
 * (R1 MEDIUM-4). The shape mirrors the sync-manifest headroom-floor exception,
 * which carries an explicit EXPIRES date for the same reason.
 */
function validateDeclaration(label, decl, errors) {
  if (!decl || typeof decl !== "object" || Array.isArray(decl)) {
    errors.push(
      `${label} must be an object with 'reason', 'graduation' and 'expires' fields, got ${Array.isArray(decl) ? "an array" : typeof decl}`,
    );
    return;
  }
  for (const field of ["reason", "graduation"]) {
    const v = decl[field];
    if (typeof v !== "string" || v.trim() === "") {
      errors.push(
        `${label}.${field} must be a non-empty string — a declaration without a ${field === "reason" ? "stated reason is an unexplained coverage gap" : "graduation condition is a permanent blanket, not a deferral"}`,
      );
    } else if (v.trim().length < DECLARATION_MIN_TEXT) {
      errors.push(
        `${label}.${field} is ${v.trim().length} characters — too short to be a real ${field} (minimum ${DECLARATION_MIN_TEXT}). A declaration suppresses a coverage gate; state plainly why, and what ends it.`,
      );
    }
  }
  const exp = decl.expires;
  if (typeof exp !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(exp)) {
    errors.push(
      `${label}.expires must be an ISO calendar date 'YYYY-MM-DD' (got ${JSON.stringify(exp)}) — a declaration with no expiry never ages out and is green forever`,
    );
    return;
  }
  const ts = Date.parse(`${exp}T23:59:59Z`);
  // Round-trip: Date.parse silently rolls invalid days over ("2026-02-30" ->
  // Mar 2), so compare the reformatted date back against the declared string.
  if (Number.isNaN(ts) || new Date(ts).toISOString().slice(0, 10) !== exp) {
    errors.push(`${label}.expires is not a real calendar date: ${exp}`);
    return;
  }
  if (Date.now() > ts) {
    errors.push(
      `${label} is EXPIRED (expires ${exp}) — the declared graduation condition has come due. Either satisfy it (register the coverage) or renew the declaration deliberately with a fresh expiry and an updated reason.`,
    );
  }
}

/**
 * @param {{manifestPath: string, repoRoot: string}} opts
 * @returns {{ ok: boolean, errors: string[], notes: string[] }}
 */
export function checkManifestIntegrity({ manifestPath, repoRoot }) {
  const errors = [];
  // Non-fatal but MUST-be-surfaced findings — currently the declared probe
  // deferrals. A declared deferral is legal, but it is a coverage GAP, so it is
  // reported into the CI log rather than passing invisibly (loom#1368 part 2).
  const notes = [];
  // LOUD non-fatal findings (loom#1393): a gate that ASSERTS NOTHING here but
  // cannot fail closed without regressing an un-surveyed consumer. Distinct from
  // `notes` (a declared, intentional gap) — a warning is an UNDECLARED gap that
  // still needs wiring, and every renderer prints it on PASS *and* on FAIL.
  const warnings = [];
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
    return {
      ok: false,
      errors: [
        `manifest not readable/parseable at ${manifestPath}: ${e.message} — the harness is UNCONFIGURED, which is a FAILURE, never a pass`,
      ],
      notes: [],
      warnings: [],
    };
  }

  const keys = new Set(Object.keys(manifest).filter((k) => !k.startsWith("_")));

  // Resolve the (c)/(i) pin sets from THIS repo's class before either check runs
  // (loom#1393). `null` means the sets are UNRESOLVED or UNDECLARED — the
  // explaining error is already in `errors`, and both checks are SKIPPED rather
  // than run over an invented empty set (a skipped-and-failing check is honest;
  // a check that iterates an assumed-empty list prints a vacuous PASS).
  const pins = resolvePinSets(manifest, repoRoot, errors, warnings);

  // (k) DECLARED-EMPTY vs SILENTLY-EMPTIED (loom#1368 part 2). A zero-entry
  // manifest verifies NOTHING, so exit 0 over it is only defensible when zero is
  // the DECLARED intent. `_declared_empty` is that declaration; without it a
  // zero-entry manifest is indistinguishable from drift (entries deleted, a
  // botched merge, a half-finished adoption) and MUST fail closed.
  //
  // Both fields are mandatory. `reason` is what the run's NO-COVERAGE banner
  // quotes into the CI log; `graduation` is the exit condition, without which the
  // declaration becomes a permanent blanket excusing every future emptying. The
  // CONTRADICTION arm (declaration + real entries) is the ratchet's other half:
  // once the harness has entries the declaration is stale and must be removed,
  // so it cannot lie dormant in the file waiting to excuse the next emptying.
// Keyed on STRUCTURAL coverage, not entry count (R1 HIGH-1). The first version
// asked `keys.size === 0` while coc-eval-all reported coverage as
// `structural.length > 0`, and the gap between those two quantities was a live
// disarm: RETYPING the only structural entry to probe-only
// (`{type:"rule", scanner:null, expected:{}}`) collapsed 1/1 coverage to 0/0 at
// exit 0 with no declaration required. Deleting the entry was caught; hollowing
// it out was not. Neither backstop closes it — (d2) is keyed on
// `scanner != null` and exempts probe-only entries by design, and (f)'s orphan
// sweep only matches `*-readiness-check.mjs`, so a scanner under any other name
// leaves no trace. Keying (k) on the SAME quantity coc-eval-all reports means
// the gate and the coverage claim cannot disagree by construction.
//
// A manifest whose every entry is probe-only genuinely asserts zero structural
// coverage, so it needs the declaration exactly as an empty one does. The
// contradiction arm is keyed the same way: once real structural coverage exists
// the declaration is stale and must go.
  const structuralKeys = [...keys].filter((k) => {
    const spec = manifest[k];
    return spec && typeof spec === "object" && spec.scanner != null;
  });
  const declaredEmpty = manifest._declared_empty;
  if (structuralKeys.length === 0) {
    if (declaredEmpty == null) {
      errors.push(
        `manifest asserts ZERO structural coverage (${keys.size} entr${keys.size === 1 ? "y" : "ies"}, none with a scanner) and carries no '_declared_empty' declaration — an undeclared zero-coverage manifest is an UNCONFIGURED (or silently-emptied/hollowed-out) harness, not a passing one. If zero structural coverage IS the intended steady state, declare it explicitly: "_declared_empty": { "reason": "<why this repo has no structural scanners>", "graduation": "<the condition under which this declaration is removed>", "expires": "<YYYY-MM-DD>" }`,
      );
    } else {
      validateDeclaration("'_declared_empty'", declaredEmpty, errors);
    }
  } else if (declaredEmpty != null) {
    errors.push(
      `manifest carries a '_declared_empty' declaration but has ${structuralKeys.length} structural entr${structuralKeys.length === 1 ? "y" : "ies"} — the declaration is STALE and MUST be removed now that the harness is populated (leaving it in place would silently re-authorize a future zero-coverage run)`,
    );
  }

  // (a) every non-null scanner/fixturesDir/probes path resolves on disk.
  for (const key of keys) {
    const spec = manifest[key];
    if (!spec || typeof spec !== "object") {
      errors.push(`entry '${key}' is not an object`);
      continue;
    }
    for (const field of MANIFEST_PATH_FIELDS) {
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
      const ok = MANIFEST_DIR_FIELDS.includes(field)
        ? existsSync(p) && statSync(p).isDirectory()
        : existsSync(p);
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

  // (c) every on-disk must-register COC artifact has a manifest entry. The set
  // is class-derived (loom#1393): loom's own in-code set at `coc-source`, the
  // repo's `_must_register_artifacts` declaration elsewhere.
  for (const [artPath, expectedKey] of pins ? pins.mustRegisterArtifacts : []) {
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

  // (i) pinned structural entries — a pinned structural tool's ENTRY + scanner +
  // fixturesDir are locked to their canonical identity. Deleting the entry (+ its
  // scanner file + fixtures dir) erases the whole structural tier with
  // structural_run:0 while the gate stays green — checks (d)-(h) all presuppose
  // the entry EXISTS. Pinning the triple makes deletion OR a fixturesDir repoint
  // (the (h)-sibling lever) a HARD fail. The set is class-derived (loom#1393):
  // loom's own in-code set at `coc-source`, the repo's
  // `_required_structural_entries` declaration elsewhere.
  for (const req of pins ? pins.requiredStructuralEntries : []) {
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

  // (e) every probe file on disk is referenced by some manifest entry, OR is
  // explicitly declared deferred — an orphan probe file (present, unregistered,
  // undeclared) is a coverage claim nobody runs.
  //
  // BOTH extensions are enumerated (loom#1368 part 2C). (e) previously matched
  // only `*.probes.json`, so renaming a staged probe file to `.probes.jsonl`
  // made it invisible to this check — and that rename was in active use at loom
  // as a deliberate escape hatch. A file extension is not a coverage decision.
  // `.probes.json` stays the canonical DEFINITION format (check (b) parses it as
  // a JSON array of `artifact_id` rows); `.probes.jsonl` is the extension
  // /test-harness-probe emits for RESULTS and the shape staged definitions were
  // authored in. Either way, a probe file sitting in the probes dir is a
  // coverage claim, so it must be registered or declared — never merely renamed.
  const PROBE_FILE_SUFFIXES = [".probes.json", ".probes.jsonl"];

  // `_deferred_probes` — the explicit, per-file declaration that a staged probe
  // file is knowingly NOT yet registered. Same declared-vs-silent contract as
  // `_declared_empty` (check (k)): a deferral must state its reason AND the
  // condition that ends it, and a deferral whose file is gone is STALE and fails
  // (so the declaration cannot linger and pre-authorize the next staged file).
  const deferredProbes = manifest._deferred_probes;
  const deferredResolved = new Set();
  if (deferredProbes != null) {
    if (typeof deferredProbes !== "object" || Array.isArray(deferredProbes)) {
      errors.push(
        `'_deferred_probes' must be an object mapping a repo-relative probe path to { reason, graduation }, got ${Array.isArray(deferredProbes) ? "an array" : typeof deferredProbes}`,
      );
    } else {
      for (const [probePath, decl] of Object.entries(deferredProbes)) {
        validateDeclaration(`'_deferred_probes'['${probePath}']`, decl, errors);
        if (!decl || typeof decl !== "object" || Array.isArray(decl)) continue;
        const abs = resolve(rel(probePath));
        if (!existsSync(abs)) {
          errors.push(
            `'_deferred_probes'['${probePath}'] is STALE — the declared probe file is not on disk. Remove the declaration in the same change that removes or registers the file (a lingering deferral would silently pre-clear a future staged probe at this path).`,
          );
          continue;
        }
        deferredResolved.add(abs);
        notes.push(`deferred probe (declared, NOT registered — its coverage does NOT run): ${probePath} — ${decl.reason}`);
      }
    }
  }

  const probesDir = rel(join(".claude", "test-harness", "probes"));
  if (existsSync(probesDir) && statSync(probesDir).isDirectory()) {
    const registered = new Set([...probeFiles].map((pf) => resolve(rel(pf))));
    for (const fname of readdirSync(probesDir)) {
      if (!PROBE_FILE_SUFFIXES.some((s) => fname.endsWith(s))) continue;
      const abs = resolve(join(probesDir, fname));
      if (registered.has(abs) || deferredResolved.has(abs)) continue;
      errors.push(
        `orphan probe file .claude/test-harness/probes/${fname} is neither referenced by any manifest entry nor declared in '_deferred_probes' (present-but-unregistered = a coverage claim nobody runs; renaming it to another extension does not clear this check)`,
      );
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

  return { ok: errors.length === 0, errors, notes, warnings };
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
    // A declared deferral is legal but is a coverage GAP — never silent.
    for (const n of result.notes) console.log(`  NOTE: ${n}`);
    // An UNDECLARED gap: the run passed, but a gate asserted nothing. Louder
    // than a NOTE and printed on BOTH branches (loom#1393).
    for (const w of result.warnings ?? []) console.log(`  !! WARN: ${w}`);
  } else {
    console.log("manifest-integrity: FAIL");
    for (const e of result.errors) console.log(`  - ${e}`);
    for (const w of result.warnings ?? []) console.log(`  !! WARN: ${w}`);
  }
  process.exit(result.ok ? 0 : 1);
}
