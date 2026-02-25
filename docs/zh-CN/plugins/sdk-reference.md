# SDK 参考

## NekoPluginBase

所有插件必须继承 `NekoPluginBase`。

```python
from plugin.sdk.base import NekoPluginBase

class MyPlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
```

### 方法

#### `get_input_schema() → dict`

返回插件的输入 JSON Schema。默认从类属性中读取。可重写以实现动态 Schema。

#### `report_status(status: dict) → None`

向主进程报告插件状态。

```python
self.report_status({
    "status": "running",
    "progress": 50,
    "message": "Processing..."
})
```

#### `collect_entries() → dict`

收集所有入口点（使用 `@plugin_entry` 装饰的方法）。由系统自动调用。

## PluginContext

传递给插件构造函数的 `ctx` 对象。

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `ctx.plugin_id` | `str` | 插件标识符 |
| `ctx.config_path` | `Path` | `plugin.toml` 的路径 |
| `ctx.logger` | `Logger` | 日志记录器实例 |

### 方法

#### `ctx.update_status(status: dict) → None`

在主进程中更新插件状态。

#### `ctx.push_message(...) → None`

向主系统推送消息。

```python
ctx.push_message(
    source="my_feature",          # 消息来源标识符
    message_type="text",          # "text" | "url" | "binary" | "binary_url"
    description="Task complete",  # 人类可读的描述
    priority=5,                   # 0-10（0=低，10=紧急）
    content="Result text",        # 用于 text/url 类型
    binary_data=b"...",           # 用于 binary 类型
    binary_url="https://...",     # 用于 binary_url 类型
    metadata={"key": "value"}    # 附加元数据
)
```

### 消息类型

| 类型 | 使用场景 |
|------|----------|
| `text` | 纯文本消息 |
| `url` | URL 链接 |
| `binary` | 小型二进制数据（直接传输） |
| `binary_url` | 大文件（通过 URL 引用） |

### 优先级等级

| 范围 | 等级 | 使用场景 |
|------|------|----------|
| 0-2 | 低 | 信息性消息 |
| 3-5 | 中 | 一般通知 |
| 6-8 | 高 | 重要通知 |
| 9-10 | 紧急 | 需要立即处理 |

## PluginConfigManager

用于从 `plugin.toml` 加载和访问插件配置的工具。

### 使用方法

```python
from plugin.sdk.config import PluginConfigManager

# 在插件 __init__ 中
def __init__(self, ctx):
    super().__init__(ctx)
    self.config_manager = PluginConfigManager(ctx.config_path, ctx.logger)
    
    # 获取配置值（带默认值）
    # 如果没有 [plugin.config] 部分，这些会返回默认值
    self.api_key = self.config_manager.get_config("api_key", "")
    self.timeout = self.config_manager.get_config("timeout", 30)
    self.feature_enabled = self.config_manager.get_config("features.my_feature", False)
```

### 关键点

- **配置是可选的**：插件可以在没有任何 `[plugin.config]` 部分的情况下工作
- **支持默认值**：`get_config` 方法在键不存在时返回默认值
- **嵌套键**：支持使用点表示法访问嵌套的配置值
- **热重载**：可以在不重启插件的情况下重新加载配置

### 方法

#### `get_config(key: str, default: Any = None) → Any`

获取配置值，支持使用点表示法访问嵌套键。

**参数：**
- `key`：配置键（支持点表示法，如 "features.api.enabled"）
- `default`：键不存在时的默认值

**返回：**
- 配置值或默认值

#### `get_all_config() → Dict[str, Any]`

获取所有配置值作为字典。

**返回：**
- 所有配置值的字典

#### `reload_config() → None`

从 `plugin.toml` 重新加载配置。

### 示例 `plugin.toml`

```toml
# 可选的配置部分
[plugin.config]
api_key = "your-api-key"
timeout = 30

# 可选的嵌套配置
[plugin.config.features]
api = true
webhook = false

[plugin.config.features.api]
enabled = true
endpoint = "https://api.example.com"
```
