#!/usr/bin/env python3
"""数据目录与文件路径：凭据目录、配置文件、密钥文件、安全写入。"""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

__all__ = ["DATA_DIR_ENV", "DATA_DIR_NAME", "program_dir", "data_dir", "ensure_data_dir", "config_path", "auth_path", "active_key_path", "jwt_path", "links_path", "secure_write"]
DATA_DIR_ENV = "QWEATHER_DATA_DIR"


DATA_DIR_NAME = "data"


def program_dir() -> Path:
    """程序所在目录：打包后是 exe 所在目录，源码运行时是源码所在目录。

    凭据目录就生成在这里，即 exe 放在 bin/ 下就是 bin/data。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """凭据目录（与程序同目录，名为 data），可用环境变量 QWEATHER_DATA_DIR 覆盖。"""
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return program_dir() / DATA_DIR_NAME


def ensure_data_dir() -> Path:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def auth_path() -> Path:
    return data_dir() / "auth.json"


def active_key_path() -> Path:
    return data_dir() / "active_key.json"


def jwt_path() -> Path:
    return data_dir() / "jwt.txt"


def links_path() -> Path:
    return data_dir() / "qweather_links.sh"


def secure_write(path: Path, text: str) -> None:
    """写入文件；在 POSIX 上把权限收紧到仅属主可读写。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def _atomic_write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    secure_write(tmp, text)
    os.replace(tmp, path)


def _now_text() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()
