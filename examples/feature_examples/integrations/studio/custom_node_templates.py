"""
Custom Node Templates for Kailash Workflow Studio

This file provides template JSON structures for creating different types of custom nodes:
1. Python-based nodes - Execute Python code
2. Workflow-based nodes - Compose nodes from other workflows
3. API-based nodes - Wrap external REST APIs

These templates can be used:
- Via the Studio API POST /api/custom-nodes endpoint
- In the Studio UI when creating custom nodes
- As reference for the JSON structure required
"""

import json
from typing import Any

# ============================================================================
# PYTHON-BASED CUSTOM NODES
# ============================================================================

sentiment_analyzer_template = {
    "name": "SentimentAnalyzer",
    "category": "nlp",
    "description": "Analyzes sentiment of text using rule-based approach",
    "icon": "sentiment_satisfied",
    "color": "#FF9800",
    "parameters": [
        {
            "name": "text_column",
            "type": "str",
            "required": True,
            "description": "Column containing text to analyze",
        },
        {
            "name": "threshold",
            "type": "float",
            "required": False,
            "default": 0.5,
            "description": "Sentiment score threshold for classification",
        },
    ],
    "inputs": [{"name": "data", "type": "DataFrame", "required": True}],
    "outputs": [
        {
            "name": "output",
            "type": "DataFrame",
            "description": "Data with sentiment scores and labels",
        }
    ],
    "implementation_type": "python",
    "implementation": {
        "code": """
# Simple sentiment analysis based on word lists
positive_words = ['good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'love', 'best']
negative_words = ['bad', 'terrible', 'awful', 'horrible', 'hate', 'worst', 'poor', 'disappointing']

def analyze_sentiment(text):
    if not text:
        return 0.0

    text_lower = str(text).lower()
    words = text_lower.split()

    pos_count = sum(1 for word in words if word in positive_words)
    neg_count = sum(1 for word in words if word in negative_words)

    if pos_count + neg_count == 0:
        return 0.0

    sentiment_score = (pos_count - neg_count) / (pos_count + neg_count)
    return sentiment_score

# Apply sentiment analysis
text_col = parameters['text_column']
threshold = parameters.get('threshold', 0.5)

data['sentiment_score'] = data[text_col].apply(analyze_sentiment)
data['sentiment'] = data['sentiment_score'].apply(
    lambda x: 'positive' if x > threshold else ('negative' if x < -threshold else 'neutral')
)

return data
"""
    },
}

data_validator_template = {
    "name": "DataValidator",
    "category": "validation",
    "description": "Validates data quality with configurable rules",
    "icon": "fact_check",
    "color": "#4CAF50",
    "parameters": [
        {
            "name": "validation_rules",
            "type": "list",
            "default": ["not_null", "unique", "data_types"],
            "description": "List of validation rules to apply",
        },
        {
            "name": "strict_mode",
            "type": "bool",
            "default": False,
            "description": "Fail on any validation error",
        },
    ],
    "inputs": [{"name": "data", "type": "DataFrame", "required": True}],
    "outputs": [
        {"name": "valid_data", "type": "DataFrame"},
        {"name": "invalid_data", "type": "DataFrame"},
        {"name": "validation_report", "type": "Dict"},
    ],
    "implementation_type": "python",
    "implementation": {
        "code": """
import pandas as pd

rules = parameters.get('validation_rules', ['not_null'])
strict = parameters.get('strict_mode', False)

report = {
    'total_rows': len(data),
    'passed': True,
    'errors': []
}

# Apply validation rules
valid_mask = pd.Series([True] * len(data), index=data.index)

if 'not_null' in rules:
    null_mask = data.isnull().any(axis=1)
    if null_mask.any():
        report['errors'].append({
            'rule': 'not_null',
            'count': null_mask.sum(),
            'columns': data.columns[data.isnull().any()].tolist()
        })
        valid_mask &= ~null_mask

if 'unique' in rules:
    dup_mask = data.duplicated()
    if dup_mask.any():
        report['errors'].append({
            'rule': 'unique',
            'count': dup_mask.sum()
        })
        valid_mask &= ~dup_mask

if 'data_types' in rules:
    # Check for numeric columns that contain non-numeric data
    for col in data.select_dtypes(include=['object']).columns:
        try:
            pd.to_numeric(data[col], errors='coerce')
            # If successful, it could be numeric
        except:
            pass  # Keep as object type

report['passed'] = len(report['errors']) == 0
report['valid_count'] = valid_mask.sum()
report['invalid_count'] = (~valid_mask).sum()

# Split data
valid_data = data[valid_mask] if not strict or report['passed'] else pd.DataFrame()
invalid_data = data[~valid_mask]

return {
    'valid_data': valid_data,
    'invalid_data': invalid_data,
    'validation_report': report
}
"""
    },
}

