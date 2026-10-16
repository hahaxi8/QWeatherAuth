#!/usr/bin/env python3
"""窗口外观：高分屏适配与窗口/任务栏图标。"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path

import qweather_core as core

__all__ = ["enable_dpi_awareness", "apply_window_icon"]
def enable_dpi_awareness() -> None:
    """Windows 高分屏下避免界面模糊。"""
    if os.name != "nt":
        return
    try:
        from ctypes import windll  # type: ignore[attr-defined]

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - 失败不影响功能
        pass


def apply_window_icon(window: tk.Misc) -> str:
    """把窗口与任务栏图标设置成与 exe 相同的图标。

    Tk 默认会用自己的图标，导致"标题栏/任务栏图标"与"exe 文件图标"不一致。
    打包时用 --add-data 把 icon.ico 塞进 exe，这里按优先级查找并应用。
    """
    candidates: list = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "icon.ico")
    for base in Path(__file__).resolve().parents:
        candidate = base / "assets" / "icon.ico"
        if candidate.is_file():
            candidates.append(candidate)
            break
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "icon.ico")
    for path in candidates:
        if path.is_file():
            try:
                window.iconbitmap(default=str(path))
                return str(path)
            except tk.TclError:
                continue
    return ""
