#!/usr/bin/env python3
"""控制台操作的错误类型与失败信息整理。"""

from __future__ import annotations

from typing import Any, Dict

__all__ = ["ConsoleError", "PublicKeyInUseError", "CODE_PUBLIC_KEY_EXIST",
           "describe_failure", "raise_for_failure"]

# 控制台前端枚举：PublicKeyExist=122（同一个公钥不能注册到第二个凭据上）
CODE_PUBLIC_KEY_EXIST = "122"


class ConsoleError(RuntimeError):
    """控制台抓取相关的可读错误。"""

    def __init__(self, message: str, code: object = None) -> None:
        super().__init__(message)
        self.code = str(code) if code is not None else ""


class PublicKeyInUseError(ConsoleError):
    """该公钥已在控制台的其它凭据里使用（code=122），需要换一把密钥。"""


def raise_for_failure(method: str, path: str, payload: Dict[str, Any], raw: str,
                      hint: str = "") -> None:
    """按响应体抛出合适的错误类型（公钥重复用专门的类型，便于调用方重试）。"""
    message = describe_failure(method, path, payload, raw, hint)
    code = payload.get("code") if isinstance(payload, dict) else None
    if str(code) == CODE_PUBLIC_KEY_EXIST:
        raise PublicKeyInUseError(message, code)
    raise ConsoleError(message, code)


def describe_failure(method: str, path: str, payload: Dict[str, Any], raw: str,
                     hint: str = "") -> str:
    """把控制台的失败响应整理成一句可读的话。

    控制台的失败原因在响应体的 message/msg/desc 里，必须原样带出来，
    否则只剩一个 code，使用者和开发者都无法定位。
    hint 是本地已知错误码的说明（未知码时为空）。
    """
    code = payload.get("code") if isinstance(payload, dict) else None
    detail = ""
    if isinstance(payload, dict):
        for key in ("message", "msg", "desc", "error", "errorMessage"):
            value = payload.get(key)
            if value:
                detail = str(value).strip()
                break
    parts = []
    if hint:
        parts.append(hint)
    if detail and detail not in parts:
        parts.append(detail)
    if not parts:
        parts.append(str(raw)[:300])
    label = f"（code={code}）" if code not in (None, "") else ""
    return f"{method} {path} 被控制台拒绝{label}：" + "；".join(parts)
