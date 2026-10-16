#!/usr/bin/env python3
"""和风天气接口生成工具的图形界面包。

按区域拆成 mixins；这里对外只暴露主窗口与入口。
"""

from __future__ import annotations

from .app import AuthApp
from .constants import APP_TITLE
from .main import main

__all__ = ["AuthApp", "APP_TITLE", "main"]
