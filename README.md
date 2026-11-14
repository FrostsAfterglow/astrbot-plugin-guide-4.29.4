# AstrBot v4.29.4 插件开发指南

> 面向 **AstrBot 4.29.4**（Python ≥ 3.12）的插件创建指南与代码指南。
> 本指南所有 API、字段名、类型白名单、管线时序均从 **4.29.4 实际安装源码**逐项核对，而非照抄旧版文档或凭印象编写。
> 编写日期：2026-11-14。

---

## 这份指南解决什么

AstrBot 的官方文档分成了「旧版指南」「新版指南」「配置」「发布」等多个页面，且部分页面已标注过时；网上流传的插件教程多为 v3.x/v4.0 时代写法，直接套到 4.29.4 会出现「照着写却加载失败」的问题。本指南做三件事：

1. **把 4.29.4 的真实约定固化下来**：哪些字段必填、哪些类型合法、config 怎么注入、钩子何时触发。
2. **给出可直接运行的代码**：仓库 `examples/` 下两个插件都在 AstrBot 4.29.4 / Python 3.12 环境里做过真实加载验证。
3. **收录实测踩过的坑**：配置类型写成 `number` 导致整个插件加载失败、安装器报「未在仓库根目录找到 metadata.yaml」其实是网络误报等，都给出根因和修复。

---

## 5 分钟：最小插件

目录放在 AstrBot 的 `data/plugins/astrbot_plugin_hello/` 下：

```
astrbot_plugin_hello/
├── metadata.yaml      # 必需：插件身份
└── main.py            # 必需：入口（也可命名为与目录同名的 .py）
```

`metadata.yaml`（`name/desc/version/author` 四个字段必填且必须是非空字符串）：

```yaml
name: astrbot_plugin_hello
desc: 一个最小示例插件
version: 1.0.0
author: YourName
repo: https://github.com/YourName/astrbot_plugin_hello
```

`main.py`：

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.api import logger


class HelloPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)          # 必须调用：注入 self.context / self.logger
        self.config = config or {}         # 4.29.4 传入的是 AstrBotConfig（dict 子类）

    @filter.command("hello")               # 发送 /hello 触发
    async def hello(self, event: AstrMessageEvent):
        """打招呼"""                       # docstring 会被解析为指令帮助
        yield event.plain_result(f"你好，{event.get_sender_name()}！")

    async def terminate(self):
        """插件卸载/停用时调用"""
        logger.info("[hello] 已卸载")
