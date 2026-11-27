# Correctness

- **Priority: High** - Missing division by zero check in `divide()` function. Division by `right = 0` will raise `ZeroDivisionError`.
  - Evidence: Line 2 calls `left / right` without validating `right != 0`
  - Correction: Add condition `if right == 0: raise ZeroDivisionError("Cannot divide by zero")` before the division

# Safety

- **Priority: Medium** - No input validation for non-float types. Type hints suggest floats, but runtime values could be invalid.
  - Evidence: Function accepts any Python object, not validated against type hints
  - Correction: Add type checking with `if not isinstance(left, float) or not isinstance(right, float): raise TypeError(...)`

# Maintainability

- **Priority: Low** - No documentation or docstring for the function.
  - Evidence: Function has no string describing its purpose, parameters, or behavior
  - Correction: Add docstring explaining what `divide()` does and what it expects

# Tests

- **Priority: Medium** - No test coverage exists. A production function like this should have unit tests.
  - Evidence: No test file found for calculator.py
  - Correction: Create unit tests covering normal division, zero divisor edge case, and type validation
