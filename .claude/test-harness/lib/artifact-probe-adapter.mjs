/*
 * artifact-probe-adapter — dispatch/score adapter for the ARTIFACT-EVAL probe
 * suite row shape (`.claude/test-harness/probes/*.probes.json`).
 *
 * WHY THIS EXISTS (loom#1465). `/test-harness-probe` already scores probes, but
 * only ONE row shape: a test-harness SUITE RESULT row (`state: "needs_probe"`,
 * candidate text = `stdout + stderr`, schema named at
 * `score.criteria[*].probe_schema`). The artifact-eval suites registered in
 * `.claude/test-harness/eval-manifest.json` are a DIFFERENT shape entirely —
 * `{artifact_id, id, pair_id, artifact, artifact_type, property, paired_case,
 * schema, judge_model, rule_ref, candidate_fixture, expect}`, candidate text =
 * the CONTENTS OF A FIXTURE FILE, and no suite run produces them. With no
 * adapter the semantic tier was reproducible only BY HAND. This module is the
 * missing translation layer.
 *
 * SCHEMA AUTHORITY IS NOT DUPLICATED. Every rubric, required-field list, shape
 * and scoringRule is imported from `./probe-schemas.mjs`. This module defines
 * NO schema of its own — per loom#1465 the adapter must not create a second
 * schema surface.
 *
 * TWO PHASES, because Node cannot dispatch CC subagents from a child process
 * (the same split `.claude/skills/test-harness-probe/SKILL.md` § "Why a slash
 * command instead of in-process" already documents):
 *
 *   buildPlan(...)  -> a dispatch plan: one fully-rendered judge prompt per row.
 *                      The CC orchestrator dispatches these in parallel.
 *   scoreAnswers(...) -> validates each returned answer against its schema shape,
 *                      applies the schema's scoringRule, and computes the
 *                      per-PAIR separation verdict.
 *
 * MUST-3 (coc-artifact-eval-coverage.md): an UNRUN or ERRORED probe is ZERO
 * evidence, never a pass. Every row therefore carries an explicit `state` of
 * pass | fail | error | unrun, and the summary reports `coverage_asserted` —
 * the count of rows a judge genuinely answered. A caller MUST cite
 * `coverage_asserted`, never the process exit code alone.
 *
 * ANSWER-KEY HYGIENE, BOTH HALVES OF THE PROMPT. The row's `expect` field and
 * the fixture's `.expected` sidecar are ANSWER KEYS, and so — less obviously —
 * are the schema's NAME and its legacy rubric: `ComplianceViolationAnswer`,
 * "presented as a NON-compliant / adversarial case you must correctly catch",
 * "For a genuine violation you should answer false". None reaches a judge. The
 * fence is structural in buildPlan: the prompt renders ONLY the schema's
 * judgeContract (opaque alias + neutral rubric, SHARED by both poles of a pair),
 * and a rendered prompt that still discloses its pole is REFUSED
 * (`polarity-disclosure`) rather than dispatched.
 *
 * AND THE CANDIDATE'S NAME IS AN ANSWER KEY TOO — the fourth channel, which
 * survived all of the above. Every prompt used to print
 * `CANDIDATE TEXT (.claude/audit-fixtures/<rule>/<name>)`, and 12 of 12 fixture
 * names encode their pole in the prefix: `flag-` / `meta-violation-` on every
 * violation row, `clean-` / `meta-compliant-` on every compliant row. A judge
 * scored the pair off the path without parsing a clause.
 *
 * NEITHER SHIPPED INSTRUMENT COULD SEE IT, and the reasons are worth keeping:
 *   - the SWAPPED-POLE control asserts `prompt = f(candidate)`. The path travels
 *     WITH the candidate, so swapping the poles swaps the paths too and the
 *     identity still holds. The control PASSES with the channel wide open — a
 *     blind spot in the control, not a bug in it.
 *   - `detectPolarityDisclosure`'s lexicon targets rubric phrasing and schema
 *     names; a path prefix is neither. And it is applied to the rubric half
 *     only, which is cut immediately BEFORE the line that carried the path.
 *
 * The fix is structural, not lexical: buildPlan renders NO candidate identity at
 * all by default, so there is no reference from which a pole could be read. The
 * regression fence is `buildIdentifierShuffleControl` — content from this pole,
 * IDENTIFIER from the sibling. If any prompt moves, the identifier is a live
 * polarity channel. The naming convention itself is GOOD (it is how Rule-9
 * fixture sets stay legible); what was wrong was rendering it into a judge.
 *
 * JUDGE-MODEL ATTESTATION. `judge_model` is pinned on the row AND attested by
 * the dispatcher in the answer; scoreAnswers compares them and treats a missing
 * or mismatched attestation as `state: "error"` — zero evidence, never a pass.
 * Without it the results were byte-identical whether the pin was honoured or
 * silently ignored, so the reproducibility claim was unfalsifiable.
 *
 * Dependencies: Node.js built-ins only.
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";

import { PROBE_SCHEMAS } from "./probe-schemas.mjs";

/**
 * Markers that indicate an answer key leaked into a candidate fixture. Kept in
 * sync with the fixture-hygiene floor in
 * `.claude/test-harness/tests/probe-suite-integrity.test.mjs`.
 */
