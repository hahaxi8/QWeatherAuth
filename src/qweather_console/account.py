#!/usr/bin/env python3
"""账号数据抓取：项目选择、字段提取、一条龙登录抓取。"""

from __future__ import annotations

from typing import Any, Dict, List

from .constants import *
from .errors import ConsoleError
from .session import ConsoleSession

__all__ = ["choose_project", "extract_account_data", "collect_account_data", "login_and_fetch"]
def choose_project(apps: Any, hint: str = "") -> Dict[str, Any]:
    """从项目列表中选一个：优先匹配名称或项目 ID，否则取第一个。"""
    if not isinstance(apps, list) or not apps:
        raise ConsoleError("账号下还没有项目，请先在控制台创建项目")
    hint = str(hint or "").strip().lower()
    if hint:
        for app in apps:
            if not isinstance(app, dict):
                continue
            name = str(app.get("name", "")).lower()
            code = str(app.get("uniqueCode", "")).lower()
            if hint == code or hint in name:
                return app
    return apps[0]


def extract_account_data(user: Any, apps: Any, detail: Any) -> Dict[str, Any]:
    """把控制台接口返回整理成程序需要的字段。"""
    if not isinstance(user, dict):
        raise ConsoleError("账号信息结构异常")
    api_host = str(user.get("subDomain") or "").strip()
    developer_id = str(user.get("uniqueCode") or "").strip()
    if not api_host:
        raise ConsoleError("控制台没有返回 API Host，请确认账号已开通开发服务")
    if not developer_id:
        raise ConsoleError("控制台没有返回开发者 ID")

    # 没有项目时不再直接报错：先把账号信息带回去，由调用方（界面/命令行）引导创建
    project: Dict[str, Any] = {}
    if isinstance(apps, list) and apps:
        project = choose_project(apps)
    project_id = str(project.get("uniqueCode") or "").strip()
    keys = detail.get("keyList") if isinstance(detail, dict) else None
    keys = keys if isinstance(keys, list) else []

    api_key = api_key_id = ""
    jwt_credential_id = jwt_public_sha256 = ""
    credentials: List[Dict[str, Any]] = []
    for item in keys:
        if not isinstance(item, dict):
            continue
        entry = {
            "name": str(item.get("name", "")),
            "id": str(item.get("publicId", "")),
            "type": item.get("type"),
        }
        if item.get("type") == KEY_TYPE_API_KEY and not api_key_id:
            api_key = str(item.get("key") or "")
            api_key_id = entry["id"]
            entry["has_key"] = bool(api_key)
        elif item.get("type") == KEY_TYPE_JWT and not jwt_credential_id:
            jwt_credential_id = entry["id"]
            jwt_public_sha256 = str(item.get("sha256") or "")
            entry["sha256"] = jwt_public_sha256
        credentials.append(entry)

    return {
        "api_host": api_host,
        "developer_id": developer_id,
        "project_id": project_id,
        "project_name": str(project.get("name") or ""),
        "api_key": api_key,
        "api_key_id": api_key_id,
        "jwt_credential_id": jwt_credential_id,
        "jwt_public_sha256": jwt_public_sha256,
        "credentials": credentials,
        "projects": [
            {"id": str(item.get("uniqueCode", "")), "name": str(item.get("name", ""))}
            for item in apps if isinstance(item, dict)
        ],
        "account": {
            "name": str(user.get("realName") or ""),
            "email": str(user.get("email") or ""),
            "phone": str(user.get("phone") or ""),
        },
    }


def collect_account_data(session: "ConsoleSession", project_hint: str = "",
                         progress=None) -> Dict[str, Any]:
    """按顺序读取：账号信息 → 项目列表 → 项目凭据。"""
    def note(text: str) -> None:
        if progress:
            progress(text)

    note("读取账号信息…")
    user = session.fetch_api(API_USER)
    note("读取项目列表…")
    apps = session.fetch_api(API_APPS)
    detail: Dict[str, Any] = {}
    if isinstance(apps, list) and apps:
        project = choose_project(apps, project_hint)
        note(f"读取项目「{project.get('name', '')}」的凭据…")
        detail = session.fetch_api(API_APP_DETAIL.format(code=project.get("uniqueCode", "")))
    else:
        note("账号下还没有项目")
    return extract_account_data(user, apps, detail)


def login_and_fetch(project_hint: str = "", timeout: float = 600.0,
                    progress=None) -> Dict[str, Any]:
    """一条龙：复用/打开浏览器 → 必要时等用户登录 → 抓取账号数据。

    登录始终在真实浏览器里由用户完成，程序不接触账号密码。
    """
    session = ConsoleSession.connect()
    try:
        def tick(remaining: float) -> None:
            if progress:
                progress(f"等待登录… 剩余 {int(remaining)} 秒")

        if progress:
            progress("已连接浏览器，正在检查登录状态…")
        session.ensure_logged_in(timeout=timeout, on_tick=tick)
        return collect_account_data(session, project_hint, progress)
    finally:
        # 浏览器保持打开以便复用登录态，只断开调试连接
        if session.cdp:
            try:
                session.cdp.close()
            except OSError:
                pass
            session.cdp = None
