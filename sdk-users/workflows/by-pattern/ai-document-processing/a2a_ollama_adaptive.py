"""
Adaptive A2A Communication with Ollama

This example automatically detects available Ollama models and adapts
the multi-agent system to use what's installed.
"""

import subprocess

from kailash import Workflow
from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime


def get_available_ollama_models() -> list[dict[str, str]]:
    """Get list of available Ollama models with their full names."""
    try:
        result = subprocess.execute(
            ["ollama", "list"], capture_output=True, text=True, check=True
        )

        # Parse the output
        lines = result.stdout.strip().split("\n")
        models = []

        for line in lines[1:]:  # Skip header
            if line.strip():
                # Model name is the first column
                full_name = line.split()[0]
                # Extract base name and tag
                if ":" in full_name:
                    base_name = full_name.split(":")[0]
                    tag = full_name.split(":")[1]
                else:
                    base_name = full_name
                    tag = "latest"

                models.append(
                    {"full_name": full_name, "base_name": base_name, "tag": tag}
                )

        return models
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  Ollama not found or not running. Please install and start Ollama.")
        return []


def create_adaptive_workflow(available_models: list[dict[str, str]]) -> Workflow:
    """Create a workflow adapted to available models."""
    workflow = Workflow(
        workflow_id="adaptive_a2a",
        name="Adaptive A2A System",
        description="Multi-agent system that adapts to available Ollama models",
    )

    # Always create shared memory
    workflow.add_node("shared_memory", SharedMemoryPoolNode())

    # Always create coordinator
    workflow.add_node("coordinator", A2ACoordinatorNode())

    # Model preferences for different roles
    role_preferences = {
        "researcher": [
            "llama3.2",
            "llama3.1",
            "llama3",
            "llama2",
            "mistral",
            "mixtral",
            "qwen2.5",
            "qwen2",
            "gemma2",
            "gemma",
        ],
        "analyst": [
            "mistral",
            "mixtral",
            "llama3.2",
            "llama3.1",
            "llama3",
            "llama2",
            "codellama",
            "deepseek-coder-v2",
            "deepseek-coder",
        ],
        "synthesizer": [
            "phi",
            "phi3",
            "llama3.2",
            "llama3.1",
            "llama3",
            "llama2",
            "mistral",
            "gemma2",
            "tinyllama",
            "qwen2.5",
        ],
    }

    # Create a lookup of available models by base name
    model_lookup = {}
    for model in available_models:
        base_name = model["base_name"]
        if base_name not in model_lookup:
            model_lookup[base_name] = model["full_name"]

    agents_created = []

    # Try to create agents based on available models
    for role, preferences in role_preferences.items():
        model_found = None
        model_full_name = None

        for preferred_model in preferences:
            if preferred_model in model_lookup:
                model_found = preferred_model
                model_full_name = model_lookup[preferred_model]
                break

        if model_found:
            agent_id = f"{role}_agent"
            workflow.add_node(
                agent_id,
                A2AAgentNode(),
                config={
                    "agent_id": f"{role}_{model_found}",
                    "agent_role": role,
                    "provider": "ollama",
                    "model": model_full_name,  # Use full name with tag
                    "system_prompt": get_role_prompt(role, model_found),
                    "attention_filter": get_role_attention_filter(role),
                },
            )
            workflow.connect(agent_id, "shared_memory")
            workflow.connect(agent_id, "coordinator")
            agents_created.append((role, model_full_name, model_found))
            print(f"✅ Created {role} agent using {model_found} ({model_full_name})")
        else:
            print(f"⚠️  No suitable model found for {role} role")

    return workflow, agents_created


def get_role_prompt(role: str, model: str) -> str:
    """Get appropriate prompt for each role."""
    prompts = {
        "researcher": f"""You are a research specialist using {model}. Your responsibilities:
1. Gather comprehensive information on topics
2. Identify key facts, statistics, and trends
3. Find relevant examples and case studies
4. Share discoveries with importance ratings:
   - CRITICAL (0.9-1.0): Breakthrough findings
   - HIGH (0.7-0.8): Important insights
   - MEDIUM (0.5-0.6): Relevant information
   - LOW (0.3-0.4): Supporting details""",
        "analyst": f"""You are an analytical expert using {model}. Focus on:
1. Analyzing patterns in research findings
2. Identifying correlations and causations
3. Evaluating data quality and reliability
4. Providing quantitative insights
5. Rating findings by analytical value""",
        "synthesizer": f"""You are a synthesis specialist using {model}. Your tasks:
1. Integrate findings from all agents
2. Identify consensus and conflicts
3. Create coherent summaries
4. Formulate actionable conclusions
5. Prioritize recommendations""",
    }
    return prompts.get(role, f"You are a {role} using {model}.")


