---
title: Tool Contract
description: Agent capability contract
---

# Tool Contract

Tools provide capabilities that agents can invoke.

## Purpose

Tools extend what agents can do: read files, execute commands, search the web, etc.

## Protocol

```python
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class Tool(Protocol):
    @property
    def name(self) -> str:
        """Unique tool identifier."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description for LLM."""
        ...

    async def execute(
        self,
        input: dict[str, Any]
    ) -> ToolResult:
        """Execute the tool."""
        ...
```

!!! note "Input Schema"
    The `input_schema` property is not part of the formal Protocol but is commonly implemented by tools as a class attribute. Orchestrators use it to generate tool definitions for LLMs.

## Mount Function

```python
async def mount(coordinator, config=None):
    config = config or {}
    tool = MyTool(config)
    await coordinator.mount("tools", tool, name=tool.name)
    return cleanup_function  # or None
```

## ToolResult

```python
class ToolResult:
    success: bool           # Whether execution succeeded
    output: str | None      # Output for LLM context
    error: str | None       # Error message if failed
    metadata: dict | None   # Additional metadata
```

## Input Schema

Tools declare their parameters using JSON Schema:

```python
input_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "File path to read"
        },
        "encoding": {
            "type": "string",
            "description": "File encoding",
            "default": "utf-8"
        }
    },
    "required": ["path"]
}
```

## Events

Tools are wrapped with events:

| Event | When | Data |
|-------|------|------|
| `tool:pre` | Before execution | tool_name, input |
| `tool:post` | After execution | tool_name, result |
| `tool:error` | On failure | tool_name, error |

## Example Implementation

```python
class ReadFileTool:
    name = "read_file"
    description = "Read the contents of a file"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"}
        },
        "required": ["path"]
    }

    def __init__(self, config):
        self.allowed_paths = config.get("allowed_paths", [])

    async def execute(self, input):
        path = input.get("path")

        # Validate path
        if not self._is_allowed(path):
            return {"success": False, "error": "Path not allowed"}

        try:
            content = Path(path).read_text()
            return {"success": True, "output": content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _is_allowed(self, path):
        # Check against allowed paths
        ...
```

## Authoritative Reference

**→ [Tool Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/TOOL_CONTRACT.md)** - Complete specification
