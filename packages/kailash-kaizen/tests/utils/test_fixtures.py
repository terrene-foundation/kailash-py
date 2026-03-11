"""
Test Fixtures for Kaizen framework integration testing.

Provides consistent test data, configurations, and utilities for comprehensive testing.
Used across all test tiers to ensure consistent testing environments with real data patterns.

Based on Kailash Core SDK test fixtures with Kaizen-specific enhancements.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kaizen.core.config import KaizenConfig


@dataclass
class KaizenTestScenario:
    """Test scenario data structure for organized testing."""

    name: str
    description: str
    inputs: Dict[str, Any]
    expected_outputs: List[str]
    execution_time_limit_ms: float = 5000
    memory_limit_mb: float = 100
    requires_ai_model: bool = False


class KaizenTestDataManager:
    """Manages test data for integration and E2E testing."""

    def __init__(self):
        self.scenarios = {}
        self.configurations = {}
        self.sample_data = {}

    def add_scenario(self, scenario: KaizenTestScenario):
        """Add a test scenario."""
        self.scenarios[scenario.name] = scenario

    def get_scenario(self, name: str) -> Optional[KaizenTestScenario]:
        """Get a test scenario by name."""
        return self.scenarios.get(name)

    def list_scenarios(self) -> List[str]:
        """List all available scenarios."""
        return list(self.scenarios.keys())


# Enterprise Kaizen configuration presets
def enterprise_test_config() -> KaizenConfig:
    """Enterprise KaizenConfig with all features enabled for comprehensive testing."""
    return KaizenConfig(
        debug=True,
        memory_enabled=True,
        optimization_enabled=True,
        security_config={"encryption": True, "auth_enabled": True, "audit_trail": True},
        monitoring_enabled=True,
        cache_enabled=True,
        multi_modal_enabled=True,
        signature_validation=True,
        auto_optimization=True,
        enterprise_features={
            "compliance_reporting": True,
            "advanced_audit": True,
            "performance_analytics": True,
            "multi_tenant": False,  # Single tenant for testing
        },
    )


def minimal_test_config() -> KaizenConfig:
    """Minimal KaizenConfig for basic functionality testing."""
    return KaizenConfig(
        debug=True,
        memory_enabled=False,
        optimization_enabled=False,
        monitoring_enabled=False,
    )


def integration_test_config() -> KaizenConfig:
    """Integration test configuration with essential features."""
    return KaizenConfig(
        debug=True,
        memory_enabled=True,
        optimization_enabled=True,
        monitoring_enabled=True,
        cache_enabled=True,
        signature_validation=True,
    )


# Agent configuration presets
def get_test_agent_configs() -> Dict[str, Dict[str, Any]]:
    """
    Provide various test agent configurations for different test scenarios.

    Returns:
        Dictionary of agent configurations for comprehensive testing
    """
    return {
        "basic_agent": {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 1000,
            "timeout": 30,
            "description": "Basic agent for simple tasks",
        },
        "enterprise_agent": {
            "model": "gpt-4",
            "temperature": 0.3,
            "max_tokens": 2000,
            "timeout": 60,
            "optimization_enabled": True,
            "memory_enabled": True,
            "audit_enabled": True,
            "description": "Enterprise agent with full features",
        },
        "fast_agent": {
            "model": "gpt-3.5-turbo",
            "temperature": 0.5,
            "max_tokens": 500,
            "timeout": 15,
            "stream": True,
            "description": "Fast agent for performance testing",
        },
        "analytical_agent": {
            "model": "gpt-4",
            "temperature": 0.1,  # Low temperature for consistency
            "max_tokens": 3000,
            "timeout": 90,
            "system_message": "You are a data analyst. Provide detailed, structured analysis.",
            "description": "Specialized agent for analytical tasks",
        },
        "creative_agent": {
            "model": "gpt-4",
            "temperature": 0.9,  # High temperature for creativity
            "max_tokens": 2500,
            "timeout": 75,
            "system_message": "You are a creative writing assistant. Be imaginative and engaging.",
            "description": "Creative agent for content generation",
        },
        "local_ollama_agent": {
            "provider": "ollama",
            "model": "llama3.1:8b-instruct-q8_0",
            "temperature": 0.7,
            "max_tokens": 1000,
            "base_url": "http://localhost:11435",
            "description": "Local Ollama agent for offline testing",
        },
    }


# Signature definitions for testing
def get_test_signatures() -> Dict[str, str]:
    """
    Provide test signature definitions for signature-based programming testing.

    Returns:
        Dictionary of signature definitions
    """
    return {
        "simple_qa": """
            name: Simple Q&A
            description: Basic question answering signature
            inputs:
                question: str = The question to answer
            outputs:
                answer: str = The answer to the question
                confidence: float = Confidence score (0-1)
        """,
        "data_analysis": """
            name: Data Analysis
            description: Analyze data and provide insights
            inputs:
                data: Any = Raw data to analyze
                analysis_type: str = Type of analysis to perform
            outputs:
                analysis: dict = Analysis results
                insights: list = Key insights discovered
                recommendations: list = Recommended actions
        """,
        "content_generation": """
            name: Content Generation
            description: Generate content based on requirements
            inputs:
                topic: str = Topic for content generation
                style: str = Writing style to use
                length: int = Approximate length in words
            outputs:
                content: str = Generated content
                metadata: dict = Content metadata
        """,
        "chain_of_thought": """
            name: Chain of Thought Reasoning
            description: Step-by-step reasoning for complex problems
            inputs:
                problem: str = Problem to solve
                context: str = Additional context
            outputs:
                steps: list = Reasoning steps
                solution: str = Final solution
                confidence: float = Solution confidence
        """,
        "multi_modal": """
            name: Multi-Modal Processing
            description: Process multiple types of input data
            inputs:
                text_input: str = Text data
                image_input: str = Image data (base64 or path)
                audio_input: str = Audio data (optional)
            outputs:
                combined_analysis: dict = Multi-modal analysis
                text_insights: str = Text-specific insights
                visual_insights: str = Image-specific insights
        """,
    }


# Test data sets
def integration_test_data() -> Dict[str, Any]:
    """Provide comprehensive test data for integration testing."""
    return {
        "simple_prompts": [
            "Hello, how are you?",
            "What is the capital of France?",
            "Explain quantum computing in simple terms.",
            "Generate a short story about a robot learning to paint.",
        ],
        "complex_prompts": [
            """Analyze the following business scenario and provide strategic recommendations:
            Company X is experiencing declining sales in their traditional product line but seeing
            growth in their digital services. They need to decide on resource allocation.""",
            """Create a comprehensive project plan for implementing a new customer service
            chatbot, including timeline, resources needed, and risk mitigation strategies.""",
        ],
        "structured_data": {
            "sales_data": [
                {"month": "Jan", "sales": 10000, "region": "North"},
                {"month": "Feb", "sales": 12000, "region": "North"},
                {"month": "Jan", "sales": 8000, "region": "South"},
                {"month": "Feb", "sales": 9500, "region": "South"},
            ],
            "customer_feedback": [
                {"rating": 5, "comment": "Excellent service!", "category": "support"},
                {"rating": 3, "comment": "Could be better", "category": "product"},
                {
                    "rating": 4,
                    "comment": "Good experience overall",
                    "category": "support",
                },
            ],
        },
        "multi_agent_scenarios": {
            "debate_scenario": {
                "topic": "The impact of artificial intelligence on employment",
                "positions": ["Pro-AI", "Cautious", "Critical"],
                "rounds": 3,
            },
            "collaboration_scenario": {
                "task": "Plan a marketing campaign for a new product",
                "roles": ["Strategist", "Creative", "Analyst", "Budget_Manager"],
            },
        },
        "performance_test_data": {
            "small_dataset": list(range(100)),
            "medium_dataset": list(range(10000)),
            "large_dataset": list(range(100000)),
            "concurrent_requests": [f"Request {i}" for i in range(50)],
        },
    }


# Mock LLM responses for predictable testing
def mock_llm_responses() -> Dict[str, Any]:
    """
    Provide mock LLM responses for unit testing.

    Note: Only use these for Tier 1 (Unit) tests. Tier 2+ tests use real models.
    """
    return {
        "simple_responses": {
            "hello": "Hello! I'm doing well, thank you for asking.",
            "capital_france": "The capital of France is Paris.",
            "quantum_computing": "Quantum computing uses quantum mechanics principles to process information in ways that classical computers cannot.",
        },
        "structured_responses": {
            "analysis": {
                "analysis": {
                    "key_findings": ["Finding 1", "Finding 2"],
                    "metrics": {"accuracy": 0.95},
                },
                "insights": ["Data shows positive trend", "Seasonal patterns observed"],
                "recommendations": ["Increase investment", "Monitor closely"],
            },
            "qa_response": {
                "answer": "This is a test answer to the question.",
                "confidence": 0.85,
            },
        },
        "error_responses": {
            "timeout_error": {"error": "Request timed out", "code": "TIMEOUT"},
            "invalid_input": {"error": "Invalid input format", "code": "INVALID_INPUT"},
            "model_error": {
                "error": "Model temporarily unavailable",
                "code": "MODEL_ERROR",
            },
        },
    }


# Test scenarios for E2E testing
def create_test_scenarios() -> KaizenTestDataManager:
    """Create comprehensive test scenarios for E2E testing."""
    manager = KaizenTestDataManager()

    # Single agent scenarios
    manager.add_scenario(
        KaizenKaizenTestScenario(
            name="simple_qa",
            description="Simple question answering with basic agent",
            inputs={"question": "What is the capital of Japan?"},
            expected_outputs=["answer", "confidence"],
            execution_time_limit_ms=3000,
            requires_ai_model=True,
        )
    )

    manager.add_scenario(
        KaizenTestScenario(
            name="data_analysis",
            description="Analyze structured data and provide insights",
            inputs={
                "data": [
                    {"sales": 100, "month": "Jan"},
                    {"sales": 150, "month": "Feb"},
                ],
                "analysis_type": "trend_analysis",
            },
            expected_outputs=["analysis", "insights", "recommendations"],
            execution_time_limit_ms=5000,
            requires_ai_model=True,
        )
    )

    # Multi-agent scenarios
    manager.add_scenario(
        KaizenTestScenario(
            name="multi_agent_debate",
            description="Multi-agent debate on a given topic",
            inputs={
                "topic": "Benefits and risks of remote work",
                "agent_positions": ["pro_remote", "mixed_approach", "office_focused"],
                "rounds": 2,
            },
            expected_outputs=[
                "debate_transcript",
                "final_positions",
                "consensus_points",
            ],
            execution_time_limit_ms=15000,
            requires_ai_model=True,
        )
    )

    # Enterprise scenarios
    manager.add_scenario(
        KaizenTestScenario(
            name="enterprise_workflow",
            description="Enterprise workflow with audit trail and compliance",
            inputs={
                "task": "Process customer complaint and generate response",
                "compliance_requirements": ["audit_trail", "approval_workflow"],
                "priority": "high",
            },
            expected_outputs=["processed_complaint", "audit_log", "compliance_report"],
            execution_time_limit_ms=10000,
            memory_limit_mb=200,
            requires_ai_model=True,
        )
    )

    # Performance testing scenarios
    manager.add_scenario(
        KaizenTestScenario(
            name="concurrent_execution",
            description="Multiple agents executing concurrently",
            inputs={
                "concurrent_tasks": [f"Task {i}" for i in range(5)],
                "max_parallel": 3,
            },
            expected_outputs=[
                "all_results",
                "execution_summary",
                "performance_metrics",
            ],
            execution_time_limit_ms=8000,
            requires_ai_model=True,
        )
    )

    return manager


# Error scenarios for robust testing
def get_error_test_scenarios() -> Dict[str, Any]:
    """Provide error scenarios for testing error handling and recovery."""
    return {
        "invalid_configurations": {
            "missing_model": {"temperature": 0.7, "max_tokens": 1000},  # Missing model
            "invalid_temperature": {
                "model": "gpt-3.5-turbo",
                "temperature": 2.0,
            },  # Invalid temp
            "negative_tokens": {
                "model": "gpt-3.5-turbo",
                "max_tokens": -1,
            },  # Invalid tokens
            "zero_timeout": {"model": "gpt-3.5-turbo", "timeout": 0},  # Invalid timeout
        },
        "network_scenarios": {
            "timeout_config": {
                "model": "gpt-3.5-turbo",
                "timeout": 0.001,
            },  # Very short timeout
            "invalid_endpoint": {
                "model": "gpt-3.5-turbo",
                "base_url": "http://invalid-endpoint",
            },
            "connection_refused": {
                "model": "gpt-3.5-turbo",
                "base_url": "http://localhost:99999",
            },
        },
        "input_scenarios": {
            "empty_input": "",
            "very_long_input": "A" * 50000,  # Very long input
            "invalid_json": '{"incomplete": json',
            "null_input": None,
            "special_characters": "Test with émojis 🚀 and speciâl chars ñ",
        },
        "resource_scenarios": {
            "memory_intensive": {
                "large_context": ["Large data item"] * 10000,
                "deep_nesting": {
                    "level_" + str(i): {"data": list(range(1000))} for i in range(100)
                },
            }
        },
    }


# Database test fixtures for DataFlow integration
def get_database_test_fixtures() -> Dict[str, Any]:
    """Provide database test fixtures for enterprise testing."""
    return {
        "user_records": [
            {"id": 1, "name": "Alice Johnson", "role": "admin", "active": True},
            {"id": 2, "name": "Bob Smith", "role": "user", "active": True},
            {"id": 3, "name": "Charlie Brown", "role": "user", "active": False},
        ],
        "workflow_executions": [
            {
                "id": "exec_001",
                "workflow_name": "data_processing",
                "status": "completed",
                "start_time": datetime.now() - timedelta(hours=2),
                "end_time": datetime.now() - timedelta(hours=1),
                "user_id": 1,
            },
            {
                "id": "exec_002",
                "workflow_name": "report_generation",
                "status": "running",
                "start_time": datetime.now() - timedelta(minutes=30),
                "end_time": None,
                "user_id": 2,
            },
        ],
        "audit_logs": [
            {
                "id": "audit_001",
                "action": "workflow_started",
                "user_id": 1,
                "execution_id": "exec_001",
                "timestamp": datetime.now() - timedelta(hours=2),
                "details": {
                    "workflow": "data_processing",
                    "inputs": {"file": "data.csv"},
                },
            }
        ],
    }


# Configuration validation utilities
def validate_test_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate test configuration and return list of issues.

    Args:
        config: Configuration to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    issues = []

    required_fields = ["model"]
    for field in required_fields:
        if field not in config:
            issues.append(f"Missing required field: {field}")

    if "temperature" in config:
        temp = config["temperature"]
        if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
            issues.append("Temperature must be a number between 0 and 2")

    if "max_tokens" in config:
        tokens = config["max_tokens"]
        if not isinstance(tokens, int) or tokens <= 0:
            issues.append("max_tokens must be a positive integer")

    if "timeout" in config:
        timeout = config["timeout"]
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            issues.append("timeout must be a positive number")

    return issues


# Environment-specific configurations
def get_environment_config(env: str = "test") -> Dict[str, Any]:
    """
    Get environment-specific configuration.

    Args:
        env: Environment name ("test", "integration", "e2e")

    Returns:
        Environment configuration
    """
    configs = {
        "test": {
            "use_real_models": False,
            "enable_caching": False,
            "timeout": 5.0,
            "max_retries": 1,
            "log_level": "DEBUG",
        },
        "integration": {
            "use_real_models": True,
            "enable_caching": True,
            "timeout": 30.0,
            "max_retries": 3,
            "log_level": "INFO",
        },
        "e2e": {
            "use_real_models": True,
            "enable_caching": True,
            "timeout": 60.0,
            "max_retries": 3,
            "log_level": "INFO",
            "enable_monitoring": True,
            "enable_audit": True,
        },
    }

    return configs.get(env, configs["test"])


# Export all main fixtures and utilities
__all__ = [
    "KaizenTestDataManager",
    "KaizenTestScenario",
    "enterprise_test_config",
    "minimal_test_config",
    "integration_test_config",
    "get_test_agent_configs",
    "get_test_signatures",
    "integration_test_data",
    "mock_llm_responses",
    "create_test_scenarios",
    "get_error_test_scenarios",
    "get_database_test_fixtures",
    "validate_test_config",
    "get_environment_config",
]
