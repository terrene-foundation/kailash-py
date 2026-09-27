"""Real POSIX signing files preserve identity and restrict private inodes."""

import base64
import os
import stat

import pytest
from cryptography.hazmat.primitives import serialization
from nacl.signing import SigningKey, VerifyKey

from kailash.trust.plane.holds import _load_or_create_signing_keys
from kailash.trust.plane.key_managers.manager import LocalFileKeyManager
from kailash.trust.plane.project import _load_keys, _save_keys
from kailash.trust.signing.crypto import generate_keypair

pytestmark = [
    pytest.mark.regression,
    pytest.mark.skipif(os.name != "posix", reason="POSIX inode permissions"),
]


def paths(directory, kind):
    suffix = "pem" if kind == "manager" else "key"
    return directory / f"private.{suffix}", directory / f"public.{suffix}"


def load(directory, kind):
    if kind in ("holds", "project"):
        if kind == "project":
            private_path, public_path = paths(directory, kind)
            if (
                not private_path.exists()
                and not public_path.exists()
                and not private_path.is_symlink()
                and not public_path.is_symlink()
            ):
                _save_keys(directory, *generate_keypair())
            private, public = _load_keys(directory)
        else:
            private, public = _load_or_create_signing_keys(directory)
        signing = SigningKey(base64.b64decode(private))
        VerifyKey(base64.b64decode(public)).verify(
            b"identity-proof", signing.sign(b"identity-proof").signature
        )
        return base64.b64decode(public)
    manager = LocalFileKeyManager(directory)
    public = serialization.load_pem_public_key((directory / "public.pem").read_bytes())
    public.verify(manager.sign(b"identity-proof"), b"identity-proof")
    assert manager.algorithm() == "ed25519"
    return manager.get_public_key()


@pytest.mark.parametrize("kind", ["holds", "manager", "project"])
@pytest.mark.parametrize("remove_public", [False, True])
def test_existing_identity_and_private_bytes_survive_recovery(
    tmp_path, kind, remove_public
):
    first = load(tmp_path, kind)
    private, public = paths(tmp_path, kind)
    before = private.read_bytes()
    private.chmod(0o666)
    if remove_public:
        public.unlink()
    assert load(tmp_path, kind) == first
    assert private.read_bytes() == before
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert stat.S_IMODE(public.stat().st_mode) == 0o644
    assert before not in public.read_bytes()


@pytest.mark.parametrize("kind", ["holds", "manager", "project"])
@pytest.mark.parametrize("state", ["public-only", "mismatched", "invalid-private"])
def test_incomplete_or_inconsistent_identity_fails_without_rotation(
    tmp_path, kind, state
):
    load(tmp_path, kind)
    private, public = paths(tmp_path, kind)
    if state == "public-only":
        private.unlink()
    elif state == "mismatched":
        other = tmp_path / "other"
        other.mkdir()
        load(other, kind)
        public.write_bytes(paths(other, kind)[1].read_bytes())
    else:
        private.write_bytes(b"invalid-existing-private")
        public.unlink()
    before = {p.name: p.read_bytes() for p in (private, public) if p.exists()}
    with pytest.raises((ValueError, TypeError)):
        load(tmp_path, kind)
    assert {p.name: p.read_bytes() for p in (private, public) if p.exists()} == before


@pytest.mark.parametrize("kind", ["holds", "manager", "project"])
@pytest.mark.parametrize("target_exists", [False, True])
@pytest.mark.parametrize("component", ["private", "public"])
def test_final_component_symlinks_are_rejected(
    tmp_path, kind, component, target_exists
):
    load(tmp_path, kind)
    private, public = paths(tmp_path, kind)
    path = private if component == "private" else public
    path.unlink()
    target = tmp_path / "external-target"
    if target_exists:
        target.write_bytes(b"unchanged-target")
    path.symlink_to(target)
    with pytest.raises(OSError):
        load(tmp_path, kind)
    assert path.is_symlink()
    assert (
        target.read_bytes() == b"unchanged-target"
        if target_exists
        else not target.exists()
    )


@pytest.mark.parametrize("producer", ["project", "manager"])
def test_overwrite_restricts_existing_inode_before_private_write(tmp_path, producer):
    if producer == "project":
        private, public = generate_keypair()
        target = tmp_path / "private.key"
        target.write_bytes(b"previous-bytes")
        target.chmod(0o666)
        _save_keys(tmp_path, private, public)
        assert target.read_text() == private
        assert (tmp_path / "public.key").read_text() == public
    else:
        manager = LocalFileKeyManager(tmp_path)
        target = tmp_path / "private.pem"
        before = target.read_bytes()
        target.chmod(0o666)
        manager._save_keys()
        assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize("private", [False, True])
def test_shared_writer_rejects_symlink_and_closes_on_failure(tmp_path, private):
    from kailash.trust.plane._key_files import write_key_file

    target = tmp_path / "target"
    target.write_bytes(b"original")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(OSError):
        write_key_file(link, b"replacement", private=private)
    assert target.read_bytes() == b"original"
    # /dev/full is not portable to macOS; a real FIFO exercises the opened-fd
    # validation failure without substituting filesystem calls.
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        for _ in range(5):
            with pytest.raises(OSError, match="regular file"):
                write_key_file(fifo, b"replacement", private=private)
    finally:
        os.close(reader)