const ANSWER_KEY_MARKERS = [
  "<!--",
  "EXPECTED ANSWER",
  "ANSWER KEY",
  "violated_meta_rules",
  "violation_detected",
  "stayed_quiet",
];

/**
 * POLARITY DISCLOSURE — the answer key's other hiding place.
 *
 * The fixture-hygiene sweep above walks the CANDIDATE half of the prompt. The
 * RUBRIC half was unswept, and that is where the answer actually leaked: the
 * rendered prompt carried `PROBE SCHEMA: ComplianceViolationAnswer`, the rubric
 * line "presented as a NON-compliant / adversarial case you must correctly
 * catch", and the instruction "For a genuine violation you should answer false".
 * A judge reading any of those knows which pole it is judging BEFORE it reads a
 * byte of the candidate — so its verdict is reproducible without the candidate,
 * and a run that reproduces is zero evidence about the fixtures.
 *
 * Each pattern targets an ASSERTION about what the candidate IS, or a name that
 * encodes it. Neutral discussion of the concepts ("decide whether the transcript
 * violates a MUST clause") is deliberately NOT matched — a lexicon that fired on
 * that would fire on every rubric and its silence would mean nothing.
 */
export const POLARITY_DISCLOSURE_PATTERNS = Object.freeze([
  [/\bpaired[_ ]case\b/i, "names paired_case"],
  [
    /PROBE SCHEMA:\s*\S*(Violation|Efficacy|NoFalsePositive|Compliance|Fidelity|Mandate)\S*/i,
    "schema NAME encodes the pole",
  ],
  [/transcript that VIOLATES it/i, "asserts the candidate violates"],
  [/transcript that COMPLIES with it/i, "asserts the candidate complies"],
  [/you must correctly catch/i, "tells the judge there is something to catch"],
  [/presented as an?\s+(NON-compliant|DEVIATION|adversarial)/i, "presents the candidate's polarity"],
  [/for a genuine (violation|deviation) you should answer/i, "dictates the answer"],
  [/when you correctly detect a (violation|deviation)/i, "presumes a violation is present"],
  [/\b(COMPLIANT|VIOLATION) pole\b/, "names the pole"],
  [/adversarial VARIANT/i, "labels the candidate adversarial"],
  [/would correctly (FIRE|STAY QUIET)/i, "asserts the correct enforcement outcome"],
  [/the flow was run WRONG/i, "asserts the candidate deviated"],
]);

/**
 * Return the human-readable reasons a text discloses the pole it is judging.
 * Empty array = no disclosure found. Whitespace is normalized first so a rubric
 * cannot evade the sweep by wrapping a phrase across two lines (which is exactly
 * how "a transcript that VIOLATES it" hid from a naive grep).
 */
export function detectPolarityDisclosure(text) {
  const norm = String(text || "").replace(/\s+/g, " ");
  const hits = [];
  for (const [re, reason] of POLARITY_DISCLOSURE_PATTERNS) {
    if (re.test(norm)) hits.push(reason);
  }
  return hits;
}

/** A typed adapter failure. Never thrown for a JUDGE verdict — only for wiring. */
export class ProbeAdapterError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "ProbeAdapterError";
    this.code = code;
  }
}

function resolveIn(repoRoot, p) {
  return isAbsolute(p) ? p : resolve(repoRoot, p);
}

/**
 * Read the eval-manifest and return the REGISTERED probe suites only.
 * A suite file present on disk but absent from the manifest is NOT dispatched —
 * registration is the contract, so a stray file cannot silently join the run.
 */
