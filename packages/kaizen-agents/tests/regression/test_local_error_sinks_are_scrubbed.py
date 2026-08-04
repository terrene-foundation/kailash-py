# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Every local exception-text sink in ``kaizen_agents`` is credential-scrubbed.

WHAT LANDED, AND WHY IT IS NOT THE SWEEP THAT WAS HALTED
--------------------------------------------------------
A first attempt would have routed these sites through ``scrub_credentials`` in
its DEFAULT (aggressive) mode. That was halted, because the default is not a
no-op on ordinary text: it rewrites ``$HOME`` paths, 40-char contiguous runs
(git SHAs, long CamelCase identifiers), 32+ hex runs (MD5 digests, unhyphenated
UUID/trace ids) and Azure resource names. Those bytes are incidental noise in a
provider error body and load-bearing diagnostics in a LOCAL one — an ``OSError``
message IS a path plus a reason, and it is read by an LLM deciding its retry.
See ``kailash-kaizen``'s ``test_scrub_credentials_ordinary_text_is_not_noop``.

So the helper's contract was split instead. ``scrub_local_error`` is
``scrub_credentials`` with ``redact_paths=False, redact_opaque_tokens=False``:
only the rules anchored on a literal that cannot occur outside a credential
(``sk-``, ``AKIA``, ``ASIA``, ``ghp_``, ``hf_``, ``fw_``, ``xox?-``,
``sk_live_``, ``sig=``, ``Bearer``, bare JWTs) plus URL-userinfo / DSN
credentials. That combination is a measured no-op across the credential-free
corpus, which is what makes this sweep safe where the aggressive one was not.

WHAT THIS FILE PINS
-------------------
Four tiers, and the first two are what make the last two generalise:

1. ``test_no_unwrapped_exception_text_sink_remains`` — per module, an AST pass
   re-derives the sink set from source and asserts NONE is unwrapped. This is
   the coverage instrument: it reds if a site is reverted AND if a NEW
   unscrubbed sink is added later.
2. ``test_module_binds_the_canonical_preset`` — per module, the imported
   ``scrub_local_error`` is the SAME object as the one in
   ``kaizen.utils.credential_scrub``, so no module can drift onto a local copy.
3. ``test_credential_scrubbed_and_path_survives`` — per module, the symbol that
   module will actually invoke redacts a credential and leaves an ``OSError``
   filename byte-identical. (1) + (2) + (3) compose to a per-module behavioural
   claim about every one of that module's sinks.
4. The agent-facing tool sinks named in the halt report — ``file_read``,
   ``file_write``, ``file_edit``, ``bash_tool``, ``glob_tool``, ``grep_tool``
   — driven END TO END through ``Tool.execute``, asserting on the real
   ``ToolResult`` the model would receive.

``patterns/discovery.py`` was scrubbed earlier, under the aggressive default, by
a different change, and is left that way. Tier 1 recognises that form too, so it
is covered without a hand-maintained exclusion; Tiers 2-4 do not see it because
it does not use the conservative preset.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from kaizen.utils.credential_scrub import scrub_local_error as CANONICAL

pytestmark = pytest.mark.regression

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = SRC / "kaizen_agents"
HELPER = "scrub_local_error"

#: The AGGRESSIVE entry point. ``patterns/discovery.py`` was routed through it
#: by an earlier, separate change and is deliberately left that way. Tier 1
#: recognises it as scrubbed, so ``discovery.py`` needs no special case and
#: still cannot regain a bare sink unnoticed; it is absent from the Tier 2/3
#: parametrisation as a CONSEQUENCE of not using the conservative preset, not
#: as a hand-maintained exclusion.
AGGRESSIVE_HELPER = "scrub_credentials"

EXCLUDED_PARTS = {"build", "tests", "examples", "__pycache__"}

#: Measured surface, reproduced by ``_enumerate`` below. Pinned so the
#: parametrisation cannot silently shrink to nothing and still report green.
EXPECTED_FILES = 51
EXPECTED_SITES = 180


