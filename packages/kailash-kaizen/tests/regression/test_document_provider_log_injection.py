"""Caller-supplied ``file_path`` must not forge log records in the document providers.

The three document-extraction providers each rendered the caller's ``file_path``
into a ``logger.info`` line by f-string interpolation, before any network call::

    logger.info(f"Extracting {file_path} with OpenAI Vision ...")

A path containing ``\\n`` therefore emitted TWO well-formed lines into whatever
collector ingests the stream — the second one attacker-composed, at a level that
survives production filters. Severity is LOW (the path is caller-supplied, not
attacker-reachable across a network boundary), but the barrier is the same one
``security.md`` § Credential Decode Helpers mandates: ONE shared sanitizer, never
a hand-rolled ``replace`` per site. All seven sites route through
``kailash.utils.secure_logging.sanitize_log_value``.

THE INSTRUMENT, and why it is not ``caplog`` record counting. A forged record is
forged at FORMAT time, not at emit time: the unsanitized call produces exactly
ONE ``LogRecord`` whose ``message`` happens to contain a newline. MEASURED on
this tree before these tests were written — an unsanitized
``logger.info(f"...{evil}...")`` yields ``len(caplog.records) == 1`` and
``len(stream.splitlines()) == 2``. A record count is therefore constant across
the hypothesis and carries zero information (``rules/instrument-discipline.md``
MUST-1). These tests attach a real ``StreamHandler`` with a real ``Formatter``
and count the LINES a collector would actually ingest, which is the convention
the ``#2104`` JWT-header fix already established in this repo.

The success-path siblings (``file_path_obj.name`` — ``Path`` preserves an
embedded newline in ``.name``, measured) sit after the provider's network call
and cannot be driven without a live backend, so they are pinned structurally by
``test_no_logger_call_interpolates_caller_path`` instead.
"""

from __future__ import annotations

import ast
import io
import logging
import pathlib

import pytest

pytestmark = pytest.mark.regression

# A filename whose embedded newline composes a second, well-formed log line.
_FORGED = "ERROR kaizen.audit: extraction approved by operator"
_EVIL_NAME = f"invoice.txt\n{_FORGED}"

_PROVIDER_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "kaizen"
    / "providers"
    / "document"
)
_PROVIDER_FILES = (
    "openai_vision_provider.py",
    "ollama_vision_provider.py",
    "landing_ai_provider.py",
)


