#!/usr/bin/env python3
"""
REST API Integration Workflow - Real API Integration
===================================================

Demonstrates comprehensive REST API integration patterns using Kailash SDK with real APIs.
This workflow uses HTTPRequestNode to interact with actual public APIs,
avoiding any mock data generation.

Patterns demonstrated:
1. Real API calls to public REST APIs
2. Multi-endpoint API orchestration
3. Response data processing and transformation
4. Error handling and validation
5. Structured output generation

Features:
- Uses HTTPRequestNode for real API calls against public APIs
- Calls JSONPlaceholder API (no auth required) for user/post data
- Calls GitHub API for real repository information
- Processes actual API responses without mocking
- Generates comprehensive API integration reports
"""

import json
import os
from typing import Any

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONWriterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime


def get_api_endpoints() -> dict[str, Any]:
    """Get list of real API endpoints to demonstrate integration patterns."""
    return {
        "jsonplaceholder": {
            "base_url": "https://jsonplaceholder.typicode.com",
            "endpoints": {
                "users": "/users",
                "posts": "/posts",
                "comments": "/comments",
                "albums": "/albums",
            },
            "description": "Free fake JSON API for testing and prototyping",
            "auth_required": False,
        },
        "github": {
            "base_url": "https://api.github.com",
            "endpoints": {
                "repos": "/repos/{owner}/{repo}",
                "user": "/users/{username}",
                "orgs": "/orgs/{org}",
            },
            "description": "GitHub REST API for repository and user data",
            "auth_required": False,  # For public data
            "rate_limit": "60 requests per hour",
        },
        "httpbin": {
            "base_url": "https://httpbin.org",
            "endpoints": {
                "get": "/get",
                "post": "/post",
                "headers": "/headers",
                "status": "/status/{code}",
            },
            "description": "HTTP testing service for request/response validation",
            "auth_required": False,
        },
    }


