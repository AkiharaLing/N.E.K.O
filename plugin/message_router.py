"""
插件消息路由器

负责消费插件推送的消息，并根据消息类型路由到相应的处理器。
支持泛化的消息处理和 AI 回复接口。
"""
import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

from plugin.core.state import state

logger = logging.getLogger("plugin_message_router")


@dataclass
class MessageHandler:
    """消息处理器"""
    plugin_id: str
    handler_func: Callable


class PluginMessageRouter:
    """插件消息路由器
    
    职责：
    1. 持续消费 state.message_queue 中的消息
    2. 根据消息类型和插件 ID 路由到相应的处理器
    3. 提供泛化的 AI 回复发送接口
    """
    
    def __init__(self):
        self._handlers: Dict[str, MessageHandler] = {}
        self._consumer_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None
    
    def register_handler(
        self,
        plugin_id: str,
        handler_func: Callable
    ) -> None:
        """注册消息处理器
        
        Args:
            plugin_id: 插件 ID
            handler_func: 处理函数，签名为 async def handler(message: dict) -> None
        """
        self._handlers[plugin_id] = MessageHandler(
            plugin_id=plugin_id,
            handler_func=handler_func
        )
        logger.info(f"✅ 已注册消息处理器: plugin_id={plugin_id}")
    
    def unregister_handler(self, plugin_id: str) -> None:
        """取消注册消息处理器"""
        if plugin_id in self._handlers:
            del self._handlers[plugin_id]
            logger.info(f"🗑️ 已取消注册消息处理器: plugin_id={plugin_id}")
    
    async def start(self) -> None:
        """启动消息消费后台任务"""
        if self._consumer_task is None or self._consumer_task.done():
            self._shutdown_event = asyncio.Event()
            self._consumer_task = asyncio.create_task(self._consume_messages())
            logger.info("🚀 插件消息路由器已启动")
    
    async def stop(self) -> None:
        """停止消息消费后台任务"""
        if self._shutdown_event:
            self._shutdown_event.set()
        
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 插件消息路由器已停止")
    
    async def _consume_messages(self) -> None:
        """持续消费消息队列"""
        while not self._shutdown_event.is_set():
            try:
                msg = await asyncio.wait_for(
                    state.message_queue.get(),
                    timeout=1.0
                )
                await self._process_message(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"❌ 处理插件消息时出错: {e}")
    
    async def _process_message(self, msg: Dict[str, Any]) -> None:
        """处理单条消息
        
        Args:
            msg: 消息字典，格式为：
                {
                    "type": "MESSAGE_PUSH",
                    "plugin_id": "xxx",
                    "source": "xxx",
                    "message_type": "xxx",
                    "description": "xxx",
                    "priority": 0,
                    "content": "...",
                    "metadata": {},
                    "time": "..."
                }
        """
        msg_type = msg.get("type")
        source = msg.get("source", "")
        content = msg.get("content")
        
        # 处理插件推送的消息
        if msg_type != "MESSAGE_PUSH":
            return
        
        plugin_id = msg.get("plugin_id")
        if not plugin_id:
            # 如果没有plugin_id，尝试从content中提取（AI回复消息）
            if isinstance(content, dict):
                plugin_id = content.get("source", "")
            if not plugin_id:
                logger.debug("⚠️ 消息缺少 plugin_id")
                return
        
        message_type = msg.get("message_type")
        metadata = msg.get("metadata", {})
        
        # 发送消息到插件进程
        await self._send_message_to_plugin(plugin_id, msg)
    
    async def _send_message_to_plugin(self, plugin_id: str, msg: Dict[str, Any]) -> None:
        """将消息发送到插件的 cmd_queue
        
        Args:
            plugin_id: 目标插件 ID
            msg: 消息字典
        """
        from plugin.core.state import state
        
        host = state.plugin_hosts.get(plugin_id)
        if not host:
            logger.warning(f"⚠️ 插件 {plugin_id} 未注册，无法发送消息")
            return
        
        if not host.is_alive():
            logger.warning(f"⚠️ 插件 {plugin_id} 进程未运行，无法发送消息")
            return
        
        try:
            # 发送完整的消息对象到插件
            await host.send_message(
                source=msg.get("source", ""),
                content=msg
            )
        except Exception as e:
            logger.exception(f"❌ 发送消息到插件 {plugin_id} 失败: {e}")


# 全局单例
_router: Optional[PluginMessageRouter] = None


def get_message_router() -> PluginMessageRouter:
    """获取全局消息路由器实例"""
    global _router
    if _router is None:
        _router = PluginMessageRouter()
    return _router
