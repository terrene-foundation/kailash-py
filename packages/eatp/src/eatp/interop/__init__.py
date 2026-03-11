# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP standards interoperability — JWT, W3C VC, DID, UCAN, SD-JWT, Biscuit."""

# DID identity layer — always available (no extra dependencies).
from eatp.interop.did import (
    DIDDocument,
    DIDResolutionError,
    DIDValidationError,
    ServiceEndpoint,
    VerificationMethod,
    create_did_document,
    did_document_from_dict,
    did_document_to_dict,
    did_from_authority,
    generate_did,
    generate_did_key,
    resolve_did,
)

__all__ = [
    # DID identity layer
    "DIDDocument",
    "DIDResolutionError",
    "DIDValidationError",
    "ServiceEndpoint",
    "VerificationMethod",
    "create_did_document",
    "did_document_from_dict",
    "did_document_to_dict",
    "did_from_authority",
    "generate_did",
    "generate_did_key",
    "resolve_did",
]

# Re-export JWT interop public API when pyjwt is available.
# If pyjwt is not installed, imports from this package will raise a clear
# ImportError only when the jwt submodule is accessed directly.
try:
    from eatp.interop.jwt import (
        EATP_VERSION,
        export_capability_as_jwt,
        export_chain_as_jwt,
        export_delegation_as_jwt,
        import_chain_from_jwt,
    )

    __all__ += [
        "EATP_VERSION",
        "export_chain_as_jwt",
        "import_chain_from_jwt",
        "export_capability_as_jwt",
        "export_delegation_as_jwt",
    ]
except ImportError:
    # pyjwt not installed -- jwt interop unavailable but other interop
    # submodules (W3C VC, DID, etc.) remain importable from this package.
    pass

# W3C Verifiable Credentials interop — uses only pynacl (always available).
from eatp.interop.w3c_vc import (
    EATP_CONTEXT_URL,
    W3C_CREDENTIALS_V2_CONTEXT,
    export_as_verifiable_credential,
    export_capability_as_vc,
    import_from_verifiable_credential,
    verify_credential,
)

__all__ += [
    # W3C Verifiable Credentials
    "EATP_CONTEXT_URL",
    "W3C_CREDENTIALS_V2_CONTEXT",
    "export_as_verifiable_credential",
    "export_capability_as_vc",
    "import_from_verifiable_credential",
    "verify_credential",
]

# Biscuit-inspired token format — uses pynacl for Ed25519 signing.
try:
    from eatp.interop.biscuit import (
        BISCUIT_VERSION,
        attenuate,
        from_biscuit,
        to_biscuit,
        verify_biscuit,
    )

    __all__ += [
        "BISCUIT_VERSION",
        "to_biscuit",
        "from_biscuit",
        "attenuate",
        "verify_biscuit",
    ]
except ImportError:
    # pynacl not installed -- biscuit interop unavailable but other interop
    # submodules remain importable from this package.
    pass

# UCAN v0.10.0 delegation tokens — uses pynacl for Ed25519 signing.
try:
    from eatp.interop.ucan import (
        UCAN_VERSION,
        from_ucan,
        to_ucan,
    )

    __all__ += [
        "UCAN_VERSION",
        "to_ucan",
        "from_ucan",
    ]
except ImportError:
    # pynacl not installed -- UCAN interop unavailable but other interop
    # submodules remain importable from this package.
    pass
