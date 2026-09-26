"""Canonical path boundaries and framework-derived diagnostics preserve privacy."""

import io
import json
import logging
import tempfile
from pathlib import Path

import pytest

from kailash import security
from kailash.nodes.mixins.security import LoggingMixin

pytestmark = pytest.mark.regression
PRIVATE = "sibling.synthetic@example.invalid"


@pytest.fixture
def capture():
    stream = io.StringIO()
    records = []

    class Capture(logging.StreamHandler):
        def emit(self, record):
            records.append(dict(record.__dict__))
            super().emit(record)

    handler = Capture(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    loggers = [security.logger, logging.getLogger("LoggingMixin")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    try:
        yield stream, records
    finally:
        for logger, level in zip(loggers, levels):
            logger.removeHandler(handler)
            logger.setLevel(level)


def assert_private(capture, event):
    stream, records = capture
    assert records, "the diagnostic must still be emitted"
    assert event in stream.getvalue()
    assert PRIVATE not in stream.getvalue()
    assert PRIVATE not in json.dumps(records, default=str)
    assert all(record["exc_info"] is None for record in records)


def config(root):
    return security.SecurityConfig(allowed_directories=[str(root)])


def test_sources_are_from_this_checkout():
    root = Path(__file__).resolve().parents[2]
    assert Path(security.__file__).resolve() == root / "src/kailash/security.py"
    assert Path(LoggingMixin.log_error.__code__.co_filename).resolve() == (
        root / "src/kailash/nodes/mixins/security.py"
    )


def test_allowed_existing_and_new_paths_keep_real_read_write_behavior(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    output = root / "new" / "record.txt"
    with security.safe_open(output, "w", config(root)) as handle:
        handle.write("retained data")
    with security.safe_open(output, "r", config(root)) as handle:
        assert handle.read() == "retained data"
    assert security.validate_file_path(output, config(root)) == output.resolve()
    # Configuring a new output directory remains supported.
    new_root = tmp_path / "new-root"
    with security.safe_open(new_root / "new.txt", "w", config(new_root)) as handle:
        handle.write("new root")
    assert (new_root / "new.txt").read_text() == "new root"


@pytest.mark.parametrize("mode", ["r", "w"])
def test_sibling_prefix_cannot_escape_allowlist(tmp_path, mode):
    root = tmp_path / "allowed"
    sibling = tmp_path / "allowed-private"
    root.mkdir()
    sibling.mkdir()
    outside = sibling / "record.txt"
    outside.write_text("unchanged")
    with pytest.raises(security.SecurityError, match="outside allowed directories"):
        with security.safe_open(outside, mode, config(root)):
            pass
    assert outside.read_text() == "unchanged"


def test_symlinked_root_and_internal_target_are_resolved_together(tmp_path):
    root = tmp_path / "physical"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    internal = root / "target.txt"
    internal.write_text("inside")
    link = root / "link.txt"
    link.symlink_to(internal)
    assert security.validate_file_path(link, config(alias)) == internal.resolve()
    with security.safe_open(alias / "fresh.txt", "w", config(alias)) as handle:
        handle.write("written")
    assert (root / "fresh.txt").read_text() == "written"


def test_sensitive_roots_use_canonical_component_boundaries(tmp_path):
    alias = tmp_path / "sensitive-alias"
    alias.symlink_to(Path("/etc"), target_is_directory=True)
    broad = config(Path("/"))
    for path in (Path("/etc"), alias, Path("/var/privacy-outside-temp/record.txt")):
        with pytest.raises(security.PathTraversalError):
            security.validate_file_path(path, broad)
    # A lexical prefix is not a filesystem parent.
    assert security.validate_file_path("/variety/record.txt", broad) == (
        Path("/variety/record.txt").resolve()
    )


def test_system_temp_exception_still_requires_allowlist(tmp_path):
    system_temp = Path(tempfile.gettempdir())
    for root in (system_temp, Path("/var/tmp")):
        candidate = root / "privacy-output-not-created.txt"
        assert security.validate_file_path(candidate, config(root)) == (
            candidate.resolve()
        )
        with pytest.raises(security.SecurityError):
            security.validate_file_path(candidate, config(tmp_path / "other"))


@pytest.mark.parametrize("temp_root", ["/", "/var", "/etc"])
def test_temp_exception_cannot_exempt_protected_roots(monkeypatch, temp_root):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: temp_root)
    for candidate in ("/var/privacy-outside-temp/record.txt", "/etc/record.txt"):
        with pytest.raises(security.PathTraversalError):
            security.validate_file_path(candidate, config("/"))


@pytest.mark.parametrize("kind", ["escape", "dangling", "loop", "not_directory"])
def test_unresolvable_or_escaping_candidates_fail_closed(tmp_path, kind):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "record.txt").write_text("outside")
    link = root / "link"
    if kind == "escape":
        link.symlink_to(outside, target_is_directory=True)
        candidate = link / "record.txt"
    elif kind == "dangling":
        link.symlink_to(outside / "absent", target_is_directory=True)
        candidate = link / "record.txt"
    elif kind == "loop":
        link.symlink_to(link)
        candidate = link / "record.txt"
    else:
        link.write_text("not a directory")
        candidate = link / "record.txt"
    with pytest.raises(security.SecurityError):
        security.validate_file_path(candidate, config(root))
    assert (outside / "record.txt").read_text() == "outside"


def test_unresolvable_root_never_falls_back_to_lexical_prefix(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    target = root / "record.txt"
    target.write_text("inside")
    resolve = Path.resolve

    def reject_boundary(path, **kwargs):
        if path == root:
            raise PermissionError(PRIVATE)
        return resolve(path, **kwargs)

    monkeypatch.setattr(Path, "resolve", reject_boundary)
    with pytest.raises(security.SecurityError, match="Invalid file path"):
        security.validate_file_path(target, config(root))


@pytest.mark.parametrize("kind", ["outside", "traversal", "extension", "resolution"])
def test_rejected_path_logs_omit_values_but_keep_typed_errors(
    tmp_path, capture, kind, monkeypatch
):
    root = tmp_path / "allowed"
    root.mkdir()
    path = tmp_path / PRIVATE / "record.txt"
    expected = "Path outside allowed directories"
    error = security.SecurityError
    if kind == "traversal":
        path = root / ".." / PRIVATE / "record.txt"
        expected = "Path traversal attempt detected"
        error = security.PathTraversalError
    elif kind == "extension":
        path = root / ("record." + PRIVATE)
        expected = "File extension not allowed"
    elif kind == "resolution":

        def fail_resolution(*args, **kwargs):
            raise OSError(PRIVATE)

        monkeypatch.setattr(Path, "resolve", fail_resolution)
        expected = "Path validation error"
    with pytest.raises(error) as caught:
        security.validate_file_path(path, config(root))
    if kind == "extension":
        assert str(caught.value) == "File extension not allowed: .invalid"
    else:
        assert PRIVATE in str(caught.value)
    assert_private(capture, expected)


@pytest.mark.parametrize("operation", ["read", "write", "access", PRIVATE])
def test_operation_diagnostic_retains_only_known_categories(
    tmp_path, capture, operation
):
    output = tmp_path / "record.txt"
    assert (
        security.validate_file_path(output, config(tmp_path), operation)
        == output.resolve()
    )
    category = operation if operation != PRIVATE else "other"
    assert_private(capture, "File path validated: operation=" + category)
    assert capture[1][-1]["args"] == (category,)


def test_allowed_path_parameter_open_and_temp_logs_omit_values(tmp_path, capture):
    root = tmp_path / PRIVATE
    root.mkdir()
    output = root / "record.txt"
    cfg = config(root)
    with security.safe_open(output, "w", cfg) as handle:
        handle.write("retained")
    result = security.validate_node_parameters({"file_path": str(output)}, cfg)
    assert result["file_path"] == output.resolve()
    created = security.create_secure_temp_dir(prefix=PRIVATE, config=cfg)
    try:
        assert created.is_dir()
        assert created.stat().st_mode & 0o777 == 0o700
    finally:
        created.rmdir()
    assert_private(capture, "Opening validated file")
    assert "Node parameters validated: count=1" in capture[0].getvalue()
    assert "Created secure temp directory" in capture[0].getvalue()


@pytest.mark.parametrize("blocked", [False, True])
def test_command_diagnostics_omit_payload_without_changing_decision(capture, blocked):
    command = "echo " + PRIVATE + ("; whoami" if blocked else "")
    if blocked:
        with pytest.raises(security.CommandInjectionError) as caught:
            security.validate_command_string(command)
        assert str(caught.value) == "Potentially dangerous command: " + command
        expected = "Command injection attempt detected"
    else:
        assert security.validate_command_string(command) == command
        expected = "Command validated"
    assert_private(capture, expected)


def test_sanitizer_and_parameter_key_diagnostics_keep_results_not_values(capture):
    value = "<b>" + PRIVATE + "</b>"
    assert security.sanitize_input(value) == "b" + PRIVATE + "/b"
    assert security.validate_node_parameters({PRIVATE: "unchanged"}) == {
        PRIVATE: "unchanged"
    }
    assert_private(capture, "Input sanitized: length")


@pytest.mark.parametrize("traceback", [False, True])
def test_sync_error_diagnostics_keep_frames_not_exception_payload(capture, traceback):
    node = LoggingMixin()
    try:
        try:
            raise OSError("cause " + PRIVATE)
        except OSError as cause:
            raise ValueError("outer " + PRIVATE) from cause
    except ValueError as error:
        if traceback:
            node.log_error_with_traceback(error, "fixed operation")
        else:
            node.log_error("fixed diagnostic", error)
        assert str(error) == "outer " + PRIVATE
    assert_private(capture, "fixed operation" if traceback else "fixed diagnostic")
    record = capture[1][-1]
    assert record["error_type"] == "ValueError"
    assert "ValueError@" in record["error_message"]
    assert "OSError@" in record["error_message"]
    assert "test_sync_error_diagnostics" in record["error_message"]


def test_exception_type_diagnostic_cannot_forge_a_record(capture):
    hostile_name = "Injected\nERROR counterfeit " + "x" * 1000
    error_type = type(hostile_name, (Exception,), {})
    LoggingMixin().log_error("fixed diagnostic", error_type(PRIVATE))
    record = capture[1][-1]
    assert record["error_type"].startswith("Injected?ERROR?")
    assert len(record["error_type"]) < 200
    assert "\n" not in record["error_type"]
    assert_private(capture, "fixed diagnostic")


def test_caller_authored_logging_message_and_context_remain_intact(capture):
    node = LoggingMixin()
    node.set_log_context(caller_field="caller-owned")
    node.log_error("explicit caller message", extra_field=7)
    record = capture[1][-1]
    assert record["msg"] == "explicit caller message"
    assert record["caller_field"] == "caller-owned" and record["extra_field"] == 7
    assert "error_message" not in record


@pytest.mark.parametrize("hostile_type", [False, True])
def test_optional_type_resolution_diagnostic_omits_exception_payload(
    capture, monkeypatch, hostile_type
):
    error_type = (
        type("Injected\nERROR counterfeit", (OSError,), {}) if hostile_type else OSError
    )

    def reject():
        raise error_type(PRIVATE)

    monkeypatch.setattr(security, "_ALLOWED_TYPES_CACHE", None)
    monkeypatch.setattr(security, "_CACHED_ALLOWED_TYPES", ())
    monkeypatch.setattr(security, "_loaded_optional_signature", lambda: ("probe",))
    monkeypatch.setattr(
        security, "_OPTIONAL_TYPE_GROUPS", [(frozenset({"probe"}), reject)]
    )
    assert str in security._get_cached_allowed_types()
    assert security._ALLOWED_TYPES_CACHE is None
    assert_private(capture, "could not be resolved")
    assert len(capture[0].getvalue().splitlines()) == 1
    assert all("\n" not in str(arg) for arg in capture[1][-1]["args"])


@pytest.mark.parametrize("phase", ["enter", "loosen", "restore"])
def test_resource_failure_diagnostic_keeps_safeguard_without_payload(
    capture, monkeypatch, phase
):
    from types import SimpleNamespace

    def reject(*args):
        raise OSError(PRIVATE)

    resource = SimpleNamespace(
        RLIMIT_AS=0,
        RLIM_INFINITY=-1,
        getrlimit=lambda limit: (-1, -1),
        setrlimit=reject,
    )
    monkeypatch.setattr(security, "resource", resource)
    monkeypatch.setattr(security, "_current_address_space_bytes", lambda: 1000)
    monkeypatch.setattr(security, "_address_space_unsupported_logged", False)
    monkeypatch.setattr(security, "_address_space_requests", [])
    monkeypatch.setattr(security, "_address_space_saved", None)
    monkeypatch.setattr(security, "_address_space_applied", None)
    if phase == "enter":
        assert security._enter_address_space_guard(32) is None
        assert security._address_space_requests == []
        expected = "Memory limit is NOT enforced"
    else:
        security._address_space_saved = (-1, -1)
        security._address_space_applied = 1
        security._address_space_requests[:] = [1, 2] if phase == "loosen" else [1]
        security._exit_address_space_guard(1)
        assert security._address_space_saved == (-1, -1)
        assert security._address_space_applied == 1
        expected = "Could not loosen" if phase == "loosen" else "Could not restore"
    assert_private(capture, expected)
