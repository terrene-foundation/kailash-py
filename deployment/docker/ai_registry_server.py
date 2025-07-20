import asyncio
import json
from typing import Dict, List, Any
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_registry_mcp")

# Sample AI registry data
AI_REGISTRY = [
    {
        "company": "Healthcare AI Inc",
        "use_case": "Medical diagnosis assistance",
        "implementation": "Deep learning model for X-ray analysis",
        "category": "Healthcare",
        "tags": ["healthcare", "diagnosis", "deep learning"]
    },
    {
        "company": "FinTech Solutions",
        "use_case": "Fraud detection system",
        "implementation": "Real-time transaction monitoring with ML",
        "category": "Finance",
        "tags": ["finance", "fraud", "machine learning"]
    },
    {
        "company": "Retail Analytics",
        "use_case": "Customer behavior prediction",
        "implementation": "Recommendation engine using collaborative filtering",
        "category": "Retail",
        "tags": ["retail", "recommendations", "analytics"]
    },
    {
        "company": "Manufacturing AI",
        "use_case": "Predictive maintenance",
        "implementation": "IoT sensor data analysis with time series ML",
        "category": "Manufacturing",
        "tags": ["manufacturing", "IoT", "predictive maintenance"]
    },
    {
        "company": "AgriTech Innovation",
        "use_case": "Crop yield optimization",
        "implementation": "Satellite imagery analysis with computer vision",
        "category": "Agriculture",
        "tags": ["agriculture", "computer vision", "optimization"]
    }
]

# Create MCP server
server = Server("ai-registry")

@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools for AI Registry."""
    return [
        Tool(
            name="search_use_cases",
            description="Search AI use cases by query or category",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (Healthcare, Finance, Retail, etc.)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 10
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_categories",
            description="Get list of all AI use case categories",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="analyze_implementation",
            description="Get detailed analysis of a specific AI implementation",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name"
                    }
                },
                "required": ["company"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool execution."""
    
    if name == "search_use_cases":
        query = arguments.get("query", "").lower()
        category = arguments.get("category", "").lower()
        limit = arguments.get("limit", 10)
        
        results = []
        for item in AI_REGISTRY:
            # Check if query matches
            if query and not any(query in field.lower() for field in [
                item["company"], item["use_case"], item["implementation"], 
                item["category"], " ".join(item["tags"])
            ]):
                continue
            
            # Check if category matches
            if category and category not in item["category"].lower():
                continue
            
            results.append(item)
            
        results = results[:limit]
        
        return [TextContent(
            type="text",
            text=f"Found {len(results)} AI use cases:\n\n" + 
                 "\n\n".join([
                     f"**{r['company']}**\n" +
                     f"- Use Case: {r['use_case']}\n" +
                     f"- Implementation: {r['implementation']}\n" +
                     f"- Category: {r['category']}\n" +
                     f"- Tags: {', '.join(r['tags'])}"
                     for r in results
                 ])
        )]
    
    elif name == "get_categories":
        categories = sorted(set(item["category"] for item in AI_REGISTRY))
        return [TextContent(
            type="text",
            text=f"Available AI use case categories:\n\n" + "\n".join(f"- {cat}" for cat in categories)
        )]
    
    elif name == "analyze_implementation":
        company = arguments.get("company", "")
        item = next((i for i in AI_REGISTRY if i["company"].lower() == company.lower()), None)
        
        if not item:
            return [TextContent(
                type="text",
                text=f"No implementation found for company: {company}"
            )]
        
        return [TextContent(
            type="text",
            text=f"**AI Implementation Analysis: {item['company']}**\n\n" +
                 f"**Use Case:** {item['use_case']}\n\n" +
                 f"**Implementation Details:** {item['implementation']}\n\n" +
                 f"**Industry Category:** {item['category']}\n\n" +
                 f"**Key Technologies:** {', '.join(item['tags'])}\n\n" +
                 f"**Analysis:**\n" +
                 f"This implementation leverages modern AI techniques to address " +
                 f"specific challenges in the {item['category']} sector. " +
                 f"The approach demonstrates practical application of " +
                 f"{item['tags'][0]} technology for real-world business value."
        )]
    
    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]

# Add health check endpoint for HTTP mode
from fastapi import FastAPI
import uvicorn
import threading

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "healthy", "server": "ai-registry"}

def run_http_server():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

async def main():
    """Run the MCP server."""
    # Start HTTP health check in background
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Run MCP server
    logger.info("Starting AI Registry MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ai-registry",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())