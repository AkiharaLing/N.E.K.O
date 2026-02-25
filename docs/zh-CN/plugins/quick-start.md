# 插件快速开始

## 第一步：创建插件目录

```bash
mkdir -p plugin/plugins/hello_world
```

## 第二步：创建 `plugin.toml`

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

### 配置字段

| 字段 | 是否必需 | 说明 |
|------|----------|------|
| `id` | 是 | 唯一插件标识符 |
| `name` | 否 | 显示名称 |
| `description` | 否 | 插件描述 |
| `version` | 否 | 插件版本 |
| `entry` | 是 | 入口点：`module_path:ClassName` |

### SDK 版本字段

| 字段 | 说明 |
|------|------|
| `recommended` | 推荐的 SDK 版本范围 |
| `supported` | 最低支持范围（不满足则拒绝加载） |
| `untested` | 允许但加载时会发出警告 |
| `conflicts` | 拒绝的版本范围 |

## 第三步：创建 `__init__.py`

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
        # Use configured prefix if provided
        if not name or name == "World":
            name = self.default_name
        
        message = f"{self.greeting_prefix}, {name}!"
        self.logger.info(f"Greeting: {message}")
        return {
            "message": message
        }
```

## 第四步：添加配置（可选）

**注意：配置完全是可选的。** 插件可以在没有任何自定义配置的情况下工作。

如果你想添加自定义配置，创建带有配置部分的 `plugin.toml` 文件：

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

### 配置是可选的

插件可以在没有任何 `[plugin.config]` 部分的情况下运行。当配置键不存在时，`PluginConfigManager` 会简单地返回默认值。

## 第五步：测试

启动插件服务器后，通过 HTTP 调用你的插件：

```bash
curl -X POST http://localhost:48916/plugin/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "plugin_id": "hello_world",
    "entry_id": "greet",
    "args": {"name": "N.E.K.O"}
  }'
```

## 下一步

- [SDK 参考](./sdk-reference) — 了解 `NekoPluginBase` 和 `PluginContext`
- [装饰器](./decorators) — 所有可用的装饰器类型
- [示例](./examples) — 完整的可运行插件示例
