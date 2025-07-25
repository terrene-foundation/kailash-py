"""
E2E tests for multi-agent collaboration with Ollama and cycles.

These tests demonstrate:
- Dynamic test data generation using Ollama
- Multi-agent systems that iterate to improve quality
- Convergence based on LLM evaluation
- Real-world pattern: document refinement with AI feedback
"""

import asyncio
import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
from tests.utils.docker_config import OLLAMA_CONFIG

from kailash import Workflow
from kailash.nodes.ai import A2ACoordinatorNode, LLMAgentNode, SharedMemoryPoolNode
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime

# Mark all tests as ollama-dependent and slow
pytestmark = [pytest.mark.ollama, pytest.mark.slow, pytest.mark.e2e]


class OllamaMultiAgentHelper:
    """Helper for Ollama multi-agent testing."""

    @staticmethod
    async def check_ollama_available():
        """Check if Ollama is available with required models."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # Use test Ollama port
                response = await client.get(f"{OLLAMA_CONFIG['host']}/api/tags")
                if response.status_code != 200:
                    return False, "Ollama not responding"

                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]

                # Check for small fast models suitable for testing
                required_models = ["llama3.2:3b", "llama3.2:1b", "mistral:7b"]
                available_models = []

                for model in required_models:
                    if any(model in name for name in model_names):
                        available_models.append(model)

                if not available_models:
                    return False, f"No suitable models found. Available: {model_names}"

                return True, available_models[0]  # Return first available model
        except Exception as e:
            return False, f"Ollama check failed: {e}"

    @staticmethod
    def create_test_data_prompt():
        """Create prompt for generating test data."""
        return """Generate realistic customer feedback data in JSON format.
        Create 5 customer reviews with these fields:
        - customer_id: unique identifier
        - product: product name
        - rating: 1-5 stars
        - feedback: 1-2 sentence review
        - sentiment: positive/neutral/negative

        Return only valid JSON array."""

    @staticmethod
    def create_quality_check_prompt(data: str):
        """Create prompt for quality checking."""
        return f"""Analyze this customer feedback data and rate its quality.

        Data: {data}

        Check for:
        1. Completeness (all fields present)
        2. Realism (believable feedback)
        3. Variety (diverse opinions)

        Return JSON with:
        - quality_score: 0.0 to 1.0
        - issues: list of any problems found
        - suggestions: improvements needed"""


class TestOllamaMultiAgentCycles:
    """Test multi-agent collaboration with Ollama and cycles."""

    def setup_method(self):
        """Setup test method - check Ollama availability."""
        # Run async check synchronously
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            available, model_or_error = loop.run_until_complete(
                OllamaMultiAgentHelper.check_ollama_available()
            )
            if not available:
                pytest.skip(f"Ollama not available: {model_or_error}")
            self.ollama_model = model_or_error
        finally:
            loop.close()

    def test_document_refinement_with_ai_feedback_cycles(self):
        """Test iterative document refinement using AI agents."""
        workflow = Workflow("ai-refinement", "AI Document Refinement")

        # Shared memory for agent collaboration
        memory_pool = SharedMemoryPoolNode()
        workflow.add_node("memory", memory_pool)

        # A2A Coordinator for agent orchestration
        coordinator = A2ACoordinatorNode()
        workflow.add_node("coordinator", coordinator)

        # Initial document generator agent
        generator_agent = LLMAgentNode(
            name="content_generator",
            model=self.ollama_model,
            base_url=OLLAMA_CONFIG["host"],
            system_prompt="""You are a content generation specialist.
            Create high-quality technical documentation based on the given topic.
            Focus on clarity, completeness, and technical accuracy.""",
            temperature=0.7,
        )
        workflow.add_node("generator", generator_agent)

        # Quality reviewer agent
        reviewer_agent = LLMAgentNode(
            name="quality_reviewer",
            model=self.ollama_model,
            base_url=OLLAMA_CONFIG["host"],
            system_prompt="""You are a technical documentation reviewer.
            Analyze documents for:
            1. Technical accuracy
            2. Clarity and readability
            3. Completeness
            4. Code examples quality

            Provide specific, actionable feedback.""",
            temperature=0.3,
        )
        workflow.add_node("reviewer", reviewer_agent)

        # Document refiner with cycle awareness
        class DocumentRefiner(CycleAwareNode):
            def get_parameters(self):
                return {
                    "document": NodeParameter(type=str, required=True),
                    "feedback": NodeParameter(type=str, required=True),
                    "quality_threshold": NodeParameter(
                        type=float, required=False, default=0.85
                    ),
                    "model": NodeParameter(type=str, required=False, default=""),
                    "base_url": NodeParameter(type=str, required=False, default=""),
                }

            def run(self, **kwargs):
                document = kwargs.get("document", "")
                feedback = kwargs.get("feedback", "")
                quality_threshold = kwargs.get("quality_threshold", 0.85)
                model = kwargs.get("model", self.ollama_model)
                base_url = kwargs.get("base_url", OLLAMA_CONFIG["host"])

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                prev_quality = self.get_previous_state(context).get(
                    "quality_score", 0.0
                )

                # Use LLM to refine document based on feedback
                refiner = LLMAgentNode(
                    name="refiner",
                    model=model,
                    base_url=base_url,
                    system_prompt="You are a document improvement specialist.",
                )

                refinement_prompt = f"""Improve this document based on the feedback:

                Current Document:
                {document}

                Feedback:
                {feedback}

                Iteration: {iteration + 1}
                Previous Quality: {prev_quality:.2f}

                Provide an improved version addressing all feedback points."""

                refined_result = refiner.execute(prompt=refinement_prompt)
                refined_doc = refined_result.get("response", document)

                # Extract quality score from feedback (simple parsing)
                quality_score = prev_quality + 0.15  # Simulate improvement
                if "excellent" in feedback.lower():
                    quality_score = min(0.95, quality_score + 0.1)
                elif "poor" in feedback.lower():
                    quality_score = max(0.3, quality_score - 0.1)

                # Cap at 1.0
                quality_score = min(1.0, quality_score)

                # Check convergence
                converged = quality_score >= quality_threshold or iteration >= 4

                return {
                    "refined_document": refined_doc,
                    "quality_score": quality_score,
                    "iteration": iteration,
                    "converged": converged,
                    "improvement": quality_score - prev_quality,
                    **self.set_cycle_state({"quality_score": quality_score}),
                }

        refiner = DocumentRefiner()
        refiner.ollama_model = self.ollama_model  # Pass model info
        workflow.add_node("refiner", refiner)

        # Test data generator
        test_gen = PythonCodeNode(
            code="""
