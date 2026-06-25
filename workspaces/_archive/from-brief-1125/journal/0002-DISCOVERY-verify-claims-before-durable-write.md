# DISCOVERY — verify code-claims against ground truth before durable write

**Date:** 2026-05-27
**Phase:** /codify (post-release)
**Inherit-by:** every future session that writes code-claims into CHANGELOG /
commit / PR / docs / rules — especially after a `/clear` / compaction boundary.

## The pattern

A claim about code (public API names, signatures, set/list counts, class names,
allowlist/denylist contents) written into a DURABLE artifact MUST be verified
against ground truth — import the symbol, read the source/wheel, print the FULL
collection — BEFORE the write. Two sources of false claims to distrust:

1. **Context-boundary reconstruction.** After `/clear` / auto-compaction /
   resume, claims carried forward (compaction summary, `.session-notes`,
   prior-session framing) are unfalsifiable until re-verified. Same epistemic
   shape as `zero-tolerance.md` Rule 1c.
2. **Truncated command output.** `tail -N` / `head -N` / `... | head` over the
   line carrying the value you're about to cite silently drops the very datum
   you need.

## Evidence (this session — both caught before consumer impact)

1. The 2.27.0 CHANGELOG Added section fabricated 5 `kailash.workflow` function
   names (`from_brief` / `afrom_brief` / `from_brief_validate` /
   `from_brief_analyze` / `from_brief_realize`) carried verbatim from a
   compaction-summary "5 entrypoints" framing. 4 of the 5 do not exist; the real
   surface is `Workflow.from_brief` + `kailash.bootstrap` + `workflow_from_brief`.
   The "5 surfaces" of #1125 are 5 distinct FRAMEWORKS, not 5 functions. Caught
   by the TestPyPI clean-venv import (`ImportError: afrom_brief`). Fixed PR #1187.
2. The correction then said the `_DANGEROUS_NODE_TYPES` floor is "8 types" (and
   that AsyncPythonCodeNode is NOT in it) because `tail -8` dropped the count
   line + 4 leading alphabetical entries. Real floor is 12; AsyncPythonCodeNode
   IS in it. Caught at post-publish verify. Fixed PR #1188.

Both cost an extra correction PR; the over-claim → fix → re-fix chain is now
permanent in `git log`. The wheel/code was correct both times — only the prose
about it was wrong.

## Structural backstops that caught it

- **TestPyPI rehearsal + clean-venv import-shape check** caught defect 1 before
  the immutable production publish. This is why the rehearsal gate exists — it
  is the structural last line, NOT the first line.
- **Post-publish production verify** caught defect 2.

Both backstops fired AFTER the bad write. The fix is to verify BEFORE the write
(this DISCOVERY's pattern), so the rehearsal/verify confirm rather than rescue.

## Codified as

- Proposal candidate `verify-claims-before-durable-write` (BUILD→loom, git.md
  extension or new baseline rule).
- Auto-memory `feedback_verify_claims_before_durable_write.md`.
