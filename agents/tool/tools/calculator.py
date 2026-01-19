"""
Calculator tool for mathematical operations.

This module provides a calculator tool that can evaluate mathematical expressions
using Python's eval() function in a restricted environment. The tool supports
standard mathematical operations and functions from the math module.

Security Considerations:
    The tool uses eval() with restricted namespaces to prevent code injection:
    - __builtins__ is set to an empty dict, blocking access to dangerous functions
    - Only math module functions are available in the evaluation context
    - The expression is evaluated in a sandboxed environment

    However, eval() should be used with caution. For production use with untrusted
    input, consider using a more restrictive expression parser such as:
    - ast.literal_eval() for simple literals
    - A dedicated math expression parser library (e.g., pyparsing, simpleeval)

Limitations:
    - Complex expressions with nested function calls may not work as expected
    - Variable assignments are not supported
    - Only mathematical operations and math module functions are available
"""

from strands.tools import tool


@tool
def calculator(expression: str) -> float:
    """
    Evaluate a mathematical expression.

    Supports standard mathematical operations (+, -, *, /, **) and functions
    from Python's math module (e.g., sqrt, sin, cos, log, exp).

    Args:
        expression: Mathematical expression to evaluate as a string.
            Examples: "2 + 2", "sqrt(16)", "sin(pi/2)", "log(10)"

    Returns:
        Result of the calculation as a float.

    Raises:
        ValueError: If the expression is invalid, cannot be evaluated, or
            contains unsupported operations or functions.

    Examples:
        >>> calculator("2 + 2")
        4.0
        >>> calculator("10 * 5")
        50.0
        >>> calculator("sqrt(16)")
        4.0
        >>> calculator("sin(pi/2)")
        1.0
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
    except (ValueError, TypeError, NameError, SyntaxError) as e:
        raise ValueError(f"Invalid expression '{expression}': {e}")
    except Exception as e:
        raise ValueError(f"Error evaluating expression '{expression}': {e}")
