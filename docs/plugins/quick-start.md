# Plugin Quick Start

## Step 1: Create plugin directory

```bash
mkdir -p plugin/plugins/hello_world
```

## Step 2: Create `plugin.toml`

```toml
[plugin]
id = "hello_world"
name = "Hello World Plugin"
description = "A simple example plugin"
version = "1.0.0"
entry = "plugins.hello_world:HelloWorldPlugin"

[plugin.sdk]
recommended = ">=0.1.0,<0.2.0"
supported = ">=0.1.0,<0.3.0"
```

### Configuration fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique plugin identifier |
| `name` | No | Display name |
| `description` | No | Plugin description |
| `version` | No | Plugin version |
| `entry` | Yes | Entry point: `module_path:ClassName` |

### SDK version fields

| Field | Description |
|-------|-------------|
| `recommended` | Recommended SDK version range |
| `supported` | Minimum supported range (rejected if not met) |
| `untested` | Allowed but warns on load |
| `conflicts` | Rejected version ranges |

## Step 3: Create `__init__.py`

```python
from plugin.sdk.base import NekoPluginBase
from plugin.sdk.decorators import neko_plugin, plugin_entry
from plugin.sdk.config import PluginConfigManager
from typing import Any

@neko_plugin
class HelloWorldPlugin(NekoPluginBase):
    """Hello World plugin example"""

    def __init__(self, ctx: Any):
        super().__init__(ctx)
        self.logger = ctx.logger
        
        # Initialize configuration manager
        self.config_manager = PluginConfigManager(ctx.config_path, ctx.logger)
        
        # Get configuration values
        self.greeting_prefix = self.config_manager.get_config("greeting_prefix", "Hello")
        self.default_name = self.config_manager.get_config("default_name", "World")
        
        self.logger.info(f"HelloWorldPlugin initialized with prefix: '{self.greeting_prefix}'")

    @plugin_entry(
        id="greet",
        name="Greet",
        description="Return a greeting message",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to greet",
                    "default": "World"
                }
            }
        }
    )
    def greet(self, name: str = "World", **_):
        """Greeting function"""
<<<<<<< HEAD
        # Use configured prefix if provided
        if not name or name == "World":
            name = self.default_name
        
        message = f"{self.greeting_prefix}, {name}!"
=======
        message = f"Hello, {name}!"
>>>>>>> main
        self.logger.info(f"Greeting: {message}")
        return {
            "message": message
        }
```

<<<<<<< HEAD
## Step 4: Add configuration (optional)

**Note: Configuration is completely optional.** Plugins can work without any custom configuration.

If you want to add custom configuration, create a `plugin.toml` file with configuration sections:

```toml
[plugin]
id = "hello_world"
name = "Hello World Plugin"
description = "A simple example plugin"
version = "1.0.0"
entry = "plugins.hello_world:HelloWorldPlugin"

[plugin.sdk]
recommended = ">=0.1.0,<0.2.0"
supported = ">=0.1.0,<0.3.0"

# Optional custom configuration
[plugin.config]
greeting_prefix = "Hello"
default_name = "N.E.K.O"
```

### Configuration is optional

Plugins can function without any `[plugin.config]` section. The `PluginConfigManager` will simply return default values when configuration keys are not found.

## Step 5: Test
=======
## Step 4: Test
>>>>>>> main

After starting the plugin server, call your plugin via HTTP:

```bash
curl -X POST http://localhost:48916/plugin/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "plugin_id": "hello_world",
    "entry_id": "greet",
    "args": {"name": "N.E.K.O"}
  }'
```

## Next steps

- [SDK Reference](./sdk-reference) — Learn about `NekoPluginBase` and `PluginContext`
- [Decorators](./decorators) — All available decorator types
- [Examples](./examples) — Complete working plugin examples
