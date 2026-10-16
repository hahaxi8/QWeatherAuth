#!/usr/bin/env python3
"""一键打包：把 src/qweather_auth_gui.py 打包成 dist/QWeatherAuth.exe。

直接运行即可（Windows 上双击或用 python 运行）：

    python build_exe.py             # 打包到 dist/QWeatherAuth.exe
    python build_exe.py --verify    # 打包后再启动一次，确认能正常打开
    python build_exe.py --keep      # 保留 build/ 中间产物（排查用）

脚本会做这些事：
1. 检查入口文件与图标是否存在；
2. 缺 PyInstaller 时自动安装；
3. 关闭正在运行的 QWeatherAuth.exe（否则覆盖不了）；
4. 调用 PyInstaller 打包，产物留在 dist/；
5. 清理 build/ 与 *.spec 中间产物（dist/ 保留）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
DIST_DIR = ROOT / "dist"
ASSETS_DIR = ROOT / "assets"
ENTRY = SRC_DIR / "qweather_auth_gui.py"
ICON = ASSETS_DIR / "icon.ico"
EXE_NAME = "QWeatherAuth"
APP_TITLE = "和风天气接口生成工具"
TARGET = DIST_DIR / f"{EXE_NAME}.exe"


def say(message: str = "") -> None:
    print(message, flush=True)


def hidden_process_kwargs() -> dict:
    """Windows 下不让辅助命令弹出控制台窗口。"""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def check_layout() -> None:
    missing = [path for path in (ENTRY, ICON) if not path.is_file()]
    if missing:
        raise SystemExit("缺少必要文件：\n  " + "\n  ".join(str(path) for path in missing))
    if not (SRC_DIR / "qweather_gui").is_dir():
        raise SystemExit(f"源码目录不完整，找不到 {SRC_DIR / 'qweather_gui'}")
    DIST_DIR.mkdir(exist_ok=True)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        return
    except ImportError:
        pass
    say("未检测到 PyInstaller，正在自动安装…")
    code = subprocess.call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    if code != 0:
        raise SystemExit("PyInstaller 安装失败，请手动执行：python -m pip install pyinstaller")


def running_pids() -> list:
    """正在运行的 QWeatherAuth.exe 进程号。"""
    if os.name != "nt":
        return []
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {EXE_NAME}.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20, check=False,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in (result.stdout or "").splitlines():
        parts = [item.strip('"') for item in line.split('","')]
        if len(parts) >= 2 and parts[0].lower().endswith(".exe") and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def stop_running_app() -> None:
    pids = running_pids()
    if not pids:
        return
    say(f"检测到正在运行的 {EXE_NAME}.exe（PID {', '.join(map(str, pids))}），先关闭它…")
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False, **hidden_process_kwargs())
    for _ in range(10):
        if not running_pids():
            return
        time.sleep(0.5)
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False, **hidden_process_kwargs())
    time.sleep(1.0)


def clean_intermediate() -> None:
    """只清中间产物：build/ 与 *.spec；dist/ 里是最终产物，保留。"""
    build_dir = ROOT / "build"
    if build_dir.is_dir():
        shutil.rmtree(build_dir, ignore_errors=True)
    for spec in ROOT.glob("*.spec"):
        try:
            spec.unlink()
        except OSError:
            pass


def run_pyinstaller() -> None:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onefile", "--windowed",
        "--name", EXE_NAME,
        "--icon", str(ICON),
        "--add-data", f"{ICON}{os.pathsep}.",
        "--distpath", str(DIST_DIR),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        str(ENTRY),
    ]
    say("开始打包…（首次或改动较大时约需 1-2 分钟）")
    code = subprocess.call(command, cwd=str(ROOT))
    if code != 0:
        raise SystemExit(f"PyInstaller 打包失败（退出码 {code}）")


def locate_exe() -> Path:
    if not TARGET.is_file():
        raise SystemExit(f"没有找到打包产物：{TARGET}")
    return TARGET


def verify_exe(seconds: float = 8.0) -> bool:
    """启动一次，确认进程能稳定存活（能存活说明窗口正常创建）。"""
    say("启动一次做验证…")
    process = subprocess.Popen([str(TARGET)])
    deadline = time.time() + seconds
    while time.time() < deadline:
        if process.poll() is not None:
            say(f"验证失败：程序启动后立即退出（退出码 {process.returncode}）")
            return False
        time.sleep(0.4)
    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=False, **hidden_process_kwargs())
    say("验证通过：程序启动后保持运行")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=f"打包 {APP_TITLE}")
    parser.add_argument("--verify", action="store_true", help="打包后启动一次，确认能正常打开")
    parser.add_argument("--keep", action="store_true", help="保留 build/ 与 dist/ 中间产物")
    parser.add_argument("--no-pause", action="store_true", help="结束后不等待按键（供脚本调用）")
    args = parser.parse_args()

    try:
        check_layout()
        ensure_pyinstaller()
        stop_running_app()
        run_pyinstaller()
        target = locate_exe()
        size_mb = target.stat().st_size / 1024 / 1024
        say()
        say(f"打包完成：{target}")
        say(f"文件大小：{size_mb:.1f} MB")
        ok = True
        if args.verify:
            ok = verify_exe()
        if not args.keep:
            clean_intermediate()
            say("已清理 build/ 与 *.spec（dist/ 里的 exe 保留）")
        say()
        say(f"双击 {target.relative_to(ROOT)} 即可使用。")
        return 0 if ok else 1
    except SystemExit as exc:
        say(f"\n打包失败：{exc}")
        return 1
    finally:
        if not args.no_pause and sys.stdin is not None and sys.stdin.isatty():
            try:
                input("\n按回车键退出…")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    sys.exit(main())
