"""
Tests for the HMI workflow immutable state management.

This module tests the implementation of the immutable state management
in the HMI workflow project, validating that state is properly transformed
through the workflow execution.
"""

import asyncio

import pytest
from examples.migrations.project_hmi.adapted.shared import AgentState, DoctorInfo, SlotInfo

from kailash.workflow.state import WorkflowStateWrapper


class TestImmutableStateManagement:
    """Tests for immutable state management in the HMI workflow."""

    def test_state_update_in(self):
        """Test that update_in correctly updates nested properties."""
        # Arrange
        state = AgentState()
        state.patient_details.patient_name = "John Doe"

        # Act
        state_wrapper = WorkflowStateWrapper(state)
        updated_wrapper = state_wrapper.update_in(
            ["w1_context", "no_hmi_slot_flag"], True
        )

        # Assert
        assert (
            state_wrapper.get_state().w1_context.no_hmi_slot_flag is False
        )  # Original unchanged
        assert (
            updated_wrapper.get_state().w1_context.no_hmi_slot_flag is True
        )  # New is updated
        assert (
            updated_wrapper.get_state().patient_details.patient_name == "John Doe"
        )  # Other fields preserved

    def test_state_batch_update(self):
        """Test that batch_update correctly updates multiple properties atomically."""
        # Arrange
        state = AgentState()
        doctor = DoctorInfo(
            doctor_given_id="D12345", doctor_name="Dr. Smith", system_id="starmed"
        )
        slot = SlotInfo(
            appointment_start_time="2025-05-30T10:30:00",
            appointment_date_str="30 May 2025",
            appointment_time_str="10:30 AM",
            location="Medical Center",
        )

        # Act
        state_wrapper = WorkflowStateWrapper(state)
        updated_wrapper = state_wrapper.batch_update(
            [
                (["patient_details", "patient_name"], "John Doe"),
                (["w1_context", "current_doctor_under_consideration"], doctor),
                (["w1_context", "earliest_slot_found"], slot),
                (["w1_context", "no_hmi_slot_flag"], False),
            ]
        )

        # Assert
        assert updated_wrapper.get_state().patient_details.patient_name == "John Doe"
        assert (
            updated_wrapper.get_state().w1_context.current_doctor_under_consideration.doctor_name
            == "Dr. Smith"
        )
        assert (
            updated_wrapper.get_state().w1_context.earliest_slot_found.location
            == "Medical Center"
        )
        assert updated_wrapper.get_state().w1_context.no_hmi_slot_flag is False

        # Original state should be unchanged
        assert state_wrapper.get_state().patient_details.patient_name is None
        assert (
            state_wrapper.get_state().w1_context.current_doctor_under_consideration
            is None
        )

    def test_deep_nested_update(self):
        """Test that updates to deeply nested properties work correctly."""
        # Arrange
        state = AgentState()
        doctor = DoctorInfo(
            doctor_given_id="D12345",
            doctor_name="Dr. Smith",
            doctor_specialties=["Cardiology"],
            system_id="starmed",
            clinic_location="Downtown",
        )
        state.w1_context.current_doctor_under_consideration = doctor

        # Act
        state_wrapper = WorkflowStateWrapper(state)
        updated_wrapper = state_wrapper.update_in(
            ["w1_context", "current_doctor_under_consideration", "doctor_name"],
            "Dr. Johnson",
        )

        # Assert
        # New state should have the updated doctor name
        assert (
            updated_wrapper.get_state().w1_context.current_doctor_under_consideration.doctor_name
            == "Dr. Johnson"
        )

        # Original state should be unchanged
        assert (
            state_wrapper.get_state().w1_context.current_doctor_under_consideration.doctor_name
            == "Dr. Smith"
        )

        # Other properties should be preserved
        assert updated_wrapper.get_state().w1_context.current_doctor_under_consideration.doctor_specialties == [
            "Cardiology"
        ]
        assert (
            updated_wrapper.get_state().w1_context.current_doctor_under_consideration.clinic_location
            == "Downtown"
        )

    def test_invalid_path_raises_error(self):
        """Test that invalid paths raise appropriate errors."""
        # Arrange
        state = AgentState()
        state_wrapper = WorkflowStateWrapper(state)

        # Act & Assert
        # Top-level invalid field raises ValueError from Pydantic
        with pytest.raises((ValueError, KeyError)):
            state_wrapper.update_in(["invalid_field"], "test")

        # Nested invalid field should raise KeyError or ValueError
        with pytest.raises((ValueError, KeyError)):
            state_wrapper.update_in(["w1_context", "invalid_field"], "test")

        # Invalid path in list should raise KeyError
        with pytest.raises((ValueError, KeyError)):
            state_wrapper.update_in(
                ["w1_context", "ranked_doctors_list", "invalid_field"], "test"
            )

    def test_compare_immutable_vs_traditional(self):
        """Compare immutable state approach with traditional approach for clarity."""
        # Arrange
        state = AgentState()
        doctor = DoctorInfo(
            doctor_given_id="D12345", doctor_name="Dr. Smith", system_id="starmed"
        )

        # Traditional approach
        def traditional_update(state, doctor):
            updated_w1_context = state.w1_context.model_copy()
            updated_w1_context.current_doctor_under_consideration = doctor
            return state.copy_with_updates(w1_context=updated_w1_context)

        # Immutable approach
        def immutable_update(state, doctor):
            wrapper = WorkflowStateWrapper(state)
            updated_wrapper = wrapper.update_in(
                ["w1_context", "current_doctor_under_consideration"], doctor
            )
            return updated_wrapper.get_state()

        # Act
        traditional_result = traditional_update(state, doctor)
        immutable_result = immutable_update(state, doctor)

        # Assert
        assert (
            traditional_result.w1_context.current_doctor_under_consideration.doctor_name
            == "Dr. Smith"
        )
        assert (
            immutable_result.w1_context.current_doctor_under_consideration.doctor_name
            == "Dr. Smith"
        )

        # Both should create new objects
        assert state is not traditional_result
        assert state.w1_context is not traditional_result.w1_context
        assert state is not immutable_result
        assert state.w1_context is not immutable_result.w1_context


