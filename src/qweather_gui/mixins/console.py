#!/usr/bin/env python3
"""凭据管理窗口：项目/凭据列表、一键生成、结果应用。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
import webbrowser
from tkinter import filedialog, messagebox
from typing import Optional

import qweather_core as core
import qweather_console as qconsole
from ..constants import *

__all__ = ["ConsoleFlowMixin"]
class ConsoleFlowMixin:
    """凭据管理窗口：项目/凭据列表、一键生成、结果应用。"""

    def _set_console_busy(self, busy: bool) -> None:
        self._console_busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.manage_button, self.console_button):
            button.configure(state=state)
    def _finish_console_flow(self, message: str = "") -> None:
        self._destroy_picker()
        self._set_console_busy(False)
        if message:
            self._set_status(message)
    def _on_manage_credentials(self) -> None:
        """打开「凭据管理」窗口：选项目、选凭据，或新建 JWT / API KEY 凭据。"""
        if self._console_busy:
            self._set_status("上一个控制台操作还没结束，请稍等…")
            return
        self._set_console_busy(True)
        self._open_picker()
        self._set_status("正在读取控制台的项目列表…")
        self._run_console_step(self._console_load_projects, "projects")
    def _run_console_step(self, func, kind: str) -> None:
        """在工作线程执行一个控制台步骤，结果投递回主线程。"""
        def worker() -> None:
            try:
                payload = func()
            except Exception as exc:  # noqa: BLE001
                self._console_queue.put(("console_error", str(exc), None))
                return
            self._console_queue.put((kind, "", payload))

        threading.Thread(target=worker, daemon=True).start()
    def _console_progress(self, text: str) -> None:
        self._console_queue.put(("progress", text, None))
    def _with_session(self, action):
        """在工作线程里开一个控制台会话（复用已登录浏览器）执行 action。"""
        session = qconsole.ConsoleSession.connect()
        try:
            session.ensure_logged_in(
                timeout=600.0,
                on_tick=lambda left: self._console_progress(
                    f"请在浏览器里登录控制台…剩余 {int(left)} 秒"
                ),
            )
            return action(session)
        finally:
            if session.cdp:
                try:
                    session.cdp.close()
                except OSError:
                    pass
                session.cdp = None
    def _console_load_projects(self):
        return self._with_session(qconsole.list_projects)
    def _console_create_project(self, name: str):
        return self._with_session(lambda session: qconsole.create_project(session, name))
    def _console_load_credentials(self, project: dict):
        credentials = self._with_session(
            lambda session: qconsole.list_credentials(session, project["id"])
        )
        return {"project": project, "credentials": credentials}
    def _open_picker(self) -> None:
        """打开唯一的「选择项目与凭据」窗口；之后所有刷新都在这个窗口内完成。"""
        if self._picker_state:
            self._picker_state["dialog"].lift()
            return
        dialog = tk.Toplevel(self)
        dialog.title("凭据管理")
        dialog.transient(self)
        dialog.geometry("780x430")
        dialog.protocol("WM_DELETE_WINDOW", self._close_picker)

        body = ttk.Frame(dialog, padding=(12, 10, 12, 6))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(1, weight=1)

        ttk.Label(body, text="项目（点一行即切换，右侧随之刷新）").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="该项目的凭据（双击某条可直接选用它）").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )

        projects_list = tk.Listbox(body, font=("Microsoft YaHei UI", 10), exportselection=False)
        projects_list.grid(row=1, column=0, sticky="nsew")
        credentials_list = tk.Listbox(body, font=("Microsoft YaHei UI", 10), exportselection=False)
        credentials_list.grid(row=1, column=1, sticky="nsew", padx=(12, 0))

        create_row = ttk.Frame(body)
        create_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(create_row, text="没有项目？新建").pack(side="left")
        new_project_var = tk.StringVar()
        entry = ttk.Entry(create_row, textvariable=new_project_var, width=14)
        entry.pack(side="left", padx=(6, 6))
        ttk.Button(create_row, text="创建",
                   command=lambda: self._create_project_in_picker(new_project_var.get())).pack(side="left")

        status = ttk.Label(body, text="正在读取项目列表…", style="Hint.TLabel",
                           wraplength=360, justify="left")
        status.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(8, 0))

        footer = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        ttk.Button(footer, text="一键生成", command=self._start_picker_provision,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(footer, text="重新生成密钥", command=self._on_generate_keys).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(footer, text="取消", command=self._close_picker).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="打开公钥目录", command=self._on_open_key_dir).pack(side="right")
        ttk.Button(footer, text="控制台项目管理",
                   command=lambda: webbrowser.open(CONSOLE_PROJECT_URL)).pack(
            side="right", padx=(0, 8)
        )

        self._picker_state = {
            "dialog": dialog, "projects_list": projects_list, "credentials_list": credentials_list,
            "status": status, "new_project_var": new_project_var, "entry": entry,
            "projects": [], "credentials": [], "project": None, "select_id": "",
        }
        projects_list.bind("<<ListboxSelect>>", lambda _e: self._picker_project_changed())
        credentials_list.bind("<Double-Button-1>", lambda _e: self._confirm_picker())
        entry.bind("<Return>", lambda _e: self._create_project_in_picker(new_project_var.get()))
        entry.focus_set()
    def _destroy_picker(self) -> None:
        state, self._picker_state = self._picker_state, None
        if state:
            try:
                state["dialog"].destroy()
            except tk.TclError:
                pass
    def _close_picker(self) -> None:
        self._destroy_picker()
        self._finish_console_flow("已取消")
    def _picker_project_changed(self) -> None:
        state = self._picker_state
        if not state:
            return
        selection = state["projects_list"].curselection()
        if not selection or selection[0] >= len(state["projects"]):
            return
        project = state["projects"][selection[0]]
        if state.get("project") and state["project"]["id"] == project["id"] and state["credentials"]:
            return  # 同一个项目不重复拉取
        state["project"] = project
        state["credentials"] = []
        state["credentials_list"].delete(0, "end")
        state["credentials_list"].insert("end", "正在读取…")
        state["status"].configure(text=f"正在读取项目「{project['name']}」的凭据…")
        self._run_console_step(lambda: self._console_load_credentials(project), "credentials")
    def _create_project_in_picker(self, name: str) -> None:
        state = self._picker_state
        name = str(name).strip()
        if not state or not name:
            return
        state["new_project_var"].set("")
        state["status"].configure(text=f"正在创建项目「{name}」…")
        self._run_console_step(lambda: self._console_create_project(name), "project_created")
    def _confirm_picker(self) -> None:
        """使用窗口里选中的项目与凭据（不新建、不改密钥）。"""
        state = self._picker_state
        if not state or not state.get("project"):
            return
        selection = state["credentials_list"].curselection()
        if not state["credentials"] or not selection:
            state["status"].configure(text="请先在右侧选择一个凭据")
            return
        project = state["project"]
        credential = state["credentials"][selection[0]]
        self.sub_var.set(project["id"])

        if credential.get("type") == qconsole.KEY_TYPE_API_KEY:
            # API KEY 凭据：填 API KEY 字段（kid 是 JWT 专用的，不动）
            key = self._apply_api_key_field(credential)
            self._destroy_picker()
            self._finish_console_flow(
                f"已选用 API KEY 凭据 {credential['name']}（{credential['id']}）"
            )
            messagebox.showinfo(APP_TITLE, "\n".join([
                "已选用控制台里的现有 API KEY 凭据：",
                f"  项目：{project['name']}（{project['id']}）",
                f"  凭据：{credential['name']}（{credential['id']}）",
                "",
                ("已填入 API KEY 并保存到 auth.json。" if key
                 else "控制台没有返回明文密钥，请在控制台该凭据页面复制后粘贴到 API KEY 输入框。"),
            ]))
            return

        self.kid_var.set(credential["id"])
        self._persist_config()

        matched = self._credential_matches_local_key(credential)
        if matched is False:
            if messagebox.askyesno(
                APP_TITLE,
                "该凭据里上传的公钥与你的本地私钥不是同一对，用它签发的 JWT 会返回 401。\n\n"
                "是否改为「一键生成」（会用当前密钥新建 JWT 凭据）？",
            ):
                self._start_picker_provision()
                return

        self._destroy_picker()
        self._finish_console_flow(f"已选用凭据 {credential['name']}（{credential['id']}）")
        header = [
            "已选用控制台里的现有凭据：",
            f"  项目：{project['name']}（{project['id']}）",
            f"  凭据：{credential['name']}（{credential['id']}）",
            f"  类型：{credential['type_label']}",
            "",
        ]
        if matched is True:
            messagebox.showinfo(APP_TITLE, "\n".join(
                header + ["该凭据的公钥与本地私钥一致，JWT 可以直接使用。"]))
        elif matched is False:
            messagebox.showwarning(APP_TITLE, "\n".join(
                header + ["该凭据的公钥与本地私钥不一致，用它签发的 JWT 会返回 401。",
                          "想换成可用的，请点「凭据管理…」里的「新建 JWT 凭据」。"]))
        else:
            messagebox.showinfo(APP_TITLE, "\n".join(
                header + ["本地还没有密钥，无法核对公钥。"]))
    def _start_picker_provision(self) -> None:
        """一键备齐：JWT 凭据（本地公钥）+ API KEY 凭据，已有的直接复用。"""
        state = self._picker_state
        project = (state or {}).get("project")
        if not project:
            return
        self._destroy_picker()
        self._set_status("正在检查并创建凭据…")
        self._run_console_step(
            lambda: self._console_provision(project["id"], None), "provisioned"
        )
    @staticmethod
    def _key_material(public_path):
        """返回 (PEM 文本, 公钥指纹集合)。"""
        public_pem = public_path.read_text(encoding="utf-8")
        fingerprints = {
            value.lower()
            for value in core.public_key_fingerprints(public_path.read_bytes()).values()
        }
        return public_pem, fingerprints

    def _project_keypair(self, project_code: str):
        """该项目该用哪把密钥：有记录就用记录那把，否则用当前密钥并记下。"""
        name = core.key_for_project(project_code)
        if name:
            pair = core.keypair_by_name(name)
            if pair:
                core.activate_keypair(*pair)
                return pair
        try:
            private_path, public_path = core.active_keypair()
        except FileNotFoundError:
            private_path, public_path = core.generate_keypair()
        core.remember_project_key(project_code, private_path)
        return private_path, public_path

    def _console_provision(self, project_code: str, name_prefix: Optional[str] = None):
        """工作线程：确保本地有密钥对，并把 JWT / API KEY 凭据都备好。

        同一个公钥在控制台只能注册到一个凭据上：先切回该项目原来用的密钥；
        若该公钥已被别的项目占用（控制台返回 code=122 PublicKeyExist），
        就生成一把新密钥并记住它属于本项目，然后自动重试。
        """
        _private_path, public_path = self._project_keypair(project_code)
        self._console_progress(f"使用本地密钥 {public_path.name}")
        public_pem, fingerprints = self._key_material(public_path)

        def fresh_key():
            new_private, new_public = core.generate_keypair()
            core.remember_project_key(project_code, new_private)
            self._console_progress(f"已生成新密钥 {new_public.name}（本项目专用）")
            return self._key_material(new_public)

        return qconsole.provision_credentials(
            project_hint=project_code, name_prefix=name_prefix,
            public_key_pem=public_pem, fingerprints=fingerprints,
            timeout=600.0, progress=self._console_progress, key_provider=fresh_key,
        )
    def _apply_provisioned(self, data: dict) -> None:
        project_id = str(data.get("project_id", ""))
        jwt = data.get("jwt") or {}
        api = data.get("api_key") or {}
        if project_id:
            self.sub_var.set(project_id)
        if jwt.get("public_id"):
            self.kid_var.set(str(jwt["public_id"]))
            self.auth_mode_var.set("jwt")
        key = str(api.get("api_key") or "")
        if key:
            self.api_key_var.set(key)
            try:
                core.save_auth(core.build_auth_record("api_key", api_key=key))
            except Exception:  # noqa: BLE001 - 保存失败不影响界面填写
                pass
        self._persist_config()
        self._set_status("凭据已就绪：JWT 与 API KEY 都能用，可以直接生成链接")
        lines = [
            "凭据已就绪：",
            f"  项目：{data.get('project_name', '')}（{project_id}）",
            f"  JWT 凭据：{jwt.get('name', '')}（{jwt.get('public_id', '')}）"
            + ("　复用已有的，未新建" if jwt.get("reused") else "　已新建"),
            f"  API KEY 凭据：{api.get('name', '')}（{api.get('public_id', '')}）"
            + ("　复用已有的，未新建" if api.get("reused") else "　已新建"),
        ]
        if jwt.get("reused") or api.get("reused"):
            lines.append("")
            lines.append("已存在可直接使用的凭据，所以没有重复创建。")
        if key:
            lines.append("")
            lines.append(f"API KEY：{key}")
        lines.append("")
        lines.append("已填入界面并保存，点「一键生成所有链接」即可。")
        messagebox.showinfo(APP_TITLE, "\n".join(lines))
    @staticmethod
    def _credential_line(item: dict) -> str:
        """凭据列表的一行；API KEY 凭据本来就没有公钥，不要显示成「未上传公钥」。"""
        if item.get("type") == qconsole.KEY_TYPE_JWT:
            tail = f"公钥 {item['sha256'][:12]}" if item.get("sha256") else "公钥（未上传）"
        elif item.get("type") == qconsole.KEY_TYPE_API_KEY:
            key = str(item.get("key") or "")
            tail = (f"密钥 {key[:4]}…{key[-4:]}" if len(key) > 8
                    else "密钥（控制台未返回）")
        else:
            tail = ""
        return f"{item['name']}　[{item['type_label']}]　ID {item['id']}　{tail}"
    def _handle_projects(self, projects: list) -> None:
        """项目列表回来了：填进左栏并自动选中第一个（同一窗口内刷新）。"""
        state = self._picker_state
        if not state:
            return
        state["projects"] = projects
        state["projects_list"].delete(0, "end")
        if not projects:
            state["projects_list"].insert("end", "（账号下还没有项目）")
            state["status"].configure(
                text="在左下角输入名字并点「创建」，创建成功后本窗口会自动刷新。"
            )
            state["new_project_var"].set("天气数据接口")
            state["entry"].focus_set()
            return
        for item in projects:
            state["projects_list"].insert(
                "end", f"{item['name']}　凭据 {item['key_count']} 个　ID {item['id']}"
            )
        index = 0
        if state.get("select_id"):
            for position, item in enumerate(projects):
                if item["id"] == state["select_id"]:
                    index = position
                    break
            state["select_id"] = ""
        state["projects_list"].selection_clear(0, "end")
        state["projects_list"].selection_set(index)
        state["projects_list"].activate(index)
        state["projects_list"].see(index)
        self._picker_project_changed()
    def _handle_credentials(self, payload: dict) -> None:
        """凭据列表回来了：填进右栏（忽略过期响应）。"""
        state = self._picker_state
        if not state:
            return
        if not state.get("project") or state["project"]["id"] != payload["project"]["id"]:
            return
        credentials = payload["credentials"]
        state["credentials"] = credentials
        state["credentials_list"].delete(0, "end")
        if credentials:
            for item in credentials:
                state["credentials_list"].insert("end", self._credential_line(item))
            state["credentials_list"].selection_set(0)
        else:
            state["credentials_list"].insert("end", "（该项目下还没有凭据）")
        text = (f"项目「{state['project']['name']}」共 {len(credentials)} 个凭据"
                + ("" if credentials else "；可点「新建凭据（同步当前密钥）」创建"))
        state["status"].configure(text=text)
        self._set_status(text)
    def _credential_matches_local_key(self, credential: dict):
        """该凭据的公钥是否在本地。

        本地可能存着多把密钥（每个项目一把），所以遍历全部密钥对；
        命中时顺手切到那把密钥并记到项目上，JWT 才不会 401。
        返回 True=匹配、False=本地有密钥但都不匹配、None=本地没有密钥/该凭据没有公钥。
        """
        sha = str(credential.get("sha256") or "").strip().lower()
        if not sha:
            return None
        if not core.list_keypairs():
            return None
        pair = core.keypair_for_fingerprint(sha)
        if pair is None:
            return False
        core.activate_keypair(*pair)
        project = self.sub_var.get().strip()
        if project:
            core.remember_project_key(project, pair[0])
        self._refresh_key_info()
        return True
    def _apply_api_key_field(self, credential: dict) -> str:
        """把 API KEY 凭据里的明文密钥填进界面并保存到 auth.json。"""
        key = str(credential.get("key") or "").strip()
        if key:
            self.api_key_var.set(key)
            try:
                core.save_auth(core.build_auth_record("api_key", api_key=key))
            except Exception:  # noqa: BLE001 - 保存失败不影响界面填写
                pass
        self._persist_config()
        return key
