#!/usr/bin/env python3
"""图形界面入口：真正的实现已按业务拆分到 qweather_gui 包。

运行方式与打包方式保持不变：
    python src/qweather_auth_gui.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from qweather_gui import APP_TITLE, AuthApp, main  # noqa: E402

__all__ = ["AuthApp", "APP_TITLE", "main"]


if __name__ == "__main__":
    sys.exit(main())