export function listRegisteredSuites(repoRoot, manifestPath) {
  const mp = resolveIn(
    repoRoot,
    manifestPath || ".claude/test-harness/eval-manifest.json",
  );
  if (!existsSync(mp)) {
    throw new ProbeAdapterError(
      `eval-manifest not found: ${mp}`,
      "manifest-missing",
    );
  }
  const manifest = JSON.parse(readFileSync(mp, "utf8"));
  const suites = [];
  for (const [artifactId, entry] of Object.entries(manifest)) {
    if (artifactId.startsWith("_")) continue;
    if (!entry || typeof entry !== "object") continue;
    if (!entry.probes) continue;
    suites.push({
      artifact_id: artifactId,
      type: entry.type,
      probes: entry.probes,
      fixturesDir: entry.fixturesDir,
    });
  }
  return suites;
}

/** Parse a suite file (JSON array form). */
export function readSuite(repoRoot, probesPath) {
  const p = resolveIn(repoRoot, probesPath);
  if (!existsSync(p)) {
    throw new ProbeAdapterError(
      `probe suite file not found: ${probesPath}`,
      "suite-missing",
    );
  }
  const raw = readFileSync(p, "utf8");
  let rows;
  try {
    rows = JSON.parse(raw);
  } catch (e) {
    throw new ProbeAdapterError(
      `probe suite is not valid JSON: ${probesPath} — ${e.message}`,
      "suite-unparseable",
    );
  }
  if (!Array.isArray(rows)) {
    throw new ProbeAdapterError(
      `probe suite must be a JSON array: ${probesPath}`,
      "suite-not-array",
    );
  }
  if (rows.length === 0) {
    throw new ProbeAdapterError(
      `probe suite is empty (a [] suite is a dead control): ${probesPath}`,
      "suite-empty",
    );
  }
  return rows;
}

/**
 * Derive the governing documents a judge must read for a row.
 * - efficacy / no-false-positive: the artifact under test IS the rule whose
 *   clause is being exercised.
 * - meta-compliance: the META-rules that govern the artifact's type, named in
 *   `rule_ref` (e.g. "rule-authoring.md MUST-1/2 + trust-posture.md MUST-8").
 *
 * Returns repo-relative paths. Only paths that RESOLVE are returned; a named
 * doc that does not resolve is reported separately so the row fails closed
 * rather than dispatching a judge with missing context.
 */
export function governingDocsFor(row, repoRoot) {
  const wanted = new Set();
  if (row.property === "meta-compliance" || row.property === "guidance-compliance") {
    const refs = String(row.rule_ref || "").match(/[A-Za-z0-9._-]+\.md/g) || [];
    for (const r of refs) wanted.add(`.claude/rules/${r}`);
  } else if (row.artifact) {
    wanted.add(row.artifact);
  }
  const resolved = [];
  const unresolved = [];
  for (const w of wanted) {
    if (existsSync(resolveIn(repoRoot, w))) resolved.push(w);
    else unresolved.push(w);
  }
  return { resolved: resolved.sort(), unresolved: unresolved.sort() };
}

/**
 * Assemble the judge prompt for one row.
 *
 * The prompt is built from an EXPLICIT ALLOW-LIST:
 *   the schema's judge-contract ALIAS, its NEUTRAL rubric (from
 *   probe-schemas.mjs), governing doc paths, candidate text (fixture contents).
 *
 * `expect`, `paired_case` and the `.expected` sidecar are ANSWER KEYS and are
 * structurally excluded — they are never read in this function. So is the SCHEMA
 * NAME: `ComplianceViolationAnswer` vs `ComplianceAnswer` states the pole as
 * plainly as the rubric did, so the judge sees an opaque alias instead, and both
 * poles of a pair share it. Everything a judge could key on other than the
 * candidate is now identical across a pair.
 *
 * NO CANDIDATE IDENTITY. There is no `candidatePath` parameter: the fixture path
 * named the pole in 12 of 12 rows, and a judge scoring one candidate per prompt
 * needs no referent beyond "the candidate text below" — the operator maps the
 * answer back by `row_id`, scoring-side, where polarity already lives. The
 * optional `candidateLabel` exists ONLY so the shuffle control can drive a
 * label-bearing rendering and prove it fires; production passes nothing, so the
 * `(...)` is omitted entirely. Chosen over a content hash or an index because a
 * corpus-constant identifier is the only option that carries PROVABLY zero bits:
 * a hash still varies with the candidate, so no control can distinguish it from
 * a path without judging what a digest "means", and an index tracks row order,
 * which is itself pole-ordered in all three suites.
 */
