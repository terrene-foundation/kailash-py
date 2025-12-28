# Signature Programming Guide

**Master declarative AI development with signature-based programming**

Signature programming is Kaizen's core innovation - it lets you define WHAT you want your AI to do declaratively, while the framework figures out HOW to implement it. This guide covers everything from basic syntax to advanced patterns.

## 🎯 What is Signature Programming?

### Traditional vs Signature-Based AI

**Traditional Approach:**
```python
# Manual prompt engineering
prompt = """
You are an expert analyst. Please analyze the following text and provide:
1. A concise summary (max 100 words)
2. The sentiment (positive, negative, or neutral)
3. Key topics (as a list)

Text: {text}

Please format your response as JSON with keys: summary, sentiment, topics.
"""

response = llm.generate(prompt.format(text=input_text))
result = json.loads(response)  # Hope it's valid JSON
```

**Signature-Based Approach (Class-based):**
```python
from kaizen.signatures import Signature, InputField, OutputField

# Declarative class-based signature (Option 3 - DSPy-inspired)
class AnalysisSignature(Signature):
    """Analyze text for summary, sentiment, and topics"""
    text: str = InputField(desc="Text to analyze")
    summary: str = OutputField(desc="Concise summary")
    sentiment: str = OutputField(desc="Overall sentiment")
    topics: list = OutputField(desc="Key topics")

# Create agent with signature class
agent = framework.create_agent("analyzer", signature=AnalysisSignature)

# Framework handles everything
workflow = agent.to_workflow()
results, run_id = runtime.execute(workflow.build(), {"text": input_text})
```

**Signature-Based Approach (String-based - legacy):**
```python
# String-based signature (still supported for simple cases)
agent = framework.create_agent(
    "analyzer",
    signature="text -> summary, sentiment, topics"
)

# Framework handles everything
workflow = agent.to_workflow()
results, run_id = runtime.execute(workflow.build(), {"text": input_text})
```

### Key Benefits

- **Declarative**: Define inputs and outputs, not implementation
- **Automatic Optimization**: Framework optimizes prompts and error handling
- **Type Safety**: Structured inputs and outputs with validation
- **Reusable**: Signatures work across different models and configurations
- **Maintainable**: Changes to implementation don't break the interface

## 📝 Signature Syntax

### Modern Class-Based Signatures (Recommended)

Kaizen uses a DSPy-inspired class-based signature system for maximum clarity and type safety:

```python
from kaizen.signatures import Signature, InputField, OutputField

class QuestionAnswer(Signature):
    """Answer questions accurately and concisely"""
    question: str = InputField(desc="The question to answer")
    answer: str = OutputField(desc="Clear, accurate answer")

class TextAnalysis(Signature):
    """Comprehensive text analysis"""
    text: str = InputField(desc="Text to analyze")
    summary: str = OutputField(desc="Concise summary")
    sentiment: str = OutputField(desc="Overall sentiment")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0")

class MultiInputExample(Signature):
    """Example with multiple inputs and outputs"""
    question: str = InputField(desc="User question")
    context: str = InputField(desc="Additional context", default="")
    answer: str = OutputField(desc="Contextualized answer")
    sources: list = OutputField(desc="Source citations")
```

**Key Features:**
- Inherit from `Signature` base class
- Use `InputField(desc="...")` or `InputField(description="...")` for inputs (both work)
- Use `OutputField(desc="...")` or `OutputField(description="...")` for outputs (both work)
- Add type annotations for clarity (`str`, `float`, `list`, etc.)
- Provide field descriptions for better AI understanding
- Support default values for optional inputs

> **📝 Note on Parameter Names**
> Both `desc=` and `description=` parameters work identically - they are aliases. Use whichever you prefer for consistency with your codebase. Examples in this guide use `desc=` for brevity, but `description=` is equally valid.

### Basic Patterns (String-based - Legacy)

