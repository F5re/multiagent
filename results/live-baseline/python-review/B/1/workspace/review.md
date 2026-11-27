# Review Report: calculator.py

## Correctness
- **Priority**: Medium
- **Finding**: The `divide` function does not handle division by zero, which will raise an exception instead of returning a safe value.
- **Evidence**: Line 2 shows `return left / right` without any check for `right == 0`.

## Safety
- **Priority**: High
- **Finding**: Division by zero will cause runtime exceptions and undefined behavior.
- **Evidence**: The function accepts any float as the divisor with no validation.

## Maintainability
- **Priority**: Low
- **Finding**: Type hints are present (good), but the function lacks documentation about edge cases.
- **Suggestion**: Add docstring explaining division by zero behavior.

## Tests
- **Priority**: N/A
- **Finding**: No test file exists for calculator.py.
- **Recommendation**: Consider adding unit tests to cover normal division and divide-by-zero scenarios.