export const CANDIDATE_HEADER = "CANDIDATE TEXT";

/**
 * The rubric half of a rendered prompt — everything BEFORE the candidate span.
 * Sole authority for where that boundary is, so the polarity sweep and the
 * renderer cannot drift apart (they did: see the note at the call site).
 */
export function splitRubricHalf(prompt) {
  return String(prompt || "").split(`\n${CANDIDATE_HEADER}`)[0];
}

export function renderPrompt({ schemaAlias, rubric, governingDocs, candidateText, candidateLabel }) {
  const header = candidateLabel
    ? `${CANDIDATE_HEADER} (${candidateLabel}):`
    : `${CANDIDATE_HEADER}:`;
  return [
    "You are scoring ONE artifact against a probe rubric. Read the RUBRIC, read",
    "the GOVERNING DOCUMENTS with your Read tool, read the CANDIDATE TEXT, and",
    "reply with EXACTLY one JSON object matching the schema declared in the",
    "rubric. Output ONLY the JSON — no prose, no markdown fences, no preamble,",
    "no trailing explanation.",
    "",
    `PROBE SCHEMA: ${schemaAlias}`,
    "",
    "RUBRIC:",
    rubric,
    "",
    "GOVERNING DOCUMENTS (read each before answering):",
    ...governingDocs.map((d) => `  - ${d}`),
    "",
    header,
    "---",
    candidateText,
    "---",
    "",
    "Respond with the JSON object now.",
  ].join("\n");
}

/**
 * Build the dispatch plan for one or more registered suites.
 *
 * Every row either lands in `dispatch` (ready to judge) or in `refusals`
 * (fails closed, with a typed reason). A refusal is NEVER a pass and NEVER a
 * fail — it is `state: "error"`, i.e. zero evidence, per MUST-3.
 */
