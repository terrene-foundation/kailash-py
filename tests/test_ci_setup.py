"""Simple test file to verify CI setup is working."""

import pytest


def test_truth():
    """Simple test that will always pass."""
    assert True, "This should always pass"


def test_basic_math():
    """Test basic math operations."""
    assert 2 + 2 == 4, "Basic addition should work"
    assert 5 - 3 == 2, "Basic subtraction should work"
    assert 3 * 4 == 12, "Basic multiplication should work"


@pytest.mark.parametrize(
    "input_val,expected",
    [
        (1, 1),
        (2, 4),
        (3, 9),
        (4, 16),
        (5, 25),
    ],
)
def test_square_function(input_val, expected):
    """Test a simple square function with various inputs."""

    def square(x):
        return x * x

    result = square(input_val)
    assert (
        result == expected
    ), f"Square of {input_val} should be {expected}, got {result}"


class TestSimpleClass:
    """Test class with setup and multiple test methods."""

    def setup_method(self):
        """Setup method called before each test."""
        self.value = 10

    def test_increment(self):
        """Test incrementing a value."""
        self.value += 1
        assert self.value == 11

    def test_decrement(self):
        """Test decrementing a value."""
        self.value -= 1
        assert self.value == 9