def create_real_api_integration_workflow() -> Workflow:
    """Create a comprehensive API integration workflow using real public APIs."""
    workflow = Workflow(
        workflow_id="real_api_integration_001",
        name="real_api_integration_workflow",
        description="Integrate with real public APIs using HTTPRequestNode",
    )

    # === API CONFIGURATION ===

    # Configure real API endpoints
    api_configurator = PythonCodeNode(
        name="api_configurator",
        code="""
# Configure real API endpoints for integration
api_config = {
    "jsonplaceholder": {
        "base_url": "https://jsonplaceholder.typicode.com",
        "endpoints": {
            "users": "/users",
            "posts": "/posts",
            "comments": "/comments"
        }
    },
    "github": {
        "base_url": "https://api.github.com",
        "endpoints": {
            "repos": "/repos/microsoft/TypeScript",  # Example public repo
            "user": "/users/github",  # GitHub's own user profile
            "orgs": "/orgs/microsoft"  # Microsoft organization
        }
    },
    "httpbin": {
        "base_url": "https://httpbin.org",
        "endpoints": {
            "get": "/get",
            "headers": "/headers",
            "json": "/json"
        }
    }
}

result = {
    "api_endpoints": api_config,
    "total_apis": len(api_config),
    "total_endpoints": sum(len(config["endpoints"]) for config in api_config.values())
}
""",
    )
    workflow.add_node("api_configurator", api_configurator)

    # === JSONPLACEHOLDER API INTEGRATION ===

    # Fetch real user data from JSONPlaceholder
    jsonplaceholder_integrator = PythonCodeNode(
        name="jsonplaceholder_integrator",
        code="""
# Integrate with JSONPlaceholder API using HTTPRequestNode
from kailash.nodes.api.http import HTTPRequestNode
from datetime import datetime

endpoints = config_data.get("api_endpoints", {}).get("jsonplaceholder", {})
base_url = endpoints.get("base_url", "")
endpoint_paths = endpoints.get("endpoints", {})

integration_results = []

# Fetch users data
users_url = f"{base_url}{endpoint_paths.get('users', '')}"
try:
    http_node = HTTPRequestNode(name="users_fetcher")
    users_response = http_node.execute(
        url=users_url,
        method="GET",
        timeout=30,
        headers={"Accept": "application/json"}
    )

    users_success = users_response.get("success", False)
    users_data = users_response.get("response", {}).get("content", []) if users_success else []

    # Process real user data
    processed_users = []
    if users_success and isinstance(users_data, list):
        for user in users_data:
            if isinstance(user, dict):
                processed_user = {
                    "user_id": user.get("id"),
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                    "phone": user.get("phone"),
                    "website": user.get("website"),
                    "company": user.get("company", {}).get("name", "N/A") if user.get("company") else "N/A",
                    "address_city": user.get("address", {}).get("city", "N/A") if user.get("address") else "N/A"
                }
                processed_users.append(processed_user)

    users_result = {
        "endpoint": "users",
        "url": users_url,
        "success": users_success,
        "total_users": len(processed_users),
        "users_data": processed_users,
        "response_code": users_response.get("status_code"),
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(users_result)

except Exception as e:
    users_result = {
        "endpoint": "users",
        "url": users_url,
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(users_result)

# Fetch posts data
posts_url = f"{base_url}{endpoint_paths.get('posts', '')}"
try:
    http_node = HTTPRequestNode(name="posts_fetcher")
    posts_response = http_node.execute(
        url=posts_url,
        method="GET",
        timeout=30,
        headers={"Accept": "application/json"}
    )

    posts_success = posts_response.get("success", False)
    posts_data = posts_response.get("response", {}).get("content", []) if posts_success else []

    # Analyze real posts data
    posts_analysis = {}
    if posts_success and isinstance(posts_data, list):
        # Count posts per user
        user_post_counts = {}
        for post in posts_data:
            if isinstance(post, dict):
                user_id = post.get("userId")
                if user_id:
                    user_post_counts[user_id] = user_post_counts.get(user_id, 0) + 1

        posts_analysis = {
            "total_posts": len(posts_data),
            "unique_users": len(user_post_counts),
            "avg_posts_per_user": len(posts_data) / len(user_post_counts) if user_post_counts else 0,
            "user_post_counts": user_post_counts,
            "sample_posts": posts_data[:3]  # First 3 posts for reference
        }

    posts_result = {
        "endpoint": "posts",
        "url": posts_url,
        "success": posts_success,
        "posts_analysis": posts_analysis,
        "response_code": posts_response.get("status_code"),
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(posts_result)

except Exception as e:
    posts_result = {
        "endpoint": "posts",
        "url": posts_url,
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(posts_result)

result = {
    "api_name": "jsonplaceholder",
    "integration_results": integration_results,
    "successful_calls": sum(1 for r in integration_results if r.get("success")),
    "total_calls": len(integration_results)
}
""",
    )
    workflow.add_node("jsonplaceholder_integrator", jsonplaceholder_integrator)
    workflow.connect(
        "api_configurator",
        "jsonplaceholder_integrator",
        mapping={"result": "config_data"},
    )

    # === GITHUB API INTEGRATION ===

    # Fetch real repository data from GitHub API
    github_integrator = PythonCodeNode(
        name="github_integrator",
        code="""
# Integrate with GitHub API using HTTPRequestNode
from kailash.nodes.api.http import HTTPRequestNode
from datetime import datetime

endpoints = config_data.get("api_endpoints", {}).get("github", {})
base_url = endpoints.get("base_url", "")
endpoint_paths = endpoints.get("endpoints", {})

integration_results = []

# Fetch repository information
repo_url = f"{base_url}{endpoint_paths.get('repos', '')}"
try:
    http_node = HTTPRequestNode(name="repo_fetcher")
    repo_response = http_node.execute(
        url=repo_url,
        method="GET",
        timeout=30,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kailash-SDK-Demo"
        }
    )

    repo_success = repo_response.get("success", False)
    repo_data = repo_response.get("response", {}).get("content", {}) if repo_success else {}

    # Process real repository data
    repo_analysis = {}
    if repo_success and isinstance(repo_data, dict):
        repo_analysis = {
            "repo_name": repo_data.get("name"),
            "full_name": repo_data.get("full_name"),
            "description": repo_data.get("description"),
            "language": repo_data.get("language"),
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "watchers": repo_data.get("watchers_count", 0),
            "size_kb": repo_data.get("size", 0),
            "open_issues": repo_data.get("open_issues_count", 0),
            "created_at": repo_data.get("created_at"),
            "updated_at": repo_data.get("updated_at"),
            "is_private": repo_data.get("private", False),
            "has_wiki": repo_data.get("has_wiki", False),
            "license": repo_data.get("license", {}).get("name", "N/A") if repo_data.get("license") else "N/A"
        }

    repo_result = {
        "endpoint": "repository",
        "url": repo_url,
        "success": repo_success,
        "repo_analysis": repo_analysis,
        "response_code": repo_response.get("status_code"),
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(repo_result)

except Exception as e:
    repo_result = {
        "endpoint": "repository",
        "url": repo_url,
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(repo_result)

# Fetch user information
user_url = f"{base_url}{endpoint_paths.get('user', '')}"
try:
    http_node = HTTPRequestNode(name="user_fetcher")
    user_response = http_node.execute(
        url=user_url,
        method="GET",
        timeout=30,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kailash-SDK-Demo"
        }
    )

    user_success = user_response.get("success", False)
    user_data = user_response.get("response", {}).get("content", {}) if user_success else {}

    # Process real user data
    user_analysis = {}
    if user_success and isinstance(user_data, dict):
        user_analysis = {
            "username": user_data.get("login"),
            "user_id": user_data.get("id"),
            "name": user_data.get("name"),
            "bio": user_data.get("bio"),
            "company": user_data.get("company"),
            "location": user_data.get("location"),
            "public_repos": user_data.get("public_repos", 0),
            "followers": user_data.get("followers", 0),
            "following": user_data.get("following", 0),
            "created_at": user_data.get("created_at"),
            "updated_at": user_data.get("updated_at"),
            "account_type": user_data.get("type"),
            "is_site_admin": user_data.get("site_admin", False)
        }

    user_result = {
        "endpoint": "user",
        "url": user_url,
        "success": user_success,
        "user_analysis": user_analysis,
        "response_code": user_response.get("status_code"),
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(user_result)

except Exception as e:
    user_result = {
        "endpoint": "user",
        "url": user_url,
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "fetched_at": datetime.now().isoformat()
    }
    integration_results.append(user_result)

result = {
    "api_name": "github",
    "integration_results": integration_results,
    "successful_calls": sum(1 for r in integration_results if r.get("success")),
    "total_calls": len(integration_results)
}
""",
    )
    workflow.add_node("github_integrator", github_integrator)
    workflow.connect(
        "api_configurator", "github_integrator", mapping={"result": "config_data"}
    )

    # === HTTPBIN API INTEGRATION ===

    # Test HTTP methods and headers using HTTPBin
    httpbin_integrator = PythonCodeNode(
        name="httpbin_integrator",
        code="""
# Integrate with HTTPBin API for HTTP testing using HTTPRequestNode
from kailash.nodes.api.http import HTTPRequestNode
from datetime import datetime

endpoints = config_data.get("api_endpoints", {}).get("httpbin", {})
base_url = endpoints.get("base_url", "")
endpoint_paths = endpoints.get("endpoints", {})

integration_results = []

# Test GET method with headers
get_url = f"{base_url}{endpoint_paths.get('get', '')}"
try:
    http_node = HTTPRequestNode(name="get_tester")
    get_response = http_node.execute(
        url=get_url,
        method="GET",
        timeout=30,
        headers={
            "User-Agent": "Kailash-SDK-Test",
            "X-Custom-Header": "API-Integration-Test",
            "Accept": "application/json"
        },
        params={
            "test_param": "kailash_sdk",
            "timestamp": datetime.now().isoformat()
        }
    )

    get_success = get_response.get("success", False)
    get_data = get_response.get("response", {}).get("content", {}) if get_success else {}

    # Analyze GET response
    get_analysis = {}
    if get_success and isinstance(get_data, dict):
        get_analysis = {
            "origin_ip": get_data.get("origin"),
            "headers_sent": get_data.get("headers", {}),
            "args_received": get_data.get("args", {}),
            "url_called": get_data.get("url"),
            "user_agent": get_data.get("headers", {}).get("User-Agent"),
            "custom_header": get_data.get("headers", {}).get("X-Custom-Header")
        }

    get_result = {
        "endpoint": "get_test",
        "url": get_url,
        "method": "GET",
        "success": get_success,
        "analysis": get_analysis,
        "response_code": get_response.get("status_code"),
        "tested_at": datetime.now().isoformat()
    }
    integration_results.append(get_result)

except Exception as e:
    get_result = {
        "endpoint": "get_test",
        "url": get_url,
        "method": "GET",
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "tested_at": datetime.now().isoformat()
    }
    integration_results.append(get_result)

# Test headers endpoint
headers_url = f"{base_url}{endpoint_paths.get('headers', '')}"
try:
    http_node = HTTPRequestNode(name="headers_tester")
    headers_response = http_node.execute(
        url=headers_url,
        method="GET",
        timeout=30,
        headers={
            "Authorization": "Bearer fake-token-for-testing",
            "Content-Type": "application/json",
            "X-API-Version": "v1.0",
            "X-Client": "Kailash-SDK"
        }
    )

    headers_success = headers_response.get("success", False)
    headers_data = headers_response.get("response", {}).get("content", {}) if headers_success else {}

    # Analyze headers response
    headers_analysis = {}
    if headers_success and isinstance(headers_data, dict):
        received_headers = headers_data.get("headers", {})
        headers_analysis = {
            "total_headers": len(received_headers),
            "authorization_header": received_headers.get("Authorization"),
            "content_type": received_headers.get("Content-Type"),
            "api_version": received_headers.get("X-Api-Version"),
            "client_header": received_headers.get("X-Client"),
            "host": received_headers.get("Host"),
            "all_headers": received_headers
        }

    headers_result = {
        "endpoint": "headers_test",
        "url": headers_url,
        "method": "GET",
        "success": headers_success,
        "analysis": headers_analysis,
        "response_code": headers_response.get("status_code"),
        "tested_at": datetime.now().isoformat()
    }
    integration_results.append(headers_result)

except Exception as e:
    headers_result = {
        "endpoint": "headers_test",
        "url": headers_url,
        "method": "GET",
        "success": False,
        "error": str(e),
        "error_type": type(e).__name__,
        "tested_at": datetime.now().isoformat()
    }
    integration_results.append(headers_result)

result = {
    "api_name": "httpbin",
    "integration_results": integration_results,
    "successful_calls": sum(1 for r in integration_results if r.get("success")),
    "total_calls": len(integration_results)
}
""",
    )
    workflow.add_node("httpbin_integrator", httpbin_integrator)
    workflow.connect(
        "api_configurator", "httpbin_integrator", mapping={"result": "config_data"}
    )

    # === MERGE API INTEGRATION RESULTS ===

    # Merge all API integration results
    api_merger = MergeNode(id="api_merger", merge_type="merge_dict")
    workflow.add_node("api_merger", api_merger)
    workflow.connect(
        "jsonplaceholder_integrator", "api_merger", mapping={"result": "data1"}
    )
    workflow.connect("github_integrator", "api_merger", mapping={"result": "data2"})
    workflow.connect("httpbin_integrator", "api_merger", mapping={"result": "data3"})

    # === API PERFORMANCE ANALYSIS ===

    # Analyze API integration performance and results
    api_analyzer = PythonCodeNode(
        name="api_analyzer",
        code="""
# Analyze API integration performance and results
from datetime import datetime

merged_results = merged_data
api_results = [merged_results.get("api_name"), merged_results.get("integration_results")]

# Extract individual API results
jsonplaceholder_data = merged_results.get("api_name") == "jsonplaceholder"
github_data = merged_results.get("api_name") == "github"
httpbin_data = merged_results.get("api_name") == "httpbin"

all_integrations = []
for key, value in merged_results.items():
    if isinstance(value, dict) and "integration_results" in value:
        api_name = value.get("api_name", key)
        integration_results = value.get("integration_results", [])
        successful_calls = value.get("successful_calls", 0)
        total_calls = value.get("total_calls", 0)

        api_summary = {
            "api_name": api_name,
            "total_endpoints_tested": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": total_calls - successful_calls,
            "success_rate": (successful_calls / total_calls * 100) if total_calls > 0 else 0,
            "integration_results": integration_results
        }
        all_integrations.append(api_summary)

# Calculate overall metrics
total_api_calls = sum(api.get("total_endpoints_tested", 0) for api in all_integrations)
total_successful = sum(api.get("successful_calls", 0) for api in all_integrations)
overall_success_rate = (total_successful / total_api_calls * 100) if total_api_calls > 0 else 0

# Extract specific insights
insights = []
for api in all_integrations:
    api_name = api.get("api_name", "unknown")

    if api_name == "jsonplaceholder":
        # Analyze user and posts data
        for result in api.get("integration_results", []):
            if result.get("endpoint") == "users" and result.get("success"):
                user_count = result.get("total_users", 0)
                insights.append(f"JSONPlaceholder: Successfully fetched {user_count} real users")
            elif result.get("endpoint") == "posts" and result.get("success"):
                posts_analysis = result.get("posts_analysis", {})
                total_posts = posts_analysis.get("total_posts", 0)
                unique_users = posts_analysis.get("unique_users", 0)
                insights.append(f"JSONPlaceholder: Analyzed {total_posts} posts from {unique_users} users")

    elif api_name == "github":
        # Analyze repository and user data
        for result in api.get("integration_results", []):
            if result.get("endpoint") == "repository" and result.get("success"):
                repo_analysis = result.get("repo_analysis", {})
                repo_name = repo_analysis.get("repo_name", "unknown")
                stars = repo_analysis.get("stars", 0)
                language = repo_analysis.get("language", "unknown")
                insights.append(f"GitHub: Repository '{repo_name}' has {stars} stars, written in {language}")
            elif result.get("endpoint") == "user" and result.get("success"):
                user_analysis = result.get("user_analysis", {})
                username = user_analysis.get("username", "unknown")
                public_repos = user_analysis.get("public_repos", 0)
                followers = user_analysis.get("followers", 0)
                insights.append(f"GitHub: User '{username}' has {public_repos} public repos and {followers} followers")

    elif api_name == "httpbin":
        # Analyze HTTP testing results
        for result in api.get("integration_results", []):
            if result.get("endpoint") == "get_test" and result.get("success"):
                analysis = result.get("analysis", {})
                origin_ip = analysis.get("origin_ip", "unknown")
                headers_count = len(analysis.get("headers_sent", {}))
                insights.append(f"HTTPBin: GET test successful from IP {origin_ip} with {headers_count} headers")
            elif result.get("endpoint") == "headers_test" and result.get("success"):
                analysis = result.get("analysis", {})
                total_headers = analysis.get("total_headers", 0)
                insights.append(f"HTTPBin: Headers test verified {total_headers} request headers correctly")

# Generate recommendations
recommendations = []
if overall_success_rate < 100:
    failed_apis = [api["api_name"] for api in all_integrations if api.get("success_rate", 0) < 100]
    recommendations.append(f"Review failed API calls for: {', '.join(failed_apis)}")

if total_api_calls < 6:  # Expected: 2 JSONPlaceholder + 2 GitHub + 2 HTTPBin
    recommendations.append("Some API endpoints were not tested - check network connectivity")

if overall_success_rate > 80:
    recommendations.append("Good API integration success rate - consider implementing rate limiting for production")

if any("github" in api["api_name"] for api in all_integrations):
    recommendations.append("GitHub API has rate limits (60 req/hour) - implement authentication for higher limits")

# Compile comprehensive analysis
analysis_report = {
    "overall_metrics": {
        "total_apis_tested": len(all_integrations),
        "total_endpoint_calls": total_api_calls,
        "successful_calls": total_successful,
        "overall_success_rate": round(overall_success_rate, 2),
        "apis_tested": [api["api_name"] for api in all_integrations]
    },
    "api_breakdown": all_integrations,
    "business_insights": insights,
    "technical_recommendations": recommendations,
    "integration_patterns_demonstrated": [
        "Real public API integration without authentication",
        "Multi-endpoint API orchestration",
        "Response data processing and analysis",
        "Error handling for network failures",
        "HTTP method and header testing"
    ],
    "analysis_metadata": {
        "analyzed_at": datetime.now().isoformat(),
        "analysis_type": "real_api_integration_analysis",
        "data_sources": ["jsonplaceholder", "github_api", "httpbin"]
    }
}

result = analysis_report
""",
    )
    workflow.add_node("api_analyzer", api_analyzer)
    workflow.connect(
        "api_merger", "api_analyzer", mapping={"merged_data": "merged_data"}
    )

    # === COMPREHENSIVE REPORTING ===

    # Generate comprehensive API integration report
    report_generator = PythonCodeNode(
        name="report_generator",
        code="""
# Generate comprehensive API integration report
from datetime import datetime

analysis_data = analysis_results
overall_metrics = analysis_data.get("overall_metrics", {})
api_breakdown = analysis_data.get("api_breakdown", [])
insights = analysis_data.get("business_insights", [])
recommendations = analysis_data.get("technical_recommendations", [])
patterns = analysis_data.get("integration_patterns_demonstrated", [])

# Determine integration status
total_apis = overall_metrics.get("total_apis_tested", 0)
success_rate = overall_metrics.get("overall_success_rate", 0)

if success_rate >= 90:
    integration_status = "EXCELLENT"
    status_color = "green"
elif success_rate >= 75:
    integration_status = "GOOD"
    status_color = "yellow"
elif success_rate >= 50:
    integration_status = "FAIR"
    status_color = "orange"
else:
    integration_status = "POOR"
    status_color = "red"

# Generate executive summary
current_time = datetime.now()
executive_summary = {
    "integration_status": integration_status,
    "status_color": status_color,
    "apis_integrated": total_apis,
    "success_rate": f"{success_rate}%",
    "total_endpoint_calls": overall_metrics.get("total_endpoint_calls", 0),
    "successful_calls": overall_metrics.get("successful_calls", 0),
    "apis_tested": overall_metrics.get("apis_tested", []),
    "integration_method": "HTTPRequestNode + Real Public APIs",
    "report_timestamp": current_time.isoformat()
}

# Generate detailed sections
integration_summary = {
    "total_integrations": len(api_breakdown),
    "by_api": {api["api_name"]: {
        "endpoints_tested": api.get("total_endpoints_tested", 0),
        "success_rate": f"{api.get('success_rate', 0):.1f}%",
        "failed_calls": api.get("failed_calls", 0)
    } for api in api_breakdown},
    "successful_integrations": sum(1 for api in api_breakdown if api.get("success_rate", 0) > 0),
    "perfect_integrations": sum(1 for api in api_breakdown if api.get("success_rate", 0) == 100)
}

# Generate key findings
key_findings = []
if success_rate == 100:
    key_findings.append({
        "type": "success",
        "finding": "All API integrations completed successfully",
        "impact": "Demonstrates robust HTTPRequestNode functionality",
        "recommendation": "Production-ready for similar public API integrations"
    })

# Check for specific API insights
for api in api_breakdown:
    api_name = api.get("api_name")
    if api_name == "jsonplaceholder" and api.get("success_rate", 0) > 0:
        key_findings.append({
            "type": "data_quality",
            "finding": "JSONPlaceholder API provided structured user and post data",
            "impact": "Suitable for testing data transformation workflows",
            "recommendation": "Use for development and testing workflows"
        })

    if api_name == "github" and api.get("success_rate", 0) > 0:
        key_findings.append({
            "type": "real_world_integration",
            "finding": "GitHub API integration successful with real repository data",
            "impact": "Demonstrates capability for production API integrations",
            "recommendation": "Implement authentication for production usage"
        })

# Final comprehensive report
report = {
    "api_integration_report": {
        "executive_summary": executive_summary,
        "integration_summary": integration_summary,
        "key_findings": key_findings,
        "business_insights": insights,
        "technical_recommendations": recommendations,
        "patterns_demonstrated": patterns,
        "detailed_results": {
            "overall_metrics": overall_metrics,
            "api_breakdown": api_breakdown
        }
    },
    "report_metadata": {
        "generated_at": current_time.isoformat(),
        "report_type": "real_api_integration_analysis",
        "version": "1.0",
        "integration_method": "HTTPRequestNode + Public APIs",
        "data_sources": ["jsonplaceholder.typicode.com", "api.github.com", "httpbin.org"]
    },
    "next_steps": {
        "immediate_actions": [
            "Review any failed API calls and error details",
            "Test rate limiting and authentication for production usage",
            "Implement proper error handling for network failures"
        ],
        "production_considerations": [
            "Add authentication for APIs that require it",
            "Implement proper rate limiting and backoff strategies",
            "Add monitoring and alerting for API failures",
            "Consider caching for frequently accessed data"
        ]
    }
}

result = report
""",
    )
    workflow.add_node("report_generator", report_generator)
    workflow.connect(
        "api_analyzer", "report_generator", mapping={"result": "analysis_results"}
    )

    # === OUTPUTS ===

    # Save comprehensive API integration report
    report_writer = JSONWriterNode(
        id="report_writer",
        file_path="data/outputs/comprehensive_api_integration_report.json",
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect("report_generator", "report_writer", mapping={"result": "data"})

    # Save raw API integration data
    raw_data_writer = JSONWriterNode(
        id="raw_data_writer", file_path="data/outputs/raw_api_integration_data.json"
    )
    workflow.add_node("raw_data_writer", raw_data_writer)
    workflow.connect("api_merger", "raw_data_writer", mapping={"merged_data": "data"})

    return workflow


def run_real_api_integration():
    """Execute the real API integration workflow."""
    workflow = create_real_api_integration_workflow()
    runtime = LocalRuntime()

    parameters = {}

    try:
        print("Starting Real API Integration Workflow...")
        print("🔍 Integrating with real public APIs...")

        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("\\n✅ API Integration Complete!")
        print("📁 Outputs generated:")
        print(
            "   - Comprehensive report: data/outputs/comprehensive_api_integration_report.json"
        )
        print("   - Raw integration data: data/outputs/raw_api_integration_data.json")

        # Show executive summary
        report_result = result.get("report_generator", {}).get("result", {})
        api_report = report_result.get("api_integration_report", {})
        executive_summary = api_report.get("executive_summary", {})

        print(
            f"\\n📊 Integration Status: {executive_summary.get('integration_status', 'UNKNOWN')}"
        )
        print(f"   - APIs Integrated: {executive_summary.get('apis_integrated', 0)}")
        print(f"   - Success Rate: {executive_summary.get('success_rate', 'N/A')}")
        print(
            f"   - Total API Calls: {executive_summary.get('total_endpoint_calls', 0)}"
        )
        print(f"   - Successful Calls: {executive_summary.get('successful_calls', 0)}")
        print(
            f"   - APIs Tested: {', '.join(executive_summary.get('apis_tested', []))}"
        )

        # Show key findings
        key_findings = api_report.get("key_findings", [])
        if key_findings:
            print("\\n💡 KEY FINDINGS:")
            for finding in key_findings[:3]:  # Show top 3 findings
                print(
                    f"   - [{finding.get('type', 'unknown').upper()}] {finding.get('finding', 'N/A')}"
                )

        # Show recommendations
        recommendations = api_report.get("technical_recommendations", [])
        if recommendations:
            print("\\n🎯 TECHNICAL RECOMMENDATIONS:")
            for rec in recommendations:
                print(f"   - {rec}")

        return result

    except Exception as e:
        print(f"❌ API Integration failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Create output directories
    os.makedirs("data/outputs", exist_ok=True)

    # Run the real API integration workflow
    run_real_api_integration()

    # Display generated reports
    print("\\n=== API Integration Report Preview ===")
    try:
        with open("data/outputs/comprehensive_api_integration_report.json") as f:
            report = json.load(f)
            executive_summary = report["api_integration_report"]["executive_summary"]
            print(json.dumps(executive_summary, indent=2))

        print("\\n=== Integration Summary by API ===")
        integration_summary = report["api_integration_report"]["integration_summary"]
        by_api = integration_summary.get("by_api", {})
        for api_name, metrics in by_api.items():
            print(
                f"{api_name}: {metrics['endpoints_tested']} endpoints, {metrics['success_rate']} success rate"
            )

        print("\\n=== Key Findings ===")
        key_findings = report["api_integration_report"]["key_findings"]
        for finding in key_findings[:3]:  # Show top 3 findings
            print(f"- [{finding['type'].upper()}] {finding['finding']}")

    except Exception as e:
        print(f"Could not read reports: {e}")


if __name__ == "__main__":
    main()