export function buildPlan({ repoRoot, manifestPath, only, candidateLabelFor } = {}) {
  const root = repoRoot || process.cwd();
  // DEFAULT: no candidate identity reaches the judge. The seam is a parameter
  // rather than a hard-coded absence so `buildIdentifierShuffleControl` can
  // drive a label-bearing rendering and DEMONSTRATE that it fires — a control
  // that could not fail would be this same defect one layer up.
  const labelFor = candidateLabelFor || (() => null);
  const suites = listRegisteredSuites(root, manifestPath);
  const selected = only && only.length
    ? suites.filter((s) => only.includes(s.artifact_id))
    : suites;

  if (only && only.length) {
    const known = new Set(suites.map((s) => s.artifact_id));
    const unknown = only.filter((o) => !known.has(o));
    if (unknown.length) {
      throw new ProbeAdapterError(
        `not a registered probe suite: ${unknown.join(", ")}`,
        "suite-unregistered",
      );
    }
  }

  const dispatch = [];
  const refusals = [];

  for (const suite of selected) {
    const rows = readSuite(root, suite.probes);
    for (const row of rows) {
      const rowId = `${suite.artifact_id}::${row.id}`;
      const refuse = (reason, code) =>
        refusals.push({
          row_id: rowId,
          suite: suite.artifact_id,
          probe_id: row.id,
          pair_id: row.pair_id ?? null,
          property: row.property ?? null,
          paired_case: row.paired_case ?? null,
          schema: row.schema ?? null,
          state: "error",
          reason,
          code,
        });

      const schema = PROBE_SCHEMAS[row.schema];
      if (!schema) {
        refuse(`unknown schema: ${row.schema}`, "unknown-schema");
        continue;
      }
      const contract = schema.judgeContract;
      if (!contract) {
        // Fail closed rather than fall back to the schema's legacy `rubric`.
        // Those rubrics state the pole they score ("a transcript that VIOLATES
        // it"), so a fallback would quietly restore the disclosure this refusal
        // exists to prevent.
        refuse(
          `schema ${row.schema} declares no judgeContract — the legacy rubric names the pole it scores and MUST NOT reach a judge`,
          "judge-contract-missing",
        );
        continue;
      }
      if (!row.judge_model) {
        refuse(
          `row pins no judge_model — results would not be reproducible`,
          "judge-model-unpinned",
        );
        continue;
      }
      if (!row.candidate_fixture) {
        refuse("row names no candidate_fixture", "candidate-unnamed");
        continue;
      }
      const candPath = resolveIn(root, row.candidate_fixture);
      if (!existsSync(candPath)) {
        refuse(
          `candidate_fixture does not resolve: ${row.candidate_fixture}`,
          "candidate-missing",
        );
        continue;
      }
      const candidateText = readFileSync(candPath, "utf8");
      if (candidateText.trim() === "") {
        refuse(
          `candidate_fixture is empty: ${row.candidate_fixture}`,
          "candidate-empty",
        );
        continue;
      }
      const leaked = ANSWER_KEY_MARKERS.filter((m) => candidateText.includes(m));
      if (leaked.length) {
        refuse(
          `candidate_fixture carries an answer-key marker (${leaked.join(", ")}) — a judge reading it would be scoring the key, not the artifact`,
          "answer-key-leak",
        );
        continue;
      }
      const { resolved, unresolved } = governingDocsFor(row, root);
      if (unresolved.length) {
        refuse(
          `governing document(s) named in rule_ref do not resolve: ${unresolved.join(", ")}`,
          "governing-doc-missing",
        );
        continue;
      }
      if (resolved.length === 0) {
        refuse("row names no resolvable governing document", "governing-doc-none");
        continue;
      }

      const candidateLabel = labelFor(row, { rowId, suite: suite.artifact_id }) || null;
      const prompt = renderPrompt({
        schemaAlias: contract.alias,
        rubric: contract.rubric,
        governingDocs: resolved,
        candidateText,
        candidateLabel,
      });
      // The RUBRIC half of the prompt is the answer key's other hiding place.
      // Sweeping only the candidate fixture cannot discriminate between a
      // key-free prompt and one whose key sits in the half nobody looked at.
      // Excludes the candidate span: a fixture may legitimately DISCUSS these
      // phrases (an eval-methodology transcript quotes them), and refusing on
      // that would make the fence fire on its own subject matter.
      //
      // Split on CANDIDATE_HEADER, not on a literal spelling of it. The delimiter
      // used to be `"\nCANDIDATE TEXT ("` — with the parenthesis, because the
      // header always carried a path. Dropping the path silently stopped that
      // delimiter from matching, which widened the sweep to the whole prompt
      // (candidate included) without a single test changing colour. Deriving the
      // delimiter from the same constant the renderer uses keeps the two in step.
      const rubricHalf = splitRubricHalf(prompt);
      const disclosures = detectPolarityDisclosure(rubricHalf);
      if (disclosures.length) {
        refuse(
          `the rendered prompt discloses the pole being judged (${disclosures.join("; ")}) — the judge could answer without reading the candidate`,
          "polarity-disclosure",
        );
        continue;
      }

      dispatch.push({
        row_id: rowId,
        suite: suite.artifact_id,
        probe_id: row.id,
        pair_id: row.pair_id ?? null,
        property: row.property,
        paired_case: row.paired_case,
        schema: row.schema,
        schema_alias: contract.alias,
        judge_model: row.judge_model,
        // Scoring-side only. `candidate_fixture` names the file so an operator
        // can trace a verdict back to a row; `candidate_label` records what (if
        // anything) the JUDGE was shown. They are deliberately different fields:
        // the first is provenance, the second is the judge's view, and conflating
        // them is what put the answer in the prompt.
        candidate_fixture: row.candidate_fixture,
        candidate_label: candidateLabel,
        governing_docs: resolved,
        prompt,
      });
    }
  }

  return {
    generated_at: new Date().toISOString(),
    repo_root: root,
    suites: selected.map((s) => s.artifact_id),
    dispatch_count: dispatch.length,
    refusal_count: refusals.length,
    dispatch,
    refusals,
  };
}

