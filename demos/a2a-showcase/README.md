# A2A Agent Collaboration Demo

Experience the power of Agent-to-Agent (A2A) collaboration in real-time! This demo showcases how AI agents work together using the Kailash SDK's A2A system.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- OpenAI API key in `.env` file
- Kailash SDK installed

### Setup

1. **Install dependencies:**
   ```bash
   pip install kailash fastapi uvicorn websockets python-dotenv
   ```

2. **Add your OpenAI API key to `.env`:**
   ```bash
   echo "OPENAI_API_KEY=your-api-key-here" > .env
   ```

3. **Run the demo:**
   ```bash
   cd demos/a2a-showcase
   python app.py
   ```

4. **Open your browser:**
   Navigate to http://localhost:8000

## 🎯 What to Try

The demo lets you see how AI agents collaborate on research tasks. Try these example queries:

- **"Analyze the impact of AI on healthcare productivity"** - Watch agents research, analyze data, and synthesize findings
- **"Research quantum computing applications in cryptography"** - See technical expertise emerge through collaboration
- **"Evaluate the environmental benefits of renewable energy"** - Observe how agents share insights and build on each other's work
- **"Investigate the future of autonomous vehicles"** - Experience multi-perspective analysis
- **"Assess blockchain technology for supply chain management"** - Watch consensus building among agents

## 🤖 The Research Team

The demo includes four specialized agents:

1. **Dr. Emma Chen** - Research Specialist
   - Conducts thorough research and literature reviews
   - Synthesizes information from multiple sources

2. **Marcus Johnson** - Data Analyst
   - Analyzes patterns and statistical trends
   - Creates data visualizations and metrics

3. **Prof. Sarah Williams** - Subject Matter Expert
   - Provides deep expertise in AI and technology
   - Offers critical evaluation and validation

4. **Alex Thompson** - Technical Writer
   - Creates clear documentation
   - Organizes and presents findings effectively

## 🔍 What You'll See

### Live Activity Tab
- **Real-time agent thinking** - See what each agent is processing
- **Insight generation** - Watch as agents discover and share key findings
- **Memory operations** - Observe agents reading context and writing insights
- **Collaboration flow** - Experience how agents build on each other's work

### Shared Memory Tab
- **Memory pool statistics** - Track total memories and active segments
- **Insight storage** - Browse all shared insights with importance ratings
- **Tag organization** - See how knowledge is categorized

### Key Insights Tab
- **Curated findings** - The most important discoveries from the collaboration
- **Agent attribution** - Know which agent contributed each insight
- **Temporal flow** - See how insights evolved over time

## 🛠️ Technical Details

### How It Works

1. **Agent Cards**: Each agent has rich capability descriptions that enable intelligent task matching
2. **Shared Memory Pool**: Agents share insights through a decentralized memory system
3. **Attention Filtering**: Agents focus on relevant information based on their expertise
4. **Real OpenAI Integration**: Uses actual GPT-4 for authentic agent responses (not mocked!)

### Key A2A Features Demonstrated

- **Dynamic Team Formation**: Agents are selected based on task requirements
- **Context Sharing**: Later agents build on earlier agents' insights
- **Insight Extraction**: Automatic extraction of key findings from agent responses
- **Performance Tracking**: Each agent's contributions are measured and tracked

## 📚 Understanding the Code

### Simple Demo (`simple_demo.py`)
A programmatic demonstration showing:
- Basic agent setup and registration
- Sequential task execution
- Context propagation between agents
- Results aggregation

### Complex Demo (`complex_demo.py`)
An advanced demonstration featuring:
- 10-agent software development team
- Multi-stage task workflows
- Consensus building mechanisms
- Performance analytics
- Task dependencies and coordination

### Web Application (`app.py`)
The interactive demo showing:
- Real-time WebSocket communication
- Live agent status updates
- Dynamic UI updates
- Actual OpenAI API integration

## 🎨 Customization

### Adding New Agents
Edit `app.py` and add new agent cards in the `create_research_team()` function:

```python
new_agent = A2AAgentCard(
    agent_id="custom_001",
    agent_name="Your Agent Name",
    agent_type="specialist",
    primary_capabilities=[
        Capability(
            name="your_skill",
            domain="Your Domain",
            level=CapabilityLevel.EXPERT,
            description="What this agent does",
            keywords=["relevant", "keywords"]
        )
    ],
    collaboration_style=CollaborationStyle.COOPERATIVE
)
```

### Modifying Prompts
The agent system prompts are generated dynamically based on their capabilities. You can modify the prompt template in the `execute_agent_task()` function.

### Changing Models
By default, the demo uses `gpt-4o-mini` for fast responses. You can change this in `execute_agent_task()`:
```python
model="gpt-4o"  # For higher quality responses
```

## 🐛 Troubleshooting

- **"Connection refused"**: Make sure the server is running on port 8000
- **"Invalid API key"**: Check your `.env` file has a valid OpenAI API key
- **Slow responses**: Consider using `gpt-4o-mini` instead of larger models
- **WebSocket errors**: Refresh the page to reconnect

## 📖 Learn More

- [A2A Implementation Details](../../src/kailash/nodes/ai/a2a.py)
- [Kailash SDK Documentation](../../sdk-users/)
- [Agent Card Specifications](../../sdk-users/2-core-concepts/cheatsheet/023-a2a-agent-coordination.md)

## 🚀 Next Steps

1. **Experiment with different queries** to see how agents adapt
2. **Select specific agents** to see how team composition affects results
3. **Watch the shared memory** to understand knowledge propagation
4. **Review the insights tab** to see the collective intelligence emerge

Enjoy exploring the collaborative power of AI agents!