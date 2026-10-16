#!/usr/bin/env python3
"""凭据相关业务：项目与凭据查询、创建、一键备齐。"""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from .constants import *
from .errors import ConsoleError, PublicKeyInUseError
from .payloads import *
from .session import ConsoleSession
from .account import choose_project

__all__ = ["list_projects", "list_credentials", "project_name_available", "create_project", "local_public_key_fingerprints", "find_matching_jwt_credential", "pick_api_template", "provision_credentials", "publish_public_key", "create_api_key"]
def list_projects(session: "ConsoleSession") -> List[Dict[str, Any]]:
    """列出账号下的项目（标准化为 {id, name, key_count}）。"""
    apps = session.fetch_api(API_APPS)
    if not isinstance(apps, list):
        return []
    return [normalize_project(item) for item in apps]


def list_credentials(session: "ConsoleSession", project_code: str) -> List[Dict[str, Any]]:
    """列出项目下的凭据（含类型与已上传公钥指纹）。"""
    detail = session.fetch_api(API_APP_DETAIL.format(code=project_code))
    result: List[Dict[str, Any]] = []
    for item in (detail.get("keyList") or []):
        if not isinstance(item, dict):
            continue
        entry = {
            "id": str(item.get("publicId") or ""),
            "name": str(item.get("name") or ""),
            "type": item.get("type"),
            "type_label": credential_type_label(item.get("type")),
            "sha256": str(item.get("sha256") or ""),
            "key": str(item.get("key") or ""),          # API KEY 凭据的明文密钥
            "create_time": str(item.get("createTime") or ""),
        }
        result.append(entry)
    return result


def project_name_available(session: "ConsoleSession", name: str) -> bool:
    """项目名是否可用（占用时返回非空）。"""
    data = session.fetch_api(API_APP_CHECK_NAME.format(name=urllib.parse.quote(str(name).strip())))
    return not data


def create_project(session: "ConsoleSession", name: str) -> Dict[str, Any]:
    """新建项目，返回 {id, name}。"""
    payload = build_project_payload(name)
    result = session.write_json("PUT", API_APP_CREATE, payload)
    data = result.get("data")
    if isinstance(data, dict) and data.get("uniqueCode"):
        return {"id": str(data["uniqueCode"]), "name": str(data.get("name") or payload["appName"])}
    # 控制台有的版本只返回成功标记，这时回读一次列表
    for item in list_projects(session):
        if item["name"] == payload["appName"]:
            return {"id": item["id"], "name": item["name"]}
    raise ConsoleError(f"项目已创建，但没能取到项目 ID：{str(result)[:200]}")


def local_public_key_fingerprints(public_key_pem: str) -> set:
    """本地公钥的多种 SHA256 口径（与控制台记录的 sha256 比对用）。"""
    try:
        import qweather_core as core  # 同目录，按需导入避免循环依赖

        return {value.lower() for value in core.public_key_fingerprints(
            public_key_pem.encode("utf-8")).values()}
    except Exception:  # noqa: BLE001 - 拿不到指纹时退化为"找不到匹配"
        return set()


def find_matching_jwt_credential(session: "ConsoleSession", project_code: str,
                                 fingerprints: set) -> Optional[Dict[str, Any]]:
    """项目里是否已有"上传公钥与本地公钥一致"的 JWT 凭据。"""
    if not fingerprints:
        return None
    wanted = {str(item).strip().lower() for item in fingerprints if item}
    try:
        detail = session.fetch_api(API_APP_DETAIL.format(code=project_code))
    except ConsoleError:
        return None
    for item in (detail.get("keyList") or []):
        if not isinstance(item, dict) or item.get("type") != KEY_TYPE_JWT:
            continue
        public_id = str(item.get("publicId") or "")
        if not public_id:
            continue
        try:
            info = session.credential_detail(project_code, public_id)
        except ConsoleError:
            continue
        sha = str(info.get("sha256") or "").lower()
        if sha and sha in wanted:
            return {
                "public_id": public_id,
                "name": str(info.get("name") or ""),
                "sha256": sha,
                "console_api_limit_value": str(info.get("consoleApiLimitValue") or ""),
                "api_limit_value": str(info.get("apiLimitValue") or ""),
            }
    return None


