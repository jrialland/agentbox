---
name: commit-message
description: Write a clear conventional-commit message from a repository diff. Use when the user asks to commit, draft a commit message, or summarize changes for version control.
---
# Commit Message

1. Inspect the staged diff (`git diff --staged`).
2. Summarize the change in a `type(scope): subject` line (max 72 chars).
3. Add a short body explaining *why*, then note any breaking changes.
4. Do not run `git commit` unless the user asks.
