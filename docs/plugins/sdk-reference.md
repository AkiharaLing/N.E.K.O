# SDK Reference

## NekoPluginBase

All plugins must inherit from `NekoPluginBase`.

```python
from plugin.sdk.base import NekoPluginBase

class MyPlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
```

### Methods

#### `get_input_schema() → dict`

Returns the plugin's input JSON Schema. By default reads from the class attribute. Override for dynamic schemas.

#### `report_status(status: dict) → None`

Report plugin status to the main process.

```python
self.report_status({
    "status": "running",
    "progress": 50,
    "message": "Processing..."
})
```

#### `collect_entries() → dict`

Collect all entry points (methods decorated with `@plugin_entry`). Called automatically by the system.

## PluginContext

The `ctx` object passed to plugin constructors.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `ctx.plugin_id` | `str` | Plugin identifier |
| `ctx.config_path` | `Path` | Path to `plugin.toml` |
| `ctx.logger` | `Logger` | Logger instance |

### Methods

#### `ctx.update_status(status: dict) → None`

Update plugin status in the main process.

#### `ctx.push_message(...) → None`

Push a message to the main system.

```python
ctx.push_message(
    source="my_feature",          # Message source identifier
    message_type="text",          # "text" | "url" | "binary" | "binary_url"
    description="Task complete",  # Human-readable description
    priority=5,                   # 0-10 (0=low, 10=emergency)
    content="Result text",        # For text/url types
    binary_data=b"...",           # For binary type
    binary_url="https://...",     # For binary_url type
    metadata={"key": "value"}    # Additional metadata
)
```

### Message types

| Type | Use case |
|------|----------|
| `text` | Plain text messages |
| `url` | URL links |
| `binary` | Small binary data (transmitted directly) |
| `binary_url` | Large files (referenced by URL) |

### Priority levels

| Range | Level | Use case |
|-------|-------|----------|
| 0-2 | Low | Informational messages |
| 3-5 | Medium | General notifications |
| 6-8 | High | Important notifications |
| 9-10 | Emergency | Needs immediate handling |

## PluginConfigManager

Utility for loading and accessing plugin configuration from `plugin.toml`.

### Usage

```python
from plugin.sdk.config import PluginConfigManager

# In plugin __init__
def __init__(self, ctx):
    super().__init__(ctx)
    self.config_manager = PluginConfigManager(ctx.config_path, ctx.logger)
    
    # Get configuration values with defaults
    # These will return defaults if no [plugin.config] section exists
    self.api_key = self.config_manager.get_config("api_key", "")
    self.timeout = self.config_manager.get_config("timeout", 30)
    self.feature_enabled = self.config_manager.get_config("features.my_feature", False)
```

### Key points

- **Configuration is optional**: Plugins can work without any `[plugin.config]` section
- **Defaults are supported**: The `get_config` method returns default values when keys are not found
- **Nested keys**: Supports dot notation for accessing nested configuration values
- **Hot reload**: Can reload configuration without restarting the plugin

### Methods

#### `get_config(key: str, default: Any = None) → Any`

Get a configuration value with support for nested keys using dot notation.

**Parameters:**
- `key`: Configuration key (supports dot notation like "features.api.enabled")
- `default`: Default value if key not found

**Returns:**
- The configuration value or default

#### `get_all_config() → Dict[str, Any]`

Get all configuration values as a dictionary.

**Returns:**
- Dictionary of all configuration values

#### `reload_config() → None`

Reload configuration from `plugin.toml`.

### Example `plugin.toml`

```toml
# Optional configuration section
[plugin.config]
api_key = "your-api-key"
timeout = 30

# Optional nested configuration
[plugin.config.features]
api = true
webhook = false

[plugin.config.features.api]
enabled = true
endpoint = "https://api.example.com"
```
