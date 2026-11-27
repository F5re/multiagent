# Calculator.py Review

## Correctness
The `divide` function performs basic division but has no error handling for division by zero, which would cause a runtime exception. The type hints are correctly specified.

## Safety
The function lacks protection against division by zero. When `right` is 0, the function will raise a ZeroDivisionError. Consider adding validation or try-except handling.

## Maintainability
- Simple and minimal code structure
- Clear function name and type hints
- No docstring present, which limits self-documentation
- Could benefit from additional test coverage

## Tests
No tests are included in the file. The function should be tested for:
1. Normal division operations
2. Edge cases (division by zero, negative numbers)
3. Type handling

Recommended: Add a test suite with pytest or unittest to verify correctness and error handling.
