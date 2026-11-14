# 07 平台 API 与工具

## 调用 OneBot / 协议端原生 API

在 `aiocqhttp`（QQ 个人号，NapCat / LLOneBot 等）适配器下，`AstrMessageEvent` 的实际类型是 `AiocqhttpMessageEvent`，带 `bot` 属性，类型是 `aiocqhttp.CQHttp`。

源码 `core/platform/sources/aiocqhttp/aiocqhttp_message_event.py` 里官方自己的用法：

```python
info = await self.bot.call_action("get_group_member_info", ...)
```

### 两条等价路径（4.29.4 都可用）

```python
# 路径 A：CQHttp 自身的方法（推荐，官方内置代码就用这个）
ret = await event.bot.call_action("get_image", file=file_id)

# 路径 B：UnifiedApi 代理（CQHttp.api 是 property，返回 UnifiedApi 实例）
ret = await event.bot.api.call_action("get_image", file=file_id)
```

实测 `CQHttp` 有 `call_action(self, action: str, **params) -> Any`，且 `.api` 是 `UnifiedApi`、同样有 `call_action`。两者都能用，现有插件里两种写法都出现过。

### 安全写法（跨适配器）

`bot` 不是所有平台都有，跨适配器插件要做防御：

```python
bot = getattr(event, "bot", None)
if bot is None or event.get_platform_name() != "aiocqhttp":
    return
try:
    ret = await bot.call_action("get_image", file=file_id)
except Exception as e:
    self.logger.warning("[xxx] call_action 失败: %s", e)
```

### 常用 action

| action | 用途 | 关键参数 |
|---|---|---|
| `get_image` | 按 file_id 取图片本地缓存（绕开 rkey） | `file` / `file_id` / `id` / `image` 因协议端而异 |
| `get_file` | 取文件 | 同上 |
| `get_version_info` | 查协议端版本 | — |
| `get_group_member_info` | 群成员资料 | `group_id`, `user_id` |
| `send_group_msg` / `send_private_msg` | 直接发消息 | `group_id` / `user_id`, `message` |
| `send_group_forward_msg` | 合并转发 | `messages` |

> **参数名兜底很重要**：不同协议端对 `get_image` 的参数名要求不同。4.29.4 官方 `core/utils/quoted_message/image_resolver.py` 用 `file / file_id / id / image` 四种依次尝试，并配 `get_file` 兜底。只试一种命中率会明显偏低。

返回值形态也不统一，可能是：

- 本地文件路径字符串 / `file://` URI
- base64 字符串或 `base64://...` / `data:` URI
- dict（含 `file`、`url`、`base64`、`data` 等键）

建议写归一化函数统一成字节，再按需转 `data:` URI 或本地路径。

## 函数工具（llm_tool）

让 LLM 在对话中主动调用你的函数：

```python
from astrbot.api.event import AstrMessageEvent, filter


class ToolPlugin(Star):
    @filter.llm_tool(name="get_weather")   # 不填 name 则用函数名
    async def get_weather(self, event: AstrMessageEvent, location: str):
        '''获取指定地点的天气信息。

        Args:
            location(string): 地点名称
        '''
        return f"{location} 今天晴"
```

源码 `register_llm_tool` 的 docstring 明确要求：

- **docstring 必须按上面格式写**（AstrBot 会解析它生成工具 schema）；
- 第一个参数是 `event`；
- 可接受的参数类型：`string, number, object, array, boolean`（注意这是函数工具的参数类型，与配置 schema 的 `type` 白名单是两套东西，**别混淆**）。

相关钩子：`@filter.on_using_llm_tool()`（调用前，收 `tool, tool_args`）、`@filter.on_llm_tool_respond()`（返回后，收 `tool, tool_args, tool_result`）。

也可以用 `self.context.add_llm_tools(*tools)` / `StarTools.register_llm_tool(...)` 动态注册。

## 自定义过滤器

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.custom_filter import CustomFilter


class OnlyMyGroup(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg) -> bool:
        return event.get_group_id() == "123456"


@filter.custom_filter(OnlyMyGroup())
@filter.command("secret")
async def secret(self, event: AstrMessageEvent):
    yield event.plain_result("仅特定群可见")
```

## 插件提供 Skills

4.29.4 支持插件随附 Skill，加载后自动纳入 Skill Manager（WebUI「插件 → 技能」里只读展示）：

```
your_plugin/
├── metadata.yaml
├── main.py
└── skills/
    ├── report-writer/
    │   └── SKILL.md
    └── web-search-helper/
        └── SKILL.md
```

也可以让 `skills/` 本身就是一个 Skill（直接放 `skills/SKILL.md`），此时 Skill 名取插件目录名。

## 注册自定义 Web API

```python
self.context.register_web_api(
    route="/api/myplugin/status",
    ...   # 参考 Context.register_web_api 签名
)
```

## Context 方法完整分组（`core/star/context.py`）

| 分组 | 方法 |
|---|---|
| 配置 | `get_config(umo=None)`、`get_current_chat_provider_id(umo)` |
| LLM | `llm_generate(...)`、`tool_loop_agent(...)`、`get_using_provider(_async)`、`get_all_providers()`、`get_all_tts_providers()`、`get_all_stt_providers()`、`get_all_embedding_providers()`、`get_provider_by_id(...)` |
| 插件 | `get_registered_star(name)`、`get_all_stars()`、`get_llm_tool_manager()`、`activate_llm_tool(_async)`、`deactivate_llm_tool(_async)` |
| 平台 | `get_platform(type)`、`get_platform_inst(id)` |
| 消息 | `send_message(session, message_chain)` |
| 注册 | `add_llm_tools(*tools)`、`register_llm_tool(...)`、`unregister_llm_tool(name)`、`register_commands(...)`(已废弃)、`register_task(awaitable, desc)`、`register_web_api(...)`、`register_provider(...)` |
| 其他 | `get_event_queue()`、`get_db()` |

## 开发原则（官方要求，写插件时遵守）

1. 功能需经过测试；包含良好注释。
2. 持久化数据放 `data/` 下，不放插件目录。
3. 良好错误处理，不要让单个错误导致插件崩溃。
4. 提交前用 `ruff` 格式化。
5. **不要用同步的 `requests`**，用 `aiohttp` / `httpx` 等异步库。
6. 给现有插件扩功能优先提 PR，不要另起一个插件（原作者停维护除外）。
7. 借鉴/移植他人代码或设计，需在 README 说明灵感来源并附链接，遵守原许可证。