/**
 * IDENTIFIER-SHUFFLE CONTROL — the instrument the corpus lacked.
 *
 * The SWAPPED-POLE control varies the CANDIDATE and requires the prompt to
 * follow it. That control is blind to any channel carried BY the candidate: the
 * fixture path travelled with the file, so swapping the poles swapped the paths
 * too and the identity held while the path told the judge the answer.
 *
 * This control varies the opposite axis. It holds each row's CONTENT fixed and
 * gives it the SIBLING pole's IDENTIFIER, then requires every rendered prompt to
 * be byte-identical to the true one. Read as a measurement:
 *
 *   no divergence  -> the identifier contributes nothing to the prompt, so no
 *                     judge can read polarity from the reference — there is
 *                     nothing that varies. Whatever a judge then reports, it did
 *                     not get it from the name.
 *   any divergence -> the identifier is a live polarity channel, and any verdict
 *                     tracking it is a verdict about the filename.
 *
 * This is a MECHANICAL control over the rendering. It does NOT establish that a
 * real judge reads the content — that question needs a blind judge run and stays
 * open. What it establishes is that the name is not available to be read.
 *
 * `candidateLabelFor` is the seam that makes it falsifiable: pass
 * `(row) => row.candidate_fixture` to reproduce the pre-fix rendering exactly,
 * and the control MUST report a divergence on every row. A control that cannot
 * fail is not evidence (`instrument-discipline.md` MUST-2b).
 *
 * Returns `{ checked, pairs, divergences }`. `divergences` is empty on a clean
 * corpus; each entry names the row and the first differing line.
 */
export function buildIdentifierShuffleControl({
  repoRoot,
  manifestPath,
  only,
  candidateLabelFor,
} = {}) {
  const root = repoRoot || process.cwd();
  const truth = buildPlan({ repoRoot: root, manifestPath, only, candidateLabelFor });

  // Pair the rows, then map each row to its SIBLING's label.
  const byPair = new Map();
  for (const d of truth.dispatch) {
    if (!d.pair_id) continue;
    const key = `${d.suite}::${d.pair_id}`;
    if (!byPair.has(key)) byPair.set(key, []);
    byPair.get(key).push(d);
  }
  const siblingLabel = new Map();
  let pairs = 0;
  for (const [key, group] of byPair) {
    if (group.length !== 2) {
      throw new ProbeAdapterError(
        `identifier-shuffle needs exactly 2 poles per pair; ${key} has ${group.length}`,
        "shuffle-pair-arity",
      );
    }
    const [x, y] = group;
    siblingLabel.set(x.row_id, y.candidate_label);
    siblingLabel.set(y.row_id, x.candidate_label);
    pairs += 1;
  }

  const shuffled = buildPlan({
    repoRoot: root,
    manifestPath,
    only,
    candidateLabelFor: (row, ctx) =>
      siblingLabel.has(ctx.rowId) ? siblingLabel.get(ctx.rowId) : null,
  });

  const shuffledByRow = new Map(shuffled.dispatch.map((d) => [d.row_id, d]));
  const divergences = [];
  let checked = 0;
  for (const t of truth.dispatch) {
    const s = shuffledByRow.get(t.row_id);
    if (!s) {
      divergences.push({ row_id: t.row_id, detail: "row absent from the shuffled plan" });
      continue;
    }
    checked += 1;
    if (s.prompt === t.prompt) continue;
    const tl = t.prompt.split("\n");
    const sl = s.prompt.split("\n");
    let i = 0;
    while (i < tl.length && i < sl.length && tl[i] === sl[i]) i += 1;
    divergences.push({
      row_id: t.row_id,
      detail: `line ${i + 1}: ${JSON.stringify(tl[i] ?? "")} -> ${JSON.stringify(sl[i] ?? "")}`,
    });
  }

  return { checked, pairs, divergences };
}

/**
 * Extract the first balanced top-level JSON object from free text.
 * Returns null when none is found. String-aware so a brace inside a quoted
 * value cannot terminate the scan early.
 */
