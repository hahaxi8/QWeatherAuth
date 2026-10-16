#!/usr/bin/env python3
"""程序入口。"""

from __future__ import annotations

import sys

from .app import AuthApp
def main() -> int:
    AuthApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
