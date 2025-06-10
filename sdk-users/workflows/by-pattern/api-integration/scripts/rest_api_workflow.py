#!/usr/bin/env python3
"""
REST API Integration Workflow
=============================

This script demonstrates REST API integration patterns with Kailash SDK:
1. Real API calls to public APIs
2. Data transformation using existing nodes
3. Error handling and validation
4. CSV export of results

Key Features:
- Uses HTTPRequestNode for real API calls
- Calls public APIs (JSONPlaceholder, OpenWeatherMap)
- Works around DataTransformer dict bug using PythonCodeNode
- Saves results to CSV
"""

import os

from kailash import Workflow
from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.data import CSVWriterNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.nodes.logic import MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime import LocalRuntime


def create_jsonplaceholder_workflow() -> Workflow:
    """Create a workflow that fetches and processes data from JSONPlaceholder API."""
    workflow = Workflow(
        workflow_id="jsonplaceholder_api",
        name="jsonplaceholder_workflow",
        description="Fetch users and posts from JSONPlaceholder API",
    )

    # Fetch users from API
    users_api = HTTPRequestNode(
        id="users_api",
        url="https://jsonplaceholder.typicode.com/users",
        method="GET",
        timeout=30,
    )
    workflow.add_node("users_api", users_api)

    # Fetch posts from API
    posts_api = HTTPRequestNode(
        id="posts_api",
        url="https://jsonplaceholder.typicode.com/posts",
        method="GET",
        timeout=30,
    )
    workflow.add_node("posts_api", posts_api)

    # Use PythonCodeNode to extract content from API response
    # This avoids the DataTransformer dict bug
    user_content_extractor = PythonCodeNode(
        name="user_content_extractor",
        code="""
# Extract content from HTTP response
# HTTPRequestNode returns a dict with 'content' field
if isinstance(response, dict) and 'content' in response:
    result = response['content']
else:
    result = response
""",
    )
    workflow.add_node("user_content_extractor", user_content_extractor)
    workflow.connect(
        "users_api", "user_content_extractor", mapping={"response": "response"}
    )

    post_content_extractor = PythonCodeNode(
        name="post_content_extractor",
        code="""
# Extract content from HTTP response
if isinstance(response, dict) and 'content' in response:
    result = response['content']
else:
    result = response
""",
    )
    workflow.add_node("post_content_extractor", post_content_extractor)
    workflow.connect(
        "posts_api", "post_content_extractor", mapping={"response": "response"}
    )

    # Extract user data
    user_extractor = DataTransformer(
        id="user_extractor",
        transformations=[
            """
# Extract key user fields from API response
# Data comes from PythonCodeNode which extracts content from HTTPRequestNode response
if isinstance(data, list):
    result = [{
        "user_id": user.get("id") if isinstance(user, dict) else None,
        "username": user.get("username") if isinstance(user, dict) else None,
        "email": user.get("email") if isinstance(user, dict) else None,
        "company": user.get("company", {}).get("name", "N/A") if isinstance(user, dict) and user.get("company") else "N/A"
    } for user in data]
else:
    result = []
"""
        ],
    )
    workflow.add_node("user_extractor", user_extractor)
    workflow.connect(
        "user_content_extractor", "user_extractor", mapping={"result": "data"}
    )

    # Extract post data
    post_extractor = DataTransformer(
        id="post_extractor",
        transformations=[
            """
# Extract post data and count posts per user
user_post_counts = {}
if isinstance(data, list):
    for post in data:
        if isinstance(post, dict):
            user_id = post.get("userId")
            if user_id:
                if user_id not in user_post_counts:
                    user_post_counts[user_id] = 0
                user_post_counts[user_id] += 1

result = [{
    "user_id": user_id,
    "post_count": count
} for user_id, count in user_post_counts.items()]
"""
        ],
    )
    workflow.add_node("post_extractor", post_extractor)
    workflow.connect(
        "post_content_extractor", "post_extractor", mapping={"result": "data"}
    )

    # Merge user and post data
    merger = MergeNode(
        id="user_post_merger",
        merge_type="merge_dict",  # Use merge_dict to join lists of dicts
        key="user_id",  # Join on user_id field
    )
    workflow.add_node("merger", merger)
    workflow.connect("user_extractor", "merger", mapping={"result": "data1"})
    workflow.connect("post_extractor", "merger", mapping={"result": "data2"})

    # Save results
    writer = CSVWriterNode(
        id="result_writer", file_path="data/outputs/user_analytics.csv"
    )
    workflow.add_node("writer", writer)
    workflow.connect("merger", "writer", mapping={"merged_data": "data"})

    return workflow


