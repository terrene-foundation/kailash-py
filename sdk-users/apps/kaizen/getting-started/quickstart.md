# Quickstart Tutorial

**Create your first Kaizen agent in 5 minutes**

This tutorial gets you up and running with Kaizen's signature-based AI programming. You'll create a working agent, execute it with the Core SDK runtime, and see results.

## 🎯 What You'll Build

A text analysis agent that takes any text input and returns:
- A concise summary
- Sentiment analysis (positive/negative/neutral)
- Key topics extracted from the text

**Time required:** 5-10 minutes

## 🚀 Step 1: Basic Setup

Create a new Python file called `quickstart.py`:

```python
import kaizen
from kailash.runtime.local import LocalRuntime

print("🚀 Kaizen Quickstart Tutorial")
print("Creating your first signature-based AI agent...\n")
```

## 🧠 Step 2: Initialize Framework

Add framework initialization with signature programming enabled:

```python
# Initialize Kaizen framework
framework = kaizen.Kaizen(signature_programming_enabled=True)

print("✅ Framework initialized with signature programming")
```

**What this does:**
- Creates a Kaizen framework instance
- Enables signature-based programming features
- Sets up lazy loading for optimal performance

## 🤖 Step 3: Create Your First Agent

Add a signature-based agent that processes text:

```python
# Create signature-based agent
agent = framework.create_agent(
    agent_id="text_analyzer",
    signature="text -> summary, sentiment, key_topics"
)

print("✅ Created text analyzer agent with signature")
print("   Input: text")
print("   Outputs: summary, sentiment, key_topics\n")
```

**Understanding the signature:**
- `"text -> summary, sentiment, key_topics"` defines inputs and outputs
- Framework automatically handles the AI logic
- No need to write prompts or manage model interactions

## ⚡ Step 4: Execute with Core SDK

Add execution using Kailash Core SDK runtime:

```python
# Initialize Core SDK runtime
runtime = LocalRuntime()

# Convert agent to workflow and execute
workflow = agent.to_workflow()
built_workflow = workflow.build()

print("✅ Agent converted to Core SDK workflow")
print("⚡ Executing with LocalRuntime...\n")

# Execute with sample text
sample_text = """
Artificial intelligence is transforming how businesses operate.
Companies are using AI for customer service, data analysis, and
automation. This technology offers incredible opportunities but
also presents challenges in ethics and employment.
"""

# Execute the workflow
results, run_id = runtime.execute(
    built_workflow,
    parameters={"text": sample_text.strip()}
)

print(f"✅ Execution completed (Run ID: {run_id})")
```

**Key Patterns:**
- Always use `runtime.execute(workflow.build())`
- Pass inputs as parameters dictionary
- Runtime returns results and execution ID

## 📊 Step 5: Access Results

Add result processing and display:

```python
# Display results
print("\n📊 Analysis Results:")
print("=" * 50)

if 'summary' in results:
    print(f"📝 Summary:")
    print(f"   {results['summary']}\n")

if 'sentiment' in results:
    print(f"😊 Sentiment: {results['sentiment']}\n")

if 'key_topics' in results:
    print(f"🔑 Key Topics:")
    topics = results['key_topics']
    if isinstance(topics, list):
        for topic in topics:
            print(f"   • {topic}")
    else:
        print(f"   {topics}")

print("\n🎉 Quickstart completed successfully!")
```

## 🏃‍♂️ Complete Code

Here's your complete `quickstart.py` file:

```python
import kaizen
from kailash.runtime.local import LocalRuntime

print("🚀 Kaizen Quickstart Tutorial")
print("Creating your first signature-based AI agent...\n")

# Step 1: Initialize Kaizen framework
framework = kaizen.Kaizen(signature_programming_enabled=True)
print("✅ Framework initialized with signature programming")

# Step 2: Create signature-based agent
agent = framework.create_agent(
    agent_id="text_analyzer",
    signature="text -> summary, sentiment, key_topics"
)
print("✅ Created text analyzer agent with signature")
print("   Input: text")
print("   Outputs: summary, sentiment, key_topics\n")

# Step 3: Execute with Core SDK
runtime = LocalRuntime()
workflow = agent.to_workflow()
built_workflow = workflow.build()

print("✅ Agent converted to Core SDK workflow")
print("⚡ Executing with LocalRuntime...\n")

# Sample text for analysis
sample_text = """
Artificial intelligence is transforming how businesses operate.
Companies are using AI for customer service, data analysis, and
automation. This technology offers incredible opportunities but
also presents challenges in ethics and employment.
"""

# Execute the workflow
results, run_id = runtime.execute(
    built_workflow,
    parameters={"text": sample_text.strip()}
)

print(f"✅ Execution completed (Run ID: {run_id})")

# Display results
print("\n📊 Analysis Results:")
print("=" * 50)

if 'summary' in results:
    print(f"📝 Summary:")
    print(f"   {results['summary']}\n")

if 'sentiment' in results:
    print(f"😊 Sentiment: {results['sentiment']}\n")

if 'key_topics' in results:
    print(f"🔑 Key Topics:")
    topics = results['key_topics']
    if isinstance(topics, list):
        for topic in topics:
            print(f"   • {topic}")
    else:
        print(f"   {topics}")

print("\n🎉 Quickstart completed successfully!")
```

