---
name: python-code-review
description: >-
  Review a Python module and write a concise report with evidence and priorities.
version: 1.0.0
---

1. Read the requested Python source and its tests when available.
2. Report only findings supported by a concrete file and behavior.
3. Group findings as correctness, safety, maintainability, and tests.
4. Give each finding a priority and a short proposed correction.
5. State explicitly when a category has no supported finding.
6. Save the report at the path requested by the user.
