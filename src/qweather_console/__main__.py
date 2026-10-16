#!/usr/bin/env python3
"""支持 python -m qweather_console 的入口。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