**Single Input, Single Output:**
```python
"text -> summary"                    # Text summarization
"question -> answer"                 # Question answering
"data -> insights"                   # Data analysis
"image -> description"               # Image captioning
```

**Note:** String-based signatures are still supported for simple cases, but class-based signatures are recommended for production use.

**Multiple Inputs:**
```python
"question, context -> answer"                    # RAG pattern
"text, style -> rewritten_text"                # Style transfer
"data, requirements -> analysis"                # Customized analysis
"user_input, conversation_history -> response" # Chat with context
```

**Multiple Outputs:**
```python
"text -> summary, sentiment"                    # Multiple analyses
"document -> title, content, metadata"          # Document parsing
"query -> results, confidence, sources"         # Search with metadata
"text -> translation, confidence, language"     # Translation with info
```

**Complex Mappings:**
```python
"text -> summary, sentiment, topics, entities"  # Comprehensive analysis
"document -> extract, classify, validate, audit" # Document processing
"data -> insights, risks, recommendations, metrics" # Business analysis
```

### Advanced Syntax

**Type Annotations:**
```python
"text: str -> summary: str, sentiment: str"
"data: dict -> analysis: dict, confidence: float"
"image: bytes -> objects: list, description: str"
"documents: list -> summaries: list, themes: list"
```

**Optional Outputs:**
```python
"text -> summary, sentiment, warnings?"         # Warnings may be empty
"data -> results, error_message?, metadata?"   # Error and metadata optional
"query -> answer, sources?, confidence?"       # Sources optional
```

**Structured Outputs:**
```python
# Nested structures
"document -> {title: str, summary: str, metadata: {author: str, date: str}}"

# Arrays and lists
"text -> {insights: [str], scores: [float], categories: [str]}"

# Complex business objects
"financial_data -> {
    analysis: {metrics: [float], trends: [str]},
    risks: {level: str, factors: [str]},
    recommendations: [str]
}"
```

**Conditional Logic:**
```python
"text -> summary, if(length > 1000): detailed_analysis"
"data -> results, if(urgent): priority_flag, if(sensitive): audit_trail"
"query -> answer, if(confident): sources, if(!confident): alternatives"
```

## 🎯 Structured Outputs with OpenAI API (v0.6.3+)

### What is OpenAI Structured Outputs?

**New in v0.6.3:** Kaizen now supports OpenAI's Structured Outputs API with **100% schema compliance** (vs 70-85% with legacy JSON mode). This feature guarantees that LLM responses will match your signature schema exactly.

**Why It Matters:**
- **Legacy Mode** (JSON object): 70-85% compliance, may produce extra/missing fields
- **Strict Mode** (Structured Outputs): **100% compliance**, enforced by OpenAI API
- **Production Ready**: No manual validation needed, guaranteed type safety

### Enabling Structured Outputs

**Quick Start:**
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config

class ProductAnalysisSignature(Signature):
    """Structured product analysis."""
    product_description: str = InputField(desc="Product description")
    category: str = OutputField(desc="Product category")
    price_range: str = OutputField(desc="Price range estimate")
    confidence: float = OutputField(desc="Confidence score 0-1")

# Enable structured outputs with strict mode
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",  # Requires gpt-4o-2024-08-06+
    provider_config=create_structured_output_config(
        signature=ProductAnalysisSignature(),
        strict=True,  # 100% compliance
        name="product_analysis"
    )
)

agent = BaseAgent(config=config, signature=ProductAnalysisSignature())
result = agent.run(product_description="Wireless headphones with 30-hour battery")
# Guaranteed to have: category, price_range, confidence fields
```

### Configuration Modes

**Strict Mode (Recommended):**
```python
# 100% schema compliance with gpt-4o-2024-08-06+
provider_config = create_structured_output_config(
    signature=MySignature(),
    strict=True,
    name="my_response"
)

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=provider_config
)
```

**Legacy Mode (Best-Effort):**
```python
# 70-85% compliance with older models
provider_config = create_structured_output_config(
    signature=MySignature(),
    strict=False,
    name="my_response"
)

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",  # Works with older models
    provider_config=provider_config
)
```

### Response Handling

OpenAI structured outputs return pre-parsed dict responses. The framework handles this automatically:

```python
# OpenAI returns dict directly for structured outputs
response = {
    "category": "Electronics",
    "price_range": "$200-$400",
    "confidence": 0.95
}

