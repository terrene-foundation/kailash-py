# Kaizen User Scenarios

Real-world demonstration scripts showing how different types of users will use Kaizen in practice.

## 📋 Overview

These scenarios demonstrate Kaizen's developer experience across different user profiles and complexity levels, from beginners to advanced ML engineers. All scenarios use **Ollama** (free, local inference) to ensure you can run them immediately.

## 🎯 Scenarios

### 1. Beginner - Simple Q&A Bot
**File**: `01-beginner-simple-qa-bot.py`

**User Profile**: Just learning AI agents, no prior experience

**What it demonstrates**:
- ✅ Minimal code (< 20 lines of logic)
- ✅ Zero-config complexity
- ✅ Immediate results
- ✅ Basic agent creation and usage

**Key Learning**: Create your first Kaizen agent and ask questions

```bash
python user-scenarios/01-beginner-simple-qa-bot.py
```

---

### 2. Data Analyst - CSV Data Analysis
**File**: `02-data-analyst-csv-analysis.py`

**User Profile**: Data analyst working with datasets

**What it demonstrates**:
- ✅ Data integration with pandas
- ✅ Multiple analysis tasks
- ✅ Structured output
- ✅ AI-powered insights from data

**Key Learning**: Combine data processing with AI analysis

```bash
python user-scenarios/02-data-analyst-csv-analysis.py
```

---

### 3. Product Manager - Customer Feedback Analysis
**File**: `03-product-manager-feedback-analysis.py`

**User Profile**: Product manager collecting user feedback

**What it demonstrates**:
- ✅ Memory persistence across sessions
- ✅ Batch processing of feedback
- ✅ Sentiment analysis
- ✅ Context-aware insights

**Key Learning**: Use `MemoryAgent` with `session_id` for persistent context

```bash
python user-scenarios/03-product-manager-feedback-analysis.py
```

---

### 4. DevOps - Log Analysis with Memory
**File**: `04-devops-log-analysis-memory.py`

**User Profile**: DevOps engineer monitoring application logs

**What it demonstrates**:
- ✅ Log parsing and pattern detection
- ✅ Memory continuity across interactions
- ✅ Multi-phase analysis workflow
- ✅ Actionable insights generation

**Key Learning**: Track patterns and context across analysis sessions

```bash
python user-scenarios/04-devops-log-analysis-memory.py
```

---

### 5. Content Creator - Multi-Modal Content
**File**: `05-content-creator-multimodal.py`

**User Profile**: Content creator working with images and videos

**What it demonstrates**:
- ✅ Vision agent for image analysis
- ✅ Multi-modal workflow (vision + text)
- ✅ Content generation pipeline
- ✅ SEO and social media optimization

**Key Learning**: Combine `VisionAgent` and `SimpleQAAgent` for multi-modal content

**Note**: Requires actual image files for full vision analysis. Demo includes simulation.

```bash
python user-scenarios/05-content-creator-multimodal.py
```

---

### 6. ML Engineer - Multi-Agent Research System
**File**: `06-ml-engineer-multiagent-research.py`

**User Profile**: ML engineer researching new techniques

**What it demonstrates**:
- ✅ Multiple specialized agents coordination
- ✅ Research → Analysis → Review workflow
- ✅ Chain-of-thought reasoning
- ✅ Systematic research output

**Key Learning**: Build multi-agent systems with coordinated workflows

```bash
python user-scenarios/06-ml-engineer-multiagent-research.py
```

---

## 🚀 Quick Start

### Prerequisites

1. **Install Kaizen**:
   ```bash
   pip install kailash[kaizen]
   # or
   pip install kailash-kaizen
   ```

