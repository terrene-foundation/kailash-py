"""
Enhanced Enterprise Gateway with Service Discovery

This gateway automatically discovers apps using manifests and provides:
- Dynamic service discovery
- Unified API routing  
- MCP tool aggregation
- Health monitoring
- Inter-app communication
"""

import asyncio
import sys
import os
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add core to Python path
sys.path.insert(0, '/app')

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

from core.discovery import initialize_service_discovery, get_registry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enhanced_gateway")

app = FastAPI(
    title="Enhanced MCP Enterprise Gateway", 
    version="2.0.0",
    description="Service discovery and orchestration for MCP apps"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global registry
registry = None


class MCPRequest(BaseModel):
    """MCP protocol request model."""
    jsonrpc: str = "2.0"
    id: int
    method: str
    params: Optional[Dict[str, Any]] = None


@app.on_event("startup")
async def startup_event():
    """Initialize service discovery on startup."""
    global registry
    logger.info("🚀 Starting Enhanced Enterprise Gateway...")
    
    # Initialize service discovery with mounted apps directory
    from pathlib import Path
    apps_path = Path("/apps")
    if not apps_path.exists():
        logger.warning(f"Mounted apps directory not found at {apps_path}, trying local path...")
        apps_path = Path("apps")
    
    registry = await initialize_service_discovery()
    
    logger.info(f"📋 Discovered {len(registry.services)} services")
    for name, app in registry.services.items():
        logger.info(f"  - {name} ({app.type}): API={app.has_api}, MCP={app.has_mcp}")


@app.get("/health")
async def health_check():
    """Gateway health check."""
    return {
        "status": "healthy",
        "gateway": "enhanced",
        "version": "2.0.0",
        "services": len(registry.services) if registry else 0
    }


@app.get("/api/v1/discovery")
async def get_discovery_info():
    """Get service discovery information."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    return {
        "apps_discovered": len(registry.services),
        "api_services": len(registry.get_api_services()),
        "mcp_services": len(registry.get_mcp_services()),
        "services": {
            name: {
                "type": app.type,
                "version": app.version,
                "description": app.description,
                "has_api": app.has_api,
                "has_mcp": app.has_mcp,
                "tags": app.tags
            }
            for name, app in registry.services.items()
        }
    }


@app.get("/api/v1/services")
async def list_services():
    """List all registered services with health status."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    # Get current health status
    health_status = await registry.check_all_health()
    
    services = {}
    for name, app in registry.services.items():
        services[name] = {
            "type": app.type,
            "version": app.version,
            "description": app.description,
            "capabilities": {
                "api": app.has_api,
                "mcp": app.has_mcp
            },
            "health": health_status.get(name, {"status": "unknown"}),
            "endpoints": app.api_endpoints if app.has_api else [],
            "tools": app.mcp_tools if app.has_mcp else []
        }
    
    return services


@app.get("/api/v1/services/api")
async def list_api_services():
    """List services that provide APIs."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    api_services = registry.get_api_services()
    health_status = await registry.check_all_health()
    
    return {
        service.name: {
            "port": service.api_port,
            "endpoints": service.api_endpoints,
            "health": health_status.get(service.name, {"status": "unknown"}),
            "url": f"http://{service.name}:{service.api_port}"
        }
        for service in api_services
    }


@app.get("/api/v1/services/mcp")
async def list_mcp_services():
    """List services that provide MCP tools."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    mcp_services = registry.get_mcp_services()
    health_status = await registry.check_all_health()
    
    return {
        service.name: {
            "tools": service.mcp_tools,
            "protocol": service.capabilities.get("mcp", {}).get("protocol", "stdio"),
            "health": health_status.get(service.name, {"status": "unknown"})
        }
        for service in mcp_services
    }


@app.get("/api/v1/tools")
async def list_all_tools():
    """Aggregate tools from all MCP services."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    all_tools = {}
    mcp_services = registry.get_mcp_services()
    
    # For each MCP service, try to get tools via MCP protocol
    async with httpx.AsyncClient() as client:
        for service in mcp_services:
            try:
                # Check if service supports HTTP-based MCP
                if service.has_api:
                    mcp_request = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list"
                    }
                    
                    response = await client.post(
                        f"http://{service.name}:{service.api_port}/",
                        json=mcp_request,
                        timeout=10.0,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if "result" in data and "tools" in data["result"]:
                            all_tools[service.name] = data["result"]["tools"]
                        else:
                            # Fallback to manifest tools
                            all_tools[service.name] = [
                                {"name": tool, "description": f"Tool from {service.name}"}
                                for tool in service.mcp_tools
                            ]
                    else:
                        # Try REST API fallback
                        try:
                            rest_response = await client.get(
                                f"http://{service.name}:{service.api_port}/tools",
                                timeout=10.0
                            )
                            if rest_response.status_code == 200:
                                all_tools[service.name] = rest_response.json()
                            else:
                                all_tools[service.name] = {"error": f"HTTP {response.status_code}"}
                        except Exception:
                            all_tools[service.name] = {"error": f"HTTP {response.status_code}"}
                else:
                    # For stdio MCP services, use manifest info
                    all_tools[service.name] = [
                        {"name": tool, "description": f"Tool from {service.name}"}
                        for tool in service.mcp_tools
                    ]
                    
            except Exception as e:
                all_tools[service.name] = {"error": str(e)}
    
    return all_tools


@app.post("/api/v1/tools/{service_name}/{tool_name}")
async def execute_tool(service_name: str, tool_name: str, payload: dict):
    """Execute a tool on a specific service."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    service = registry.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    if not service.has_mcp:
        raise HTTPException(status_code=400, detail=f"Service {service_name} does not provide MCP tools")
    
    # Try to execute via HTTP MCP protocol
    if service.has_api:
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": payload
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"http://{service.name}:{service.api_port}/",
                    json=mcp_request,
                    timeout=30.0,
                    headers={"Content-Type": "application/json"}
                )
                return response.json()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=501, detail=f"Stdio MCP execution not yet supported")


