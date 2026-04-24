# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``TrainingContext`` — the provenance envelope for ML training runs.

Every ``km.fit(...)`` / ``km.autolog()`` / ``ModelRegistry.register_version``
call that wants to record reproducible lineage passes a
``TrainingContext`` that carries the four fields the registry stores as
mandatory lineage provenance (see spec § 4.4 and
``ml-registry-draft.md`` § 4):

* ``run_id``        — experiment-tracker run identifier
* ``tenant_id``     — the DataFlow tenant the training set was read from
* ``dataset_hash``  — output of :func:`dataflow.ml.hash`; the stable
  content fingerprint of the training set
* ``actor_id``      — the clearance subject who initiated the run (user,
  service, or agent)

The dataclass is frozen so a context passed to a training engine cannot
be mutated mid-run — any change in provenance is a separate context and
a separate registry entry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

__all__ = ["TrainingContext"]


@dataclass(frozen=True)
class TrainingContext:
    """Provenance envelope for a single ML training run.

    Attributes:
        run_id: Identifier for the run in the experiment tracker. MUST
            be non-empty.
        tenant_id: Tenant that owns the training data. ``None`` is
            permitted ONLY for single-tenant ``DataFlow`` instances;
            multi-tenant feature groups raise
            :class:`MLTenantRequiredError` upstream before a
            ``TrainingContext`` can be constructed with ``None``.
        dataset_hash: The ``dataflow.ml.hash()`` output for the training
            set. MUST start with ``"sha256:"`` and be 64 hex chars.
        actor_id: The subject who initiated the training run. MUST be
            non-empty.
    """

    run_id: str
    tenant_id: Optional[str]
    dataset_hash: str
    actor_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("TrainingContext.run_id MUST be a non-empty string")
        if self.tenant_id is not None and not isinstance(self.tenant_id, str):
            raise ValueError(
                "TrainingContext.tenant_id MUST be str or None; got "
                f"{type(self.tenant_id).__name__}"
            )
        if not isinstance(self.dataset_hash, str) or not self.dataset_hash.startswith(
            "sha256:"
        ):
            raise ValueError(
                "TrainingContext.dataset_hash MUST be a 'sha256:<64hex>' string "
                "from dataflow.ml.hash(); got "
                f"{self.dataset_hash!r}"
            )
        if not isinstance(self.actor_id, str) or not self.actor_id:
            raise ValueError("TrainingContext.actor_id MUST be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly representation (payload-safe).

        The dataset hash is already a fingerprint (``sha256:<64hex>``),
        so it is safe to emit verbatim. ``tenant_id`` is operational
        metadata, not classified data — safe to emit. ``actor_id`` and
        ``run_id`` are opaque identifiers.
        """
        return asdict(self)
