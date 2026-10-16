#!/usr/bin/env python3
"""Ed25519 密钥对与 JWT：生成、指纹、签发、解析。"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typing import Any, Dict, List, Optional, Tuple

from .constants import *
from .paths import *
from .paths import _atomic_write_json
from .paths import _now_text
from .params import *

__all__ = ["activate_keypair", "keypair_by_name", "keypair_for_fingerprint", "base64url", "public_key_fingerprints",
           "public_key_fingerprint", "generate_keypair", "list_keypairs", "active_keypair",
           "active_private_key_path", "load_private_key", "create_jwt", "decode_jwt"]
def base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def public_key_fingerprints(public_pem: bytes) -> Dict[str, str]:
    """公钥的多种 SHA256 表示，用于和控制台显示值比对。

    控制台的口径文档未写死，因此这里把所有常见口径都算出来，命中任意一个即视为一致：
    - der：SubjectPublicKeyInfo 的 DER 字节
    - pem：去掉首尾空白后的 PEM 文本（控制台文档描述的口径）
    - pem_body：仅 PEM 主体（不含 BEGIN/END 行）
    - pem_file：文件原始字节（等价于 sha256sum 公钥文件）
    """
    result: Dict[str, str] = {}
    try:
        key = serialization.load_pem_public_key(public_pem)
        der = key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        result["der"] = hashlib.sha256(der).hexdigest()
    except Exception:  # noqa: BLE001 - 格式异常时只保留文本口径
        pass
    result["pem_file"] = hashlib.sha256(public_pem).hexdigest()
    text = public_pem.decode("utf-8", "replace").strip()
    if text:
        result["pem"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        body = "".join(
            line for line in text.splitlines() if not line.startswith("-----")
        ).strip()
        if body:
            result["pem_body"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return result


def public_key_fingerprint(public_pem: bytes) -> str:
    """界面展示用的公钥 SHA256 指纹（按控制台文档口径：去首尾空白后的 PEM 文本）。"""
    fingerprints = public_key_fingerprints(public_pem)
    for name in ("pem", "pem_file", "der"):
        if name in fingerprints:
            return fingerprints[name]
    return ""


def keypair_for_fingerprint(sha256: str) -> Optional[Tuple[Path, Path]]:
    """在全部本地公钥里找指纹匹配的那一对（控制台记录的是 PEM 文本的 SHA256）。

    多项目时本地会有多把密钥，命中哪把就说明那个凭据属于哪个项目。
    """
    wanted = str(sha256 or "").strip().lower()
    if not wanted:
        return None
    for private_path, public_path in list_keypairs():
        try:
            fingerprints = public_key_fingerprints(public_path.read_bytes())
        except OSError:
            continue
        if any(str(value).lower() == wanted for value in fingerprints.values()):
            return private_path, public_path
    return None


def activate_keypair(private_path: Path, public_path: Path) -> None:
    """把 active_key.json 指向指定密钥对（切换项目时用）。"""
    _atomic_write_json(
        active_key_path(),
        {
            "private_key": private_path.name,
            "public_key": public_path.name,
            "created_at": _now_text(),
        },
    )


def keypair_by_name(private_name: str) -> Optional[Tuple[Path, Path]]:
    """按私钥文件名取回密钥对；公钥缺失或文件不存在时返回 None。"""
    name = str(private_name or "").strip()
    if not name:
        return None
    directory = data_dir()
    private_path = directory / name
    public_name = name.replace("private", "public", 1) if "private" in name else ""
    public_path = directory / public_name if public_name else Path("")
    if not private_path.is_file():
        return None
    if not public_path.is_file():
        # 私钥在但公钥没了：从私钥导出一次
        try:
            private_key = load_private_key(private_path)
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            public_path = directory / (name.replace("private", "public", 1)
                                       if "private" in name
                                       else "ed25519-public.pem")
            public_path.write_bytes(public_pem)
        except Exception:  # noqa: BLE001 - 取不到就当作没有
            return None
    return private_path, public_path


def generate_keypair(force: bool = False) -> Tuple[Path, Path]:
    """生成 Ed25519 密钥对，文件名带时间戳，并把 active_key.json 指向新密钥。

    带时间戳可保留历史密钥；旧版 CLI 的固定文件名（ed25519-private.pem）
    仍被 active_keypair() 识别，因此老用户不受影响。
    """
    directory = ensure_data_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    private_path = directory / f"ed25519-private-{stamp}.pem"
    public_path = directory / f"ed25519-public-{stamp}.pem"
    # 同一秒内重复生成时自增后缀，避免覆盖或报错；force 则直接覆盖同名文件
    suffix = 1
    while not force and (private_path.exists() or public_path.exists()):
        suffix += 1
        private_path = directory / f"ed25519-private-{stamp}-{suffix}.pem"
        public_path = directory / f"ed25519-public-{stamp}-{suffix}.pem"

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    secure_write(private_path, private_pem.decode("ascii"))
    public_path.write_bytes(public_pem)
    _atomic_write_json(
        active_key_path(),
        {
            "private_key": private_path.name,
            "public_key": public_path.name,
            "created_at": _now_text(),
        },
    )
    return private_path, public_path


def list_keypairs() -> List[Tuple[Path, Path]]:
    """按修改时间倒序列出所有密钥对（比按文件名排序更可靠）。"""
    directory = data_dir()
    if not directory.is_dir():
        return []
    found = list(directory.glob("ed25519-private*.pem"))
    found.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return [
        (private_path, Path(str(private_path).replace("private", "public", 1)))
        for private_path in found
    ]


def active_keypair() -> Tuple[Path, Path]:
    """定位当前生效的密钥对，兼容三种历史命名。"""
    directory = data_dir()

    marker = active_key_path()
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            private_path = directory / str(data.get("private_key", ""))
            if private_path.is_file():
                public_path = directory / str(data.get("public_key", ""))
                if not public_path.is_file():
                    public_path = Path(str(private_path).replace("private", "public", 1))
                return private_path, public_path

    legacy_private = directory / "ed25519-private.pem"
    if legacy_private.is_file():
        return legacy_private, directory / "ed25519-public.pem"

    pairs = list_keypairs()
    if pairs:
        return pairs[0]

    raise FileNotFoundError("尚未生成 Ed25519 密钥，请先点击“一键生成公私钥”")


def active_private_key_path() -> Path:
    return active_keypair()[0]


def load_private_key(private_path: Optional[Path] = None) -> Ed25519PrivateKey:
    path = Path(private_path) if private_path else active_private_key_path()
    if not path.is_file():
        raise FileNotFoundError(f"私钥不存在：{path}")
    private_key = serialization.load_pem_private_key(path.read_bytes(), None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError(f"私钥不是 Ed25519 格式：{path.name}")
    return private_key


def create_jwt(
    kid: str,
    issuer: str,
    subject: str,
    lifetime: int = 900,
    private_path: Optional[Path] = None,
) -> str:
    """按官方规范签发 JWT：Header {alg:EdDSA, kid}，Payload {iss, sub, iat, exp}。"""
    kid = str(kid).strip()
    issuer = str(issuer).strip()
    subject = str(subject).strip()
    if not kid:
        raise ValueError("凭据 ID（kid）不能为空")
    if not issuer:
        raise ValueError("开发者 ID（iss）不能为空")
    if not subject:
        raise ValueError("项目 ID（sub）不能为空")
    lifetime = normalize_lifetime(lifetime)

    private_key = load_private_key(private_path)
    now = int(time.time())
    header = {"alg": "EdDSA", "kid": kid}
    payload = {"iss": issuer, "sub": subject, "iat": now - JWT_IAT_BACKOFF, "exp": now + lifetime}
    segments = [
        base64url(json.dumps(header, separators=(",", ":")).encode()),
        base64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    segments.append(base64url(private_key.sign(signing_input)))
    return ".".join(segments)


def decode_jwt(token: str) -> Dict[str, Any]:
    """仅解析（不验签）JWT 的 header 与 payload，便于界面展示与自检。"""
    parts = str(token).split(".")
    if len(parts) != 3:
        raise ValueError("JWT 结构不是 header.payload.signature")
    result: Dict[str, Any] = {}
    for name, segment in (("header", parts[0]), ("payload", parts[1])):
        padded = segment + "=" * (-len(segment) % 4)
        result[name] = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
    return result