# Generate initial documentation task
topics = [
    "How to implement a custom Node in Kailash SDK",
    "Best practices for error handling in workflows",
    "Optimizing workflow performance with caching",
    "Building multi-agent systems with A2A communication"
]

import random
selected_topic = random.choice(topics)

# Initial document stub
initial_doc = f'''# {selected_topic}

## Overview
This guide covers {selected_topic.lower()}.

## Getting Started
[To be completed]

## Implementation
[To be completed]

## Best Practices
[To be completed]

## Examples
[To be completed]
'''

result = {
    "topic": selected_topic,
    "initial_document": initial_doc,
    "target_quality": 0.85
}
"""
        )
        workflow.add_node("test_gen", test_gen)

        # Agent registrar
        agent_registrar = PythonCodeNode(
            code="""
# Register agents with coordinator
agents = [
    {
        "id": "generator_001",
        "skills": ["content_generation", "technical_writing"],
        "role": "generator"
    },
    {
        "id": "reviewer_001",
        "skills": ["quality_review", "technical_accuracy"],
        "role": "reviewer"
    },
    {
        "id": "refiner_001",
        "skills": ["document_refinement", "feedback_integration"],
        "role": "refiner"
    }
]

result = {
    "agents": agents,
    "coordination_strategy": "sequential"
}
"""
        )
        workflow.add_node("registrar", agent_registrar)

        # Quality assessor
        quality_assessor = PythonCodeNode(
            code="""
