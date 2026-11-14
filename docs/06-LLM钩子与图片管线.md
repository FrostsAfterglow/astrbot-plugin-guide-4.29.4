# 06 LLM 钩子与 4.29.4 图片管线

这一章是 **4.29.4 变化最大、也最容易踩坑**的部分。所有时序结论来自 `core/pipeline/preprocess_stage/stage.py`、`core/astr_main_agent.py`、`core/pipeline/process_stage/method/agent_sub_stages/internal.py` 的实际代码。

## 管线顺序（4.29.4）

```
适配器收到消息
   ↓
① PreProcessStage（预处理）
   - 遍历消息链里的 Image，尝试把 url 下载/转成本地路径
   - 下载失败时判定「可恢复错误」→ 跳过该图，继续处理
   ↓
② 命令 handler / 指令处理
   ↓
③ collect_initial_request()（构造 ProviderRequest）
   - 成功的图片 → req.image_urls（url 已被改写成本地路径）
   - 失败的图片 → 往请求里塞一个 TextPart("[Image unavailable]")
   ↓
④ on_llm_request 钩子  ★ 插件能介入的位置
   ↓
⑤ prepare_request_images()
   - 用 MediaResolver / prepare_model_image 逐项标准化 req.image_urls
   - 支持本地路径、file:// URI、data: base64 URI
   ↓
⑥ 调用 LLM
   ↓
on_llm_response → on_decorating_result → 发送
```

**关键结论 1**：AstrBot **没有「预处理之前」的插件钩子**。预处理永远先于插件，因此 `gchat.qpic.cn 400` 这类 WARNING 无法被任何插件消除（它无害，可忽略）。

**关键结论 2**：`on_llm_request` 在 ③ 之后、⑤ 之前。插件此时能同时看到「原始消息段（仍带 file_id）」和「已构造好的 req」，是修复图片、改系统提示的唯一正确位置。

## ProviderRequest 字段

`astrbot.api.provider.ProviderRequest`（源码 `core/provider/entities.py:194`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `prompt` | str \| None | 用户提示 |
| `system_prompt` | str | 系统提示（可直接拼接修改） |
| `image_urls` | list[str] | 图片引用：http / 本地路径 / `data:` URI / `base64://` |
| `audio_urls` | list[str] | 音频 |
| `extra_user_content_parts` | list[ContentPart] | 额外内容段，**`[Image unavailable]` 占位就在这里** |
| `contexts` | list[dict] | 对话上下文 |
| `conversation` | Conversation \| None | 会话对象 |
| `func_tool` | ToolSet \| None | 函数工具集 |
| `tool_calls_result` | ... | 工具调用结果 |
| `session_id` | str | 会话 ID |
| `model` | str \| None | 指定模型 |

## on_llm_request 标准写法

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star


class PromptPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}

    @filter.on_llm_request()
    async def on_req(self, event: AstrMessageEvent, req: ProviderRequest):
        # 1) 改系统提示
        if "猫娘" not in req.system_prompt:
            req.system_prompt += "\n请用可爱的语气回答。"

        # 2) 追加图片（本地路径或 data URI 都可被下游标准化）
        # req.image_urls.append("/abs/path/a.png")
```

> 回调**必须接收两个参数** `event, req`（注册函数 docstring 明确要求）。返回 `None` 即可，不需要 yield。

## 其他 LLM / Agent 钩子

```python
@filter.on_llm_response()
async def on_resp(self, event: AstrMessageEvent, response):
    """LLM 响应后；response 是 LLMResponse"""
    ...

@filter.on_decorating_result()
async def decorate(self, event: AstrMessageEvent):
    """发送前，可改 event.get_result().chain"""
    ...

@filter.on_waiting_llm_request()
async def waiting(self, event: AstrMessageEvent):
    """已确定要调 LLM、排队等锁之前（适合发『思考中』）"""
    await event.send(MessageChain().message("🤔 正在思考中..."))

@filter.on_agent_begin()
async def agent_begin(self, event, run_context):
    ...

@filter.on_agent_done()
async def agent_done(self, event, run_context, ...):
    ...
