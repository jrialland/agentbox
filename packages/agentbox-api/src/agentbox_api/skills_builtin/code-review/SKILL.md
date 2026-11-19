---
name: code-review
description: Review a code change for correctness, security, and maintainability, producing prioritized findings. Use when the user asks for a code review or to check changes before merging.
---
# Code Review

1. Read the diff and the surrounding code.
2. Look for correctness bugs, security issues (injection, secrets, authz), and missing tests.
3. Report findings ordered by severity with file:line and a concrete fix.
4. Keep feedback specific and actionable; do not rewrite the code unless asked.
