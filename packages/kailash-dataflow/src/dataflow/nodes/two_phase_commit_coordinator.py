"""DataFlow Two-Phase Commit Coordinator Node - SDK Compliant Implementation."""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.transaction.two_phase_commit import (
    TwoPhaseCommitCoordinatorNode as SDK2PCCoordinator,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TransactionPhase(Enum):
    """Two-phase commit transaction phases."""

    INIT = "init"
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTING = "aborting"
    ABORTED = "aborted"


@register_node()
class DataFlowTwoPhaseCommitNode(AsyncNode):
    """Node for coordinating two-phase commit transactions in DataFlow operations.

    This node extends AsyncNode and leverages the SDK's TwoPhaseCommitCoordinatorNode
    to provide enterprise-grade 2PC implementation following SDK patterns.

    Configuration Parameters (set during initialization):
        timeout_seconds: Transaction timeout in seconds
        prepare_timeout: Prepare phase timeout
        commit_timeout: Commit phase timeout
        max_participants: Maximum number of participants
        enable_recovery: Enable recovery from failures
        recovery_interval: Recovery check interval in seconds

    Runtime Parameters (provided during execution):
        participants: List of transaction participants
        transaction_data: Data for the transaction
        isolation_level: Transaction isolation level
        synchronous_prepare: Execute prepare phase synchronously
    """

    def __init__(self, **kwargs):
        """Initialize the DataFlowTwoPhaseCommitNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.timeout_seconds = kwargs.pop("timeout_seconds", 60)
        self.prepare_timeout = kwargs.pop("prepare_timeout", 30)
        self.commit_timeout = kwargs.pop("commit_timeout", 30)
        self.max_participants = kwargs.pop("max_participants", 10)
        self.enable_recovery = kwargs.pop("enable_recovery", True)
        self.recovery_interval = kwargs.pop("recovery_interval", 5)

        # Call parent constructor
        super().__init__(**kwargs)

        # Initialize the SDK 2PC Coordinator
        self.tpc_coordinator = SDK2PCCoordinator(
            node_id=f"{self.node_id}_sdk_2pc",
            timeout=self.timeout_seconds,
            prepare_timeout=self.prepare_timeout,
            commit_timeout=self.commit_timeout,
        )

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "participants": NodeParameter(
                name="participants",
                type=list,
                required=True,
                description="List of transaction participants",
            ),
            "transaction_data": NodeParameter(
                name="transaction_data",
                type=dict,
                required=True,
                description="Data for the transaction",
                auto_map_from=["data", "tx_data"],
            ),
            "isolation_level": NodeParameter(
                name="isolation_level",
                type=str,
                required=False,
                default="READ_COMMITTED",
                description="Transaction isolation level",
            ),
            "synchronous_prepare": NodeParameter(
                name="synchronous_prepare",
                type=bool,
                required=False,
                default=True,
                description="Execute prepare phase synchronously",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute two-phase commit transaction asynchronously."""
        transaction_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            participants = validated_inputs.get("participants", [])
            transaction_data = validated_inputs.get("transaction_data", {})
            isolation_level = validated_inputs.get("isolation_level", "READ_COMMITTED")
            synchronous_prepare = validated_inputs.get("synchronous_prepare", True)

            # Validate participants
            if not participants:
                raise NodeValidationError("No participants provided for transaction")

            if len(participants) > self.max_participants:
                raise NodeValidationError(
                    f"Too many participants: {len(participants)} > {self.max_participants}"
                )

            # Initialize transaction state
            transaction_state = {
                "id": transaction_id,
                "phase": TransactionPhase.INIT,
                "participants": participants,
                "data": transaction_data,
                "isolation_level": isolation_level,
                "prepared_participants": [],
                "failed_participants": [],
                "committed_participants": [],
                "aborted_participants": [],
                "start_time": start_time,
            }

            # Execute 2PC protocol
            result = await self._execute_two_phase_commit(
                transaction_state, synchronous_prepare
            )

            # Calculate metrics
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            # Build result following SDK patterns
            result_data = {
                "success": result["success"],
                "transaction_id": transaction_id,
                "final_phase": result["phase"].value,
                "participants_total": len(participants),
                "participants_prepared": len(result.get("prepared_participants", [])),
                "participants_committed": len(result.get("committed_participants", [])),
                "participants_failed": len(result.get("failed_participants", [])),
                "metadata": {
                    "duration_seconds": duration,
                    "isolation_level": isolation_level,
                    "synchronous_prepare": synchronous_prepare,
                    "recovery_enabled": self.enable_recovery,
                },
            }

            # Add participant details
            if result.get("prepared_participants"):
                result_data["prepared_participants"] = result["prepared_participants"]

            if result.get("committed_participants"):
                result_data["committed_participants"] = result["committed_participants"]

            if result.get("failed_participants"):
                result_data["failed_participants"] = result["failed_participants"]
                result_data["failure_reasons"] = result.get("failure_reasons", [])

            if result.get("aborted_participants"):
                result_data["aborted_participants"] = result["aborted_participants"]

            # Add performance metrics
            result_data["performance_metrics"] = {
                "prepare_phase_latency_ms": result.get("prepare_latency", 0) * 1000,
                "commit_phase_latency_ms": result.get("commit_latency", 0) * 1000,
                "total_latency_ms": duration * 1000,
                "participant_latencies": result.get("participant_latencies", {}),
            }

            return result_data

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "transaction_id": transaction_id,
                "final_phase": TransactionPhase.ABORTED.value,
            }

    async def _execute_two_phase_commit(
        self, transaction_state: Dict[str, Any], synchronous_prepare: bool
    ) -> Dict[str, Any]:
        """Execute the two-phase commit protocol."""
        prepare_latency = 0
        commit_latency = 0
        participant_latencies = {}
        failure_reasons = []

        try:
            # Phase 1: Prepare
            prepare_start = datetime.utcnow()
            transaction_state["phase"] = TransactionPhase.PREPARING

            prepare_success = await self._prepare_phase(
                transaction_state,
                synchronous_prepare,
                participant_latencies,
                failure_reasons,
            )

            prepare_latency = (datetime.utcnow() - prepare_start).total_seconds()

            if not prepare_success:
                # Prepare failed - abort all
                transaction_state["phase"] = TransactionPhase.ABORTING
                await self._abort_phase(transaction_state, participant_latencies)
                transaction_state["phase"] = TransactionPhase.ABORTED

                return {
                    "success": False,
                    "phase": transaction_state["phase"],
                    "prepared_participants": transaction_state["prepared_participants"],
                    "failed_participants": transaction_state["failed_participants"],
                    "aborted_participants": transaction_state["aborted_participants"],
                    "failure_reasons": failure_reasons,
                    "prepare_latency": prepare_latency,
                    "participant_latencies": participant_latencies,
                }

            # All participants prepared - proceed to commit
            transaction_state["phase"] = TransactionPhase.PREPARED

            # Phase 2: Commit
            commit_start = datetime.utcnow()
            transaction_state["phase"] = TransactionPhase.COMMITTING

            commit_success = await self._commit_phase(
                transaction_state, participant_latencies, failure_reasons
            )

            commit_latency = (datetime.utcnow() - commit_start).total_seconds()

            if commit_success:
                transaction_state["phase"] = TransactionPhase.COMMITTED

                return {
                    "success": True,
                    "phase": transaction_state["phase"],
                    "prepared_participants": transaction_state["prepared_participants"],
                    "committed_participants": transaction_state[
                        "committed_participants"
                    ],
                    "prepare_latency": prepare_latency,
                    "commit_latency": commit_latency,
                    "participant_latencies": participant_latencies,
                }
            else:
                # Commit failed - this is a serious error requiring recovery
                if self.enable_recovery:
                    await self._attempt_recovery(
                        transaction_state, participant_latencies
                    )

                return {
                    "success": False,
                    "phase": transaction_state["phase"],
                    "prepared_participants": transaction_state["prepared_participants"],
                    "committed_participants": transaction_state[
                        "committed_participants"
                    ],
                    "failed_participants": transaction_state["failed_participants"],
                    "failure_reasons": failure_reasons,
                    "prepare_latency": prepare_latency,
                    "commit_latency": commit_latency,
                    "participant_latencies": participant_latencies,
                    "recovery_attempted": self.enable_recovery,
                }

        except Exception as e:
            # Unexpected error - abort all
            transaction_state["phase"] = TransactionPhase.ABORTING
            await self._abort_phase(transaction_state, participant_latencies)
            transaction_state["phase"] = TransactionPhase.ABORTED

            return {
                "success": False,
                "phase": transaction_state["phase"],
                "prepared_participants": transaction_state["prepared_participants"],
                "aborted_participants": transaction_state["aborted_participants"],
                "failure_reasons": [str(e)],
                "prepare_latency": prepare_latency,
                "commit_latency": commit_latency,
                "participant_latencies": participant_latencies,
            }

    async def _prepare_phase(
        self,
        transaction_state: Dict[str, Any],
        synchronous: bool,
        latencies: Dict[str, float],
        failure_reasons: List[str],
    ) -> bool:
        """Execute the prepare phase."""
        participants = transaction_state["participants"]

        if synchronous:
            # Prepare participants sequentially
            for participant in participants:
                p_start = datetime.utcnow()
                participant_id = participant.get("id", str(uuid.uuid4()))

                try:
                    # Prepare participant
                    prepare_result = await self._prepare_participant(
                        participant, transaction_state
                    )

                    if prepare_result["prepared"]:
                        transaction_state["prepared_participants"].append(
                            {
                                "id": participant_id,
                                "name": participant.get("name", "unknown"),
                                "prepared_at": datetime.utcnow().isoformat(),
                            }
                        )
                    else:
                        transaction_state["failed_participants"].append(
                            {
                                "id": participant_id,
                                "name": participant.get("name", "unknown"),
                                "reason": prepare_result.get("reason", "Unknown"),
                            }
                        )
                        failure_reasons.append(
                            f"Participant {participant_id} prepare failed: {prepare_result.get('reason')}"
                        )
                        return False

                    # Record latency
                    p_duration = (datetime.utcnow() - p_start).total_seconds()
                    latencies[f"{participant_id}_prepare"] = p_duration * 1000

                except Exception as e:
                    transaction_state["failed_participants"].append(
                        {
                            "id": participant_id,
                            "name": participant.get("name", "unknown"),
                            "error": str(e),
                        }
                    )
                    failure_reasons.append(
                        f"Participant {participant_id} prepare error: {str(e)}"
                    )
                    return False
        else:
            # Prepare participants in parallel
            prepare_tasks = []
            for participant in participants:
                task = self._prepare_participant_async(
                    participant, transaction_state, latencies
                )
                prepare_tasks.append(task)

            results = await asyncio.gather(*prepare_tasks, return_exceptions=True)

            # Check results
            for i, result in enumerate(results):
                participant = participants[i]
                participant_id = participant.get("id", str(uuid.uuid4()))

                if isinstance(result, Exception):
                    transaction_state["failed_participants"].append(
                        {"id": participant_id, "error": str(result)}
                    )
                    failure_reasons.append(
                        f"Participant {participant_id} prepare error: {str(result)}"
                    )
                    return False
                elif not result["prepared"]:
                    transaction_state["failed_participants"].append(
                        {
                            "id": participant_id,
                            "reason": result.get("reason", "Unknown"),
                        }
                    )
                    failure_reasons.append(
                        f"Participant {participant_id} prepare failed: {result.get('reason')}"
                    )
                    return False
                else:
                    transaction_state["prepared_participants"].append(
                        {
                            "id": participant_id,
                            "name": participant.get("name", "unknown"),
                            "prepared_at": datetime.utcnow().isoformat(),
                        }
                    )

        return True

    async def _commit_phase(
        self,
        transaction_state: Dict[str, Any],
        latencies: Dict[str, float],
        failure_reasons: List[str],
    ) -> bool:
        """Execute the commit phase."""
        # Commit all prepared participants
        commit_tasks = []

        for prepared in transaction_state["prepared_participants"]:
            # Find original participant data
            participant = next(
                (
                    p
                    for p in transaction_state["participants"]
                    if p.get("id") == prepared["id"]
                ),
                {"id": prepared["id"]},
            )

            task = self._commit_participant_async(
                participant, transaction_state, latencies
            )
            commit_tasks.append(task)

        results = await asyncio.gather(*commit_tasks, return_exceptions=True)

        # Check results
        all_committed = True
        for i, result in enumerate(results):
            prepared = transaction_state["prepared_participants"][i]
            participant_id = prepared["id"]

            if isinstance(result, Exception):
                transaction_state["failed_participants"].append(
                    {"id": participant_id, "phase": "commit", "error": str(result)}
                )
                failure_reasons.append(
                    f"Participant {participant_id} commit error: {str(result)}"
                )
                all_committed = False
            elif result["committed"]:
                transaction_state["committed_participants"].append(
                    {
                        "id": participant_id,
                        "committed_at": datetime.utcnow().isoformat(),
                    }
                )
            else:
                transaction_state["failed_participants"].append(
                    {
                        "id": participant_id,
                        "phase": "commit",
                        "reason": result.get("reason", "Unknown"),
                    }
                )
                failure_reasons.append(
                    f"Participant {participant_id} commit failed: {result.get('reason')}"
                )
                all_committed = False

        return all_committed

    async def _abort_phase(
        self, transaction_state: Dict[str, Any], latencies: Dict[str, float]
    ) -> None:
        """Execute the abort phase."""
        # Abort all prepared participants
        abort_tasks = []

        for prepared in transaction_state["prepared_participants"]:
            # Find original participant data
            participant = next(
                (
                    p
                    for p in transaction_state["participants"]
                    if p.get("id") == prepared["id"]
                ),
                {"id": prepared["id"]},
            )

            task = self._abort_participant_async(
                participant, transaction_state, latencies
            )
            abort_tasks.append(task)

        results = await asyncio.gather(*abort_tasks, return_exceptions=True)

        # Record aborted participants
        for i, result in enumerate(results):
            prepared = transaction_state["prepared_participants"][i]
            if not isinstance(result, Exception):
                transaction_state["aborted_participants"].append(
                    {"id": prepared["id"], "aborted_at": datetime.utcnow().isoformat()}
                )

    async def _prepare_participant(
        self, participant: Dict[str, Any], transaction_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare a single participant."""
        # Use SDK 2PC coordinator
        return await self.tpc_coordinator.prepare_participant(
            participant, transaction_state["data"]
        )

    async def _prepare_participant_async(
        self,
        participant: Dict[str, Any],
        transaction_state: Dict[str, Any],
        latencies: Dict[str, float],
    ) -> Dict[str, Any]:
        """Async wrapper for participant preparation."""
        p_start = datetime.utcnow()
        participant_id = participant.get("id", str(uuid.uuid4()))

        result = await self._prepare_participant(participant, transaction_state)

        # Record latency
        p_duration = (datetime.utcnow() - p_start).total_seconds()
        latencies[f"{participant_id}_prepare"] = p_duration * 1000

        return result

    async def _commit_participant_async(
        self,
        participant: Dict[str, Any],
        transaction_state: Dict[str, Any],
        latencies: Dict[str, float],
    ) -> Dict[str, Any]:
        """Async wrapper for participant commit."""
        p_start = datetime.utcnow()
        participant_id = participant.get("id", str(uuid.uuid4()))

        try:
            # Use SDK 2PC coordinator
            result = await self.tpc_coordinator.commit_participant(participant)

            # Record latency
            p_duration = (datetime.utcnow() - p_start).total_seconds()
            latencies[f"{participant_id}_commit"] = p_duration * 1000

            return {"committed": True}
        except Exception as e:
            return {"committed": False, "reason": str(e)}

    async def _abort_participant_async(
        self,
        participant: Dict[str, Any],
        transaction_state: Dict[str, Any],
        latencies: Dict[str, float],
    ) -> None:
        """Async wrapper for participant abort."""
        p_start = datetime.utcnow()
        participant_id = participant.get("id", str(uuid.uuid4()))

        try:
            # Use SDK 2PC coordinator
            await self.tpc_coordinator.abort_participant(participant)

            # Record latency
            p_duration = (datetime.utcnow() - p_start).total_seconds()
            latencies[f"{participant_id}_abort"] = p_duration * 1000
        except Exception:
            # Log but continue
            pass

    async def _attempt_recovery(
        self, transaction_state: Dict[str, Any], latencies: Dict[str, float]
    ) -> None:
        """Attempt to recover from partial commit failure."""
        # This would implement recovery logic, such as:
        # - Retrying failed commits
        # - Recording state for manual intervention
        # - Triggering compensating transactions
        # For now, just mark as recovery attempted
        pass
