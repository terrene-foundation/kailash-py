# Codify Candidates — kailash-ml 1.5.x Followup

Five learnings surfaced during `/analyze`. Each is recorded here so `/codify` (after `/redteam` confirmation) has the trail. Final classification (global vs variant) and rule-file placement happens at `/codify`.

## 1. API deprecation cycle discipline (origin: #700)

**Pattern.** kailash-ml 1.5.x dropped public API surface (`InferenceServer(registry=, cache_size=)`, `warm_cache`, `load_model(name, model)`) without a deprecation cycle, shim, or CHANGELOG migration entry. Every 1.1.x callsite hard-broke on first import in 1.5.0 (released 2026-04-27, hit production 2026-04-28).

**Rule candidate.** Public-API removal MUST land with a `DeprecationWarning` shim covering at least one minor cycle, plus a CHANGELOG migration section explicitly documenting the 1.x → next-1.x callsite change. Removal-without-shim is BLOCKED.

**Cross-SDK applicability.** GLOBAL. The same gap exists structurally in Rust SDK: `pub fn` removal without `#[deprecated(since = "X.Y.Z", note = "...")]` produces the same hard-break class. `01-analysis/cross-sdk-rs-audit.md` flagged the gap forward-looking; codifying the rule covers both SDKs.

**Likely placement.** New `rules/api-deprecation.md` OR extension to `rules/zero-tolerance.md` Rule 6 ("Implement Fully") with a sibling clause "Remove Fully" — public-API removal must include shim + migration doc + CHANGELOG entry.

**Cross-references.** `rules/cross-cli-parity.md` (variant overlay), `rules/cross-sdk-inspection.md` MUST Rule 1.

## 2. Inline DDL outside migrations (origin: #699)

**Pattern.** `ModelRegistry._create_registry_tables()` shipped `CREATE TABLE IF NOT EXISTS _kml_model_versions ...` in application code. Migration 0002 already owns the canonical schema for the same table. The inline DDL drifted from the migration's column-set; users hit the schema mismatch via the IF-NOT-EXISTS no-op.

**Rule candidate.** `rules/schema-migration.md` Rule 1 ALREADY says DDL outside migrations is BLOCKED — the rule was violated. The codify question is whether to ADD a structural detection mechanism (e.g., `/redteam` grep for `CREATE TABLE` outside `migrations/` directories), not whether the rule is missing.

**Cross-SDK applicability.** GLOBAL. The same audit grep applies to Rust SDK (CREATE TABLE strings outside migration .rs files = same Rule 1 violation).

**Likely placement.** Audit protocol extension to `rules/schema-migration.md` § Audit / Detection — explicit grep command for `/redteam`. OR extension to `skills/16-validation-patterns/` with a new spec-compliance check.

