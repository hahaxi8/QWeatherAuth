#!/usr/bin/env python3
"""接口表与链接渲染：端点定义、请求上下文、URL 与 curl/shell 输出。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlencode
from typing import Any, Dict, List, Tuple

from .constants import *
from .params import *
from .params import _as_bool

__all__ = ["Endpoint", "ENDPOINTS", "ENDPOINTS_BY_KEY", "LOCATION_ID_REQUIRED", "build_request_context", "build_url", "build_urls", "auth_header_line", "render_links_text", "render_shell_script"]
@dataclass(frozen=True)
class Endpoint:
    key: str
    name: str
    group: str
    path: str
    query: Dict[str, str] = field(default_factory=dict)
    note: str = ""
    doc_url: str = ""
    deprecated: bool = False
    # 需要 LocationID（而不是经纬度）的接口，缺 ID 时给出提示
    needs_location_id: bool = False


ENDPOINTS: Tuple[Endpoint, ...] = (
    Endpoint(
        key="geo_city_lookup",
        name="GeoAPI 城市搜索",
        group="GeoAPI",
        path="/geo/v2/city/lookup",
        query={"location": "{location_name}", "number": "10", "lang": "{lang}"},
        note="城市名 / LocationID / “经度,纬度” 换 LocationID，时光机必须用 LocationID",
        doc_url="https://dev.qweather.com/docs/api/geoapi/city-lookup/",
    ),
    Endpoint(
        key="geo_top_city",
        name="GeoAPI 热门城市",
        group="GeoAPI",
        path="/geo/v2/city/top",
        query={"range": "{geo_range}", "number": "10", "lang": "{lang}"},
        note="range 为 ISO 3166 国家代码（默认 cn，留空则不限国家）",
        doc_url="https://dev.qweather.com/docs/api/geoapi/top-city/",
    ),
    Endpoint(
        key="geo_poi_lookup",
        name="GeoAPI POI 搜索",
        group="GeoAPI",
        path="/geo/v2/poi/lookup",
        query={"location": "{location_lonlat}", "type": "{poi_type}", "number": "10", "lang": "{lang}"},
        note="type 只支持 scenic（景点）/ TSTA（潮汐站点）；可另加 city=LocationID 限定范围",
        doc_url="https://dev.qweather.com/docs/api/geoapi/poi-lookup/",
    ),
    Endpoint(
        key="geo_poi_range",
        name="GeoAPI POI 范围搜索",
        group="GeoAPI",
        path="/geo/v2/poi/range",
        query={"location": "{location_lonlat}", "type": "{poi_type}",
               "radius": "{poi_radius_km}", "number": "10", "lang": "{lang}"},
        note="location 只接受“经度,纬度”；radius 单位为公里（1-50，默认 5）；"
             "若返回 No Such Location，通常是该坐标附近没有对应类型的 POI 数据，可换坐标或加大半径",
        doc_url="https://dev.qweather.com/docs/api/geoapi/poi-range/",
    ),
    Endpoint(
        key="weather_current",
        name="实时天气",
        group="天气预报",
        path="/weather/v1/current/{latitude}/{longitude}",
        query={"localTime": "{local_time}", "lang": "{lang}"},
        note="天气现象、温度、体感、湿度、风、降水、气压、能见度、紫外线等",
        doc_url="https://dev.qweather.com/docs/api/weather/weather-current/",
    ),
    Endpoint(
        key="weather_daily",
        name="每日天气预报",
        group="天气预报",
        path="/weather/v1/daily/{latitude}/{longitude}",
        query={"days": "{forecast_days}", "localTime": "{local_time}", "lang": "{lang}"},
        note="days 取值 1-10（官方默认 7）",
        doc_url="https://dev.qweather.com/docs/api/weather/weather-daily-forecast/",
    ),
    Endpoint(
        key="weather_hourly",
        name="逐小时天气预报",
        group="天气预报",
        path="/weather/v1/hourly/{latitude}/{longitude}",
        query={"hours": "{forecast_hours}", "localTime": "{local_time}", "lang": "{lang}"},
        note="hours 取值 1-240（官方默认 24）",
        doc_url="https://dev.qweather.com/docs/api/weather/weather-hourly-forecast/",
    ),
    Endpoint(
        key="weather_city_now_v7",
        name="城市实时天气（按 LocationID）",
        group="天气预报",
        path="/v7/weather/now",
        query={"location": "{location_query}", "lang": "{lang}"},
        note="WebAPI v7 城市版，官方已标注弃用（停服 2027-06-01），新项目建议用上面的 v1 实时天气",
        doc_url="https://dev.qweather.com/docs/api/weather/weather-now-webapi-v7/",
        deprecated=True,
    ),
    Endpoint(
        key="weather_city_daily_v7",
        name="城市每日预报（按 LocationID）",
        group="天气预报",
        path="/v7/weather/{city_forecast_days}",
        query={"location": "{location_query}", "lang": "{lang}"},
        note="路径天数可选 3d/7d/10d/15d/30d；官方已标注弃用（停服 2027-06-01）",
        doc_url="https://dev.qweather.com/docs/api/weather/weather-daily-forecast-webapi-v7/",
        deprecated=True,
    ),
    Endpoint(
        key="weather_city_hourly_v7",
        name="城市小时预报（按 LocationID）",
        group="天气预报",
        path="/v7/weather/{city_forecast_hours}",
        query={"location": "{location_query}", "lang": "{lang}"},
        note="路径小时数可选 24h/72h/168h；官方已标注弃用（停服 2027-06-01）",
        doc_url="https://dev.qweather.com/docs/api/weather/weather-hourly-forecast-webapi-v7/",
        deprecated=True,
    ),
    Endpoint(
        key="minutely_precipitation",
        name="分钟级降水",
        group="分钟预报",
        path="/v7/minutely/5m",
        query={"location": "{location_lonlat}", "lang": "{lang}"},
        note="中国区域未来 2 小时、每 5 分钟更新；location 为“经度,纬度”",
        doc_url="https://dev.qweather.com/docs/api/minutely/minutely-precipitation/",
    ),
    Endpoint(
        key="air_current",
        name="实时空气质量",
        group="空气质量",
        path="/airquality/v1/current/{latitude}/{longitude}",
        query={"lang": "{lang}"},
        note="官方文档未记录 localTime 参数，故不带该参数",
        doc_url="https://dev.qweather.com/docs/api/air-quality/air-current/",
    ),
    Endpoint(
        key="air_daily",
        name="每日空气质量",
        group="空气质量",
        path="/airquality/v1/daily/{latitude}/{longitude}",
        query={"lang": "{lang}"},
        note="固定返回未来 3 天，官方文档无 days 参数",
        doc_url="https://dev.qweather.com/docs/api/air-quality/air-daily-forecast/",
    ),
    Endpoint(
        key="weather_warning",
        name="实时天气预警",
        group="预警",
        path="/weatheralert/v1/current/{latitude}/{longitude}",
        query={"localTime": "{local_time}", "lang": "{lang}"},
        note="服务段是 weatheralert，不是 warning",
        doc_url="https://dev.qweather.com/docs/api/warning/weather-alert/",
    ),
    Endpoint(
        key="indices_daily",
        name="天气生活指数",
        group="天气指数",
        path="/v7/indices/{indices_days}",
        query={"type": "{indices_type}", "location": "{location_query}", "lang": "{lang}"},
        note="days 仅支持 1d / 3d；type=0 表示全部且不可与其他混用",
        doc_url="https://dev.qweather.com/docs/api/indices/indices-forecast/",
    ),
    Endpoint(
        key="time_machine",
        name="时光机（历史天气）",
        group="时光机",
        path="/v7/historical/weather",
        query={"location": "{location_id}", "date": "{time_machine_date}", "lang": "{lang}"},
        note="仅支持 LocationID（不支持经纬度），日期需在最近 10 天内且不含今天",
        doc_url="https://dev.qweather.com/docs/api/time-machine/time-machine-weather/",
        needs_location_id=True,
    ),
)


ENDPOINTS_BY_KEY = {item.key: item for item in ENDPOINTS}


LOCATION_ID_REQUIRED = tuple(item.key for item in ENDPOINTS if item.needs_location_id)


def build_request_context(config: Dict[str, Any]) -> Dict[str, str]:
    """把配置整理成 URL 模板可用的上下文。"""
    latitude = normalize_latitude(config.get("latitude", DEFAULTS["latitude"]))
    longitude = normalize_longitude(config.get("longitude", DEFAULTS["longitude"]))
    location_id = str(config.get("location_id") or "").strip()
    local_time = config.get("local_time", DEFAULTS["local_time"])
    location_query = location_id or f"{longitude},{latitude}"
    return {
        "latitude": latitude,
        "longitude": longitude,
        # 分钟预报 / 天气指数的 location 是“经度,纬度”，不是“纬度,经度”
        "location_lonlat": f"{longitude},{latitude}",
        # 城市版接口（v7）与指数接口都接受 LocationID 或“经度,纬度”
        "location_query": location_query,
        "location_id": location_id,
        "location_name": str(config.get("location_name") or DEFAULTS["location_name"]).strip(),
        "lang": str(config.get("lang") or DEFAULTS["lang"]).strip(),
        "local_time": "true" if _as_bool(local_time) else "false",
        "forecast_days": normalize_int(
            config.get("forecast_days", DEFAULTS["forecast_days"]), "预报天数", 1, 10
        ),
        "forecast_hours": normalize_int(
            config.get("forecast_hours", DEFAULTS["forecast_hours"]), "预报小时数", 1, 240
        ),
        "indices_type": normalize_indices_type(config.get("indices_type", DEFAULTS["indices_type"])),
        "indices_days": normalize_indices_days(config.get("indices_days", DEFAULTS["indices_days"])),
        "time_machine_date": normalize_time_machine_date(config.get("time_machine_date")),
        "geo_range": normalize_country(config.get("geo_range", DEFAULTS["geo_range"])),
        "poi_type": normalize_choice(
            config.get("poi_type"), "POI 类型", tuple(item[0] for item in POI_TYPES), "scenic"
        ),
        "poi_radius_km": normalize_radius_km(config.get("poi_radius_km", DEFAULTS["poi_radius_km"])),
        "city_forecast_days": normalize_choice(
            config.get("city_forecast_days"), "城市预报天数", CITY_FORECAST_DAYS, "3d"
        ),
        "city_forecast_hours": normalize_choice(
            config.get("city_forecast_hours"), "城市预报小时数", CITY_FORECAST_HOURS, "24h"
        ),
    }


def build_url(host: str, endpoint: Endpoint, context: Dict[str, str]) -> str:
    host = normalize_host(host)
    if not host:
        raise ValueError("API Host 不能为空，请在和风天气控制台-设置中查看")
    path = endpoint.path.format(**context)
    if endpoint.query:
        params = {key: str(value).format(**context) for key, value in endpoint.query.items()}
        params = {key: value for key, value in params.items() if value != ""}
        if params:
            path = f"{path}?{urlencode(params, quote_via=quote)}"
    return f"https://{host}{path}"


def build_urls(config: Dict[str, Any]) -> List[Tuple[Endpoint, str]]:
    """按端点表顺序生成全部接口链接。"""
    context = build_request_context(config)
    return [(item, build_url(config.get("api_host", ""), item, context)) for item in ENDPOINTS]


def auth_header_line(record: Dict[str, Any]) -> str:
    header = str(record.get("header", "")).strip()
    value = str(record.get("value", "")).strip()
    return f"{header}: {value}" if header and value else ""


def render_links_text(
    config: Dict[str, Any],
    auth: Dict[str, Any],
    include_curl: bool = True,
    token_lifetime: int = 0,
) -> str:
    """把全部接口链接渲染成可直接粘贴到 Linux 的文本。"""
    urls = build_urls(config)
    header_line = auth_header_line(auth)
    context = build_request_context(config)
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append(f"{APP_TITLE} v{TOOL_VERSION} —— 全部接口链接")
    lines.append("=" * 70)
    lines.append(f"API Host  : {normalize_host(config.get('api_host', ''))}")
    lines.append(f"位置      : {context['latitude']},{context['longitude']}")
    if context["location_id"]:
        lines.append(f"LocationID: {context['location_id']}")
    lines.append(f"语言      : {context['lang']}")
    lines.append(f"生成时间  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    mode = str(auth.get("mode", "")).lower()
    lines.append(f"认证方式  : {'JWT（临时令牌）' if mode == 'jwt' else 'API KEY'}")
    if header_line:
        lines.append(f"认证头    : {header_line}")
    if token_lifetime:
        expire_at = datetime.now() + timedelta(seconds=int(token_lifetime))
        lines.append(
            f"有效期至  : {expire_at.strftime('%Y-%m-%d %H:%M:%S')}"
            f"（{int(token_lifetime)} 秒，过期后请重新生成）"
        )
    lines.append("")
    lines.append(f"共 {len(urls)} 个接口。")

    for item, url in urls:
        lines.append("")
        lines.append("-" * 70)
        title = f"【{item.group}】{item.name}"
        if item.deprecated:
            title += "（官方已弃用，建议优先用新版接口）"
        lines.append(title)
        if item.note:
            lines.append(f"说明：{item.note}")
        if item.needs_location_id and not context["location_id"]:
            lines.append("⚠ 缺少 LocationID，此链接无法直接使用：请先用 GeoAPI 查询并填入 LocationID")
        lines.append(f"URL：{url}")
        if include_curl and header_line:
            lines.append(f'curl --compressed -H "{header_line}" "{url}"')

    lines.append("")
    lines.append("-" * 70)
    lines.append("提示：请按官方要求注明数据来源“天气服务由和风天气驱动”。")
    lines.append("      错误处理请参考 HTTP 状态码（400/401/403/404/429/500），429 需退避重试。")
    return "\n".join(lines)


def render_shell_script(config: Dict[str, Any], auth: Dict[str, Any]) -> str:
    """生成可在 Linux 直接执行的 shell 脚本。"""
    urls = build_urls(config)
    header_line = auth_header_line(auth)
    header_name, _, header_value = header_line.partition(": ")
    lines = [
        "#!/bin/sh",
        f"# {APP_TITLE} v{TOOL_VERSION} 自动生成",
        f"# 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# 注意：JWT 有效期较短，过期后请重新生成本脚本。",
        "",
        "request() {",
        f'    curl --compressed -H "{header_name}: {header_value}" "$1"',
        '    echo ""',
        "}",
        "",
    ]
    for item, url in urls:
        lines.append(f'echo "===== {item.group} / {item.name} ====="')
        lines.append(f'request "{url}"')
        lines.append("")
    return "\n".join(lines)
