# Review: calculator.py

## Correctness
- **Issue**: Division by zero is not handled. If `right` is 0, the function will raise a ZeroDivisionError.
  - **Priority**: High
  - **Proposed Correction**: Add validation to handle division by zero, either by raising a custom exception or returning infinity/negative infinity based on the sign of `left`.

## Safety
- **Issue**: No type enforcement at runtime. While type hints are present, Python does not enforce them by default, so non-float inputs could be passed without error.
  - **Priority**: Medium
  - **Proposed Correction**: Add input validation to ensure both `left` and `right` are floats before performing division.

## Maintainability
- **Issue**: No documentation or docstrings present. Future maintainers cannot understand the purpose, usage, or expected behavior of the function without examining tests or external documentation.
  - **Priority**: Medium
  - **Proposed Correction**: Add a clear docstring explaining the function's purpose, parameters, return value, and edge cases (e.g., division by zero).

## Tests
- **Finding**: No test file found for calculator.py. This makes it impossible to verify correctness or catch regressions.
  - **Priority**: High
  - **Proposed Correction**: Create a test file (e.g., `test_calculator.py`) with tests covering normal division, edge cases (zero divisor), and type validation if implemented.
