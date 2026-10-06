#!/usr/bin/env bash
# Run Python hooks on the fleet from this checkout's frozen uv environment.
# Usage: scripts/development/find-venv-python.sh -m pytest tests/unit/
# Historical name retained for the existing pre-commit entries.
set -euo pipefail

if [ "$#" -eq 0 ] || [ -z "$1" ]; then
  echo "find-venv-python.sh: a Python module or script argument is required" >&2
  exit 64
fi

# Fleet execution is the default. Legacy settings must not silently select
# local execution or a host; callers must remove them rather than bypass it.
case "${KAILASH_TRESTLE_TESTS:-}" in
  ''|1) ;;
  *)
    echo "find-venv-python.sh: KAILASH_TRESTLE_TESTS no longer disables fleet execution; unset it" >&2
    exit 64
    ;;
esac
if [ -n "${KAILASH_TRESTLE_HOST:-}" ]; then
  echo "find-venv-python.sh: host pinning is disabled; unset KAILASH_TRESTLE_HOST" >&2
  exit 64
fi
case "${KAILASH_TRESTLE_OS:-}" in
  ''|linux|darwin) ;;
  *)
    echo "find-venv-python.sh: KAILASH_TRESTLE_OS must be linux or darwin" >&2
    exit 64
    ;;
esac

# A fixed suffix protects pathname newlines from command substitution. Strip
# the suffix and exactly one command-output newline, leaving the path intact.
FLEET_REPO=$(git rev-parse --show-toplevel 2>/dev/null && printf '.') || FLEET_REPO=""
FLEET_REPO=${FLEET_REPO%.}
FLEET_REPO=${FLEET_REPO%$'\n'}
if [ -z "${FLEET_REPO}" ]; then
  echo "find-venv-python.sh: not inside a git repository" >&2
  exit 64
fi
FLEET_REPO=$(CDPATH='' cd -- "${FLEET_REPO}" && pwd -P && printf '.') || {
  echo "find-venv-python.sh: cannot resolve the checkout root" >&2
  exit 64
}
FLEET_REPO=${FLEET_REPO%.}
FLEET_REPO=${FLEET_REPO%$'\n'}
TRESTLE_ARGS=(run --repo "${FLEET_REPO}")
if [ -n "${KAILASH_TRESTLE_OS:-}" ]; then
  TRESTLE_ARGS+=(--os "${KAILASH_TRESTLE_OS}")
fi
UV_ARGS=(run --project . --frozen)
if [ -n "${UV_PYTHON:-}" ]; then
  UV_ARGS+=(--python "${UV_PYTHON}")
fi

# Trestle snapshots the current checkout and starts at its root. uv installs
# the lockfile's editable sources there; inherited local interpreter/import
# paths must not redirect those imports into another checkout. Launch uv
# directly so the remote command cannot recurse through this wrapper.
# exec preserves command status, including 114 (unknown) and 116 (not run).
exec trestle "${TRESTLE_ARGS[@]}" -- env \
  -u KAILASH_TRESTLE_TESTS -u PYTHONPATH -u PYTHONHOME \
  -u VIRTUAL_ENV -u UV_PROJECT_ENVIRONMENT UV_LINK_MODE=copy \
  uv "${UV_ARGS[@]}" \
  --extra dev --extra server --extra http-client \
  --extra db-postgres --extra db-mysql --extra db-sqlite --extra redis \
  --extra trust --extra auth --extra auth-azure --extra monitoring \
  --extra telemetry --extra scheduler --extra mcp --extra data \
  --extra rfc3161 --extra dataflow --extra nexus --extra kaizen python "$@"
