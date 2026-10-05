# CSQ16 current-source promotion claim corrections — 2026-10-05

Three independent parallel source audits actually ran against frozen dev
`e9ad3ab7153aa08170bc2178758532a49e55f0c5`. The parent read their full
concise reports, operative evidence, independently discriminating controls
and scope limits. These findings cover the twelve failure/warning rows in
the retained stale PR2229 annotations; the other eighty-eight notice rows
remain NOT_AUDITED. No current CodeQL execution or annotation dismissal
was performed. The stale run's FAILURE remains unresolved.

## Brief corrections before repair allocation

| Row | Current source disposition | Evidence and practical limit |
| --- | --- | --- |
| 0 | Functional missing-parent-construction interpretation refuted | The constructor consists of `raise AppendOnlyViolationError(...)` and never returns an initialized instance. The literal no-super observation remains true. `packages/kailash-dataflow/src/dataflow/core/nodes.py:389-397`. |
| 1 | Standard URL-password sink interpretation refuted | The actual logger receives `safe_log_field(scheme)` after `scheme = database_url.split("://")[0] if "://" in database_url else "unknown"`. Standard URL userinfo/query credentials lie after that delimiter. Arbitrary secrets in malformed scheme text remain UNANSWERED. `packages/kailash-dataflow/src/dataflow/utils/pool_utils.py:151-156`. |
| 2 | Constructor keyword defect confirmed | ProtectedDataFlow passes `WorkflowBuilder(workflow_id=workflow_id, **kwargs)`, but Core's constructor accepts only `edge_config`. This is a source-derived binding failure, not an executed reproduction. Preserve actual workflow identity and advertised metadata; dropping the keyword silently is not a repair. `packages/kailash-dataflow/src/dataflow/core/protected_engine.py:156-165`; `src/kailash/workflow/builder.py:24-47`. |
| 3 | Nonbulk graph-call arity defect confirmed | The per-record helper calls `add_connection(previous, next)` while Core requires four explicit node/port arguments. Preserve independent record data rather than inventing ports or copying one record into the next. `packages/kailash-dataflow/src/dataflow/testing/simple_test_utils.py:101-136`; `src/kailash/workflow/builder.py:570-585`. |
| 4–5 | Specific reciprocal runtime-import cycle interpretation refuted | Reciprocal imports are under `if TYPE_CHECKING:`; actual framework Agent imports occur within `_lazy_import_agents()`. This does not certify all imports or package runtime behavior. `packages/kailash-kaizen/src/kaizen/core/agents.py:73-74`; `packages/kailash-kaizen/src/kaizen/core/framework.py:10-15`; `packages/kailash-kaizen/src/kaizen/core/framework.py:39-43`. |
| 6 | Redundant pass and deeper audit integration gap confirmed | `original_node = node_params["node_instance"]` is followed by an unconsumed wrapper path and `pass`; metadata separately advertises audit. Removing only pass leaves the same-function stub. Derive PythonCodeNode callable ownership before implementing the operative wrapper. `packages/kailash-kaizen/src/kaizen/signatures/core.py:1655-1676`. |
| 7–8 | Keyword entry and Core forwarding defects confirmed | Both overrides use `execute(self, input_data)`, while Core uses `execute(self, **runtime_inputs)`; each also calls `core_node.execute(input_data)`. Fix both boundaries together, retaining validation and existing direct-call compatibility. Runtime/security execution is NOT_RUN. `packages/kailash-kaizen/src/kaizen/nodes/security/ai_threat_detection.py:344-372`; `packages/kailash-kaizen/src/kaizen/nodes/security/ai_behavior_analysis.py:323-353`; `src/kailash/nodes/base.py:1583-1583`. |
| 9 | Dead initial transition assignment confirmed | Every branch assigns a transition, including the final `else` setting `"clarification"`, before the return reads it. Preserve reachable later assignments. `packages/kailash-kaizen/src/kaizen/nodes/rag/conversational.py:334-377`. |
| 10 | Supported validated-call failure interpretation refuted; structural warning retained | The schema declares `action` required and Core invokes `self.run(**validated_inputs)`; supplied keyword action binds. This does not prove general substitutability for invalid or third-party calls. `packages/kailash-kaizen/src/kaizen/nodes/compliance/gdpr.py:284-332`; `src/kailash/nodes/base.py:1365-1405`; `src/kailash/nodes/base.py:1661-1677`. |
| 11 | Formal signature mismatch confirmed; valid-call failure unproven | FileSource adds required `file_path` compared with AsyncNode's kwargs signature; inspected framework and Express callers supply the required field by keyword. Path safety and all direct-call behavior remain outside this audit. `packages/kailash-dataflow/src/dataflow/nodes/file_source.py:147-207`; `src/kailash/nodes/base_async.py:184-202`; `packages/kailash-dataflow/src/dataflow/features/express.py:2553-2563`. |

The logger audit decoded the complete quoted sink span before its narrow
security characterization. The Kaizen audit retained twenty-eight complete
decoded spans. AST controls independently discriminate rejecting versus
returning constructors, supported versus unsupported keywords, complete
versus short connections, eager versus guarded imports, operative versus
redundant pass, and exhaustive versus incomplete assignments. These are
source instruments, not SDK/security test execution or scanner closure.

## Raw evidence bindings

- DataFlow API JSON `/tmp/csq16-promotion-dataflow-api-source-audit.json`,
  SHA256 `241ebbb8976e1660800562d009ceed91129ae1e76069d1dda1987f05effbf911`.
- DataFlow logger JSON `/tmp/csq16-promotion-dataflow-log-source-audit.json`,
  SHA256 `e362e4543ea771ee7ebcfe056d6c7d0723a553a5df7aea74fb366fe79fc35b46`.
- Kaizen JSON `/tmp/csq16-promotion-kaizen-source-audit.json`,
  SHA256 `5e1011111f3a84df784557f9810b78c63c7e992c9803f3ff6299fcd9285db71f`.
- Retained annotations JSON SHA256
  `5047fc92c246364e990c197682ed9756a3e46f9030bfad082888d0fc602dde83`.

All three auditors returned clean read-only worktrees and drained jobs.
No source repair, clean review pair, original owner signoff or promotion
follows from these audits. Root allocated separate read-only DataFlow API
and Kaizen audit-wrapper contract consultations before implementation.
Core source remains the authority for a missing SDK primitive; no custom
builder, private patch, data-port fiction or silently dropped kwarg is
authorized. Root owns ledger/dev/reaping; peer SQLite ownership is unchanged.

## Reporting prerequisite review correction

Unlanded reporting source `c6f69b1ecd13a5c69aa7a624e5e2cca8df5c20ab`
passed its stock normal commit gate and one source correctness review.
Separate STATIC R1 is NONCLEAN: the existing fixture still asserts
`safe_type_name(Hostile()) == "<unrepresentable>"`, whereas the canonical
descriptor obtains the declared name `Hostile`. This is SOURCE INFERENCE;
the hostile fixture was NOT_RUN. Sources:
`tests/regression/test_redteam_round11b_unpinned_behaviours.py:123-144`;
`src/kailash/utils/secure_logging.py:651-672`, frozen c6.

STATIC report SHA256 is
`184e2958e3c9edda6378519dfaa2446b90f845587115669bde3d7b9e8b98be9c`.
The full fixture and decoded bytes are retained. Root allocated a separate
follow-up owning only the existing assertion and adjacent stale wording;
production/spec/other tests remain protected. Tier1 success does not prove
this regression ran. Final source must receive fresh correctness and
separate STATIC rounds; no old-context convergence credit transfers.
