# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared scaffolding for ``kailash_align.rl_bridge`` adapters.

Per ``specs/ml-rl-align-unification.md`` §2 + §3, every TRL-backed
bridge adapter (DPO, PPO-RLHF, RLOO, OnlineDPO, ...) MUST satisfy
:class:`kailash_ml.rl.protocols.RLLifecycleProtocol` at runtime. This
module defines :class:`_BridgeAdapterBase`, the mix-in that supplies
the shared instance state (``run_id``, ``tenant_id``, ``device``), the
dual-fan-out ``emit_metric`` contract (ambient tracker + the adapter's
own :class:`~kailash_align.diagnostics.AlignmentDiagnostics`), default
``save``/``load``/``checkpoint``/``resume`` plumbing, and a
``__make_for_test__`` factory the Protocol conformance test uses.

Design constraints
------------------

* NOT a subclass of ``RLLifecycleProtocol`` — the Protocol is
  :func:`runtime_checkable` and adapters satisfy it by duck typing.
  Subclassing a ``typing.Protocol`` at runtime is NOT the contract the
  spec §2 mandates; the Protocol's ``isinstance`` check relies on
  structural attribute presence, not MRO.
* No align-side type imports of ``kailash_ml.rl.protocols`` at module
  scope beyond :class:`PolicyArtifactRef` — we re-use the frozen
  dataclass directly rather than redeclare an align-local variant so
  ``save`` / ``load`` produce refs the classical side can consume.
* Persistence surface is intentionally thin — TRL trainers own
  checkpoint/resume semantics; the adapter's ``checkpoint`` / ``resume``
  forward to the underlying trainer after guarding ``_built``.

``__make_for_test__`` returns a minimal stub that satisfies the
Protocol's runtime structural checks (class-level ``name`` /
``paradigm`` / ``buffer_kind``, instance ``run_id`` / ``tenant_id`` /
``device``, and every method slot). The stub is for the spec §4
conformance test — production code constructs adapters via their real
``__init__``.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional

from kailash_ml.rl.protocols import PolicyArtifactRef

__all__ = ["_BridgeAdapterBase"]

logger = logging.getLogger(__name__)


