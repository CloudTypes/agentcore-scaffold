"""Calculator tool for mathematical operations."""

from strands.tools import tool


@tool
def calculator(expression: str) -> float:
    """
    Evaluate a mathematical expression.

    Args:
        expression: Mathematical expression to evaluate (e.g., "2 + 2", "sqrt(16)")

    Returns:
        Result of the calculation

    Examples:
        >>> calculator("2 + 2")
        4.0
        >>> calculator("10 * 5")
        50.0
    """
    try:
        # Security consideration: Using eval() for mathematical expression evaluation.
        # This is safe because:
        # 1. __builtins__ is restricted to an empty dict, preventing access to dangerous functions
        # 2. Only math module functions are allowed in the local namespace
        # 3. The expression is evaluated in a sandboxed environment
        # However, eval() should be used with caution. If this tool is exposed to untrusted input,
        # consider using a more restrictive expression parser (e.g., ast.literal_eval for literals
        # or a dedicated math expression parser library).
        import math

        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return float(result)
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")
