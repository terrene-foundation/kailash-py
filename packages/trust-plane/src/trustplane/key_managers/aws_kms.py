# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AWS KMS key manager for TrustPlane.

Uses AWS KMS for signing operations with ECDSA P-256 (the only
asymmetric algorithm available in AWS KMS that supports Ed25519-like
use cases). Ed25519 is not available in AWS KMS.

Requires boto3: pip install trust-plane[aws]

Example:
    from trustplane.key_managers.aws_kms import AwsKmsKeyManager

    manager = AwsKmsKeyManager(
        key_id="arn:aws:kms:us-east-1:123456789012:key/my-key-id",
        region="us-east-1",
    )
    signature = manager.sign(b"data to sign")
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from trustplane.exceptions import KeyManagerError, KeyNotFoundError, SigningError

logger = logging.getLogger(__name__)

__all__ = [
    "AwsKmsKeyManager",
]

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore[assignment]


class AwsKmsKeyManager:
    """AWS KMS key manager implementing TrustPlaneKeyManager protocol.

    Uses ECDSA_SHA_256 signing algorithm (the AWS KMS equivalent for
    asymmetric signing). Ed25519 is not available in AWS KMS, so this
    manager uses ECDSA P-256 instead.

    Args:
        key_id: AWS KMS key ARN or alias.
        region: AWS region (default: "us-east-1").

    Raises:
        ImportError: If boto3 is not installed.
    """

    ALGORITHM = "ecdsa-p256"

    def __init__(self, key_id: str, region: str = "us-east-1") -> None:
        if not _BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for AWS KMS key management. "
                "Install with: pip install trust-plane[aws]"
            )

        self._key_id = key_id
        self._region = region
        self._client: Any = boto3.client("kms", region_name=region)  # type: ignore[union-attr]
        self._public_key_cache: bytes | None = None

        logger.info(
            "Initialized AWS KMS key manager for key %s in %s",
            key_id,
            region,
        )

    def sign(self, data: bytes) -> bytes:
        """Sign data using AWS KMS.

        Calls KMS Sign API with ECDSA_SHA_256 algorithm.

        Args:
            data: Bytes to sign.

        Returns:
            DER-encoded ECDSA signature bytes.

        Raises:
            TrustPlaneError: If KMS signing fails.
        """
        try:
            response = self._client.sign(
                KeyId=self._key_id,
                Message=data,
                MessageType="RAW",
                SigningAlgorithm="ECDSA_SHA_256",
            )
        except (BotoCoreError, ClientError) as exc:
            raise SigningError(
                f"KMS Sign failed: {exc}",
                provider="aws_kms",
                key_id=self._key_id,
            ) from exc
        return response["Signature"]

    def get_public_key(self) -> bytes:
        """Retrieve the public key from AWS KMS.

        Caches the result since KMS public keys do not change.

        Returns:
            DER-encoded public key bytes.

        Raises:
            KeyNotFoundError: If the key does not exist in KMS.
            KeyManagerError: If the KMS API call fails.
        """
        if self._public_key_cache is None:
            try:
                response = self._client.get_public_key(KeyId=self._key_id)
            except (BotoCoreError, ClientError) as exc:
                err_code = ""
                if hasattr(exc, "response"):
                    err_code = exc.response.get("Error", {}).get("Code", "")  # type: ignore[union-attr]
                if err_code == "NotFoundException":
                    raise KeyNotFoundError(
                        f"Key not found in KMS: {exc}",
                        provider="aws_kms",
                        key_id=self._key_id,
                    ) from exc
                raise KeyManagerError(
                    f"KMS GetPublicKey failed: {exc}",
                    provider="aws_kms",
                    key_id=self._key_id,
                ) from exc
            self._public_key_cache = response["PublicKey"]
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
            Always "ecdsa-p256" for AWS KMS.
        """
        return self.ALGORITHM
