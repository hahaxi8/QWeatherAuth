#!/usr/bin/env python3
"""浏览器与本机状态：隐藏窗口参数、配置目录、调试端口发现、进程收尾。"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

from .constants import *
from .errors import ConsoleError

__all__ = ["hidden_process_kwargs", "app_local_dir", "profile_dir", "state_file", "read_state", "devtools_port_from_profile", "find_profile_browser_port", "port_alive", "write_state", "clear_state", "find_browser", "free_port", "http_get_json"]
def hidden_process_kwargs() -> Dict[str, Any]:
    """Windows 下隐藏子进程的控制台窗口。

    否则调用 PowerShell / taskkill 时会闪出（甚至弹出）一个黑色控制台窗口。
    注意：只用于辅助命令，启动浏览器时不能加（用户要看见浏览器）。
    """
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def app_local_dir() -> Path:
    """本机数据目录（不放共享盘）：%LOCALAPPDATA%\\QWeatherTool。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "QWeatherTool"


def profile_dir() -> Path:
    path = app_local_dir() / PROFILE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_file() -> Path:
    return app_local_dir() / STATE_FILE_NAME


def read_state() -> Dict[str, Any]:
    path = state_file()
    if not path.is_file():
        return {}
    try:
        # 用 utf-8-sig：文件可能被其他工具写入 BOM
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def devtools_port_from_profile() -> int:
    """读取浏览器自己写的 DevToolsActivePort（最可靠的发现方式）。"""
    candidate = profile_dir() / "DevToolsActivePort"
    if not candidate.is_file():
        return 0
    try:
        first_line = candidate.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        return int(first_line.strip())
    except (OSError, ValueError, IndexError):
        return 0


def find_profile_browser_port(timeout: float = 12.0) -> int:
    """从正在运行的浏览器进程里找出"使用本工具配置目录"的调试端口。

    浏览器不一定写 DevToolsActivePort（Edge 常常没有），所以进程命令行是更可靠的来源。
    """
    if os.name != "nt":
        return 0
    profile = str(profile_dir()).lower()
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' or Name='chrome.exe'\" "
        "| ForEach-Object { $_.CommandLine }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout, check=False, errors="replace",
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    for line in (result.stdout or "").splitlines():
        lowered = line.lower()
        if profile in lowered and "--remote-debugging-port=" in lowered:
            match = re.search(r"--remote-debugging-port=(\d+)", line)
            if match:
                return int(match.group(1))
    return 0


def port_alive(port: int, timeout: float = 2.0) -> bool:
    """调试端口是否在响应。"""
    try:
        http_get_json(f"http://127.0.0.1:{port}/json/version", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return False


def write_state(port: int, pid: int) -> None:
    try:
        state_file().write_text(
            json.dumps({"port": port, "pid": pid}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def clear_state() -> None:
    try:
        state_file().unlink()
    except OSError:
        pass


def find_browser() -> Path:
    for candidate in BROWSER_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    raise ConsoleError("找不到 Edge 或 Chrome，无法自动登录控制台")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_get_json(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))
