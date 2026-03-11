# Content Creator (PEVAgent)

## Overview

Automated content creation agent that generates high-quality content through iterative refinement using the PEVAgent (Plan-Execute-Verify) pattern. The agent creates an initial draft, verifies its quality, then refines the content based on feedback until quality thresholds are met.

**Pattern**: Plan → Execute → Verify → Refine (iterative loop, max 5 cycles)

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen
```

## Usage

```bash
python content_creator.py "content task" [length=1000] [tone=professional]
```

### Basic Examples

```bash
# Simple blog post
python content_creator.py "blog post on AI ethics"

# Technical documentation
python content_creator.py "technical documentation for REST API" length=2000 tone=technical

# Marketing copy
python content_creator.py "product launch announcement" tone=enthusiastic length=500
```

### Context Parameters

- `length`: Target word count (default: 1000)
- `tone`: Writing tone (professional, technical, casual, enthusiastic, etc.)
- `audience`: Target audience (developers, executives, general, etc.)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              CONTENT CREATOR                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────┐        ┌───────────────────┐   │
│  │ Control Protocol │        │  Performance      │   │
│  │ (Progress)       │        │  Metrics Hook     │   │
│  └──────────────────┘        └───────────────────┘   │
│          │                            │               │
│          │                            │               │
│          ▼                            ▼               │
│  ┌──────────────────────────────────────────────┐   │
│  │         PEVAgent (Iterative Loop)            │   │
│  │                                              │   │
│  │  Iteration 1:                                │   │
│  │    Plan → Execute → Verify → Refine          │   │
│  │                                              │   │
│  │  Iteration 2:                                │   │
│  │    Plan → Execute → Verify → Refine          │   │
│  │                                              │   │
│  │  Iteration 3:                                │   │
│  │    Plan → Execute → Verify → ✅ Complete     │   │
│  │                                              │   │
│  └──────────────────────────────────────────────┘   │
│          │                                           │
│          ▼                                           │
│  ┌──────────────────────────────────────────────┐   │
│  │         Export (Markdown, HTML, TXT)         │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Iterative Refinement Flow

### Iteration 1: Initial Draft

```
📝 INITIAL DRAFT
============================================================
# Artificial Intelligence Ethics: A Modern Imperative

Introduction
Artificial intelligence (AI) is transforming our world...
[... draft continues ...]
============================================================

Iteration 1:
  Verification Score: 0.6
  Status: needs_improvement
  Issues Found: 3
    - Grammar: Missing comma in line 5
    - Style: Sentence too long in paragraph 2
    - Coherence: Weak transition between sections
  Improvements Made: 3
```

### Iteration 2: Refinement

```
Iteration 2:
  Verification Score: 0.75
  Status: improving
  Issues Found: 2
    - Style: More concrete examples needed
    - Coherence: Strengthen conclusion
  Improvements Made: 2
```

### Iteration 3: Final Polish

```
Iteration 3:
  Verification Score: 0.92
  Status: completed
  ✅ No issues found
```

### Final Verification

```
✅ FINAL VERIFICATION
============================================================
Passed: True
Final Score: 0.92
✅ All quality checks passed
============================================================
```

## Expected Output

```
============================================================
🤖 CONTENT CREATOR INITIALIZED
============================================================
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0
🔄 Max Iterations: 5
✅ Verification: medium
🛡️  Error Recovery: True
📊 Performance Metrics: True
============================================================

✍️  Starting content creation: blog post on AI ethics

⏱️  Performance: Content creation started

============================================================
📋 CONTENT PLAN
============================================================
Objective: Create engaging blog post on AI ethics
Target Length: 1000
Tone: professional
============================================================

============================================================
📝 INITIAL DRAFT
============================================================
# The Ethics of Artificial Intelligence

## Introduction
As artificial intelligence becomes increasingly integrated...
[... draft continues ...]
============================================================

============================================================
🔄 ITERATIVE REFINEMENT (3 iterations)
============================================================

Iteration 1:
  Verification Score: 0.6
  Status: needs_improvement
  Issues Found: 3
    - Grammar: Missing comma in line 5
    - Style: Sentence too long in paragraph 2
    - Coherence: Weak transition between sections
  Improvements Made: 3

Iteration 2:
  Verification Score: 0.75
  Status: improving
  Issues Found: 2
    - Style: More concrete examples needed
    - Coherence: Strengthen conclusion
  Improvements Made: 2

Iteration 3:
  Verification Score: 0.92
  Status: completed
  ✅ No issues found

============================================================

============================================================
✅ FINAL VERIFICATION
============================================================
Passed: True
Final Score: 0.92
✅ All quality checks passed
============================================================

============================================================
📄 FINAL CONTENT
============================================================
# The Ethics of Artificial Intelligence

## Introduction
As artificial intelligence becomes increasingly integrated into our
daily lives, the ethical implications of these systems demand our
immediate attention. From autonomous vehicles to healthcare
diagnostics, AI systems make decisions that directly impact human
lives.

[... full polished content ...]

## Conclusion
The ethical deployment of AI requires a collaborative effort...

============================================================

⏱️  Performance Metrics:
   Total Time: 45.32 seconds
   Iterations: 3
   Avg Iteration Time: 15.11 seconds

============================================================
💾 EXPORTING CONTENT
============================================================
✅ Markdown: ./content_output/content_20251103_143022.md
✅ HTML: ./content_output/content_20251103_143022.html
✅ Text: ./content_output/content_20251103_143022.txt
============================================================