# BaseAgent automatically detects dict responses and returns them directly
result = agent.run(product_description="Wireless headphones")

# Access fields directly - no JSON parsing needed
print(result['category'])        # "Electronics"
print(result['price_range'])     # "$200-$400"
print(result['confidence'])      # 0.95
```

**How It Works:**
- OpenAI structured outputs return JSON as a dict object (not a string)
- Both `AsyncSingleShotStrategy` and `SingleShotStrategy` detect dict responses
- Dict responses are returned directly without string parsing
- This is transparent to users - no code changes needed

**Traditional vs Structured Outputs:**
```python
# Traditional (string response, needs parsing)
response = '{"category": "Electronics", ...}'  # String
result = json.loads(response)  # Manual parsing

# Structured Outputs (dict response, pre-parsed)
response = {"category": "Electronics", ...}  # Dict
result = response  # Already parsed, use directly
```

### Signature Inheritance (v0.6.3+)

**New in v0.6.3:** Child signatures now **MERGE** parent fields instead of replacing them.

**Parent-Child Inheritance:**
```python
from kaizen.signatures import Signature, InputField, OutputField

class BaseConversationSignature(Signature):
    """Parent signature with 6 output fields."""
    conversation_text: str = InputField(desc="The conversation text")

    # Parent fields (6 fields)
    next_action: str = OutputField(desc="Next action to take")
    extracted_fields: dict = OutputField(desc="Extracted fields")
    conversation_context: str = OutputField(desc="Context of conversation")
    user_intent: str = OutputField(desc="User intent")
    system_response: str = OutputField(desc="System response")
    confidence_level: float = OutputField(desc="Confidence level 0-1")

class ReferralConversationSignature(BaseConversationSignature):
    """Child signature EXTENDS parent with 4 additional fields."""

    # Child fields (4 new fields)
    confidence_score: float = OutputField(desc="Confidence score for referral")
    user_identity_detected: bool = OutputField(desc="Whether user identity detected")
    referral_needed: bool = OutputField(desc="Whether referral is needed")
    referral_reason: str = OutputField(desc="Reason for referral")

# Verify field merging
sig = ReferralConversationSignature()
print(f"Total output fields: {len(sig.output_fields)}")  # 10 (6 from parent + 4 from child)

# Parent fields preserved
assert "next_action" in sig.output_fields
assert "extracted_fields" in sig.output_fields
assert "conversation_context" in sig.output_fields
assert "user_intent" in sig.output_fields
assert "system_response" in sig.output_fields
assert "confidence_level" in sig.output_fields

# Child fields added
assert "confidence_score" in sig.output_fields
assert "user_identity_detected" in sig.output_fields
assert "referral_needed" in sig.output_fields
assert "referral_reason" in sig.output_fields
```

**Multi-Level Inheritance:**
```python
class Level1Signature(Signature):
    """Level 1: Base signature."""
    input1: str = InputField(desc="Level 1 input")
    output1: str = OutputField(desc="Level 1 output")

class Level2Signature(Level1Signature):
    """Level 2: Extends Level 1."""
    output2: str = OutputField(desc="Level 2 output")

class Level3Signature(Level2Signature):
    """Level 3: Extends Level 2."""
    output3: str = OutputField(desc="Level 3 output")

# Verify multi-level merging
sig = Level3Signature()
assert len(sig.output_fields) == 3  # All 3 levels merged
assert "output1" in sig.output_fields  # From Level1
assert "output2" in sig.output_fields  # From Level2
assert "output3" in sig.output_fields  # From Level3
```

**Field Overriding:**
```python
class ParentSignature(Signature):
    """Parent with default field."""
    input_text: str = InputField(desc="Input text")
    result: str = OutputField(desc="Parent result")

