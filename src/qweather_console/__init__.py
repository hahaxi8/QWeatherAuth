#!/usr/bin/env python3
"""和风天气控制台工具包：浏览器会话、凭据管理与命令行。

拆分后各模块职责单一；这里统一再导出，`import qweather_console` 的用法保持不变。
"""

from __future__ import annotations

import subprocess  # noqa: F401 - 外部脚本会替换它做测试

from .constants import *
from .errors import ConsoleError, PublicKeyInUseError, describe_failure, raise_for_failure
from .cdp import Cdp, WebSocketClient
from .browser import *
from .payloads import *
from .session import ConsoleSession
from .credentials import *
from .account import *

__all__ = [
    "API_APPS",
    "API_APP_CHECK_NAME",
    "API_APP_CREATE",
    "API_APP_DETAIL",
    "API_APP_KEY_CHECK_NAME",
    "API_APP_KEY_CREATE",
    "API_APP_KEY_ITEM",
    "API_APP_KEY_UPDATE",
    "API_CODE_NAMES",
    "API_USER",
    "BROWSER_CANDIDATES",
    "CONSOLE_DATA_CODES",
    "CONSOLE_ERROR_HINTS",
    "CONSOLE_HOME",
    "CONSOLE_PROJECT",
    "CONSOLE_SETTING",
    "CREDENTIAL_NAME_PREFIX",
    "CREDENTIAL_NAME_PREFIX_API",
    "Cdp",
    "ConsoleSession",
    "DEFAULT_API_LIMIT",
    "DEFAULT_API_LIMIT_VALUE",
    "DEFAULT_CONSOLE_API_LIMIT_VALUE",
    "FREE_API_CODES",
    "JWT_ALGORITHM_ED25519",
    "KEY_TYPE_API_KEY",
    "KEY_TYPE_JWT",
    "LOGIN_HOST",
    "PROFILE_DIR_NAME",
    "STATE_FILE_NAME",
    "WebSocketClient",
    "api_names",
    "app_local_dir",
    "build_api_key_credential_payload",
    "build_credential_update_payload",
    "build_jwt_credential_payload",
    "build_parser",
    "build_project_payload",
    "choose_project",
    "clear_state",
    "collect_account_data",
    "command_api_key",
    "command_create_project",
    "command_discover",
    "command_login",
    "command_publish",
    "create_api_key",
    "create_project",
    "credential_type_label",
    "default_credential_name",
    "describe_console_code",
    "devtools_port_from_profile",
    "extract_account_data",
    "find_browser",
    "find_matching_jwt_credential",
    "find_profile_browser_port",
    "free_port",
    "hidden_process_kwargs",
    "http_get_json",
    "list_credentials",
    "list_projects",
    "local_public_key_fingerprints",
    "login_and_fetch",
    "main",
    "merge_console_codes",
    "normalize_project",
    "pick_api_template",
    "port_alive",
    "profile_dir",
    "project_name_available",
    "provision_credentials",
    "publish_public_key",
    "read_state",
    "state_file",
    "write_state",
    "Cdp",
    "WebSocketClient",
    "ConsoleError",
]
