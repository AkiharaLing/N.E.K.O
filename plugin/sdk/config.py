"""
插件配置管理模块

提供统一的插件配置获取方法。
"""
from typing import Any, Dict, Optional
import toml


class PluginConfigManager:
    """插件配置管理器"""
    
    def __init__(self, config_path, logger):
        self.config_path = config_path
        self.logger = logger
        self._config_cache: Optional[Dict[str, Any]] = None
    
    def _load_config(self) -> Dict[str, Any]:
        """加载插件配置文件"""
        if self._config_cache is not None:
            return self._config_cache
        
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = toml.load(f)
                    self._config_cache = config_data.get('plugin', {}).get('config', {})
                    return self._config_cache
            else:
                self.logger.warning(f"Plugin config file not found: {self.config_path}")
                return {}
        except Exception as e:
            self.logger.error(f"Failed to load plugin config: {e}")
            return {}
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取插件配置项
        
        Args:
            key: 配置键，支持点号分隔的嵌套键，如 "auto_reply.enabled"
            default: 默认值，当配置不存在时返回
            
        Returns:
            配置值或默认值
            
        使用示例:
            ```python
            # 获取顶层配置
            napcat_host = config_manager.get_config("napcat_host", "127.0.0.1")
            
            # 获取嵌套配置
            enabled = config_manager.get_config("auto_reply.enabled", True)
            cooldown = config_manager.get_config("auto_reply.cooldown_seconds", 3)
            ```
        """
        config = self._load_config()
        
        # 支持点号分隔的嵌套键
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        获取所有插件配置
        
        Returns:
            完整的配置字典
        """
        return self._load_config()
    
    def reload_config(self) -> Dict[str, Any]:
        """
        重新加载插件配置
        
        Returns:
            重新加载后的配置字典
        """
        self._config_cache = None
        return self._load_config()