def pick_api_template(session: "ConsoleSession", project_code: str) -> Optional[Dict[str, Any]]:
    """挑一个已有凭据作为「启用 API」的模板：优先 JWT，其次同项目任意凭据。"""
    try:
        detail = session.fetch_api(API_APP_DETAIL.format(code=project_code))
    except ConsoleError:
        return None
    key_list = detail.get("keyList") if isinstance(detail, dict) else None
    ordered = sorted(
        [item for item in (key_list or []) if isinstance(item, dict)],
        key=lambda item: 0 if item.get("type") == KEY_TYPE_JWT else 1,
    )
    for item in ordered:
        try:
            candidate = session.credential_detail(project_code, str(item.get("publicId", "")))
        except ConsoleError:
            continue
        if candidate.get("apiLimitValue"):
            return candidate
    return None


def _ensure_jwt_credential(session: "ConsoleSession", project: Dict[str, Any],
                           public_key_pem: str, fingerprints: Optional[set] = None,
                           name_prefix: Optional[str] = None, note=None) -> Dict[str, Any]:
    """确保项目里有与本地公钥匹配的 JWT 凭据：已有则复用，没有才新建。"""
    def say(text: str) -> None:
        if note:
            note(text)

    project_code = str(project.get("uniqueCode") or "").strip()
    project_name = str(project.get("name") or "")
    keys = fingerprints if fingerprints is not None else local_public_key_fingerprints(public_key_pem)

    say("检查是否已有匹配的 JWT 凭据…")
    existing = find_matching_jwt_credential(session, project_code, keys)
    if existing:
        console_value = existing.get("console_api_limit_value", "")
        console_enabled = set(CONSOLE_DATA_CODES) <= {
            part.strip() for part in str(console_value).split(",") if part.strip()
        }
        if not console_enabled:
            try:
                detail = session.credential_detail(project_code, existing["public_id"])
                update = build_credential_update_payload(
                    detail, console_api_limit_value=merge_console_codes(console_value)
                )
                session.write_json(
                    "POST",
                    API_APP_KEY_UPDATE.format(project=project_code,
                                              public_id=existing["public_id"]),
                    update,
                )
                console_enabled = True
            except ConsoleError:
                console_enabled = False
        say(f"已存在匹配的 JWT 凭据「{existing['name']}」，直接复用")
        api_value = str(existing.get("api_limit_value") or DEFAULT_API_LIMIT_VALUE)
        return {
            "name": str(existing["name"]),
            "public_id": str(existing["public_id"]),
            "api_limit_value": api_value,
            "api_count": len(api_names(api_value)),
            "api_names": api_names(api_value),
            "api_from_existing": True,
            "console_api_enabled": console_enabled,
            "reused": True,
        }

    template = pick_api_template(session, project_code)
    base_name = default_credential_name(name_prefix, credential_type=KEY_TYPE_JWT)
    name = _unique_credential_name(session, project_code, base_name, say)
    say(f"正在创建 JWT 凭据 {name}…")
    created = session.create_jwt_credential(
        project_code, name, public_key_pem, template, allow_console_data=True
    )
    api_value = str((template or {}).get("apiLimitValue") or DEFAULT_API_LIMIT_VALUE)
    return {
        "name": str(created.get("name") or name),
        "public_id": str(created.get("publicId") or ""),
        "api_limit_value": api_value,
        "api_count": len(api_names(api_value)),
        "api_names": api_names(api_value),
        "api_from_existing": bool(template),
        "console_api_enabled": bool(created.get("console_api_enabled")),
        "reused": False,
    }


