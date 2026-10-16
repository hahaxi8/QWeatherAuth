#!/usr/bin/env python3
"""主窗口：按功能组合各 mixin，自身只声明窗口类。"""

from __future__ import annotations

import tkinter as tk

from .constants import APP_TITLE
from .mixins.auth import AuthSectionMixin
from .mixins.config import ConfigMixin
from .mixins.console import ConsoleFlowMixin
from .mixins.console_account import ConsoleAccountMixin
from .mixins.host import HostSectionMixin
from .mixins.links import LinksSectionMixin
from .mixins.location import LocationMixin
from .mixins.queues import QueueMixin
from .mixins.root import RootMixin

__all__ = ["AuthApp"]


class AuthApp(RootMixin, HostSectionMixin, AuthSectionMixin, LinksSectionMixin,
               ConfigMixin, LocationMixin, QueueMixin, ConsoleFlowMixin,
               ConsoleAccountMixin, tk.Tk):
    """和风天气接口生成工具主窗口（各区域实现见 qweather_gui.mixins）。"""
    LOCATION_HINT = ("填城市或区县名会自动查询；时光机必须用 LocationID，"
                     "其余接口用经纬度即可。")
