# DISCOVERY — `uv pip install --refresh` can still resolve to stale index when PyPI metadata is current

**Date**: 2026-05-01
**Author**: Claude Opus 4.7 (1M context) — `/autonomize` release verification
**Type**: DISCOVERY

## Context

Per `rules/build-repo-release-discipline.md` Rule 2 § "uv index-cache override":

> when `pypi.org/pypi/<pkg>/<ver>/json` returns the new metadata BUT
> `uv pip install "<pkg>==<ver>"` reports `No solution found ...`, the gap
> is uv's local index cache. Pass `--refresh` to force a re-fetch.

Discovered today: `--refresh` alone is insufficient when uv's deeper index-state cache pins the previous "latest" version even after the HTTP response cache is invalidated.

## Reproduction

```bash
# After tag-push triggered publish-pypi.yml success
$ curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/kailash-dataflow/2.7.5/json
200

$ curl -s https://pypi.org/pypi/kailash-dataflow/json | python -c 'import sys,json; print(json.load(sys.stdin)["info"]["version"])'
2.7.5

$ uv venv /tmp/v --python 3.13
$ uv pip install --refresh --python /tmp/v/bin/python "kailash-dataflow==2.7.5"
× No solution found when resolving dependencies:
  ╰─▶ Because there is no version of kailash-dataflow==2.7.5 and you require
      kailash-dataflow==2.7.5, we can conclude that your requirements are
      unsatisfiable.
```

## Resolution

Fall back to direct pip via `ensurepip`:

```bash
$ /tmp/v/bin/python -m ensurepip --upgrade
Successfully installed pip-25.2

$ /tmp/v/bin/python -m pip install --no-cache-dir "kailash-dataflow==2.7.5"
Successfully installed kailash-dataflow-2.7.5  # one-shot success
```

pip's index TTL is shorter than uv's deeper index-state cache. `--no-cache-dir` further bypasses pip's local wheel cache.

## Why this matters

`build-repo-release-discipline.md` Rule 2 mandates a clean-venv install + import as the "done gate" for every release. If `uv pip install --refresh` reports unresolvable, an agent following the existing rule paragraph stalls on the verification step until the cache settles (which can be ~5-15 min in practice, plus another retry cycle if the rule's "retry up to 3× with 60s pause" interpretation is taken literally).

The pip-direct fallback is one shell command and resolves immediately. Codified in proposal `2026-05-01-uv-pip-refresh-fallback` for upstream `build-repo-release-discipline.md` Rule 2 § "uv index-cache override".

## Class generalization

This is a sub-case of "second-tier cache-invalidation fallback when first-tier flag fails". Same shape applies to:

- `npm install --no-cache` when `npm cache clean --force` doesn't surface the new version
- `cargo build` when the registry index TOML is stale despite `cargo update`
- Any tool with a multi-layer cache where the documented invalidation flag clears one layer and not the deeper one.

The institutional learning: when a documented `--refresh` / `--no-cache` flag fails to resolve a known-published artifact, the second-tier escape hatch is a different tool/command on the same source-of-truth, not a longer wait. Speed of recovery matters.