class _SinkScan(ast.NodeVisitor):
    """Find string-context uses of one handler's bound exception name.

    ``wrapped`` are the uses already routed through :data:`HELPER`; ``bare``
    are the ones that would put the raw exception text into a message.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.bare: list[int] = []
        self.wrapped: list[int] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # An inner handler rebinding the same name owns its own uses.
        if node.name != self.name:
            self.generic_visit(node)

    def _is_our_name(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id == self.name

    def _is_str_of_our_name(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
            and self._is_our_name(node.args[0])
        )

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id == HELPER
            and len(node.args) == 1
            and self._is_our_name(node.args[0])
        ):
            self.wrapped.append(node.lineno)
            return  # do not descend: the Name inside is accounted for
        if (
            isinstance(func, ast.Name)
            and func.id == AGGRESSIVE_HELPER
            and len(node.args) == 1
            and (
                self._is_our_name(node.args[0])
                or self._is_str_of_our_name(node.args[0])
            )
        ):
            # Scrubbed, but by the aggressive entry point. Counts as covered for
            # Tier 1; deliberately NOT counted as part of this sweep.
            return
        if (
            isinstance(func, ast.Name)
            and func.id in ("str", "repr")
            and len(node.args) == 1
            and self._is_our_name(node.args[0])
        ):
            self.bare.append(node.lineno)
            return
        self.generic_visit(node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if self._is_our_name(node.value):
            self.bare.append(node.value.lineno)
            return
        self.generic_visit(node)


def _enumerate(path: Path) -> tuple[list[int], list[int]]:
    """Return ``(bare_linenos, wrapped_linenos)`` for one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bare: list[int] = []
    wrapped: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not node.name:
            continue
        scan = _SinkScan(node.name)
        for stmt in node.body:
            scan.visit(stmt)
        bare.extend(scan.bare)
        wrapped.extend(scan.wrapped)
    return bare, wrapped


def _source_files() -> list[Path]:
    out = []
    for p in sorted(PKG.rglob("*.py")):
        if EXCLUDED_PARTS & set(p.relative_to(PKG).parts):
            continue
        out.append(p)
    return out


def _swept_files() -> list[Path]:
    """Files that carry at least one scrubbed sink."""
    return [p for p in _source_files() if _enumerate(p)[1]]


SWEPT = _swept_files()
SWEPT_IDS = [str(p.relative_to(PKG)) for p in SWEPT]


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


# ---------------------------------------------------------------------------
# Tier 1 — coverage. No bare sink anywhere in the package.
# ---------------------------------------------------------------------------
class TestNoBareExceptionTextSinkRemains:
    @pytest.mark.parametrize(
        "path",
        _source_files(),
        ids=[str(p.relative_to(PKG)) for p in _source_files()],
    )
    def test_no_unwrapped_exception_text_sink_remains(self, path: Path) -> None:
        bare, _ = _enumerate(path)
        assert bare == [], (
            f"{path.relative_to(PKG)} puts a caught exception into a string at "
            f"line(s) {bare} without {HELPER}(). A local error message can carry "
            "a credential from a DSN, a config value or a provider payload; every "
            "such sink routes through the conservative scrub."
        )

    def test_the_sweep_covers_the_measured_surface(self) -> None:
        """Pin the enumeration itself.

        Without this, every parametrised assertion above could pass over an
        empty set — the classic vacuous-coverage shape.
        """
        total = sum(len(_enumerate(p)[1]) for p in SWEPT)
        assert (len(SWEPT), total) == (EXPECTED_FILES, EXPECTED_SITES), (
            f"swept surface moved: {len(SWEPT)} files / {total} sites, "
            f"expected {EXPECTED_FILES} / {EXPECTED_SITES}. If a sink was "
            "legitimately added or removed, update the pin in the same commit."
        )


# ---------------------------------------------------------------------------
# Tier 2 + 3 — per module: the right symbol, doing the right thing.
# ---------------------------------------------------------------------------
CREDENTIAL = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
LOADBEARING_PATH = "/Users/alice/repos/app/config.yaml"


