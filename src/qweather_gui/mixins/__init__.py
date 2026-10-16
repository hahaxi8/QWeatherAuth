#!/usr/bin/env python3
"""主窗口的区域实现：每个模块一个 mixin，由 app.AuthApp 组合。"""

from __future__ import annotations

from .auth import AuthSectionMixin
from .config import ConfigMixin
from .console import ConsoleFlowMixin
from .console_account import ConsoleAccountMixin
from .host import HostSectionMixin
from .links import LinksSectionMixin
from .location import LocationMixin
from .queues import QueueMixin
from .root import RootMixin

__all__ = ["AuthSectionMixin", "ConfigMixin", "ConsoleFlowMixin",
           "ConsoleAccountMixin", "HostSectionMixin", "LinksSectionMixin",
           "LocationMixin", "QueueMixin", "RootMixin"]
