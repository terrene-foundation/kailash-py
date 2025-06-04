"""
Template: API Integration Pattern
Purpose: Integrate with external REST APIs with authentication and error handling
Use Case: Consuming third-party services, microservice communication

Customization Points:
- API_CONFIG: Your API endpoint and authentication details
- process_api_response(): Transform API responses
- Error handling and retry logic
- Rate limiting configuration
"""

from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.api.auth import APIKeyNode, OAuth2Node, BasicAuthNode
from kailash.nodes.api.rest import RESTClientNode
from kailash.nodes.api.rate_limiting import RateLimitedAPINode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from typing import Dict, Any, List
import os

# Configuration (customize these)
API_CONFIG = {
    "base_url": "https://api.example.com/v1",
    "auth_type": "api_key",  # Options: api_key, oauth2, basic
    "api_key": os.getenv("API_KEY", "your-api-key-here"),
    "rate_limit": 100,  # Requests per minute
    "timeout": 30,  # Seconds
    "retry_count": 3,
    "retry_delay": 1.0  # Seconds
}

# OAuth2 config (if using OAuth)
OAUTH_CONFIG = {
    "client_id": os.getenv("CLIENT_ID", ""),
    "client_secret": os.getenv("CLIENT_SECRET", ""),
    "token_url": "https://auth.example.com/oauth/token",
    "scope": "read write"
}

# Output configuration
OUTPUT_FILE = "outputs/api_results.json"

def prepare_api_request(data: Dict) -> Dict[str, Any]:
    """Prepare data for API request"""
    # Example: Transform input data to API format
    api_payload = {
        "filters": data.get("filters", {}),
        "page": data.get("page", 1),
        "per_page": data.get("per_page", 100),
        "sort": data.get("sort", "created_at"),
        "order": data.get("order", "desc")
    }
    
    # Add any required headers
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-ID": f"kailash-{data.get('request_id', 'default')}"
    }
    
    return {
        "endpoint": data.get("endpoint", "/resources"),
        "method": data.get("method", "GET"),
        "params": api_payload,
        "headers": headers
    }

def process_api_response(response: Dict) -> Dict[str, Any]:
    """Process and transform API response"""
    # Handle different response structures
    if "error" in response:
        return {
            "success": False,
            "error": response["error"],
            "data": []
        }
    
    # Extract data from response
    data = response.get("data", response.get("results", []))
    
    # Transform each item
    processed_items = []
    for item in data if isinstance(data, list) else [data]:
        processed_item = {
            "id": item.get("id"),
            "name": item.get("name", "Unknown"),
            "status": item.get("status", "active"),
            "created_at": item.get("created_at"),
            "processed_at": "2025-06-04",  # Add processing timestamp
            # Add custom transformations
            "category": classify_item(item),
            "priority": calculate_priority(item)
        }
        processed_items.append(processed_item)
    
    # Return processed data with metadata
    return {
        "success": True,
        "data": processed_items,
        "metadata": {
            "total_count": len(processed_items),
            "api_version": response.get("version", "unknown"),
            "rate_limit_remaining": response.get("headers", {}).get("X-RateLimit-Remaining", "unknown")
        }
    }

def classify_item(item: Dict) -> str:
    """Custom classification logic"""
    # Example classification based on attributes
    if item.get("value", 0) > 1000:
        return "high_value"
    elif item.get("active", True):
        return "active_standard"
    else:
        return "inactive"

def calculate_priority(item: Dict) -> int:
    """Calculate item priority"""
    # Example priority calculation
    base_priority = 1
    if item.get("urgent", False):
        base_priority += 3
    if item.get("value", 0) > 500:
        base_priority += 2
    return min(base_priority, 5)  # Cap at 5

def handle_pagination(response: Dict, context: Dict) -> Dict[str, Any]:
    """Handle paginated API responses"""
    current_page = context.get("current_page", 1)
    total_pages = response.get("total_pages", 1)
    
    all_data = context.get("accumulated_data", [])
    all_data.extend(response.get("data", []))
    
    if current_page < total_pages:
        # Need to fetch more pages
        return {
            "continue": True,
            "next_request": {
                "endpoint": context.get("endpoint"),
                "page": current_page + 1,
                "accumulated_data": all_data
            }
        }
    else:
        # All pages fetched
        return {
            "continue": False,
            "final_data": all_data
        }