@app.get("/api/v1/proxy/{service_name}")
async def proxy_api_request(service_name: str, request: Request):
    """Proxy API requests to registered services."""
    if not registry:
        raise HTTPException(status_code=503, detail="Service discovery not initialized")
    
    service = registry.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    if not service.has_api:
        raise HTTPException(status_code=400, detail=f"Service {service_name} does not provide API")
    
    # Extract path after service name
    original_path = str(request.url.path)
    proxy_path = original_path.replace(f"/api/v1/proxy/{service_name}", "", 1)
    if not proxy_path:
        proxy_path = "/"
    
    # Forward request to service
    target_url = f"http://{service.name}:{service.api_port}{proxy_path}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                headers=request.headers,
                content=await request.body(),
                timeout=30.0
            )
            
            return JSONResponse(
                content=response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/gateway")
async def gateway_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time gateway updates."""
    await websocket.accept()
    
    try:
        while True:
            # Send periodic health updates
            if registry:
                health_status = await registry.check_all_health()
                await websocket.send_json({
                    "type": "health_update",
                    "services": health_status,
                    "timestamp": asyncio.get_event_loop().time()
                })
            
            await asyncio.sleep(30)  # Send updates every 30 seconds
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


@app.get("/")
async def root():
    """Gateway information."""
    if not registry:
        return {
            "name": "Enhanced MCP Enterprise Gateway",
            "version": "2.0.0",
            "status": "initializing",
            "description": "Service discovery and orchestration for MCP apps"
        }
    
    return {
        "name": "Enhanced MCP Enterprise Gateway",
        "version": "2.0.0",
        "status": "running",
        "description": "Service discovery and orchestration for MCP apps",
        "services": len(registry.services),
        "api_services": len(registry.get_api_services()),
        "mcp_services": len(registry.get_mcp_services()),
        "endpoints": [
            "/health",
            "/api/v1/discovery",
            "/api/v1/services",
            "/api/v1/tools",
            "/api/v1/proxy/{service_name}",
            "/ws/gateway"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")