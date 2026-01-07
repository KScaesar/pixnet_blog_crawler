# Pixnet Blog Crawler Agent Guide

This document outlines the technical stack and coding standards for the Pixnet Blog Crawler project.

## Technical Stack

- **Package Manager:** [uv](https://github.com/astral-sh/uv)
  - **Important:** Always ensure the `.venv` virtual environment is activated before running or installing packages, or use `uv run`.
  - Use `uv sync` to install dependencies.
  - Use `uv run <command>` to execute scripts.
  - Use `uv add <package>` to add new dependencies.
- **HTTP Client:** [httpx](https://www.python-httpx.org/)
  - Preferred for its asynchronous support and modern API.
- **HTML Parser:** [selectolax](https://github.com/rushter/selectolax)
  - Preferred for high-performance CSS selector-based parsing.

## Coding Standards

### Type Hints
All code must use strict Python type hints to ensure clarity and catch potential bugs early.
- Use `list[]`, `dict[]`, and `tuple[]` (Python 3.9+ style).
- Use `T | None` for nullable types.
- All function signatures must be fully typed (including `-> None` for void returns).

### Patterns
- **Async First:** Use `asyncio` and `httpx.AsyncClient` for network operations.
- **Data Models:** Use `pydantic` or `dataclasses` for structured data.

## Example