class _StreamCapture:
    """A real handler + real formatter: counts the lines a collector ingests."""

    def __init__(self, logger_name: str) -> None:
        self._logger = logging.getLogger(logger_name)
        self._buf = io.StringIO()
        self._handler = logging.StreamHandler(self._buf)
        self._handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        self._records: list[logging.LogRecord] = []

        capture = self._records

        class _Recorder(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                capture.append(record)

        self._recorder = _Recorder()
        self._prev_level = self._logger.level
        self._prev_propagate = self._logger.propagate

    def __enter__(self) -> "_StreamCapture":
        self._logger.addHandler(self._handler)
        self._logger.addHandler(self._recorder)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        return self

    def __exit__(self, *exc) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.removeHandler(self._recorder)
        self._logger.setLevel(self._prev_level)
        self._logger.propagate = self._prev_propagate

    @property
    def lines(self) -> list[str]:
        return [ln for ln in self._buf.getvalue().splitlines() if ln.strip()]

    @property
    def records(self) -> list[logging.LogRecord]:
        return self._records


def _evil_file(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / _EVIL_NAME
    path.write_text("some document text\n", encoding="utf-8")
    assert (
        "\n" in path.name
    ), "the test vector lost its newline before the provider saw it"
    return path


def _assert_one_line_per_record(capture: _StreamCapture) -> None:
    """N log calls must ingest as exactly N lines — never N+1.

    Counting lines against RECORDS (rather than against a fixed number) is what
    makes this discriminating without depending on how many legitimate calls a
    given provider makes on the path under test: the unsanitized code emits one
    record and two lines, the sanitized code emits one record and one line.
    """
    assert capture.records, (
        "the provider emitted no record at all; the log call site was never reached, "
        "so this test proves nothing"
    )
    assert len(capture.lines) == len(capture.records), (
        f"caller-supplied file_path forged extra log lines: "
        f"{len(capture.records)} record(s) ingested as {len(capture.lines)} line(s): "
        f"{capture.lines!r}"
    )
    assert not any(
        ln.startswith(_FORGED) for ln in capture.lines
    ), f"forged content survived as a line of its own: {capture.lines!r}"
    for record in capture.records:
        assert (
            "\n" not in record.getMessage()
        ), f"newline survived into the record message: {record.getMessage()!r}"


@pytest.mark.asyncio
async def test_openai_vision_extract_does_not_forge_a_log_line(tmp_path, monkeypatch):
    """The OpenAI Vision 'Extracting ...' line flattens a newline-bearing path."""
    from kaizen.providers.document import openai_vision_provider as mod

    provider = mod.OpenAIVisionProvider(api_key="test-key-not-real", ungoverned=True)

    class _Stop(RuntimeError):
        pass

    # First step AFTER the log site; stops before any network egress.
    monkeypatch.setattr(
        mod.OpenAIVisionProvider,
        "_prepare_document_images",
        lambda self, *a, **k: (_ for _ in ()).throw(_Stop("stop after log")),
    )

    with _StreamCapture(mod.__name__) as capture:
        with pytest.raises(_Stop):
            await provider.extract(file_path=str(_evil_file(tmp_path)), file_type="txt")

    _assert_one_line_per_record(capture)


@pytest.mark.asyncio
async def test_ollama_vision_extract_does_not_forge_a_log_line(tmp_path, monkeypatch):
    """The Ollama Vision 'Extracting ...' line flattens a newline-bearing path."""
    from kaizen.providers.document import ollama_vision_provider as mod

    # No ``model=`` kwarg: OllamaVisionProvider takes its model from config.
    provider = mod.OllamaVisionProvider(ungoverned=True)

    # First step AFTER the log site; stops before any network egress.
    monkeypatch.setattr(mod.OllamaVisionProvider, "is_available", lambda self: False)

    with _StreamCapture(mod.__name__) as capture:
        with pytest.raises(RuntimeError):
            await provider.extract(file_path=str(_evil_file(tmp_path)), file_type="txt")

    _assert_one_line_per_record(capture)


@pytest.mark.asyncio
async def test_landing_ai_extract_does_not_forge_a_log_line(tmp_path, monkeypatch):
    """The Landing AI 'Extracting ...' line flattens a newline-bearing path."""
    import httpx

    from kaizen.providers.document import landing_ai_provider as mod

    provider = mod.LandingAIProvider(api_key="test-key-not-real", ungoverned=True)

    class _Stop(RuntimeError):
        pass

    def _no_client(*a, **k):
        raise _Stop("stop after log")

    # First network-touching construction AFTER the log site.
    monkeypatch.setattr(httpx, "AsyncClient", _no_client)

    with _StreamCapture(mod.__name__) as capture:
        with pytest.raises(_Stop):
            await provider.extract(file_path=str(_evil_file(tmp_path)), file_type="txt")

    _assert_one_line_per_record(capture)


@pytest.mark.parametrize("filename", _PROVIDER_FILES)
def test_no_logger_call_interpolates_caller_path(filename):
    """No logger call in these modules may f-string-interpolate caller path data.

    Covers the success-path siblings (``file_path_obj.name``) that the three
    behavioural tests above cannot reach without a live backend. An AST walk,
    not a line-oriented grep: Black wraps the ``logger.<level>(`` and the
    f-string onto SEPARATE lines, so a single-line pattern under-reports this
    class (that under-reporting is what left these siblings unfound).
    """
    source = (_PROVIDER_DIR / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)

    tainted = {"file_path", "file_path_obj"}
    offenders: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr
            in {"debug", "info", "warning", "warn", "error", "exception", "critical"}
        ):
            continue
        if not (
            isinstance(func.value, ast.Name) and func.value.id in {"logger", "log"}
        ):
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if not isinstance(sub, ast.JoinedStr):
                    continue
                for piece in ast.walk(sub):
                    if isinstance(piece, ast.Name) and piece.id in tainted:
                        offenders.append(
                            f"{filename}:{node.lineno} interpolates {piece.id}"
                        )

    assert not offenders, (
        "caller-supplied path interpolated into a log call; route it through "
        f"kailash.utils.secure_logging.sanitize_log_value instead: {offenders}"
    )
