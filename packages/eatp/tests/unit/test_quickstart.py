"""
Unit tests for EATP CLI quickstart module.

Tests the interactive quickstart demo that demonstrates all 4 EATP operations
(ESTABLISH, VERIFY, DELEGATE, AUDIT) in a single function.

Tests cover:
- run_quickstart() completes without errors
- Output contains all 4 EATP operations
- Output includes trust score
- Output includes next-step commands
- verbose mode produces additional output
- main() entry point works for `python -m eatp.cli.quickstart`
- Deterministic output structure (same steps every run)
- Dashboard renders within 80-column width
"""

import asyncio
import io
import re
import sys
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_output():
    """Capture stdout for testing print output."""
    buffer = io.StringIO()
    return buffer


# ---------------------------------------------------------------------------
# Core Function Tests
# ---------------------------------------------------------------------------


class TestRunQuickstart:
    """Tests for run_quickstart() async function."""

    @pytest.mark.asyncio
    async def test_quickstart_completes_without_error(self):
        """run_quickstart() must complete without raising any exception."""
        from eatp.cli.quickstart import run_quickstart

        # Should not raise
        await run_quickstart(verbose=False)

    @pytest.mark.asyncio
    async def test_quickstart_verbose_completes_without_error(self):
        """run_quickstart(verbose=True) must complete without raising."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=True)

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_establish(self, capsys):
        """Quickstart output must show the ESTABLISH operation."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        assert "ESTABLISH" in captured.out

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_verify(self, capsys):
        """Quickstart output must show the VERIFY operation."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        assert "VERIFY" in captured.out

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_delegate(self, capsys):
        """Quickstart output must show the DELEGATE operation."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        assert "DELEGATE" in captured.out

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_audit(self, capsys):
        """Quickstart output must show the AUDIT operation."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        assert "AUDIT" in captured.out

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_trust_score(self, capsys):
        """Quickstart output must display trust score information."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # Must contain either "Trust Score" or "trust score" or the numeric score
        assert "Trust Score" in captured.out or "trust score" in captured.out.lower()

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_auto_approved(self, capsys):
        """Quickstart must show AUTO_APPROVED verdict during VERIFY."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # Verification of a directly established agent should be approved
        assert "APPROVED" in captured.out.upper() or "VERIFIED" in captured.out.upper()

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_agent_names(self, capsys):
        """Quickstart must reference concrete agent names in the output."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # The quickstart demo should have at least two agents
        # (one established, one delegated)
        output_lower = captured.out.lower()
        assert "agent" in output_lower

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_next_steps(self, capsys):
        """Quickstart must show actionable next-step commands."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # Must contain at least one eatp CLI command as a next step
        assert "eatp" in captured.out

    @pytest.mark.asyncio
    async def test_quickstart_output_contains_authority(self, capsys):
        """Quickstart must reference the authority that was created."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        output_lower = captured.out.lower()
        assert "authority" in output_lower

    @pytest.mark.asyncio
    async def test_quickstart_verbose_has_more_output(self, capsys):
        """Verbose mode must produce more output than non-verbose."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        normal_output = capsys.readouterr().out

        await run_quickstart(verbose=True)
        verbose_output = capsys.readouterr().out

        assert len(verbose_output) > len(normal_output)

    @pytest.mark.asyncio
    async def test_quickstart_deterministic_structure(self, capsys):
        """Two runs must produce the same output structure (same step headings)."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        output1 = capsys.readouterr().out

        await run_quickstart(verbose=False)
        output2 = capsys.readouterr().out

        # Extract step headings (lines starting with step markers)
        # Both runs should have the same numbered steps
        step_pattern = re.compile(r"(?:Step \d|STEP \d|\[\d\]|#\d)")
        steps1 = step_pattern.findall(output1)
        steps2 = step_pattern.findall(output2)
        assert steps1 == steps2
        assert len(steps1) >= 4  # At least 4 steps (one per operation)

    @pytest.mark.asyncio
    async def test_quickstart_fits_80_columns(self, capsys):
        """All output lines must fit within 80 columns."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()

        for line_num, line in enumerate(captured.out.splitlines(), 1):
            # Strip ANSI escape codes before measuring length
            clean_line = re.sub(r"\033\[[0-9;]*m", "", line)
            assert len(clean_line) <= 80, (
                f"Line {line_num} exceeds 80 columns ({len(clean_line)} chars): "
                f"{clean_line!r}"
            )

    @pytest.mark.asyncio
    async def test_quickstart_shows_delegation_constraints(self, capsys):
        """Quickstart must show that delegated agent has tightened constraints."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        output_lower = captured.out.lower()
        assert "constraint" in output_lower

    @pytest.mark.asyncio
    async def test_quickstart_shows_delegation_chain(self, capsys):
        """Quickstart must show delegation from one agent to another."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # Should show "agent-1" -> "agent-2" or similar delegation notation
        assert "->" in captured.out or "to" in captured.out.lower()


# ---------------------------------------------------------------------------
# Entry Point Tests
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the __main__ entry point."""

    def test_main_function_exists(self):
        """The module must have a callable main() function."""
        from eatp.cli.quickstart import main

        assert callable(main)

    def test_main_runs_without_error(self):
        """main() must complete without raising."""
        from eatp.cli.quickstart import main

        # main() wraps run_quickstart in asyncio.run
        main()

    def test_module_runnable_as_script(self):
        """python -m eatp.cli.quickstart must be runnable."""
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "eatp.cli.quickstart"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd="packages/eatp",
        )
        assert result.returncode == 0, (
            f"Module execution failed with returncode {result.returncode}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "ESTABLISH" in result.stdout


# ---------------------------------------------------------------------------
# ANSI Color Tests
# ---------------------------------------------------------------------------


class TestAnsiColors:
    """Tests for ANSI color usage."""

    @pytest.mark.asyncio
    async def test_output_contains_ansi_codes(self, capsys):
        """Quickstart output must include ANSI color escape sequences."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # Check for any ANSI escape sequence
        assert "\033[" in captured.out

    @pytest.mark.asyncio
    async def test_output_resets_ansi_at_end(self, capsys):
        """Output must reset ANSI codes so terminal is clean after."""
        from eatp.cli.quickstart import run_quickstart

        await run_quickstart(verbose=False)
        captured = capsys.readouterr()
        # The reset code is \033[0m
        assert "\033[0m" in captured.out
