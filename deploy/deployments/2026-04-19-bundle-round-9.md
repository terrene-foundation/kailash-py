# Bundle Release: Round 9 — 2026-04-19

## Packages Published

| Package          | Version | PyPI URL                                          | Tag                  | Notes                                            |
| ---------------- | ------- | ------------------------------------------------- | -------------------- | ------------------------------------------------ |
| kailash          | 2.8.8   | https://pypi.org/project/kailash/2.8.8/           | v2.8.8               | GPU-first Phase 1 (DeviceReport + km.device())   |
| kailash-dataflow | 2.0.11  | https://pypi.org/project/kailash-dataflow/2.0.11/ | dataflow-v2.0.11     | BP-049 classified-data leak fixes                |
| kailash-ml       | 0.11.0  | https://pypi.org/project/kailash-ml/0.11.0/       | ml-v0.11.0           | —                                                |
| kailash-align    | 0.3.2   | https://pypi.org/project/kailash-align/0.3.2/     | align-v0.3.2         | —                                                |
| kailash-pact     | 0.8.2   | https://pypi.org/project/kailash-pact/0.8.2/      | pact-v0.8.2          | —                                                |
| kaizen-agents    | 0.9.3   | https://pypi.org/project/kaizen-agents/0.9.3/     | kaizen-agents-v0.9.3 | —                                                |
| kailash-trust    | 0.1.1   | https://pypi.org/project/kailash-trust/0.1.1/     | trust-v0.1.1         | Initial release; manual twine upload (see below) |

## Release Commit

All version bumps in commit `640832e3` (feat(ml): GPU-first Phase 1).

## Incidents During Release

### 1 — CI failure: kailash-pact>=0.8.2 not on PyPI during PR #524

Root cause: root `[dev]` extra pinned `kailash-pact>=0.8.2` before 0.8.2 was published.
Fix: reverted pin to `>=0.8.1` in commit `78dea322`. PR #524 then went green and was admin-merged.

### 2 — trust-v0.1.1 publish workflow never triggered

Root cause: `publish-pypi.yml` had no `trust-v*` pattern in push.tags, no dispatch option for kailash-trust, no determine-package case branch.
Fix: PR #526 added all three entries. Admin-merged immediately.

### 3 — kailash-trust build failure: src/ was empty

Root cause: commit `eb1362a4` (eatp bridge removal) deleted all source from `packages/kailash-trust/src/`, leaving the directory with only the local `.egg-info` artifact (untracked). The pyproject.toml still declared `package-dir = { "" = "src" }`, so the build tool failed with "src does not exist or is not a directory".

Fix: PR #527 created `src/kailash_trust/__init__.py` (re-exports 30 symbols from `kailash.trust`) and `README.md`. Admin-merged.

### 4 — OIDC publish failure: "Non-user identities cannot create new projects"

Root cause: `kailash-trust` had never been published to PyPI before. PyPI's Trusted Publisher (OIDC) cannot create brand-new projects — the project must already exist.

Fix: Used local `~/.pypirc` token (`python3 -m twine upload`) to do the initial upload, creating the project. Future releases can use OIDC once a Trusted Publisher is registered for `kailash-trust` on pypi.org.

## Post-Release Pin Tighten (commit 9ca5b66c)

After all packages confirmed live on PyPI:

- `kailash-ml`: `kailash-dataflow>=2.0.10` → `>=2.0.11`
- `kailash-align`: `kailash-ml>=0.10.0` → `>=0.11.0`
- kailash root `[dev]`: `kailash-pact>=0.8.1` → `>=0.8.2`

## Follow-Up Required

- Register Trusted Publisher for `kailash-trust` on pypi.org to enable OIDC for future releases.
  Go to: https://pypi.org/manage/project/kailash-trust/settings/publishing/
  Add publisher: GitHub → terrene-foundation/kailash-py → workflow `publish-pypi.yml`