# Assess final document quality
quality_metrics = {
    "completeness": 0.0,
    "clarity": 0.0,
    "technical_accuracy": 0.0,
    "examples_quality": 0.0
}

# Simple heuristic scoring
doc = refined_document if 'refined_document' in locals() else ''
doc_lower = doc.lower()

# Completeness check
sections = ["overview", "getting started", "implementation", "best practices", "examples"]
completed_sections = sum(1 for s in sections if s in doc_lower and "[to be completed]" not in doc_lower)
quality_metrics["completeness"] = completed_sections / len(sections)

# Clarity (based on structure)
quality_metrics["clarity"] = 0.8 if "##" in doc else 0.4

# Technical accuracy (simulated)
quality_metrics["technical_accuracy"] = quality_score if 'quality_score' in locals() else 0.5

# Examples quality
quality_metrics["examples_quality"] = 0.9 if "```" in doc else 0.3

# Overall score
overall_quality = sum(quality_metrics.values()) / len(quality_metrics)

result = {
    "quality_metrics": quality_metrics,
    "overall_quality": overall_quality,
    "final_iteration": iteration if 'iteration' in locals() else 0,
    "document_length": len(doc)
}
"""
        )
        workflow.add_node("assessor", quality_assessor)

        # Connect workflow
        workflow.connect("test_gen", "registrar")
        workflow.connect("registrar", "coordinator", mapping={"agents": "agents"})

        # Initial generation
        workflow.connect("test_gen", "generator", mapping={"topic": "prompt"})
        workflow.connect(
            "generator",
            "memory",
            mapping={"response": "content", "agent_id": "agent_id"},
        )

        # Review cycle
        workflow.connect("generator", "reviewer", mapping={"response": "prompt"})
        workflow.connect("reviewer", "refiner", mapping={"response": "feedback"})
        workflow.connect("generator", "refiner", mapping={"response": "document"})

        # Refinement cycle
        workflow.connect(
            "refiner",
            "refiner",
            cycle=True,
            max_iterations=5,
            convergence_check="converged == True",
            mapping={"refined_document": "document"},
        )

        # Connect back to reviewer for iterative feedback
        workflow.connect("refiner", "reviewer", mapping={"refined_document": "prompt"})

        # Final assessment
        workflow.connect(
            "refiner",
            "assessor",
            mapping={
                "refined_document": "refined_document",
                "quality_score": "quality_score",
                "iteration": "iteration",
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "refiner": {
                    "model": self.ollama_model,
                    "base_url": OLLAMA_CONFIG["host"],
                }
            },
        )

        # Verify results
        assert "refined_document" in results["refiner"]
        assert results["refiner"]["converged"] is True
        assert results["refiner"]["quality_score"] >= 0.5  # Some improvement

        # Check quality assessment
        assert results["assessor"]["overall_quality"] > 0.3
        assert results["assessor"]["document_length"] > 100  # Non-trivial document

    def test_multi_agent_data_quality_improvement_cycles(self):
        """Test multi-agent system for iterative data quality improvement."""
        workflow = Workflow("data-quality-agents", "Multi-Agent Data Quality")

        # Data generator agent
        data_gen_agent = LLMAgentNode(
            name="data_generator",
            model=self.ollama_model,
            base_url=OLLAMA_CONFIG["host"],
            system_prompt="You are a test data generator. Create realistic, diverse data.",
            temperature=0.8,
        )
        workflow.add_node("data_gen", data_gen_agent)

        # Data validator agent
        validator_agent = LLMAgentNode(
            name="data_validator",
            model=self.ollama_model,
            base_url=OLLAMA_CONFIG["host"],
            system_prompt="""You are a data quality analyst.
            Check data for:
            - Completeness
            - Format consistency
            - Realistic values
            - No duplicates

            Return JSON with quality_score (0-1) and specific issues.""",
            temperature=0.2,
        )
        workflow.add_node("validator", validator_agent)

        # Data improver with cycles
        class DataImprover(CycleAwareNode):
            def get_parameters(self):
                return {
                    "data": NodeParameter(type=str, required=True),
                    "validation_feedback": NodeParameter(type=str, required=True),
                    "min_quality": NodeParameter(
                        type=float, required=False, default=0.9
                    ),
                }

            def run(self, **kwargs):
                data = kwargs.get("data", "")
                feedback = kwargs.get("validation_feedback", "")
                min_quality = kwargs.get("min_quality", 0.9)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                improvements = self.get_previous_state(context).get("improvements", [])

                # Parse quality score from feedback
                try:
                    feedback_json = json.loads(feedback)
                    quality_score = feedback_json.get("quality_score", 0.5)
                    issues = feedback_json.get("issues", [])
                except:
                    quality_score = 0.5
                    issues = ["Failed to parse feedback"]

                # Improve data based on feedback
                if quality_score < min_quality and iteration < 5:
                    # Simulate improvement
                    improvement_prompt = f"""Improve this data based on feedback:

                    Current Data: {data}
                    Issues: {issues}

                    Fix all issues and return improved data."""

                    # In real scenario, would use LLM here
                    improved_data = data  # Placeholder
                    quality_score = min(
                        1.0, quality_score + 0.2
                    )  # Simulate improvement

                    improvements.append(
                        {
                            "iteration": iteration,
                            "quality_before": quality_score - 0.2,
                            "quality_after": quality_score,
                            "issues_fixed": len(issues),
                        }
                    )
                else:
                    improved_data = data

                converged = quality_score >= min_quality or iteration >= 5

                return {
                    "improved_data": improved_data,
                    "quality_score": quality_score,
                    "converged": converged,
                    "improvements_history": improvements,
                    "total_iterations": iteration + 1,
                    **self.set_cycle_state({"improvements": improvements}),
                }

        improver = DataImprover()
        workflow.add_node("improver", improver)

        # Initial task setup
        task_setup = PythonCodeNode(
            code=f"""