class ChildSignature(ParentSignature):
    """Child overrides parent field."""
    result: str = OutputField(desc="Child result (overridden)")
    extra: str = OutputField(desc="Extra field")

sig = ChildSignature()
assert sig.output_fields["result"]["desc"] == "Child result (overridden)"
assert len(sig.output_fields) == 2  # Parent overridden + child extra
```

### Type Mapping

Kaizen automatically converts Python types to JSON schema types:

| Python Type | JSON Schema Type | Notes |
|-------------|------------------|-------|
| `str` | `"string"` | Basic string type |
| `int` | `"integer"` | Whole numbers |
| `float` | `"number"` | Decimal numbers |
| `bool` | `"boolean"` | True/False |
| `dict` | `"object"` | Nested objects |
| `list` | `"array"` | Arrays of items |
| `List[str]` | `{"type": "array", "items": {"type": "string"}}` | Typed arrays |
| `Optional[str]` | Not in `required` | Optional fields |

**Complex Types Example:**
```python
from typing import List, Optional

class ComplexSignature(Signature):
    """Signature with complex types."""
    user_id: str = InputField(desc="User ID")

    # Complex output types
    tags: List[str] = OutputField(desc="List of tags")
    metadata: dict = OutputField(desc="Nested metadata object")
    score: float = OutputField(desc="Numeric score")
    is_valid: bool = OutputField(desc="Validation flag")
    notes: Optional[str] = OutputField(desc="Optional notes")

# Auto-generated JSON schema:
# {
#     "type": "object",
#     "properties": {
#         "tags": {"type": "array", "items": {"type": "string"}},
#         "metadata": {"type": "object"},
#         "score": {"type": "number"},
#         "is_valid": {"type": "boolean"},
#         "notes": {"type": "string"}
#     },
#     "required": ["tags", "metadata", "score", "is_valid"],
#     "additionalProperties": false
# }
```

### Supported Models

**OpenAI Structured Outputs (Strict Mode):**
- `gpt-4o-2024-08-06` (recommended)
- `gpt-4o-mini-2024-07-18`
- Newer models released after August 2024

**Legacy JSON Object Mode:**
- `gpt-4` / `gpt-4-turbo`
- `gpt-3.5-turbo`
- Any model with JSON mode support

### Real-World Example

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config
from typing import List

class SupportTicketSignature(Signature):
    """Structured support ticket analysis."""
    ticket_text: str = InputField(desc="Customer support ticket text")

    category: str = OutputField(desc="Ticket category (technical, billing, feature_request)")
    priority: str = OutputField(desc="Priority level (low, medium, high, urgent)")
    sentiment: str = OutputField(desc="Customer sentiment (positive, neutral, negative)")
    action_items: List[str] = OutputField(desc="List of action items for support team")
    estimated_resolution_hours: int = OutputField(desc="Estimated hours to resolve")

# Create agent with structured outputs
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-2024-08-06",
    provider_config=create_structured_output_config(
        signature=SupportTicketSignature(),
        strict=True,
        name="support_analysis"
    )
)

agent = BaseAgent(config=config, signature=SupportTicketSignature())

# Process ticket with guaranteed schema compliance
result = agent.run(
    ticket_text="My payment failed but I was still charged! This is the third time this month. Please fix ASAP!"
)

print(result)
# {
#     'category': 'billing',
#     'priority': 'urgent',
#     'sentiment': 'negative',
#     'action_items': [
#         'Verify payment status',
#         'Process refund if duplicate charge',
#         'Investigate recurring payment issue'
#     ],
#     'estimated_resolution_hours': 2
# }
```

### Troubleshooting

**Issue: "Workflow parameters ['provider_config'] not declared"**
- **Cause:** Using older version of Kaizen (< 0.6.3)
- **Solution:** `pip install --upgrade kailash-kaizen`

