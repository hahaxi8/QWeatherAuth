#!/usr/bin/env python3
"""配置与凭据文件读写：config.json、auth.json 及兼容旧格式的解析。"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from .constants import *
from .paths import *
from .paths import _atomic_write_json
from .paths import _now_text

__all__ = ["key_for_project", "remember_project_key", "parse_legacy_config", "load_config",
           "save_config", "build_auth_record", "save_auth", "normalize_auth_record", "load_auth"]
def parse_legacy_config(text: str) -> Dict[str, Any]:
    """解析历史上被写成 `key: value` 行格式的配置，抢救出已有的值。"""
    data: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for separator in (":", "="):
            if separator in line:
                key, _, value = line.partition(separator)
                key, value = key.strip(), value.strip().strip("'\"")
                if key:
                    data[key] = value
                break
    return data


def load_config() -> Dict[str, Any]:
    """读取 config.json；坏文件自动抢救并备份，绝不因为解析失败而中断。"""
    config = dict(DEFAULTS)
    path = config_path()
    if not path.is_file():
        return config

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return config

    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        salvaged = parse_legacy_config(raw)
        try:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        except OSError:
            pass
        if salvaged:
            config.update(salvaged)
            try:
                _atomic_write_json(path, config)
            except OSError:
                pass
        return config

    if isinstance(data, dict):
        config.update({key: value for key, value in data.items() if value is not None})
    return config


def save_config(config: Dict[str, Any]) -> Path:
    path = config_path()
    payload = dict(DEFAULTS)
    payload.update({key: value for key, value in config.items() if key in DEFAULTS})
    _atomic_write_json(path, payload)
    return path


def key_for_project(project_id: str) -> str:
    """该项目上次用的私钥文件名（没有记录时返回空字符串）。"""
    mapping = load_config().get("project_keys") or {}
    if not isinstance(mapping, dict):
        return ""
    return str(mapping.get(str(project_id or "").strip(), "") or "")


def remember_project_key(project_id: str, private_path: Path) -> None:
    """记下“这个项目用的是哪把私钥”，切回该项目时好换回来。"""
    project = str(project_id or "").strip()
    if not project:
        return
    config = load_config()
    mapping = config.get("project_keys")
    mapping = dict(mapping) if isinstance(mapping, dict) else {}
    mapping[project] = Path(private_path).name
    config["project_keys"] = mapping
    save_config(config)


def build_auth_record(
    mode: str,
    api_key: str = "",
    token: str = "",
    lifetime: int = 0,
) -> Dict[str, Any]:
    """统一 auth.json 结构：CLI 与 GUI 写同一种格式。"""
    mode = str(mode).strip().lower()
    if mode not in AUTH_MODES:
        raise ValueError(f"未知的认证方式：{mode}")
    record: Dict[str, Any] = {"mode": mode, "created_at": _now_text()}
    if mode == "api_key":
        api_key = str(api_key).strip()
        if not api_key:
            raise ValueError("API KEY 不能为空")
        record["header"] = "X-QW-Api-Key"
        record["value"] = api_key
    else:
        token = str(token).strip()
        if not token:
            raise ValueError("JWT 不能为空")
        record["header"] = "Authorization"
        record["value"] = f"Bearer {token}"
        record["expires_in"] = int(lifetime)
        record["expires_at"] = (
            datetime.now().astimezone() + timedelta(seconds=int(lifetime))
        ).replace(microsecond=0).isoformat()
    return record


def save_auth(record: Dict[str, Any]) -> Path:
    path = auth_path()
    payload = dict(record)
    payload.setdefault("created_at", _now_text())
    _atomic_write_json(path, payload)
    return path


def normalize_auth_record(data: Any) -> Dict[str, Any]:
    """把历史版本的 auth.json 归一化到统一结构。

    旧版 GUI 只写了 {"mode": "api_key", "request_command": "curl ... -H \\"...: ...\\" ..."}，
    这里从 curl 命令里把请求头还原成 header/value，避免升级后凭据"读不出来"。
    """
    if not isinstance(data, dict):
        return {}
    record = dict(data)
    if not record.get("value"):
        command = str(record.get("request_command") or "")
        match = _HEADER_PATTERN.search(command)
        if match:
            record["header"] = match.group(1).strip()
            record["value"] = match.group(2).strip()
    return record


def load_auth() -> Dict[str, Any]:
    path = auth_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return normalize_auth_record(data)


_HEADER_PATTERN = re.compile(r'-H\s+"([^":]+):\s*([^"]+)"')
