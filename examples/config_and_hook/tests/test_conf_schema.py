"""配置 Schema 兼容性回归测试（AstrBot 4.29.4）。

背景：4.29.4 的 AstrBotConfig._config_schema_to_default_config 只接受
DEFAULT_VALUE_MAP 中的类型。写成 "number" 会在 star_manager.load 阶段直接抛
`TypeError: 不受支持的配置类型 number`，导致整个插件加载失败。

跑法：
    python tests/test_conf_schema.py
"""

import json
import os
import pathlib
import tempfile

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_VALUE_MAP

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "_conf_schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))


def test_schema_types_are_supported():
    schema = _load_schema()
    supported = set(DEFAULT_VALUE_MAP)
    bad = {
        k: v.get("type")
        for k, v in schema.items()
        if v.get("type") not in supported
    }
    assert not bad, f"存在 4.29.4 不支持的配置类型: {bad}"
    print(f"  [PASS] schema 类型全部合法（{len(schema)} 项）")


def test_astrbot_config_constructs():
    """复现 star_manager.load 里的 AstrBotConfig(schema=...) 构造路径。"""
    schema = _load_schema()
    cfg = AstrBotConfig(
        config_path=os.path.join(tempfile.mkdtemp(), "guide_config.json"),
        schema=schema,
    )
    assert cfg["ENABLED"] is True
    assert int(cfg["MAX_ITEMS"]) == 10
    assert float(cfg["RATIO"]) == 0.75
    assert cfg["MODE"] == "normal"
    assert isinstance(cfg["WHITELIST"], list)
    assert isinstance(cfg["ADVANCED"], dict) and cfg["ADVANCED"]["timeout"] == 30
    print("  [PASS] AstrBotConfig 构造成功，默认值正确")


if __name__ == "__main__":
    print("=== 配置 schema 兼容性测试 (AstrBot 4.29.4) ===")
    test_schema_types_are_supported()
    test_astrbot_config_constructs()
    print("=== 全部通过 ===")
