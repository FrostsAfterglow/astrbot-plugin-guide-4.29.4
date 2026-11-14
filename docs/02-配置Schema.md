# 02 配置 Schema（_conf_schema.json）

## 作用

在插件目录放 `_conf_schema.json`，AstrBot 会：

1. 依据 schema 生成默认配置，保存为 `data/config/<插件目录名>_config.json`；
2. 在 WebUI 插件配置弹窗里渲染可视化表单；
3. 实例化插件时把配置对象作为 `config` 传给 `__init__`。

配置对象类型是 `AstrBotConfig`（`astrbot.core.config.astrbot_config`），**继承自 `dict`**，拥有字典全部方法，另有 `save_config()`。

## 致命陷阱：`type` 只能用这 10 种

源码 `core/config/default.py` 的 `DEFAULT_VALUE_MAP` 与 `astrbot_config._config_schema_to_default_config()`：

```python
DEFAULT_VALUE_MAP = {
    "int": 0, "float": 0.0, "bool": False,
    "string": "", "text": "",
    "list": [], "file": [],
    "object": {}, "template_list": [], "dict": {},
}
```

只要 `type` 不在这个字典里，加载阶段立刻抛：

```
TypeError: 不受支持的配置类型 number。支持的类型有：dict_keys(['int', 'float', 'bool', 'string', 'text', 'list', 'file', 'object', 'template_list', 'dict'])
```

**后果是整个插件加载失败**（`star_manager.load` 里构造 `AstrBotConfig` 时抛错，插件进「加载失败」列表），不是一个配置项失效。

> 这是本指南收录的实测事故：把数值配置写成 `"type": "number"`（很多框架/JSON Schema 的写法），在 AstrBot 里非法。
> **数值请用 `int`（整数）或 `float`（可小数）**。写 `float` 时 `default` 写 `15` 也没问题 —— `_parse_schema` 不校验默认值类型，只是直接赋值；插件里建议自行 `float(...)` / `int(...)` 归一化。

| 你想表达 | 正确 `type` | 默认值缺省时 |
|---|---|---|
| 开关 | `bool` | `False` |
| 整数（秒数、次数） | `int` | `0` |
| 小数（MB、比例） | `float` | `0.0` |
| 单行文本 / Token | `string` | `""` |
| 多行长文本 | `text` | `""` |
| 列表 | `list` | `[]` |
| 文件上传 | `file` | `[]` |
| 嵌套对象 | `object` | `{}` |
| 模板列表 | `template_list` | `[]` |
| 自由字典 | `dict` | `{}` |

## 全部 schema 字段

| 字段 | 适用 | 说明 |
|---|---|---|
| `type` | 全部 | **必填**，10 种之一 |
| `description` | 全部 | 配置描述，建议一句话 |
| `default` | 全部 | 默认值，省略则用上表缺省值 |
| `hint` | 全部 | 悬浮问号提示 |
| `obvious_hint` | 全部 | 让 hint 醒目显示 |
| `items` | `object` / `list` / `dict` | 子 schema 或元素类型 |
| `invisible` | 全部 | `true` 时不在面板显示 |
| `secret` | `string` / 字符串 `list` | 密码框遮罩。**只遮显示，不加密落盘**，插件不要回显/记录 |
| `options` | 字符串类 | 下拉可选项列表 |
| `labels` | 配合 `options` | 按索引对应的展示名 |
| `subtitles` | 配合 `options` | 下拉项副标题 |
| `slider` | `int` / `float` | `{"min":1,"max":100,"step":1}` |
| `editor_mode` | 文本类 | 启用代码编辑器 |
| `editor_language` / `editor_theme` | 文本类 | 默认 `json` / `vs-light` |
| `enum` | 字符串类 | 可枚举值（与 `options` 二选一即可，面板表现以 `options` 为佳） |
| `file_types` | `file` | 允许的扩展名，如 `["pdf","docx"]` |
| `template_schema` | `dict` | 可视化编辑 dict 的模板 |
| `templates` / `display_item` / `hide_hint_in_list` | `template_list` | 模板列表定义 |
| `_special` | 特定 | 调用内置选择器：`select_provider`、`select_persona`、`select_knowledgebase`、`sender_id`、`umo` 等 |

