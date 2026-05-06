"""Tier-1 regression tests for ``dataflow.utils.filenames``.

Origin: 2026-05-06 — ``Mock(name="X")`` does NOT set ``Mock.name``;
accessing ``.name`` returns a child Mock whose ``__str__`` is
``<Mock name='X.name' id='...'>``. ``generate.py:156`` interpolated
this into a real filename, leaking 108 orphan files into ``docs/``
across the repo. ``safe_workflow_filename`` is the structural
defense; this suite pins its allowlist + reject behavior so a
future loosening of the regex re-opens the leak loudly.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from dataflow.utils.filenames import WorkflowNameError, safe_workflow_filename


class TestSafeWorkflowFilenameAccepts:
    """Names that MUST be accepted (sample of the production allowlist)."""

    @pytest.mark.parametrize(
        "name,ext,expected",
        [
            ("test_workflow", "md", "test_workflow.md"),
            ("a", "md", "a.md"),
            ("My_Workflow_2026", "md", "My_Workflow_2026.md"),
            ("workflow-v1.2.3", "md", "workflow-v1.2.3.md"),
            ("_underscore_first", "md", "_underscore_first.md"),
            ("digits_123", "md", "digits_123.md"),
            ("X" * 128, "md", "X" * 128 + ".md"),  # exactly 128 chars
            ("workflow", "json", "workflow.json"),
            ("workflow", "html", "workflow.html"),
        ],
    )
    def test_accepts_valid(self, name, ext, expected):
        assert safe_workflow_filename(name, ext) == expected


class TestSafeWorkflowFilenameRejects:
    """Names that MUST be rejected (the historical leak vectors + injection vectors)."""

    @pytest.mark.parametrize(
        "bad_name,why",
        [
            ("", "empty string"),
            (" ", "whitespace only"),
            (".", "single dot (current dir)"),
            ("..", "double dot (parent dir / path traversal)"),
            (".hidden", "leading dot (hidden file)"),
            ("-leading-hyphen", "leading hyphen (looks like CLI flag)"),
            ("name with space", "embedded space"),
            ("name/slash", "POSIX path separator"),
            ("name\\backslash", "Windows path separator"),
            ("../etc/passwd", "explicit path traversal"),
            ("foo..bar", "embedded path-traversal substring"),
            ("name\x00null", "null byte injection"),
            ("name\nnewline", "control char (newline)"),
            ("name\ttab", "control char (tab)"),
            ("name@symbol", "shell-metachar @"),
            ("name;semicolon", "shell-metachar ;"),
            ("name|pipe", "shell-metachar |"),
            ("name`backtick`", "shell-metachar backtick"),
            ("name$variable", "shell-metachar $"),
            ("X" * 129, "exceeds 128-char length cap"),
            ("X" * 1000, "extreme length"),
            ("‮" + "rtl_override", "Unicode bidi-override"),
            ("résumé", "Unicode letters (allowlist is ASCII-only)"),
        ],
    )
    def test_rejects_unsafe_strings(self, bad_name, why):
        with pytest.raises(WorkflowNameError, match=r"workflow name"):
            safe_workflow_filename(bad_name, "md")
        # `why` is consumed in the failure message via parametrize id;
        # binding it here keeps it accessible to debuggers + linters.
        assert isinstance(why, str)

    @pytest.mark.parametrize(
        "bad_input",
        [
            None,
            123,
            12.5,
            ["test_workflow"],
            {"name": "test_workflow"},
            object(),
        ],
    )
    def test_rejects_non_string(self, bad_input):
        with pytest.raises(WorkflowNameError):
            safe_workflow_filename(bad_input, "md")

    def test_rejects_mock_object_directly(self):
        """Regression for the originating leak (2026-05-06).

        ``Mock(name="test_workflow")`` does NOT set ``Mock.name``; accessing
        ``.name`` returns a child Mock that f-strings to
        ``<Mock name='test_workflow.name' id='...'>``. The helper MUST
        reject the child Mock, NOT silently produce a Mock-repr filename.
        """
        mock = Mock(name="test_workflow")
        with pytest.raises(WorkflowNameError):
            safe_workflow_filename(mock.name, "md")

    def test_accepts_mock_with_name_set_correctly(self):
        """Sanity: the CORRECT Mock-construction pattern (post-assignment) works."""
        mock = Mock()
        mock.name = "test_workflow"
        assert safe_workflow_filename(mock.name, "md") == "test_workflow.md"


class TestSafeWorkflowFilenameExtension:
    """Extension MUST also be validated (defense-in-depth)."""

    @pytest.mark.parametrize(
        "bad_ext",
        [
            "",
            ".md",  # leading dot is the API contract violation
            "md.",
            "md/sub",
            "md\\sub",
            "md with space",
            "x" * 17,  # exceeds 16-char cap
            None,
            123,
        ],
    )
    def test_rejects_bad_extension(self, bad_ext):
        with pytest.raises(WorkflowNameError):
            safe_workflow_filename("workflow", bad_ext)


class TestSafeWorkflowFilenameErrorMessage:
    """Error messages MUST NOT echo raw input (log-poisoning defense)."""

    def test_error_message_does_not_echo_raw_input(self):
        """Per ``observability.md`` Rule 8 + ``security.md`` § Output Encoding,
        the message carries a hashed fingerprint, NOT the raw input."""
        sentinel = "INJECTION_PAYLOAD_d8f7e6a5b4c3"
        try:
            safe_workflow_filename(sentinel + "/etc/passwd", "md")
        except WorkflowNameError as exc:
            assert sentinel not in str(
                exc
            ), f"WorkflowNameError leaked raw input into message: {exc!r}"
        else:
            pytest.fail("expected WorkflowNameError")

    def test_error_message_includes_actionable_mock_hint_for_non_string(self):
        """When called with a non-string, the message MUST hint at the
        Mock(name=) anti-pattern (the originating cause of this rule)."""
        mock = Mock(name="test_workflow")
        try:
            safe_workflow_filename(mock.name, "md")
        except WorkflowNameError as exc:
            msg = str(exc)
            assert (
                "Mock" in msg and "post-construction" in msg
            ), f"expected Mock-anti-pattern hint, got: {msg!r}"
        else:
            pytest.fail("expected WorkflowNameError")


class TestSafeWorkflowFilenameLogging:
    """Logging contract: WARN with hashed fingerprint, never raw input."""

    def test_logs_warn_with_fingerprint_on_invalid(self, caplog):
        """Per observability.md Rule 8 — WARN logs schema-revealing data
        as hashed fingerprints, never the raw input."""
        import logging

        caplog.set_level(logging.WARNING, logger="dataflow.utils.filenames")
        sentinel = "RAW_INPUT_SENTINEL_5e8a3f"
        with pytest.raises(WorkflowNameError):
            safe_workflow_filename(sentinel + "/x", "md")

        assert any(
            "filename.invalid_workflow_name" in r.message for r in caplog.records
        ), "expected structured warn log"
        # Critical: no log line carries the raw sentinel.
        for record in caplog.records:
            assert (
                sentinel not in record.getMessage()
            ), f"raw input leaked into log: {record.getMessage()!r}"
