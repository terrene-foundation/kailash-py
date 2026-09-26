"""SQLite address conversion shared by sync and async connection producers."""

import hashlib
import json
import os
from urllib.parse import quote, unquote, unquote_plus, urlencode, urlsplit

# SQLAlchemy's SQLite dialect separates these Python driver options from the
# native SQLite URI options (SQLiteDialect_pysqlite.create_connect_args).
_DRIVER_OPTIONS = {
    "uri": bool,
    "timeout": float,
    "isolation_level": str,
    "detect_types": int,
    "check_same_thread": bool,
    "cached_statements": int,
}


def _decode_component(value: str, *, form: bool = False) -> str:
    decoded = (unquote_plus if form else unquote)(value, errors="strict")
    if "\x00" in decoded:
        raise ValueError("SQLite URI components must not contain decoded NUL bytes")
    return decoded


def _query_pairs(query: str, *, sql_url: bool = False) -> list[tuple[str, str]]:
    # SQLite URI query uses percent escapes, not form-encoded '+' for spaces.
    return [
        (_decode_component(k, form=sql_url), _decode_component(v, form=sql_url))
        for part in query.split("&")
        if part
        for k, _, v in [part.partition("=")]
    ]


def is_sqlite_url(value: str) -> bool:
    """Recognize SQLite URLs and native URIs without classifying other engines."""
    scheme, separator, _ = value.partition("://")
    return (
        value == ":memory:"
        or value.lower().startswith("file:")
        or (bool(separator) and scheme.lower().split("+", 1)[0] == "sqlite")
    )


def sqlite_connection_target(value: str) -> tuple[str, dict]:
    """Return the native SQLite target and Python driver options.

    Three-slash URLs name relative paths, four slashes absolute paths; the
    legacy two-slash relative form remains accepted. Bare paths stay literal.
    Native URI options, including unknown extension options, reach SQLite.
    """
    scheme, separator, remainder = value.partition("://")
    sql_url = bool(separator) and scheme.lower().split("+", 1)[0] == "sqlite"
    if sql_url:
        value = remainder[1:] if remainder.startswith("/") else remainder
    native_uri = value.lower().startswith("file:")
    if native_uri:
        if any(character in value for character in "\t\r\n"):
            raise ValueError("SQLite native URIs must percent-encode TAB, CR, and LF")
        # Never collapse distinct native filename bytes through replacement
        # characters in the cache identity. Reject before any driver opens it.
        parsed_native = urlsplit(value)
        if parsed_native.netloc not in {"", "localhost"}:
            raise ValueError("SQLite file: URI authority must be empty or localhost")
        _decode_component(parsed_native.path)
    if not sql_url and not native_uri:
        return value or ":memory:", {}
    target, _, query = value.partition("?")
    options = {}
    native_options = []
    seen = set()
    for key, raw in _query_pairs(query, sql_url=sql_url):
        converter = _DRIVER_OPTIONS.get(key)
        semantic_key = _decode_component(key) if sql_url and converter is None else key
        if semantic_key in seen:
            raise ValueError(f"Duplicate SQLite option: {semantic_key}")
        seen.add(semantic_key)
        if converter is None and semantic_key in _DRIVER_OPTIONS:
            raise ValueError("Encoded SQLite driver option names are ambiguous")
        if converter is None:
            # SQLAlchemy decodes its URL once, then SQLite decodes the native
            # URI again. Keep the two escaping layers separate.
            native_options.append(
                (semantic_key, _decode_component(raw)) if sql_url else (key, raw)
            )
        elif converter is bool:
            if raw.lower() not in {"true", "false", "yes", "no", "on", "off", "1", "0"}:
                raise ValueError(f"Invalid SQLite boolean option: {key}")
            options[key] = raw.lower() in {"true", "yes", "on", "1"}
        else:
            options[key] = converter(raw)
    if native_uri:
        if options.get("uri") is False:
            raise ValueError("Native SQLite file: URIs require uri=true")
        target = "file:" + target[5:]
        options["uri"] = True
        if native_options:
            target += "?" + urlencode(native_options, quote_via=quote)
    elif native_options:
        raise ValueError("SQLite native URI options require a file: URI")
    return target or ":memory:", options