# ============================================================================
# WORKFLOW-BASED CUSTOM NODES
# ============================================================================

data_quality_pipeline_template = {
    "name": "DataQualityPipeline",
    "category": "composite",
    "description": "Comprehensive data quality pipeline using multiple nodes",
    "icon": "hub",
    "color": "#9C27B0",
    "parameters": [
        {
            "name": "generate_report",
            "type": "bool",
            "default": True,
            "description": "Generate detailed quality report",
        }
    ],
    "inputs": [{"name": "raw_data", "type": "DataFrame", "required": True}],
    "outputs": [
        {"name": "clean_data", "type": "DataFrame"},
        {"name": "quality_report", "type": "Dict"},
    ],
    "implementation_type": "workflow",
    "implementation": {
        "workflow_definition": {
            "nodes": [
                {
                    "id": "validator",
                    "type": "DataValidator",
                    "config": {
                        "validation_rules": ["not_null", "unique"],
                        "strict_mode": False,
                    },
                },
                {
                    "id": "profiler",
                    "type": "PythonCodeNode",
                    "config": {
                        "code": """
# Generate data profile
profile = {
    'shape': data.shape,
    'columns': data.columns.tolist(),
    'dtypes': data.dtypes.to_dict(),
    'missing_values': data.isnull().sum().to_dict(),
    'unique_counts': {col: data[col].nunique() for col in data.columns}
}
return {'profile': profile, 'data': data}
"""
                    },
                },
                {
                    "id": "merger",
                    "type": "PythonCodeNode",
                    "config": {
                        "code": """
# Merge validation report and profile
quality_report = {
    'validation': inputs.get('validation_report', {}),
    'profile': inputs.get('profile', {}),
    'timestamp': str(datetime.now())
}
return quality_report
"""
                    },
                },
            ],
            "connections": [
                {"from": "input", "to": "validator", "input": "data"},
                {
                    "from": "validator",
                    "output": "valid_data",
                    "to": "profiler",
                    "input": "data",
                },
                {
                    "from": "validator",
                    "output": "validation_report",
                    "to": "merger",
                    "input": "validation_report",
                },
                {
                    "from": "profiler",
                    "output": "profile",
                    "to": "merger",
                    "input": "profile",
                },
                {
                    "from": "validator",
                    "output": "valid_data",
                    "to": "output",
                },
                {"from": "merger", "to": "output", "output": "quality_report"},
            ],
        }
    },
}

# ============================================================================
# API-BASED CUSTOM NODES
# ============================================================================

geocoding_api_template = {
    "name": "GeocodingService",
    "category": "enrichment",
    "description": "Geocode addresses using external API",
    "icon": "pin_drop",
    "color": "#2196F3",
    "parameters": [
        {
            "name": "address_column",
            "type": "str",
            "required": True,
            "description": "Column containing addresses",
        },
        {
            "name": "api_key",
            "type": "str",
            "required": True,
            "sensitive": True,
            "description": "API key for geocoding service",
        },
        {
            "name": "batch_size",
            "type": "int",
            "default": 100,
            "description": "Number of addresses to geocode per batch",
        },
    ],
    "inputs": [{"name": "data", "type": "DataFrame", "required": True}],
    "outputs": [{"name": "geocoded_data", "type": "DataFrame"}],
    "implementation_type": "api",
    "implementation": {
        "base_url": "https://api.geocoding-service.com/v1",
        "auth": {"type": "api_key", "header": "X-API-Key", "value": "{{api_key}}"},
        "endpoints": [
            {
                "name": "batch_geocode",
                "path": "/batch",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "addresses": "{{addresses}}",
                    "options": {"include_confidence": True, "include_components": True},
                },
                "response_mapping": {
                    "results": "$.results",
                    "latitude": "$.results[*].location.lat",
                    "longitude": "$.results[*].location.lng",
                    "confidence": "$.results[*].confidence",
                    "formatted": "$.results[*].formatted_address",
                },
            }
        ],
        "rate_limit": {"requests_per_minute": 60, "concurrent_requests": 5},
        "retry": {"max_attempts": 3, "backoff_factor": 2},
        "error_handling": {
            "on_error": "skip",
            "default_values": {"latitude": None, "longitude": None, "confidence": 0.0},
        },
    },
}