def _ensure_api_key_credential(session: "ConsoleSession", project: Dict[str, Any],
                               name_prefix: Optional[str] = None, note=None) -> Dict[str, Any]:
    """确保项目里有 API KEY 凭据：已有则取回明文密钥，没有才新建。"""
    def say(text: str) -> None:
        if note:
            note(text)

    project_code = str(project.get("uniqueCode") or "").strip()
    say("检查是否已有 API KEY 凭据…")
    for item in list_credentials(session, project_code):
        if item.get("type") != KEY_TYPE_API_KEY:
            continue
        api_key = str(item.get("key") or "")
        if not api_key:
            try:
                api_key = str(session.credential_detail(project_code, item["id"]).get("key") or "")
            except ConsoleError:
                api_key = ""
        say(f"已存在 API KEY 凭据「{item['name']}」，直接复用")
        return {
            "name": item["name"],
            "public_id": item["id"],
            "api_key": api_key,
            "api_limit_value": DEFAULT_API_LIMIT_VALUE,
            "api_names": api_names(DEFAULT_API_LIMIT_VALUE),
            "api_from_existing": True,
            "console_api_enabled": None,   # 复用时不改设置，也不去校验
            "reused": True,
        }

    template = pick_api_template(session, project_code)
    base_name = default_credential_name(name_prefix, credential_type=KEY_TYPE_API_KEY)
    name = _unique_credential_name(session, project_code, base_name, say)
    say(f"正在创建 API KEY 凭据 {name}…")
    created = session.create_api_key_credential(project_code, name, template)
    api_value = str((template or {}).get("apiLimitValue") or DEFAULT_API_LIMIT_VALUE)
    return {
        "name": str(created.get("name") or name),
        "public_id": str(created.get("publicId") or ""),
        "api_key": str(created.get("key") or ""),
        "api_limit_value": api_value,
        "api_names": api_names(api_value),
        "api_from_existing": bool(template),
        "console_api_enabled": bool(created.get("console_api_enabled")),
        "reused": False,
    }


def _unique_credential_name(session: "ConsoleSession", project_code: str, base_name: str,
                            note=None) -> str:
    """凭据名占用时追加 -1/-2…；连续 20 个都占用则报错。"""
    name = base_name
    if note:
        note(f"检查凭据名 {name} 是否可用…")
    for suffix in range(1, 20):
        if session.credential_name_available(project_code, name):
            return name
        name = f"{base_name}-{suffix}"
    raise ConsoleError("连续 20 个凭据名都被占用，请换一个前缀")


def provision_credentials(project_hint: str = "", name_prefix: Optional[str] = None,
                          public_key_pem: str = "", fingerprints: Optional[set] = None,
                          timeout: float = 600.0, progress=None, key_provider=None) -> Dict[str, Any]:
    """一次把项目里该有的凭据备齐：JWT 凭据 + API KEY 凭据，已有的直接复用。

    供界面「一键生成」使用：本地公钥与项目里已有的 JWT 凭据匹配就不再新建；
    项目里已有 API KEY 凭据就直接取回明文密钥。
    name_prefix 只作用于 JWT 凭据；API KEY 凭据固定用 api 前缀。

    同一个公钥在控制台只能注册到一个凭据上：若返回 code=122（PublicKeyExist），
    说明这把公钥已经用在别的项目里了，此时用 key_provider() 换一把新密钥重试一次。
    """
    def note(text: str) -> None:
        if progress:
            progress(text)

    session = ConsoleSession.connect()
    try:
        note("检查控制台登录状态…")
        session.ensure_logged_in(
            timeout=timeout,
            on_tick=lambda left: note(f"请在浏览器里登录控制台…剩余 {int(left)} 秒"),
        )
        note("读取项目列表…")
        apps = session.fetch_api(API_APPS)
        project = choose_project(apps, project_hint)
        project_code = str(project.get("uniqueCode") or "").strip()
        if not project_code:
            raise ConsoleError("没有取到项目 ID，请确认控制台里已创建项目")

        # 公钥已注册在其它凭据上时（code=122），换一把新密钥再试一次
        for attempt in (1, 2):
            try:
                jwt_result = _ensure_jwt_credential(
                    session, project, public_key_pem, fingerprints, name_prefix, note
                )
                break
            except PublicKeyInUseError:
                if key_provider is None or attempt == 2:
                    raise
                note("该公钥已在控制台其它凭据中使用，生成新的密钥对后重试…")
                public_key_pem, fingerprints = key_provider()
        # API KEY 凭据始终用自己默认的前缀（api），不沿用界面上的 JWT 前缀
        api_result = _ensure_api_key_credential(session, project, None, note)
        note("完成")
        return {
            "project_id": project_code,
            "project_name": str(project.get("name") or ""),
            "jwt": jwt_result,
            "api_key": api_result,
        }
    finally:
        if session.cdp:
            try:
                session.cdp.close()
            except OSError:
                pass
            session.cdp = None


