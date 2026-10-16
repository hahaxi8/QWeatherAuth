#!/usr/bin/env python3
"""控制台命令行入口：真正的实现已按业务拆分到 qweather_console 包。

用法与之前一致：
    python src/qweather_console.py login --save
    python src/qweather_console.py publish --public-key <公钥.pem> --save
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from qweather_console.cli import main  # noqa: E402

__all__ = ["main"]


if __name__ == "__main__":
    sys.exit(main())
