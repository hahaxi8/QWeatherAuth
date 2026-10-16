#!/usr/bin/env python3
"""结构自检：包内模块不应引用「未显式导入的私有名字」。

`from .模块 import *` 不会带出下划线开头的名字，拆分包时最容易在这里出错
（曾经漏导入 _WRITE_JS，导致点击“一键生成”时报 name '_WRITE_JS' is not defined）。

运行（项目根目录）：
    python -m unittest discover tests
"""

from __future__ import annotations

import ast
import sys
import unittest
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _top_level_private(tree: ast.Module) -> set:
    names: set = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("_"):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.startswith("_"):
                names.add(node.target.id)
    return names


def _explicit_imports(tree: ast.Module) -> set:
    names: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
    return names


def _loaded_names(tree: ast.Module) -> set:
    return {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


class TestPackageStructure(unittest.TestCase):
    def test_no_missing_private_imports(self) -> None:
        modules = {
            path: ast.parse(path.read_text(encoding="utf-8"))
            for path in sorted(SRC.rglob("*.py"))
            if "__pycache__" not in path.parts
        }
        self.assertTrue(modules, "没有找到源码模块")

        owner: dict = defaultdict(set)
        for path, tree in modules.items():
            for name in _top_level_private(tree):
                owner[name].add(path)

        problems = []
        for path, tree in modules.items():
            known = _top_level_private(tree) | _explicit_imports(tree)
            for name in sorted(_loaded_names(tree)):
                if not name.startswith("_") or name.startswith("__"):
                    continue
                if name in known or name not in owner:
                    continue
                where = ", ".join(sorted(str(p.relative_to(SRC)) for p in owner[name]))
                problems.append(f"{path.relative_to(SRC)} 使用了 {name}（在 {where}）但没有显式导入")
        self.assertEqual(problems, [], "跨模块私有名缺失：\n" + "\n".join(problems))

    def test_write_json_js_template_is_available(self) -> None:
        """回归用例：write_json 依赖的页内 fetch 模板必须能取到（曾经漏导入 _WRITE_JS）。"""
        import json

        import qweather_console as qconsole

        class FakeCdp:
            def __init__(self) -> None:
                self.expressions = []

            def evaluate(self, expression, await_promise=True, timeout=30.0):
                self.expressions.append(expression)
                return {"status": 200,
                        "body": json.dumps({"success": True, "data": {"uniqueCode": "P1"}})}

        session = qconsole.ConsoleSession()
        session.cdp = FakeCdp()
        result = session.write_json("PUT", "/v2/rest/app", {"appName": "天气数据接口"})

        self.assertTrue(result.get("success"))
        self.assertTrue(session.cdp.expressions, "没有向浏览器发请求")
        javascript = session.cdp.expressions[0]
        for token in ("fetch", "PUT", "/v2/rest/app", "XSRF-TOKEN", "credentials"):
            self.assertIn(token, javascript)
        self.assertIn("appName", javascript)


if __name__ == "__main__":
    unittest.main(verbosity=2)
