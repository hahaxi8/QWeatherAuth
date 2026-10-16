#!/usr/bin/env python3
"""和风天气认证与接口链接命令行工具。

与 GUI（qweather_auth_gui.py）共用 qweather_core.py，两者读写同一份
config.json / auth.json / 密钥，不会再出现“GUI 与 CLI 各用一套密钥”的问题。

常用命令：
    python qweather_auth.py keygen                    # 生成 Ed25519 密钥对
    python qweather_auth.py api-key <API_KEY>         # 写入 API KEY 凭据
    python qweather_auth.py jwt <凭据ID>              # 生成并写入 JWT
    python qweather_auth.py links                     # 输出全部接口链接
    python qweather_auth.py links --shell             # 输出可直接执行的 shell 脚本
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import qweather_core as core


def prompt_value(config: dict, name: str, prompt: str, force: bool = False) -> str:
    value = "" if force else str(config.get(name, "")).strip()
    if value:
        return value
    if not sys.stdin.isatty():
        raise SystemExit(f"缺少{prompt}，请先在交互终端执行一次，或使用 GUI 填写")
    value = input(f"请输入{prompt}: ").strip()
    if not value:
        raise SystemExit(f"{prompt}不能为空")
    return value


def command_keygen(args: argparse.Namespace) -> int:
    private_path, public_path = core.generate_keypair(force=args.force)
    print("Ed25519 密钥生成成功")
    print(f"私钥：{private_path}")
    print(f"公钥：{public_path}")
    try:
        fingerprint = core.public_key_fingerprint(public_path.read_bytes())
    except OSError:
        fingerprint = ""
    if fingerprint:
        print(f"公钥 SHA256：{fingerprint}")
    print("请把公钥内容上传到和风天气控制台-项目管理-JWT 凭据。")
    return 0


def command_api_key(args: argparse.Namespace) -> int:
    record = core.build_auth_record("api_key", api_key=args.api_key)
    path = core.save_auth(record)
    config = core.load_config()
    config["auth_mode"] = "api_key"
    core.save_config(config)
    print(f"API KEY 认证信息已保存：{path}")
    return 0


def command_jwt(args: argparse.Namespace) -> int:
    config = core.load_config()
    issuer = prompt_value(config, "developer_id", "开发者 ID（Developer ID）")
    subject = prompt_value(config, "project_id", "项目 ID（Project ID）")
    lifetime = core.normalize_lifetime(args.lifetime)

    try:
        token = core.create_jwt(args.credential_id, issuer, subject, lifetime)
    except FileNotFoundError:
        print("未找到 Ed25519 私钥，先执行：python qweather_auth.py keygen")
        return 2

    record = core.build_auth_record("jwt", token=token, lifetime=lifetime)
    auth_file = core.save_auth(record)
    core.secure_write(core.jwt_path(), token + "\n")
    config.update(
        {
            "auth_mode": "jwt",
            "credential_id": args.credential_id,
            "developer_id": issuer,
            "project_id": subject,
            "jwt_lifetime": lifetime,
        }
    )
    core.save_config(config)

    print(f"JWT 生成成功，有效期 {lifetime} 秒")
    print(f"Authorization: Bearer {token}")
    print(f"凭据已保存：{auth_file}")
    return 0


def command_links(args: argparse.Namespace) -> int:
    config = core.load_config()
    overrides = {
        "api_host": args.host,
        "latitude": args.lat,
        "longitude": args.lon,
        "location_name": args.city,
        "location_id": args.location_id,
        "lang": args.lang,
        "auth_mode": args.mode,
        "credential_id": args.kid,
    }
    for key, value in overrides.items():
        if value:
            config[key] = value
    if args.days:
        config["forecast_days"] = args.days
    if args.hours:
        config["forecast_hours"] = args.hours
    if args.date:
        config["time_machine_date"] = args.date

    mode = str(config.get("auth_mode", "jwt")).lower()
    if mode == "jwt":
        try:
            token = core.create_jwt(
                str(config.get("credential_id", "")),
                str(config.get("developer_id", "")),
                str(config.get("project_id", "")),
                config.get("jwt_lifetime", 900),
            )
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(f"无法生成 JWT：{exc}") from exc
        record = core.build_auth_record(
            "jwt", token=token, lifetime=int(config.get("jwt_lifetime", 900))
        )
    else:
        record = core.load_auth()
        if str(record.get("mode", "")) != "api_key":
            raise SystemExit("尚未配置 API KEY，请先执行：qweather_auth.py api-key <KEY>")

    if args.shell:
        print(core.render_shell_script(config, record))
    else:
        print(core.render_links_text(config, record, include_curl=not args.no_curl))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="和风天气认证与接口链接工具：API KEY / JWT / 全部接口链接"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("keygen", help="生成 JWT 使用的 Ed25519 密钥对")
    keygen.add_argument("--force", action="store_true", help="覆盖同名密钥")
    keygen.set_defaults(func=command_keygen)

    api_key = commands.add_parser("api-key", aliases=["apikey"], help="配置 API KEY")
    api_key.add_argument("api_key", help="控制台生成的 API KEY")
    api_key.set_defaults(func=command_api_key)

    jwt_parser = commands.add_parser("jwt", help="生成 JWT 并写入凭据")
    jwt_parser.add_argument("credential_id", help="JWT 凭据 ID（kid）")
    jwt_parser.add_argument("--lifetime", default=900, help="有效期（秒），默认 900")
    jwt_parser.set_defaults(func=command_jwt)

    links = commands.add_parser("links", help="输出全部接口链接")
    links.add_argument("--host", help="API Host，例如 abcxyz.qweatherapi.com")
    links.add_argument("--lat", help="纬度")
    links.add_argument("--lon", help="经度")
    links.add_argument("--city", help="城市名，用于 GeoAPI 查询")
    links.add_argument("--location-id", dest="location_id", help="LocationID（时光机必需）")
    links.add_argument("--lang", help="语言，默认 zh")
    links.add_argument("--mode", choices=["jwt", "api_key"], help="认证方式")
    links.add_argument("--kid", help="JWT 凭据 ID")
    links.add_argument("--days", help="每日预报天数 1-10")
    links.add_argument("--hours", help="逐小时预报小时数 1-240")
    links.add_argument("--date", help="时光机日期 yyyyMMdd")
    links.add_argument("--no-curl", action="store_true", help="只输出 URL，不输出 curl 命令")
    links.add_argument("--shell", action="store_true", help="输出可直接执行的 shell 脚本")
    links.set_defaults(func=command_links)
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
