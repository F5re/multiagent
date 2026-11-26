# Calculator.py Code Review

## Correctness

**Priority: Medium**

- **Issue**: The `divide` function does not handle division by zero.
  - **Location**: Line 2 of calculator.py
  - **Evidence**: No validation of the `right` parameter before performing division
  - **Impact**: Will raise ZeroDivisionError when right is 0
  - **Proposed correction**: Add a check for zero divisor:
    ```python
    if right == 0:
        raise ValueError("Cannot divide by zero")
    return left / right
    ```

## Safety

**Priority: Medium**

- **Issue**: No bounds checking on input values.
  - **Location**: Line 2 of calculator.py
  - **Evidence**: No validation that inputs are reasonable finite numbers
  - **Impact**: Very large or very small numbers may cause overflow/underflow
  - **Proposed correction**: Add range checks if appropriate for the intended use case

## Maintainability

**Priority: Low**

- **Issue**: Function has no docstring.
  - **Location**: Line 1 of calculator.py
  - **Evidence**: The function lacks documentation
  - **Impact**: Reduces code readability and makes it harder to understand usage
  - **Proposed correction**: Add a docstring explaining the function's purpose:
    ```python
    def divide(left: float, right: float) -> float:
        """
        Divide left by right.
        
        Args:
            left: The dividend (numerator).
            right: The divisor (denominator).
            
        Returns:
            The result of dividing left by right.
            
        Raises:
            ZeroDivisionError: When right is zero.
        """
        return left / right
    ```

## Tests

**Priority: High**

- **Issue**: No test file found for calculator.py.
  - **Evidence**: No tests were available for analysis
  - **Impact**: Without tests, changes may break existing functionality
  - **Proposed correction**: Create comprehensive test coverage including:
    - Normal division cases
    - Division by zero (expected to raise)
    - Edge cases (very small/large numbers)
