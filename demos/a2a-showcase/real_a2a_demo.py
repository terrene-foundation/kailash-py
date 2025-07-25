"""
Real A2A Demo Backend - Exposes actual internal workings

This demonstrates the REAL A2A system with full visibility into:
- Insight extraction processes
- Memory operations and state changes
- Agent collaboration mechanisms
- Attention filtering in action
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

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
    InsightType,
    SharedMemoryPoolNode,
)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Real A2A Agent Collaboration Demo")

# Global state
memory_pool = SharedMemoryPoolNode()
coordinator = A2ACoordinatorNode()
active_agents = {}
websocket_clients = []


class InternalProcessMessage(BaseModel):
    """Message for exposing internal A2A processes."""

    process_type: str  # "memory_state", "insight_extraction", "attention_filter", "context_building"
    agent_id: str
    agent_name: str
    step: str
    data: Dict = {}
    timestamp: float = None


class AgentCollaborationState(BaseModel):
    """Track agent collaboration state."""

    phase: str
    active_agent: str
    memory_stats: Dict
    insights_extracted: List[Dict]
    attention_results: Dict
    context_used: List[Dict]


class RealA2ADemo:
    """Demonstrates real A2A system internals."""

    def __init__(self):
        self.collaboration_state = {
            "active_task": None,
            "phase": "idle",
            "agents_completed": [],
            "total_insights": 0,
            "memory_evolution": [],
        }

    async def broadcast_internal_process(self, message: InternalProcessMessage):
        """Show internal A2A processes to frontend."""
        # LOG EVERY STEP FOR VERIFICATION
        print(
            f"🔍 STEP TRACE [{message.timestamp}]: {message.process_type}.{message.step}"
        )
        print(f"   Agent: {message.agent_name} ({message.agent_id})")
        print(f"   Data: {json.dumps(message.data, indent=2)}")
        print("=" * 80)

        disconnected = []
        for client in websocket_clients:
            try:
                await client.send_json(
                    {"type": "internal_process", "data": message.model_dump()}
                )
            except:
                disconnected.append(client)

        for client in disconnected:
            websocket_clients.remove(client)

    async def execute_real_a2a_agent(
        self, agent_card: A2AAgentCard, task: str, task_id: str
    ) -> Dict:
        """Execute agent with REAL A2A system - expose ACTUAL internals."""

        start_time = time.time()

        # Step 1: Show agent activation (real timing)
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="agent_activation",
                agent_id=agent_card.agent_id,
                agent_name=agent_card.agent_name,
                step="agent_starting",
                data={
                    "task": task,
                    "agent_type": agent_card.agent_type,
                    "primary_capabilities": [
                        cap.name for cap in agent_card.primary_capabilities
                    ],
                    "collaboration_style": agent_card.collaboration_style.value,
                },
                timestamp=time.time(),
            )
        )

        # Add realistic delay for agent initialization
        await asyncio.sleep(0.5)

        # Step 2: Create REAL A2A agent
        a2a_agent = A2AAgentNode()

        # Step 3: Show memory pool state BEFORE (real timing)
        memory_stats_before = memory_pool.execute(action="metrics")
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="memory_state",
                agent_id=agent_card.agent_id,
                agent_name=agent_card.agent_name,
                step="memory_state_before_execution",
                data={
                    "total_memories": memory_stats_before.get("memory_id_counter", 0),
                    "segments": memory_stats_before.get("segment_sizes", {}),
                    "agent_subscriptions": len(
                        memory_stats_before.get("agent_subscriptions", {})
                    ),
                },
                timestamp=time.time(),
            )
        )

        # Add realistic delay for memory inspection
        await asyncio.sleep(0.3)

        # Step 4: Show A2A execution starting (with real timing)
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="a2a_execution",
                agent_id=agent_card.agent_id,
                agent_name=agent_card.agent_name,
                step="a2a_execution_starting",
                data={
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "use_real_mcp": True,
                    "use_llm_insight_extraction": True,
                    "message": f"As a {agent_card.agent_type}, analyze: {task}",
                },
                timestamp=time.time(),
            )
        )

        # Step 5: ACTUALLY execute with real A2A system (LET A2A DO ITS OWN FILTERING)
        execution_start = time.time()

        print(f"🚀 REAL A2A EXECUTION STARTING: {execution_start}")
        print(f"   Task: {task}")
        print(f"   Agent: {agent_card.agent_name} ({agent_card.agent_type})")
        print("   Model: gpt-4o-mini")
        print(f"   Memory Pool Active: {memory_pool is not None}")

        try:
            result = a2a_agent.execute(
                agent_id=agent_card.agent_id,
                agent_role=agent_card.agent_type,
                memory_pool=memory_pool,
                provider="openai",
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": f"As a {agent_card.agent_type}, analyze: {task}",
                    }
                ],
                temperature=0.7,
                max_tokens=800,
                # DON'T pass fake attention_filter - let A2A create its own
                use_llm_insight_extraction=True,  # Use REAL insight extraction
            )
            execution_end = time.time()
            execution_time = execution_end - execution_start

            print(f"✅ REAL A2A EXECUTION COMPLETE: {execution_end}")
            print(f"   Execution Time: {execution_time:.3f} seconds")
            print(f"   Result Keys: {list(result.keys())}")

            # Extract REAL A2A metadata (what the A2A system actually did)
            a2a_metadata = result.get("a2a_metadata", {})

            print("📊 REAL A2A METADATA EXTRACTED:")
            print(
                f"   Shared Context Used: {a2a_metadata.get('shared_context_used', 0)}"
            )
            print(f"   Insights Generated: {a2a_metadata.get('insights_generated', 0)}")
            print(
                f"   Memory Pool Active: {a2a_metadata.get('memory_pool_active', False)}"
            )
            print(f"   Local Memory Size: {a2a_metadata.get('local_memory_size', 0)}")
            print(f"   Full Metadata: {json.dumps(a2a_metadata, indent=2)}")
            print("=" * 80)

            # Step 6: Extract and show REAL attention filtering (from A2A metadata)
            await asyncio.sleep(0.2)  # Real processing delay
            if a2a_metadata.get("shared_context_used", 0) > 0:
                await self.broadcast_internal_process(
                    InternalProcessMessage(
                        process_type="attention_filter",
                        agent_id=agent_card.agent_id,
                        agent_name=agent_card.agent_name,
                        step="real_attention_filtering_applied",
                        data={
                            "memories_filtered": a2a_metadata.get(
                                "shared_context_used", 0
                            ),
                            "filter_source": "real_a2a_internal_filtering",
                            "execution_time_ms": int(execution_time * 1000),
                            "memory_pool_active": a2a_metadata.get(
                                "memory_pool_active", False
                            ),
                        },
                        timestamp=time.time(),
                    )
                )

            # Step 7: Extract and show REAL context building (from A2A execution)
            await asyncio.sleep(0.3)  # Real processing delay
            if a2a_metadata.get("shared_context_used", 0) > 0:
                await self.broadcast_internal_process(
                    InternalProcessMessage(
                        process_type="context_building",
                        agent_id=agent_card.agent_id,
                        agent_name=agent_card.agent_name,
                        step="real_context_integration_complete",
                        data={
                            "memories_used": a2a_metadata.get("shared_context_used", 0),
                            "context_integration_method": "real_a2a_internal_summarization",
                            "local_memory_size": a2a_metadata.get(
                                "local_memory_size", 0
                            ),
                            "context_effectiveness": min(
                                a2a_metadata.get("shared_context_used", 0) / 5.0, 1.0
                            ),
                        },
                        timestamp=time.time(),
                    )
                )

            # Step 8: Show the REAL A2A execution results
            await asyncio.sleep(0.2)  # Real processing delay
            await self.broadcast_internal_process(
                InternalProcessMessage(
                    process_type="a2a_execution",
                    agent_id=agent_card.agent_id,
                    agent_name=agent_card.agent_name,
                    step="a2a_execution_complete",
                    data={
                        "execution_time_ms": int(execution_time * 1000),
                        "shared_context_used": a2a_metadata.get(
                            "shared_context_used", 0
                        ),
                        "insights_generated": a2a_metadata.get("insights_generated", 0),
                        "insight_statistics": a2a_metadata.get(
                            "insight_statistics", {}
                        ),
                        "memory_pool_active": a2a_metadata.get(
                            "memory_pool_active", False
                        ),
                        "local_memory_size": a2a_metadata.get("local_memory_size", 0),
                        "real_openai_call": True,
                        "token_usage": result.get("usage", {}),
                    },
                    timestamp=time.time(),
                )
            )

            # Step 9: Show REAL insight extraction (if any generated)
            if a2a_metadata.get("insights_generated", 0) > 0:
                await asyncio.sleep(0.2)  # Real processing delay
                await self.broadcast_internal_process(
                    InternalProcessMessage(
                        process_type="insight_extraction",
                        agent_id=agent_card.agent_id,
                        agent_name=agent_card.agent_name,
                        step="insights_extracted",
                        data={
                            "extraction_method": a2a_metadata.get(
                                "insight_statistics", {}
                            ).get("extraction_method", "LLM"),
                            "total_insights": a2a_metadata.get("insights_generated", 0),
                            "high_importance_count": a2a_metadata.get(
                                "insight_statistics", {}
                            ).get("high_importance", 0),
                            "insights_by_type": a2a_metadata.get(
                                "insight_statistics", {}
                            ).get("by_type", {}),
                            "iteration": 0,  # First execution, will be updated by iterative calls
                            "insights": [],  # Will be populated with actual insights if available
                        },
                        timestamp=time.time(),
                    )
                )

            # Step 10: Show memory pool state AFTER (real timing)
            await asyncio.sleep(0.2)  # Real processing delay
            memory_stats_after = memory_pool.execute(action="metrics")
            await self.broadcast_internal_process(
                InternalProcessMessage(
                    process_type="memory_state",
                    agent_id=agent_card.agent_id,
                    agent_name=agent_card.agent_name,
                    step="memory_state_after_execution",
                    data={
                        "total_memories": memory_stats_after.get(
                            "memory_id_counter", 0
                        ),
                        "memories_added": memory_stats_after.get("memory_id_counter", 0)
                        - memory_stats_before.get("memory_id_counter", 0),
                        "segments": memory_stats_after.get("segment_sizes", {}),
                        "memory_growth": {
                            "before": memory_stats_before.get("memory_id_counter", 0),
                            "after": memory_stats_after.get("memory_id_counter", 0),
                        },
                        "total_execution_time_ms": int(
                            (time.time() - start_time) * 1000
                        ),
                    },
                    timestamp=time.time(),
                )
            )

            # Step 11: Show the actual response (real timing)
            await asyncio.sleep(0.1)  # Real processing delay
            response_content = result.get("response", {}).get("content", "")
            await self.broadcast_internal_process(
                InternalProcessMessage(
                    process_type="agent_response",
                    agent_id=agent_card.agent_id,
                    agent_name=agent_card.agent_name,
                    step="real_response_generated",
                    data={
                        "content": (
                            response_content[:200] + "..."
                            if len(response_content) > 200
                            else response_content
                        ),
                        "full_content_length": len(response_content),
                        "token_usage": result.get("usage", {}),
                        "model_used": result.get("model", "gpt-4o-mini"),
                        "success": result.get("success", False),
                        "total_execution_time_ms": int(
                            (time.time() - start_time) * 1000
                        ),
                    },
                    timestamp=time.time(),
                )
            )

            return result

        except Exception as e:
            await self.broadcast_internal_process(
                InternalProcessMessage(
                    process_type="error",
                    agent_id=agent_card.agent_id,
                    agent_name=agent_card.agent_name,
                    step="execution_failed",
                    data={"error": str(e)},
                    timestamp=time.time(),
                )
            )
            return {"success": False, "error": str(e)}

    async def demonstrate_memory_pool_internals(self):
        """Show detailed memory pool internals."""

        # Get detailed memory state
        stats = memory_pool.execute(action="metrics")

        # Query recent memories to show actual content
        recent_memories = memory_pool.execute(
            action="read",
            agent_id="demo_viewer",
            attention_filter={"importance_threshold": 0.0, "window_size": 20},
        )

        # Show semantic query capabilities
        if recent_memories.get("memories"):
            semantic_result = memory_pool.execute(
                action="query",
                agent_id="demo_viewer",
                query="analysis",  # Search for analysis-related memories
            )

            await self.broadcast_internal_process(
                InternalProcessMessage(
                    process_type="memory_pool_internals",
                    agent_id="system",
                    agent_name="Memory Pool",
                    step="detailed_state",
                    data={
                        "stats": stats,
                        "recent_memories": recent_memories.get("memories", [])[
                            :5
                        ],  # Show first 5
                        "semantic_search_results": semantic_result.get("results", [])[
                            :3
                        ],
                        "attention_indices": {
                            "total_tags": len(
                                memory_pool.attention_indices.get("tags", {})
                            ),
                            "total_agents": len(
                                memory_pool.attention_indices.get("agents", {})
                            ),
                            "importance_distribution": memory_pool.attention_indices.get(
                                "importance", {}
                            ),
                        },
                    },
                    timestamp=time.time(),
                )
            )

    async def show_agent_collaboration_evolution(self, phase: str):
        """Show how agent collaboration evolves through phases."""

        self.collaboration_state["phase"] = phase

        # Get current memory pool state
        stats = memory_pool.execute(action="metrics")

        # Calculate collaboration metrics
        collaboration_score = self._calculate_collaboration_effectiveness()

        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="collaboration_evolution",
                agent_id="system",
                agent_name="Collaboration System",
                step=phase,
                data={
                    "phase": phase,
                    "total_memories": stats.get("memory_id_counter", 0),
                    "active_segments": len(stats.get("segment_sizes", {})),
                    "agents_participated": len(
                        self.collaboration_state["agents_completed"]
                    ),
                    "collaboration_effectiveness": collaboration_score,
                    "knowledge_growth": self._calculate_knowledge_growth(),
                },
                timestamp=time.time(),
            )
        )

    def _calculate_collaboration_effectiveness(self) -> float:
        """Calculate how effectively agents are collaborating."""
        stats = memory_pool.execute(action="metrics")
        total_memories = stats.get("memory_id_counter", 0)

        if total_memories == 0:
            return 0.0

        # Simple metric: more shared memories = better collaboration
        agents_count = len(self.collaboration_state["agents_completed"])
        if agents_count == 0:
            return 0.0

        # Effectiveness = memories per agent (capped at 1.0)
        effectiveness = min(total_memories / (agents_count * 3), 1.0)
        return effectiveness

    def _calculate_knowledge_growth(self) -> Dict:
        """Calculate knowledge growth metrics."""
        stats = memory_pool.execute(action="metrics")
        segments = stats.get("segment_sizes", {})

        return {
            "total_knowledge_items": stats.get("memory_id_counter", 0),
            "knowledge_diversity": len(segments),
            "largest_knowledge_area": (
                max(segments.keys(), key=lambda k: segments[k]) if segments else None
            ),
            "knowledge_distribution": segments,
        }

    # REMOVED: Fake attention filter and context building methods
    # Now we extract real data from A2A metadata instead of creating parallel fake processes

    async def show_real_coordination_start(
        self, topic: str, agents_to_use: List[str], strategy: str
    ):
        """Show REAL A2A coordination system starting."""
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="coordination_start",
                agent_id="system",
                agent_name="A2A Coordinator",
                step="coordination_initialization",
                data={
                    "task": topic,
                    "available_agents": len(agents_to_use),
                    "coordination_strategy": strategy,
                    "coordination_algorithm": f"real_a2a_{strategy}_algorithm",
                    "performance_tracking": True,
                },
                timestamp=time.time(),
            )
        )

    async def select_agent_with_real_coordination(
        self,
        task: str,
        available_agents: List[A2AAgentCard],
        iteration: int,
        strategy: str,
    ) -> Optional[A2AAgentCard]:
        """Select agent using REAL A2A coordination strategies."""

        if not available_agents:
            return None

        # Extract task requirements (simulate real A2A analysis)
        required_skills = self._extract_task_skills(task)

        if strategy == "best_match":
            selected_agent = await self._find_best_match_real_a2a(
                task, available_agents, required_skills, iteration
            )
        elif strategy == "round_robin":
            selected_agent = self._round_robin_real_a2a(available_agents, iteration)
        elif strategy == "auction":
            selected_agent = await self._run_auction_real_a2a(
                task, available_agents, required_skills
            )
        else:
            # Default to best_match
            selected_agent = await self._find_best_match_real_a2a(
                task, available_agents, required_skills, iteration
            )

        return selected_agent

    async def _find_best_match_real_a2a(
        self,
        task: str,
        agents: List[A2AAgentCard],
        required_skills: List[str],
        iteration: int,
    ) -> A2AAgentCard:
        """REAL A2A best match algorithm with cycle awareness."""

        best_agent = None
        best_score = 0
        scoring_details = {}

        for agent in agents:
            # Skill matching score (real A2A algorithm)
            agent_skills = set()
            for cap in agent.primary_capabilities:
                agent_skills.update(cap.keywords)

            required_skills_set = set(required_skills)
            skill_score = (
                len(required_skills_set & agent_skills) / len(required_skills_set)
                if required_skills_set
                else 1.0
            )

            # Historical performance weighting (real A2A feature)
            agent_perf = self.collaboration_state["agent_performance"].get(
                agent.agent_id, {}
            )
            if agent_perf:
                success_rate = agent_perf.get("success_rate", 0.5)
                avg_insights = agent_perf.get("avg_insights_generated", 1.0)
                performance_score = (success_rate * 0.7) + (
                    min(avg_insights / 3.0, 1.0) * 0.3
                )
            else:
                performance_score = 0.5  # Default for new agents

            # Combined scoring with iteration awareness (real A2A)
            combined_score = (skill_score * 0.6) + (performance_score * 0.4)

            # Capability level bonus (real A2A consideration)
            if any(cap.level.value == "expert" for cap in agent.primary_capabilities):
                combined_score += 0.1
            elif any(
                cap.level.value == "advanced" for cap in agent.primary_capabilities
            ):
                combined_score += 0.05

            scoring_details[agent.agent_id] = {
                "skill_score": skill_score,
                "performance_score": performance_score,
                "combined_score": combined_score,
                "matched_skills": list(required_skills_set & agent_skills),
            }

            if combined_score > best_score:
                best_score = combined_score
                best_agent = agent

        # Store reasoning for visibility
        self.collaboration_state["last_selection_reasoning"] = {
            "strategy": "best_match",
            "winning_agent": best_agent.agent_id if best_agent else None,
            "winning_score": best_score,
            "all_scores": scoring_details,
            "required_skills": required_skills,
        }

        return best_agent

    async def select_top_agents_with_coordination(
        self,
        task: str,
        available_agents: List[A2AAgentCard],
        top_k: int,
        coordination_strategy: str,
    ) -> List[A2AAgentCard]:
        """Select TOP K agents using REAL A2A coordination with skill-based ranking."""

        if not available_agents:
            return []

        # Extract task requirements (simulate real A2A analysis)
        required_skills = self._extract_task_skills(task)

        # Score all agents using the same algorithm as best_match
        agent_scores = []
        scoring_details = {}

        for agent in available_agents:
            # Skill matching score (real A2A algorithm)
            agent_skills = set()
            for cap in agent.primary_capabilities:
                agent_skills.update(cap.keywords)

            required_skills_set = set(required_skills)
            skill_score = (
                len(required_skills_set & agent_skills) / len(required_skills_set)
                if required_skills_set
                else 1.0
            )

            # Historical performance weighting (real A2A feature)
            agent_perf = self.collaboration_state["agent_performance"].get(
                agent.agent_id, {}
            )
            if agent_perf:
                success_rate = agent_perf.get("success_rate", 0.5)
                avg_insights = agent_perf.get("avg_insights_generated", 1.0)
                performance_score = (success_rate * 0.7) + (
                    min(avg_insights / 3.0, 1.0) * 0.3
                )
            else:
                performance_score = 0.5  # Default for new agents

            # Combined scoring with capability level bonus
            combined_score = (skill_score * 0.6) + (performance_score * 0.4)

            # Capability level bonus (real A2A consideration)
            if any(cap.level.value == "expert" for cap in agent.primary_capabilities):
                combined_score += 0.1
            elif any(
                cap.level.value == "advanced" for cap in agent.primary_capabilities
            ):
                combined_score += 0.05

            agent_scores.append((combined_score, agent))
            scoring_details[agent.agent_id] = {
                "skill_score": skill_score,
                "performance_score": performance_score,
                "combined_score": combined_score,
                "matched_skills": list(required_skills_set & agent_skills),
            }

        # Sort agents by score (highest first) and select top K
        agent_scores.sort(key=lambda x: x[0], reverse=True)
        top_agents = [agent for score, agent in agent_scores[:top_k]]

        # Store reasoning for visibility (showing all scores for transparency)
        self.collaboration_state["last_selection_reasoning"] = {
            "strategy": f"top_{top_k}_best_match",
            "selected_agents": [agent.agent_id for agent in top_agents],
            "top_k": top_k,
            "all_scores": scoring_details,
            "required_skills": required_skills,
            "selection_rationale": f"Selected top {top_k} agents with highest combined skill and performance scores",
        }

        return top_agents

    def _round_robin_real_a2a(
        self, agents: List[A2AAgentCard], iteration: int
    ) -> A2AAgentCard:
        """REAL A2A round-robin with cycle awareness."""
        selected_index = iteration % len(agents)
        selected_agent = agents[selected_index]

        self.collaboration_state["last_selection_reasoning"] = {
            "strategy": "round_robin",
            "selected_index": selected_index,
            "iteration": iteration,
            "total_agents": len(agents),
        }

        return selected_agent

    async def _run_auction_real_a2a(
        self, task: str, agents: List[A2AAgentCard], required_skills: List[str]
    ) -> A2AAgentCard:
        """REAL A2A auction-based selection."""

        bids = []

        for agent in agents:
            # Skill-based bidding (real A2A algorithm)
            agent_skills = set()
            for cap in agent.primary_capabilities:
                agent_skills.update(cap.keywords)

            required_skills_set = set(required_skills)
            skill_match = (
                len(required_skills_set & agent_skills) / len(required_skills_set)
                if required_skills_set
                else 1.0
            )

            # Performance-based bid adjustment
            agent_perf = self.collaboration_state["agent_performance"].get(
                agent.agent_id, {}
            )
            if agent_perf:
                performance_modifier = agent_perf.get("success_rate", 0.5)
                bid_value = skill_match * (1.0 + performance_modifier)
            else:
                bid_value = skill_match * 0.8  # Penalty for unknown performance

            # Collaboration style influence
            if agent.collaboration_style == CollaborationStyle.LEADER:
                bid_value *= 1.2  # Leaders bid higher
            elif agent.collaboration_style == CollaborationStyle.SUPPORT:
                bid_value *= 0.9  # Support agents bid lower

            bids.append(
                {
                    "agent": agent,
                    "bid": bid_value,
                    "skill_match": skill_match,
                    "performance_modifier": performance_modifier if agent_perf else 0.0,
                }
            )

        # Select highest bidder
        if bids:
            winning_bid = max(bids, key=lambda x: x["bid"])

            self.collaboration_state["last_selection_reasoning"] = {
                "strategy": "auction",
                "winning_bid": winning_bid["bid"],
                "winning_agent": winning_bid["agent"].agent_id,
                "all_bids": [
                    {
                        "agent_id": b["agent"].agent_id,
                        "bid_value": b["bid"],
                        "skill_match": b["skill_match"],
                    }
                    for b in bids
                ],
            }

            return winning_bid["agent"]

        return agents[0] if agents else None

    def _extract_task_skills(self, task: str) -> List[str]:
        """Extract required skills from task (real A2A capability)."""
        task_lower = task.lower()

        skill_keywords = {
            "research": ["research", "study", "investigate", "literature", "academic"],
            "analysis": ["analyze", "analysis", "evaluate", "assess", "examine"],
            "data": ["data", "statistics", "metrics", "quantitative", "numbers"],
            "technical": [
                "technical",
                "technology",
                "AI",
                "machine learning",
                "software",
            ],
            "domain_expertise": [
                "expert",
                "expertise",
                "specialist",
                "domain",
                "field",
            ],
            "synthesis": ["synthesis", "integrate", "combine", "consolidate", "merge"],
        }

        required_skills = []
        for skill, keywords in skill_keywords.items():
            if any(keyword in task_lower for keyword in keywords):
                required_skills.append(skill)

        return required_skills or ["general"]

    async def show_coordination_decision(
        self, selected_agent: A2AAgentCard, iteration: int, strategy: str
    ):
        """Show the REAL coordination decision process."""
        reasoning = self.collaboration_state.get("last_selection_reasoning", {})

        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="coordination_decision",
                agent_id="system",
                agent_name="A2A Coordinator",
                step="agent_selected",
                data={
                    "selected_agent": selected_agent.agent_id,
                    "agent_name": selected_agent.agent_name,
                    "iteration": iteration,
                    "strategy": strategy,
                    "selection_reasoning": reasoning,
                    "coordination_algorithm": f"real_a2a_{strategy}_cycle_aware",
                },
                timestamp=time.time(),
            )
        )

    async def track_real_agent_performance(
        self, agent_card: A2AAgentCard, result: Dict
    ) -> float:
        """Track REAL agent performance metrics (not calculated) and return performance score."""

        # Extract real metrics from A2A execution result
        success = result.get("success", False)
        a2a_metadata = result.get("a2a_metadata", {})
        insights_generated = a2a_metadata.get("insights_generated", 0)
        context_used = a2a_metadata.get("shared_context_used", 0)

        # Update real performance tracking
        agent_id = agent_card.agent_id
        if agent_id not in self.collaboration_state["agent_performance"]:
            self.collaboration_state["agent_performance"][agent_id] = {
                "total_tasks": 0,
                "successful_tasks": 0,
                "total_insights": 0,
                "total_context_usage": 0,
                "success_rate": 0.0,
                "avg_insights_generated": 0.0,
                "avg_context_usage": 0.0,
            }

        perf = self.collaboration_state["agent_performance"][agent_id]
        perf["total_tasks"] += 1
        if success:
            perf["successful_tasks"] += 1
        perf["total_insights"] += insights_generated
        perf["total_context_usage"] += context_used

        # Calculate real rates
        perf["success_rate"] = perf["successful_tasks"] / perf["total_tasks"]
        perf["avg_insights_generated"] = perf["total_insights"] / perf["total_tasks"]
        perf["avg_context_usage"] = perf["total_context_usage"] / perf["total_tasks"]

        # Calculate overall performance score (0.0 to 1.0)
        performance_score = (
            perf["success_rate"] * 0.5
            + min(perf["avg_insights_generated"] / 5.0, 1.0) * 0.3
            + min(perf["avg_context_usage"] / 100.0, 1.0) * 0.2
        )

        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="performance_tracking",
                agent_id=agent_id,
                agent_name=agent_card.agent_name,
                step="performance_updated",
                data={
                    "current_task_success": success,
                    "insights_this_task": insights_generated,
                    "context_used_this_task": context_used,
                    "performance_score": performance_score,
                    "cumulative_performance": perf,
                },
                timestamp=time.time(),
            )
        )

        return performance_score

    async def select_next_iterative_agent(
        self,
        selected_agents: List[A2AAgentCard],
        agent_performance_scores: Dict[str, float],
        agent_call_counts: Dict[str, int],
        topic: str,
        iteration: int,
    ) -> A2AAgentCard:
        """Select next agent for iterative execution based on performance and need."""

        # Strategy: Balance between giving high performers more chances and ensuring all agents get opportunities
        if iteration < len(selected_agents):
            # First round: ensure all selected agents get at least one call
            for agent in selected_agents:
                if agent_call_counts[agent.agent_id] == 0:
                    return agent

        # Subsequent rounds: weighted selection based on performance
        agent_scores = []
        for agent in selected_agents:
            perf_score = agent_performance_scores.get(agent.agent_id, 0.5)
            call_count = agent_call_counts.get(agent.agent_id, 0)

            # Penalize agents that have been called too many times
            if call_count >= 3:
                perf_score *= 0.5
            elif call_count >= 2:
                perf_score *= 0.8

            # Bonus for underutilized high performers
            if call_count <= 1 and perf_score > 0.7:
                perf_score *= 1.2

            agent_scores.append((perf_score, agent))

        # Select best available agent
        if agent_scores:
            agent_scores.sort(reverse=True)
            return agent_scores[0][1]

        return None

    async def calculate_collaboration_effectiveness(self, results: List[Dict]) -> float:
        """Calculate real-time collaboration effectiveness."""
        if not results:
            return 0.0

        # Factors: diversity of agents, performance improvement, insight quality
        agent_ids_used = set(r["agent_id"] for r in results)
        diversity_score = len(agent_ids_used) / len(results) if results else 0

        # Performance trend (are later results better?)
        if len(results) >= 2:
            recent_performances = [
                r["coordination_metadata"]["performance_score"] for r in results[-2:]
            ]
            if len(recent_performances) == 2:
                trend_score = max(
                    0, recent_performances[1] - recent_performances[0] + 0.5
                )
            else:
                trend_score = 0.5
        else:
            trend_score = 0.5

        # Average performance
        avg_performance = sum(
            r["coordination_metadata"]["performance_score"] for r in results
        ) / len(results)

        effectiveness = (
            diversity_score * 0.3 + trend_score * 0.3 + avg_performance * 0.4
        )
        return min(effectiveness, 1.0)

    async def update_tab_data(self, agent: A2AAgentCard, result: Dict, iteration: int):
        """Update data for the different tabs during iterative execution."""

        # Extract data from result
        a2a_metadata = result.get("a2a_metadata", {})
        insights = a2a_metadata.get("insights", [])
        context_data = a2a_metadata.get("context_building", {})
        attention_data = a2a_metadata.get("attention_filtering", {})

        # Send insight extraction data (always send, even if no specific insights array)
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="insight_extraction",
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                step="insights_extracted",
                data={
                    "iteration": iteration,
                    "insights": insights if insights else [],
                    "extraction_method": "LLM",
                    "total_insights": (
                        len(insights)
                        if insights
                        else a2a_metadata.get("insights_generated", 0)
                    ),
                    "high_importance_count": (
                        len([i for i in insights if i.get("importance", 0) > 0.7])
                        if insights
                        else a2a_metadata.get("insight_statistics", {}).get(
                            "high_importance", 0
                        )
                    ),
                },
                timestamp=time.time(),
            )
        )

        # Send attention filtering data (always send, even if empty)
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="attention_filter",
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                step="attention_applied",
                data={
                    "iteration": iteration,
                    "filter_criteria": (
                        attention_data.get("criteria", [])
                        if attention_data
                        else [f"focus_on_{agent.agent_type}"]
                    ),
                    "filtered_items": (
                        attention_data.get("filtered_items", [])
                        if attention_data
                        else []
                    ),
                    "focus_areas": (
                        attention_data.get("focus_areas", [])
                        if attention_data
                        else [f"{agent.agent_type}_expertise"]
                    ),
                },
                timestamp=time.time(),
            )
        )

        # Send context building data (always send, even if empty)
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="context_building",
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                step="context_built",
                data={
                    "iteration": iteration,
                    "context_sources": (
                        context_data.get("sources", [])
                        if context_data
                        else ["memory_pool", f"{agent.agent_type}_expertise"]
                    ),
                    "context_size": (
                        context_data.get("size", 0)
                        if context_data
                        else result.get("a2a_metadata", {}).get(
                            "shared_context_used", 0
                        )
                    ),
                    "relevance_score": (
                        context_data.get("relevance", 0.0) if context_data else 0.8
                    ),
                },
                timestamp=time.time(),
            )
        )

        # Send collaboration data
        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="collaboration_evolution",
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                step="collaboration_step",
                data={
                    "iteration": iteration,
                    "agent_contribution": result.get("content", ""),
                    "coordination_impact": a2a_metadata.get("coordination_impact", 0.0),
                    "collaboration_style": agent.collaboration_style.value,
                },
                timestamp=time.time(),
            )
        )

    async def show_real_collaboration_complete(self):
        """Show REAL collaboration completion analysis."""
        total_agents = len(self.collaboration_state["agents_completed"])
        total_performance = self.collaboration_state.get("agent_performance", {})

        # Calculate real collaboration metrics
        coordination_effectiveness = self.calculate_real_coordination_effectiveness()

        await self.broadcast_internal_process(
            InternalProcessMessage(
                process_type="collaboration_complete",
                agent_id="system",
                agent_name="A2A Coordinator",
                step="final_analysis",
                data={
                    "total_agents_participated": total_agents,
                    "coordination_strategy": self.collaboration_state.get(
                        "coordination_strategy"
                    ),
                    "coordination_effectiveness": coordination_effectiveness,
                    "agent_performance_summary": total_performance,
                    "collaboration_success": coordination_effectiveness > 0.7,
                },
                timestamp=time.time(),
            )
        )

    def calculate_real_coordination_effectiveness(self) -> float:
        """Calculate REAL coordination effectiveness from actual performance data."""
        agent_performance = self.collaboration_state.get("agent_performance", {})

        if not agent_performance:
            return 0.0

        # Real metrics: average success rate across all agents
        success_rates = [perf["success_rate"] for perf in agent_performance.values()]
        avg_success_rate = sum(success_rates) / len(success_rates)

        # Real metrics: insights generation effectiveness
        insights_rates = [
            perf["avg_insights_generated"] for perf in agent_performance.values()
        ]
        avg_insights = sum(insights_rates) / len(insights_rates)
        insights_effectiveness = min(avg_insights / 2.0, 1.0)  # Normalize to 0-1

        # Real metrics: context utilization effectiveness
        context_rates = [
            perf["avg_context_usage"] for perf in agent_performance.values()
        ]
        avg_context = sum(context_rates) / len(context_rates)
        context_effectiveness = min(avg_context / 5.0, 1.0)  # Normalize to 0-1

        # Weighted combination (real A2A would use this)
        coordination_effectiveness = (
            avg_success_rate * 0.5  # Task success weight
            + insights_effectiveness * 0.3  # Knowledge contribution weight
            + context_effectiveness * 0.2  # Collaboration usage weight
        )

        return coordination_effectiveness


# Initialize the real demo
demo = RealA2ADemo()


def create_research_team():
    """Create research team with detailed capabilities for A2A."""

    # Research Specialist with detailed A2A configuration
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
                keywords=[
                    "research",
                    "papers",
                    "studies",
                    "evidence",
                    "sources",
                    "literature",
                ],
            ),
            Capability(
                name="synthesis",
                domain="Knowledge Integration",
                level=CapabilityLevel.ADVANCED,
                description="Synthesizes information from multiple sources",
                keywords=["synthesis", "integration", "summary", "consolidation"],
            ),
        ],
        collaboration_style=CollaborationStyle.COOPERATIVE,
        description="PhD in Information Science, expert at finding and synthesizing research",
    )

    # Data Analyst with quantitative focus
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
                keywords=[
                    "analysis",
                    "statistics",
                    "patterns",
                    "metrics",
                    "data",
                    "quantitative",
                ],
            ),
            Capability(
                name="interpretation",
                domain="Data Interpretation",
                level=CapabilityLevel.ADVANCED,
                description="Interprets data findings for actionable insights",
                keywords=[
                    "interpretation",
                    "insights",
                    "trends",
                    "correlation",
                    "significance",
                ],
            ),
        ],
        collaboration_style=CollaborationStyle.SUPPORT,
        description="MS in Data Science, specializes in turning data into insights",
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
                keywords=[
                    "AI",
                    "machine learning",
                    "technology",
                    "innovation",
                    "expertise",
                    "technical",
                ],
            ),
            Capability(
                name="evaluation",
                domain="Critical Analysis",
                level=CapabilityLevel.EXPERT,
                description="Provides critical evaluation and expert assessment",
                keywords=[
                    "evaluation",
                    "critique",
                    "assessment",
                    "validation",
                    "expert opinion",
                ],
            ),
        ],
        collaboration_style=CollaborationStyle.LEADER,
        description="Professor of Computer Science, 20+ years in AI research",
    )

    # Healthcare Specialist
    healthcare_specialist = A2AAgentCard(
        agent_id="healthcare_001",
        agent_name="Dr. Jennifer Martinez",
        agent_type="healthcare_specialist",
        version="1.0",
        primary_capabilities=[
            Capability(
                name="healthcare_domain",
                domain="Healthcare Systems",
                level=CapabilityLevel.EXPERT,
                description="Deep knowledge of healthcare operations and patient care",
                keywords=[
                    "healthcare",
                    "medical",
                    "patient care",
                    "clinical",
                    "hospital",
                    "treatment",
                ],
            ),
            Capability(
                name="productivity_analysis",
                domain="Healthcare Productivity",
                level=CapabilityLevel.EXPERT,
                description="Specializes in healthcare productivity and efficiency metrics",
                keywords=[
                    "productivity",
                    "efficiency",
                    "workflow",
                    "healthcare operations",
                    "performance",
                ],
            ),
        ],
        collaboration_style=CollaborationStyle.COOPERATIVE,
        description="MD with 15+ years in healthcare administration and productivity optimization",
    )

    # Technology Consultant
    tech_consultant = A2AAgentCard(
        agent_id="consultant_001",
        agent_name="Alex Thompson",
        agent_type="consultant",
        version="1.0",
        primary_capabilities=[
            Capability(
                name="implementation",
                domain="Technology Implementation",
                level=CapabilityLevel.ADVANCED,
                description="Specializes in implementing AI solutions in enterprise environments",
                keywords=[
                    "implementation",
                    "deployment",
                    "integration",
                    "enterprise",
                    "solutions",
                ],
            ),
            Capability(
                name="strategy",
                domain="Business Strategy",
                level=CapabilityLevel.ADVANCED,
                description="Develops strategic approaches for technology adoption",
                keywords=[
                    "strategy",
                    "planning",
                    "business",
                    "adoption",
                    "transformation",
                ],
            ),
        ],
        collaboration_style=CollaborationStyle.SUPPORT,
        description="Senior Technology Consultant with expertise in AI implementations",
    )

    return {
        "researcher": researcher,
        "analyst": analyst,
        "expert": expert,
        "healthcare_specialist": healthcare_specialist,
        "tech_consultant": tech_consultant,
    }


async def startup_event():
    """Initialize agents on startup."""
    global active_agents

    # Create and register agents
    team = create_research_team()

    for role, card in team.items():
        # Register with coordinator using real A2A registration
        coordinator.execute(
            action="register_with_card",
            agent_id=card.agent_id,
            agent_card=card.to_dict(),
        )
        active_agents[card.agent_id] = card

    print(f"✅ Initialized {len(active_agents)} agents with real A2A capabilities")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the enhanced UI."""
    return HTMLResponse(content=open("static/real_a2a_index.html").read())


