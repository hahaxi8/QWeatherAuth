#!/usr/bin/env python3
"""和风天气工具的核心包：常量、路径、参数、密钥、接口表、配置与 HTTP。

拆分后各模块职责单一；这里统一再导出，`import qweather_core` 的用法保持不变。
"""

from __future__ import annotations

from .constants import *
from .paths import *
from .params import *
from .crypto import *
from .endpoints import *
from .config import *
from .http import *

__all__ = [
    "APP_TITLE",
    "AUTH_MODES",
    "CITY_FORECAST_DAYS",
    "CITY_FORECAST_HOURS",
    "DATA_DIR_ENV",
    "DATA_DIR_NAME",
    "DEFAULTS",
    "ENDPOINTS",
    "ENDPOINTS_BY_KEY",
    "Endpoint",
    "INDICES_TYPES",
    "JWT_IAT_BACKOFF",
    "JWT_MAX_LIFETIME",
    "LANGUAGES",
    "LOCATION_ID_REQUIRED",
    "POI_TYPES",
    "TIME_MACHINE_MAX_DAYS",
    "TOOL_VERSION",
    "active_key_path",
    "active_keypair",
    "active_private_key_path",
    "auth_header_line",
    "auth_path",
    "base64url",
    "build_auth_record",
    "build_request_context",
    "build_url",
    "build_urls",
    "config_path",
    "create_jwt",
    "data_dir",
    "decode_jwt",
    "default_time_machine_date",
    "describe_error",
    "ensure_data_dir",
    "format_coordinate",
    "generate_keypair",
    "http_get_json",
    "jwt_path",
    "links_path",
    "list_keypairs",
    "load_auth",
    "load_config",
    "load_private_key",
    "lookup_location_id",
    "normalize_auth_record",
    "normalize_choice",
    "normalize_country",
    "normalize_host",
    "normalize_indices_days",
    "normalize_indices_type",
    "normalize_int",
    "normalize_latitude",
    "normalize_lifetime",
    "normalize_longitude",
    "normalize_radius_km",
    "normalize_time_machine_date",
    "parse_legacy_config",
    "program_dir",
    "public_key_fingerprint",
    "public_key_fingerprints",
    "render_links_text",
    "render_shell_script",
    "save_auth",
    "save_config",
    "secure_write",
]

# 兼容旧用法：外部脚本/测试会直接引用这两个第三方名字
from cryptography.hazmat.primitives import serialization  # noqa: F401,E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,  # noqa: F401
)