**Issue: Child signature missing parent fields**
- **Cause:** Using older version of Kaizen (< 0.6.3)
- **Solution:** Upgrade to Kaizen 0.6.3+ (fixed in signature inheritance)

**Issue: Model returns extra fields not in schema**
- **Cause:** Using legacy mode (strict=False) with best-effort compliance
- **Solution:** Switch to strict mode with supported model

**Issue: "Invalid schema: additionalProperties must be false"**
- **Cause:** OpenAI Structured Outputs requires `additionalProperties: false`
- **Solution:** Use `strict=True` mode (automatically sets this)

## 🏗️ Implementation Patterns

### Text Processing Signatures

**Document Analysis:**
```python
# Basic document processing
doc_analyzer = framework.create_agent(
    "doc_analyzer",
    signature="document -> summary, key_points, sentiment"
)

# Advanced document processing
advanced_analyzer = framework.create_agent(
    "advanced_analyzer",
    signature="""
    document -> {
        content: {summary: str, key_points: [str]},
        analysis: {sentiment: str, tone: str, complexity: str},
        metadata: {word_count: int, readability: float, language: str},
        extraction: {entities: [str], topics: [str], keywords: [str]}
    }
    """
)
```

**Content Generation:**
```python
# Blog post generator
blog_generator = framework.create_agent(
    "blog_generator",
    signature="topic, audience, tone -> title, content, tags, meta_description"
)

# Email composer
email_composer = framework.create_agent(
    "email_composer",
    signature="purpose, recipient_context, key_points -> subject, body, tone_check"
)
```

### Data Analysis Signatures

**Business Intelligence:**
```python
# Sales analysis
sales_analyzer = framework.create_agent(
    "sales_analyzer",
    signature="""
    sales_data -> {
        metrics: {revenue: float, growth: float, trends: [str]},
        insights: [str],
        recommendations: [str],
        risks: {level: str, factors: [str]}
    }
    """
)

# Customer feedback analysis
feedback_analyzer = framework.create_agent(
    "feedback_analyzer",
    signature="reviews -> sentiment_distribution, themes, action_items, priority_issues"
)
```

**Research and Investigation:**
```python
# Market research
market_researcher = framework.create_agent(
    "market_researcher",
    signature="""
    industry, timeframe -> {
        market_size: float,
        growth_trends: [str],
        key_players: [str],
        opportunities: [str],
        threats: [str],
        recommendations: [str]
    }
    """
)

# Competitive analysis
competitor_analyzer = framework.create_agent(
    "competitor_analyzer",
    signature="company_data, competitor_data -> strengths, weaknesses, opportunities, threats"
)
```

### Multi-Modal Signatures

**Image Analysis:**
```python
# Image processing
image_analyzer = framework.create_agent(
    "image_analyzer",
    signature="image -> description, objects, scene_type, safety_rating"
)

# Document OCR and analysis
doc_ocr = framework.create_agent(
    "doc_ocr",
    signature="scanned_document -> extracted_text, document_type, confidence, layout_analysis"
)
```

**Audio Processing:**
```python
# Audio transcription and analysis
audio_processor = framework.create_agent(
    "audio_processor",
    signature="audio_file -> transcript, speaker_count, sentiment, key_topics"
)
```

## 🎯 Signature Design Patterns

### Input Design Patterns

**Context-Aware Inputs:**
```python
# Include context for better results
"query, user_context, conversation_history -> personalized_response"
"question, domain_expertise, urgency_level -> tailored_answer"
"request, user_permissions, security_context -> authorized_response"
```

**Parameterized Inputs:**
```python
# Control output style and format
"content, output_format, target_audience -> formatted_content"
"data, analysis_type, detail_level -> customized_analysis"
"text, translation_target, formality_level -> translated_text"
```

