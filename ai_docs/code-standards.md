# Code Standards Reference

Consolidated guide for linting, logging, and type checking in the Reachy Agent codebase.

## Linting (Ruff)

Configuration from `pyproject.toml`:

```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
]
ignore = [
    "E501",   # line too long (handled by black)
    "B008",   # do not perform function calls in argument defaults
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["ARG"]  # Unused args allowed in tests
```

### Handling Unused Arguments

For intentionally unused function parameters (common in hooks, callbacks):

```python
# Use noqa comment - preserves API compatibility
def create_reachy_mcp_server(
    config: ReachyConfig | None = None,  # noqa: ARG001
    daemon_url: str = "http://localhost:8000",
) -> FastMCP:
```

**Important**: Don't use underscore prefixes (`_config`) as this breaks callers using keyword arguments.

### Running Linter

```bash
uvx ruff check .           # Check for issues
uvx ruff check . --fix     # Auto-fix safe issues
```

## Formatting (Black + isort)

```toml
[tool.black]
line-length = 88
target-version = ["py310", "py311", "py312"]

[tool.isort]
profile = "black"
line_length = 88
known_first_party = ["reachy_agent"]
```

### Running Formatters

```bash
uvx black .                # Format code
uvx isort . --profile black  # Sort imports
```

## Type Checking (mypy)

Configuration from `mypy.ini`:

```ini
[mypy]
python_version = 3.10
warn_return_any = False
warn_unused_ignores = True
ignore_missing_imports = True
strict_optional = True
no_implicit_optional = True

[mypy-pydantic.*]
ignore_errors = True

[mypy-yaml.*]
ignore_missing_imports = True
```

### Type Annotation Patterns

```python
# Use modern syntax (Python 3.10+)
def func(items: list[str] | None = None) -> dict[str, Any]:
    ...

# For mixed types in dicts
data: dict[str, str | float] = {
    "name": "value",
    "amount": 1.0,
}

# Use field() for mutable defaults in dataclasses
@dataclass
class Config:
    items: list[str] = field(default_factory=list)
```

### Running Type Checker

```bash
uvx mypy .                 # Full check
uvx mypy src/              # Check source only
```

## Logging (structlog)

The project uses `structlog` for structured logging with context propagation.

### Setup

```python
from reachy_agent.utils.logging import get_logger, bind_context, clear_context

log = get_logger(__name__)
```

### Basic Usage

```python
# Simple logging with key-value context
log.info("Processing request", user_id="123", action="create")
log.warning("Rate limit approaching", requests=95, limit=100)
log.error("Database connection failed", error=str(e), retry_count=3)
```

### Context Propagation

```python
# Bind context for a request/session
bind_context(request_id="abc123", user="test")

# All subsequent logs include this context
log.info("Step 1 complete")  # includes request_id, user
log.info("Step 2 complete")  # includes request_id, user

# Clear when done
clear_context()
```

### Output Modes

| Mode | Usage | Format |
|------|-------|--------|
| Console (dev) | `json_format=False` | Colored, human-readable |
| JSON (prod) | `json_format=True` | Structured JSON for parsing |

### Log File Configuration

```python
from pathlib import Path
from reachy_agent.utils.logging import configure_logging

configure_logging(
    level="INFO",
    json_format=False,      # Console output
    log_file=Path("logs/agent.log"),  # Optional file output (always JSON)
)
```

## Quality Commands Cheat Sheet

```bash
# Full quality check
uvx black . && uvx isort . && uvx ruff check . && uvx mypy .

# Quick format
uvx black . && uvx isort .

# Security scan
uvx bandit -r src/

# Coverage report
uvx pytest --cov=src --cov-report=html
```

## Test Coverage Target

The project requires **80% minimum coverage**:

```toml
[tool.coverage.report]
fail_under = 80
```

## Import Order

Following isort's black profile:

```python
# 1. Future imports
from __future__ import annotations

# 2. Standard library
import asyncio
from dataclasses import dataclass
from typing import Any

# 3. Third-party packages
import httpx
from pydantic import BaseModel

# 4. First-party (reachy_agent)
from reachy_agent.utils.logging import get_logger
```
