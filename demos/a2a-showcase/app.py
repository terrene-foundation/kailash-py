"""
A2A Interactive Demo Application

Real-time visualization of agent collaboration using actual OpenAI API.
Shows internal workings, message passing, and insight generation.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from kailash.nodes.ai.a2a import (
    A2AAgentCard,
    A2AAgentNode,
    A2ACoordinatorNode,
    Capability,
    CapabilityLevel,
    CollaborationStyle,
    SharedMemoryPoolNode,
)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="A2A Agent Collaboration Demo")

# Global state
memory_pool = SharedMemoryPoolNode()
coordinator = A2ACoordinatorNode()
active_agents = {}
websocket_clients = []


class AgentMessage(BaseModel):
    """Message structure for agent communication."""

    agent_id: str
    agent_name: str
    message_type: str  # "thinking", "insight", "memory_read", "memory_write"
    content: str
    metadata: Dict = {}
    timestamp: float = None


class TaskRequest(BaseModel):
    """Request to create a new task."""

    topic: str
    task_type: str = "research"
    agents_to_use: List[str] = []


class DemoState:
    """Manages demo state and broadcasts updates."""

    def __init__(self):
        self.messages: List[AgentMessage] = []
        self.insights: List[Dict] = []
        self.memory_stats = {}
        self.agent_states = {}

    async def broadcast_message(self, message: AgentMessage):
        """Broadcast message to all connected clients."""
        self.messages.append(message)

        # Send to all websocket clients
        disconnected = []
        for client in websocket_clients:
            try:
                await client.send_json(
                    {"type": "agent_message", "data": message.dict()}
                )
            except:
                disconnected.append(client)

        # Clean up disconnected clients
        for client in disconnected:
            websocket_clients.remove(client)

    async def broadcast_state_update(self, update_type: str, data: Dict):
        """Broadcast state updates to clients."""
        disconnected = []
        for client in websocket_clients:
            try:
                await client.send_json({"type": update_type, "data": data})
            except:
                disconnected.append(client)

        for client in disconnected:
            websocket_clients.remove(client)


# Initialize demo state
demo_state = DemoState()


def create_research_team():
    """Create a team of research agents with real capabilities."""

    # Research Specialist
    researcher = A2AAgentCard(
        agent_id="researcher_001",
        agent_name="Dr. Emma Chen",
        agent_type="researcher",
        version="1.0",
        primary_capabilities=[
            Capability(
                name="research",
                domain="Academic Research",
                level=CapabilityLevel.EXPERT,
                description="Conducts thorough research and literature reviews",
                keywords=["research", "papers", "studies", "evidence", "sources"],
            ),
            Capability(
                name="synthesis",
                domain="Knowledge Integration",
                level=CapabilityLevel.ADVANCED,
                description="Synthesizes information from multiple sources",
                keywords=["synthesis", "integration", "summary"],
            ),
        ],
        collaboration_style=CollaborationStyle.COOPERATIVE,
        description="PhD in Information Science, 10+ years research experience",
    )

    # Data Analyst
    analyst = A2AAgentCard(
        agent_id="analyst_001",
        agent_name="Marcus Johnson",
        agent_type="analyst",
        version="1.0",
        primary_capabilities=[
            Capability(
                name="data_analysis",
                domain="Quantitative Analysis",
                level=CapabilityLevel.EXPERT,
                description="Analyzes data patterns and statistical trends",
                keywords=["analysis", "statistics", "patterns", "metrics", "data"],
            ),
            Capability(
                name="visualization",
                domain="Data Presentation",
                level=CapabilityLevel.ADVANCED,
                description="Creates clear data visualizations",
                keywords=["charts", "graphs", "visualization", "presentation"],
            ),
        ],
        collaboration_style=CollaborationStyle.SUPPORT,
        description="MS in Data Science, specializes in pattern recognition",
    )

    # Subject Matter Expert
    expert = A2AAgentCard(
        agent_id="expert_001",
        agent_name="Prof. Sarah Williams",
        agent_type="expert",
        version="1.0",
        primary_capabilities=[
            Capability(
                name="domain_expertise",
                domain="AI and Technology",
                level=CapabilityLevel.EXPERT,
                description="Deep expertise in AI, ML, and emerging tech",
                keywords=["AI", "machine learning", "technology", "innovation"],
            ),
            Capability(
                name="critical_analysis",
                domain="Evaluation",
                level=CapabilityLevel.EXPERT,
                description="Provides critical evaluation and insights",
                keywords=["evaluation", "critique", "assessment", "validation"],
            ),
        ],
        collaboration_style=CollaborationStyle.LEADER,
        description="Professor of Computer Science, AI researcher",
    )

    # Technical Writer
    writer = A2AAgentCard(
        agent_id="writer_001",
        agent_name="Alex Thompson",
        agent_type="writer",
        version="1.0",
        primary_capabilities=[
            Capability(
                name="technical_writing",
                domain="Documentation",
                level=CapabilityLevel.EXPERT,
                description="Creates clear, comprehensive documentation",
                keywords=["writing", "documentation", "communication", "clarity"],
            ),
            Capability(
                name="content_organization",
                domain="Information Architecture",
                level=CapabilityLevel.ADVANCED,
                description="Organizes complex information effectively",
                keywords=["structure", "organization", "flow", "coherence"],
            ),
        ],
        collaboration_style=CollaborationStyle.COOPERATIVE,
        description="Technical writer with 8 years experience",
    )

    return {
        "researcher": researcher,
        "analyst": analyst,
        "expert": expert,
        "writer": writer,
    }


async def execute_agent_task(
    agent_card: A2AAgentCard, task: str, shared_context: List[Dict]
) -> Dict:
    """Execute a task with a real A2A agent using OpenAI."""

    # Create A2A agent node
    agent = A2AAgentNode()

    # Notify UI that agent is thinking
    await demo_state.broadcast_message(
        AgentMessage(
            agent_id=agent_card.agent_id,
            agent_name=agent_card.agent_name,
            message_type="thinking",
            content=f"Processing task: {task}",
            metadata={"task": task},
            timestamp=time.time(),
        )
    )

    # Build context from shared memory
    context_summary = ""
    if shared_context:
        context_items = []
        for memory in shared_context[:5]:  # Use top 5 most relevant
            context_items.append(
                f"- {memory.get('agent_id', 'Unknown')}: {memory.get('content', '')}"
            )
        context_summary = "Relevant insights from team:\n" + "\n".join(context_items)

    # Prepare messages for OpenAI
    system_prompt = f"""You are {agent_card.agent_name}, a {agent_card.agent_type} with the following expertise:

