#!/usr/bin/env python3
"""参数校验与格式化：经纬度、有效期、预报范围、POI、指数、时光机日期。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Tuple

from .constants import *

__all__ = ["TIME_MACHINE_MAX_DAYS", "CITY_FORECAST_DAYS", "CITY_FORECAST_HOURS", "POI_TYPES", "normalize_host", "format_coordinate", "normalize_latitude", "normalize_longitude", "normalize_lifetime", "normalize_int", "normalize_indices_type", "normalize_indices_days", "normalize_choice", "normalize_radius_km", "normalize_country", "normalize_time_machine_date", "default_time_machine_date"]
TIME_MACHINE_MAX_DAYS = 10


CITY_FORECAST_DAYS = ("3d", "7d", "10d", "15d", "30d")


CITY_FORECAST_HOURS = ("24h", "72h", "168h")


POI_TYPES = (("scenic", "景点"), ("TSTA", "潮汐站点"))


def normalize_host(host: str) -> str:
    host = (host or "").strip()
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix):]
    return host.strip().strip("/")


def format_coordinate(value: Any, name: str, limit: float) -> str:
    """校验并规范化坐标：保留精度（最多 8 位小数），去掉多余的 0，不做两位四舍五入。

    官方文档写"最多两位小数"，但实测 9 个接口对 8 位小数均返回 200，
    且 GeoAPI 自己返回的坐标就是 5 位小数（如 39.90499），
    所以这里原样保留精度，只裁掉超过 8 位的浮点噪声。
    """
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name}不能为空")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"{name}必须是数字：{text}") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name}不是有效数字：{text}")
    if not -limit <= number <= limit:
        raise ValueError(f"{name}必须在 -{limit:g} 到 {limit:g} 之间")
    if number == 0:
        return "0"
    return f"{number:.8f}".rstrip("0").rstrip(".")


def normalize_latitude(value: Any) -> str:
    return format_coordinate(value, "纬度", 90.0)


def normalize_longitude(value: Any) -> str:
    return format_coordinate(value, "经度", 180.0)


def normalize_lifetime(value: Any) -> int:
    try:
        lifetime = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("有效期必须是整数秒") from exc
    if not 1 <= lifetime <= JWT_MAX_LIFETIME:
        raise ValueError(f"有效期必须在 1 到 {JWT_MAX_LIFETIME} 秒之间")
    return lifetime


def normalize_int(value: Any, name: str, low: int, high: int) -> str:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}必须是整数") from exc
    if not low <= number <= high:
        raise ValueError(f"{name}必须在 {low} 到 {high} 之间")
    return str(number)


def normalize_indices_type(value: Any) -> str:
    """type=0 表示全部指数，且不能与其他类型同时出现。"""
    text = str(value).strip() or "0"
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return "0"
    valid = {item[0] for item in INDICES_TYPES}
    for part in parts:
        if part not in valid:
            raise ValueError(f"天气指数类型只能是 0-16 的数字，收到：{part}")
    if "0" in parts and len(parts) > 1:
        raise ValueError("type=0 表示全部指数，不能与其他类型同时填写")
    return ",".join(parts)


def normalize_indices_days(value: Any) -> str:
    text = str(value).strip().lower() or "1d"
    if text not in ("1d", "3d"):
        raise ValueError("天气指数天数只能是 1d 或 3d")
    return text


def normalize_choice(value: Any, name: str, allowed: Tuple[str, ...], default: str) -> str:
    text = str(value or "").strip() or default
    if text not in allowed:
        raise ValueError(f"{name}只能是 {' / '.join(allowed)}")
    return text


def normalize_radius_km(value: Any) -> str:
    """POI 范围搜索的半径，单位是公里（官方 1-50，默认 5）。"""
    text = str(value if value is not None else "").strip() or "5"
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError("POI 搜索半径必须是数字（公里）") from exc
    if not 1 <= number <= 50:
        raise ValueError("POI 搜索半径必须在 1 到 50 公里之间")
    return f"{number:g}"


def normalize_country(value: Any) -> str:
    """热门城市的国家代码（ISO 3166 两位字母，例如 cn）；留空表示不限。"""
    text = str(value or "").strip().lower()
    if text and not re.fullmatch(r"[a-z]{2}", text):
        raise ValueError("国家代码应为两位字母，例如 cn（留空表示不限）")
    return text


def normalize_time_machine_date(value: Any) -> str:
    """校验时光机日期：yyyyMMdd，最近 10 天内且不含今天。"""
    text = str(value).strip() or default_time_machine_date()
    try:
        parsed = datetime.strptime(text, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("时光机日期格式必须是 yyyyMMdd，例如 20261014") from exc
    today = date.today()
    if parsed >= today:
        raise ValueError("时光机日期不能是今天或未来（当天数据尚未归档）")
    if (today - parsed).days > TIME_MACHINE_MAX_DAYS:
        raise ValueError(f"时光机仅支持最近 {TIME_MACHINE_MAX_DAYS} 天内的日期")
    return text


def default_time_machine_date() -> str:
    """时光机默认查询昨天（当天数据尚未归档，且只支持最近 10 天）。"""
    return (date.today() - timedelta(days=1)).strftime("%Y%m%d")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "是")
