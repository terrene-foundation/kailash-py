"""
Secure hook loading with signature verification.

Prevents arbitrary code execution via filesystem hook discovery by requiring
cryptographic signatures for all hooks. Addresses Finding #2 (CRITICAL):
Arbitrary Code Execution via Filesystem Hook Discovery.

Security Features:
- Cryptographic signature verification (Ed25519)
- Hook signature metadata (.sig files)
- SecureHookLoader with signature validation
- SecureHookManager that extends HookManager with secure discovery
"""

import hashlib
import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    Ed25519PublicKey = None
    InvalidSignature = Exception

from ..manager import HookManager
from ..protocol import BaseHook

logger = logging.getLogger(__name__)


@dataclass
class HookSignature:
    """
    Cryptographic signature metadata for a hook.

    Stored as .sig file alongside hook .py file.

    Format (.sig file):
        {
            "hook_file": "my_hook.py",
            "signature": "<base64_ed25519_signature>",
            "public_key": "<base64_ed25519_public_key>",
            "algorithm": "ed25519",
            "signer": "trusted-developer@company.com",
            "timestamp": "2025-11-02T12:00:00Z",
            "metadata": {"purpose": "audit logging"}
        }

    Example:
        >>> # Generate signature (developer workflow)
        >>> from cryptography.hazmat.primitives.asymmetric import ed25519
        >>> private_key = ed25519.Ed25519PrivateKey.generate()
        >>> public_key = private_key.public_key()
        >>>
        >>> # Sign hook file
        >>> hook_content = Path("audit_hook.py").read_bytes()
        >>> signature = private_key.sign(hook_content)
        >>>
        >>> # Create signature metadata
        >>> sig = HookSignature(
        ...     hook_file="audit_hook.py",
        ...     signature=base64.b64encode(signature).decode(),
        ...     public_key=base64.b64encode(
        ...         public_key.public_bytes(
        ...             encoding=serialization.Encoding.Raw,
        ...             format=serialization.PublicFormat.Raw
        ...         )
        ...     ).decode(),
        ...     algorithm="ed25519",
        ...     signer="alice@company.com"
        ... )
        >>>
        >>> # Save signature
        >>> Path("audit_hook.py.sig").write_text(sig.to_json())
    """

    hook_file: str
    signature: str  # Base64-encoded signature
    public_key: str  # Base64-encoded public key
    algorithm: str = "ed25519"
    signer: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(
            {
                "hook_file": self.hook_file,
                "signature": self.signature,
                "public_key": self.public_key,
                "algorithm": self.algorithm,
                "signer": self.signer,
                "timestamp": self.timestamp,
                "metadata": self.metadata,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "HookSignature":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)

    @classmethod
    def from_file(cls, sig_file: Path) -> "HookSignature":
        """Load signature from .sig file."""
        return cls.from_json(sig_file.read_text())


class SecureHookLoader:
    """
    Secure hook loader with signature verification.

    Validates cryptographic signatures before loading hook files.
    Prevents loading of unsigned or tampered hooks.

    Example:
        >>> loader = SecureHookLoader(
        ...     require_signatures=True,
        ...     trusted_signers={"alice@company.com", "bob@company.com"}
        ... )
        >>>
        >>> # Load hook with signature verification
        >>> hook_instance = loader.load_hook(
        ...     hook_file=Path("/secure/hooks/audit_hook.py"),
        ...     sig_file=Path("/secure/hooks/audit_hook.py.sig")
        ... )
        >>>
        >>> # Discovery with signature verification
        >>> hooks = loader.discover_hooks(hooks_dir=Path("/secure/hooks"))
    """

    def __init__(
        self,
        require_signatures: bool = True,
        trusted_signers: Optional[Set[str]] = None,
        trusted_public_keys: Optional[Set[str]] = None,
    ):
        """
        Initialize secure loader.

        Args:
            require_signatures: If True, reject unsigned hooks
            trusted_signers: Set of trusted signer emails (whitelist)
            trusted_public_keys: Set of trusted public keys (whitelist)

        Raises:
            ImportError: If cryptography library not available
        """
        if require_signatures and not CRYPTO_AVAILABLE:
            raise ImportError(
                "cryptography library required for signature verification. "
                "Install with: pip install cryptography"
            )

        self.require_signatures = require_signatures
        self.trusted_signers = trusted_signers or set()
        self.trusted_public_keys = trusted_public_keys or set()

    def verify_signature(
        self,
        hook_file: Path,
        sig: HookSignature,
    ) -> bool:
        """
        Verify cryptographic signature of hook file.

        Args:
            hook_file: Hook .py file
            sig: Signature metadata

        Returns:
            True if signature valid

        Raises:
            ValueError: If signature verification fails
        """
        # Check signer whitelist
        if self.trusted_signers and sig.signer not in self.trusted_signers:
            raise ValueError(
                f"Untrusted signer: {sig.signer} " f"(allowed: {self.trusted_signers})"
            )

        # Check public key whitelist
        if self.trusted_public_keys and sig.public_key not in self.trusted_public_keys:
            raise ValueError(f"Untrusted public key: {sig.public_key[:16]}...")

        # Verify algorithm
        if sig.algorithm != "ed25519":
            raise ValueError(f"Unsupported algorithm: {sig.algorithm}")

        # Load public key
        import base64

        public_key_bytes = base64.b64decode(sig.public_key)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # Load signature
        signature_bytes = base64.b64decode(sig.signature)

        # Load hook file content
        hook_content = hook_file.read_bytes()

        # Verify signature
        try:
            public_key.verify(signature_bytes, hook_content)
            logger.info(
                f"✅ Signature verified for {hook_file.name} " f"(signer: {sig.signer})"
            )
            return True
        except InvalidSignature:
            raise ValueError(
                f"Invalid signature for {hook_file.name} " f"(signer: {sig.signer})"
            )

    def load_hook(
        self,
        hook_file: Path,
        sig_file: Optional[Path] = None,
    ) -> BaseHook:
        """
        Load hook with signature verification.

        Args:
            hook_file: Hook .py file
            sig_file: Signature .sig file (defaults to hook_file + ".sig")

        Returns:
            Instantiated hook

        Raises:
            ValueError: If signature verification fails
            FileNotFoundError: If signature required but not found
        """
        # Check signature file
        if sig_file is None:
            sig_file = hook_file.with_suffix(hook_file.suffix + ".sig")

        if self.require_signatures:
            if not sig_file.exists():
                raise FileNotFoundError(f"Signature required but not found: {sig_file}")

            # Load and verify signature
            sig = HookSignature.from_file(sig_file)
            self.verify_signature(hook_file, sig)

        # Load module
        module_name = f"kaizen_secure_hooks_{hook_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, hook_file)

        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load hook file: {hook_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find hook class
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            if not isinstance(attr, type):
                continue

            if not issubclass(attr, BaseHook) or attr is BaseHook:
                continue

            # Instantiate and return
            try:
                hook_instance = attr()
                logger.info(f"✅ Loaded secure hook: {attr_name} from {hook_file.name}")
                return hook_instance
            except Exception as e:
                raise ValueError(f"Failed to instantiate hook {attr_name}: {e}")

        raise ValueError(f"No hook class found in {hook_file}")

    def discover_hooks(
        self,
        hooks_dir: Path,
    ) -> list[BaseHook]:
        """
        Discover and load hooks with signature verification.

        Only loads hooks with valid signatures.

        Args:
            hooks_dir: Directory containing hook files

        Returns:
            List of loaded hooks

        Raises:
            OSError: If hooks_dir doesn't exist
        """
        if not hooks_dir.exists():
            raise OSError(f"Hooks directory not found: {hooks_dir}")

        if not hooks_dir.is_dir():
            raise OSError(f"Not a directory: {hooks_dir}")

        hooks = []
        hook_files = [f for f in hooks_dir.glob("*.py") if f.name != "__init__.py"]

        for hook_file in hook_files:
            try:
                hook = self.load_hook(hook_file)
                hooks.append(hook)
            except Exception as e:
                if self.require_signatures:
                    logger.error(f"❌ Failed to load {hook_file.name}: {e}")
                else:
                    logger.warning(f"⚠️  Failed to load {hook_file.name}: {e}")

        logger.info(
            f"Discovered {len(hooks)} secure hooks from {hooks_dir} "
            f"({len(hook_files)} files checked)"
        )
        return hooks


class SecureHookManager(HookManager):
    """
    Hook manager with secure filesystem discovery.

    Extends HookManager with signature verification for filesystem hooks.
    Prevents loading of unsigned or tampered hooks.

    Example:
        >>> from kaizen.core.autonomy.hooks.security import SecureHookManager
        >>>
        >>> manager = SecureHookManager(
        ...     require_signatures=True,
        ...     trusted_signers={"alice@company.com"}
        ... )
        >>>
        >>> # Discover hooks with signature verification
        >>> count = await manager.discover_filesystem_hooks(
        ...     hooks_dir=Path("/secure/hooks")
        ... )
        >>> print(f"Loaded {count} verified hooks")
    """

    def __init__(
        self,
        require_signatures: bool = True,
        trusted_signers: Optional[Set[str]] = None,
        trusted_public_keys: Optional[Set[str]] = None,
    ):
        """
        Initialize secure hook manager.

        Args:
            require_signatures: If True, reject unsigned hooks
            trusted_signers: Set of trusted signer emails
            trusted_public_keys: Set of trusted public keys
        """
        super().__init__()
        self.loader = SecureHookLoader(
            require_signatures=require_signatures,
            trusted_signers=trusted_signers,
            trusted_public_keys=trusted_public_keys,
        )

    async def discover_filesystem_hooks(self, hooks_dir: Path) -> int:
        """
        Discover and register hooks with signature verification.

        Overrides HookManager.discover_filesystem_hooks() with secure loading.

        Args:
            hooks_dir: Directory containing hook files

        Returns:
            Number of hooks discovered and registered

        Raises:
            OSError: If hooks_dir doesn't exist
        """
        hooks = self.loader.discover_hooks(hooks_dir)

        # Register all discovered hooks
        discovered_count = 0
        for hook in hooks:
            if not hasattr(hook, "events"):
                logger.warning(
                    f"Hook {hook.__class__.__name__} missing 'events' attribute, skipping"
                )
                continue

            events = hook.events
            if not isinstance(events, list):
                events = [events]

            for event in events:
                self.register(event, hook)
                discovered_count += 1

        logger.info(
            f"Registered {discovered_count} hooks from {len(hooks)} verified files"
        )
        return discovered_count


__all__ = [
    "HookSignature",
    "SecureHookLoader",
    "SecureHookManager",
    "CRYPTO_AVAILABLE",
]
