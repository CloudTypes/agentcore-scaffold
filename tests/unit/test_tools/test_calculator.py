"""
Unit tests for calculator tool.
"""

import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from tools.calculator import calculator


class TestCalculator:
    """Test cases for calculator tool."""

    def test_valid_addition(self):
        """Test simple addition."""
        assert calculator("2 + 2") == 4.0

    def test_valid_multiplication(self):
        """Test multiplication."""
        assert calculator("10 * 5") == 50.0

    def test_valid_subtraction(self):
        """Test subtraction."""
        assert calculator("10 - 3") == 7.0

    def test_valid_division(self):
        """Test division."""
        assert calculator("15 / 3") == 5.0

    def test_valid_sqrt(self):
        """Test square root function."""
        assert calculator("sqrt(16)") == 4.0

    def test_valid_pi(self):
        """Test pi constant (exposed directly, not via math module)."""
        import math

        # The calculator exposes math functions directly, so pi is available as 'pi'
        result = calculator("pi * 1")
        assert abs(result - math.pi) < 0.0001

    def test_valid_power(self):
        """Test power operation."""
        assert calculator("2 ** 3") == 8.0

    def test_valid_complex_expression(self):
        """Test complex mathematical expression."""
        assert calculator("(2 + 3) * 4") == 20.0

    def test_valid_negative_numbers(self):
        """Test negative numbers."""
        assert calculator("-5 + 3") == -2.0

    def test_valid_decimals(self):
        """Test decimal numbers."""
        assert calculator("3.5 * 2") == 7.0

    def test_valid_sin_function(self):
        """Test sin function."""
        import math

        assert calculator("sin(0)") == 0.0
        # Math functions are exposed directly, so use 'pi' not 'math.pi'
        result = calculator("sin(pi / 2)")
        assert abs(result - 1.0) < 0.0001

    def test_invalid_expression_syntax(self):
        """Test invalid expression syntax."""
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("2 +")

    def test_invalid_expression_text(self):
        """Test invalid text expression."""
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("invalid")

    def test_invalid_expression_security(self):
        """Test that dangerous operations are blocked."""
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("__import__('os')")

    def test_invalid_expression_undefined_variable(self):
        """Test undefined variable."""
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("x + 1")

    def test_division_by_zero(self):
        """Test division by zero."""
        # The calculator catches ZeroDivisionError and raises ValueError
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("5 / 0")

    def test_empty_expression(self):
        """Test empty expression."""
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("")

    def test_whitespace_only(self):
        """Test whitespace-only expression."""
        with pytest.raises(ValueError, match="Invalid expression"):
            calculator("   ")