Primary Skills:
{chr(10).join(f"- {cap.name}: {cap.description}" for cap in agent_card.primary_capabilities)}

Your collaboration style is {agent_card.collaboration_style.value}.

{context_summary}

Provide thoughtful, specific insights based on your expertise. Be concise but thorough.
Format your response with clear sections and bullet points where appropriate."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    try:
        # Execute with real OpenAI API
        result = agent.execute(
            agent_id=agent_card.agent_id,
            agent_role=agent_card.agent_type,
            memory_pool=memory_pool,
            provider="openai",
            model="gpt-4o-mini",  # Using GPT-4o-mini for faster responses
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            attention_filter={
                "tags": [
                    tag
                    for cap in agent_card.primary_capabilities
                    for tag in cap.keywords
                ],
                "importance_threshold": 0.6,
            },
        )

        if result.get("success"):
            content = result.get("response", {}).get("content", "")

            # Notify UI of completion
            await demo_state.broadcast_message(
                AgentMessage(
                    agent_id=agent_card.agent_id,
                    agent_name=agent_card.agent_name,
                    message_type="insight",
                    content=content,
                    metadata={
                        "shared_context_used": result.get("a2a_metadata", {}).get(
                            "shared_context_used", 0
                        ),
                        "insights_generated": result.get("a2a_metadata", {}).get(
                            "insights_generated", 0
                        ),
                    },
                    timestamp=time.time(),
                )
            )

            # Show memory writes
            insights_count = result.get("a2a_metadata", {}).get("insights_generated", 0)
            if insights_count > 0:
                await demo_state.broadcast_message(
                    AgentMessage(
                        agent_id=agent_card.agent_id,
                        agent_name=agent_card.agent_name,
                        message_type="memory_write",
                        content=f"Shared {insights_count} insights with the team",
                        metadata={"count": insights_count},
                        timestamp=time.time(),
                    )
                )

            return result

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        await demo_state.broadcast_message(
            AgentMessage(
                agent_id=agent_card.agent_id,
                agent_name=agent_card.agent_name,
                message_type="error",
                content=error_msg,
                timestamp=time.time(),
            )
        )
        return {"success": False, "error": error_msg}


