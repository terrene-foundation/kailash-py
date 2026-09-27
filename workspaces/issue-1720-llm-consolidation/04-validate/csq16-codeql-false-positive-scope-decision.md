# D1 CodeQL false-positive disposition packet

Status: review complete for the nine candidates below; no new dismissal authorized
or performed. Whether they still block promotion will be checked on the next exact
candidate scan. Existing approved dismissals and the173spec-advisory exception keep
their separate scopes.

| Alert IDs | Proposed classification | Executed evidence |
| --- | --- | --- |
|10967|False positive: forbidden constructor intentionally always raises|All6generated forbidden operations raise AppendOnlyViolationError before base initialization; direct bypassrun also rejects. Removing the constructor raise creates6returned instances.|
|10936,185|False positive: Kaizen cyclic imports are type-only|Both cold public import orders and real framework/agent creation succeed; traced guarded import hits0. Forcing guards executes the alerted lines and fails with partially initialized-module ImportError.|
|184,180|False positive: gateway reverse import is type-only|Both cold public import entry orders, real CheckpointManager construction and Checkpoint dictionary roundtrip succeed. Forcing the guarded reverse import reaches line37 and raises a partial-initialization ImportError.|
|11226,5152|False positive: flagged world-readable files contain public verification keys|Actual Ed25519 public material verifies signatures made by the corresponding private key. Opposite controls replacing public material with private bytes are detected. Private-key permission/lifecycle and nonregular-file defects were repaired and tested separately.|
|5112|False positive: SHA256 is an in-memory client-cache fingerprint|Full source and callsite inspection finds no password authentication or stored password verifier. Distinct Optional[str] identity probes cover400pairs twice; plaintext-index opposite controls detect retained credentials. The separate delimiter/Unicode identity defects are repaired.|
|153|False positive: flagged file is a static public executable|Different node/config values produce byte-identical entrypoint scripts with mode0755; synthetic secret canary is absent. Appending it as a control is detected.|

The proposed action, if required after the new scan, is to mark only these9alert IDs
as `false positive`, with a per-alert explanation citing the executable evidence.
This packet requests no severity change, disabled query, blanket dismissal or
accepted source-security defect. Other scanner findings remain independently open
until their own repair or disposition is verified.

Evidence is retained in `csq16-codeql-three-errors-review.json`,
`csq16-codeql-gateway-import-review.json`,
`csq16-codeql-remaining-high-triage.json` and
`csq16-dev-and-false-positive-review.json` and `csq16-byok-security-review.json`. These pin source hashes, actual output,
opposing controls and scope limits. The gateway probe tests construction and a
Checkpoint dictionary roundtrip; it does not claim disk persistence coverage.

The scanner's427PR-new summary cannot be reconstructed from its100annotations
and the downloaded SARIF. Branch-alert totals and main-set differences are distinct
measurements. A successful source review therefore does not claim the remote check
has passed; the exact new head must be scanned and read before promotion.
