# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test — pre-commit hook entries MUST NOT reference a bare
``.venv/bin/python`` path. Such paths break in git worktrees
(``.claude/worktrees/<X>/``) where pre-commit invokes hooks with cwd at
the worktree, NOT the main checkout. The main checkout's ``.venv/`` does
not exist inside worktrees, so a bare-path entry raises
``No such file or directory`` and blocks every commit until the user
bypasses via ``git -c core.hooksPath=/dev/null``.

The shared ``scripts/development/find-venv-python.sh`` wrapper routes Python
hooks through unpinned Trestle, shipping the current checkout and using its
frozen uv environment and editable sources.

Origin: 2026-04-27 W7 worktrees both required ``core.hooksPath=/dev/null``
bypass per ``rules/git.md`` § Pre-Commit Hook Workarounds. Wrapper script
lands as part of the W7 follow-up cycle.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _isolated_routing_environment() -> dict[str, str]:
    """Fixture cwd and parameters own Git discovery and routing selectors."""
    selectors = {
        "KAILASH_TRESTLE_HOST",
        "KAILASH_TRESTLE_OS",
        "KAILASH_TRESTLE_TESTS",
        "UV_PYTHON",
    }
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_") and name not in selectors
    }


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
def test_find_venv_python_routes_current_checkout_to_fleet():
    """The wrapper must snapshot the checkout whose hooks are running."""
    wrapper = REPO_ROOT / "scripts" / "development" / "find-venv-python.sh"
    text = wrapper.read_text()
    assert "git rev-parse --show-toplevel" in text
    assert "git rev-parse --git-common-dir" not in text
    assert 'TRESTLE_ARGS=(run --repo "${FLEET_REPO}")' in text


@pytest.mark.regression
@pytest.mark.parametrize(
    "host,python,platform,tests_setting,exit_code",
    [
        (host, python, None, None, 23)
        for host in [None, "", "esperie-ai", "host with spaces; $(false)"]
        for python in [None, "", "3.13", "python with spaces; $(false)"]
    ]
    + [
        (None, None, "", "", 23),
        (None, None, "linux", "1", 23),
        (None, None, "darwin", None, 23),
        (None, None, "platform with spaces", None, 23),
        (None, None, None, "0", 23),
        (None, None, None, None, 114),
        (None, None, None, None, 116),
    ],
)
@pytest.mark.parametrize(
    "arguments",
    [
        ["-m", "pytest", "tests/unit/", "-m", "not (slow or integration)"],
        ["scripts/spec_drift_gate.py", "--format", "human", "specs/path\nname.md"],
        ["scripts/ci/job_budget_audit.py"],
        ["tools/lint-delegate-fences.py"],
        ["tools/check_pin_consistency.py"],
        [],
        [""],
    ],
)
def test_trestle_python_routing_preserves_arguments_and_failure(
    tmp_path, host, python, platform, tests_setting, exit_code, arguments
):
    """Default fleet routing preserves argv/status and refuses old selectors."""
    import json
    import subprocess
    import sys

    launcher = tmp_path / "trestle"
    receipt = tmp_path / "arguments.json"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['TRESTLE_ARGUMENTS'], 'w') as output:\n"
        "    json.dump(sys.argv[1:], output)\n"
        "sys.exit(int(os.environ['TRESTLE_EXIT']))\n"
    )
    launcher.chmod(0o755)
    checkout = tmp_path / "checkout with spaces; $(false)\n"
    environment = _isolated_routing_environment()
    subprocess.run(
        ["git", "init", "--quiet", str(checkout)], check=True, env=environment
    )
    environment.update(
        {
            "PATH": f"{tmp_path}:{environment['PATH']}",
            "TRESTLE_ARGUMENTS": str(receipt),
            "TRESTLE_EXIT": str(exit_code),
        }
    )
    if host is not None:
        environment["KAILASH_TRESTLE_HOST"] = host
    if python is not None:
        environment["UV_PYTHON"] = python
    if platform is not None:
        environment["KAILASH_TRESTLE_OS"] = platform
    if tests_setting is not None:
        environment["KAILASH_TRESTLE_TESTS"] = tests_setting
    result = subprocess.run(
        [str(REPO_ROOT / "scripts/development/find-venv-python.sh"), *arguments],
        cwd=checkout,
        env=environment,
        capture_output=True,
        text=True,
    )
    if not arguments or not arguments[0]:
        refusal = "a Python module or script argument is required"
    elif tests_setting not in (None, "", "1"):
        refusal = "KAILASH_TRESTLE_TESTS no longer disables fleet execution"
    elif host:
        refusal = "host pinning is disabled"
    elif platform not in (None, "", "linux", "darwin"):
        refusal = "KAILASH_TRESTLE_OS must be linux or darwin"
    else:
        refusal = None
    if refusal is not None:
        assert result.returncode == 64, result.stderr
        assert refusal in result.stderr
        assert not receipt.exists(), "refused invocation reached the launcher"
        return
    assert result.returncode == exit_code, result.stderr
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
        "--repo",
        str(checkout.resolve()),
        *(["--os", platform] if platform else []),
        "--",
        "env",
        "-u",
        "KAILASH_TRESTLE_TESTS",
        "-u",
        "PYTHONPATH",
        "-u",
        "PYTHONHOME",
        "-u",
        "VIRTUAL_ENV",
        "-u",
        "UV_PROJECT_ENVIRONMENT",
        "UV_LINK_MODE=copy",
        "uv",
        "run",
        "--project",
        ".",
        "--frozen",
        *(["--python", python] if python else []),
        *[argument for extra in expected_extras for argument in ("--extra", extra)],
        "python",
        *arguments,
    ]


@pytest.mark.regression
def test_trestle_python_routing_refuses_missing_checkout(tmp_path):
    """Fleet routing must not dispatch tests outside a Git checkout."""
    import subprocess

    environment = _isolated_routing_environment()
    environment["KAILASH_TRESTLE_TESTS"] = "1"
    result = subprocess.run(
        [str(REPO_ROOT / "scripts/development/find-venv-python.sh"), "-m", "pytest"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64
    assert "not inside a git repository" in result.stderr
