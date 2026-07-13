# #1717 — redteam convergence receipt

Commits: 4eeb7e7b5 (feat), 7133d4e7a (gate remediation), e1d30f7ec (redteam remediation).
Branch: feat/1717-vertex-claude-four-axis-completion.

## Gate review (over 4eeb7e7b5)

- **reviewer** (gate-reviewer): CLEAN — no Critical/Important. Verified gated body
  transform byte-identical for direct paths, redact-before-shape, real SSRF-safe
  streaming, temperature handling, error-taxonomy parity. 3 <20-LOC minors → all
  folded (stream() HTTPError catch parity; temperature-determinism docstring;
  lifecycle GC pre-drain).
- **security-reviewer** (gate-security): 1 MEDIUM — caller `model` interpolated raw
  into URL path (Google/Bedrock/HF {model} templates). Fixed: `_validate_completion_model`
  fail-closed in `_build_completion_request` (covers complete()+stream()). Behavioral
  regression test. All other surfaces CLEAN (GCP cred hygiene, no-secrets-in-logs,
  streaming SSRF, redaction).

## Holistic /redteam (3 parallel, over 4eeb7e7b5 + 7133d4e7a)

- **rt-closure** (general-purpose, Bash+Read): every AC (1–8) + NEW-A/B/C VERIFIED —
  each backed by delivered code AND a passing test; NEW-B/C confirmed by live probe.
  141 targeted tests pass, collection exit 0.
- **rt-security** (security-reviewer): fix CLOSES THE CLASS; 1 LOW — regex `$` allows
  a single trailing newline. Fixed `$`→`\Z` + trailing-\n/\r/\t reject cases + e2e
  reject through a {model}-template (Bedrock) wire.
- **rt-correct** (reviewer): cross-shard CLEAN; 1 LOW/MED (F1) — complete() leaked the
  owned client on a non-httpx send-phase error (SSRF InvalidEndpoint / auth-refresh).
  Fixed: catch-all send-phase clause closes owned client + re-raises (symmetry with
  stream()). Regression test PROVEN to fail without the fix. Confirmed the 3
  cross_sdk_parity failures are pre-existing on main (ran main in throwaway worktree:
  list_presets()=42 vs fixture 24).

## Convergence

All findings remediated with regression tests. Suite: 1205 passed / 11 skipped,
stable across runs. Remaining 3 failures = pre-existing cross_sdk_parity drift
(registry 42 vs Rust fixture 24 + deepseek legacy-key order) — NOT introduced this
session (verified red on base 6c8bd36d9 and on main), different bug class, NOT
CI-gated (kaizen has no job in unified-ci.yml). Surfaced to co-owner (§ disposition
in 0002 + issue comment): needs Rust ground truth / cross-repo grant to reconcile.