============================================================
📈 CONTENT CREATION STATISTICS
============================================================
Iterations: 3
Final Verification: True
Word Count: 1050
💰 Cost: $0.00 (using Ollama local inference)
============================================================
```

## Features

### 1. Iterative Refinement Pattern (PEV)

**Plan**: Create content structure and objectives
**Execute**: Generate initial draft
**Verify**: Check grammar, style, coherence, facts
**Refine**: Improve content based on verification feedback
**Repeat**: Until quality threshold met or max iterations reached

**Benefits**:
- Continuous quality improvement
- Catches errors early
- Produces polished final output
- Configurable quality thresholds

### 2. Quality Verification

**Grammar Checks**:
- Spelling errors
- Punctuation issues
- Sentence structure

**Style Checks**:
- Tone consistency
- Readability score
- Sentence length variation

**Coherence Checks**:
- Logical flow
- Transition quality
- Argument strength

**Fact Checks** (when enabled):
- Citation accuracy
- Data validation

### 3. Performance Metrics (Hooks)

- **Total Time**: End-to-end content creation duration
- **Iteration Count**: Number of refinement cycles
- **Average Iteration Time**: Time per refinement cycle
- **Real-time Tracking**: Async hook execution with < 0.01ms overhead

### 4. Multi-Format Export

- **Markdown**: For documentation and blogs
- **HTML**: For web publishing
- **Text**: For plain text applications

### 5. Progress Reporting (Control Protocol)

- **Real-time Updates**: "Creating draft", "Refining (iteration 2/5)"
- **Percentage Tracking**: 0-100% completion
- **Status Messages**: Clear progress indicators

## Configuration

### PEVAgentConfig Options

```python
config = PEVAgentConfig(
    llm_provider="ollama",              # LLM provider
    model="llama3.1:8b-instruct-q8_0",                 # Model name
    temperature=0.7,                     # 0.0-1.0 (creativity vs consistency)
    max_iterations=5,                    # Maximum refinement cycles
    verification_strictness="medium",    # strict/medium/lenient
    enable_error_recovery=True,          # Continue on errors
    timeout=30,                          # Request timeout (seconds)
    max_retries=3                        # Retry count on errors
)
```

### Verification Strictness Modes

**Strict** (`verification_strictness="strict"`):
- Blocks completion until all issues resolved
- Best for: Technical documentation, legal content
- Quality score threshold: 0.95

**Medium** (`verification_strictness="medium"`):
- Balanced quality and speed
- Best for: Blog posts, articles, marketing copy
- Quality score threshold: 0.80

**Lenient** (`verification_strictness="lenient"`):
- Minimal quality checks, faster execution
- Best for: Draft content, brainstorming
- Quality score threshold: 0.60

### Environment Variables

```bash
export KAIZEN_LLM_PROVIDER=ollama
export KAIZEN_MODEL=llama3.1:8b-instruct-q8_0
export KAIZEN_TEMPERATURE=0.7
```

## Troubleshooting

### Issue: "Ollama connection refused"
**Solution**: Make sure Ollama is running:
```bash
ollama serve
```

### Issue: "Model not found"
**Solution**: Pull the model first:
```bash
ollama pull llama3.1:8b-instruct-q8_0
```

### Issue: "Max iterations reached without passing verification"
**Solution**: Increase max iterations or lower verification strictness:
```python
config = PEVAgentConfig(
    max_iterations=10,                 # More refinement cycles
    verification_strictness="medium"   # Lower quality threshold
)
```

### Issue: "Content too short/long"
**Solution**: Specify target length explicitly:
```bash
python content_creator.py "topic" length=2000
```

### Issue: "Tone not matching expectations"
**Solution**: Be more specific with tone parameter:
```bash
python content_creator.py "topic" tone="technical and formal"
```

## Production Notes

### Deployment Considerations

1. **Scalability**:
   - Parallel content generation for multiple requests
   - Queue system for long-running tasks
   - Database storage for generated content

2. **Cost Optimization**:
   - Ollama: $0.00 (unlimited content generation)
   - GPT-4: ~$0.20 per article (better quality)
   - Budget tracking prevents runaway costs

3. **Quality Improvement**:
   - Use GPT-4 for higher quality content
   - Increase `max_iterations` for more polish
   - Add custom verification rules for domain-specific content

4. **Monitoring**:
   - Performance metrics track iteration efficiency
   - Progress reporting enables real-time monitoring
   - Export logs for quality analysis

### Cost Analysis

**Ollama (FREE):**
- $0.00 per article
- Unlimited content generation
- Local inference (no network required)
- Good for development and testing
- ~45-60 seconds per article (3-5 iterations)

**GPT-4 (Paid):**
- ~$0.20 per article
- Better grammar and style
- Cloud API (requires network)
- Good for production
- ~20-30 seconds per article

## Next Steps

1. **Custom Verification Rules**: Domain-specific quality checks
2. **Multi-Language Support**: Content generation in multiple languages
3. **SEO Optimization**: Automatic keyword integration and meta tags
4. **Plagiarism Detection**: Check content originality
5. **Collaborative Editing**: Multi-agent content review and improvement

## Related Examples

- [Research Assistant (Planning)](../research-assistant/) - Three-phase planning pattern
- [Problem Solver (ToT)](../problem-solver/) - Multi-path exploration
- [Data Analysis Agent](../../tool-calling/data-analysis-agent/) - Checkpoint system