## 🏃‍♂️ Run Your Agent

Execute your first Kaizen agent:

```bash
python quickstart.py
```

**Expected output:**
```
🚀 Kaizen Quickstart Tutorial
Creating your first signature-based AI agent...

✅ Framework initialized with signature programming
✅ Created text analyzer agent with signature
   Input: text
   Outputs: summary, sentiment, key_topics

✅ Agent converted to Core SDK workflow
⚡ Executing with LocalRuntime...

✅ Execution completed (Run ID: run_abc123)

📊 Analysis Results:
==================================================
📝 Summary:
   AI is revolutionizing business operations through automation,
   customer service, and analytics, creating opportunities while
   raising ethical and employment concerns.

😊 Sentiment: neutral

🔑 Key Topics:
   • artificial intelligence
   • business transformation
   • automation
   • ethics
   • employment

🎉 Quickstart completed successfully!
```

## 🔧 Try Different Inputs

Experiment with different text inputs:

```python
# Try different examples
examples = [
    "I love this new restaurant! The food is amazing and the service is excellent.",
    "The quarterly financial report shows significant losses across all departments.",
    "Climate change requires immediate action from governments and businesses worldwide."
]

for i, text in enumerate(examples, 1):
    print(f"\n--- Example {i} ---")
    results, _ = runtime.execute(
        built_workflow,
        parameters={"text": text}
    )
    print(f"Text: {text[:50]}...")
    print(f"Sentiment: {results.get('sentiment', 'N/A')}")
```

## 🎯 Understanding What Happened

### Signature-Based Programming
- **Declarative**: You defined WHAT you wanted (`"text -> summary, sentiment, key_topics"`)
- **Automatic**: Framework figured out HOW to implement it
- **Optimized**: Framework handles prompt engineering, error handling, and optimization

### Core SDK Integration
- **Workflow Conversion**: Agent becomes a Core SDK workflow node
- **Runtime Execution**: Uses LocalRuntime for actual execution
- **Result Handling**: Structured outputs matching your signature

### Key Benefits
- **No Prompt Engineering**: Framework handles AI interactions
- **Structured Outputs**: Results match your signature specification
- **Enterprise Ready**: Built-in error handling and optimization
- **Ecosystem Integration**: Works seamlessly with Kailash Core SDK

## 🚨 Common Issues

**1. Module Import Errors**
```python
# Error: No module named 'kaizen'
# Solution: Check installation
pip install kailash[kaizen]
```

**2. API Key Issues**
```python
# Error: Authentication failed
# Solution: Set API key
import os
os.environ["OPENAI_API_KEY"] = "your-key-here"
```

**3. Empty Results**
```python
# Issue: Results contain empty values
# Solution: Check agent configuration
agent = framework.create_agent(
    agent_id="text_analyzer",
    config={"model": "gpt-4"},  # Specify model explicitly
    signature="text -> summary, sentiment, key_topics"
)
```

## 🏗️ Next Steps

### Immediate Next Steps
1. **[First Agent Deep Dive](first-agent.md)** - Learn detailed agent configuration
2. **Try Different Signatures** - Experiment with different input/output patterns
3. **Add Error Handling** - Make your agents more robust

### Explore More Features
1. **[Enterprise Features](../guides/enterprise-features.md)** - Memory, audit trails, compliance
2. **[Multi-Agent Workflows](../guides/multi-agent-workflows.md)** - Coordinate multiple agents
3. **[MCP Integration](../guides/mcp-integration.md)** - Connect external tools

### Example Extensions

**Add Configuration:**
```python
# More sophisticated agent
agent = framework.create_agent(
    agent_id="advanced_analyzer",
    config={
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 500
    },
    signature="text -> summary, sentiment, key_topics, readability_score"
)
```

**Add Memory:**
```python
# Enterprise features
enterprise_framework = kaizen.Kaizen(
    memory_enabled=True,
    audit_trail_enabled=True
)

memory = enterprise_framework.create_memory_system(tier="standard")
agent = enterprise_framework.create_agent(
    "memory_analyzer",
    config={"memory_system": memory},
    signature="text -> summary, sentiment, similar_texts"
)
```

**Multiple Agents:**
```python
# Create specialized agents
summarizer = framework.create_agent("summarizer", signature="text -> summary")
sentiment_analyzer = framework.create_agent("sentiment", signature="text -> sentiment")
topic_extractor = framework.create_agent("topics", signature="text -> key_topics")

# Use them in sequence or parallel
```

## 📚 What You Learned

✅ **Framework Initialization** - How to set up Kaizen with signature programming
✅ **Signature Syntax** - Declarative input/output definitions
✅ **Agent Creation** - Building AI agents without prompt engineering
✅ **Core SDK Integration** - Executing agents with LocalRuntime
✅ **Result Handling** - Accessing structured outputs
✅ **Essential Pattern** - Always use `runtime.execute(workflow.build())`

## 🎉 Congratulations!

You've successfully created and executed your first Kaizen agent using signature-based programming! You now understand the core concepts of declarative AI development.

**Ready for more?** Continue to the **[First Agent Deep Dive](first-agent.md)** for detailed configuration options and advanced patterns.