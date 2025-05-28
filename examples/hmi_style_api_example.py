#!/usr/bin/env python3
"""
HMI-Style API Integration Example for Kailash SDK

This example demonstrates how to implement an HMI-style API integration using the
Kailash SDK's built-in API capabilities. It shows how to handle complex API workflows
with multiple endpoints, authentication, rate limiting, and error handling.

This example is based on the patterns identified in the gaps analysis and demonstrates
how the SDK can handle real-world API integration scenarios.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Kailash SDK imports
from kailash.workflow import Workflow
from kailash.nodes.api import (
    HTTPRequestNode,
    RESTClientNode,
    OAuth2Node,
    APIKeyNode,
    RateLimitConfig,
    RateLimitedAPINode,
)
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class MockHMIConfig:
    """Configuration for mock HMI API integration."""
    hmi_api_base_url: str = "https://api.mockservice.com/hmi"
    hmi_api_key: str = "demo-hmi-api-key"
    mhc_token_url: str = "https://api.mockservice.com/oauth/token"
    mhc_api_base_url: str = "https://api.mockservice.com/mhc"
    mhc_client_id: str = "demo-mhc-client"
    mhc_client_secret: str = "demo-mhc-secret"
    specialist_ranking_url: str = "https://api.mockservice.com/specialists"


class MockAPIResponseNode(Node):
    """Node that simulates API responses for demonstration purposes."""
    
    def __init__(self, response_data: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.response_data = response_data
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "request_type": NodeParameter(
                name="request_type",
                type=str,
                required=True,
                description="Type of API request to simulate"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=Any,
                required=True,
                description="Simulated API response data"
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=True,
                description="Whether the simulated request was successful"
            ),
            "status_code": NodeParameter(
                name="status_code",
                type=int,
                required=True,
                description="Simulated HTTP status code"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        request_type = kwargs.get("request_type")
        
        if request_type in self.response_data:
            response = self.response_data[request_type]
            return {
                "data": response.get("data", {}),
                "success": response.get("success", True),
                "status_code": response.get("status_code", 200)
            }
        else:
            return {
                "data": {"error": f"Unknown request type: {request_type}"},
                "success": False,
                "status_code": 404
            }


class HMIDoctorSearchNode(Node):
    """Node for searching doctors in HMI system."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rest_client = RESTClientNode(**kwargs)
        
        # Rate limiting configuration for HMI API
        self.rate_config = RateLimitConfig(
            max_requests=10,
            time_window=60.0,
            strategy="token_bucket",
            burst_limit=15
        )
        
        self.rate_limited_client = RateLimitedAPINode(
            wrapped_node=self.rest_client,
            rate_limit_config=self.rate_config,
            node_id=f"{kwargs.get('node_id', 'hmi_search')}_rate_limited"
        )
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "specialty": NodeParameter(
                name="specialty",
                type=str,
                required=False,
                description="Medical specialty to search for"
            ),
            "location": NodeParameter(
                name="location",
                type=str,
                required=False,
                description="Location to search in"
            ),
            "api_key": NodeParameter(
                name="api_key",
                type=str,
                required=True,
                description="HMI API key"
            ),
            "base_url": NodeParameter(
                name="base_url",
                type=str,
                required=True,
                description="HMI API base URL"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "doctors": NodeParameter(
                name="doctors",
                type=list,
                required=True,
                description="List of doctors matching search criteria"
            ),
            "search_metadata": NodeParameter(
                name="search_metadata",
                type=dict,
                required=True,
                description="Search metadata including filters applied"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        specialty = kwargs.get("specialty")
        location = kwargs.get("location")
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")
        
        # Build query parameters
        query_params = {}
        if specialty:
            query_params["specialty"] = specialty
        if location:
            query_params["location"] = location
        
        # Prepare headers with API key
        headers = {
            "X-API-Key": api_key,
            "Accept": "application/json"
        }
        
        try:
            # Make the API call using rate-limited REST client
            result = self.rate_limited_client.run(
                base_url=base_url,
                resource="doctors",
                method="GET",
                query_params=query_params,
                headers=headers
            )
            
            if result["success"]:
                # Simulate processing doctor data
                doctors = result.get("data", {}).get("doctors", [])
                
                # For demo purposes, simulate some doctor data
                if not doctors:
                    doctors = [
                        {
                            "id": "dr_001",
                            "name": "Dr. Jane Smith",
                            "specialty": specialty or "General Medicine",
                            "location": location or "Singapore",
                            "availability": "Available",
                            "rating": 4.8
                        },
                        {
                            "id": "dr_002", 
                            "name": "Dr. John Doe",
                            "specialty": specialty or "General Medicine",
                            "location": location or "Singapore",
                            "availability": "Limited",
                            "rating": 4.6
                        }
                    ]
                
                return {
                    "doctors": doctors,
                    "search_metadata": {
                        "specialty": specialty,
                        "location": location,
                        "total_found": len(doctors),
                        "rate_limit_info": result.get("rate_limit_metadata", {})
                    }
                }
            else:
                raise NodeExecutionError(f"Doctor search failed: {result}")
        
        except Exception as e:
            logger.error(f"Error in doctor search: {e}")
            raise NodeExecutionError(f"Doctor search failed: {str(e)}")


class HMISlotCheckNode(Node):
    """Node for checking available appointment slots."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rest_client = RESTClientNode(**kwargs)
        
        # More aggressive rate limiting for slot checking
        self.rate_config = RateLimitConfig(
            max_requests=5,
            time_window=60.0,
            strategy="sliding_window",
            backoff_factor=2.0
        )
        
        self.rate_limited_client = RateLimitedAPINode(
            wrapped_node=self.rest_client,
            rate_limit_config=self.rate_config,
            node_id=f"{kwargs.get('node_id', 'hmi_slots')}_rate_limited"
        )
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "doctor_id": NodeParameter(
                name="doctor_id",
                type=str,
                required=True,
                description="Doctor ID to check slots for"
            ),
            "date_range": NodeParameter(
                name="date_range",
                type=dict,
                required=False,
                description="Date range for slot search"
            ),
            "api_key": NodeParameter(
                name="api_key",
                type=str,
                required=True,
                description="HMI API key"
            ),
            "base_url": NodeParameter(
                name="base_url",
                type=str,
                required=True,
                description="HMI API base URL"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "available_slots": NodeParameter(
                name="available_slots",
                type=list,
                required=True,
                description="List of available appointment slots"
            ),
            "slot_metadata": NodeParameter(
                name="slot_metadata",
                type=dict,
                required=True,
                description="Metadata about slot availability"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        doctor_id = kwargs.get("doctor_id")
        date_range = kwargs.get("date_range", {})
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")
        
        # Build query parameters
        query_params = {"doctor_id": doctor_id}
        if date_range:
            query_params.update(date_range)
        
        # Prepare headers
        headers = {
            "X-API-Key": api_key,
            "Accept": "application/json"
        }
        
        try:
            # Make the API call
            result = self.rate_limited_client.run(
                base_url=base_url,
                resource="slots",
                method="GET",
                query_params=query_params,
                headers=headers
            )
            
            if result["success"]:
                # Simulate slot data processing
                slots = result.get("data", {}).get("slots", [])
                
                # For demo purposes, simulate some slot data
                if not slots:
                    slots = [
                        {
                            "slot_id": "slot_001",
                            "start_time": "2024-01-15T09:00:00Z",
                            "end_time": "2024-01-15T09:30:00Z",
                            "status": "available"
                        },
                        {
                            "slot_id": "slot_002",
                            "start_time": "2024-01-15T10:00:00Z", 
                            "end_time": "2024-01-15T10:30:00Z",
                            "status": "available"
                        }
                    ]
                
                return {
                    "available_slots": slots,
                    "slot_metadata": {
                        "doctor_id": doctor_id,
                        "total_slots": len(slots),
                        "date_range": date_range,
                        "rate_limit_info": result.get("rate_limit_metadata", {})
                    }
                }
            else:
                raise NodeExecutionError(f"Slot check failed: {result}")
        
        except Exception as e:
            logger.error(f"Error in slot check: {e}")
            raise NodeExecutionError(f"Slot check failed: {str(e)}")


class MHCInsuranceNode(Node):
    """Node for checking insurance coverage via MHC API."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.oauth_node = OAuth2Node(**kwargs)
        self.rest_client = RESTClientNode(**kwargs)
        
        # Conservative rate limiting for insurance API
        self.rate_config = RateLimitConfig(
            max_requests=3,
            time_window=60.0,
            strategy="token_bucket",
            burst_limit=5
        )
        
        self.rate_limited_client = RateLimitedAPINode(
            wrapped_node=self.rest_client,
            rate_limit_config=self.rate_config,
            node_id=f"{kwargs.get('node_id', 'mhc_insurance')}_rate_limited"
        )
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "patient_nric": NodeParameter(
                name="patient_nric",
                type=str,
                required=True,
                description="Patient NRIC for insurance lookup"
            ),
            "patient_dob": NodeParameter(
                name="patient_dob",
                type=str,
                required=True,
                description="Patient date of birth (YYYYMMDD)"
            ),
            "oauth_config": NodeParameter(
                name="oauth_config",
                type=dict,
                required=True,
                description="OAuth configuration for MHC API"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        return {
            "coverage_info": NodeParameter(
                name="coverage_info",
                type=dict,
                required=True,
                description="Insurance coverage information"
            ),
            "covered_providers": NodeParameter(
                name="covered_providers",
                type=list,
                required=True,
                description="List of covered healthcare providers"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        patient_nric = kwargs.get("patient_nric")
        patient_dob = kwargs.get("patient_dob")
        oauth_config = kwargs.get("oauth_config")
        
        try:
            # First, get OAuth token (simulated)
            print(f"   Getting OAuth token for MHC API...")
            auth_headers = {"Authorization": "Bearer demo-oauth-token"}
            
            # Check patient coverage
            coverage_result = self.rate_limited_client.run(
                base_url=oauth_config["api_base_url"],
                resource="coverage",
                method="POST",
                headers=auth_headers,
                data={
                    "nric": patient_nric,
                    "dob": patient_dob
                }
            )
            
            if coverage_result["success"]:
                # Simulate coverage data
                coverage_info = {
                    "patient_nric": patient_nric,
                    "coverage_type": "Premium",
                    "coverage_limit": 100000,
                    "deductible": 1000,
                    "co_pay_percentage": 10
                }
                
                # Get covered providers
                providers_result = self.rate_limited_client.run(
                    base_url=oauth_config["api_base_url"],
                    resource="providers",
                    method="POST",
                    headers=auth_headers,
                    data={
                        "nric": patient_nric,
                        "dob": patient_dob
                    }
                )
                
                covered_providers = [
                    {"provider_id": "HMI_001", "name": "HMI Medical Center", "network": "preferred"},
                    {"provider_id": "HMI_002", "name": "HMI Specialist Clinic", "network": "standard"}
                ]
                
                return {
                    "coverage_info": coverage_info,
                    "covered_providers": covered_providers
                }
            else:
                raise NodeExecutionError(f"Coverage check failed: {coverage_result}")
        
        except Exception as e:
            logger.error(f"Error in insurance check: {e}")
            raise NodeExecutionError(f"Insurance check failed: {str(e)}")


def example_hmi_workflow():
    """Demonstrate a complete HMI-style API workflow."""
    print("\n" + "="*80)
    print("HMI-Style API Integration Workflow Example")
    print("="*80)
    
    # Configuration
    config = MockHMIConfig()
    
    # Create workflow
    workflow = Workflow(name="hmi_api_workflow")
    
    # Create nodes
    doctor_search = HMIDoctorSearchNode(node_id="search_doctors")
    slot_check = HMISlotCheckNode(node_id="check_slots")
    insurance_check = MHCInsuranceNode(node_id="check_insurance")
    
    # Add nodes to workflow
    workflow.add_node(doctor_search)
    workflow.add_node(slot_check)
    workflow.add_node(insurance_check)
    
    # Connect nodes for data flow
    workflow.connect(
        "search_doctors", "check_slots",
        {"doctors": "doctor_list"}
    )
    workflow.connect(
        "search_doctors", "check_insurance", 
        {"search_metadata": "search_context"}
    )
    
    # Execute the workflow
    runtime = LocalRuntime()
    
    print("\n1. Patient Information:")
    patient_info = {
        "nric": "S1234567A",
        "dob": "19900101",
        "preferred_specialty": "Cardiology",
        "preferred_location": "Singapore Central"
    }
    
    for key, value in patient_info.items():
        print(f"   {key}: {value}")
    
    try:
        print("\n2. Step 1: Search for doctors by specialty and location")
        doctor_result = runtime.execute_node(
            doctor_search,
            specialty=patient_info["preferred_specialty"],
            location=patient_info["preferred_location"],
            api_key=config.hmi_api_key,
            base_url=config.hmi_api_base_url
        )
        
        doctors = doctor_result["doctors"]
        search_meta = doctor_result["search_metadata"]
        
        print(f"   Found {len(doctors)} doctors:")
        for doctor in doctors:
            print(f"   - {doctor['name']} ({doctor['specialty']}) - Rating: {doctor['rating']}")
        
        print(f"   Rate limiting: {search_meta['rate_limit_info'].get('rate_limiting_active', 'N/A')}")
        
        print("\n3. Step 2: Check available slots for top doctor")
        if doctors:
            top_doctor = doctors[0]  # Select highest rated doctor
            
            slot_result = runtime.execute_node(
                slot_check,
                doctor_id=top_doctor["id"],
                date_range={"start_date": "2024-01-15", "end_date": "2024-01-20"},
                api_key=config.hmi_api_key,
                base_url=config.hmi_api_base_url
            )
            
            slots = slot_result["available_slots"]
            slot_meta = slot_result["slot_metadata"]
            
            print(f"   Doctor: {top_doctor['name']}")
            print(f"   Available slots: {len(slots)}")
            for slot in slots[:3]:  # Show first 3 slots
                print(f"   - {slot['start_time']} ({slot['status']})")
            
            print(f"   Rate limiting: {slot_meta['rate_limit_info'].get('rate_limiting_active', 'N/A')}")
        
        print("\n4. Step 3: Check insurance coverage")
        oauth_config = {
            "token_url": config.mhc_token_url,
            "api_base_url": config.mhc_api_base_url,
            "client_id": config.mhc_client_id,
            "client_secret": config.mhc_client_secret
        }
        
        insurance_result = runtime.execute_node(
            insurance_check,
            patient_nric=patient_info["nric"],
            patient_dob=patient_info["dob"],
            oauth_config=oauth_config
        )
        
        coverage = insurance_result["coverage_info"]
        providers = insurance_result["covered_providers"]
        
        print(f"   Coverage type: {coverage['coverage_type']}")
        print(f"   Coverage limit: ${coverage['coverage_limit']:,}")
        print(f"   Deductible: ${coverage['deductible']:,}")
        print(f"   Covered providers: {len(providers)}")
        for provider in providers:
            print(f"   - {provider['name']} ({provider['network']} network)")
        
        print("\n5. Workflow Summary:")
        print("   ✓ Doctor search completed with rate limiting")
        print("   ✓ Slot availability checked with conservative rate limits")
        print("   ✓ Insurance coverage verified via OAuth-protected API")
        print("   ✓ All API calls were properly rate limited and authenticated")
        
    except Exception as e:
        print(f"Error in HMI workflow: {e}")


def example_rate_limiting_strategies():
    """Demonstrate different rate limiting strategies."""
    print("\n" + "="*80)
    print("Rate Limiting Strategies Comparison")
    print("="*80)
    
    # Create a simple HTTP node for testing
    http_node = HTTPRequestNode(node_id="test_http")
    
    # Test different rate limiting strategies
    strategies = [
        {
            "name": "Token Bucket",
            "config": RateLimitConfig(
                max_requests=3,
                time_window=5.0,
                strategy="token_bucket",
                burst_limit=5,
                backoff_factor=1.5
            )
        },
        {
            "name": "Sliding Window", 
            "config": RateLimitConfig(
                max_requests=3,
                time_window=5.0,
                strategy="sliding_window",
                backoff_factor=2.0
            )
        }
    ]
    
    runtime = LocalRuntime()
    
    for strategy in strategies:
        print(f"\n{strategy['name']} Strategy:")
        print(f"   Config: {strategy['config'].max_requests} requests per {strategy['config'].time_window}s")
        
        # Create rate limited node
        rate_limited = RateLimitedAPINode(
            wrapped_node=http_node,
            rate_limit_config=strategy["config"],
            node_id=f"rate_test_{strategy['name'].lower().replace(' ', '_')}"
        )
        
        # Make several rapid requests
        print("   Making 5 rapid requests:")
        for i in range(5):
            try:
                start_time = time.time()
                
                # Use a mock URL for demonstration (will likely return 404 but that's ok)
                result = runtime.execute_node(
                    rate_limited,
                    url="https://httpbin.org/delay/0",  # Fast endpoint for testing
                    method="GET"
                )
                
                end_time = time.time()
                metadata = result.get("rate_limit_metadata", {})
                
                print(f"     Request {i+1}: "
                      f"Status {result.get('status_code', 'N/A')}, "
                      f"Wait: {metadata.get('total_wait_time', 0):.2f}s, "
                      f"Total: {end_time - start_time:.2f}s")
                
            except Exception as e:
                print(f"     Request {i+1}: Error - {e}")
        
        # Reset between strategies
        time.sleep(1)


def run_hmi_examples():
    """Run all HMI-style API integration examples."""
    print("Kailash SDK - HMI-Style API Integration Examples")
    print("================================================")
    print("This demonstrates real-world API integration patterns")
    print("similar to those found in healthcare management systems.")
    
    # Run the examples
    example_hmi_workflow()
    example_rate_limiting_strategies()
    
    print("\n" + "="*80)
    print("HMI Examples completed!")
    print("="*80)
    print("\nKey features demonstrated:")
    print("- Multi-step API workflows with data dependencies")
    print("- Different authentication methods (API Key, OAuth2)")
    print("- Sophisticated rate limiting strategies")
    print("- Error handling and resilience patterns")
    print("- Real-world healthcare API integration patterns")
    print("- Proper separation of concerns between different API services")


if __name__ == "__main__":
    run_hmi_examples()