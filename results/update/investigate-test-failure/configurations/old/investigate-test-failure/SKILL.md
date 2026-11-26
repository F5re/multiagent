---
name: investigate-test-failure
description: >-
  Investigate and fix failing tests without weakening or editing their expectations.
version: 1.0.0
---

1. Read the failing test and its error before editing code.
2. Read the implementation exercised by the test.
3. State a testable cause using the observed data.
4. Make the smallest implementation change that addresses the cause.
5. Do not edit tests to make a failure disappear.
6. Run the relevant tests after the final change and report the real result.
