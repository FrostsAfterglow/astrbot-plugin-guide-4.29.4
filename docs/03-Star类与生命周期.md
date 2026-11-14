# 03 Star 类与生命周期

## 继承与实例化

所有插件继承 `Star`（`astrbot.api.star.Star` → `astrbot.core.star.base.Star`）。`Star` 同时混入 `CommandParserMixin` 和 `PluginKVStoreMixin`。

源码 `star_manager.load()` 的实例化逻辑（约 1222–1240 行）：

```python
# 注入类属性，便于 __init__ 读取
setattr(star_cls_type, "name", p_name)
setattr(star_cls_type, "author", p_author)
setattr(star_cls_type, "plugin_id", plugin_id)

if plugin_config and star_cls_type:
    try:
        star_cls = star_cls_type(context=self.context, config=plugin_config)
    except TypeError:
        star_cls = star_cls_type(context=self.context)   # 回退
elif star_cls_type:
    star_cls = star_cls_type(context=self.context)
```

三个推论：

1. **`config` 是关键字参数**，类型 `AstrBotConfig`（dict 子类）；有 `_conf_schema.json` 才非空。
2. 写 `def __init__(self, context)` 也能加载（走回退），但读不到配置。
3. 类名任意、不需要 `@register`；`Star.__init_subclass__` 自动登记到 `star_map`。

## 标准构造函数

```python
from astrbot.api.star import Context, Star


class MyPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)      # 必须！否则没有 self.context / self.logger
        self.config = config if isinstance(config, dict) else {}
        # 其他初始化：读配置、建缓存、创建后台任务等
```

`super().__init__(context)` 做两件事（`core/star/base.py`）：

- `self.context = context`
- 从 `star_map` 解析插件名，绑定**插件专属 logger** 到 `self.logger`（`astrbot.plugin.<plugin_name>`，级别可在 WebUI 单独设置）

> 若插件类把 `logger` 定义成只读 property，`Star.__init__` 会捕获 `AttributeError` 并保留你自己的实现。

## 生命周期钩子

| 方法 | 触发时机 | 是否异步 |
|---|---|---|
| `__init__` | 插件实例化 | 同步 |
| `initialize()` | 插件加载完成后 | **async**，源码 `star_manager.py:1424` 处 `await metadata.star_cls.initialize()` |
| `terminate()` | 插件卸载 / 停用 / 重载前 | **async**，源码 `~1966` 处 `await star_metadata.star_cls.terminate()` |
| `__del__` | 对象析构（`Star` 基类有定义） | 同步 |

```python
class MyPlugin(Star):
    async def initialize(self):
        """适合：建表、恢复缓存、启动后台任务、注册 Web API"""
        self.logger.info("[myplugin] 初始化完成")

    async def terminate(self):
        """适合：取消任务、关闭连接、flush 数据"""
        ...
```

> 不要用 `initialize` 做重活阻塞加载；可用 `self.context.register_task(awaitable, desc)` 托管后台协程。

## self.logger 与全局 logger

两种写法都正确：

```python
from astrbot.api import logger          # 代理对象，按调用模块自动路由到插件 logger
logger.info("...")

self.logger.info("...")                  # 插件专属，推荐
```

`astrbot.api.logger` 是 `_PluginContextLogger` 代理（源码 `api/__init__.py`），会根据调用者的 `__name__` 在 `star_map` 里找对应插件的 logger；非插件调用者回退到全局 `astrbot` logger。**不要用 `logging.getLogger(...)`**，否则失去 WebUI 的按插件级别控制。

## 内置工具方法（Star 基类）

| 方法 | 用途 |
|---|---|
| `await self.text_to_image(text, return_url=True, template_name=None, umo=None)` | 用 t2i 服务把文本渲染成图片，返回 URL 或文件路径 |
| `await self.html_render(tmpl, data, return_url=True, options=None, umo=None)` | 用 Jinja2 HTML 模板渲染成图片 |
| `self.parse_commands(message)` / `self.regex_match(message, command)` | `CommandParserMixin` 提供的指令解析辅助 |

```python
from astrbot.api.message_components import Image

async def render(self, event):
    url = await self.html_render("<h1>{{ title }}</h1>", {"title": "报告"})
    yield event.chain_result([Image.fromURL(url)])
```

## KV 持久化（PluginKVStoreMixin）

`Star` 自带三个异步方法，数据由 AstrBot 统一管理，不必自己建文件：

```python
await self.put_kv_data("counter", 1)
n = await self.get_kv_data("counter", 0)
await self.delete_kv_data("counter")
```

源码签名：`put_kv_data(key, value)`、`get_kv_data(key, default) -> value | None`、`delete_kv_data(key)`。

## StarTools：数据目录与工具管理

`astrbot.api.star.StarTools` 是类方法集合（源码 `core/star/star_tools.py`）：

| 方法 | 用途 |
|---|---|
| `StarTools.get_data_dir(plugin_name=None)` | 返回 `data/plugin_data/<name>`，自动创建目录；不传参则从调用栈推断插件名 |
| `await StarTools.send_message(...)` / `create_message(...)` / `create_event(...)` | 主动构造/发送消息 |
| `StarTools.activate_llm_tool(name)` / `deactivate_llm_tool(name)` | 启用/停用 LLM 工具 |
| `StarTools.register_llm_tool(...)` / `unregister_llm_tool(name)` | 注册/注销工具 |

```python
from astrbot.api.star import StarTools

data_dir = StarTools.get_data_dir("astrbot_plugin_xxx")
(data_dir / "cache.json").write_text("{}", encoding="utf-8")
```

> 官方开发原则：持久化数据放 `data/` 下，**不要写进插件自身目录**，否则插件更新/重装会覆盖。

## Context 常用方法速查

`self.context` 是 `Context`（`core/star/context.py`），常用：

| 方法 | 用途 |
|---|---|
| `get_config(umo=None) -> AstrBotConfig` | 读取（会话级）主配置 |
| `await send_message(session, message_chain)` | 按 `unified_msg_origin` 主动发消息 |
| `await llm_generate(...)` / `await tool_loop_agent(...)` | 直接调用 LLM / Agent |
| `get_using_provider(umo=None)` / `get_all_providers()` | 获取模型提供商 |
| `get_all_stars()` / `get_registered_star(name)` | 查其他插件 |
| `get_platform(type)` / `get_platform_inst(id)` | 取平台适配器实例 |
| `get_db()` | 数据库 |
| `register_web_api(...)` | 注册自定义 Web API |
| `register_commands(...)` / `register_task(awaitable, desc)` | 动态注册指令 / 后台任务 |
| `add_llm_tools(*tools)` / `register_llm_tool(...)` | 注册函数工具 |
| `get_event_queue()` | 事件队列 |

详见 [07 平台 API 与工具](07-平台API与工具.md)。

## 常见构造错误

| 现象 | 原因 |
|---|---|
| `AttributeError: 'XxxPlugin' object has no attribute 'context'` | 没调 `super().__init__(context)` |
| 配置全是默认值 / 读不到 | `__init__` 只接 `context`，触发加载器回退；或没把 `config` 存到 `self.config` |
| `TypeError: 不受支持的配置类型 ...` | `_conf_schema.json` 的 `type` 非法，见 [02 配置 Schema](02-配置Schema.md) |
| 插件出现在「加载失败」列表 | 看日志 Traceback；`__init__` 里抛任何异常都会导致加载失败 |