**Batch Processing Inputs:**
```python
# Process multiple items
"documents -> batch_summaries, common_themes, outliers"
"emails -> priority_ranking, response_templates, action_items"
"images -> batch_descriptions, similarity_groups, quality_scores"
```

### Output Design Patterns

**Hierarchical Outputs:**
```python
# Structured information hierarchy
"business_plan -> {
    executive_summary: str,
    sections: {
        market_analysis: {size: float, trends: [str]},
        financial_projections: {revenue: [float], costs: [float]},
        risk_assessment: {risks: [str], mitigation: [str]}
    },
    appendices: [str]
}"
```

**Confidence and Metadata:**
```python
# Include confidence and reasoning
"analysis_request -> {
    results: str,
    confidence: float,
    reasoning: str,
    sources: [str],
    limitations: [str]
}"
```

**Action-Oriented Outputs:**
```python
# Outputs that drive action
"problem_description -> {
    root_causes: [str],
    solutions: [{solution: str, effort: str, impact: str}],
    next_steps: [str],
    timeline: str
}"
```

## ⚡ Advanced Signature Features

### Conditional Logic

**Dynamic Output Based on Input:**
```python
# Different outputs based on input characteristics
complex_analyzer = framework.create_agent(
    "conditional_analyzer",
    signature="""
    text -> summary,
           if(technical_content): technical_analysis,
           if(sentiment_negative): mitigation_suggestions,
           if(length > 5000): executive_summary
    """
)
```

**Quality Gates:**
```python
# Only provide certain outputs if quality threshold met
quality_analyzer = framework.create_agent(
    "quality_analyzer",
    signature="""
    content -> analysis,
              if(confidence > 0.8): recommendations,
              if(data_complete): detailed_insights,
              if(requires_review): review_flags
    """
)
```

### Signature Composition

**Chained Signatures:**
```python
# Step 1: Extract information
extractor = framework.create_agent(
    "extractor",
    signature="document -> raw_data, structure_info"
)

# Step 2: Analyze extracted data
analyzer = framework.create_agent(
    "analyzer",
    signature="raw_data, structure_info -> insights, recommendations"
)

# Step 3: Format for presentation
formatter = framework.create_agent(
    "formatter",
    signature="insights, recommendations -> formatted_report, executive_summary"
)
```

**Parallel Processing:**
```python
# Multiple agents processing same input
content = "Long document text..."

# Run in parallel
summarizer = framework.create_agent("summarizer", signature="text -> summary")
sentiment_analyzer = framework.create_agent("sentiment", signature="text -> sentiment, emotions")
topic_extractor = framework.create_agent("topics", signature="text -> topics, categories")
```

### Template Signatures

**Reusable Signature Templates:**
```python
# Define template patterns
analysis_template = "data: {input_type} -> insights: [str], confidence: float, metadata: dict"

# Use template for different data types
sales_analyzer = framework.create_agent(
    "sales_analyzer",
    signature=analysis_template.format(input_type="sales_data")
)

customer_analyzer = framework.create_agent(
    "customer_analyzer",
    signature=analysis_template.format(input_type="customer_data")
)
```

## 🔧 Signature Optimization

### Performance Optimization

**Signature Complexity vs Performance:**
```python
# Simple signature - faster execution
basic_agent = framework.create_agent(
    "basic",
    signature="text -> summary"
)

# Complex signature - more detailed but slower
detailed_agent = framework.create_agent(
    "detailed",
    signature="text -> summary, sentiment, topics, entities, readability, language"
)

# Balanced approach - essential outputs only
balanced_agent = framework.create_agent(
    "balanced",
    signature="text -> summary, sentiment, key_topics"
)
```

**Batch Processing Optimization:**
```python
# Process multiple items in one call
batch_processor = framework.create_agent(
    "batch_processor",
    signature="texts: [str] -> summaries: [str], avg_sentiment: str, common_themes: [str]"
)

# More efficient than processing individually
individual_results = []
for text in texts:
    result, _ = runtime.execute(single_processor.to_workflow().build(), {"text": text})
    individual_results.append(result)
```