**Cross-references.** `rules/dataflow-identifier-safety.md` Rule 1 (every dynamic DDL through `quote_identifier`), `rules/orphan-detection.md` (the inline DDL was effectively orphan'd from the migration).

## 3. Brief-claim verification protocol (origin: meta-finding)

**Pattern.** This workspace's brief at `briefs/01-context.md` had THREE distinct factual inaccuracies surfaced during analysis:

1. ExperimentTracker creates `_kml_model_versions` (FALSE — migration 0002 does)
2. InferenceServer at `engines/inference_server.py` (FALSE — it's at `serving/server.py:254` after W6-004 deletion)
3. 1.1.x kwargs silently dropped (FALSE — they raise TypeError; only `data=` is silent-drop)

Each was caught only because three parallel deep-dive agents were tasked to verify the brief independently. A single-agent or sequential-agent approach would have inherited the brief's framing.

**Rule candidate.** `/analyze` MUST run a brief-verification sweep — every factual claim in the brief tagged with file:line citations is independently re-grep'd / re-read by the analysis. Inaccuracies recorded in journal AND in the architecture plan's "Brief corrections" section AS the gate before `/todos`. Single-agent analysis is BLOCKED for workstreams with ≥3 issues — parallel verification is structural defense.

**Cross-SDK applicability.** GLOBAL. Briefs are language-agnostic; the verification protocol applies to every COC workstream.

**Likely placement.** Extension to `skills/analyze` skill OR a new `rules/brief-verification.md` rule. Companion update to `rules/agents.md` § Parallel Execution mandating parallel deep-dive when issue count ≥ 3.

**Cross-references.** `rules/specs-authority.md` §3 ("specs are detailed, not summaries" — same intent at the brief level), `rules/agents.md` MUST § Mechanical AST/Grep Sweep.

## 4. Silent-drop kwargs as `rules/zero-tolerance.md` Rule 3 instance (origin: #701)

**Pattern.** `diagnose(model, kind="dl", data=loader)` — `data=` is in the public signature, documented in spec §3.1, and silently ignored on the `kind="dl"` branch. The user's loader has nowhere to go; the diagnostic returns a bare `DLDiagnostics` that has no method consuming it. The kwarg's existence is a lie.

**Rule candidate.** `rules/zero-tolerance.md` Rule 3 (No Silent Fallbacks) is ALREADY the home for this pattern. The codify question is whether to add an explicit clause naming "documented kwarg with zero effect" as a Rule 3 instance, alongside `except: pass` and `except Exception: return None`.

**Cross-SDK applicability.** GLOBAL. Rust's type system structurally prevents the pattern (a function that takes `data: DataLoader` and doesn't use it produces an unused-variable warning), but the rule applies to every SDK with kwargs.

**Likely placement.** Extension to `rules/zero-tolerance.md` Rule 3 with a sub-clause "3c: Kwargs accepted but unused" naming the pattern.

**Cross-references.** `rules/zero-tolerance.md` Rule 6 (Implement Fully), `rules/observability.md` Rule 1 (use the framework logger — log when ignoring an arg, don't silently drop).

## 5. Accepted-literals-without-dispatch as `rules/zero-tolerance.md` Rule 2 instance (origin: #701 bonus finding)

**Pattern.** `diagnose(kind=...)` accepts `kind="clustering"`, `kind="alignment"`, `kind="llm"`, `kind="agent"` as valid literals (passes the validation gate at `_wrappers.py:474–485`) but has NO dispatch branch — every one falls through to `DLDiagnostics(subject)`. Documented in the spec as supported `kind` values; silently broken in practice.

This is structurally the same as `rules/zero-tolerance.md` Rule 2 "fake X" patterns: fake encryption, fake transaction, fake health, fake classification. Add: **fake dispatch** — accepted in the literal list, no branch in the dispatcher.

**Rule candidate.** Extension to `rules/zero-tolerance.md` Rule 2 with explicit "fake dispatch" subentry and a `/redteam` grep protocol — for any `Literal[...]` or `Enum`-valued dispatch parameter, AST-walk the dispatcher to confirm every literal has a branch.

**Cross-SDK applicability.** GLOBAL. Rust's `match` exhaustiveness check structurally prevents this for `enum DiagnosticKind`, but `&str` dispatch is NOT exhaustively-checked — same gap exists if Rust ever adds a string-dispatch surface. Python lacks the structural check entirely; the rule is the only defense.

**Likely placement.** Extension to `rules/zero-tolerance.md` Rule 2 § Extended BLOCKED Patterns with a fake-dispatch subentry.

**Cross-references.** `rules/orphan-detection.md` Rule 1 (every public symbol must have a production call site — the dispatch BRANCH is the call site for an accepted literal).

## Open questions for `/codify` (post-redteam)

- Candidates 4 and 5 are sub-extensions to existing rules (`zero-tolerance.md`). Worth asking at codify time whether the existing rule already covers them in spirit, or whether the explicit subclause is load-bearing.
- Candidate 1 (API deprecation discipline) is the most likely to need a NEW rule file. Worth scoping the rule's blast radius before drafting — does it apply to internal-only APIs, or only public-API surface (re-exported via `__all__`)?
- Candidate 3 (brief-verification) is meta — it's about the COC analyze phase itself, not about SDK code. Likely belongs in `skills/analyze` or a CC-artifact rule rather than an SDK rule.