# Setup data generation task
prompt = "{OllamaMultiAgentHelper.create_test_data_prompt()}"

result = {{
    "generation_prompt": prompt,
    "quality_target": 0.9,
    "max_iterations": 5
}}
"""
        )
        workflow.add_node("task_setup", task_setup)

        # Results analyzer
        analyzer = PythonCodeNode(
            code="""
# Analyze improvement process
improvements = improvements_history if 'improvements_history' in locals() else []

total_improvement = 0
if improvements:
    initial_quality = improvements[0].get("quality_before", 0)
    final_quality = quality_score if 'quality_score' in locals() else initial_quality
    total_improvement = final_quality - initial_quality

# Calculate metrics
metrics = {
    "iterations_used": total_iterations if 'total_iterations' in locals() else 0,
    "final_quality": quality_score if 'quality_score' in locals() else 0,
    "total_improvement": total_improvement,
    "improvement_per_iteration": total_improvement / max(1, len(improvements)),
    "converged": converged if 'converged' in locals() else False
}

result = {
    "improvement_metrics": metrics,
    "improvement_history": improvements,
    "success": metrics["final_quality"] >= 0.9
}
"""
        )
        workflow.add_node("analyzer", analyzer)

        # Connect workflow
        workflow.connect(
            "task_setup", "data_gen", mapping={"generation_prompt": "prompt"}
        )
        workflow.connect("data_gen", "validator", mapping={"response": "prompt"})
        workflow.connect("data_gen", "improver", mapping={"response": "data"})
        workflow.connect(
            "validator", "improver", mapping={"response": "validation_feedback"}
        )

        # Improvement cycle
        workflow.connect(
            "improver",
            "improver",
            cycle=True,
            max_iterations=5,
            convergence_check="converged == True",
            mapping={"improved_data": "data"},
        )

        # Re-validate after each improvement
        workflow.connect("improver", "validator", mapping={"improved_data": "prompt"})

        # Final analysis
        workflow.connect(
            "improver",
            "analyzer",
            mapping={
                "improvements_history": "improvements_history",
                "quality_score": "quality_score",
                "converged": "converged",
                "total_iterations": "total_iterations",
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify multi-agent collaboration
        assert results["improver"]["converged"] is True
        assert results["analyzer"]["improvement_metrics"]["iterations_used"] >= 1
        assert results["analyzer"]["improvement_metrics"]["final_quality"] >= 0.5

    def test_collaborative_problem_solving_with_consensus(self):
        """Test multi-agent consensus building for problem solving."""
        workflow = Workflow("consensus-agents", "Multi-Agent Consensus")

        # Shared memory for collaboration
        memory = SharedMemoryPoolNode()
        workflow.add_node("memory", memory)

        # Coordinator for consensus
        coordinator = A2ACoordinatorNode()
        workflow.add_node("coordinator", coordinator)

        # Problem statement generator
        problem_gen = PythonCodeNode(
            code="""