### Caching Strategies

**Signature-Based Caching:**
```python
# Enable caching for expensive operations
cached_agent = framework.create_agent(
    "research_agent",
    config={
        "cache_enabled": True,
        "cache_ttl": 3600  # 1 hour
    },
    signature="research_query -> comprehensive_analysis, sources, methodology"
)
```

### Model Selection by Signature

**Different Models for Different Signatures:**
```python
# Simple signatures can use cheaper models
simple_agent = framework.create_agent(
    "simple_summarizer",
    config={"model": "gpt-3.5-turbo"},
    signature="text -> summary"
)

# Complex signatures benefit from better models
complex_agent = framework.create_agent(
    "complex_analyzer",
    config={"model": "gpt-4"},
    signature="data -> insights, predictions, risks, recommendations, action_plan"
)
```

## 🚨 Common Patterns and Pitfalls

### Best Practices

**1. Clear and Specific Signatures:**
```python
# Good: Specific and actionable
"customer_complaint -> issue_category, severity, resolution_steps"

# Avoid: Vague and ambiguous
"text -> analysis"
```

**2. Appropriate Granularity:**
```python
# Good: Right level of detail
"article -> summary, main_points, author_perspective"

# Avoid: Too granular
"article -> word_count, sentence_count, paragraph_count, avg_word_length"

# Avoid: Too broad
"article -> everything_about_it"
```

**3. Predictable Output Formats:**
```python
# Good: Consistent structure
"review -> rating: float, sentiment: str, highlights: [str]"

# Avoid: Inconsistent or unpredictable
"review -> various_insights"
```

### Common Pitfalls

**1. Over-Complex Signatures:**
```python
# Problematic: Too many outputs
"text -> summary, sentiment, topics, entities, language, readability, style, tone, complexity, word_count, char_count, paragraph_count"

# Better: Focus on essential outputs
"text -> summary, sentiment, key_topics"
```

**2. Ambiguous Type Definitions:**
```python
# Problematic: Unclear types
"data -> results"

# Better: Clear types
"sales_data: dict -> revenue: float, trends: [str], forecast: dict"
```

**3. Missing Error Handling:**
```python
# Include error handling in signature design
"document -> {
    success: bool,
    content: str?,
    error_message: str?,
    partial_results: dict?
}"
```

## 🧪 Testing Signatures

### Signature Validation

```python
def test_signature_outputs(agent, test_cases):
    """Test that agent outputs match signature specification."""

    runtime = LocalRuntime()
    workflow = agent.to_workflow()

    for test_input, expected_keys in test_cases:
        try:
            results, _ = runtime.execute(
                workflow.build(),
                parameters=test_input
            )

            # Validate output structure
            for key in expected_keys:
                assert key in results, f"Missing expected output: {key}"

            print(f"✅ Test passed for input: {test_input}")

        except Exception as e:
            print(f"❌ Test failed for input: {test_input}, Error: {e}")

# Example test cases
test_cases = [
    ({"text": "Short text"}, ["summary", "sentiment"]),
    ({"text": "Long detailed text..."}, ["summary", "sentiment"]),
    ({"text": ""}, ["summary", "sentiment"])  # Edge case
]

text_analyzer = framework.create_agent(
    "test_analyzer",
    signature="text -> summary, sentiment"
)

test_signature_outputs(text_analyzer, test_cases)
```

### Performance Testing

