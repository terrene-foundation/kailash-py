# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HashiCorp Vault Transit key manager for TrustPlane.

Uses HashiCorp Vault's Transit secrets engine for signing operations
with ECDSA P-256.

Requires hvac: pip install kailash[vault]

Example:
    from kailash.trust.plane.key_managers.vault import VaultKeyManager

    manager = VaultKeyManager(
        vault_addr="https://vault.example.com:8200",
        key_name="trustplane-signing-key",
        mount_point="transit",
    )
    signature = manager.sign(b"data to sign")
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

from kailash.trust.plane.exceptions import (
    KeyManagerError,
    KeyNotFoundError,
    SigningError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "VaultKeyManager",
]

try:
    import hvac

    _HVAC_AVAILABLE = True
except ImportError:
    _HVAC_AVAILABLE = False
    hvac = None  # type: ignore[assignment]


class VaultKeyManager:
    """HashiCorp Vault Transit key manager implementing TrustPlaneKeyManager protocol.

    Uses the Vault Transit secrets engine for signing with ECDSA P-256.
    Authentication is expected to be configured via environment variables
    (VAULT_TOKEN) or the hvac client's auto-auth mechanisms.

    Args:
        vault_addr: Vault server address (e.g. "https://vault.example.com:8200").
        key_name: Name of the Transit key.
        mount_point: Transit engine mount point (default: "transit").

    Raises:
        ImportError: If hvac is not installed.
    """

    ALGORITHM = "ecdsa-p256"
    DEFAULT_MOUNT_POINT = "transit"

    def __init__(
        self,
        vault_addr: str,
        key_name: str,
        mount_point: str = "transit",
    ) -> None:
        if not _HVAC_AVAILABLE:
            raise ImportError(
                "hvac is required for HashiCorp Vault key management. "
                "Install with: pip install kailash[vault]"
            )

        self._vault_addr = vault_addr
        self._key_name = key_name
        self._mount_point = mount_point

        self._client: Any = hvac.Client(url=vault_addr)  # type: ignore[union-attr]
        self._public_key_cache: bytes | None = None

        logger.info(
            "Initialized Vault Transit key manager for key %s at %s (mount: %s)",
            key_name,
            vault_addr,
            mount_point,
        )

    def sign(self, data: bytes) -> bytes:
        """Sign data using Vault Transit engine.

        Encodes data as base64 for the Transit API, then decodes the
        returned base64 signature.

        Args:
            data: Bytes to sign.

        Returns:
            Raw signature bytes.

        Raises:
            TrustPlaneError: If Vault signing fails.
        """
        b64_input = base64.b64encode(data).decode("utf-8")
        try:
            response = self._client.secrets.transit.sign_data(
                name=self._key_name,
                hash_input=b64_input,
                hash_algorithm="sha2-256",
                signature_algorithm="pkcs1v15",
                mount_point=self._mount_point,
            )
        except Exception as exc:
            raise SigningError(
                f"Vault Transit signing failed: {exc}",
                provider="hashicorp_vault",
                key_id=self._key_name,
            ) from exc
        # Vault returns signature as "vault:v1:base64data"
        sig_str = response["data"]["signature"]
        # Strip the vault prefix
        sig_b64 = sig_str.split(":")[-1]
        return base64.b64decode(sig_b64)

    def get_public_key(self) -> bytes:
        """Retrieve the public key from Vault Transit engine.

        Returns:
            The public key bytes from the Transit key.

        Raises:
            KeyNotFoundError: If the key does not exist in Vault Transit.
            KeyManagerError: If the Vault API call fails.
        """
        if self._public_key_cache is None:
            try:
                response = self._client.secrets.transit.read_key(
                    name=self._key_name,
                    mount_point=self._mount_point,
                )
            except Exception as exc:
                raise KeyNotFoundError(
                    f"Vault Transit key not found or inaccessible: {exc}",
                    provider="hashicorp_vault",
                    key_id=self._key_name,
                ) from exc
            # The latest version's public key
            keys = response["data"]["keys"]
            latest_version = str(max(int(k) for k in keys))
            pub_key_pem = keys[latest_version]["public_key"]
            self._public_key_cache = pub_key_pem.encode("utf-8")
        assert self._public_key_cache is not None
        return self._public_key_cache

    def key_id(self) -> str:
        """Return SHA-256 hex fingerprint of the public key.

        Returns:
            64-character hex string.

        Raises:
            KeyManagerError: If the public key cannot be retrieved.
        """
        return hashlib.sha256(self.get_public_key()).hexdigest()

    def algorithm(self) -> str:
        """Return the signing algorithm identifier.

        Returns:
            Always "ecdsa-p256" for Vault Transit.
        """
        return self.ALGORITHM