@pytest.mark.parametrize("producer", ["project", "manager", "shared"])
def test_actual_write_descriptor_is_private_and_closed(tmp_path, monkeypatch, producer):
    from kailash.trust.plane import _key_files

    real_os = os
    writes = []
    opened = []

    class ObservedOS:
        def __getattr__(self, name):
            return getattr(real_os, name)

        def open(self, path, flags, mode=0o600):
            fd = real_os.open(path, flags, mode)
            opened.append(fd)
            return fd

        def write(self, fd, data):
            writes.append(stat.S_IMODE(real_os.fstat(fd).st_mode))
            # Exercise real short writes so full key material must be completed.
            return real_os.write(fd, data[:7])

    if producer == "manager":
        manager = LocalFileKeyManager(tmp_path)
        target = tmp_path / "private.pem"
        expected = target.read_bytes()
    else:
        target = tmp_path / "private.key"
        expected = generate_keypair()[0].encode()
        target.write_bytes(b"previous-bytes")
    target.chmod(0o666)
    monkeypatch.setattr(_key_files, "os", ObservedOS())
    if producer == "project":
        _save_keys(tmp_path, expected.decode(), generate_keypair()[1])
    elif producer == "manager":
        manager._save_keys()
    else:
        _key_files.write_key_file(target, expected, private=True)
    assert writes and writes[0] == 0o600
    assert all(mode in (0o600, 0o644) for mode in writes)
    assert target.read_bytes() == expected
    for fd in opened:
        with pytest.raises(OSError):
            real_os.fstat(fd)


def test_permission_failure_precedes_truncation_and_closes_descriptor(
    tmp_path, monkeypatch
):
    from kailash.trust.plane import _key_files

    target = tmp_path / "private.key"
    original = generate_keypair()[0].encode()
    target.write_bytes(original)
    target.chmod(0o644)
    reached = []

    def deny(path, *, fd=None):
        reached.append(fd)
        assert os.fstat(fd).st_size == len(original)
        raise PermissionError("controlled permission denial")

    monkeypatch.setattr(_key_files, "restrict_to_owner", deny)
    with pytest.raises(PermissionError, match="controlled permission denial"):
        _key_files.write_key_file(target, generate_keypair()[0].encode(), private=True)
    assert reached
    assert target.read_bytes() == original
    for fd in reached:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("existing", [False, True])
def test_unavailable_permission_provider_never_writes_private_bytes(
    tmp_path, monkeypatch, existing
):
    from kailash.trust.plane import _key_files

    path = tmp_path / "private.key"
    original = generate_keypair()[0].encode() if existing else b""
    if existing:
        path.write_bytes(original)
    reached = []

    def unavailable(path, *, fd=None):
        reached.append(fd)
        return False

    monkeypatch.setattr(_key_files, "restrict_to_owner", unavailable)
    with pytest.raises(PermissionError, match="pywin32"):
        _key_files.write_key_file(path, generate_keypair()[0].encode(), private=True)
    assert path.read_bytes() == original
    assert reached
    for fd in reached:
        with pytest.raises(OSError):
            os.fstat(fd)
    public = tmp_path / "public.key"
    public_bytes = generate_keypair()[1].encode()
    _key_files.write_key_file(public, public_bytes, private=False)
    assert public.read_bytes() == public_bytes
    assert len(reached) == 1


@pytest.mark.parametrize("kind", ["holds", "manager", "project"])
@pytest.mark.parametrize("private_present", [False, True])
@pytest.mark.parametrize("public_type", ["fifo", "directory"])
def test_public_key_requires_regular_file_without_waiting_for_fifo_writer(
    tmp_path, kind, private_present, public_type
):
    load(tmp_path, kind)
    private, public = paths(tmp_path, kind)
    original = private.read_bytes()
    if not private_present:
        private.unlink()
    public.unlink()
    if public_type == "fifo":
        os.mkfifo(public)
    else:
        public.mkdir()
    # No FIFO writer exists: a blocking open would stall here and fail timeout.
    with pytest.raises(OSError, match="Signing key must be a regular file"):
        load(tmp_path, kind)
    assert private.exists() is private_present
    if private_present:
        assert private.read_bytes() == original
    mode = public.stat().st_mode
    assert stat.S_ISFIFO(mode) if public_type == "fifo" else stat.S_ISDIR(mode)


@pytest.mark.parametrize(
    "public_type", ["regular", "missing", "fifo", "directory", "symlink"]
)
@pytest.mark.asyncio
async def test_bundle_uses_same_public_key_descriptor_guard(tmp_path, public_type):
    from kailash.trust.plane.bundle import VerificationBundle
    from kailash.trust.plane.project import TrustProject

    project = await TrustProject.create(
        trust_dir=str(tmp_path), project_name="key-reader", author="key-review"
    )
    public = tmp_path / "keys" / "public.key"
    original = public.read_text()
    if public_type != "regular":
        public.unlink()
    if public_type == "fifo":
        os.mkfifo(public)
    elif public_type == "directory":
        public.mkdir()
    elif public_type == "symlink":
        target = tmp_path / "public-target"
        target.write_text(original)
        public.symlink_to(target)
    if public_type in {"regular", "missing"}:
        bundle = await VerificationBundle.create(project)
        assert bundle.public_key == (original if public_type == "regular" else "")
    else:
        with pytest.raises(OSError):
            await VerificationBundle.create(project)
