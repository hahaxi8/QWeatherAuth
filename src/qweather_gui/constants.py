#!/usr/bin/env python3
"""界面常量：标题、控制台地址、各种延迟与轮询间隔。"""

from __future__ import annotations


import qweather_core as core

__all__ = ["APP_TITLE", "CONSOLE_URL", "CONSOLE_PROJECT_URL", "CITY_LOOKUP_DELAY_MS", "CITY_LOOKUP_MIN_CHARS", "LOOKUP_POLL_MS", "AUTO_CONSOLE_FIRST_DELAY_MS", "AUTO_CONSOLE_RETRY_MS"]
APP_TITLE = core.APP_TITLE


CONSOLE_URL = "https://console.qweather.com/setting"


CONSOLE_PROJECT_URL = "https://console.qweather.com/project"


CITY_LOOKUP_DELAY_MS = 800


CITY_LOOKUP_MIN_CHARS = 2


LOOKUP_POLL_MS = 100


AUTO_CONSOLE_FIRST_DELAY_MS = 900


AUTO_CONSOLE_RETRY_MS = 20000
