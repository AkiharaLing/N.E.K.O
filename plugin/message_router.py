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
    message_type_filter: Optional[str] = None


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
        self._ai_reply_callback: Optional[Callable] = None
    
    def register_handler(
        self,
        plugin_id: str,
        handler_func: Callable,
        message_type_filter: Optional[str] = None
    ) -> None:
        """注册消息处理器
        
        Args:
            plugin_id: 插件 ID
            handler_func: 处理函数，签名为 async def handler(message: dict) -> None
            message_type_filter: 消息类型过滤器（可选）
        """
        self._handlers[plugin_id] = MessageHandler(
            plugin_id=plugin_id,
            handler_func=handler_func,
            message_type_filter=message_type_filter
        )
        logger.info(f"✅ 已注册消息处理器: plugin_id={plugin_id}, message_type={message_type_filter}")
    
    def unregister_handler(self, plugin_id: str) -> None:
        """取消注册消息处理器"""
        if plugin_id in self._handlers:
            del self._handlers[plugin_id]
            logger.info(f"🗑️ 已取消注册消息处理器: plugin_id={plugin_id}")
    
    def set_ai_reply_callback(self, callback: Callable) -> None:
        """设置 AI 回复回调函数
        
        Args:
            callback: 回调函数，签名为 async def callback(plugin_id: str, reply: str, metadata: dict) -> None
        """
        self._ai_reply_callback = callback
        logger.info("✅ 已设置 AI 回复回调")
    
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
        
        logger.info(f"📨 处理消息: msg_type={msg_type}, source={source}")
        
        # 处理来自主系统的 AI 回复消息
        if source == "main_system" and isinstance(content, dict):
            content_source = content.get("source", "")
            logger.info(f"🤖 检测到AI回复消息: content_source={content_source}")
            if content_source:
                # 将 AI 回复发送到目标插件的 cmd_queue
                await self._send_message_to_plugin(content_source, msg)
                return
        
        # 处理插件推送的消息
        if msg_type != "MESSAGE_PUSH":
            return
        
        plugin_id = msg.get("plugin_id")
        if not plugin_id:
            return
        
        message_type = msg.get("message_type")
        metadata = msg.get("metadata", {})
        
        logger.debug(
            f"📨 收到插件消息: plugin_id={plugin_id}, "
            f"source={source}, message_type={message_type}, "
            f"content={str(content)[:100]}"
        )
        
        handler = self._handlers.get(plugin_id)
        if not handler:
            logger.debug(f"⚠️ 未找到插件 {plugin_id} 的消息处理器")
            return
        
        if handler.message_type_filter and message_type != handler.message_type_filter:
            logger.debug(f"⚠️ 消息类型不匹配: {message_type} != {handler.message_type_filter}")
            return
        
        try:
            await handler.handler_func(msg)
        except Exception as e:
            logger.exception(f"❌ 消息处理器执行失败: plugin_id={plugin_id}, error={e}")
    
    async def _send_message_to_plugin(self, plugin_id: str, msg: Dict[str, Any]) -> None:
        """将消息发送到插件的 cmd_queue
        
        Args:
            plugin_id: 目标插件 ID
            msg: 消息字典
        """
        from plugin.core.state import state
        
        logger.info(f"📤 准备发送消息到插件: plugin_id={plugin_id}")
        
        host = state.plugin_hosts.get(plugin_id)
        if not host:
            logger.warning(f"⚠️ 插件 {plugin_id} 未注册，无法发送消息")
            return
        
        if not host.is_alive():
            logger.warning(f"⚠️ 插件 {plugin_id} 进程未运行，无法发送消息")
            return
        
        try:
            await host.send_message(
                source=msg.get("source", ""),
                content=msg.get("content", {})
            )
            logger.info(f"✅ 消息已发送到插件 {plugin_id}")
        except Exception as e:
            logger.exception(f"❌ 发送消息到插件 {plugin_id} 失败: {e}")
    
    async def send_ai_reply(
        self,
        plugin_id: str,
        reply: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """发送 AI 回复到插件（泛化接口）
        
        Args:
            plugin_id: 目标插件 ID
            reply: AI 回复内容
            metadata: 额外的元数据
        
        Returns:
            bool: 是否发送成功
        """
        if not self._ai_reply_callback:
            logger.warning("⚠️ AI 回复回调未设置，无法发送回复")
            return False
        
        try:
            await self._ai_reply_callback(plugin_id, reply, metadata or {})
            logger.info(f"✅ AI 回复已发送到插件: plugin_id={plugin_id}, reply={reply[:50]}...")
            return True
        except Exception as e:
            logger.exception(f"❌ 发送 AI 回复失败: plugin_id={plugin_id}, error={e}")
            return False
    
    async def trigger_ai_processing(
        self,
        plugin_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """触发 AI 处理插件消息（通过 HTTP API）
        
        Args:
            plugin_id: 插件 ID
            message: 消息内容
            metadata: 额外的元数据
        
        Returns:
            bool: 是否成功触发
        """
        try:
            import httpx
            from config import MAIN_SERVER_PORT
            
            url = f"http://127.0.0.1:{MAIN_SERVER_PORT}/plugin/ai_reply"
            payload = {
                "plugin_id": plugin_id,
                "message": message,
                "metadata": metadata or {}
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        logger.info(f"✅ AI 处理已触发: plugin_id={plugin_id}")
                        return True
                    else:
                        logger.warning(f"⚠️ AI 处理触发失败: {result.get('error')}")
                        return False
                else:
                    logger.warning(f"⚠️ AI 处理触发 HTTP 错误: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.exception(f"❌ 触发 AI 处理失败: plugin_id={plugin_id}, error={e}")
            return False


# 全局单例
_router: Optional[PluginMessageRouter] = None


def get_message_router() -> PluginMessageRouter:
    """获取全局消息路由器实例"""
    global _router
    if _router is None:
        _router = PluginMessageRouter()
    return _router