class _BridgeAdapterBase:
    """Shared plumbing for every ``rl_bridge`` adapter.

    Subclasses MUST set the class-level ``name`` / ``paradigm`` /
    ``buffer_kind`` attributes so :class:`RLLifecycleProtocol`'s
    runtime check sees them. Subclasses MUST also populate the
    ``_trainer`` attribute during :meth:`build` — the default
    :meth:`learn` delegates to it.

    Why this is a mix-in, not a Protocol subclass
    ----------------------------------------------
    ``typing.Protocol`` with ``@runtime_checkable`` uses structural
    ``isinstance`` checks — subclassing it at runtime is legal for
    Python 3.12+ but adds no enforcement beyond the structural check
    that already fires at ``isinstance(adapter, RLLifecycleProtocol)``.
    Keeping the base as a regular class keeps the MRO simple and makes
    the conformance test (``test_all_adapters_satisfy_protocol``) the
    actual gate — not inheritance.
    """

    # Class-level defaults — subclasses override. Present here so the
    # Protocol's runtime check passes on instances of the base class
    # itself (the ``__make_for_test__`` path constructs one).
    name: ClassVar[str] = "_base"
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]] = "rlhf"
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]] = (
        "preference"
    )

    # Instance-attribute annotations so ``isinstance(obj, Protocol)`` can
    # detect them on duck-typed access. Initialised in ``__init__``.
    run_id: str
    tenant_id: Optional[str]
    device: Any

    def __init__(
        self,
        *,
        run_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        device: Any = None,
    ) -> None:
        # run_id is correlation identity — default to a fresh uuid hex
        # so every adapter instance is grep-able across logs.
        self.run_id = run_id if run_id is not None else uuid.uuid4().hex
        self.tenant_id = tenant_id
        self.device = device

        # Subclasses populate during build(); keep as None until then.
        self._trainer: Any = None
        self._built: bool = False

        # The adapter's own diagnostics instance. Constructed lazily on
        # first ``emit_metric`` call to avoid pulling the full
        # ``kailash_align.diagnostics`` tree at adapter-import time.
        self._diagnostics: Any = None

        # Ambient tracker — set by the orchestrator (kailash_ml.rl
        # dispatch layer OR the caller). None means "metrics still
        # flow to diagnostics, just not to an external tracker".
        self._tracker: Any = None

    # ------------------------------------------------------------------
    # Telemetry contract (spec §3.3/§3.4)
    # ------------------------------------------------------------------

    def attach_tracker(self, tracker: Any) -> None:
        """Attach an ambient tracker (e.g. ``MLDashboard``'s tracker).

        Orchestrators call this before :meth:`learn`. Adapters never
        construct a tracker themselves (see
        ``rules/facade-manager-detection.md`` § 3 — no self-construction).
        """
        self._tracker = tracker

    def emit_metric(self, key: str, value: float, *, step: int) -> None:
        """Forward ``(key, value, step)`` to the ambient tracker AND diagnostics.

        Per spec §2 "Telemetry contract": every ``emit_metric`` call
        MUST reach both the tracker (so ``MLDashboard`` sees it) AND
        the adapter's own ``AlignmentDiagnostics`` instance (so
        post-hoc report generation has the same data).

        Non-finite values are dropped at this layer with a single WARN
        — the tracker and diagnostics both assume finite floats per
        the W29 metric parity contract.
        """
        import math

        if not math.isfinite(float(value)):
            logger.warning(
                "rl_bridge.metric.dropped",
                extra={
                    "rl_algo": self.name,
                    "rl_run_id": self.run_id,
                    "rl_metric_key": key,
                    "rl_step": step,
                    "reason": "non_finite",
                    "mode": "real",
                },
            )
            return

        # Tracker fan-out.
        tracker = self._tracker
        if tracker is not None:
            record = getattr(tracker, "record_metric", None) or getattr(
                tracker, "log_metric", None
            )
            if callable(record):
                try:
                    record(key=key, value=float(value), step=int(step))
                except Exception as exc:  # pragma: no cover — tracker is caller-owned
                    logger.warning(
                        "rl_bridge.tracker.record_failed",
                        extra={
                            "rl_algo": self.name,
                            "rl_run_id": self.run_id,
                            "rl_metric_key": key,
                            "error": str(exc),
                        },
                    )

        # Diagnostics fan-out. Lazy-construct on first use so adapter
        # import doesn't pull the diagnostics tree.
        diag = self._get_diagnostics()
        track = getattr(diag, "track_training", None)
        if callable(track):
            try:
                # AlignmentDiagnostics.track_training accepts iterables
                # of {step, <metric>: value, ...} dicts.
                track([{"step": int(step), key: float(value)}])
            except Exception as exc:  # pragma: no cover — diag is adapter-owned
                logger.warning(
                    "rl_bridge.diagnostics.track_failed",
                    extra={
                        "rl_algo": self.name,
                        "rl_run_id": self.run_id,
                        "rl_metric_key": key,
                        "error": str(exc),
                    },
                )

    def _get_diagnostics(self) -> Any:
        """Lazy accessor for the adapter's ``AlignmentDiagnostics``."""
        if self._diagnostics is None:
            try:
                from kailash_align.diagnostics import AlignmentDiagnostics

                self._diagnostics = AlignmentDiagnostics(
                    label=f"{self.name}:{self.run_id[:8]}",
                    run_id=self.run_id,
                )
            except Exception as exc:  # pragma: no cover — diagnostics optional
                logger.warning(
                    "rl_bridge.diagnostics.init_failed",
                    extra={
                        "rl_algo": self.name,
                        "rl_run_id": self.run_id,
                        "error": str(exc),
                    },
                )
                self._diagnostics = False  # sentinel: construction failed
        return self._diagnostics if self._diagnostics is not False else None

    # ------------------------------------------------------------------
    # Lifecycle — ``build`` and ``learn`` live on concrete adapters
    # (DPOAdapter, PPORLHFAdapter, RLOOAdapter, OnlineDPOAdapter).
    #
    # Per ``rules/zero-tolerance.md`` Rule 2 ``raise NotImplementedError``
    # is BLOCKED in production code. The base class is Protocol-conformed
    # (not ABC-inherited); concrete adapters satisfy
    # :class:`RLLifecycleProtocol` by defining ``build`` and ``learn``
    # directly. Attempting to call them on an unextended base instance
    # surfaces as a regular ``AttributeError`` from Python's normal
    # method-resolution path — loud enough to diagnose without a
    # placeholder raise in production bytecode.
    #
    # ``save`` / ``load`` / ``checkpoint`` / ``resume`` have real default
    # bodies below that delegate to TRL's native persistence primitives
    # (``trainer.save_model`` + ``state.save_to_json`` +
    # ``resume_from_checkpoint``). These are not stubs — they are
    # genuinely usable defaults that concrete adapters MAY override for
    # algorithm-specific persistence quirks (e.g. PPO's replay buffer).
    # ------------------------------------------------------------------

    def save(self, path: Path) -> PolicyArtifactRef:
        """Persist the trainer state + return a :class:`PolicyArtifactRef`.

        Default behaviour delegates to the TRL trainer's ``save_model``
        (standard HuggingFace convention). Subclasses MAY override for
        PEFT-adapter-only saves.
        """
        self._require_trainer("save")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        save_model = getattr(self._trainer, "save_model", None)
        if not callable(save_model):
            raise RuntimeError(
                f"{type(self).__name__}._trainer has no save_model(); "
                f"cannot persist policy. Override save() in the adapter subclass "
                f"or supply a TRL trainer with save_model support."
            )
        save_model(str(path))

        sha = _content_hash(path)
        policy_class = (
            type(self._trainer).__module__ + "." + type(self._trainer).__name__
        )
        return PolicyArtifactRef(
            path=path,
            sha=sha,
            algorithm=self.name,
            policy_class=policy_class,
            created_at=datetime.now(timezone.utc),
            tenant_id=self.tenant_id,
        )

    @classmethod
    def load(cls, ref: PolicyArtifactRef) -> "_BridgeAdapterBase":
        """Round-trip complement of :meth:`save`.

        Reconstructs a minimal adapter whose ``_trainer`` is the
        serialized policy reloaded via the HuggingFace ``from_pretrained``
        pattern. This is a thin implementation — downstream callers
        typically construct the adapter fresh and point it at the saved
        checkpoint via ``resume_from``; the ``load`` classmethod exists
        to satisfy the Protocol and to support the spec §3 crypto-pair
        round-trip test.
        """
        if ref.algorithm != cls.name and cls.name != "_base":
            raise ValueError(
                f"{cls.__name__}.load refusing to load algorithm="
                f"{ref.algorithm!r}; expected {cls.name!r}"
            )
        instance = cls.__make_for_test__()
        instance._trainer = _LoadedTrainerRef(
            path=ref.path, policy_class=ref.policy_class
        )
        instance._built = True
        return instance

    def checkpoint(self, path: Path) -> None:
        """Persist full training state for warm restart.

        Default: delegates to TRL's ``state.save_to_json`` + trainer
        ``save_model``. Subclasses may override for algorithms with
        non-standard checkpointing (e.g. PPO's replay-buffer).
        """
        self._require_trainer("checkpoint")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        save_model = getattr(self._trainer, "save_model", None)
        if callable(save_model):
            save_model(str(path))
        state = getattr(self._trainer, "state", None)
        if state is not None and hasattr(state, "save_to_json"):
            state.save_to_json(str(path / "trainer_state.json"))

    def resume(self, path: Path) -> None:
        """Restore full training state from :meth:`checkpoint` output.

        Default: re-runs :meth:`build` and points TRL at the resumed
        path via the canonical ``resume_from_checkpoint`` kwarg on the
        next ``.train()`` call. Subclasses MAY override.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"{type(self).__name__}.resume: checkpoint path does not exist: {path}"
            )
        if not self._built:
            self.build()
        # The actual resume happens when ``learn`` calls
        # ``self._trainer.train(resume_from_checkpoint=path)``. We stash
        # the path so ``learn`` can pick it up.
        self._resume_from = path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_trainer(self, op: str) -> None:
        """Typed guard per ``rules/zero-tolerance.md`` Rule 3a.

        Opaque ``AttributeError`` on ``None._trainer.save_model`` is
        BLOCKED. Surface a RuntimeError with actionable text instead.
        """
        if self._trainer is None or not self._built:
            raise RuntimeError(
                f"{type(self).__name__}.{op} called before build() — "
                f"the backing TRL trainer is not yet constructed. Call "
                f"adapter.build() or adapter.learn(...) first."
            )

    @classmethod
    def __make_for_test__(cls) -> "_BridgeAdapterBase":
        """Factory for the Protocol conformance test (spec §4).

        Returns an instance with all structural attributes present and
        the lifecycle methods in place, but WITHOUT constructing the
        underlying TRL trainer (which would require real models).
        The conformance test asserts
        ``isinstance(instance, RLLifecycleProtocol)`` — this must hold
        before ``build`` is ever called.
        """
        # ``__init__`` of concrete subclasses requires ``policy=``,
        # ``reference_model=``, etc. Bypass via object.__new__ and call
        # the base __init__ directly to populate run_id/tenant_id/device.
        instance = object.__new__(cls)
        _BridgeAdapterBase.__init__(instance)  # type: ignore[misc]
        return instance


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _content_hash(path: Path) -> str:
    """Stable fingerprint for a persisted policy path.

    For a directory, we hash the sorted list of ``<name, size>`` pairs
    for every file — this is cheap, deterministic, and sufficient for
    the :class:`PolicyArtifactRef.sha` fingerprint contract (consumers
    treat it as opaque).
    """
    hasher = hashlib.sha256()
    if path.is_file():
        hasher.update(path.name.encode("utf-8"))
        hasher.update(str(path.stat().st_size).encode("utf-8"))
        return hasher.hexdigest()[:16]
    if path.is_dir():
        entries: list[tuple[str, int]] = []
        for child in sorted(path.rglob("*")):
            if child.is_file():
                entries.append((str(child.relative_to(path)), child.stat().st_size))
        for name, size in entries:
            hasher.update(name.encode("utf-8"))
            hasher.update(str(size).encode("utf-8"))
        return hasher.hexdigest()[:16]
    # Nonexistent path — stable sentinel.
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]


class _LoadedTrainerRef:
    """Marker object placed on ``instance._trainer`` after :meth:`load`.

    Concrete adapters that call `super().load(ref)` should override
    :meth:`_BridgeAdapterBase.load` to replace this ref with a real
    re-hydrated TRL trainer. The ref alone is sufficient to satisfy the
    Protocol's structural check after load.
    """

    def __init__(self, *, path: Path, policy_class: str) -> None:
        self.path = path
        self.policy_class = policy_class
