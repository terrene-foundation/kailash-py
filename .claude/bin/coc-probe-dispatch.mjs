#!/usr/bin/env node
/**
 * coc-probe-dispatch — CLI front-end for the artifact-eval probe adapter (loom#1465).
 *
 * The SEMANTIC tier (Contract C3) had no mechanical dispatch path: the probe
 * suites registered in `.claude/test-harness/eval-manifest.json` use a row shape
 * `/test-harness-probe` could not read, so reproducing the tier meant doing it by
 * hand. This bin is the mechanical path.
 *
 * Usage:
 *   coc-probe-dispatch.mjs plan  [--suite <artifact_id>]... [--out <plan.json>]
 *   coc-probe-dispatch.mjs score --plan <plan.json> --answers <answers.json>
 *                                [--out <results.json>]
 *
 * `plan` emits a dispatch plan — one fully-rendered judge prompt per probe row.
 * The CC orchestrator dispatches each prompt to a subagent IN PARALLEL and
 * collects the raw answer text. Node cannot dispatch CC subagents from a child
 * process, which is why this is a two-phase contract rather than one command
 * (the same split `.claude/skills/test-harness-probe/SKILL.md` documents).
 *
 * `score` validates each answer against its schema shape, applies the schema's
 * scoringRule, and reports discrimination BY PAIR and PER AXIS.
 *
 * EXIT CODES — deliberately NOT a pass/fail proxy for the semantic tier:
 *   0  the command completed
 *   1  a row was UNRUN or ERRORED, or a pair failed to separate
 *   2  a wiring failure (bad args, unregistered suite, unparseable input)
 *
 * Per `coc-artifact-eval-coverage.md` MUST-3 a caller MUST cite
 * `coverage_asserted` from the summary, never this exit code alone: exit 0 over
 * a zero-row plan would verify nothing.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  ProbeAdapterError,
  buildPlan,
  renderSummary,
  scoreAnswers,
} from "../test-harness/lib/artifact-probe-adapter.mjs";

function repoRoot() {
  return process.env.COC_REPO_ROOT
    ? resolve(process.env.COC_REPO_ROOT)
    : process.cwd();
}

function parseArgs(argv) {
  const out = { _: [], suite: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--suite") out.suite.push(argv[++i]);
    else if (a === "--out") out.out = argv[++i];
    else if (a === "--plan") out.plan = argv[++i];
    else if (a === "--answers") out.answers = argv[++i];
    else if (a === "--json") out.json = true;
    else if (a.startsWith("--")) {
      // An UNRECOGNISED flag is a HARD error, never silently ignored: a scanner
      // that ignores an unknown flag reports a confident verdict about the wrong
      // input. Fail closed instead.
      console.error(`coc-probe-dispatch: unrecognised flag: ${a}`);
      process.exit(2);
    } else out._.push(a);
  }
  return out;
}

function usage() {
  console.error(
    [
      "usage:",
      "  coc-probe-dispatch.mjs plan  [--suite <artifact_id>]... [--out <plan.json>]",
      "  coc-probe-dispatch.mjs score --plan <plan.json> --answers <answers.json> [--out <results.json>]",
    ].join("\n"),
  );
}

function readJsonOrDie(p, label) {
  const abs = resolve(p);
  if (!existsSync(abs)) {
    console.error(`coc-probe-dispatch: ${label} not found: ${abs}`);
    process.exit(2);
  }
  try {
    return JSON.parse(readFileSync(abs, "utf8"));
  } catch (e) {
    console.error(`coc-probe-dispatch: ${label} is not valid JSON: ${e.message}`);
    process.exit(2);
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const cmd = args._[0];

  if (cmd === "plan") {
    let plan;
    try {
      plan = buildPlan({ repoRoot: repoRoot(), only: args.suite });
    } catch (e) {
      if (e instanceof ProbeAdapterError) {
        console.error(`coc-probe-dispatch: ${e.code}: ${e.message}`);
        process.exit(2);
      }
      throw e;
    }
    const text = JSON.stringify(plan, null, 2);
    if (args.out) {
      writeFileSync(resolve(args.out), `${text}\n`);
      console.error(
        `plan: ${plan.dispatch_count} row(s) to dispatch, ${plan.refusal_count} refused -> ${args.out}`,
      );
      for (const r of plan.refusals) {
        console.error(`  REFUSED ${r.row_id}: ${r.code}: ${r.reason}`);
      }
    } else {
      process.stdout.write(`${text}\n`);
    }
    process.exit(plan.refusal_count > 0 ? 1 : 0);
  }

  if (cmd === "score") {
    if (!args.plan || !args.answers) {
      usage();
      process.exit(2);
    }
    const plan = readJsonOrDie(args.plan, "plan");
    const answers = readJsonOrDie(args.answers, "answers");
    if (!Array.isArray(answers)) {
      console.error("coc-probe-dispatch: answers must be a JSON array of {row_id, answer_text|error}");
      process.exit(2);
    }
    const { results, summary } = scoreAnswers({ plan, answers });
    if (args.out) {
      writeFileSync(
        resolve(args.out),
        `${JSON.stringify({ summary, results }, null, 2)}\n`,
      );
    }
    if (args.json) {
      process.stdout.write(`${JSON.stringify({ summary, results }, null, 2)}\n`);
    } else {
      process.stdout.write(`${renderSummary(summary)}\n`);
    }
    const unclean =
      (summary.counts.unrun || 0) > 0 ||
      (summary.counts.error || 0) > 0 ||
      summary.pairs.some((p) => !p.separated);
    process.exit(unclean ? 1 : 0);
  }

  usage();
  process.exit(2);
}

main();
