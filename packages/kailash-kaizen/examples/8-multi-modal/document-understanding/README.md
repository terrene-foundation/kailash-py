## # Document Understanding - Complete Multi-Modal Workflow

Complete end-to-end document processing pipeline demonstrating Kaizen's multi-modal capabilities.

## 🎯 What This Example Demonstrates

### Phase 4 Multi-Modal Orchestration
- **Multi-step processing pipeline**: Image → OCR → Analysis → Summary
- **Provider abstraction**: Ollama (free) vs OpenAI (paid)
- **Cost tracking**: Real-time usage monitoring and budget management
- **Memory integration**: Cross-agent insights and history
- **Batch processing**: Process multiple documents efficiently

## 🏗️ Pipeline Architecture

```
┌─────────────┐
│ Document    │
│ Image (PNG) │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ Step 1: OCR Agent   │
│ (Vision Processing) │
│ - llava:13b model   │
│ - ImageField input  │
└──────┬──────────────┘
       │ extracted_text
       ▼
┌──────────────────────┐
│ Step 2: Analysis     │
│ Agent                │
│ (Text Processing)    │
│ - Document type      │
│ - Key information    │
│ - Entity extraction  │
└──────┬───────────────┘
       │ analysis
       ▼
┌──────────────────────┐
│ Step 3: Summary      │
│ Agent                │
│ (Text Processing)    │
│ - Brief summary      │
│ - Action items       │
└──────────────────────┘
```

## 💡 Key Features

### 1. Multi-Modal Signature System
```python
class DocumentOCRSignature(MultiModalSignature):
    """Extract text from document image."""
    image: ImageField = InputField(
        description="Document image to extract text from",
        max_size_mb=2.0
    )
    extracted_text: str = OutputField(description="Extracted text")
    confidence: float = OutputField(description="OCR confidence")
```

### 2. Provider Abstraction
```python
# Ollama (FREE)
config = DocumentUnderstandingConfig(
    llm_provider="ollama",
    vision_model="llava:13b"
)

# OpenAI (PAID - for validation)
config = DocumentUnderstandingConfig(
    llm_provider="openai",
    vision_model="gpt-4-vision-preview"
)
```

### 3. Cost Tracking
```python
cost_tracker = CostTracker(
    budget_limit=5.0,
    warn_on_openai_usage=True
)

# Automatic cost tracking
result = workflow.process_document(image_path)

# Get cost summary
print(f"Total cost: ${cost_tracker.get_total_cost():.3f}")
print(f"Savings: ${cost_tracker.estimate_openai_equivalent_cost():.3f}")
```

### 4. Shared Memory Integration
```python
# All agents share memory pool
memory_pool = SharedMemoryPool()

# Store results
agent.analyze(image=image_path, store_in_memory=True)

# Retrieve insights
memories = workflow.get_memory_insights(limit=10)
```

## 🚀 Usage

### Basic Usage
```python
from workflow import DocumentUnderstandingWorkflow, DocumentUnderstandingConfig

# Create workflow
config = DocumentUnderstandingConfig(
    llm_provider="ollama",  # Free local processing
    enable_cost_tracking=True
)
workflow = DocumentUnderstandingWorkflow(config)

# Process document
result = workflow.process_document("invoice.png")

print(result['summary']['summary'])
# "Invoice INV-2025-001 for $9,222.50 due Feb 15, 2025..."
```

### Batch Processing
```python
# Process multiple documents
images = ["invoice1.png", "invoice2.png", "receipt.png"]
results = workflow.batch_process_documents(images)

# Get cost summary
for i, result in enumerate(results):
    print(f"Document {i+1}: {result['summary']['summary']}")
```

