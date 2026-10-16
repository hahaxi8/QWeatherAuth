#!/usr/bin/env python3
"""后台线程结果轮询：查询队列与控制台队列。"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import filedialog, messagebox

import qweather_core as core
import qweather_console as qconsole
from ..constants import *

__all__ = ["QueueMixin"]
class QueueMixin:
    """后台线程结果轮询：查询队列与控制台队列。"""

    def _start_lookup_poller(self) -> None:
        """在主线程轮询后台查询结果（Tk 不允许从其他线程访问界面）。"""
        if self._closing:
            return
        try:
            self._drain_lookup_queue()
        except tk.TclError:  # 窗口已销毁
            return
        self._poll_after_id = self.after(LOOKUP_POLL_MS, self._start_lookup_poller)
    def _drain_lookup_queue(self) -> None:
        while True:
            try:
                sequence, manual, error, results = self._lookup_queue.get_nowait()
            except queue.Empty:
                break
            if error is not None:
                self._lookup_failed(error, sequence, manual)
            else:
                self._show_lookup_results(results, sequence, manual)
        # 控制台抓取的结果（工作线程只投递，不碰界面）
        while True:
            try:
                kind, text, payload = self._console_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "progress":
                self._set_status(text)
            elif kind == "error":
                self._console_busy = False
                self.console_button.configure(state="normal")
                self._show_error(ValueError(text))
            elif kind == "data":
                self._finish_console_flow()
                self._apply_console_data(payload)
            elif kind == "project_created_login":
                self._finish_console_flow()
                self.sub_var.set(str(payload.get("id", "")))
                self._persist_config()
                self._set_status(
                    f"已创建项目「{payload.get('name', '')}」，接下来点「凭据管理…」创建凭据"
                )
                messagebox.showinfo(APP_TITLE, "\n".join([
                    "已在控制台创建项目：",
                    f"  {payload.get('name', '')}（{payload.get('id', '')}）",
                    "",
                    "项目下还没有凭据。点「凭据管理…」，再点「新建 JWT 凭据」或「新建 API KEY 凭据」即可。",
                ]))
            elif kind == "auto":
                self._console_auto_running = False
                if payload:
                    self._console_auto_done = True
                    self._apply_console_data(payload, silent=True)
                else:
                    self._schedule_console_auto_retry()
            elif kind == "provisioned":
                self._finish_console_flow()
                self._apply_provisioned(payload)
            elif kind == "projects":
                self._handle_projects(payload)
            elif kind == "project_created":
                state = self._picker_state
                if state:
                    state["select_id"] = payload["id"]
                    state["project"] = None          # 强制重新拉取该项目
                self._set_status(f"已创建项目「{payload['name']}」，正在刷新列表…")
                self._run_console_step(self._console_load_projects, "projects")
            elif kind == "credentials":
                self._handle_credentials(payload)
            elif kind in ("error", "publish_error", "console_error"):
                self._finish_console_flow()
                prefix = "同步到控制台失败：" if kind == "publish_error" else ""
                self._show_error(ValueError(
                    f"{prefix}{text}\n\n可以用“打开公钥目录”把公钥手动上传到控制台。"
                    if kind == "publish_error" else f"{prefix}{text}"
                ))
