"""
Test fixtures for research integration tests.

Provides:
- Sample research papers for testing
- Mock arXiv/PDF responses
- Test validation datasets
- Performance measurement utilities
"""

import time
from dataclasses import dataclass
from typing import Dict, List

import pytest


@dataclass
class MockResearchPaper:
    """Mock research paper for testing."""

    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    methodology: str
    metrics: Dict[str, float]
    code_url: str = ""


@pytest.fixture
def flash_attention_paper():
    """Flash Attention paper fixture (arXiv:2205.14135)."""
    return MockResearchPaper(
        arxiv_id="2205.14135",
        title="FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
        authors=["Tri Dao", "Dan Fu", "Stefano Ermon", "Atri Rudra", "Christopher Ré"],
        abstract="Transformers are slow and memory-hungry on long sequences...",
        methodology="We propose FlashAttention, an IO-aware exact attention algorithm that uses tiling to reduce the number of memory reads/writes between GPU high bandwidth memory (HBM) and GPU on-chip SRAM.",
        metrics={
            "speedup": 2.7,
            "memory_reduction": 0.3,  # 3x less memory
            "accuracy": 1.0,  # Exact attention
        },
        code_url="https://github.com/Dao-AILab/flash-attention",
    )


@pytest.fixture
def maml_paper():
    """MAML (Model-Agnostic Meta-Learning) paper fixture (arXiv:1703.03400)."""
    return MockResearchPaper(
        arxiv_id="1703.03400",
        title="Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks",
        authors=["Chelsea Finn", "Pieter Abbeel", "Sergey Levine"],
        abstract="We propose an algorithm for meta-learning that is model-agnostic...",
        methodology="MAML trains model initial parameters such that the model has maximal performance on a new task after the parameters have been updated through one or more gradient steps computed with a small amount of data from that new task.",
        metrics={
            "few_shot_accuracy": 0.95,
            "adaptation_steps": 5.0,
            "tasks_tested": 20.0,
        },
        code_url="https://github.com/cbfinn/maml",
    )


@pytest.fixture
def tree_of_thought_paper():
    """Tree of Thoughts paper fixture (arXiv:2305.10601)."""
    return MockResearchPaper(
        arxiv_id="2305.10601",
        title="Tree of Thoughts: Deliberate Problem Solving with Large Language Models",
        authors=[
            "Shunyu Yao",
            "Dian Yu",
            "Jeffrey Zhao",
            "Izhak Shafran",
            "Thomas L. Griffiths",
            "Yuan Cao",
            "Karthik Narasimhan",
        ],
        abstract="Language models are increasingly being deployed for general problem solving...",
        methodology="Tree of Thoughts (ToT) generalizes over the popular 'Chain of Thought' approach to prompting language models, and enables exploration over coherent units of text ('thoughts') that serve as intermediate steps toward problem solving.",
        metrics={
            "success_rate": 0.74,
            "steps_to_solution": 10.0,
            "branching_factor": 3.0,
        },
        code_url="https://github.com/princeton-nlp/tree-of-thought-llm",
    )


@pytest.fixture
def invalid_paper():
    """Invalid paper fixture for error testing."""
    return MockResearchPaper(
        arxiv_id="invalid_id",
        title="",
        authors=[],
        abstract="",
        methodology="",
        metrics={},
        code_url="",
    )


@pytest.fixture
def sample_papers(flash_attention_paper, maml_paper, tree_of_thought_paper):
    """Collection of sample research papers."""
    return [flash_attention_paper, maml_paper, tree_of_thought_paper]


@pytest.fixture
def validation_dataset():
    """Sample validation dataset for reproducibility testing."""
    return [
        {"input": "sequence_1", "expected_speedup": 2.5},
        {"input": "sequence_2", "expected_speedup": 2.8},
        {"input": "sequence_3", "expected_speedup": 2.6},
    ]


@pytest.fixture
def performance_timer():
    """Utility for measuring test performance."""

    class Timer:
        def __init__(self):
            self.start_time = None
            self.elapsed = None

        def start(self):
            self.start_time = time.perf_counter()
            return self

        def stop(self):
            if self.start_time is None:
                raise RuntimeError("Timer not started")
            self.elapsed = time.perf_counter() - self.start_time
            return self.elapsed

        def assert_under(self, max_seconds, operation_name="Operation"):
            if self.elapsed is None:
                raise RuntimeError("Timer not stopped")
            assert (
                self.elapsed < max_seconds
            ), f"{operation_name} took {self.elapsed:.3f}s (max: {max_seconds}s)"

    return Timer
