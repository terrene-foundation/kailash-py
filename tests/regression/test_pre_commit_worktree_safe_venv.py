# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test — pre-commit hook entries MUST NOT reference a bare
``.venv/bin/python`` path. Such paths break in git worktrees
(``.claude/worktrees/<X>/``) where pre-commit invokes hooks with cwd at
the worktree, NOT the main checkout. The main checkout's ``.venv/`` does
not exist inside worktrees, so a bare-path entry raises
``No such file or directory`` and blocks every commit until the user
bypasses via ``git -c core.hooksPath=/dev/null``.

The fix uses ``scripts/development/find-venv-python.sh``, which resolves
the canonical interpreter via ``git rev-parse --git-common-dir`` —
worktree-safe by construction.

Origin: 2026-04-27 W7 worktrees both required ``core.hooksPath=/dev/null``
bypass per ``rules/git.md`` § Pre-Commit Hook Workarounds. Wrapper script
lands as part of the W7 follow-up cycle.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.regression
def test_pre_commit_config_has_no_bare_venv_entry():
    """``entry: .venv/bin/python ...`` is BLOCKED. Use
    ``scripts/development/find-venv-python.sh`` instead."""
    config = REPO_ROOT / ".pre-commit-config.yaml"
    text = config.read_text()
    bad_pattern = re.compile(r"^\s*entry:\s*\.venv/bin/python\b", re.MULTILINE)
    matches = bad_pattern.findall(text)
    assert matches == [], (
        f"{config} has {len(matches)} hook entries that reference "
        f"`.venv/bin/python` directly. This breaks in git worktrees. "
        f"Replace with: `entry: scripts/development/find-venv-python.sh ...`"
    )


@pytest.mark.regression
def test_find_venv_python_wrapper_exists_and_executable():
    """The wrapper MUST exist and be executable. If the file is removed
    every pre-commit hook breaks; if non-executable pre-commit cannot
    invoke it."""
    wrapper = REPO_ROOT / "scripts" / "development" / "find-venv-python.sh"
    assert (
        wrapper.exists()
    ), f"missing wrapper at {wrapper}; pre-commit hooks reference it"
    # `executable` mode bit (0o111). Check at least owner-execute (0o100).
    mode = wrapper.stat().st_mode
    assert mode & 0o100, (
        f"wrapper at {wrapper} is not owner-executable (mode={oct(mode)}); "
        f"pre-commit invocation will fail with PermissionError"
    )


@pytest.mark.regression
def test_find_venv_python_uses_git_common_dir_resolution():
    """Wrapper MUST use ``git rev-parse --git-common-dir`` so worktrees
    resolve to the main checkout's ``.venv/``. A simpler ``readlink -f .venv``
    or ``./.venv/bin/python`` would NOT survive worktree cwds."""
    wrapper = REPO_ROOT / "scripts" / "development" / "find-venv-python.sh"
    text = wrapper.read_text()
    assert "git rev-parse --git-common-dir" in text, (
        f"wrapper at {wrapper} no longer uses --git-common-dir resolution. "
        f"Other resolution mechanisms (readlink, GIT_DIR, find . -maxdepth) "
        f"are NOT worktree-safe. See rules/git.md § Pre-Commit Hook Workarounds."
    )


@pytest.mark.regression
@pytest.mark.parametrize("host", [None, "", "esperie-ai", "host with spaces; $(false)"])
@pytest.mark.parametrize("python", [None, "", "3.13", "python with spaces; $(false)"])
def test_trestle_pytest_routing_preserves_arguments_and_failure(tmp_path, host, python):
    """The opt-in sends the exact hook arguments and propagates fleet failure."""
    import json
    import os
    import subprocess
    import sys

    launcher = tmp_path / "trestle"
    receipt = tmp_path / "arguments.json"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['TRESTLE_ARGUMENTS'], 'w') as output:\n"
        "    json.dump(sys.argv[1:], output)\n"
        "sys.exit(23)\n"
    )
    launcher.chmod(0o755)
    checkout = tmp_path / "checkout with spaces; $(false)"
    subprocess.run(["git", "init", "--quiet", str(checkout)], check=True)
    arguments = ["-m", "pytest", "tests/unit/", "-m", "not (slow or integration)"]
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "KAILASH_TRESTLE_TESTS": "1",
        "TRESTLE_ARGUMENTS": str(receipt),
    }
    environment.pop("KAILASH_TRESTLE_HOST", None)
    environment.pop("UV_PYTHON", None)
    if host is not None:
        environment["KAILASH_TRESTLE_HOST"] = host
    if python is not None:
        environment["UV_PYTHON"] = python
    result = subprocess.run(
        [str(REPO_ROOT / "scripts/development/find-venv-python.sh"), *arguments],
        cwd=checkout,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 23, result.stderr
    expected_extras = [
        "dev",
        "server",
        "http-client",
        "db-postgres",
        "db-mysql",
        "db-sqlite",
        "redis",
        "trust",
        "auth",
        "auth-azure",
        "monitoring",
        "telemetry",
        "scheduler",
        "mcp",
        "data",
        "rfc3161",
        "dataflow",
        "nexus",
        "kaizen",
    ]
    assert json.loads(receipt.read_text()) == [
        "run",
        "--no-reap-cache",
        "--no-reap-mirrors",
        "--repo",
        str(checkout.resolve()),
        *(["--host", host] if host else []),
        "--",
        "env",
        "-u",
        "KAILASH_TRESTLE_TESTS",
        "UV_LINK_MODE=copy",
        "uv",
        "run",
        "--frozen",
        *(["--python", python] if python else []),
        *[argument for extra in expected_extras for argument in ("--extra", extra)],
        "python",
        *arguments,
    ]


@pytest.mark.regression
def test_trestle_pytest_routing_refuses_missing_checkout(tmp_path):
    """Fleet routing must not dispatch tests outside a Git checkout."""
    import os
    import subprocess

    environment = {**os.environ, "KAILASH_TRESTLE_TESTS": "1"}
    result = subprocess.run(
        [str(REPO_ROOT / "scripts/development/find-venv-python.sh"), "-m", "pytest"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64
    assert "not inside a git repository" in result.stderr