```python
def benchmark_signature_performance(agent, test_inputs, iterations=5):
    """Benchmark signature performance across multiple executions."""

    import time
    runtime = LocalRuntime()
    workflow = agent.to_workflow()

    results = []

    for test_input in test_inputs:
        execution_times = []

        for i in range(iterations):
            start_time = time.time()

            try:
                output, run_id = runtime.execute(
                    workflow.build(),
                    parameters=test_input
                )
                execution_time = time.time() - start_time
                execution_times.append(execution_time)

            except Exception as e:
                print(f"❌ Execution failed: {e}")
                execution_times.append(float('inf'))

        avg_time = sum(execution_times) / len(execution_times)
        results.append({
            "input": test_input,
            "avg_execution_time": avg_time,
            "min_time": min(execution_times),
            "max_time": max(execution_times)
        })

    return results

# Benchmark different signature complexities
simple_agent = framework.create_agent("simple", signature="text -> summary")
complex_agent = framework.create_agent("complex", signature="text -> summary, sentiment, topics, entities")

test_inputs = [
    {"text": "Short text"},
    {"text": "Medium length text that provides more content to analyze..."},
    {"text": "Very long text..." * 100}
]

simple_results = benchmark_signature_performance(simple_agent, test_inputs)
complex_results = benchmark_signature_performance(complex_agent, test_inputs)

print("Simple signature performance:", simple_results)
print("Complex signature performance:", complex_results)
```

## 🎯 Real-World Examples

### Enterprise Document Processing

```python
# Complete document processing pipeline
document_processor = framework.create_agent(
    "enterprise_doc_processor",
    signature="""
    document, processing_requirements -> {
        extraction: {
            text: str,
            metadata: {author: str, date: str, version: str},
            structure: {sections: [str], page_count: int}
        },
        analysis: {
            summary: str,
            key_points: [str],
            sentiment: str,
            compliance_status: str
        },
        classification: {
            document_type: str,
            sensitivity_level: str,
            retention_category: str
        },
        audit: {
            processing_timestamp: str,
            processor_id: str,
            confidence_scores: dict
        }
    }
    """
)
```

### Customer Service Automation

```python
# Intelligent customer service agent
service_agent = framework.create_agent(
    "customer_service",
    signature="""
    customer_inquiry, customer_history, knowledge_base -> {
        response: {
            message: str,
            tone: str,
            confidence: float
        },
        routing: {
            escalation_needed: bool,
            department: str,
            priority: str
        },
        followup: {
            required: bool,
            timeline: str,
            actions: [str]
        },
        analytics: {
            sentiment: str,
            issue_category: str,
            resolution_type: str
        }
    }
    """
)
```

### Financial Analysis

```python
# Investment analysis agent
investment_analyzer = framework.create_agent(
    "investment_analyzer",
    signature="""
    financial_data, market_context -> {
        valuation: {
            current_value: float,
            fair_value: float,
            upside_potential: float
        },
        risks: {
            risk_level: str,
            risk_factors: [str],
            mitigation_strategies: [str]
        },
        recommendation: {
            action: str,
            reasoning: str,
            confidence: float,
            timeframe: str
        },
        metrics: {
            key_ratios: dict,
            peer_comparison: dict,
            historical_performance: dict
        }
    }
    """
)
```

## 📚 Next Steps

### Master Signature Programming
1. **Practice with Different Domains** - Try signatures for various use cases
2. **Experiment with Complexity** - Find the right balance for your needs
3. **Test Thoroughly** - Validate outputs match your signature specifications
4. **Optimize Performance** - Benchmark and improve execution speed

### Advanced Topics
1. **[Enterprise Features](enterprise-features.md)** - Production-ready configurations
2. **[Multi-Agent Workflows](multi-agent-workflows.md)** - Coordinate multiple signatures
3. **[Optimization](optimization.md)** - Performance tuning and scaling

### Integration Patterns
1. **[Core SDK Integration](../../2-core-concepts/)** - Workflow orchestration
2. **[DataFlow Usage](../dataflow/)** - Database integration
3. **[MCP Integration](mcp-integration.md)** - External tool connections

---

**You now understand signature programming!** This declarative approach to AI development is Kaizen's core innovation. Continue to **[Enterprise Features](enterprise-features.md)** to learn about production-ready capabilities, or explore **[Multi-Agent Workflows](multi-agent-workflows.md)** to coordinate multiple signature-based agents.
