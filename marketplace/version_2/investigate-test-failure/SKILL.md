---
name: investigate-test-failure
description: >-
  Investigate failing tests with explicit evidence, minimal changes, and verification.
version: 2.0.0
---

1. Read the exact failure output before editing.
2. Read the failing test and the implementation it exercises.
3. Record one cause supported by both sources.
4. Make the smallest implementation-only correction.
5. Preserve test files and unrelated behavior.
6. Run the exact relevant test command after the final edit.
7. Report the command, exit code, and remaining limitations.