def create_api_integration_workflow():
    """Create the API integration workflow"""
    workflow = Workflow()
    
    # 1. Prepare request
    request_preparer = PythonCodeNode.from_function(
        func=prepare_api_request,
        name="request_preparer",
        description="Prepare API request parameters"
    )
    workflow.add_node("prepare_request", request_preparer)
    
    # 2. Authentication (choose based on API_CONFIG)
    if API_CONFIG["auth_type"] == "api_key":
        auth_node = APIKeyNode(
            config={
                "api_key": API_CONFIG["api_key"],
                "header_name": "X-API-Key"
            }
        )
    elif API_CONFIG["auth_type"] == "oauth2":
        auth_node = OAuth2Node(
            config={
                "client_id": OAUTH_CONFIG["client_id"],
                "client_secret": OAUTH_CONFIG["client_secret"],
                "token_url": OAUTH_CONFIG["token_url"],
                "scope": OAUTH_CONFIG["scope"]
            }
        )
    elif API_CONFIG["auth_type"] == "basic":
        auth_node = BasicAuthNode(
            config={
                "username": os.getenv("API_USERNAME", ""),
                "password": os.getenv("API_PASSWORD", "")
            }
        )
    else:
        auth_node = None
    
    if auth_node:
        workflow.add_node("auth", auth_node)
    
    # 3. API Client with rate limiting
    if API_CONFIG["rate_limit"] > 0:
        api_client = RateLimitedAPINode(
            config={
                "base_url": API_CONFIG["base_url"],
                "rate_limit": API_CONFIG["rate_limit"],
                "time_window": 60,  # Per minute
                "timeout": API_CONFIG["timeout"],
                "retry_count": API_CONFIG["retry_count"],
                "retry_delay": API_CONFIG["retry_delay"]
            }
        )
    else:
        api_client = RESTClientNode(
            config={
                "base_url": API_CONFIG["base_url"],
                "timeout": API_CONFIG["timeout"],
                "retry_count": API_CONFIG["retry_count"]
            }
        )
    workflow.add_node("api_client", api_client)
    
    # 4. Process response
    response_processor = PythonCodeNode.from_function(
        func=process_api_response,
        name="response_processor",
        description="Process API response"
    )
    workflow.add_node("process_response", response_processor)
    
    # 5. Handle pagination (optional)
    pagination_handler = PythonCodeNode.from_function(
        func=handle_pagination,
        name="pagination_handler",
        description="Handle paginated responses"
    )
    workflow.add_node("handle_pagination", pagination_handler)
    
    # 6. Write results
    writer = JSONWriterNode(
        config={
            "file_path": OUTPUT_FILE,
            "indent": 2
        }
    )
    workflow.add_node("writer", writer)
    
    # Connect workflow
    workflow.connect("prepare_request", "api_client")
    
    if auth_node:
        workflow.connect("auth", "api_client", mapping={"token": "auth_token"})
    
    workflow.connect("api_client", "process_response", mapping={"response": "response"})
    workflow.connect("process_response", "handle_pagination")
    workflow.connect("handle_pagination", "writer", mapping={"final_data": "data"})
    
    return workflow

def create_simple_api_workflow():
    """Simplified version without pagination"""
    workflow = Workflow()
    
    # Simple API call
    api_client = RESTClientNode(
        config={
            "base_url": API_CONFIG["base_url"],
            "headers": {"X-API-Key": API_CONFIG["api_key"]}
        }
    )
    workflow.add_node("api", api_client)
    
    # Process and save
    processor = PythonCodeNode.from_function(
        func=process_api_response,
        name="processor"
    )
    workflow.add_node("process", processor)
    
    writer = JSONWriterNode(
        config={"file_path": OUTPUT_FILE}
    )
    workflow.add_node("save", writer)
    
    # Connect
    workflow.connect("api", "process")
    workflow.connect("process", "save", mapping={"data": "data"})
    
    return workflow

def main():
    """Execute the API integration workflow"""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Choose workflow version
    # workflow = create_api_integration_workflow()  # Full version
    workflow = create_simple_api_workflow()  # Simple version
    
    workflow.validate()
    
    runtime = LocalRuntime()
    try:
        # Execute with initial parameters
        results = runtime.execute(
            workflow,
            parameters={
                "prepare_request": {
                    "data": {
                        "endpoint": "/users",
                        "filters": {"status": "active"},
                        "page": 1,
                        "per_page": 50
                    }
                },
                "api": {  # For simple workflow
                    "endpoint": "/users",
                    "method": "GET",
                    "params": {"status": "active", "limit": 50}
                }
            }
        )
        
        print("API integration completed successfully!")
        print(f"Results saved to: {OUTPUT_FILE}")
        
        # Print summary
        if "process_response" in results or "process" in results:
            result = results.get("process_response", results.get("process", {}))
            if result.get("success"):
                metadata = result.get("metadata", {})
                print(f"\nSummary:")
                print(f"- Records fetched: {metadata.get('total_count', 0)}")
                print(f"- API version: {metadata.get('api_version', 'unknown')}")
                print(f"- Rate limit remaining: {metadata.get('rate_limit_remaining', 'unknown')}")
            else:
                print(f"\nError: {result.get('error', 'Unknown error')}")
        
        return 0
        
    except Exception as e:
        print(f"Error executing workflow: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())