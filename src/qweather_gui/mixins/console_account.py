#!/usr/bin/env python3
"""控制台账号参数：自动读取、登录、项目创建。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox

import qweather_core as core
import qweather_console as qconsole
from ..constants import *

__all__ = ["ConsoleAccountMixin"]
class ConsoleAccountMixin:
    """控制台账号参数：自动读取、登录、项目创建。"""

    def _start_console_auto_fetch(self) -> None:
        """启动后自动读取控制台参数：已有会话就直接显示（不会自己开浏览器）。"""
        if self._closing or self._console_auto_done:
            return
        if self._console_auto_after_id is None:
            self._console_auto_after_id = self.after(
                AUTO_CONSOLE_FIRST_DELAY_MS, self._console_auto_tick
            )
    def _schedule_console_auto_retry(self) -> None:
        if self._closing or self._console_auto_done or self._console_auto_after_id is not None:
            return
        self._console_auto_after_id = self.after(AUTO_CONSOLE_RETRY_MS, self._console_auto_tick)
    def _console_auto_tick(self) -> None:
        """静默尝试一次；拿不到就过一会儿再试（不弹窗、不开浏览器）。"""
        self._console_auto_after_id = None
        if (self._closing or self._console_auto_done or self._console_auto_running
                or self._console_busy):
            self._schedule_console_auto_retry()
            return
        self._console_auto_running = True
        self._console_auto_attempt += 1
        # 每三次做一次进程扫描（要开 PowerShell，不必每轮都做）
        scan = self._console_auto_attempt % 3 == 1
        hint = self.sub_var.get().strip()          # 主线程取值，工作线程不碰 Tk

        def worker() -> None:
            data = None
            try:
                session = qconsole.ConsoleSession.attach_existing(scan=scan)
                if session is not None:
                    try:
                        if session.is_logged_in():
                            data = qconsole.collect_account_data(session, project_hint=hint)
                    finally:
                        try:
                            if session.cdp:
                                session.cdp.close()
                        except OSError:
                            pass
                        session.cdp = None
            except Exception:  # noqa: BLE001 - 静默路径，失败就等下一轮
                data = None
            self._console_queue.put(("auto", "", data))

        threading.Thread(target=worker, daemon=True).start()
    def _on_open_console(self) -> None:
        """打开控制台（本工具的浏览器实例），登录后自动显示参数。"""
        if self._console_busy:
            self._set_status("正在等待控制台登录完成…")
            return
        self._console_busy = True
        self._set_console_busy(True)
        self._set_status("正在打开控制台…（已登录会直接读取，否则请在浏览器里登录）")

        def progress(text: str) -> None:
            self._console_queue.put(("progress", text, None))

        def worker() -> None:
            try:
                data = qconsole.login_and_fetch(timeout=600.0, progress=progress)
            except Exception as exc:  # noqa: BLE001
                self._console_queue.put(("error", str(exc), None))
                return
            self._console_queue.put(("data", "", data))

        threading.Thread(target=worker, daemon=True).start()
    def _fill_account_fields(self, data: dict) -> None:
        """把控制台里读到的账号级参数填进界面。"""
        api_host = str(data.get("api_host", "")).strip()
        developer_id = str(data.get("developer_id", "")).strip()
        if api_host:
            self.host_var.set(api_host)
        if developer_id:
            self.iss_var.set(developer_id)
        if data.get("jwt_credential_id"):
            self.kid_var.set(str(data["jwt_credential_id"]))
        if data.get("api_key"):
            self.api_key_var.set(str(data["api_key"]))
        self._persist_config()
    def _ask_project_name(self, initial: str = "天气数据接口") -> str:
        """只问一个项目名：账号下没有项目时用。"""
        dialog = tk.Toplevel(self)
        dialog.title("创建项目")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("440x170")
        ttk.Label(dialog, text="还没有项目，填个名字即可创建：",
                  padding=(14, 16, 14, 6)).pack(anchor="w")
        var = tk.StringVar(value=initial)
        entry = ttk.Entry(dialog, textvariable=var, width=40)
        entry.pack(fill="x", padx=14)
        entry.focus_set()
        entry.select_range(0, "end")
        result = {"value": ""}

        def confirm(_event=None) -> None:
            result["value"] = var.get().strip()
            dialog.destroy()

        entry.bind("<Return>", confirm)
        row = ttk.Frame(dialog)
        row.pack(pady=14)
        ttk.Button(row, text="一键创建", command=confirm,
                   style="Accent.TButton").pack(side="left", padx=6)
        ttk.Button(row, text="取消", command=dialog.destroy).pack(side="left", padx=6)
        self._raise_dialog(dialog)
        dialog.wait_window()
        return result["value"]
    def _prompt_create_project_for_login(self) -> None:
        """登录后发现有账号但没项目：问个名字，直接创建。"""
        name = self._ask_project_name()
        if not name:
            self._finish_console_flow("账号下还没有项目，已取消创建")
            return
        self._set_console_busy(True)
        self._set_status(f"正在创建项目「{name}」…")
        self._run_console_step(
            lambda: self._console_create_project(name), "project_created_login"
        )
    def _apply_console_data(self, data: dict, silent: bool = False) -> None:
        projects = data.get("projects") or []
        project_id = str(data.get("project_id", "")).strip()
        project_name = str(data.get("project_name", ""))

        if not projects:
            # 账号下还没有项目：先把账号信息填上，再问一个项目名并自动创建
            self._fill_account_fields(data)
            if silent:
                self._set_status("已获取控制台账号信息；账号下还没有项目，点「凭据管理…」可以创建")
                return
            self._prompt_create_project_for_login()
            return

        known = self.sub_var.get().strip()
        match = next(
            (item for item in projects if item["id"] in (known, project_id)), None
        )
        if match is None and len(projects) == 1:
            match = projects[0]
        if match is None and not silent:
            # 多个项目且没命中：只有手动点击时才弹选择框
            chosen = self._choose_project(projects)
            if not chosen:
                self._set_status("已取消选择项目")
                return
            match = chosen
        if match is not None:
            project_id = match["id"]
            project_name = match.get("name", project_name)

        self._fill_account_fields(data)
        if project_id:
            self.sub_var.set(project_id)
            self._persist_config()

        if silent:
            self._set_status(
                "已自动获取控制台参数："
                + f"API Host {str(data.get('api_host', '')).strip() or '（未变）'}"
                + f"，项目 {project_name or project_id or '（未变）'}"
                + ("，API KEY 已获取" if data.get("api_key") else "")
            )
            return

        account = data.get("account") or {}
        lines = [
            f"账号：{account.get('name', '')} {account.get('email', '')}".strip(),
            f"API Host：{data.get('api_host', '')}",
            f"开发者 ID：{data.get('developer_id', '')}",
            f"项目：{data.get('project_name', '')}（{project_id}）",
        ]
        if data.get("jwt_credential_id"):
            lines.append(f"JWT 凭据 ID：{data['jwt_credential_id']}")
        if data.get("api_key"):
            lines.append(f"API KEY：已获取（ID {data.get('api_key_id', '')}）")
        key_note = self._compare_console_public_key(str(data.get("jwt_public_sha256", "")))
        if key_note:
            lines.append("")
            lines.append(key_note)
        lines.append("")
        lines.append("界面已自动填写，配置已保存。")

        self._set_status("已从控制台自动填写完成")
        messagebox.showinfo(APP_TITLE, "\n".join(lines))
    def _choose_project(self, projects: list) -> dict:
        dialog = tk.Toplevel(self)
        dialog.title("选择项目")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("460x260")
        ttk.Label(dialog, text="账号下有多个项目，请选择要使用的项目：",
                  padding=(12, 10, 12, 4)).pack(anchor="w")
        listbox = tk.Listbox(dialog, font=("Microsoft YaHei UI", 10))
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        for item in projects:
            listbox.insert("end", f"{item['name']}　ID: {item['id']}")
        listbox.selection_set(0)
        result: dict = {}

        def confirm() -> None:
            selection = listbox.curselection()
            if selection:
                result.update(projects[selection[0]])
            dialog.destroy()

        ttk.Button(dialog, text="使用选中项目", command=confirm).pack(pady=(0, 12))
        dialog.wait_window()
        return result
    def _compare_console_public_key(self, console_sha256: str) -> str:
        """把本地公钥指纹和控制台上传的公钥 SHA256 对比，避免 JWT 静默 401。

        本地可能有多把密钥（每个项目一把），这里遍历全部：
        命中就切到那把并记到当前项目，之后签发 JWT 才不会 401。
        """
        if not console_sha256:
            return ""
        pairs = core.list_keypairs()
        if not pairs:
            return ("本地还没有 Ed25519 密钥对：点「凭据管理…」里的「一键生成」即可创建并上传公钥。")
        pair = core.keypair_for_fingerprint(console_sha256)
        if pair is None:
            return (
                "⚠ 控制台该 JWT 凭据里记录的公钥指纹，与本地所有密钥都对不上，"
                "用 JWT 会返回 401。可在「凭据管理…」里点「一键生成」换一把密钥新建凭据。"
            )
        core.activate_keypair(*pair)
        project = self.sub_var.get().strip()
        if project:
            core.remember_project_key(project, pair[0])
        self._refresh_key_info()
        return f"✔ 公钥已核对：控制台上传的公钥就是本地的 {pair[1].name}，JWT 可用。"