def get_role_attention_filter(role: str) -> dict:
    """Get attention filter configuration for each role."""
    filters = {
        "researcher": {
            "tags": ["research", "data", "findings", "evidence"],
            "importance_threshold": 0.5,
            "window_size": 20,
        },
        "analyst": {
            "tags": ["analysis", "pattern", "correlation", "research"],
            "importance_threshold": 0.6,
            "window_size": 15,
        },
        "synthesizer": {
            "tags": ["findings", "analysis", "conclusion", "recommendation"],
            "importance_threshold": 0.4,
            "window_size": 30,
        },
    }
    return filters.get(role, {"importance_threshold": 0.5, "window_size": 10})


def demonstrate_adaptive_system():
    """Run demonstration with available models."""
    print("=" * 60)
    print("ADAPTIVE A2A SYSTEM WITH OLLAMA")
    print("=" * 60)

    # Check available models
    print("\n🔍 Checking available Ollama models...")
    models = get_available_ollama_models()

    if not models:
        print("\n❌ No Ollama models found!")
        print("\nTo install models, run:")
        print("  ollama pull llama3.2    # Fast, good general model")
        print("  ollama pull mistral     # Good for analysis")
        print("  ollama pull phi         # Small, efficient model")
        print("  ollama pull gemma2      # Google's model")
        print("  ollama pull qwen2.5     # Alibaba's model")
        return

    print(
        f"\n📦 Found {len(models)} models: {', '.join([m['full_name'] for m in models])}"
    )

    # Create adaptive workflow
    print("\n🔧 Creating adaptive workflow...")
    workflow, agents = create_adaptive_workflow(models)

    if not agents:
        print("\n❌ Could not create any agents with available models")
        return

    print(f"\n✅ Created {len(agents)} agents")

    # Initialize system
    runtime = LocalRuntime()
    memory_pool = workflow._node_instances["shared_memory"]
    coordinator = workflow._node_instances["coordinator"]

    # Register agents
    print("\n📝 Registering agents with coordinator...")
    for role, model_full_name, model_base_name in agents:
        agent_id = f"{role}_{model_base_name}"
        coordinator.execute(
            action="register",
            agent_info={
                "id": agent_id,
                "role": role,
                "model": model_full_name,
                "skills": [role, "ollama", model_base_name],
            },
        )

    # Run collaborative task
    topic = "The future of human-AI collaboration in creative fields"
    print(f"\n{'='*60}")
    print("COLLABORATIVE ANALYSIS")
    print(f"Topic: {topic}")
    print(f"{'='*60}")

    # Execute each available agent
    for i, (role, model_full_name, model_base_name) in enumerate(agents, 1):
        print(f"\n{i}. {role.capitalize()} Agent ({model_full_name})")
        print("-" * 40)

        agent_node = f"{role}_agent"

        # Customize message based on role
        messages = {
            "researcher": f"Research this topic and identify key trends: {topic}",
            "analyst": f"Analyze the implications and patterns in: {topic}",
            "synthesizer": f"Synthesize insights about: {topic}",
        }

        try:
            result, _ = runtime.execute(
                workflow,
                parameters={
                    agent_node: {
                        "messages": [
                            {
                                "role": "user",
                                "content": messages.get(
                                    role, f"Provide insights on: {topic}"
                                ),
                            }
                        ],
                        "memory_pool": memory_pool,
                        "provider": "ollama",
                        "model": model_full_name,
                    }
                },
            )

            if result.get(agent_node, {}).get("success"):
                response = result[agent_node]["response"]["content"]
                # Show first 400 chars
                print(response[:400] + "..." if len(response) > 400 else response)

                # Show memory activity
                insights = result[agent_node]["a2a_metadata"]["insights_generated"]
                shared = result[agent_node]["a2a_metadata"]["shared_context_used"]
                print(
                    f"\n📊 Generated {insights} insights, used {shared} shared memories"
                )
            else:
                error = result.get(agent_node, {}).get("error", "Unknown error")
                print(f"❌ Agent failed: {error}")

        except Exception as e:
            print(f"❌ Error: {e}")

    # Analyze collective memory
    print(f"\n\n{'='*60}")
    print("COLLECTIVE INTELLIGENCE ANALYSIS")
    print("=" * 60)

    # Get all memories
    all_memories = memory_pool.execute(
        action="read",
        agent_id="observer",
        attention_filter={"importance_threshold": 0.0, "window_size": 100},
    )

    if all_memories["success"] and all_memories["memories"]:
        print(f"\n📚 Total shared memories: {all_memories['total_available']}")

        # Group by importance
        importance_buckets = {"high": 0, "medium": 0, "low": 0}
        for mem in all_memories["memories"]:
            imp = mem["importance"]
            if imp >= 0.7:
                importance_buckets["high"] += 1
            elif imp >= 0.5:
                importance_buckets["medium"] += 1
            else:
                importance_buckets["low"] += 1

        print("\n📊 Memory importance distribution:")
        for level, count in importance_buckets.items():
            print(f"  {level.capitalize()}: {count} memories")

        # Show top insights
        high_importance = [
            m for m in all_memories["memories"] if m["importance"] >= 0.7
        ]
        if high_importance:
            print("\n💡 Top insights (importance >= 0.7):")
            for mem in high_importance[:3]:
                print(f"\n- [{mem['agent_id']}]: {mem['content'][:150]}...")

    # Build consensus if we have multiple agents
    if len(agents) > 1:
        print(f"\n\n{'='*60}")
        print("CONSENSUS BUILDING")
        print("=" * 60)

        proposal = "AI will fundamentally transform creative fields by augmenting human creativity"
        print(f"\nProposal: {proposal}")

        # Start consensus
        coordinator.execute(
            action="consensus",
            consensus_proposal={
                "session_id": "creative_ai_consensus",
                "proposal": proposal,
            },
        )

        # Simulate votes
        print("\nAgent votes:")
        for role, model_full_name, model_base_name in agents:
            agent_id = f"{role}_{model_base_name}"
            vote = True  # In real scenario, this would be based on agent analysis
            coordinator.execute(
                action="consensus",
                consensus_proposal={"session_id": "creative_ai_consensus"},
                agent_id=agent_id,
                vote=vote,
            )
            print(f"  {agent_id}: Yes")

        print(f"\n✅ Consensus reached among {len(agents)} agents")


