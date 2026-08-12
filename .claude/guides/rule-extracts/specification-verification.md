# specification-verification — depth extract

Depth companion to `.claude/rules/specification-verification.md`. The rule body carries the
load-bearing MUST clauses; this file carries the worked cases, the full BLOCKED-rationalization
corpora, and the originating evidence chain.

## The shape of the failure

Every gate in the pipeline validates against the specification:

- the implementer writes the fix to the AC,
- the test author writes the test to the AC,
- the reviewer checks the diff against the AC,
- the issue closes because the AC is satisfied.

None of them measures whether the AC was true. So when the specification is wrong, the wrongness is
**invisible to every gate simultaneously** — not because any gate was skipped, but because they all
share one unverified premise. This is why the class survives an otherwise-disciplined session, and
why the defense has to sit BEFORE implementation rather than at review.

It is the same structural defect as a non-discriminating instrument
(`instrument-discipline.md`): the check's output is identical whether the proposition is true or
false. Here the "instrument" is the AC itself.

## Worked case — MUST-2, the sharpest instance (kailash-py #2004)

The issue named a real defect: a health-check logged and returned an untrusted spawn command
containing a credential. Its AC#1 prescribed the remedy — route the value through the package's
scrubbing helper, `mask_error_text`.

Tested against the issue's own threat example:

```
RAW str(e):      spawn command 'npx -y @vendor/server --token=sk-live-ABCDEF123456' is not in the allowlist...
mask_error_text: spawn command 'npx -y @vendor/server --token=sk-live-ABCDEF123456' is not in the allowlist...
TOKEN STILL PRESENT AFTER MASK?: True
```

`mask_error_text` masks URL userinfo (`scheme://user:pass@host`) and URL query parameters
(`?token=`). A CLI flag `--token=` matches neither. Two sibling scrubbers were also tested and also
leave the token intact — **no scrubber in the monorepo redacted CLI-flag-form credentials.**

So implementing AC#1 exactly produces:

- a diff that matches the acceptance criterion,
- a test written to the acceptance criterion that passes,
- a closed issue,
- and the original credential still in the log.

The correct fix was at a location the AC never mentions — the raise site
(`SpawnSecurityError.__init__`), storing a safe reference instead of the raw command — which
additionally covers two other callers and a JSON-RPC wire surface (`MCPError.to_dict()` puts
`data` on the wire) that the issue did not know about.

**Following the specification exactly is what produces the vulnerability.** That is the case
MUST-2 exists for.

## Full BLOCKED corpora

### MUST-1 — un-re-derived factual claims

- "the issue says N"
- "it was measured when filed"
- "the reporter works on this code / knows it better than me"
- "re-measuring duplicates the triage that already happened"
- "the AC is the contract, not a claim"
- "a prior session already verified this"
- "the numbers are approximate anyway"
- "the line numbers are close enough to find it"

### MUST-2 — prescribed remedy adopted untested

- "the AC specifies the fix, my job is to implement it"
- "the reporter chose that helper deliberately"
- "the test passes"
- "a follow-up can harden it"
- "it's strictly better than nothing"
- "the helper is the project's standard for this"
- "if the helper is wrong, that's a separate issue"

### MUST-3 — inherited enumeration instrument

- "the issue's grep is the definition of the class"
- "I got the same number, so it's confirmed"
- "a second instrument is redundant"
- "the scanner already enumerated it"

### MUST-4 — measured contradiction left unposted

- "the code is what matters, not the issue text"
- "I'll note it in the PR description"
- "the issue closes anyway"
- "correcting the issue is bookkeeping, not work"
- "the next session will re-derive it too"

## The originating set (2026-08-10, kailash-py burn-down)

Wrong-specification instances, each of which a faithful implementation would have closed wrongly:

| #     | What the spec said                             | What measurement showed                                                                                                                                              |
| ----- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #2004 | route through `mask_error_text`                | that helper leaves the credential fully intact; correct fix is at the raise site, plus an unmentioned wire surface                                                   |
| #2006 | the `else` branch sends the explicit NULL      | its own repro model takes the `elif "default"` branch; patching `else` does not fix the reported case                                                                |
| #2015 | "auth path worst"; 24 sites filed              | 1 auth site vs 10 unauthenticated routes leaking DSNs; 24 production `.py` sites confirmed, plus a 25th (f-string spelling) the issue's grep structurally cannot see |
| #1997 | per-key probabilistic gap for one vendor       | coverage is PRESET-dependent; all four vendors leak unconditionally on the conservative preset, where nothing tested                                                 |
| #2022 | `BaseAgentConfig` built without `llm_provider` | that path already falls back to env detection; the user-facing defect is a swallow reporting a `ConfigurationError` as "the LLM emitted a malformed plan"            |

Stale-claim instances from the same session (MUST-1 class):

- **#2013** cited `core.py:4782` — that line is `"health_monitoring": True`, a status-dict key, not
  a method at all; `enable_auth` is at `4814` and `enable_monitoring` at `4825`. Note this rule's
  own first draft "corrected" 4782 to 4813/4826 — both wrong. Two independently-derived wrong
  numbers for one location is the MUST-1 case at its sharpest.
- **#2023** titled "five workflow steps"; there are eight, across three files.
- **#2002** claimed 1,564 of 1,566 uncovered; re-measured 1,698 of 1,715 on the current branch.

## Scanner findings are specifications too

A static-analysis finding is a specification with the same defect profile: it reports what its
queries model, not what is risky. In the same session, CodeQL flagged a generic pass-through
`logger.error` at `base_agent.py:744` (a genuine false positive) and did **not** flag lines 728 and
735 two functions above, which render whole agent input and result dicts at INFO by default — the
actual leak, filed separately.

A triage that works the scanner queue therefore closes the flagged line, records the file reviewed,
and leaves the real defect standing. Treat a finding's severity, mechanism, and location as claims
to re-derive, exactly like an issue's.

Corollary already codified elsewhere: `evidence-first-claims.md` MUST-3 (an errored detector is not
an all-clear) is the same principle for the case where the instrument did not run at all.