weather_enrichment_template = {
    "name": "WeatherDataEnricher",
    "category": "enrichment",
    "description": "Add current weather data to records",
    "icon": "wb_sunny",
    "color": "#FFC107",
    "parameters": [
        {
            "name": "location_column",
            "type": "str",
            "required": True,
            "description": "Column with location names or coordinates",
        },
        {"name": "api_key", "type": "str", "required": True, "sensitive": True},
        {
            "name": "units",
            "type": "str",
            "default": "metric",
            "choices": ["metric", "imperial"],
            "description": "Temperature units",
        },
    ],
    "inputs": [{"name": "data", "type": "DataFrame", "required": True}],
    "outputs": [{"name": "weather_enriched_data", "type": "DataFrame"}],
    "implementation_type": "api",
    "implementation": {
        "base_url": "https://api.openweathermap.org/data/2.5",
        "endpoints": [
            {
                "name": "current_weather",
                "path": "/weather",
                "method": "GET",
                "params_template": {
                    "q": "{{location}}",
                    "appid": "{{api_key}}",
                    "units": "{{units}}",
                },
                "response_mapping": {
                    "temperature": "$.main.temp",
                    "feels_like": "$.main.feels_like",
                    "humidity": "$.main.humidity",
                    "pressure": "$.main.pressure",
                    "weather": "$.weather[0].main",
                    "weather_desc": "$.weather[0].description",
                    "wind_speed": "$.wind.speed",
                    "wind_direction": "$.wind.deg",
                    "clouds": "$.clouds.all",
                },
            }
        ],
        "cache": {"enabled": True, "ttl_seconds": 600},  # Cache for 10 minutes
    },
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_custom_node_examples():
    """Generate example custom nodes in different categories"""

    examples = {
        "python_nodes": [sentiment_analyzer_template, data_validator_template],
        "workflow_nodes": [data_quality_pipeline_template],
        "api_nodes": [geocoding_api_template, weather_enrichment_template],
    }

    return examples


def print_node_summary(node_template: dict[str, Any]):
    """Print a summary of a node template"""
    print(f"\nNode: {node_template['name']}")
    print(f"Type: {node_template['implementation_type']}")
    print(f"Category: {node_template['category']}")
    print(f"Description: {node_template['description']}")
    print(f"Parameters: {[p['name'] for p in node_template.get('parameters', [])]}")
    print(f"Inputs: {[i['name'] for i in node_template.get('inputs', [])]}")
    print(f"Outputs: {[o['name'] for o in node_template.get('outputs', [])]}")


def export_node_templates(output_dir: str = "./custom_node_templates"):
    """Export node templates as JSON files"""
    import os

    os.makedirs(output_dir, exist_ok=True)

    examples = create_custom_node_examples()

    for category, nodes in examples.items():
        category_dir = os.path.join(output_dir, category)
        os.makedirs(category_dir, exist_ok=True)

        for node in nodes:
            filename = f"{node['name'].lower()}.json"
            filepath = os.path.join(category_dir, filename)

            with open(filepath, "w") as f:
                json.dump(node, f, indent=2)

            print(f"✅ Exported: {filepath}")


# ============================================================================
# EXAMPLE WORKFLOW USING CUSTOM NODES
# ============================================================================

example_workflow_with_custom_nodes = {
    "name": "Advanced Data Processing Pipeline",
    "description": "Workflow combining multiple custom nodes",
    "nodes": [
        {
            "id": "reader",
            "type": "CSVReaderNode",
            "config": {"file_path": "customer_feedback.csv"},
        },
        {
            "id": "sentiment",
            "type": "SentimentAnalyzer",
            "config": {"text_column": "feedback", "threshold": 0.3},
        },
        {
            "id": "quality",
            "type": "DataQualityPipeline",
            "config": {"generate_report": True},
        },
        {
            "id": "geocoder",
            "type": "GeocodingService",
            "config": {"address_column": "address", "api_key": "${GEOCODING_API_KEY}"},
        },
        {
            "id": "weather",
            "type": "WeatherDataEnricher",
            "config": {
                "location_column": "city",
                "api_key": "${WEATHER_API_KEY}",
                "units": "metric",
            },
        },
        {
            "id": "writer",
            "type": "CSVWriterNode",
            "config": {"file_path": "enriched_feedback.csv"},
        },
    ],
    "connections": [
        {"from": "reader", "to": "sentiment"},
        {"from": "sentiment", "to": "quality", "input": "raw_data"},
        {"from": "quality", "output": "clean_data", "to": "geocoder"},
        {"from": "geocoder", "output": "geocoded_data", "to": "weather"},
        {"from": "weather", "output": "weather_enriched_data", "to": "writer"},
    ],
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=== Kailash Custom Node Templates ===\n")

    examples = create_custom_node_examples()

    # Print summaries
    for category, nodes in examples.items():
        print(f"\n{category.upper()}")
        print("=" * 50)
        for node in nodes:
            print_node_summary(node)

    # Show example workflow
    print("\n\nEXAMPLE WORKFLOW")
    print("=" * 50)
    print(json.dumps(example_workflow_with_custom_nodes, indent=2))

    # Optionally export templates
    print("\n\nTo export these templates as JSON files, uncomment the line below:")
    print("# export_node_templates()")

    print("\n✅ Custom node templates ready for use!")
