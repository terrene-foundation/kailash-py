# Nine scoped CodeQL disposition proposals

No dismissals have been made. The recovered approval covers only alerts 11587,
11588 and 11594; these nine additional dispositions require an explicit decision.
This revised proposal supersedes the pending eight-alert question by adding 6082.
The proposal does not waive CodeQL, change queries, alter scan scope, or authorize
merging a failing promotion. Actual defects are being repaired separately.

| Alert | Reported issue | Observed protection and negative control | Proposed disposition |
| --- | --- | --- | --- |
| 11595 | Polynomial JSON-token regex | The actual regex receives only text accepted by whole-document `json.loads`. Malformed escaped-quote input reached the regex zero times; valid JSON reached it once. The raw unguarded regex control slowed from 0.007s at 1,000 repetitions to 1.009s at 4,000; the guarded public path at 4,000 took 0.000246s. | False positive for the reported malformed-input path. |
| 11596 | Polynomial scheme regex | The negative lookbehind prevents restarting within one scheme-character run. The actual 16,000-character input took 0.000136s; removing that reached boundary produced 1.333s. A credential-bearing URL control was still masked. | False positive for the reported repeated-letter path. |
| 11466, 11467 | Cleartext secret logging | The actual nested DataFlow sanitizer emits a schema-field digest and a fixed pattern or `value redacted`; the synthetic secret value was absent. Replacing the reached digest helper with identity exposed the field name and failed the instrument. The schema name remains dictionary-recoverable, which is a documented correlation property, not a confidentiality claim. | False positives for cleartext secret-value disclosure. |
| 10866 | Cleartext secret logging | The actual preset rejection path emits an eight-hex tag of a public preset name, not the raw supplied value. The reached identity-helper mutation exposed it and failed the instrument. This does not claim secrecy for enumerable preset names. | False positive for secret logging at this public-symbol diagnostic. |
| 5153 | Overly permissive secret file | Actual generated Ed25519 private bytes were written to mode 0600, public bytes to mode 0644. The public key verified the legitimate signature but could not forge one under the trusted verifier. A reached mutation writing private bytes into the public file failed the content assertion. | False positive for the public-key file. |
| 131, 133 | Incomplete script-tag filter | The complete generic and shell branches remove every angle bracket. Actual malformed closing-tag, nested-tag and image-handler inputs produced no tag delimiters. Removing each reached bracket-removal backstop left `<script>alert(1)</script >` and failed the instrument. | False positives for tag creation through these branches. |
| 6082 | Missing parent finalizer call | Both finalizers intentionally warn without cleanup. Calling the actual subclass finalizer emitted one warning and left owned resources unchanged; adding the actual parent call emitted two warnings, with no added cleanup. Closed and partially constructed objects emitted none. | False positive for this deliberate replacement of a warning-only parent finalizer. |

## Evidence and limits

Production references: `src/kailash/utils/url_credentials.py:501-565`,
`packages/kailash-dataflow/src/dataflow/core/nodes.py:1048-1079`,
`packages/kailash-kaizen/src/kaizen/llm/presets.py:105-123`,
`src/kailash/trust/plane/project.py:144-175`, and
`src/kailash/security.py:1270-1295`.

The source-pinned executable evidence is recorded in
`/tmp/csq14-codeql-runtime-probe.log` and `/tmp/csq14-seven-alert-probes.log`.
The JSON/scanner checks establish the specified guard ordering and reported
attack paths, not a universal performance bound for arbitrary future changes.
The DataFlow proof executes the extracted, unchanged nested producer with its
exact lexical patterns; it does not claim an end-to-end generated-node run.
The key-file proof covers fresh files on local POSIX, not existing permissions
or Windows ACLs. The HTML checks establish removal of tag delimiters, not safety
in every possible HTML/JavaScript context.

Alert 6082 evidence is `/tmp/csq14-finalizer-disposition-proof.log`, using actual
`src/kailash/runtime/async_local.py:2189-2220` and
`src/kailash/runtime/local.py:2200-2229`. This establishes the warning-only
replacement contract; deterministic cleanup remains the caller's responsibility.

The latest full scan has 2,253 results. GitHub's required findings check reports
265 alerts and exposes only 100 annotations. These proposals identify specific
alert IDs; none of the alternative inventories is asserted to equal that hidden
265-alert set. All required checks still need to pass on the final PR head.

Alert 11597 was repaired by removing a beneficiary from DEBUG logging. Alert
11624 was repaired by deleting a duplicated regex character. A separate email
correlation privacy repair landed at eae68c672; alert 11474 is intentionally excluded
from this proposal. The remaining confirmed lifecycle, migration and transaction
issues continue through implementation and independent review.
