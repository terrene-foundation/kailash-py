# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Pluggable key manager backends for TrustPlane.

This package provides cloud/HSM key management implementations:
- AwsKmsKeyManager: AWS KMS (ECDSA P-256)
- AzureKeyVaultKeyManager: Azure Key Vault (EC P-256)
- VaultKeyManager: HashiCorp Vault Transit engine (ECDSA P-256)

The local filesystem backend (LocalFileKeyManager) is in the parent
module trustplane.key_manager.

Each cloud backend requires its SDK to be installed. If the SDK is
not available, importing the class succeeds but instantiation raises
ImportError with install instructions.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "AwsKmsKeyManager",
    "AzureKeyVaultKeyManager",
    "VaultKeyManager",
]

from trustplane.key_managers.aws_kms import AwsKmsKeyManager
from trustplane.key_managers.azure_keyvault import AzureKeyVaultKeyManager
from trustplane.key_managers.vault import VaultKeyManager
