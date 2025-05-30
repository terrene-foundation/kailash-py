"""
MCP API Wrapper for HMI project using Kailash SDK.

This module provides a wrapper for the MCP API that is used throughout the HMI workflow.
"""

import datetime
import json
import os
import urllib.parse
from typing import Any, Dict, Optional

import requests
from examples.project_hmi.adapted.shared import (
    NRIC_Type,
)

# API Endpoints and Keys
HMI_ONE_API_BASE_URL = "https://hmi-nonprod-vpc-gwy.azure-api.net/la/hmi"
HMI_ONE_API_KEY = "ad615a33114b4df1afdd1e0f5d40be3b"  # Ocp-Apim-Subscription-Key
HMI_ONE_API_REFAPP = "hmimedical"
HMI_ONE_API_REFDOMAIN = "hmimedical"

MHC_AUTH_URL = "https://login.microsoftonline.com/624f3a01-8226-480a-8a46-15e5d0f5affb/oauth2/v2.0/token"
MHC_API_BASE_URL = "https://mhc-benefit-lookup-uat-2.azure-api.net/api"
MHC_CLIENT_ID = "db51f6f9-c018-42af-ad2f-54b30a5ad0eb"
MHC_CLIENT_SECRET = "nvl8Q~a5hhVC-myzpZOy18ND70FD.O8R9mi7ldmN"
MHC_SCOPE = "api://4f097ac2-ed87-4e66-825f-e9a30de50683/.default"
MHC_GRANT_TYPE = "client_credentials"

SPECIALIST_RANKING_API_URL = "https://prod-74.southeastasia.logic.azure.com/workflows/83d1d2a53ff34e8090a11020f3452666/triggers/manual/paths/invoke"
SPECIALIST_RANKING_API_PARAMS = {
    "api-version": "2016-06-01",
    "sp": "/triggers/manual/run",
    "sv": "1.0",
    "sig": "EmU5h6FAUbdC1CJtXy7L3Q6-YX1qMV2e_VQBubUMMOc",
}