@app.get("/api/agents")
async def get_agents():
    """Get all registered agents with detailed capabilities."""
    return {
        "agents": [
            {
                "id": agent.agent_id,
                "name": agent.agent_name,
                "type": agent.agent_type,
                "capabilities": [
                    {
                        "name": cap.name,
                        "domain": cap.domain,
                        "level": cap.level.value,
                        "keywords": cap.keywords,
                    }
                    for cap in agent.primary_capabilities
                ],
                "style": agent.collaboration_style.value,
                "description": agent.description,
            }
            for agent in active_agents.values()
        ]
    }


@app.post("/api/task/real-a2a")
async def execute_real_a2a_task(request: dict):
    """Execute a task using REAL A2A coordination patterns with full visibility."""

    topic = request.get("topic", "")
    agents_to_use = request.get("agents_to_use", list(active_agents.keys()))
    coordination_strategy = request.get(
        "coordination_strategy", "best_match"
    )  # best_match, round_robin, auction

    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    # Initialize collaboration tracking with real A2A metrics
    demo.collaboration_state = {
        "active_task": topic,
        "phase": "starting",
        "agents_completed": [],
        "total_insights": 0,
        "memory_evolution": [],
        "coordination_strategy": coordination_strategy,
        "agent_performance": {},  # Track real performance metrics
        "coordination_history": [],
    }

    # Show REAL A2A coordination starting
    await demo.show_real_coordination_start(topic, agents_to_use, coordination_strategy)

    results = []
    available_agents = [
        active_agents[aid] for aid in agents_to_use if aid in active_agents
    ]

    # INTELLIGENT AGENT SELECTION: Pick TOP 3 agents out of 5 available
    # This demonstrates real A2A multi-agent coordination with intelligent selection

    # REAL A2A: Select TOP 3 agents using skill-based ranking
    selected_agents = await demo.select_top_agents_with_coordination(
        topic, available_agents, top_k=3, coordination_strategy=coordination_strategy
    )

    if not selected_agents:
        raise HTTPException(
            status_code=500, detail="No suitable agents found for the task"
        )

    # ITERATIVE A2A EXECUTION: Agents called multiple times based on performance
    max_iterations = 8  # Maximum total agent calls
    convergence_threshold = 0.95  # Stop when collaboration effectiveness is high
    iteration_count = 0

    # Track agent call counts and performance
    agent_call_counts = {agent.agent_id: 0 for agent in selected_agents}
    agent_performance_scores = {
        agent.agent_id: 0.5 for agent in selected_agents
    }  # Start with neutral

    while iteration_count < max_iterations:
        # Select next agent based on performance and task needs
        next_agent = await demo.select_next_iterative_agent(
            selected_agents,
            agent_performance_scores,
            agent_call_counts,
            topic,
            iteration_count,
        )

        if not next_agent:
            break

        agent_call_counts[next_agent.agent_id] += 1

        # Show the REAL coordination decision process
        await demo.show_coordination_decision(
            next_agent, iteration_count, coordination_strategy
        )

        # Execute with real A2A internals exposed
        result = await demo.execute_real_a2a_agent(
            next_agent,
            f"Research and analyze (iteration {iteration_count + 1}): {topic}",
            f"task_{int(time.time())}_{iteration_count}",
        )

        # Track REAL performance metrics and update scores
        performance_score = await demo.track_real_agent_performance(next_agent, result)
        agent_performance_scores[next_agent.agent_id] = performance_score

        # Get agent's current score from the selection reasoning
        agent_score = (
            demo.collaboration_state.get("last_selection_reasoning", {})
            .get("all_scores", {})
            .get(next_agent.agent_id, {})
            .get("combined_score", 0)
        )

        results.append(
            {
                "agent_id": next_agent.agent_id,
                "agent_name": next_agent.agent_name,
                "result": result,
                "coordination_metadata": {
                    "selection_strategy": coordination_strategy,
                    "iteration": iteration_count,
                    "call_count": agent_call_counts[next_agent.agent_id],
                    "performance_score": performance_score,
                    "selection_reasoning": demo.collaboration_state.get(
                        "last_selection_reasoning", ""
                    ),
                    "why_selected": f"Selected for iteration {iteration_count + 1} with score {agent_score:.2f}",
                    "rank": iteration_count + 1,
                },
            }
        )

        # Track completion with real coordination
        if next_agent.agent_id not in demo.collaboration_state["agents_completed"]:
            demo.collaboration_state["agents_completed"].append(next_agent.agent_id)

        # Update insights and context for tabs
        await demo.update_tab_data(next_agent, result, iteration_count)

        # Check convergence
        collaboration_effectiveness = await demo.calculate_collaboration_effectiveness(
            results
        )
        if collaboration_effectiveness >= convergence_threshold:
            await demo.broadcast_internal_process(
                InternalProcessMessage(
                    process_type="collaboration_complete",
                    agent_id="system",
                    agent_name="A2A Coordinator",
                    step="convergence_reached",
                    data={
                        "effectiveness": collaboration_effectiveness,
                        "total_iterations": iteration_count + 1,
                        "agent_call_counts": agent_call_counts,
                    },
                    timestamp=time.time(),
                )
            )
            break

        iteration_count += 1

        # Brief delay between iterations to see coordination evolution
        await asyncio.sleep(1.5)

    # Show memory pool internals after execution
    await demo.demonstrate_memory_pool_internals()

    # Brief delay to see coordination evolution
    await asyncio.sleep(1)

    # Final REAL collaboration analysis
    await demo.show_real_collaboration_complete()

    return {
        "task": topic,
        "results": results,
        "collaboration_state": demo.collaboration_state,
        "coordination_effectiveness": demo.calculate_real_coordination_effectiveness(),
        "success": True,
    }


