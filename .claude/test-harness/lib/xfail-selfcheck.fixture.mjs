/**
 * Self-check fixture for `.claude/bin/run-harness-suites.mjs`.
 *
 * NOT a test suite. It is the POSITIVE + NEGATIVE CONTROL the strict-xfail gate
 * runs against ITSELF before it reports on anything else, per
 * instrument-discipline.md MUST-1: a checker that cannot produce a different
 * result when the proposition is false is not evidence.
 *
 * The runner asserts it observes EXACTLY this shape:
 *   - "selfcheck group > selfcheck PASSES by design"  -> a leaf PASS
 *   - "selfcheck group > selfcheck FAILS by design"   -> a leaf FAIL
 *   - "selfcheck group"                               -> a roll-up, FILTERED OUT
 *   - exactly 1 leaf failure in total
 * Anything else means the parse is broken (node stopped emitting `test:start`,
 * the `subtestsFailed` discriminator changed, ancestor paths no longer
 * reconstruct) and the runner exits 1 rather than printing a green it cannot
 * substantiate.
 *
 * DELIBERATELY FAILING. This file is expected to exit non-zero when executed on
 * its own - that is the whole point, and it is why it lives in lib/ and is named
 * `.fixture.mjs` rather than `.test.mjs`: the harness registry globs
 * `tests/*.test.mjs`, so this file is never collected as a suite and its
 * designed red can never be mistaken for a corpus failure.
 *
 * The two test bodies must stay trivial and dependency-free. The control is only
 * meaningful if its own outcome is beyond doubt - anything that could fail for an
 * incidental reason (fs, git, env, timing) would turn a broken-instrument signal
 * into a flake.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";

describe("selfcheck group", () => {
  it("selfcheck PASSES by design", () => {
    assert.equal(1, 1);
  });

  it("selfcheck FAILS by design", () => {
    assert.equal(
      "instrument-is-broken",
      "this assertion fails on purpose",
      "If this ever PASSES, the runner's failure detection is broken.",
    );
  });
});