def publish_public_key(public_key_pem: str, project_hint: str = "",
                       name_prefix: Optional[str] = None,
                       timeout: float = 600.0, progress=None,
                       fingerprints: Optional[set] = None) -> Dict[str, Any]:
    """确保控制台存在与本地公钥匹配的 JWT 凭据。

    - 项目里已有"上传公钥与本地公钥一致"的 JWT 凭据 → **直接复用，不新建**；
    - 没有 → 新建一个名为「前缀+年月日时分秒」（如 jwb20261015172350）的 JWT 凭据。

    返回的 public_id 即 JWT 的 kid。
    """
    def note(text: str) -> None:
        if progress:
            progress(text)

    session = ConsoleSession.connect()
    try:
        note("检查控制台登录状态…")
        session.ensure_logged_in(
            timeout=timeout,
            on_tick=lambda left: note(f"请在浏览器里登录控制台…剩余 {int(left)} 秒"),
        )
        note("读取项目列表…")
        apps = session.fetch_api(API_APPS)
        project = choose_project(apps, project_hint)
        project_code = str(project.get("uniqueCode") or "").strip()
        if not project_code:
            raise ConsoleError("没有取到项目 ID，请确认控制台里已创建项目")

        result = _ensure_jwt_credential(
            session, project, public_key_pem, fingerprints, name_prefix, note
        )
        result["project_id"] = project_code
        result["project_name"] = str(project.get("name") or "")
        return result
    finally:
        if session.cdp:
            try:
                session.cdp.close()
            except OSError:
                pass
            session.cdp = None


def create_api_key(project_hint: str = "", name_prefix: Optional[str] = None,
                   timeout: float = 600.0, progress=None) -> Dict[str, Any]:
    """确保控制台存在可用的 API KEY 凭据：已有则取回明文密钥，没有才新建。

    新建时名字为「前缀+年月日时分秒」，默认前缀 `api`（如 api20261015190000）；
    "启用 API"设置沿用项目里已有凭据的选择，并打开"访问控制台数据"权限。
    """
    def note(text: str) -> None:
        if progress:
            progress(text)

    session = ConsoleSession.connect()
    try:
        note("检查控制台登录状态…")
        session.ensure_logged_in(
            timeout=timeout,
            on_tick=lambda left: note(f"请在浏览器里登录控制台…剩余 {int(left)} 秒"),
        )

        note("读取项目列表…")
        apps = session.fetch_api(API_APPS)
        project = choose_project(apps, project_hint)
        project_code = str(project.get("uniqueCode") or "").strip()
        if not project_code:
            raise ConsoleError("没有取到项目 ID，请确认控制台里已创建项目")

        result = _ensure_api_key_credential(session, project, name_prefix, note)
        api_value = str(result.get("api_limit_value") or DEFAULT_API_LIMIT_VALUE)
        result.setdefault("api_limit_value", api_value)
        result.setdefault("api_count", len(api_names(api_value)))
        result.setdefault("api_names", api_names(api_value))
        result.setdefault("api_from_existing", True)
        result.setdefault("console_api_enabled", False)
        result["project_id"] = project_code
        result["project_name"] = str(project.get("name") or "")
        return result
    finally:
        if session.cdp:
            try:
                session.cdp.close()
            except OSError:
                pass
            session.cdp = None