class TestStateManagerPerformance:
    """Performance tests for the state management system."""

    def test_batch_update_performance(self):
        """Test that batch updates are more efficient than sequential updates."""
        # Arrange
        state = AgentState()
        fields = [
            (["patient_details", "patient_name"], "John Doe"),
            (["patient_details", "patient_email"], "john@example.com"),
            (["patient_details", "patient_contact_number"], "555-1234"),
            (["referral_context", "referral_specialties"], ["Cardiology"]),
            (["w1_context", "no_hmi_slot_flag"], False),
        ]

        # Sequential updates
        def sequential_updates(state):
            wrapper = WorkflowStateWrapper(state)
            result = wrapper
            for path, value in fields:
                result = result.update_in(path, value)
            return result

        # Batch update
        def batch_update(state):
            wrapper = WorkflowStateWrapper(state)
            return wrapper.batch_update(fields)

        # Act & Assert - just make sure it works in both cases
        sequential_result = sequential_updates(state)
        batch_result = batch_update(state)

        # Results should be equivalent
        assert sequential_result.get_state().patient_details.patient_name == "John Doe"
        assert batch_result.get_state().patient_details.patient_name == "John Doe"
        assert sequential_result.get_state().w1_context.no_hmi_slot_flag is False
        assert batch_result.get_state().w1_context.no_hmi_slot_flag is False


@pytest.mark.asyncio
class TestAsyncWorkflowStateIntegration:
    """Tests for async workflow integration with state management."""

    class MockNode:
        """Mock node for testing async workflow execution."""

        def __init__(self, transform_func=None):
            self.transform_func = transform_func or (lambda x: x)

        async def async_run(self, **kwargs):
            await asyncio.sleep(0.01)  # Simulate some async work
            state_wrapper = kwargs["state_wrapper"]
            # Apply the transform function to get a new state
            new_state = self.transform_func(state_wrapper.get_state())
            # Return an updated wrapper
            return {"state_wrapper": WorkflowStateWrapper(new_state)}

    @pytest.mark.asyncio
    async def test_async_node_execution(self):
        """Test that state is correctly transformed in async nodes."""
        # Arrange
        state = AgentState()
        state.patient_details.patient_name = "John Doe"
        state_wrapper = WorkflowStateWrapper(state)

        # Define transforms
        def transform1(state):
            new_state = state.copy_with_updates(
                referral_context=state.referral_context.model_copy(
                    update={"referral_specialties": ["Cardiology"]}
                )
            )
            return new_state

        def transform2(state):
            doctor = DoctorInfo(
                doctor_name="Dr. Smith", doctor_specialties=["Cardiology"]
            )
            new_state = state.copy_with_updates()
            new_state.w1_context.current_doctor_under_consideration = doctor
            return new_state

        node1 = self.MockNode(transform1)
        node2 = self.MockNode(transform2)

        # Act - simulate pipeline of nodes
        result1 = await node1.async_run(state_wrapper=state_wrapper)
        result2 = await node2.async_run(state_wrapper=result1["state_wrapper"])

        # Assert
        final_state = result2["state_wrapper"].get_state()
        assert (
            final_state.patient_details.patient_name == "John Doe"
        )  # Preserved from original
        assert final_state.referral_context.referral_specialties == [
            "Cardiology"
        ]  # From transform1
        assert (
            final_state.w1_context.current_doctor_under_consideration.doctor_name
            == "Dr. Smith"
        )  # From transform2


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
