#!/usr/bin/env python3
"""命令行入口：login / publish / api-key / create-project / discover。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import *
from .errors import ConsoleError
from .browser import *
from .payloads import *
from .session import ConsoleSession
from .credentials import *
from .account import *

__all__ = ["command_discover", "command_login", "command_publish", "command_api_key", "command_create_project", "build_parser", "main"]
def command_discover(args) -> int:
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    session = ConsoleSession(port=args.port)
    print(f"启动浏览器：{find_browser()}")
    print(f"配置目录（本机，不放共享盘）：{profile_dir()}")
    session.start(CONSOLE_SETTING)
    print("请在打开的浏览器里登录和风天气（支持微信扫码）；登录后本程序会自动抓取。")

    state = {"last": 0.0}

    def tick(remaining: float) -> None:
        now = time.time()
        if now - state["last"] < 15:
            return
        state["last"] = now
        try:
            url = session.current_url()[:80]
        except ConsoleError:
            url = "(读取中)"
        print(f"  等待登录… 剩余 {int(remaining)} 秒（当前页面：{url}）", flush=True)

    if not session.wait_for_login(timeout=args.timeout, on_tick=tick):
        print("超时未检测到登录状态")
        session.close()
        return 2

    print("已登录，开始抓取…")
    # 本地存储里常常直接存着账号信息，先抓下来
    try:
        storage = session.cdp.evaluate(
            "JSON.stringify({local: {...localStorage}, session: {...sessionStorage}})",
            await_promise=False,
        )
        (out / "storage.json").write_text(str(storage or "{}"), encoding="utf-8")
        print(f"localStorage/sessionStorage 已导出（{len(str(storage or ''))} 字符）")
    except ConsoleError as exc:
        print(f"导出本地存储失败：{exc}")

    captured: List[Dict[str, Any]] = []
    for name, url in (("setting", CONSOLE_SETTING), ("project", CONSOLE_PROJECT)):
        session.cdp.events = []
        session.navigate(url, settle=6.0)
        text = session.body_text()
        (out / f"{name}_innerText.txt").write_text(text, encoding="utf-8")
        (out / f"{name}_outerHTML.html").write_text(session.html(), encoding="utf-8")
        responses = session.collect_json_responses(wait=3.0)
        captured.append({"page": name, "url": session.current_url(), "responses": responses})
        print(f"[{name}] 文本 {len(text)} 字符，捕获接口响应 {len(responses)} 条")
        for item in responses:
            print(f"    {item['status']} {item['url'][:110]}")

    (out / "captured.json").write_text(
        json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"结果已写入：{out}")
    if not args.keep_open:
        session.close()
    return 0


def command_login(args) -> int:
    """打开浏览器登录控制台并抓取账号数据；可选写入 config.json。"""
    data = login_and_fetch(timeout=args.timeout,
                           progress=lambda text: print(text, flush=True))
    print("\n=== 抓取结果 ===")
    print(f"账号      : {data['account']['name']} {data['account']['email']}")
    print(f"API Host  : {data['api_host']}")
    print(f"开发者 ID : {data['developer_id']}")
    if data["project_id"]:
        print(f"项目      : {data['project_name']}（{data['project_id']}）")
    else:
        print("项目      : 账号下还没有项目，请先在控制台创建项目，或用 create-project 命令创建")
        print("            图形界面里会直接弹窗让你填名字，自动创建。")
        return 0
    if data["api_key"]:
        print(f"API KEY   : {data['api_key_id']}（已获取明文，长度 {len(data['api_key'])}）")
    else:
        print("API KEY   : 该项目下没有 API KEY 凭据")
    if data["jwt_credential_id"]:
        print(f"JWT 凭据  : {data['jwt_credential_id']}")
        print(f"公钥SHA256: {data['jwt_public_sha256']}")
    else:
        print("JWT 凭据  : 该项目下没有 JWT 凭据")

    if args.json:
        Path(args.json).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n完整数据已写入：{args.json}")

    if args.save:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import qweather_core as core

        config = core.load_config()
        config.update({
            "api_host": data["api_host"],
            "developer_id": data["developer_id"],
            "project_id": data["project_id"],
        })
        if data["jwt_credential_id"]:
            config["credential_id"] = data["jwt_credential_id"]
            config["auth_mode"] = "jwt"
        elif data["api_key"]:
            config["auth_mode"] = "api_key"
        core.save_config(config)
        print(f"已写入配置：{core.config_path()}")
    return 0


def command_publish(args) -> int:
    """把公钥发布到控制台（新建 JWT 凭据），无需手动上传。"""
    key_path = Path(args.public_key)
    if not key_path.is_file():
        print(f"公钥文件不存在：{key_path}")
        return 1
    data = publish_public_key(
        key_path.read_text(encoding="utf-8"),
        project_hint=args.project or "",
        name_prefix=args.prefix,
        timeout=args.timeout,
        progress=lambda text: print(text, flush=True),
    )
    print("\n=== 创建结果 ===")
    print(f"项目    : {data['project_name']}（{data['project_id']}）")
    print(f"凭据名  : {data['name']}")
    print(f"凭据 ID : {data['public_id']}   ← 这就是 JWT 的 kid")
    if args.save:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import qweather_core as core

        config = core.load_config()
        config.update({
            "project_id": data["project_id"],
            "credential_id": data["public_id"],
            "auth_mode": "jwt",
        })
        core.save_config(config)
        print(f"已写入配置：{core.config_path()}")
    return 0


def command_api_key(args) -> int:
    """在控制台新建 API KEY 凭据（名字 api+年月日时分秒）。"""
    data = create_api_key(
        project_hint=args.project,
        name_prefix=args.prefix or None,
        timeout=args.timeout,
        progress=lambda text: print(f"  {text}"),
    )
    print(f"\n已创建 API KEY 凭据：{data['name']}（{data['public_id']}）")
    print(f"项目      : {data['project_name']}（{data['project_id']}）")
    print(f"已启用 API: {', '.join(data['api_names'])}")
    print(f"控制台数据: {'已开启' if data['console_api_enabled'] else '未开启'}")
    if data["api_key"]:
        print(f"API KEY   : {data['api_key']}")
    else:
        print("API KEY   : 控制台没有返回明文密钥，请到控制台复制")

    if args.save:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import qweather_core as core

        config = core.load_config()
        config.update({
            "project_id": data["project_id"],
            "auth_mode": "api_key",
        })
        core.save_config(config)
        if data["api_key"]:
            core.save_auth(core.build_auth_record("api_key", api_key=data["api_key"]))
            print(f"API KEY 已写入：{core.auth_path()}")
        print(f"已写入配置：{core.config_path()}")
    return 0


def command_create_project(args) -> int:
    """在控制台新建项目（账号下没有项目时用）。"""
    name = args.name.strip()
    if not name:
        print("项目名不能为空")
        return 1
    session = ConsoleSession.connect()
    try:
        session.ensure_logged_in(
            timeout=args.timeout,
            on_tick=lambda left: print(f"  请在浏览器里登录控制台…剩余 {int(left)} 秒", flush=True),
        )
        if not project_name_available(session, name):
            print(f"项目名已存在：{name}")
            return 1
        project = create_project(session, name)
        print(f"\n已创建项目：{project['name']}（{project['id']}）")
        if args.save:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import qweather_core as core

            config = core.load_config()
            config["project_id"] = project["id"]
            core.save_config(config)
            print(f"已写入配置：{core.config_path()}")
        return 0
    finally:
        if session.cdp:
            try:
                session.cdp.close()
            except OSError:
                pass
            session.cdp = None


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="和风天气控制台登录与抓取")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="登录控制台并抓取 API Host / 开发者 ID / 项目 / 凭据")
    login.add_argument("--timeout", type=float, default=600.0, help="等待登录的秒数")
    login.add_argument("--json", default="", help="把完整结果写入指定 JSON 文件")
    login.add_argument("--save", action="store_true", help="同时写入 <程序目录>/data/config.json")
    login.set_defaults(func=command_login)

    publish = sub.add_parser("publish", help="把公钥发布到控制台（自动新建 JWT 凭据）")
    publish.add_argument("--public-key", required=True, help="公钥 PEM 文件路径")
    publish.add_argument("--project", default="", help="项目 ID 或名称（默认第一个项目）")
    publish.add_argument("--prefix", default="", help="新凭据名前缀（默认 JWT 用 jwb、API KEY 用 api）")
    publish.add_argument("--timeout", type=float, default=600.0, help="等待登录的秒数")
    publish.add_argument("--save", action="store_true", help="把新的凭据 ID 写入 config.json")
    publish.set_defaults(func=command_publish)

    project_cmd = sub.add_parser("create-project", help="在控制台新建项目（账号下没有项目时用）")
    project_cmd.add_argument("name", help="项目名")
    project_cmd.add_argument("--timeout", type=float, default=600.0, help="等待登录的秒数")
    project_cmd.add_argument("--save", action="store_true", help="把新项目 ID 写入 config.json")
    project_cmd.set_defaults(func=command_create_project)

    api_key = sub.add_parser("api-key", help="确保有可用的 API KEY 凭据（已有则复用，自动取回明文密钥）")
    api_key.add_argument("--project", default="", help="项目 ID 或名称（默认第一个项目）")
    api_key.add_argument("--prefix", default="", help="凭据名前缀，默认 api")
    api_key.add_argument("--timeout", type=float, default=600.0, help="等待登录的秒数")
    api_key.add_argument("--save", action="store_true", help="把 API KEY 写入 auth.json 与 config.json")
    api_key.set_defaults(func=command_api_key)

    discover = sub.add_parser("discover", help="打开浏览器等待登录并导出页面数据（开发用）")
    discover.add_argument("--out", default="console_dump", help="导出目录")
    discover.add_argument("--timeout", type=float, default=600.0, help="等待登录的秒数")
    discover.add_argument("--port", type=int, default=0, help="调试端口（默认自动分配）")
    discover.add_argument("--keep-open", action="store_true", help="抓取完成后不关闭浏览器")
    discover.set_defaults(func=command_discover)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ConsoleError as exc:
        print(f"失败：{exc}")
        return 1