### Cost Comparison
```python
# Compare Ollama vs OpenAI costs
config_ollama = DocumentUnderstandingConfig(llm_provider="ollama")
config_openai = DocumentUnderstandingConfig(llm_provider="openai")

# Process with both
result_ollama = workflow_ollama.process_document(image)
result_openai = workflow_openai.process_document(image)

# Compare costs
print(f"Ollama: ${result_ollama['cost']['total_cost']:.3f}")  # $0.00
print(f"OpenAI: ${result_openai['cost']['total_cost']:.3f}")  # ~$0.02
```

## 📊 Expected Output

```
📄 Processing document: invoice.png
💰 Provider: ollama (Cost tracking: True)

🔍 Step 1: Extracting text (OCR)...
   ✓ Extracted 245 characters

📊 Step 2: Analyzing document...
   ✓ Document type: Invoice

📝 Step 3: Generating summary...
   ✓ Summary: Invoice INV-2025-001 for Acme Corporation...

💵 Cost Summary:
   Total calls: 3
   Ollama calls: 3 (FREE)
   OpenAI calls: 0
   Total cost: $0.000
   💡 OpenAI equivalent would cost: $0.032
   💰 Savings: $0.032

📋 FINAL RESULTS
📝 Summary: Invoice INV-2025-001 for $9,222.50...
✅ Action Items: Payment due by February 15, 2025
```

## 🔧 Configuration Options

### DocumentUnderstandingConfig
```python
@dataclass
class DocumentUnderstandingConfig:
    llm_provider: str = "ollama"       # "ollama" or "openai"
    vision_model: str = "llava:13b"    # Vision model
    budget_limit: float = 5.0          # Safety limit (USD)
    enable_cost_tracking: bool = True   # Track costs
    store_in_memory: bool = True       # Store in memory
```

## 💰 Cost Analysis

### Ollama (Local, FREE)
- **Vision**: llava:13b - $0.00
- **Text**: llama2 - $0.00
- **Total**: **$0.00** ✅

### OpenAI (Cloud, PAID)
- **Vision**: GPT-4V - ~$0.01 per image
- **Text**: GPT-3.5 - ~$0.002 per request
- **Total**: **~$0.032** per document

### Savings
- **Per document**: $0.032 saved
- **100 documents**: $3.20 saved
- **1000 documents**: $32.00 saved

## 📈 Use Cases

1. **Invoice Processing**
   - Extract invoice details
   - Identify vendor, amounts, dates
   - Generate payment reminders

2. **Receipt Scanning**
   - OCR receipt text
   - Categorize expenses
   - Track spending

3. **Document Classification**
   - Identify document type
   - Extract key metadata
   - Route to appropriate workflow

4. **Contract Analysis**
   - Extract key terms
   - Identify parties
   - Highlight important clauses

## 🧪 Testing

```bash
# Run the example
cd examples/8-multi-modal/document-understanding
python workflow.py

# Run tests
pytest tests/integration/test_multi_modal_workflows.py::TestDocumentUnderstandingWorkflow -v
```

## 🎓 Learning Points

1. **Multi-Modal Signatures**: Define complex inputs/outputs
2. **Provider Abstraction**: Switch providers seamlessly
3. **Cost Optimization**: Track and minimize API costs
4. **Pipeline Orchestration**: Chain multiple agents
5. **Memory Sharing**: Cross-agent context

## 🔗 Related Examples

- **Image Analysis**: `/examples/8-multi-modal/image-analysis/`
- **Audio Transcription**: `/examples/8-multi-modal/audio-transcription/`
- **Vision Agent**: `/examples/8-multi-modal/vision-qa/`

## 📚 Technical Details

### Component Integration
- **MultiModalAgent**: Unified agent for all modalities
- **MultiModalAdapter**: Provider abstraction (Ollama/OpenAI)
- **CostTracker**: Real-time cost monitoring
- **SharedMemoryPool**: Cross-agent memory

### Phase 4 Deliverables
✅ Multi-modal orchestration
✅ Provider abstraction layer
✅ Cost tracking and warnings
✅ Cross-modal workflows
✅ Batch processing
✅ Memory integration

---

**Phase 4: Unified Multi-Modal Orchestration** ✨
