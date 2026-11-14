"""AstrBot v4.29.4 最小插件示例。

要点（与 4.29.4 源码一致）：
- 不使用已废弃的 @register 装饰器，继承 Star 即被自动识别。
- __init__ 接 (context, config=None)，并调用 super().__init__(context)。
- 处理函数是插件类里的 async def，前两个参数 self, event。
- 用 yield event.xxx_result(...) 返回结果。
- 日志用 astrbot.api.logger / self.logger。
"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class HelloPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}

    async def initialize(self):
        """插件加载完成后调用（异步）。"""
        self.logger.info("[hello] 初始化完成")

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """打招呼：/hello"""
        user_name = event.get_sender_name()
        logger.info("[hello] 收到来自 %s 的指令", user_name)
        yield event.plain_result(f"你好，{user_name}！")

    @filter.command("echo")
    async def echo(self, event: AstrMessageEvent, message: str):
        """复读：/echo <内容>（参数靠类型注解解析）"""
        yield event.plain_result(f"你发了: {message}")

    @filter.command("add")
    async def add(self, event: AstrMessageEvent, a: int, b: int):
        """加法：/add 1 2"""
        yield event.plain_result(f"结果是: {a + b}")

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_private(self, event: AstrMessageEvent):
        """私聊消息监听示例；注意它会收到所有私聊消息。"""
        self.logger.debug("[hello] 私聊: %s", event.get_message_str())

    async def terminate(self):
        """插件卸载 / 停用 / 重载前调用（异步）。"""
        logger.info("[hello] 已卸载")