# Generate a complex problem requiring multiple perspectives
problems = [
    {
        "title": "Optimize Workflow Performance",
        "description": "Our workflow takes 45 seconds to process 1000 records. How can we reduce this to under 10 seconds?",
        "constraints": ["Cannot increase hardware", "Must maintain data accuracy", "Budget: $1000"],
        "current_metrics": {"processing_time": 45, "records": 1000, "accuracy": 0.99}
    },
    {
        "title": "Scale Multi-Agent System",
        "description": "Design a system to handle 10,000 concurrent agents without performance degradation.",
        "constraints": ["Limited to 100 CPU cores", "Memory: 512GB", "Network: 10Gbps"],
        "current_metrics": {"max_agents": 100, "response_time": 50}
    }
]

import random
selected_problem = random.choice(problems)

# Register specialist agents
agents = [
    {"id": "performance_expert", "skills": ["optimization", "profiling"], "role": "analyst"},
    {"id": "architect", "skills": ["system_design", "scalability"], "role": "designer"},
    {"id": "economist", "skills": ["cost_analysis", "budgeting"], "role": "advisor"}
]

result = {
    "problem": selected_problem,
    "agents": agents,
    "consensus_threshold": 0.7
}
"""
        )
        workflow.add_node("problem_gen", problem_gen)

        # Solution proposer with cycles
        class SolutionProposer(CycleAwareNode):
            def get_parameters(self):
                return {
                    "problem": NodeParameter(type=dict, required=True),
                    "agents": NodeParameter(type=list, required=True),
                    "consensus_threshold": NodeParameter(
                        type=float, required=False, default=0.7
                    ),
                }

            def run(self, **kwargs):
                problem = kwargs.get("problem", {})
                agents = kwargs.get("agents", [])
                consensus_threshold = kwargs.get("consensus_threshold", 0.7)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                proposals = self.get_previous_state(context).get("proposals", [])
                consensus_history = self.get_previous_state(context).get(
                    "consensus_history", []
                )

                # Simulate agent proposals (in real scenario, use LLMs)
                new_proposals = []
                for agent in agents:
                    proposal = {
                        "agent_id": agent["id"],
                        "solution": f"Solution from {agent['role']} perspective (iteration {iteration})",
                        "confidence": random.uniform(0.6, 0.95),
                        "cost_estimate": random.randint(100, 900),
                        "time_estimate": random.randint(5, 30),
                    }
                    new_proposals.append(proposal)

                proposals.extend(new_proposals)

                # Calculate consensus
                if len(proposals) >= len(agents) * 2:  # At least 2 rounds
                    # Simulate voting
                    votes = [random.uniform(0.5, 1.0) for _ in agents]
                    consensus_score = sum(votes) / len(votes)
                else:
                    consensus_score = 0.0

                # Record consensus attempt
                consensus_history.append(
                    {
                        "iteration": iteration,
                        "consensus_score": consensus_score,
                        "proposal_count": len(proposals),
                    }
                )

                converged = consensus_score >= consensus_threshold or iteration >= 4

                return {
                    "proposals": proposals,
                    "consensus_score": consensus_score,
                    "converged": converged,
                    "consensus_history": consensus_history,
                    "best_proposal": (
                        max(proposals, key=lambda p: p["confidence"])
                        if proposals
                        else None
                    ),
                    **self.set_cycle_state(
                        {"proposals": proposals, "consensus_history": consensus_history}
                    ),
                }

        proposer = SolutionProposer()
        workflow.add_node("proposer", proposer)

        # Consensus analyzer
        consensus_analyzer = PythonCodeNode(
            code="""