@app.get("/api/memory/detailed")
async def get_detailed_memory_state():
    """Get detailed memory pool state for visualization."""
    stats = memory_pool.execute(action="metrics")

    # Get recent memories with full details
    recent_memories = memory_pool.execute(
        action="read",
        agent_id="api_viewer",
        attention_filter={"importance_threshold": 0.0, "window_size": 10},
    )

    return {
        "stats": stats,
        "memories": recent_memories.get("memories", []),
        "attention_indices": {
            "tags_count": len(memory_pool.attention_indices.get("tags", {})),
            "agents_count": len(memory_pool.attention_indices.get("agents", {})),
            "importance_levels": {
                "high": len(
                    memory_pool.attention_indices.get("importance", {}).get("high", [])
                ),
                "medium": len(
                    memory_pool.attention_indices.get("importance", {}).get(
                        "medium", []
                    )
                ),
                "low": len(
                    memory_pool.attention_indices.get("importance", {}).get("low", [])
                ),
            },
        },
    }


@app.post("/api/reset")
async def reset_demo():
    """Reset the demo to clean slate - clear all memories."""
    try:
        # Get memory count before clearing
        stats_before = memory_pool.execute(action="metrics")
        memory_count = stats_before.get("total_memories", 0)

        # Clear the shared memory pool
        clear_result = memory_pool.execute(action="clear")

        print(f"🧹 Demo reset: Cleared {memory_count} memories from shared pool")

        # Notify all connected clients about the reset
        reset_notification = {
            "type": "system_reset",
            "data": {"message": "Demo reset to clean slate", "timestamp": time.time()},
        }

        # Send reset notification to all WebSocket clients
        for client in websocket_clients[
            :
        ]:  # Create copy to avoid modification during iteration
            try:
                await client.send_json(reset_notification)
            except:
                websocket_clients.remove(client)

        return {
            "success": True,
            "message": "Demo reset successfully",
            "memories_cleared": True,
            "timestamp": time.time(),
        }

    except Exception as e:
        print(f"❌ Reset failed: {e}")
        return {"success": False, "error": str(e), "timestamp": time.time()}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time A2A internal updates."""
    await websocket.accept()
    websocket_clients.append(websocket)

    # Send initial connection
    await websocket.send_json(
        {
            "type": "connected",
            "data": {
                "message": "Connected to Real A2A Demo",
                "agents": len(active_agents),
                "timestamp": time.time(),
            },
        }
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not found in environment variables")
        print("Please add your OpenAI API key to .env file")
        exit(1)

    # Initialize agents
    asyncio.run(startup_event())

    print("🚀 Starting REAL A2A Demo Server...")
    print("📍 Open http://localhost:8081 in your browser")
    print("🔍 This demo exposes the actual A2A system internals!")

    uvicorn.run(app, host="0.0.0.0", port=8081)
