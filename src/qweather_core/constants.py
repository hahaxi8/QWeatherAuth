#!/usr/bin/env python3
"""全局常量：程序名称、语言、指标类型、鉴权方式、JWT 上限与配置默认值。"""

from __future__ import annotations

from typing import Any, Dict, Tuple

__all__ = ["APP_TITLE", "TOOL_VERSION", "LANGUAGES", "INDICES_TYPES", "AUTH_MODES", "JWT_MAX_LIFETIME", "JWT_IAT_BACKOFF", "DEFAULTS"]
APP_TITLE = "和风天气接口生成工具"


TOOL_VERSION = "2.0"


LANGUAGES = ["zh", "zh-Hant", "en", "ja", "ko", "fr", "de", "es", "ru"]


INDICES_TYPES: Tuple[Tuple[str, str], ...] = (
    ("0", "全部（推荐）"),
    ("1", "运动"),
    ("2", "洗车"),
    ("3", "穿衣"),
    ("4", "钓鱼"),
    ("5", "紫外线"),
    ("6", "旅游"),
    ("7", "花粉过敏"),
    ("8", "舒适度"),
    ("9", "感冒"),
    ("10", "空气污染扩散条件"),
    ("11", "空调开启"),
    ("12", "太阳镜"),
    ("13", "化妆"),
    ("14", "晾晒"),
    ("15", "交通"),
    ("16", "防晒"),
)


AUTH_MODES = ("jwt", "api_key")


JWT_MAX_LIFETIME = 86400


JWT_IAT_BACKOFF = 30


DEFAULTS: Dict[str, Any] = {
    "api_host": "",
    "latitude": "22.53",
    "longitude": "113.94",
    "lang": "zh",
    "location_name": "深圳",
    "location_label": "",
    "location_id": "",
    "local_time": True,
    "auth_mode": "jwt",
    # 项目 ID → 该项目使用的私钥文件名：同一个公钥在控制台只能注册一次，
    # 因此多项目各自需要不同的密钥对，切回项目时要换回对应密钥
    "project_keys": {},
    "credential_id": "",
    "developer_id": "",
    "project_id": "",
    "jwt_lifetime": 900,
    "credential_name_prefix": "jwb",
    "forecast_days": 3,
    "forecast_hours": 24,
    "indices_type": "0",
    "indices_days": "1d",
    "time_machine_date": "",
    "geo_range": "cn",
    "poi_type": "scenic",
    "poi_radius_km": "5",
    "city_forecast_days": "3d",
    "city_forecast_hours": "24h",
}
