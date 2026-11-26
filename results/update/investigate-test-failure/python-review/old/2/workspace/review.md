# Code Review: calculator.py

## Correctness
- **Division by zero vulnerability**: The `divide` function can return `Infinity` or raise exceptions when dividing by zero, which may cause downstream failures. No explicit validation exists.
  - Priority: High
  - Correction: Add check for `right == 0`.

## Safety
- **Unbounded error propagation**: Division by zero returns `float('inf')`, which can silently corrupt computations in numeric algorithms that expect finite results.
  - Priority: Medium
  - Correction: Raise a clear exception or return an explicit sentinel value on invalid input.

## Maintainability
- **Missing documentation**: No docstring, type hints are present but limited. Future maintainers may misunderstand the intended behavior.
  - Priority: Low-Medium
  - Correction: Add docstring explaining expected inputs and behavior on zero divisor.

## Tests
- **No test file found**: The review could not locate a corresponding `test_calculator.py` or test suite for `calculator.py`.
  - Priority: Medium
  - Correction: Implement tests covering normal cases, division by zero, and edge cases.
