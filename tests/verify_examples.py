"""用真实 AstrBot 4.29.4 环境验证本仓库的两个示例插件。

跑法（需装有 astrbot==4.29.4 的 Python 3.12 环境）：
    python tests/verify_examples.py

验证项：
1. metadata.yaml 通过官方 _PluginUpdater.validate_plugin_metadata
2. _conf_schema.json 类型合法 + AstrBotConfig(schema=...) 构造成功（无该文件则跳过）
3. main.py 语法编译 + 真实导入
4. 存在 Star 子类，且 filter 装饰器确实注册到 star_handlers_registry
5. 插件类可实例化、context 已注入、配置可读取
6. 打包成 zip 后通过官方 inspect_plugin_archive
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import zipfile

import yaml
from astrbot.api.star import Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_VALUE_MAP
from astrbot.core.star.register.star_handler import star_handlers_registry
from astrbot.core.star.updater import _PluginUpdater as Updater

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

PASS: list[bool] = []


def check(label: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        print(f"  [FAIL] {label}: {type(exc).__name__}: {exc}")
        PASS.append(False)
    else:
        print(f"  [PASS] {label}")
        PASS.append(True)


class FakeContext:
    """最小上下文，满足 Star 基类与 _conf() 兜底调用。"""

    def get_config(self) -> dict:
        return {}


def load_module(name: str, plugin_dir: pathlib.Path):
    """以包形式加载 main.py（支持相对导入）。"""
    spec = importlib.util.spec_from_file_location(
        name, plugin_dir / "main.py", submodule_search_locations=[str(plugin_dir)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def find_star_class(mod, module_name: str):
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if (
            isinstance(obj, type)
            and issubclass(obj, Star)
            and obj is not Star
            and obj.__module__ == module_name
        ):
            return obj
    return None


def verify_one(module_name: str, dirname: str) -> None:
    d = EXAMPLES / dirname
    print(f"--- {dirname} ---")

    # 1) metadata
    def _metadata():
        meta = yaml.safe_load((d / "metadata.yaml").read_text(encoding="utf-8"))
        Updater.validate_plugin_metadata(meta, "metadata.yaml")

    check("metadata.yaml 官方校验通过", _metadata)

    # 2) schema（无文件则明确跳过，不伪装成 PASS）
    schema_path = d / "_conf_schema.json"
    cfg = None
    if schema_path.exists():
        def _schema():
            schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
            bad = {
                k: v.get("type")
                for k, v in schema.items()
                if v.get("type") not in set(DEFAULT_VALUE_MAP)
            }
            assert not bad, f"不支持的配置类型: {bad}"
            AstrBotConfig(
                config_path=os.path.join(tempfile.mkdtemp(), "v.json"),
                schema=schema,
            )

        check("_conf_schema.json 类型合法 + AstrBotConfig 构造通过", _schema)
        cfg = AstrBotConfig(
            config_path=os.path.join(tempfile.mkdtemp(), "inst.json"),
            schema=json.loads(schema_path.read_text(encoding="utf-8-sig")),
        )
    else:
        print("  [SKIP] 该示例不含 _conf_schema.json")

    # 3) 语法
    def _compile():
        compile((d / "main.py").read_text(encoding="utf-8"), str(d / "main.py"), "exec")

    check("main.py 语法编译通过", _compile)

    # 4) 导入 + 注册
    holder: dict = {}

    def _import():
        holder["mod"] = load_module(module_name, d)

    check("main.py 真实导入成功", _import)
    mod = holder.get("mod")
    if mod is None:
        print("         （导入失败，后续检查跳过）")
        print()
        return

    def _star_class():
        assert find_star_class(mod, module_name) is not None, "未找到继承 Star 的插件类"

    check("存在 Star 子类", _star_class)

    def _handlers():
        hits = [
            h
            for h in star_handlers_registry.star_handlers_map.values()
            if h.handler_module_path == module_name
        ]
        assert hits, "没有 handler 注册成功"
        print(f"         已注册 handler: {len(hits)} 个 "
              f"({', '.join(sorted({h.event_type.name for h in hits}))})")

    check("filter 装饰器已注册", _handlers)

    # 5) 实例化
    def _instantiate():
        cls = find_star_class(mod, module_name)
        plugin = cls(context=FakeContext(), config=cfg)
        assert plugin.context is not None, "super().__init__ 未注入 context"
        if cfg is not None:
            assert plugin._conf("ENABLED", None) is True, "配置读取失败"
        assert hasattr(plugin, "logger"), "缺少插件专属 logger"

    check("插件类可实例化且配置可读取", _instantiate)

    # 6) zip
    def _zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in sorted(d.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts and ".pyc" not in f.name:
                    z.write(f, str(f.relative_to(d)))
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(buf.getvalue())
            path = tmp.name
        try:
            result = Updater.inspect_plugin_archive(path)
            assert result["metadata"]["name"], "zip 内 metadata 为空"
        finally:
            os.unlink(path)

    check("打包后 inspect_plugin_archive 通过", _zip)
    print()


def main() -> int:
    print("=== AstrBot 4.29.4 示例插件验证 ===")
    print(f"  AstrBot = {importlib.metadata.version('astrbot')}, "
          f"Python = {sys.version.split()[0]}")
    print()
    verify_one("guide_minimal", "minimal")
    verify_one("guide_advanced", "config_and_hook")
    print(f"=== 结果: {sum(PASS)}/{len(PASS)} 通过 ===")
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
