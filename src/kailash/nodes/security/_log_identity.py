"""Credential-safe logger names assembled from original metadata components."""

import hashlib
import hmac
import re
import secrets

from kailash.utils.secure_logging import safe_log_field

_LOG_IDENTITY_KEY = secrets.token_bytes(32)


def log_name_parts(
    name: object, parts: tuple[object, ...] | None
) -> tuple[object, ...]:
    """Keep identity components separate until each has been masked."""
    if parts is None:
        return (name,)
    if type(parts) is not tuple:
        raise TypeError("log_name_parts must be a tuple or None")
    return parts


def _identity_bytes(name: object) -> bytes:
    """Frame the original identity without running user conversion callbacks."""
    if isinstance(name, str):
        kind, value = b"str", str.__str__(name).encode("utf-8", "surrogatepass")
    elif isinstance(name, bytes):
        kind, value = b"bytes", bytes.__bytes__(name)
    elif name is None:
        kind, value = b"none", b""
    elif type(name) is bool:  # noqa: E721 - exclude user conversion overrides
        kind, value = b"bool", b"1" if name else b"0"
    elif type(name) is int:  # noqa: E721 - exclude user conversion overrides
        kind, value = b"int", str(name).encode("ascii")
    elif type(name) is float:  # noqa: E721 - exclude user conversion overrides
        kind, value = b"float", name.hex().encode("ascii")
    else:
        # Node names are documented as strings. Opaque metadata is never
        # rendered; object identity keeps simultaneous unsupported values apart.
        kind, value = b"object", str(id(name)).encode("ascii")
    return kind + b":" + str(len(value)).encode("ascii") + b":" + value


def log_namespace(prefix: str, name: object, parts: tuple[object, ...] | None) -> str:
    """Mask components and preserve distinct logger configuration identities.

    Masked names receive a process-keyed identifier: credential guesses cannot
    be tested against a public unkeyed hash. Ordinary string names retain their
    historical namespace. The identifier depends on the original name, so the
    same node identity retains the same logger across repeated construction.
    """
    components = log_name_parts(name, parts)
    rendered = safe_log_field(
        prefix + "".join(safe_log_field(part) for part in components)
    )
    if (
        isinstance(name, str)
        and rendered == prefix + str.__str__(name)
        and not re.search(r"\.id-[0-9a-f]{64}$", rendered)
    ):
        return rendered
    digest = hmac.new(
        _LOG_IDENTITY_KEY, _identity_bytes(name), hashlib.sha256
    ).hexdigest()
    suffix = ".id-" + digest
    return rendered[: 512 - len(suffix)] + suffix
