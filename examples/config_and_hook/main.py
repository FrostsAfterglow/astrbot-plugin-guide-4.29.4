"""AstrBot v4.29.4 进阶插件示例：配置 + 指令组 + 权限 + LLM 钩子 + 平台 API。

配套文件：metadata.yaml、_conf_schema.json、tests/test_conf_schema.py
"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools


class AdvancedPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 4.29.4 传 AstrBotConfig（dict 子类）；旧版/测试可能不传，故做兼容
        self.config = config if isinstance(config, dict) else {}

    # ------------------------------------------------------------------ #
    # 配置读取：一律走 _conf 兜底 + 自行归一化类型
    # ------------------------------------------------------------------ #
    def _conf(self, key, default):
        if isinstance(self.config, dict) and key in self.config:
            return self.config[key]
        try:
            cfg = self.context.get_config()
            if isinstance(cfg, dict) and key in cfg:
                return cfg[key]
        except Exception:
            pass
        return default

    @property
    def enabled(self) -> bool:
        return bool(self._conf("ENABLED", True))

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def initialize(self):
        data_dir = StarTools.get_data_dir("astrbot_plugin_guide_advanced")
        self.logger.info("[guide] 数据目录: %s", data_dir)
        await self.put_kv_data("boot_count", (await self.get_kv_data("boot_count", 0)) + 1)

    async def terminate(self):
        logger.info("[guide] 已卸载")

    # ------------------------------------------------------------------ #
    # 指令组 + 权限
    # ------------------------------------------------------------------ #
    @filter.command_group("guide")
    def guide(self):
        """指令组入口，函数体无需实现。用户发 /guide 会看到指令树。"""
        pass

    @guide.command("status")
    async def status(self, event: AstrMessageEvent):
        """查看当前配置：/guide status"""
        if not self.enabled:
            yield event.plain_result("插件已停用")
            return
        lines = [
            "[指南示例] 当前配置",
            f"运行模式: {self._conf('MODE', 'normal')}",
            f"最大条数: {int(self._conf('MAX_ITEMS', 10))}",
            f"比例阈值: {float(self._conf('RATIO', 0.75))}",
            f"系统提示后缀: {self._conf('PROMPT_SUFFIX', '')}",
        ]
        yield event.plain_result("\n".join(lines))

    @guide.command("chain")
    async def chain_demo(self, event: AstrMessageEvent):
        """消息链示例：/guide chain"""
        yield event.chain_result([Plain("这是一条由 chain_result 构造的消息")])

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("guide_admin")
    async def admin_only(self, event: AstrMessageEvent):
        """仅管理员：/guide_admin"""
        yield event.plain_result("管理员指令执行成功")

    # ------------------------------------------------------------------ #
    # LLM 钩子：在请求发出前改系统提示
    # ------------------------------------------------------------------ #
    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.enabled:
            return
        suffix = str(self._conf("PROMPT_SUFFIX", "")).strip()
        if suffix and suffix not in req.system_prompt:
            req.system_prompt += "\n" + suffix

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, response):
        if self._conf("MODE", "normal") == "verbose":
            self.logger.debug("[guide] LLM 已响应")

    # ------------------------------------------------------------------ #
    # OneBot 平台 API：安全调用示例
    # ------------------------------------------------------------------ #
    @filter.command("botver")
    async def bot_version(self, event: AstrMessageEvent):
        """查询协议端版本：/botver（仅 aiocqhttp 有效）"""
        bot = getattr(event, "bot", None)
        if bot is None:
            yield event.plain_result("当前平台不提供 bot API")
            return
        try:
            ret = await bot.call_action("get_version_info")
            yield event.plain_result(f"协议端版本信息: {ret}")
        except Exception as exc:
            self.logger.warning("[guide] get_version_info 失败: %s", exc)
            yield event.plain_result("查询失败，详见日志")
