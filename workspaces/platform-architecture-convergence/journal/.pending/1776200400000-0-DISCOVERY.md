# DISCOVERY: pact-v0.8.1 tag silent drop from batch push

**Date**: 2026-04-12
**Workspace**: platform-architecture-convergence

## Finding

When multiple git tags are pushed simultaneously (`git push --tags`), GitHub Actions silently drops webhook events for some tags. The `pact-v0.8.1` tag was pushed alongside 4 other tags during the v2.8.3 release — the other 4 triggered CI publish workflows, pact did not. The tag existed on the remote, the source was correct, but PyPI never received the package.

## Impact

- `pip install kailash[all]` broken for all users (dependency on `kailash-pact>=0.8.1` unresolvable)
- Docker Hub image build failed (same dependency)
- No CI signal — the absence of a workflow run is invisible in the GitHub Actions UI

## Mitigation

Used `gh workflow run publish-pypi.yml -f package=kailash-pact -f publish_to=pypi` to manually trigger. Future releases should verify each tag's CI run fired, or push tags one at a time.
