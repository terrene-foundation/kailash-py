# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Trust Vault Shamir backup binding -- scaffold awaiting mint ISS-37.

This module owns the binding between the SLIP-0039 wrapper in
:mod:`kailash.trust.vault.shamir` and the Trust Vault key-management
surface. The binding spec is gated on mint ISS-37 (Trust Vault key
identity / clearance / rotation envelope) which is NOT YET STABLE.

Scope today
-----------

The function signature :func:`back_up_vault_key` is published so callers
can compile against it and the wrapper API surface is frozen. The body
deliberately raises :class:`NotImplementedError` referencing issue #606
and mint ISS-37 -- the ONE permitted stub per ``rules/zero-tolerance.md``
Rule 2 (issue-linked, gate documented). When mint ISS-37 lands the body
will fill in the binding; the public signature will not change.

Forward path
------------

When ISS-37 stabilises:

1. The body will resolve the vault key by ID against the mint-issued
   clearance envelope, validating that the calling agent holds the
   required ``backup`` capability.
2. The resolved key bytes will be passed to
   :func:`kailash.trust.vault.shamir.generate` under the supplied
   ritual.
3. An audit anchor will be written to the canonical audit store
   (per ``rules/eatp.md`` audit anchor contract) capturing the ritual
   parameters, the holder distribution policy, and the shard count.
   Shard contents themselves are NEVER logged
   (``rules/observability.md`` MUST Rule 4).

Issue tracker
-------------

* GitHub issue: terrene-foundation/kailash-py#606
* Mint spec: ISS-37 (Trust Vault key clearance and rotation envelope)
"""

from __future__ import annotations

import logging
from typing import List

from kailash.trust.vault.shamir import ShamirRitual

logger = logging.getLogger(__name__)

__all__ = ["back_up_vault_key"]


def back_up_vault_key(
    vault_key: bytes,
    ritual: ShamirRitual,
) -> List[List[str]]:
    """Split a Trust Vault key into Shamir shards under ``ritual``.

    .. warning::

       This is a gated stub awaiting mint ISS-37. The signature is the
       threading point that ISS-37 stabilises later -- the body fills in
       once the binding spec lands. Callers reaching this stub today
       receive :class:`NotImplementedError`.

    Parameters
    ----------
    vault_key:
        The raw vault key bytes resolved by the Trust Vault key manager.
        When implemented, the function will accept either a key handle
        or raw bytes; the signature evolution is in scope for ISS-37.
    ritual:
        The ``m``-of-``n`` ritual parameters captured by
        :class:`ShamirRitual`.

    Returns
    -------
    list[list[str]]
        ``ritual.total_shards`` SLIP-0039 mnemonic shards.

    Raises
    ------
    NotImplementedError
        Until mint ISS-37 stabilises the Trust Vault binding.
    """
    raise NotImplementedError(
        "back_up_vault_key: Trust Vault Shamir binding awaits mint ISS-37 "
        "(see issue #606). The SLIP-0039 wrapper is available today via "
        "kailash.trust.vault.shamir.generate(...) for direct callers."
    )