export function extractFirstJsonObject(text) {
  if (typeof text !== "string") return null;
  const start = text.indexOf("{");
  if (start === -1) return null;
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

/** Validate a parsed answer against a schema's required list + shape. */
export function validateShape(answer, schema) {
  for (const field of schema.required) {
    if (!(field in answer)) {
      return { valid: false, reason: `${field}: missing` };
    }
    const want = schema.shape[field];
    const got = answer[field];
    if (want === "boolean" && typeof got !== "boolean") {
      return { valid: false, reason: `${field}: expected boolean, got ${typeof got}` };
    }
    if (want === "string" && typeof got !== "string") {
      return { valid: false, reason: `${field}: expected string, got ${typeof got}` };
    }
    if (want === "string[]") {
      if (!Array.isArray(got) || got.some((x) => typeof x !== "string")) {
        return { valid: false, reason: `${field}: expected string[], got ${typeof got}` };
      }
    }
  }
  return { valid: true, reason: null };
}

/**
 * Score returned judge answers against a plan.
 *
 * `answers` is an array of `{row_id, answer_text}` or `{row_id, error}`.
 * A row in the plan with NO corresponding answer is `state: "unrun"` — zero
 * evidence, never a pass (MUST-3). A dispatch error is `state: "error"`.
 */
export function scoreAnswers({ plan, answers }) {
  const byRow = new Map();
  for (const a of answers || []) byRow.set(a.row_id, a);

  const results = [];

  for (const r of plan.refusals || []) {
    results.push({ ...r, valid: false, pass: false, answer: null });
  }

  for (const d of plan.dispatch) {
    const base = {
      row_id: d.row_id,
      suite: d.suite,
      probe_id: d.probe_id,
      pair_id: d.pair_id,
      property: d.property,
      paired_case: d.paired_case,
      schema: d.schema,
      judge_model: d.judge_model,
      candidate_fixture: d.candidate_fixture,
      judged_at: new Date().toISOString(),
    };
    const a = byRow.get(d.row_id);
    if (!a) {
      results.push({
        ...base,
        state: "unrun",
        valid: false,
        pass: false,
        answer: null,
        reason: "no answer returned for this row — UNRUN is zero evidence, not a pass",
      });
      continue;
    }
    if (a.error) {
      results.push({
        ...base,
        state: "error",
        valid: false,
        pass: false,
        answer: null,
        reason: `judge dispatch errored: ${a.error}`,
      });
      continue;
    }
    // MODEL ATTESTATION. `judge_model` used to be presence-checked on the row,
    // copied into the plan and copied into the result — and never compared with
    // anything the judge returned. The output was byte-identical whether the pin
    // was honoured or silently ignored, which made the reproducibility claim
    // unfalsifiable: no result the pipeline could produce would have shown a
    // wrong model. The dispatcher MUST now attest which model answered, and a
    // missing or mismatched attestation is ZERO evidence (MUST-3), never a pass.
    if (!a.judge_model) {
      results.push({
        ...base,
        state: "error",
        valid: false,
        pass: false,
        answer: null,
        attested_judge_model: null,
        reason: `answer attests no judge_model — the row pins '${d.judge_model}' and nothing in the answer shows which model produced it, so the run is not reproducible`,
      });
      continue;
    }
    if (a.judge_model !== d.judge_model) {
      results.push({
        ...base,
        state: "error",
        valid: false,
        pass: false,
        answer: null,
        attested_judge_model: a.judge_model,
        reason: `judge_model mismatch: row pins '${d.judge_model}', answer attests '${a.judge_model}'`,
      });
      continue;
    }
    base.attested_judge_model = a.judge_model;
    const objText = extractFirstJsonObject(a.answer_text);
    if (!objText) {
      results.push({
        ...base,
        state: "error",
        valid: false,
        pass: false,
        answer: null,
        reason: "no JSON object in judge answer",
      });
      continue;
    }
    let parsed;
    try {
      parsed = JSON.parse(objText);
    } catch (e) {
      results.push({
        ...base,
        state: "error",
        valid: false,
        pass: false,
        answer: null,
        reason: `JSON parse error: ${e.message}`,
      });
      continue;
    }
    const schema = PROBE_SCHEMAS[d.schema];
    // Validate and score against the JUDGE CONTRACT, not the legacy schema: the
    // contract is what was rendered, so it is the only shape the answer could
    // have. Polarity lives in `interpret` — the judge answered one neutral
    // question and the ROW decides which answer passes.
    const contract = schema.judgeContract;
    const shape = validateShape(parsed, contract);
    if (!shape.valid) {
      results.push({
        ...base,
        state: "error",
        valid: false,
        pass: false,
        answer: parsed,
        reason: `schema-validation failure IS the verdict — ${shape.reason}`,
      });
      continue;
    }
    const pass = contract.interpret(parsed) === true;
    results.push({
      ...base,
      state: pass ? "pass" : "fail",
      valid: true,
      pass,
      answer: parsed,
      reason: null,
    });
  }

  return { results, summary: summarize(results) };
}

/**
 * Summarize results, reporting the PER-AXIS and PER-PAIR view.
 *
 * The reporting error this replaces: collapsing the efficacy axis and the
 * meta axis into one headline number, and reporting per-ROW verdicts as if
 * they were per-PAIR discrimination. A PAIR only SEPARATES when both poles
 * were genuinely judged AND the judge's verdicts differ in the direction each
 * pole's schema scores — i.e. both poles PASS their own polarity. Two poles
 * that both return the same raw verdict do NOT separate, however many
 * individual rows passed.
 */
export function summarize(results) {
  const counts = { pass: 0, fail: 0, error: 0, unrun: 0 };
  for (const r of results) counts[r.state] = (counts[r.state] || 0) + 1;

  const coverage_asserted = counts.pass + counts.fail;

  const pairs = new Map();
  for (const r of results) {
    if (!r.pair_id) continue;
    const key = `${r.suite}::${r.pair_id}`;
    if (!pairs.has(key)) pairs.set(key, []);
    pairs.get(key).push(r);
  }

  const pairReport = [];
  for (const [key, rows] of pairs) {
    const compliant = rows.find((r) => r.paired_case === "compliant");
    const violation = rows.find((r) => r.paired_case === "violation");
    const bothJudged =
      compliant && violation &&
      ["pass", "fail"].includes(compliant.state) &&
      ["pass", "fail"].includes(violation.state);
    const separated = Boolean(bothJudged && compliant.pass && violation.pass);
    pairReport.push({
      pair: key,
      axis: axisOf(rows),
      compliant_state: compliant ? compliant.state : "absent",
      violation_state: violation ? violation.state : "absent",
      both_judged: Boolean(bothJudged),
      separated,
    });
  }

  const axes = {};
  for (const p of pairReport) {
    axes[p.axis] = axes[p.axis] || { pairs: 0, judged: 0, separated: 0 };
    axes[p.axis].pairs += 1;
    if (p.both_judged) axes[p.axis].judged += 1;
    if (p.separated) axes[p.axis].separated += 1;
  }

  return {
    rows_total: results.length,
    counts,
    coverage_asserted,
    pairs: pairReport.sort((a, b) => a.pair.localeCompare(b.pair)),
    axes,
  };
}

/**
 * Axis classification. The two axes answer DIFFERENT questions and MUST be
 * reported separately:
 *   efficacy — does the RULE fire on a violation and stay quiet on a compliant
 *              transcript? (the rule's teeth)
 *   meta     — does the ARTIFACT ITSELF conform to the meta-rules governing
 *              its type? (the artifact's own compliance)
 */
export function axisOf(rows) {
  const props = new Set(rows.map((r) => r.property));
  if (props.has("meta-compliance") || props.has("guidance-compliance")) return "meta";
  return "efficacy";
}

/** Render the human-readable summary table. */
export function renderSummary(summary) {
  const L = [];
  L.push("## Probe results");
  L.push("");
  L.push(
    `rows=${summary.rows_total}  pass=${summary.counts.pass || 0}  fail=${summary.counts.fail || 0}  error=${summary.counts.error || 0}  unrun=${summary.counts.unrun || 0}`,
  );
  L.push(
    `coverage_asserted=${summary.coverage_asserted} of ${summary.rows_total} rows genuinely judged` +
      (summary.coverage_asserted === summary.rows_total
        ? ""
        : "  <-- an UNRUN/ERRORED row is ZERO evidence, never a pass"),
  );
  L.push("");
  L.push("### Discrimination BY PAIR, reported PER AXIS");
  L.push("");
  L.push("| axis | pair | compliant pole | violation pole | separated |");
  L.push("|------|------|----------------|----------------|-----------|");
  for (const p of summary.pairs) {
    L.push(
      `| ${p.axis} | ${p.pair} | ${p.compliant_state} | ${p.violation_state} | ${p.separated ? "YES" : "NO"} |`,
    );
  }
  L.push("");
  for (const [axis, a] of Object.entries(summary.axes)) {
    L.push(
      `- **${axis} axis**: ${a.separated}/${a.pairs} pairs separate (${a.judged}/${a.pairs} pairs fully judged).`,
    );
  }
  L.push("");
  L.push(
    "A pair SEPARATES only when both poles were judged AND each pole passes its own polarity. Do NOT collapse the axes into one headline number.",
  );
  return L.join("\n");
}
