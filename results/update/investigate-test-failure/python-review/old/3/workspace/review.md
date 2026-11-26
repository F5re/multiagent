# Code Review: calculator.py

## Correctness
- **Priority**: Medium
- **Finding**: The `divide` function lacks division-by-zero protection, which will raise an exception instead of returning a defined value.
- **Proposed correction**: Add a check for `right == 0` and handle it explicitly, e.g., return `float('inf')`, `0`, or raise a custom exception with documentation.

## Safety
- **Priority**: Low
- **Finding**: No null/None input validation; division with `None` would cause a runtime error.
- **Proposed correction**: Add type checks for both arguments to ensure they are `float`.

## Maintainability
- **Priority**: Medium
- **Finding**: The function is single-line and lacks docstrings, which reduces maintainability and self-documentation.
- **Proposed correction**: Add a docstring explaining the function's behavior and return value (including edge cases).

## Tests
- **Priority**: High
- **Finding**: There are no test cases for this function; existing test coverage is zero.
- **Proposed correction**: Create tests covering normal division, zero divisor, and None inputs. Ensure tests pass before merging any changes.