def sqlite_sqlalchemy_url(value: str) -> str:
    """Adapt SQLite addresses to SQLAlchemy; leave other engines unchanged."""
    if not is_sqlite_url(value):
        return value
    target, options = sqlite_connection_target(value)
    return _sqlalchemy_target_url(target, options)


def _sqlalchemy_target_url(target: str, options: dict) -> str:
    native_query = ""
    if options.get("uri"):
        target, _, raw_query = target.partition("?")
        native_query = urlencode(
            [(quote(k, safe=""), quote(v, safe="")) for k, v in _query_pairs(raw_query)]
        )
    driver_query = urlencode(
        {k: str(v).lower() if isinstance(v, bool) else v for k, v in options.items()}
    )
    query = "&".join(part for part in [native_query, driver_query] if part)
    if query:
        target += "?" + query
    return f"sqlite:///{target}"


def sqlite_cache_identity_url(value: str) -> str:
    """Encode physical address and URI semantics into generic encoder input.

    Driver timeout/thread options do not select a database. Unknown native URI
    options are conservatively identity-bearing, including VFS extensions.
    The digest lives in the URL path because the generic Express encoder
    deliberately excludes query parameters from its Rust-pinned byte contract.
    """
    if not is_sqlite_url(value):
        return value
    target, options = sqlite_connection_target(value)
    identity_options = []
    if options.get("uri"):
        parsed = urlsplit(target)
        identity_options = [
            (k, v)
            for k, v in _query_pairs(parsed.query)
            if not (k == "mode" and v in {"ro", "rw", "rwc"})
        ]
        target = _decode_component(parsed.path)
        is_memory = (
            target == ":memory:"
            or ("mode", "memory") in identity_options
            or ("vfs", "memdb") in identity_options
        )
    else:
        is_memory = target == ":memory:"
    address = target if is_memory else os.path.realpath(target)
    identity = json.dumps([address, identity_options], separators=(",", ":"))
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return "sqlite:///__kailash_sqlite_identity__/" + digest


def sqlite_memory_uri_kind(value: str) -> str | None:
    """Classify native memory URI sharing without altering Core semantics."""
    if not is_sqlite_url(value):
        return None
    target, options = sqlite_connection_target(value)
    if not options.get("uri"):
        return "anonymous" if target == ":memory:" else None
    parsed = urlsplit(target)
    native_path = _decode_component(parsed.path)
    if not native_path:
        return "private"
    params = dict(_query_pairs(parsed.query))
    if params.get("vfs") == "memdb":
        return "shared" if native_path.startswith("/") else "private"
    if native_path == ":memory:" or params.get("mode") == "memory":
        return "shared" if params.get("cache") == "shared" else "private"
    return None


def sqlite_owner_url(value: str) -> str:
    """Pin a file address to its owner's creation directory, retaining options."""
    if not is_sqlite_url(value) or sqlite_memory_uri_kind(value) is not None:
        return value
    target, options = sqlite_connection_target(value)
    if target == ":memory:":
        return value
    if options.get("uri"):
        parsed = urlsplit(target)
        path = os.path.realpath(_decode_component(parsed.path))
        target = "file:" + quote(path, safe="/")
        if parsed.query:
            target += "?" + parsed.query
    else:
        target = os.path.realpath(target)
    return _sqlalchemy_target_url(target, options)


def sqlite_is_readonly(value: str) -> bool:
    """Whether native URI mode forbids database writes, without weakening it."""
    target, options = sqlite_connection_target(value)
    return bool(
        options.get("uri")
        and dict(_query_pairs(urlsplit(target).query)).get("mode") == "ro"
    )
