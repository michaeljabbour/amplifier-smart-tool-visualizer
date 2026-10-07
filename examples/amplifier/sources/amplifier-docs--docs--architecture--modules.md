---
title: Module System
description: How Amplifier modules are discovered, loaded, and coordinated
---

# Module System

Modules are the building blocks of Amplifier. They implement specific functionality according to stable contracts.

## Module Types

| Type | Purpose | Mount Point | Example |
|------|---------|-------------|---------|
| **Provider** | LLM backends | `providers` | Anthropic, OpenAI |
| **Tool** | Agent capabilities | `tools` | Filesystem, Bash |
| **Orchestrator** | Execution loops | `orchestrator` | Basic, Streaming |
| **Context** | Memory management | `context` | Simple, Persistent |
| **Hook** | Observability | (registered) | Logging, Approval |

## Module Discovery

Modules are discovered via Python entry points:

```toml
# In module's pyproject.toml
[project.entry-points."amplifier.modules"]
provider-anthropic = "amplifier_module_provider_anthropic:mount"
```

The kernel discovers all installed modules:

```python
# Entry points group: amplifier.modules
discovered = {
    "provider-anthropic": "amplifier_module_provider_anthropic:mount",
    "tool-filesystem": "amplifier_module_tool_filesystem:mount",
    ...
}
```

## Module Loading

### Mount Function

Every module exposes a `mount` function:

```python
async def mount(
    coordinator: ModuleCoordinator,
    config: dict | None = None
) -> Callable | None:
    """
    Mount the module.

    Args:
        coordinator: Infrastructure context
        config: Module configuration from Mount Plan

    Returns:
        Optional cleanup function
    """
    config = config or {}

    # Create module instance
    module = MyModule(config)

    # Mount to coordinator
    await coordinator.mount("providers", module, name="my-provider")

    # Return optional cleanup
    async def cleanup():
        await module.close()

    return cleanup
```

### Loading Sequence

```
Mount Plan
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Load Orchestrator (required)                              │
│    mount_plan["session"]["orchestrator"]                    │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Load Context Manager (required)                           │
│    mount_plan["session"]["context"]                         │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Load Providers                                            │
│    mount_plan["providers"]                                  │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Load Tools                                                │
│    mount_plan["tools"]                                      │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Load Hooks                                                │
│    mount_plan["hooks"]                                      │
└─────────────────────────────────────────────────────────────┘
```

## Module Contracts

### Provider Contract

```python
class Provider(Protocol):
    @property
    def name(self) -> str: ...

    def get_info(self) -> ProviderInfo: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def complete(
        self,
        request: ChatRequest,
        **kwargs
    ) -> ChatResponse: ...

    def parse_tool_calls(
        self,
        response: ChatResponse
    ) -> list[ToolCall]: ...
```

### Tool Contract

```python
class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def input_schema(self) -> dict: ...

    async def execute(
        self,
        input: dict[str, Any]
    ) -> ToolResult: ...
```

### Orchestrator Contract

```python
class Orchestrator(Protocol):
    async def execute(
        self,
        prompt: str,
        context: ContextManager,
        providers: dict[str, Provider],
        tools: dict[str, Tool],
        hooks: HookRegistry,
    ) -> str: ...
```

### Context Contract

```python
class ContextManager(Protocol):
    async def add_message(self, message: dict) -> None: ...
    async def get_messages(self) -> list[dict]: ...
    async def should_compact(self) -> bool: ...
    async def compact(self) -> None: ...
    async def clear(self) -> None: ...
```

### Hook Contract

```python
class HookHandler(Protocol):
    async def __call__(
        self,
        event: str,
        data: dict
    ) -> HookResult: ...
```

## The Coordinator

The `ModuleCoordinator` provides infrastructure context to modules:

```python
class ModuleCoordinator:
    # Mount points
    orchestrator: Orchestrator
    context: ContextManager
    providers: dict[str, Provider]
    tools: dict[str, Tool]
    hooks: HookRegistry

    # Infrastructure
    session_id: str
    parent_id: str | None
    config: dict

    # Capabilities
    def register_capability(self, name: str, impl: Any) -> None
    def get_capability(self, name: str) -> Any

    # Contribution channels
    def register_contributor(self, channel: str, name: str, callback: Callable)
    async def collect_contributions(self, channel: str) -> list

    # Module lifecycle
    async def mount(self, mount_point: str, module: Any, name: str)
    async def unmount(self, mount_point: str, name: str)
```

## Module Communication

### Via Events

Modules communicate through events:

```python
# Emitter
await coordinator.hooks.emit("my-module:event", {"data": ...})

# Observer (hook)
async def handler(event: str, data: dict) -> HookResult:
    if event == "my-module:event":
        # Handle event
        ...
    return HookResult(action="continue")
```

### Via Capabilities

Modules can register and use capabilities:

```python
# Register
coordinator.register_capability("cache", my_cache_impl)

# Use
cache = coordinator.get_capability("cache")
if cache:
    cache.set("key", "value")
```

### Via Contribution Channels

Non-interfering aggregation pattern:

```python
# Module declares observable events
coordinator.register_contributor(
    "observability.events",
    "my-module",
    lambda: ["my-module:start", "my-module:complete"]
)

# Consumer collects
events = await coordinator.collect_contributions("observability.events")
# Returns: [["my-module:start", ...], ["other:event", ...]]
```

## Module Independence

Modules are designed to be independent:

- **No peer awareness**: Modules don't know about other modules
- **Non-interference**: Module failures don't crash others
- **Swappable**: Any module can be replaced
- **Testable**: Modules can be tested in isolation

## Creating Modules

See [Module Development Guide](../developer/module_development.md) for creating your own modules.

## References

- **→ [Provider Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/PROVIDER_CONTRACT.md)**
- **→ [Tool Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/TOOL_CONTRACT.md)**
- **→ [Hook Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/HOOK_CONTRACT.md)**
- **→ [Orchestrator Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/ORCHESTRATOR_CONTRACT.md)**
- **→ [Context Contract](https://github.com/microsoft/amplifier-core/blob/main/docs/contracts/CONTEXT_CONTRACT.md)**
