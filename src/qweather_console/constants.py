#!/usr/bin/env python3
"""控制台接口地址与枚举常量。"""

from __future__ import annotations


__all__ = ["CONSOLE_HOME", "CONSOLE_SETTING", "CONSOLE_PROJECT", "LOGIN_HOST", "BROWSER_CANDIDATES", "PROFILE_DIR_NAME", "STATE_FILE_NAME", "API_USER", "API_APPS", "API_APP_DETAIL", "API_APP_CREATE", "API_APP_CHECK_NAME", "API_APP_KEY_CREATE", "API_APP_KEY_UPDATE", "API_APP_KEY_ITEM", "API_APP_KEY_CHECK_NAME", "KEY_TYPE_API_KEY", "KEY_TYPE_JWT", "JWT_ALGORITHM_ED25519", "CREDENTIAL_NAME_PREFIX", "CREDENTIAL_NAME_PREFIX_API", "API_CODE_NAMES", "FREE_API_CODES", "CONSOLE_DATA_CODES", "DEFAULT_API_LIMIT", "DEFAULT_API_LIMIT_VALUE", "DEFAULT_CONSOLE_API_LIMIT_VALUE", "CONSOLE_ERROR_HINTS"]
CONSOLE_HOME = "https://console.qweather.com/"


CONSOLE_SETTING = "https://console.qweather.com/setting?lang=zh"


CONSOLE_PROJECT = "https://console.qweather.com/project"


LOGIN_HOST = "id.qweather.com"


BROWSER_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


PROFILE_DIR_NAME = "browser-profile"


STATE_FILE_NAME = "cdp.json"


API_USER = "/v2/rest/user"


API_APPS = "/v2/rest/app"


API_APP_DETAIL = "/v2/rest/app/{code}"


API_APP_CREATE = "/v2/rest/app"


API_APP_CHECK_NAME = "/v2/rest/app/name/{name}"


API_APP_KEY_CREATE = "/v2/rest/app/key/app/{project}"


API_APP_KEY_UPDATE = "/v2/rest/app/key/app/{project}/key/{public_id}"


API_APP_KEY_ITEM = "/v2/rest/app/key/app/{project}/key/{public_id}"


API_APP_KEY_CHECK_NAME = "/v2/rest/app/key/app/{project}/name/{name}"


KEY_TYPE_API_KEY = 3


KEY_TYPE_JWT = 7


JWT_ALGORITHM_ED25519 = "2"


CREDENTIAL_NAME_PREFIX = "jwb"


CREDENTIAL_NAME_PREFIX_API = "api"


API_CODE_NAMES = {
    "1": "天气预报", "2": "GeoAPI", "3": "分钟降水", "4": "天气预警", "5": "天气指数",
    "6": "空气质量", "7": "时光机", "8": "天文", "9": "热带气旋", "10": "海洋",
    "11": "辐照", "12": "财务汇总", "13": "请求量统计",
}


FREE_API_CODES = ("1", "2", "3", "4", "5", "6", "7", "8")


CONSOLE_DATA_CODES = ("12", "13")


DEFAULT_API_LIMIT = 1


DEFAULT_API_LIMIT_VALUE = ",".join(FREE_API_CODES)


DEFAULT_CONSOLE_API_LIMIT_VALUE = ",".join(CONSOLE_DATA_CODES)


CONSOLE_ERROR_HINTS = {
    "103": "控制台返回：凭据名已存在，请换一个名字",
    "105": "控制台返回：内容不合法（公钥格式或参数有误）",
}


_WRITE_JS = """
(() => {
  let token = '';
  try {
    const m = document.cookie.match(/(?:^|;\\s*)XSRF-TOKEN=([^;]*)/);
    token = m ? decodeURIComponent(m[1]) : '';
  } catch (e) { token = ''; }
  return fetch(%s, {
    method: %s,
    credentials: 'include',
    headers: {'Content-Type': %s, 'Accept': 'application/json', 'X-XSRF-TOKEN': token},
    body: %s
  }).then(r => r.text().then(t => ({status: r.status, body: t})))
    .catch(e => ({status: -1, body: String(e)}));
})()
"""