```

`LLMResponse` 可从 `astrbot.api.provider` 导入，含 `role`、`completion_text`、`result_chain`、`tools_call_name`、`reasoning_content`、`raw_completion` 等字段。

## 4.29.4 图片管线细节（写给要修图片的人）

### ① 预处理阶段的失败判定

`is_recoverable_image_error()`（`core/utils/media_utils.py`）把 `DownloadFileHTTPError`（HTTP 400/403/404 等）判为**可恢复错误**：不中断消息处理，只跳过该图片。因此 QQ 图片因 rkey 失效返回 400 时，插件仍有机会介入。

### ② `[Image unavailable]` 占位文本

`collect_initial_request()`（`core/astr_main_agent.py` 约 1540–1630 行）对下载失败的图片插入：

```python
TextPart(text="[Image unavailable]")
```

到 `req.extra_user_content_parts`。**插件补回图片后必须等量清除这句**，否则 LLM 会同时收到「图不可用」和实际图片，自相矛盾。

### ③ 图片标准化

`prepare_request_images()` → `prepare_model_image(ref, max_size, output_dir)`：

- 内部用 `MediaResolver`（`core/utils/media_utils.py`）解析引用；
- 支持本地路径、`file://` URI、`data:image/png;base64,...`；
- `describe_media_ref()` 生成给 LLM 的描述，**不会把 base64 payload 泄漏进提示文本**；
- `max_size` 必须 > 0（如 1568），传 0 会返回 None。

> 模块路径变化：旧版 `astrbot.core.utils.media_resolver` → 4.29.4 为 **`astrbot.core.utils.media_utils`**（类仍叫 `MediaResolver`，方法 `as_path()` / `to_base64_data()` / `to_data_url()` / `to_path()` / `to_bytes()`）。引用该内部模块的旧插件需要改名。

### ④ 官方自带的取图兜底可作为参考

4.29.4 内置 `core/utils/quoted_message/image_resolver.py`，用 `get_image` 的 `file / file_id / id / image` 四种参数名 + `get_file` 兜底解析**引用消息**图片。写图片修复插件时应照抄这个兜底顺序，只试一种参数名命中率很低。

## 完整案例：图片本地化修复插件骨架

针对「QQ/NapCat 因 rkey 失效导致 `gchat.qpic.cn` 图片 400、机器人看不到图」的场景，插件思路是：用 OneBot `get_image` 取协议端**本地缓存**，绕开腾讯 CDN 与 rkey。

```python
import base64
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Reply
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api import logger

UNAVAILABLE = "[Image unavailable]"


class ImageFixPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}

    @filter.on_llm_request()
    async def fix(self, event: AstrMessageEvent, req: ProviderRequest):
        # 1) 收集预处理失败的图片 file_id（顶层 + 引用链）
        ids = []
        for comp in event.message_obj.message or []:
            if isinstance(comp, Reply) and comp.chain:
                items = comp.chain
            else:
                items = [comp]
            for seg in items:
                if isinstance(seg, Image) and seg.file:
                    ids.append(seg.file)

        # 2) 逐个用 get_image 多参数名兜底取本地缓存
        added = 0
        for fid in dict.fromkeys(ids):
            data = await self._fetch(event, fid)
            if not data:
                continue
            uri = "data:image/jpeg;base64," + base64.b64encode(data).decode()
            if uri not in req.image_urls:
                req.image_urls.append(uri)
                added += 1

        # 3) 等量清除占位文本
        if added:
            parts = req.extra_user_content_parts
            removed = 0
            keep = []
            for p in parts:
                txt = getattr(p, "text", None)
                if removed < added and txt and txt.strip() == UNAVAILABLE:
                    removed += 1
                    continue
                keep.append(p)
            req.extra_user_content_parts = keep
            logger.info("[imagefix] 补图 %d 张，清除占位 %d 条", added, removed)

    async def _fetch(self, event, fid):
        bot = getattr(event, "bot", None)
        if bot is None:
            return None
        for action in ("get_image", "get_file"):
            for key in ("file", "file_id", "id", "image"):
                try:
                    ret = await bot.api.call_action(action, **{key: fid})
                    # 返回可能是路径 / base64 / dict，需归一化后读取字节
                    ...
                except Exception:
                    continue
        return None
```

要点与局限：

- **不要改写消息组件本身**（改 `Image.url` 无效，预处理已跑完），只需写 `req.image_urls`。
- 图片已成功时 url 会被改写成本地路径，插件应跳过，避免重复。
- `data:` URI 与本地路径都能被 ⑤ 的 `MediaResolver` 消费，不会二次下载。
- 该插件**治标**：预处理 400 警告与群文件 `retcode=1400 packetBackend 不可用` 属于另一条链路，插件消除不了；彻底解决要对齐 QQ 版本与协议端支持的版本映射，或换协议端。

> 本仓库的实现参考：[`astrbot_plugin_qpicfix`](https://github.com/FrostsAfterglow/astrbot_plugin_qpicfix)（v1.1.1，已在 4.29.4 做过 8 项集成测试）。