class HmiMcpWrapper:
    """Wrapper for the HMI and MCP APIs.

    This class provides methods for interacting with the various APIs used in the HMI workflow.
    """

    def __init__(self):
        self._mhc_access_token: Optional[str] = None

    def _get_hmi_one_headers(self) -> Dict[str, str]:
        """Get the headers required for HMI One API calls."""
        return {
            "ocp-apim-subscription-key": HMI_ONE_API_KEY,
            "Refapp": HMI_ONE_API_REFAPP,
            "Refdomain": HMI_ONE_API_REFDOMAIN,
            "Content-Type": "application/json",
        }

    def _get_mhc_headers(self, requires_auth: bool = True) -> Dict[str, str]:
        """Get the headers required for MHC API calls."""
        headers = {"Content-Type": "application/json"}
        if requires_auth:
            if not self._mhc_access_token:
                self.get_mhc_access_token()  # Attempt to get token if not available
            if (
                self._mhc_access_token
            ):  # Check again if token was successfully retrieved
                headers["Authorization"] = f"Bearer {self._mhc_access_token}"
            else:
                print("Error: MHC Access Token not available for authorized request.")
        return headers

    # --- HMI One API Methods ---
    def get_doctors_list(
        self,
        page_index: int = 1,
        page_size: int = 1000,
        sort_by: str = "name",
        system_id: str = "",
    ) -> Dict[str, Any]:
        """
        Retrieves a list of doctors from the HMI One API.
        Args:
            page_index: Page index for pagination.
            page_size: Number of results per page.
            sort_by: Field to sort by (e.g., "name").
            system_id: System ID to filter by (e.g., "starmed", "eec", "harly", "rmcc", "rsh"). Empty for all.

        Returns:
            Dict containing doctor information that can be parsed into List[DoctorInfo]
        """
        payload = {
            "endpt": "vpcdoctors",
            "entities": "ALL",
            "payload": {
                "pgIdx": page_index,
                "pageSize": page_size,
                "sortby": sort_by,
                "systemId": system_id,
            },
        }
        try:
            response = requests.post(
                HMI_ONE_API_BASE_URL, headers=self._get_hmi_one_headers(), json=payload
            )
            response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
            }
        except json.JSONDecodeError:
            return {
                "error": "Failed to decode JSON response",
                "response_text": response.text,
            }

    def get_doctor_available_slots(
        self, doctor_given_id: str, system_id: str
    ) -> Dict[str, Any]:
        """
        Retrieves available time slots for a specific doctor from the HMI One API.
        If MOCK_SLOTS_FOR_DOCTOR_ID environment variable is set and matches doctor_given_id,
        returns a mock response.

        Args:
            doctor_given_id: The given ID of the doctor.
            system_id: System ID (e.g., "starmed").

        Returns:
            Dict containing available slots information that can be parsed into List[SlotInfo]
        """
        mock_doctor_id = os.environ.get("MOCK_SLOTS_FOR_DOCTOR_ID")
        if mock_doctor_id and doctor_given_id == mock_doctor_id:
            print(
                f"DEBUG MCP_WRAPPER: Returning MOCK slots for doctor_id: {doctor_given_id}"
            )
            now = datetime.datetime.now()
            slot_start_time = (now + datetime.timedelta(days=2)).replace(
                hour=15, minute=0, second=0, microsecond=0
            )
            slot_end_time = slot_start_time + datetime.timedelta(minutes=15)

            mock_response = {
                "slots": [
                    {
                        "appointmentStartTime": slot_start_time.isoformat(),
                        "appointmentEndTime": slot_end_time.isoformat(),
                        "appointmentDate": slot_start_time.strftime("%d %b %Y"),
                        "appointmentTime": slot_start_time.strftime("%I:%M %p"),
                        "location": "HMI Mocked Clinic (Farrer Park)",
                        "colorcode": "mocked",
                        "timeslotinterval": 15,
                    },
                    # Example of a second slot
                    {
                        "appointmentStartTime": (
                            slot_start_time + datetime.timedelta(minutes=30)
                        ).isoformat(),
                        "appointmentEndTime": (
                            slot_end_time + datetime.timedelta(minutes=30)
                        ).isoformat(),
                        "appointmentDate": slot_start_time.strftime("%d %b %Y"),
                        "appointmentTime": (
                            slot_start_time + datetime.timedelta(minutes=30)
                        ).strftime("%I:%M %p"),
                        "location": "HMI Mocked Clinic (Farrer Park)",
                    },
                ],
                "message": "Successfully retrieved mocked slots.",
                "status": "success",
            }
            return mock_response

        payload = {
            "endpt": "doctoravailableslots",
            "entities": "hmimedical",
            "payload": {"doctorgivenid": doctor_given_id, "systemId": system_id},
        }
        try:
            response = requests.post(
                HMI_ONE_API_BASE_URL, headers=self._get_hmi_one_headers(), json=payload
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
                "response_text": response.text if "response" in locals() else None,
            }
        except json.JSONDecodeError:
            return {
                "error": "Failed to decode JSON response",
                "response_text": response.text,
            }

    def manage_in_person_appointment(
        self,
        # Required parameters (no default values)
        doctor_given_id: str,
        system_id: str,
        patient_name: str,
        patient_email: str,
        patient_id: str,
        nric: str,
        nric_type: NRIC_Type,  # NRIC, PASSPORT, or FIN
        mobile_number: str,
        dob: str,  # YYYY-MM-DD
        nationality: str,
        country_code: str,  # e.g., "+65"
        enable_email_updates: bool,
        pdpa_consent: bool,
        privacy_policy: bool,
        # Optional parameters (with default values)
        appointment_type: str = "inperson",
        uploaded_files: str = "",
        cc_name: str = "",
        agent_name: str = "",
        schedule_type: Optional[
            str
        ] = None,  # null/omitted for booking, "RESCH" for reschedule, "CANCEL" for cancel
        # Booking & Reschedule specific
        appointment_start_time: Optional[str] = None,  # ISO 8601 for booking/reschedule
        appointment_end_time: Optional[str] = None,  # ISO 8601 for booking/reschedule
        appointment_date: Optional[str] = None,  # "DD MMM YYYY" e.g., "10 JUN 2025"
        appointment_time: Optional[str] = None,  # "H:MM AM/PM" e.g., "9:30 AM"
        subject: Optional[str] = None,
        notes: Optional[str] = None,  # Medical notes
        doctor_code: Optional[str] = None,
        doctor_name: Optional[str] = None,
        clinic_location: Optional[str] = None,  # Booking only
        clinic_location_code: Optional[str] = None,  # Booking only
        additional_notes: Optional[str] = None,
        medical_condition: Optional[
            str
        ] = None,  # Required for eec (booking/reschedule)
        purpose: Optional[str] = None,  # Required for eec (booking/reschedule/cancel)
        mysid_no: Optional[
            str
        ] = None,  # Required for Malaysian nationality (booking/reschedule)
        mysid_type: Optional[
            str
        ] = None,  # Required for Malaysian nationality (booking/reschedule)
        passport: Optional[
            str
        ] = None,  # Required for Malaysia entities for non-Malaysians (booking/reschedule)
        passport_exp: Optional[
            str
        ] = None,  # Required for Malaysia entities for non-Malaysians (booking/reschedule)
        # Reschedule & Cancel specific
        existing_appointment_id: Optional[
            str
        ] = None,  # 'id' field from booking response
        # Cancel specific
        returning_patient: Optional[str] = None,
        reason_for_cancellation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Manages in-person appointments (book, reschedule, cancel) via the HMI One API.

        Returns:
            Dict containing booking information that relates to BookingContext model
        """
        payload_data = {
            "appointmenttype": appointment_type,
            "doctorgivenid": doctor_given_id,
            "systemid": system_id,
            "patientname": patient_name,
            "patientemail": patient_email,
            "patientid": patient_id,
            "nric": nric,
            "nrictype": nric_type,
            "mobilenumber": mobile_number,
            "dob": dob,
            "nationality": nationality,
            "countrycode": country_code,
            "enableemailupdates": enable_email_updates,
            "pdpaconsent": pdpa_consent,
            "privacypolicy": privacy_policy,
            "uploadedfiles": uploaded_files,
            "ccname": cc_name,
            "agentname": agent_name,
        }

        if schedule_type:
            payload_data["scheduletype"] = schedule_type

        # Common for Booking and Reschedule
        if schedule_type is None or schedule_type == "RESCH":
            if appointment_start_time:
                payload_data["appointmentstarttime"] = appointment_start_time
            if appointment_end_time:
                payload_data["appointmentendtime"] = appointment_end_time
            if appointment_date:
                payload_data["appointmentdate"] = appointment_date
            if appointment_time:
                payload_data["appointmenttime"] = appointment_time
            if subject:
                payload_data["subject"] = subject
            if notes:
                payload_data["notes"] = notes
            if doctor_code:
                payload_data["doctorcode"] = doctor_code
            if doctor_name:
                payload_data["doctorname"] = doctor_name
            if additional_notes:
                payload_data["additionalnotes"] = additional_notes
            if medical_condition and system_id == "eec":
                payload_data["medicalcondition"] = medical_condition
            if purpose and system_id == "eec":
                payload_data["purpose"] = purpose
            if mysid_no and nationality.lower() == "malaysian":
                payload_data["mysidno"] = mysid_no
            if mysid_type and nationality.lower() == "malaysian":
                payload_data["mysidtype"] = mysid_type
            if (
                passport
                and "malaysia" in system_id.lower()
                and nationality.lower() != "malaysian"
            ):
                payload_data["passport"] = passport
            if (
                passport_exp
                and "malaysia" in system_id.lower()
                and nationality.lower() != "malaysian"
            ):
                payload_data["passportexp"] = passport_exp

        # Booking specific
        if schedule_type is None:
            if clinic_location:
                payload_data["cliniclocation"] = clinic_location
            if clinic_location_code:
                payload_data["cliniclocationcode"] = clinic_location_code

        # Reschedule specific
        if schedule_type == "RESCH":
            if existing_appointment_id:
                payload_data["id"] = existing_appointment_id
                payload_data["appointmentid"] = existing_appointment_id

        # Cancel specific
        if schedule_type == "CANCEL":
            if existing_appointment_id:
                payload_data["id"] = existing_appointment_id
                payload_data["appointmentid"] = existing_appointment_id
            if appointment_start_time:
                payload_data["appointmentstarttime"] = appointment_start_time
            if appointment_end_time:
                payload_data["appointmentendtime"] = appointment_end_time
            if appointment_date:
                payload_data["appointmentdate"] = appointment_date
            if appointment_time:
                payload_data["appointmenttime"] = appointment_time
            if doctor_code:
                payload_data["doctorcode"] = doctor_code
            if doctor_name:
                payload_data["doctorname"] = doctor_name
            if purpose and system_id == "eec":
                payload_data["purpose"] = purpose
            if returning_patient:
                payload_data["returningpatient"] = returning_patient
            if reason_for_cancellation:
                payload_data["reasonforcancellation"] = reason_for_cancellation

        request_body = {
            "endpt": "inpersonappt",
            "entities": "hmimedical",
            "payload": payload_data,
        }

        try:
            response = requests.post(
                HMI_ONE_API_BASE_URL,
                headers=self._get_hmi_one_headers(),
                json=request_body,
            )
            response.raise_for_status()
            # Cancellation returns "success" as plain text
            if schedule_type == "CANCEL" and response.text == "success":
                return {"status": "success"}
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
                "response_text": response.text if "response" in locals() else None,
            }
        except json.JSONDecodeError:
            # Handle cases where response is not JSON but not the "success" string for cancel
            if schedule_type == "CANCEL":  # If it was a cancel, but not "success" text
                return {
                    "error": "Cancellation failed or unexpected response",
                    "response_text": response.text,
                }
            return {
                "error": "Failed to decode JSON response",
                "response_text": response.text,
            }

    # --- MHC Insurance API Methods ---
    def get_mhc_access_token(self) -> Optional[str]:
        """
        Obtains an access token for the MHC Insurance API.
        The token is stored internally for subsequent MHC API calls.
        Returns:
            The access token string if successful, None otherwise.
        """
        payload = {
            "client_id": MHC_CLIENT_ID,
            "scope": MHC_SCOPE,
            "client_secret": MHC_CLIENT_SECRET,
            "grant_type": MHC_GRANT_TYPE,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = requests.post(MHC_AUTH_URL, headers=headers, data=payload)
            response.raise_for_status()
            token_data = response.json()
            self._mhc_access_token = token_data.get("access_token")
            if not self._mhc_access_token:
                print(
                    f"Error: 'access_token' not found in MHC auth response. Response: {token_data}"
                )
                return None
            return self._mhc_access_token
        except requests.exceptions.RequestException as e:
            print(
                f"Error getting MHC access token: {e}. Status: {response.status_code if 'response' in locals() else 'N/A'}. Response text: {response.text if 'response' in locals() else 'N/A'}"
            )
            self._mhc_access_token = None
            return None
        except json.JSONDecodeError:
            print(
                f"Error decoding JSON from MHC auth response. Response text: {response.text}"
            )
            self._mhc_access_token = None
            return None

    def get_patient_coverage(self, nric: str) -> Dict[str, Any]:
        """
        Retrieves a patient's coverage and balances from the MHC Insurance API using their NRIC.
        Args:
            nric: Patient's NRIC.

        Returns:
            Dict containing patient coverage information that relates to PatientDetails model
        """
        if not self._mhc_access_token:
            token = self.get_mhc_access_token()
            if not token:
                return {
                    "error": "Failed to obtain MHC access token. Cannot proceed with get_patient_coverage."
                }

        payload = {"nric": nric}
        url = f"{MHC_API_BASE_URL}/coverage"
        try:
            response = requests.post(url, headers=self._get_mhc_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # If token expired (e.g. 401), try to refresh and retry once.
            if response.status_code == 401:
                print(
                    "MHC token might have expired. Attempting to refresh and retry..."
                )
                self.get_mhc_access_token()  # Refresh token
                if self._mhc_access_token:
                    try:
                        response_retry = requests.post(
                            url, headers=self._get_mhc_headers(), json=payload
                        )
                        response_retry.raise_for_status()
                        return response_retry.json()
                    except requests.exceptions.RequestException as e_retry:
                        return {
                            "error": f"Retry failed: {str(e_retry)}",
                            "status_code": (
                                response_retry.status_code
                                if "response_retry" in locals()
                                else None
                            ),
                        }
                    except json.JSONDecodeError:
                        return {
                            "error": "Retry failed: Failed to decode JSON response",
                            "response_text": response_retry.text,
                        }
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
            }
        except json.JSONDecodeError:
            return {
                "error": "Failed to decode JSON response",
                "response_text": response.text,
            }

    def get_member_details(self, nric: str, dob: str) -> Dict[str, Any]:
        """
        Retrieves a patient's benefit policies and verifies their Date of Birth (YYYYMMDD) from the MHC Insurance API.
        An empty response indicates an incorrect DOB.
        Args:
            nric: Patient's NRIC.
            dob: Patient's Date of Birth (format YYYYMMDD).

        Returns:
            Dict containing patient member details that relates to PatientDetails model
        """
        if not self._mhc_access_token:
            token = self.get_mhc_access_token()
            if not token:
                return {
                    "error": "Failed to obtain MHC access token. Cannot proceed with get_member_details."
                }

        payload = {"nric": nric, "dob": dob}
        url = f"{MHC_API_BASE_URL}/member/details"
        try:
            response = requests.post(url, headers=self._get_mhc_headers(), json=payload)
            response.raise_for_status()
            # According to docs, an empty response means incorrect DOB.
            # A successful response with data should be parsable as JSON.
            # If response.content is empty, response.json() will raise an error.
            if not response.content:  # Checks if the response body is empty
                return {
                    "status": "Incorrect DOB or no data found",
                    "nric": nric,
                    "dob": dob,
                }
            return response.json()
        except requests.exceptions.RequestException as e:
            if response.status_code == 401:  # Unauthorized
                print(
                    "MHC token might have expired. Attempting to refresh and retry..."
                )
                self.get_mhc_access_token()  # Refresh token
                if self._mhc_access_token:
                    try:
                        response_retry = requests.post(
                            url, headers=self._get_mhc_headers(), json=payload
                        )
                        response_retry.raise_for_status()
                        if not response_retry.content:
                            return {
                                "status": "Incorrect DOB or no data found (after retry)",
                                "nric": nric,
                                "dob": dob,
                            }
                        return response_retry.json()
                    except requests.exceptions.RequestException as e_retry:
                        return {
                            "error": f"Retry failed: {str(e_retry)}",
                            "status_code": (
                                response_retry.status_code
                                if "response_retry" in locals()
                                else None
                            ),
                        }
                    except json.JSONDecodeError:
                        return {
                            "error": "Retry failed: Failed to decode JSON response",
                            "response_text": response_retry.text,
                        }
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
            }
        except json.JSONDecodeError:
            # This case implies non-empty response that isn't valid JSON.
            return {
                "error": "Failed to decode JSON response, but response was not empty.",
                "response_text": response.text,
            }

    def get_member_clinic_list(self, nric: str, dob: str) -> Dict[str, Any]:
        """
        Provides a list of clinics covered under the patient's policy and specialists available.
        Requires NRIC and DOB (YYYYMMDD) for verification via MHC Insurance API.
        Args:
            nric: Patient's NRIC.
            dob: Patient's Date of Birth (format YYYYMMDD).

        Returns:
            Dict containing list of clinics that can be parsed to relevant models
        """
        if not self._mhc_access_token:
            token = self.get_mhc_access_token()
            if not token:
                return {
                    "error": "Failed to obtain MHC access token. Cannot proceed with get_member_clinic_list."
                }

        payload = {"nric": nric, "dob": dob}
        url = f"{MHC_API_BASE_URL}/member/clinics"
        try:
            response = requests.post(url, headers=self._get_mhc_headers(), json=payload)
            response.raise_for_status()
            # Similar to get_member_details, an empty response might indicate DOB mismatch or no clinics.
            # The documentation implies a JSON array is expected on success.
            if not response.content:
                return {
                    "status": "Incorrect DOB or no clinics found",
                    "nric": nric,
                    "dob": dob,
                }
            return response.json()
        except requests.exceptions.RequestException as e:
            if response.status_code == 401:  # Unauthorized
                print(
                    "MHC token might have expired. Attempting to refresh and retry..."
                )
                self.get_mhc_access_token()  # Refresh token
                if self._mhc_access_token:
                    try:
                        response_retry = requests.post(
                            url, headers=self._get_mhc_headers(), json=payload
                        )
                        response_retry.raise_for_status()
                        if not response_retry.content:
                            return {
                                "status": "Incorrect DOB or no clinics found (after retry)",
                                "nric": nric,
                                "dob": dob,
                            }
                        return response_retry.json()
                    except requests.exceptions.RequestException as e_retry:
                        return {
                            "error": f"Retry failed: {str(e_retry)}",
                            "status_code": (
                                response_retry.status_code
                                if "response_retry" in locals()
                                else None
                            ),
                        }
                    except json.JSONDecodeError:
                        return {
                            "error": "Retry failed: Failed to decode JSON response",
                            "response_text": response_retry.text,
                        }
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
            }
        except json.JSONDecodeError:
            return {
                "error": "Failed to decode JSON response, but response was not empty.",
                "response_text": response.text,
            }

    # --- Specialist Ranking API Tool ---
    def get_specialist_ranking(
        self,
        specialty: Optional[str] = None,
        sort_by: Optional[str] = None,  # e.g., "rank"
        sort_order: Optional[str] = None,  # e.g., "asc" or "desc"
    ) -> Dict[str, Any]:
        """
        Retrieves a ranking of specialists, with optional filtering by specialty and sorting.
        Args:
            specialty: Filter results by medical specialty (e.g., "cardiology").
            sort_by: Field to sort the results by (e.g., "rank").
            sort_order: Order of sorting ("asc" or "desc").

        Returns:
            Dict containing specialist ranking information that relates to DoctorInfo models
        """
        params = SPECIALIST_RANKING_API_PARAMS.copy()  # Start with fixed params
        if specialty:
            params["specialty"] = specialty
        if sort_by:
            params["sort_by"] = sort_by
        if sort_order:
            params["sort_order"] = sort_order

        # ***** DEBUG PRINT *****
        full_url = f"{SPECIALIST_RANKING_API_URL}?{urllib.parse.urlencode(params)}"
        print(f"DEBUG MCP_WRAPPER (get_specialist_ranking): Calling URL: {full_url}")
        # ***** END DEBUG PRINT *****

        try:
            response = requests.get(SPECIALIST_RANKING_API_URL, params=params)
            # ***** DEBUG PRINT *****
            print(
                f"DEBUG MCP_WRAPPER (get_specialist_ranking): Response Status Code: {response.status_code}"
            )
            print(
                f"DEBUG MCP_WRAPPER (get_specialist_ranking): Response Text: {response.text[:500]}..."
            )  # Print first 500 chars
            # ***** END DEBUG PRINT *****
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(
                f"DEBUG MCP_WRAPPER (get_specialist_ranking): RequestException: {str(e)}"
            )  # DEBUG
            return {
                "error": str(e),
                "status_code": response.status_code if "response" in locals() else None,
                "response_text": response.text if "response" in locals() else None,
            }
        except json.JSONDecodeError as e:
            print(
                f"DEBUG MCP_WRAPPER (get_specialist_ranking): JSONDecodeError: {str(e)}"
            )  # DEBUG
            return {
                "error": "Failed to decode JSON response",
                "response_text": response.text,
            }
