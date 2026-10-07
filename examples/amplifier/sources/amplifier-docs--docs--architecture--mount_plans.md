---
title: Mount Plans
description: The configuration contract between apps and kernel
---

# Mount Plans

A Mount Plan is the configuration contract that tells the kernel which modules to load and how to configure them.

## Overview

Mount Plans are the **only way** applications communicate configuration to the kernel. They specify:

- Which orchestrator and context manager to use (required)
- Which providers, tools, and hooks to load (optional)
- Configuration for each module
- Agent definitions for sub-session delegation

## Structure

```python
{
    "session": {
        "orchestrator": str,    # Required: module ID
        "context": str,         # Required: module ID
        "injection_budget_per_turn": int | None,
        "injection_size_limit": int | None
    },
    "orchestrator": {
        "config": dict          # Orchestrator-specific config
    },
    "context": {
        "config": dict          # Context-specific config
    },
    "providers": [
        {
            "module": str,      # Module ID
            "source": str,      # Git URL or path
            "config": dict      # Provider-specific config
        }
    ],
    "tools": [
        {
            "module": str,
            "source": str,
            "config": dict
        }
    ],
    "hooks": [
        {
            "module": str,
            "source": str,
            "config": dict
        }
    ],
    "agents": {
        "agent-name": {
            "description": str,
            "session": dict,
            "providers": list,
            "tools": list,
            "hooks": list,
            "system": {
                "instruction": str
            }
        }
    }
}
```

## Example Mount Plan

```python
{
    "session": {
        "orchestrator": "loop-streaming",
        "context": "context-persistent"
    },
    "providers": [
        {
            "module": "provider-anthropic",
            "source": "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main",
            "config": {
                "default_model": "claude-sonnet-4-5",
                "max_tokens": 4096
            }
        }
    ],
    "tools": [
        {
            "module": "tool-filesystem",
            "source": "git+https://github.com/microsoft/amplifier-module-tool-filesystem@main",
            "config": {
                "allowed_paths": ["/home/user/projects"]
            }
        },
        {
            "module": "tool-bash",
            "source": "git+https://github.com/microsoft/amplifier-module-tool-bash@main",
            "config": {
                "timeout": 30
            }
        }
    ],
    "hooks": [
        {
            "module": "hooks-logging",
            "source": "git+https://github.com/microsoft/amplifier-module-hooks-logging@main",
            "config": {
                "level": "info"
            }
        },
        {
            "module": "hooks-approval",
            "source": "git+https://github.com/microsoft/amplifier-module-hooks-approval@main"
        }
    ],
    "agents": {
        "explorer": {
            "description": "Codebase exploration agent",
            "tools": ["tool-filesystem", "tool-search"],
            "system": {
                "instruction": "You are a codebase exploration specialist..."
            }
        }
    }
}
```

## Session Configuration

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `orchestrator` | string | Module ID for orchestrator |
| `context` | string | Module ID for context manager |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `injection_budget_per_turn` | int | 10,000 | Token limit for hook injections per turn |
| `injection_size_limit` | int | 10,240 | Byte limit per injection |

## Module Configuration

Each module entry supports:

| Field | Required | Description |
|-------|----------|-------------|
| `module` | Yes | Module ID (entry point name) |
| `source` | No* | Where to load module from |
| `config` | No | Module-specific configuration |

*Source is required if module isn't installed as a package.

### Source Formats

```yaml
# Git repository
source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main

# Git with specific tag
source: git+https://github.com/org/module@v1.0.0

# Local path
source: file:///home/user/modules/my-module

# Subdirectory in monorepo
source: git+https://github.com/org/monorepo@main#subdirectory=modules/my-module
```

## Agent Configuration

Agents are **configuration overlays** for sub-session delegation:

```python
"agents": {
    "agent-name": {
        # Description shown in agent list
        "description": "What this agent does",

        # Override session settings
        "session": {
            "orchestrator": "loop-basic"
        },

        # Override/limit providers
        "providers": [
            {"module": "provider-anthropic", "config": {...}}
        ],

        # Override/limit tools
        "tools": ["tool-filesystem"],

        # Override/add hooks
        "hooks": [...],

        # System instruction
        "system": {
            "instruction": "You are a specialist in..."
        }
    }
}
```

Agents are **not** loaded at session start. They're used when the task tool spawns a sub-session.

## Mount Plan Creation

### From Profiles (Typical)

```python
from amplifier_profiles import compile_profile_to_mount_plan

profile = load_profile("dev")
mount_plan = compile_profile_to_mount_plan(profile)
```

### Programmatic

```python
mount_plan = {
    "session": {
        "orchestrator": "loop-basic",
        "context": "context-simple"
    },
    "providers": [
        {"module": "provider-anthropic"}
    ]
}
```

## Validation

The kernel validates Mount Plans before loading:

```python
# Required fields
assert "session" in mount_plan
assert "orchestrator" in mount_plan["session"]
assert "context" in mount_plan["session"]

# Module references exist
for provider in mount_plan.get("providers", []):
    assert "module" in provider
```

Invalid Mount Plans raise `ValidationError` with details.

## Best Practices

1. **Always specify source**: Don't rely on packages being installed
2. **Use git tags for production**: Pin to specific versions
3. **Minimal configuration**: Only override defaults when needed
4. **Test Mount Plans**: Validate before deploying

## References

- **→ [Mount Plan Specification](https://github.com/microsoft/amplifier-core/blob/main/docs/specs/MOUNT_PLAN_SPECIFICATION.md)** - Complete specification