def suggest_model_installation():
    """Suggest models to install based on what's missing."""
    print("\n" + "=" * 60)
    print("RECOMMENDED OLLAMA MODELS FOR A2A")
    print("=" * 60)

    recommendations = [
        ("llama3.2", "3B", "Fast, versatile, good for general tasks"),
        ("mistral", "7B", "Excellent for analysis and reasoning"),
        ("phi", "2.7B", "Microsoft's efficient model, good for synthesis"),
        ("gemma2", "2B-9B", "Google's model, good balance"),
        ("qwen2.5", "0.5B-7B", "Multilingual, good for research"),
        ("tinyllama", "1.1B", "Very fast, good for simple tasks"),
        ("codellama", "7B", "Specialized for code analysis"),
    ]

    print("\nRecommended models (in order of preference):")
    for model, size, description in recommendations:
        print(f"\n📦 {model} ({size})")
        print(f"   {description}")
        print(f"   Install: ollama pull {model}")

    print("\n💡 Tip: Start with llama3.2, mistral, and phi for a good balance")
    print("   These three models cover research, analysis, and synthesis well")


def main():
    """Run the adaptive A2A demonstration."""
    # First, show what's possible
    demonstrate_adaptive_system()

    # Then suggest improvements
    suggest_model_installation()

    print("\n\n" + "=" * 60)
    print("ADAPTIVE A2A COMPLETE")
    print("=" * 60)
    print("\n✨ The system automatically adapted to your available models!")
    print("📈 Install more models to unlock additional capabilities")
    print("🔄 The system will use the best available model for each role")


if __name__ == "__main__":
    main()