2. **Install Ollama** (free, local LLM):
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh

   # Or download from https://ollama.com/download
   ```

3. **Pull required models**:
   ```bash
   ollama pull llama2      # Text generation
   ollama pull bakllava    # Vision (for scenario 5)
   ```

4. **Set up environment** (optional, for OpenAI/Anthropic):
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

### Running Scenarios

**Run individual scenario**:
```bash
python user-scenarios/01-beginner-simple-qa-bot.py
```

**Run all scenarios** (requires Ollama running):
```bash
for script in user-scenarios/*.py; do
    echo "Running $script..."
    python "$script"
    echo "---"
done
```

## 📊 Complexity Matrix

| Scenario | Complexity | Agents | Memory | Multi-Modal | Lines of Code |
|----------|-----------|--------|--------|-------------|---------------|
| 1. Beginner Q&A | ⭐ | 1 | No | No | 70 |
| 2. Data Analyst | ⭐⭐ | 1 | No | No | 150 |
| 3. Product Manager | ⭐⭐⭐ | 1 | Yes | No | 180 |
| 4. DevOps Log Analysis | ⭐⭐⭐ | 1 | Yes | No | 190 |
| 5. Content Creator | ⭐⭐⭐⭐ | 2 | No | Yes | 210 |
| 6. ML Engineer | ⭐⭐⭐⭐⭐ | 3 | No | No | 250 |

## 🎓 Learning Path

**Recommended order**:

1. **Start**: Scenario 1 (Beginner) - Learn basic agent creation
2. **Data Integration**: Scenario 2 (Data Analyst) - Combine data + AI
3. **Memory**: Scenario 3 or 4 - Understand session persistence
4. **Multi-Modal**: Scenario 5 - Vision + text workflows
5. **Advanced**: Scenario 6 - Multi-agent coordination

## 💡 Key Concepts Demonstrated

### Agent Types Used
- **SimpleQAAgent**: Basic question answering
- **MemoryAgent**: Session-based memory persistence
- **VisionAgent**: Image analysis (multi-modal)
- **ChainOfThoughtAgent**: Step-by-step reasoning
- **RAGResearchAgent**: Research with retrieval

### Patterns Demonstrated
- ✅ Single-agent patterns
- ✅ Memory persistence with `session_id`
- ✅ Multi-modal processing (vision + text)
- ✅ Multi-agent coordination
- ✅ Progressive complexity
- ✅ Error handling
- ✅ Production-ready code structure

## 🔧 Configuration

All scenarios use Ollama by default for zero-cost local inference. To switch to OpenAI or Anthropic:

```python
# Change this:
config = SimpleQAConfig(
    llm_provider="ollama",
    model="llama2"
)

# To this:
config = SimpleQAConfig(
    llm_provider="openai",
    model="gpt-4"
)
```

**Requirements for cloud providers**:
- Set API keys in `.env`
- Load with `load_dotenv()`

## 🐛 Troubleshooting

### Ollama Connection Error
```
Error: Could not connect to Ollama
```

**Solution**: Ensure Ollama is running
```bash
ollama serve  # Start Ollama server
```

### Model Not Found
```
Error: Model 'llama2' not found
```

**Solution**: Pull the model first
```bash
ollama pull llama2
```

### Import Error
```
ModuleNotFoundError: No module named 'kaizen'
```

**Solution**: Install Kaizen
```bash
pip install kailash[kaizen]
```

### Vision Agent Error (Scenario 5)
```
Error: Image file not found
```

**Solution**: Scenario 5 simulates vision analysis. For real vision:
1. Replace placeholder paths with actual image files
2. Use `vision_agent.analyze(image="/path/to/real/image.jpg", question="...")`

## 📚 Related Documentation

- **[Kaizen Documentation](../docs/README.md)** - Complete framework docs
- **[Examples](../examples/)** - 35+ production-ready examples
- **[API Reference](../docs/reference/api-reference.md)** - Complete API
- **[Troubleshooting](../docs/reference/troubleshooting.md)** - Common issues

## 🎯 Next Steps

After completing these scenarios:

1. **Explore Examples**: Check `examples/` for 35+ production patterns
2. **Read Guides**: See `docs/guides/` for in-depth tutorials
3. **Build Your Agent**: Use `BaseAgent` to create custom agents
4. **Production Deploy**: See `docs/deployment/` for deployment guides

## ✅ Validation Checklist

- [ ] Ollama installed and running
- [ ] Models pulled (llama2, bakllava)
- [ ] Environment set up (.env if using cloud providers)
- [ ] All dependencies installed (`pip install kailash[kaizen]`)
- [ ] Can run scenario 1 successfully
- [ ] Can run scenarios 2-6 successfully

## 🤝 Feedback

If you encounter issues or have suggestions:

1. Check **[Troubleshooting Guide](../docs/reference/troubleshooting.md)**
2. Review **[Common Pitfalls](../docs/reference/multi-modal-api-reference.md#common-pitfalls)**
3. See working **[Examples](../examples/)**

---

**Last Updated**: 2025-10-05
**Kaizen Version**: v0.1.0
**License**: Same as Kailash SDK
