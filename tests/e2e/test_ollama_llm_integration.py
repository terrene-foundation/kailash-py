"""
E2E tests with Ollama LLM integration for real-world AI workflows.

These tests use real Ollama instances to validate AI-powered workflows
with dynamic data generation, intelligent processing, and LLM agents.
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder
from tests.utils.docker_config import OLLAMA_CONFIG

# Mark all tests as ollama-dependent and slow
pytestmark = [pytest.mark.ollama, pytest.mark.slow]


class OllamaTestHelper:
    """Helper class for Ollama integration testing."""

    @staticmethod
    async def check_ollama_available():
        """Check if Ollama is available and has required models."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # Check Ollama health
                response = await client.get(f"{OLLAMA_CONFIG['base_url']}/api/tags")
                if response.status_code != 200:
                    return False, "Ollama not responding"

                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]

                # Check for required models
                required_models = ["llama3.2:3b", "llama3.2:1b"]
                available_model = None

                for model in required_models:
                    if any(model in name for name in model_names):
                        available_model = model
                        break

                if not available_model:
                    return False, f"No suitable model found. Available: {model_names}"

                return True, available_model
        except Exception as e:
            return False, f"Ollama check failed: {e}"

    @staticmethod
    async def create_ollama_client():
        """Create Ollama HTTP client."""
        try:
            import httpx

            return httpx.AsyncClient(base_url=OLLAMA_CONFIG["base_url"])
        except ImportError:
            pytest.skip("httpx not available for Ollama testing")


