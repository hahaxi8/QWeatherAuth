#!/usr/bin/env python3
"""纯数据整理与请求体构造（不依赖会话）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .constants import *
from .errors import ConsoleError

__all__ = ["describe_console_code", "default_credential_name", "credential_type_label", "normalize_project", "build_project_payload", "merge_console_codes", "build_jwt_credential_payload", "build_api_key_credential_payload", "build_credential_update_payload", "api_names"]
def describe_console_code(code: Any) -> str:
    text = str(code or "").strip()
    if not text:
        return ""
    return CONSOLE_ERROR_HINTS.get(text, f"控制台返回 code={text}")


def default_credential_name(prefix: Optional[str] = None,
                            now: Optional[datetime] = None,
                            credential_type: Any = KEY_TYPE_JWT) -> str:
    """新建凭据名：前缀 + 年月日时分秒。

    未指定前缀时按凭据类型取默认值：JWT 用 jwb、API KEY 用 api。
    """
    moment = now or datetime.now()
    text = str(prefix or "").strip()
    if not text:
        text = (CREDENTIAL_NAME_PREFIX_API if credential_type == KEY_TYPE_API_KEY
                else CREDENTIAL_NAME_PREFIX)
    return f"{text}{moment:%Y%m%d%H%M%S}"


def credential_type_label(value: Any) -> str:
    if value == KEY_TYPE_JWT:
        return "JWT"
    if value == KEY_TYPE_API_KEY:
        return "API KEY"
    return f"类型{value}"


def normalize_project(item: Any) -> Dict[str, Any]:
    item = item if isinstance(item, dict) else {}
    return {
        "id": str(item.get("uniqueCode") or ""),
        "name": str(item.get("name") or ""),
        "key_count": int(item.get("totalKeys") or 0),
    }


def build_project_payload(name: str, app_type: int = 1) -> Dict[str, Any]:
    """新建项目的请求体（照控制台前端：{appName, appType:1}）。"""
    text = str(name).strip()
    if not text:
        raise ConsoleError("项目名不能为空")
    return {"appName": text, "appType": app_type}


def merge_console_codes(current: str, required: Tuple[str, ...] = CONSOLE_DATA_CODES) -> str:
    """把控制台数据权限码补进已有取值里（不删除原有权限）。"""
    parts = [part.strip() for part in str(current or "").split(",") if part.strip()]
    for code in required:
        if code not in parts:
            parts.append(code)
    return ",".join(parts)


def build_jwt_credential_payload(name: str, public_key_pem: str,
                                 template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造新建 JWT 凭据的请求体（字段与取值照控制台前端的创建逻辑）。

    对应前端：{name, type: Jwt, apiLimit, apiLimitValue} 且 JWT 时补
    algorithm="2"（Ed25519）与 publicKey。
    """
    template = template or {}
    payload = {
        "name": str(name).strip(),
        "type": KEY_TYPE_JWT,
        "algorithm": JWT_ALGORITHM_ED25519,
        "publicKey": str(public_key_pem).strip(),
        "apiLimit": template.get("apiLimit", DEFAULT_API_LIMIT),
        "apiLimitValue": template.get("apiLimitValue") or DEFAULT_API_LIMIT_VALUE,
    }
    if not payload["name"]:
        raise ConsoleError("凭据名不能为空")
    if "BEGIN PUBLIC KEY" not in payload["publicKey"]:
        raise ConsoleError("公钥内容不是 PEM 格式（应包含 BEGIN PUBLIC KEY）")
    return payload


def build_api_key_credential_payload(name: str,
                                     template: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造新建 API KEY 凭据的请求体。

    对应控制台前端：{name, type: ApiKey, apiLimit, apiLimitValue}，
    且**不带** algorithm 与 publicKey（只有 JWT 才补这两个字段）。
    """
    template = template or {}
    payload = {
        "name": str(name).strip(),
        "type": KEY_TYPE_API_KEY,
        "apiLimit": template.get("apiLimit", DEFAULT_API_LIMIT),
        "apiLimitValue": template.get("apiLimitValue") or DEFAULT_API_LIMIT_VALUE,
    }
    if not payload["name"]:
        raise ConsoleError("凭据名不能为空")
    return payload


def build_credential_update_payload(detail: Dict[str, Any],
                                    api_limit_value: Optional[str] = None,
                                    console_api_limit_value: Optional[str] = None) -> Dict[str, Any]:
    """构造凭据编辑请求体（字段与控制台编辑页一致）。

    控制台编辑页提交：type / requestLimit / requestLimitValue / apiLimit /
    apiLimitValue / consoleApiLimitValue。
    """
    detail = detail or {}
    return {
        "type": detail.get("type", KEY_TYPE_JWT),
        "requestLimit": detail.get("requestLimit", 0),
        "requestLimitValue": detail.get("requestLimitValue", ""),
        "apiLimit": detail.get("apiLimit", DEFAULT_API_LIMIT),
        "apiLimitValue": (
            api_limit_value if api_limit_value is not None
            else detail.get("apiLimitValue") or DEFAULT_API_LIMIT_VALUE
        ),
        "consoleApiLimitValue": (
            console_api_limit_value if console_api_limit_value is not None
            else detail.get("consoleApiLimitValue", "")
        ),
    }


def api_names(api_limit_value: str) -> List[str]:
    """把 API 编号串翻译成中文名，便于界面展示。"""
    return [
        API_CODE_NAMES.get(part.strip(), part.strip())
        for part in str(api_limit_value or "").split(",")
        if part.strip()
    ]
