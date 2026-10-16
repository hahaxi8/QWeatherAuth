#!/usr/bin/env python3
"""HTTP 调用与错误说明：GET JSON、错误码描述、LocationID 查询。"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode
from typing import Any, Dict, List, Tuple

from .constants import *
from .params import *

__all__ = ["http_get_json", "describe_error", "lookup_location_id"]
def http_get_json(
    url: str,
    header_name: str = "",
    header_value: str = "",
    timeout: float = 10.0,
) -> Tuple[int, Dict[str, Any]]:
    """发 GET 请求并解析 JSON；官方要求处理 Gzip，这里显式声明并解压。"""
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept-Encoding", "gzip")
    request.add_header("User-Agent", f"QWeatherTool/{TOOL_VERSION}")
    if header_name and header_value:
        request.add_header(header_name, header_value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        body = exc.read()
        if (exc.headers.get("Content-Encoding", "") or "").lower() == "gzip":
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
        status = int(exc.code)
    text = body.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"服务返回的不是 JSON（HTTP {status}）：{text[:200]}") from None
    if not isinstance(data, dict):
        raise ValueError(f"服务返回结构异常（HTTP {status}）")
    return status, data


def describe_error(status: int, data: Dict[str, Any]) -> str:
    """把官方 problem+json 错误体翻译成可读提示。"""
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    title = str(error.get("title") or "").strip()
    detail = str(error.get("detail") or "").strip()
    invalid = error.get("invalidParams")
    hints = {
        400: "参数错误，请检查经纬度、日期、LocationID 等取值",
        401: "身份认证失败：检查 API KEY / JWT 是否有效，或凭据与 API Host 是否匹配",
        403: "无权限或额度不足：检查 API Host、请求限制、账号额度",
        404: "路径或路径参数错误",
        429: "请求过于频繁，请退避重试（持续 429 可能导致账号被冻结）",
        500: "和风天气服务端故障",
    }
    parts = [f"HTTP {status}"]
    if title:
        parts.append(title)
    if detail:
        parts.append(detail)
    if isinstance(invalid, list) and invalid:
        parts.append("问题参数：" + ", ".join(str(item) for item in invalid))
    if not title and not detail:
        parts.append(hints.get(status, "未知错误"))
    return "；".join(parts)


def lookup_location_id(
    host: str,
    location: str,
    header_name: str = "",
    header_value: str = "",
    lang: str = "zh",
) -> List[Dict[str, str]]:
    """调用 GeoAPI 把城市名换成 LocationID，返回 [{id, name, adm1, adm2, country}]。"""
    host = normalize_host(host)
    if not host:
        raise ValueError("查询 LocationID 需要先填写 API Host")
    location = str(location).strip()
    if not location:
        raise ValueError("请先填写城市名（例如 深圳 或 深圳,南山）")
    params = urlencode({"location": location, "number": "10", "lang": lang}, quote_via=quote)
    url = f"https://{host}/geo/v2/city/lookup?{params}"
    status, data = http_get_json(url, header_name, header_value)
    if status != 200:
        raise ValueError(describe_error(status, data))
    items = data.get("location")
    if not isinstance(items, list) or not items:
        raise ValueError(f"未查询到“{location}”对应的城市")
    results: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "adm1": str(item.get("adm1", "")),
                "adm2": str(item.get("adm2", "")),
                "country": str(item.get("country", "")),
                "lat": str(item.get("lat", "")),
                "lon": str(item.get("lon", "")),
            }
        )
    return results