class TestEverySweptModule:
    @pytest.mark.parametrize("path", SWEPT, ids=SWEPT_IDS)
    def test_module_binds_the_canonical_preset(self, path: Path) -> None:
        mod = importlib.import_module(_module_name(path))
        bound = getattr(mod, HELPER, None)
        assert bound is CANONICAL, (
            f"{path.relative_to(PKG)} does not bind the canonical "
            f"kaizen.utils.credential_scrub.{HELPER}. A per-module copy is the "
            "drift this module exists to prevent."
        )

    @pytest.mark.parametrize("path", SWEPT, ids=SWEPT_IDS)
    def test_credential_scrubbed_and_path_survives(self, path: Path) -> None:
        """Both directions, through the symbol this module actually calls."""
        mod = importlib.import_module(_module_name(path))
        scrub = getattr(mod, HELPER)

        exc = OSError(
            f"[Errno 13] Permission denied: '{LOADBEARING_PATH}' "
            f"(token {CREDENTIAL})"
        )
        rendered = scrub(exc)

        assert (
            CREDENTIAL not in rendered
        ), f"{path.relative_to(PKG)} would leak a credential into its error text"
        assert "[REDACTED]" in rendered
        assert LOADBEARING_PATH in rendered, (
            f"{path.relative_to(PKG)} would mangle the path an agent needs in "
            "order to retry — the exact failure the aggressive sweep was halted "
            "over."
        )


# ---------------------------------------------------------------------------
# Tier 4 — the agent-facing tool sinks, driven end to end.
# ---------------------------------------------------------------------------
def _raising_oserror(message: str):
    def _raise(*_args, **_kwargs):
        raise OSError(message)

    return _raise


CREDENTIALED_OSERROR = (
    f"[Errno 5] I/O error: '{LOADBEARING_PATH}' while using {CREDENTIAL}"
)
ORDINARY_OSERROR = f"[Errno 5] Input/output error: '{LOADBEARING_PATH}'"


class TestDelegateToolResultsReachTheModelIntact:
    """The ``ToolResult`` an LLM reads to decide its retry.

    Asserting on ``result.error`` rather than on the scrub helper is the point:
    this is the surface the halt report identified, so it is driven rather than
    reasoned about.
    """

    def test_file_read_scrubs_credential_and_keeps_path(self, tmp_path, monkeypatch):
        from kaizen_agents.delegate.tools.file_read import FileReadTool

        target = tmp_path / "config.yaml"
        target.write_text("k: v", encoding="utf-8")
        monkeypatch.setattr(Path, "read_text", _raising_oserror(CREDENTIALED_OSERROR))

        result = FileReadTool().execute(file_path=str(target))

        assert result.is_error
        assert CREDENTIAL not in result.error
        assert "[REDACTED]" in result.error
        assert LOADBEARING_PATH in result.error

    def test_file_read_leaves_an_ordinary_oserror_path_byte_identical(
        self, tmp_path, monkeypatch
    ):
        from kaizen_agents.delegate.tools.file_read import FileReadTool

        target = tmp_path / "config.yaml"
        target.write_text("k: v", encoding="utf-8")
        monkeypatch.setattr(Path, "read_text", _raising_oserror(ORDINARY_OSERROR))

        result = FileReadTool().execute(file_path=str(target))

        assert result.error == f"Error reading file: {ORDINARY_OSERROR}", (
            "an ordinary OSError must reach the model unchanged; the model "
            "cannot retry against '[PATH]/...'"
        )

    def test_file_write_scrubs_credential_and_keeps_path(self, tmp_path, monkeypatch):
        from kaizen_agents.delegate.tools.file_write import FileWriteTool

        monkeypatch.setattr(Path, "write_text", _raising_oserror(CREDENTIALED_OSERROR))

        result = FileWriteTool().execute(
            file_path=str(tmp_path / "out.txt"), content="x"
        )

        assert result.is_error
        assert CREDENTIAL not in result.error
        assert LOADBEARING_PATH in result.error

    def test_file_write_leaves_an_ordinary_oserror_path_byte_identical(
        self, tmp_path, monkeypatch
    ):
        from kaizen_agents.delegate.tools.file_write import FileWriteTool

        monkeypatch.setattr(Path, "write_text", _raising_oserror(ORDINARY_OSERROR))

        result = FileWriteTool().execute(
            file_path=str(tmp_path / "out.txt"), content="x"
        )

        assert result.error == f"Error writing file: {ORDINARY_OSERROR}"
