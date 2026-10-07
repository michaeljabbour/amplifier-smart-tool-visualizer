---
title: Hook Contract
description: Observability and control contract
---

# Hook Contract

Hooks observe, validate, and control operations in Amplifier.

## Purpose

Hooks participate in the agent's cognitive loop by:

- Observing events (logging, metrics)
- Blocking operations (security, validation)
- Modifying data (transformation)
- Injecting context (feedback loops)
- Requesting approval (user confirmation)

## Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class HookHandler(Protocol):
    async def __call__(
        self,
        event: str,
        data: dict
    ) -> HookResult:
        """Handle an event."""
        ...
```

## HookResult

```python
class HookResult:
    action: str  # "continue", "deny", "modify", "inject_context", "ask_user"

    # For "deny" and "modify"
    reason: str | None
    data: dict | None

    # For "inject_context"
    context_injection: str | None
    context_injection_role: str  # "system", "user", "assistant"
    ephemeral: bool  # Not stored in history

    # For "ask_user"
    approval_prompt: str | None
    approval_options: list[str] | None
    approval_timeout: float
    approval_default: str  # "allow", "deny"

    # Output control
    suppress_output: bool
    user_message: str | None
    user_message_level: str  # "info", "warning", "error"
```

## Mount Function

Hooks register handlers rather than mounting:

```python
async def mount(coordinator, config=None):
    config = config or {}
    handler = MyHook(config)

    # Register for events
    coordinator.hooks.register("tool:pre", handler.on_tool_pre, priority=10)
    coordinator.hooks.register("tool:post", handler.on_tool_post, priority=10)

    return cleanup_function  # or None
```

## Actions

### continue

Proceed with no changes:

```python
return HookResult(action="continue")
```

### deny

Block the operation:

```python
return HookResult(
    action="deny",
    reason="Operation not allowed"
)
```

### modify

Transform event data:

```python
return HookResult(
    action="modify",
    data={**data, "modified_field": "new_value"}
)
```

### inject_context

Add to conversation:

```python
return HookResult(
    action="inject_context",
    context_injection="Linter found 3 errors...",
    user_message="Found linting issues"
)
```

### ask_user

Request approval:

```python
return HookResult(
    action="ask_user",
    approval_prompt="Allow write to /etc/config?",
    approval_options=["Allow", "Deny"],
    approval_default="deny"
)
```

## Example Implementation

```python
class SafetyHook:
    def __init__(self, config):
        self.blocked_commands = config.get("blocked_commands", ["rm -rf"])

    async def on_tool_pre(self, event, data):
        if data.get("tool_name") != "bash":
            return HookResult(action="continue")

        command = data.get("input", {}).get("command", "")

        for blocked in self.blocked_commands:
            if blocked in command:
                return HookResult(
                    action="deny",
                    reason=f"Blocked command: {blocked}"
                )

        return HookResult(action="continue")
```

## Authoritative Reference

**→ [Hook Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/HOOK_CONTRACT.md)** - Complete specification
**→ [Hooks API](https://github.com/microsoft/amplifier-core/blob/main/docs/HOOKS_API.md)** - Full API reference