@app.on_event("startup")
async def startup_event():
    """Initialize agents on startup."""
    global active_agents

    # Create and register agents
    team = create_research_team()

    for role, card in team.items():
        # Register with coordinator
        coordinator.execute(
            action="register_with_card",
            agent_id=card.agent_id,
            agent_card=card.to_dict(),  # Convert to dict
        )
        active_agents[card.agent_id] = card

    print(f"✅ Initialized {len(active_agents)} agents")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI."""
    return HTMLResponse(content=open("static/index.html").read())


@app.get("/api/agents")
async def get_agents():
    """Get all registered agents."""
    return {
        "agents": [
            {
                "id": agent.agent_id,
                "name": agent.agent_name,
                "type": agent.agent_type,
                "capabilities": [cap.name for cap in agent.primary_capabilities],
                "style": agent.collaboration_style.value,
                "description": agent.description,
            }
            for agent in active_agents.values()
        ]
    }


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get memory pool statistics."""
    stats = memory_pool.execute(action="metrics")
    return stats


@app.post("/api/task/create")
async def create_task(request: TaskRequest):
    """Create and execute a collaborative task."""

    # Create task in coordinator
    task_result = coordinator.execute(
        action="create_task",
        task_type=request.task_type,
        name=f"Research: {request.topic}",
        description=f"Collaborate to research and analyze: {request.topic}",
        requirements=["research", "analysis", "writing"],
        priority="high",
    )

    task_id = task_result["task_id"]

    # Broadcast task creation
    await demo_state.broadcast_state_update(
        "task_created",
        {"task_id": task_id, "topic": request.topic, "timestamp": time.time()},
    )

    # Execute task with each agent in sequence
    agents_to_use = request.agents_to_use or list(active_agents.keys())

    for i, agent_id in enumerate(agents_to_use):
        if agent_id not in active_agents:
            continue

        agent_card = active_agents[agent_id]

        # Notify UI of agent activation
        await demo_state.broadcast_state_update(
            "agent_active",
            {
                "agent_id": agent_id,
                "agent_name": agent_card.agent_name,
                "phase": i + 1,
                "total_phases": len(agents_to_use),
            },
        )

        # Add small delay for UI visibility
        await asyncio.sleep(1)

        # Read from shared memory
        memory_result = memory_pool.execute(
            action="read",
            agent_id=agent_id,
            attention_filter={
                "tags": request.topic.lower().split()
                + [
                    kw for cap in agent_card.primary_capabilities for kw in cap.keywords
                ],
                "importance_threshold": 0.5,
                "window_size": 10,
            },
        )

        shared_context = memory_result.get("memories", [])

        if shared_context:
            await demo_state.broadcast_message(
                AgentMessage(
                    agent_id=agent_id,
                    agent_name=agent_card.agent_name,
                    message_type="memory_read",
                    content=f"Retrieved {len(shared_context)} relevant insights from team memory",
                    metadata={"count": len(shared_context)},
                    timestamp=time.time(),
                )
            )

        # Execute agent task
        await execute_agent_task(
            agent_card,
            f"As a {agent_card.agent_type}, analyze and provide insights on: {request.topic}",
            shared_context,
        )

        # Small delay between agents
        await asyncio.sleep(2)

    # Final summary
    final_stats = memory_pool.execute(action="metrics")
    await demo_state.broadcast_state_update(
        "task_completed",
        {
            "task_id": task_id,
            "total_insights": final_stats["memory_id_counter"],
            "agents_participated": len(agents_to_use),
            "timestamp": time.time(),
        },
    )

    return {
        "task_id": task_id,
        "status": "completed",
        "insights_generated": final_stats["memory_id_counter"],
    }


@app.get("/api/insights/recent")
async def get_recent_insights(limit: int = 10):
    """Get recent insights from memory pool."""
    result = memory_pool.execute(
        action="read",
        agent_id="api",
        attention_filter={"importance_threshold": 0.0, "window_size": limit},
    )

    insights = []
    for memory in result.get("memories", []):
        insights.append(
            {
                "id": memory.get("id"),
                "agent_id": memory.get("agent_id"),
                "content": memory.get("content"),
                "importance": memory.get("importance"),
                "tags": memory.get("tags", []),
                "timestamp": memory.get("timestamp"),
            }
        )

    return {"insights": insights}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    websocket_clients.append(websocket)

    # Send initial state
    await websocket.send_json(
        {
            "type": "connected",
            "data": {"agents": len(active_agents), "timestamp": time.time()},
        }
    )

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)


# Ensure static files are served
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not found in environment variables")
        print("Please add your OpenAI API key to .env file")
        exit(1)

    print("🚀 Starting A2A Demo Server...")
    print("📍 Open http://localhost:8080 in your browser")

    uvicorn.run(app, host="0.0.0.0", port=8080)