> 源码提醒：`select_providers`、`provider_pool`、`persona_pool`、`t2i_template` 等 `_special` 值属于 Core 内部实现，随时可能变，**插件不要用**。

## 最小可用示例

```json
{
  "ENABLED": {
    "description": "是否启用",
    "type": "bool",
    "default": true
  },
  "MAX_SIZE_MB": {
    "description": "单文件最大体积（MB，可小数）",
    "type": "float",
    "default": 15,
    "slider": {"min": 1, "max": 100, "step": 0.5}
  },
  "RETRY_COUNT": {
    "description": "失败重试次数",
    "type": "int",
    "default": 3
  },
  "MODE": {
    "description": "运行模式",
    "type": "string",
    "default": "normal",
    "options": ["normal", "verbose"],
    "labels": ["常规", "详细"]
  },
  "API_KEY": {
    "description": "接口密钥",
    "type": "string",
    "default": "",
    "secret": true
  }
}
```

## 嵌套 object / list / file

```json
{
  "server": {
    "description": "服务设置",
    "type": "object",
    "items": {
      "host": {"type": "string", "default": "127.0.0.1"},
      "port": {"type": "int", "default": 8080}
    }
  },
  "whitelist": {
    "description": "允许的 ID",
    "type": "list",
    "default": [],
    "items": {"type": "string"}
  },
  "attachments": {
    "description": "上传附件",
    "type": "file",
    "default": [],
    "file_types": ["pdf", "docx"]
  }
}
```

`object` 的 `_parse_schema` 会递归解析 `items` 生成嵌套默认字典；`template_list` 走单独分支，直接采用 `default`。

## 在插件里读配置

```python
from astrbot.api.star import Context, Star


class MyPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config if isinstance(config, dict) else {}

    def _conf(self, key, default):
        """带兜底的读取：兼容 4.29.4 注入、旧版只传 context、以及直接实例化测试。"""
        if isinstance(self.config, dict) and key in self.config:
            return self.config[key]
        try:
            cfg = self.context.get_config()
            if isinstance(cfg, dict) and key in cfg:
                return cfg[key]
        except Exception:
            pass
        return default

    async def foo(self):
        enabled = self._conf("ENABLED", True)
        max_mb = float(self._conf("MAX_SIZE_MB", 15))   # 自己归一化类型
        retry = int(self._conf("RETRY_COUNT", 3))
```

要点：

- 加载器（`star_manager.load`，约 1228 行）先尝试 `star_cls_type(context=..., config=plugin_config)`；若抛 `TypeError`（你的 `__init__` 不接受 `config`），**自动回退**为只传 `context`。所以写 `def __init__(self, context)` 也不会崩，但拿不到配置。
- 建议始终把 `config` 存到 `self.config`，并用 `_conf()` 兜底 —— 面板里用户删了配置项、配置迁移、单元测试直接实例化时都不会 `KeyError`。
- 修改后可调用 `self.config.save_config()` 持久化（注意并发与用户面板编辑的覆盖关系）。
- 发布新版本更新 schema 时，AstrBot 会递归补齐缺失项、移除已不存在的项。

## 回归测试：锁死类型合法性

把这段放进插件的测试里，可以在升级 AstrBot 或改 schema 时立刻发现问题：

```python
import json, pathlib
from astrbot.core.config.default import DEFAULT_VALUE_MAP
from astrbot.core.config.astrbot_config import AstrBotConfig

schema = json.loads(pathlib.Path("_conf_schema.json").read_text(encoding="utf-8-sig"))
bad = {k: v.get("type") for k, v in schema.items() if v.get("type") not in DEFAULT_VALUE_MAP}
assert not bad, f"存在不支持的配置类型: {bad}"

cfg = AstrBotConfig(config_path="/tmp/test_config.json", schema=schema)
assert cfg["ENABLED"] is True
```

完整可运行版本见 [`examples/config_and_hook/tests/test_conf_schema.py`](../examples/config_and_hook/tests/test_conf_schema.py)。
