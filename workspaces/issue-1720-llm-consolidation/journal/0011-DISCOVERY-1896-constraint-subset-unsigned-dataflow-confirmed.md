# DISCOVERY — #1896 audit: constraint_subset is unsigned AND feeds the effective-constraint surface (enforcement-consumption link unproven)

Date: 2026-07-21 (cont-6). Repo class: BUILD. Coordination OFF (un-enrolled public repo).
Read-only audit; no code changed. Advances F5/#1896 from journal 0009 "For Discussion" item 1.

## Question (journal 0009 F5)

Does v2/v3 delegation enforcement read `constraint_subset` (a field that round-trips
faithfully but is NOT in the v2/v3 signed pre-image), making it a live tamper surface?

## FACTS (each quoted/verified this session)

1. **`constraint_subset` is NOT in the signed pre-image.** `_FoldSourceRecord`
   (`src/kailash/trust/signing/delegation_fold_serde.py:53-67`) folds exactly:
   `constraints`, `resource_limits`, `scope`, `multi_sig`, `multi_sig_policy`.
   `constraint_subset` is ABSENT. → editing a persisted `constraint_subset` does NOT
   break the delegation signature.
2. **`constraint_subset` and the signed `constraints` are DIFFERENT fields.**
   `DelegationRecord.constraint_subset: List[str]` (chain.py:294, "Additional constraints
   (tightening only)") vs the signed `constraints: Optional[ConstraintDimensions]`
   (chain.py:334). The fold signs `constraints` (dimensions object); the runtime
   aggregation reads `constraint_subset` (the list).
3. **`constraint_subset` flows into the effective-constraint surface.**
   `TrustLineageChain.get_effective_constraints` (chain.py:933) does
   `constraints.update(delegation.constraint_subset)` → returned as
   `VerificationResult.effective_constraints` (operations/**init**.py:735, populated at the
   point `valid=True` is ALREADY decided — a REPORTING field, not the gate) →
   `runtime/trust/verifier.py:398` builds `constraints={c: True for c in
kaizen_result.effective_constraints}` AND `trusted_agent.py:693` sets
   `ctx.effective_constraints = ...`.

## INFERENCE (labeled — NOT proven)

Whether the `{c: True}` runtime constraints map / `ctx.effective_constraints` is READ to
make an allow/deny/restrict decision. A bounded grep found it surfaced into the runtime
result map (verifier.py:343 `constraints=result.constraints`), the trust context merge
(context.py:231), and the TrustedAgent execution ctx — but NO definitive SDK-core gate that
DENIES on a missing/edited effective-constraint. It reads as advisory/contextual;
applications MAY enforce it. The enforcement-consumption link is the remaining open question.

## DISPOSITION

The tamper surface is **REAL in dataflow** (an unsigned field, `constraint_subset`, reaches
the effective-constraint reporting/context surface, and what is SIGNED — `constraints`
dimensions — differs from what the runtime aggregates — `constraint_subset`). Severity is
**bounded**: no confirmed privilege-escalation, because no SDK-core enforcement gate on
`effective_constraints` was found this audit. This CONFIRMS F5 as a genuine
integrity-hygiene gap for the #1841 signing-coverage owners, and does NOT overclaim it as an
exploitable escalation. Recommended fix (owner decision): fold `constraint_subset` into the
v2/v3 signed pre-image (defense-in-depth; it is documented "tightening only" and is
security-relevant), OR document that `effective_constraints` is advisory-not-enforced.
Not fixed here — #1896 stays OPEN with this evidence attached (value-bearing; no user close-gate given).
