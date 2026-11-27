# Calculator.py Code Review

## Correctness
- **Critical**: `divide()` function lacks validation for zero divisor, which will cause division by zero errors when `right` is 0. No runtime exception handling or pre-condition check exists.
  - *Priority: Critical*
  - *Proposed fix*: Add validation to raise `ZeroDivisionError` or validate that `right != 0` before performing division.

## Safety
- **No findings**: The function only performs a single operation without side effects, no external I/O, and no memory management concerns.

## Maintainability
- **High**: Function has a clear name and simple implementation. However, type hints exist but docstring is missing.
  - *Priority: Low*
  - *Proposed fix*: Add documentation string explaining the function's purpose and expected behavior.

## Tests
- **No findings**: No test file was provided or found. Cannot evaluate test coverage or test validity.