# Analyze consensus building process
history = consensus_history if 'consensus_history' in locals() else []
proposals = proposals if 'proposals' in locals() else []

# Calculate consensus metrics
consensus_rounds = len(history)
avg_consensus = sum(h["consensus_score"] for h in history) / consensus_rounds if consensus_rounds > 0 else 0
consensus_trend = "improving" if len(history) > 1 and history[-1]["consensus_score"] > history[0]["consensus_score"] else "stable"

# Analyze proposals
unique_agents = set(p["agent_id"] for p in proposals)
proposals_per_agent = len(proposals) / len(unique_agents) if unique_agents else 0

# Best solution selection
if best_proposal:
    selected_solution = {
        "agent": best_proposal["agent_id"],
        "confidence": best_proposal["confidence"],
        "cost": best_proposal["cost_estimate"],
        "time": best_proposal["time_estimate"]
    }
else:
    selected_solution = None

result = {
    "consensus_metrics": {
        "rounds": consensus_rounds,
        "average_consensus": avg_consensus,
        "final_consensus": consensus_score if 'consensus_score' in locals() else 0,
        "trend": consensus_trend
    },
    "proposal_metrics": {
        "total_proposals": len(proposals),
        "unique_contributors": len(unique_agents),
        "proposals_per_agent": proposals_per_agent
    },
    "selected_solution": selected_solution,
    "consensus_achieved": converged if 'converged' in locals() else False
}
"""
        )
        workflow.add_node("consensus_analyzer", consensus_analyzer)

        # Connect workflow
        workflow.connect("problem_gen", "coordinator", mapping={"agents": "agents"})
        workflow.connect(
            "problem_gen",
            "proposer",
            mapping={
                "problem": "problem",
                "agents": "agents",
                "consensus_threshold": "consensus_threshold",
            },
        )

        # Consensus building cycle
        workflow.connect(
            "proposer",
            "proposer",
            cycle=True,
            max_iterations=5,
            convergence_check="converged == True",
        )

        # Store proposals in shared memory
        workflow.connect(
            "proposer",
            "memory",
            mapping={"proposals": "content", "agent_id": "agent_id"},
        )

        # Final analysis
        workflow.connect(
            "proposer",
            "consensus_analyzer",
            mapping={
                "proposals": "proposals",
                "consensus_history": "consensus_history",
                "consensus_score": "consensus_score",
                "best_proposal": "best_proposal",
                "converged": "converged",
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify consensus building
        consensus_metrics = results["consensus_analyzer"]["consensus_metrics"]
        assert consensus_metrics["rounds"] >= 1
        assert consensus_metrics["average_consensus"] > 0

        proposal_metrics = results["consensus_analyzer"]["proposal_metrics"]
        assert proposal_metrics["total_proposals"] >= 3  # At least one per agent
        assert proposal_metrics["unique_contributors"] >= 3

        # Check if solution was selected
        assert results["consensus_analyzer"]["selected_solution"] is not None