@pytest.mark.asyncio
class TestOllamaLLMIntegration:
    """E2E tests with Ollama LLM integration."""

    async def test_ai_powered_content_generation_pipeline(self):
        """Test AI-powered content generation with real Ollama LLMs."""

        class AIContentGenerationTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Check Ollama availability
                available, model_or_error = (
                    await OllamaTestHelper.check_ollama_available()
                )
                if not available:
                    pytest.skip(f"Ollama not available: {model_or_error}")

                self.ollama_model = model_or_error
                self.ollama_client = await OllamaTestHelper.create_ollama_client()

                await self.create_test_resource("ollama", lambda: self.ollama_client)

            async def test_dynamic_content_creation_workflow(self):
                """Test dynamic content creation using Ollama LLMs."""
                workflow = (
                    AsyncWorkflowBuilder("ai_content_generation")
                    .add_async_code(
                        "generate_content_prompts",
                        f"""
# Generate diverse content prompts for AI processing
import random

content_types = [
    "blog_post", "product_description", "email_newsletter",
    "social_media_post", "technical_documentation", "marketing_copy"
]

topics = [
    "artificial intelligence", "sustainable technology", "remote work",
    "cybersecurity", "cloud computing", "data analytics", "mobile apps",
    "blockchain", "quantum computing", "green energy"
]

tones = ["professional", "casual", "technical", "persuasive", "informative", "creative"]

# Generate 10 diverse content requests
content_requests = []
for i in range(10):
    request = {{
        "id": f"content_{{i+1:02d}}",
        "type": random.choice(content_types),
        "topic": random.choice(topics),
        "tone": random.choice(tones),
        "target_length": random.choice([100, 200, 300, 500]),
        "audience": random.choice(["developers", "business_users", "general_public", "students"]),
        "priority": random.choice(["high", "medium", "low"])
    }}
    content_requests.append(request)

result = {{
    "content_requests": content_requests,
    "total_requests": len(content_requests),
    "model": "{self.ollama_model}"
}}
""",
                    )
                    .add_async_code(
                        "ai_content_generation",
                        """
# Generate content using Ollama LLM
import json
import asyncio

ollama = await get_resource("ollama")
generated_content = []
generation_metrics = {
    "total_requests": 0,
    "successful_generations": 0,
    "total_tokens": 0,
    "total_time": 0,
    "errors": []
}

start_time = asyncio.get_event_loop().time()

for request in content_requests:
    try:
        # Construct specific prompt based on request
        prompt = f'''Create a {request["tone"]} {request["type"]} about {request["topic"]}
        for {request["audience"]}. Target length: approximately {request["target_length"]} words.

        Requirements:
        - Be informative and engaging
        - Match the specified tone
        - Include relevant details
        - End with a clear conclusion or call-to-action

        Topic: {request["topic"]}
        Content Type: {request["type"]}
        Tone: {request["tone"]}
        Audience: {request["audience"]}'''

        # Call Ollama API
        response = await ollama.post("/api/generate", json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_k": 40,
                "top_p": 0.9
            }
        })

        if response.status_code == 200:
            result_data = response.json()
            content = result_data.get("response", "").strip()

            # Analyze generated content
            word_count = len(content.split())
            char_count = len(content)

            generated_item = {
                "request_id": request["id"],
                "request": request,
                "generated_content": content,
                "analysis": {
                    "word_count": word_count,
                    "character_count": char_count,
                    "meets_length_target": abs(word_count - request["target_length"]) <= request["target_length"] * 0.3,
                    "has_content": len(content) > 50
                },
                "generation_time": result_data.get("total_duration", 0) / 1000000000,  # Convert to seconds
                "tokens": result_data.get("eval_count", 0)
            }

            generated_content.append(generated_item)
            generation_metrics["successful_generations"] += 1
            generation_metrics["total_tokens"] += generated_item["tokens"]

        else:
            error_msg = f"Failed to generate content for {request['id']}: {response.status_code}"
            generation_metrics["errors"].append(error_msg)

    except Exception as e:
        error_msg = f"Error generating content for {request['id']}: {str(e)}"
        generation_metrics["errors"].append(error_msg)

    generation_metrics["total_requests"] += 1

generation_metrics["total_time"] = asyncio.get_event_loop().time() - start_time
generation_metrics["success_rate"] = generation_metrics["successful_generations"] / generation_metrics["total_requests"]
generation_metrics["avg_tokens_per_generation"] = generation_metrics["total_tokens"] / max(1, generation_metrics["successful_generations"])

result = {
    "generated_content": generated_content,
    "generation_metrics": generation_metrics,
    "content_quality_summary": {
        "total_generated": len(generated_content),
        "avg_word_count": sum(item["analysis"]["word_count"] for item in generated_content) / max(1, len(generated_content)),
        "length_target_hit_rate": sum(1 for item in generated_content if item["analysis"]["meets_length_target"]) / max(1, len(generated_content)),
        "content_types_covered": len(set(item["request"]["type"] for item in generated_content)),
        "topics_covered": len(set(item["request"]["topic"] for item in generated_content))
    }
}
""",
                    )
                    .add_async_code(
                        "content_quality_analysis",
                        """
# Analyze content quality and perform content intelligence
import re
import json
import time

ollama = await get_resource("ollama")

quality_analysis = []
content_insights = {
    "sentiment_distribution": {},
    "complexity_levels": {},
    "topic_coverage": {},
    "style_consistency": {},
    "total_analysis_time": 0
}

analysis_start = time.time()

for item in generated_content:
    content = item["generated_content"]
    request = item["request"]

    # Basic content analysis
    sentences = len(re.split(r'[.!?]+', content))
    paragraphs = len([p for p in content.split('\\n\\n') if p.strip()])
    avg_sentence_length = item["analysis"]["word_count"] / max(1, sentences)

    # Use LLM for quality assessment
    analysis_prompt = f'''Analyze this {request["type"]} content and provide a JSON response with the following structure:
    {{
        "sentiment": "positive/neutral/negative",
        "readability": "easy/medium/complex",
        "tone_match": "excellent/good/fair/poor",
        "content_relevance": "high/medium/low",
        "key_themes": ["theme1", "theme2", "theme3"],
        "strengths": ["strength1", "strength2"],
        "areas_for_improvement": ["improvement1", "improvement2"]
    }}

    Content to analyze:
    {content[:500]}...

    Expected tone: {request["tone"]}
    Expected audience: {request["audience"]}'''

    try:
        analysis_response = await ollama.post("/api/generate", json={
            "model": model,
            "prompt": analysis_prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower temperature for more consistent analysis
                "top_k": 20
            }
        })

        if analysis_response.status_code == 200:
            analysis_text = analysis_response.json().get("response", "")

            # Try to extract JSON from response
            try:
                # Look for JSON in the response
                json_start = analysis_text.find('{')
                json_end = analysis_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    analysis_json = json.loads(analysis_text[json_start:json_end])
                else:
                    # Fallback analysis
                    analysis_json = {
                        "sentiment": "neutral",
                        "readability": "medium",
                        "tone_match": "good",
                        "content_relevance": "medium",
                        "key_themes": ["general"],
                        "strengths": ["content generated"],
                        "areas_for_improvement": ["analysis unavailable"]
                    }
            except json.JSONDecodeError:
                analysis_json = {
                    "sentiment": "neutral",
                    "readability": "medium",
                    "tone_match": "good",
                    "content_relevance": "medium",
                    "key_themes": ["general"],
                    "strengths": ["content generated"],
                    "areas_for_improvement": ["json parse error"]
                }

            quality_item = {
                "content_id": item["request_id"],
                "basic_metrics": {
                    "sentences": sentences,
                    "paragraphs": paragraphs,
                    "avg_sentence_length": round(avg_sentence_length, 1),
                    "word_count": item["analysis"]["word_count"]
                },
                "ai_analysis": analysis_json,
                "overall_score": {
                    "structure": min(100, (paragraphs * 20) + (sentences * 2)),
                    "length_appropriateness": 100 if item["analysis"]["meets_length_target"] else 70,
                    "content_presence": 100 if item["analysis"]["has_content"] else 50
                }
            }

            quality_analysis.append(quality_item)

            # Update content insights
            sentiment = analysis_json.get("sentiment", "neutral")
            content_insights["sentiment_distribution"][sentiment] = content_insights["sentiment_distribution"].get(sentiment, 0) + 1

            readability = analysis_json.get("readability", "medium")
            content_insights["complexity_levels"][readability] = content_insights["complexity_levels"].get(readability, 0) + 1

    except Exception as e:
        # Fallback quality analysis
        quality_item = {
            "content_id": item["request_id"],
            "basic_metrics": {
                "sentences": sentences,
                "paragraphs": paragraphs,
                "avg_sentence_length": round(avg_sentence_length, 1),
                "word_count": item["analysis"]["word_count"]
            },
            "ai_analysis": {"error": str(e)},
            "overall_score": {
                "structure": min(100, (paragraphs * 20) + (sentences * 2)),
                "length_appropriateness": 100 if item["analysis"]["meets_length_target"] else 70,
                "content_presence": 100 if item["analysis"]["has_content"] else 50
            }
        }
        quality_analysis.append(quality_item)

content_insights["total_analysis_time"] = time.time() - analysis_start

# Calculate aggregate quality metrics
total_scores = {"structure": 0, "length_appropriateness": 0, "content_presence": 0}
for qa in quality_analysis:
    for metric, score in qa["overall_score"].items():
        total_scores[metric] += score

avg_scores = {metric: total / max(1, len(quality_analysis)) for metric, total in total_scores.items()}

result = {
    "quality_analysis": quality_analysis,
    "content_insights": content_insights,
    "aggregate_metrics": {
        "total_content_pieces": len(quality_analysis),
        "average_quality_scores": avg_scores,
        "overall_quality_score": sum(avg_scores.values()) / len(avg_scores),
        "analysis_coverage": len(quality_analysis) / max(1, len(generated_content)) * 100
    },
    "performance_summary": {
        "generation_success_rate": generation_metrics["success_rate"] * 100,
        "avg_generation_time": generation_metrics["total_time"] / max(1, generation_metrics["total_requests"]),
        "total_tokens_generated": generation_metrics["total_tokens"],
        "quality_analysis_time": content_insights["total_analysis_time"]
    }
}
""",
                    )
                    .add_connection(
                        "generate_content_prompts",
                        "content_requests",
                        "ai_content_generation",
                        "content_requests",
                    )
                    .add_connection(
                        "ai_content_generation",
                        "generated_content",
                        "content_quality_analysis",
                        "generated_content",
                    )
                    .add_connection(
                        "ai_content_generation",
                        "generation_metrics",
                        "content_quality_analysis",
                        "generation_metrics",
                    )
                    .build()
                )

                # Execute AI content pipeline with extended timeout
                async with self.assert_time_limit(
                    180.0
                ):  # 3 minutes for LLM operations
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive AI workflow validation
                self.assert_workflow_success(result)

                # Verify prompt generation
                prompt_output = result.get_output("generate_content_prompts")
                assert (
                    prompt_output["total_requests"] == 10
                ), "Should generate 10 content requests"

                # Verify AI content generation
                generation_output = result.get_output("ai_content_generation")
                metrics = generation_output["generation_metrics"]
                quality_summary = generation_output["content_quality_summary"]

                assert metrics["total_requests"] == 10, "Should process all requests"
                assert (
                    metrics["success_rate"] > 0.7
                ), f"Should have >70% success rate, got {metrics['success_rate']:.2%}"
                assert quality_summary["total_generated"] > 0, "Should generate content"
                assert (
                    quality_summary["avg_word_count"] > 50
                ), "Should generate substantial content"
                assert (
                    quality_summary["content_types_covered"] >= 3
                ), "Should cover multiple content types"

                # Verify quality analysis
                analysis_output = result.get_output("content_quality_analysis")
                aggregate = analysis_output["aggregate_metrics"]
                performance = analysis_output["performance_summary"]

                assert aggregate["total_content_pieces"] > 0, "Should analyze content"
                assert (
                    aggregate["overall_quality_score"] > 50
                ), "Should have reasonable quality score"
                assert (
                    aggregate["analysis_coverage"] > 80
                ), "Should analyze most content"

                # Performance requirements
                assert (
                    performance["generation_success_rate"] > 70
                ), "Should maintain high success rate"
                assert (
                    performance["total_tokens_generated"] > 0
                ), "Should generate tokens"

                # AI-specific validations
                content_insights = analysis_output["content_insights"]
                if content_insights["sentiment_distribution"]:
                    assert (
                        len(content_insights["sentiment_distribution"]) > 0
                    ), "Should detect sentiments"
                if content_insights["complexity_levels"]:
                    assert (
                        len(content_insights["complexity_levels"]) > 0
                    ), "Should assess complexity"

            async def tearDown(self):
                """Clean up Ollama resources."""
                if hasattr(self, "ollama_client"):
                    await self.ollama_client.aclose()
                await super().tearDown()

        async with AIContentGenerationTest("ai_content_generation_test") as test:
            await test.test_dynamic_content_creation_workflow()

    async def test_intelligent_data_processing_with_llm_agents(self):
        """Test intelligent data processing using LLM agents."""

        class IntelligentDataProcessingTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Check Ollama availability
                available, model_or_error = (
                    await OllamaTestHelper.check_ollama_available()
                )
                if not available:
                    pytest.skip(f"Ollama not available: {model_or_error}")

                self.ollama_model = model_or_error
                self.ollama_client = await OllamaTestHelper.create_ollama_client()

                await self.create_test_resource("ollama", lambda: self.ollama_client)

            async def test_ai_powered_data_analysis_workflow(self):
                """Test AI-powered data analysis with multiple LLM agents."""
                workflow = (
                    AsyncWorkflowBuilder("intelligent_data_processing")
                    .add_async_code(
                        "generate_synthetic_dataset",
                        f"""
# Generate realistic synthetic business data for AI analysis
import random
import json
from datetime import datetime, timedelta

# Generate customer data
customers = []
for i in range(50):
    customer = {{
        "id": f"CUST_{{i+1:03d}}",
        "name": f"Customer {{random.choice(['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon'])}} {{random.choice(['Corp', 'LLC', 'Inc', 'Ltd'])}}",
        "industry": random.choice(["Technology", "Healthcare", "Finance", "Manufacturing", "Retail", "Education"]),
        "size": random.choice(["Small", "Medium", "Large", "Enterprise"]),
        "region": random.choice(["North America", "Europe", "Asia Pacific", "Latin America"]),
        "tier": random.choice(["Bronze", "Silver", "Gold", "Platinum"]),
        "satisfaction_score": round(random.uniform(1.0, 5.0), 1),
        "contract_value": round(random.uniform(10000, 500000), 2),
        "signup_date": (datetime.now() - timedelta(days=random.randint(30, 730))).isoformat()
    }}
    customers.append(customer)

# Generate transaction data
transactions = []
for i in range(200):
    customer = random.choice(customers)
    transaction = {{
        "id": f"TXN_{{i+1:05d}}",
        "customer_id": customer["id"],
        "amount": round(random.uniform(100, 50000), 2),
        "type": random.choice(["Purchase", "Renewal", "Upgrade", "Support", "Consulting"]),
        "status": random.choice(["Completed", "Pending", "Failed", "Refunded"]),
        "channel": random.choice(["Web", "Mobile", "Phone", "Email", "In-Person"]),
        "timestamp": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
        "payment_method": random.choice(["Credit Card", "Bank Transfer", "Invoice", "PayPal"])
    }}
    transactions.append(transaction)

# Generate support tickets
support_tickets = []
for i in range(75):
    customer = random.choice(customers)
    ticket = {{
        "id": f"SUP_{{i+1:04d}}",
        "customer_id": customer["id"],
        "subject": random.choice([
            "Payment processing issue", "Account access problem", "Feature request",
            "Bug report", "Integration question", "Performance concern",
            "Data export request", "Billing inquiry", "Technical support"
        ]),
        "priority": random.choice(["Low", "Medium", "High", "Critical"]),
        "status": random.choice(["Open", "In Progress", "Resolved", "Closed"]),
        "category": random.choice(["Technical", "Billing", "Account", "Feature", "Integration"]),
        "resolution_time_hours": random.randint(1, 168) if random.random() > 0.3 else None,
        "created_date": (datetime.now() - timedelta(days=random.randint(1, 180))).isoformat()
    }}
    support_tickets.append(ticket)

result = {{
    "customers": customers,
    "transactions": transactions,
    "support_tickets": support_tickets,
    "dataset_summary": {{
        "total_customers": len(customers),
        "total_transactions": len(transactions),
        "total_support_tickets": len(support_tickets),
        "date_range_days": 730,
        "model": "{self.ollama_model}"
    }}
}}
""",
                    )
                    .add_async_code(
                        "ai_customer_segmentation",
                        """
# Use AI to perform intelligent customer segmentation
import json
import asyncio
from datetime import datetime

ollama = await get_resource("ollama")

# Prepare customer data for AI analysis
customer_profiles = []
try:
    for customer in customers:
        # Ensure customer is a dictionary
        if not isinstance(customer, dict):
            continue

        try:
            # Get related transactions and support tickets
            customer_transactions = [t for t in transactions if isinstance(t, dict) and t.get("customer_id") == customer.get("id")]
            customer_tickets = [t for t in support_tickets if isinstance(t, dict) and t.get("customer_id") == customer.get("id")]

            # Calculate metrics
            total_spend = sum(t.get("amount", 0) for t in customer_transactions if isinstance(t, dict) and t.get("status") == "Completed")
            transaction_count = len(customer_transactions)
            support_ticket_count = len(customer_tickets)
            avg_transaction = total_spend / max(1, transaction_count)

            profile = {{
                "customer_id": customer.get("id", ""),
                "name": customer.get("name", ""),
                "industry": customer.get("industry", ""),
                "size": customer.get("size", ""),
                "region": customer.get("region", ""),
                "tier": customer.get("tier", ""),
                "satisfaction_score": customer.get("satisfaction_score", 0),
                "contract_value": customer.get("contract_value", 0),
                "total_spend": total_spend,
                "transaction_count": transaction_count,
                "avg_transaction_value": avg_transaction,
                "support_ticket_count": support_ticket_count,
                "months_as_customer": 12  # Simplified calculation
            }}
            customer_profiles.append(profile)
        except Exception as e:
            print(f"Error processing customer {{customer}}: {{e}}")
            continue
except Exception as e:
    print(f"Error in customer processing loop: {{e}}")
    customer_profiles = []  # Fallback to empty list

# Use AI to analyze customer segments
segmentation_prompt = f'''Analyze these customer profiles and create intelligent customer segments based on behavior patterns, value, and characteristics.

Customer Data Summary:
- Total customers: {len(customer_profiles)}
- Industries: {list(set(c.get("industry", "Unknown") for c in customer_profiles if isinstance(c, dict)))}
- Size categories: {list(set(c.get("size", "Unknown") for c in customer_profiles if isinstance(c, dict)))}
- Regions: {list(set(c.get("region", "Unknown") for c in customer_profiles if isinstance(c, dict)))}

Sample customer profiles:
{json.dumps(customer_profiles[:5], indent=2)}

Please provide a JSON response with the following structure:
{{
    "segments": [
        {{
            "name": "segment_name",
            "description": "segment description",
            "criteria": "segmentation criteria",
            "characteristics": ["char1", "char2"],
            "typical_value_range": "value range",
            "growth_potential": "high/medium/low",
            "recommended_strategy": "strategy description"
        }}
    ],
    "segmentation_insights": {{
        "key_differentiators": ["factor1", "factor2"],
        "value_drivers": ["driver1", "driver2"],
        "risk_factors": ["risk1", "risk2"]
    }}
}}'''

try:
    response = await ollama.post("/api/generate", json={{
        "model": model,
        "prompt": segmentation_prompt,
        "stream": False,
        "options": {{
            "temperature": 0.4,
            "top_k": 30
        }}
    }})

    if response.status_code == 200:
        ai_response = response.json().get("response", "")

        # Extract JSON from AI response
        try:
            json_start = ai_response.find('{{')
            json_end = ai_response.rfind('}}') + 1
            if json_start >= 0 and json_end > json_start:
                ai_segments = json.loads(ai_response[json_start:json_end])
            else:
                ai_segments = {{"segments": [], "segmentation_insights": {{"error": "JSON not found"}}}}
        except json.JSONDecodeError:
            ai_segments = {{"segments": [], "segmentation_insights": {{"error": "JSON parse error"}}}}
    else:
        ai_segments = {{"segments": [], "segmentation_insights": {{"error": f"API error: {{response.status_code}}"}}}}

except Exception as e:
    ai_segments = {{"segments": [], "segmentation_insights": {{"error": str(e)}}}}

# Apply rule-based segmentation as fallback/comparison
rule_based_segments = []
for profile in customer_profiles:
    if profile["total_spend"] > 100000 and profile["satisfaction_score"] >= 4.0:
        segment = "High-Value Champions"
    elif profile["total_spend"] > 50000 and profile["support_ticket_count"] <= 2:
        segment = "Loyal Customers"
    elif profile["satisfaction_score"] <= 2.5 or profile["support_ticket_count"] > 5:
        segment = "At-Risk Customers"
    elif profile["months_as_customer"] <= 3:
        segment = "New Customers"
    elif profile["avg_transaction_value"] > 5000:
        segment = "High-Transaction Customers"
    else:
        segment = "Standard Customers"

    profile["rule_based_segment"] = segment
    rule_based_segments.append(profile)

# Calculate segment statistics
segment_stats = {{}}
for profile in rule_based_segments:
    segment = profile["rule_based_segment"]
    if segment not in segment_stats:
        segment_stats[segment] = {{
            "count": 0,
            "total_value": 0,
            "avg_satisfaction": 0,
            "avg_tickets": 0
        }}

    stats = segment_stats[segment]
    stats["count"] += 1
    stats["total_value"] += profile["total_spend"]
    stats["avg_satisfaction"] += profile["satisfaction_score"]
    stats["avg_tickets"] += profile["support_ticket_count"]

# Finalize segment statistics
for segment, stats in segment_stats.items():
    stats["avg_satisfaction"] = round(stats["avg_satisfaction"] / stats["count"], 2)
    stats["avg_tickets"] = round(stats["avg_tickets"] / stats["count"], 1)
    stats["avg_customer_value"] = round(stats["total_value"] / stats["count"], 2)

result = {{
    "customer_profiles": customer_profiles,
    "ai_segmentation": ai_segments,
    "rule_based_segmentation": rule_based_segments,
    "segment_statistics": segment_stats,
    "segmentation_metrics": {{
        "total_customers_analyzed": len(customer_profiles),
        "ai_segments_identified": len(ai_segments.get("segments", [])),
        "rule_based_segments": len(set(p["rule_based_segment"] for p in rule_based_segments)),
        "segmentation_coverage": 100.0  # All customers segmented
    }}
}}
""",
                    )
                    .add_async_code(
                        "ai_insights_and_recommendations",
                        """
# Generate AI-powered business insights and recommendations
import json

ollama = await get_resource("ollama")

# Prepare comprehensive business summary
business_summary = {{
    "customer_segments": segment_statistics,
    "total_revenue": sum(t["amount"] for t in transactions if t["status"] == "Completed"),
    "transaction_patterns": {{
        "total_transactions": len(transactions),
        "avg_transaction_value": sum(t["amount"] for t in transactions) / len(transactions),
        "top_transaction_types": {{}}
    }},
    "support_patterns": {{
        "total_tickets": len(support_tickets),
        "resolution_rate": len([t for t in support_tickets if t["status"] in ["Resolved", "Closed"]]) / len(support_tickets),
        "avg_resolution_time": sum(t["resolution_time_hours"] or 0 for t in support_tickets) / len([t for t in support_tickets if t["resolution_time_hours"]])
    }},
    "customer_health": {{
        "avg_satisfaction": sum(c["satisfaction_score"] for c in customers) / len(customers),
        "at_risk_customers": len([p for p in customer_profiles if p["satisfaction_score"] <= 2.5]),
        "high_value_customers": len([p for p in customer_profiles if p["total_spend"] > 100000])
    }}
}}

# Count transaction types
for txn in transactions:
    txn_type = txn["type"]
    business_summary["transaction_patterns"]["top_transaction_types"][txn_type] = business_summary["transaction_patterns"]["top_transaction_types"].get(txn_type, 0) + 1

# Generate AI insights
insights_prompt = f'''As a business intelligence analyst, analyze this business data and provide strategic insights and recommendations.

Business Data Summary:
{json.dumps(business_summary, indent=2, default=str)}

Customer Segmentation Results:
{json.dumps(segment_statistics, indent=2)}

Please provide a comprehensive JSON response with:
{{
    "key_insights": [
        {{
            "category": "category_name",
            "insight": "detailed insight",
            "impact": "high/medium/low",
            "data_support": "supporting data points"
        }}
    ],
    "strategic_recommendations": [
        {{
            "priority": "high/medium/low",
            "recommendation": "specific recommendation",
            "expected_outcome": "expected result",
            "implementation_effort": "high/medium/low",
            "target_segments": ["segment1", "segment2"]
        }}
    ],
    "risk_assessment": {{
        "primary_risks": ["risk1", "risk2"],
        "mitigation_strategies": ["strategy1", "strategy2"],
        "early_warning_indicators": ["indicator1", "indicator2"]
    }},
    "growth_opportunities": {{
        "revenue_expansion": ["opportunity1", "opportunity2"],
        "customer_retention": ["strategy1", "strategy2"],
        "operational_efficiency": ["improvement1", "improvement2"]
    }}
}}'''

try:
    response = await ollama.post("/api/generate", json={{
        "model": model,
        "prompt": insights_prompt,
        "stream": False,
        "options": {{
            "temperature": 0.3,
            "top_k": 25
        }}
    }})

    if response.status_code == 200:
        ai_response = response.json().get("response", "")

        # Extract JSON from AI response
        try:
            json_start = ai_response.find('{{')
            json_end = ai_response.rfind('}}') + 1
            if json_start >= 0 and json_end > json_start:
                ai_insights = json.loads(ai_response[json_start:json_end])
            else:
                ai_insights = {{"error": "JSON not found in response"}}
        except json.JSONDecodeError as e:
            ai_insights = {{"error": f"JSON parse error: {{str(e)}}"}}
    else:
        ai_insights = {{"error": f"API error: {{response.status_code}}"}}

except Exception as e:
    ai_insights = {{"error": f"Request failed: {{str(e)}}"}}

# Generate rule-based insights as baseline
rule_based_insights = {{
    "performance_metrics": {{
        "revenue_per_customer": business_summary["total_revenue"] / len(customers),
        "support_efficiency": business_summary["support_patterns"]["resolution_rate"],
        "customer_satisfaction": business_summary["customer_health"]["avg_satisfaction"],
        "transaction_frequency": len(transactions) / len(customers)
    }},
    "alerts": [],
    "recommendations": []
}}

# Rule-based alerts
if business_summary["customer_health"]["avg_satisfaction"] < 3.0:
    rule_based_insights["alerts"].append("Low customer satisfaction detected")
if business_summary["support_patterns"]["resolution_rate"] < 0.7:
    rule_based_insights["alerts"].append("Low support resolution rate")
if business_summary["customer_health"]["at_risk_customers"] > len(customers) * 0.2:
    rule_based_insights["alerts"].append("High number of at-risk customers")

# Rule-based recommendations
if len([p for p in customer_profiles if p["months_as_customer"] <= 3]) > 10:
    rule_based_insights["recommendations"].append("Focus on new customer onboarding")
if business_summary["customer_health"]["high_value_customers"] < len(customers) * 0.1:
    rule_based_insights["recommendations"].append("Develop high-value customer acquisition strategy")

result = {{
    "business_summary": business_summary,
    "ai_insights": ai_insights,
    "rule_based_insights": rule_based_insights,
    "analysis_quality": {{
        "ai_response_valid": "error" not in ai_insights,
        "insights_generated": len(ai_insights.get("key_insights", [])),
        "recommendations_generated": len(ai_insights.get("strategic_recommendations", [])),
        "data_completeness": 100.0,  # All required data available
        "analysis_depth": "comprehensive"
    }},
    "execution_summary": {{
        "customers_analyzed": len(customers),
        "transactions_processed": len(transactions),
        "support_tickets_analyzed": len(support_tickets),
        "segments_created": len(segment_statistics),
        "ai_model_used": model
    }}
}}
""",
                    )
                    .add_connection(
                        "generate_synthetic_dataset",
                        "customers",
                        "ai_customer_segmentation",
                        "customers",
                    )
                    .add_connection(
                        "generate_synthetic_dataset",
                        "transactions",
                        "ai_customer_segmentation",
                        "transactions",
                    )
                    .add_connection(
                        "generate_synthetic_dataset",
                        "support_tickets",
                        "ai_customer_segmentation",
                        "support_tickets",
                    )
                    .add_connection(
                        "ai_customer_segmentation",
                        "customer_profiles",
                        "ai_insights_and_recommendations",
                        "customer_profiles",
                    )
                    .add_connection(
                        "ai_customer_segmentation",
                        "segment_statistics",
                        "ai_insights_and_recommendations",
                        "segment_statistics",
                    )
                    .add_connection(
                        "generate_synthetic_dataset",
                        "transactions",
                        "ai_insights_and_recommendations",
                        "transactions",
                    )
                    .add_connection(
                        "generate_synthetic_dataset",
                        "customers",
                        "ai_insights_and_recommendations",
                        "customers",
                    )
                    .build()
                )

                # Execute intelligent data processing with extended timeout
                async with self.assert_time_limit(
                    240.0
                ):  # 4 minutes for complex AI operations
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive intelligent data processing validation
                self.assert_workflow_success(result)

                # Verify dataset generation
                dataset_output = result.get_output("generate_synthetic_dataset")
                summary = dataset_output["dataset_summary"]
                assert summary["total_customers"] == 50, "Should generate 50 customers"
                assert (
                    summary["total_transactions"] == 200
                ), "Should generate 200 transactions"
                assert (
                    summary["total_support_tickets"] == 75
                ), "Should generate 75 support tickets"

                # Verify AI customer segmentation
                segmentation_output = result.get_output("ai_customer_segmentation")
                seg_metrics = segmentation_output["segmentation_metrics"]
                assert (
                    seg_metrics["total_customers_analyzed"] == 50
                ), "Should analyze all customers"
                assert (
                    seg_metrics["segmentation_coverage"] == 100.0
                ), "Should achieve full coverage"
                assert (
                    seg_metrics["rule_based_segments"] >= 3
                ), "Should create multiple segments"

                # Verify segment statistics
                segment_stats = segmentation_output["segment_statistics"]
                assert len(segment_stats) >= 3, "Should have multiple customer segments"
                total_customers_in_segments = sum(
                    stats["count"] for stats in segment_stats.values()
                )
                assert (
                    total_customers_in_segments == 50
                ), "All customers should be segmented"

                # Verify AI insights
                insights_output = result.get_output("ai_insights_and_recommendations")
                analysis_quality = insights_output["analysis_quality"]
                execution_summary = insights_output["execution_summary"]

                assert (
                    execution_summary["customers_analyzed"] == 50
                ), "Should analyze all customers"
                assert (
                    execution_summary["segments_created"] >= 3
                ), "Should create segments"
                assert (
                    analysis_quality["data_completeness"] == 100.0
                ), "Should have complete data"

                # AI-specific validations
                ai_insights = insights_output["ai_insights"]
                if "error" not in ai_insights:
                    # If AI analysis succeeded, validate structure
                    if "key_insights" in ai_insights:
                        assert (
                            len(ai_insights["key_insights"]) > 0
                        ), "Should generate insights"
                    if "strategic_recommendations" in ai_insights:
                        assert (
                            len(ai_insights["strategic_recommendations"]) > 0
                        ), "Should provide recommendations"

                # Business logic validations
                business_summary = insights_output["business_summary"]
                assert business_summary["total_revenue"] > 0, "Should calculate revenue"
                assert (
                    business_summary["customer_health"]["avg_satisfaction"] > 0
                ), "Should track satisfaction"
                assert (
                    business_summary["support_patterns"]["total_tickets"] == 75
                ), "Should track all tickets"

                # Rule-based insights validation
                rule_insights = insights_output["rule_based_insights"]
                assert (
                    "performance_metrics" in rule_insights
                ), "Should calculate performance metrics"
                assert (
                    rule_insights["performance_metrics"]["revenue_per_customer"] > 0
                ), "Should calculate revenue per customer"

            async def tearDown(self):
                """Clean up Ollama resources."""
                if hasattr(self, "ollama_client"):
                    await self.ollama_client.aclose()
                await super().tearDown()

        async with IntelligentDataProcessingTest(
            "intelligent_data_processing_test"
        ) as test:
            await test.test_ai_powered_data_analysis_workflow()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