def create_simple_data_workflow() -> Workflow:
    """Create a simple workflow with local data transformation."""
    workflow = Workflow(
        workflow_id="simple_data_workflow",
        name="simple_data_workflow",
        description="Transform and merge local data without external API calls",
    )

    # Create mock user data
    user_source = DataTransformer(
        id="user_source",
        transformations=[
            """
# Create mock user data
users = [
    {"id": 1, "username": "alice", "email": "alice@example.com", "company": {"name": "Tech Corp"}},
    {"id": 2, "username": "bob", "email": "bob@example.com", "company": {"name": "Data Inc"}},
    {"id": 3, "username": "charlie", "email": "charlie@example.com", "company": {"name": "AI Labs"}},
    {"id": 4, "username": "diana", "email": "diana@example.com", "company": {"name": "Cloud Co"}},
    {"id": 5, "username": "eve", "email": "eve@example.com", "company": {"name": "Dev House"}}
]
result = users
"""
        ],
    )
    workflow.add_node("user_source", user_source)

    # Extract user data (simulating what we'd do with API response)
    user_extractor = DataTransformer(
        id="user_extractor",
        transformations=[
            """
# Transform user data
result = [{
    "user_id": user["id"],
    "username": user["username"],
    "email": user["email"],
    "company": user["company"]["name"]
} for user in data]
"""
        ],
    )
    workflow.add_node("user_extractor", user_extractor)
    workflow.connect("user_source", "user_extractor", mapping={"result": "data"})

    # Create mock post counts
    post_source = DataTransformer(
        id="post_source",
        transformations=[
            """
# Create mock post count data
post_counts = [
    {"user_id": 1, "post_count": 10},
    {"user_id": 2, "post_count": 5},
    {"user_id": 3, "post_count": 15},
    {"user_id": 4, "post_count": 8},
    {"user_id": 5, "post_count": 12}
]
result = post_counts
"""
        ],
    )
    workflow.add_node("post_source", post_source)

    # Merge user and post data
    merger = MergeNode(id="data_merger", merge_type="merge_dict", key="user_id")
    workflow.add_node("merger", merger)
    workflow.connect("user_extractor", "merger", mapping={"result": "data1"})
    workflow.connect("post_source", "merger", mapping={"result": "data2"})

    # Save results
    writer = CSVWriterNode(
        id="result_writer", file_path="data/outputs/merged_user_data.csv"
    )
    workflow.add_node("writer", writer)
    workflow.connect("merger", "writer", mapping={"merged_data": "data"})

    return workflow


