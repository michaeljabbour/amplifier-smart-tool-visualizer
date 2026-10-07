---
title: Context Contract
description: Memory management contract
---

# Context Contract

Context managers handle conversation memory and state.

## Purpose

Context managers:

- Store conversation history
- Manage token limits
- Implement compaction strategies
- Support persistence

## Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ContextManager(Protocol):
    async def add_message(self, message: dict) -> None:
        """Add a message to context."""
        ...

    async def get_messages(self) -> list[dict]:
        """Get all messages."""
        ...

    async def should_compact(self) -> bool:
        """Check if compaction is needed."""
        ...

    async def compact(self) -> None:
        """Compact the context to fit token limits."""
        ...

    async def clear(self) -> None:
        """Clear all messages."""
        ...
```

## Mount Function

```python
async def mount(coordinator, config=None):
    config = config or {}
    context = MyContext(config)
    await coordinator.mount("context", context)
    return cleanup_function  # or None
```

## Configuration

Common configuration:

| Option | Type | Description |
|--------|------|-------------|
| `max_tokens` | int | Maximum context tokens |
| `compaction_strategy` | string | How to compact ("truncate", "summarize") |
| `preserve_system` | bool | Keep system messages on compact |

## Events

Context managers should emit:

| Event | When | Data |
|-------|------|------|
| `context:pre_compact` | Before compaction | message_count, tokens |
| `context:post_compact` | After compaction | message_count, tokens |
| `context:include` | Context injected | source, content |

## Message Format

Messages follow this structure:

```python
{
    "role": "user" | "assistant" | "system" | "tool",
    "content": str | list,  # Text or content blocks
    "tool_call_id": str | None,  # For tool results
    "name": str | None,  # Tool name for tool messages
}
```

## Example Implementation

```python
class SimpleContext:
    def __init__(self, config):
        self.max_tokens = config.get("max_tokens", 100000)
        self.messages = []

    async def add_message(self, message):
        self.messages.append(message)

    async def get_messages(self):
        return self.messages.copy()

    async def should_compact(self):
        token_count = self._estimate_tokens()
        return token_count > self.max_tokens * 0.9

    async def compact(self):
        # Simple truncation: remove oldest non-system messages
        system_messages = [m for m in self.messages if m["role"] == "system"]
        other_messages = [m for m in self.messages if m["role"] != "system"]

        # Keep last N messages that fit
        while self._estimate_tokens() > self.max_tokens * 0.7:
            if other_messages:
                other_messages.pop(0)
            else:
                break

        self.messages = system_messages + other_messages

    async def clear(self):
        self.messages = []

    def _estimate_tokens(self):
        # Rough estimate: 4 chars per token
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        return total_chars // 4
```

## Persistent Context

For session resumption, implement persistence:

```python
class PersistentContext:
    def __init__(self, config):
        self.storage_path = Path(config.get("storage_path"))
        self.messages = self._load()

    async def add_message(self, message):
        self.messages.append(message)
        self._save()

    def _load(self):
        if self.storage_path.exists():
            return json.loads(self.storage_path.read_text())
        return []

    def _save(self):
        self.storage_path.write_text(json.dumps(self.messages))
```

## Authoritative Reference

**→ [Context Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/CONTEXT_CONTRACT.md)** - Complete specification
