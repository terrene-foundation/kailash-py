"""
Booking Agent - Doctor Matching and Selection

Extends BaseAgent with BookingSignature for matching patients with
specialists and handling the booking selection process.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


class DoctorDatabase(Protocol):
    """
    Protocol for doctor database backends.

    Implementations should provide methods to query available doctors
    based on symptoms, preferences, and availability.
    """

    async def find_specialists(
        self,
        symptoms: List[str],
        preferences: Dict[str, Any],
        exclude_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Find specialists matching patient criteria.

        Args:
            symptoms: List of patient symptoms
            preferences: Patient preferences (time, gender, telehealth, location)
            exclude_ids: Doctor IDs to exclude (rejected doctors)

        Returns:
            List of doctor dicts with id, name, specialty, available_slots, etc.
        """
        ...


class MockDoctorDatabase:
    """
    Mock doctor database for testing and demos.

    Provides a realistic set of doctors with availability for testing
    the booking flow without a real database.
    """

    def __init__(self):
        self._doctors = [
            {
                "id": "dr-chen-001",
                "name": "Dr. Sarah Chen",
                "specialty": "Orthopedics",
                "gender": "female",
                "location": "Downtown Medical Center",
                "telehealth": True,
                "rating": 4.9,
                "available_slots": [
                    "2024-01-15T09:00:00",
                    "2024-01-15T14:00:00",
                    "2024-01-16T10:00:00",
                ],
                "symptom_match": [
                    "back pain",
                    "joint pain",
                    "stiffness",
                    "sports injury",
                ],
            },
            {
                "id": "dr-smith-002",
                "name": "Dr. Michael Smith",
                "specialty": "Orthopedics",
                "gender": "male",
                "location": "Westside Orthopedic Clinic",
                "telehealth": False,
                "rating": 4.7,
                "available_slots": [
                    "2024-01-15T11:00:00",
                    "2024-01-17T09:00:00",
                    "2024-01-17T15:00:00",
                ],
                "symptom_match": ["back pain", "spine issues", "neck pain"],
            },
            {
                "id": "dr-patel-003",
                "name": "Dr. Priya Patel",
                "specialty": "Physical Medicine",
                "gender": "female",
                "location": "East Bay Rehabilitation Center",
                "telehealth": True,
                "rating": 4.8,
                "available_slots": [
                    "2024-01-16T08:00:00",
                    "2024-01-16T13:00:00",
                    "2024-01-18T10:00:00",
                ],
                "symptom_match": [
                    "back pain",
                    "muscle pain",
                    "chronic pain",
                    "rehabilitation",
                ],
            },
            {
                "id": "dr-johnson-004",
                "name": "Dr. Robert Johnson",
                "specialty": "Neurology",
                "gender": "male",
                "location": "Central Neurology Associates",
                "telehealth": True,
                "rating": 4.6,
                "available_slots": [
                    "2024-01-18T09:00:00",
                    "2024-01-19T11:00:00",
                ],
                "symptom_match": ["headache", "numbness", "tingling", "migraine"],
            },
            {
                "id": "dr-lee-005",
                "name": "Dr. Jennifer Lee",
                "specialty": "Rheumatology",
                "gender": "female",
                "location": "Bay Area Rheumatology",
                "telehealth": True,
                "rating": 4.9,
                "available_slots": [
                    "2024-01-17T10:00:00",
                    "2024-01-17T14:00:00",
                    "2024-01-19T09:00:00",
                ],
                "symptom_match": ["joint pain", "swelling", "arthritis", "stiffness"],
            },
        ]

    async def find_specialists(
        self,
        symptoms: List[str],
        preferences: Dict[str, Any],
        exclude_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find matching specialists based on symptoms and preferences.

        Filters doctors by:
        - Symptom match (at least one symptom matches)
        - Gender preference (if specified)
        - Telehealth preference (if specified)
        - Excludes rejected doctors

        Args:
            symptoms: Patient symptoms
            preferences: Patient preferences
            exclude_ids: Doctors to exclude

        Returns:
            Filtered and scored list of doctors
        """
        exclude_ids = exclude_ids or []
        results = []

        symptoms_lower = [s.lower() for s in symptoms]

        for doctor in self._doctors:
            # Skip excluded doctors
            if doctor["id"] in exclude_ids:
                continue

            # Check symptom match
            symptom_match_count = sum(
                1
                for s in symptoms_lower
                for m in doctor["symptom_match"]
                if s in m or m in s
            )

            if symptom_match_count == 0:
                continue

            # Check gender preference
            gender_pref = preferences.get("gender_preference")
            if gender_pref and doctor["gender"] != gender_pref.lower():
                continue

            # Check telehealth preference
            telehealth_pref = preferences.get("telehealth_ok")
            if telehealth_pref is True and not doctor["telehealth"]:
                # Patient wants telehealth but doctor doesn't offer it
                continue

            # Filter time preferences (simplified)
            time_pref = preferences.get("time_preference", "").lower()
            available = doctor["available_slots"].copy()

            if time_pref == "morning":
                available = [
                    s for s in available if "T0" in s or "T10" in s or "T11" in s
                ]
            elif time_pref == "afternoon":
                available = [
                    s
                    for s in available
                    if "T1" in s and "T10" not in s and "T11" not in s
                ]

            if not available:
                continue

            # Calculate match score
            match_score = (
                symptom_match_count * 0.4
                + doctor["rating"] / 5.0 * 0.3
                + (0.3 if doctor["telehealth"] else 0.1)
            )

            # Generate match reason
            match_reason = (
                f"Specializes in conditions related to {', '.join(symptoms[:2])}"
            )
            if doctor["telehealth"]:
                match_reason += "; offers telehealth appointments"

            results.append(
                {
                    **doctor,
                    "available_slots": available,
                    "match_score": match_score,
                    "match_reason": match_reason,
                }
            )

        # Sort by match score
        results.sort(key=lambda x: x["match_score"], reverse=True)

        return results[:5]  # Return top 5 matches


@dataclass
class BookingAgentConfig:
    """
    Configuration for BookingAgent.

    Attributes:
        llm_provider: LLM provider to use
        model: Model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response
    """

    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1200


class BookingAgent:
    """
    Agent for doctor booking in healthcare referral.

    Matches patients with appropriate specialists based on their symptoms
    and preferences, presents options, and handles the selection process.

    Key Features:
    - Tracks rejected doctors to avoid re-suggesting
    - Presents at most 3 options per turn
    - Explains why each doctor is a good match

    Example:
        >>> config = BookingAgentConfig(llm_provider="ollama", model="llama3.2:3b")
        >>> agent = BookingAgent(config)
        >>> result = await agent.find_doctors(
        ...     patient_message="Show me options for back specialists",
        ...     symptoms=["back pain", "stiffness"],
        ...     preferences={"time_preference": "morning"},
        ...     rejected_doctors=[]
        ... )
        >>> print(len(result["suggested_doctors"]))
        3
    """

    def __init__(
        self,
        config: Optional[BookingAgentConfig] = None,
        doctor_database: Optional[DoctorDatabase] = None,
    ):
        """
        Initialize BookingAgent.

        Args:
            config: Agent configuration
            doctor_database: Doctor database backend (defaults to MockDoctorDatabase)
        """
        from examples.journey.healthcare_referral.signatures.booking import (
            BookingSignature,
        )
        from kaizen.core.base_agent import BaseAgent

        self._config = config or BookingAgentConfig()
        self._doctor_db = doctor_database or MockDoctorDatabase()

        # Create internal BaseAgent
        self._agent = BaseAgent(
            config=self._config,
            signature=BookingSignature(),
        )

    async def find_doctors(
        self,
        patient_message: str,
        symptoms: List[str],
        preferences: Dict[str, Any],
        rejected_doctors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Find matching doctors and present options.

        Args:
            patient_message: Patient's booking-related message
            symptoms: Patient symptoms from intake
            preferences: Patient preferences from intake
            rejected_doctors: Previously rejected doctor IDs

        Returns:
            Dict containing:
            - suggested_doctors: List of matching doctors
            - selected_doctor: Selected doctor (if selection made)
            - selected_slot: Selected time slot (if selection made)
            - new_rejected_doctors: Newly rejected doctor IDs
            - response: Agent's response
            - booking_complete: Whether booking is finalized
        """
        rejected_doctors = rejected_doctors or []

        # Get available doctors from database
        available = await self._doctor_db.find_specialists(
            symptoms=symptoms,
            preferences=preferences,
            exclude_ids=rejected_doctors,
        )

        # Run agent with available doctors context
        result = await self._agent.run_async(
            patient_message=patient_message,
            symptoms=symptoms,
            preferences=preferences,
            rejected_doctors=rejected_doctors,
            available_doctors=available[:3],  # Present at most 3
        )

        # Merge rejected doctors
        new_rejected = result.get("new_rejected_doctors", [])
        if new_rejected:
            result["rejected_doctors"] = rejected_doctors + new_rejected

        return result

    def find_doctors_sync(
        self,
        patient_message: str,
        symptoms: List[str],
        preferences: Dict[str, Any],
        rejected_doctors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous version of find_doctors.

        For use in non-async contexts.
        """
        import asyncio

        return asyncio.run(
            self.find_doctors(
                patient_message=patient_message,
                symptoms=symptoms,
                preferences=preferences,
                rejected_doctors=rejected_doctors,
            )
        )

    # BaseAgent interface methods for Journey compatibility
    async def run_async(self, **kwargs) -> Dict[str, Any]:
        """Run agent asynchronously (Journey interface)."""
        return await self.find_doctors(
            patient_message=kwargs.get("message", kwargs.get("patient_message", "")),
            symptoms=kwargs.get("symptoms", []),
            preferences=kwargs.get("preferences", {}),
            rejected_doctors=kwargs.get("rejected_doctors", []),
        )

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run agent synchronously (Journey interface)."""
        return self.find_doctors_sync(
            patient_message=kwargs.get("message", kwargs.get("patient_message", "")),
            symptoms=kwargs.get("symptoms", []),
            preferences=kwargs.get("preferences", {}),
            rejected_doctors=kwargs.get("rejected_doctors", []),
        )


__all__ = [
    "BookingAgent",
    "BookingAgentConfig",
    "DoctorDatabase",
    "MockDoctorDatabase",
]
