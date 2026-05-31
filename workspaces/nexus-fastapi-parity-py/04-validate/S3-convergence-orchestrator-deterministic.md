---
type: CONVERGENCE-STATUS
shard: S3 (AC 4 — Multipart + UploadFile body extractors)
status: APPROVED via orchestrator-deterministic review (agent panel throttled) + 1 hardening applied
branch: feat/1174-s3-multipart
date: 2026-05-31
---

# Shard 3 (Multipart/UploadFile) — convergence via orchestrator-deterministic review

## Why orchestrator-deterministic (transient-infra honesty per `verify-resource-existence.md` MUST-4)

The reviewer + security-reviewer dispatches both terminated with the transient
Anthropic server-side rate-limit (`not your usage limit`), 0 findings — the same
infra throttle documented at S2 / R5 / R6. Per that precedent the orchestrator
ran the deterministic / mechanical review lenses directly, including an
ADVERSARIAL probe of the path-traversal sanitizer (the canonical multipart
exploit).

**Throttled-dispatch receipts:** reviewer `a5785d773df02ad08`; security-reviewer `a50007579605ced12` (both rate-limited, 0 findings).

## Deterministic checks (orchestrator-run, with receipts)

1. **Tests (real parser/sniff/tempfiles, no mocking):** `pytest .../integration/nexus/ -q` → **87 passed** (after the hardening + 4 new vectors); path-traversal suite **12 passed**; `--collect-only` exit 0.
2. **Path-traversal (MUST-3) — adversarially probed.** `sanitize_upload_filename` neutralizes every real-separator attack: `../../../etc/passwd`→`passwd`, `..\..\windows\system32\cmd.exe`→`cmd.exe`, leading `/`→basename, `..`/`.`/`../`/`/`→`upload`, reserved dirs stripped. **FINDING (defence-in-depth, fixed in commit on this branch):** an encoded-separator payload leaving a leading-`..` basename (`..%2f..%2fetc`) and a NUL byte (`file\x00.txt`) passed through; hardened to reject leading-`..` + strip NUL. Legit `.gitignore` / `foo..bar.txt` preserved. The resolver never `open()`s the unsanitized value (test asserts).
3. **File-DoS caps (MUST-1/2/6):** total-body Content-Length pre-check → 413 before parse; per-file cap → 413 first-over (no partial); file-count cap via Starlette `max_files` → early `TOO_MANY_FILES` 413 at the (cap+1)th file (bounds memory). Body spools to disk (Starlette spool threshold) — memory bounded.
4. **MIME-confusion (MUST-4):** `content_type` derived from a puremagic content-sniff of the first 4 KiB; client header captured as `client_declared_content_type` (audit) but NEVER what the handler sees; `mime_sniffer` override + degrade-on-ImportError (WARN, never crash).
5. **Tempfile lifecycle (MUST-5):** `parse_multipart_uploads` `except BaseException` closes every parsed file; the resolver `finally` (resolver.py:467-474) closes `files_to_close` — cleanup in both success + exception branches.
6. **Hygiene:** no `eval`/`exec`/`subprocess`; raw filename NOT echoed in error bodies (`UploadFileTooLargeError` omits it) or logs; `puremagic>=1.0` + `python-multipart>=0.0.9` declared in nexus pyproject (Declared=Imported); no new top-level `fastapi` dep; the 3 new config kwargs coexist with Shards 2+4's kwargs (rebase clean); unused `import io` removed.
7. **Gateway-boundary test approach:** the `/workflows/execute` route binds JSON (422 on raw multipart before the resolver), so Tier-2 tests drive the real resolver chain with a real Starlette multipart Request — same documented precedent as Shard 1's `Bytes` extractor. Legitimate (real parser + real puremagic + real tempfiles exercised), not masking.

## Verdict

**APPROVE** (with the leading-`..`/NUL hardening applied this branch). CI (full matrix incl CodeQL) is the remaining gate.

## Note (bounded, not blocking)

Encoded-separator residue in the MIDDLE of a name (`foo%2f..%2fbar`) is not decoded by the sanitizer (it strips real separators only); the contract is "result is an opaque single filename — callers MUST NOT URL-decode before filesystem use." Same disk-spool (not memory) bound for a no-Content-Length chunked body as Shard 1's `Bytes` MED-1 (accepted).
