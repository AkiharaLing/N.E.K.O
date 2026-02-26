import logging
import asyncio
import json
import threading
import queue
import websockets
import time
import httpx
from pathlib import Path
from plugin.sdk.base import NekoPluginBase
from plugin.sdk.decorators import plugin_entry, lifecycle, timer_interval, message, neko_plugin
from plugin.sdk.config import PluginConfigManager


@neko_plugin
class NapCatQQPlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        
        # 启用文件日志
        self.logger = self.enable_file_logging(log_level=logging.INFO)
        
        # 创建配置管理器
        self.config_manager = PluginConfigManager(ctx.config_path, ctx.logger)
        
        # NapCat配置
        self.napcat_host = self.config_manager.get_config("napcat_host", "127.0.0.1")
        self.napcat_port = self.config_manager.get_config("napcat_port", 3001)
        self.qq_account = self.config_manager.get_config("qq_account", 0)
        self.master_qq = self.config_manager.get_config("master_qq", 0)
        
        # 验证必需配置
        self._validate_required_config()
        
        # 自动回复配置
        self.auto_reply_enabled = self.config_manager.get_config("auto_reply.enabled", True)
        self.reply_private = self.config_manager.get_config("auto_reply.reply_private", True)
        self.reply_group = self.config_manager.get_config("auto_reply.reply_group", False)
        self.reply_mention = self.config_manager.get_config("auto_reply.reply_mention", True)
        self.reply_master_only = self.config_manager.get_config("auto_reply.reply_master_only", False)
        self.max_reply_length = self.config_manager.get_config("auto_reply.max_reply_length", 500)
        self.cooldown_seconds = self.config_manager.get_config("auto_reply.cooldown_seconds", 3)
        
        # 消息冷却时间记录 {user_id: last_reply_time}
        self.reply_cooldown = {}

        # WebSocket 地址（用于双向通信）
        self.ws_url = f"ws://{self.napcat_host}:{self.napcat_port}/ws"
        # WebSocket 连接对象
        self.websocket = None
        # 状态标识
        self.ws_connected = False
        # 请求-响应映射（用于同步等待响应）
        self.pending_requests = {}
        self.request_counter = 0
        # WebSocket 线程
        self.ws_thread = None
        self.ws_loop = None
        self.ws_stop_event = None
        # 请求队列（用于跨线程通信）
        self.request_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.logger.info(f"✅ NapCatQQ 插件初始化完成，WebSocket地址：{self.ws_url}")
        # 上报初始状态
        self.report_status({
            "status": "initialized",
            "napcat_host": self.napcat_host,
            "napcat_port": self.napcat_port,
            "qq_account": self.qq_account
        })

    def _validate_required_config(self):
        """验证必需的配置项"""
        missing_configs = []
        
        if not self.napcat_host:
            missing_configs.append("napcat_host")
        if not self.napcat_port:
            missing_configs.append("napcat_port")
        if not self.qq_account:
            missing_configs.append("qq_account")
        
        if missing_configs:
            self.logger.error(f"❌ 配置缺失: {', '.join(missing_configs)}")
            self.logger.error(f"   当前配置: napcat_host={self.napcat_host}, napcat_port={self.napcat_port}, qq_account={self.qq_account}")
            self.logger.error(f"   请在 plugin.toml 中配置这些项")

    async def _ws_connect(self):
        """建立 WebSocket 连接"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.ws_connected = True
            self.report_status({"status": "ws_connected", "message": "WebSocket连接成功"})
            self.logger.info(f"🔌 WebSocket 连接成功：{self.ws_url}")
        except Exception as e:
            self.logger.error(f"❌ WebSocket 连接失败：{e}")
            self.ws_connected = False
            self.report_status({"status": "ws_disconnected", "message": str(e)})
            raise

    def _ws_send(self, data: dict, timeout: float = 10.0) -> dict:
        """通过 WebSocket 发送请求并等待响应（使用队列机制）"""
        if not self.ws_connected or not self.websocket:
            raise ConnectionError("WebSocket 未连接")

        # 生成请求 ID
        request_id = f"req_{self.request_counter}"
        self.request_counter += 1

        # 添加请求 ID
        data["echo"] = request_id

        # 创建响应等待器
        response_waiter = threading.Event()
        self.pending_requests[request_id] = response_waiter

        try:
            # 将请求放入队列（由 WebSocket 线程处理）
            self.request_queue.put({
                "type": "request",
                "data": data,
                "request_id": request_id,
                "waiter": response_waiter
            })
            self.logger.debug(f"📤 发送 WebSocket 请求：{data}")

            # 等待响应（阻塞当前线程）
            if response_waiter.wait(timeout=timeout):
                # 从响应队列获取结果
                result = None
                try:
                    result = self.response_queue.get_nowait()
                except queue.Empty:
                    pass
                return result or {"retcode": -1, "message": "未收到响应"}
            else:
                self.logger.error(f"❌ WebSocket 请求超时：{data}")
                return {"retcode": -1, "message": "请求超时"}
        except Exception as e:
            self.logger.error(f"❌ WebSocket 请求失败：{e}")
            return {"retcode": -1, "message": str(e)}
        finally:
            # 清理请求
            self.pending_requests.pop(request_id, None)

    def _ws_listen(self):
        """WebSocket 实时监听 QQ 消息（在线程中运行）"""
        self.logger.info(f"🔌 开始连接 WebSocket：{self.ws_url}")
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)

        # 持续重连循环
        while not self.ws_stop_event.is_set():
            try:
                self.ws_loop.run_until_complete(self._async_ws_listen())
            except Exception as e:
                self.logger.error(f"❌ WebSocket 监听异常：{e}")
                self.ws_connected = False
                self.report_status({"status": "ws_disconnected", "message": str(e)})
                # 等待后重连
                if not self.ws_stop_event.is_set():
                    self.logger.info("🔄 5秒后尝试重新连接 WebSocket...")
                    self.ws_stop_event.wait(5)

    async def _async_ws_listen(self):
        """异步 WebSocket 监听"""
        try:
            await self._ws_connect()

            while not self.ws_stop_event.is_set():
                # 处理请求队列中的请求
                try:
                    while not self.request_queue.empty():
                        req = self.request_queue.get_nowait()
                        if req.get("type") == "request":
                            # 发送请求到 WebSocket
                            await self.websocket.send(json.dumps(req["data"], ensure_ascii=False))
                            self.logger.debug(f"📤 发送 WebSocket 请求：{req['data']}")
                except queue.Empty:
                    pass

                # 接收消息（带超时）
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=0.1
                    )
                    msg_data = json.loads(message)
                    self.logger.debug(f"📥 收到 WebSocket 消息：{json.dumps(msg_data, ensure_ascii=False)}")

                    # 检查是否为响应消息
                    echo = msg_data.get("echo")
                    if echo and echo in self.pending_requests:
                        # 响应消息，唤醒等待的请求
                        waiter = self.pending_requests.pop(echo)
                        # 将响应放入响应队列
                        self.response_queue.put(msg_data)
                        if not waiter.is_set():
                            waiter.set()
                        continue

                    # 处理事件消息
                    if msg_data.get("post_type") == "message":
                        # 提取消息内容（处理 NapCat 的消息格式）
                        raw_content = msg_data.get("content", "")
                        raw_message = msg_data.get("message", [])
                        
                        # 如果 content 为空，尝试从 message 数组中提取文本
                        if not raw_content and raw_message:
                            text_parts = []
                            for msg_item in raw_message:
                                if msg_item.get("type") == "text":
                                    text_parts.append(msg_item.get("data", {}).get("text", ""))
                            raw_content = "".join(text_parts)
                        
                        # 判断是否是主人
                        sender_id = msg_data.get("user_id")
                        is_master = (self.master_qq != 0 and sender_id == self.master_qq)
                        
                        # 构造标准化消息结构
                        neko_msg = {
                            "type": "qq_message",
                            "source": f"qq_{self.qq_account}",
                            "sender": {
                                "id": sender_id,
                                "nickname": msg_data.get("sender", {}).get("nickname", ""),
                            },
                            "content": raw_content,
                            "message_type": msg_data.get("message_type"),  # private/group
                            "target_id": msg_data.get("group_id") or msg_data.get("user_id"),
                            "timestamp": msg_data.get("time"),
                            "is_master": is_master,
                            "raw": msg_data
                        }
                        # 自动回复处理
                        await self._handle_auto_reply(msg_data, neko_msg)
                        
                        # 推送到 N.E.K.O 主系统
                        self.ctx.push_message(
                            source=self._plugin_id,
                            message_type="qq",
                            description="QQ消息接收",
                            priority=1,
                            content=neko_msg,
                        )
                except asyncio.TimeoutError:
                    # 超时是正常的，继续循环
                    continue
        except Exception as e:
            self.logger.error(f"❌ WebSocket 连接异常：{e}")
            self.ws_connected = False
            self.report_status({"status": "ws_disconnected", "message": str(e)})
            # 尝试重连
            await asyncio.sleep(5)
            self.logger.info("🔄 尝试重新连接 WebSocket...")

    async def _handle_auto_reply(self, msg_data: dict, neko_msg: dict):
        """处理自动回复
        
        Args:
            msg_data: 原始 NapCat 消息数据
            neko_msg: 标准化的消息结构
        """
        if not self.auto_reply_enabled:
            return
        
        message_type = msg_data.get("message_type")
        content = neko_msg.get("content", "")
        sender_id = msg_data.get("user_id")
        sender_name = msg_data.get("sender", {}).get("nickname", "")
        group_id = msg_data.get("group_id")
        is_master = neko_msg.get("is_master", False)
        
        # 检查是否应该回复
        should_reply = False
        
        # 如果启用了仅回复主人模式，非主人消息直接跳过
        if self.reply_master_only and not is_master:
            self.logger.debug(f"🔒 仅回复主人模式已启用，跳过非主人消息: sender_id={sender_id}")
            return
        
        if message_type == "private" and self.reply_private:
            should_reply = True
        elif message_type == "group" and self.reply_group:
            # 群聊模式：检查是否@了机器人
            if self.reply_mention:
                # 检查消息中是否包含机器人的QQ号（@格式）
                bot_mention = f"[CQ:at,qq={self.qq_account}]"
                if bot_mention in content:
                    should_reply = True
                    # 去除@标记，只保留实际消息内容
                    content = content.replace(bot_mention, "").strip()
            else:
                should_reply = True
        
        if not should_reply:
            return
        
        # 检查冷却时间
        current_time = time.time()
        last_reply_time = self.reply_cooldown.get(sender_id, 0)
        if current_time - last_reply_time < self.cooldown_seconds:
            self.logger.debug(f"⏰ 消息冷却中，跳过回复: sender_id={sender_id}")
            return
        
        # 更新冷却时间
        self.reply_cooldown[sender_id] = current_time
        
        # 过滤空消息
        if not content or not content.strip():
            return
        
        self.logger.info(f"🤖 触发自动回复: sender={sender_name}({sender_id}), type={message_type}, is_master={is_master}, content={content[:50]}")
        
        # 触发 AI 处理
        try:
            await self._trigger_ai_reply(
                message=content,
                sender_id=sender_id,
                sender_name=sender_name,
                message_type=message_type,
                target_id=group_id or sender_id,
                is_master=is_master
            )
        except Exception as e:
            self.logger.error(f"❌ 触发 AI 回复失败: {e}")
    
    async def _trigger_ai_reply(
        self,
        message: str,
        sender_id: int,
        sender_name: str,
        message_type: str,
        target_id: int,
        is_master: bool = False
    ):
        """触发 AI 回复
        
        Args:
            message: 消息内容
            sender_id: 发送者ID
            sender_name: 发送者昵称
            message_type: 消息类型（private/group）
            target_id: 目标ID（群号或QQ号）
            is_master: 是否是主人
        """
        try:
            # 构造元数据
            metadata = {
                "sender_id": str(sender_id),
                "sender_name": sender_name,
                "message_type": message_type,
                "target_id": str(target_id),
                "is_master": is_master
            }
            
            # 构造上下文提示（插件自行决定如何构造）
            if message_type == "group":
                if is_master:
                    context_prompt = f"[来自群聊的消息（主人）] 发送者: {sender_name}\n消息内容: {message}"
                else:
                    context_prompt = f"[来自群聊的消息] 发送者: {sender_name}\n消息内容: {message}"
            elif message_type == "private":
                if is_master:
                    context_prompt = f"[来自私聊的消息（主人）] 发送者: {sender_name}\n消息内容: {message}"
                else:
                    context_prompt = f"[来自私聊的消息] 发送者: {sender_name}\n消息内容: {message}"
            else:
                if is_master:
                    context_prompt = f"[主人消息] 发送者: {sender_name}\n消息内容: {message}"
                else:
                    context_prompt = message
            
            # 调用主系统的 AI 回复接口
            from config import MAIN_SERVER_PORT
            
            url = f"http://127.0.0.1:{MAIN_SERVER_PORT}/plugin/ai_reply"
            payload = {
                "plugin_id": self._plugin_id,
                "message": context_prompt,
                "metadata": metadata
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        self.logger.info(f"✅ AI 处理已触发: message={message[:50]}")
                    else:
                        self.logger.warning(f"⚠️ AI 处理触发失败: {result.get('error')}")
                else:
                    self.logger.warning(f"⚠️ AI 处理触发 HTTP 错误: {response.status_code}")
                    
        except Exception as e:
            self.logger.error(f"❌ 触发 AI 回复异常: {e}")
    # ========== 对外暴露的插件入口 ==========
    @plugin_entry(
        id="send_qq_message",
        name="发送QQ消息",
        description="通过 NapCatQQ 发送消息到 QQ 好友或群聊。必须提供三个参数：target_type(消息类型)、target_id(目标QQ号/群号)、content(消息内容)。示例：发送给好友需要 target_type='private' 和 target_id=123456789；发送到群聊需要 target_type='group' 和 target_id=987654321。",
        input_schema={
            "type": "object",
            "properties": {
                "target_type": {
                    "type": "string",
                    "enum": ["private", "group"],
                    "description": "消息类型，必须是 'private'（发送给好友）或 'group'（发送到群聊）"
                },
                "target_id": {
                    "type": "integer",
                    "description": "目标QQ号（当 target_type='private' 时）或群号（当 target_type='group' 时），必须是数字"
                },
                "content": {
                    "type": "string",
                    "description": "要发送的消息文本内容"
                }
            },
            "required": ["target_type", "target_id", "content"]
        },
        kind="action",
        auto_start=False
    )
    def send_qq_message(self, target_type: str, target_id: int, content: str, **kwargs):
        """发送 QQ 消息（通过 WebSocket）"""
        self.logger.info(f"📤 准备发送 QQ 消息：{target_type} {target_id} -> {content}")

        # 构造请求参数
        params = {
            "message": content,
            "auto_escape": False
        }
        if target_type == "private":
            params["user_id"] = target_id
            action = "send_private_msg"
        else:
            params["group_id"] = target_id
            action = "send_group_msg"

        # NapCat WebSocket API 格式：action + params
        data = {
            "action": action,
            "params": params
        }

        # 通过 WebSocket 发送请求
        result = self._ws_send(data)

        if result.get("retcode") == 0:
            self.logger.info(f"✅ 消息发送成功：{content}")
            self.report_status({
                "status": "message_sent",
                "target_type": target_type,
                "target_id": target_id,
                "content": content
            })
        else:
            self.logger.error(f"❌ 消息发送失败：{result}")

        return result

    @plugin_entry(
        id="get_friend_list",
        name="获取好友列表",
        description="获取当前登录 QQ 账号的所有好友列表，返回好友的详细信息（包括QQ号、昵称等）。不需要任何参数。",
        input_schema={},
        kind="action",
        auto_start=False
    )
    def get_friend_list(self, **kwargs):
        """获取 QQ 好友列表（通过 WebSocket）"""
        data = {
            "action": "get_friend_list",
            "params": {}
        }
        result = self._ws_send(data)

        if result.get("retcode") == 0:
            self.logger.info(f"✅ 获取好友列表成功，共{len(result.get('data', []))}个好友")
            self.report_status({"status": "friend_list_fetched", "count": len(result.get('data', []))})

        return result

    @plugin_entry(
        id="get_group_list",
        name="获取群列表",
        description="获取当前登录 QQ 账号的所有群聊列表，返回群聊的详细信息（包括群号、群名称等）。不需要任何参数。",
        input_schema={},
        kind="action",
        auto_start=False
    )
    def get_group_list(self, **kwargs):
        """获取 QQ 群列表（通过 WebSocket）"""
        data = {
            "action": "get_group_list",
            "params": {}
        }
        result = self._ws_send(data)

        if result.get("retcode") == 0:
            self.logger.info(f"✅ 获取群列表成功，共{len(result.get('data', []))}个群聊")
            self.report_status({"status": "group_list_fetched", "count": len(result.get('data', []))})

        return result

    # ========== 生命周期钩子 ==========
    @lifecycle(id="startup", name="插件启动", description="启动 WebSocket 监听")
    def on_startup(self):
        """插件启动时启动 WebSocket 监听（在线程中运行）"""
        self.logger.info("🚀 插件启动，开始连接 NapCatQQ WebSocket")
        # 创建停止事件
        self.ws_stop_event = threading.Event()
        # 在独立线程中运行 WebSocket 监听
        self.ws_thread = threading.Thread(
            target=self._ws_listen,
            daemon=True,
            name=f"napcat_qq_ws_{self.qq_account}"
        )
        self.ws_thread.start()
        self.report_status({"status": "started", "ws_thread_created": True})

    @lifecycle(id="shutdown", name="插件关闭", description="关闭 WebSocket 监听")
    def on_shutdown(self):
        """插件关闭时清理资源"""
        self.logger.info("🔌 插件关闭，清理 WebSocket 连接")
        # 停止 WebSocket 线程
        if self.ws_stop_event:
            self.ws_stop_event.set()
        # 关闭 WebSocket 连接
        if self.ws_loop and self.ws_loop.is_running():
            self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
        # 等待线程结束
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)
        self.ws_connected = False
        self.report_status({"status": "stopped", "ws_connected": False})

    # ========== 定时心跳检测 ==========
    @timer_interval(id="heartbeat", seconds=3600, name="NapCatQQ心跳检测", auto_start=True)
    def napcat_heartbeat(self):
        """定时检测 NapCatQQ 服务是否可用（通过 WebSocket）"""
        # 如果 WebSocket 未连接，跳过心跳检测
        if not self.ws_connected:
            self.logger.debug("WebSocket 未连接，跳过心跳检测")
            self.report_status({"status": "disconnected", "napcat_status": "offline"})
            return

        try:
            data = {
                "action": "get_status",
                "params": {}
            }
            result = self._ws_send(data)

            if result.get("retcode") == 0:
                self.logger.debug("NapCatQQ 服务链接正常")
                self.report_status({"status": "alive", "napcat_status": "online"})
            else:
                self.logger.warning("NapCatQQ 服务链接失败")
                self.report_status({"status": "warning", "napcat_status": "offline"})
        except Exception as e:
            self.logger.warning(f"心跳检测失败：{e}")
            self.report_status({"status": "warning", "napcat_status": "offline"})
    
    # ========== 消息处理器 ==========
    @message(
        id="handle_ai_reply",
        name="处理AI回复",
        description="处理来自主系统的 AI 回复并发送到 QQ",
        input_schema={
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "source": {"type": "string"},
                "reply": {"type": "string"},
                "metadata": {"type": "object"}
            }
        },
        source="main_system"
    )
    def handle_ai_reply(self, type: str, source: str, reply: str, metadata: dict = None, **_):
        """处理 AI 回复并发送到 QQ"""
        if not reply or not reply.strip():
            self.logger.warning("⚠️ 收到空回复，跳过发送")
            return {"success": False, "error": "空回复"}
        
        metadata = metadata or {}
        message_type = metadata.get("message_type", "private")
        target_id = int(metadata.get("target_id", 0))
        
        if not target_id:
            self.logger.error("❌ 缺少目标ID，无法发送回复")
            return {"success": False, "error": "缺少目标ID"}
        
        # 截断过长的回复
        if len(reply) > self.max_reply_length:
            reply = reply[:self.max_reply_length] + "..."
            self.logger.warning(f"⚠️ 回复过长，已截断到 {self.max_reply_length} 字符")
        
        # 发送回复
        result = self.send_qq_message(
            target_type=message_type,
            target_id=target_id,
            content=reply
        )
        
        if result.get("retcode") == 0:
            self.logger.info(f"✅ AI 回复已发送: {reply[:50]}...")
            return {"success": True, "sent": True}
        else:
            self.logger.error(f"❌ AI 回复发送失败: {result}")
            return {"success": False, "error": result.get("message", "发送失败")}
