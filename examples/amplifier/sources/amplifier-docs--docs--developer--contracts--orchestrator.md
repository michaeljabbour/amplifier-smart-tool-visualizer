---
title: Orchestrator Contract
description: Execution loop strategy contract
---

# Orchestrator Contract

Orchestrators control how agents execute: the loop structure, tool handling, and response generation.

## Purpose

Orchestrators define the execution strategy:

- Basic: Simple request/response loop
- Streaming: Real-time token streaming
- Events: Event-driven architecture

## Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Orchestrator(Protocol):
    async def execute(
        self,
        prompt: str,
        context: ContextManager,
        providers: dict[str, Provider],
        tools: dict[str, Tool],
        hooks: HookRegistry,
    ) -> str:
        """Execute the orchestration loop."""
        ...
```

## Mount Function

```python
async def mount(coordinator, config=None):
    config = config or {}
    orchestrator = MyOrchestrator(config)
    await coordinator.mount("orchestrator", orchestrator)
    return cleanup_function  # or None
```

## Execution Flow

Typical orchestrator flow:

```
1. Add user prompt to context
2. Loop:
   a. Get messages from context
   b. Emit provider:request
   c. Call provider.complete()
   d. Emit provider:response
   e. Add response to context
   f. Parse tool calls
   g. If no tools: return response
   h. For each tool:
      - Emit tool:pre
      - Execute tool
      - Emit tool:post
      - Add result to context
   i. Continue loop
3. Return final response
```

## Events

Orchestrators should emit:

| Event | When | Data |
|-------|------|------|
| `prompt:submit` | Received prompt | prompt |
| `provider:request` | Before LLM call | messages, model |
| `provider:response` | After LLM response | response, usage |
| `tool:pre` | Before tool execution | tool_name, input |
| `tool:post` | After tool execution | tool_name, result |
| `prompt:complete` | Final response | response |
| `orchestrator:complete` | Loop finished | iterations, tokens |

## Configuration

Common configuration:

| Option | Type | Description |
|--------|------|-------------|
| `max_iterations` | int | Maximum loop iterations |
| `parallel_tools` | bool | Execute tools in parallel |

## Example Implementation

```python
class BasicOrchestrator:
    def __init__(self, config):
        self.max_iterations = config.get("max_iterations", 10)

    async def execute(self, prompt, context, providers, tools, hooks):
        await context.add_message({"role": "user", "content": prompt})
        provider = list(providers.values())[0]

        for iteration in range(self.max_iterations):
            messages = await context.get_messages()

            await hooks.emit("provider:request", {
                "messages": messages,
                "iteration": iteration
            })

            response = await provider.complete({"messages": messages})

            await hooks.emit("provider:response", {
                "response": response
            })

            await context.add_message({
                "role": "assistant",
                "content": response["content"]
            })

            tool_calls = provider.parse_tool_calls(response)

            if not tool_calls:
                return self._extract_text(response)

            for call in tool_calls:
                tool = tools.get(call["name"])
                if tool:
                    await hooks.emit("tool:pre", {
                        "tool_name": call["name"],
                        "input": call["input"]
                    })

                    result = await tool.execute(call["input"])

                    await hooks.emit("tool:post", {
                        "tool_name": call["name"],
                        "result": result
                    })

                    await context.add_message({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": result.get("output", "")
                    })

        return "Max iterations reached"

    def _extract_text(self, response):
        for block in response.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        return ""
```

## Authoritative Reference

**→ [Orchestrator Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/ORCHESTRATOR_CONTRACT.md)** - Complete specification