```

放进 `data/plugins/` 后重启 AstrBot，或在 WebUI 插件页点「重载插件」。完整可运行版本见 [`examples/minimal/`](examples/minimal/)。

> **注意**：`@register(...)` 装饰器在 4.29.4 **已废弃**，不要再用。加载器会自动识别所有继承 `Star` 的类（源码 `core/star/base.py` 的 `__init_subclass__` + `core/star/star_manager.py` 的模块扫描）。

---

## 目录

| 章节 | 内容 |
|---|---|
| [01 项目结构与 metadata.yaml](docs/01-项目结构与元数据.md) | 目录约定、入口发现规则、metadata 全字段、命名与版本约束、logo、requirements.txt |
| [02 配置 Schema（_conf_schema.json）](docs/02-配置Schema.md) | 10 种合法类型、全部 schema 字段、AstrBotConfig 读取、`type: number` 致命陷阱 |
| [03 Star 类与生命周期](docs/03-Star类与生命周期.md) | `__init__` 与 config 注入回退、initialize/terminate、self.logger、KV 存储、HTML 渲染、StarTools |
| [04 事件、指令与过滤器](docs/04-事件与指令.md) | 全部 `filter.*` 装饰器、带参指令、指令组、权限/平台过滤、priority、AstrMessageEvent 方法 |
| [05 消息组件与结果](docs/05-消息组件与结果.md) | 消息链、全部组件、plain/chain/image_result、send、stop_event、request_llm |
| [06 LLM 钩子与 4.29.4 图片管线](docs/06-LLM钩子与图片管线.md) | on_llm_request 等钩子签名、ProviderRequest 字段、图片预处理时序、`[Image unavailable]` 占位 |
| [07 平台 API 与工具](docs/07-平台API与工具.md) | `event.bot.call_action`、Context 常用方法、llm_tool、Skills、Web API |
| [08 发布、安装与排错](docs/08-发布安装与排错.md) | 三种安装方式、插件市场发布、常见报错速查表、调试流程 |
| [09 版本差异与避坑清单](docs/09-版本差异与避坑清单.md) | 4.29.4 相对旧版的变化、逐条避坑清单 |

**代码指南（可直接复制运行）**：

- [`examples/minimal/`](examples/minimal/) —— 最小插件：指令、消息结果、生命周期。
- [`examples/config_and_hook/`](examples/config_and_hook/) —— 进阶插件：配置 Schema、权限指令、指令组、`on_llm_request` 改系统提示、平台 API 调用。
- [`tests/verify_examples.py`](tests/verify_examples.py) —— 用真实 4.29.4 环境验证示例的脚本。

---

## 黄金法则（先记住这 8 条）

1. **入口**：`main.py`（或 `<目录名>.py`），类名任意，但必须继承 `Star`；处理函数必须写在插件类里，前两个参数是 `self, event`。
2. **元数据**：`metadata.yaml` 四个字段 `name / desc / version / author` 缺一不可，且都是非空字符串；文件名只能是 `metadata.yaml` 或 `metadata.yml`，必须在仓库根目录。
3. **配置类型**：`_conf_schema.json` 的 `type` 只接受 `int / float / bool / string / text / list / file / object / template_list / dict`。**没有 `number`**，写错会在加载阶段抛 `TypeError`，整个插件加载失败。
4. **构造函数**：写 `def __init__(self, context: Context, config=None)` 并调用 `super().__init__(context)`。加载器先尝试 `config=` 注入，若你的 `__init__` 不接受则回退为只传 `context`。
5. **日志**：用 `from astrbot.api import logger` 或 `self.logger`，不要用 `logging.getLogger`；`self.logger` 是插件专属 logger，可在 WebUI 单独调级别。
6. **返回结果**：`yield event.plain_result(...)` / `yield event.chain_result([...])`，或 `return` 一个 `MessageEventResult`。处理函数是异步的。
7. **网络请求**：用 `aiohttp` / `httpx` 等异步库，**不要**用同步的 `requests`（会阻塞事件循环）。
8. **持久化数据**：写到 `data/` 下（推荐 `StarTools.get_data_dir()`），不要写进插件自身目录 —— 插件更新/重装会覆盖。

---

## 适用范围说明

- 本指南针对 **AstrBot 4.29.4**，对应 Python **≥ 3.12**。旧版（如 4.14.6 及更早）部分 API 路径不同，见 [09 版本差异](docs/09-版本差异与避坑清单.md)。
- 「AstrBot 泡泡版」等手机端打包发行版内置的就是 AstrBot 组件；插件目录、加载机制与桌面版一致，但**不同运行环境的文件系统互不相通**：在别处创建的 Linux 工作区 / Rootfs 里 `mkdir` 不出泡泡版的插件目录。
- 官方资料：[插件开发指南（新）](https://docs.astrbot.app/dev/star/plugin-new.html)、[插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)、[发布到插件市场](https://docs.astrbot.app/dev/star/plugin-publish.html)。本指南与官方文档冲突时，以 4.29.4 源码为准，并在文中标注差异。

---

## 验证方式

仓库内所有示例代码都可以在装有 AstrBot 4.29.4 的环境里验证：

```bash
python -m py_compile examples/minimal/main.py examples/config_and_hook/main.py
python tests/verify_examples.py
```

`verify_examples.py` 会真实执行：metadata 校验、`AstrBotConfig(schema=...)` 构造、插件模块导入、`filter` 装饰器注册计数、压缩包合法性检查。不是纸面代码。
