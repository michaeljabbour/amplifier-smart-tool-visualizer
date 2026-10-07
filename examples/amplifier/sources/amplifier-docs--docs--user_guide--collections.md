---
title: Collections
description: Shareable bundles of profiles, agents, and context
---

# Collections

Collections are shareable bundles of profiles, agents, context files, and modules. They provide a way to package and distribute Amplifier configurations.

## What's in a Collection?

```
my-collection/
├── profiles/           # Profile configurations
│   ├── analyst.md
│   └── writer.md
├── agents/             # Agent definitions
│   ├── data-expert.md
│   └── editor.md
├── context/            # Context files
│   ├── guidelines.md
│   └── templates/
├── modules/            # Custom modules (optional)
│   └── tool-custom/
└── pyproject.toml      # Collection metadata
```

## Built-in Collections

| Collection | Purpose |
|------------|---------|
| `foundation` | Core philosophy and shared patterns |
| `developer-expertise` | Development-focused profiles and agents |

## Using Collections

### List Installed Collections

```bash
amplifier collection list
```

### Install a Collection

```bash
# From GitHub
amplifier collection add my-collection --source git+https://github.com/org/my-collection

# From local path
amplifier collection add my-collection --source file:///path/to/collection
```

### Remove a Collection

```bash
amplifier collection remove my-collection
```

### View Collection Contents

```bash
amplifier collection show my-collection
```

## Referencing Collection Resources

### In Profiles

```yaml
---
name: my-profile
extends: collection:foundation/base
---

Include context from collections:

@collection:developer-expertise/context/coding-standards.md
```

### In Agents

```yaml
---
name: my-agent
extends: collection:developer-expertise/agents/code-reviewer
---
```

### In Interactive Mode

```bash
amplifier> @collection:foundation/context/philosophy.md
```

## Collection Search Path

Collections are resolved from (in order):

1. `.amplifier/collections/` (project)
2. `~/.amplifier/collections/` (user)
3. Bundled collections

First match wins.

## Creating Collections

### Directory Structure

```
my-collection/
├── profiles/
│   └── my-profile.md
├── agents/
│   └── my-agent.md
├── context/
│   └── my-context.md
├── pyproject.toml
└── README.md
```

### pyproject.toml

```toml
[project]
name = "my-collection"
version = "1.0.0"
description = "My awesome collection"

[project.optional-dependencies]
# Dependencies for any custom modules
my-tool = ["requests>=2.28.0"]

[tool.amplifier.collection]
# Collection metadata
name = "my-collection"
description = "Profiles and agents for my team"
```

### Profile in Collection

`profiles/analyst.md`:

```yaml
---
name: analyst
extends: base
description: Data analysis profile
---

# Data Analyst

You are a data analysis expert.

@context/analysis-guidelines.md
```

### Agent in Collection

`agents/data-expert.md`:

```yaml
---
name: data-expert
description: Data analysis specialist
tools:
  - tool-filesystem
  - tool-bash
---

# Data Analysis Expert

You specialize in data analysis and visualization.
```

### Context in Collection

`context/analysis-guidelines.md`:

```markdown
# Analysis Guidelines

When performing data analysis:

1. Always validate data quality first
2. Document assumptions
3. Use appropriate statistical methods
4. Visualize results when helpful
```

## Publishing Collections

### Via GitHub

1. Create a repository for your collection
2. Structure it according to the convention
3. Share the installation command:

```bash
amplifier collection add my-collection \
  --source git+https://github.com/myorg/my-collection@main
```

### Via Git Tag/Version

```bash
# Install specific version
amplifier collection add my-collection \
  --source git+https://github.com/myorg/my-collection@v1.0.0
```

## Collection Conventions

### Naming

- Use lowercase with hyphens: `my-collection`
- Be descriptive: `python-web-dev`, `data-science`

### Documentation

Include a `README.md` with:

- What the collection provides
- How to install
- Overview of profiles and agents
- Usage examples

### Versioning

Use semantic versioning:

- `v1.0.0` - Major version (breaking changes)
- `v1.1.0` - Minor version (new features)
- `v1.1.1` - Patch version (bug fixes)

## Collection Dependencies

Collections can depend on other collections:

```toml
[tool.amplifier.collection]
name = "my-collection"
dependencies = [
  "foundation",
  "developer-expertise"
]
```

Referenced collections will be installed automatically.

## Best Practices

1. **Single purpose**: Each collection should have a clear focus
2. **Document everything**: Include README and inline comments
3. **Version carefully**: Use semantic versioning
4. **Test profiles**: Verify profiles work before publishing
5. **Keep it small**: Don't bundle unnecessary resources

## Troubleshooting

### Collection Not Found

```bash
# Check installed collections
amplifier collection list

# Check collection paths
ls ~/.amplifier/collections/
ls .amplifier/collections/
```

### Resource Not Loading

```bash
# Verify collection structure
amplifier collection show my-collection

# Check resource exists
cat ~/.amplifier/collections/my-collection/profiles/my-profile.md
```

### Refresh Collection Cache

```bash
amplifier collection refresh
```

## See Also

- [Profiles](profiles.md) - Profile configuration
- [Agents](agents.md) - Agent configuration
- [CLI Reference](cli.md) - Collection commands
- **→ [Collection Guide](https://github.com/microsoft/amplifier-collections/blob/main/docs/COLLECTION_GUIDE.md)** - Complete reference