def create_weather_api_workflow() -> Workflow:
    """Create a workflow that fetches weather data from OpenWeatherMap API."""
    workflow = Workflow(
        workflow_id="weather_api_workflow",
        name="weather_api_workflow",
        description="Fetch and process weather data from OpenWeatherMap",
    )

    # Note: For weather API, you need an API key from OpenWeatherMap
    # For demo purposes, we'll use a free tier endpoint
    # Get your free API key at: https://openweathermap.org/api

    # Create a data source node with city list
    city_source = DataTransformer(
        id="city_source",
        transformations=[
            """
# List of cities to fetch weather for
cities = ["London", "New York", "Tokyo", "Sydney", "Paris"]
result = [{"city": city, "country": ""} for city in cities]
"""
        ],
    )
    workflow.add_node("city_source", city_source)

    # For demo without API key, use mock weather data
    weather_simulator = DataTransformer(
        id="weather_simulator",
        transformations=[
            """
# Simulate weather API responses for demo
import random
from datetime import datetime
weather_data = []
for city_info in data:
    city = city_info["city"]
    # Generate realistic weather data
    temp = round(random.uniform(10, 35), 1)
    humidity = random.randint(30, 90)
    weather_data.append({
        "city": city,
        "temperature_c": temp,
        "temperature_f": round(temp * 9/5 + 32, 1),
        "humidity": humidity,
        "conditions": random.choice(["Clear", "Cloudy", "Rainy", "Partly Cloudy"]),
        "wind_speed_kmh": round(random.uniform(5, 30), 1),
        "timestamp": datetime.now().isoformat()
    })
result = weather_data
"""
        ],
    )
    workflow.add_node("weather_simulator", weather_simulator)
    workflow.connect("city_source", "weather_simulator", mapping={"result": "data"})

    # Filter for warm weather cities
    warm_filter = FilterNode(id="warm_weather_filter")
    workflow.add_node("warm_filter", warm_filter)
    workflow.connect("weather_simulator", "warm_filter", mapping={"result": "data"})

    # Calculate weather statistics using DataTransformer
    stats_calculator = DataTransformer(
        id="weather_stats",
        transformations=[
            """
# Calculate weather statistics
if isinstance(data, list) and len(data) > 0:
    temps = [d["temperature_c"] for d in data]
    avg_temp = sum(temps) / len(temps)
    max_temp = max(temps)
    min_temp = min(temps)
    
    humidity_vals = [d["humidity"] for d in data]
    avg_humidity = sum(humidity_vals) / len(humidity_vals)
    
    result = [{
        "metric": "temperature",
        "avg": round(avg_temp, 1),
        "max": max_temp,
        "min": min_temp,
        "unit": "celsius"
    }, {
        "metric": "humidity",
        "avg": round(avg_humidity, 1),
        "max": max(humidity_vals),
        "min": min(humidity_vals),
        "unit": "percent"
    }]
else:
    result = []
"""
        ],
    )
    workflow.add_node("stats_calculator", stats_calculator)
    workflow.connect(
        "weather_simulator", "stats_calculator", mapping={"result": "data"}
    )

    # Save all weather data
    all_weather_writer = CSVWriterNode(
        id="all_weather_writer", file_path="data/outputs/weather_data.csv"
    )
    workflow.add_node("all_weather_writer", all_weather_writer)
    workflow.connect(
        "weather_simulator", "all_weather_writer", mapping={"result": "data"}
    )

    # Save warm weather cities
    warm_weather_writer = CSVWriterNode(
        id="warm_weather_writer", file_path="data/outputs/warm_weather_cities.csv"
    )
    workflow.add_node("warm_weather_writer", warm_weather_writer)
    workflow.connect(
        "warm_filter", "warm_weather_writer", mapping={"filtered_data": "data"}
    )

    # Save weather statistics
    stats_writer = CSVWriterNode(
        id="stats_writer", file_path="data/outputs/weather_statistics.csv"
    )
    workflow.add_node("stats_writer", stats_writer)
    workflow.connect("stats_calculator", "stats_writer", mapping={"result": "data"})

    return workflow


def run_jsonplaceholder_workflow():
    """Run the JSONPlaceholder API workflow."""
    workflow = create_jsonplaceholder_workflow()
    runtime = LocalRuntime()

    parameters = {
        "users_api": {},
        "posts_api": {},
        "user_content_extractor": {},
        "post_content_extractor": {},
        "user_extractor": {},
        "post_extractor": {},
        "merger": {},
    }

    try:
        print("Fetching data from JSONPlaceholder API...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("API workflow complete!")
        print("Results saved to: data/outputs/user_analytics.csv")
        return result
    except Exception as e:
        print(f"API workflow failed: {str(e)}")
        raise


def run_weather_workflow():
    """Run weather API workflow."""
    workflow = create_weather_api_workflow()
    runtime = LocalRuntime()

    parameters = {
        "city_source": {},
        "weather_simulator": {},
        "warm_filter": {"field": "temperature_c", "operator": ">=", "value": 25},
        "stats_calculator": {},
    }

    try:
        print("Running weather API workflow...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("Workflow complete!")
        print("Weather data saved to: data/outputs/weather_data.csv")
        print("Warm cities saved to: data/outputs/warm_weather_cities.csv")
        return result
    except Exception as e:
        print(f"Workflow failed: {str(e)}")
        raise


def run_simple_workflow():
    """Run simple data workflow."""
    workflow = create_simple_data_workflow()
    runtime = LocalRuntime()

    parameters = {
        "user_source": {},
        "user_extractor": {},
        "post_source": {},
        "merger": {},
    }

    try:
        print("Running simple data workflow...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("Workflow complete!")
        print("Results saved to: data/outputs/merged_user_data.csv")
        return result
    except Exception as e:
        print(f"Workflow failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    import sys

    # Create output directory
    os.makedirs("data/outputs", exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == "jsonplaceholder":
        # Run JSONPlaceholder API workflow (real API, no auth needed)
        run_jsonplaceholder_workflow()
    elif len(sys.argv) > 1 and sys.argv[1] == "simple":
        # Run simple data workflow
        run_simple_workflow()
    else:
        # Run weather workflow (simulated data)
        print("Running weather workflow with simulated data...")
        print("To run with real API: use OpenWeatherMap API")
        run_weather_workflow()


if __name__ == "__main__":
    main()
